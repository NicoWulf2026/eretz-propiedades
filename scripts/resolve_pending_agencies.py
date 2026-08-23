#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Resolver las agencias que no tienen eretz_id.

Sus propiedades estan descubiertas y normalizadas pero no pueden escribirse:
sin id real no pertenecen a ninguna inmobiliaria existente.

El criterio es deliberadamente conservador. No hay fusion automatica por
parecido de nombre: una coincidencia debil que asigna el inventario de una
inmobiliaria a otra es un error que nadie detecta despues, porque las
propiedades quedan bien formadas y en la agencia equivocada.

Estados:
  EXISTING_RESOLVED    hay una unica candidata con evidencia fuerte
  AMBIGUOUS            varias candidatas, o una sola con evidencia debil
  NEW_AGENCY_REQUIRED  ninguna candidata: es una inmobiliaria que ERETZ no tiene
  INSUFFICIENT         no hay ni siquiera nombre utilizable

Solo lee artefactos. No escribe en la base ni pide nada a la red.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

EXISTING = "EXISTING_RESOLVED"
AMBIGUA = "AMBIGUOUS"
NUEVA = "NEW_AGENCY_REQUIRED"
INSUFICIENTE = "INSUFFICIENT"

RUIDO = {"inmobiliaria", "propiedades", "negocios", "inmobiliarios",
         "inmobiliario", "bienes", "raices", "estate", "real", "servicios",
         "grupo", "estudio", "sa", "srl", "sas", "ltda", "cia", "y", "de",
         "del", "la", "el", "los", "las"}

# El nombre de la red NO identifica a la oficina. Sin sacarlo, "Century 21 Di
# Girolamo" coincide con "Century 21 MM Real Estate" por compartir "century" y
# "21", y adjudicarle el inventario de una oficina a otra es el error mas caro
# que puede cometer esta resolucion.
FRANQUICIAS = {"century", "21", "remax", "re", "max", "keller", "williams",
               "coldwell", "banker", "century21", "kw", "engel", "volkers",
               "sothebys", "century-21"}
RUIDO |= FRANQUICIAS


