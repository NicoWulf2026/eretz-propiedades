#!/usr/bin/env python3
"""Run the existing Playwright diagnostic against an explicit HTTP checkpoint."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import run_full_coverage_playwright_pass as runner


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "_scratch/codex_full_7004_coverage/current_http_diagnostic/source_results.jsonl"
DEFAULT_OUT = ROOT / "_scratch/codex_full_7004_coverage/current_playwright_diagnostic"


def _filter_checkpoint(input_path: Path, ids_path: Path, output_path: Path) -> tuple[int, str]:
    with ids_path.open(encoding="utf-8-sig", newline="") as handle:
        ids = [int(row["source_id"]) for row in csv.DictReader(handle)]
    if len(ids) != len(set(ids)):
        raise RuntimeError("Duplicate source_id in Playwright ID manifest")
    selected = set(ids)
    records = []
    statuses = set()
    with input_path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if int(record.get("source_id") or 0) not in selected:
                continue
            records.append(record)
            statuses.add(str(record.get("final_status") or "unknown"))
    found = {int(record["source_id"]) for record in records}
    missing = selected - found
    if missing:
        raise RuntimeError(f"Playwright input is missing {len(missing)} source IDs")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return len(records), ",".join(sorted(statuses))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--source-ids-file", type=Path)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--only", default="requires_playwright,forbidden,antibot,no_property_links")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--listing-timeout", type=int, default=25)
    parser.add_argument("--property-timeout", type=int, default=12)
    parser.add_argument("--max-items", type=int, default=5)
    parser.add_argument("--max-pages", type=int, default=2)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if not args.input.exists():
        raise RuntimeError(f"HTTP checkpoint not found: {args.input}")
    if not 1 <= args.workers <= 2:
        raise RuntimeError("MAX_ACTIVE_BROWSERS=2")

    selected_input = args.input
    only = args.only
    if args.source_ids_file:
        selected_input = args.out / "selected_http_input.jsonl"
        _selected_count, only = _filter_checkpoint(
            args.input, args.source_ids_file, selected_input
        )

    runner.HTTP_JSONL = selected_input
    forwarded = [
        "run_full_coverage_playwright_pass.py",
        "--only", only,
        "--playwright-workers", str(args.workers),
        "--listing-timeout", str(args.listing_timeout),
        "--property-timeout", str(args.property_timeout),
        "--max-items", str(args.max_items),
        "--max-pages", str(args.max_pages),
        "--out", str(args.out),
    ]
    if args.limit:
        forwarded.extend(("--limit", str(args.limit)))
    if args.resume:
        forwarded.append("--resume")
    original = sys.argv
    try:
        sys.argv = forwarded
        runner.main()
    finally:
        sys.argv = original
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
