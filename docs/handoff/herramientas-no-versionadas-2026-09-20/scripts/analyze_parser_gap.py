#!/usr/bin/env python
"""PR-BE-PARSER-07 parser-gap analysis for ERETZ.

Analyzes pages classified as needs_parser_fix after the url_listado update.
This is diagnostic-only: no DB writes, no publish, no raw/staging writes, and
no productive scraping runs.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import pathlib
import random
import re
import threading
import time
import urllib.parse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup
from scraper.network_security import secure_get

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPO_ROOT / "_scratch" / "url_listing_post_update_validation" / "needs_parser_fix.csv"
DEFAULT_POST_RESULTS = REPO_ROOT / "_scratch" / "url_listing_post_update_validation" / "post_update_validation_results.csv"
DEFAULT_STILL_FAILED = REPO_ROOT / "_scratch" / "url_listing_post_update_validation" / "still_failed_after_url_fix.csv"
DEFAULT_TOP_FAILED = REPO_ROOT / "_scratch" / "url_listing_post_update_validation" / "top_still_failed_by_yield.csv"
DEFAULT_BEFORE_AFTER = REPO_ROOT / "_scratch" / "url_listing_post_update_validation" / "before_after_comparison.csv"
DEFAULT_UPDATED = REPO_ROOT / "_scratch" / "url_listing_update_pr_be_url_06d" / "updated_rows.csv"
DEFAULT_OUT = REPO_ROOT / "_scratch" / "parser_gap_analysis_pr_be_parser_07"
EXPECTED_COUNT = 413

USER_AGENT = "ERETZ-ParserGapAnalysis/07 (+diagnostic; no DB writes)"

OPERATION_RE = re.compile(r"\b(venta|ventas|alquiler|alquileres|comprar|renta|emprendimiento|desarrollo)\b", re.I)
TYPE_RE = re.compile(r"\b(casa|departamento|depto|terreno|lote|local|oficina|ph|duplex|galpon|inmueble|propiedad)\b", re.I)
PRICE_RE = re.compile(r"(u\$s|us\$|usd|ars|\$\s*\d|precio|consultar)", re.I)
PAGINATION_RE = re.compile(r"(page=|pagina|pagination|paginacion|siguiente|next|anterior|prev|load-more)", re.I)
JS_RE = re.compile(r"(__NEXT_DATA__|window\.__|webpack|vite|gatsby|id=[\"']root[\"']|id=[\"']app[\"']|ng-version|nuxt)", re.I)
JSON_STATE_RE = re.compile(r"(__NEXT_DATA__|__NUXT__|window\.__INITIAL_STATE__|window\.INITIAL_STATE|window\.__APOLLO_STATE__|props\s*:|properties\s*:|propiedades\s*:)", re.I)
WP_RE = re.compile(r"(wp-content|wp-json|houzez|realhomes|elementor|estate|property-card|rh_prop|ere-property)", re.I)
TOKKO_RE = re.compile(r"(tokko|tokkobroker|/api/web/|/p/\d+|data-tokko)", re.I)
PROHIBITED_RE = re.compile(r"(zonaprop|argenprop|properati)", re.I)

CARD_SELECTORS = [
    "[class*='property-card']",
    "[class*='property-item']",
    "[class*='prop-card']",
    "[class*='prop-item']",
    "[class*='listing-item']",
    "[class*='listing-card']",
    "[class*='inmueble-item']",
    "[class*='item-inmueble']",
    "[class*='card-inmueble']",
    "[class*='inmueble-card']",
    "[class*='aviso']",
    "[class*='result-item']",
    "[class*='search-result']",
    "[class*='estate-item']",
    ".card",
    "article",
    "li[class*='item']",
    "div[class*='item']",
]

NEGATIVE_HREF_RE = re.compile(r"(contacto|nosotros|quienes|servicios|tasacion|blog|noticia|page=|/page/|buscar|busqueda|search|categoria|category)", re.I)
DETAIL_SEGMENT_RE = re.compile(
    r"(/p/\d+|/propiedad/[^/?#]+|/properties?/[^/?#]+|/inmuebles?/[^/?#]+|/detalle/[^/?#]+|/detalles/[^/?#]+|/ficha[^/?#]*|/aviso/[^/?#]+|/emprendimiento/[^/?#]+|/ref-[^/?#]+|/portfolio/[^/?#]+)",
    re.I,
)
QUERY_DETAIL_RE = re.compile(r"(\?|&)(id|cod|codigo|propiedad|inmueble|ref|referencia|ficha|item)=([^&#]{2,})", re.I)
ONCLICK_URL_RE = re.compile(
    r"(?:location(?:\.href)?|window\.open|openProperty|goTo|verDetalle|detalle|ficha)\s*\(?\s*['\"]([^'\"]+)['\"]",
    re.I,
)
GENERIC_URL_IN_JS_RE = re.compile(r"['\"]((?:https?://|/)[^'\"]{4,160}(?:propiedad|inmueble|detalle|ficha|aviso|properties|property|ref-)[^'\"]*)['\"]", re.I)

RESULT_FIELDS = [
    "source_id",
    "source_name",
    "website_url",
    "url_listado",
    "http_status",
    "html_size",
    "detected_family",
    "confidence",
    "evidence",
    "card_count_estimate",
    "candidate_detail_links_count",
    "candidate_detail_links_sample",
    "detected_href_patterns",
    "detected_data_attrs",
    "detected_onclick_patterns",
    "has_json_ld",
    "has_embedded_json",
    "has_pagination",
    "requires_js",
    "estimated_property_yield",
    "recommended_parser_fix",
    "risk",
    "notes",
]


def clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(clean(value)))
    except Exception:
        return default


def read_csv(path: pathlib.Path) -> list[dict[str, str]]:
    if not path.exists():
        raise SystemExit(f"Missing required input: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: pathlib.Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = []
        for row in rows:
            for key in row:
                if key not in fields:
                    fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_jsonl(path: pathlib.Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def normalize_url(base_url: str, href: str) -> str:
    href = html.unescape(clean(href))
    if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "whatsapp:")):
        return ""
    return urllib.parse.urljoin(base_url, href)


def host(url: str) -> str:
    try:
        return urllib.parse.urlsplit(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def path_query(url: str) -> str:
    try:
        p = urllib.parse.urlsplit(url)
        return f"{p.path}?{p.query}".lower()
    except Exception:
        return url.lower()


def is_probable_detail_url(url: str) -> bool:
    pq = path_query(url)
    if NEGATIVE_HREF_RE.search(pq):
        return False
    if DETAIL_SEGMENT_RE.search(pq):
        # Reject pure category paths, e.g. /propiedades/venta.
        tail = re.split(r"/(?:propiedades|properties|inmuebles|inmueble|propiedad|property)/", pq, maxsplit=1)
        if len(tail) == 2 and tail[1].strip("/?") in {"venta", "ventas", "alquiler", "alquileres", "search", "buscar"}:
            return False
        return True
    if QUERY_DETAIL_RE.search(pq):
        return True
    # Sites with slug-only detail links commonly include a long descriptive slug.
    parts = [x for x in urllib.parse.urlsplit(url).path.strip("/").split("/") if x]
    if len(parts) >= 2 and re.search(r"(venta|alquiler|casa|departamento|terreno|local|ph|lote)", pq) and re.search(r"\d{2,}", pq):
        return True
    return False


def href_pattern(url: str) -> str:
    pq = path_query(url)
    if QUERY_DETAIL_RE.search(pq):
        return "query_param_detail_url"
    if "/p/" in pq:
        return "tokko_p"
    if "/propiedad/" in pq:
        return "propiedad"
    if "/propiedades/" in pq:
        return "propiedades"
    if "/inmueble/" in pq or "/inmuebles/" in pq:
        return "inmueble"
    if "/property/" in pq or "/properties/" in pq:
        return "property"
    if "/detalle/" in pq or "/detalles/" in pq:
        return "detalle"
    if "ficha" in pq:
        return "ficha"
    if "ref-" in pq:
        return "ref"
    if "/aviso/" in pq:
        return "aviso"
    return "slug_or_custom"


def card_candidates(soup: BeautifulSoup) -> list[Any]:
    seen: set[int] = set()
    cards: list[Any] = []
    for selector in CARD_SELECTORS:
        for el in soup.select(selector):
            ident = id(el)
            if ident in seen:
                continue
            text = el.get_text(" ", strip=True)
            cls = " ".join(el.get("class", []))
            blob = f"{text} {cls}"
            if len(text) < 20:
                continue
            if not (PRICE_RE.search(blob) or OPERATION_RE.search(blob) or TYPE_RE.search(blob) or CARD_RE(blob)):
                continue
            seen.add(ident)
            cards.append(el)
    return cards[:500]


def CARD_RE(text: str) -> bool:
    return bool(re.search(r"(card|property|propiedad|inmueble|listing|result|item|precio|price)", text, re.I))


def data_url_values(soup: BeautifulSoup) -> tuple[list[str], list[str]]:
    urls: list[str] = []
    attrs: Counter[str] = Counter()
    for el in soup.find_all(True):
        for key, value in el.attrs.items():
            if not key.startswith("data-"):
                continue
            attrs[key] += 1
            if isinstance(value, list):
                values = value
            else:
                values = [value]
            for val in values:
                sval = clean(val)
                if not sval:
                    continue
                if any(tok in key for tok in ["href", "url", "link", "slug", "path", "target"]) or is_probable_detail_url(sval):
                    urls.append(sval)
    return urls[:50], [f"{k}:{v}" for k, v in attrs.most_common(12)]


def onclick_values(soup: BeautifulSoup) -> list[str]:
    out: list[str] = []
    for el in soup.find_all(True):
        val = clean(el.get("onclick"))
        if not val:
            continue
        match = ONCLICK_URL_RE.search(val)
        if match:
            out.append(match.group(1))
        elif any(tok in val.lower() for tok in ["detalle", "ficha", "propiedad", "inmueble", "location", "window.open"]):
            out.append(val[:160])
    return out[:50]


def script_detail_candidates(soup: BeautifulSoup) -> list[str]:
    out: list[str] = []
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        if not text:
            continue
        for match in GENERIC_URL_IN_JS_RE.finditer(text[:1_000_000]):
            out.append(match.group(1))
            if len(out) >= 50:
                return out
    return out


def classify_family(
    *,
    url_listado: str,
    http_status: int,
    html_size: int,
    cards: list[Any],
    anchors: list[str],
    detail_links: list[str],
    data_urls: list[str],
    onclick_urls: list[str],
    script_urls: list[str],
    has_json_ld: bool,
    has_embedded_json: bool,
    has_pagination: bool,
    requires_js: bool,
    text_blob: str,
) -> tuple[str, str, str, str, str, str]:
    if http_status < 200 or http_status >= 400:
        return ("manual_review", "low", "http_error_in_analysis", "manual_http_review", "medium", f"http_status={http_status}")
    if PROHIBITED_RE.search(url_listado):
        return ("manual_review", "low", "prohibited_portal_signal", "exclude_from_parser_changes", "low", "prohibited portal signal")
    if requires_js and html_size < 80_000 and not detail_links and not data_urls and not onclick_urls:
        return ("requires_js_rendering", "medium", "js_app_low_static_html", "confirm_with_playwright_or_network_api_capture", "medium", "static HTML likely incomplete")
    if onclick_urls:
        return ("onclick_detail_url", "high", f"onclick_urls={len(onclick_urls)}", "extract_detail_urls_from_onclick_handlers", "medium", "parse onclick safely and same-host only")
    if data_urls:
        return ("data_href_or_data_url", "high", f"data_url_attrs={len(data_urls)}", "extract_detail_urls_from_data_href_url_slug_attrs", "low", "use data-* attrs as candidate URLs after same-host/detail validation")
    if script_urls or has_embedded_json:
        family = "embedded_json_state"
        if has_json_ld:
            family = "json_ld_offers_or_realestate"
        return (family, "medium", f"script_url_candidates={len(script_urls)} json_ld={has_json_ld}", "extract_urls_from_json_ld_and_embedded_state", "medium", "parse JSON defensively; no broad regex-only ingestion")
    if detail_links:
        patterns = Counter(href_pattern(u) for u in detail_links)
        if patterns.get("query_param_detail_url"):
            return ("query_param_detail_url", "high", f"detail_links={len(detail_links)} patterns={dict(patterns)}", "accept_query_param_detail_urls_in_parse_cards", "low", "validate id/ref-like query params")
        if any(not urllib.parse.urlsplit(a).scheme for a in anchors):
            return ("relative_url_not_detected", "medium", f"detail_links={len(detail_links)} patterns={dict(patterns)}", "normalize_relative_urls_before_detail_detection", "low", "likely urljoin/detail path gap")
        return ("anchor_cards_without_detail_link", "medium", f"detail_links={len(detail_links)} patterns={dict(patterns)}", "broaden_card_anchor_selectors_and_detail_url_patterns", "low", "anchors exist but current selector likely misses them")
    if cards:
        no_anchor_cards = sum(1 for card in cards if not card.select("a[href]"))
        if no_anchor_cards >= max(2, len(cards) // 3):
            return ("listing_items_with_no_anchor", "high", f"cards={len(cards)} no_anchor_cards={no_anchor_cards}", "support_card_containers_without_anchors_or_find_detail_api", "medium", "cards render data but no static anchor")
        clickable = sum(1 for card in cards if "cursor" in clean(card.get("style")).lower() or "onclick" in card.attrs or card.get("role") == "button")
        if clickable:
            return ("card_clickable_container", "high", f"cards={len(cards)} clickable={clickable}", "inspect_clickable_card_attrs_and_nested_js_state", "medium", "container click likely owns navigation")
        if WP_RE.search(text_blob):
            return ("wordpress_realestate_plugin_pattern", "medium", f"cards={len(cards)} wp_signals=true", "add_wordpress_realestate_card_patterns", "medium", "WP theme/plugin selectors need targeted support")
        if TOKKO_RE.search(text_blob):
            return ("tokko_like_custom_pattern", "medium", f"cards={len(cards)} tokko_like=true", "extend_tokko_like_fallback_and_api_detection", "medium", "Tokko-like static output not matching current detail rules")
        return ("anchor_cards_without_detail_link", "medium", f"cards={len(cards)} anchors={len(anchors)}", "broaden_card_anchor_selectors_or_container_scoring", "medium", "cards exist but no usable detail href extracted")
    if has_pagination and not cards:
        return ("pagination_only", "medium", "pagination_without_cards", "inspect_listing_structure_and_page_params", "medium", "pagination exists but cards not identified")
    if OPERATION_RE.search(text_blob) and TYPE_RE.search(text_blob) and PRICE_RE.search(text_blob):
        return ("false_positive_listing", "low", "listing_terms_without_cards_or_links", "manual_review_before_parser_change", "medium", "signals may be nav/filter text only")
    return ("manual_review", "low", "no_clear_parser_family", "manual_html_review", "medium", "no dominant pattern")


def analyze_one(row: dict[str, str], session: requests.Session, timeout: float) -> dict[str, Any]:
    source_id = clean(row.get("source_id"))
    url = clean(row.get("new_url_listado") or row.get("url_listado"))
    website = clean(row.get("website_url"))
    status = 0
    final_url = ""
    body = ""
    err = ""
    try:
        resp = secure_get(session, url, timeout=(8, timeout))
        status = resp.status_code
        final_url = resp.url
        ctype = resp.headers.get("content-type", "")
        if "html" in ctype or "text" in ctype or not ctype:
            body = resp.text or ""
    except Exception as exc:
        err = type(exc).__name__

    soup = BeautifulSoup(body, "html.parser") if body else BeautifulSoup("", "html.parser")
    cards = card_candidates(soup)
    anchors_raw = [clean(a.get("href")) for a in soup.find_all("a", href=True)]
    anchors_abs = [normalize_url(final_url or url, a) for a in anchors_raw]
    same_host = host(final_url or url)
    internal_anchors = [a for a in anchors_abs if a and host(a) == same_host]
    detail_links = []
    seen: set[str] = set()
    for link in internal_anchors:
        if is_probable_detail_url(link) and link not in seen:
            seen.add(link)
            detail_links.append(link)

    data_urls_raw, data_attrs = data_url_values(soup)
    data_urls_abs = [normalize_url(final_url or url, v) for v in data_urls_raw]
    data_urls = [u for u in data_urls_abs if u and (not same_host or host(u) == same_host) and is_probable_detail_url(u)]
    onclick_raw = onclick_values(soup)
    onclick_abs = [normalize_url(final_url or url, v) for v in onclick_raw]
    onclick_urls = [u for u in onclick_abs if u and (not same_host or host(u) == same_host) and is_probable_detail_url(u)]
    script_raw = script_detail_candidates(soup)
    script_abs = [normalize_url(final_url or url, v) for v in script_raw]
    script_urls = [u for u in script_abs if u and (not same_host or host(u) == same_host) and is_probable_detail_url(u)]

    json_ld_scripts = soup.find_all("script", attrs={"type": re.compile("ld\\+json", re.I)})
    has_json_ld = bool(json_ld_scripts)
    full_text = soup.get_text(" ", strip=True)
    script_text = " ".join((s.string or s.get_text() or "")[:100_000] for s in soup.find_all("script")[:40])
    text_blob = f"{full_text[:500_000]} {script_text[:500_000]} {' '.join(data_attrs)}"
    has_embedded_json = bool(JSON_STATE_RE.search(script_text))
    has_pagination = bool(PAGINATION_RE.search(body) or PAGINATION_RE.search(url))
    requires_js = bool(JS_RE.search(body)) and len(internal_anchors) < 15

    family, confidence, evidence, fix, risk, notes = classify_family(
        url_listado=url,
        http_status=status,
        html_size=len(body),
        cards=cards,
        anchors=anchors_raw,
        detail_links=detail_links,
        data_urls=data_urls,
        onclick_urls=onclick_urls,
        script_urls=script_urls,
        has_json_ld=has_json_ld,
        has_embedded_json=has_embedded_json,
        has_pagination=has_pagination,
        requires_js=requires_js,
        text_blob=text_blob,
    )
    if err:
        family = "manual_review"
        confidence = "low"
        evidence = f"request_error={err}"
        fix = "manual_http_review"
        risk = "medium"
        notes = err

    patterns = Counter(href_pattern(u) for u in detail_links + data_urls + onclick_urls + script_urls)
    return {
        "source_id": source_id,
        "source_name": clean(row.get("source_name")),
        "website_url": website,
        "url_listado": url,
        "http_status": status,
        "html_size": len(body),
        "detected_family": family,
        "confidence": confidence,
        "evidence": evidence,
        "card_count_estimate": len(cards),
        "candidate_detail_links_count": len(detail_links) + len(data_urls) + len(onclick_urls) + len(script_urls),
        "candidate_detail_links_sample": " | ".join((detail_links + data_urls + onclick_urls + script_urls)[:5]),
        "detected_href_patterns": "; ".join(f"{k}:{v}" for k, v in patterns.most_common(8)),
        "detected_data_attrs": "; ".join(data_attrs[:10]),
        "detected_onclick_patterns": " | ".join(onclick_raw[:5]),
        "has_json_ld": has_json_ld,
        "has_embedded_json": has_embedded_json,
        "has_pagination": has_pagination,
        "requires_js": requires_js,
        "estimated_property_yield": to_int(row.get("estimated_property_yield")),
        "recommended_parser_fix": fix,
        "risk": risk,
        "notes": notes,
        "_final_url": final_url,
        "_anchors": len(internal_anchors),
    }


def merge_input_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    merged = []
    for row in rows:
        merged.append({
            "source_id": clean(row.get("source_id")),
            "source_name": clean(row.get("source_name")),
            "website_url": clean(row.get("website_url")),
            "url_listado": clean(row.get("new_url_listado") or row.get("url_listado")),
            "new_url_listado": clean(row.get("new_url_listado") or row.get("url_listado")),
            "estimated_property_yield": clean(row.get("estimated_property_yield")),
        })
    return merged


def md_table(rows: list[dict[str, Any]], fields: list[str], limit: int = 20) -> str:
    subset = rows[:limit]
    if not subset:
        return "_Sin filas._"
    lines = ["| " + " | ".join(fields) + " |", "| " + " | ".join(["---"] * len(fields)) + " |"]
    for row in subset:
        vals = []
        for field in fields:
            value = clean(row.get(field)).replace("|", "\\|")
            if len(value) > 120:
                value = value[:117] + "..."
            vals.append(value)
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def write_docs(out: pathlib.Path, results: list[dict[str, Any]]) -> None:
    family_counts = Counter(r["detected_family"] for r in results)
    family_yield: dict[str, int] = defaultdict(int)
    for row in results:
        family_yield[row["detected_family"]] += to_int(row.get("estimated_property_yield"))
    by_family = [
        {
            "detected_family": family,
            "source_count": count,
            "estimated_property_yield": family_yield[family],
            "recommended_first_fix": family_fix_recommendation(family),
        }
        for family, count in family_counts.most_common()
    ]
    write_csv(out / "parser_gap_by_family.csv", by_family)
    by_impact = sorted(results, key=lambda r: (to_int(r.get("estimated_property_yield")), to_int(r.get("candidate_detail_links_count"))), reverse=True)
    write_csv(out / "parser_gap_by_impact.csv", by_impact)
    write_csv(out / "top_parser_fixes_by_yield.csv", by_impact[:100])

    family_files = {
        "anchor_cards_without_detail_link": "anchor_cards_without_detail_link.csv",
        "card_clickable_container": "card_clickable_container.csv",
        "onclick_detail_url": "onclick_detail_url.csv",
        "data_href_or_data_url": "data_href_or_data_url.csv",
        "relative_url_not_detected": "relative_url_not_detected.csv",
        "query_param_detail_url": "query_param_detail_url.csv",
        "json_ld_offers_or_realestate": "json_ld_or_embedded_json.csv",
        "embedded_json_state": "json_ld_or_embedded_json.csv",
        "requires_js_rendering": "requires_js_rendering.csv",
        "manual_review": "manual_review.csv",
    }
    grouped_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in results:
        fname = family_files.get(row["detected_family"])
        if fname:
            grouped_rows[fname].append(row)
    for fname in set(family_files.values()):
        write_csv(out / fname, grouped_rows.get(fname, []), RESULT_FIELDS)

    most_common = family_counts.most_common(1)[0] if family_counts else ("none", 0)
    top20 = by_impact[:20]
    family_lines = "\n".join(
        f"- {row['detected_family']}: {row['source_count']} fuentes, yield estimado {row['estimated_property_yield']}"
        for row in by_family
    )
    summary = f"""# PR-BE-PARSER-07 parser gap summary

