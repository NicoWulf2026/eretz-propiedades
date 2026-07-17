#!/usr/bin/env python3
"""Recheck rendered zero-link sources with the production card parser only."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parent.parent
SCRAPER_DIR = ROOT / "scraper"
if str(SCRAPER_DIR) not in sys.path:
    sys.path.insert(0, str(SCRAPER_DIR))
from playwright_scraper import (  # noqa: E402
    extract_candidate_detail_urls_from_document,
    parse_cards,
)


RECHECK_STATUSES = {
    "playwright_no_property_links",
    "playwright_zero_properties",
    "playwright_parser_error",
}
BLOCKED_FRAMES = ("google.", "facebook.", "recaptcha.", "zonaprop.", "argenprop.", "properati.")
FIELDS = (
    "source_id", "source_name", "listing_url", "previous_status", "final_status",
    "http_status", "final_url", "html_size", "frame_count", "property_links_count",
    "property_links_sample", "duration_seconds", "error_type", "evidence", "db_writes",
)


def discover_rendered_property_links(
    html: str, base_url: str, source_key: str = "diagnostic"
) -> list[str]:
    links: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        if value and value not in seen:
            seen.add(value)
            links.append(value)

    try:
        soup = BeautifulSoup(str(html or ""), "html.parser")
        for candidate, _text in extract_candidate_detail_urls_from_document(soup, base_url):
            add(candidate)
    except (ValueError, UnicodeError):
        pass
    try:
        for prop in parse_cards(str(html or ""), None, source_key, base_url, ""):
            add(prop.url)
    except (ValueError, UnicodeError):
        pass
    return links


def _load_input(path: Path) -> list[dict[str, Any]]:
    selected = []
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("playwright_final_status") in RECHECK_STATUSES:
                selected.append(row)
    return selected


def _done(path: Path) -> set[int]:
    if not path.exists():
        return set()
    output = set()
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                output.add(int(json.loads(line)["source_id"]))
            except (ValueError, KeyError, json.JSONDecodeError):
                continue
    return output


async def _diagnose(browser, source: dict[str, Any], timeout_s: int) -> dict[str, Any]:
    started = time.monotonic()
    source_id = int(source["source_id"])
    url = str(source.get("listing_url") or "").strip()
    record = {
        "source_id": source_id,
        "source_name": source.get("source_name") or "",
        "listing_url": url,
        "previous_status": source.get("playwright_final_status") or "",
        "final_status": "internal_error",
        "http_status": "",
        "final_url": "",
        "html_size": 0,
        "frame_count": 0,
        "property_links_count": 0,
        "property_links_sample": "",
        "duration_seconds": 0,
        "error_type": "",
        "evidence": "",
        "db_writes": 0,
    }
    context = await browser.new_context(ignore_https_errors=True, viewport={"width": 1366, "height": 900})
    page = await context.new_page()
    try:
        response = await page.goto(url, timeout=timeout_s * 1000, wait_until="domcontentloaded")
        record["http_status"] = response.status if response else ""
        record["final_url"] = page.url
        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        initial = await page.content()
        try:
            await page.mouse.wheel(0, 6000)
            await page.wait_for_timeout(1500)
        except Exception:
            pass
        rendered = await page.content()
        low = rendered.lower()
        text_length = len(re.sub(r"<[^>]+>", " ", rendered).strip())
        if any(token in low for token in ("cf-browser-verification", "challenge-platform", "_cf_chl", "datadome")):
            record["final_status"] = "external_antibot"
        elif any(token in low for token in ("g-recaptcha", "hcaptcha", "captcha")) and text_length < 1500:
            record["final_status"] = "external_captcha"
        elif record["http_status"] and int(record["http_status"]) >= 400:
            record["final_status"] = "external_http_error"
        else:
            links: list[str] = []
            seen: set[str] = set()
            for html in dict.fromkeys((initial, rendered)):
                for link in discover_rendered_property_links(html, page.url, str(source_id)):
                    if link not in seen:
                        seen.add(link)
                        links.append(link)
            frames_checked = 0
            for frame in page.frames[1:6]:
                frame_url = frame.url or ""
                host = urlparse(frame_url).netloc.lower()
                if not frame_url.startswith(("http://", "https://")) or any(item in host for item in BLOCKED_FRAMES):
                    continue
                frames_checked += 1
                try:
                    for link in discover_rendered_property_links(await frame.content(), frame_url, str(source_id)):
                        if link not in seen:
                            seen.add(link)
                            links.append(link)
                except Exception:
                    continue
            record["frame_count"] = frames_checked
            record["html_size"] = len(rendered)
            record["property_links_count"] = len(links)
            record["property_links_sample"] = " | ".join(links[:5])
            record["final_status"] = "recovered_parser" if links else "still_no_property_links"
            record["evidence"] = f"rendered_html={len(rendered)} frames={frames_checked} links={len(links)}"
    except Exception as exc:
        name = type(exc).__name__
        record["error_type"] = name
        record["final_status"] = "timeout" if "Timeout" in name else "internal_error"
    finally:
        record["duration_seconds"] = round(time.monotonic() - started, 2)
        await context.close()
    return record


async def _run(args) -> int:
    rows = _load_input(args.input)
    if args.limit:
        rows = rows[: args.limit]
    args.out.mkdir(parents=True, exist_ok=True)
    checkpoint = args.out / "results.jsonl"
    done = _done(checkpoint) if args.resume else set()
    if checkpoint.exists() and not args.resume:
        raise RuntimeError("Checkpoint exists; pass --resume or choose another output")
    pending = [row for row in rows if int(row["source_id"]) not in done]
    (args.out / "pid.txt").write_text(str(__import__("os").getpid()) + "\n", encoding="ascii")
    semaphore = asyncio.Semaphore(args.workers)
    lock = asyncio.Lock()
    counts: Counter[str] = Counter()

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)

        async def run_one(row):
            async with semaphore:
                result = await _diagnose(browser, row, args.timeout)
            async with lock:
                with checkpoint.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(result, ensure_ascii=False) + "\n")
                    handle.flush()
                counts[result["final_status"]] += 1
                completed = len(done) + sum(counts.values())
                if completed % 10 == 0 or completed == len(rows):
                    (args.out / "progress.json").write_text(json.dumps({
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "processed": completed,
                        "total": len(rows),
                        "pending": len(rows) - completed,
                        "by_status": dict(counts),
                        "db_writes": 0,
                    }, indent=2), encoding="utf-8")

        await asyncio.gather(*(run_one(row) for row in pending))
        await browser.close()

    all_rows = []
    with checkpoint.open(encoding="utf-8") as handle:
        for line in handle:
            all_rows.append(json.loads(line))
    with (args.out / "results.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_rows)
    summary_counts = Counter(row["final_status"] for row in all_rows)
    (args.out / "summary.md").write_text(
        "# Production parser Playwright recheck\n\n"
        + "\n".join(f"- {key}: {value}" for key, value in sorted(summary_counts.items()))
        + "\n- DB writes: 0\n- MAX_ACTIVE_BROWSERS: 1 shared browser, workers <= 2\n",
        encoding="utf-8",
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=25)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.workers <= 2:
        raise RuntimeError("MAX_ACTIVE_BROWSERS=2")
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
