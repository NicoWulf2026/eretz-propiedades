#!/usr/bin/env python3
"""Analyze rendered parser gaps without storing full HTML or writing DB."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import parse_qsl, urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPER_DIR = REPO_ROOT / "scraper"
if str(SCRAPER_DIR) not in sys.path:
    sys.path.insert(0, str(SCRAPER_DIR))

from run import BROWSER_ARGS, BROWSER_UA  # noqa: E402


DEFAULT_INPUT = REPO_ROOT / "_scratch" / "codex_autonomous_scraping" / "playwright_dry_run_sources.csv"
DEFAULT_OUT = REPO_ROOT / "_scratch" / "codex_autonomous_scraping" / "parser_gap_patterns.csv"
FIELDS = [
    "source_id", "nombre", "url", "domain", "html_size", "anchor_count",
    "iframe_count", "property_signal_count", "href_patterns",
    "data_attribute_patterns", "script_patterns", "iframe_sources",
    "spa_framework", "detected_family", "recommended_fix", "status",
]
DETAIL_WORDS = re.compile(
    r"(propiedad|inmueble|ficha|detalle|aviso|listing|departamento|casa|terreno|lote|local|venta|alquiler)",
    re.IGNORECASE,
)
BAD_WORDS = re.compile(r"(contact|nosotros|quienes|servicios|tasacion|blog|noticia)", re.IGNORECASE)


def _read(path: Path) -> List[Dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: int(row["source_id"])))


def _path_pattern(value: str, base_url: str) -> str:
    absolute = urljoin(base_url, value)
    parsed = urlparse(absolute)
    path = re.sub(r"\b\d{2,}\b", "{id}", parsed.path.lower())
    path = re.sub(r"/[0-9a-f]{8,}(?=/|$)", "/{id}", path)
    keys = sorted({key.lower() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)})
    return f"{path}?{','.join(keys)}" if keys else path


def _spa_framework(html: str) -> str:
    lowered = html.lower()
    found = []
    for name, tokens in {
        "nextjs": ("__next_data__", "/_next/static/"),
        "nuxt": ("__nuxt__", "/_nuxt/"),
        "angular": ("ng-version", "app-root"),
        "vue": ("data-v-", "__vue__"),
        "react": ("data-reactroot", "react-dom"),
    }.items():
        if any(token in lowered for token in tokens):
            found.append(name)
    return ";".join(found) or "none"


def _select_sample(rows: List[Dict[str, str]], limit: int) -> List[Dict[str, str]]:
    gaps = [row for row in rows if row.get("status") == "PARSER_ERROR"]
    timeouts = [row for row in gaps if row.get("error_type") == "parse_timeout"]
    no_links = [row for row in gaps if row.get("error_type") != "parse_timeout"]
    selected = []
    for row in timeouts + no_links:
        if row["source_id"] not in {item["source_id"] for item in selected}:
            selected.append(row)
        if len(selected) >= limit:
            break
    return selected


def _analyze(row: Dict[str, str], timeout_ms: int) -> Dict[str, Any]:
    result = {field: "" for field in FIELDS}
    result.update(
        source_id=row["source_id"],
        nombre=row["nombre"],
        url=row["url"],
        domain=urlparse(row["url"]).netloc.lower().lstrip("www."),
        status="unexpected_error",
    )
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=BROWSER_ARGS)
            try:
                context = browser.new_context(user_agent=BROWSER_UA, viewport={"width": 1366, "height": 768}, locale="es-AR")
                page = context.new_page()
                page.goto(row["url"], wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(1500)
                for _ in range(2):
                    try:
                        page.evaluate("window.scrollTo(0, document.body ? document.body.scrollHeight : 0)")
                        page.wait_for_timeout(500)
                    except Exception:
                        break
                html = page.content()
                soup = BeautifulSoup(html[:2_000_000], "html.parser")
                anchors = [anchor.get("href", "") for anchor in soup.select("a[href]")]
                patterns = Counter(
                    _path_pattern(href, page.url)
                    for href in anchors
                    if href and not href.startswith(("#", "mailto:", "tel:", "javascript:"))
                )
                interesting = [
                    (pattern, count) for pattern, count in patterns.most_common()
                    if DETAIL_WORDS.search(pattern) and not BAD_WORDS.search(pattern)
                ]
                if not interesting:
                    interesting = patterns.most_common(8)

                data_counts: Counter[str] = Counter()
                onclick_count = 0
                for element in soup.find_all(True):
                    for key, value in element.attrs.items():
                        if key.startswith("data-") and any(token in key for token in ("url", "href", "link", "slug", "id", "property", "prop")):
                            data_counts[key] += 1
                    if element.get("onclick"):
                        onclick_count += 1

                script_text = "\n".join(script.get_text(" ", strip=True)[:100_000] for script in soup.find_all("script"))
                script_patterns = []
                for label, pattern in {
                    "next_data": r"__NEXT_DATA__",
                    "nuxt_state": r"__NUXT__",
                    "json_ld": r"application/ld\+json",
                    "embedded_property_urls": r"[\"'](?:url|href|link|slug)[\"']\s*:\s*[\"'][^\"']*(?:propiedad|inmueble|ficha|detalle)",
                    "onclick": r"(?:location\.href|window\.location|open\s*\()",
                }.items():
                    count = len(re.findall(pattern, html if label == "json_ld" else script_text, flags=re.IGNORECASE))
                    if count:
                        script_patterns.append(f"{label}:{count}")

                iframe_sources = []
                for frame in soup.select("iframe[src]"):
                    src = urljoin(page.url, frame.get("src", ""))
                    parsed = urlparse(src)
                    iframe_sources.append(f"{parsed.netloc.lower()}{_path_pattern(src, src)}")

                body_lower = soup.get_text(" ", strip=True).lower()[:300_000]
                signal_count = sum(
                    len(re.findall(pattern, body_lower))
                    for pattern in (r"\bventa\b", r"\balquiler\b", r"\bpropiedad(?:es)?\b", r"\binmueble(?:s)?\b", r"\b(?:usd|u\$s)\b", r"\$\s*\d", r"\b(?:dormitorios?|ambientes?|m2|m²)\b")
                )
                framework = _spa_framework(html)

                if iframe_sources:
                    family, fix = "iframe_provider", "parse_same_site_and_provider_iframe_documents"
                elif data_counts:
                    family, fix = "data_attribute_urls", "expand_safe_data_attribute_extraction"
                elif onclick_count or any(item.startswith("onclick:") for item in script_patterns):
                    family, fix = "onclick_or_script_urls", "extract_safe_onclick_and_embedded_script_urls"
                elif framework != "none" and any(item.startswith(("next_data:", "nuxt_state:", "embedded_property_urls:")) for item in script_patterns):
                    family, fix = "spa_embedded_state", "extract_detail_urls_from_framework_state"
                elif interesting:
                    family, fix = "unrecognized_href_pattern", "score_repeated_same_site_property_hrefs"
                elif signal_count >= 3:
                    family, fix = "cards_without_links", "extract_repeated_card_ids_or_xhr_state"
                else:
                    family, fix = "institutional_or_empty", "exclude_or_repair_listing_url"

                result.update(
                    html_size=len(html),
                    anchor_count=len(anchors),
                    iframe_count=len(iframe_sources),
                    property_signal_count=signal_count,
                    href_patterns="; ".join(f"{pattern}:{count}" for pattern, count in interesting[:12]),
                    data_attribute_patterns="; ".join(f"{key}:{count}" for key, count in data_counts.most_common(12)),
                    script_patterns="; ".join(script_patterns),
                    iframe_sources="; ".join(dict.fromkeys(iframe_sources))[:1000],
                    spa_framework=framework,
                    detected_family=family,
                    recommended_fix=fix,
                    status="analyzed",
                )
                context.close()
            finally:
                browser.close()
    except Exception as exc:
        result["status"] = f"error:{type(exc).__name__}"
    return result


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--timeout-ms", type=int, default=25_000)
    args = parser.parse_args(argv)
    if not 1 <= args.workers <= 2:
        parser.error("--workers must be 1 or 2")
    sample = _select_sample(_read(args.input), args.limit)
    results: List[Dict[str, Any]] = []
    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(_analyze, row, args.timeout_ms): row for row in sample}
        for index, future in enumerate(as_completed(futures), 1):
            result = future.result()
            with lock:
                results.append(result)
                if index % 5 == 0 or index == len(sample):
                    _write(args.out, results)
                    print(f"processed={len(results)}/{len(sample)} family={result['detected_family']}")
    print(json.dumps(Counter(row["detected_family"] for row in results), ensure_ascii=False))
    print("db_writes=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
