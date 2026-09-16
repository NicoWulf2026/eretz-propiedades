#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""¿Cuánto se habría ahorrado ayer con la política nueva? Contado, no estimado.

No escribe nada. `database_writes: 0`.

El §5 lo pide así: replay sobre las últimas 24 h, comparando antes y después,
**sin inventar ahorro**. Por eso cada corrida repetida del historial se vuelve
a juzgar con la política nueva y se suma su duración real medida, no un
promedio.

La pregunta que contesta es la del §29: *¿cuánto más rápido se vuelve ERETZ si
dejamos de repetir las mismas 53 agencias?*

Uso:
    python scripts/replay_anti_recertificacion.py --horas 24
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

from scripts.run_agency_certification_queue import (diferida_vigente,  # noqa: E402
                                                    diferidos)

CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")


def epoch(t: str) -> float | None:
    try:
        return datetime.strptime((t or "")[:19], "%Y-%m-%dT%H:%M:%S").timestamp()
    except (ValueError, TypeError):
        return None


def habria_saltado(previa: dict, difs: list[dict], momento: float) -> bool:
    """Con la política nueva, ¿esta corrida se habría evitado?

    Llama a la función de producción, no a una copia. La copia fue justamente
    como se escapó el defecto que este replay encontró: `diferidos()` no
    proyectaba `cuando`, así que en producción ninguna diferida habría valido
    mientras la copia del replay leía la fecha del disco y mostraba un ahorro
    que no existía.

    Se juzga con el estado del MOMENTO de la repetición: una diferida escrita
    después no podría haber evitado una corrida anterior, y por eso se filtra
    antes de preguntar.
    """
    if previa.get("status") != "NEEDS_FIX":
        return False
    if not previa.get("strategy_fingerprint"):
        return False
    ya_existian = [d for d in difs
                   if (epoch(d.get("cuando") or "") or 0) <= momento]
    return diferida_vigente(previa, ya_existian, ahora=momento)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--horas", type=float, default=24)
    args = ap.parse_args()

    corte = time.time() - args.horas * 3600
    difs = diferidos(CERT)
    historia: dict[str, list[dict]] = defaultdict(list)
    for linea in (CERT / "AGENCY_CERTIFICATION_RESULTS.jsonl").read_text(
            encoding="utf-8", errors="replace").splitlines():
        if not linea.strip():
            continue
        try:
            r = json.loads(linea)
        except ValueError:
            continue
        if r.get("canonical_agency_id"):
            historia[r["canonical_agency_id"]].append(r)

    runs_antes = runs_despues = nuevas = 0
    seg_antes = seg_despues = 0.0
    evitadas: Counter = Counter()
    agencias_evitadas: set[str] = set()

    for agencia, corridas in historia.items():
        corridas.sort(key=lambda r: epoch(r.get("checked_at") or "") or 0)
        for i, r in enumerate(corridas):
            t = epoch(r.get("checked_at") or "")
            if not t or t < corte:
                continue
            dur = (r.get("operational_metrics") or {}).get("duration_seconds") or 0
            runs_antes += 1
            seg_antes += dur
            if i == 0:
                nuevas += 1
                runs_despues += 1
                seg_despues += dur
                continue
            if habria_saltado(corridas[i - 1], difs.get(agencia, []), t):
                evitadas[(corridas[i - 1].get("status") or "")] += 1
                agencias_evitadas.add(agencia)
                continue        # la politica nueva no la ejecuta
            runs_despues += 1
            seg_despues += dur

    repetidas_antes = runs_antes - nuevas
    repetidas_despues = runs_despues - nuevas
    ahorro = seg_antes - seg_despues

    print(f"REPLAY — ultimas {args.horas:.0f} h, historial real\n")
    print(f"{'':28} {'ANTES':>10} {'DESPUES':>10}")
    print(f"{'TOTAL_RUNS':28} {runs_antes:10,} {runs_despues:10,}")
    print(f"{'NEW_RUNS':28} {nuevas:10,} {nuevas:10,}")
    print(f"{'RECERTIFICATIONS':28} {repetidas_antes:10,} {repetidas_despues:10,}")
    print(f"{'WORKER_HOURS':28} {seg_antes/3600:10.1f} {seg_despues/3600:10.1f}")
    if runs_antes and runs_despues:
        print(f"{'NEW_WORK_RATIO':28} {nuevas/runs_antes:10.1%} "
              f"{nuevas/runs_despues:10.1%}")

    print(f"\n   recertificaciones evitadas: {sum(evitadas.values()):,}")
    print(f"   agencias que dejan de repetirse: {len(agencias_evitadas)}")
    print(f"   horas de worker liberadas: {ahorro/3600:.1f}")
    if seg_antes:
        print(f"   o sea el {ahorro/seg_antes:.0%} del tiempo de certificacion")

    print("\n   NOTA: se juzga con el estado del MOMENTO de cada repeticion.")
    print("   Una diferida escrita despues no podria haber evitado una corrida")
    print("   anterior, y por eso no se cuenta.")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
