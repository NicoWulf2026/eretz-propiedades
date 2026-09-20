#!/usr/bin/env python
"""Detect proposed real-estate listing URLs without writing to DB.

PR-BE-URL-06 is intentionally proposal-only:
- no DB writes
- no scraper runs
- no publish
- no --commit
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import re
import sys
import time
import urllib.parse
import warnings
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import requests
except Exception as exc:  # pragma: no cover
    raise SystemExit("requests is required and must already be installed") from exc

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover
    BeautifulSoup = None  # type: ignore
from scraper.network_security import secure_get


REPO_ROOT = Path(__file__).resolve().parents[1]

COMMON_LISTING_PATHS = [
    "/propiedades",
    "/propiedad",
    "/inmuebles",
    "/inmueble",
    "/ventas",
    "/venta",
    "/alquileres",
    "/alquiler",
    "/comprar",
    "/rentas",
    "/emprendimientos",
    "/desarrollos",
    "/buscar",
    "/busqueda",
    "/catalogo",
    "/listado",
    "/resultados",
    "/propiedades-en-venta",
    "/propiedades-en-alquiler",
    "/inmuebles-en-venta",
    "/inmuebles-en-alquiler",
]

PRIORITY_COMMON_LISTING_PATHS = [
    "/propiedades",
    "/inmuebles",
    "/ventas",
    "/alquileres",
    "/propiedades-en-venta",
    "/propiedades-en-alquiler",
    "/inmuebles-en-venta",
    "/inmuebles-en-alquiler",
    "/buscar",
    "/busqueda",
    "/listado",
    "/resultados",
]

POSITIVE_PATH_TERMS = [
    "propiedad",
    "propiedades",
    "inmueble",
    "inmuebles",
    "venta",
    "ventas",
    "alquiler",
    "alquileres",
    "renta",
    "rentas",
    "emprendimiento",
    "desarrollo",
    "buscar",
    "busqueda",
    "catalogo",
    "listado",
    "resultado",
]

NEGATIVE_PATH_TERMS = [
    "contacto",
    "nosotros",
    "quienes",
    "quienes-somos",
    "empresa",
    "staff",
    "tasaciones",
    "servicios",
    "blog",
    "blogs",
    "nota",
    "notas",
    "detalle",
    "detalles",
    "ficha",
    "noticia",
    "noticias",
    "quiero-vender",
    "vender",
    "tasacion",
    "tasaciones",
    "login",
    "admin",
    "wp-admin",
    "politica",
    "privacidad",
    "terminos",
]

PROPERTY_TYPE_TERMS = [
    "casa",
    "casas",
    "departamento",
    "departamentos",
    "depto",
    "terreno",
    "terrenos",
    "lote",
    "lotes",
    "local",
    "locales",
    "oficina",
    "oficinas",
    "ph",
    "duplex",
    "galpon",
    "galpón",
]

OPERATION_TERMS = [
    "venta",
    "ventas",
    "alquiler",
    "alquileres",
    "temporario",
    "temporaria",
    "renta",
    "comprar",
    "vender",
]

PRICE_RE = re.compile(
    r"(?:u\s?\$s|usd|ars|\$)\s*[0-9][0-9\.\,]{2,}|[0-9][0-9\.\,]{3,}\s*(?:usd|ars)",
    re.I,
)
PAGINATION_RE = re.compile(r"\b(?:pagina|página|page|siguiente|next|anterior|prev)\b|[?&]page=", re.I)
JSONLD_RE = re.compile(r'<script[^>]+type=["\']application/ld\+json["\']', re.I)
CARD_HINT_RE = re.compile(
    r"\b(?:card|property|propiedad|inmueble|listing|resultado|item-prop|ficha)\b",
    re.I,
)

PROHIBITED_HOST_RE = re.compile(
    r"(^|\.)("
    r"zonaprop\.com|argenprop\.com|properati\.com|mercadolibre\.com|inmuebles\.clarin\.com|"
    r"remax\.com|airbnb\.com|booking\.com"
    r")$",
    re.I,
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

@dataclass
class SourceRecord:
    source_id: str
    source_name: str = ""
    website_url: str = ""
    current_listing_url: str = ""
    reasons: set[str] = field(default_factory=set)
    row: Dict[str, str] = field(default_factory=dict)
    estimated_property_yield: int = 0


@dataclass
class FetchResult:
    url: str
    status: Optional[int] = None
    final_url: str = ""
    text: str = ""
    error: str = ""
    elapsed_ms: int = 0


@dataclass
class CandidateResult:
    source_id: str
    source_name: str
    website_url: str
    current_listing_url: str
    candidate_url: str
    score: int
    confidence: str
    final_category: str
    http_status: str
    final_url_after_redirect: str
    evidence: str
    detected_from: str
    candidate_url_count: int
    property_links_count: int
    property_links_sample: str
    has_price_signals: bool
    has_operation_signals: bool
    has_property_type_signals: bool
    has_pagination: bool
    requires_playwright: bool
    is_homepage: bool
    is_property_detail: bool
    is_prohibited: bool
    estimated_property_yield: int
    recommended_action: str
    requires_db_change_later: bool
    risk: str
    notes: str


def norm_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "t", "yes", "y", "si", "sí"}


def to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or str(value).strip() == "":
            return default
        return int(float(str(value).strip()))
    except Exception:
        return default


def clean_cell(value: Any) -> str:
    return str(value or "").strip()


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return [dict(row) for row in csv.DictReader(f)]


def write_csv(path: Path, rows: Sequence[Dict[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def write_jsonl(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def normalize_url(raw: str, base: str = "") -> str:
    raw = html.unescape(clean_cell(raw))
    if not raw or raw in {"#", "/#"}:
        return ""
    if raw.startswith(("mailto:", "tel:", "javascript:", "whatsapp:")):
        return ""
    if base:
        raw = urllib.parse.urljoin(base, raw)
    if raw.startswith("//"):
        raw = "https:" + raw
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw
    try:
        parsed = urllib.parse.urlsplit(raw)
    except Exception:
        return ""
    if not parsed.netloc:
        return ""
    scheme = parsed.scheme.lower() if parsed.scheme in {"http", "https"} else "https"
    netloc = parsed.netloc.lower()
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    query = parsed.query
    return urllib.parse.urlunsplit((scheme, netloc, path, query, ""))


def canonical_url(url: str) -> str:
    try:
        p = urllib.parse.urlsplit(url)
    except Exception:
        return url
    path = (p.path or "/").rstrip("/") or "/"
    return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), path, p.query, ""))


def host_of(url: str) -> str:
    try:
        return urllib.parse.urlsplit(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def path_of(url: str) -> str:
    try:
        return urllib.parse.urlsplit(url).path or "/"
    except Exception:
        return "/"


def is_prohibited_url(url: str) -> bool:
    host = host_of(url)
    return bool(host and PROHIBITED_HOST_RE.search(host))


def same_site(url: str, base: str) -> bool:
    hu = host_of(url)
    hb = host_of(base)
    return bool(hu and hb and (hu == hb or hu.endswith("." + hb) or hb.endswith("." + hu)))


def is_home_url(url: str, website_url: str) -> bool:
    if not url or not website_url:
        return False
    if host_of(url) != host_of(website_url):
        return False
    path = path_of(url).strip("/")
    query = urllib.parse.urlsplit(url).query if url else ""
    return path == "" and query == ""


def looks_like_property_detail_url(url: str) -> bool:
    path = path_of(url).lower().strip("/")
    if not path:
        return False
    segments = [s for s in path.split("/") if s]
    if len(segments) >= 2 and any(t in segments[0] for t in ("propiedad", "inmueble", "property", "properties", "detalle", "detalles", "ficha")):
        return True
    if len(segments) >= 3 and segments[0] in {"nota", "notas", "blog", "noticia", "noticias"}:
        return True
    if re.search(r"(propiedad|inmueble|casa|departamento|terreno)[-/]?[0-9]{3,}", path):
        return True
    if re.search(r"/[a-z0-9-]+-[0-9]{4,}/?$", "/" + path):
        return True
    return False


def looks_like_listing_url(url: str) -> bool:
    path = path_of(url).lower()
    return any(term in path for term in POSITIVE_PATH_TERMS)


def looks_negative_url(url: str) -> bool:
    path = path_of(url).lower()
    return any(term in path for term in NEGATIVE_PATH_TERMS)


def is_non_listing_negative_path(url: str) -> bool:
    path = path_of(url).lower()
    if any(term in path for term in ["nota", "notas", "noticia", "noticias", "blog", "quiero-vender", "tasacion", "tasaciones"]):
        return True
    if "vender" in path and not any(term in path for term in ["venta", "ventas", "propiedad", "inmueble"]):
        return True
    return False


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-AR,es;q=0.9,en;q=0.5",
        }
    )
    return s


def fetch(session: requests.Session, url: str, timeout: float) -> FetchResult:
    started = time.monotonic()
    result = FetchResult(url=url)
    if not url:
        result.error = "empty_url"
        return result
    try:
        resp = secure_get(session, url, timeout=(8, timeout))
        result.status = resp.status_code
        result.final_url = resp.url
        ctype = resp.headers.get("content-type", "")
        if "text" in ctype or "html" in ctype or not ctype:
            result.text = resp.text[:220_000]
        else:
            result.text = ""
        result.elapsed_ms = int((time.monotonic() - started) * 1000)
    except Exception as exc:
        result.error = type(exc).__name__
        result.elapsed_ms = int((time.monotonic() - started) * 1000)
    return result


def extract_links(page_url: str, text: str) -> List[Tuple[str, str, str]]:
    if not text:
        return []
    links: List[Tuple[str, str, str]] = []
    if BeautifulSoup is not None:
        soup = BeautifulSoup(text, "html.parser")
        for a in soup.find_all("a"):
            href = a.get("href")
            url = normalize_url(href, page_url)
            if not url:
                continue
            label = " ".join(a.get_text(" ", strip=True).split())
            parent_labels = []
            for parent in a.parents:
                name = getattr(parent, "name", "")
                if name in {"nav", "header"}:
                    parent_labels.append("menu")
                    break
                if name == "footer":
                    parent_labels.append("footer")
                    break
            source = parent_labels[0] if parent_labels else "internal_link"
            links.append((url, label[:160], source))
        return links

    for match in re.finditer(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', text, re.I | re.S):
        url = normalize_url(match.group(1), page_url)
        if url:
            label = re.sub(r"<[^>]+>", " ", match.group(2))
            links.append((url, " ".join(label.split())[:160], "internal_link"))
    return links


def text_signals(text: str) -> Dict[str, Any]:
    lower = text.lower()
    operation_hits = sum(1 for term in OPERATION_TERMS if term in lower)
    type_hits = sum(1 for term in PROPERTY_TYPE_TERMS if term in lower)
    price_hits = len(PRICE_RE.findall(text))
    pagination = bool(PAGINATION_RE.search(text))
    jsonld = bool(JSONLD_RE.search(text))
    card_hints = len(CARD_HINT_RE.findall(text))
    institutional_hits = sum(1 for term in ["quienes somos", "nuestra empresa", "contacto", "tasaciones"] if term in lower)
    return {
        "operation_hits": operation_hits,
        "type_hits": type_hits,
        "price_hits": price_hits,
        "pagination": pagination,
        "jsonld": jsonld,
        "card_hints": card_hints,
        "institutional_hits": institutional_hits,
    }


def property_link_score(url: str, label: str) -> bool:
    path = path_of(url).lower()
    joined = f"{path} {label.lower()}"
    if looks_negative_url(url):
        return False
    if re.search(r"/(propiedad|propiedades|inmueble|inmuebles)/[^/]{4,}", path):
        return True
    if any(term in joined for term in PROPERTY_TYPE_TERMS) and any(term in joined for term in OPERATION_TERMS):
        return True
    if PRICE_RE.search(label):
        return True
    return False


def extract_property_links(base_url: str, page_url: str, text: str) -> List[str]:
    out = []
    seen = set()
    for url, label, _source in extract_links(page_url, text[:180_000]):
        if not same_site(url, base_url):
            continue
        if property_link_score(url, label):
            cu = canonical_url(url)
            if cu not in seen:
                seen.add(cu)
                out.append(url)
    return out[:50]


def sitemap_urls(session: requests.Session, website_url: str, timeout: float) -> List[str]:
    root = normalize_url("/", website_url)
    if not root:
        return []
    sitemap = urllib.parse.urljoin(root, "/sitemap.xml")
    res = fetch(session, sitemap, timeout)
    if res.status is None or res.status >= 400 or not res.text:
        return []
    urls = re.findall(r"<loc>\s*([^<]+)\s*</loc>", res.text, re.I)
    clean = []
    seen = set()
    for raw in urls[:1500]:
        url = normalize_url(raw)
        if not url or not same_site(url, website_url):
            continue
        if not looks_like_listing_url(url):
            continue
        cu = canonical_url(url)
        if cu not in seen:
            seen.add(cu)
            clean.append(url)
    return clean[:20]


def candidate_paths_from_links(website_url: str, links: List[Tuple[str, str, str]]) -> List[Tuple[str, str]]:
    candidates: List[Tuple[str, str]] = []
    seen = set()
    for url, label, source in links[:350]:
        if not same_site(url, website_url):
            continue
        if is_prohibited_url(url):
            continue
        label_l = label.lower()
        if looks_like_listing_url(url) or any(t in label_l for t in POSITIVE_PATH_TERMS):
            if looks_negative_url(url):
                continue
            cu = canonical_url(url)
            if cu not in seen:
                seen.add(cu)
                candidates.append((url, source))
                if len(candidates) >= 35:
                    break
    return candidates


def score_candidate(
    src: SourceRecord,
    candidate_url: str,
    detected_from: str,
    fetch_result: FetchResult,
    website_url: str,
    current_listing_url: str,
    candidate_url_count: int,
) -> CandidateResult:
    text = fetch_result.text or ""
    signals = text_signals(text)
    property_links = extract_property_links(website_url, fetch_result.final_url or candidate_url, text)
    is_homepage = is_home_url(fetch_result.final_url or candidate_url, website_url)
    is_detail = looks_like_property_detail_url(fetch_result.final_url or candidate_url)
    is_bad_negative_path = is_non_listing_negative_path(fetch_result.final_url or candidate_url)
    prohibited = is_prohibited_url(fetch_result.final_url or candidate_url)
    status = fetch_result.status
    final_url = fetch_result.final_url or ""

    score = 0
    evidence_parts: List[str] = []

    if status and 200 <= status < 300:
        score += 18
        evidence_parts.append(f"http={status}")
    elif status and 300 <= status < 400:
        score += 8
        evidence_parts.append(f"http={status}")
    elif status:
        score -= 25
        evidence_parts.append(f"http={status}")
    else:
        score -= 20
        evidence_parts.append(f"fetch_error={fetch_result.error or 'unknown'}")

    if not is_homepage:
        score += 12
    else:
        score -= 25
        evidence_parts.append("homepage")

    if canonical_url(candidate_url) == canonical_url(current_listing_url):
        score += 5
        evidence_parts.append("current_url")

    if looks_like_listing_url(candidate_url):
        score += 14
        evidence_parts.append("listing_path")
    if detected_from == "menu":
        score += 10
        evidence_parts.append("menu")
    elif detected_from == "footer":
        score += 6
        evidence_parts.append("footer")
    elif detected_from == "sitemap":
        score += 9
        evidence_parts.append("sitemap")
    elif detected_from == "common_path":
        score += 4
        evidence_parts.append("common_path")

    if property_links:
        link_points = min(22, 7 + len(property_links) * 2)
        score += link_points
        evidence_parts.append(f"property_links={len(property_links)}")

    if signals["price_hits"] > 0:
        score += min(15, 5 + signals["price_hits"])
        evidence_parts.append(f"price_signals={signals['price_hits']}")
    if signals["operation_hits"] > 0:
        score += min(10, signals["operation_hits"] * 2)
        evidence_parts.append(f"operation_terms={signals['operation_hits']}")
    if signals["type_hits"] > 0:
        score += min(10, signals["type_hits"] * 2)
        evidence_parts.append(f"type_terms={signals['type_hits']}")
    if signals["pagination"]:
        score += 8
        evidence_parts.append("pagination")
    if signals["jsonld"]:
        score += 4
        evidence_parts.append("jsonld")
    if signals["card_hints"] >= 5:
        score += 8
        evidence_parts.append(f"card_hints={signals['card_hints']}")

    if looks_negative_url(candidate_url):
        score -= 35 if is_bad_negative_path else 20
        evidence_parts.append("negative_path")
    if is_detail:
        score -= 30
        evidence_parts.append("property_detail")
    if is_bad_negative_path:
        score = min(score, 34)
        evidence_parts.append("non_listing_path")
    if prohibited:
        score = 0
        evidence_parts.append("prohibited")
    if final_url and same_site(final_url, website_url) and is_home_url(final_url, website_url) and not is_home_url(candidate_url, website_url):
        score -= 18
        evidence_parts.append("redirects_to_home")
    if signals["institutional_hits"] >= 2 and not property_links and signals["price_hits"] == 0:
        score -= 12
        evidence_parts.append("institutional")

    score = max(0, min(100, score))

    requires_playwright = (
        bool(status and 200 <= status < 400)
        and score < 55
        and not property_links
        and (
            "__NEXT_DATA__" in text
            or "id=\"root\"" in text
            or "id=\"app\"" in text
            or "window.__NUXT__" in text
            or len(text) < 3500
        )
    )
    if requires_playwright:
        evidence_parts.append("requires_playwright_to_confirm")

    if score >= 75 and not is_homepage and not is_detail and not prohibited:
        confidence = "high"
        category = "found_high_confidence"
        action = "propose_update_later"
        risk = "low"
    elif score >= 55 and not is_homepage and not is_detail and not prohibited:
        confidence = "medium"
        category = "found_medium_confidence"
        action = "manual_review_then_update_later"
        risk = "medium"
    elif score >= 35 and not prohibited:
        confidence = "low"
        category = "found_low_confidence"
        action = "manual_review"
        risk = "high"
    else:
        confidence = "none"
        category = "no_candidate_found"
        action = "manual_review"
        risk = "high"

    if requires_playwright and category in {"found_low_confidence", "no_candidate_found"}:
        category = "requires_playwright_to_confirm"
        action = "confirm_with_playwright_later"

    if canonical_url(candidate_url) == canonical_url(current_listing_url) and score >= 70:
        category = "current_listing_url_ok"
        action = "no_db_change"
        risk = "low"

    if is_homepage:
        category = "homepage_as_listing"
        action = "do_not_update_to_home"
        risk = "high"

    if is_detail:
        category = "property_detail_as_listing"
        action = "do_not_update_to_detail"
        risk = "high"

    if is_bad_negative_path and category not in {"skipped_prohibited", "property_detail_as_listing"}:
        category = "manual_review"
        action = "manual_review"
        confidence = "none"
        risk = "high"

    if prohibited:
        category = "skipped_prohibited"
        action = "skip"
        risk = "prohibited"

    return CandidateResult(
        source_id=src.source_id,
        source_name=src.source_name,
        website_url=website_url,
        current_listing_url=current_listing_url,
        candidate_url=candidate_url,
        score=score,
        confidence=confidence,
        final_category=category,
        http_status=str(status or ""),
        final_url_after_redirect=final_url,
        evidence="; ".join(evidence_parts),
        detected_from=detected_from,
        candidate_url_count=candidate_url_count,
        property_links_count=len(property_links),
        property_links_sample=" | ".join(property_links[:5]),
        has_price_signals=signals["price_hits"] > 0,
        has_operation_signals=signals["operation_hits"] > 0,
        has_property_type_signals=signals["type_hits"] > 0,
        has_pagination=bool(signals["pagination"]),
        requires_playwright=requires_playwright,
        is_homepage=is_homepage,
        is_property_detail=is_detail,
        is_prohibited=prohibited,
        estimated_property_yield=src.estimated_property_yield,
        recommended_action=action,
        requires_db_change_later=action in {"propose_update_later", "manual_review_then_update_later"},
        risk=risk,
        notes=f"reasons={','.join(sorted(src.reasons))}; elapsed_ms={fetch_result.elapsed_ms}",
    )


def should_skip_row(row: Dict[str, str]) -> Tuple[bool, str]:
    website = clean_cell(row.get("website_url"))
    listing = clean_cell(row.get("listing_url"))
    final_status = clean_cell(row.get("final_status")).lower()
    diagnostic = clean_cell(row.get("diagnostic_status")).lower()
    category = clean_cell(row.get("error_category")).lower()
    skip_reason = clean_cell(row.get("skip_reason")).lower()
    readiness = clean_cell(row.get("scraping_readiness")).lower()
    exclude_reason = clean_cell(row.get("exclude_reason")).lower()
    combined = " ".join([final_status, diagnostic, category, skip_reason, readiness, exclude_reason])
    if not website:
        return True, "skipped_missing_website"
    if "missing_url" in combined or "sin_url" in combined:
        return True, "skipped_missing_website"
    if "domain_down" in combined or "dns_error" in combined or "dominio_caido" in combined:
        return True, "skipped_domain_down"
    if "prohibited" in combined or "zonaprop" in combined or "argenprop" in combined or "properati" in combined:
        return True, "skipped_prohibited"
    if is_prohibited_url(website) or is_prohibited_url(listing):
        return True, "skipped_prohibited"
    if norm_bool(row.get("exclude_from_scraping")) and any(
        token in combined for token in ["prohibited", "missing_url", "domain_down", "dominio_caido"]
    ):
        return True, "skipped_excluded"
    return False, ""


def source_needs_candidate(row: Dict[str, str]) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    final_status = clean_cell(row.get("final_status")).lower()
    diagnostic = clean_cell(row.get("diagnostic_status")).lower()
    error_category = clean_cell(row.get("error_category")).lower()
    fix_family = clean_cell(row.get("recommended_fix_family")).lower()
    next_action = clean_cell(row.get("recommended_next_action")).lower()
    website = normalize_url(clean_cell(row.get("website_url")))
    listing = normalize_url(clean_cell(row.get("listing_url")), website)
    property_links = to_int(row.get("property_links_count"))
    http_status = to_int(row.get("http_status"))

    terms = " ".join([final_status, diagnostic, error_category, fix_family, next_action])
    for needle in ["needs_listing_url", "bad_listing_url", "missing_listing_url"]:
        if needle in terms:
            reasons.append(needle)
    if fix_family == "url":
        reasons.append("recommended_fix_family_url")
    if "fix_listing_url" in next_action:
        reasons.append("recommended_fix_listing_url")
    if website and listing and is_home_url(listing, website):
        reasons.append("listing_url_looks_home")
    if website and not listing and "missing_url" not in terms:
        reasons.append("missing_listing_url")
    if property_links == 0 and http_status in {0, 200} and any(x in terms for x in ["no_property_links", "cms_unknown", "url"]):
        reasons.append("active_no_property_links_possible_url")
    return bool(reasons), reasons


def merge_source(target: Dict[str, SourceRecord], row: Dict[str, str], reasons: Iterable[str]) -> None:
    source_id = clean_cell(row.get("source_id"))
    if not source_id:
        return
    skip, skip_reason = should_skip_row(row)
    if skip:
        return
    rec = target.get(source_id)
    if rec is None:
        rec = SourceRecord(source_id=source_id)
        target[source_id] = rec
    rec.source_name = rec.source_name or clean_cell(row.get("source_name"))
    rec.website_url = rec.website_url or clean_cell(row.get("website_url"))
    rec.current_listing_url = rec.current_listing_url or clean_cell(row.get("listing_url"))
    rec.reasons.update(reasons)
    rec.row.update({k: v for k, v in row.items() if v not in (None, "")})
    rec.estimated_property_yield = max(
        rec.estimated_property_yield,
        to_int(row.get("estimated_property_yield")),
        to_int(row.get("properties_detected")),
        to_int(row.get("property_links_count")),
    )


def load_sources(input_source_results: Path, input_cms_proposal: Path) -> Tuple[List[SourceRecord], Dict[str, int]]:
    sources: Dict[str, SourceRecord] = {}
    input_counts: Counter[str] = Counter()

    source_rows = read_csv(input_source_results)
    for row in source_rows:
        needed, reasons = source_needs_candidate(row)
        if needed:
            merge_source(sources, row, reasons + ["source_results"])
            input_counts["source_results_candidates"] += 1

    sibling_full = input_source_results.parent
    for name, reason in [
        ("requires_listing_url_fix.csv", "requires_listing_url_fix_csv"),
        ("failed_sources.csv", "failed_sources_url_related"),
    ]:
        for row in read_csv(sibling_full / name):
            terms = " ".join(
                clean_cell(row.get(k)).lower()
                for k in ["final_status", "error_category", "recommended_fix_family", "recommended_next_action"]
            )
            if name == "requires_listing_url_fix.csv" or any(
                token in terms for token in ["url", "bad_listing_url", "missing_listing_url", "no_property_links"]
            ):
                merge_source(sources, row, [reason])
                input_counts[reason] += 1

    cms_rows = read_csv(input_cms_proposal)
    for row in cms_rows:
        reasons = []
        if norm_bool(row.get("requires_listing_url_fix")):
            reasons.append("cms_requires_listing_url_fix")
        if clean_cell(row.get("recommended_fix_family")).lower() == "url":
            reasons.append("cms_recommended_url")
        if reasons:
            merge_source(sources, row, reasons + ["cms_strategy_proposal"])
            input_counts["cms_strategy_candidates"] += 1

    listing_problem = input_cms_proposal.parent / "listing_url_problem_candidates.csv"
    for row in read_csv(listing_problem):
        merge_source(sources, row, ["listing_url_problem_candidates_csv"])
        input_counts["listing_url_problem_candidates_csv"] += 1

    return list(sources.values()), dict(input_counts)


def analyze_source(src: SourceRecord, timeout: float) -> Tuple[SourceRecord, List[CandidateResult], Dict[str, Any]]:
    session = make_session()
    try:
        website = normalize_url(src.website_url)
        current = normalize_url(src.current_listing_url, website)
        diagnostics: Dict[str, Any] = {
            "source_id": src.source_id,
            "source_name": src.source_name,
            "website_url": website,
            "current_listing_url": current,
            "skip": "",
        }

        if not website:
            diagnostics["skip"] = "skipped_missing_website"
            return src, [], diagnostics
        if is_prohibited_url(website) or is_prohibited_url(current):
            diagnostics["skip"] = "skipped_prohibited"
            return src, [], diagnostics

        home = fetch(session, website, timeout)
        if home.status is None:
            diagnostics["skip"] = "skipped_domain_down"
            diagnostics["home_error"] = home.error
            return src, [], diagnostics
        if home.status >= 500:
            diagnostics["skip"] = "skipped_domain_down"
            diagnostics["home_status"] = home.status
            return src, [], diagnostics
        if home.status in {401, 403, 404, 410}:
            diagnostics["skip"] = "skipped_domain_down"
            diagnostics["home_status"] = home.status
            return src, [], diagnostics

        links = extract_links(home.final_url or website, home.text)
        candidates: Dict[str, str] = {}

        if current:
            candidates[canonical_url(current)] = "current"
        link_candidates = candidate_paths_from_links(website, links)
        for url, source in link_candidates:
            candidates.setdefault(canonical_url(url), source)

        # Probe all priority common routes, and only add the tail routes when no
        # strong internal-link candidates were found. This keeps PR-BE-URL-06
        # full-source, but prevents pathological 60+ request sites.
        common_paths: Sequence[str] = []
        if len(link_candidates) == 0:
            common_paths = COMMON_LISTING_PATHS
        elif len(link_candidates) <= 2:
            common_paths = PRIORITY_COMMON_LISTING_PATHS[:8]
        for path in common_paths:
            url = urllib.parse.urljoin(website.rstrip("/") + "/", path.lstrip("/"))
            candidates.setdefault(canonical_url(url), "common_path")
        for url in sitemap_urls(session, website, timeout):
            candidates.setdefault(canonical_url(url), "sitemap")

        ordered = sorted(
            candidates.items(),
            key=lambda item: (
                {"menu": 0, "current": 1, "sitemap": 2, "footer": 3, "internal_link": 4, "common_path": 5}.get(item[1], 9),
                len(item[0]),
            ),
        )
        ordered = ordered[:18]
        diagnostics["candidate_url_count"] = len(ordered)

        results: List[CandidateResult] = []
        for url, detected_from in ordered:
            if is_prohibited_url(url):
                continue
            if not same_site(url, website):
                continue
            res = fetch(session, url, timeout)
            scored = score_candidate(src, url, detected_from, res, website, current, len(ordered))
            results.append(scored)
            if (
                scored.score >= 85
                and scored.property_links_count >= 3
                and not scored.is_homepage
                and not scored.is_property_detail
            ):
                break

        if not results:
            diagnostics["skip"] = "no_candidate_found"

        return src, results, diagnostics
    finally:
        try:
            session.close()
        except Exception:
            pass


OUTPUT_FIELDS = [
    "source_id",
    "source_name",
    "website_url",
    "current_listing_url",
    "proposed_listing_url",
    "confidence",
    "score",
    "final_category",
    "http_status",
    "final_url_after_redirect",
    "evidence",
    "detected_from",
    "candidate_url_count",
    "property_links_count",
    "property_links_sample",
    "has_price_signals",
    "has_operation_signals",
    "has_property_type_signals",
    "has_pagination",
    "requires_playwright",
    "is_homepage",
    "is_property_detail",
    "is_prohibited",
    "estimated_property_yield",
    "recommended_action",
    "requires_db_change_later",
    "risk",
    "notes",
]


def candidate_to_row(c: CandidateResult) -> Dict[str, Any]:
    return {
        "source_id": c.source_id,
        "source_name": c.source_name,
        "website_url": c.website_url,
        "current_listing_url": c.current_listing_url,
        "proposed_listing_url": c.candidate_url,
        "confidence": c.confidence,
        "score": c.score,
        "final_category": c.final_category,
        "http_status": c.http_status,
        "final_url_after_redirect": c.final_url_after_redirect,
        "evidence": c.evidence,
        "detected_from": c.detected_from,
        "candidate_url_count": c.candidate_url_count,
        "property_links_count": c.property_links_count,
        "property_links_sample": c.property_links_sample,
        "has_price_signals": c.has_price_signals,
        "has_operation_signals": c.has_operation_signals,
        "has_property_type_signals": c.has_property_type_signals,
        "has_pagination": c.has_pagination,
        "requires_playwright": c.requires_playwright,
        "is_homepage": c.is_homepage,
        "is_property_detail": c.is_property_detail,
        "is_prohibited": c.is_prohibited,
        "estimated_property_yield": c.estimated_property_yield,
        "recommended_action": c.recommended_action,
        "requires_db_change_later": c.requires_db_change_later,
        "risk": c.risk,
        "notes": c.notes,
    }


def pick_best(source_id: str, candidates: List[CandidateResult]) -> CandidateResult:
    valid = [
        c
        for c in candidates
        if not c.is_prohibited and not c.is_property_detail and not c.is_homepage
    ]
    pool = valid or [c for c in candidates if not c.is_prohibited] or candidates
    if not pool:
        raise ValueError(f"no candidates for {source_id}")
    return sorted(
        pool,
        key=lambda c: (
            c.score,
            c.property_links_count,
            1 if c.has_price_signals else 0,
            1 if c.detected_from in {"menu", "sitemap"} else 0,
            -len(c.candidate_url),
        ),
        reverse=True,
    )[0]


def source_no_candidate_row(src: SourceRecord, diagnostics: Dict[str, Any]) -> Dict[str, Any]:
    website = normalize_url(src.website_url)
    current = normalize_url(src.current_listing_url, website)
    return {
        "source_id": src.source_id,
        "source_name": src.source_name,
        "website_url": website,
        "current_listing_url": current,
        "proposed_listing_url": "",
        "confidence": "none",
        "score": 0,
        "final_category": diagnostics.get("skip") or "no_candidate_found",
        "http_status": diagnostics.get("home_status", ""),
        "final_url_after_redirect": "",
        "evidence": diagnostics.get("home_error", ""),
        "detected_from": "",
        "candidate_url_count": diagnostics.get("candidate_url_count", 0),
        "property_links_count": 0,
        "property_links_sample": "",
        "has_price_signals": False,
        "has_operation_signals": False,
        "has_property_type_signals": False,
        "has_pagination": False,
        "requires_playwright": False,
        "is_homepage": False,
        "is_property_detail": False,
        "is_prohibited": False,
        "estimated_property_yield": src.estimated_property_yield,
        "recommended_action": "manual_review",
        "requires_db_change_later": False,
        "risk": "high",
        "notes": f"reasons={','.join(sorted(src.reasons))}",
    }


def validation_errors(best_rows: List[Dict[str, Any]], candidate_rows: List[Dict[str, Any]]) -> List[str]:
    errors = []
    seen = Counter(row["source_id"] for row in best_rows)
    dupes = [sid for sid, n in seen.items() if n > 1]
    if dupes:
        errors.append(f"duplicated_source_id_in_best={len(dupes)}")
    for row in best_rows:
        sid = row.get("source_id")
        if not row.get("final_category"):
            errors.append(f"missing_final_category source_id={sid}")
        if row.get("score") in {"", None} or row.get("confidence") in {"", None}:
            errors.append(f"missing_score_confidence source_id={sid}")
        if row.get("confidence") == "high" and not row.get("evidence"):
            errors.append(f"high_without_evidence source_id={sid}")
        if str(row.get("is_prohibited")).lower() == "true" and str(row.get("requires_db_change_later")).lower() == "true":
            errors.append(f"prohibited_marked_for_update source_id={sid}")
        if str(row.get("is_property_detail")).lower() == "true" and str(row.get("requires_db_change_later")).lower() == "true":
            errors.append(f"detail_marked_for_update source_id={sid}")
        if str(row.get("is_homepage")).lower() == "true" and str(row.get("requires_db_change_later")).lower() == "true":
            errors.append(f"homepage_marked_for_update source_id={sid}")
    for row in candidate_rows:
        if str(row.get("is_prohibited")).lower() == "true" and row.get("recommended_action") != "skip":
            errors.append(f"prohibited_candidate_not_skipped source_id={row.get('source_id')}")
    return errors


def md_table(rows: Sequence[Dict[str, Any]], fields: Sequence[str], limit: int = 20) -> str:
    rows = list(rows)[:limit]
    if not rows:
        return "_Sin filas._\n"
    out = ["| " + " | ".join(fields) + " |", "| " + " | ".join(["---"] * len(fields)) + " |"]
    for row in rows:
        vals = []
        for f in fields:
            val = str(row.get(f, ""))
            val = val.replace("|", "\\|").replace("\n", " ")
            if len(val) > 90:
                val = val[:87] + "..."
            vals.append(val)
        out.append("| " + " | ".join(vals) + " |")
    return "\n".join(out) + "\n"


def write_docs(out: Path, best_rows: List[Dict[str, Any]], all_candidate_rows: List[Dict[str, Any]], input_counts: Dict[str, int], validation: List[str]) -> None:
    counts = Counter(row["final_category"] for row in best_rows)
    confidence = Counter(row["confidence"] for row in best_rows)
    high_found = [r for r in best_rows if r.get("final_category") == "found_high_confidence"]
    medium_found = [r for r in best_rows if r.get("final_category") == "found_medium_confidence"]
    low_found = [r for r in best_rows if r.get("final_category") == "found_low_confidence"]
    no_candidate_rows = [r for r in best_rows if r.get("final_category") == "no_candidate_found" or r.get("confidence") == "none"]
    current_bad_rows = [
        r
        for r in best_rows
        if "bad_listing_url" in str(r.get("notes", ""))
        or r.get("final_category") in {"homepage_as_listing", "property_detail_as_listing"}
    ]
    updateable = [r for r in best_rows if str(r.get("requires_db_change_later")).lower() == "true" and r.get("confidence") == "high"]
    manual = [
        r
        for r in best_rows
        if r.get("recommended_action") in {"manual_review", "manual_review_then_update_later", "confirm_with_playwright_later"}
    ]
    top = sorted(
        [r for r in best_rows if str(r.get("requires_db_change_later")).lower() == "true"],
        key=lambda r: (to_int(r.get("estimated_property_yield")), to_int(r.get("score"))),
        reverse=True,
    )[:50]
    impact_by_conf = defaultdict(int)
    for row in best_rows:
        impact_by_conf[row["confidence"]] += to_int(row.get("estimated_property_yield"))

    summary = f"""# PR-BE-URL-06 — Listing URL detection proposal

_Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}_

## Scope
- Total candidatas analizadas: **{len(best_rows)}**
- Candidate URLs evaluadas: **{len(all_candidate_rows)}**
- Inputs usados: `{json.dumps(input_counts, ensure_ascii=False, sort_keys=True)}`
- DB writes ejecutados: **0**
- Publish/scraping productivo/runs/push/deploy/frontend: **0**

## Resultados principales
1. Total candidatas analizadas: **{len(best_rows)}**
2. High confidence: **{len(high_found)}**
3. Medium confidence: **{len(medium_found)}**
4. Low confidence: **{len(low_found)}**
5. No candidate: **{len(no_candidate_rows)}**
6. Current listing URL correcta: **{counts['current_listing_url_ok']}**
7. Home como listing: **{counts['homepage_as_listing']}**
8. Listing URL mala: **{len(current_bad_rows)}**
9. Requieren Playwright para confirmar: **{counts['requires_playwright_to_confirm']}**
10. Impacto potencial por grupo: high={impact_by_conf['high']}, medium={impact_by_conf['medium']}, low={impact_by_conf['low']}
11. Top 50 fixes por impacto: ver tabla abajo y `top_url_fixes_by_impact.csv`
12. Podrian actualizarse automaticamente despues: **{len(updateable)}** (solo high confidence)
13. Requieren revision manual: **{len(manual)}**
14. Riesgos: falsos positivos en rutas de detalle, sitios JS que no renderizan en HTTP estatico, redirecciones a home, CMS custom con cards no semanticas.
15. Validacion necesaria antes de cualquier UPDATE: dry-run SQL, backup, muestreo manual, confirmacion HTTP/Playwright para medium/low, re-scrape controlado.
16. Primer proximo paso recomendado: revisar `high_confidence_proposals.csv`, validar top 50 manualmente y preparar una fase DB dry-run separada.

