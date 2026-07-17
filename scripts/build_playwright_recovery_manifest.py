#!/usr/bin/env python3
"""Build an evidence-based, explicit Playwright diagnostic manifest."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GAPS = ROOT / "_scratch/codex_full_7004_coverage/partition_after_parser/manifest_internal_gaps.csv"
DEFAULT_CMS = ROOT / "_scratch/cms_strategy_proposal/cms_strategy_proposal.csv"
DEFAULT_PARSER = ROOT / "_scratch/parser_gap_analysis_pr_be_parser_07/parser_gap_results.csv"
DEFAULT_OUT = ROOT / "_scratch/codex_full_7004_coverage/playwright_recovery_candidates.csv"
DYNAMIC_CMS = {"wix", "next_spa", "react_spa", "nuxt", "vue"}


def _read(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _truth(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "si"}


def select(
    gaps: list[dict[str, str]],
    cms_by_id: dict[str, dict[str, str]],
    parser_by_id: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    selected = []
    for row in gaps:
        reasons = []
        if row.get("gap_family") == "playwright":
            reasons.append("current_playwright_gap")
        cms = cms_by_id.get(row["source_id"], {})
        if _truth(cms.get("requires_playwright")):
            reasons.append("cms_requires_playwright")
        parser = parser_by_id.get(row["source_id"], {})
        if _truth(parser.get("requires_js")):
            reasons.append("parser_requires_js")
        if (
            row.get("gap_family") in {"strategy", "parser"}
            and str(row.get("cms_detectado") or "").lower() in DYNAMIC_CMS
        ):
            reasons.append("dynamic_cms")
        if reasons:
            selected.append({
                "source_id": row["source_id"],
                "source_name": row.get("nombre") or "",
                "website_url": row.get("website_url") or "",
                "listing_url": row.get("current_listing_url") or "",
                "gap_family": row.get("gap_family") or "",
                "evidence": ";".join(reasons),
            })
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gaps", type=Path, default=DEFAULT_GAPS)
    parser.add_argument("--cms", type=Path, default=DEFAULT_CMS)
    parser.add_argument("--parser-analysis", type=Path, default=DEFAULT_PARSER)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    gaps = _read(args.gaps)
    cms = {row["source_id"]: row for row in _read(args.cms)}
    parser_rows = {row["source_id"]: row for row in _read(args.parser_analysis)}
    rows = select(gaps, cms, parser_rows)
    if len(rows) != len({row["source_id"] for row in rows}):
        raise RuntimeError("Duplicate source_id in Playwright recovery manifest")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fields = ("source_id", "source_name", "website_url", "listing_url", "gap_family", "evidence")
    with args.out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"playwright_candidates={len(rows)} unique={len({row['source_id'] for row in rows})}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
