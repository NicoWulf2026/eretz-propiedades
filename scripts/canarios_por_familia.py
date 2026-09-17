#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Dos o tres fuentes representativas por familia, congeladas. §23, §24, §46.

Sólo lectura sobre artefactos locales. `database_writes: 0`. No corre scraping:
elige los canarios y **congela lo que hoy dan**, que es lo único que después
permite ver si un cambio los rompió.

Para qué
--------
El §24 pide que ningún cambio semántico en una familia se amplíe sin pasar
antes por canarios. Hoy no existe esa lista, así que un arreglo a
`shared/certifier` —que toca todas las estrategias— se valida contra los tests
y contra la agencia que motivó el arreglo, y nada más. Las otras 83 agencias de
la familia `tokko` se enteran cuando la cola vuelve a pasar por ellas, días
después.

Cómo se elige un canario
------------------------
Un canario tiene que estar **verde hoy**. Un caso roto no sirve: si ya falla,
no se puede distinguir el daño nuevo del viejo. Así que se exige:

  - estado terminal bueno (`CERTIFIED_COMPLETE` o `CERTIFIED_BEST_AVAILABLE`);
  - inventario real enumerado, no cero;
  - huella de estrategia registrada, para saber contra qué versión se congeló.

Y se prefieren tamaños distintos dentro de la familia —uno chico, uno mediano,
uno grande— porque los defectos de paginación sólo aparecen con volumen y los
de "página única" sólo aparecen sin él.

Qué se congela
--------------
Por cada canario: cuántas enumeró, con qué estrategia, con qué huella y cuándo.
Eso es la expectativa. Si mañana un cambio hace que ese número baje, el canario
lo dice antes de que la cola recorra la familia entera.

No se congela la **calidad** de los campos, sólo el inventario: la cobertura
por campo se mueve legítimamente cuando la fuente publica más o menos, y
clavarla produciría falsos rojos.

Uso:
    python scripts/canarios_por_familia.py
    python scripts/canarios_por_familia.py --comparar
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
SALIDA = CERT / "ERETZ_CANARIOS_POR_FAMILIA.json"

TERMINALES_BUENOS = {"CERTIFIED_COMPLETE", "CERTIFIED_BEST_AVAILABLE"}

# Cuántos canarios por familia. Tres cuando hay de dónde elegir; el §24 pide
# 2–3 y más que eso es costo de recertificación sin información nueva.
POR_FAMILIA = 3

# Agencias que NO pueden ser canario aunque hoy estén en verde.
#
# El §26 las nombra como casos conocidos de indeterminismo. Un canario que se
# mueve solo es peor que no tener canario: cada vez que se mueva habrá que
# averiguar si fue el cambio o fue la agencia, y a la tercera vez nadie lo mira.
# `ancarola` entraba como canario de `wordpress` por estar CERTIFIED_COMPLETE
# con 71 propiedades; queda afuera por esto.
INDETERMINISTAS = {"ancarola", "carames", "diego malizia"}

# Familias que no pueden tener canario y por qué. Se declaran para que la
# ausencia sea un hecho registrado y no un olvido.
SIN_CANARIO_POSIBLE = {
    "generic/no_inventory": "ninguna de sus 35 agencias esta en verde: es el "
                            "cajon donde caen las que no pudimos enumerar",
    "generic/unknown": "sin agencias terminales buenas",
    "generic/empty_catalog": "sin agencias terminales buenas",
}


def _jsonl(ruta: Path):
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


def elegibles(resultados: dict[str, dict]) -> dict[str, list[dict]]:
    por_familia: dict[str, list[dict]] = defaultdict(list)
    for agencia, fila in resultados.items():
        familia = fila.get("connector_strategy")
        enumerado = (fila.get("enumeration_audit") or {}).get("enumerated")
        if not familia or fila.get("status") not in TERMINALES_BUENOS:
            continue
        if not enumerado:
            continue
        if any(n in agencia.lower() for n in INDETERMINISTAS):
            continue
        por_familia[familia].append({
            "canonical_agency_id": agencia,
            "agency_name": fila.get("agency_name"),
            "official_url": fila.get("official_url"),
            "platform": fila.get("platform"),
            "publication_mechanism": fila.get("publication_mechanism"),
            "status": fila.get("status"),
            "enumerated": enumerado,
            "strategy_fingerprint": fila.get("strategy_fingerprint"),
            "connector_version": fila.get("connector_version"),
            "checked_at": fila.get("checked_at"),
        })
    return por_familia