## Distribucion por categoria final
{md_table([{'category': k, 'count': v} for k, v in counts.most_common()], ['category', 'count'], 40)}

## Top 50 fixes por impacto
{md_table(top, ['source_id', 'source_name', 'current_listing_url', 'proposed_listing_url', 'confidence', 'score', 'estimated_property_yield', 'evidence'], 50)}

## Validaciones obligatorias
{md_table([{'validation': e} for e in validation] if validation else [{'validation': 'OK - no blocking validation errors'}], ['validation'], 50)}
"""
    (out / "listing_url_detection_summary.md").write_text(summary, encoding="utf-8")

    (out / "recommended_db_backfill_later.md").write_text(
        """# Recommended DB backfill later — DO NOT RUN NOW

No DB update was executed in PR-BE-URL-06.

## Column to update later
- `url_listado` only.

## Update criteria
- Only sources with `confidence=high`.
- `score >= 75`.
- `requires_db_change_later=true`.
- `is_prohibited=false`.
- `is_homepage=false`.
- `is_property_detail=false`.
- `proposed_listing_url` responds 2xx/3xx and has evidence.

## Medium confidence
Medium confidence must go through manual review or Playwright confirmation before any DB update.

## Backup before update
- Export current `source_id`, `nombre`, `web`, `url_listado`, `cms_detectado`, `estrategia_scraping`, `diagnostic_status`, `scraping_readiness`.
- Save the exact proposal CSV used for the update.

