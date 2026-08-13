#!/usr/bin/env python3
"""Find deterministic historical URL candidates for sources missing a website."""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import audit_missing_website_identity as identity


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_UNIVERSE = ROOT / "_scratch/codex_full_7004_coverage/source_universe_7004.csv"
DEFAULT_BACKUPS = ROOT / "backups supabase"
DEFAULT_OUT = ROOT / "_scratch/codex_full_7004_coverage/historical_url_recovery"
PROHIBITED_HOSTS = {
    "argenprop.com",
    "argenprop.com.ar",
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "mercadolibre.com.ar",
    "properati.com.ar",
    "twitter.com",
    "x.com",
    "zonaprop.com.ar",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def normalized_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if not raw.lower().startswith(("http://", "https://")):
        raw = "https://" + raw.lstrip("/")
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if not host or "." not in host:
        return ""
    if any(host == blocked or host.endswith("." + blocked) for blocked in PROHIBITED_HOSTS):
        return ""
    if parsed.scheme not in {"http", "https"}:
        return ""
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme}://{host}{path}" + (f"?{parsed.query}" if parsed.query else "")


def domain(value: Any) -> str:
    parsed = urlparse(normalized_url(value))
    return (parsed.hostname or "").lower().removeprefix("www.")


def _same_identity(current: dict[str, Any], historical: dict[str, Any]) -> bool:
    return bool(
        identity.normalized_name(current.get("nombre"))
        and identity.normalized_name(current.get("nombre"))
        == identity.normalized_name(historical.get("nombre"))
    )


def classify(
    universe: list[dict[str, str]],
    historical_rows: list[tuple[str, dict[str, str]]],
) -> list[dict[str, Any]]:
    by_id: dict[int, list[tuple[str, dict[str, str]]]] = defaultdict(list)
    for backup_name, row in historical_rows:
        try:
            by_id[int(row.get("id") or 0)].append((backup_name, row))
        except ValueError:
            continue

    results: list[dict[str, Any]] = []
    for current in universe:
        if current.get("website_url") or current.get("current_listing_url"):
            continue
        source_id = int(current["source_id"])
        matches = [
            (backup_name, row)
            for backup_name, row in by_id.get(source_id, [])
            if _same_identity(current, row)
        ]
        urls: list[tuple[str, str, str]] = []
        for backup_name, row in matches:
            for field in ("url_listado", "web"):
                candidate = normalized_url(row.get(field))
                if candidate:
                    urls.append((candidate, backup_name, field))

        domains = sorted({domain(candidate) for candidate, _, _ in urls if domain(candidate)})
        unique_urls = sorted({candidate for candidate, _, _ in urls})
        listing_urls = sorted({candidate for candidate, _, field in urls if field == "url_listado"})
        if not matches:
            confidence = "NO_MATCH"
            status = "historical_identity_not_found"
            proposed = ""
            evidence = "no same-id historical row with compatible normalized name"
        elif not unique_urls:
            confidence = "NO_MATCH"
            status = "historical_url_not_found"
            proposed = ""
            evidence = f"compatible_backups={len(matches)}; usable_urls=0"
        elif len(domains) != 1:
            confidence = "LOW"
            status = "historical_domain_ambiguous"
            proposed = ""
            evidence = f"compatible_backups={len(matches)}; domains={len(domains)}"
        else:
            confidence = "HIGH"
            status = "historical_url_deterministic"
            proposed = listing_urls[0] if len(listing_urls) == 1 else unique_urls[0]
            evidence = (
                f"same_source_id; compatible_name; domain={domains[0]}; "
                f"backup_rows={len(matches)}; url_observations={len(urls)}"
            )
        results.append(
            {
                "source_id": source_id,
                "source_name": current.get("nombre") or "",
                "proposed_url": proposed,
                "confidence": confidence,
                "status": status,
                "historical_domains": "|".join(domains),
                "historical_urls": "|".join(unique_urls[:8]),
                "detected_from": "|".join(sorted({name for _, name, _ in urls})),
                "evidence": evidence,
                "recommended_action": "preflight_http" if confidence == "HIGH" else "manual_review",
                "requires_db_change_later": confidence == "HIGH",
                "db_writes": 0,
            }
        )
    return results


def write_csv(path: Path, rows: list[dict[str, Any]], fields: tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_UNIVERSE)
    parser.add_argument("--backups", type=Path, default=DEFAULT_BACKUPS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    universe = read_csv(args.input)
    if len(universe) != 7004:
        raise RuntimeError(f"Expected 7004 universe rows, got {len(universe)}")
    historical_rows: list[tuple[str, dict[str, str]]] = []
    for path in sorted(args.backups.glob("*_inmobiliarias_main.csv")):
        historical_rows.extend((path.name, row) for row in read_csv(path))
    for path in sorted(args.backups.glob("*_inmobiliarias_scraping.csv")):
        historical_rows.extend((path.name, row) for row in read_csv(path))

    results = classify(universe, historical_rows)
    fields = (
        "source_id", "source_name", "proposed_url", "confidence", "status",
        "historical_domains", "historical_urls", "detected_from", "evidence",
        "recommended_action", "requires_db_change_later", "db_writes",
    )
    write_csv(args.out / "historical_url_recovery_results.csv", results, fields)
    safe = [row for row in results if row["confidence"] == "HIGH"]
    write_csv(args.out / "historical_url_recovery_high.csv", safe, fields)
    manual = [row for row in results if row["confidence"] != "HIGH"]
    write_csv(args.out / "historical_url_recovery_manual.csv", manual, fields)

    counts = Counter(row["status"] for row in results)
    summary = [
        "# Historical URL recovery audit",
        "",
        f"- Missing website sources audited: {len(results)}",
        f"- Deterministic historical URL candidates: {len(safe)}",
        f"- Manual/no match: {len(manual)}",
    ]
    summary.extend(f"- {key}: {value}" for key, value in sorted(counts.items()))
    summary.extend([
        "- DB writes: 0",
        "- URLs updated: 0",
        "- Next gate: bounded HTTP validation before any controlled DB preflight",
    ])
    (args.out / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print(f"audited={len(results)} high={len(safe)} manual={len(manual)} db_writes=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
