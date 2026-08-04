#!/usr/bin/env python3
"""Classify missing-website records against exact-name canonical sources."""

from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import run_targeted_coverage_diagnostic as diagnostic  # noqa: E402


DEFAULT_INPUT = ROOT / "_scratch/codex_full_7004_coverage/source_universe_7004.csv"
DEFAULT_OUT = ROOT / "_scratch/codex_full_7004_coverage/missing_website_identity_audit"


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def normalized_name(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode().lower()
    stop = {"inmobiliaria", "propiedades", "bienes", "raices", "negocios", "inmobiliarios", "sa", "srl", "de", "y", "del"}
    return " ".join(token for token in re.findall(r"[a-z0-9]+", text) if token not in stop)


def normalized_location(value: Any) -> str:
    return unicodedata.normalize("NFKD", str(value or "")).encode(
        "ascii", "ignore"
    ).decode().lower().strip()


def location_compatible(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_city, right_city = normalized_location(left.get("ciudad")), normalized_location(right.get("ciudad"))
    left_province = normalized_location(left.get("provincia"))
    right_province = normalized_location(right.get("provincia"))
    return bool(
        (left_city and right_city and left_city == right_city)
        or (left_province and right_province and left_province == right_province)
    )


def classify(
    universe: list[dict[str, str]], db_by_id: dict[int, dict[str, Any]]
) -> list[dict[str, Any]]:
    url_sources: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in universe:
        if row.get("website_url") or row.get("current_listing_url"):
            url_sources[normalized_name(row.get("nombre"))].append(row)
    output = []
    for row in universe:
        if row.get("website_url") or row.get("current_listing_url"):
            continue
        matches = url_sources.get(normalized_name(row.get("nombre")), [])
        if len(matches) != 1:
            decision = "missing_website_unmatched"
            canonical = None
            evidence = f"exact_name_url_sources={len(matches)}"
        else:
            canonical = matches[0]
            left = db_by_id.get(int(row["source_id"]), {})
            right = db_by_id.get(int(canonical["source_id"]), {})
            if location_compatible(left, right):
                decision = "duplicate_source_record"
                evidence = "exact normalized name plus compatible city/province"
            else:
                decision = "manual_identity_review"
                evidence = "exact normalized name but no compatible city/province evidence"
        output.append({
            "source_id": row["source_id"],
            "source_name": row.get("nombre") or "",
            "decision": decision,
            "canonical_source_id": canonical.get("source_id") if canonical else "",
            "canonical_name": canonical.get("nombre") if canonical else "",
            "canonical_website_url": canonical.get("website_url") if canonical else "",
            "canonical_listing_url": canonical.get("current_listing_url") if canonical else "",
            "evidence": evidence,
            "db_writes": 0,
        })
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    universe = _read(args.input)
    if len(universe) != 7004:
        raise RuntimeError("Universe must contain 7004 rows")
    names_with_one_match = set()
    url_counts: dict[str, int] = defaultdict(int)
    for row in universe:
        if row.get("website_url") or row.get("current_listing_url"):
            url_counts[normalized_name(row.get("nombre"))] += 1
    for row in universe:
        if not row.get("website_url") and not row.get("current_listing_url") and url_counts[normalized_name(row.get("nombre"))] == 1:
            names_with_one_match.add(normalized_name(row.get("nombre")))
    relevant_ids = {
        int(row["source_id"])
        for row in universe
        if normalized_name(row.get("nombre")) in names_with_one_match
    }
    db_rows, _checksum = diagnostic._load_sources_rest(sorted(relevant_ids))
    results = classify(universe, {int(row["id"]): row for row in db_rows})
    fields = (
        "source_id", "source_name", "decision", "canonical_source_id", "canonical_name",
        "canonical_website_url", "canonical_listing_url", "evidence", "db_writes",
    )
    with (args.out / "missing_website_identity_results.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)
    counts: dict[str, int] = defaultdict(int)
    for row in results:
        counts[row["decision"]] += 1
    (args.out / "summary.md").write_text(
        "# Missing website identity audit\n\n"
        + "\n".join(f"- {key}: {value}" for key, value in sorted(counts.items()))
        + "\n- DB writes: 0\n- URLs copied or updated: 0\n",
        encoding="utf-8",
    )
    print(" ".join(f"{key}={value}" for key, value in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
