#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Que se puede afirmar de una coordenada, y que no.

El catalogo local de GeoRef trae solo centroides. Con centroides, preguntar
"que localidad es este punto" solo se puede responder por vecino mas cercano, y
el vecino mas cercano es precisamente lo que produjo `Villa del Parque` en Rio
Negro. No se usa.

GeoRef publica `/ubicacion`, que resuelve un punto contra la GEOMETRIA real de
las capas administrativas. Eso no es una aproximacion nuestra: es la respuesta
oficial de la misma fuente ya adoptada, y devuelve provincia, departamento y
municipio -nunca localidad, porque el organismo no publica los poligonos de
localidad-.

De ahi la asimetria que este script mide y que la decision ya anticipo:

  provincia, departamento, municipio   determinables por geometria
  localidad                            NO determinable por coordenada

Ademas se contrasta la provincia devuelta contra la que publico la fuente. Una
discrepancia no se resuelve aca: se cuenta, porque significa que una de las dos
esta mal y escribir cualquiera de las dos seria elegir sin evidencia.

Solo lee. No escribe en ninguna base y no propone escribir localidad.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.geo_dryrun_audit import APTA, clasificar  # noqa: E402
from scripts.preingestion_manifest import (base_canonica,  # noqa: E402
                                           exigir_base_vigente)

from connectors.base import Connector, PropiedadNormalizada  # noqa: E402
from connectors.geografia import geografia  # noqa: E402

SONDEO_VERSION = "geo_reverse_probe_v1"

BASE = "https://apis.datos.gob.ar/georef/api/ubicacion"
AGENTE = "ERETZ-PropertyBot/1.0 (+contacto@eretz)"
# El organismo no documenta un tope para el POST masivo. 500 anduvo y mantiene
# cada respuesta manejable; el objetivo no es ir rapido sino no molestar.
LOTE = 500
CORTESIA = 1.5
REINTENTOS = 3


def _normalizar(texto: str | None) -> str:
    tabla = str.maketrans("\u00e1\u00e9\u00ed\u00f3\u00fa\u00fc\u00f1"
                          "\u00c1\u00c9\u00cd\u00d3\u00da\u00dc\u00d1",
                          "aeiouunAEIOUUN")
    return "".join(c for c in (texto or "").translate(tabla).lower()
                   if c.isalnum())


