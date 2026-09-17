#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Los defectos NUESTROS, agrupados por patron y ordenados por impacto.

`EXTRACTION_FAILED` es el unico estado de campo que es un defecto propio: la
fuente lo publica y no lo leimos. Contarlos por campo -como hacia el resumen
del quality gate- ordena mal el trabajo, porque un campo que falla en ocho
lugares distintos no es un problema y ocho campos que fallan en el mismo lugar
son uno solo.

Agrupar por FAMILIA y campo cambia el diagnostico. Sobre la medicion actual,
`wordpress` falla en ambientes, dormitorios, superficie cubierta, direccion,
ciudad, barrio, banos y operacion con recuentos parecidos y sobre las MISMAS
cinco agencias: eso no son ocho defectos, es una lectura estructurada que no
esta ocurriendo.

El orden de ataque sale de §25 del plan -primero lo que pierde propiedades
enteras, despues precio, operacion, tipo, ubicacion- cruzado con cuantas
propiedades recupera cada arreglo.

No escribe en ninguna base.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]

ANALISIS_VERSION = "extraction_failures_v1"

# Cuanto pesa cada campo. Sale del orden de impacto del plan, no del gusto:
# una propiedad sin operacion pierde un filtro entero; una sin superficie
# pierde una linea de la ficha.
PESO_DEL_CAMPO = {
    "operacion": 100, "tipo_propiedad": 90, "precio": 90, "moneda": 90,
    "ciudad": 70, "direccion": 60, "barrio": 50, "imagenes": 50,
    "titulo": 80, "descripcion": 40,
    "ambientes": 30, "dormitorios": 30, "banos": 25,
    "superficie_total": 20, "superficie_cubierta": 20,
    "latitud": 40, "longitud": 40,
}


def vigencia(db: Path) -> dict[str, Any]:
    """Si los datos que se estan midiendo son anteriores al codigo que los saco.

    El ranking mide una snapshot, no el mundo. Las 58.427 propiedades se
    extrajeron en agosto y desde entonces hubo 41 commits de connectors: dos de
    los tres defectos mejor rankeados -`tokko/superficie_total` y
    `generic/html_catalog operacion`- ya estaban arreglados en el codigo, y
    perseguirlos costo medio dia.

    No se corrige el ranking ni se ocultan grupos: no se puede saber sin correr
    cual arreglo ya cubre cual defecto. Se dice que la lista puede estar
    midiendo fantasmas, que es lo que hay que saber antes de elegir en que
    trabajar.
    """
    datos = None
    if db.exists():
        conexion = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        try:
            fila = conexion.execute(
                "select max(json_extract(row_json, '$.scraped_at')) from rows "
                "where status = 'CANDIDATE'").fetchone()
            datos = fila[0] if fila else None
        except sqlite3.Error:
            datos = None
        finally:
            conexion.close()
    try:
        git = ["git", "-c", f"safe.directory={RAIZ.as_posix()}"]
        codigo = subprocess.run(
            git + ["log", "-1", "--format=%cI", "--", "connectors"],
            cwd=RAIZ, capture_output=True, text=True, timeout=30,
            check=True).stdout.strip()
        posteriores = subprocess.run(
            git + ["log", "--format=%h", f"--since={datos}", "--", "connectors"],
            cwd=RAIZ, capture_output=True, text=True, timeout=30, check=True
        ).stdout.split() if datos else []
    except (OSError, subprocess.SubprocessError):
        codigo, posteriores = "", []
    vencida = bool(datos and codigo and codigo[:19] > datos[:19])
    return {
        "datos_extraidos_hasta": datos,
        "codigo_de_connectors_hasta": codigo or None,
        "commits_de_connectors_posteriores_a_los_datos": len(posteriores),
        "los_datos_son_anteriores_al_codigo": vencida,
        "advertencia": (
            "el ranking mide una snapshot anterior al codigo actual: un grupo "
            "puede estar ya arreglado y solo esperando la recertificacion. "
            "Antes de trabajar sobre uno, abrir una ficha real y correr el "
            "parser de hoy." if vencida else None),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate",
                    default=r"D:\INMO CAPITAL\ERETZ_PREINGESTION_REBUILD_20260903"
                            r"\PROPERTY_QUALITY_GATE.jsonl")
    ap.add_argument("--resultados",
                    default=r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827"
                            r"\AGENCY_CERTIFICATION_RESULTS.jsonl")
    ap.add_argument("--db",
                    default=r"D:\INMO CAPITAL\ERETZ_PREINGESTION_REBUILD_20260903"
                            r"\PREINGESTION_REBUILD.sqlite3")
    ap.add_argument("--salida",
                    default=r"D:\INMO CAPITAL\ERETZ_PREINGESTION_REBUILD_20260903")
    args = ap.parse_args()

    familia_de: dict[str, str] = {}
    for linea in Path(args.resultados).read_text(encoding="utf-8").splitlines():
        if linea.strip():
            fila = json.loads(linea)
            familia_de[fila["canonical_agency_id"]] = (
                fila.get("connector_strategy") or fila.get("connector")
                or "sin familia")

    por_par: Counter = Counter()
    agencias: dict[tuple[str, str], set[str]] = defaultdict(set)
    campos_por_familia: dict[str, set[str]] = defaultdict(set)
    total = 0

    for linea in Path(args.gate).read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        fila = json.loads(linea)
        familia = familia_de.get(fila["canonical_agency_id"], "sin certificar")
        for campo, estado in (fila.get("estados_de_campo") or {}).items():
            if estado != "EXTRACTION_FAILED":
                continue
            total += 1
            por_par[(familia, campo)] += 1
            agencias[(familia, campo)].add(fila["canonical_agency_id"])
            campos_por_familia[familia].add(campo)

    grupos: list[dict[str, Any]] = []
    for (familia, campo), propiedades in por_par.items():
        grupos.append({
            "familia": familia,
            "campo": campo,
            "propiedades": propiedades,
            "agencias": len(agencias[(familia, campo)]),
            "ejemplos": sorted(agencias[(familia, campo)])[:3],
            # Prioridad = cuantas propiedades recupera por lo que vale el campo.
            "prioridad": propiedades * PESO_DEL_CAMPO.get(campo, 10),
        })
    grupos.sort(key=lambda g: -g["prioridad"])

    # Una familia que falla en muchos campos a la vez es UN defecto, no varios.
    sospechosas = sorted(
        ({"familia": f, "campos_que_fallan": len(c),
          "propiedades": sum(por_par[(f, campo)] for campo in c),
          "campos": sorted(c)}
         for f, c in campos_por_familia.items() if len(c) >= 5),
        key=lambda x: -x["propiedades"])

    destino = Path(args.salida) / "EXTRACTION_FAILURES.jsonl"
    with destino.open("w", encoding="utf-8") as archivo:
        for grupo in grupos:
            archivo.write(json.dumps(
                dict(grupo, analisis_version=ANALISIS_VERSION),
                ensure_ascii=False) + "\n")

    resumen = {
        "analisis_version": ANALISIS_VERSION,
        "vigencia": vigencia(Path(args.db)),
        "defectos_de_campo": total,
        "grupos": len(grupos),
        "primeros_por_impacto": grupos[:10],
        "familias_con_falla_ancha": sospechosas,
        "database_writes": 0,
        "artefacto": destino.name,
    }
    (Path(args.salida) / "EXTRACTION_FAILURES_SUMMARY.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
