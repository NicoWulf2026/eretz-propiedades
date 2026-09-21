#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""El contrato de propiedad que consume el frontend, y fixtures reales.

Codex construye el frontend en paralelo y no puede quedarse esperando a que
vuelva produccion. Este modulo fija la forma de una propiedad publicada y
genera fixtures a partir de los datos LOCALES, no inventados: si el frontend
se construye contra propiedades imaginarias, el dia que se conecte descubre
que la mitad de los campos son null.

**Nullability primero.** La regla del sistema es que una propiedad real
incompleta sobrevive, asi que el frontend TIENE que estar preparado para que
falte casi cualquier cosa. El contrato marca lo que nunca es null y lo que
puede serlo, con el porcentaje medido para que nadie disene una tarjeta
suponiendo que siempre hay precio.

**Los alcances mandan sobre la presentacion.** Una propiedad sin localidad
demostrada NO se muestra con una ciudad inventada: se muestra con su area de
busqueda y su nivel. Por eso `alcances` viaja en cada fila.

No escribe en ninguna base.
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from connectors.geografia import geografia_de_fila_publicable  # noqa: E402
from scripts.preingestion_manifest import (base_canonica,  # noqa: E402
                                           exigir_base_vigente)

CONTRATO_API_VERSION = "eretz_api_property_v1"

# Lo unico que nunca puede faltar. Coincide con `IDENTIDAD` del contrato de
# propiedad: sin esto no hay a que volver ni como deduplicar.
NUNCA_NULO = ("id", "source_url", "agency_id", "alcances")

# La forma de una propiedad publicada. El tipo dice que esperar; el
# comentario, que hacer cuando falta.
FORMA: dict[str, dict[str, Any]] = {
    "id": {"tipo": "string", "nulo": False,
           "nota": "hash_dedup: estable entre corridas"},
    "source_url": {"tipo": "string", "nulo": False,
                   "nota": "la ficha en el sitio de la inmobiliaria"},
    "agency_id": {"tipo": "string", "nulo": False,
                  "nota": "canonical_agency_id"},
    "titulo": {"tipo": "string", "nulo": True,
               "nota": "si falta, hay descripcion: nunca faltan las dos"},
    "descripcion": {"tipo": "string", "nulo": True},
    "operacion": {"tipo": "enum(venta|alquiler|alquiler_temporario)", "nulo": True,
                  "nota": "sin esto no entra al filtro venta/alquiler"},
    "tipo_propiedad": {"tipo": "string", "nulo": True},
    "precio": {"tipo": "number", "nulo": True},
    "moneda": {"tipo": "enum(USD|ARS)", "nulo": True,
               "nota": "un precio sin moneda NO es un precio: no mostrarlo"},
    "ambientes": {"tipo": "integer", "nulo": True},
    "dormitorios": {"tipo": "integer", "nulo": True},
    "banos": {"tipo": "integer", "nulo": True},
    "superficie_total": {"tipo": "number", "nulo": True},
    "superficie_cubierta": {"tipo": "number", "nulo": True},
    "imagenes": {"tipo": "string[]", "nulo": False,
                 "nota": "puede venir vacia; no descartar la propiedad por eso"},
    "latitud": {"tipo": "number", "nulo": True},
    "longitud": {"tipo": "number", "nulo": True},
    "geo": {"tipo": "objeto", "nulo": False, "nota": "ver FORMA_GEO"},
    "alcances": {"tipo": "string[]", "nulo": False,
                 "nota": "donde puede aparecer; ver ALCANCES"},
}

# Las cinco dimensiones, cada una con su procedencia. NINGUNA rellena a otra.
FORMA_GEO: dict[str, dict[str, Any]] = {
    "provincia": {"tipo": "dimension", "nulo": True},
    "departamento": {"tipo": "dimension", "nulo": True},
    "municipio": {"tipo": "dimension", "nulo": True},
    "localidad": {"tipo": "dimension", "nulo": True,
                  "nota": "UNKNOWN cuando no se pudo demostrar, AUNQUE haya "
                          "municipio. No sustituirla por el area."},
    "barrio": {"tipo": "dimension", "nulo": True,
               "nota": "texto de la fuente; puede no estar canonizado"},
    "area_busqueda": {"tipo": "objeto", "nulo": False,
                      "nota": "{nivel, nombre, id, origen}. El NIVEL es "
                              "obligatorio de mostrar: sin el, un municipio se "
                              "lee como una ciudad."},
}

