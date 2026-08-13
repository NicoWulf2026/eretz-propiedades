#!/usr/bin/env python3
"""Finalize bounded Playwright gap diagnostics into manifest-ready evidence."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


FIELDS = (
    "source_id", "source_name", "listing_url", "previous_status", "final_status",
    "http_status", "final_url", "html_size", "frame_count", "property_links_count",
    "property_links_sample", "duration_seconds", "error_type", "evidence", "db_writes",
    "finalization_reason",
)

SUCCESS_STATUSES = {"recovered_parser"}
EXTERNAL_STATUSES = {
    "external_transport_error",
    "external_http_error",
    "external_captcha",
    "external_antibot",
}
PLAYWRIGHT_STATUS_MAP = {
    "playwright_success": "recovered_parser",
    "playwright_partial_due_to_cap": "recovered_parser",
    "playwright_success_low_quality": "recovered_parser",
    "playwright_no_property_links": "external_empty",
    "playwright_zero_properties": "external_empty",
    "playwright_parser_error": "external_empty",
    "playwright_true_antibot": "external_antibot",
    "playwright_captcha": "external_captcha",
    "playwright_login_required": "auth_required",
    "playwright_timeout": "external_timeout",
    "playwright_domain_down": "external_transport_error",
    "playwright_error": "internal_error",
}


def load_records(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            rows.append(json.loads(line))
    return rows


def finalize_status(row: dict[str, Any]) -> tuple[str, str]:
    playwright_status = str(row.get("playwright_final_status") or "")
    if playwright_status:
        mapped = PLAYWRIGHT_STATUS_MAP.get(playwright_status, playwright_status)
        row["final_status"] = mapped
        if mapped == "internal_error":
            return mapped, "playwright_status_requires_internal_review"
        return mapped, "playwright_status_final"
    status = str(row.get("final_status") or "")
    if status in SUCCESS_STATUSES or status in EXTERNAL_STATUSES:
        return status, "diagnostic_status_final"
    if status == "timeout":
        return "external_timeout", "bounded_retry_timeout"
    if status == "still_no_property_links":
        return "external_empty", "rendered_no_property_links_after_http_and_playwright"
    return status or "internal_error", "requires_internal_review"


def choose_result(
    broad: dict[int, dict[str, Any]],
    retry: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source_id, broad_row in sorted(broad.items()):
        chosen = retry.get(source_id, broad_row)
        final_status, reason = finalize_status(chosen)
        output = dict(chosen)
        output["source_id"] = source_id
        output["final_status"] = final_status
        output["finalization_reason"] = reason
        if final_status == "internal_error":
            output["finalization_reason"] = "unresolved_internal_error"
        rows.append(output)
    return rows


def by_source_id(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    output: dict[int, dict[str, Any]] = {}
    for row in rows:
        source_id = int(row["source_id"])
        output[source_id] = row
    return output


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--broad-results", type=Path, required=True)
    parser.add_argument("--retry-results", type=Path, required=True)
    parser.add_argument("--out-csv", type=Path, required=True)
    parser.add_argument("--out-jsonl", type=Path, required=True)
    args = parser.parse_args()

    broad = by_source_id(load_records(args.broad_results))
    retry = by_source_id(load_records(args.retry_results))
    rows = choose_result(broad, retry)
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    write_csv(args.out_csv, rows)
    with args.out_jsonl.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    unresolved = [row for row in rows if row["final_status"] == "internal_error"]
    print(json.dumps({
        "broad": len(broad),
        "retry": len(retry),
        "final": len(rows),
        "unresolved_internal": len(unresolved),
        "db_writes": sum(int(row.get("db_writes") or 0) for row in rows),
    }, ensure_ascii=False))
    return 1 if unresolved else 0


if __name__ == "__main__":
    raise SystemExit(main())
