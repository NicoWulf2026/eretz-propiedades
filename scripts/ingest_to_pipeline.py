#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Adaptación y dry-run de propiedades normalizadas al pipeline ERETZ.

Produce filas para `internal_scraping.propiedades_raw`. El consumidor de
escritura es `scripts/property_write_canary.py`; luego el pipeline continúa
hacia staging y publicación. Este script sólo adapta y valida en memoria.

No conecta a una base ni carga configuración. El escritor directo sin rol y
prueba de ownership fue retirado; `--escribir` falla antes de leer entrada.
El canary usa estos mismos adapters y agrega los gates transaccionales.

La idempotencia del consumidor depende del índice único sobre hash_dedup.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from connectors.base import (MONEDAS_VALIDAS, OPERACIONES_VALIDAS,  # noqa: E402
                             TIPOS_VALIDOS, normalizar_url)
from scripts.agency_web_discovery import es_portal  # noqa: E402

# Las columnas son las del pipeline, no una lista propia.
RAW_COLUMNS = [
    "scraping_run_item_id", "inmobiliaria_id", "hash_dedup", "titulo",
    "descripcion", "precio", "moneda", "superficie_total", "superficie_cubierta",
    "tipo_propiedad", "operacion", "url", "url_normalizada", "direccion_raw",
    "barrio", "ciudad", "provincia", "pais", "latitud", "longitud", "imagenes",
    "datos_extra", "status",
]


def a_fila_raw(p: dict) -> dict:
    """Traduce la representacion normalizada al contrato de propiedades_raw.

    Lo que no tiene columna va a datos_extra, que ya es JSONB. No se agrega
    ninguna columna: el pipeline ignoraria lo que no conoce.
    """
    extra = dict(p.get("extra") or {})
    extra.update({
        "source_listing_id": p.get("source_listing_id"),
        "connector": p.get("connector"),
        "canonical_agency_id": p.get("canonical_agency_id"),
        "fingerprint": p.get("fingerprint"),
        "provenance": p.get("provenance"),
        "ambientes": p.get("ambientes"),
        "dormitorios": p.get("dormitorios"),
        "banos": p.get("banos"),
        "scraped_at": p.get("scraped_at"),
    })
    return {
        "scraping_run_item_id": None,
        "inmobiliaria_id": p.get("inmobiliaria_id"),
        "hash_dedup": p.get("hash_dedup"),
        "titulo": p.get("titulo"),
        "descripcion": p.get("descripcion"),
        "precio": p.get("precio"),
        "moneda": p.get("moneda"),
        "superficie_total": p.get("superficie_total"),
        "superficie_cubierta": p.get("superficie_cubierta"),
        "tipo_propiedad": p.get("tipo_propiedad"),
        "operacion": p.get("operacion") or "desconocida",
        "url": p.get("source_url"),
        "url_normalizada": normalizar_url(p.get("source_url")),
        "direccion_raw": p.get("direccion"),
        "barrio": p.get("barrio"),
        "ciudad": p.get("ciudad"),
        "provincia": p.get("provincia"),
        "pais": "Argentina",
        "latitud": p.get("latitud"),
        "longitud": p.get("longitud"),
        "imagenes": json.dumps(p.get("imagenes") or [], ensure_ascii=False),
        "datos_extra": json.dumps(extra, ensure_ascii=False, default=str),
        "status": "raw",
    }


def rechazos(p: dict) -> list[str]:
    """Motivos por los que la base rechazaria la fila, comprobados antes.

    Vale la pena mirarlos aca: una constraint violada a mitad del lote aborta
    la transaccion entera y hace perder trabajo bueno junto con el malo.
    """
    r = []
    if not p.get("hash_dedup"):
        r.append("sin hash_dedup")
    iid = p.get("inmobiliaria_id")
    if iid is None:
        r.append("sin inmobiliaria_id")
    elif isinstance(iid, bool) or not isinstance(iid, int) or not (0 < iid <= 2_147_483_647):
        # La columna es INTEGER. Un id fuera de rango no da error de datos:
        # aborta la transaccion entera y se lleva puesto el lote completo.
        r.append("inmobiliaria_id fuera del rango INTEGER")
    if not p.get("source_url"):
        r.append("sin url")
    else:
        parsed = urllib.parse.urlparse(p['source_url'])
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username is not None:
            r.append('url invalida')
        elif es_portal(p['source_url']):
            r.append('fuente no oficial')
    if p.get("moneda") and p["moneda"] not in MONEDAS_VALIDAS:
        r.append("moneda invalida")
    op = p.get("operacion") or "desconocida"
    if op not in OPERACIONES_VALIDAS:
        r.append("operacion invalida")
    if p.get("tipo_propiedad") and p["tipo_propiedad"] not in TIPOS_VALIDOS:
        r.append("tipo invalido")
    # Raw preserves optional source values for the validator to accept or
    # withhold field-by-field. A bad price must not erase a real property.
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", required=True, help="properties_runN.jsonl")
    ap.add_argument("--escribir", action="store_true",
                    help="sin esto es dry run y no toca la base")
    ap.add_argument("--lote", type=int, default=200)
    ap.add_argument("--limite", type=int, default=0)
    a = ap.parse_args()
    if a.escribir:
        print('La escritura directa sin rol/ownership fue retirada. '
              'Usar scripts/property_write_canary.py con sus gates; no se leyó configuración ni se escribió.')
        return 2

    props = [json.loads(line) for line in Path(a.entrada).open(encoding="utf-8") if line.strip()]
    if a.limite:
        props = props[:a.limite]

    aptas, descartadas = [], Counter()
    for p in props:
        motivos = rechazos(p)
        if motivos:
            descartadas[motivos[0]] += 1
            continue
        aptas.append(p)

    print("### CARGA AL PIPELINE ERETZ ###")
    print(f"  entrada:            {a.entrada}")
    print(f"  propiedades:        {len(props):,}")
    print(f"  aptas:              {len(aptas):,}")
    print(f"  descartadas:        {sum(descartadas.values()):,} {dict(descartadas)}")
    print(f"  hash unicos:        {len({p['hash_dedup'] for p in aptas}):,}")
    print(f"  modo:               {'ESCRITURA' if a.escribir else 'DRY RUN'}")

    if not a.escribir:
        muestra = a_fila_raw(aptas[0]) if aptas else {}
        print("\n  fila de ejemplo (columnas reales de propiedades_raw):")
        for c in RAW_COLUMNS:
            v = muestra.get(c)
            print(f"    {c:22} {str(v)[:70]}")
        print("\n  dry run: no se escribio nada.")
        return 0

if __name__ == "__main__":
    sys.exit(main())
