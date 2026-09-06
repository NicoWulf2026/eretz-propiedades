#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""El quality gate: donde puede aparecer cada propiedad, y por que.

No decide si una propiedad vale. Decide en que superficies puede mostrarse sin
mentirle a nadie, aplicando `property_contract`. Una propiedad sin `operacion`
sigue teniendo ficha y sigue en el listado; lo unico que pierde es el filtro
venta/alquiler, porque ahi si estariamos afirmando algo que no sabemos.

Explicable, versionado y auditable:

  explicable  cada propiedad sale con la lista de razones por las que no llega
              a un alcance, en castellano y sin codigos internos
  versionado  `contrato_version` viaja en cada fila; cambiar el contrato se ve
              en el artefacto y no hay que adivinar con que reglas se decidio
  auditable   el artefacto es una fila por propiedad, no un agregado. Un numero
              resumido no se puede discutir; una fila si

**De donde sale el diagnostico de un campo ausente.** El contrato distingue
`SOURCE_NOT_PROVIDED` de `EXTRACTION_FAILED`, y esa diferencia importa: el
primero no tiene arreglo posible y el segundo es un defecto nuestro. La fila de
pre-ingesta no alcanza para separarlos, pero los paquetes de certificacion si
saben, por agencia y por campo, si la fuente lo publicaba. Aca se usa esa
cobertura para resolver los ausentes, y cada fila declara que el diagnostico
vino de ahi -`cobertura_de_la_agencia`- y no de la propiedad misma. Sin paquete
queda `AUSENTE_SIN_DIAGNOSTICO`, que es la verdad: todavia no sabemos.

No escribe en ninguna base.
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

from scripts.property_contract import (AUSENTE_SIN_DIAGNOSTICO,  # noqa: E402
                                       CONTRATO_VERSION, evaluar)

GATE_VERSION = "property_quality_gate_v1"


def geografia_por_propiedad(cobertura: Path) -> dict[str, dict[str, Any]]:
    """Las dimensiones geograficas ya resueltas, por propiedad.

    Sale de `GEO_COVERAGE_AUDIT.jsonl`, que corre el mismo resolver del
    pipeline y exige corroboracion antes de afirmar una localidad. Sin esto el
    gate leia `ciudad` cruda y contaba un barrio como si fuera una localidad
    censal.
    """
    fuera: dict[str, dict[str, Any]] = {}
    if not cobertura.exists():
        return fuera
    for linea in cobertura.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        fila = json.loads(linea)
        if fila.get("hash_dedup"):
            fuera[fila["hash_dedup"]] = fila
    return fuera


def ciudades_propuestas(auditoria: Path) -> dict[str, dict[str, Any]]:
    """Las propuestas de ciudad que la auditoria dio por aptas, por propiedad.

    Se leen las APTAS unicamente. Las 6.890 retenidas -entre ellas `Villa del
    Parque`, barrio de CABA, propuesto como localidad de Rio Negro- no entran
    ni siquiera en la proyeccion: proyectar sobre datos que no se van a
    escribir seria prometer un filtro que no va a existir.
    """
    fuera: dict[str, dict[str, Any]] = {}
    if not auditoria.exists():
        return fuera
    for linea in auditoria.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        fila = json.loads(linea)
        if not fila.get("apta_para_escritura"):
            continue
        hash_dedup = fila.get("hash_dedup")
        if hash_dedup:
            fuera[hash_dedup] = fila.get("propuesto") or {}
    return fuera


