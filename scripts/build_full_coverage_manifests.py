#!/usr/bin/env python3
"""Partition all 7004 sources into exclusive coverage manifests."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_UNIVERSE = ROOT / "_scratch/codex_full_7004_coverage/source_universe_7004.csv"
DEFAULT_RESULTS = ROOT / "_scratch/codex_full_7004_coverage/current_http_diagnostic/source_results.csv"
DEFAULT_OUT = ROOT / "_scratch/codex_full_7004_coverage"
DEFAULT_DUPLICATES = DEFAULT_OUT / "duplicate_source_audit/duplicate_source_records.csv"
DEFAULT_MISSING_IDENTITIES = DEFAULT_OUT / "missing_website_identity_audit/missing_website_identity_results.csv"
SUCCESS_STATUSES = {"success", "partial_due_to_cap", "partial_success"}
TRANSIENT_STATUSES = {"timeout", "server_error", "http_error", "dns_error", "unexpected_error"}
RESULT_EXTERNAL_FINAL = {
    "antibot": "ANTI_BOT",
    "captcha": "CAPTCHA",
    "auth_required": "AUTH_REQUIRED",
}
PROHIBITED_DOMAINS = {
    "facebook.com", "instagram.com", "twitter.com", "x.com", "tiktok.com",
    "linkedin.com", "youtube.com", "youtu.be", "mercadolibre.com",
    "argenprop.com", "argenprop.com.ar", "zonaprop.com", "zonaprop.com.ar",
    "properati.com", "properati.com.ar", "navent.com", "inmuebles24.com",
    "mitula.com.ar", "nuroa.com.ar", "wa.me", "whatsapp.com", "t.me",
    "bit.ly", "linktr.ee", "wordpress.com", "blogspot.com", "wixsite.com",
    "maps.google", "google.com", "remax.com", "remax.com.ar",
}
MANIFEST_FIELDS = (
    "source_id", "source_name", "new_url_listado", "old_url_listado",
    "combined_status", "needs_playwright", "error", "final_status",
    "scraping_strategy", "province", "city", "website_url", "inmobiliaria_id",
    "fk_status", "manifest_slug", "eligible", "final_validation_status",
    "coverage_family", "evidence",
)


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write(path: Path, rows: list[dict[str, Any]], fields: tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _truth(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "si"}


def _result_rank(row: dict[str, str]) -> int:
    status = row.get("final_status") or ""
    if status in SUCCESS_STATUSES:
        return 40
    if status == "success_low_quality":
        return 35
    if status in TRANSIENT_STATUSES:
        return 10
    if status:
        return 25
    return 0


def _normalize_result(row: dict[str, str]) -> dict[str, str]:
    normalized = dict(row)
    status = row.get("final_status") or ""
    if not status and row.get("playwright_final_status"):
        status = {
            "playwright_success": "success",
            "playwright_partial_due_to_cap": "partial_due_to_cap",
            "playwright_success_low_quality": "success_low_quality",
            "playwright_no_property_links": "no_property_links",
            "playwright_zero_properties": "no_property_links",
            "playwright_parser_error": "parser_error",
            "playwright_true_antibot": "antibot",
            "playwright_captcha": "captcha",
            "playwright_login_required": "auth_required",
            "playwright_timeout": "timeout",
            "playwright_domain_down": "dns_error",
            "playwright_error": "unexpected_error",
        }.get(row["playwright_final_status"], row["playwright_final_status"])
    status = {
        "recovered_parser": "success",
        "still_no_property_links": "no_property_links",
        "external_antibot": "antibot",
        "external_captcha": "captcha",
        "external_http_error": "http_error",
        "internal_error": "unexpected_error",
    }.get(status, status)
    normalized["final_status"] = status
    return normalized


def _merge_result(current: dict[str, str] | None, candidate: dict[str, str]) -> dict[str, str]:
    if current is None or _result_rank(candidate) >= _result_rank(current):
        return candidate
    return current


def _is_prohibited_url(value: Any) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return False
    if "://" not in raw:
        raw = "https://" + raw
    host = urlsplit(raw).netloc.lower().removeprefix("www.")
    return any(host == item or host.endswith("." + item) for item in PROHIBITED_DOMAINS)


def _slug(value: Any, source_id: Any) -> str:
    import re
    text = re.sub(r"[^a-z0-9_]+", "_", str(value or "").lower()).strip("_")[:40]
    return text or f"src_{source_id}"


def _manifest_row(source: dict[str, str], family: str, evidence: str) -> dict[str, Any]:
    source_id = int(source["source_id"])
    listing = source.get("current_listing_url") or source.get("website_url") or ""
    return {
        "source_id": source_id,
        "source_name": source.get("nombre") or "",
        "new_url_listado": listing,
        "old_url_listado": source.get("current_listing_url") or "",
        "combined_status": "success",
        "needs_playwright": source.get("requires_playwright") or "False",
        "error": "",
        "final_status": "success",
        "scraping_strategy": source.get("estrategia_scraping") or "",
        "province": "",
        "city": "",
        "website_url": source.get("website_url") or "",
        "inmobiliaria_id": source_id,
        "fk_status": "canonical_id",
        "manifest_slug": _slug(source.get("nombre"), source_id),
        "eligible": True,
        "final_validation_status": family.upper(),
        "coverage_family": family,
        "evidence": evidence,
    }


def _recovery_family(source: dict[str, str]) -> str:
    status = source.get("diagnostic_status") or ""
    return {
        "needs_listing_url": "recovered_url",
        "needs_parser": "recovered_parser",
        "needs_cms_strategy": "recovered_strategy",
        "needs_playwright": "recovered_playwright",
        "needs_quality_fix": "recovered_config",
    }.get(status, "ready_existing")


def _gap_family(result: dict[str, str] | None, source: dict[str, str]) -> str:
    status = (result or {}).get("final_status") or ""
    if status in {"bad_listing_url", "missing_listing_url", "ssl_error"}:
        return "url"
    if status in {"cms_unknown", "strategy_missing", "strategy_wrong"}:
        return "strategy"
    if status in {"no_property_links", "parser_error"}:
        return "parser"
    if status in {"requires_playwright", "forbidden", "antibot", "captcha"}:
        return "playwright"
    if status in {"timeout", "server_error", "http_error", "dns_error"}:
        return "transient_http"
    if status in {"success_low_quality"}:
        return "quality"
    return (source.get("diagnostic_status") or "manual").removeprefix("needs_")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE)
    parser.add_argument("--http-results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--additional-results", type=Path, action="append", default=[])
    parser.add_argument("--duplicate-audit", type=Path, default=DEFAULT_DUPLICATES)
    parser.add_argument("--missing-identity-audit", type=Path, default=DEFAULT_MISSING_IDENTITIES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    universe = _read(args.universe)
    results = {
        int(row["source_id"]): _normalize_result(row)
        for row in _read(args.http_results)
    }
    for path in args.additional_results:
        for row in _read(path):
            row = _normalize_result(row)
            source_id = int(row["source_id"])
            results[source_id] = _merge_result(results.get(source_id), row)
    duplicate_decisions = {
        int(row["source_id"]): row
        for row in _read(args.duplicate_audit)
        if row.get("decision") in {"duplicate_source_record", "manual_shared_url"}
    } if args.duplicate_audit.exists() else {}
    missing_identity_decisions = {
        int(row["source_id"]): row
        for row in _read(args.missing_identity_audit)
        if row.get("decision") in {"duplicate_source_record", "manual_identity_review"}
    } if args.missing_identity_audit.exists() else {}
    if len(universe) != 7004 or len({row["source_id"] for row in universe}) != 7004:
        raise RuntimeError("Universe must contain 7004 unique source IDs")

    families: dict[str, list[dict[str, Any]]] = {
        "ready_existing": [],
        "recovered_url": [],
        "recovered_parser": [],
        "recovered_strategy": [],
        "recovered_playwright": [],
        "recovered_config": [],
    }
    manual: list[dict[str, Any]] = []
    external: list[dict[str, Any]] = []
    prohibited: list[dict[str, Any]] = []
    internal_gaps: list[dict[str, Any]] = []
    assignments: dict[int, str] = {}

    for source in universe:
        source_id = int(source["source_id"])
        result = results.get(source_id)
        category = source.get("current_category") or ""
        effective_url = source.get("current_listing_url") or source.get("website_url") or ""
        duplicate = duplicate_decisions.get(source_id)
        missing_identity = missing_identity_decisions.get(source_id)
        if category == "PROHIBITED_SOURCE" or _is_prohibited_url(effective_url):
            prohibited.append({**source, "reason": source.get("final_exclusion_reason") or "prohibited URL", "classification": "PROHIBITED_SOURCE"})
            assignments[source_id] = "prohibited"
        elif duplicate:
            duplicate_classification = (
                "DUPLICATE_SOURCE_RECORD"
                if duplicate["decision"] == "duplicate_source_record"
                else "MANUAL_REVIEW"
            )
            manual.append({
                **source,
                "reason": duplicate.get("evidence") or duplicate["decision"],
                "classification": duplicate_classification,
            })
            assignments[source_id] = "manual_review"
        elif missing_identity:
            missing_classification = (
                "DUPLICATE_SOURCE_RECORD"
                if missing_identity["decision"] == "duplicate_source_record"
                else "MANUAL_REVIEW"
            )
            manual.append({
                **source,
                "reason": missing_identity.get("evidence") or missing_identity["decision"],
                "classification": missing_classification,
            })
            assignments[source_id] = "manual_review"
        elif result and (result.get("final_status") or "") in RESULT_EXTERNAL_FINAL:
            status = result.get("final_status") or ""
            classification = RESULT_EXTERNAL_FINAL[status]
            external.append({
                **source,
                "reason": result.get("error_detail_short") or status,
                "classification": classification,
            })
            assignments[source_id] = "external_blocked"
        elif result and (result.get("final_status") or "") in SUCCESS_STATUSES:
            family = _recovery_family(source)
            families[family].append(_manifest_row(
                source,
                family,
                f"current HTTP diagnostic={result.get('final_status')}; properties_parsed={result.get('properties_parsed')}",
            ))
            assignments[source_id] = family
        elif category in {"SUCCESS_NEW", "SUCCESS_NO_NEW"} and _truth(source.get("final_eligible")):
            family = "ready_existing"
            families[family].append(_manifest_row(
                source,
                family,
                f"prior productive coverage; category={category}; run_b={source.get('run_b_status')}",
            ))
            assignments[source_id] = family
        elif category in {
            "DOMAIN_DOWN", "SOURCE_GONE", "CAPTCHA", "ANTI_BOT", "AUTH_REQUIRED",
            "REMOTE_HTTP_ERROR", "SSL_EXTERNAL", "DNS_EXTERNAL", "DATA_QUALITY_EXTERNAL",
            "SUCCESS_EXTERNAL_EMPTY", "MISSING_WEBSITE", "MISSING_LISTING_URL_UNRECOVERABLE",
        }:
            external.append({**source, "reason": source.get("final_exclusion_reason"), "classification": category})
            assignments[source_id] = "external_blocked"
        elif category in {"MANUAL_REVIEW", "DUPLICATE_SOURCE_RECORD"}:
            manual.append({**source, "reason": source.get("final_exclusion_reason"), "classification": category})
            assignments[source_id] = "manual_review"
        else:
            gap = _gap_family(result, source)
            internal_gaps.append({
                **source,
                "gap_family": gap,
                "current_http_status": (result or {}).get("final_status") or "not_run",
                "http_status": (result or {}).get("http_status") or "",
                "error_detail": (result or {}).get("error_detail_short") or source.get("last_error") or "",
                "recommended_action": (result or {}).get("recommended_next_action") or f"fix_{gap}",
            })
            assignments[source_id] = "internal_gap"

    all_eligible = [row for rows in families.values() for row in rows]
    assigned_ids = list(assignments)
    if len(assigned_ids) != 7004 or len(set(assigned_ids)) != 7004:
        raise RuntimeError("Every source must have exactly one manifest assignment")
    if len({int(row["source_id"]) for row in all_eligible}) != len(all_eligible):
        raise RuntimeError("Duplicate source_id in eligible manifests")

    _write(args.out / "manifest_ready_existing.csv", families["ready_existing"], MANIFEST_FIELDS)
    _write(args.out / "manifest_recovered_url.csv", families["recovered_url"], MANIFEST_FIELDS)
    _write(args.out / "manifest_recovered_parser.csv", families["recovered_parser"], MANIFEST_FIELDS)
    _write(args.out / "manifest_recovered_strategy.csv", families["recovered_strategy"], MANIFEST_FIELDS)
    _write(args.out / "manifest_recovered_playwright.csv", families["recovered_playwright"], MANIFEST_FIELDS)
    _write(args.out / "manifest_recovered_config.csv", families["recovered_config"], MANIFEST_FIELDS)
    _write(args.out / "manifest_final_all_eligible.csv", sorted(all_eligible, key=lambda row: int(row["source_id"])), MANIFEST_FIELDS)
    extra_fields = tuple(universe[0].keys()) + ("reason", "classification")
    _write(args.out / "manifest_manual_review.csv", manual, extra_fields)
    _write(args.out / "manifest_external_blocked.csv", external, extra_fields)
    _write(args.out / "manifest_prohibited.csv", prohibited, extra_fields)
    gap_fields = tuple(universe[0].keys()) + (
        "gap_family", "current_http_status", "http_status", "error_detail", "recommended_action",
    )
    _write(args.out / "manifest_internal_gaps.csv", internal_gaps, gap_fields)

    counts = {
        **{family: len(rows) for family, rows in families.items()},
        "eligible_total": len(all_eligible),
        "internal_gaps": len(internal_gaps),
        "manual_review": len(manual),
        "external_blocked": len(external),
        "prohibited": len(prohibited),
    }
    if sum(counts[key] for key in ("eligible_total", "internal_gaps", "manual_review", "external_blocked", "prohibited")) != 7004:
        raise RuntimeError("Final manifest partition does not sum to 7004")
    gap_counts = Counter(row["gap_family"] for row in internal_gaps)
    args.out.joinpath("manifest_partition_summary.md").write_text(
        "# Full 7004 manifest partition\n\n"
        + "\n".join(f"- {key}: {value}" for key, value in counts.items())
        + "\n\n## Internal gaps\n\n"
        + "\n".join(f"- {key}: {value}" for key, value in sorted(gap_counts.items()))
        + "\n\n- Missing assignments: 0\n- Duplicate assignments: 0\n",
        encoding="utf-8",
    )
    print(json.dumps({**counts, "gap_families": dict(gap_counts)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