def normalizar(nombre: str) -> str:
    t = unicodedata.normalize("NFKD", str(nombre or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def distintivos(nombre: str) -> set[str]:
    """Las palabras que de verdad identifican a la inmobiliaria.

    Sin sacar el ruido, "Lopez Propiedades" y "Garcia Propiedades" comparten la
    mitad del nombre y cualquier medida de similitud las acerca.
    """
    return {p for p in normalizar(nombre).split() if len(p) >= 3 and p not in RUIDO}


def distintivos_crudos(nombre: str) -> set[str]:
    return {p for p in normalizar(nombre).split() if len(p) >= 2}


def host(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", url or "").split("/")[0].lower()


def leer(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    out = []
    for l in ruta.open(encoding="utf-8"):
        l = l.strip()
        if not l:
            continue
        try:
            out.append(json.loads(l))
        except ValueError:
            continue
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifiesto",
                    default=r"D:\INMO CAPITAL\AGENCY_ID_PENDING_MANIFEST.jsonl")
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--salida",
                    default=r"D:\INMO CAPITAL\AGENCY_ID_RESOLUTION.jsonl")
    a = ap.parse_args()
    dd = Path(a.data_dir)

    pendientes = leer(Path(a.manifiesto))
    directorio = leer(dd / "agency_web_directory.jsonl")
    crosswalk = {}
    for r in leer(dd / "crosswalk_final.jsonl"):
        k = r.get("stable_id") or r.get("canonical_agency_id")
        if k:
            crosswalk[k] = r

    # Indices de las agencias que SI tienen eretz_id.
    por_nombre: dict[str, list] = defaultdict(list)
    por_host: dict[str, list] = defaultdict(list)
    conocidas = []
    for d in directorio:
        eid = d.get("eretz_id")
        if not str(eid).isdigit():
            continue
        ficha = {"eretz_id": int(eid),
                 "canonical_agency_id": d.get("canonical_agency_id"),
                 "nombre": d.get("canonical_name"),
                 "dominio": d.get("selected_domain") or d.get("current_eretz_web"),
                 "province": d.get("province")}
        conocidas.append(ficha)
        por_nombre[normalizar(ficha["nombre"])].append(ficha)
        h = host(ficha["dominio"])
        if h:
            por_host[h].append(ficha)

    print("### RESOLUCION DE AGENCIAS SIN eretz_id ###")
    print(f"  pendientes:            {len(pendientes)}")
    print(f"  agencias con eretz_id: {len(conocidas):,}\n", flush=True)

    filas = []
    for p in pendientes:
        nombre = p.get("agency_name") or ""
        dominio = p.get("official_domain") or ""
        h = host(dominio)
        toks = distintivos(nombre)
        fila = {
            "canonical_agency_id": p.get("canonical_agency_id"),
            "agency_name": nombre,
            "official_domain": dominio,
            "connector": p.get("connector"),
            "propiedades_descubiertas": p.get("propiedades_descubiertas"),
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        if not toks:
            filas.append({**fila, "estado": INSUFICIENTE,
                          "motivo": "el nombre no tiene ninguna palabra distintiva"})
            continue

        # Dos oficinas de la misma red no son la misma inmobiliaria. Si el
        # nombre solo se distingue por la red, no hay con que resolver.
        franquicia = bool(distintivos_crudos(nombre) & FRANQUICIAS)
        candidatas, evidencia = [], {}

        # 1. El dominio es la evidencia mas fuerte: nadie comparte sitio con
        #    otra inmobiliaria salvo en plataformas, que se excluyen aparte.
        compartido = len(por_host.get(h, [])) > 3
        if h and not compartido:
            for c in por_host[h]:
                candidatas.append(c)
                evidencia.setdefault(c["eretz_id"], []).append("mismo_dominio")

        # 2. Nombre normalizado exacto.
        for c in por_nombre.get(normalizar(nombre), []):
            candidatas.append(c)
            evidencia.setdefault(c["eretz_id"], []).append("nombre_exacto")

        # 3. Todas las palabras distintivas contenidas, en ambos sentidos.
        if not candidatas:
            for c in conocidas:
                otros = distintivos(c["nombre"])
                if not otros:
                    continue
                if toks <= otros or otros <= toks:
                    candidatas.append(c)
                    evidencia.setdefault(c["eretz_id"], []).append(
                        "palabras_distintivas_contenidas")

        unicas = {c["eretz_id"]: c for c in candidatas}
        if not unicas:
            estado = NUEVA
            motivo = ("ninguna inmobiliaria de ERETZ coincide por dominio ni por "
                      "nombre: es una agencia que el padron no tiene")
        elif len(unicas) > 1:
            estado = AMBIGUA
            motivo = f"{len(unicas)} candidatas; no se elige por parecido"
        else:
            eid = next(iter(unicas))
            ev = set(evidencia.get(eid, []))
            fuerte = bool(ev & {"mismo_dominio", "nombre_exacto"})
            estado = EXISTING if fuerte else AMBIGUA
            motivo = ("evidencia fuerte: " + ", ".join(sorted(ev)) if fuerte else
                      "unica candidata pero solo por parecido de nombre")
        if franquicia and estado == AMBIGUA and not any(
                "mismo_dominio" in (evidencia.get(c["eretz_id"]) or [])
                for c in unicas.values()):
            estado = NUEVA
            motivo = ("es una oficina de una red: las candidatas solo coinciden "
                      "en el nombre de la franquicia, que no identifica oficina")
        fila.update({
            "estado": estado, "motivo": motivo,
            "candidatas": [{"eretz_id": c["eretz_id"], "nombre": c["nombre"],
                            "dominio": c["dominio"],
                            "evidencia": sorted(set(evidencia.get(c["eretz_id"], [])))}
                           for c in unicas.values()][:5],
            "dominio_compartido": compartido,
        })
        filas.append(fila)

    Path(a.salida).write_text(
        "\n".join(json.dumps(f, ensure_ascii=False) for f in filas), encoding="utf-8")

    print("  resultado:")
    for k, v in Counter(f["estado"] for f in filas).most_common():
        props = sum(f.get("propiedades_descubiertas") or 0
                    for f in filas if f["estado"] == k)
        print(f"    {k:22} {v:4}  ({props:,} propiedades)")
    res = [f for f in filas if f["estado"] == EXISTING]
    if res:
        print("\n  resueltas con evidencia fuerte:")
        for f in res[:10]:
            c = f["candidatas"][0]
            print(f"    {f['agency_name'][:32]:32} -> eretz_id {c['eretz_id']} "
                  f"({', '.join(c['evidencia'])})")
    print(f"\n  artefacto -> {a.salida}")
    print("  Ninguna resolucion se aplica automaticamente: liberar sus "
          "propiedades requiere confirmar el id.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