## Dry-run SQL preview (commented, not executed)
```sql
-- SELECT i.id, i.nombre, i.url_listado AS old_url_listado, p.proposed_listing_url
-- FROM inmobiliarias_main i
-- JOIN temp_listing_url_proposals p ON p.source_id = i.id
-- WHERE p.confidence = 'high'
--   AND p.score >= 75
--   AND p.is_homepage = false
--   AND p.is_property_detail = false
--   AND p.is_prohibited = false;
```

## Rollback
- Restore `url_listado` from the backup table/export for the affected `source_id`.

## Success measurement
- Run a small dry-run scrape/readiness check against updated high-confidence rows.
- Compare `property_links_count`, `properties_detected`, and error family before/after.
- Promote only if bad_listing_url/no_property_links decreases without increasing parser errors disproportionately.
""",
        encoding="utf-8",
    )

    (out / "recommended_code_changes.md").write_text(
        """# Recommended code changes — proposal only

## Add reusable listing URL detection
Keep `scripts/detect_listing_url_candidates.py` as an offline proposal tool first. Later, extract helpers into a small module if the results are strong.

## Pipeline integration later
- Do not run inside productive scraping by default.
- Add an explicit diagnostic phase that can read home/menu/footer/sitemap/common paths.
- Write only proposals until reviewed.

