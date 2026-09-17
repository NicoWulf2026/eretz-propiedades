"""Finalize bounded diagnostics without inventing COMPLETE or empty inventory.

Adapted from the untracked local operator tool. Zero observed links, parser
errors, caps and low quality are not evidence of absent inventory or success.
Never writes to a database. Input evidence is preserved without mutation.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


PLAYWRIGHT_STATUS_MAP = {
    'playwright_success': 'recovered_parser',
    'playwright_partial_due_to_cap': 'partial_due_to_cap',
    'playwright_success_low_quality': 'needs_quality_fix',
    'playwright_no_property_links': 'no_property_links',
    'playwright_zero_properties': 'no_property_links',
    'playwright_parser_error': 'internal_error',
    'playwright_true_antibot': 'external_antibot',
    'playwright_captcha': 'external_captcha',
    'playwright_login_required': 'auth_required',
    'playwright_timeout': 'external_timeout',
    'playwright_domain_down': 'external_transport_error',
    'playwright_error': 'internal_error',
}


def load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding='utf-8-sig') as handle:
        if path.suffix.lower() == '.csv':
            return list(csv.DictReader(handle))
        return [json.loads(line) for line in handle if line.strip()]


def finalize_status(row: dict[str, Any]) -> tuple[str, str]:
    raw = row.get('playwright_final_status') or row.get('final_status') or 'internal_error'
    status = PLAYWRIGHT_STATUS_MAP.get(str(raw), str(raw))
    if status == 'still_no_property_links':
        status = 'no_property_links'
    if status == 'timeout':
        return 'external_timeout', 'bounded_retry_timeout'
    if status in ('no_property_links', 'partial_due_to_cap', 'needs_quality_fix', 'internal_error'):
        return status, 'requires_review_not_inventory_completeness'
    return status, 'playwright_status_final' if row.get('playwright_final_status') else 'diagnostic_status_final'


def by_source_id(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {int(row['source_id']): row for row in rows}


def choose_result(broad: dict[int, dict[str, Any]], retry: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for source_id in sorted(broad.keys() | retry.keys()):
        chosen = retry.get(source_id, broad.get(source_id))
        status, reason = finalize_status(chosen)
        result.append(dict(chosen, source_id=source_id, final_status=status,
                           finalization_reason=reason))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--broad-results', type=Path, required=True)
    parser.add_argument('--retry-results', type=Path, required=True)
    parser.add_argument('--out-csv', type=Path, required=True)
    parser.add_argument('--out-jsonl', type=Path, required=True)
    args = parser.parse_args()
    rows = choose_result(by_source_id(load_records(args.broad_results)), by_source_id(load_records(args.retry_results)))
    for path in (args.out_csv, args.out_jsonl):
        path.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open('w', encoding='utf-8', newline='') as handle:
        fields = sorted(set().union(*(row.keys() for row in rows))) if rows else ['source_id', 'final_status']
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    with args.out_jsonl.open('w', encoding='utf-8') as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
    review = sum(row['final_status'] in ('no_property_links', 'partial_due_to_cap', 'needs_quality_fix', 'internal_error') for row in rows)
    print(json.dumps({'sources': len(rows), 'requires_review': review, 'database_writes': 0}))
    return int(review > 0)


if __name__ == '__main__':
    raise SystemExit(main())