def consultar(puntos: list[tuple[float, float]]) -> list[dict[str, Any]]:
    """Un lote de puntos contra `/ubicacion`, con reintento y cortesia."""
    cuerpo = json.dumps({"ubicaciones": [
        {"lat": lat, "lon": lon, "aplanar": True} for lat, lon in puntos]}).encode()
    ultimo: Exception | None = None
    for intento in range(REINTENTOS):
        peticion = urllib.request.Request(
            BASE, data=cuerpo, method="POST",
            headers={"User-Agent": AGENTE, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(peticion, timeout=120) as respuesta:
                return json.load(respuesta).get("resultados", [])
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            ultimo = error
            time.sleep(CORTESIA * (intento + 1) * 2)
    raise RuntimeError(f"GeoRef no respondio tras {REINTENTOS} intentos: {ultimo}")


def objetivo(db: Path) -> list[dict[str, Any]]:
    """Las candidatas con coordenada y sin localidad demostrable."""
    geografia()
    conexion = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    fuera: list[dict[str, Any]] = []
    for crudo, connector, hash_dedup in conexion.execute(
            "select row_json, connector, hash_dedup from rows "
            "where status = 'CANDIDATE'"):
        fila = json.loads(crudo)
        lat, lon = fila.get("latitud"), fila.get("longitud")
        if lat in (None, "") or lon in (None, ""):
            continue
        prop = PropiedadNormalizada(
            canonical_agency_id=str(fila.get("canonical_agency_id") or ""),
            source_listing_id=str(fila.get("source_listing_id") or ""),
            source_url=str(fila.get("source_url") or ""),
            connector=connector or "",
            ciudad=fila.get("ciudad"), barrio=fila.get("barrio"),
            provincia=fila.get("provincia"), latitud=lat, longitud=lon)
        if fila.get("ciudad") or fila.get("barrio"):
            Connector._resolver_geografia(prop)
        veredicto = clasificar({
            "publicado": {"provincia": fila.get("provincia")},
            "evidencia": {"match": prop.extra.get("ciudad_match"),
                          "campo_de_origen":
                              prop.extra.get("ciudad_campo_de_origen")}})
        if prop.ciudad and veredicto == APTA:
            continue          # ya tiene localidad demostrada: no es el hueco
        fuera.append({"hash_dedup": hash_dedup, "lat": float(lat),
                      "lon": float(lon),
                      "provincia_publicada": fila.get("provincia"),
                      "source_url": fila.get("source_url")})
    return fuera


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(base_canonica()))
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\ERETZ_GEO")
    ap.add_argument("--limite", type=int, default=0,
                    help="0 = todas; util para una muestra")
    args = ap.parse_args()
    exigir_base_vigente(args.db)

    filas = objetivo(Path(args.db))
    if args.limite:
        filas = filas[:args.limite]
    print(f"con coordenada y sin localidad demostrable: {len(filas):,}", flush=True)

    destino = Path(args.salida) / "GEO_REVERSE_PROBE.jsonl"
    tiene: Counter = Counter()
    provincia: Counter = Counter()
    resueltos = 0

    with destino.open("w", encoding="utf-8") as archivo:
        for inicio in range(0, len(filas), LOTE):
            lote = filas[inicio:inicio + LOTE]
            resultados = consultar([(f["lat"], f["lon"]) for f in lote])
            for fila, resultado in zip(lote, resultados):
                u = resultado.get("ubicacion") or {}
                prov = u.get("provincia_nombre")
                depto = u.get("departamento_nombre")
                muni = u.get("municipio_nombre")
                resueltos += 1
                if prov:
                    tiene["provincia"] += 1
                if depto:
                    tiene["departamento"] += 1
                if muni:
                    tiene["municipio"] += 1
                if not (prov or depto or muni):
                    tiene["fuera_del_pais_o_sin_capa"] += 1

                publicada = fila["provincia_publicada"]
                if not publicada:
                    estado = "SIN_PROVINCIA_PUBLICADA"
                elif not prov:
                    estado = "SIN_PROVINCIA_GEOMETRICA"
                elif _normalizar(publicada) == _normalizar(prov):
                    estado = "COINCIDE"
                else:
                    estado = "CONTRADICE"
                provincia[estado] += 1

                archivo.write(json.dumps({
                    "hash_dedup": fila["hash_dedup"],
                    "sondeo_version": SONDEO_VERSION,
                    # La coordenada viaja en la salida: sin ella, reconstruir
                    # la cache exige volver a la base y unir por hash.
                    "lat": fila["lat"], "lon": fila["lon"],
                    "provincia_geometrica": prov,
                    "departamento_geometrico": depto,
                    "municipio_geometrico": muni,
                    "provincia_publicada": publicada,
                    "acuerdo_de_provincia": estado,
                    # Nunca se propone localidad desde una coordenada.
                    "localidad_propuesta": None,
                    "writes": False,
                }, ensure_ascii=False) + "\n")
            print(f"  {min(inicio + LOTE, len(filas)):,}/{len(filas):,}", flush=True)
            time.sleep(CORTESIA)

    resumen = {
        "sondeo_version": SONDEO_VERSION,
        "puntos_consultados": resueltos,
        "determinable_por_geometria": dict(tiene.most_common()),
        "localidad_determinable_por_coordenada": 0,
        "acuerdo_con_la_provincia_publicada": dict(provincia.most_common()),
        "fuente": "georef:/ubicacion (geometria oficial, no centroide)",
        "database_writes": 0,
        "artefacto": destino.name,
    }
    (Path(args.salida) / "GEO_REVERSE_PROBE_SUMMARY.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
