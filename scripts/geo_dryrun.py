#!/usr/bin/env python
"""Que ciudad propondria la geografia canonica, sin escribir nada.

Deja la cadena lista hasta la barrera: la escritura de `ciudad` sobre
propiedades ya guardadas es una operacion productiva y no se hace desde aca.

Cada propuesta viaja con su procedencia. Un campo geografico sin procedencia no
se puede auditar despues, y la diferencia entre "la fuente lo publico" y
"nosotros lo dedujimos" es justamente lo que evita que una inferencia se
confunda con un dato.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from connectors.base import Connector, PropiedadNormalizada
from connectors.geografia import geografia

# La ciudad que la fuente publica en un campo propio es evidencia de la
# publicacion; la que sacamos del texto es una lectura nuestra. Se distinguen
# porque no valen lo mismo.
CONNECTORS_CON_CAMPO_PROPIO = {"wasi", "century21"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=r"D:\INMO CAPITAL\ERETZ_SUPABASE_RECONCILIATION_V2_20260827\PREINGESTION_REBUILD.sqlite3")
    parser.add_argument("--salida", default=r"D:\INMO CAPITAL\ERETZ_GEO")
    args = parser.parse_args()

    geo = geografia()
    conexion = sqlite3.connect(f"file:{Path(args.db).as_posix()}?mode=ro",
                               uri=True)
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    destino = salida / "CIUDAD_DRYRUN.jsonl"

    conteo: Counter = Counter()
    propuestas = 0
    with destino.open("w", encoding="utf-8") as archivo:
        for crudo, connector, hash_dedup in conexion.execute(
                "select row_json, connector, hash_dedup from rows"):
            fila = json.loads(crudo)
            if not (fila.get("ciudad") or fila.get("barrio")):
                conteo["sin ubicacion que normalizar"] += 1
                continue

            # Se invoca EXACTAMENTE la logica del pipeline, no una copia:
            # un backfill que decide distinto que la ingesta produce dos
            # verdades para el mismo dato.
            prop = PropiedadNormalizada(
                canonical_agency_id=str(fila.get("canonical_agency_id") or ""),
                source_listing_id=str(fila.get("source_listing_id") or ""),
                source_url=str(fila.get("source_url") or ""),
                connector=connector or "",
                ciudad=fila.get("ciudad"), barrio=fila.get("barrio"),
                provincia=fila.get("provincia"),
                latitud=fila.get("latitud"), longitud=fila.get("longitud"))
            Connector._resolver_geografia(prop)
            conteo[prop.extra.get("ciudad_match") or "SIN_UBICACION"] += 1
            if not prop.ciudad:
                continue
            origen = ("SOURCE_STRUCTURED"
                      if connector in CONNECTORS_CON_CAMPO_PROPIO
                      else "SOURCE_TEXT")
            propuestas += 1
            archivo.write(json.dumps({
                "hash_dedup": hash_dedup,
                "source_url": fila.get("source_url"),
                "publicado": {"ciudad": fila.get("ciudad"),
                              "barrio": fila.get("barrio"),
                              "provincia": fila.get("provincia")},
                "propuesto": {
                    "ciudad": prop.ciudad,
                    "barrio": prop.barrio,
                    "provincia": prop.provincia,
                    "locality_id": prop.extra.get("localidad_id"),
                },
                "evidencia": {
                    "match": prop.extra.get("ciudad_match"),
                    "evidence_origin": origen,
                    "provenance": prop.extra.get("ciudad_provenance"),
                    "campo_de_origen": prop.extra.get("ciudad_campo_de_origen"),
                    "source": prop.extra.get("localidad_fuente"),
                },
                "writes": False,
            }, ensure_ascii=False) + "\n")

    cambia = 0
    igual = 0
    for linea in destino.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        fila = json.loads(linea)
        if fila["publicado"]["ciudad"] == fila["propuesto"]["ciudad"]:
            igual += 1
        else:
            cambia += 1

    resumen = {
        "filas_evaluadas": sum(conteo.values()),
        "por_resolucion": dict(conteo),
        "propuestas": propuestas,
        "propuestas_que_corrigen_el_texto": cambia,
        "propuestas_que_confirman_el_texto": igual,
        "database_writes": 0,
        "artefacto": destino.name,
    }
    (salida / "CIUDAD_DRYRUN_SUMMARY.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
