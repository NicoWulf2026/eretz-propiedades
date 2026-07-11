#!/usr/bin/env python3
"""Concurrent, resumable, zero-write parser dry-run for the safe manifest."""

from __future__ import annotations

import argparse
import csv
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

import requests
import urllib3


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPER_DIR = REPO_ROOT / "scraper"
if str(SCRAPER_DIR) not in sys.path:
    sys.path.insert(0, str(SCRAPER_DIR))

from playwright_scraper import parse_cards  # noqa: E402


DEFAULT_INPUT = REPO_ROOT / "_scratch" / "codex_autonomous_scraping" / "general_manifest_safe.csv"
DEFAULT_OUT = REPO_ROOT / "_scratch" / "codex_autonomous_scraping"
FIELDS = [
    "run_id", "source_id", "inmobiliaria_id", "nombre", "url", "started_at",
    "finished_at", "duration_s", "status", "classification", "http_status",
    "final_url", "cards", "property_links", "error_type", "error_sanitized",
    "retryable", "requires_playwright", "db_writes",
]
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _sanitize(value: Any) -> str:
    text = str(value or "")
    text = re.sub(
        r"([?&](?:key|apikey|api_key|token|access_token)=)[^&\s]+",
        r"\1<redacted>",
        text,
        flags=re.IGNORECASE,
    )
    return text[:500]


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


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept-Language": "es-AR,es;q=0.9"})
    return session


def _check(row: Dict[str, str], timeout: float, run_id: str) -> Dict[str, Any]:
    started = datetime.now(timezone.utc)
    result: Dict[str, Any] = {
        "run_id": run_id,
        "source_id": row["source_id"],
        "inmobiliaria_id": row["inmobiliaria_id"],
        "nombre": row["source_name"],
        "url": row.get("new_url_listado") or row.get("old_url_listado") or "",
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
        "requires_playwright": False,
        "db_writes": 0,
    }
    session = _session()
    try:
        response = session.get(result["url"], timeout=timeout, allow_redirects=True, verify=False)
        result["http_status"] = response.status_code
        result["final_url"] = response.url
        body_lower = response.text[:200_000].lower()
        if response.status_code in {401, 407}:
            result.update(status="AUTH_REQUIRED", classification="EXTERNAL", error_type="auth_required", retryable=False)
        elif response.status_code in {403, 429} and any(token in body_lower for token in ("captcha", "cloudflare", "access denied", "forbidden")):
            result.update(status="ANTI_BOT", classification="EXTERNAL", error_type="antibot", retryable=False)
        elif response.status_code >= 400:
            result.update(status="REMOTE_HTTP_ERROR", classification="EXTERNAL_RETRYABLE", error_type=f"http_{response.status_code}")
        else:
            base_url = f"{urlparse(response.url).scheme}://{urlparse(response.url).netloc}"
            try:
                properties = parse_cards(response.text, None, f"dry_{row['source_id']}", base_url, "")
            except Exception as exc:
                result.update(
                    status="PARSER_ERROR",
                    classification="INTERNAL_CORRECTABLE",
                    error_type="parse_exception",
                    error_sanitized=_sanitize(exc),
                )
            else:
                links = {prop.url for prop in properties if getattr(prop, "url", None)}
                result["cards"] = len(properties)
                result["property_links"] = len(links)
                if links:
                    result.update(status="SUCCESS_NO_NEW", classification="DRY_RUN_OK", retryable=False)
                else:
                    has_signals = any(token in body_lower for token in ("propiedad", "inmueble", "venta", "alquiler", "precio"))
                    result.update(
                        status="PARSER_ERROR",
                        classification="INTERNAL_CORRECTABLE",
                        error_type="no_property_links",
                        requires_playwright=has_signals,
                    )
    except requests.Timeout:
        result.update(status="TIMEOUT", classification="EXTERNAL_RETRYABLE", error_type="http_timeout")
    except requests.SSLError as exc:
        result.update(status="SSL_ERROR", classification="EXTERNAL", error_type="ssl_error", error_sanitized=_sanitize(exc), retryable=False)
    except requests.RequestException as exc:
        result.update(status="NETWORK_TRANSIENT", classification="EXTERNAL_RETRYABLE", error_type=type(exc).__name__, error_sanitized=_sanitize(exc))
    except Exception as exc:
        result.update(status="INTERNAL_ERROR", classification="INTERNAL_RETRYABLE", error_type=type(exc).__name__, error_sanitized=_sanitize(exc))
    finally:
        session.close()
    finished = datetime.now(timezone.utc)
    result["finished_at"] = finished.isoformat()
    result["duration_s"] = round((finished - started).total_seconds(), 2)
    return result


def _summary(path: Path, rows: List[Dict[str, Any]], total: int, run_id: str) -> None:
    counts = Counter(row["status"] for row in rows)
    lines = [
        "# Full manifest dry-run",
        "",
        f"Run ID: `{run_id}`",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        f"- Manifest sources: {total}",
        f"- Processed: {len(rows)}",
        f"- Parser success: {counts.get('SUCCESS_NO_NEW', 0)}",
        f"- Internal errors: {sum(counts.get(key, 0) for key in ('PARSER_ERROR', 'INTERNAL_ERROR', 'DATA_QUALITY_ERROR', 'CONFIG_ERROR'))}",
        f"- External/retryable: {sum(counts.get(key, 0) for key in ('TIMEOUT', 'NETWORK_TRANSIENT', 'SSL_ERROR', 'REMOTE_HTTP_ERROR', 'ANTI_BOT', 'AUTH_REQUIRED'))}",
        f"- Property links: {sum(int(row.get('property_links') or 0) for row in rows)}",
        f"- Requires Playwright confirmation: {sum(str(row.get('requires_playwright')).lower() == 'true' or row.get('requires_playwright') is True for row in rows)}",
        "- DB writes: 0",
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
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.workers <= 8:
        parser.error("--workers must be between 1 and 8")
    args.out.mkdir(parents=True, exist_ok=True)
    output = args.out / "dry_run_sources.csv"
    rows = _read(args.input)
    run_id = f"full_dry_run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    results: List[Dict[str, Any]] = []
    if args.resume and output.exists():
        results = _read(output)
        if results:
            run_id = results[0].get("run_id") or run_id
    done = {str(row["source_id"]) for row in results}
    pending = [row for row in rows if str(row["source_id"]) not in done]
    lock = threading.Lock()
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    print(f"run_id={run_id} total={len(rows)} pending={len(pending)} workers={args.workers} db_writes=0")
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(_check, row, args.timeout, run_id): row for row in pending}
        for index, future in enumerate(as_completed(futures), 1):
            result = future.result()
            with lock:
                results.append(result)
                if index % 25 == 0 or index == len(pending):
                    _write(output, results)
                    _summary(args.out / "dry_run_summary.md", results, len(rows), run_id)
                    print(f"processed={len(results)}/{len(rows)} last_status={result['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
