#!/usr/bin/env python
"""FULL_SOURCE_DIAGNOSTIC_7004 — censo diagnostico FORENSE read-only de inmobiliarias.

Recorre TODAS las inmobiliarias de public.inmobiliarias_main (no depende de
v_next_scraping_batch ni del flag scrapeable) y produce un diagnostico forense
por inmobiliaria (~150 campos): URLs, accesibilidad (DNS/SSL/redirects/antibot/JS),
CMS/estrategia con confianza, descubrimiento de links de propiedad, parseo de
muestra (<=3 fichas), calidad estimada, causa raiz y recomendacion.

GARANTIAS:
- Solo LECTURA de DB (un SELECT a inmobiliarias_main).  NO escribe DB. NO publica.
- Escribe SOLO archivos locales en --out.  Checkpoint/resume via JSONL + progress.json.
- Fuentes prohibidas (zonaprop/argenprop/portales) -> prohibited_source_skipped, no se scrapean.
- try/except por inmobiliaria: una nunca corta la campania.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import pathlib
import re
import socket
import threading
import time
import traceback
import uuid
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_env(path: pathlib.Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


load_env(REPO_ROOT / ".env")
load_env(REPO_ROOT / ".env.local")

import requests  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402
from scraper.network_security import secure_get  # noqa: E402

# ── Politica de fuentes prohibidas / portales de terceros ─────────────────────
PROHIBITED_PORTAL_RE = re.compile(r"(zonaprop|argenprop)\.com\.ar", re.I)
EXTERNAL_PORTAL_RE = re.compile(
    r"(mercadolibre|navent|buscainmueble|properati|inmuebles24|imovelweb|infocasas|"
    r"remax\.com\.ar|infobae\.com|clarin\.com|lanacion\.com\.ar|"
    r"facebook\.com|instagram\.com|linktr\.ee|wa\.me|api\.whatsapp)",
    re.I,
)
KNOWN_JS_DOMAINS_RE = re.compile(
    r"(redremax|tokkobroker\.com|tokko\.io|proppit|laanunciadora)", re.I
)

UA = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept-Language": "es-AR,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

ANTIBOT_SIGNS = ("just a moment", "cf-browser-verification", "challenge-platform",
                 "attention required", "_cf_chl", "datadome", "perimeterx", "incapsula",
                 "verifique que es un humano", "verificando que")
CAPTCHA_SIGNS = ("captcha", "recaptcha", "hcaptcha", "g-recaptcha")
LOGIN_SIGNS = ("iniciar sesion", "iniciar sesión", "ingresar al sistema", "login required",
               "debe iniciar sesion", "acceso restringido")
JS_SHELL_SIGNS = ("__next_data__", "window.__nuxt__", "data-reactroot", "ng-version",
                  "please enable javascript", "necesitas habilitar javascript",
                  "habilita javascript", "id=\"root\"></div>", "id=\"app\"></div>")
PROP_LINK_RE = re.compile(
    r"(propiedad|propiedades|inmueble|inmuebles|ficha|detalle|emprendimiento|"
    r"/p/|/prop/|listing|property|/aviso|/venta/|/alquiler/)", re.I)
PAGINATION_RE = re.compile(r"(\?page=|/page/|&pagina=|\?pagina=|paged=|/p-\d+|page-\d+)", re.I)
IMG_BLOCK_RE = re.compile(r"(logo|placeholder|no-?photo|no-?image|sin-?imagen|prop-icons|"
                          r"footer|banner|avatar|whatsapp|icon)", re.I)
PRICE_RE = re.compile(r"(u\$s|us\$|usd|ar\$|\$|pesos|dolar)\s*\.?\s*[\d][\d\.\,]{2,}", re.I)
COORD_RE = re.compile(r"(\"lat(itude)?\"\s*[:=]\s*-?\d{1,2}\.\d{3,}|"
                      r"maps[^\"']{0,40}@?-?\d{1,2}\.\d{3,},-?\d{1,2}\.\d{3,}|"
                      r"google\.com/maps[^\"']*-?\d{1,2}\.\d{3,})", re.I)

LOCK = threading.Lock()

# Campos del JSONL (orden estable para CSV)
FIELD_ORDER = [
    # identificacion
    "diagnostic_run_id", "diagnosed_at", "source_index", "source_id", "source_name",
    "business_name", "province", "city", "address_if_available", "phone_if_available",
    "email_if_available",
    # urls
    "website_url", "listing_url", "normalized_website_url", "normalized_listing_url",
    "final_website_url_after_redirect", "final_listing_url_after_redirect", "url_source",
    "url_is_missing", "url_is_malformed", "listing_url_is_missing", "listing_url_is_malformed",
    "listing_url_seems_homepage", "listing_url_seems_search_page", "listing_url_seems_property_detail",
    "same_domain_website_listing", "redirect_count", "redirect_chain_summary",
    # accesibilidad
    "http_status_website", "http_status_listing", "http_error_type", "dns_ok", "ssl_ok",
    "robots_relevant_if_checked", "response_time_ms_website", "response_time_ms_listing",
    "timeout", "timeout_stage", "domain_down", "connection_error", "blocked_by_cloudflare",
    "blocked_by_antibot", "requires_playwright", "requires_js", "captcha_detected",
    "login_required", "rate_limited", "forbidden_403", "not_found_404", "server_error_5xx",
    # clasificacion
    "cms_current_db", "cms_detected", "cms_confidence", "platform_detected", "technology_hints",
    "strategy_current_db", "strategy_detected", "strategy_confidence", "strategy_is_missing",
    "strategy_seems_wrong", "strategy_recommendation", "scraper_family_recommended",
    "http_possible", "playwright_needed", "api_detected", "sitemap_detected", "wordpress_detected",
    "tokko_detected", "custom_detected", "wix_detected", "iframe_detected",
    # prohibiciones
    "is_prohibited_source", "prohibited_reason", "prohibited_source_type", "skipped_due_to_policy",
    # descubrimiento
    "listing_page_loaded", "listing_page_title", "listing_page_text_sample",
    "property_links_detected", "property_links_count", "property_links_unique_count",
    "property_links_sample", "pagination_detected", "pagination_type", "max_pages_detected_if_known",
    "infinite_scroll_detected", "json_ld_detected", "structured_data_detected",
    "embedded_api_detected", "search_results_detected", "zero_properties_detected",
    "no_property_links_reason",
    # parseo muestra
    "sample_property_urls", "sample_property_count_attempted", "sample_property_count_loaded",
    "sample_property_count_parsed", "sample_parse_success", "sample_parse_error_type",
    "sample_parse_error_detail",
    # campos por muestra
    "sample_has_title", "sample_has_price", "sample_has_currency", "sample_has_operation",
    "sample_has_property_type", "sample_has_description", "sample_has_city", "sample_has_province",
    "sample_has_neighborhood", "sample_has_address", "sample_has_images", "sample_images_count_avg",
    "sample_has_real_images", "sample_has_coordinates", "sample_has_area", "sample_has_rooms",
    "sample_has_bedrooms", "sample_has_bathrooms", "sample_has_garage", "sample_has_original_url",
    # calidad
    "estimated_quality_score_0_100", "quality_tier", "missing_title_rate_sample",
    "missing_price_rate_sample", "missing_operation_rate_sample", "missing_type_rate_sample",
    "missing_location_rate_sample", "missing_images_rate_sample", "missing_description_rate_sample",
    "coordinates_available_rate_sample", "price_suspicious", "operation_suspicious",
    "type_suspicious", "location_suspicious", "images_suspicious",
    # resultado
    "final_status", "error_category", "error_subcategory", "error_detail_short",
    "error_detail_long", "root_cause_hypothesis", "is_scrapeable_now", "is_scrapeable_after_url_fix",
    "is_scrapeable_after_strategy_fix", "is_scrapeable_after_playwright", "is_not_scrapeable_reason",
    "recommended_action", "recommended_fix_family", "priority", "estimated_fix_effort",
    "expected_property_yield", "should_include_in_next_real_scrape", "notes",
]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def base_record():
    return {k: None for k in FIELD_ORDER}


def s(v):
    return "" if v is None else str(v).strip()


def normalize_url(u):
    u = s(u)
    if not u:
        return ""
    if not re.match(r"^https?://", u, re.I):
        u = "https://" + u
    return u


def is_malformed(u):
    if not u:
        return False
    try:
        p = urlparse(normalize_url(u))
        host = p.netloc
        if not host or "." not in host or " " in host:
            return True
        if re.match(r"^(admin|login|panel|home|inicio|contacto|nosotros|web|sitio|pagina)$", host, re.I):
            return True
        return False
    except Exception:
        return True


def host_of(u):
    try:
        return urlparse(normalize_url(u)).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def dns_ok(u, timeout=5):
    host = urlparse(normalize_url(u)).netloc.split(":")[0]
    if not host:
        return False
    try:
        socket.setdefaulttimeout(timeout)
        socket.getaddrinfo(host, None)
        return True
    except Exception:
        return False


def fetch(url, connect_t, page_t):
    """Devuelve dict con status/html/final_url/redirects/ssl_ok/elapsed_ms/error_type/flags."""
    out = {"status": None, "html": "", "final_url": None, "redirects": 0,
           "chain": "", "ssl_ok": None, "elapsed_ms": None, "error_type": None}
    url = normalize_url(url)
    is_https = url.lower().startswith("https")
    t0 = time.monotonic()
    r = None
    try:
        r = secure_get(requests, url, timeout=(connect_t, page_t), headers=UA)
        out["ssl_ok"] = True if is_https else None
    except requests.exceptions.SSLError as e:
        out["ssl_ok"] = False
        out["error_type"] = "ssl_error"
        out["elapsed_ms"] = int((time.monotonic() - t0) * 1000)
        return out
    except requests.exceptions.ConnectTimeout:
        out["error_type"] = "connect_timeout"; out["elapsed_ms"] = int((time.monotonic()-t0)*1000); return out
    except requests.exceptions.ReadTimeout:
        out["error_type"] = "read_timeout"; out["elapsed_ms"] = int((time.monotonic()-t0)*1000); return out
    except requests.exceptions.Timeout:
        out["error_type"] = "timeout"; out["elapsed_ms"] = int((time.monotonic()-t0)*1000); return out
    except requests.exceptions.ConnectionError as e:
        out["error_type"] = "connection_error"; out["elapsed_ms"] = int((time.monotonic()-t0)*1000); return out
    except Exception as e:
        out["error_type"] = "fetch_" + type(e).__name__; out["elapsed_ms"] = int((time.monotonic()-t0)*1000); return out
    out["elapsed_ms"] = int((time.monotonic() - t0) * 1000)
    out["status"] = r.status_code
    out["final_url"] = r.url
    out["redirects"] = len(r.history)
    out["chain"] = " -> ".join([str(h.status_code) for h in r.history] + [str(r.status_code)])
    try:
        out["html"] = r.text or ""
    except Exception:
        out["html"] = ""
    return out


def detect_cms(html_low, final_url):
    fu = (final_url or "").lower()
    if "tokkobroker" in html_low or "tokko.io" in html_low or "api.tokkobroker" in html_low or "tokko" in fu:
        return "tokko", 0.95
    if "wp-content" in html_low or "wp-json" in html_low or "/wp-includes/" in html_low:
        return "wordpress", 0.9
    if "parastorage" in html_low or "wix.com" in html_low or "_wixcssbootstrap" in html_low:
        return "wix", 0.9
    if "squarespace" in html_low:
        return "squarespace", 0.85
    if "webflow" in html_low:
        return "webflow", 0.85
    if "/_next/" in html_low or "__next_data__" in html_low:
        return "next_spa", 0.8
    return "unknown", 0.0


def parse_property(url, connect_t, sample_t):
    """Parsea una ficha y devuelve dict has_* + images_count."""
    res = {"loaded": False, "parsed": False, "error_type": None,
           "fields": {k: False for k in ("title", "price", "currency", "operation", "property_type",
                                         "description", "city", "province", "neighborhood", "address",
                                         "images", "real_images", "coordinates", "area", "rooms",
                                         "bedrooms", "bathrooms", "garage", "original_url")},
           "images_count": 0}
    f = fetch(url, connect_t, sample_t)
    if f["error_type"] or not f["status"] or f["status"] >= 400:
        res["error_type"] = f["error_type"] or f"http_{f['status']}"
        return res
    res["loaded"] = True
    html = f["html"]; low = html.lower()
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")
    fld = res["fields"]
    fld["original_url"] = True
    if (soup.title and soup.title.text.strip()) or soup.find("h1"):
        fld["title"] = True
    if PRICE_RE.search(low):
        fld["price"] = True
        fld["currency"] = bool(re.search(r"(u\$s|us\$|usd|ar\$|pesos|dolar)", low))
    if re.search(r"\b(venta|alquiler|alquila|vende|temporario|en pozo)\b", low):
        fld["operation"] = True
    if re.search(r"\b(casa|departamento|depto|ph|terreno|lote|local|oficina|galpon|campo|cochera|duplex|chalet)\b", low):
        fld["property_type"] = True
    md = soup.find("meta", attrs={"name": "description"})
    if (md and md.get("content")) or soup.find("meta", attrs={"property": "og:description"}):
        fld["description"] = True
    if re.search(r"\"addresslocality\"|\"streetaddress\"|\"address\"", low):
        fld["address"] = True; fld["city"] = True
    if re.search(r"\"addressregion\"|provincia", low):
        fld["province"] = True
    if re.search(r"\b(barrio|neighborhood)\b", low):
        fld["neighborhood"] = True
    if re.search(r"\b(calle|av\.|avenida|bv\.|ruta|n°|nro)\b", low):
        fld["address"] = True
    imgs = [i.get("src", "") for i in soup.find_all("img", src=True)]
    og = soup.find("meta", attrs={"property": "og:image"})
    if og and og.get("content"):
        imgs.append(og["content"])
    real_imgs = [i for i in imgs if i and not IMG_BLOCK_RE.search(i)]
    res["images_count"] = len(real_imgs)
    fld["images"] = len(imgs) > 0
    fld["real_images"] = len(real_imgs) > 0
    if COORD_RE.search(low):
        fld["coordinates"] = True
    if re.search(r"(\bm2\b|metros|superficie|m²)", low):
        fld["area"] = True
    if re.search(r"\bambientes?\b", low):
        fld["rooms"] = True
    if re.search(r"\b(dormitorios?|habitaciones?)\b", low):
        fld["bedrooms"] = True
    if re.search(r"\b(ba[ñn]os?)\b", low):
        fld["bathrooms"] = True
    if re.search(r"\b(cochera|garage|garaje)\b", low):
        fld["garage"] = True
    res["parsed"] = any(fld.values())
    return res


def discover_links(html, base_url, max_links):
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")
    base_host = urlparse(base_url).netloc.lower()
    found, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        full = urljoin(base_url, href)
        if urlparse(full).netloc.lower() not in ("", base_host):
            continue
        if not PROP_LINK_RE.search(href):
            continue
        path = urlparse(full).path
        if path.count("/") < 2 and not re.search(r"\d{2,}", path):
            continue
        if full in seen:
            continue
        seen.add(full)
        found.append(full)
        if len(found) >= max_links:
            break
    pagination = bool(PAGINATION_RE.search(html)) or bool(soup.find("a", attrs={"rel": "next"}))
    json_ld = "application/ld+json" in html.lower()
    embedded_api = bool(re.search(r"(/wp-json/|/api/|fetch\(|xmlhttprequest|axios)", html.lower()))
    return found, pagination, json_ld, embedded_api


def diagnose_forensic(inmob, idx, cfg, run_id):
    t0 = time.monotonic()
    r = base_record()
    r["diagnostic_run_id"] = run_id
    r["diagnosed_at"] = now_iso()
    r["source_index"] = idx
    r["source_id"] = inmob.get("id")
    r["source_name"] = inmob.get("nombre")
    r["business_name"] = inmob.get("nombre")
    r["province"] = inmob.get("provincia")
    r["city"] = inmob.get("ciudad")
    r["address_if_available"] = inmob.get("direccion")
    r["phone_if_available"] = inmob.get("telefono_principal") or inmob.get("telefono")
    r["email_if_available"] = inmob.get("email_principal")
    r["cms_current_db"] = inmob.get("cms_detectado")
    r["strategy_current_db"] = inmob.get("estrategia_scraping")
    r["expected_property_yield"] = inmob.get("total_propiedades")
    r["website_url"] = inmob.get("web")
    r["listing_url"] = inmob.get("url_listado")
    web = s(inmob.get("web")); listing = s(inmob.get("url_listado"))
    r["normalized_website_url"] = normalize_url(web) or None
    r["normalized_listing_url"] = normalize_url(listing) or None
    r["url_is_missing"] = (not web)
    r["listing_url_is_missing"] = (not listing)
    r["url_is_malformed"] = is_malformed(web)
    r["listing_url_is_malformed"] = is_malformed(listing)
    r["robots_relevant_if_checked"] = None  # no se chequea en pasada HTTP base
    # defaults
    for k in ("is_prohibited_source", "skipped_due_to_policy", "timeout", "domain_down",
              "connection_error", "blocked_by_cloudflare", "blocked_by_antibot", "requires_playwright",
              "requires_js", "captcha_detected", "login_required", "rate_limited", "forbidden_403",
              "not_found_404", "server_error_5xx", "listing_page_loaded", "property_links_detected",
              "pagination_detected", "json_ld_detected", "structured_data_detected", "embedded_api_detected",
              "search_results_detected", "zero_properties_detected", "infinite_scroll_detected",
              "wordpress_detected", "tokko_detected", "custom_detected", "wix_detected", "iframe_detected",
              "api_detected", "sitemap_detected", "http_possible", "playwright_needed",
              "strategy_is_missing", "strategy_seems_wrong", "sample_parse_success",
              "price_suspicious", "operation_suspicious", "type_suspicious", "location_suspicious",
              "images_suspicious"):
        r[k] = False
    r["property_links_count"] = 0
    r["property_links_unique_count"] = 0
    r["sample_property_count_attempted"] = 0
    r["sample_property_count_loaded"] = 0
    r["sample_property_count_parsed"] = 0
    r["redirect_count"] = 0

    def finalize(status, category, action, fix_family, priority, effort,
                 subcat="", short="", long="", root="", notes=""):
        r["final_status"] = status
        r["error_category"] = category
        r["error_subcategory"] = subcat
        r["error_detail_short"] = short
        r["error_detail_long"] = long
        r["root_cause_hypothesis"] = root
        r["recommended_action"] = action
        r["recommended_fix_family"] = fix_family
        r["priority"] = priority
        r["estimated_fix_effort"] = effort
        r["notes"] = notes
        r["is_scrapeable_now"] = status in ("success", "success_low_quality")
        r["should_include_in_next_real_scrape"] = status == "success"
        return r

    # url_source
    r["url_source"] = "listing" if listing else ("website" if web else "none")
    r["same_domain_website_listing"] = bool(web and listing and host_of(web) == host_of(listing))

    # 1) Prohibidas
    hay = f"{web} {listing}".lower()
    if PROHIBITED_PORTAL_RE.search(hay):
        r["is_prohibited_source"] = True; r["skipped_due_to_policy"] = True
        r["prohibited_reason"] = "zonaprop/argenprop (portal prohibido por politica ERETZ)"
        r["prohibited_source_type"] = "portal_inmobiliario_prohibido"
        r["is_not_scrapeable_reason"] = "prohibited"
        return finalize("prohibited_source_skipped", "prohibited_source_skipped", "skip_prohibited_source",
                        "prohibited", "none", "none", root="fuente prohibida")
    if EXTERNAL_PORTAL_RE.search(hay):
        r["is_prohibited_source"] = True; r["skipped_due_to_policy"] = True
        r["prohibited_reason"] = "portal/red social de terceros"
        r["prohibited_source_type"] = "portal_externo_terceros"
        r["is_not_scrapeable_reason"] = "prohibited"
        return finalize("prohibited_source_skipped", "prohibited_source_skipped", "skip_prohibited_source",
                        "prohibited", "none", "none", root="portal de terceros")

    # 2) Sin URL
    target = listing or web
    if not target:
        r["is_not_scrapeable_reason"] = "sin web ni url_listado"
        return finalize("missing_url", "missing_url", "skip_not_real_estate", "url", "low", "manual",
                        root="registro sin URL", short="sin web ni url_listado")

    # 3) DNS
    r["dns_ok"] = dns_ok(target, cfg["connect"])
    if not r["dns_ok"]:
        r["domain_down"] = True
        r["is_not_scrapeable_reason"] = "dns_no_resuelve"
        r["is_scrapeable_after_url_fix"] = True
        return finalize("dns_error", "dns_error", "fix_listing_url" if listing else "detect_listing_url",
                        "url", "medium", "manual", root="dominio no resuelve DNS",
                        short="dns fail", long=f"host={host_of(target)}")

    # 4) Fetch del target (listing si existe, si no website)
    fres = fetch(target, cfg["connect"], cfg["page"])
    r["response_time_ms_listing"] = fres["elapsed_ms"]
    r["http_status_listing"] = fres["status"]
    r["final_listing_url_after_redirect"] = fres["final_url"]
    r["redirect_count"] = fres["redirects"]
    r["redirect_chain_summary"] = fres["chain"]
    r["ssl_ok"] = fres["ssl_ok"]
    if fres["ssl_ok"] is False:
        r["error_subcategory"] = "ssl"
    # errores de transporte
    if fres["error_type"]:
        et = fres["error_type"]
        if "timeout" in et:
            r["timeout"] = True; r["timeout_stage"] = "listing"
            r["is_scrapeable_after_playwright"] = True
            return finalize("timeout", "timeout", "retry_later", "infra", "medium", "auto",
                            subcat=et, root="timeout HTTP", short=et)
        if "ssl" in et:
            r["is_scrapeable_after_url_fix"] = True
            return finalize("ssl_error", "ssl_error", "requires_antibot_review", "url", "medium", "manual",
                            root="ssl invalido", short=et)
        r["connection_error"] = True; r["domain_down"] = True
        r["is_scrapeable_after_url_fix"] = True
        return finalize("domain_down", "domain_down", "fix_listing_url" if listing else "detect_listing_url",
                        "url", "medium", "manual", subcat=et, root="conexion fallida", short=et)

    status = fres["status"]
    html = fres["html"]; low = html.lower()
    r["listing_page_loaded"] = status and status < 400
    # HTTP status flags
    r["forbidden_403"] = status == 403
    r["not_found_404"] = status == 404
    r["server_error_5xx"] = status is not None and status >= 500
    r["rate_limited"] = status == 429

    # contenido visible (para distinguir gate-pages de paginas reales con form de contacto)
    vis_text = re.sub(r"<[^>]+>", " ", html)
    text_len = len(vis_text.strip())

    # antibot real (challenge pages tipo Cloudflare/Datadome) -> bloquea
    if any(x in low for x in ANTIBOT_SIGNS) or (status in (403, 503) and "cloudflare" in low):
        r["blocked_by_antibot"] = True
        r["blocked_by_cloudflare"] = "cloudflare" in low or "_cf_chl" in low
        r["requires_playwright"] = True; r["playwright_needed"] = True
        r["is_scrapeable_after_playwright"] = True
        return finalize("antibot", "antibot", "requires_antibot_review", "antibot", "high", "high",
                        root="proteccion antibot", short=f"http {status}")
    # captcha: SOLO bloquea si la pagina es una gate (poco contenido). Un recaptcha en el
    # form de contacto de un sitio que igual carga su listado NO bloquea el scraping.
    if any(x in low for x in CAPTCHA_SIGNS):
        r["captcha_detected"] = True
        if text_len < 1200:
            r["requires_playwright"] = True
            return finalize("captcha", "captcha", "requires_antibot_review", "antibot", "high", "high",
                            root="captcha gate", short="captcha")
    if status == 429:
        return finalize("rate_limited", "rate_limited", "retry_later", "infra", "medium", "auto",
                        root="rate limited", short="429")
    if status == 403:
        return finalize("forbidden", "forbidden", "requires_antibot_review", "antibot", "high", "high",
                        root="403 forbidden", short="403")
    if status == 404:
        r["is_scrapeable_after_url_fix"] = True
        cat = "bad_listing_url" if listing else "bad_website_url"
        return finalize("not_found", cat, "fix_listing_url" if listing else "detect_listing_url",
                        "url", "medium", "manual", root="404 not found", short="404")
    if status is not None and status >= 500:
        return finalize("server_error", "server_error", "retry_later", "infra", "low", "auto",
                        root="5xx server error", short=str(status))
    if status is not None and status >= 400:
        return finalize("bad_listing_url", "bad_listing_url", "fix_listing_url", "url", "medium", "manual",
                        root=f"http {status}", short=str(status))
    if any(x in low for x in LOGIN_SIGNS):
        r["login_required"] = True
        if text_len < 1200:
            return finalize("login_required", "login_required", "manual_review", "antibot", "medium", "manual",
                            root="login gate", short="login")

    # CMS / plataforma
    cms, conf = detect_cms(low, fres["final_url"])
    r["cms_detected"] = cms; r["cms_confidence"] = conf; r["platform_detected"] = cms
    r["wordpress_detected"] = cms == "wordpress"
    r["tokko_detected"] = cms == "tokko"
    r["wix_detected"] = cms == "wix"
    r["custom_detected"] = cms == "unknown"
    r["iframe_detected"] = "<iframe" in low
    r["api_detected"] = "tokko" in cms or "/wp-json/" in low
    r["sitemap_detected"] = "sitemap" in low
    hints = []
    for kw in ("jquery", "bootstrap", "react", "vue", "angular", "elementor", "cloudflare", "nginx"):
        if kw in low:
            hints.append(kw)
    r["technology_hints"] = ",".join(hints)

    # needs JS / SPA
    text = re.sub(r"<[^>]+>", " ", html)
    needs_js = (cms == "next_spa") or (any(x in low for x in JS_SHELL_SIGNS) and len(text.strip()) < 1800) \
        or bool(KNOWN_JS_DOMAINS_RE.search(hay))
    r["requires_js"] = needs_js
    # listing page title/sample
    try:
        title_el = BeautifulSoup(html, "html.parser").title
        r["listing_page_title"] = (title_el.text.strip()[:160] if title_el and title_el.text else None)
    except Exception:
        pass
    r["listing_page_text_sample"] = re.sub(r"\s+", " ", text).strip()[:300]

    # estrategia
    db_strat = (r["strategy_current_db"] or "").lower()
    r["strategy_is_missing"] = db_strat in ("", "none", "sin_estrategia", "sin_url")
    if cms == "tokko":
        fam, strat = "tokko", "tokko_api_or_static"
    elif cms == "wordpress":
        fam, strat = "wordpress", "wordpress_generic_detail"
    elif cms == "next_spa" or needs_js:
        fam, strat = "playwright", "playwright_dynamic"
    elif cms in ("wix", "squarespace", "webflow"):
        fam, strat = "playwright", "playwright_dynamic"
    else:
        fam, strat = "custom", "html_generic"
    r["scraper_family_recommended"] = fam
    r["strategy_detected"] = strat
    r["strategy_confidence"] = conf if conf else (0.5 if fam != "custom" else 0.4)
    r["http_possible"] = fam in ("tokko", "wordpress", "custom") and not needs_js
    r["playwright_needed"] = needs_js or fam == "playwright"
    r["strategy_recommendation"] = "assign_" + ("tokko_strategy" if fam == "tokko" else
                                                "wordpress_strategy" if fam == "wordpress" else
                                                "custom_strategy" if fam == "custom" else "playwright_runner")
    if db_strat and not r["strategy_is_missing"] and fam not in db_strat and db_strat not in fam:
        r["strategy_seems_wrong"] = True

    # listing url shape
    path = urlparse(fres["final_url"]).path.rstrip("/")
    r["listing_url_seems_homepage"] = (path == "" or path == "/")
    r["listing_url_seems_search_page"] = bool(re.search(r"(buscar|search|listado|propiedades|resultados|filtro)", fres["final_url"], re.I))
    r["listing_url_seems_property_detail"] = bool(re.search(r"(/propiedad/|/inmueble/|/ficha/|/p/\d|-id-\d)", fres["final_url"], re.I))

    # needs JS -> requires_playwright (despues de registrar CMS/estrategia)
    if needs_js:
        r["requires_playwright"] = True
        r["is_scrapeable_after_playwright"] = True
        return finalize("requires_playwright", "requires_playwright", "requires_playwright_runner",
                        "playwright", "high", "medium", root=f"SPA/JS cms={cms}",
                        short="requires_js", notes="diferir a pasada Playwright")

    # descubrimiento de links
    links, pagination, json_ld, emb_api = discover_links(html, fres["final_url"], cfg["max_links"])
    r["property_links_detected"] = len(links) > 0
    r["property_links_count"] = len(links)
    r["property_links_unique_count"] = len(set(links))
    r["property_links_sample"] = json.dumps(links[:5], ensure_ascii=False)
    r["pagination_detected"] = pagination
    r["pagination_type"] = "query_or_path" if pagination else None
    r["json_ld_detected"] = json_ld
    r["structured_data_detected"] = json_ld or ("og:" in low)
    r["embedded_api_detected"] = emb_api
    r["search_results_detected"] = r["listing_url_seems_search_page"] or len(links) > 0

    if not links:
        r["zero_properties_detected"] = True
        if cms == "unknown":
            r["no_property_links_reason"] = "cms_desconocido_sin_patron_de_links"
            return finalize("cms_unknown", "cms_unknown", "fix_cms_detection", "cms", "medium", "manual",
                            root="cms desconocido + sin links", short="no links / cms unknown")
        r["no_property_links_reason"] = f"cms={cms}_pero_0_links_en_html (posible JS o selector distinto)"
        return finalize("no_property_links", "no_property_links", "requires_parser_fix", "parser",
                        "medium", "medium", root="parser/selector no encuentra links", short="0 links")

    # 5) Parseo de muestra (<=N fichas)
    sample = links[: cfg["sample_n"]]
    r["sample_property_urls"] = json.dumps(sample, ensure_ascii=False)
    r["sample_property_count_attempted"] = len(sample)
    agg = {k: 0 for k in ("title", "price", "currency", "operation", "property_type", "description",
                          "city", "province", "neighborhood", "address", "images", "real_images",
                          "coordinates", "area", "rooms", "bedrooms", "bathrooms", "garage", "original_url")}
    loaded = parsed = 0
    img_counts = []
    last_err = None
    for purl in sample:
        try:
            pr = parse_property(purl, cfg["connect"], cfg["sample"])
        except Exception as e:
            last_err = type(e).__name__
            continue
        if pr["loaded"]:
            loaded += 1
        if pr["parsed"]:
            parsed += 1
            img_counts.append(pr["images_count"])
            for k, v in pr["fields"].items():
                if v:
                    agg[k] += 1
        elif pr["error_type"]:
            last_err = pr["error_type"]
    r["sample_property_count_loaded"] = loaded
    r["sample_property_count_parsed"] = parsed
    r["sample_parse_success"] = parsed > 0
    r["sample_parse_error_type"] = last_err
    n = max(parsed, 1)
    for fk, rk in [("title", "sample_has_title"), ("price", "sample_has_price"), ("currency", "sample_has_currency"),
                   ("operation", "sample_has_operation"), ("property_type", "sample_has_property_type"),
                   ("description", "sample_has_description"), ("city", "sample_has_city"),
                   ("province", "sample_has_province"), ("neighborhood", "sample_has_neighborhood"),
                   ("address", "sample_has_address"), ("images", "sample_has_images"),
                   ("real_images", "sample_has_real_images"), ("coordinates", "sample_has_coordinates"),
                   ("area", "sample_has_area"), ("rooms", "sample_has_rooms"), ("bedrooms", "sample_has_bedrooms"),
                   ("bathrooms", "sample_has_bathrooms"), ("garage", "sample_has_garage"),
                   ("original_url", "sample_has_original_url")]:
        r[rk] = (agg[fk] > 0) if parsed else False
    r["sample_images_count_avg"] = round(sum(img_counts) / len(img_counts), 1) if img_counts else 0

    # missing rates
    def miss(field):
        return round(1 - agg[field] / n, 2) if parsed else 1.0
    r["missing_title_rate_sample"] = miss("title")
    r["missing_price_rate_sample"] = miss("price")
    r["missing_operation_rate_sample"] = miss("operation")
    r["missing_type_rate_sample"] = miss("property_type")
    r["missing_location_rate_sample"] = round(1 - (agg["city"] + agg["address"]) / (2 * n), 2) if parsed else 1.0
    r["missing_images_rate_sample"] = miss("real_images")
    r["missing_description_rate_sample"] = miss("description")
    r["coordinates_available_rate_sample"] = round(agg["coordinates"] / n, 2) if parsed else 0.0

    # quality score 0-100
    if parsed == 0:
        r["estimated_quality_score_0_100"] = 0
        r["quality_tier"] = "F"
        return finalize("parser_error", "parser_error", "requires_parser_fix", "parser", "high", "medium",
                        subcat=last_err or "", root="links detectados pero fichas no parsean",
                        short="0 parsed", long=f"intentadas={len(sample)} loaded={loaded}")
    core = {"title": 18, "price": 18, "operation": 14, "property_type": 12}
    extra = {"description": 6, "city": 6, "address": 6, "real_images": 8, "coordinates": 8, "area": 4}
    score = 0.0
    for k, w in core.items():
        score += w * (agg[k] / n)
    for k, w in extra.items():
        score += w * (agg[k] / n)
    score = int(round(score))
    r["estimated_quality_score_0_100"] = score
    r["quality_tier"] = ("A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "D")
    # suspicious flags
    r["price_suspicious"] = r["missing_price_rate_sample"] > 0.6
    r["operation_suspicious"] = r["missing_operation_rate_sample"] > 0.6
    r["type_suspicious"] = r["missing_type_rate_sample"] > 0.6
    r["location_suspicious"] = r["missing_location_rate_sample"] > 0.7
    r["images_suspicious"] = r["missing_images_rate_sample"] > 0.6

    notes = "url_listado vacio; se uso website" if (not listing) else ""
    if score >= 55:
        return finalize("success", "success", "ready_to_scrape", fam, "low", "none",
                        root="ok", short=f"q={score}", notes=notes)
    return finalize("success_low_quality", "low_quality_data", "requires_parser_fix", "parser", "medium", "medium",
                    root="parsea pero faltan campos clave", short=f"q={score}", notes=notes)


# ── DB read-only ──────────────────────────────────────────────────────────────
def get_all_inmobiliarias():
    import psycopg
    url = os.getenv("INTERNAL_DB_URL", "").strip()
    if not url:
        raise SystemExit("Falta INTERNAL_DB_URL")
    conn = psycopg.connect(url, connect_timeout=30)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SET default_transaction_read_only = on")
    cur.execute(
        """
        SELECT id, nombre, web, url_listado, provincia, ciudad, direccion,
               telefono, telefono_principal, email_principal,
               cms_detectado, estrategia_scraping, tiene_antibot, activa, sitio_activo, total_propiedades
        FROM public.inmobiliarias_main
        ORDER BY id ASC
        """
    )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    return rows


def load_done_ids(jsonl):
    done = set()
    if jsonl.exists():
        for line in jsonl.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line:
                try:
                    done.add(json.loads(line)["source_id"])
                except Exception:
                    pass
    return done


def append_jsonl(jsonl, rec):
    with LOCK:
        with jsonl.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")


def flatten(rec):
    out = {}
    for k in FIELD_ORDER:
        v = rec.get(k)
        if isinstance(v, (list, dict)):
            v = json.dumps(v, ensure_ascii=False)
        out[k] = v
    return out


def build_outputs(out_dir):
    jsonl = out_dir / "diagnostic_results.jsonl"
    if not jsonl.exists():
        return None
    recs = []
    for line in jsonl.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line:
            try:
                recs.append(json.loads(line))
            except Exception:
                pass
    # CSV principal
    with (out_dir / "diagnostic_results.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELD_ORDER, extrasaction="ignore")
        w.writeheader()
        for r in recs:
            w.writerow(flatten(r))

    def subset_csv(name, pred, cols=None):
        rows = [r for r in recs if pred(r)]
        cols = cols or ["source_id", "source_name", "province", "city", "website_url", "listing_url",
                        "final_status", "error_category", "recommended_action", "recommended_fix_family",
                        "priority", "expected_property_yield", "estimated_quality_score_0_100", "error_detail_short"]
        with (out_dir / name).open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({c: (json.dumps(r.get(c), ensure_ascii=False) if isinstance(r.get(c), (list, dict)) else r.get(c)) for c in cols})
        return len(rows)

    cat = Counter(r.get("error_category") for r in recs)
    status = Counter(r.get("final_status") for r in recs)
    cms = Counter(r.get("cms_detected") for r in recs if r.get("cms_detected"))
    strat = Counter(r.get("scraper_family_recommended") for r in recs if r.get("scraper_family_recommended"))
    prov = Counter((r.get("province"), r.get("city")) for r in recs)

    def write_counter_csv(name, counter, keyname):
        with (out_dir / name).open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f); w.writerow([keyname, "count"])
            for k, v in counter.most_common():
                w.writerow([k, v])

    write_counter_csv("summary_by_category.csv", cat, "error_category")
    write_counter_csv("summary_by_cms.csv", cms, "cms_detected")
    write_counter_csv("summary_by_strategy.csv", strat, "scraper_family_recommended")
    with (out_dir / "summary_by_province_city.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f); w.writerow(["province", "city", "count", "problemas"])
        prob = Counter()
        for r in recs:
            if r.get("final_status") not in ("success",):
                prob[(r.get("province"), r.get("city"))] += 1
        for (p, c), n in prov.most_common():
            w.writerow([p, c, n, prob.get((p, c), 0)])

    # subsets
    subset_csv("ready_to_scrape.csv", lambda r: r.get("final_status") == "success")
    subset_csv("success_low_quality.csv", lambda r: r.get("final_status") == "success_low_quality")
    subset_csv("prohibited_sources_skipped.csv", lambda r: r.get("is_prohibited_source"))
    subset_csv("bad_urls.csv", lambda r: r.get("error_category") in ("bad_listing_url", "bad_website_url", "not_found", "ssl_error"))
    subset_csv("missing_listing_urls.csv", lambda r: r.get("listing_url_is_missing") and not r.get("url_is_missing"))
    subset_csv("requires_playwright.csv", lambda r: r.get("requires_playwright") or r.get("requires_js"))
    subset_csv("antibot_sources.csv", lambda r: r.get("blocked_by_antibot") or r.get("captcha_detected") or r.get("error_category") in ("antibot", "forbidden", "captcha"))
    subset_csv("domain_down.csv", lambda r: r.get("error_category") in ("domain_down", "dns_error"))
    subset_csv("parser_errors.csv", lambda r: r.get("error_category") in ("parser_error", "no_property_links"))
    subset_csv("zero_properties.csv", lambda r: r.get("zero_properties_detected"))
    subset_csv("misclassified_sources.csv", lambda r: (not r.get("marcada_scrapeable_db", True)) and r.get("final_status") == "success")
    # top problem sources: alto potencial + corregible
    def potential(r):
        try:
            y = int(r.get("expected_property_yield") or 0)
        except Exception:
            y = 0
        fixable = r.get("error_category") in ("bad_listing_url", "missing_listing_url", "cms_unknown",
                                              "no_property_links", "strategy_missing", "strategy_wrong",
                                              "requires_playwright", "low_quality_data", "parser_error")
        return y if fixable else 0
    top = sorted(recs, key=potential, reverse=True)[:200]
    subset_csv("top_problem_sources.csv", lambda r: r in top and potential(r) > 0)

    # summary.md
    total = len(recs)
    lines = [f"# FULL_SOURCE_DIAGNOSTIC_7004 — summary", f"_generado: {now_iso()}_  ·  total diagnosticadas: **{total}**", ""]
    lines.append("## Por final_status")
    for k, v in status.most_common():
        lines.append(f"- `{k}`: {v}")
    lines.append("\n## Por error_category")
    for k, v in cat.most_common():
        lines.append(f"- `{k}`: {v}")
    lines.append("\n## Top CMS detectados")
    for k, v in cms.most_common(10):
        lines.append(f"- {k}: {v}")
    lines.append("\n## Familias de scraper recomendadas")
    for k, v in strat.most_common():
        lines.append(f"- {k}: {v}")
    (out_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")

    # recommended_fixes_by_family.md
    fam = Counter(r.get("recommended_fix_family") for r in recs)
    act = Counter(r.get("recommended_action") for r in recs)
    fl = ["# Fixes recomendados por familia", ""]
    for k, v in fam.most_common():
        fl.append(f"- familia `{k}`: {v}")
    fl.append("\n## Acciones recomendadas")
    for k, v in act.most_common():
        fl.append(f"- `{k}`: {v}")
    (out_dir / "recommended_fixes_by_family.md").write_text("\n".join(fl), encoding="utf-8")
    return {"total": total, "status": dict(status), "category": dict(cat)}


def write_progress(out_dir, processed, total_pending, counts, rate, healthy=True):
    p = {"updated_at": now_iso(), "diagnosticadas_en_corrida": processed,
         "pendientes_en_corrida": max(total_pending - processed, 0),
         "rate_per_s": round(rate, 2), "script_sano": healthy, "categorias": dict(counts)}
    with LOCK:
        (out_dir / "progress.json").write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Censo diagnostico FORENSE read-only (no DB writes, no publish)")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--forensic", action="store_true")
    ap.add_argument("--mode", default="http")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--limit", type=int, default=0, help="Limite de inmobiliarias (0=sin limite). Sanity test.")
    ap.add_argument("--start-offset", type=int, default=0)
    ap.add_argument("--timeout-connect", type=int, default=5)
    ap.add_argument("--timeout-page", type=int, default=12)
    ap.add_argument("--timeout-sample", type=int, default=10)
    ap.add_argument("--sample-properties", type=int, default=3)
    ap.add_argument("--max-listing-pages", type=int, default=2)
    ap.add_argument("--max-links", type=int, default=60)
    ap.add_argument("--out", default=str(REPO_ROOT / "_scratch" / "full_source_diagnostic_7004"))
    ap.add_argument("--fresh", action="store_true", help="Censo limpio (borra results previos del --out)")
    ap.add_argument("--resume", action="store_true", help="Saltea ids ya diagnosticados")
    args = ap.parse_args()

    cfg = {"connect": args.timeout_connect, "page": args.timeout_page, "sample": args.timeout_sample,
           "sample_n": args.sample_properties, "max_links": args.max_links,
           "max_pages": args.max_listing_pages}
    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl = out_dir / "diagnostic_results.jsonl"
    err_log = out_dir / "errors.log"

    if args.fresh and jsonl.exists():
        bak = out_dir / f"diagnostic_results.prev_{int(time.time())}.jsonl"
        jsonl.rename(bak)
        print(f"[diagnose] --fresh: results previos movidos a {bak.name}")

    run_id = f"FULL_SOURCE_DIAGNOSTIC_7004_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"[diagnose] run_id={run_id}")
    print("[diagnose] cargando inmobiliarias (read-only)...")
    inmobs = get_all_inmobiliarias()
    print(f"[diagnose] total registradas: {len(inmobs)}")

    done = load_done_ids(jsonl) if args.resume else set()
    if done:
        print(f"[diagnose] resume: {len(done)} ya hechas, se saltean")
    pending = [(i, x) for i, x in enumerate(inmobs) if x["id"] not in done]
    if args.start_offset:
        pending = pending[args.start_offset:]
    if args.limit and args.limit > 0:
        pending = pending[: args.limit]
    print(f"[diagnose] a procesar: {len(pending)}  (workers={args.workers}, sample={args.sample_properties}, "
          f"timeouts c/p/s={args.timeout_connect}/{args.timeout_page}/{args.timeout_sample})")

    counts = Counter()
    processed = 0
    t0 = time.monotonic()
    last_report = t0
    last_report_n = 0
    total_pending = len(pending)
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(diagnose_forensic, x, idx, cfg, run_id): (idx, x) for idx, x in pending}
        for fut in as_completed(futs):
            idx, x = futs[fut]
            try:
                rec = fut.result()
            except Exception as e:
                rec = base_record()
                rec.update({"diagnostic_run_id": run_id, "diagnosed_at": now_iso(),
                            "source_id": x["id"], "source_name": x.get("nombre"),
                            "final_status": "unexpected_error", "error_category": "unexpected_error",
                            "recommended_action": "retry_later", "error_detail_short": str(e)[:150]})
                with LOCK:
                    with err_log.open("a", encoding="utf-8") as f:
                        f.write(f"{x['id']}: {traceback.format_exc()}\n")
            append_jsonl(jsonl, rec)
            counts[rec.get("error_category") or rec.get("final_status")] += 1
            processed += 1
            # checkpoint cada 100: regenerar progress
            if processed % 100 == 0:
                rate = processed / max(time.monotonic() - t0, 0.1)
                write_progress(out_dir, processed, total_pending, counts, rate)
            # log a stdout cada 250
            if processed % 250 == 0 or processed == total_pending:
                rate = processed / max(time.monotonic() - t0, 0.1)
                eta = (total_pending - processed) / max(rate, 0.01)
                print(f"  [{processed}/{total_pending}] {rate:.1f}/s ETA~{eta/60:.0f}min "
                      f"top={dict(counts.most_common(6))}")

    rate = processed / max(time.monotonic() - t0, 0.1)
    write_progress(out_dir, processed, total_pending, counts, rate)
    print("[diagnose] generando outputs (CSV/MD/subsets)...")
    res = build_outputs(out_dir)
    print(f"[diagnose] LISTO. {processed} diagnosticadas en {(time.monotonic()-t0)/60:.1f} min")
    if res:
        print("[diagnose] status:", res["status"])


if __name__ == "__main__":
    main()