## Heuristics to keep
- Normalize website and current listing URL.
- Prefer menu/sitemap/internal links over brute-force common paths.
- Score listing evidence: property links, cards, prices, operations, property types, pagination, JSON-LD.
- Reject home, contact/about pages, property detail pages and prohibited portals.

## Playwright use
Use Playwright only as a confirmation path for medium/low cases or JS-heavy sites. Do not make it the default for all sources until cost and runtime are measured.

## Scrapers productivos
Do not change productive scrapers in this phase. Use this proposal to decide which URLs deserve a DB dry-run/backfill later.
""",
        encoding="utf-8",
    )

    (out / "risk_assessment.md").write_text(
        """# Risk assessment

## Main risks
- False positive: a candidate URL is an individual property detail, not a listing.
- False positive: candidate redirects to home while preserving a listing-looking path.
- False negative: JS/SPA listing needs Playwright to reveal cards.
- Prohibited portal leakage through external links.
- Sites with generic terms like "ventas" but no real property inventory.
- Inflated `estimated_property_yield` can distort impact prioritization.

## Mitigations
- Never auto-update medium/low confidence.
- Keep prohibited, homepage and detail candidates out of updateable rows.
- Manually review top 50 by impact.
- Confirm medium/low with Playwright later.
- Run DB dry-run and small scrape validation before any real update.
""",
        encoding="utf-8",
    )

    (out / "validation_plan.md").write_text(
        """# Validation plan

