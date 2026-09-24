# -*- coding: utf-8 -*-
"""Regression Gate entre una línea base y lo que la cola recertificó después.

`scripts/regression_gate.py` compara filas por propiedad y dice qué campo se
perdió, cuál se recuperó y cuál cambió. Lo que faltaba es armar sus dos
entradas con el mismo criterio y mirar sólo lo que de verdad se volvió a
certificar: comparar el universo entero mezcla miles de filas idénticas —las
agencias que la cola todavía no tocó— con las pocas que importan.

    python scripts/comparar_con_linea_base.py \
        --linea-base _regresion/ANTES_DEL_LOTE_2026-09-24.jsonl \
        --desde 2026-09-24T11:39:00

`database_writes: 0`. No decide nada: una pérdida sin explicar es un pedido
de revisión, no un permiso para restaurar ni para borrar.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from scripts.regression_gate import compare  # noqa: E402

CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")


def leer_jsonl(ruta: Path) -> Iterable[dict[str, Any]]:
    with ruta.open(encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if linea:
                try:
                    fila = json.loads(linea)
                except ValueError:
                    continue
                if isinstance(fila, dict):
                    yield fila


def recertificadas_desde(cert: Path, desde: str) -> set[str]:
    """Agencias cuyo último resultado es posterior a `desde`."""
    ultimo: dict[str, str] = {}
    for fila in leer_jsonl(cert / "AGENCY_CERTIFICATION_RESULTS.jsonl"):
        agencia = fila.get("canonical_agency_id")
        if agencia:
            ultimo[agencia] = str(fila.get("checked_at") or "")
    return {a for a, cuando in ultimo.items() if cuando[:19] >= desde[:19]}


def filas_actuales(cert: Path, agencias: set[str]) -> list[dict[str, Any]]:
    """La segunda corrida de cada paquete: la que queda como resultado."""
    filas = []
    for paquete in sorted((cert / "agencies").iterdir()):
        ruta = paquete / "properties_run2.jsonl"
        if not ruta.exists():
            continue
        for fila in leer_jsonl(ruta):
            if fila.get("canonical_agency_id") in agencias:
                filas.append(fila)
    return filas


def resumir(reporte: dict[str, Any]) -> dict[str, Any]:
    por_agencia: dict[str, Counter] = defaultdict(Counter)
    por_campo: dict[str, Counter] = defaultdict(Counter)
    for cambio in reporte["changes"]:
        por_agencia[cambio["agency"]][cambio["kind"]] += 1
        if cambio.get("field"):
            por_campo[cambio["field"]][cambio["kind"]] += 1
    return {"status": reporte["status"], "counts": reporte["counts"],
            "old_rows": reporte["old_rows"], "fresh_rows": reporte["fresh_rows"],
            "matched_rows": reporte["matched_rows"],
            "por_campo": {c: dict(n) for c, n in sorted(por_campo.items())},
            "por_agencia": {a: dict(n) for a, n in sorted(por_agencia.items())}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--linea-base", type=Path, required=True)
    ap.add_argument("--desde", required=True,
                    help="comparar solo agencias recertificadas desde esta hora ISO")
    ap.add_argument("--cert", type=Path, default=CERT)
    ap.add_argument("--salida", type=Path, default=None,
                    help="reporte completo; por defecto junto a la linea base")
    args = ap.parse_args(argv)

    base = args.linea_base if args.linea_base.is_absolute() else args.cert / args.linea_base
    agencias = recertificadas_desde(args.cert, args.desde)
    antes = [f for f in leer_jsonl(base) if f.get("canonical_agency_id") in agencias]
    despues = filas_actuales(args.cert, agencias)
    reporte = compare(antes, despues)
    resumen = {"agencias_recertificadas": len(agencias), **resumir(reporte)}
    salida = args.salida or base.with_name(
        f"GATE_{args.desde[:19].replace(':', '')}.json")
    salida.write_text(json.dumps({**resumen, "changes": reporte["changes"]},
                                 ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in resumen.items() if k != "por_agencia"},
                     ensure_ascii=False, indent=1))
    print(f"reporte completo -> {salida}")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
