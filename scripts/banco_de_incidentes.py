#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Los 24 incidentes reales, convertidos en replay permanente. §13, §30, §102.

Sólo lectura sobre artefactos locales. `database_writes: 0`.

El §102 dice para qué sirve esto: que una clase de error se investigue **una
vez**. Hoy cada incidente vive repartido entre un resultado de certificación,
una diferida firmada y, a veces, nada. Este módulo los junta en un solo archivo
con la forma que pide el §13, y —lo importante— anota para cada uno qué es lo
que **nunca** puede volver a pasar.

La regla de honestidad que gobierna todo el módulo
--------------------------------------------------
El §30 prohíbe decidir desde texto humano. Así que la causa raíz de cada
incidente no se infiere ni se redacta acá: se toma de campos, y cuando no hay
campo, el incidente queda `SIN_EVIDENCIA_ESTRUCTURADA` y se dice cuál es el
artefacto que falta. Un banco con 24 filas donde seis son inventadas vale menos
que uno con 18 reales y seis huecos declarados.

Cada incidente lleva:

    incident_id            estable, derivado del nombre
    root_cause             de la firma diferida, o SIN_EVIDENCIA_ESTRUCTURADA
    expected_behavior      qué tendría que dar
    forbidden_behavior     qué no puede volver a pasar, nunca
    evidence               de dónde sale, con el artefacto nombrado
    component_affected     radio declarado por el triage

El campo que hace el trabajo a largo plazo es `forbidden_behavior`. Los otros
describen el pasado; ése es el que se puede convertir en test.

Uso:
    python scripts/banco_de_incidentes.py
    python scripts/banco_de_incidentes.py --verificar