def cobertura_por_agencia(paquetes: Path) -> dict[str, dict[str, bool]]:
    """Por agencia y campo: la fuente lo publicaba, si o no.

    Sale de `field_coverage` de cada certificacion, que es donde se comparo lo
    que la pagina ofrecia contra lo que el parser saco.

    **Haberlo extraido tambien prueba que la fuente lo publica.** El detector
    de senales de origen mira el marcado y falla hacia el "no lo publica":
    `alpha inmobiliaria` figura con `source_provided: 0` en `descripcion` y al
    mismo tiempo con las 127 descripciones extraidas. Leyendo solo la senal,
    esas 127 fichas exoneraban al parser con un `SOURCE_NOT_PROVIDED` -"no hay
    nada que arreglar"- sobre un campo que la fuente evidentemente publica.
    Son 128 de 290 exoneraciones, el 44 %.

    Sumar la extraccion como evidencia solo puede mover un campo de exonerado
    a `EXTRACTION_FAILED`, es decir hacia buscar defectos nuestros, que es el
    lado por el que hay que fallar.
    """
    fuera: dict[str, dict[str, bool]] = {}
    if not paquetes.exists():
        return fuera
    for carpeta in paquetes.iterdir():
        archivo = carpeta / "certification.json"
        if not archivo.exists():
            continue
        try:
            paquete = json.loads(archivo.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        campos = paquete.get("field_coverage") or {}
        publica: dict[str, bool] = {}
        for campo, dato in campos.items():
            if not isinstance(dato, dict):
                continue
            provistos = dato.get("source_provided")
            extraidos = dato.get("normalized_present")
            if isinstance(provistos, int):
                publica[campo] = (provistos > 0
                                  or (isinstance(extraidos, int)
                                      and extraidos > 0))
        if publica:
            fuera[paquete.get("canonical_agency_id")] = publica
    return fuera


def main() -> int:
    # La base sale del manifiesto, no de una ruta escrita a mano: una snapshot
    # vieja clavada en el default ya hizo que el certificador midiera contra un
    # universo al que le faltaban 13.023 candidatas.
    from scripts.preingestion_manifest import (base_canonica,
                                            exigir_base_vigente)

    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(base_canonica()))
    ap.add_argument("--paquetes", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827\agencies")
    # El artefacto vive al lado de la base que describe, asi que la salida
    # sigue a la canonica en vez de repetir la ruta.
    ap.add_argument("--salida", default=str(base_canonica().parent))
    ap.add_argument("--limite", type=int, default=0)
    ap.add_argument("--sondeo-geometrico",
                    default=r"D:\INMO CAPITAL\ERETZ_GEO\GEO_REVERSE_PROBE.jsonl")
    ap.add_argument("--cobertura-geografica",
                    default=r"D:\INMO CAPITAL\ERETZ_GEO\GEO_COVERAGE_AUDIT.jsonl")
    ap.add_argument("--auditoria-de-ciudad",
                    default=r"D:\INMO CAPITAL\ERETZ_GEO\CIUDAD_DRYRUN_AUDIT.jsonl")
    args = ap.parse_args()
    # Una base vencida es legible y no se queja: hay que preguntar.
    exigir_base_vigente(args.db)

    cobertura = cobertura_por_agencia(Path(args.paquetes))
    propuestas = ciudades_propuestas(Path(args.auditoria_de_ciudad))
    geo_por_hash = geografia_por_propiedad(Path(args.cobertura_geografica))
    geometria = geografia_por_propiedad(Path(args.sondeo_geometrico))
    conexion = sqlite3.connect(f"file:{Path(args.db).as_posix()}?mode=ro", uri=True)
    consulta = ("select row_json, canonical_id, hash_dedup from rows "
                "where status = 'CANDIDATE'")
    if args.limite:
        consulta += f" limit {args.limite}"

    destino = Path(args.salida) / "PROPERTY_QUALITY_GATE.jsonl"
    alcances: Counter = Counter()
    proyectados: Counter = Counter()
    niveles_actuales: Counter = Counter()
    niveles_proyectados: Counter = Counter()
    con_municipio_geometrico = 0
    razones: Counter = Counter()
    estados: Counter = Counter()
    con_diagnostico = sin_diagnostico = 0
    fallos_por_campo: Counter = Counter()
    total = publicables = 0
    agencias_con_cobertura = set()

    with destino.open("w", encoding="utf-8") as archivo:
        for crudo, canonical, hash_dedup in conexion.execute(consulta):
            fila = json.loads(crudo)
            total += 1
            fuente = cobertura.get(canonical)
            if fuente:
                agencias_con_cobertura.add(canonical)
            geo = geo_por_hash.get(hash_dedup)
            niveles_actuales[((geo or {}).get("area_busqueda") or {}).get("nivel")
                             or "SIN_AREA"] += 1
            veredicto = evaluar(fila, fuente, geo)
            publicables += bool(veredicto["publicable"])
            for alcance in veredicto["alcances"]:
                alcances[alcance] += 1

            # El alcance que HABRIA si las propuestas aptas estuvieran
            # escritas. Se informa aparte y nunca reemplaza al real: la
            # geografia esta resuelta y sin escribir porque la base de
            # produccion no responde, y confundir "se puede" con "esta" es
            # prometer un filtro que hoy no existe.
            # La proyeccion ya NO es "si se escribieran las propuestas de
            # ciudad": la cobertura aplica la misma regla de corroboracion que
            # decide cuales son aptas, asi que esas ya estan contadas arriba.
            # Lo que falta medir es el escalon siguiente: el municipio
            # geometrico como AREA DE BUSQUEDA, que no afirma localidad.
            geo_proyectada = dict(geo or {})
            sonda = geometria.get(hash_dedup)
            nivel_actual = ((geo or {}).get("area_busqueda") or {}).get("nivel")
            if sonda and nivel_actual in (None, "SIN_AREA", "PROVINCIA"):
                municipio = sonda.get("municipio_geometrico")
                departamento = sonda.get("departamento_geometrico")
                if municipio:
                    geo_proyectada["area_busqueda"] = {
                        "nivel": "MUNICIPIO", "valor": municipio}
                    con_municipio_geometrico += 1
                elif departamento:
                    geo_proyectada["area_busqueda"] = {
                        "nivel": "DEPARTAMENTO", "valor": departamento}
            for alcance in evaluar(fila, fuente, geo_proyectada)["alcances"]:
                proyectados[alcance] += 1
            niveles_proyectados[
                (geo_proyectada.get("area_busqueda") or {}).get("nivel")
                or "SIN_AREA"] += 1
            for razon in veredicto["razones_de_exclusion"]:
                razones[razon] += 1
            for campo, estado in veredicto["estados_de_campo"].items():
                estados[estado] += 1
                if estado == AUSENTE_SIN_DIAGNOSTICO:
                    sin_diagnostico += 1
                elif estado in ("SOURCE_NOT_PROVIDED", "EXTRACTION_FAILED"):
                    con_diagnostico += 1
                if estado == "EXTRACTION_FAILED":
                    fallos_por_campo[campo] += 1
            archivo.write(json.dumps({
                "hash_dedup": hash_dedup,
                "canonical_agency_id": canonical,
                "source_url": fila.get("source_url"),
                "gate_version": GATE_VERSION,
                "origen_del_diagnostico": ("cobertura_de_la_agencia" if fuente
                                           else "sin_paquete_de_certificacion"),
                "area_busqueda": (geo or {}).get("area_busqueda"),
                "localidad_canonica": (geo or {}).get("localidad_canonica"),
                **veredicto,
            }, ensure_ascii=False) + "\n")

    resumen = {
        "gate_version": GATE_VERSION,
        "contrato_version": CONTRATO_VERSION,
        "propiedades_evaluadas": total,
        "publicables": publicables,
        "no_publicables": total - publicables,
        "por_alcance": dict(alcances.most_common()),
        "por_alcance_con_municipio_geometrico": dict(proyectados.most_common()),
        "area_de_busqueda_por_nivel_hoy": dict(niveles_actuales.most_common()),
        "area_de_busqueda_por_nivel_proyectada": dict(niveles_proyectados.most_common()),
        "propiedades_que_suben_a_nivel_municipio": con_municipio_geometrico,
        "propuestas_de_ciudad_aptas_leidas": len(propuestas),
        "puntos_con_sondeo_geometrico": len(geometria),
        "motivos_de_alcance_reducido": dict(razones.most_common()),
        "estados_de_campo": dict(estados.most_common()),
        "campos_ausentes_con_diagnostico": con_diagnostico,
        "campos_ausentes_sin_diagnostico": sin_diagnostico,
        "extraccion_fallida_por_campo": dict(fallos_por_campo.most_common()),
        "agencias_con_cobertura_certificada": len(agencias_con_cobertura),
        "database_writes": 0,
        "artefacto": destino.name,
    }
    (Path(args.salida) / "PROPERTY_QUALITY_GATE_SUMMARY.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
