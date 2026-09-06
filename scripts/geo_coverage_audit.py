#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Cuanta geografia se puede demostrar por dimension, sin mezclar niveles.

`FILTRO_CIUDAD: 5.965` no era cobertura de localidad canonica: era "la fila
tiene algun texto en el campo ciudad". Las filas no guardan procedencia de
`ciudad` -solo de `provincia`-, asi que un barrio escrito en ese campo contaba
igual que una localidad censal. Medir eso como cobertura de ciudad es medir
otra cosa.

Aca cada dimension se cuenta por separado y con su evidencia:

  provincia      la publica la fuente, o la deduce el resolver
  departamento   se deriva del id de la localidad cuando hay localidad
  municipio      el `gobierno_local` de la localidad, cuando el catalogo lo trae
  localidad      SOLO si el resolver la demuestra Y la propuesta esta corroborada
  barrio         texto de la fuente; no se resuelve contra el catalogo de
                 localidades
  coordenadas    lat y lon presentes

Un municipio NUNCA se cuenta como localidad. Si la localidad no se puede
demostrar, la localidad es UNKNOWN aunque haya municipio: esa es la decision
tomada, y este script la mide en vez de discutirla.

`AREA_BUSQUEDA` es la capa de descubrimiento y viaja con su nivel explicito,
para que nadie la confunda con la ciudad.

No escribe en ninguna base.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.geo_dryrun_audit import APTA, clasificar  # noqa: E402
from scripts.preingestion_manifest import (base_canonica,  # noqa: E402
                                           exigir_base_vigente)

from connectors.base import Connector, PropiedadNormalizada  # noqa: E402
from connectors.geografia import geografia  # noqa: E402

COBERTURA_VERSION = "geo_coverage_audit_v1"

CONNECTORS_CON_CAMPO_PROPIO = {"wasi", "century21"}

# Niveles del area de busqueda, de mas preciso a menos. El nivel viaja SIEMPRE
# junto al valor: sin el, un municipio en la caja de busqueda se lee como una
# ciudad y eso es exactamente lo que no se quiere.
NIVEL_LOCALIDAD = "LOCALIDAD"
NIVEL_MUNICIPIO = "MUNICIPIO"
NIVEL_DEPARTAMENTO = "DEPARTAMENTO"
NIVEL_PROVINCIA = "PROVINCIA"
SIN_AREA = "SIN_AREA"


def catalogo_de_localidades(geo: Any) -> dict[str, Any]:
    """Localidad censal por id.

    La `Entidad` del catalogo ya trae `departamento_id` y `municipio_id`: los
    ids de GeoRef son jerarquicos -`06` provincia, `06280` departamento,
    `06280040` localidad-, asi que ningun nivel hay que adivinarlo.
    """
    return {str(e.official_id): e for e in geo.entidades if e.official_id}


