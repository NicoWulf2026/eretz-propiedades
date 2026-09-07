#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Una base lista para servir la API, armada con datos locales reales.

Produccion no responde y el frontend se esta construyendo igual. Sin esto,
Codex tiene dos opciones malas: esperar, o construir contra mocks y descubrir
en la integracion que la mitad de los campos son null.

Esta snapshot es la tercera opcion: las 58.427 propiedades reales con la forma
EXACTA que va a servir la API, indexadas para las consultas que el frontend
hace de verdad -filtro por operacion, por tipo, por rango de precio, por area
de busqueda-.

**Es derivada y desechable.** Se reconstruye entera desde los artefactos
locales, no se edita a mano y no es fuente de verdad de nada. Si el resultado
no gusta, se arregla el generador y se vuelve a correr.

No escribe en ninguna base productiva.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.api_contract import CONTRATO_API_VERSION, fila_de_api  # noqa: E402
from scripts.preingestion_manifest import (base_canonica,  # noqa: E402
                                           exigir_base_vigente)

SNAPSHOT_VERSION = "api_snapshot_v1"

ESQUEMA = """
create table if not exists propiedades (
    id text primary key,
    agency_id text not null,
    source_url text not null,
    titulo text,
    descripcion text,
    operacion text,
    tipo_propiedad text,
    precio real,
    moneda text,
    ambientes integer,
    dormitorios integer,
    banos integer,
    superficie_total real,
    superficie_cubierta real,
    imagenes_n integer not null default 0,
    latitud real,
    longitud real,
    localidad text,
    localidad_id text,
    municipio text,
    departamento text,
    provincia text,
    barrio text,
    area_nivel text not null,
    area_nombre text,
    geo_estado text,
    alcances text not null,
    documento text not null
);
-- Los indices salen de las consultas que el frontend hace, no de "por si
-- acaso": listado filtrado por operacion y tipo, rango de precio, y busqueda
-- por area. Cada uno se justifica con una consulta real o no va.
create index if not exists ix_operacion on propiedades(operacion);
create index if not exists ix_tipo on propiedades(tipo_propiedad);
create index if not exists ix_precio on propiedades(moneda, precio);
create index if not exists ix_area on propiedades(area_nivel, area_nombre);
create index if not exists ix_localidad on propiedades(localidad);
create index if not exists ix_agencia on propiedades(agency_id);
"""


def _leer_jsonl(ruta: Path, clave: str = "hash_dedup") -> dict[str, dict[str, Any]]:
    fuera: dict[str, dict[str, Any]] = {}
    if not ruta.exists():
        return fuera
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if linea.strip():
            fila = json.loads(linea)
            if fila.get(clave):
                fuera[fila[clave]] = fila
    return fuera


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(base_canonica()))
    ap.add_argument("--gate",
                    default=str(base_canonica().parent / "PROPERTY_QUALITY_GATE.jsonl"))
    ap.add_argument("--cobertura",
                    default=r"D:\INMO CAPITAL\ERETZ_GEO\GEO_COVERAGE_AUDIT.jsonl")
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\ERETZ_API_CONTRACT")
    args = ap.parse_args()
    exigir_base_vigente(args.db)

    geo = _leer_jsonl(Path(args.cobertura))
    gate = _leer_jsonl(Path(args.gate))

    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    destino = salida / "ERETZ_API_SNAPSHOT.sqlite3"
    # Se reconstruye entera: es derivada, no acumulativa.
    destino.unlink(missing_ok=True)

    origen = sqlite3.connect(f"file:{Path(args.db).as_posix()}?mode=ro", uri=True)
    api = sqlite3.connect(destino)
    api.executescript(ESQUEMA)

    filas = 0
    for (crudo,) in origen.execute(
            "select row_json from rows where status = 'CANDIDATE'"):
        cruda = json.loads(crudo)
        hash_dedup = cruda.get("hash_dedup")
        g = geo.get(hash_dedup)
        documento = fila_de_api(cruda, g, (gate.get(hash_dedup) or {}).get("alcances") or [])
        area = documento["geo"]["area_busqueda"] or {}
        api.execute(
            "insert or replace into propiedades values "
            "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (documento["id"], documento["agency_id"], documento["source_url"],
             documento["titulo"], documento["descripcion"], documento["operacion"],
             documento["tipo_propiedad"], documento["precio"], documento["moneda"],
             documento["ambientes"], documento["dormitorios"], documento["banos"],
             documento["superficie_total"], documento["superficie_cubierta"],
             len(documento["imagenes"]), documento["latitud"], documento["longitud"],
             documento["geo"]["localidad"]["nombre"],
             documento["geo"]["localidad"].get("id"),
             documento["geo"]["municipio"]["nombre"],
             documento["geo"]["departamento"]["nombre"],
             documento["geo"]["provincia"]["nombre"],
             documento["geo"]["barrio"]["nombre"],
             area.get("nivel") or "SIN_AREA",
             area.get("nombre"),
             documento["geo"].get("estado"),
             json.dumps(documento["alcances"], ensure_ascii=False),
             json.dumps(documento, ensure_ascii=False)))
        filas += 1
    api.commit()

    resumen = {
        "snapshot_version": SNAPSHOT_VERSION,
        "contrato_api_version": CONTRATO_API_VERSION,
        "propiedades": filas,
        "generada_en": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "origen": str(Path(args.db)),
        "artefacto": destino.name,
        "database_writes": 0,
    }
    api.close()
    (salida / "ERETZ_API_SNAPSHOT_SUMMARY.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
