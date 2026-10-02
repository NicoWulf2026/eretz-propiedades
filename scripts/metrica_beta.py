#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Metrica de la beta del 12/10, separada del backlog nacional. Solo lectura.

Pedido del usuario (02-10): la ETA de beta no se mide sobre las ~1.750
agencias pendientes de la cola, sino sobre lo que puede impedir una beta
confiable. Esto separa:

- BETA_CRITICAL_PENDING: agencias criticas (falsos COMPLETE TIV) que todavia
  no tienen un resultado con la huella VIGENTE de su estrategia. Cualquier
  cierre cuenta -NEEDS_FIX honesto incluido-: lo critico es no servir un
  COMPLETE falso, no que la agencia quede verde.
- NATIONAL_BACKLOG_PENDING: el resto de la cola (nunca certificadas, long
  tail, recertificaciones sin dato falso conocido).
- REGRESSION_GATE_UNEXPLAINED: filas del gate sin clase o REAL_BETA_BLOCKER
  en la clasificacion de la candidata.

    python scripts/metrica_beta.py --desde 2026-10-02T05:53
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import median

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parent)]
try:
    from scripts.rutas_de_datos import dato  # noqa: E402
except ImportError:
    from rutas_de_datos import dato  # noqa: E402
import agency_fingerprints as F  # noqa: E402
from avance_recertificacion import avance, _t  # noqa: E402

CERT = Path(str(dato("ERETZ_AGENCY_CERTIFICATION_20260827")))
CLASES_QUE_NO_BLOQUEAN = {"KNOWN_DEBT", "CORRECTION_OF_OLD_BAD_DATA",
                          "REVIEWED_FALSE_LOSS", "FIXED_IN_NEXT_CANDIDATE"}


def ultimos(cert: Path) -> dict[str, dict]:
    ult: dict[str, dict] = {}
    for linea in open(cert / "AGENCY_CERTIFICATION_RESULTS.jsonl", encoding="utf-8", errors="replace"):
        try:
            r = json.loads(linea)
        except ValueError:
            continue
        if r.get("canonical_agency_id"):
            ult[r["canonical_agency_id"]] = r
    return ult


def vigente(r: dict) -> bool:
    try:
        actual = F.strategy_fingerprint(r.get("connector"), r.get("connector_strategy"))
    except Exception:  # noqa: BLE001 - estrategia desconocida: no vigente
        return False
    return bool(r.get("strategy_fingerprint")) and r.get("strategy_fingerprint") == actual


def criticas(ult: dict[str, dict], agencias: list[str], desde: datetime,
             declarado: dict[str, int] | None = None) -> dict:
    cerradas = {a: ult[a] for a in agencias if a in ult and vigente(ult[a])}
    abiertas = [a for a in agencias if a not in cerradas]
    # Segundos por ficha de las criticas ya cerradas desde el cambio: estima lo que falta.
    spp = [float((r.get("operational_metrics") or {}).get("duration_seconds") or 0)
           / max(int((r.get("run1") or {}).get("enumeradas") or 0), 1)
           for r in cerradas.values() if _t(r.get("checked_at")) and _t(r["checked_at"]) >= desde]
    # Lo enumerado por un COMPLETE falso es justamente lo que subestima: se
    # toma el inventario declarado por el buscador del sitio cuando se conoce.
    fichas = {a: max(int((ult.get(a, {}).get("run1") or {}).get("total_declarado") or 0),
                     int((ult.get(a, {}).get("run1") or {}).get("enumeradas") or 0),
                     int((declarado or {}).get(a[7:] if a.startswith("roomix:") else a) or 0))
              for a in abiertas}
    seg = median(spp) if spp else None
    return {
        "cerradas": len(cerradas), "abiertas": len(abiertas),
        "estado_de_cerradas": dict(Counter(r.get("status") for r in cerradas.values())),
        "fichas_abiertas": sum(fichas.values()),
        "segundos_por_ficha_mediana": round(seg, 1) if seg else None,
        "horas_de_worker_estimadas": round(sum(fichas.values()) * seg / 3600, 1) if seg else None,
        "horas_de_la_mas_larga": round(max(fichas.values(), default=0) * seg / 3600, 1) if seg else None,
        "abiertas_detalle": {a[7:]: fichas[a] for a in abiertas},
    }


