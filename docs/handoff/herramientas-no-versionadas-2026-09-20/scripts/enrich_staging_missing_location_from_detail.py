#!/usr/bin/env python
"""Enrich propiedades_staging rows that have missing_location by scraping their detail page.

Strategies (in order, no Playwright first):
  1. JSON-LD (application/ld+json)
  2. Meta tags (og:city, og:region, geo.*, article:section, etc.)
  3. Breadcrumbs (nav[aria-label=breadcrumb], .breadcrumb, itemtype=BreadcrumbList)
  4. Microdata (itemtype=Place, PostalAddress)
  5. Visible text inference via normalize_location_fields (title + description + url)
  6. Playwright (only if --allow-playwright and static HTML found nothing)

Default mode: dry-run (no writes to Neon). Pass --commit to apply high-confidence updates.

Safety:
  - Never writes Supabase.
  - Never touches .env, publish_queue, or frontend/.
  - Only updates propiedades_staging.ciudad/provincia/barrio/direccion_normalizada
    when --commit and confidence='high'.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# --- Optional pipeline imports ---
try:
    from scraper.scraper_propiedades import (
        normalize_location_fields as pipeline_normalize_location,
        clean_property_images as pipeline_clean_images,
        _normalizar_precio_detalle as pipeline_price_from_text,
    )
except Exception:
    pipeline_normalize_location = None  # type: ignore
    pipeline_clean_images = None        # type: ignore
    pipeline_price_from_text = None     # type: ignore

try:
    from bs4 import BeautifulSoup  # type: ignore
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

try:
    import requests as _requests_mod  # type: ignore
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
from scraper.network_security import secure_get

from scripts.validate_raw_properties import internal_db_config, connect_internal_db

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M")

CAMPAIGN_PREFIXES = (
    "internal_batch_20260604_19",
    "internal_batch_20260604_20",
    "internal_batch_20260604_21",
    "internal_batch_20260604_22",
    "internal_batch_20260604_23",
    "internal_batch_20260605_00",
    "internal_batch_20260605_08",
    "internal_batch_20260605_10",
)

PROHIBITED_DOMAINS_RE = re.compile(
    r"(^|\.)(?:zonaprop|argenprop)\.com\.ar$", re.I
)

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
HTTP_TIMEOUT = 15
RATE_LIMIT_SECS = 1.5   # min seconds between requests to same domain

# --- Location confidence thresholds ---
# Sources ranked high → low
HIGH_SOURCES = {"json_ld", "breadcrumb_list", "microdata"}
MEDIUM_SOURCES = {"meta_og", "meta_geo", "breadcrumb_text", "visible_heading"}
LOW_SOURCES = {"title_inference", "description_inference"}

GARBAGE_ADDR = [
    "contacto", "oficinas", "telefono", "teléfono", "whatsapp",
    "email", "www.", "http", "inmobiliaria", "consultar precio",
    "superficie", "expensas", "matricula", "cucicba",
]

# Common non-location breadcrumb items to discard
CRUMB_STOPWORDS = {
    "inicio", "home", "propiedades", "inmuebles", "venta",
    "alquiler", "alquileres", "ventas", "comprar", "buscar",
    "contacto", "nosotros", "quiénes somos", "quienes somos",
    "servicios", "nuestras propiedades", "todas las propiedades",
    "listado", "listados", "resultados", "mapa", "principal",
    "inmobiliaria", "bienes raices", "bienes raíces",
    "detalle", "ficha", "ver detalle", "ver ficha",
    "detalle del inmueble", "detalle de la propiedad",
    "detalle del inmueble / propiedad", "descripcion",
    "descripción", "galería", "galeria",
    "detalle de este departamento en venta",
    "detalle de este departamento en alquiler",
    "detalle de esta propiedad en venta",
    "detalle de esta casa en venta",
    "detalle de este terreno",
    "ver propiedad venta.asp", "prop detail.php",
    "detalle de este local", "propiedad", "property",
    "real estate", "nuestros inmuebles", "nuestro catálogo",
}

AR_PROVINCES = {
    "buenos aires", "córdoba", "cordoba", "santa fe", "mendoza",
    "tucumán", "tucuman", "entre ríos", "entre rios", "salta",
    "misiones", "chaco", "corrientes", "santiago del estero",
    "san juan", "jujuy", "río negro", "rio negro", "neuquén", "neuquen",
    "formosa", "chubut", "san luis", "catamarca", "la rioja",
    "la pampa", "santa cruz", "tierra del fuego",
    "ciudad autónoma de buenos aires", "caba", "capital federal",
}


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return ""


def _clean(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = re.sub(r"\s+", " ", str(v)).strip()
    return s or None


def _is_garbage(text: Optional[str]) -> bool:
    if not text:
        return True
    lo = text.lower()
    return any(p in lo for p in GARBAGE_ADDR)


def _looks_like_province(text: str) -> bool:
    return text.lower().strip() in AR_PROVINCES


def _make_session() -> Any:
    if not HAS_REQUESTS:
        return None
    s = _requests_mod.Session()
    s.headers.update(HTTP_HEADERS)
    return s


def _fetch_html(url: str, session: Any, timeout: int = HTTP_TIMEOUT) -> Optional[str]:
    if session is None:
        return None
    try:
        r = secure_get(session, url, timeout=(8, timeout))
        if r.status_code == 200:
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text
    except Exception:
        pass
    return None


# --- Extraction strategies ---

def _extract_json_ld(soup: Any, url: str) -> Optional[Dict[str, Any]]:
    """Try to get address/location from JSON-LD scripts."""
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            # Look for address in RealEstateListing, Residence, Place, etc.
            addr = item.get("address") or {}
            if isinstance(addr, str):
                addr = {"streetAddress": addr}
            loc = item.get("location") or {}
            if isinstance(loc, dict):
                loc_addr = loc.get("address") or {}
                if isinstance(loc_addr, dict):
                    for k, v in loc_addr.items():
                        addr.setdefault(k, v)

            city = _clean(
                addr.get("addressLocality")
                or addr.get("city")
                or item.get("addressLocality")
            )
            province = _clean(
                addr.get("addressRegion")
                or addr.get("region")
                or item.get("addressRegion")
            )
            street = _clean(
                addr.get("streetAddress")
                or addr.get("address")
            )
            barrio = _clean(addr.get("neighborhood") or addr.get("barrio"))

            # BreadcrumbList as location source
            if item.get("@type") == "BreadcrumbList":
                crumbs = item.get("itemListElement") or []
                texts = [
                    _clean(c.get("name") or (c.get("item") or {}).get("name"))
                    for c in crumbs if isinstance(c, dict)
                ]
                texts = [t for t in texts if t]
                for t in reversed(texts):
                    if _looks_like_province(t) and not province:
                        province = t
                    elif not city and not _looks_like_province(t) and _is_plausible_location_name(t):
                        city = t

            if city or province:
                return {
                    "ciudad": city, "provincia": province,
                    "barrio": barrio, "direccion": street,
                    "source": "json_ld",
                }
    return None


def _is_crumb_stopword(text: str) -> bool:
    lo = text.lower().strip()
    return lo in CRUMB_STOPWORDS or lo.startswith("detalle") or lo.startswith("ficha")


def _is_plausible_location_name(text: str) -> bool:
    """True if the text looks like an actual city/province name."""
    if not text or len(text) < 3 or len(text) > 60:
        return False
    lo = text.lower().strip()
    if _is_crumb_stopword(text):
        return False
    if _is_garbage(text):
        return False
    # Must start with uppercase letter (proper noun)
    if not text[0].isupper():
        return False
    # Must not be all digits
    if text.strip().isdigit():
        return False
    # Reject if it contains too many verbs/action words
    bad_words = {"venta", "alquiler", "compra", "ver", "ver ", "en venta", "en alquiler", "#"}
    for bw in bad_words:
        if bw in lo:
            return False
    return True


def _extract_breadcrumb(soup: Any) -> Optional[Dict[str, Any]]:
    """Extract location from breadcrumb nav, filtering navigation stopwords."""
    crumb_texts: List[str] = []

    # Try itemtype BreadcrumbList first
    bclist = soup.find(attrs={"itemtype": re.compile(r"BreadcrumbList", re.I)})
    if bclist:
        items = bclist.find_all(attrs={"itemprop": re.compile(r"name|item", re.I)})
        crumb_texts = [_clean(i.get_text()) for i in items if _clean(i.get_text())]

    if not crumb_texts:
        bc = (
            soup.find("nav", {"aria-label": re.compile(r"breadcrumb", re.I)})
            or soup.find(class_=re.compile(r"\bbreadcrumb\b", re.I))
        )
        if bc:
            crumb_texts = [_clean(a.get_text()) for a in bc.find_all("a") if _clean(a.get_text())]
            for tag in bc.find_all(["li", "span"]):
                t = _clean(tag.get_text())
                if t and t not in crumb_texts:
                    crumb_texts.append(t)

    if not crumb_texts:
        return None

    city, province = None, None
    for t in reversed(crumb_texts):
        if not t:
            continue
        if _looks_like_province(t) and not province:
            province = t
        elif not city and not _looks_like_province(t) and _is_plausible_location_name(t):
            city = t

    if city or province:
        return {"ciudad": city, "provincia": province, "barrio": None, "direccion": None, "source": "breadcrumb_list"}
    return None


def _parse_ar_region_code(text: Optional[str]) -> Optional[str]:
    """Convert ISO 3166-2 codes like 'AR-B' or 'AR-Buenos Aires' to plain name."""
    if not text:
        return None
    # Strip "AR-" prefix
    cleaned = re.sub(r"^AR-", "", text.strip(), flags=re.I).strip()
    if not cleaned or len(cleaned) <= 2:
        return None  # discard short codes like "B", "X", "M"
    return cleaned


def _extract_meta(soup: Any) -> Optional[Dict[str, Any]]:
    """Extract location from meta / OG tags, parsing ISO region codes."""
    def _meta(name: str, attr: str = "name") -> Optional[str]:
        tag = soup.find("meta", {attr: re.compile(name, re.I)})
        return _clean(tag.get("content")) if tag else None

    city_raw = (
        _meta("og:locality", "property")
        or _meta("article:locality", "property")
        or _meta("city")
        or _meta("locality")
    )
    province_raw = (
        _meta("og:region", "property")
        or _meta("article:region", "property")
        or _meta("geo.region")
        or _meta("region")
        or _meta("province")
        or _meta("estado")
    )
    street = _meta("og:street-address", "property") or _meta("street.address")

    city = _parse_ar_region_code(city_raw) or city_raw
    province = _parse_ar_region_code(province_raw) or province_raw

    # Filter garbage
    if _is_garbage(city):
        city = None
    if _is_garbage(province):
        province = None
    # Discard if they look the same and are not real location names
    if city and not _is_plausible_location_name(city):
        city = None
    if province and not _is_plausible_location_name(province) and not _looks_like_province(province or ""):
        province = None

    if city or province:
        return {"ciudad": city, "provincia": province, "barrio": None, "direccion": street, "source": "meta_og"}
    return None


def _extract_microdata(soup: Any) -> Optional[Dict[str, Any]]:
    """Extract from schema.org microdata."""
    addr_el = soup.find(attrs={"itemtype": re.compile(r"PostalAddress|Place", re.I)})
    if not addr_el:
        return None
    def _prop(name: str) -> Optional[str]:
        el = addr_el.find(attrs={"itemprop": name})
        return _clean(el.get_text()) if el else None

    city = _prop("addressLocality") or _prop("city")
    province = _prop("addressRegion") or _prop("region")
    street = _prop("streetAddress")
    if city or province:
        return {"ciudad": city, "provincia": province, "barrio": None, "direccion": street, "source": "microdata"}
    return None


def _extract_from_pipeline(titulo: str, descripcion: str, url: str) -> Optional[Dict[str, Any]]:
    """Use scraper pipeline's normalize_location_fields to infer from title/desc/url."""
    if not callable(pipeline_normalize_location):
        return None
    try:
        result = pipeline_normalize_location(
            titulo, None, None, None, None, "Argentina", url, descripcion
        )
    except Exception:
        return None
    if not isinstance(result, dict) or not result.get("location_normalized"):
        return None
    city = _clean(result.get("ciudad"))
    province = _clean(result.get("provincia"))
    if city or province:
        return {
            "ciudad": city, "provincia": province,
            "barrio": _clean(result.get("barrio")),
            "direccion": None,
            "source": "title_inference",
        }
    return None


