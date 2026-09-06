#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""La geometria resuelta, guardada una vez y reusable para siempre.

GeoRef es una fuente oficial y gratuita, y por eso mismo no puede volverse una
dependencia online del producto. Ni el frontend, ni la API en runtime, ni el
scraper deben preguntarle lo que ya se preguntó: 36.552 puntos ya resueltos no
se vuelven a consultar.

Esta caché es la forma reproducible de ese conocimiento. Se indexa por
COORDENADA redondeada, no por propiedad: dos avisos del mismo edificio
comparten respuesta, y una corrida futura sobre propiedades nuevas sólo
consulta lo que todavía no está.

Cada entrada guarda lo que hace falta para auditarla y para rehacerla:
coordenada de entrada, resultado, ids, fecha, fuente y versión.

**Cinco decimales, ~1,1 m.** Es la misma precisión que usa la firma de
duplicados. Redondear más agruparía puntos de municipios distintos; redondear
menos haría la caché inútil.

No escribe en ninguna base.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

CACHE_VERSION = "geo_reverse_cache_v1"
DECIMALES = 5


def clave(lat: float, lon: float) -> str:
    """La coordenada redondeada, como texto estable."""
    return f"{round(float(lat), DECIMALES)},{round(float(lon), DECIMALES)}"


def cargar(ruta: Path) -> dict[str, dict[str, Any]]:
    """La caché existente, por clave de coordenada."""
    fuera: dict[str, dict[str, Any]] = {}
    if not ruta.exists():
        return fuera
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        fila = json.loads(linea)
        if fila.get("clave"):
            fuera[fila["clave"]] = fila
    return fuera


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sondeo",
                    default=r"D:\INMO CAPITAL\ERETZ_GEO\GEO_REVERSE_PROBE.jsonl")
    ap.add_argument("--coordenadas",
                    default=r"D:\INMO CAPITAL\ERETZ_GEO\GEO_REVERSE_COORDS.jsonl",
                    help="coordenada por hash_dedup, para poder indexar el sondeo")
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\ERETZ_GEO")
    args = ap.parse_args()

    coords = {}
    ruta_coords = Path(args.coordenadas)
    if ruta_coords.exists():
        for linea in ruta_coords.read_text(encoding="utf-8").splitlines():
            if linea.strip():
                fila = json.loads(linea)
                coords[fila["hash_dedup"]] = (fila["lat"], fila["lon"])

    destino = Path(args.salida) / "GEO_REVERSE_CACHE.jsonl"
    cache = cargar(destino)
    antes = len(cache)
    hoy = time.strftime("%Y-%m-%d")
    sin_coordenada = 0
    niveles: Counter = Counter()

    for linea in Path(args.sondeo).read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        fila = json.loads(linea)
        par = coords.get(fila.get("hash_dedup"))
        if not par:
            sin_coordenada += 1
            continue
        k = clave(*par)
        if k in cache:
            continue
        cache[k] = {
            "clave": k,
            "cache_version": CACHE_VERSION,
            "lat": par[0], "lon": par[1],
            "provincia": fila.get("provincia_geometrica"),
            "departamento": fila.get("departamento_geometrico"),
            "municipio": fila.get("municipio_geometrico"),
            "consultado_en": hoy,
            "fuente": "georef:/ubicacion",
        }
        if fila.get("municipio_geometrico"):
            niveles["municipio"] += 1
        elif fila.get("departamento_geometrico"):
            niveles["departamento"] += 1
        elif fila.get("provincia_geometrica"):
            niveles["provincia"] += 1
        else:
            niveles["sin resolver"] += 1

    with destino.open("w", encoding="utf-8") as archivo:
        for k in sorted(cache):
            archivo.write(json.dumps(cache[k], ensure_ascii=False) + "\n")

    digest = hashlib.sha256(destino.read_bytes()).hexdigest()
    resumen = {
        "cache_version": CACHE_VERSION,
        "decimales": DECIMALES,
        "coordenadas_en_cache": len(cache),
        "agregadas_en_esta_corrida": len(cache) - antes,
        "filas_del_sondeo_sin_coordenada": sin_coordenada,
        "por_nivel_resuelto": dict(niveles.most_common()),
        "sha256": digest,
        "fuente": "georef:/ubicacion (geometria oficial)",
        "database_writes": 0,
        "artefacto": destino.name,
    }
    (Path(args.salida) / "GEO_REVERSE_CACHE_SUMMARY.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
