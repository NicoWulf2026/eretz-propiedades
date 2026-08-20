#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Bucle de deltas con cierre determinista sobre el universo de publicadores.

Roomix rota ~16% de sus avisos cada tres dias, y los hashes nuevos son
genuinamente nuevos: se comparo el sufijo de cada URL nueva contra todas las
observadas y no hubo una sola coincidencia. Por lo tanto "repetir hasta que una
pasada no traiga URLs nuevas" describe un bucle que no termina: cada pasada dura
horas y mientras corre aparecen miles de avisos mas.

El cierre se define entonces sobre el universo que esta mision investiga, que es
el de entidades publicadoras inmobiliarias. NO es convergencia estadistica: se
siguen enumerando y procesando REALMENTE todos los avisos nuevos de cada delta.
Lo unico que cambia es la pregunta que decide el corte, de "aparecieron avisos
nuevos" a "esos avisos revelaron alguna inmobiliaria u oficina que no
conociamos".

Condicion de cierre, sin margen interpretativo:

  DOS deltas consecutivos completos con, simultaneamente,
    NEW_INMOBILIARIA        = 0
    NEW_OFICINA_FRANQUICIA  = 0
    UNKNOWN nuevos que puedan ser inmobiliaria = 0

Un delta puede traer miles de avisos, cientos de agent_id, agentes y
desarrolladoras nuevas, y aun asi contar como cero: ninguna de esas categorias
es una entidad inmobiliaria canonica.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


rd = _load("roomix_agency_discovery")
delta = _load("roomix_delta")
leer_jsonl = delta.leer_jsonl
d = _load("eretz_dedupe")
cwin = _load("coverage_windows")

OBJETIVO = ("INMOBILIARIA", "OFICINA_FRANQUICIA")


def puede_ser_inmobiliaria(nombre: str) -> bool:
    """Un UNKNOWN que todavia podria resolverse como inmobiliaria.

    Se cuenta como pendiente si el nombre tiene sustancia suficiente para que
    mas evidencia lo resuelva. Un nombre de una sola palabra corta o basura no
    va a convertirse en una inmobiliaria por ver mas avisos suyos, asi que no
    bloquea el cierre.
    """
    basura, _ = rd_is_garbage(nombre)
    if basura:
        return False
    toks = d.norm_name(nombre).split()
    return len(toks) >= 2 and sum(len(t) for t in toks) >= 8


def rd_is_garbage(nombre: str):
    cw = _load("agency_crosswalk")
    return cw.is_garbage(nombre)


def estado(obs_p: Path) -> tuple[dict[str, str], set[str], set[str]]:
    """Entidades canonicas actuales: clave -> tipo. Ademas raw ids y URLs."""
    nombres: dict[str, Counter] = defaultdict(Counter)
    urls: set[str] = set()
    for o in leer_jsonl(obs_p):
        u = o.get("url")
        if u:
            urls.add(u)
        aid, nom = o.get("agent_id"), o.get("agent_name")
        if aid and nom:
            nombres[aid][nom] += 1
    canon: dict[str, str] = {}
    for aid, c in nombres.items():
        nom = c.most_common(1)[0][0]
        k = d.norm_name(nom)
        if not k:
            continue
        t = cwin.tipo_de(nom)
        # Si dos agent_id caen en la misma clave, gana el tipo mas especifico.
        if k not in canon or (canon[k] == "UNKNOWN" and t != "UNKNOWN"):
            canon[k] = t
    return canon, set(nombres), urls