DIMENSION = {"id": "string|null", "nombre": "string|null",
             "procedencia": "SOURCE_STRUCTURED|SOURCE_TEXT|"
                            "CANONICAL_NORMALIZED|GEOMETRY|UNKNOWN",
             "confianza": "string|null", "evidencia": "string|null",
             "rechazo": "string|null"}

ALCANCES = ("FICHA", "LISTADO", "MAPA", "FILTRO_PRECIO", "FILTRO_TIPO",
            "FILTRO_OPERACION", "FILTRO_LOCALIDAD", "AREA_BUSQUEDA")

# Reglas que el frontend NO puede romper sin mentir.
REGLAS_DE_PRESENTACION = (
    "Nunca mostrar `area_busqueda.nombre` como si fuera la ciudad: si el nivel "
    "no es LOCALIDAD, decir el nivel.",
    "Nunca componer 'Ciudad, Provincia' a partir del area de busqueda.",
    "Un precio sin moneda no se muestra como precio.",
    "Una propiedad sin imagenes se muestra igual, con placeholder.",
    "Un alcance ausente esconde el FILTRO, nunca la propiedad.",
)


def _procedencia(geo: dict[str, Any] | None, dimension: str) -> str:
    """De donde salio esta dimension, o `UNKNOWN` si no esta.

    `UNKNOWN` cuando el nombre falta, igual que hace `localidad`: una
    dimension vacia no tiene procedencia, y devolver la de otra cosa seria
    peor que no devolver nada.
    """
    if not (geo or {}).get(f"{dimension}_canonico"):
        return "UNKNOWN"
    return ((geo or {}).get("procedencia_de_dimensiones") or {}).get(
        dimension, "UNKNOWN")


