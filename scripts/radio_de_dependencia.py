#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Si toco este componente, ¿qué certificaciones se invalidan realmente?

No escribe nada. `database_writes: 0`.

El §5 lo pide así: **no asumir "cambió shared → recertificar todo"**. La huella
se arma por componente y cada estrategia consume un subconjunto. Una agencia
que no consume el componente tocado no tiene por qué perder su certificación.

La diferencia no es teórica. Con 374 agencias certificadas y 36,8 h diarias ya
perdidas en repetición, invalidar de más es el error más caro que se puede
cometer al abrir la ventana.

Uso:
    python scripts/radio_de_dependencia.py
    python scripts/radio_de_dependencia.py --componente shared/geografia
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from scripts.agency_fingerprints import (GENERIC_STRATEGY_METHODS,  # noqa: E402
                                         fingerprint_components)

CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
TERMINAL = {"CERTIFIED_COMPLETE", "CERTIFIED_BEST_AVAILABLE",
            "NO_INVENTORY_CONFIRMED", "BLOCKED_EXTERNAL"}


def pares_certificados() -> tuple[dict[tuple[str, str], int], dict[tuple[str, str], int]]:
    """(conector, estrategia) -> agencias certificadas y propiedades."""
    ultimo: dict[str, dict] = {}
    for linea in (CERT / "AGENCY_CERTIFICATION_RESULTS.jsonl").read_text(
            encoding="utf-8", errors="replace").splitlines():
        if not linea.strip():
            continue
        try:
            r = json.loads(linea)
        except ValueError:
            continue
        if r.get("canonical_agency_id"):
            ultimo[r["canonical_agency_id"]] = r
    agencias: Counter = Counter()
    props: Counter = Counter()
    for r in ultimo.values():
        if r.get("status") not in TERMINAL:
            continue
        c, e = r.get("connector"), r.get("connector_strategy")
        if not c or not e:
            continue
        agencias[(c, e)] += 1
        props[(c, e)] += (r.get("enumeration_audit") or {}).get("enumerated") or 0
    return agencias, props


def componentes_por_par() -> dict[tuple[str, str], set[str]]:
    fuera: dict[tuple[str, str], set[str]] = {}
    pares = [("generico", s) for s in sorted(GENERIC_STRATEGY_METHODS)]
    pares += [(n, n) for n in ("tokko", "wasi", "wordpress", "century21")]
    for par in pares:
        try:
            fuera[par] = set(fingerprint_components(*par))
        except Exception:
            continue
    return fuera


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--componente")
    args = ap.parse_args()

    agencias, props = pares_certificados()
    mapa = componentes_por_par()

    # Quien consume cada componente
    consumidores: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for par, comps in mapa.items():
        for c in comps:
            consumidores[c].append(par)

    if args.componente:
        pares = consumidores.get(args.componente, [])
        ag = sum(agencias.get(p, 0) for p in pares)
        pr = sum(props.get(p, 0) for p in pares)
        print(f"COMPONENT_CHANGED     {args.componente}")
        print(f"AFFECTED_STRATEGIES   {len(pares)}")
        print(f"AFFECTED_AGENCIES     {ag}")
        print(f"AFFECTED_PROPERTIES   {pr:,}")
        print("\nestrategias alcanzadas:")
        for p in sorted(pares):
            if agencias.get(p):
                print(f"   {p[0]}/{p[1]:28} {agencias[p]:4} agencias "
                      f"{props[p]:7,} propiedades")
        print("\ndatabase_writes: 0")
        return 0

    total_ag = sum(agencias.values())
    total_pr = sum(props.values())
    print(f"certificaciones terminales vigentes: {total_ag} agencias, "
          f"{total_pr:,} propiedades\n")
    print(f"{'componente':30} {'estrat':>7} {'agencias':>9} {'props':>9} {'% del total':>12}")
    filas = []
    for comp, pares in consumidores.items():
        ag = sum(agencias.get(p, 0) for p in pares)
        pr = sum(props.get(p, 0) for p in pares)
        filas.append((ag, comp, len(pares), pr))
    for ag, comp, n, pr in sorted(filas, reverse=True):
        pct = ag / total_ag if total_ag else 0
        print(f"{comp[:28]:30} {n:7} {ag:9} {pr:9,} {pct:11.0%}")

    print("\nLECTURA")
    print("  Los `shared/*` alcanzan a todo: tocarlos invalida la pasada entera.")
    print("  Los `connector/*` y `strategy/*` alcanzan solo a su familia, y ahi")
    print("  esta el margen: un arreglo escrito como estrategia nueva no invalida")
    print("  nada de lo ya certificado.")
    print("\n  Antes de cada cambio de la ventana, correr:")
    print("     python scripts/radio_de_dependencia.py --componente <el que se toca>")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
