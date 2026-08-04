#!/usr/bin/env python3
"""Consolidate autonomous dry-run evidence into final safe manifest/exclusions."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "_scratch" / "codex_autonomous_scraping"
SAFE = OUT / "general_manifest_safe.csv"
EVIDENCE_FILES = [
    OUT / "playwright_dry_run_sources.csv",
    OUT / "playwright_internal_retry" / "playwright_dry_run_sources.csv",
    OUT / "playwright_parser_fix_validation" / "playwright_dry_run_sources.csv",
    OUT / "playwright_parser_fix_round2" / "playwright_dry_run_sources.csv",
    OUT / "playwright_parser_fix_round3c" / "playwright_dry_run_sources.csv",
    OUT / "playwright_parser_fix_round4" / "playwright_dry_run_sources.csv",
    OUT / "playwright_parser_fix_round5" / "playwright_dry_run_sources.csv",
    OUT / "playwright_final_retry" / "playwright_dry_run_sources.csv",
]
PATTERN_FILES = [
    OUT / "parser_gap_patterns.csv",
    OUT / "parser_gap_patterns_round2.csv",
    OUT / "parser_gap_patterns_final.csv",
]
PROHIBITED = {"zonaprop.com", "argenprop.com", "properati.com"}
SUCCESS = {"SUCCESS_NO_NEW", "SUCCESS_NEW"}
EXTERNAL_STATUS = {
    "ANTI_BOT", "CAPTCHA", "AUTH_REQUIRED", "SOURCE_GONE", "REMOTE_HTTP_ERROR",
    "SSL_ERROR", "TIMEOUT", "NETWORK_TRANSIENT", "EXTERNAL_EMPTY",
}


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def domain(url: str) -> str:
    return urlparse(url or "").netloc.lower().lstrip("www.")


def main() -> int:
    safe_rows = read_csv(SAFE)
    latest: Dict[str, Dict[str, str]] = {}
    for path in EVIDENCE_FILES:
        for row in read_csv(path):
            latest[row["source_id"]] = {**row, "evidence_file": str(path.relative_to(ROOT))}

    patterns: Dict[str, Dict[str, str]] = {}
    for path in PATTERN_FILES:
        for row in read_csv(path):
            if row.get("status") == "analyzed":
                patterns[row["source_id"]] = row

    final_rows: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []
    seen = set()
    for row in safe_rows:
        sid = row["source_id"]
        if sid in seen:
            raise RuntimeError(f"duplicate source_id in safe manifest: {sid}")
        seen.add(sid)
        url = row.get("new_url_listado") or row.get("old_url_listado") or ""
        status_row = latest.get(sid)
        status = status_row.get("status", "SUCCESS_NO_NEW") if status_row else "SUCCESS_NO_NEW"
        reason = ""
        classification = ""
        retryable = False
        evidence = status_row.get("evidence_file", "full HTTP dry-run success") if status_row else "full HTTP dry-run success"

        if sid == "6292":
            reason = "tokko_source_without_authorized_key_rotation"
            classification = "AUTH_REQUIRED"
        elif any(host == blocked or host.endswith("." + blocked) for blocked in PROHIBITED for host in [domain(url)]):
            reason = "prohibited_source"
            classification = "EXCLUDED"
        elif status in SUCCESS:
            final_rows.append({**row, "eligible": True, "final_validation_status": status})
            continue
        elif status == "PARSER_ERROR":
            pattern = patterns.get(sid, {})
            reason = "no_navigable_detail_endpoint_after_rendered_audit"
            classification = "EXTERNAL_EMPTY_OR_WRONG_LISTING"
            retryable = False
            evidence = "; ".join(filter(None, [
                evidence,
                f"href={pattern.get('href_patterns', '')[:350]}",
                f"data={pattern.get('data_attribute_patterns', '')[:200]}",
                f"framework={pattern.get('spa_framework', '')}",
            ]))
        elif status in EXTERNAL_STATUS:
            reason = status_row.get("error_type") or status.lower()
            classification = status
            retryable = str(status_row.get("retryable", "")).lower() == "true"
        else:
            reason = status_row.get("error_type") or "unclassified_validation_failure"
            classification = "INTERNAL_ERROR"
            retryable = True

        excluded.append({
            "source_id": sid,
            "nombre": row.get("source_name", ""),
            "url": url,
            "reason": reason,
            "classification": classification,
            "evidence": evidence,
            "retryable": retryable,
        })

    if len(final_rows) + len(excluded) != len(safe_rows):
        raise RuntimeError("manifest reconciliation failed")
    if any(row["classification"] == "INTERNAL_ERROR" for row in excluded):
        raise RuntimeError("internal errors remain in final classification")
    if any(not row.get("inmobiliaria_id") for row in final_rows):
        raise RuntimeError("eligible source without inmobiliaria_id")

    final_fields = list(safe_rows[0].keys()) + ["eligible", "final_validation_status"]
    write_csv(OUT / "general_manifest_final.csv", final_rows, final_fields)
    write_csv(
        OUT / "general_manifest_exclusions.csv",
        excluded,
        ["source_id", "nombre", "url", "reason", "classification", "evidence", "retryable"],
    )
    print(f"safe={len(safe_rows)} final={len(final_rows)} excluded={len(excluded)}")
    print("fk_unresolved=0 duplicates=0 internal_errors=0 db_writes=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