def _presente(valor: Any) -> bool:
    return valor not in (None, "", [], {})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(base_canonica()))
    ap.add_argument("--geo", default=r"D:\INMO CAPITAL\ERETZ_GEO")
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\ERETZ_GEO")
    args = ap.parse_args()
    exigir_base_vigente(args.db)

    geo = geografia()
    localidades = catalogo_de_localidades(geo)

    conexion = sqlite3.connect(f"file:{Path(args.db).as_posix()}?mode=ro",
                               uri=True)
    destino = Path(args.salida) / "GEO_COVERAGE_AUDIT.jsonl"

    fuente_tiene: Counter = Counter()
    demostrable: Counter = Counter()
    area: Counter = Counter()
    motivos_sin_localidad: Counter = Counter()
    total = 0

    with destino.open("w", encoding="utf-8") as archivo:
        for crudo, connector, hash_dedup in conexion.execute(
                "select row_json, connector, hash_dedup from rows "
                "where status = 'CANDIDATE'"):
            fila = json.loads(crudo)
            total += 1

            tiene_coord = _presente(fila.get("latitud")) and _presente(fila.get("longitud"))
            for campo, hay in (("provincia", _presente(fila.get("provincia"))),
                               ("ciudad_texto", _presente(fila.get("ciudad"))),
                               ("barrio", _presente(fila.get("barrio"))),
                               ("direccion", _presente(fila.get("direccion"))),
                               ("coordenadas", tiene_coord)):
                if hay:
                    fuente_tiene[campo] += 1

            # El mismo resolver del pipeline, no una copia: un backfill que
            # decide distinto que la ingesta produce dos verdades del mismo
            # dato.
            prop = PropiedadNormalizada(
                canonical_agency_id=str(fila.get("canonical_agency_id") or ""),
                source_listing_id=str(fila.get("source_listing_id") or ""),
                source_url=str(fila.get("source_url") or ""),
                connector=connector or "",
                ciudad=fila.get("ciudad"), barrio=fila.get("barrio"),
                provincia=fila.get("provincia"),
                latitud=fila.get("latitud"), longitud=fila.get("longitud"))
            if fila.get("ciudad") or fila.get("barrio"):
                Connector._resolver_geografia(prop)

            match = prop.extra.get("ciudad_match")
            localidad_id = prop.extra.get("localidad_id")

            # Corroboracion: exactamente la misma regla que decide que
            # propuestas son aptas para escritura. Una localidad que no se
            # puede escribir tampoco se puede contar como cobertura.
            veredicto = clasificar({
                "publicado": {"provincia": fila.get("provincia")},
                "evidencia": {"match": match,
                              "campo_de_origen":
                                  prop.extra.get("ciudad_campo_de_origen")}})
            corroborada = prop.ciudad and veredicto == APTA

            localidad = localidades.get(str(localidad_id or ""))
            departamento_id = getattr(localidad, "departamento_id", None) if corroborada else None
            departamento_nombre = getattr(localidad, "departamento", None) if corroborada else None
            municipio_id = getattr(localidad, "municipio_id", None) if corroborada else None
            municipio_nombre = getattr(localidad, "municipio", None) if corroborada else None
            provincia_final = (fila.get("provincia")
                               or getattr(localidad, "provincia", None))

            if corroborada:
                demostrable["localidad"] += 1
            else:
                motivos_sin_localidad[
                    veredicto if prop.ciudad else (match or "SIN_TEXTO_DE_UBICACION")] += 1
            if _presente(departamento_id):
                demostrable["departamento"] += 1
            if _presente(municipio_id):
                demostrable["municipio"] += 1
            if _presente(provincia_final):
                demostrable["provincia"] += 1
            if _presente(fila.get("barrio")):
                demostrable["barrio_texto"] += 1

            # El area de busqueda baja de nivel, nunca miente sobre cual es.
            if corroborada:
                nivel, valor = NIVEL_LOCALIDAD, prop.ciudad
            elif _presente(municipio_nombre):
                nivel, valor = NIVEL_MUNICIPIO, municipio_nombre
            elif _presente(departamento_nombre):
                nivel, valor = NIVEL_DEPARTAMENTO, departamento_nombre
            elif _presente(provincia_final):
                nivel, valor = NIVEL_PROVINCIA, provincia_final
            else:
                nivel, valor = SIN_AREA, None
            area[nivel] += 1

            archivo.write(json.dumps({
                "hash_dedup": hash_dedup,
                "cobertura_version": COBERTURA_VERSION,
                "fuente": {"provincia": fila.get("provincia"),
                           "ciudad_texto": fila.get("ciudad"),
                           "barrio": fila.get("barrio"),
                           "coordenadas": tiene_coord},
                "localidad_canonica": prop.ciudad if corroborada else None,
                "localidad_id": localidad_id if corroborada else None,
                "departamento_canonico": departamento_nombre or None,
                "municipio_canonico": municipio_nombre or None,
                "provincia_canonica": provincia_final,
                "barrio_fuente": fila.get("barrio"),
                "match": match,
                "veredicto_de_corroboracion": veredicto,
                "area_busqueda": {"nivel": nivel, "valor": valor},
                "writes": False,
            }, ensure_ascii=False) + "\n")

    con_area = total - area[SIN_AREA]
    resumen = {
        "cobertura_version": COBERTURA_VERSION,
        "candidatas": total,
        "publica_la_fuente": dict(fuente_tiene.most_common()),
        "demostrable_por_dimension": dict(demostrable.most_common()),
        "area_de_busqueda_por_nivel": dict(area.most_common()),
        "area_busqueda_total": con_area,
        "area_busqueda_total_pct": round(100 * con_area / total, 1) if total else 0,
        "localidad_canonica_pct": round(
            100 * demostrable["localidad"] / total, 1) if total else 0,
        "motivos_sin_localidad": dict(motivos_sin_localidad.most_common()),
        "database_writes": 0,
        "artefacto": destino.name,
    }
    (Path(args.salida) / "GEO_COVERAGE_AUDIT_SUMMARY.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
