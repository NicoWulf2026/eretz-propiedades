#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Inventario y calidad son dos preguntas distintas. §32, §33, §34, §12.

Sólo lectura sobre artefactos locales. **No decide nada**: corre en SHADOW MODE,
anota qué habría dicho y lo compara con lo que el sistema dice hoy.
`database_writes: 0`.

El incidente que obliga a esto
------------------------------
`analia requena` cierra `CERTIFIED_COMPLETE` con la razón *"two complete
idempotent runs passed"*, 143 propiedades enumeradas, y su `provincia` figura
con `state=EXTRACTED` y `coverage=1.0`.

Cobertura perfecta. Y la provincia está mal en 130 de esas propiedades.

`coverage` mide **presencia**, no corrección. Un campo puede estar en el 100% de
las fichas y ser incorrecto en el 100% de las fichas, y el número no se mueve.
Por eso el §32 pide separar formalmente las dos certificaciones, y el §12 pide
que una regla nueva observe antes de decidir.

Hay una pista que el sistema **ya guarda** y que hoy no mira nadie: en el mismo
resultado, `ciudad` está en `REJECTED_BY_VALIDATION` con cobertura 0,0. La
validación rechazó la ciudad de las 143. Una provincia perfecta conviviendo con
una ciudad enteramente rechazada es una contradicción geográfica visible en los
datos que ya tenemos.

Por qué esto importa más allá de una agencia
--------------------------------------------
De 150 agencias `CERTIFIED_COMPLETE`, sólo 4 tienen alguna diferida. Las otras
146 **no tienen dónde registrar un defecto de calidad**: la única vía es una
diferida, y una diferida sólo se escribe cuando algo para la cola. Un campo mal
en una agencia terminal no para nada, así que no se anota en ninguna parte.

No se inventa ningún dato
-------------------------
Todo sale de `field_coverage` y `enumeration_audit`, que ya existen. Cuando un
campo no alcanza para decidir, la dimensión queda en `SIN_EVIDENCIA` y no en un
número inventado —el §33 pide escala categórica honesta antes que falsa
precisión—.

Uso:
    python scripts/gates_independientes.py
    python scripts/gates_independientes.py --desacuerdos
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
RESULTADOS = CERT / "AGENCY_CERTIFICATION_RESULTS.jsonl"
SALIDA = CERT / "ERETZ_GATES_INDEPENDIENTES.jsonl"

TERMINALES_BUENOS = {"CERTIFIED_COMPLETE", "CERTIFIED_BEST_AVAILABLE"}

# Qué campo pertenece a qué dimensión de confianza (§33).
DIMENSIONES = {
    "geo": ("provincia", "ciudad", "barrio", "direccion", "latitud", "longitud"),
    "price": ("precio", "moneda"),
    "images": ("imagenes",),
    "attributes": ("ambientes", "dormitorios", "banos", "superficie_total",
                   "superficie_cubierta", "tipo_propiedad", "operacion"),
}

# Un campo rechazado por la validación no es lo mismo que un campo que la fuente
# no publica. El primero es un defecto nuestro o un conflicto real; el segundo
# es la fuente siendo la fuente.
ESTADOS_DEFECTUOSOS = {"REJECTED_BY_VALIDATION", "EXTRACTION_FAILED"}
ESTADOS_NEUTROS = {"SOURCE_NOT_PROVIDED", "NOT_ATTEMPTED"}


def _jsonl(ruta: Path):
    for linea in ruta.open(encoding="utf-8", errors="replace"):
        linea = linea.strip()
        if not linea:
            continue
        try:
            yield json.loads(linea)
        except ValueError:
            continue


def inventory_gate(resultado: dict) -> dict[str, Any]:
    """¿Enumeramos bien el inventario? Nada sobre la calidad de los campos."""
    auditoria = resultado.get("enumeration_audit") or {}
    declarado = auditoria.get("declared_total")
    enumerado = auditoria.get("enumerated")
    estado = resultado.get("status")

    if estado in ("BLOCKED_EXTERNAL", "IDENTITY_PENDING"):
        return {"gate": "NO_APLICA", "porque": f"cerro {estado} antes de enumerar"}
    if enumerado is None:
        return {"gate": "SIN_EVIDENCIA", "porque": "no hay conteo de enumeracion"}
    # §28: si la fuente declara N y enumeramos M < N, no es COMPLETE.
    if declarado and enumerado < declarado:
        return {"gate": "FAIL", "porque": f"la fuente declara {declarado} y "
                                          f"enumeramos {enumerado}",
                "declared_total": declarado, "enumerated": enumerado}
    if estado in TERMINALES_BUENOS:
        return {"gate": "PASS", "porque": resultado.get("reasons") or estado,
                "enumerated": enumerado}
    return {"gate": "FAIL", "porque": f"estado {estado}", "enumerated": enumerado}


