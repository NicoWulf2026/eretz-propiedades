#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""¿Este paro ya lo diagnosticamos antes? §38, §102.

Sólo lectura sobre artefactos locales. `database_writes: 0`. No difiere, no
retira la bandera, no decide: contesta una pregunta antes de que alguien gaste
una hora contestándola de nuevo.

Por qué existe
--------------
El §102 dice para qué sirve todo esto: *"que una clase de error se investigue
UNA VEZ, se convierta en regla / test / replay / firma, y no vuelva a costarnos
horas cada vez que reaparece"*.

El banco de firmas ya existe. Lo que no existía es que alguien lo **consulte**
cuando la cola para. El 2026-09-17 la cola paró en `di santo negocios
inmobiliarios` con un colapso de inventario del 100%, y resultó ser la firma
exacta de `etcheverry propiedades`, diferida tres días antes: el mismo
frontend propio de Tokko, el mismo `<ul id="propiedades">` vacío que rellena
JavaScript. Reconocerlo llevó seis consultas a la fuente que no hacían falta,
porque la respuesta estaba escrita.

Cómo empareja, y por qué no usa el texto
----------------------------------------
Por campos, nunca por prosa. El §30 lo prohíbe y además el texto de un
diagnóstico está escrito para un humano, no para emparejar.

    1. misma firma MEDIDA contra el sitio        (la más fuerte)
    2. mismo mecanismo de publicación + misma forma de fallo
    3. mismo componente de triage + misma estrategia de conector

Cada coincidencia dice **por qué** coincidió y con qué fuerza. Una coincidencia
débil presentada como certeza sería peor que no buscar: haría cerrar un caso
nuevo con la explicación de otro.

Uso:
    python scripts/ya_lo_vimos.py                    # lee la bandera de paro
    python scripts/ya_lo_vimos.py --agencia "di santo"
