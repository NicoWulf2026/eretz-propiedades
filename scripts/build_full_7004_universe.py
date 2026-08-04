#!/usr/bin/env python3
"""Build the current 7004-source truth and reconcile prior run coverage."""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "_scratch/codex_full_7004_coverage"
PREVIOUS = ROOT / "_scratch/codex_autonomous_scraping"
PROHIBITED = ("zonaprop.com", "argenprop.com", "properati.com")
FIELDS = (
    "source_id", "inmobiliaria_id", "nombre", "website_url", "current_listing_url",
    "activa", "sitio_activo", "exclude_from_scraping", "exclude_reason",
    "diagnostic_status", "scraping_readiness", "cms_detectado", "estrategia_scraping",
    "requires_playwright", "in_previous_manifest", "run_a_status", "run_b_status",
    "last_success", "last_error", "properties_count", "url_status", "domain_status",
    "fk_status", "parser_status", "strategy_status", "playwright_status",
    "current_category", "internally_fixable", "externally_blocked", "final_eligible",
    "final_exclusion_reason", "coverage_status", "classification_evidence",
)


def _load_db_url() -> str:
    load_dotenv(ROOT / ".env", override=False)
    value = os.getenv("SUPABASE_DATABASE_URL", "") or os.getenv("INTERNAL_DB_URL", "")
    if not value:
        raise RuntimeError("INTERNAL_DB_URL is not configured")
    return value