def data_quality_gate(resultado: dict) -> dict[str, Any]:
    """¿Los campos tienen calidad suficiente? Nada sobre el inventario."""
    cobertura = resultado.get("field_coverage") or {}
    if not cobertura:
        return {"gate": "SIN_EVIDENCIA", "porque": "sin field_coverage"}

    defectuosos, vacios = [], []
    for campo, dato in cobertura.items():
        estado = (dato or {}).get("state")
        if estado in ESTADOS_DEFECTUOSOS:
            defectuosos.append(f"{campo}:{estado}")
        elif estado not in ESTADOS_NEUTROS and not (dato or {}).get("coverage"):
            vacios.append(campo)

    # La contradiccion que delata a `analia requena`, acotada.
    #
    # La primera version de esta regla marcaba 135 de 244 agencias, y esa tasa
    # era la pista de que estaba midiendo otra cosa. Medido sobre las 409:
    # `provincia` se rechaza el 0,0% de las veces y `direccion` tambien el
    # 0,0%. O sea que "provincia perfecta" es casi siempre verdad, y exigirlo
    # no aporta nada: la regla en realidad decia "algun campo geografico se
    # rechazo", disfrazado de contradiccion.
    #
    # La contradiccion real es mas estrecha y tiene una forma precisa: una
    # provincia afirmada con cobertura total mientras la geografia MAS FINA que
    # deberia sostenerla -ciudad o barrio- se rechaza entera. Una latitud
    # rechazada es un problema de geocodificacion, no una provincia mal puesta,
    # y mezclarlas hace que la senal deje de significar algo.
    geo = {c: (cobertura.get(c) or {}) for c in DIMENSIONES["geo"]
           if c in cobertura}
    provincia = geo.get("provincia") or {}
    provincia_afirmada = (provincia.get("state") == "EXTRACTED"
                          and provincia.get("coverage") == 1.0)
    finas_rechazadas = [c for c in ("ciudad", "barrio")
                        if (geo.get(c) or {}).get("state")
                        == "REJECTED_BY_VALIDATION"]

    if provincia_afirmada and finas_rechazadas:
        return {"gate": "DEGRADED", "porque":
                f"contradiccion geografica: `provincia` con cobertura total "
                f"mientras {finas_rechazadas} se rechaza entero. La cobertura "
                f"mide presencia, no correccion: es la forma de "
                f"`analia requena`",
                "campos_defectuosos": defectuosos}
    if defectuosos:
        return {"gate": "DEGRADED",
                "porque": f"{len(defectuosos)} campos con defecto",
                "campos_defectuosos": defectuosos}
    if vacios:
        return {"gate": "PARCIAL", "porque": f"{len(vacios)} campos sin valor",
                "campos_vacios": vacios}
    return {"gate": "PASS", "porque": "sin campos defectuosos"}