def _extract_visible_heading(soup: Any) -> Optional[Dict[str, Any]]:
    """Look for visible location cues in h1/h2/address tags — strict matching only."""
    for tag in soup.find_all(["h1", "h2", "address"]):
        text = _clean(tag.get_text())
        if not text or len(text) < 8 or len(text) > 200:
            continue
        # Pattern: "en <CityName>, <Province>" or "en <City>"
        # Require: word boundary, then a proper noun (1-3 words), max 30 chars
        m = re.search(
            r"\ben\s+([A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+(?:\s+[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+){0,2})"
            r"(?:\s*,\s*([A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+(?:\s+[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+){0,2}))?",
            text
        )
        if m:
            city_cand = m.group(1).strip()
            prov_cand = (m.group(2) or "").strip()
            # Reject if candidate is a stopword or not plausible
            if not _is_plausible_location_name(city_cand):
                continue
            city = city_cand if not _looks_like_province(city_cand) else None
            province = prov_cand if _looks_like_province(prov_cand) else (city_cand if _looks_like_province(city_cand) else None)
            if city or province:
                return {
                    "ciudad": city, "provincia": province,
                    "barrio": None, "direccion": None,
                    "source": "visible_heading",
                }
    return None


def _assign_confidence(source: str) -> str:
    if source in HIGH_SOURCES:
        return "high"
    if source in MEDIUM_SOURCES:
        return "medium"
    return "low"


