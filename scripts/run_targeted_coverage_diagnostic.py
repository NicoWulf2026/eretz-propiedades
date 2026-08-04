#!/usr/bin/env python3
"""Run a checkpointed HTTP diagnostic for explicitly fixable coverage gaps."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
import traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from psycopg.rows import dict_row

import run_full_coverage_campaign as campaign


ROOT = Path(__file__).resolve().parent.parent
SCRAPER_DIR = ROOT / "scraper"
if str(SCRAPER_DIR) not in sys.path:
    sys.path.insert(0, str(SCRAPER_DIR))
from playwright_scraper import extract_candidate_detail_urls_from_document  # noqa: E402


FIELDS = campaign.FIELDS
append_jsonl = campaign.append_jsonl
build_outputs = campaign.build_outputs
_ORIGINAL_DISCOVER_LINKS = campaign.discover_links


def _safe_discover_links(html: str, base_url: str, max_links: int):
    """Keep malformed remote markup from escaping as an internal error."""
    try:
        links, pages = _ORIGINAL_DISCOVER_LINKS(html, base_url, max_links)
    except (ValueError, UnicodeError):
        cleaned = str(html or "").replace("\x00", "").encode(
            "utf-8", errors="replace"
        ).decode("utf-8", errors="replace")
        try:
            links, pages = _ORIGINAL_DISCOVER_LINKS(cleaned, base_url, max_links)
        except Exception:
            links, pages = [], []

    # The production parser owns the guarded relative/data/onclick/query URL
    # heuristics. Reusing it keeps this diagnostic aligned with Pipeline A.
    try:
        soup = BeautifulSoup(str(html or ""), "html.parser")
        seen = set(links)
        for candidate, _text in extract_candidate_detail_urls_from_document(soup, base_url):
            if candidate in seen:
                continue
            seen.add(candidate)
            links.append(candidate)
            if len(links) >= max_links:
                break
    except (ValueError, UnicodeError):
        pass
    return links[:max_links], pages


campaign.discover_links = _safe_discover_links
_ORIGINAL_PROCESS_HTTP = campaign.process_http


def process_http(source, config, run_id):
    record = _ORIGINAL_PROCESS_HTTP(source, config, run_id)
    error = str(record.get("error_subcategory") or record.get("error_detail_short") or "")
    if record.get("final_status") == "unexpected_error" and "ChunkedEncodingError" in error:
        record["final_status"] = "http_error"
        record["error_category"] = "http_error"
        record["error_subcategory"] = "chunked_encoding_error"
        record["recommended_fix_family"] = "infra"
        record["recommended_next_action"] = "retry_later"
    return record


DEFAULT_UNIVERSE = ROOT / "_scratch/codex_full_7004_coverage/source_universe_7004.csv"
DEFAULT_OUT = ROOT / "_scratch/codex_full_7004_coverage/current_http_diagnostic"


def _truth(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "si"}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _load_done(path: Path) -> set[int]:
    done: set[int] = set()
    if not path.exists():
        return done
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                done.add(int(json.loads(line)["source_id"]))
            except (ValueError, KeyError, json.JSONDecodeError):
                continue
    return done


def _load_sources(source_ids: list[int]) -> tuple[list[dict[str, Any]], str]:
    load_dotenv(ROOT / ".env", override=False)
    db_urls = [
        value for value in (
            os.getenv("SUPABASE_DATABASE_URL", ""),
            os.getenv("INTERNAL_DB_URL", ""),
        ) if value
    ]
    for db_url in dict.fromkeys(db_urls):
        try:
            with psycopg.connect(db_url, row_factory=dict_row, connect_timeout=20) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SET TRANSACTION READ ONLY")
                    cursor.execute(
                        """
                        SELECT id, nombre, web, url_listado, provincia, ciudad, cms_detectado,
                               estrategia_scraping, diagnostic_status, scraping_readiness,
                               exclude_from_scraping, coalesce(total_propiedades, 0) AS total_propiedades
                        FROM public.inmobiliarias_main
                        WHERE id = ANY(%s)
                        ORDER BY id
                        """,
                        (source_ids,),
                    )
                    sources = [dict(row) for row in cursor.fetchall()]
                    cursor.execute(
                        """
                        SELECT md5(coalesce(string_agg(
                            id || coalesce(sitio_activo::text, '') || coalesce(cms_detectado, '') ||
                            coalesce(estrategia_scraping, '') || coalesce(url_listado, '') ||
                            coalesce(diagnostic_status, '') || coalesce(scraping_readiness, '') ||
                            coalesce(exclude_from_scraping::text, ''), ',' ORDER BY id
                        ), '')) AS checksum
                        FROM public.inmobiliarias_main
                        WHERE id = ANY(%s)
                        """,
                        (source_ids,),
                    )
                    checksum = cursor.fetchone()["checksum"]
            if len(sources) != len(source_ids):
                raise RuntimeError(f"DB source count drift: {len(sources)} != {len(source_ids)}")
            return sources, checksum
        except psycopg.Error:
            continue
    return _load_sources_rest(source_ids)


def _load_sources_rest(source_ids: list[int]) -> tuple[list[dict[str, Any]], str]:
    base_url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
        or ""
    )
    if not base_url or not key:
        raise RuntimeError("No read-only Supabase fallback is configured")
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    fields = (
        "id,nombre,web,url_listado,provincia,ciudad,cms_detectado,estrategia_scraping,"
        "diagnostic_status,scraping_readiness,exclude_from_scraping,total_propiedades,"
        "sitio_activo"
    )
    all_rows: list[dict[str, Any]] = []
    session = requests.Session()
    # Fetch only the requested rows. Pulling all agencies made small retry
    # manifests depend on a much larger REST response than necessary.
    for start in range(0, len(source_ids), 100):
        batch = source_ids[start:start + 100]
        last_error: requests.RequestException | None = None
        for attempt in range(3):
            try:
                response = session.get(
                    f"{base_url}/rest/v1/inmobiliarias_main",
                    params={
                        "select": fields,
                        "id": f"in.({','.join(str(value) for value in batch)})",
                        "order": "id.asc",
                    },
                    headers=headers,
                    timeout=(20, 45),
                )
                response.raise_for_status()
                all_rows.extend(response.json())
                last_error = None
                break
            except requests.RequestException as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(attempt + 1)
        if last_error is not None:
            raise RuntimeError(
                f"REST source batch failed after bounded retries: "
                f"offset={start} size={len(batch)}"
            ) from last_error
    selected = set(source_ids)
    sources = [row for row in all_rows if int(row["id"]) in selected]
    sources.sort(key=lambda row: int(row["id"]))
    if len(sources) != len(source_ids):
        raise RuntimeError(f"REST source count drift: {len(sources)} != {len(source_ids)}")
    checksum_payload = ",".join(
        str(row.get("id") or "")
        + str(row.get("sitio_activo") or "")
        + str(row.get("cms_detectado") or "")
        + str(row.get("estrategia_scraping") or "")
        + str(row.get("url_listado") or "")
        + str(row.get("diagnostic_status") or "")
        + str(row.get("scraping_readiness") or "")
        + str(row.get("exclude_from_scraping") or "")
        for row in sources
    )
    checksum = hashlib.md5(checksum_payload.encode("utf-8"), usedforsecurity=False).hexdigest()
    for row in sources:
        row["total_propiedades"] = row.get("total_propiedades") or 0
    return sources, checksum


def _current_checksum(source_ids: list[int]) -> str:
    _, checksum = _load_sources(source_ids)
    return checksum


def _apply_source_overrides(
    sources: list[dict[str, Any]], overrides: list[dict[str, str]]
) -> list[dict[str, Any]]:
    by_id = {int(row["source_id"]): row for row in overrides}
    if len(by_id) != len(overrides):
        raise RuntimeError("Duplicate source_id in source overrides")
    output = []
    for source in sources:
        row = dict(source)
        override = by_id.get(int(row["id"]))
        if override:
            if override.get("website_url"):
                row["web"] = override["website_url"]
            if override.get("listing_url"):
                row["url_listado"] = override["listing_url"]
        output.append(row)
    return output


def _selection(rows: list[dict[str, str]], selection: str, limit: int) -> list[int]:
    if selection == "internal":
        selected = [
            int(row["source_id"])
            for row in rows
            if _truth(row.get("internally_fixable"))
            and not _truth(row.get("exclude_from_scraping"))
            and row.get("current_category") == "INTERNAL_ERROR"
        ]
    elif selection == "external_retryable":
        selected = [
            int(row["source_id"])
            for row in rows
            if row.get("current_category") == "REMOTE_HTTP_ERROR"
            and not _truth(row.get("exclude_from_scraping"))
        ]
    else:
        raise RuntimeError(f"Unsupported selection: {selection}")
    if len(selected) != len(set(selected)):
        raise RuntimeError("Duplicate source_id in selected universe")
    return selected[:limit] if limit else selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-universe", type=Path, default=DEFAULT_UNIVERSE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--selection", choices=("internal", "external_retryable"), default="internal")
    parser.add_argument("--source-ids", default="")
    parser.add_argument("--source-ids-file", type=Path)
    parser.add_argument("--source-overrides", type=Path)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--timeout-connect", type=int, default=5)
    parser.add_argument("--timeout-page", type=int, default=12)
    parser.add_argument("--timeout-property", type=int, default=10)
    parser.add_argument("--max-items", type=int, default=5)
    parser.add_argument("--max-pages", type=int, default=2)
    parser.add_argument("--max-links", type=int, default=300)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--offline-finalize", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.workers <= 12:
        raise RuntimeError("HTTP workers must be between 1 and 12")
    args.out.mkdir(parents=True, exist_ok=True)

    universe_rows = _read_csv(args.source_universe)
    if args.source_ids_file:
        file_rows = _read_csv(args.source_ids_file)
        selected_ids = [int(row["source_id"]) for row in file_rows]
        if len(selected_ids) != len(set(selected_ids)):
            raise RuntimeError("Duplicate source_id in --source-ids-file")
        if args.limit:
            selected_ids = selected_ids[:args.limit]
    elif args.source_ids:
        selected_ids = [int(value.strip()) for value in args.source_ids.split(",") if value.strip()]
        if len(selected_ids) != len(set(selected_ids)):
            raise RuntimeError("Duplicate source_id in --source-ids")
        if args.limit:
            selected_ids = selected_ids[:args.limit]
    else:
        selected_ids = _selection(universe_rows, args.selection, args.limit)
    if args.offline_finalize:
        by_id = {int(row["source_id"]): row for row in universe_rows}
        sources = [
            {
                "id": source_id,
                "nombre": by_id[source_id].get("nombre") or "",
                "web": by_id[source_id].get("website_url") or "",
                "url_listado": by_id[source_id].get("current_listing_url") or "",
                "provincia": "",
                "ciudad": "",
                "cms_detectado": by_id[source_id].get("cms_detectado") or "",
                "estrategia_scraping": by_id[source_id].get("estrategia_scraping") or "",
                "diagnostic_status": by_id[source_id].get("diagnostic_status") or "",
                "scraping_readiness": by_id[source_id].get("scraping_readiness") or "",
                "exclude_from_scraping": _truth(by_id[source_id].get("exclude_from_scraping")),
                "total_propiedades": int(by_id[source_id].get("properties_count") or 0),
            }
            for source_id in selected_ids
        ]
        checksum_before = "offline_verification_pending"
    else:
        sources, checksum_before = _load_sources(selected_ids)
    if args.source_overrides:
        sources = _apply_source_overrides(sources, _read_csv(args.source_overrides))
    jsonl = args.out / "source_results.jsonl"
    done = _load_done(jsonl) if args.resume else set()
    if not args.resume and jsonl.exists():
        raise RuntimeError("Output checkpoint already exists; pass --resume or choose a new --out")
    pending = [source for source in sources if int(source["id"]) not in done]
    run_id = f"FULL_7004_TARGETED_HTTP_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    config = {
        "ct": args.timeout_connect,
        "pt": args.timeout_page,
        "prop_t": args.timeout_property,
        "max_items": args.max_items,
        "max_pages": args.max_pages,
        "max_links": args.max_links,
    }
    (args.out / "pid.txt").write_text(str(os.getpid()) + "\n", encoding="utf-8")
    (args.out / "run_config.json").write_text(json.dumps({
        "run_id": run_id,
        "selected": len(selected_ids),
        "already_done": len(done),
        "pending": len(pending),
        "workers": args.workers,
        "selection": args.selection,
        "timeouts": config,
        "db_writes": 0,
        "pipeline": "diagnostic_http_only",
    }, indent=2), encoding="utf-8")
    print(f"[targeted] selected={len(selected_ids)} done={len(done)} pending={len(pending)} workers={args.workers}", flush=True)

    counts: Counter[str] = Counter()
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_http, source, config, run_id): source for source in pending}
        for future in as_completed(futures):
            source = futures[future]
            try:
                record = future.result()
            except Exception as exc:
                record = {field: None for field in FIELDS}
                record.update({
                    "campaign_run_id": run_id,
                    "source_id": source["id"],
                    "source_name": source.get("nombre"),
                    "website_url": source.get("web"),
                    "listing_url": source.get("url_listado"),
                    "attempted": True,
                    "skipped": False,
                    "final_status": "unexpected_error",
                    "error_category": "unexpected_error",
                    "error_detail_short": type(exc).__name__,
                    "stack_trace_or_exception": traceback.format_exc()[:500],
                    "recommended_fix_family": "internal",
                    "recommended_next_action": "fix_internal_error",
                })
            append_jsonl(jsonl, record)
            counts[str(record.get("final_status") or "unknown")] += 1
            processed = len(done) + sum(counts.values())
            if processed % 25 == 0 or processed == len(selected_ids):
                elapsed = max(time.monotonic() - started, 0.1)
                progress = {
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "processed": processed,
                    "total": len(selected_ids),
                    "pending": len(selected_ids) - processed,
                    "rate_per_s": round(sum(counts.values()) / elapsed, 3),
                    "by_status_current_session": dict(counts),
                    "db_writes": 0,
                }
                (args.out / "progress.json").write_text(json.dumps(progress, indent=2), encoding="utf-8")
                print(f"[targeted] {processed}/{len(selected_ids)} {dict(counts.most_common(8))}", flush=True)

    classification_unchanged: bool | None
    if args.offline_finalize:
        classification_unchanged = None
    else:
        if _current_checksum(selected_ids) != checksum_before:
            raise RuntimeError("Agency configuration changed during read-only diagnostic")
        classification_unchanged = True
    build_outputs(args.out)
    checkpoint_counts: Counter[str] = Counter()
    with jsonl.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                checkpoint_counts[str(json.loads(line).get("final_status") or "unknown")] += 1
            except json.JSONDecodeError:
                continue
    (args.out / "completed.json").write_text(json.dumps({
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "sources": len(selected_ids),
        "status": dict(checkpoint_counts),
        "db_writes": 0,
        "classification_unchanged": classification_unchanged,
        "classification_verification_pending": classification_unchanged is None,
    }, indent=2), encoding="utf-8")
    print(f"[targeted] complete sources={len(selected_ids)} status={dict(counts)} db_writes=0", flush=True)
    return 0


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
