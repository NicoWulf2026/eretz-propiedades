#!/usr/bin/env python
"""Valida la geografia canonica contra propiedades reales, por estrato.

Los tests sinteticos no alcanzan: la primera version de este modulo pasaba la
bateria entera y dejaba sin ciudad a 1.498 avisos de La Plata, porque el campo
`provincia` de la fuente traia "GBA Sur". Eso solo aparece midiendo.

Un falso positivo geografico es mas grave que un UNKNOWN: una ciudad equivocada
despues no se distingue de una correcta, y una ausente si. Por eso el reporte
mide por separado lo resuelto, lo ambiguo, lo no encontrado y -con las
coordenadas como verdad independiente- lo resuelto MAL.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.preingestion_manifest import (base_canonica,  # noqa: E402
                                            exigir_base_vigente)

from connectors.geografia import (_distancia, _en_argentina, geografia,
                                  CONTRADICE_A_KM, normalizar)

BARRIOS_CONOCIDOS = {"palermo", "caballito", "villa crespo", "centro",
                     "nordelta", "belgrano", "recoleta", "almagro"}


def estrato(fila: dict[str, Any]) -> str:
    """En que caso cae esta propiedad, para no promediar peras con manzanas."""
    ciudad = normalizar(fila.get("ciudad"))
    tiene_coord = _en_argentina(fila.get("latitud"), fila.get("longitud"))
    if not ciudad:
        return "sin ciudad publicada"
    if ciudad in BARRIOS_CONOCIDOS:
        return "barrio publicado como ciudad"
    if ciudad.endswith(" capital") or ciudad in ("caba", "capital federal"):
        return "forma comercial o capital"
    return ("con ciudad y coordenada" if tiene_coord
            else "con ciudad sin coordenada")


def main() -> int:
    parser = argparse.ArgumentParser()
    # Sale del manifiesto: este default estuvo clavado en la base del 27 de
    # agosto -13.023 candidatas menos- y las propuestas de ciudad se
    # calcularon sobre ese universo sin que nadie lo notara.
    parser.add_argument("--db", default=str(base_canonica()))
    parser.add_argument("--salida", default=r"D:\INMO CAPITAL\ERETZ_GEO\VALIDACION_GEOGRAFICA.json")
    args = parser.parse_args()
    # Una base vencida es legible y no se queja: hay que preguntar.
    exigir_base_vigente(args.db)

    geo = geografia()
    conexion = sqlite3.connect(f"file:{Path(args.db).as_posix()}?mode=ro",
                               uri=True)

    por_estrato: dict[str, Counter] = defaultdict(Counter)
    por_connector: dict[str, Counter] = defaultdict(Counter)
    distancias: list[float] = []
    falsos: list[dict[str, Any]] = []
    ejemplos: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for (crudo, connector) in conexion.execute(
            "select row_json, connector from rows"):
        fila = json.loads(crudo)
        grupo = estrato(fila)
        if grupo == "sin ciudad publicada":
            por_estrato[grupo]["sin ciudad"] += 1
            continue

        resultado = geo.resolver_localidad(
            fila.get("ciudad"), provincia=fila.get("provincia"),
            lat=fila.get("latitud"), lon=fila.get("longitud"))
        por_estrato[grupo][resultado.certeza] += 1
        por_connector[connector][resultado.certeza] += 1

        if len(ejemplos[grupo]) < 5:
            ejemplos[grupo].append({
                "fuente": {"ciudad": fila.get("ciudad"),
                           "provincia": fila.get("provincia"),
                           "coordenada": bool(_en_argentina(
                               fila.get("latitud"), fila.get("longitud")))},
                "resolucion": resultado.a_dict(),
            })

        entidad = resultado.entidad
        if (entidad is not None and entidad.lat is not None
                and _en_argentina(fila.get("latitud"), fila.get("longitud"))):
            km = _distancia(fila["latitud"], fila["longitud"],
                            entidad.lat, entidad.lon)
            distancias.append(km)
            if km > CONTRADICE_A_KM:
                falsos.append({"ciudad": fila.get("ciudad"),
                               "resuelta": entidad.official_name,
                               "km": round(km, 1)})

    distancias.sort()
    def cuantil(q: float) -> float:
        return round(distancias[int(len(distancias) * q)], 1) if distancias else 0.0

    informe = {
        "propiedades_por_estrato": {k: dict(v) for k, v in por_estrato.items()},
        "por_connector": {k: dict(v) for k, v in por_connector.items()},
        "verificacion_con_coordenadas": {
            "verificables": len(distancias),
            "mediana_km": cuantil(0.5),
            "p95_km": cuantil(0.95),
            "max_km": round(distancias[-1], 1) if distancias else 0.0,
            "falsos_positivos": len(falsos),
            "umbral_km": CONTRADICE_A_KM,
        },
        "falsos_positivos": falsos[:20],
        "ejemplos_por_estrato": ejemplos,
    }
    Path(args.salida).write_text(
        json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")

    print("resolucion por estrato:")
    for grupo, cuenta in sorted(por_estrato.items()):
        total = sum(cuenta.values())
        resueltas = sum(v for k, v in cuenta.items()
                        if k in ("EXACT_CANONICAL", "ALIAS_MATCH",
                                 "CONTEXT_MATCH", "COORDINATE_SUPPORTED"))
        print(f"  {grupo:32} n={total:6}  resueltas={resueltas:6} "
              f"({100 * resueltas / max(total, 1):5.1f}%)")
    verif = informe["verificacion_con_coordenadas"]
    print()
    print(f"verificadas con coordenada: {verif['verificables']}")
    print(f"  mediana {verif['mediana_km']} km | p95 {verif['p95_km']} km | "
          f"max {verif['max_km']} km")
    print(f"  FALSOS POSITIVOS: {verif['falsos_positivos']}")
    print(f"informe en {args.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