Generated: {datetime.now(timezone.utc).isoformat()}

## Resultado
- Total fuentes analizadas: **{len(results)}**
- Familia mas comun: **{most_common[0]}** ({most_common[1]} fuentes)
- Fix global recomendado primero: **{family_fix_recommendation(most_common[0])}**
- Fuentes que podria recuperar ese fix: **{most_common[1]}**

## Distribucion por familia
{family_lines}

## Top 20 por impacto
{md_table(top20, ['source_id', 'source_name', 'detected_family', 'confidence', 'estimated_property_yield', 'card_count_estimate', 'candidate_detail_links_count', 'recommended_parser_fix'])}

## Lectura tecnica
- El extractor productivo clave es `parse_cards` en `scraper/playwright_scraper.py`.
- `scraper/run.py` llama `parse_cards(html, operacion, key, base_url, ciudad)` para poblar URLs de fichas antes de visitar detalles.
- La mayor parte del gap no parece ser `url_listado`: son cards con senales inmobiliarias pero sin anchors directos o con navegacion escondida en atributos/JS/estado embebido.

## Guardrails
- DB writes: 0
- UPDATE: 0
- Publish: 0
- Scraping productivo/runs: 0
- Push/deploy/frontend: 0
- `--include-backlog`: no usado
- Outputs: `_scratch/parser_gap_analysis_pr_be_parser_07/`
"""
    (out / "parser_gap_summary.md").write_text(summary, encoding="utf-8")

    code_changes = f"""# Recommended code changes