"""
from __future__ import annotations

import argparse
import json
import textwrap
from pathlib import Path
from typing import Any

CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
RESULTADOS = CERT / "AGENCY_CERTIFICATION_RESULTS.jsonl"
DIFERIDAS = CERT / "AGENCY_DEFECTS_DIFERIDOS.jsonl"
FIRMAS = CERT / "ERETZ_FIRMA_NAVEGACION_JS.jsonl"
BANDERA = CERT / "AGENCY_CERTIFICATION_STOP.json"


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


def ultimos() -> dict[str, dict]:
    vistos: dict[str, dict] = {}
    for fila in _jsonl(RESULTADOS):
        agencia = fila.get("canonical_agency_id")
        if agencia:
            vistos[agencia] = fila
    return vistos


def firmas_medidas() -> dict[str, str]:
    return {f["agency_id"]: f["firma"] for f in _jsonl(FIRMAS)
            if f.get("agency_id") and f.get("firma")}


def forma_de_fallo(resultado: dict[str, Any]) -> str:
    """Una etiqueta corta y estructural. Nunca sale de la prosa.

    Enumerar cero es **una sola** forma de fallo, haya o no línea base. La
    primera versión las separaba en `CERO_ENUMERADAS` y
    `CERO_ENUMERADAS_CON_BASELINE`, y por eso este módulo no encontró el caso
    para el que fue escrito: `di santo` tiene baseline 30 y `etcheverry` tiene
    0, y son el mismo defecto —el mismo frontend de Tokko, el mismo contenedor
    vacío—.

    La línea base dice cuánto DUELE, no qué pasó. Mezclar severidad con forma
    parte en dos un grupo que hay que ver junto.

    Lo mismo, y peor, con el componente del triage: a los cuatro casos TFW con
    cero enumeradas les puso tres nombres distintos —`perdida_sistematica_de_
    inventario`, `posible_perdida_de_inventario`, `variante_no_soportada`— según
    hubiera línea base o no. Por eso acá el componente pesa poco.
    """
    auditoria = resultado.get("enumeration_audit") or {}
    enumeradas = auditoria.get("enumerated")
    base = auditoria.get("baseline")
    if not enumeradas:
        return "CERO_ENUMERADAS"
    if base and enumeradas < base * 0.2:
        return "COLAPSO_MAYOR_AL_80"
    declarado = auditoria.get("declared_total")
    if declarado and enumeradas < declarado:
        return "DECLARA_MAS_DE_LO_ENUMERADO"
    return "OTRA"


def parecidos(agencia: str, resultado: dict[str, Any],
              todos: dict[str, dict], medidas: dict[str, str],
              diferidas: dict[str, list[dict]]) -> list[dict[str, Any]]:
    mi_firma = medidas.get(agencia)
    mi_forma = forma_de_fallo(resultado)
    mi_mecanismo = resultado.get("publication_mechanism")
    mi_estrategia = resultado.get("connector_strategy")
    mi_componente = (diferidas.get(agencia) or [{}])[-1].get("componente")

    fuera = []
    for otra, suyo in todos.items():
        if otra == agencia or otra not in diferidas:
            continue
        razones, fuerza = [], 0
        if mi_firma and medidas.get(otra) == mi_firma:
            razones.append(f"misma firma medida contra el sitio: {mi_firma}")
            fuerza += 3
        if mi_mecanismo and suyo.get("publication_mechanism") == mi_mecanismo \
                and forma_de_fallo(suyo) == mi_forma:
            razones.append(f"mismo mecanismo ({mi_mecanismo}) y misma forma de "
                           f"fallo ({mi_forma})")
            fuerza += 2
        suyo_componente = (diferidas[otra] or [{}])[-1].get("componente")
        if mi_componente and suyo_componente == mi_componente \
                and mi_estrategia and suyo.get("connector_strategy") == mi_estrategia:
            razones.append(f"mismo componente de triage ({mi_componente}) y "
                           f"misma estrategia ({mi_estrategia})")
            fuerza += 1
        if not razones:
            continue
        ultima = diferidas[otra][-1]
        fuera.append({
            "agencia": otra, "fuerza": fuerza, "porque": razones,
            "cuando": ultima.get("cuando"),
            "diagnostico": ultima.get("diagnostico"),
            "por_que_se_difirio": ultima.get("por_que_se_difiere"),
            "verificada_contra_la_fuente":
                bool(ultima.get("firma_verificada_contra_la_fuente")),
        })
    fuera.sort(key=lambda f: f["fuerza"], reverse=True)
    return fuera


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agencia", help="nombre parcial; sin esto lee la bandera")
    ap.add_argument("--tope", type=int, default=3)
    args = ap.parse_args()

    todos = ultimos()
    nombre = args.agencia
    if not nombre:
        bandera = {}
        if BANDERA.exists():
            try:
                bandera = json.loads(BANDERA.read_text(encoding="utf-8"))
            except ValueError:
                bandera = {}
        nombre = bandera.get("canonical_agency_id")
        if not nombre:
            print("no hay bandera de paro y no se paso --agencia")
            return 1

    clave = next((a for a in todos if nombre.lower() in a.lower()), None)
    if not clave:
        print(f"sin resultado de certificacion para {nombre!r}")
        return 1

    resultado = todos[clave]
    diferidas: dict[str, list[dict]] = {}
    for fila in _jsonl(DIFERIDAS):
        agencia = fila.get("canonical_agency_id")
        if agencia:
            diferidas.setdefault(agencia, []).append(fila)

    medidas = firmas_medidas()
    auditoria = resultado.get("enumeration_audit") or {}
    print(f"{clave}")
    print(f"  estado    : {resultado.get('status')}")
    print(f"  mecanismo : {resultado.get('publication_mechanism')}")
    print(f"  estrategia: {resultado.get('connector_strategy')}")
    print(f"  enumeradas: {auditoria.get('enumerated')}  "
          f"baseline: {auditoria.get('baseline')}")
    print(f"  forma     : {forma_de_fallo(resultado)}")
    print(f"  firma medida: {medidas.get(clave) or '(no medida)'}\n")

    casos = parecidos(clave, resultado, todos, medidas, diferidas)
    if not casos:
        print("  NO HAY CASO PREVIO que empareje por campos.")
        print("  Esto es diagnostico desde cero. Cuando termine, la diferida")
        print("  firmada hace que el proximo no lo sea.")
        print("\ndatabase_writes: 0")
        return 0

    print(f"  YA LO VIMOS: {len(casos)} caso(s) previo(s)\n")
    for caso in casos[:args.tope]:
        etiqueta = ("FUERTE" if caso["fuerza"] >= 3
                    else "MEDIA" if caso["fuerza"] == 2 else "DEBIL")
        print(f"  [{etiqueta}] {caso['agencia'].split(':')[-1]}  "
              f"({caso['cuando'][:10] if caso['cuando'] else '?'}, "
              f"{'verificada' if caso['verificada_contra_la_fuente'] else 'SIN verificar'})")
        for razon in caso["porque"]:
            print(f"      - {razon}")
        if caso["diagnostico"]:
            print(textwrap.fill(caso["diagnostico"][:420], width=74,
                                initial_indent="      ", subsequent_indent="      "))
        print()

    print("  Una coincidencia DEBIL no cierra nada: dice donde mirar primero.")
    print("  Cerrar un caso nuevo con la explicacion de otro es peor que no")
    print("  haber buscado.")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
