#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Que arreglar primero cuando se abra la ventana semantica, y por que.

No escribe nada. Lee los logs de la cola y cuenta AGENCIAS DISTINTAS por firma
de defecto.

La distincion importa mas de lo que parece. Contar lineas del log da un numero
inflado: cada vez que un worker se relanza vuelve a certificar las que quedaron
NEEDS_FIX, y cada pasada escribe otro `continua_pese_a` de la misma agencia por
el mismo motivo. Al 2026-09-13 eso son 225 lineas de `variante_no_soportada`
sobre 20 agencias reales: un factor de once. Quien planifique la ventana con el
numero de lineas va a creer que tiene un incendio donde hay veinte casas.

Uso:
    python scripts/agenda_de_ventana.py
    python scripts/agenda_de_ventana.py --firma variante_no_soportada
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

SALIDA = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
LOGS = ("cola_w0.log", "cola_w1.log")


def leer(directorio: Path) -> tuple[dict[str, set], dict[str, int]]:
    """firma -> agencias distintas, y firma -> lineas escritas."""
    agencias: dict[str, set] = defaultdict(set)
    lineas: dict[str, int] = defaultdict(int)
    for nombre in LOGS:
        ruta = directorio / nombre
        if not ruta.exists():
            continue
        for linea in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
            linea = linea.strip()
            if not linea.startswith("{"):
                continue
            try:
                d = json.loads(linea)
            except ValueError:
                continue
            agencia = d.get("continua_pese_a") or d.get("detiene")
            if not agencia:
                continue
            firma = d.get("componente") or "(sin firma)"
            agencias[firma].add(agencia)
            lineas[firma] += 1
    return agencias, lineas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default=str(SALIDA))
    ap.add_argument("--firma", help="listar las agencias de una firma")
    args = ap.parse_args()

    agencias, lineas = leer(Path(args.output))
    if not agencias:
        print("no hay logs de cola para leer")
        return 1

    if args.firma:
        for a in sorted(agencias.get(args.firma, ())):
            print("  ", a.split(":")[-1])
        print(f"\n{len(agencias.get(args.firma, ()))} agencias")
        return 0

    print(f"{'firma':46} {'agencias':>9} {'lineas':>7} {'inflado':>8}")
    for firma, conjunto in sorted(agencias.items(), key=lambda x: -len(x[1])):
        n = len(conjunto)
        factor = lineas[firma] / n if n else 0
        print(f"{firma[:44]:46} {n:9} {lineas[firma]:7} {factor:7.1f}x")

    total = len(set().union(*agencias.values()))
    print(f"\n{total} agencias distintas con algun defecto atravesado")
    print("database_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