## Extractor actual que esta fallando
El cuello esta en `parse_cards` dentro de `scraper/playwright_scraper.py`. La llamada principal ocurre desde `scraper/run.py`, donde el HTML renderizado del listado se pasa a `parse_cards` para cosechar URLs de fichas antes del scraping de detalle.

## Codigo productivo relevante
- `scraper/playwright_scraper.py`: `parse_cards`, selectores de cards, filtros `_is_detail_url`, fallback por `a[href]`.
- `scraper/run.py`: fase que recorre listados y llama `parse_cards`.
- `scripts/run_full_coverage_campaign.py` y `scripts/run_internal_scraping_batch.py`: diagnostico/categorizacion de `no_property_links`.

## Heuristicas nuevas recomendadas
1. Agregar un extractor auxiliar, por ejemplo `extract_candidate_detail_urls_from_card(card, base_url)`.
2. Dentro de ese auxiliar probar, en orden seguro:
   - anchors `a[href]` con patrones actuales;
   - `data-href`, `data-url`, `data-link`, `data-slug`, `data-target`;
   - `onclick` con `location.href`, `window.open`, `verDetalle`, `openProperty`;
   - URLs en JSON-LD y estado embebido, solo si pertenecen al mismo host;
   - cards clickeables con `role=button`, `tabindex`, `cursor:pointer` o clases de listado.
