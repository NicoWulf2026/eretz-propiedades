"""Compare local extraction rows, never agency aggregates or production writes.

This replaces the untracked historical gate's purpose, not its unsafe inference:
query-string IDs survive, ambiguous identities are retained for review, and one
property's presence cannot explain another property's loss. Exit 1 means review
is required, not permission to restore stale data or delete missing inventory.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from scraper.models import _normalize_url_for_hash
from scripts.property_freshest import CAMPOS_FUSIONABLES

VERSION = 'property_regression_gate_v2'


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple)):
        return bool(value)
    return not isinstance(value, float) or math.isfinite(value)


def identity(row: dict) -> tuple[str, str]:
    agency = row.get('canonical_agency_id')
    source = row.get('source_url')
    if not isinstance(agency, str) or not agency.strip() or not isinstance(source, str):
        raise ValueError('missing row identity')
    parsed = urlsplit(source)
    # A diagnostic artifact must not serialize embedded credentials either.
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('invalid source URL')
    parsed.port  # validates malformed ports without printing the input
    return agency, _normalize_url_for_hash(source)


def _index(rows: list[dict]) -> tuple[dict, list[dict]]:
    groups: dict = defaultdict(list)
    issues = []
    for position, row in enumerate(rows):
        try:
            groups[identity(row)].append(row)
        except (ValueError, TypeError, AttributeError):
            issues.append({'kind': 'INVALID_IDENTITY', 'position': position})
    indexed = {}
    for key, candidates in groups.items():
        # Never silently choose a last row; even equal duplicate rows need
        # an explicit dedupe decision before a regression gate can prove a match.
        if len(candidates) > 1:
            issues.append({'kind': 'AMBIGUOUS_IDENTITY', 'agency': key[0], 'url': key[1]})
        else:
            indexed[key] = candidates[0]
    return indexed, issues


def _loss_reason(field: str, old: dict, fresh: dict) -> str:
    # Row-scoped evidence is required. Aggregated field_coverage is deliberately
    # never read. An extraction detector's absence is not source-change proof.
    field_evidence = fresh.get('field_evidence')
    evidence = field_evidence.get(field) if isinstance(field_evidence, dict) else None
    if isinstance(evidence, dict) and evidence.get('reason'):
        try:
            same_row = identity(dict(fresh, source_url=evidence.get('source_url'))) == identity(fresh)
        except (ValueError, TypeError, AttributeError):
            same_row = False
        if same_row:
            if evidence.get('state') == 'PROVIDED_REJECTED':
                return 'EXPLAINED_VALIDATION'
            if evidence.get('state') == 'NOT_PROVIDED':
                return 'SOURCE_CHANGED_RECORDED'
    # The runner empties a description that is the site's own boilerplate
    # (repeated across the agency's listings, or a copyright footer) and marks
    # THAT row with the reason. Row-scoped, so it explains this row only.
    extra = fresh.get('extra')
    if (field == 'descripcion' and isinstance(extra, dict)
            and extra.get('descripcion_descartada')):
        return 'EXPLAINED_VALIDATION'
    # A move only exists if the value is present in the FRESH neighboring field.
    neighbors = {'barrio': ('ciudad', 'provincia'), 'ciudad': ('barrio', 'provincia'),
                 'provincia': ('ciudad', 'barrio')}
    for neighbor in neighbors.get(field, ()):
        if present(fresh.get(neighbor)) and old[field] == fresh[neighbor]:
            # Report the move, but do not authorize it: municipio != localidad.
            return 'DIMENSION_MOVE_REVIEW'
    return 'UNEXPLAINED_LOSS'


def compare(old_rows: list[dict], fresh_rows: list[dict]) -> dict:
    old, old_issues = _index(old_rows)
    fresh, fresh_issues = _index(fresh_rows)
    blocked = { (item['agency'], item['url']) for item in old_issues + fresh_issues
               if item['kind'] == 'AMBIGUOUS_IDENTITY' }
    changes = []
    for key in sorted(set(old) | set(fresh)):
        if key in blocked:
            continue
        before, after = old.get(key), fresh.get(key)
        if before is None or after is None:
            changes.append({'agency': key[0], 'url': key[1],
                            'kind': 'NEWLY_OBSERVED' if before is None else 'INVENTORY_NOT_OBSERVED'})
            continue
        for field in CAMPOS_FUSIONABLES:
            previous, current = before.get(field), after.get(field)
            had, has = present(previous), present(current)
            if had and not has:
                kind = _loss_reason(field, before, after)
            elif has and not had:
                kind = 'FIELD_RECOVERED'
            elif had and (previous != current or isinstance(previous, bool) != isinstance(current, bool)):
                kind = 'FIELD_CHANGED'
            else:
                continue
            # Values/payloads are intentionally not reproduced in the report.
            changes.append({'agency': key[0], 'url': key[1], 'field': field, 'kind': kind})
    needs_review = {'UNEXPLAINED_LOSS', 'DIMENSION_MOVE_REVIEW', 'INVENTORY_NOT_OBSERVED'}
    review = bool(old_issues or fresh_issues or any(row['kind'] in needs_review for row in changes))
    return {'version': VERSION, 'status': 'REVIEW_REQUIRED' if review else 'NO_UNEXPLAINED_LOSS',
            'old_rows': len(old_rows), 'fresh_rows': len(fresh_rows),
            'matched_rows': len((set(old) & set(fresh)) - blocked),
            'counts': dict(Counter(row['kind'] for row in changes)), 'changes': changes,
            'old_issues': old_issues, 'fresh_issues': fresh_issues,
            'database_writes': 0, 'publication_authorized': False}


def read_rows(path: Path) -> list[dict]:
    rows = []
    for position, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError('not an object')
        except ValueError as exc:
            raise ValueError(f'invalid JSONL row {position}') from exc
        rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old', type=Path, required=True)
    parser.add_argument('--fresh', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() in {args.old.resolve(), args.fresh.resolve()} or args.output.exists():
        parser.error('output must be a new artifact, not an input or an existing file')
    try:
        report = compare(read_rows(args.old), read_rows(args.fresh))
    except ValueError:
        parser.error('invalid input artifact; no report written')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    print(json.dumps({key: value for key, value in report.items()
                      if key not in {'changes', 'old_issues', 'fresh_issues'}}, ensure_ascii=False))
    return int(report['status'] == 'REVIEW_REQUIRED')


if __name__ == '__main__':
    raise SystemExit(main())
