#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Avance de la recertificacion despues de un cambio de huella. Solo lectura.

Cuenta, por estrategia, cuantas agencias ya tienen su resultado VIGENTE con la
huella ACTUAL de su estrategia; mide ritmo, duraciones y duty cycle desde
`--desde` y estima la llegada. Pedido del usuario para la beta del 12/10:
medir cada 6 h TIV recertificadas, generico recertificadas, agencias/hora,
duracion media y mediana, duty cycle y ETA. `database_writes: 0`.

    python scripts/avance_recertificacion.py --desde 2026-10-02T05:53 --workers 2
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import mean, median

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parent)]
try:
    from scripts.rutas_de_datos import dato  # noqa: E402
except ImportError:
    from rutas_de_datos import dato  # noqa: E402
import agency_fingerprints as F  # noqa: E402

CERT = Path(str(dato("ERETZ_AGENCY_CERTIFICATION_20260827")))


def _t(x):
    try:
        return datetime.fromisoformat(str(x)[:19])
    except ValueError:
        return None


def avance(desde: datetime, workers: int, prioridad: list[str], cert: Path = CERT) -> dict:
    ult: dict[str, dict] = {}
    for linea in open(cert / "AGENCY_CERTIFICATION_RESULTS.jsonl", encoding="utf-8", errors="replace"):
        try:
            r = json.loads(linea)
        except ValueError:
            continue
        if r.get("canonical_agency_id") and _t(r.get("checked_at")):
            ult[r["canonical_agency_id"]] = r
    huellas: dict = {}
    def actual(r):
        clave = (r.get("connector"), r.get("connector_strategy"))
        if clave not in huellas:
            try:
                huellas[clave] = F.strategy_fingerprint(*clave)
            except Exception:  # noqa: BLE001 - estrategia desconocida: no cuenta
                huellas[clave] = None
        return huellas[clave]
    por_conector = Counter(); hechas = Counter()
    for r in ult.values():
        c = r.get("connector") or "?"
        por_conector[c] += 1
        if r.get("strategy_fingerprint") and r.get("strategy_fingerprint") == actual(r):
            hechas[c] += 1
    ahora = datetime.now()
    recientes = [r for r in ult.values() if _t(r["checked_at"]) >= desde]
    duraciones = [float((r.get("operational_metrics") or {}).get("duration_seconds") or 0) / 60
                  for r in recientes if (r.get("operational_metrics") or {}).get("duration_seconds")]
    horas = max((ahora - desde).total_seconds() / 3600, 1e-9)
    ritmo = len(recientes) / horas
    pendientes = sum(por_conector.values()) - sum(hechas.values())
    prio = {a: ult.get(a, {}) for a in prioridad}
    prio_hechas = [a for a, r in prio.items()
                   if r and _t(r.get("checked_at")) >= desde and r.get("strategy_fingerprint") == actual(r)]
    return {
        "desde": desde.isoformat(timespec="minutes"), "horas": round(horas, 2), "workers": workers,
        "vigentes_con_huella_actual": dict(hechas), "universo_por_conector": dict(por_conector),
        "pendientes_de_recertificar": pendientes,
        "prioridad_hechas": f"{len(prio_hechas)}/{len(prio)}",
        "prioridad_estado": {a[7:]: (r.get("status"), (r.get("run1") or {}).get("enumeradas"))
                             for a, r in prio.items() if a in prio_hechas},
        "agencias_por_hora": round(ritmo, 2),
        "duracion_min_media": round(mean(duraciones), 1) if duraciones else None,
        "duracion_min_mediana": round(median(duraciones), 1) if duraciones else None,
        "duty_cycle": round(sum(duraciones) / 60 / (workers * horas), 2) if duraciones else None,
        "eta_horas": round(pendientes / ritmo, 1) if ritmo else None,
        "database_writes": 0,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--desde", required=True)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--prioridad", type=Path, default=CERT / "ERETZ_PRIORIDAD_DE_COLA.json")
    args = ap.parse_args(argv)
    try:
        prioridad = json.loads(args.prioridad.read_text(encoding="utf-8")).get("agencias") or []
    except (OSError, ValueError):
        prioridad = []
    print(json.dumps(avance(_t(args.desde), args.workers, prioridad), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
