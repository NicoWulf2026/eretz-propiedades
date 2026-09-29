#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Las compuertas del despliegue AUTOMATICO de la snapshot local (politica P2).

Politica del usuario (29-09): la snapshot de la API LOCAL / NO PUBLICA se
reemplaza sola cuando pasan TODAS estas compuertas; si falla una, no se
despliega. No autoriza deploy publico, writes a Supabase, DNS ni nada remoto.

  1. integridad ok (la verifica el despliegue antes de copiar);
  2. QA de API 14/14 con el estado esperado por caso;
  3. 0 filas del exterior publicables (contencion en el poligono del pais);
  4. 0 precios simbolicos;
  5. 0 GEO_CONFLICT en el mapa;
  6. altas, bajas y reemplazos explicados POR ID (`CAMBIOS_DE_INVENTARIO.jsonl`),
     y solo con motivos de politicas aprobadas: un retiro por ausencia sin muerte
     verificada NO es un motivo aceptado (P1);
  7. duplicados probables que involucran altas, auditados y bajo el tope;
  8. Regression Gate sin perdidas pendientes de revision;
  9. respaldo con hash y rollback automatico (los hace el despliegue).

Devuelve la lista de fallas: vacia = se puede desplegar. No escribe nada.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import urllib.parse
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CAMBIOS = "CAMBIOS_DE_INVENTARIO.jsonl"
BENCHMARK = "API_BENCHMARK.json"
BAJAS_PERMITIDAS = frozenset({"EXTERIOR_ARGENTINA_ONLY", "WEB_AJENA",
                              "RETIRO_MUERTE_VERIFICADA", "NO_ES_FICHA_CATEGORIA"})
ALTAS_PERMITIDAS = frozenset({"SUMADA_CERTIFICADA"})
# El estado que la QA tiene que dar en cada caso (la ventana y el orden invalido
# se rechazan a proposito).
ESTADO_ESPERADO = {"window_rejected": 400, "invalid_sort": 422}
CASOS_QA = 14
LATENCIA_MAXIMA_MS = 2000
DUPLICADOS_TOPE_MINIMO = 10
DUPLICADOS_TOPE_FRACCION = 0.005


def leer_cambios(carpeta: Path) -> dict[str, str] | None:
    ruta = carpeta / CAMBIOS
    if not ruta.exists():
        return None
    fuera = {}
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if linea.strip():
            fila = json.loads(linea)
            fuera[fila["id"]] = fila["motivo"]
    return fuera


def compuerta_inventario(faltan: set[str], sobran: set[str],
                         cambios: dict[str, str] | None) -> list[str]:
    if cambios is None:
        return [f"falta {CAMBIOS}: sin motivo por id no hay despliegue automatico"]
    fallas = []
    sin_motivo = [i for i in faltan if cambios.get(i) not in BAJAS_PERMITIDAS]
    if sin_motivo:
        motivos = sorted({cambios.get(i) or "SIN_MOTIVO" for i in sin_motivo})
        fallas.append(f"{len(sin_motivo)} bajas sin motivo aprobado ({', '.join(motivos)})")
    altas = [i for i in sobran if cambios.get(i) not in ALTAS_PERMITIDAS]
    if altas:
        fallas.append(f"{len(altas)} altas sin motivo aprobado")
    return fallas


def compuerta_qa(carpeta: Path) -> list[str]:
    ruta = carpeta / BENCHMARK
    if not ruta.exists():
        return [f"falta {BENCHMARK} de la candidata"]
    qa = json.loads(ruta.read_text(encoding="utf-8"))
    fallas = []
    casos = qa.get("cases") or []
    if len(casos) != CASOS_QA:
        fallas.append(f"QA con {len(casos)} casos, se esperan {CASOS_QA}")
    for caso in casos:
        esperado = ESTADO_ESPERADO.get(caso.get("case"), 200)
        if caso.get("status") != esperado:
            fallas.append(f"QA {caso.get('case')}: {caso.get('status')} != {esperado}")
        if (caso.get("median_ms") or 0) > LATENCIA_MAXIMA_MS:
            fallas.append(f"QA {caso.get('case')}: mediana {caso.get('median_ms')} ms")
    if qa.get("conflicting_map_points"):
        fallas.append(f"{qa['conflicting_map_points']} GEO_CONFLICT en el mapa")
    return fallas


def _numeros(url: str) -> set[str]:
    p = urllib.parse.urlparse(url or "")
    return set(re.findall(r"\d{5,}", p.path + "?" + p.query))


def compuerta_datos(snapshot: Path, sobran: set[str]) -> list[str]:
    from connectors import pais
    from connectors.coherencia import _es_simbolico
    con = sqlite3.connect(f"file:{snapshot.as_posix()}?mode=ro", uri=True)
    try:
        filas = con.execute("select id, agency_id, source_url, latitud, longitud, precio, "
                            "moneda, operacion from propiedades").fetchall()
    finally:
        con.close()
    fallas = []
    fuera = sum(1 for f in filas if f[3] is not None and f[4] is not None
                and pais.contencion(f[3], f[4]) == "FUERA")
    if fuera:
        fallas.append(f"{fuera} filas con coordenada fuera del pais")
    simbolicos = sum(1 for f in filas if f[5] is not None and f[5] > 0
                     and _es_simbolico(float(f[5]), f[6], f[7]))
    if simbolicos:
        fallas.append(f"{simbolicos} precios simbolicos")
    por_numero: dict[tuple[str, str], str] = {}
    dudosos = 0
    for i, agencia, url, *_ in filas:
        for n in _numeros(url):
            previo = por_numero.setdefault((agencia, n), i)
            if previo != i and (i in sobran or previo in sobran):
                dudosos += 1
    tope = max(DUPLICADOS_TOPE_MINIMO, int(DUPLICADOS_TOPE_FRACCION * len(sobran)))
    if dudosos > tope:
        fallas.append(f"{dudosos} duplicados probables con altas (tope {tope})")
    return fallas


def compuerta_regresion(cert: Path) -> list[str]:
    gates = sorted((cert / "_regresion").glob("GATE_*.json"), key=lambda p: p.stat().st_mtime)
    if not gates:
        return ["no hay reporte del Regression Gate"]
    ultimo = json.loads(gates[-1].read_text(encoding="utf-8"))
    pendientes = int(ultimo.get("pendientes_de_revision") or 0)
    return [f"Regression Gate con {pendientes} perdidas pendientes ({gates[-1].name})"] if pendientes else []


def evaluar(servida: Path, candidata_dir: Path, cert: Path,
            faltan: set[str], sobran: set[str]) -> list[str]:
    snapshot = candidata_dir / "ERETZ_API_SNAPSHOT.sqlite3"
    return (compuerta_inventario(faltan, sobran, leer_cambios(candidata_dir))
            + compuerta_qa(candidata_dir)
            + compuerta_datos(snapshot, sobran)
            + compuerta_regresion(cert))