3. Ampliar `_is_detail_url` para aceptar query params `id`, `codigo`, `ref`, `ficha`, `propiedad`, `inmueble` cuando haya senales de card.
4. Agregar scoring para evitar falsos positivos: mismo host, no contacto/nosotros/blog, no paginacion, presencia de precio/tipo/operacion o imagen.

## Como evitar falsos positivos
- No aceptar URLs externas ni portales.
- No aceptar rutas de categorias puras: `/venta`, `/alquiler`, `/propiedades`, `/buscar`.
- Exigir al menos una senal contextual en la card: precio, operacion, tipo, imagen o metrica.
- Deduplicar por URL normalizada y limitar el maximo por pagina.
- Registrar subfamilia cuando el extractor usa data/onclick/json para monitorear calidad.

## Tests sugeridos
- Unit tests para `_is_detail_url` con rutas de ficha, categorias y query params.
- Fixtures HTML minimos para:
  - `data_href_or_data_url`;
  - `onclick_detail_url`;
  - `card_clickable_container`;
  - `listing_items_with_no_anchor`;
  - `json_ld_offers_or_realestate`;
  - `query_param_detail_url`.
- Regression test con una muestra de fuentes que ya funcionaban para asegurar que no baja el conteo de URLs.

## Que NO conviene hacer
- No reemplazar `parse_cards` completo.
- No aceptar cualquier link interno como ficha.
- No meter Playwright obligatorio para todos los casos.
- No escribir DB ni cambiar estados desde esta fase.
- No mezclar fixes de parser con publish/raw/staging.
"""
    (out / "recommended_code_changes.md").write_text(code_changes, encoding="utf-8")

    risk = """# Risk assessment

