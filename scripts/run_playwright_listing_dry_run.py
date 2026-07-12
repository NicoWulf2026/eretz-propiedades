#!/usr/bin/env python3
"""Playwright listing-only confirmation for failed HTTP dry-run sources."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPER_DIR = REPO_ROOT / "scraper"
SCRIPTS_DIR = REPO_ROOT / "scripts"
for path in (SCRAPER_DIR, SCRIPTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from playwright.sync_api import sync_playwright  # noqa: E402
from run_autonomous_manifest_dry_run import _parse_isolated, _sanitize  # noqa: E402
from run import BROWSER_ARGS, BROWSER_UA  # noqa: E402


DEFAULT_INPUT = REPO_ROOT / "_scratch" / "codex_autonomous_scraping" / "dry_run_sources.csv"
DEFAULT_OUT = REPO_ROOT / "_scratch" / "codex_autonomous_scraping"
FIELDS = [
    "run_id", "source_id", "inmobiliaria_id", "nombre", "url", "started_at",
    "finished_at", "duration_s", "status", "classification", "http_status",
    "final_url", "cards", "property_links", "error_type", "error_sanitized",
    "retryable", "html_size", "anchor_count", "iframe_count",
    "property_signal_count", "db_writes",
]


def _read(path: Path) -> List[Dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write(path: Path, rows: List[Dict[str, Any]]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: int(row["source_id"])))
    temp.replace(path)


def _check(row: Dict[str, str], timeout_ms: int, run_id: str) -> Dict[str, Any]:
    started = datetime.now(timezone.utc)
    result: Dict[str, Any] = {
        "run_id": run_id,
        "source_id": row["source_id"],
        "inmobiliaria_id": row["inmobiliaria_id"],
        "nombre": row["nombre"],
        "url": row["url"],
        "started_at": started.isoformat(),
        "status": "INTERNAL_ERROR",
        "classification": "INTERNAL_RETRYABLE",
        "http_status": "",
        "final_url": "",
        "cards": 0,
        "property_links": 0,
        "error_type": "",
        "error_sanitized": "",
        "retryable": True,
        "html_size": 0,
        "anchor_count": 0,
        "iframe_count": 0,
        "property_signal_count": 0,
        "db_writes": 0,
    }
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=BROWSER_ARGS)
            try:
                context = browser.new_context(
                    user_agent=BROWSER_UA,
                    viewport={"width": 1366, "height": 768},
                    locale="es-AR",
                )
                page = context.new_page()
                response = page.goto(row["url"], wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(1500)
                for _ in range(3):
                    try:
                        page.evaluate(
                            "window.scrollTo(0, document.body ? document.body.scrollHeight : 0)"
                        )
                        page.wait_for_timeout(500)
                    except Exception as exc:
                        if "context was destroyed" in str(exc).lower():
                            page.wait_for_timeout(750)
                            continue
                        raise
                html = page.content()
                result["html_size"] = len(html)
                result["anchor_count"] = page.locator("a").count()
                result["iframe_count"] = max(0, len(page.frames) - 1)
                result["http_status"] = response.status if response else ""
                result["final_url"] = page.url
                body_lower = html[:200_000].lower()
                signal_patterns = (
                    r"\bventa\b", r"\balquiler\b", r"\bpropiedad(?:es)?\b",
                    r"\binmueble(?:s)?\b", r"\b(?:usd|u\$s)\b", r"\$\s*\d",
                    r"\b(?:dormitorios?|ambientes?|m2|m²)\b",
                )
                result["property_signal_count"] = sum(
                    len(re.findall(pattern, body_lower, flags=re.IGNORECASE))
                    for pattern in signal_patterns
                )
                if result["http_status"] in {401, 407}:
                    result.update(status="AUTH_REQUIRED", classification="EXTERNAL", error_type="auth_required", retryable=False)
                elif result["http_status"] in {403, 429} and any(token in body_lower for token in ("captcha", "cloudflare", "access denied")):
                    result.update(status="ANTI_BOT", classification="EXTERNAL", error_type="antibot", retryable=False)
                elif isinstance(result["http_status"], int) and result["http_status"] >= 400:
                    result.update(
                        status="REMOTE_HTTP_ERROR",
                        classification="EXTERNAL_RETRYABLE",
                        error_type=f"http_{result['http_status']}",
                    )
                else:
                    base = f"{urlparse(page.url).scheme}://{urlparse(page.url).netloc}"
                    try:
                        cards, links = _parse_isolated(html[:2_000_000], base, row["source_id"])
                        if links == 0 and len(page.frames) > 1:
                            for frame in page.frames[1:]:
                                try:
                                    frame_html = frame.content()
                                    frame_cards, frame_links = _parse_isolated(
                                        frame_html[:2_000_000], base, row["source_id"]
                                    )
                                except Exception:
                                    continue
                                cards += frame_cards
                                links += frame_links
                    except TimeoutError:
                        result.update(status="PARSER_ERROR", classification="INTERNAL_CORRECTABLE", error_type="parse_timeout")
                    except Exception as exc:
                        result.update(status="PARSER_ERROR", classification="INTERNAL_CORRECTABLE", error_type="parse_exception", error_sanitized=_sanitize(exc))
                    else:
                        result["cards"] = cards
                        result["property_links"] = links
                        if links:
                            result.update(status="SUCCESS_NO_NEW", classification="DRY_PLAYWRIGHT_OK", retryable=False)
                        elif result["property_signal_count"] < 3:
                            result.update(
                                status="EXTERNAL_EMPTY",
                                classification="EXTERNAL_EMPTY_OR_WRONG_LISTING",
                                error_type="no_inventory_signals",
                                retryable=False,
                            )
                        else:
                            result.update(status="PARSER_ERROR", classification="INTERNAL_CORRECTABLE", error_type="no_property_links")
                context.close()
            finally:
                browser.close()
    except Exception as exc:
        text = str(exc).lower()
        if "timeout" in text or "timed_out" in text:
            result.update(status="TIMEOUT", classification="EXTERNAL_RETRYABLE", error_type="playwright_timeout")
        elif "err_cert" in text or "ssl" in text:
            result.update(status="SSL_ERROR", classification="EXTERNAL", error_type="ssl_error", retryable=False)
        elif any(token in text for token in ("name_not_resolved", "connection_refused", "connection_closed")):
            result.update(status="SOURCE_GONE", classification="EXTERNAL", error_type="navigation_failed", retryable=False)
        else:
            result.update(status="INTERNAL_ERROR", classification="INTERNAL_RETRYABLE", error_type=type(exc).__name__, error_sanitized=_sanitize(exc))
    finished = datetime.now(timezone.utc)
    result["finished_at"] = finished.isoformat()
    result["duration_s"] = round((finished - started).total_seconds(), 2)
    return result


def _summary(path: Path, rows: List[Dict[str, Any]], total: int, run_id: str) -> None:
    counts = Counter(row["status"] for row in rows)
    lines = [
        "# Playwright listing dry-run",
        "",
        f"Run ID: `{run_id}`",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        f"- Sources requiring confirmation: {total}",
        f"- Processed: {len(rows)}",
        f"- Recovered with browser: {counts.get('SUCCESS_NO_NEW', 0)}",
        f"- Remaining parser errors: {counts.get('PARSER_ERROR', 0)}",
        f"- Empty/wrong listing: {counts.get('EXTERNAL_EMPTY', 0)}",
        f"- DB writes: 0",
        "",
        "## Statuses",
        "",
    ]
    lines.extend(f"- {key}: {value}" for key, value in sorted(counts.items()))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--timeout-ms", type=int, default=25_000)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--source-ids", default=None)
    args = parser.parse_args(argv)
    if not 1 <= args.workers <= 2:
        parser.error("--workers must be 1 or 2; MAX_ACTIVE_BROWSERS is 2")
    args.out.mkdir(parents=True, exist_ok=True)
    output = args.out / "playwright_dry_run_sources.csv"
    all_rows = _read(args.input)
    candidates = [row for row in all_rows if row["status"] != "SUCCESS_NO_NEW"]
    if args.source_ids:
        requested = {value.strip() for value in args.source_ids.split(",") if value.strip()}
        candidates = [row for row in candidates if row["source_id"] in requested]
    run_id = f"playwright_dry_run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    results: List[Dict[str, Any]] = []
    if args.resume and output.exists():
        results = _read(output)
        if results:
            run_id = results[0].get("run_id") or run_id
    done = {row["source_id"] for row in results}
    pending = [row for row in candidates if row["source_id"] not in done]
    if args.limit is not None:
        pending = pending[: max(0, args.limit)]
    lock = threading.Lock()
    print(f"run_id={run_id} total={len(candidates)} pending={len(pending)} workers={args.workers} db_writes=0")
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(_check, row, args.timeout_ms, run_id): row for row in pending}
        for index, future in enumerate(as_completed(futures), 1):
            try:
                result = future.result()
            except Exception as exc:
                source = futures[future]
                result = {
                    "run_id": run_id,
                    "source_id": source["source_id"],
                    "inmobiliaria_id": source["inmobiliaria_id"],
                    "nombre": source["nombre"],
                    "url": source["url"],
                    "status": "INTERNAL_ERROR",
                    "classification": "INTERNAL_RETRYABLE",
                    "error_type": type(exc).__name__,
                    "error_sanitized": _sanitize(exc),
                    "retryable": True,
                    "db_writes": 0,
                }
            with lock:
                results.append(result)
                if index % 5 == 0 or index == len(pending):
                    _write(output, results)
                    _summary(args.out / "playwright_dry_run_summary.md", results, len(candidates), run_id)
                    print(f"processed={len(results)}/{len(candidates)} last_status={result['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