def _read(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _by_id(rows: list[dict[str, str]]) -> dict[int, dict[str, str]]:
    result: dict[int, dict[str, str]] = {}
    for row in rows:
        raw = row.get("source_id") or row.get("inmobiliaria_id")
        if raw:
            result[int(raw)] = row
    return result


def _write(path: Path, rows: list[dict[str, Any]], fields: tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _truth(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "si"}


def _domain(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = urlparse(text if "://" in text else "https://" + text)
        return parsed.netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _is_prohibited(*values: Any) -> bool:
    domains = [_domain(value) for value in values]
    return any(blocked in domain for domain in domains for blocked in PROHIBITED)


def _success_status(status: str) -> bool:
    return status.startswith("SUCCESS")


def _category_from_exclusion(row: dict[str, str]) -> str:
    classification = (row.get("classification") or "").upper()
    reason = (row.get("reason") or "").lower()
    if "SOURCE_GONE" in classification:
        return "SOURCE_GONE"
    if "SSL" in classification:
        return "SSL_EXTERNAL"
    if "EMPTY" in classification or "empty" in reason or "sin inventario" in reason:
        return "SUCCESS_EXTERNAL_EMPTY"
    if "AUTH" in classification:
        return "AUTH_REQUIRED"
    if "CAPTCHA" in classification:
        return "CAPTCHA"
    if "ANTI" in classification:
        return "ANTI_BOT"
    return "REMOTE_HTTP_ERROR"


def _fetch_db() -> tuple[list[dict[str, Any]], dict[int, int]]:
    with psycopg.connect(_load_db_url(), row_factory=dict_row, connect_timeout=60) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute(
                """
                SELECT id, nombre, web, url_listado, activa, sitio_activo,
                       exclude_from_scraping, exclude_reason, diagnostic_status,
                       scraping_readiness, cms_detectado, estrategia_scraping,
                       ultimo_scraping
                FROM public.inmobiliarias_main
                ORDER BY id
                """
            )
            agencies = [dict(row) for row in cursor.fetchall()]
            cursor.execute(
                "SELECT inmobiliaria_id, count(*)::int AS n FROM public.propiedades "
                "WHERE inmobiliaria_id IS NOT NULL GROUP BY inmobiliaria_id"
            )
            counts = {int(row["inmobiliaria_id"]): row["n"] for row in cursor.fetchall()}
    return agencies, counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    full_diag = _by_id(_read(ROOT / "_scratch/full_scrape_coverage_7004/source_results.csv"))
    url_validation = _by_id(_read(ROOT / "_scratch/url_listing_post_update_validation/post_update_validation_results.csv"))
    manifest = _by_id(_read(PREVIOUS / "general_manifest_final.csv"))
    exclusions = _by_id(_read(PREVIOUS / "general_manifest_exclusions.csv"))
    run_a = _by_id(_read(PREVIOUS / "general_run_A_20260712/source_results.csv"))
    run_b = _by_id(_read(PREVIOUS / "general_run_B_20260715_v2/source_results.csv"))
    run_b_retry = _by_id(_read(PREVIOUS / "run_b_internal_retry/source_results.csv"))
    final_internal = _by_id(_read(PREVIOUS / "run_b_final_internal_classification.csv"))
    agencies, property_counts = _fetch_db()

    if len(agencies) != 7004:
        raise RuntimeError(f"Expected current universe of 7004, found {len(agencies)}")
    if len(full_diag) != len(agencies):
        raise RuntimeError(f"Historical diagnostic coverage drift: {len(full_diag)} != {len(agencies)}")

    output: list[dict[str, Any]] = []
    for agency in agencies:
        source_id = int(agency["id"])
        diag = full_diag.get(source_id, {})
        url_fix = url_validation.get(source_id, {})
        a = run_a.get(source_id, {})
        b = run_b.get(source_id, {})
        retry = run_b_retry.get(source_id, {})
        closed = final_internal.get(source_id, {})
        exclusion = exclusions.get(source_id, {})
        website = str(agency.get("web") or diag.get("website_url") or "").strip()
        listing = str(agency.get("url_listado") or "").strip()
        effective = listing or website
        prohibited = _is_prohibited(website, listing) or agency.get("diagnostic_status") == "prohibited_source"
        missing_website = not website and not listing
        excluded = bool(agency.get("exclude_from_scraping"))
        diagnostic_status = str(agency.get("diagnostic_status") or "")
        readiness = str(agency.get("scraping_readiness") or "")
        latest = retry or b
        latest_status = str(latest.get("status") or "")
        latest_new = int(latest.get("new_properties") or 0)

        coverage_status = "NEVER_EXECUTED_PRODUCTIVELY"
        category = "INTERNAL_ERROR"
        internally_fixable = False
        externally_blocked = False
        eligible = False
        exclusion_reason = ""
        evidence = ""

        if prohibited:
            category = "PROHIBITED_SOURCE"
            externally_blocked = True
            exclusion_reason = agency.get("exclude_reason") or "prohibited portal/source"
            evidence = f"DB diagnostic={diagnostic_status}; prohibited domain rule"
        elif missing_website:
            category = "MISSING_WEBSITE"
            externally_blocked = True
            exclusion_reason = agency.get("exclude_reason") or "no website or listing URL"
            evidence = f"DB diagnostic={diagnostic_status}; empty web and url_listado"
        elif diagnostic_status == "domain_down" and excluded:
            category = "DOMAIN_DOWN"
            externally_blocked = True
            exclusion_reason = agency.get("exclude_reason") or "confirmed domain down"
            evidence = "DB diagnostic_status=domain_down and exclude_from_scraping=true"
        elif source_id in run_b:
            coverage_status = "EXECUTED_RUN_B"
            if closed.get("final_classification") == "EXTERNAL_FINAL":
                category = "SUCCESS_EXTERNAL_EMPTY"
                externally_blocked = True
                exclusion_reason = closed.get("evidence") or "external empty"
                evidence = "Run B internal retry closed as EXTERNAL_FINAL"
            elif _success_status(latest_status):
                category = "SUCCESS_NEW" if latest_new > 0 else "SUCCESS_NO_NEW"
                eligible = True
                evidence = f"latest productive status={latest_status}; new_properties={latest_new}"
            elif str(latest.get("classification")) == "EXTERNAL_FINAL":
                category = "DATA_QUALITY_EXTERNAL"
                externally_blocked = True
                exclusion_reason = latest.get("error_type") or latest_status
                evidence = "Run B external final"
            elif str(latest.get("classification")) == "EXTERNAL_RETRYABLE":
                category = "REMOTE_HTTP_ERROR"
                internally_fixable = False
                externally_blocked = True
                exclusion_reason = latest.get("error_type") or latest_status
                evidence = "Run B external retryable; requires fresh validation"
            else:
                category = "INTERNAL_ERROR"
                internally_fixable = True
                eligible = True
                exclusion_reason = latest.get("error_type") or latest_status
                evidence = "Run B result not yet externally proven or internally closed"
        elif source_id in exclusion:
            coverage_status = "VALIDATED_NOT_EXECUTED"
            category = _category_from_exclusion(exclusion)
            externally_blocked = True
            exclusion_reason = exclusion.get("reason") or exclusion.get("classification") or "validated exclusion"
            evidence = exclusion.get("evidence") or "general_manifest_exclusions.csv"
        elif source_id in run_a:
            coverage_status = "EXECUTED_RUN_A_ONLY"
            if _success_status(str(a.get("status") or "")):
                category = "SUCCESS_NEW" if int(a.get("new_properties") or 0) else "SUCCESS_NO_NEW"
                eligible = True
            else:
                category = "INTERNAL_ERROR"
                internally_fixable = True
                eligible = True
            evidence = "Run A only; omitted from Run B"
        elif excluded:
            if diagnostic_status == "missing_url":
                category = "MISSING_WEBSITE" if missing_website else "MISSING_LISTING_URL_UNRECOVERABLE"
            elif diagnostic_status == "manual_review":
                category = "MANUAL_REVIEW"
            else:
                category = "DATA_QUALITY_EXTERNAL"
            externally_blocked = True
            exclusion_reason = agency.get("exclude_reason") or diagnostic_status or "excluded in DB"
            evidence = "DB exclusion state"
        else:
            coverage_status = "READY_BUT_NOT_EXECUTED"
            category = "INTERNAL_ERROR"
            internally_fixable = True
            eligible = bool(effective and agency.get("sitio_activo") and readiness == "ready_now")
            exclusion_reason = diagnostic_status or "not included in previous manifest"
            evidence = (
                f"DB readiness={readiness}; historical final={diag.get('final_status','')}; "
                f"URL validation={url_fix.get('new_status','')}"
            )

        if not category:
            raise RuntimeError(f"Source {source_id} has no category")
        url_status = "missing" if not effective else (
            "prohibited" if prohibited else
            "listing_present" if listing else "website_only_needs_listing_validation"
        )
        domain_status = "down" if diagnostic_status == "domain_down" else (
            "active" if agency.get("sitio_activo") else "inactive_or_unverified"
        )
        requires_playwright = _truth(diag.get("requires_playwright")) or _truth(url_fix.get("needs_playwright")) or _truth(manifest.get(source_id, {}).get("needs_playwright"))
        row = {
            "source_id": source_id,
            "inmobiliaria_id": source_id,
            "nombre": agency.get("nombre") or "",
            "website_url": website,
            "current_listing_url": listing,
            "activa": agency.get("activa"),
            "sitio_activo": agency.get("sitio_activo"),
            "exclude_from_scraping": excluded,
            "exclude_reason": agency.get("exclude_reason") or "",
            "diagnostic_status": diagnostic_status,
            "scraping_readiness": readiness,
            "cms_detectado": agency.get("cms_detectado") or diag.get("cms_detectado") or "",
            "estrategia_scraping": agency.get("estrategia_scraping") or diag.get("estrategia_scraping") or "",
            "requires_playwright": requires_playwright,
            "in_previous_manifest": source_id in manifest,
            "run_a_status": a.get("status") or "",
            "run_b_status": b.get("status") or "",
            "last_success": agency.get("ultimo_scraping") or latest.get("finished_at") or "",
            "last_error": latest.get("error_type") or diag.get("error_category") or "",
            "properties_count": property_counts.get(source_id, 0),
            "url_status": url_status,
            "domain_status": domain_status,
            "fk_status": "canonical_id",
            "parser_status": "needs_fix" if diagnostic_status == "needs_parser" else ("validated" if source_id in run_b else "not_currently_validated"),
            "strategy_status": "needs_fix" if diagnostic_status == "needs_cms_strategy" else ("configured" if agency.get("estrategia_scraping") else "not_configured"),
            "playwright_status": "required" if requires_playwright else "not_required_or_unproven",
            "current_category": category,
            "internally_fixable": internally_fixable,
            "externally_blocked": externally_blocked,
            "final_eligible": eligible,
            "final_exclusion_reason": exclusion_reason,
            "coverage_status": coverage_status,
            "classification_evidence": evidence,
        }
        output.append(row)

    if len(output) != len(agencies) or len({row["source_id"] for row in output}) != len(output):
        raise RuntimeError("Universe cardinality or source_id uniqueness failed")
    if any(not row["current_category"] or not row["coverage_status"] for row in output):
        raise RuntimeError("Unclassified source found")

    _write(args.out / "source_universe_7004.csv", output, FIELDS)
    reconciliation_fields = (
        "source_id", "nombre", "diagnostic_status", "scraping_readiness",
        "in_previous_manifest", "run_a_status", "run_b_status", "coverage_status",
        "current_category", "internally_fixable", "externally_blocked", "final_eligible",
        "final_exclusion_reason", "classification_evidence",
    )
    _write(args.out / "coverage_reconciliation.csv", output, reconciliation_fields)

    coverage_counts = Counter(str(row["coverage_status"]) for row in output)
    category_counts = Counter(str(row["current_category"]) for row in output)
    diagnostic_counts = Counter(str(row["diagnostic_status"]) for row in output)
    ready_not_run = [row for row in output if row["coverage_status"] == "READY_BUT_NOT_EXECUTED"]
    lines = [
        "# Coverage reconciliation: 7004 vs previous manifests",
        "",
        f"Generated UTC: {datetime.now(timezone.utc).isoformat()}",
        "",
        f"- Current DB sources: {len(output)}",
        f"- Run A executed: {len(run_a)}",
        f"- Run B executed: {len(run_b)}",
        f"- Never executed productively: {len(output) - len(run_a)}",
        f"- READY_BUT_NOT_EXECUTED: {len(ready_not_run)}",
        f"- Internally fixable now: {sum(bool(row['internally_fixable']) for row in output)}",
        f"- Externally blocked now: {sum(bool(row['externally_blocked']) for row in output)}",
        f"- Initially eligible for current validation: {sum(bool(row['final_eligible']) for row in output)}",
        "- Previous manifest had 1252 sources; Run B executed 1251 because source 3902 "
        "(AL Construcciones) was explicitly removed after Run A returned no valid inventory.",
        "",
        "## Coverage status",
        "",
    ]
    lines.extend(f"- {key}: {value}" for key, value in sorted(coverage_counts.items()))
    lines.extend(["", "## Current category", ""])
    lines.extend(f"- {key}: {value}" for key, value in sorted(category_counts.items()))
    lines.extend(["", "## DB diagnostic status", ""])
    lines.extend(f"- {key}: {value}" for key, value in sorted(diagnostic_counts.items()))
    lines.extend([
        "",
        "## Interpretation",
        "",
        "`INTERNAL_ERROR / READY_BUT_NOT_EXECUTED` is deliberate: it keeps every technically "
        "recoverable source visible until a current diagnostic either recovers it or proves an external block.",
        "No source is silently omitted and this is not the final coverage classification.",
    ])
    args.out.joinpath("coverage_reconciliation_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({
        "sources": len(output),
        "run_a": len(run_a),
        "run_b": len(run_b),
        "ready_but_not_executed": len(ready_not_run),
        "internally_fixable": sum(bool(row["internally_fixable"]) for row in output),
        "unclassified": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
