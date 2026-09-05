#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Cuales de las 29.048 propuestas de ciudad se pueden escribir, y cuales no.

El dry-run de geografia quedo anotado en el plan como "29.048 propuestas
listas", esperando unicamente que vuelva Postgres. No lo estan.

La primera fila del artefacto propone `Villa del Parque` -un barrio de CABA,
con `Melincue al 2600`, una calle de CABA- como localidad de **Rio Negro**. La
segunda propone `Barrio Norte`, tambien de CABA, tambien a Rio Negro. Son
nombres de barrio que existen como localidad censal en otra provincia, y el
unico dato que los sostiene es el nombre.

El plan ya lo habia anticipado en otra forma: "GeoRef no cataloga barrios", y
el caso `Alberdi` esta documentado justamente como la razon para no hacer esto.
El control de contradiccion por coordenadas no puede intervenir porque estas
filas no tienen coordenada.

**El criterio es la corroboracion, no el origen.** Una propuesta se sostiene
cuando algo ademas del nombre la respalda: la provincia que publico la fuente,
o el apoyo de una coordenada, o el desempate por contexto. Sin nada de eso, y
saliendo del campo `barrio` -que por definicion no es una ciudad-, la respuesta
honesta es UNKNOWN.

Perder una ciudad NO pierde la propiedad: por contrato sigue teniendo ficha y
sigue en el listado, y lo unico que pierde es el filtro por ciudad. Escribir
una ciudad falsa, en cambio, no se nota y no se revierte solo.

No escribe en ninguna base. Decide que se PODRIA escribir, no escribe nada.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

AUDITORIA_VERSION = "geo_dryrun_audit_v1"

# Matches que ya traen corroboracion propia: la coordenada apoyo la candidata,
# o el contexto desempato entre homonimas.
MATCH_CORROBORADO = ("COORDINATE_SUPPORTED", "CONTEXT_MATCH")

APTA = "APTA_PARA_ESCRITURA"
SIN_CORROBORAR = "BARRIO_SIN_CORROBORAR"
DEBIL = "NOMBRE_SIN_CORROBORAR"


def corroborada(fila: dict[str, Any]) -> bool:
    """Hay algo ademas del nombre que sostenga esta propuesta?"""
    evidencia = fila.get("evidencia") or {}
    publicado = fila.get("publicado") or {}
    return (bool(publicado.get("provincia"))
            or evidencia.get("match") in MATCH_CORROBORADO)


def clasificar(fila: dict[str, Any]) -> str:
    """Apta, o el motivo por el que no lo es."""
    if corroborada(fila):
        return APTA
    origen = (fila.get("evidencia") or {}).get("campo_de_origen")
    # Un barrio no es una ciudad. Que su nombre exista en el catalogo de
    # localidades de otra provincia no lo convierte en una.
    return SIN_CORROBORAR if origen == "barrio" else DEBIL


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dryrun", default=r"D:\INMO CAPITAL\ERETZ_GEO\CIUDAD_DRYRUN.jsonl")
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\ERETZ_GEO")
    args = ap.parse_args()

    origen = Path(args.dryrun)
    destino = Path(args.salida) / "CIUDAD_DRYRUN_AUDIT.jsonl"

    clases: Counter = Counter()
    por_origen: Counter = Counter()
    provincias_dudosas: Counter = Counter()
    total = 0

    with destino.open("w", encoding="utf-8") as archivo:
        for linea in origen.read_text(encoding="utf-8").splitlines():
            if not linea.strip():
                continue
            fila = json.loads(linea)
            total += 1
            clase = clasificar(fila)
            clases[clase] += 1
            evidencia = fila.get("evidencia") or {}
            por_origen[(evidencia.get("campo_de_origen"), clase)] += 1
            if clase != APTA:
                provincias_dudosas[(fila.get("propuesto") or {}).get("provincia")] += 1
            archivo.write(json.dumps({
                "hash_dedup": fila.get("hash_dedup"),
                "source_url": fila.get("source_url"),
                "auditoria_version": AUDITORIA_VERSION,
                "clase": clase,
                "apta_para_escritura": clase == APTA,
                "campo_de_origen": evidencia.get("campo_de_origen"),
                "match": evidencia.get("match"),
                "propuesto": fila.get("propuesto"),
                "publicado": fila.get("publicado"),
                "writes": False,
            }, ensure_ascii=False) + "\n")

    resumen = {
        "auditoria_version": AUDITORIA_VERSION,
        "propuestas_auditadas": total,
        "aptas_para_escritura": clases[APTA],
        "no_aptas": total - clases[APTA],
        "por_clase": dict(clases.most_common()),
        "por_origen_y_clase": {f"{o}|{c}": n
                               for (o, c), n in por_origen.most_common()},
        "provincias_mas_propuestas_sin_corroborar":
            dict(provincias_dudosas.most_common(8)),
        "database_writes": 0,
        "artefacto": destino.name,
    }
    (Path(args.salida) / "CIUDAD_DRYRUN_AUDIT_SUMMARY.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
