#!/usr/bin/env python3
"""Reconcile an audited Pipeline A manifest without replaying closed sources."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


PROHIBITED_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "tiktok.com",
    "linkedin.com",
    "youtube.com",
    "youtu.be",
    "mercadolibre.com",
    "argenprop.com",
    "argenprop.com.ar",
    "zonaprop.com",
    "zonaprop.com.ar",
    "properati.com",
    "properati.com.ar",
    "navent.com",
    "inmuebles24.com",
    "mitula.com.ar",
    "nuroa.com.ar",
    "wa.me",
    "whatsapp.com",
    "t.me",
    "bit.ly",
    "linktr.ee",
    "wordpress.com",
    "blogspot.com",
    "wixsite.com",
    "maps.google",
    "google.com",
    "remax.com",
    "remax.com.ar",
}
UNSAFE_DUPLICATE_DECISIONS = {
    "duplicate_source_record": "DUPLICATE_SOURCE_RECORD",
    "manual_shared_url": "AMBIGUOUS_SHARED_URL",
}
EXECUTION_RELEVANT_FIELDS = (
    "new_url_listado",
    "needs_playwright",
    "scraping_strategy",
    "inmobiliaria_id",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def normalize_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urlsplit(raw)
    host = parsed.netloc.lower().removeprefix("www.")
    path = re.sub(r"/+", "/", parsed.path).rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), host, path, parsed.query, ""))


def prohibited_domain(value: str) -> str:
    normalized = normalize_url(value)
    if not normalized:
        return ""
    host = urlsplit(normalized).netloc
    return next(
        (
            domain
            for domain in PROHIBITED_DOMAINS
            if host == domain or host.endswith("." + domain)
        ),
        "",
    )


def reconcile(
    prior_rows: list[dict[str, str]],
    candidate_rows: list[dict[str, str]],
    duplicate_rows: list[dict[str, str]],
    universe_ids: set[int],
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], dict[str, int]]:
    if not candidate_rows:
        raise ValueError("Candidate manifest cannot be empty")
    fields = list(candidate_rows[0])
    prior = {int(row["source_id"]): row for row in prior_rows}
    candidates: dict[int, dict[str, str]] = {}
    for row in candidate_rows:
        source_id = int(row["source_id"])
        if source_id in candidates:
            raise ValueError(f"Duplicate candidate source_id={source_id}")
        candidates[source_id] = row

    unsafe = {
        int(row["source_id"]): UNSAFE_DUPLICATE_DECISIONS[row["decision"]]
        for row in duplicate_rows
        if row.get("decision") in UNSAFE_DUPLICATE_DECISIONS
    }
    final_rows: list[dict[str, str]] = []
    removed: list[dict[str, str]] = []
    for source_id in sorted(candidates):
        row = candidates[source_id]
        reason = unsafe.get(source_id, "")
        domain = prohibited_domain(row.get("new_url_listado", ""))
        if domain:
            reason = f"PROHIBITED_DOMAIN:{domain}"
        if reason:
            removed.append({**row, "removal_reason": reason})
        else:
            final_rows.append(row)

    if any(int(row["source_id"]) not in universe_ids for row in final_rows):
        raise ValueError("Final manifest contains a source ID outside the canonical universe")
    urls = [normalize_url(row.get("new_url_listado", "")) for row in final_rows]
    if any(not url or urlsplit(url).scheme not in {"http", "https"} for url in urls):
        raise ValueError("Final manifest contains a blank or invalid URL")
    duplicate_urls = sorted({url for url in urls if urls.count(url) > 1})
    if duplicate_urls:
        raise ValueError(f"Unresolved normalized URL duplicates: {duplicate_urls[:5]}")

    final_by_id = {int(row["source_id"]): row for row in final_rows}
    new_ids = sorted(set(final_by_id) - set(prior))
    changed_ids = sorted(
        source_id
        for source_id in set(final_by_id) & set(prior)
        if any(
            final_by_id[source_id].get(field, "") != prior[source_id].get(field, "")
            for field in EXECUTION_RELEVANT_FIELDS
        )
    )
    delta_ids = set(new_ids) | set(changed_ids)
    delta = [row for row in final_rows if int(row["source_id"]) in delta_ids]
    summary = {
        "prior_sources": len(prior),
        "candidate_sources": len(candidates),
        "final_sources": len(final_rows),
        "new_sources": len(new_ids),
        "changed_sources": len(changed_ids),
        "retired_sources": len(set(prior) - set(final_by_id)),
        "duplicate_records_removed": sum(
            row["removal_reason"] == "DUPLICATE_SOURCE_RECORD" for row in removed
        ),
        "ambiguous_shared_url_removed": sum(
            row["removal_reason"] == "AMBIGUOUS_SHARED_URL" for row in removed
        ),
        "prohibited_removed": sum(
            row["removal_reason"].startswith("PROHIBITED_DOMAIN:") for row in removed
        ),
        "execution_delta_sources": len(delta),
        "unique_source_ids": len(final_by_id),
        "unique_normalized_urls": len(set(urls)),
        "fk_resolvable_sources": len(final_rows),
        "invalid_urls": 0,
        "unresolved_duplicate_urls": 0,
        "unclassified_sources": 0,
    }
    return final_rows, delta, removed, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--duplicate-audit", type=Path, required=True)
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    prior_rows = read_csv(args.prior)
    candidate_rows = read_csv(args.candidate)
    duplicate_rows = read_csv(args.duplicate_audit)
    universe_ids = {int(row["source_id"]) for row in read_csv(args.universe)}
    final_rows, delta, removed, summary = reconcile(
        prior_rows,
        candidate_rows,
        duplicate_rows,
        universe_ids,
    )
    fields = list(candidate_rows[0])
    write_csv(args.out / "manifest_final_pipeline_a.csv", final_rows, fields)
    write_csv(args.out / "manifest_execution_delta.csv", delta, fields)
    write_csv(args.out / "manifest_removed.csv", removed, fields + ["removal_reason"])
    (args.out / "manifest_comparison.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
