#!/usr/bin/env python3
"""Derive bounded timeout overrides and retry manifests from a completed run."""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse


OVERRIDE_FIELDS = (
    "listing_timeout_ms",
    "detail_timeout_ms",
    "detail_retries",
    "retry_backoff_s",
    "source_no_progress_s",
    "source_hard_cap_s",
)


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write(path: Path, rows: list[dict], fields: list[str] | tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _domain(value: str) -> str:
    try:
        return urlparse(value).netloc.lower().split(":", 1)[0].removeprefix("www.")
    except Exception:
        return ""


def _normalized_url(value: str) -> str:
    return value.strip().rstrip("/").lower()


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    pos = (len(ordered) - 1) * quantile
    lower = int(pos)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (pos - lower)


def _timeout_urls(log_text: str) -> list[str]:
    return re.findall(r"Timeout navegando a (https?://\S+)", log_text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--url-corrections", type=Path)
    parser.add_argument("--exclusions", type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    metrics = _read(args.metrics)
    results = _read(args.results)
    manifest = _read(args.manifest)
    if args.url_corrections and args.url_corrections.exists():
        corrections = {row["source_id"]: row["new_url_listado"] for row in _read(args.url_corrections)}
        for row in manifest:
            if row["source_id"] in corrections:
                row["new_url_listado"] = corrections[row["source_id"]]
    manifest_by_id = {row["source_id"]: row for row in manifest}
    exclusion_ids = (
        {row["source_id"] for row in _read(args.exclusions)}
        if args.exclusions and args.exclusions.exists()
        else set()
    )
    metrics_by_id = {row["source_id"]: row for row in metrics}
    domains: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in manifest:
        for value in (row.get("new_url_listado", ""), row.get("website_url", "")):
            domain = _domain(value)
            if domain and row not in domains[domain]:
                domains[domain].append(row)

    timeout_urls = _timeout_urls(args.log.read_text(encoding="utf-8", errors="replace"))
    source_events: dict[str, Counter] = defaultdict(Counter)
    domain_rows = []
    for domain, urls in sorted(
        ((domain, values) for domain, values in Counter(_domain(url) for url in timeout_urls).items()),
        key=lambda item: (-item[1], item[0]),
    ):
        candidates = domains.get(domain, [])
        candidate_ids = ";".join(row["source_id"] for row in candidates)
        classification = "unique_source" if len(candidates) == 1 else "ambiguous_or_unmapped"
        domain_rows.append({
            "domain": domain,
            "timeout_events": urls,
            "candidate_source_ids": candidate_ids,
            "classification": classification,
        })
        if len(candidates) != 1:
            continue
        source = candidates[0]
        sid = source["source_id"]
        source_events[sid]["timeout_events"] += urls
        listing = _normalized_url(source.get("new_url_listado", ""))
        listing_count = sum(
            1 for url in timeout_urls
            if _domain(url) == domain and _normalized_url(url) == listing
        )
        source_events[sid]["listing_timeout_events"] += listing_count
        source_events[sid]["detail_timeout_events"] += urls - listing_count

    durations = [float(row.get("source_time_s") or 0) for row in metrics]
    detail_counts = [float(row.get("n_nuevas") or 0) for row in metrics]
    percentiles = []
    for quantile in (0.5, 0.9, 0.95, 0.99):
        percentiles.append({
            "percentile": f"p{int(quantile * 100)}",
            "duration_s": round(_percentile(durations, quantile), 1),
            "details_requested": round(_percentile(detail_counts, quantile), 1),
        })
    _write(args.out / "source_duration_percentiles.csv", percentiles, ["percentile", "duration_s", "details_requested"])

    overrides = []
    for sid, counts in sorted(source_events.items(), key=lambda item: (-item[1]["timeout_events"], int(item[0]))):
        source = manifest_by_id[sid]
        metric = metrics_by_id.get(sid, {})
        listing_count = counts["listing_timeout_events"]
        detail_count = counts["detail_timeout_events"]
        overrides.append({
            "source_id": sid,
            "source_name": source.get("source_name", ""),
            "timeout_events_run_a": counts["timeout_events"],
            "listing_timeout_events": listing_count,
            "detail_timeout_events": detail_count,
            "run_a_duration_s": metric.get("source_time_s", ""),
            "run_a_details_requested": metric.get("n_nuevas", ""),
            "listing_timeout_ms": "45000" if listing_count else "",
            "detail_timeout_ms": "30000" if detail_count else "",
            "detail_retries": "1" if detail_count else "0",
            "retry_backoff_s": "0.5",
            "source_no_progress_s": "180",
            "source_hard_cap_s": "",
            "evidence": "Run A navigation timeout log",
        })
    override_by_id = {row["source_id"]: row for row in overrides}

    def enriched(row: dict[str, str]) -> dict[str, str]:
        result = dict(row)
        override = override_by_id.get(row["source_id"], {})
        for field in OVERRIDE_FIELDS:
            result[field] = str(override.get(field, ""))
        return result

    output_fields = list(manifest[0].keys()) + [field for field in OVERRIDE_FIELDS if field not in manifest[0]]
    run_b_rows = [enriched(row) for row in manifest if row["source_id"] not in exclusion_ids]
    _write(args.out / "run_b_manifest.csv", run_b_rows, output_fields)

    internal_ids = {
        row["source_id"] for row in results
        if row.get("classification", "").startswith("INTERNAL")
    } - exclusion_ids
    internal_rows = [enriched(manifest_by_id[sid]) for sid in sorted(internal_ids, key=int)]
    timeout_only_ids = set(source_events) - internal_ids - exclusion_ids
    timeout_rows = [enriched(manifest_by_id[sid]) for sid in sorted(timeout_only_ids, key=int)]
    _write(args.out / "run_a_internal_retry_manifest.csv", internal_rows, output_fields)
    _write(args.out / "run_a_timeout_retry_manifest.csv", timeout_rows, output_fields)
    _write(
        args.out / "source_timeout_overrides.csv",
        overrides,
        [
            "source_id", "source_name", "timeout_events_run_a",
            "listing_timeout_events", "detail_timeout_events",
            "run_a_duration_s", "run_a_details_requested", *OVERRIDE_FIELDS, "evidence",
        ],
    )
    _write(
        args.out / "timeout_events_by_domain.csv",
        domain_rows,
        ["domain", "timeout_events", "candidate_source_ids", "classification"],
    )
    slowest = sorted(metrics, key=lambda row: float(row.get("source_time_s") or 0), reverse=True)[:50]
    _write(args.out / "top_slowest_sources.csv", slowest, list(metrics[0].keys()))

    ambiguous = sum(row["timeout_events"] for row in domain_rows if row["classification"] != "unique_source")
    p50 = percentiles[0]["duration_s"]
    p90 = percentiles[1]["duration_s"]
    p95 = percentiles[2]["duration_s"]
    summary = [
        "# Run A timeout policy",
        "",
        f"- Sources analyzed: {len(metrics)}",
        f"- Duration p50/p90/p95: {p50}s / {p90}s / {p95}s",
        f"- Navigation timeout events in legacy log: {len(timeout_urls)}",
        f"- Sources with uniquely attributable timeout evidence: {len(overrides)}",
        f"- Ambiguous or unmapped timeout events: {ambiguous}",
        f"- Internal retry sources: {len(internal_rows)}",
        f"- Timeout-only retry sources (excluding internal overlap): {len(timeout_rows)}",
        f"- Explicit external exclusions from Run B: {len(exclusion_ids)}",
        "",
        "## Policy for retries and Run B",
        "",
        "- HTTP connect timeout: 5s; read timeout: 15-30s by operation.",
        "- Base listing timeout: 40s (unchanged from Run A); base detail timeout: 20s.",
        "- Base detail retries: 0. Evidence-based override: 1 retry at 30s.",
        "- Backoff: 0.5s; request retries capped at 1-2.",
        "- No-progress cap: 120s base; 180s only for evidenced timeout sources.",
        "- Dynamic source budget: max(1800s, 300s + 10s/detail), absolute cap 5400s.",
        "- Listing timeout override: 45s only when Run A timed out on the listing URL.",
        "",
        "Run A legacy logs did not carry source IDs on detail warnings. Overrides are only automatic when the timeout domain maps to one manifest source; ambiguous events remain manual.",
    ]
    (args.out / "timeout_policy_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print(f"sources={len(metrics)} timeouts={len(timeout_urls)} overrides={len(overrides)} internal_retries={len(internal_rows)} ambiguous_events={ambiguous}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
