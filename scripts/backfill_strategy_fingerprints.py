"""Refresca métricas sólo de evidencia con huella actual ya registrada.

No visita webs ni bases. Idempotencia no prueba qué código ejecutó una corrida:
no agrega/reemplaza huellas ni convierte evidencia antigua en certificación actual.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.agency_certifier import (append_jsonl, operational_metrics,
                                      read_jsonl, write_json)
from scripts.agency_fingerprints import (
    current_code_evidence,
    strategy_for,
)

SAFE_TERMINAL = {
    "CERTIFIED_COMPLETE", "CERTIFIED_BEST_AVAILABLE",
    "NO_INVENTORY_CONFIRMED", "BLOCKED_EXTERNAL",
}


def safe_to_backfill(result: dict[str, Any]) -> bool:
    if not isinstance(result, dict) or not isinstance(result.get('status'), str):
        return False
    if result['status'] not in SAFE_TERMINAL or not current_code_evidence(result):
        return False
    if result.get("status") == "BLOCKED_EXTERNAL":
        return True
    comparison = result.get("comparison") or {}
    run1, run2 = result.get("run1") or {}, result.get("run2") or {}
    if not all(isinstance(item, dict) for item in (comparison, run1, run2)):
        return False
    return (comparison.get("idempotent") is True
            and type(run1.get('detalles_fallidos')) is int and run1['detalles_fallidos'] == 0
            and type(run2.get('detalles_fallidos')) is int and run2['detalles_fallidos'] == 0
            and not run1.get("presupuesto_agotado")
            and not run2.get("presupuesto_agotado"))


def latest_results(path: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        latest[row["canonical_agency_id"]] = row
    return latest


def migrate_result(result: dict[str, Any]) -> dict[str, Any]:
    if not safe_to_backfill(result):
        raise ValueError('Historical or unproven code evidence requires recertification')
    connector = str(result["connector"])
    strategy = result.get('connector_strategy') or strategy_for(connector, result.get("publication_mechanism"))
    run1, run2 = result.get("run1") or {}, result.get("run2") or {}
    network = result.get("network") or {}
    first = type("Download", (), {
        "pedidos": int(network.get("requests_run1") or 0)})()
    second = type("Download", (), {
        "pedidos": int(network.get("requests_run2") or 0)})()
    metrics = operational_metrics(
        str(result["canonical_agency_id"]), connector, strategy,
        run1, run2, first, second, str(result["status"]))
    return {
        **result,
        "connector_strategy": strategy,
        "operational_metrics_refreshed_without_recertification": True,
        "operational_metrics": metrics,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
    parser.add_argument("--refresh-safe", action="store_true")
    args = parser.parse_args()
    output = Path(args.output)
    results_path = output / "AGENCY_CERTIFICATION_RESULTS.jsonl"
    latest = latest_results(results_path)
    migrated = 0
    skipped = 0
    for canonical_id, result in sorted(latest.items()):
        if ((result.get("strategy_fingerprint") and not args.refresh_safe)
                or not safe_to_backfill(result)):
            skipped += 1
            continue
        updated = migrate_result(result)
        packet = output / "agencies" / hashlib.sha256(
            canonical_id.encode()).hexdigest()[:16] / "certification.json"
        write_json(packet, updated)
        append_jsonl(results_path, updated)
        metrics_path = packet.parent / "metrics.json"
        write_json(metrics_path, updated["operational_metrics"])
        append_jsonl(output / "AGENCY_CERTIFICATION_METRICS.jsonl",
                     updated["operational_metrics"])
        migrated += 1
    print(json.dumps({"migrated": migrated, "skipped": skipped,
                      "network_requests": 0, "database_writes": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