## Before DB dry-run
1. Review `high_confidence_proposals.csv`.
2. Manually open top 50 by impact.
3. Confirm no proposed URL points to home, contact/about, prohibited portals or detail pages.
4. Confirm evidence includes at least one of: property links, prices, operation/type signals, pagination, menu or sitemap.

## DB dry-run phase later
1. Import proposal into a temporary table or local dataframe only.
2. Produce SELECT-only diff of old vs proposed `url_listado`.
3. Export backup before any UPDATE.
4. Run a tiny controlled scraper dry-run against selected URLs.

## After real update later
1. Re-run coverage for updated sources only.
2. Compare `bad_listing_url`, `no_property_links`, `properties_detected`, `properties_parsed`.
3. Roll back rows that regress or redirect to home/detail/prohibited portals.
""",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect listing URL candidates as proposal only")
    parser.add_argument("--input-source-results", required=True)
    parser.add_argument("--input-cms-proposal", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--commit", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.commit:
        raise SystemExit("--commit is not authorized in PR-BE-URL-06")
    if args.workers <= 0:
        raise SystemExit("--workers must be > 0")
    if args.timeout <= 0:
        raise SystemExit("--timeout must be > 0")

    input_source_results = Path(args.input_source_results)
    input_cms_proposal = Path(args.input_cms_proposal)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    sources, input_counts = load_sources(input_source_results, input_cms_proposal)
    sources = sorted(sources, key=lambda s: to_int(s.source_id))
    print(f"sources_to_analyze={len(sources)}")
    print(f"input_counts={json.dumps(input_counts, ensure_ascii=False, sort_keys=True)}")

    all_candidate_results: List[CandidateResult] = []
    best_rows: List[Dict[str, Any]] = []
    skipped_rows: List[Dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(analyze_source, src, args.timeout): src for src in sources}
        done = 0
        for fut in as_completed(futures):
            src = futures[fut]
            done += 1
            if done % 25 == 0 or done == len(futures):
                print(f"progress={done}/{len(futures)}")
            try:
                _src, candidates, diagnostics = fut.result()
            except Exception as exc:
                skipped_rows.append(
                    source_no_candidate_row(
                        src,
                        {"skip": "manual_review", "home_error": f"{type(exc).__name__}: {exc}"},
                    )
                )
                continue
            if candidates:
                all_candidate_results.extend(candidates)
                best = pick_best(src.source_id, candidates)
                best_rows.append(candidate_to_row(best))
            else:
                skipped_rows.append(source_no_candidate_row(src, diagnostics))

    best_rows.extend(skipped_rows)
    best_rows = sorted(best_rows, key=lambda r: to_int(r["source_id"]))
    candidate_rows = sorted(
        [candidate_to_row(c) for c in all_candidate_results],
        key=lambda r: (to_int(r["source_id"]), -to_int(r["score"])),
    )
    validation = validation_errors(best_rows, candidate_rows)

    write_csv(out / "listing_url_candidates.csv", candidate_rows, OUTPUT_FIELDS)
    write_jsonl(out / "listing_url_candidates.jsonl", candidate_rows)
    write_csv(out / "best_listing_url_proposals.csv", best_rows, OUTPUT_FIELDS)

    high = [r for r in best_rows if r["confidence"] == "high" and r["final_category"] == "found_high_confidence"]
    medium = [r for r in best_rows if r["confidence"] == "medium" and r["final_category"] == "found_medium_confidence"]
    low = [r for r in best_rows if r["confidence"] == "low" and r["final_category"] == "found_low_confidence"]
    no_candidate = [r for r in best_rows if r["final_category"] == "no_candidate_found" or r["confidence"] == "none"]
    current_ok = [r for r in best_rows if r["final_category"] == "current_listing_url_ok"]
    current_bad = [
        r
        for r in best_rows
        if "bad_listing_url" in str(r.get("notes", "")) or r["final_category"] in {"homepage_as_listing", "property_detail_as_listing"}
    ]
    homepage = [r for r in best_rows if r["final_category"] == "homepage_as_listing"]
    playwright = [r for r in best_rows if r["final_category"] == "requires_playwright_to_confirm" or str(r["requires_playwright"]).lower() == "true"]
    manual = [
        r
        for r in best_rows
        if r["recommended_action"] in {"manual_review", "manual_review_then_update_later", "confirm_with_playwright_later"}
    ]
    top = sorted(
        [r for r in best_rows if str(r.get("requires_db_change_later")).lower() == "true"],
        key=lambda r: (to_int(r.get("estimated_property_yield")), to_int(r.get("score"))),
        reverse=True,
    )[:50]

    write_csv(out / "high_confidence_proposals.csv", high, OUTPUT_FIELDS)
    write_csv(out / "medium_confidence_proposals.csv", medium, OUTPUT_FIELDS)
    write_csv(out / "low_confidence_proposals.csv", low, OUTPUT_FIELDS)
    write_csv(out / "no_candidate_found.csv", no_candidate, OUTPUT_FIELDS)
    write_csv(out / "current_listing_url_ok.csv", current_ok, OUTPUT_FIELDS)
    write_csv(out / "current_listing_url_bad.csv", current_bad, OUTPUT_FIELDS)
    write_csv(out / "homepage_as_listing.csv", homepage, OUTPUT_FIELDS)
    write_csv(out / "requires_playwright_to_confirm.csv", playwright, OUTPUT_FIELDS)
    write_csv(out / "manual_review.csv", manual, OUTPUT_FIELDS)
    write_csv(out / "top_url_fixes_by_impact.csv", top, OUTPUT_FIELDS)

    write_docs(out, best_rows, candidate_rows, input_counts, validation)

    counts = Counter(row["final_category"] for row in best_rows)
    conf = Counter(row["confidence"] for row in best_rows)
    print(f"total_analyzed={len(best_rows)}")
    print(f"candidate_urls={len(candidate_rows)}")
    print(f"high_confidence={conf['high']}")
    print(f"medium_confidence={conf['medium']}")
    print(f"low_confidence={conf['low']}")
    print(f"no_candidate={len(no_candidate)}")
    print(f"current_ok={len(current_ok)}")
    print(f"homepage_as_listing={len(homepage)}")
    print(f"current_bad={len(current_bad)}")
    print(f"requires_playwright={len(playwright)}")
    print(f"auto_update_later_high={len(high)}")
    print(f"manual_review={len(manual)}")
    print(f"validation_errors={len(validation)}")
    if validation:
        for err in validation[:20]:
            print(f"validation_error={err}")
    print(f"out={out}")


if __name__ == "__main__":
    main()
