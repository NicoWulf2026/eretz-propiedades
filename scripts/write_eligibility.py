#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Que propiedades pueden escribirse hoy en propiedades_raw, y cuales no.

La regla no admite matices: una propiedad solo entra a la base si su
inmobiliaria tiene `eretz_id` real. Un id sintetico, derivado o temporal
produciria filas que no pertenecen a ninguna inmobiliaria existente, y ese error
no se nota al insertar: aparece meses despues, cuando alguien une las tablas y
faltan agencias.

Las que no lo tienen quedan AGENCY_ID_PENDING. Se descubren, se normalizan, se
validan y viven en los artefactos; simplemente no se escriben todavia.

Solo lee artefactos. No toca la base ni la red.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from connectors.base import calcular_hash_dedup  # noqa: E402

ELEGIBLE = "DB_WRITE_ELIGIBLE"
PENDIENTE = "AGENCY_ID_PENDING"
NO_ES_FICHA = "NO_ES_UNA_FICHA"

# Defensa en profundidad: aunque el connector ya filtre, lo que llega a la base
# se revisa otra vez. Una pagina de busqueda con filtros no es una propiedad, y
# entra facil porque la ruta de listado se llama igual que las fichas.
import re as _re
_BUSQUEDA = _re.compile(r"/(buscar|busqueda|search|filtrar|filtro|resultados?)", _re.I)


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
    ap.add_argument("--entradas", nargs="+", required=True)
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\DB_WRITE_ELIGIBLE.jsonl")
    a = ap.parse_args()

    padron = {}
    for d in leer(Path(a.data_dir) / "agency_web_directory.jsonl"):
        eid = d.get("eretz_id")
        if str(eid).isdigit():
            padron[d["canonical_agency_id"]] = int(eid)

    props: list[dict] = []
    for e in a.entradas:
        props.extend(leer(Path(e)))
    if not props:
        print("sin propiedades")
        return 1

    elegibles, pendientes, descartadas = [], [], []
    vistos_hash = set()
    for p in props:
        url = p.get("source_url") or ""
        if "?" in url or _BUSQUEDA.search(url):
            descartadas.append(p)
            continue
        real = padron.get(p.get("canonical_agency_id"))
        if real is None:
            pendientes.append(p)
            continue
        q = dict(p)
        q["inmobiliaria_id"] = real
        # El hash depende del id, asi que se recalcula con el real: el del
        # artefacto se produjo con el sustituto del canary y no coincidiria con
        # lo que produce produccion.
        q["hash_dedup"] = calcular_hash_dedup(real, p.get("source_url"))
        if q["hash_dedup"] in vistos_hash:
            # Dos urls que normalizan igual son la misma propiedad. Escribir las
            # dos no crearia un duplicado -el indice unico lo impide- pero haria
            # que la reconciliacion no cierre.
            continue
        vistos_hash.add(q["hash_dedup"])
        q["db_write_status"] = ELEGIBLE
        elegibles.append(q)

    Path(a.salida).write_text(
        "\n".join(json.dumps(q, ensure_ascii=False) for q in elegibles),
        encoding="utf-8")

    n = len(props)
    print("### ELEGIBILIDAD PARA ESCRITURA EN propiedades_raw ###")
    print(f"  propiedades analizadas:     {n:,}")
    print(f"  {ELEGIBLE:24}    {len(elegibles):,}  ({len(elegibles)/n*100:.1f}%)")
    print(f"  {PENDIENTE:24}    {len(pendientes):,}  ({len(pendientes)/n*100:.1f}%)")
    print(f"  {NO_ES_FICHA:24}    {len(descartadas):,}  ({len(descartadas)/n*100:.1f}%)")
    print(f"\n  agencias elegibles:         "
          f"{len({q['canonical_agency_id'] for q in elegibles}):,}")
    print(f"  agencias sin eretz_id:      "
          f"{len({p.get('canonical_agency_id') for p in pendientes}):,}")
    print(f"  hash unicos entre elegibles:"
          f"{len({q['hash_dedup'] for q in elegibles}):,}")
    print(f"\n  por connector (elegibles):  "
          f"{dict(Counter(q.get('connector') for q in elegibles))}")
    print(f"  por connector (pendientes): "
          f"{dict(Counter(p.get('connector') for p in pendientes))}")
    print(f"\n  artefacto -> {a.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