# Property-type words that should never appear in a clean city name
_PROPERTY_WORDS = re.compile(
    r"\b(lote|casa|depto|departamento|local|galpon|galpón|terreno|"
    r"barrio cerrado|country|chacra|quinta|duplex|ph|oficina|"
    r"venta|alquiler|compra|inmueble|propiedad|barrio)\b",
    re.I,
)


def _is_safe_city_name(text: str) -> bool:
    """Strict check that a city candidate is actually a city name, not a description."""
    if not text or len(text) > 30:
        return False
    if _property_words_in(text):
        return False
    if not _is_plausible_location_name(text):
        return False
    # Must not contain commas (those are usually "City, Province" or descriptions)
    if "," in text:
        return False
    return True


def _property_words_in(text: str) -> bool:
    return bool(_PROPERTY_WORDS.search(text or ""))


def enrich_one(
    row: Dict[str, Any],
    session: Any,
    allow_playwright: bool,
    domain_last_request: Dict[str, float],
    lock: Any,
) -> Dict[str, Any]:
    staging_id = row["staging_id"]
    url = row.get("url") or ""
    titulo = row.get("titulo") or ""
    descripcion = row.get("descripcion") or ""
    domain = _domain(url)

    base_result = {
        "staging_id": staging_id,
        "inmobiliaria_id": row.get("inmobiliaria_id"),
        "nombre": row.get("nombre") or "",
        "url": url,
        "dominio": domain,
        "titulo": titulo[:80],
        "ciudad_actual": row.get("ciudad") or "",
        "provincia_actual": row.get("provincia") or "",
        "barrio_actual": row.get("barrio") or "",
        "direccion_actual": row.get("direccion_normalizada") or "",
        "ciudad_propuesta": "",
        "provincia_propuesta": "",
        "barrio_propuesto": "",
        "direccion_propuesta": "",
        "fuente": "",
        "confidence": "",
        "aplicar": "no",
        "motivo": "",
        "precio_propuesto": "",
        "error": "",
    }

    if not url:
        base_result["motivo"] = "sin_url"
        base_result["error"] = "sin_url"
        return base_result

    if PROHIBITED_DOMAINS_RE.search(domain):
        base_result["motivo"] = "dominio_prohibido"
        return base_result

    # Rate limiting per domain
    with lock:
        last = domain_last_request.get(domain, 0.0)
        wait = RATE_LIMIT_SECS - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
        domain_last_request[domain] = time.time()

    # Fetch HTML
    html = _fetch_html(url, session)
    if not html:
        base_result["error"] = "http_error_or_timeout"
        base_result["motivo"] = "no_se_pudo_obtener_html"
        return base_result

    if not HAS_BS4:
        base_result["error"] = "bs4_not_installed"
        return base_result

    soup = BeautifulSoup(html, "html.parser")

    # Try each strategy in order
    location = (
        _extract_json_ld(soup, url)
        or _extract_breadcrumb(soup)
        or _extract_meta(soup)
        or _extract_microdata(soup)
        or _extract_visible_heading(soup)
        or _extract_from_pipeline(titulo, descripcion, url)
    )

    # Playwright fallback (only if enabled and nothing found)
    if not location and allow_playwright:
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=20000, wait_until="domcontentloaded")
                pw_html = page.content()
                browser.close()
            if pw_html:
                pw_soup = BeautifulSoup(pw_html, "html.parser")
                location = (
                    _extract_json_ld(pw_soup, url)
                    or _extract_breadcrumb(pw_soup)
                    or _extract_meta(pw_soup)
                    or _extract_microdata(pw_soup)
                    or _extract_visible_heading(pw_soup)
                )
                if location:
                    location["source"] = "playwright_" + location.get("source", "html")
        except Exception as exc:
            base_result["error"] = f"playwright_error: {str(exc)[:80]}"

    if not location:
        base_result["motivo"] = "no_location_found_in_detail_page"
        return base_result

    ciudad = _clean(location.get("ciudad")) or ""
    provincia = _clean(location.get("provincia")) or ""
    barrio = _clean(location.get("barrio")) or ""
    direccion = _clean(location.get("direccion")) or ""
    source = location.get("source", "unknown")
    confidence = _assign_confidence(source)

    # Reject garbage values
    if _is_garbage(ciudad):
        ciudad = ""
    if _is_garbage(provincia):
        provincia = ""

    if not ciudad and not provincia:
        base_result["motivo"] = "extracted_but_all_garbage"
        base_result["fuente"] = source
        return base_result

    # Only mark aplicar=yes for high confidence with verified clean city name
    city_safe = _is_safe_city_name(ciudad) if ciudad else False
    can_apply = (
        confidence == "high"
        and city_safe
        and source == "breadcrumb_list"  # only trust breadcrumb for auto-apply
    )
    motivo = (
        ""
        if can_apply
        else (
            f"city_too_long_or_has_property_words({len(ciudad)}chars)"
            if confidence == "high" and not city_safe
            else f"confidence={confidence}_needs_review"
        )
    )
    base_result.update({
        "ciudad_propuesta": ciudad,
        "provincia_propuesta": provincia,
        "barrio_propuesto": barrio,
        "direccion_propuesta": direccion,
        "fuente": source,
        "confidence": confidence,
        "aplicar": "yes" if can_apply else "no",
        "motivo": motivo,
    })
    return base_result


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich staging missing_location from detail pages (dry-run by default)")
    parser.add_argument("--limit", type=int, default=0, help="Max rows; 0=all")
    parser.add_argument("--workers", type=int, default=3, help="Parallel HTTP workers (1-5)")
    parser.add_argument("--allow-playwright", action="store_true", help="Use Playwright as fallback")
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="No writes to Neon (default)")
    parser.add_argument("--commit", action="store_true", help="Apply high-confidence updates to staging")
    parser.add_argument(
        "--domain-filter",
        default=None,
        help="Only process rows from this domain (e.g. pardoa.com). Restricts both query and commit.",
    )
    parser.add_argument(
        "--city-filter",
        default=None,
        help="Only commit rows where ciudad_propuesta == this value (e.g. 'Tres Arroyos').",
    )
    parser.add_argument(
        "--input-csv",
        type=Path,
        default=None,
        help="Use a pre-built CSV of target rows instead of querying Neon (must have staging_id + url columns).",
    )
    args = parser.parse_args()

    if args.dry_run and args.commit:
        raise SystemExit("Use --dry-run or --commit, not both")
    if not args.dry_run and not args.commit:
        args.dry_run = True
    if args.workers < 1 or args.workers > 5:
        raise SystemExit("--workers must be 1-5")
    if not HAS_BS4:
        raise SystemExit("Install beautifulsoup4: pip install beautifulsoup4")
    if not HAS_REQUESTS:
        raise SystemExit("Install requests: pip install requests")

    ts = TIMESTAMP
    out_dir = args.out_dir or (REPO / "reports" / "scraping_runs" / f"detail_location_enrichment_{ts}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    db_url = internal_db_config()
    print("=" * 68)
    print("DETAIL LOCATION ENRICHMENT")
    print(f"mode={'commit' if args.commit else 'dry-run'}")
    print(f"workers={args.workers}")
    print(f"allow_playwright={args.allow_playwright}")
    print(f"out_dir={out_dir}")
    print("supabase_write=false | neon_write=" + ("true" if args.commit else "false"))
    print("-" * 68)

    # Support --input-csv: load rows from a pre-built CSV instead of querying Neon
    if args.input_csv:
        input_csv_path = args.input_csv if args.input_csv.is_absolute() else REPO / args.input_csv
        rows = []
        with input_csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                if args.domain_filter:
                    if _domain(row.get("url") or "") != args.domain_filter:
                        continue
                rows.append(row)
        if args.limit:
            rows = rows[:args.limit]
    else:
        with connect_internal_db(db_url) as conn:
            with conn.cursor() as cur:
                prefix_conditions = " OR ".join(
                    "r.datos_extra->>'captured_file' LIKE %s" for _ in CAMPAIGN_PREFIXES
                )
                params_pref = [f"{p}%" for p in CAMPAIGN_PREFIXES]
                domain_clause = ""
                if args.domain_filter:
                    domain_clause = "AND s.url LIKE %s"
                    params_pref.append(f"%{args.domain_filter}%")
                query = f"""
                    SELECT
                        s.id AS staging_id, s.raw_id, s.inmobiliaria_id,
                        s.titulo, s.descripcion, s.url, s.url_normalizada,
                        s.direccion_normalizada, s.barrio, s.ciudad, s.provincia,
                        s.precio, s.moneda, s.imagenes,
                        s.geocoding_status, s.validation_score,
                        r.datos_extra->>'source_inmobiliaria_nombre' AS nombre,
                        r.datos_extra->>'captured_file' AS captured_file,
                        r.datos_extra->>'captured_strategy' AS strategy
                    FROM propiedades_staging s
                    JOIN propiedades_raw r ON r.id = s.raw_id
                    WHERE ({prefix_conditions})
                      AND s.status = 'staging'
                      AND (s.ciudad IS NULL OR s.ciudad = '')
                      AND (s.provincia IS NULL OR s.provincia = '')
                      {domain_clause}
                    ORDER BY s.validation_score DESC, s.id ASC
                    {"LIMIT %s" if args.limit else ""}
                """
                if args.limit:
                    cur.execute(query, params_pref + [args.limit])
                else:
                    cur.execute(query, params_pref)
                rows = [dict(r) for r in cur.fetchall()]

    total_target = len(rows)
    print(f"domain_filter={args.domain_filter or 'none'}")
    print(f"city_filter={args.city_filter or 'none'}")
    print(f"target_rows={total_target}")

    # Export target CSV
    target_csv = out_dir / "target_missing_location_387.csv"
    target_fields = [
        "staging_id", "inmobiliaria_id", "nombre", "titulo", "url",
        "dominio", "precio", "moneda", "estrategia_original", "score", "captured_file",
    ]
    with target_csv.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=target_fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            r["dominio"] = _domain(r.get("url") or "")
            r["estrategia_original"] = r.get("strategy") or ""
            r["score"] = r.get("validation_score") or ""
            w.writerow(r)
    print(f"target_csv={target_csv}")

    # Run enrichment
    import threading
    session = _make_session()
    domain_last_request: Dict[str, float] = {}
    lock = threading.Lock()
    results: List[Dict[str, Any]] = []

    t_start = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(enrich_one, row, session, args.allow_playwright, domain_last_request, lock): row
            for row in rows
        }
        done_count = 0
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            done_count += 1
            confidence = result.get("confidence") or "-"
            ciudad = result.get("ciudad_propuesta") or "-"
            prov = result.get("provincia_propuesta") or "-"
            fuente = result.get("fuente") or result.get("error") or result.get("motivo") or "-"
            if done_count % 20 == 0 or done_count == total_target:
                print(f"  [{done_count}/{total_target}] id={result['staging_id']} | {confidence} | {ciudad}/{prov} | {fuente}")

    elapsed = round(time.time() - t_start, 1)
    results.sort(key=lambda r: r["staging_id"])

    # Commit high-confidence updates — apply strict filters before writing
    committed = 0
    if args.commit:
        high = [
            r for r in results
            if r.get("aplicar") == "yes"
            and r.get("ciudad_propuesta")
            and _is_safe_city_name(r.get("ciudad_propuesta", ""))
            # --city-filter: only commit rows matching the exact city
            and (not args.city_filter or r.get("ciudad_propuesta", "").strip().lower() == args.city_filter.strip().lower())
            # --domain-filter: only commit rows from that domain
            and (not args.domain_filter or r.get("dominio", "") == args.domain_filter)
        ]
        if high:
            with connect_internal_db(db_url) as conn2:
                with conn2.cursor() as cur2:
                    for r in high:
                        try:
                            cur2.execute("""
                                UPDATE propiedades_staging
                                SET ciudad = %s,
                                    provincia = %s,
                                    barrio = COALESCE(%s, barrio),
                                    direccion_normalizada = COALESCE(NULLIF(%s,''), direccion_normalizada)
                                WHERE id = %s
                                  AND (ciudad IS NULL OR ciudad = '')
                                  AND (provincia IS NULL OR provincia = '')
                            """, [
                                r["ciudad_propuesta"] or None,
                                r["provincia_propuesta"] or None,
                                r["barrio_propuesto"] or None,
                                r["direccion_propuesta"] or None,
                                r["staging_id"],
                            ])
                            committed += 1
                        except Exception as exc:
                            print(f"  ERROR commit id={r['staging_id']}: {exc}")
                conn2.commit()

    # --- REPORTS ---
    high_conf = [r for r in results if r.get("confidence") == "high"]
    med_conf  = [r for r in results if r.get("confidence") == "medium"]
    low_conf  = [r for r in results if r.get("confidence") == "low"]
    no_loc    = [r for r in results if not r.get("ciudad_propuesta") and not r.get("provincia_propuesta")]
    errors    = [r for r in results if r.get("error")]
    found     = [r for r in results if r.get("ciudad_propuesta") or r.get("provincia_propuesta")]

    source_counts: Counter = Counter(r.get("fuente") for r in found if r.get("fuente"))
    domain_found: Counter = Counter(r.get("dominio") for r in found)
    domain_notfound: Counter = Counter(r.get("dominio") for r in no_loc)
    domain_total: Counter = Counter(r.get("dominio") for r in results)

    # Write CSVs
    result_fields = [
        "staging_id", "inmobiliaria_id", "nombre", "url", "dominio",
        "ciudad_actual", "provincia_actual", "barrio_actual", "direccion_actual",
        "ciudad_propuesta", "provincia_propuesta", "barrio_propuesto", "direccion_propuesta",
        "fuente", "confidence", "aplicar", "motivo", "error",
    ]

    def _write_csv(path: Path, data: List[Dict]) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=result_fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(data)

    _write_csv(out_dir / "proposed_location_updates.csv", results)
    _write_csv(out_dir / "high_confidence_updates.csv", high_conf)
    _write_csv(out_dir / "medium_confidence_review.csv", med_conf)
    _write_csv(out_dir / "low_confidence_unusable.csv", low_conf)
    _write_csv(out_dir / "enrichment_failures.csv", no_loc)

    # Summary markdown
    summary_lines = [
        "# Detail location enrichment — dry-run report",
        "",
        f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Modo: {'commit' if args.commit else 'dry-run (no writes)'}",
        f"Workers: {args.workers} | Playwright: {args.allow_playwright}",
        "Fuente: propiedades_staging campaña 04-05 junio 2026",
        "Seguridad: supabase_write=false | no_geocoding | no_.env | no_frontend",
        "",
        "## Resumen",
        "",
        f"- Total objetivo (missing city/province): {total_target}",
        f"- Procesadas: {len(results)}",
        f"- Con ubicación encontrada: {len(found)} ({round(100*len(found)/max(total_target,1))}%)",
        f"- Sin ubicación encontrada: {len(no_loc)} ({round(100*len(no_loc)/max(total_target,1))}%)",
        f"- Errores HTTP/timeout: {len(errors)}",
        "",
        "## Por nivel de confianza",
        "",
        f"- **high confidence** (aplicar automático): {len(high_conf)}",
        f"- **medium confidence** (revisar manualmente): {len(med_conf)}",
        f"- **low confidence** (no aplicar): {len(low_conf)}",
        f"- **sin ubicación**: {len(no_loc)}",
        "",
        "## Estrategias que recuperaron ubicación",
        "",
    ]
    for s, cnt in source_counts.most_common():
        summary_lines.append(f"- {s}: {cnt}")

    summary_lines += ["", "## Top 10 dominios donde SE recuperó ubicación", ""]
    for d, cnt in domain_found.most_common(10):
        summary_lines.append(f"- {d}: {cnt}/{domain_total.get(d,0)}")

    summary_lines += ["", "## Top 10 dominios donde NO se pudo recuperar", ""]
    for d, cnt in domain_notfound.most_common(10):
        summary_lines.append(f"- {d}: {cnt}/{domain_total.get(d,0)} sin ubicación")

    summary_lines += [
        "",
        "## Tiempo total",
        "",
        f"- elapsed: {elapsed}s ({round(elapsed/max(len(results),1),1)}s/propiedad promedio)",
        "",
        "## Archivos generados",
        "",
        f"- target_missing_location_387.csv — {total_target} propiedades objetivo",
        "- proposed_location_updates.csv — todos los resultados",
        "- high_confidence_updates.csv — aplicables automáticamente",
        "- medium_confidence_review.csv — revisar manualmente",
        "- low_confidence_unusable.csv — no aplicar",
        "- enrichment_failures.csv — sin ubicación",
        "",
        "## Recomendación",
        "",
        f"- Aplicar automáticamente: {len(high_conf)} propiedades (high confidence)",
        f"- Revisar y decidir: {len(med_conf)} propiedades (medium confidence)",
        f"- Sin solución por ahora: {len(no_loc)} propiedades",
        "",
        "## Confirmaciones de seguridad",
        "",
        "- no_toca_supabase: true",
        "- no_publish_queue: true",
        "- no_geocoding: true",
        "- no_modifica_schema: true",
        "- no_toca_env: true",
        "- no_commit_git: true",
        "- no_push_git: true",
    ]

    (out_dir / "enrichment_summary.md").write_text("\n".join(summary_lines), encoding="utf-8")

    # Print final summary
    print("-" * 68)
    print(f"total_objetivo={total_target}")
    print(f"procesadas={len(results)}")
    print(f"con_ubicacion={len(found)} ({round(100*len(found)/max(total_target,1))}%)")
    print(f"high_confidence={len(high_conf)}")
    print(f"medium_confidence={len(med_conf)}")
    print(f"low_confidence={len(low_conf)}")
    print(f"sin_ubicacion={len(no_loc)}")
    print(f"errores={len(errors)}")
    print(f"committed={committed}")
    print(f"elapsed={elapsed}s")
    print(f"out_dir={out_dir}")
    print("=" * 68)


if __name__ == "__main__":
    main()
