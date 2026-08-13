#!/usr/bin/env python
"""FULL_SCRAPE_COVERAGE_7004 — campaña de cobertura real (HTTP + Playwright).

Recorre las 7.004 inmobiliarias. exclude_from_scraping=true -> skipped (con motivo).
exclude_from_scraping=false -> intenta EXTRACCION REAL: descubre links de propiedad
siguiendo paginacion y parsea propiedades de verdad (hasta caps de seguridad que se
REGISTRAN: partial_due_to_cap / truncated_by_max_items / truncated_by_max_pages /
truncated_by_timeout).

GARANTIAS:
- NO publica. NO toca public.propiedades / publish_queue / raw / staging.
- DB SOLO read-only (cargar universo + verificar que clasificacion no cambia).
- Escribe SOLO en --out (_scratch). Checkpoint/resume por source_id. No aborta por errores.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import pathlib
import re
import threading
import time
import traceback
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_env(p):
    pp = pathlib.Path(p)
    if not pp.exists():
        return
    for line in pp.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env(REPO_ROOT / ".env")
load_env(REPO_ROOT / ".env.local")

import requests  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402
from scraper.network_security import secure_get  # noqa: E402

PROHIBITED_RE = re.compile(r"(zonaprop|argenprop|properati)\.com", re.I)
EXTERNAL_PORTAL_RE = re.compile(r"(mercadolibre|navent|inmuebles24|imovelweb|infocasas|remax\.com\.ar|"
                                r"facebook\.com|instagram\.com|linktr\.ee)", re.I)
UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"), "Accept-Language": "es-AR,es;q=0.9"}
ANTIBOT_SIGNS = ("just a moment", "cf-browser-verification", "challenge-platform", "_cf_chl",
                 "attention required", "datadome", "perimeterx", "incapsula")
CAPTCHA_SIGNS = ("recaptcha", "hcaptcha", "g-recaptcha", "captcha")
JS_SHELL = ("__next_data__", "window.__nuxt__", "data-reactroot", "ng-version", "please enable javascript",
            "habilita javascript")
PROP_LINK_RE = re.compile(r"(propiedad|propiedades|inmueble|inmuebles|ficha|detalle|emprendimiento|"
                          r"/p/|/prop/|listing|property|/aviso|/venta/|/alquiler/)", re.I)
PAGE_LINK_RE = re.compile(r"(\?page=|/page/|pagina=|&pagina=|paged=|/p-\d+|page-\d+)", re.I)
PRICE_RE = re.compile(r"(u\$s|us\$|usd|ar\$|\$|pesos|dolar)\s*\.?\s*[\d][\d\.\,]{2,}", re.I)
COORD_RE = re.compile(r"(\"lat(itude)?\"\s*[:=]\s*-?\d{1,2}\.\d{3,}|maps[^\"']{0,40}-?\d{1,2}\.\d{3,},-?\d)", re.I)
IMG_BLOCK_RE = re.compile(r"(logo|placeholder|no-?photo|no-?image|sin-?imagen|prop-icons|footer|banner|avatar|icon)", re.I)

LOCK = threading.Lock()

FIELDS = [
    "campaign_run_id", "source_id", "source_name", "website_url", "listing_url", "diagnostic_status",
    "scraping_readiness", "exclude_from_scraping", "attempted", "skipped", "skip_reason", "scraper_used",
    "cms_detectado", "estrategia_scraping", "start_time", "end_time", "duration_seconds", "final_status",
    "error_category", "error_subcategory", "error_detail_short", "error_detail_long", "stack_trace_or_exception",
    "http_status", "final_url_after_redirect", "requires_playwright", "playwright_attempted",
    "property_links_detected", "property_links_count", "properties_detected", "properties_parsed",
    "properties_failed", "partial_due_to_cap", "truncated_by_timeout", "truncated_by_max_pages",
    "truncated_by_max_items", "quality_score_avg", "missing_title_count", "missing_price_count",
    "missing_operation_count", "missing_type_count", "missing_location_count", "missing_images_count",
    "recommended_fix_family", "recommended_next_action", "notes",
]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def base_rec(src, run_id):
    r = {k: None for k in FIELDS}
    r.update({
        "campaign_run_id": run_id, "source_id": src["id"], "source_name": src.get("nombre"),
        "website_url": src.get("web"), "listing_url": src.get("url_listado"),
        "diagnostic_status": src.get("diagnostic_status"), "scraping_readiness": src.get("scraping_readiness"),
        "exclude_from_scraping": src.get("exclude_from_scraping"), "cms_detectado": src.get("cms_detectado"),
        "estrategia_scraping": src.get("estrategia_scraping"), "attempted": False, "skipped": False,
        "requires_playwright": False, "playwright_attempted": False, "property_links_detected": False,
        "property_links_count": 0, "properties_detected": 0, "properties_parsed": 0, "properties_failed": 0,
        "partial_due_to_cap": False, "truncated_by_timeout": False, "truncated_by_max_pages": False,
        "truncated_by_max_items": False, "missing_title_count": 0, "missing_price_count": 0,
        "missing_operation_count": 0, "missing_type_count": 0, "missing_location_count": 0,
        "missing_images_count": 0, "scraper_used": "none",
    })
    return r


def norm_url(u):
    u = (u or "").strip()
    if not u:
        return ""
    return u if re.match(r"^https?://", u, re.I) else "https://" + u


def detect_cms(low, fu):
    fu = (fu or "").lower()
    if "tokkobroker" in low or "tokko" in fu:
        return "tokko"
    if "wp-content" in low or "wp-json" in low:
        return "wordpress"
    if "parastorage" in low or "wix.com" in low:
        return "wix"
    if "/_next/" in low or "__next_data__" in low:
        return "next_spa"
    return "unknown"


def fetch(url, ct, pt):
    out = {"status": None, "html": "", "final": None, "err": None}
    url = norm_url(url)
    try:
        r = secure_get(requests, url, timeout=(ct, pt), headers=UA)
    except requests.exceptions.SSLError as e:
        out["err"] = "ssl_error"; return out
    except requests.exceptions.ConnectTimeout:
        out["err"] = "timeout"; return out
    except requests.exceptions.ReadTimeout:
        out["err"] = "timeout"; return out
    except requests.exceptions.ConnectionError:
        out["err"] = "dns_error"; return out
    except Exception as e:
        out["err"] = "unexpected:" + type(e).__name__; return out
    out["status"] = r.status_code; out["final"] = r.url
    try:
        out["html"] = r.text or ""
    except Exception:
        out["html"] = ""
    return out


def discover_links(html, base_url, max_links):
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")
    host = urlparse(base_url).netloc.lower()
    links, seen, pages = [], set(), set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        full = urljoin(base_url, href)
        if urlparse(full).netloc.lower() not in ("", host):
            continue
        if PAGE_LINK_RE.search(href):
            pages.add(full)
        if not PROP_LINK_RE.search(href):
            continue
        path = urlparse(full).path
        if path.count("/") < 2 and not re.search(r"\d{2,}", path):
            continue
        if full not in seen:
            seen.add(full); links.append(full)
            if len(links) >= max_links:
                break
    return links, list(pages)


def parse_property(url, ct, pt):
    f = {k: False for k in ("title", "price", "operation", "ptype", "location", "images", "coord")}
    r = fetch(url, ct, pt)
    if r["err"] or not r["status"] or r["status"] >= 400:
        return None, r["err"] or f"http_{r['status']}"
    html = r["html"]; low = html.lower()
    if "<title" in low or "<h1" in low:
        f["title"] = True
    if PRICE_RE.search(low):
        f["price"] = True
    if re.search(r"\b(venta|alquiler|alquila|vende|temporario)\b", low):
        f["operation"] = True
    if re.search(r"\b(casa|departamento|depto|ph|terreno|lote|local|oficina|galpon|campo|cochera)\b", low):
        f["ptype"] = True
    if re.search(r"(\"addresslocality\"|\"streetaddress\"|provincia|localidad|\bcalle\b|\bavenida\b)", low):
        f["location"] = True
    imgs = [i.get("src", "") for i in BeautifulSoup(html, "html.parser").find_all("img", src=True)]
    if any(i and not IMG_BLOCK_RE.search(i) for i in imgs):
        f["images"] = True
    if COORD_RE.search(low):
        f["coord"] = True
    return f, None


def fix_family_for(cat):
    return {
        "cms_unknown": "cms", "strategy_missing": "cms", "strategy_wrong": "cms",
        "no_property_links": "parser", "zero_properties": "parser", "parser_error": "parser",
        "bad_listing_url": "url", "missing_listing_url": "url",
        "requires_playwright": "playwright", "playwright_error": "playwright",
        "timeout": "infra", "server_error": "infra", "http_error": "infra",
        "ssl_error": "url", "dns_error": "url", "domain_down": "url",
        "forbidden": "antibot", "captcha": "antibot", "antibot": "antibot",
        "success_low_quality": "quality", "partial_success": "parser", "partial_due_to_cap": "none",
        "success": "none", "skipped_prohibited_source": "prohibited", "skipped_missing_url": "url",
    }.get(cat, "manual")


def process_http(src, cfg, run_id):
    r = base_rec(src, run_id)
    t0 = time.monotonic(); r["start_time"] = now_iso()

    def fin(cat, sub="", short="", long="", action="manual_review", notes=""):
        r["final_status"] = cat; r["error_category"] = cat; r["error_subcategory"] = sub
        r["error_detail_short"] = short; r["error_detail_long"] = long
        r["recommended_fix_family"] = fix_family_for(cat); r["recommended_next_action"] = action
        r["notes"] = notes; r["end_time"] = now_iso(); r["duration_seconds"] = round(time.monotonic() - t0, 2)
        return r

    web = (src.get("web") or "").strip(); listing = (src.get("url_listado") or "").strip()
    hay = f"{web} {listing}".lower()
    # SKIP por exclude_from_scraping
    if src.get("exclude_from_scraping"):
        r["skipped"] = True
        ds = src.get("diagnostic_status")
        cat = {"prohibited_source": "skipped_prohibited_source", "missing_url": "skipped_missing_url",
               "domain_down": "domain_down"}.get(ds, "skipped_prohibited_source" if PROHIBITED_RE.search(hay) else "skipped_missing_url")
        r["skip_reason"] = ds or cat
        return fin(cat, action="skip")
    # doble check prohibidas
    if PROHIBITED_RE.search(hay) or EXTERNAL_PORTAL_RE.search(hay):
        r["skipped"] = True; r["skip_reason"] = "prohibited_url"
        return fin("skipped_prohibited_source", action="skip")

    r["attempted"] = True; r["scraper_used"] = "http"
    target = listing or web
    if not target:
        return fin("missing_listing_url", short="sin URL", action="detect_listing_url")
    fr = fetch(target, cfg["ct"], cfg["pt"])
    r["http_status"] = fr["status"]; r["final_url_after_redirect"] = fr["final"]
    if fr["err"]:
        et = fr["err"]
        if et == "timeout":
            r["truncated_by_timeout"] = True
            return fin("timeout", sub=et, short="http timeout", action="retry_later")
        if et == "ssl_error":
            return fin("ssl_error", short=et, action="fix_listing_url")
        if et == "dns_error":
            return fin("dns_error", short=et, action="skip_domain_down")
        return fin("unexpected_error", sub=et, short=et, action="manual_review")
    st = fr["status"]; html = fr["html"]; low = html.lower()
    if any(x in low for x in ANTIBOT_SIGNS):
        r["requires_playwright"] = True
        return fin("antibot", short=f"http {st}", action="requires_antibot_review")
    if any(x in low for x in CAPTCHA_SIGNS) and len(re.sub(r"<[^>]+>", " ", html).strip()) < 1200:
        return fin("captcha", action="requires_antibot_review")
    if st == 403:
        return fin("forbidden", short="403", action="requires_antibot_review")
    if st == 404:
        return fin("bad_listing_url", short="404", action="fix_listing_url")
    if st and st >= 500:
        return fin("server_error", short=str(st), action="retry_later")
    if st and st >= 400:
        return fin("http_error", short=str(st), action="manual_review")
    cms = detect_cms(low, fr["final"]); r["cms_detectado"] = r["cms_detectado"] or cms
    text = re.sub(r"<[^>]+>", " ", html)
    needs_js = (cms == "next_spa") or (any(x in low for x in JS_SHELL) and len(text.strip()) < 1800)
    if needs_js:
        r["requires_playwright"] = True
        return fin("requires_playwright", short=f"js cms={cms}", action="requires_playwright_runner")

    # DESCUBRIMIENTO con paginacion (hasta max_pages)
    all_links, seen = [], set()
    links, pages = discover_links(html, fr["final"], cfg["max_links"])
    for l in links:
        if l not in seen:
            seen.add(l); all_links.append(l)
    pages_visited = 1
    for purl in pages[: cfg["max_pages"] - 1]:
        if len(all_links) >= cfg["max_links"]:
            r["truncated_by_max_pages"] = True; break
        pr = fetch(purl, cfg["ct"], cfg["pt"]); pages_visited += 1
        if pr["status"] and pr["status"] < 400:
            l2, _ = discover_links(pr["html"], pr["final"], cfg["max_links"])
            for l in l2:
                if l not in seen:
                    seen.add(l); all_links.append(l)
    if len(pages) > cfg["max_pages"]:
        r["truncated_by_max_pages"] = True
    r["property_links_detected"] = len(all_links) > 0
    r["property_links_count"] = len(all_links)
    r["properties_detected"] = len(all_links)
    if not all_links:
        if cms == "unknown":
            return fin("cms_unknown", short="cms desconocido sin links", action="detect_cms")
        return fin("no_property_links", short=f"cms={cms} 0 links", action="fix_parser")

    # EXTRACCION REAL (hasta max_items)
    to_parse = all_links[: cfg["max_items"]]
    if len(all_links) > cfg["max_items"]:
        r["partial_due_to_cap"] = True; r["truncated_by_max_items"] = True
    agg = Counter(); parsed = failed = 0; last_err = None
    for purl in to_parse:
        try:
            f, err = parse_property(purl, cfg["ct"], cfg["prop_t"])
        except Exception as e:
            failed += 1; last_err = type(e).__name__; continue
        if f is None:
            failed += 1; last_err = err; continue
        parsed += 1
        for k, v in f.items():
            if v:
                agg[k] += 1
    r["properties_parsed"] = parsed; r["properties_failed"] = failed
    n = max(parsed, 1)
    r["missing_title_count"] = parsed - agg["title"]
    r["missing_price_count"] = parsed - agg["price"]
    r["missing_operation_count"] = parsed - agg["operation"]
    r["missing_type_count"] = parsed - agg["ptype"]
    r["missing_location_count"] = parsed - agg["location"]
    r["missing_images_count"] = parsed - agg["images"]
    if parsed == 0:
        return fin("parser_error", sub=last_err or "", short="links pero 0 parseadas",
                   long=f"detectadas={len(all_links)} failed={failed}", action="fix_parser")
    score = int(round(100 * (
        0.22 * agg["title"] / n + 0.22 * agg["price"] / n + 0.16 * agg["operation"] / n +
        0.14 * agg["ptype"] / n + 0.10 * agg["location"] / n + 0.08 * agg["images"] / n + 0.08 * agg["coord"] / n)))
    r["quality_score_avg"] = score
    notes = ("cap %d/%d" % (parsed, len(all_links))) if r["partial_due_to_cap"] else ""
    if r["partial_due_to_cap"]:
        return fin("partial_due_to_cap", short=f"q={score} parsed={parsed}/{len(all_links)}",
                   action="ready_to_scrape" if score >= 55 else "fix_parser", notes=notes)
    if score >= 55:
        return fin("success", short=f"q={score} n={parsed}", action="ready_to_scrape")
    return fin("success_low_quality", short=f"q={score} n={parsed}", action="fix_parser")


# ---------------- DB read-only ----------------
def get_universe():
    import psycopg
    conn = psycopg.connect(os.getenv("INTERNAL_DB_URL"), connect_timeout=40); conn.autocommit = True
    cur = conn.cursor(); cur.execute("SET default_transaction_read_only = on")
    cur.execute("""SELECT id,nombre,web,url_listado,provincia,ciudad,cms_detectado,estrategia_scraping,
                   diagnostic_status,scraping_readiness,exclude_from_scraping,coalesce(total_propiedades,0)
                   FROM public.inmobiliarias_main ORDER BY id""")
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.execute("SELECT md5(coalesce(string_agg(id||coalesce(sitio_activo::text,'')||coalesce(cms_detectado,'')||"
                "coalesce(estrategia_scraping,'')||coalesce(url_listado,'')||coalesce(diagnostic_status,'')||"
                "coalesce(scraping_readiness,'')||coalesce(exclude_from_scraping::text,''), ',' ORDER BY id),'')) "
                "FROM public.inmobiliarias_main")
    chk = cur.fetchone()[0]
    conn.close()
    return rows, chk


def verify_no_change(chk_before):
    _, chk_after = get_universe()
    return chk_after == chk_before


def append_jsonl(p, rec):
    with LOCK:
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")


def load_done(p):
    done = set()
    if p.exists():
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.strip():
                try:
                    done.add(json.loads(line)["source_id"])
                except Exception:
                    pass
    return done


def build_outputs(out_dir):
    jl = out_dir / "source_results.jsonl"
    recs = [json.loads(l) for l in jl.read_text(encoding="utf-8").splitlines() if l.strip()] if jl.exists() else []
    with (out_dir / "source_results.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore"); w.writeheader()
        for r in recs:
            w.writerow(r)

    def y(r):
        try:
            return int(r.get("properties_detected") or 0)
        except Exception:
            return 0
    SUB = ["source_id", "source_name", "website_url", "listing_url", "final_status", "error_category",
           "property_links_count", "properties_detected", "properties_parsed", "quality_score_avg",
           "recommended_fix_family", "recommended_next_action", "error_detail_short"]

    def sub(name, pred):
        with (out_dir / name).open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=SUB, extrasaction="ignore"); w.writeheader()
            for r in sorted([x for x in recs if pred(x)], key=y, reverse=True):
                w.writerow(r)
    sub("success_sources.csv", lambda r: r["final_status"] == "success")
    sub("partial_success_sources.csv", lambda r: r["final_status"] in ("partial_success", "partial_due_to_cap"))
    sub("failed_sources.csv", lambda r: not r["skipped"] and r["final_status"] not in ("success", "success_low_quality", "partial_due_to_cap", "partial_success"))
    sub("skipped_sources.csv", lambda r: r["skipped"])
    sub("requires_cms_fix.csv", lambda r: r["recommended_fix_family"] == "cms")
    sub("requires_parser_fix.csv", lambda r: r["recommended_fix_family"] == "parser")
    sub("requires_listing_url_fix.csv", lambda r: r["recommended_fix_family"] == "url" and not r["skipped"])
    sub("requires_playwright_fix.csv", lambda r: r["recommended_fix_family"] == "playwright" or r.get("requires_playwright"))
    sub("timeout_sources.csv", lambda r: r["final_status"] == "timeout")
    sub("domain_down_sources.csv", lambda r: r["final_status"] in ("domain_down", "dns_error"))
    sub("prohibited_skipped.csv", lambda r: r["final_status"] == "skipped_prohibited_source")
    sub("quality_issues.csv", lambda r: r["final_status"] == "success_low_quality" or (r.get("quality_score_avg") or 100) < 55)

    # errors detailed
    errs = [r for r in recs if not r["skipped"] and r["final_status"] not in ("success", "success_low_quality", "partial_due_to_cap")]
    with (out_dir / "errors_detailed.jsonl").open("w", encoding="utf-8") as f:
        for r in errs:
            f.write(json.dumps({k: r.get(k) for k in ("source_id", "source_name", "final_status", "error_category",
                    "error_subcategory", "error_detail_short", "error_detail_long", "stack_trace_or_exception",
                    "http_status", "recommended_fix_family")}, ensure_ascii=False) + "\n")
    with (out_dir / "errors_detailed.csv").open("w", encoding="utf-8", newline="") as f:
        cols = ["source_id", "source_name", "final_status", "error_category", "error_subcategory",
                "error_detail_short", "http_status", "recommended_fix_family"]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader()
        for r in errs:
            w.writerow(r)
    freq = Counter(r["error_category"] for r in errs)
    with (out_dir / "top_errors_by_frequency.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f); w.writerow(["error_category", "count"]); [w.writerow(x) for x in freq.most_common()]
    impact = defaultdict(int)
    for r in errs:
        impact[r["error_category"]] += y(r)
    with (out_dir / "top_errors_by_impact.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f); w.writerow(["error_category", "links_detectados_sum"])
        for k, v in sorted(impact.items(), key=lambda x: -x[1]):
            w.writerow([k, v])
    fam = Counter(r["recommended_fix_family"] for r in recs if not r["skipped"])
    (out_dir / "recommended_fixes_by_family.md").write_text(
        "# Fixes por familia\n\n" + "\n".join(f"- `{k}`: {v}" for k, v in fam.most_common()), encoding="utf-8")
    (out_dir / "rerun_plan_after_fixes.md").write_text(
        "# Plan de rerun después de fixes\n\n"
        "1. Aplicar fixes por familia (cms -> parser -> url -> playwright).\n"
        "2. Re-correr esta campaña (resume) sobre las que tenían error.\n"
        "3. Las `success`/`partial` ya son aptas para corrida productiva real (raw/staging) por tandas.\n", encoding="utf-8")

    st = Counter(r["final_status"] for r in recs)
    L = [f"# FULL_SCRAPE_COVERAGE_7004 — summary", f"_generado: {now_iso()}_  ·  total: **{len(recs)}**", "",
         "## Por final_status"]
    for k, v in st.most_common():
        L.append(f"- `{k}`: {v}")
    attempted = sum(1 for r in recs if r["attempted"])
    skipped = sum(1 for r in recs if r["skipped"])
    succ = sum(1 for r in recs if r["final_status"] == "success")
    part = sum(1 for r in recs if r["final_status"] in ("partial_success", "partial_due_to_cap"))
    props = sum(y(r) for r in recs)
    parsed = sum(int(r.get("properties_parsed") or 0) for r in recs)
    L += ["", f"intentadas: {attempted} · skipped: {skipped} · success: {succ} · partial: {part}",
          f"propiedades detectadas (links): {props} · parseadas: {parsed}"]
    (out_dir / "campaign_summary.md").write_text("\n".join(L), encoding="utf-8")
    return {"total": len(recs), "status": dict(st.most_common())}


def main():
    ap = argparse.ArgumentParser(description="FULL_SCRAPE_COVERAGE_7004 (no DB writes, no publish)")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--full-extract", action="store_true")
    ap.add_argument("--mode", choices=["http"], default="http")
    ap.add_argument("--http-workers", type=int, default=16)
    ap.add_argument("--playwright-workers", type=int, default=4)
    ap.add_argument("--timeout-connect", type=int, default=5)
    ap.add_argument("--timeout-page", type=int, default=12)
    ap.add_argument("--timeout-property", type=int, default=10)
    ap.add_argument("--playwright-listing-timeout", type=int, default=25)
    ap.add_argument("--playwright-property-timeout", type=int, default=18)
    ap.add_argument("--max-items", type=int, default=40, help="cap de seguridad: fichas parseadas por inmobiliaria")
    ap.add_argument("--max-pages", type=int, default=5, help="cap de seguridad: paginas de listado por inmobiliaria")
    ap.add_argument("--max-links", type=int, default=1500)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=str(REPO_ROOT / "_scratch" / "full_scrape_coverage_7004"))
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    cfg = {"ct": args.timeout_connect, "pt": args.timeout_page, "prop_t": args.timeout_property,
           "max_items": args.max_items, "max_pages": args.max_pages, "max_links": args.max_links}
    out_dir = pathlib.Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)
    jl = out_dir / "source_results.jsonl"; logf = out_dir / "execution.log"
    if args.fresh and jl.exists():
        jl.rename(out_dir / f"source_results.prev_{int(time.time())}.jsonl")

    run_id = f"FULL_SCRAPE_COVERAGE_7004_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"[campaign] run_id={run_id} | cargando universo (read-only)...")
    universe, chk_before = get_universe()
    print(f"[campaign] universo={len(universe)} | checksum_clasificacion={chk_before[:12]}")
    done = load_done(jl) if args.resume else set()
    pending = [u for u in universe if u["id"] not in done]
    if args.limit:
        pending = pending[: args.limit]
    print(f"[campaign] pending={len(pending)} workers={args.http_workers} max_items={args.max_items} max_pages={args.max_pages}")

    counts = Counter(); processed = 0; t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.http_workers) as ex:
        futs = {ex.submit(process_http, u, cfg, run_id): u for u in pending}
        for fut in as_completed(futs):
            u = futs[fut]
            try:
                rec = fut.result()
            except Exception as e:
                rec = base_rec(u, run_id)
                rec.update({"final_status": "unexpected_error", "error_category": "unexpected_error",
                            "attempted": True, "stack_trace_or_exception": traceback.format_exc()[:500],
                            "error_detail_short": str(e)[:150], "recommended_fix_family": "manual",
                            "start_time": now_iso(), "end_time": now_iso()})
                with LOCK:
                    with logf.open("a", encoding="utf-8") as f:
                        f.write(f"{u['id']}: {repr(e)[:300]}\n")
            append_jsonl(jl, rec)
            counts[rec["final_status"]] += 1; processed += 1
            if processed % 100 == 0:
                with LOCK:
                    (out_dir / "progress.json").write_text(json.dumps(
                        {"updated_at": now_iso(), "processed": processed, "pending": len(pending),
                         "rate_per_s": round(processed / max(time.monotonic() - t0, 0.1), 2),
                         "by_status": dict(counts)}, ensure_ascii=False, indent=2), encoding="utf-8")
            if processed % 500 == 0 or processed == len(pending):
                rate = processed / max(time.monotonic() - t0, 0.1)
                eta = (len(pending) - processed) / max(rate, 0.01)
                print(f"  [{processed}/{len(pending)}] {rate:.1f}/s ETA~{eta/60:.0f}min top={dict(counts.most_common(7))}")

    print("[campaign] verificando que la clasificacion NO cambio (checksum)...")
    unchanged = verify_no_change(chk_before)
    print(f"[campaign] clasificacion_sin_cambios={unchanged}")
    print("[campaign] generando outputs...")
    res = build_outputs(out_dir)
    (out_dir / "progress.json").write_text(json.dumps(
        {"updated_at": now_iso(), "processed": processed, "done": True,
         "clasificacion_sin_cambios": unchanged, "by_status": dict(counts)}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[campaign] LISTO en {(time.monotonic()-t0)/60:.1f} min. {res}")


if __name__ == "__main__":
    main()