def elegir(candidatas: list[dict]) -> list[dict]:
    """Uno chico, uno mediano y uno grande.

    Los defectos de paginación no aparecen en una fuente de 4 propiedades, y
    los de "el catálogo cabe en una página" no aparecen en una de 800. Tomar
    las tres más grandes dejaría medio espectro sin vigilar.
    """
    ordenadas = sorted(candidatas, key=lambda f: f["enumerated"])
    if len(ordenadas) <= POR_FAMILIA:
        return ordenadas
    return [ordenadas[0], ordenadas[len(ordenadas) // 2], ordenadas[-1]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--comparar", action="store_true",
                    help="comparar los canarios congelados contra el estado de "
                         "hoy, sin volver a elegirlos")
    args = ap.parse_args()

    resultados = ultimos()
    por_familia = elegibles(resultados)
    todas = {f.get("connector_strategy") for f in resultados.values()
             if f.get("connector_strategy")}

    if args.comparar:
        if not SALIDA.exists():
            print("no hay canarios congelados todavia: correr sin --comparar")
            return 1
        previo = json.loads(SALIDA.read_text(encoding="utf-8"))
        print(f"canarios congelados el {previo['congelado_en'][:10]}\n")
        rotos, movidos, iguales = [], [], 0
        for familia, canarios in previo["familias"].items():
            for c in canarios:
                hoy = resultados.get(c["canonical_agency_id"])
                if not hoy:
                    continue
                ahora = (hoy.get("enumeration_audit") or {}).get("enumerated")
                if hoy.get("status") not in TERMINALES_BUENOS:
                    rotos.append((familia, c, hoy.get("status"), ahora))
                elif ahora != c["enumerated"]:
                    movidos.append((familia, c, hoy.get("status"), ahora))
                else:
                    iguales += 1
        print(f"  iguales: {iguales}   movidos: {len(movidos)}   "
              f"rotos: {len(rotos)}")
        for familia, c, estado, ahora in rotos:
            print(f"    ROTO  {familia:26} {c['agency_name'][:26]:28} "
                  f"{c['enumerated']} -> {ahora}  ({estado})")
        for familia, c, estado, ahora in movidos:
            print(f"    movio {familia:26} {c['agency_name'][:26]:28} "
                  f"{c['enumerated']} -> {ahora}")
        if not rotos and not movidos:
            print("\n  ningun canario se movio")
        print("\n  Un canario que MOVIO no es necesariamente un defecto: la")
        print("  fuente pudo publicar mas o menos. Un canario ROTO -que dejo")
        print("  de ser terminal bueno- si pide explicacion.")
        print("\ndatabase_writes: 0")
        return 0

    familias: dict[str, list[dict]] = {}
    for familia in sorted(por_familia):
        familias[familia] = elegir(por_familia[familia])

    sin_canario = {}
    for familia in sorted(todas):
        if familia in familias:
            continue
        sin_canario[familia] = SIN_CANARIO_POSIBLE.get(
            familia, "no tiene ninguna agencia terminal buena con inventario")

    reporte = {
        "congelado_en": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "familias": familias,
        "sin_canario_posible": sin_canario,
        "criterio": ("terminal bueno, inventario enumerado distinto de cero, y "
                     "tamanos distintos dentro de la familia: uno chico, uno "
                     "mediano y uno grande"),
        "que_se_congela": ("cuantas enumero, con que estrategia y con que "
                           "huella. NO se congela la cobertura por campo: se "
                           "mueve legitimamente y produciria falsos rojos"),
        "database_writes": 0,
    }
    SALIDA.write_text(json.dumps(reporte, ensure_ascii=False, indent=1),
                      encoding="utf-8")

    print(f"familias con canario: {len(familias)}   "
          f"sin canario posible: {len(sin_canario)}\n")
    print(f"  {'FAMILIA':28} {'CANARIO':30} {'ENUM':>6}  ESTADO")
    print(f"  {'-' * 28} {'-' * 30} {'-' * 6}  ------")
    for familia, canarios in familias.items():
        for i, c in enumerate(canarios):
            etiqueta = familia if i == 0 else ""
            print(f"  {etiqueta:28} {(c['agency_name'] or '')[:30]:30} "
                  f"{c['enumerated']:6}  {c['status'][:22]}")
    if sin_canario:
        print(f"\n  Sin canario posible ({len(sin_canario)}):")
        for familia, porque in sin_canario.items():
            print(f"    {familia:28} {porque[:56]}")
        print("\n  Se declaran en el artefacto. Una familia sin canario no es")
        print("  un olvido: es una familia que no tiene ni un caso sano, y eso")
        print("  es informacion.")

    print(f"\nartefacto: {SALIDA}")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