"""
from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
RESULTADOS = CERT / "AGENCY_CERTIFICATION_RESULTS.jsonl"
DIFERIDAS = CERT / "AGENCY_DEFECTS_DIFERIDOS.jsonl"
SALIDA = CERT / "ERETZ_BANCO_DE_INCIDENTES.jsonl"

# Los 24 que nombra el §13, en su orden.
INCIDENTES = [
    "ventasprop", "andrade", "alma", "alta", "a varela", "alejandro foster",
    "ancarola", "cip", "benitez ullo", "andrea gianfelice", "blanco",
    "bottega", "cavacini", "ciam", "espina", "carames", "diego malizia",
    "cipollone", "arte propiedades", "blangiforti", "berardi", "constant",
    "emir elhelou", "analia requena",
]

# Lo prohibido por firma. No describe el sintoma: describe la conclusion que no
# se puede volver a sacar. Es lo unico de este archivo que se convierte en test.
PROHIBIDO_POR_FIRMA = {
    "posible_perdida_de_inventario":
        "cerrar COMPLETE mientras la fuente declara mas de lo enumerado, o "
        "convertir un fallo de descubrimiento en NO_INVENTORY",
    "perdida_sistematica_de_inventario":
        "tratar una perdida repetida como ruido de una agencia suelta",
    "inventario_inestable_entre_corridas":
        "elegir una de las dos corridas como buena sin distinguir "
        "SCRAPER_NONDETERMINISM de SOURCE_MUTATION",
    "catalogo_declarado_mayor_que_el_enumerado":
        "declarar enumeracion agotada sin exhaustion_reason",
    "enumeracion_compartida":
        "atribuir a una agencia inventario que aparece tambien en otra",
    "lectura_de_ficha_compartida":
        "dar por propia una ficha que se leyo desde el catalogo de otra",
    "extraccion_transversal_de_atributos":
        "dar el campo por NOT_PROVIDED cuando la senal del certificador si "
        "disparo sobre el texto: eso es EXTRACTION_FAILED y se cuenta distinto",
    "extraccion_de_baja_magnitud":
        "subir el umbral del 2% sin evidencia nueva",
    "imagenes_compartidas":
        "publicar como imagen de la propiedad una que se repite en todo el sitio",
    "variante_no_soportada":
        "cerrar NO_INVENTORY_CONFIRMED sin haber probado que no hay catalogo",
    "sitio_externo":
        "enumerar inventario desde un perfil de portal ajeno",
    "fuente_inaccesible":
        "convertir un timeout en ausencia de inventario",
    "inventario_chico":
        "asumir que pocas propiedades significan catalogo incompleto",
    "sin_determinar":
        "cerrar el incidente sin nombrar la causa",
}

# Incidentes cuyo valor de referencia esta en lo que DEMUESTRAN, y que el
# mandato nombra explicitamente. La nota no reemplaza la evidencia: la agrega.
NOTA_DE_REFERENCIA = {
    "analia requena": (
        "§32 y §60. Es el caso de referencia que separa las dos "
        "certificaciones: el inventario puede enumerarse entero y consistente "
        "y aun asi tener la provincia mal. INVENTORY_GATE puede pasar mientras "
        "DATA_QUALITY_GATE falla en geo. Usar COMPLETE como garantia de campos "
        "es exactamente el error que este incidente documenta"),
    "carames": "§26. Determinismo es P0: va antes que recuperar un campo",
    "diego malizia": "§26. Determinismo es P0: va antes que recuperar un campo",
    "ancarola": "§26. Determinismo es P0: va antes que recuperar un campo",
    "cipollone": "§21. Soft-404: HTTP 200 no demuestra que la ruta exista",
    "emir elhelou": (
        "§8. Fuente actual en portal externo teniendo dominio propio vivo. "
        "Verificado apto para el canario de cambio de fuente"),
    "blanco": "§50 P1. El volumen mas grande de precios pendientes",
}


def _jsonl(ruta: Path):
    if not ruta.exists():
        return
    for linea in ruta.open(encoding="utf-8", errors="replace"):
        linea = linea.strip()
        if not linea:
            continue
        try:
            yield json.loads(linea)
        except ValueError:
            continue


def ultimos_resultados() -> dict[str, dict]:
    ultimo: dict[str, dict] = {}
    for fila in _jsonl(RESULTADOS):
        agencia = fila.get("canonical_agency_id")
        if agencia:
            ultimo[agencia] = fila
    return ultimo


def diferidas_por_agencia() -> dict[str, list[dict]]:
    por_agencia: dict[str, list[dict]] = defaultdict(list)
    for fila in _jsonl(DIFERIDAS):
        agencia = fila.get("canonical_agency_id")
        if agencia:
            por_agencia[agencia].append(fila)
    return por_agencia


def armar(nombre: str, resultados: dict[str, dict],
          diferidas: dict[str, list[dict]]) -> dict[str, Any]:
    incident_id = "INC-" + nombre.upper().replace(" ", "_")
    coincide = [a for a in resultados if nombre in a.lower()]
    if not coincide:
        return {
            "incident_id": incident_id, "agency_name": nombre,
            "canonical_agency_id": None,
            "root_cause": "SIN_EVIDENCIA_ESTRUCTURADA",
            "expected_behavior": None, "forbidden_behavior": None,
            "evidence": "no hay resultado de certificacion para este nombre en "
                        "AGENCY_CERTIFICATION_RESULTS.jsonl",
            "component_affected": None,
            "replay_listo": False,
            "que_falta": "correr la certificacion de esta agencia, o corregir "
                         "el nombre si figura con otro",
        }

    agencia = coincide[0]
    resultado = resultados[agencia]
    propias = diferidas.get(agencia, [])
    firmada = propias[-1] if propias else {}
    firma = firmada.get("componente")
    auditoria = resultado.get("enumeration_audit") or {}

    if firma and firma in PROHIBIDO_POR_FIRMA:
        causa = firma
        prohibido = PROHIBIDO_POR_FIRMA[firma]
        evidencia = (f"diferida firmada del {firmada.get('cuando', '?')[:10]} "
                     f"en AGENCY_DEFECTS_DIFERIDOS.jsonl, radio "
                     f"{firmada.get('radio')}")
        verificada = bool(firmada.get("firma_verificada_contra_la_fuente"))
    elif firma:
        causa, prohibido = firma, None
        evidencia = "diferida firmada con componente fuera del vocabulario"
        verificada = bool(firmada.get("firma_verificada_contra_la_fuente"))
    else:
        causa = "SIN_EVIDENCIA_ESTRUCTURADA"
        prohibido = None
        evidencia = (f"hay resultado ({resultado.get('status')}) pero ninguna "
                     f"diferida firmada: la causa nunca se escribio en un campo")
        verificada = False

    esperado = None
    declarado = auditoria.get("declared_total")
    enumerado = auditoria.get("enumerated")
    if declarado and enumerado is not None and enumerado < declarado:
        esperado = (f"enumerar las {declarado} que la fuente declara; hoy "
                    f"enumera {enumerado}")
    elif resultado.get("status") == "NEEDS_FIX":
        esperado = f"llegar a un estado terminal; hoy cierra NEEDS_FIX"

    fila = {
        "incident_id": incident_id,
        "agency_name": resultado.get("agency_name") or nombre,
        "canonical_agency_id": agencia,
        "root_cause": causa,
        "expected_behavior": esperado,
        "forbidden_behavior": prohibido,
        "evidence": evidencia,
        "evidence_verificada_contra_la_fuente": verificada,
        "component_affected": firmada.get("radio") or resultado.get("connector_strategy"),
        "status_actual": resultado.get("status"),
        "enumerated": enumerado,
        "declared_total": declarado,
        "platform": resultado.get("platform"),
        "source_url": resultado.get("official_url"),
        "diferidas": len(propias),
        # Un incidente esta listo para replay cuando se puede escribir un test
        # que falle si vuelve a pasar. Sin `forbidden_behavior` no se puede.
        "replay_listo": bool(prohibido),
    }
    nota = NOTA_DE_REFERENCIA.get(nombre)
    if nota:
        fila["nota_de_referencia"] = nota
    if not prohibido:
        fila["que_falta"] = ("nombrar la causa en una diferida firmada: sin "
                             "eso no hay invariante que fijar")
    return fila


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verificar", action="store_true",
                    help="comprobar que los incidentes con replay siguen "
                         "teniendo su evidencia")
    args = ap.parse_args()

    resultados = ultimos_resultados()
    diferidas = diferidas_por_agencia()
    filas = [armar(n, resultados, diferidas) for n in INCIDENTES]

    SALIDA.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n"
                              for f in filas), encoding="utf-8")

    listos = [f for f in filas if f["replay_listo"]]
    sin_causa = [f for f in filas
                 if f["root_cause"] == "SIN_EVIDENCIA_ESTRUCTURADA"]

    print(f"incidentes del §13: {len(filas)}")
    print(f"  con invariante que se puede fijar: {len(listos)}")
    print(f"  sin causa en ningun campo:         {len(sin_causa)}\n")
    print(f"  {'INCIDENTE':24} {'CAUSA RAIZ':38} {'REPLAY':7} VERIF")
    print(f"  {'-' * 24} {'-' * 38} {'-' * 7} -----")
    for f in filas:
        marca = "SI" if f["replay_listo"] else "--"
        ver = "si" if f.get("evidence_verificada_contra_la_fuente") else "-"
        print(f"  {f['agency_name'][:24]:24} {str(f['root_cause'])[:38]:38} "
              f"{marca:7} {ver}")

    if sin_causa:
        print(f"\n  Sin causa escrita en ningun campo ({len(sin_causa)}):")
        for f in sin_causa:
            print(f"     {f['agency_name'][:26]:28} {f.get('que_falta', '')[:46]}")
        print("\n  No se les inventa una. El §30 prohibe decidir desde texto y")
        print("  el §13 pide causa raiz: sin campo, el incidente queda abierto.")

    if args.verificar:
        print(f"\n{'=' * 74}\nVERIFICACION")
        rotos = [f for f in listos
                 if not f.get("evidence_verificada_contra_la_fuente")]
        print(f"  con invariante pero sin firma verificada contra la fuente: "
              f"{len(rotos)}")
        for f in rotos:
            print(f"     {f['agency_name'][:30]:32} {f['root_cause'][:32]}")
        if not rotos:
            print("  todas las invariantes tienen firma verificada")

    print(f"\nartefacto: {SALIDA}")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
