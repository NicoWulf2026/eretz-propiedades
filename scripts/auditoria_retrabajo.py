#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Por qué el 91 % de las certificaciones recientes fueron repeticiones.

No escribe nada. `database_writes: 0`.

El dato que abre la pregunta: en 24 h se ejecutaron 341 certificaciones sobre
55 agencias, y sólo 32 eran agencias nuevas. Eso no es un problema de CPU —los
workers están ocupados el 86 % del tiempo— sino de **qué** ejecutan.

El §20 fija cuándo una recertificación es legítima:

    cambió una huella relevante
    la corrida anterior fue inválida
    hace falta una segunda observación para idempotencia

Y cuándo no:

    el worker reinició
    la cola se reconstruyó
    la posición se perdió
    un resultado ya válido no fue reconocido

Este script separa unas de otras contando, no estimando. La diferencia decide
si hace falta otra máquina o si hace falta arreglar la cola: **duplicar una
máquina que repite trabajo duplica la repetición.**

Uso:
    python scripts/auditoria_retrabajo.py --horas 24
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
RESULTADOS = CERT / "AGENCY_CERTIFICATION_RESULTS.jsonl"

# Causas del §4. El orden importa: la primera que aplica manda.
FINGERPRINT = "FINGERPRINT_INVALIDATION"
FALLIDA = "FAILED_RUN"
IDEMPOTENCIA = "STOP_RETRY"
REENTRADA = "QUEUE_REENTRY"
REINICIO = "MANUAL_RESTART"
OTRA = "OTHER"

LEGITIMAS = {FINGERPRINT, FALLIDA}
# Las operacionales son las que se pueden eliminar sin tocar semantica.
OPERACIONALES = {REENTRADA, REINICIO, IDEMPOTENCIA}

TERMINAL = {"CERTIFIED_COMPLETE", "CERTIFIED_BEST_AVAILABLE", "BLOCKED_EXTERNAL",
            "NO_INVENTORY_CONFIRMED", "IDENTITY_PENDING"}


def epoch(texto: str) -> float | None:
    try:
        return datetime.strptime((texto or "")[:19], "%Y-%m-%dT%H:%M:%S").timestamp()
    except ValueError:
        return None


def arranques_por_worker() -> list[float]:
    """Cuándo arrancó cada worker. Un resultado justo después de un arranque
    y sobre una agencia ya vista es, casi seguro, reentrada de cola."""
    marcas: list[float] = []
    for nombre in ("cola_w0.log", "cola_w1.log"):
        ruta = CERT / nombre
        if not ruta.exists():
            continue
        # El log no trae timestamp por linea; se usa el mtime como cota
        # superior y el orden relativo de los encabezados. Es aproximado y se
        # dice que lo es.
        marcas.append(ruta.stat().st_mtime)
    return marcas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--horas", type=float, default=24)
    args = ap.parse_args()

    corte = time.time() - args.horas * 3600
    historia: dict[str, list[dict]] = defaultdict(list)
    for linea in RESULTADOS.read_text(encoding="utf-8", errors="replace").splitlines():
        if not linea.strip():
            continue
        try:
            r = json.loads(linea)
        except ValueError:
            continue
        if r.get("canonical_agency_id"):
            historia[r["canonical_agency_id"]].append(r)

    causas: Counter = Counter()
    props_nuevas = props_repetidas = 0
    tiempo_nuevo = tiempo_repetido = 0.0
    nuevas = repeticiones = 0
    ejemplos: dict[str, str] = {}

    for agencia, corridas in historia.items():
        corridas.sort(key=lambda r: epoch(r.get("checked_at") or "") or 0)
        for i, r in enumerate(corridas):
            t = epoch(r.get("checked_at") or "")
            if not t or t < corte:
                continue
            dur = (r.get("operational_metrics") or {}).get("duration_seconds") or 0
            props = (r.get("enumeration_audit") or {}).get("enumerated") or 0
            if i == 0:
                nuevas += 1
                props_nuevas += props
                tiempo_nuevo += dur
                continue

            repeticiones += 1
            props_repetidas += props
            tiempo_repetido += dur
            previa = corridas[i - 1]

            # --- por que se repitio
            if (previa.get("strategy_fingerprint")
                    and r.get("strategy_fingerprint")
                    and previa["strategy_fingerprint"] != r["strategy_fingerprint"]):
                causa = FINGERPRINT
            elif previa.get("status") == "RUNNER_ERROR":
                causa = FALLIDA
            elif previa.get("status") in TERMINAL:
                # Ya estaba cerrada y se volvio a ejecutar: eso es reentrada de
                # cola, y es la que se puede eliminar sin tocar semantica.
                causa = REENTRADA
            elif previa.get("status") == "NEEDS_FIX":
                # NEEDS_FIX vuelve a la cola por diseno: no es terminal. Pero si
                # nada cambio entre una y otra, repetirla no produce informacion.
                igual = (previa.get("status") == r.get("status")
                         and (previa.get("enumeration_audit") or {}).get("enumerated")
                         == (r.get("enumeration_audit") or {}).get("enumerated"))
                causa = REINICIO if igual else IDEMPOTENCIA
            else:
                causa = OTRA
            causas[causa] += 1
            ejemplos.setdefault(causa, agencia.split(":")[-1])

    total = nuevas + repeticiones
    print(f"VENTANA: ultimas {args.horas:.0f} h\n")
    print(f"TOTAL_CERTIFICATION_RUNS      {total:6,}")
    print(f"NEW_CERTIFICATIONS            {nuevas:6,}")
    print(f"RECERTIFICATIONS              {repeticiones:6,}")
    if total:
        print(f"RECERTIFICATION_PERCENT       {repeticiones/total:6.1%}")
    print(f"PROPERTIES_NEWLY_CERTIFIED    {props_nuevas:6,}")
    print(f"PROPERTIES_REPROCESSED        {props_repetidas:6,}")

    print("\nCAUSAS DE LA REPETICION")
    for causa, n in causas.most_common():
        etiqueta = ("legitima" if causa in LEGITIMAS
                    else "OPERACIONAL" if causa in OPERACIONALES else "?")
        print(f"   {causa:26} {n:5}  {etiqueta:12} ej: {ejemplos.get(causa,'')[:24]}")

    evitables = sum(n for c, n in causas.items() if c in OPERACIONALES)
    print(f"\n   evitables sin tocar semantica: {evitables:,} de {repeticiones:,}")

    print("\nRATIOS (§15)")
    total_t = tiempo_nuevo + tiempo_repetido
    if total_t:
        print(f"   NEW_WORK_RATIO              {tiempo_nuevo/total_t:6.1%}  "
              f"(tiempo en trabajo nuevo / tiempo certificando)")
        print(f"   RECERTIFICATION_RATIO       {tiempo_repetido/total_t:6.1%}")
    pared = args.horas * 3600 * 2
    print(f"   WORKER_PRODUCTIVE_UTILIZATION {tiempo_nuevo/pared:5.1%}  "
          f"(tiempo en trabajo nuevo / tiempo de pared de 2 workers)")
    print(f"\n   horas de trabajo nuevo:    {tiempo_nuevo/3600:6.1f}")
    print(f"   horas de trabajo repetido: {tiempo_repetido/3600:6.1f}")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
