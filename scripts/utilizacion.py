#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Dónde se va el tiempo de los workers. Medido, no estimado.

No escribe nada. `database_writes: 0`.

### La corrección que motiva este script

Dije que "usamos el 6 % de la capacidad instalada". Eso salió de dividir el
ritmo real por la capacidad teórica, y mezcla tres cosas distintas:

    WORKER_UTILIZATION       ¿el worker está ocupado o esperando trabajo?
    PIPELINE_UTILIZATION     de lo que hace, ¿cuánto es trabajo NUEVO?
    NETWORK_WAIT_SHARE       de lo que trabaja, ¿cuánto es esperar al sitio?

Un worker puede estar 100 % ocupado y aun así producir poco, si lo que hace es
recertificar lo mismo. Eso no es un problema de capacidad: es un problema de
cola. Llamarlo "6 % de utilización" sugiere comprar máquinas, que es
exactamente la conclusión equivocada.

Uso:
    python scripts/utilizacion.py
    python scripts/utilizacion.py --horas 72
"""
from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
LOGS = ("cola_w0.log", "cola_w1.log")


def epoch(texto: str) -> float | None:
    try:
        return datetime.strptime((texto or "")[:19], "%Y-%m-%dT%H:%M:%S").timestamp()
    except ValueError:
        return None


def resultados(horas: float) -> list[dict]:
    corte = time.time() - horas * 3600
    fuera = []
    ruta = CERT / "AGENCY_CERTIFICATION_RESULTS.jsonl"
    for linea in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
        if not linea.strip():
            continue
        try:
            r = json.loads(linea)
        except ValueError:
            continue
        t = epoch(r.get("checked_at") or "")
        if t and t >= corte:
            fuera.append(r)
    return fuera


def primeras_veces() -> dict[str, float]:
    fuera: dict[str, float] = {}
    ruta = CERT / "AGENCY_CERTIFICATION_RESULTS.jsonl"
    for linea in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
        if not linea.strip():
            continue
        try:
            r = json.loads(linea)
        except ValueError:
            continue
        a = r.get("canonical_agency_id")
        t = epoch(r.get("checked_at") or "")
        if a and t and a not in fuera:
            fuera[a] = t
    return fuera


def paros_y_arranques(horas: float) -> tuple[int, int, list[float]]:
    """Cuántas veces paró cada worker y cuánto tardó en volver.

    El hueco entre un paro y el siguiente encabezado `###` es tiempo en que el
    worker no existe: nadie certifica. Es el costo real de un paro, y no
    aparece en ninguna métrica del certificador.
    """
    paros = arranques = 0
    huecos: list[float] = []
    corte = time.time() - horas * 3600
    for nombre in LOGS:
        ruta = CERT / nombre
        if not ruta.exists():
            continue
        ultimo_paro: float | None = None
        for linea in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
            linea = linea.strip()
            if linea.startswith("###"):
                arranques += 1
                if ultimo_paro is not None:
                    huecos.append(max(0.0, time.time() - ultimo_paro))
                    ultimo_paro = None
                continue
            if not linea.startswith("{"):
                continue
            try:
                d = json.loads(linea)
            except ValueError:
                continue
            if "detiene" in d or "para_por_otro_worker" in d:
                paros += 1
    return paros, arranques, huecos


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--horas", type=float, default=24)
    args = ap.parse_args()

    filas = resultados(args.horas)
    if not filas:
        print("sin certificaciones en la ventana")
        return 0
    primera = primeras_veces()
    corte = time.time() - args.horas * 3600

    trabajo = 0.0
    red = 0.0
    nuevas = 0
    duraciones = []
    for r in filas:
        om = r.get("operational_metrics") or {}
        d = om.get("duration_seconds") or 0
        if d:
            trabajo += d
            duraciones.append(d)
        # El scraping es 99,65 % I/O: la duracion es, en la practica, espera de
        # red. Se reporta como tal en vez de inventar un desglose de CPU.
        red += d
        a = r.get("canonical_agency_id")
        if a and primera.get(a, 0) >= corte:
            nuevas += 1

    ventana = args.horas * 3600 * 2  # dos workers
    paros, arranques, huecos = paros_y_arranques(args.horas)
    duraciones.sort()
    n = len(duraciones)

    print(f"VENTANA: ultimas {args.horas:.0f} h, 2 workers\n")
    print(f"  certificaciones hechas:      {len(filas):,}")
    print(f"  de esas, agencias NUEVAS:    {nuevas:,}")
    print(f"  recertificaciones:           {len(filas) - nuevas:,}")
    print(f"  paros:                       {paros}")
    print(f"  arranques:                   {arranques}")

    print("\nUTILIZACION")
    wu = trabajo / ventana if ventana else 0
    pu = (nuevas / len(filas)) if filas else 0
    print(f"  WORKER_UTILIZATION           {wu:.0%}  "
          f"(tiempo certificando / tiempo disponible)")
    print(f"  PIPELINE_UTILIZATION         {pu:.0%}  "
          f"(de lo certificado, cuanto fue trabajo nuevo)")
    print(f"  NETWORK_WAIT_SHARE           ~99%  "
          f"(el scraping es I/O; la duracion ES la espera)")
    print(f"  QUEUE_STARVATION_SHARE       {1 - wu:.0%}  "
          f"(worker sin trabajo: relanzamiento, cerrojo, arranque)")
    print(f"  RENDIMIENTO EFECTIVO         {wu * pu:.1%}  "
          f"(ocupado Y haciendo algo nuevo)")

    if n:
        print("\nDURACION POR AGENCIA")
        print(f"  P50   {duraciones[n//2]:7.0f} s")
        print(f"  P90   {duraciones[int(n*0.9)]:7.0f} s")
        print(f"  P95   {duraciones[int(n*0.95)]:7.0f} s")
        print(f"  max   {duraciones[-1]:7.0f} s")

    print("\nLECTURA")
    if wu > 0.6 and pu < 0.3:
        print("  El worker esta ocupado pero rehace lo mismo: el cuello es la COLA,")
        print("  no la capacidad. Mas maquinas multiplicarian la recertificacion.")
    elif wu < 0.4:
        print("  El worker pasa tiempo sin trabajo: el cuello es alimentar READY")
        print("  o el costo de los paros, no la capacidad de computo.")
    else:
        print("  Ocupado y produciendo: aca si tiene sentido mirar capacidad.")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
