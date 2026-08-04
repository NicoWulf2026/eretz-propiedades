#!/usr/bin/env python3
"""Audit duplicate agency source URLs without modifying the database."""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "_scratch/codex_full_7004_coverage/source_universe_7004.csv"
DEFAULT_OUT = ROOT / "_scratch/codex_full_7004_coverage/duplicate_source_audit"


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write(path: Path, rows: list[dict[str, Any]], fields: tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def normalize_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urlsplit(raw)
    host = parsed.netloc.lower().removeprefix("www.")
    path = (parsed.path or "/").rstrip("/") or "/"
    query = parsed.query.rstrip("&")
    return host + path + ("?" + query if query else "")


def normalized_name(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode().lower()
    stop = {"inmobiliaria", "propiedades", "bienes", "raices", "grupo", "srl", "sa"}
    return " ".join(token for token in re.findall(r"[a-z0-9]+", text) if token not in stop)


def names_compatible(left: Any, right: Any) -> bool:
    a, b = normalized_name(left), normalized_name(right)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    sa, sb = set(a.split()), set(b.split())
    return len(sa & sb) / max(len(sa | sb), 1) >= 0.5


def _canonical(rows: list[dict[str, str]]) -> dict[str, str]:
    return max(
        rows,
        key=lambda row: (
            str(row.get("current_category") or "").startswith("SUCCESS"),
            int(row.get("properties_count") or 0),
            -int(row["source_id"]),
        ),
    )


def classify(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        effective = row.get("current_listing_url") or row.get("website_url") or ""
        normalized = normalize_url(effective)
        if normalized:
            groups[normalized].append(row)

    output: list[dict[str, Any]] = []
    group_number = 0
    for normalized, members in sorted(groups.items()):
        if len(members) < 2:
            continue
        group_number += 1
        compatible = all(
            names_compatible(members[0].get("nombre"), member.get("nombre"))
            for member in members[1:]
        )
        canonical = _canonical(members) if compatible else None
        for member in members:
            if canonical is None:
                decision = "manual_shared_url"
                canonical_id = ""
                eligible = False
                evidence = "identical normalized URL with incompatible agency names"
            elif member is canonical:
                decision = "canonical_source"
                canonical_id = canonical["source_id"]
                eligible = True
                evidence = "compatible names; canonical chosen by prior success, property count, source_id"
            else:
                decision = "duplicate_source_record"
                canonical_id = canonical["source_id"]
                eligible = False
                evidence = "compatible names and identical normalized effective URL"
            output.append({
                "group_id": group_number,
                "normalized_url": normalized,
                "group_size": len(members),
                "source_id": member["source_id"],
                "source_name": member.get("nombre") or "",
                "website_url": member.get("website_url") or "",
                "listing_url": member.get("current_listing_url") or "",
                "properties_count": member.get("properties_count") or 0,
                "current_category": member.get("current_category") or "",
                "decision": decision,
                "canonical_source_id": canonical_id,
                "eligible": eligible,
                "evidence": evidence,
            })
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    source_rows = _read(args.input)
    if len(source_rows) != 7004 or len({row["source_id"] for row in source_rows}) != 7004:
        raise RuntimeError("Input must contain 7004 unique source IDs")
    results = classify(source_rows)
    fields = (
        "group_id", "normalized_url", "group_size", "source_id", "source_name",
        "website_url", "listing_url", "properties_count", "current_category",
        "decision", "canonical_source_id", "eligible", "evidence",
    )
    _write(args.out / "duplicate_source_records.csv", results, fields)
    _write(
        args.out / "canonical_sources.csv",
        [row for row in results if row["decision"] == "canonical_source"],
        fields,
    )
    _write(
        args.out / "duplicate_source_exclusions.csv",
        [row for row in results if not row["eligible"]],
        fields,
    )
    counts = Counter(row["decision"] for row in results)
    groups = len({row["group_id"] for row in results})
    summary = {
        "universe": len(source_rows),
        "duplicate_url_groups": groups,
        "rows_in_groups": len(results),
        **counts,
        "db_writes": 0,
    }
    (args.out / "duplicate_source_summary.md").write_text(
        "# Duplicate source record audit\n\n"
        + "\n".join(f"- {key}: {value}" for key, value in summary.items())
        + "\n\nNo database changes were made. Shared URLs with incompatible names are fail-closed for manual review.\n",
        encoding="utf-8",
    )
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
