#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Cuánto invalida un cambio, ANTES de hacerlo. §47, §48, §51.

Sólo lectura sobre artefactos locales. `database_writes: 0`. No toca código, no
cambia huellas, no recertifica: contesta una pregunta antes de que sea tarde.

El §48 lo pide en una línea: *"No descubrir después del commit que invalidamos
medio universo"*. Hoy ese cálculo se hace de cabeza, y de cabeza se hace mal,
porque la relación entre un archivo y las certificaciones que caen no es obvia:
`connectors/texto.py` no menciona ninguna agencia y está en **todas** las
huellas.

Cómo se calcula el radio
------------------------
No se estima: se deriva de `fingerprint_components()`, que es la misma función
que la cola usa para decidir si un resultado sigue vigente.

    shared/*        entra en TODA huella      → cae el universo certificado
    connector/<x>   sólo en ese conector      → caen sus agencias
    strategy/<x>    sólo genérico + esa       → caen las de esa estrategia

Y las horas salen de `operational_metrics.duration_seconds` de las corridas ya
hechas, no de un promedio inventado: si una familia tarda tres horas por
agencia, recertificarla cuesta lo que costó.

Para qué sirve el número
------------------------
El §47 da el criterio y vale citarlo entero, porque el número solo no decide:

    arreglar 3 propiedades → invalida 600 agencias → normalmente deferir
    evitar un COMPLETE falso → aunque invalide mucho → priorizar

O sea que un radio grande no prohíbe el cambio: obliga a justificarlo. Lo que
este script hace es que la justificación se escriba **antes**.

Uso:
    python scripts/presupuesto_de_riesgo.py --componente shared/certifier
    python scripts/presupuesto_de_riesgo.py --todos
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from scripts.agency_fingerprints import (  # noqa: E402
    fingerprint_components, strategy_for,
)

CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
RESULTADOS = CERT / "AGENCY_CERTIFICATION_RESULTS.jsonl"
SALIDA = CERT / "ERETZ_PRESUPUESTO_DE_RIESGO.json"

# Sólo las que habría que rehacer. Un `IDENTITY_PENDING` no depende del
# conector, así que un cambio de extracción no lo invalida.
ALCANZABLES = frozenset({
    "CERTIFIED_COMPLETE", "CERTIFIED_BEST_AVAILABLE",
    "NO_INVENTORY_CONFIRMED", "NEEDS_FIX",
})


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


def universo_certificado() -> list[dict[str, Any]]:
    ultimo: dict[str, dict] = {}
    for fila in _jsonl(RESULTADOS):
        agencia = fila.get("canonical_agency_id")
        if agencia:
            ultimo[agencia] = fila
    return [f for f in ultimo.values() if f.get("status") in ALCANZABLES]


# `fingerprint_components()` parsea archivos y los recorre con AST. Llamarla
# una vez por agencia y por componente son ~400 x 20 parseos y la herramienta
# tarda minutos. El conjunto de componentes depende SOLO del par
# (conector, estrategia), del que hay una docena: se calcula una vez cada uno.
@lru_cache(maxsize=None)
def _componentes(conector: str, estrategia: str) -> frozenset[str]:
    try:
        return frozenset(fingerprint_components(conector, estrategia))
    except Exception:  # noqa: BLE001 - una estrategia desconocida no tumba nada
        return frozenset()


def componentes_de(fila: dict[str, Any]) -> frozenset[str]:
    """Los componentes que entraron en la huella de ESTA certificación."""
    conector = fila.get("connector") or "generico"
    estrategia = (fila.get("connector_strategy")
                  or strategy_for(conector, fila.get("publication_mechanism")))
    return _componentes(conector, estrategia)


def presupuesto(componente: str,
                universo: list[dict[str, Any]]) -> dict[str, Any]:
    alcanzadas = [f for f in universo if componente in componentes_de(f)]
    if not alcanzadas:
        return {"componente": componente, "agencias_invalidadas": 0,
                "veredicto": "NINGUNA CERTIFICACION DEPENDE DE ESTE COMPONENTE"}

    propiedades = sum((f.get("enumeration_audit") or {}).get("enumerated") or 0
                      for f in alcanzadas)
    segundos = [(f.get("operational_metrics") or {}).get("duration_seconds")
                for f in alcanzadas]
    segundos = [s for s in segundos if isinstance(s, (int, float)) and s > 0]
    # Mediana y no promedio: una sola agencia de tres horas corre el promedio y
    # hace parecer inviable un cambio que no lo es.
    mediana = statistics.median(segundos) if segundos else None
    horas_1w = (mediana * len(alcanzadas) / 3600) if mediana else None

    estrategias = Counter(f.get("connector_strategy") or "(sin estrategia)"
                          for f in alcanzadas)
    estados = Counter(f.get("status") for f in alcanzadas)
    return {
        "componente": componente,
        "agencias_invalidadas": len(alcanzadas),
        "de_un_universo_certificado_de": len(universo),
        "porcentaje": round(100 * len(alcanzadas) / len(universo), 1),
        "propiedades_afectadas": propiedades,
        "estrategias_afectadas": dict(estrategias.most_common()),
        "estados_afectados": dict(estados.most_common()),
        "mediana_segundos_por_agencia": round(mediana, 1) if mediana else None,
        "horas_de_recertificacion_1_worker": (round(horas_1w, 1)
                                              if horas_1w else None),
        "horas_de_recertificacion_2_workers": (round(horas_1w / 2, 1)
                                               if horas_1w else None),
        "nota": ("la mediana y no el promedio: una agencia de tres horas corre "
                 "el promedio y hace parecer inviable un cambio que no lo es"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--componente", help="por ejemplo shared/certifier")
    ap.add_argument("--todos", action="store_true")
    args = ap.parse_args()

    universo = universo_certificado()
    if not universo:
        print("no hay certificaciones alcanzables")
        return 1

    if args.componente:
        fuera = [presupuesto(args.componente, universo)]
    elif args.todos:
        todos: set[str] = set()
        for fila in universo:
            todos |= componentes_de(fila)
        fuera = [presupuesto(c, universo) for c in sorted(todos)]
        fuera.sort(key=lambda f: f.get("agencias_invalidadas", 0), reverse=True)
    else:
        ap.error("elegir --componente o --todos")
        return 2

    reporte = {"generado_en": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "universo_certificado": len(universo),
               "presupuestos": fuera, "database_writes": 0}
    SALIDA.write_text(json.dumps(reporte, ensure_ascii=False, indent=1),
                      encoding="utf-8")

    print(f"universo certificado alcanzable: {len(universo)} agencias\n")
    print(f"  {'COMPONENTE':32} {'AGENCIAS':>8} {'%':>6} {'PROPS':>8} "
          f"{'HORAS 2w':>9}")
    print(f"  {'-' * 32} {'-' * 8} {'-' * 6} {'-' * 8} {'-' * 9}")
    for f in fuera:
        if not f.get("agencias_invalidadas"):
            print(f"  {f['componente'][:32]:32} {'0':>8}")
            continue
        print(f"  {f['componente'][:32]:32} {f['agencias_invalidadas']:8} "
              f"{f['porcentaje']:5.1f}% {f['propiedades_afectadas']:8} "
              f"{str(f['horas_de_recertificacion_2_workers']):>9}")

    print("\n  El §47 es explicito en que el numero NO decide solo:")
    print("     arreglar 3 propiedades -> invalida 600 agencias -> deferir")
    print("     evitar un COMPLETE falso -> aunque invalide mucho -> priorizar")
    print("  Un radio grande no prohibe el cambio: obliga a justificarlo, y")
    print("  eso se escribe ANTES y no despues del commit.")
    print(f"\nartefacto: {SALIDA}")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