def auditar(antes: dict[str, str], despues: dict[str, str],
            nombres_por_clave: dict[str, str]) -> dict:
    nuevas = {k: t for k, t in despues.items() if k not in antes}
    por_tipo = Counter(nuevas.values())
    unk_pendientes = sum(
        1 for k, t in nuevas.items()
        if t == "UNKNOWN" and puede_ser_inmobiliaria(nombres_por_clave.get(k, k)))
    return {
        "canonical_nuevas": len(nuevas),
        "NEW_INMOBILIARIA": por_tipo.get("INMOBILIARIA", 0),
        "NEW_OFICINA_FRANQUICIA": por_tipo.get("OFICINA_FRANQUICIA", 0),
        "NEW_AGENTE": por_tipo.get("AGENTE", 0),
        "NEW_DESARROLLADORA": por_tipo.get("DESARROLLADORA", 0),
        "NEW_MARCA_GENERICA": por_tipo.get("MARCA_GENERICA", 0),
        "NEW_UNKNOWN": por_tipo.get("UNKNOWN", 0),
        "NEW_UNKNOWN_POTENCIALMENTE_INMOBILIARIA": unk_pendientes,
        "NEW_TARGET_ENTITIES": por_tipo.get("INMOBILIARIA", 0) + por_tipo.get("OFICINA_FRANQUICIA", 0),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--rate", type=float, default=3.0)
    ap.add_argument("--max-deltas", type=int, default=8)
    a = ap.parse_args()
    dd = Path(a.data_dir)
    obs_p = dd / "observations.jsonl"
    bitacora_p = dd / "delta_audit.jsonl"

    f = rd.Fetcher(rate_per_s=a.rate)
    ceros = 0

    for n in range(1, a.max_deltas + 1):
        print(f"\n### DELTA {n} ###", flush=True)
        t_enum = time.strftime("%Y-%m-%dT%H:%M:%S")
        antes, raw_antes, urls_antes = estado(obs_p)

        shards = rd.property_urls(f)
        actual = list(dict.fromkeys(u for v in shards.values() for u in v))
        nuevas = [u for u in actual if u not in urls_antes]
        desaparecidas = len(urls_antes - set(actual))
        print(f"  enumeracion:    {t_enum}", flush=True)
        print(f"  universo:       {len(actual):,}", flush=True)
        print(f"  nuevas:         {len(nuevas):,}", flush=True)
        print(f"  desaparecidas:  {desaparecidas:,}", flush=True)

        st = Counter()
        if nuevas:
            st = delta.procesar(f, nuevas, obs_p, f"delta{n}")

        despues, raw_despues, _ = estado(obs_p)
        # Nombre representativo de cada clave nueva, para juzgar los UNKNOWN.
        nombres_clave: dict[str, str] = {}
        for o in leer_jsonl(obs_p):
            if o.get("agent_name"):
                k = d.norm_name(o["agent_name"])
                nombres_clave.setdefault(k, o["agent_name"])

        aud = auditar(antes, despues, nombres_clave)
        aud.update({
            "delta": n, "enumerado_en": t_enum,
            "urls_universo": len(actual), "urls_nuevas": len(nuevas),
            "urls_desaparecidas": desaparecidas, "urls_procesadas": sum(st.values()),
            "raw_ids_nuevos": len(raw_despues - raw_antes),
            "aliases_nuevos": (len(raw_despues) - len(despues)) - (len(raw_antes) - len(antes)),
            "resultado_fetch": dict(st),
            "errores_fetch": dict(f.stats),
            "terminado_en": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        with bitacora_p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(aud, ensure_ascii=False) + "\n")

        print(f"  raw ids nuevos:          {aud['raw_ids_nuevos']:,}", flush=True)
        print(f"  canonical nuevas:        {aud['canonical_nuevas']:,}", flush=True)
        print(f"  NEW_INMOBILIARIA:        {aud['NEW_INMOBILIARIA']}", flush=True)
        print(f"  NEW_OFICINA_FRANQUICIA:  {aud['NEW_OFICINA_FRANQUICIA']}", flush=True)
        print(f"  NEW_AGENTE:              {aud['NEW_AGENTE']}", flush=True)
        print(f"  NEW_DESARROLLADORA:      {aud['NEW_DESARROLLADORA']}", flush=True)
        print(f"  NEW_UNKNOWN:             {aud['NEW_UNKNOWN']} "
              f"(potencialmente inmobiliarias: {aud['NEW_UNKNOWN_POTENCIALMENTE_INMOBILIARIA']})",
              flush=True)
        print(f"  NEW_TARGET_ENTITIES:     {aud['NEW_TARGET_ENTITIES']}", flush=True)

        cerrado = (aud["NEW_INMOBILIARIA"] == 0 and aud["NEW_OFICINA_FRANQUICIA"] == 0
                   and aud["NEW_UNKNOWN_POTENCIALMENTE_INMOBILIARIA"] == 0)
        ceros = ceros + 1 if cerrado else 0
        print(f"  deltas consecutivos en cero: {ceros}/2", flush=True)
        if ceros >= 2:
            print("\n  CIERRE: dos deltas consecutivos sin entidades inmobiliarias nuevas.",
                  flush=True)
            return 0

    print("\n  se agotaron los deltas permitidos sin alcanzar el cierre.", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
