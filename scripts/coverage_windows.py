#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Metricas por ventana del descubrimiento de publicadores.

Existe por dos errores concretos que hubo que corregir.

El primero: se compararon dos contadores distintos como si fueran la misma
serie. El contador vivo del crawler cuenta `agent_id` distintos sobre las fichas
ya procesadas; `publishers.jsonl` es un archivo congelado de una corrida
anterior. Uno avanzaba y el otro no, y al ponerlos juntos parecio que el numero
de entidades habia bajado. Nunca bajo.

El segundo: se leyo un acumulado como si fuera marginal. 4.194 sobre 17.320 no
dice cuantas entidades nuevas aporta la ficha numero 17.321; dice el promedio de
toda la historia. Y ademas mezclaba agentes, redes y desarrolladoras dentro de
"inmobiliarias".

De ahi que aca se separen explicitamente dos contadores que NO son lo mismo:

  RAW_PUBLISHER_IDENTITIES   -- `agent_id` distintos, tal como los emite Roomix
  CANONICAL_PUBLISHER_ENTITIES -- entidades tras unir los agent_id que son la
                                misma inmobiliaria bajo nombres equivalentes

El primero es siempre >= el segundo. Mezclarlos otra vez es el error que este
modulo esta para impedir.

KPI principal, medido por ventana y NUNCA usado como criterio de corte:

  NUEVAS ENTIDADES INMOBILIARIAS UNICAS POR 1.000 FICHAS

Cuenta INMOBILIARIA y oficina individual de franquicia. No cuenta agente, marca
generica sin oficina, desarrolladora, unknown ni garbage.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


d = _load("eretz_dedupe")
cw = _load("agency_crosswalk")
fr = _load("franchise_analysis")

# Tipos que cuentan como entidad inmobiliaria para el KPI.
CUENTA_COMO_AGENCIA = {"INMOBILIARIA", "OFICINA_FRANQUICIA"}


def tipo_de(nombre: str) -> str:
    """Tipo, distinguiendo la oficina de la marca.

    `RE/MAX Ultra` es una oficina real y cuenta. `RE/MAX` a secas es la marca y
    no cuenta: sumarla inflaria el padron con una entidad que no atiende a
    nadie.
    """
    base = cw.classify(nombre)
    if base != "RED_FRANQUICIA":
        return base
    _, sufijo = fr.brand_of(nombre)
    return "OFICINA_FRANQUICIA" if sufijo else "MARCA_GENERICA"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--ventana", type=int, default=1000)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    dd = Path(a.data_dir)

    obs = []
    for linea in (dd / "observations.jsonl").open(encoding="utf-8"):
        if linea.strip():
            obs.append(json.loads(linea))

    # Nombre dominante por agent_id: un mismo anunciante puede escribirse
    # distinto entre avisos, y la clave canonica no puede depender de cual
    # ficha se vio primero.
    nombres: dict[str, Counter] = defaultdict(Counter)
    for o in obs:
        if o.get("agent_id") and o.get("agent_name"):
            nombres[o["agent_id"]][o["agent_name"]] += 1
    dominante = {aid: c.most_common(1)[0][0] for aid, c in nombres.items()}
    canon = {aid: d.norm_name(n) for aid, n in dominante.items()}
    tipos = {aid: tipo_de(n) for aid, n in dominante.items()}

    filas = []
    raw_vistos: set[str] = set()
    canon_vistos: set[str] = set()
    canon_agencia: set[str] = set()
    por_tipo_visto: dict[str, set[str]] = defaultdict(set)

    for inicio in range(0, len(obs), a.ventana):
        trozo = obs[inicio:inicio + a.ventana]
        nuevos_raw = nuevos_canon = nuevas_agencias = 0
        nuevos_por_tipo: Counter = Counter()

        for o in trozo:
            aid = o.get("agent_id")
            if not aid:
                continue
            if aid not in raw_vistos:
                raw_vistos.add(aid)
                nuevos_raw += 1
            k = canon.get(aid, "")
            if not k:
                continue
            t = tipos.get(aid, "UNKNOWN")
            if k not in canon_vistos:
                canon_vistos.add(k)
                nuevos_canon += 1
            if k not in por_tipo_visto[t]:
                por_tipo_visto[t].add(k)
                nuevos_por_tipo[t] += 1
            if t in CUENTA_COMO_AGENCIA and k not in canon_agencia:
                canon_agencia.add(k)
                nuevas_agencias += 1

        filas.append({
            "ventana": f"{inicio + 1}-{inicio + len(trozo)}",
            "fichas": len(trozo),
            "nuevos_raw": nuevos_raw,
            "nuevas_canonical": nuevos_canon,
            "nuevas_inmobiliarias": nuevos_por_tipo.get("INMOBILIARIA", 0),
            "nuevas_oficinas_franquicia": nuevos_por_tipo.get("OFICINA_FRANQUICIA", 0),
            "nuevos_agentes": nuevos_por_tipo.get("AGENTE", 0),
            "nuevas_desarrolladoras": nuevos_por_tipo.get("DESARROLLADORA", 0),
            "nuevos_unknown": nuevos_por_tipo.get("UNKNOWN", 0),
            "kpi_agencias_por_1k": round(nuevas_agencias * 1000 / max(len(trozo), 1), 1),
            "acum_raw": len(raw_vistos),
            "acum_canonical": len(canon_vistos),
            "acum_agencias": len(canon_agencia),
        })

    print("### DESCUBRIMIENTO POR VENTANA ###", flush=True)
    print(f"  fichas procesadas:            {len(obs):,}", flush=True)
    print(f"  RAW_PUBLISHER_IDENTITIES:     {len(raw_vistos):,}   (agent_id distintos)", flush=True)
    print(f"  CANONICAL_PUBLISHER_ENTITIES: {len(canon_vistos):,}   (tras unir alias)", flush=True)
    print(f"  alias fusionados:             {len(raw_vistos) - len(canon_vistos):,}", flush=True)
    print(f"  ENTIDADES INMOBILIARIAS:      {len(canon_agencia):,}   (KPI)", flush=True)
    print(f"\n  desglose canonical por tipo:", flush=True)
    for t, s in sorted(por_tipo_visto.items(), key=lambda x: -len(x[1])):
        marca = " <- cuenta" if t in CUENTA_COMO_AGENCIA else ""
        print(f"    {t:20} {len(s):6,}{marca}", flush=True)

    print(f"\n  {'ventana':>14} {'fichas':>7} {'raw':>5} {'canon':>6} {'inmob':>6} "
          f"{'ofic':>5} {'agen':>5} {'unk':>5} {'KPI/1k':>7}", flush=True)
    for f in filas:
        print(f"  {f['ventana']:>14} {f['fichas']:>7} {f['nuevos_raw']:>5} "
              f"{f['nuevas_canonical']:>6} {f['nuevas_inmobiliarias']:>6} "
              f"{f['nuevas_oficinas_franquicia']:>5} {f['nuevos_agentes']:>5} "
              f"{f['nuevos_unknown']:>5} {f['kpi_agencias_por_1k']:>7}", flush=True)

    if a.out:
        Path(a.out).write_text(json.dumps(filas, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  series -> {a.out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