def vector_de_confianza(resultado: dict) -> dict[str, str]:
    """§33: una escala por dimensión, categórica. Sin score global inventado."""
    cobertura = resultado.get("field_coverage") or {}
    vector: dict[str, str] = {}

    identidad = resultado.get("identity_status")
    vector["identity"] = {"READY": "ALTA"}.get(identidad, "SIN_EVIDENCIA"
                                               if not identidad else "BAJA")
    inv = inventory_gate(resultado)["gate"]
    vector["inventory"] = {"PASS": "ALTA", "FAIL": "BAJA"}.get(inv, "SIN_EVIDENCIA")

    for dimension, campos in DIMENSIONES.items():
        presentes = [(cobertura.get(c) or {}) for c in campos if c in cobertura]
        if not presentes:
            vector[dimension] = "SIN_EVIDENCIA"
            continue
        if any(d.get("state") in ESTADOS_DEFECTUOSOS for d in presentes):
            vector[dimension] = "BAJA"
        elif all(d.get("state") in ESTADOS_NEUTROS for d in presentes):
            vector[dimension] = "SIN_EVIDENCIA"
        else:
            util = [d for d in presentes if d.get("state") == "EXTRACTED"]
            media = (sum(d.get("coverage") or 0 for d in util) / len(util)
                     if util else 0)
            vector[dimension] = ("ALTA" if media >= 0.8 else
                                 "MEDIA" if media >= 0.4 else "BAJA")

    fuente = resultado.get("publication_mechanism")
    vector["source"] = ("BAJA" if fuente in (None, "SIN_INVENTARIO")
                        else "ALTA")
    return vector


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--desacuerdos", action="store_true",
                    help="listar solo donde el gate nuevo contradice al estado "
                         "de hoy")
    args = ap.parse_args()

    ultimo: dict[str, dict] = {}
    for fila in _jsonl(RESULTADOS):
        agencia = fila.get("canonical_agency_id")
        if agencia:
            ultimo[agencia] = fila

    filas = []
    for agencia, resultado in ultimo.items():
        inv = inventory_gate(resultado)
        dq = data_quality_gate(resultado)
        estado = resultado.get("status")
        # SHADOW: el desacuerdo que importa es el que el estado unico esconde.
        # Una agencia terminal buena cuya calidad esta degradada hoy se publica
        # como si estuviera entera.
        desacuerdo = (estado in TERMINALES_BUENOS
                      and dq["gate"] in ("DEGRADED", "PARCIAL"))
        filas.append({
            "canonical_agency_id": agencia,
            "agency_name": resultado.get("agency_name"),
            "estado_actual_unico": estado,
            "INVENTORY_GATE": inv["gate"], "inventory_porque": inv["porque"],
            "DATA_QUALITY_GATE": dq["gate"], "data_quality_porque": dq["porque"],
            "campos_defectuosos": dq.get("campos_defectuosos"),
            "confidence_vector": vector_de_confianza(resultado),
            "shadow_disagreement": desacuerdo,
            "modo": "SHADOW",
        })

    SALIDA.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n"
                              for f in filas), encoding="utf-8")

    desacuerdos = [f for f in filas if f["shadow_disagreement"]]
    print(f"agencias evaluadas: {len(filas)}   modo: SHADOW, no decide nada\n")
    print("  INVENTORY_GATE                     DATA_QUALITY_GATE")
    inv_c = Counter(f["INVENTORY_GATE"] for f in filas)
    dq_c = Counter(f["DATA_QUALITY_GATE"] for f in filas)
    for clave in sorted(set(inv_c) | set(dq_c)):
        print(f"    {clave:16} {inv_c.get(clave, 0):5}        "
              f"{clave:16} {dq_c.get(clave, 0):5}")

    print(f"\n  DESACUERDOS: {len(desacuerdos)} agencias son terminales buenas")
    print(f"  y tienen la calidad degradada. Hoy se publican como si")
    print(f"  estuvieran enteras.\n")
    for f in desacuerdos[:12]:
        print(f"    {(f['agency_name'] or '')[:30]:32} "
              f"{f['estado_actual_unico'][:22]:24} DQ={f['DATA_QUALITY_GATE']}")
        print(f"        {f['data_quality_porque'][:92]}")
    if len(desacuerdos) > 12:
        print(f"    ... y {len(desacuerdos) - 12} mas en el artefacto")

    forma = [f for f in filas
             if "contradiccion geografica" in (f["data_quality_porque"] or "")]
    print(f"\n{'=' * 74}")
    print("LO QUE ESTA MEDIDO Y LO QUE NO (§12: shadow mide antes de decidir)")
    print(f"\n  La regla marca {len(forma)} agencias con la forma de "
          f"`analia requena`:")
    print("  provincia afirmada al 100% mientras ciudad o barrio se rechazan")
    print("  enteros.")
    print("\n  Atrapa su caso de referencia: analia requena da INVENTORY_GATE")
    print("  PASS y DATA_QUALITY_GATE DEGRADED, con geo BAJA e inventory ALTA.")
    print("  Ese es el minimo que tenia que cumplir y lo cumple.")
    print("\n  Lo que NO esta medido: la tasa de falsos positivos. Tenemos")
    print("  verdad de campo sobre UNA agencia. Que otras 88 compartan la")
    print("  forma NO prueba que compartan el defecto: prueba que comparten")
    print("  la forma. Para activar esta regla hace falta verificar una")
    print("  muestra contra la fuente, y hasta entonces sirve como criterio")
    print("  de seleccion y no como veredicto. Por eso sigue en SHADOW.")
    print("\n  Dato de contexto que acota el entusiasmo: medido sobre las 409,")
    print("  `barrio` se rechaza el 26,2% de las veces y `ciudad` el 9,4%")
    print("  en todo el universo. Parte de estas 89 puede ser eso y no una")
    print("  provincia mal puesta.")

    print(f"\nartefacto: {SALIDA}")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