- El analisis es HTTP diagnostico; algunos sitios pueden requerir HTML renderizado por Playwright para confirmar.
- Las familias con JSON/onclick tienen mas riesgo de falso positivo si se parsean solo con regex.
- El fix global debe ser incremental y protegido por tests, porque `parse_cards` ya alimenta fuentes que funcionan.
- Los sitios con cards sin anchors pueden necesitar parser especifico o captura de API, no solo un selector nuevo.
"""
    (out / "risk_assessment.md").write_text(risk, encoding="utf-8")
    validation = """# Validation plan

1. Implementar el extractor auxiliar sin cambiar la firma publica de `parse_cards`.
2. Correr unit tests con fixtures por familia.
3. Correr `parse_cards` en modo local sobre las 413 fuentes de este analisis.
4. Comparar URLs detectadas antes/despues y revisar falsos positivos en top impacto.
5. Correr una regresion sobre fuentes ya exitosas del universo scrapeable.
6. Solo despues correr minilote diagnostico sin publish ni raw/staging.
"""
    (out / "validation_plan.md").write_text(validation, encoding="utf-8")
    next_step = f"""# Next step recommendation

PR-BE-PARSER-07b deberia implementar primero `{family_fix_recommendation(most_common[0])}` en `parse_cards`, con tests de fixtures y validacion local sobre esta carpeta de resultados.