def fila_de_api(fila: dict[str, Any], geo: dict[str, Any] | None,
                alcances: list[str]) -> dict[str, Any]:
    """Una propiedad con la forma exacta que consume el frontend."""
    geo = geografia_de_fila_publicable(fila, geo)
    if geo.get('estado_geografico') == 'GEO_CONFLICT':
        alcances = [s for s in alcances if s not in ('FILTRO_LOCALIDAD', 'AREA_BUSQUEDA', 'MAPA')]
    return {
        "id": fila.get("hash_dedup"),
        "source_url": fila.get("source_url"),
        "agency_id": fila.get("canonical_agency_id"),
        "titulo": fila.get("titulo"),
        "descripcion": fila.get("descripcion"),
        "operacion": fila.get("operacion"),
        "tipo_propiedad": fila.get("tipo_propiedad"),
        "precio": fila.get("precio"),
        "moneda": fila.get("moneda"),
        "ambientes": fila.get("ambientes"),
        "dormitorios": fila.get("dormitorios"),
        "banos": fila.get("banos"),
        "superficie_total": fila.get("superficie_total"),
        "superficie_cubierta": fila.get("superficie_cubierta"),
        "imagenes": fila.get("imagenes") or [],
        "latitud": (None if geo.get('estado_geografico') == 'GEO_CONFLICT' else fila.get("latitud")),
        "longitud": (None if geo.get('estado_geografico') == 'GEO_CONFLICT' else fila.get("longitud")),
        "geo": {
            "localidad": {"nombre": (geo or {}).get("localidad_canonica"),
                          "id": (geo or {}).get("localidad_id"),
                          "procedencia": ("CANONICAL_NORMALIZED"
                                          if (geo or {}).get("localidad_canonica")
                                          else "UNKNOWN")},
            # Municipio y departamento viajan CON su procedencia. La mayoria
            # ahora sale de la geometria oficial -contencion en el poligono de
            # GeoRef- y no del nombre que escribio la fuente. Las dos cosas
            # son ciertas y no son lo mismo, asi que el consumidor tiene que
            # poder distinguirlas: sin este campo, publicar 33.003 municipios
            # nuevos seria promoverlos en silencio.
            "municipio": {"nombre": (geo or {}).get("municipio_canonico"),
                          "procedencia": _procedencia(geo, "municipio")},
            "departamento": {"nombre": (geo or {}).get("departamento_canonico"),
                             "procedencia": _procedencia(geo, "departamento")},
            "provincia": {"nombre": (geo or {}).get("provincia_canonica")},
            "barrio": {"nombre": (geo or {}).get("barrio_fuente")},
            "area_busqueda": (geo or {}).get("area_busqueda")
                             or {"nivel": "SIN_AREA", "nombre": None,
                                 "id": None, "origen": "sin_area"},
            "estado": (geo or {}).get("estado_geografico"),
        },
        "alcances": alcances,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(base_canonica()))
    ap.add_argument("--gate",
                    default=str(base_canonica().parent / "PROPERTY_QUALITY_GATE.jsonl"))
    ap.add_argument("--cobertura",
                    default=r"D:\INMO CAPITAL\ERETZ_GEO\GEO_COVERAGE_AUDIT.jsonl")
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\ERETZ_API_CONTRACT")
    ap.add_argument("--fixtures", type=int, default=60,
                    help="cuantas propiedades reales dejar como muestra")
    args = ap.parse_args()
    exigir_base_vigente(args.db)

    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)

    geo_por_hash: dict[str, dict[str, Any]] = {}
    ruta_cobertura = Path(args.cobertura)
    if ruta_cobertura.exists():
        for linea in ruta_cobertura.read_text(encoding="utf-8").splitlines():
            if linea.strip():
                f = json.loads(linea)
                geo_por_hash[f["hash_dedup"]] = f

    alcances_por_hash: dict[str, list[str]] = {}
    ruta_gate = Path(args.gate)
    if ruta_gate.exists():
        for linea in ruta_gate.read_text(encoding="utf-8").splitlines():
            if linea.strip():
                f = json.loads(linea)
                alcances_por_hash[f["hash_dedup"]] = f.get("alcances") or []

    conexion = sqlite3.connect(f"file:{Path(args.db).as_posix()}?mode=ro", uri=True)
    presentes: Counter = Counter()
    total = 0
    muestra: list[dict[str, Any]] = []
    azar = random.Random(20260906)   # semilla fija: la muestra es reproducible

    for (crudo,) in conexion.execute(
            "select row_json from rows where status = 'CANDIDATE'"):
        fila = json.loads(crudo)
        total += 1
        api = fila_de_api(fila, geo_por_hash.get(fila.get("hash_dedup")),
                          alcances_por_hash.get(fila.get("hash_dedup"), []))
        for campo in FORMA:
            valor = api.get(campo)
            if valor not in (None, "", []):
                presentes[campo] += 1
        # Muestreo por reservorio: una muestra representativa sin cargar las
        # 58.427 en memoria.
        if len(muestra) < args.fixtures:
            muestra.append(api)
        else:
            i = azar.randint(0, total - 1)
            if i < args.fixtures:
                muestra[i] = api

    contrato = {
        "contrato_api_version": CONTRATO_API_VERSION,
        "propiedades_medidas": total,
        "forma": FORMA,
        "forma_geo": FORMA_GEO,
        "dimension": DIMENSION,
        "alcances_posibles": list(ALCANCES),
        "reglas_de_presentacion": list(REGLAS_DE_PRESENTACION),
        "nunca_nulo": list(NUNCA_NULO),
        "presencia_medida_pct": {
            campo: round(100 * presentes[campo] / total, 1) if total else 0
            for campo in FORMA},
        "database_writes": 0,
    }
    (salida / "ERETZ_API_PROPERTY_CONTRACT.json").write_text(
        json.dumps(contrato, ensure_ascii=False, indent=2), encoding="utf-8")
    (salida / "ERETZ_API_FIXTURES.json").write_text(
        json.dumps(muestra, ensure_ascii=False, indent=2), encoding="utf-8")

    resumen = {k: contrato[k] for k in
               ("contrato_api_version", "propiedades_medidas",
                "presencia_medida_pct", "database_writes")}
    resumen["fixtures"] = len(muestra)
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
