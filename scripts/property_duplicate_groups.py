#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""La misma propiedad publicada por dos inmobiliarias distintas.

El dedup que ya existia es por URL dentro de una misma inmobiliaria
(`hash_dedup`). No ve el caso de producto: una casa de Cordoba publicada por
`aagaard inmobiliaria` y por `platinus bienes raices`, mismas coordenadas,
mismo tipo, misma operacion, mismos dormitorios, misma superficie y el mismo
precio. En el portal aparecen dos veces.

Medido antes de construir nada: 117 grupos y 283 filas sobre las 13.322
candidatas que tienen firma completa, repartidos en 133 pares distintos de
inmobiliarias. El par mas frecuente cubre 7 grupos, o sea que **no** es una
inmobiliaria cargada dos veces con otro nombre -eso seria un problema de
identidad y se arreglaria en otro lado-, sino multi-listado real.

**Este modulo agrupa y no elige ganador.** Cual de las dos inmobiliarias se
muestra es una decision comercial, no tecnica: define quien se lleva el clic.
Borrar una destruiria esa opcion antes de que nadie la tome. Aca se emite el
grupo con su evidencia y la decision queda afuera.

La firma es deliberadamente conservadora:

  - coordenada exacta a 5 decimales (~1,1 m). Dos inmobiliarias que geocodifican
    la misma direccion pueden diferir un poco, asi que esto pierde duplicados
    reales. Se prefiere perder uno a fusionar dos propiedades distintas.
  - todos los campos presentes. Una firma con nulos no es identidad, es
    ausencia: agrupar por ella junto dos edificios enteros en las pruebas.
  - tipo, operacion, dormitorios y superficie cubierta ademas de la coordenada,
    porque un edificio tiene muchas unidades en el mismo punto.

Aun asi dos unidades identicas del mismo edificio caen en un grupo. Es otra
razon para no borrar.

No escribe en ninguna base.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

# ~1,1 m. Mas precision separa lo que es lo mismo; menos junta lo que no lo es.
DECIMALES = 5

CAMPOS_DE_FIRMA = ("latitud", "longitud", "tipo_propiedad", "operacion",
                   "dormitorios", "superficie_cubierta")


def firma_de(fila: dict[str, Any]) -> tuple | None:
    valores = [fila.get(c) for c in CAMPOS_DE_FIRMA]
    if any(v in (None, "", 0) for v in valores):
        return None
    try:
        latitud, longitud = round(float(valores[0]), DECIMALES), \
            round(float(valores[1]), DECIMALES)
    except (TypeError, ValueError):
        return None
    return (latitud, longitud, *valores[2:])


def identificador(firma: tuple) -> str:
    crudo = "|".join(str(x) for x in firma)
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()[:16]


def agrupar(registros) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Arma los grupos y las cuentas. Separado de la base para poder probarlo."""
    grupos: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    candidatas = con_firma = 0
    for fila, canonical, hash_dedup in registros:
        candidatas += 1
        firma = firma_de(fila)
        if firma is None:
            continue
        con_firma += 1
        grupos[firma].append({
            "canonical_agency_id": canonical,
            "hash_dedup": hash_dedup,
            "source_url": fila.get("source_url"),
            "titulo": fila.get("titulo"),
            "precio": fila.get("precio"),
            "moneda": fila.get("moneda"),
            "ciudad": fila.get("ciudad"),
            "barrio": fila.get("barrio"),
        })

    salida: list[dict[str, Any]] = []
    entre_agencias = misma_agencia = filas_agrupadas = precios_en_conflicto = 0
    pares: Counter = Counter()
    for firma, miembros in grupos.items():
        if len(miembros) < 2:
            continue
        agencias = {m["canonical_agency_id"] for m in miembros}
        if len(agencias) == 1:
            misma_agencia += 1
            alcance = "MISMA_INMOBILIARIA"
        else:
            entre_agencias += 1
            alcance = "ENTRE_INMOBILIARIAS"
            for a, b in combinations(sorted(agencias), 2):
                pares[(a, b)] += 1
        filas_agrupadas += len(miembros)
        precios = {m["precio"] for m in miembros if m["precio"] not in (None, "", 0)}
        if len(precios) > 1:
            precios_en_conflicto += 1
        salida.append({
            "grupo_id": identificador(firma),
            "alcance": alcance,
            "firma": dict(zip(CAMPOS_DE_FIRMA, firma)),
            "inmobiliarias": sorted(agencias),
            "miembros": miembros,
            "precios_distintos": len(precios) > 1,
            # Quien se muestra es una decision comercial y no se toma aca.
            "ganador_elegido": None,
            "database_writes": 0,
        })

    resumen = {
        "candidatas": candidatas,
        "con_firma_completa": con_firma,
        "cobertura_de_la_firma": round(100 * con_firma / max(1, candidatas), 1),
        "grupos_entre_inmobiliarias": entre_agencias,
        "grupos_dentro_de_la_misma": misma_agencia,
        "filas_agrupadas": filas_agrupadas,
        "grupos_con_precios_distintos": precios_en_conflicto,
        "pares_de_inmobiliarias": len(pares),
        "par_mas_frecuente": (list(pares.most_common(1)[0][0])
                              + [pares.most_common(1)[0][1]] if pares else None),
        "ganadores_elegidos": 0,
        "database_writes": 0,
    }
    return salida, resumen


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=r"D:\INMO CAPITAL\ERETZ_PREINGESTION_REBUILD_20260903\PREINGESTION_REBUILD.sqlite3")
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\ERETZ_PREINGESTION_REBUILD_20260903")
    args = ap.parse_args()

    conexion = sqlite3.connect(f"file:{Path(args.db).as_posix()}?mode=ro", uri=True)
    registros = ((json.loads(crudo), canonical, hash_dedup)
                 for crudo, canonical, hash_dedup in conexion.execute(
                     "select row_json, canonical_id, hash_dedup from rows "
                     "where status = 'CANDIDATE'"))
    grupos, resumen = agrupar(registros)

    destino = Path(args.salida) / "PROPERTY_DUPLICATE_GROUPS.jsonl"
    with destino.open("w", encoding="utf-8") as archivo:
        for grupo in grupos:
            archivo.write(json.dumps(grupo, ensure_ascii=False) + chr(10))
    resumen["artefacto"] = destino.name

    (Path(args.salida) / "PROPERTY_DUPLICATE_GROUPS_SUMMARY.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