No conviene correr publish ni scraping productivo todavia.
"""
    (out / "next_step_recommendation.md").write_text(next_step, encoding="utf-8")


def family_fix_recommendation(family: str) -> str:
    return {
        "anchor_cards_without_detail_link": "broaden_card_anchor_selectors_and_detail_url_patterns",
        "card_clickable_container": "extract_urls_from_clickable_card_containers",
        "onclick_detail_url": "parse_onclick_detail_url_handlers",
        "data_href_or_data_url": "extract_data_href_url_slug_attrs",
        "relative_url_not_detected": "normalize_relative_urls_before_detail_detection",
        "query_param_detail_url": "accept_safe_query_param_detail_urls",
        "same_page_modal_detail": "support_modal_detail_payload_or_api",
        "json_ld_offers_or_realestate": "extract_json_ld_realestate_urls",
        "embedded_json_state": "extract_embedded_json_state_property_urls",
        "wordpress_realestate_plugin_pattern": "add_wordpress_realestate_card_patterns",
        "tokko_like_custom_pattern": "extend_tokko_like_fallback_and_api_detection",
        "listing_items_with_no_anchor": "support_cards_without_static_anchors_or_api_capture",
        "pagination_only": "inspect_pagination_and_listing_container_selectors",
        "requires_js_rendering": "confirm_with_playwright_or_network_api_capture",
        "false_positive_listing": "manual_review_before_parser_change",
        "manual_review": "manual_html_review",
    }.get(family, "manual_html_review")


def validate_outputs(results: list[dict[str, Any]]) -> list[str]:
    errors = []
    if len(results) != EXPECTED_COUNT:
        errors.append(f"expected_{EXPECTED_COUNT}_got_{len(results)}")
    if any(not r.get("detected_family") for r in results):
        errors.append("missing_detected_family")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze parser gap families for PR-BE-PARSER-07")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--post-results", default=str(DEFAULT_POST_RESULTS))
    parser.add_argument("--still-failed", default=str(DEFAULT_STILL_FAILED))
    parser.add_argument("--top-failed", default=str(DEFAULT_TOP_FAILED))
    parser.add_argument("--before-after", default=str(DEFAULT_BEFORE_AFTER))
    parser.add_argument("--updated", default=str(DEFAULT_UPDATED))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=12.0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--seed", type=int, default=707)
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--include-backlog", action="store_true")
    args = parser.parse_args()

    if args.commit:
        raise SystemExit("--commit is not authorized in PR-BE-PARSER-07")
    if args.include_backlog:
        raise SystemExit("--include-backlog is not authorized in PR-BE-PARSER-07")

    required = [
        pathlib.Path(args.input),
        pathlib.Path(args.post_results),
        pathlib.Path(args.still_failed),
        pathlib.Path(args.top_failed),
        pathlib.Path(args.before_after),
        pathlib.Path(args.updated),
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit("Missing required inputs: " + "; ".join(missing))

    rows = merge_input_rows(read_csv(pathlib.Path(args.input)))
    if args.limit:
        rows = rows[: args.limit]
    elif len(rows) != EXPECTED_COUNT:
        raise SystemExit(f"Expected {EXPECTED_COUNT} needs_parser_fix rows, got {len(rows)}")

    random.seed(args.seed)
    shuffled = list(rows)
    random.shuffle(shuffled)

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    completed = 0
    lock = threading.Lock()
    results: list[dict[str, Any]] = []
    thread_local = threading.local()

    def get_session() -> requests.Session:
        if not hasattr(thread_local, "session"):
            session = requests.Session()
            session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
            thread_local.session = session
        return thread_local.session

    def worker(row: dict[str, str]) -> dict[str, Any]:
        return analyze_one(row, get_session(), args.timeout)

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = [executor.submit(worker, row) for row in shuffled]
        for future in as_completed(futures):
            results.append(future.result())
            with lock:
                completed += 1
                if completed % 50 == 0 or completed == len(shuffled):
                    print(f"analyzed={completed}/{len(shuffled)}")

    results.sort(key=lambda r: to_int(r["source_id"]))
    validation_errors = validate_outputs(results) if not args.limit else []
    write_csv(out / "parser_gap_results.csv", results, RESULT_FIELDS)
    write_jsonl(out / "parser_gap_results.jsonl", results)
    write_docs(out, results)
    guardrails = [
        "# Validation guardrails",
        "",
        "- zero DB writes: True",
        "- zero UPDATE: True",
        "- zero publish: True",
        "- zero public.propiedades changes: True (no DB connection used)",
        "- zero publish_queue changes: True (no DB connection used)",
        "- zero productive runs created: True",
        "- zero push/deploy/frontend: True",
        "- --include-backlog used: False",
        "- outputs under _scratch: True",
        "",
        "## Errors",
    ]
    guardrails.extend(f"- {err}" for err in validation_errors)
    if not validation_errors:
        guardrails.append("_Sin errores._")
    (out / "validation_guardrails.md").write_text("\n".join(guardrails) + "\n", encoding="utf-8")

    counts = Counter(r["detected_family"] for r in results)
    print(f"total={len(results)}")
    for family, count in counts.most_common():
        print(f"{family}={count}")
    print(f"validation_errors={len(validation_errors)}")
    print(f"out={out}")
    print("db_writes=0")
    print("publish=0")
    print("scraping_productivo=0")
    print("runs=0")
    print("push_deploy_frontend=0")


if __name__ == "__main__":
    main()