def gate(clasificacion: Path) -> dict:
    clases: Counter = Counter()
    try:
        for linea in open(clasificacion, encoding="utf-8"):
            clases[json.loads(linea).get("clase_beta") or "SIN_CLASIFICAR"] += 1
    except OSError:
        return {"archivo": None}
    sin_explicar = sum(n for c, n in clases.items() if c not in CLASES_QUE_NO_BLOQUEAN)
    return {"archivo": clasificacion.name, "clases": dict(clases), "sin_explicar": sin_explicar}


def pendientes_de_la_cola(cert: Path, workers: int) -> int | None:
    total = None
    # Solo los checkpoints del regimen vigente: el de un worker de otro regimen
    # (w2 de la prueba con 3) quedo congelado y duplica la cuenta.
    for p in (cert / f"AGENCY_CERTIFICATION_PROGRESS.w{w}.json" for w in range(workers)):
        try:
            total = (total or 0) + int(json.loads(p.read_text(encoding="utf-8")).get("pending_count") or 0)
        except (OSError, ValueError):
            continue
    return total


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--desde", required=True)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--criticas", type=Path, default=CERT / "ERETZ_PRIORIDAD_DE_COLA.json")
    ap.add_argument("--declarado", type=Path, default=None,
                    help="JSON con el inventario declarado: {agencia: n} o [[agencia, ..., n], ...]")
    ap.add_argument("--clasificacion", type=Path,
                    default=CERT / "_regresion" / "CLASIFICACION_BETA_v4m3.jsonl")
    args = ap.parse_args(argv)
    desde = _t(args.desde)
    try:
        agencias = json.loads(args.criticas.read_text(encoding="utf-8")).get("agencias") or []
    except (OSError, ValueError):
        agencias = []
    declarado: dict[str, int] = {}
    if args.declarado:
        crudo = json.loads(args.declarado.read_text(encoding="utf-8"))
        filas = crudo.items() if isinstance(crudo, dict) else ((f[0], f[-1]) for f in crudo)
        declarado = {str(a): int(n) for a, n in filas if isinstance(n, int)}
    ult = ultimos(CERT)
    crit = criticas(ult, agencias, desde, declarado)
    cola = pendientes_de_la_cola(CERT, args.workers)
    g = gate(args.clasificacion)
    ritmo = avance(desde, args.workers, agencias)
    # Ni mejor que repartir perfecto ni mejor que la agencia mas larga sola.
    eta = (round(max(crit["horas_de_worker_estimadas"] / max(min(args.workers, crit["abiertas"]), 1),
                     crit["horas_de_la_mas_larga"]), 1)
           if crit["horas_de_worker_estimadas"] is not None else None)
    print(json.dumps({
        "medido": datetime.now().isoformat(timespec="minutes"),
        "TIV_FALSE_COMPLETE_OPEN": crit["abiertas"],
        "TIV_CRITICAL_RECERTIFIED": crit["cerradas"],
        "tiv_estado_de_cerradas": crit["estado_de_cerradas"],
        "BETA_CRITICAL_PENDING_agencias": crit["abiertas"],
        "NATIONAL_BACKLOG_PENDING": (cola - crit["abiertas"]) if cola is not None else None,
        "REGRESSION_GATE_UNEXPLAINED": g.get("sin_explicar"),
        "KNOWN_DEBT_filas_gate": (g.get("clases") or {}).get("KNOWN_DEBT"),
        "gate": g,
        "WORKERS": args.workers,
        "DUTY_CYCLE": ritmo.get("duty_cycle"),
        "BETA_ETA_horas_criticas": eta,
        "criticas": crit,
        "database_writes": 0,
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
