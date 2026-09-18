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
import os
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.api_contract import CONTRATO_API_VERSION, fila_de_api  # noqa: E402
from scripts.prepare_api_v2_snapshot import _publish_no_clobber  # noqa: E402


def publish_snapshot(temporary: Path, output: Path, *, replace: bool = False) -> None:
    """Replacement must be explicit, including a destination created mid-build."""
    if replace:
        os.replace(temporary, output)
    else:
        _publish_no_clobber(temporary, output)
from scripts.property_contract import alcances  # noqa: E402
from scripts.image_quality import is_known_page_asset  # noqa: E402
from scripts.plan_de_escritura import agencias_con_web_ajena  # noqa: E402
from scripts.property_freshest import (CAMPOS_FUSIONABLES,  # noqa: E402
                                       fusionar, mas_frescas)
from scripts.preingestion_manifest import (base_canonica,  # noqa: E402
                                           exigir_base_vigente)

SNAPSHOT_VERSION = "api_snapshot_v4"

# Review threshold only: shared building renders can occur in many listings.
# Exclusion requires an independent page-asset signal, never frequency alone.
FICHAS_PARA_SER_COMPARTIDA = 5

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
-- Compuesto porque el filtro mas frecuente del listado son los dos juntos.
-- Medido: con `ix_operacion` solo, operacion+tipo tardaba 167 ms porque
-- filtraba 42.536 filas por el segundo campo.
create index if not exists ix_operacion_tipo
    on propiedades(operacion, tipo_propiedad);
create index if not exists ix_precio on propiedades(moneda, precio);
create index if not exists ix_area on propiedades(area_nivel, area_nombre);
create index if not exists ix_localidad on propiedades(localidad);
create index if not exists ix_agencia on propiedades(agency_id);

-- Busqueda por texto. Sin esto, `/buscar` hace un scan completo: 409 ms
-- medidos sobre las 58.427, que para una caja de busqueda es demasiado.
-- FTS5 viene con SQLite y no agrega dependencias.
create virtual table if not exists busqueda using fts5(
    id unindexed, titulo, descripcion, barrio, area_nombre,
    tokenize = "unicode61 remove_diacritics 2"
);
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
    ap.add_argument("--directorio",
                    default=str(Path("D:/INMO CAPITAL/agency_platform_directory.jsonl")))
    ap.add_argument('--paquetes', type=Path,
                    default=Path(r'D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827\agencies'))
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\ERETZ_API_CONTRACT")
    ap.add_argument('--replace-derived', action='store_true',
                    help='replace an existing derived snapshot atomically after successful construction')
    args = ap.parse_args()
    salida = Path(args.salida)
    destino = salida / 'ERETZ_API_SNAPSHOT.sqlite3'
    if Path(args.db).resolve() == destino.resolve():
        ap.error('output must differ from source; the source is immutable')
    if destino.exists() and not args.replace_derived:
        ap.error('output already exists; choose a new path or explicitly --replace-derived')
    exigir_base_vigente(args.db)

    # Una propiedad leida en la web de OTRO no es de esta inmobiliaria, y el
    # buscador es donde se veria: `Barreira Bienes Raices` tiene cargada la
    # pagina de socios de una asociacion que comparten tres inmobiliarias, y
    # 729 propiedades leidas de ahi. La misma retencion que aplica el plan de
    # escritura tiene que aplicar el indice de lectura.
    ajenas = agencias_con_web_ajena(Path(args.directorio))
    geo = _leer_jsonl(Path(args.cobertura))
    frescas = mas_frescas(args.paquetes)
    gate = _leer_jsonl(Path(args.gate))

    salida.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(f'{destino.name}.building.{os.getpid()}')
    # An interrupted/failed build never truncates the artifact currently served.
    with temporal.open('xb'):
        pass

    origen = sqlite3.connect(f"file:{Path(args.db).as_posix()}?mode=ro", uri=True)

    # Primera pasada: en cuantas propiedades de cada agencia aparece cada
    # imagen. Sin esto no se puede distinguir una foto de un logo.
    apariciones: dict[str, Counter] = defaultdict(Counter)
    for crudo, canonical in origen.execute(
            "select row_json, canonical_id from rows where status = 'CANDIDATE'"):
        if canonical in ajenas:
            continue
        for url in set(json.loads(crudo).get("imagenes") or []):
            apariciones[canonical][url] += 1

    api = sqlite3.connect(temporal)
    api.executescript(ESQUEMA)

    filas = 0
    ajenas_omitidas = 0
    imagenes_compartidas = 0
    imagenes_repetidas_sin_evidencia = 0
    fichas_sin_foto_propia = 0
    for (crudo,) in origen.execute(
            "select row_json from rows where status = 'CANDIDATE'"):
        cruda = fusionar(json.loads(crudo),
                         frescas.get(json.loads(crudo).get("hash_dedup")),
                         CAMPOS_FUSIONABLES)
        hash_dedup = cruda.get("hash_dedup")
        canonical = cruda.get("canonical_agency_id")
        if canonical in ajenas:
            ajenas_omitidas += 1
            continue
        propias = [u for u in (cruda.get("imagenes") or [])
                   if not is_known_page_asset(u)]
        imagenes_repetidas_sin_evidencia += sum(
            apariciones[canonical][u] >= FICHAS_PARA_SER_COMPARTIDA for u in propias)
        imagenes_compartidas += len(cruda.get("imagenes") or []) - len(propias)
        if cruda.get("imagenes") and not propias:
            # Se queda sin fotos, no sin propiedad: lo que tenia no era suyo.
            fichas_sin_foto_propia += 1
        cruda = dict(cruda, imagenes=propias)
        g = geo.get(hash_dedup)
        # The stored gate may predate this merge. It cannot promise a price or
        # operation scope that the actual row no longer supports.
        actual_scopes, _ = alcances(cruda, g)
        previous_scopes = (gate.get(hash_dedup) or {}).get('alcances')
        scopes = sorted(actual_scopes & set(previous_scopes)) if previous_scopes is not None else sorted(actual_scopes)
        documento = fila_de_api(cruda, g, scopes)
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
        api.execute(
            "insert into busqueda (id, titulo, descripcion, barrio, area_nombre) "
            "values (?,?,?,?,?)",
            (documento["id"], documento["titulo"] or "",
             documento["descripcion"] or "",
             documento["geo"]["barrio"]["nombre"] or "",
             area.get("nombre") or ""))
        filas += 1
    api.commit()

    resumen = {
        "snapshot_version": SNAPSHOT_VERSION,
        "contrato_api_version": CONTRATO_API_VERSION,
        "propiedades": filas,
        "omitidas_por_web_ajena": ajenas_omitidas,
        "imagenes_compartidas_descartadas": imagenes_compartidas,
        "imagenes_repetidas_sin_evidencia_de_descarte": imagenes_repetidas_sin_evidencia,
        "fichas_que_quedaron_sin_foto_propia": fichas_sin_foto_propia,
        "fichas_para_ser_compartida": FICHAS_PARA_SER_COMPARTIDA,
        "generada_en": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "origen": str(Path(args.db)),
        "artefacto": destino.name,
        "database_writes": 0,
    }
    api.close()
    origen.close()
    publish_snapshot(temporal, destino, replace=args.replace_derived)
    (salida / "ERETZ_API_SNAPSHOT_SUMMARY.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
