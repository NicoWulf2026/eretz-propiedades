#!/usr/bin/env python3
"""Read-only source, FK, historical-write and dedup audit for Pipeline A."""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List
from urllib.parse import urlparse

from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = REPO_ROOT / "_scratch" / "preflight_manifest_b" / "manifest_b_candidates.csv"
DEFAULT_RESULTS = REPO_ROOT / "_scratch" / "full_scrape_coverage_7004" / "source_results.csv"
DEFAULT_OUT = REPO_ROOT / "_scratch" / "codex_autonomous_scraping"
PROHIBITED_DOMAINS = {"zonaprop.com", "argenprop.com", "properati.com"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalized(value: Any) -> str:
    text = unicodedata.normalize("NFKD", _text(value))
    return re.sub(r"[^a-z0-9]+", " ", text.encode("ascii", "ignore").decode().lower()).strip()


def _domain(value: Any) -> str:
    try:
        return urlparse(_text(value)).netloc.lower().lstrip("www.")
    except Exception:
        return ""


def _slug(name: Any, source_id: Any) -> str:
    return re.sub(r"[^a-z0-9_]", "_", _text(name).lower())[:40].strip("_") or f"src_{source_id}"


def _compatible(source: Dict[str, Any], candidate: Dict[str, Any]) -> bool:
    source_name = _normalized(source.get("source_name"))
    candidate_name = _normalized(candidate.get("nombre"))
    name_ok = bool(
        source_name and candidate_name
        and (source_name == candidate_name or source_name in candidate_name or candidate_name in source_name)
    )
    source_domain = _domain(source.get("website_url") or source.get("new_url_listado"))
    candidate_domain = _domain(candidate.get("web") or candidate.get("url_listado"))
    domain_ok = bool(
        source_domain and candidate_domain
        and (
            source_domain == candidate_domain
            or source_domain.endswith("." + candidate_domain)
            or candidate_domain.endswith("." + source_domain)
        )
    )
    return name_ok or domain_ok


def _read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: Iterable[Dict[str, Any]], fields: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _load_db_url() -> str:
    load_dotenv(REPO_ROOT / ".env", override=False)
    value = os.getenv("INTERNAL_DB_URL", "")
    if not value:
        raise RuntimeError("INTERNAL_DB_URL is not configured")
    return value


def _fetch_db(conn) -> tuple[List[Dict[str, Any]], Dict[int, Dict[str, Any]], List[Dict[str, Any]]]:
    with conn.cursor() as cursor:
        cursor.execute("SET TRANSACTION READ ONLY")
        cursor.execute(
            """
            SELECT id, nombre, web, url_listado, activa, sitio_activo,
                   cms_detectado, estrategia_scraping, scraping_id_origen,
                   diagnostic_status, scraping_readiness, exclude_from_scraping,
                   exclude_reason, tiene_antibot, ultimo_scraping
            FROM public.inmobiliarias_main
            ORDER BY id
            """
        )
        agencies = list(cursor.fetchall())
        cursor.execute(
            """
            SELECT inmobiliaria_id, count(*) AS property_count,
                   max(created_at) AS last_property_at
            FROM public.propiedades
            GROUP BY inmobiliaria_id
            """
        )
        history = {int(row["inmobiliaria_id"]): row for row in cursor.fetchall() if row["inmobiliaria_id"] is not None}
        cursor.execute(
            """
            SELECT id, inmobiliaria_id, fuente_extraccion, created_at, url
            FROM public.propiedades
            WHERE created_at >= TIMESTAMPTZ '2026-06-28 00:00:00+00'
              AND fuente_extraccion IS NOT NULL
            ORDER BY created_at, id
            """
        )
        recent = list(cursor.fetchall())
    return agencies, history, recent


def _resolve_manifest(
    manifest: List[Dict[str, Any]], agencies: List[Dict[str, Any]]
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    by_id = {str(row["id"]): row for row in agencies}
    by_origin: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in agencies:
        if row.get("scraping_id_origen") is not None:
            by_origin[str(row["scraping_id_origen"])].append(row)

    resolved = []
    audit = []
    for source in manifest:
        sid = _text(source.get("source_id"))
        primary = by_origin.get(sid, [])
        fallback = by_id.get(sid)
        primary_ok = [row for row in primary if _compatible(source, row)]
        fallback_ok = bool(fallback and _compatible(source, fallback))
        collision = bool(primary and fallback and any(row["id"] != fallback["id"] for row in primary))
        selected = None
        status = ""
        if len(primary) > 1:
            status = "ambiguous_scraping_id_origen"
        elif primary and fallback and primary[0]["id"] != fallback["id"]:
            if len(primary_ok) == 1 and not fallback_ok:
                selected, status = primary_ok[0], "primary_compatible"
            elif fallback_ok and not primary_ok:
                selected, status = fallback, "canonical_collision_resolved"
            else:
                status = "ambiguous_collision"
        elif primary or fallback:
            candidate = primary[0] if primary else fallback
            if _compatible(source, candidate):
                selected = candidate
                status = "primary_compatible" if primary else "canonical_fallback"
            else:
                status = "identity_mismatch"
        else:
            status = "missing"

        audit.append({
            "source_id": sid,
            "source_name": source.get("source_name", ""),
            "canonical_id": fallback.get("id", "") if fallback else "",
            "primary_candidate_ids": ";".join(str(row["id"]) for row in primary),
            "resolved_inmobiliaria_id": selected.get("id", "") if selected else "",
            "fk_status": status,
            "collision": collision,
            "eligible": bool(selected),
        })
        if selected:
            resolved.append({
                **source,
                "inmobiliaria_id": selected["id"],
                "fk_status": status,
                "manifest_slug": _slug(source.get("source_name"), sid),
            })
    return resolved, audit


def _audit_prior_writes(
    recent: List[Dict[str, Any]], resolved: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    by_slug: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for source in resolved:
        by_slug[source["manifest_slug"]].append(source)
    aggregate: Dict[tuple, Dict[str, Any]] = {}
    for prop in recent:
        slug = _text(prop.get("fuente_extraccion"))
        candidates = by_slug.get(slug, [])
        if len(candidates) != 1:
            continue
        source = candidates[0]
        expected = int(source["inmobiliaria_id"])
        actual = prop.get("inmobiliaria_id")
        if actual == expected:
            continue
        key = (source["source_id"], actual, expected)
        row = aggregate.setdefault(key, {
            "source_id": source["source_id"],
            "source_name": source.get("source_name", ""),
            "manifest_slug": slug,
            "actual_inmobiliaria_id": actual,
            "expected_inmobiliaria_id": expected,
            "mismatched_properties": 0,
            "first_created_at": prop.get("created_at"),
            "last_created_at": prop.get("created_at"),
            "sample_property_id": prop.get("id"),
            "classification": "historical_fk_mismatch_requires_owner_review",
        })
        row["mismatched_properties"] += 1
        row["last_created_at"] = prop.get("created_at")
    return sorted(aggregate.values(), key=lambda row: -row["mismatched_properties"])


def _dedup_audit(conn) -> List[Dict[str, Any]]:
    checks = [
        ("exact_url_per_source", "inmobiliaria_id, url", "url IS NOT NULL AND url <> ''"),
        ("normalized_url_per_source", "inmobiliaria_id, url_normalizada", "url_normalizada IS NOT NULL AND url_normalizada <> ''"),
        ("hash_dedup", "hash_dedup", "hash_dedup IS NOT NULL AND hash_dedup <> ''"),
    ]
    rows = []
    with conn.cursor() as cursor:
        for check, columns, where in checks:
            cursor.execute(
                f"""
                SELECT count(*) AS duplicate_groups, COALESCE(sum(n - 1), 0) AS excess_rows,
                       COALESCE(max(n), 0) AS largest_group
                FROM (
                    SELECT {columns}, count(*) AS n
                    FROM public.propiedades
                    WHERE {where}
                    GROUP BY {columns}
                    HAVING count(*) > 1
                ) duplicates
                """
            )
            result = cursor.fetchone()
            rows.append({
                "check": check,
                "duplicate_groups": result["duplicate_groups"],
                "excess_rows": result["excess_rows"],
                "largest_group": result["largest_group"],
                "action": "audit_only_no_cleanup",
            })
    return rows


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--source-results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    manifest = _read_csv(args.manifest)
    diagnostic_rows = _read_csv(args.source_results)
    latest_diagnostic = {_text(row.get("source_id")): row for row in diagnostic_rows}

    with psycopg.connect(_load_db_url(), row_factory=dict_row) as conn:
        agencies, history, recent = _fetch_db(conn)
        resolved, fk_rows = _resolve_manifest(manifest, agencies)
        prior_writes = _audit_prior_writes(recent, resolved)
        dedup_rows = _dedup_audit(conn)

    resolved_by_sid = {_text(row["source_id"]): row for row in resolved}
    universe = []
    for agency in agencies:
        sid = str(agency["id"])
        manifest_row = resolved_by_sid.get(sid)
        diag = latest_diagnostic.get(sid, {})
        hist = history.get(int(agency["id"]), {})
        url = agency.get("url_listado") or agency.get("web") or ""
        prohibited = any(domain in _domain(url) for domain in PROHIBITED_DOMAINS)
        excluded = bool(agency.get("exclude_from_scraping")) or prohibited
        external_reason = agency.get("exclude_reason") or agency.get("diagnostic_status") or ""
        technically_fixable = bool(
            agency.get("activa") and agency.get("sitio_activo") and url and not excluded
        )
        universe.append({
            "source_id": sid,
            "inmobiliaria_id": manifest_row.get("inmobiliaria_id", "") if manifest_row else agency["id"],
            "nombre": agency.get("nombre", ""),
            "url": url,
            "activa": agency.get("activa"),
            "en_manifest": bool(manifest_row),
            "pipeline": "A" if manifest_row else "not_scheduled",
            "cms": agency.get("cms_detectado") or diag.get("cms_detectado", ""),
            "http_or_playwright": "playwright_runtime" if manifest_row else "not_validated",
            "fk_status": manifest_row.get("fk_status", "not_in_manifest") if manifest_row else "not_in_manifest",
            "last_success": hist.get("last_property_at") or agency.get("ultimo_scraping") or "",
            "last_error": diag.get("error_category") or diag.get("final_status") or "",
            "eligible": bool(manifest_row),
            "exclusion_reason": "" if manifest_row else external_reason or "not_in_validated_manifest",
            "needs_fix": bool(not manifest_row and technically_fixable),
        })

    universe_fields = [
        "source_id", "inmobiliaria_id", "nombre", "url", "activa", "en_manifest",
        "pipeline", "cms", "http_or_playwright", "fk_status", "last_success",
        "last_error", "eligible", "exclusion_reason", "needs_fix",
    ]
    _write_csv(args.out / "source_universe.csv", universe, universe_fields)
    _write_csv(
        args.out / "fk_audit.csv",
        fk_rows,
        ["source_id", "source_name", "canonical_id", "primary_candidate_ids", "resolved_inmobiliaria_id", "fk_status", "collision", "eligible"],
    )
    _write_csv(
        args.out / "general_manifest_safe.csv",
        resolved,
        list(manifest[0].keys()) + ["inmobiliaria_id", "fk_status", "manifest_slug"],
    )
    _write_csv(
        args.out / "prior_fk_write_audit.csv",
        prior_writes,
        ["source_id", "source_name", "manifest_slug", "actual_inmobiliaria_id", "expected_inmobiliaria_id", "mismatched_properties", "first_created_at", "last_created_at", "sample_property_id", "classification"],
    )
    _write_csv(
        args.out / "dedup_audit.csv",
        dedup_rows,
        ["check", "duplicate_groups", "excess_rows", "largest_group", "action"],
    )

    fk_counts = Counter(row["fk_status"] for row in fk_rows)
    summary = [
        "# Autonomous scraping audit",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        f"- DB sources: {len(agencies)}",
        f"- Manifest candidates: {len(manifest)}",
        f"- FK resolved: {len(resolved)}",
        f"- FK unresolved: {len(manifest) - len(resolved)}",
        f"- Eligible sources: {sum(1 for row in universe if row['eligible'])}",
        f"- Active sources requiring future fix: {sum(1 for row in universe if row['needs_fix'])}",
        f"- Historical FK mismatch groups: {len(prior_writes)}",
        f"- Historical FK mismatch properties: {sum(row['mismatched_properties'] for row in prior_writes)}",
        "",
        "## FK statuses",
        "",
    ]
    summary.extend(f"- {key}: {value}" for key, value in sorted(fk_counts.items()))
    summary.extend(["", "## Dedup", ""])
    summary.extend(
        f"- {row['check']}: groups={row['duplicate_groups']}, excess_rows={row['excess_rows']}, largest={row['largest_group']}"
        for row in dedup_rows
    )
    summary.extend([
        "",
        "## Safety",
        "",
        "- Transaction mode: READ ONLY",
        "- DB writes: 0",
        "- Historical mismatches were not modified.",
    ])
    (args.out / "audit_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print(f"sources={len(agencies)} manifest={len(manifest)} resolved={len(resolved)}")
    print(f"prior_fk_mismatch_properties={sum(row['mismatched_properties'] for row in prior_writes)}")
    print("db_writes=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
