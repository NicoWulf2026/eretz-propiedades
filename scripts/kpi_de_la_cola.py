#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""KPI de la cola por HORA DE RELOJ, no por hora de worker. Solo lectura.

`database_writes: 0`. Pedido del usuario el 2026-10-01: el KPI principal es
RESOLUCIONES POR HORA DE RELOJ. Un throughput "por hora activa" alto no dice
nada si la cola paso horas detenida: las horas paradas cuentan en el reloj.

Que mide en una ventana [desde, hasta):
  - resoluciones (filas del ledger) por hora de reloj y por hora activa
    (hora de reloj con al menos un resultado);
  - cierres terminales por hora (CERTIFIED_*, NO_INVENTORY_CONFIRMED,
    BLOCKED_EXTERNAL) y NEEDS_FIX;
  - horas de reloj SIN ningun resultado (cola sin trabajo util);
  - paros por dia y su demora hasta la liberacion: el primer evento posterior
    que la libera -una diferida de esa agencia y componente, humana o
    automatica, o un resultado terminal-; los que siguen abiertos se cuentan
    aparte, sin inventarles una duracion;
  - diferidas humanas y automaticas por hora;
  - propiedades de las agencias que cerraron CERTIFIED_* en la ventana;
  - pedidos HTTP por propiedad y la parte que es la segunda corrida. La
    segunda corrida NO es una descarga duplicada a eliminar: es la prueba de
    idempotencia de la certificacion, y se informa para que nadie la "optimice".

Uso:
    python scripts/kpi_de_la_cola.py                       # ultimas 24 h
    python scripts/kpi_de_la_cola.py --desde 2026-10-01T14:00:02
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:  # raiz del estado operativo configurable (ERETZ_DATA_ROOT)
    from scripts.rutas_de_datos import dato  # noqa: E402
except ImportError:  # corrido como `python scripts/x.py`
    from rutas_de_datos import dato  # noqa: E402

CERT = Path(str(dato("ERETZ_AGENCY_CERTIFICATION_20260827")))
TERMINALES = {"CERTIFIED_COMPLETE", "CERTIFIED_BEST_AVAILABLE", "NO_INVENTORY_CONFIRMED",
              "BLOCKED_EXTERNAL"}
CERTIFICADAS = {"CERTIFIED_COMPLETE", "CERTIFIED_BEST_AVAILABLE"}


def _jsonl(ruta: Path):
    if not ruta.exists():
        return
    for linea in ruta.open(encoding="utf-8", errors="replace"):
        linea = linea.strip()
        if linea:
            try:
                yield json.loads(linea)
            except ValueError:
                continue


def _t(texto: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(texto)[:19])
    except ValueError:
        return None


def kpi(desde: datetime, hasta: datetime, cert: Path = CERT) -> dict[str, Any]:
    horas = max((hasta - desde).total_seconds() / 3600, 1e-9)
    todos = [r for r in _jsonl(cert / "AGENCY_CERTIFICATION_RESULTS.jsonl") if _t(r.get("checked_at"))]
    res = [r for r in todos if desde <= _t(r["checked_at"]) < hasta]
    activas = {_t(r["checked_at"]).strftime("%Y-%m-%dT%H") for r in res}
    terminales = [r for r in res if r.get("status") in TERMINALES]
    diferidas = [d for d in _jsonl(cert / "AGENCY_DEFECTS_DIFERIDOS.jsonl") if _t(d.get("cuando"))]
    paros = [p for p in _jsonl(cert / "AGENCY_DEFECT_QUEUE.jsonl")
             if p.get("decision") == "STOP" and _t(p.get("cuando")) and desde <= _t(p["cuando"]) < hasta]
    demoras, abiertos = [], 0
    for p in paros:
        t0, ag, comp = _t(p["cuando"]), p.get("canonical_agency_id"), p.get("componente_sospechoso")
        libera = [_t(d["cuando"]) for d in diferidas
                  if d.get("canonical_agency_id") == ag and d.get("componente") == comp and _t(d["cuando"]) >= t0]
        libera += [_t(r["checked_at"]) for r in todos
                   if r.get("canonical_agency_id") == ag and r.get("status") in TERMINALES
                   and _t(r["checked_at"]) >= t0]
        if libera:
            demoras.append((min(libera) - t0).total_seconds() / 60)
        else:
            abiertos += 1
    en_ventana = [d for d in diferidas if desde <= _t(d["cuando"]) < hasta]
    auto = sum(1 for d in en_ventana if d.get("diferida_por_precedente"))
    metricas = [r.get("operational_metrics") or {} for r in res]
    pedidos = sum(int(m.get("requests") or 0) for m in metricas)
    props_pedidas = sum(int(m.get("properties") or 0) for m in metricas)
    segunda = sum(int((r.get("network") or {}).get("requests_run2") or 0) for r in res)
    return {
        "desde": desde.isoformat(timespec="seconds"), "hasta": hasta.isoformat(timespec="seconds"),
        "horas_de_reloj": round(horas, 2), "horas_activas": len(activas),
        "horas_sin_resultados": max(0, round(horas) - len(activas)),
        "resoluciones": len(res),
        "resoluciones_por_hora_de_reloj": round(len(res) / horas, 2),
        "resoluciones_por_hora_activa": round(len(res) / max(len(activas), 1), 2),
        "terminales_por_hora_de_reloj": round(len(terminales) / horas, 2),
        "needs_fix": sum(1 for r in res if r.get("status") == "NEEDS_FIX"),
        "paros": len(paros), "paros_por_dia": round(len(paros) / horas * 24, 1),
        "paro_a_liberacion_min_mediana": round(median(demoras), 1) if demoras else None,
        "paro_a_liberacion_min_max": round(max(demoras), 1) if demoras else None,
        "paros_sin_liberar": abiertos,
        "diferidas_humanas_por_hora": round((len(en_ventana) - auto) / horas, 2),
        "diferidas_automaticas_por_hora": round(auto / horas, 2),
        "propiedades_certificadas": sum(int((r.get("operational_metrics") or {}).get("properties") or 0)
                                        for r in res if r.get("status") in CERTIFICADAS),
        "pedidos_por_propiedad": round(pedidos / max(props_pedidas, 1), 2),
        "parte_segunda_corrida": round(segunda / max(pedidos, 1), 3),
        "database_writes": 0,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--desde")
    ap.add_argument("--hasta")
    args = ap.parse_args(argv)
    hasta = _t(args.hasta) if args.hasta else datetime.now()
    desde = _t(args.desde) if args.desde else hasta - timedelta(hours=24)
    for k, v in kpi(desde, hasta).items():
        print(f"{k:34} {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
