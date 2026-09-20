#!/usr/bin/env python
"""Faceted listing discovery — mejora general para descubrir más propiedades.

Problema que resuelve:
  El scraper actual solo visita la URL base de cada inmobiliaria y sus variantes
  hardcodeadas. Pierde propiedades en sitios que separan sus listados por:
  operación (venta/alquiler), tipo (casa/departamento/terreno), o paginación.

Estrategias implementadas:
  1. URL path combinations: base × operacion_paths × tipo_paths
  2. Query param combinations: ?operacion=venta&tipo=casa, etc.
  3. Pagination following per discovered URL
  4. Select/form enumeration via Playwright (--allow-playwright)
  5. Deduplication by normalized URL

No escribe Neon, Supabase, .env ni frontend.
No scrapea Zonaprop ni Argenprop.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse, parse_qsl, urlencode, urlunparse, unquote

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M")

try:
    import requests
    from bs4 import BeautifulSoup
    from scraper.network_security import secure_get
    HAS_HTTP = True
except ImportError:
    HAS_HTTP = False

PROHIBITED_DOMAINS = re.compile(r"(^|\.)(?:zonaprop|argenprop)\.com\.ar$", re.I)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept-Language": "es-AR,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
}

# ─── Property URL detection ───────────────────────────────────────────────────
PROPERTY_URL_RE = re.compile(
    r"/(?:propiedad|property|inmueble|inmuebles|listing|ficha|detalle|imovel|"
    r"item|prop|p/)[/\-]?\d+",
    re.I,
)
PROPERTY_URL_SLUG_RE = re.compile(
    r"/(?:propiedad|property|inmueble|ficha|detalle|listing)/[a-z0-9\-]{4,}",
    re.I,
)
NON_PROPERTY_RE = re.compile(
    r"(zonaprop|argenprop|instagram|facebook|whatsapp|wa\.me|linkedin|"
    r"youtube|twitter|x\.com|tasacion|contacto|nosotros|blog|noticia|"
    r"login|admin|wp-admin|subi-tu-propiedad|publicar|mapa|maps|"
    r"gracias|thank|enviado|newsletter)",
    re.I,
)

# ─── Filter path segments ─────────────────────────────────────────────────────
OPERACION_PATHS = {
    "venta": ["venta", "ventas", "comprar", "sale", "for-sale", "en-venta"],
    "alquiler": ["alquiler", "alquileres", "alq", "rent", "for-rent", "en-alquiler"],
    "temporario": ["temporario", "temporada", "turismo", "vacacional", "temporal"],
}

TIPO_PATHS = {
    "casa": ["casas", "casa", "houses"],
    "departamento": ["departamentos", "departamento", "deptos", "depto", "apartments"],
    "terreno": ["terrenos", "terreno", "lotes", "lote", "tierra"],
    "local": ["locales", "local", "comercial", "comerciales"],
    "oficina": ["oficinas", "oficina"],
    "campo": ["campos", "campo", "rural", "chacras", "quintas"],
    "cochera": ["cocheras", "cochera", "garages"],
    "galpon": ["galpones", "galpon", "industrial"],
}

# Common query param names for filters
OPERACION_PARAMS = ["operacion", "operation", "tipo_operacion", "purpose", "for", "op"]
TIPO_PARAMS = ["tipo", "type", "property_type", "category", "cat", "propiedad"]
PAGE_PARAMS = ["p", "pagina", "page", "pag", "offset", "start", "pg"]

MAX_PAGES = 8
MAX_COMBOS = 40
RATE_LIMIT = 1.2


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _domain(url: str) -> str:
    try: return urlparse(url).netloc.lower().lstrip("www.")
    except ValueError:
        return ""


def _norm_url(url: str) -> str:
    """Normalize for deduplication."""
    try:
        p = urlparse(url.rstrip("/"))
        host = p.netloc.lower().lstrip("www.")
        path = p.path.rstrip("/").lower()
        # remove tracking params
        qs = "&".join(
            f"{k}={v}" for k, v in sorted(parse_qsl(p.query))
            if not k.startswith("utm_") and k not in {"fbclid","gclid","_"}
        )
        return f"{host}{path}" + (f"?{qs}" if qs else "")
    except Exception:
        return url.lower().rstrip("/")


def _is_property_url(url: str) -> bool:
    if NON_PROPERTY_RE.search(url):
        return False
    return bool(PROPERTY_URL_RE.search(url) or PROPERTY_URL_SLUG_RE.search(url))


def _fetch(session, url: str, timeout: int = 12) -> Optional[str]:
    try:
        r = secure_get(session, url, timeout=(8, timeout))
        if r.status_code == 200:
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text
        return None
    except Exception:
        return None


def _extract_property_links(html: str, base_url: str) -> Set[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: Set[str] = set()
    base_domain = _domain(base_url)
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue
        full = urljoin(base_url, href).split("#")[0]
        if _domain(full) == base_domain and _is_property_url(full):
            links.add(full.rstrip("/"))
    return links


def _detect_pagination(html: str, base_url: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    pager = (
        soup.find(class_=re.compile(r"\bpaginat|pager|paginator\b", re.I))
        or soup.find("nav", {"aria-label": re.compile(r"pag", re.I)})
    )
    result = {"type": "none", "param": None, "max_page": 1}
    if not pager:
        # Also search all links for page-like hrefs
        pages = []
        for a in soup.find_all("a", href=True):
            href = urljoin(base_url, a["href"])
            for pp in PAGE_PARAMS:
                m = re.search(rf"[?&]{pp}=(\d+)", href)
                if m:
                    pages.append((pp, int(m.group(1))))
        if pages:
            param, _ = max(pages, key=lambda x: x[1])
            result["type"] = "query_param"
            result["param"] = param
            result["max_page"] = max(p for _, p in pages)
        return result

    pages = []
    for a in pager.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        for pp in PAGE_PARAMS:
            m = re.search(rf"[?&]{pp}=(\d+)", href)
            if m:
                pages.append((pp, int(m.group(1))))
        m = re.search(r"/(?:page|pagina|p)/(\d+)", href)
        if m:
            result["type"] = "path_segment"
            pages.append(("_path", int(m.group(1))))
    if pages:
        param, _ = max(pages, key=lambda x: x[1])
        if result["type"] == "none":
            result["type"] = "query_param"
            result["param"] = param
        result["max_page"] = max(p for _, p in pages)
    return result


def _follow_pagination(session, base_url: str, pag_info: Dict, first_links: Set[str]) -> Tuple[Set[str], int]:
    """Follow pagination and return (new_links, pages_visited)."""
    all_links: Set[str] = set(first_links)
    parsed = urlparse(base_url)
    pages_visited = 1

    if pag_info["type"] == "none":
        return set(), 0

    for page_num in range(2, MAX_PAGES + 1):
        time.sleep(RATE_LIMIT)
        if pag_info["type"] == "query_param" and pag_info.get("param"):
            params = dict(parse_qsl(parsed.query))
            params[pag_info["param"]] = str(page_num)
            page_url = urlunparse(parsed._replace(query=urlencode(params)))
        elif pag_info["type"] == "path_segment":
            page_url = f"{base_url.rstrip('/')}/pagina-{page_num}"
        else:
            break

        html = _fetch(session, page_url)
        if not html:
            break
        links = _extract_property_links(html, base_url)
        new = links - all_links
        if not new:
            break
        all_links.update(links)
        pages_visited += 1

    return all_links - first_links, pages_visited


def _generate_static_candidates(base_url: str, max_combos: int = MAX_COMBOS) -> List[Tuple[str, str]]:
    """Generate candidate listing URLs from path combinations."""
    candidates: List[Tuple[str, str]] = []
    seen: Set[str] = set()
    parsed = urlparse(base_url)
    root = f"{parsed.scheme}://{parsed.netloc}"

    def add(url: str, label: str) -> None:
        n = _norm_url(url)
        if n not in seen:
            seen.add(n)
            candidates.append((url, label))

    # 1. Direct operation paths
    for op, paths in OPERACION_PATHS.items():
        for p in paths[:2]:
            add(f"{root}/{p}", f"op_{op}_{p}")
            add(f"{root}/propiedades/{p}", f"propiedades_op_{op}")
            add(f"{root}/inmuebles/{p}", f"inmuebles_op_{op}")

    # 2. Direct tipo paths
    for tipo, paths in TIPO_PATHS.items():
        for p in paths[:1]:
            add(f"{root}/{p}", f"tipo_{tipo}")
            add(f"{root}/propiedades/{p}", f"prop_tipo_{tipo}")

    # 3. Operation × Tipo combinations (most common pattern)
    for op, op_paths in OPERACION_PATHS.items():
        op_path = op_paths[0]
        for tipo, tipo_paths in TIPO_PATHS.items():
            tipo_path = tipo_paths[0]
            add(f"{root}/{op_path}/{tipo_path}", f"combo_{op}_{tipo}")
            add(f"{root}/propiedades/{op_path}/{tipo_path}", f"prop_combo_{op}_{tipo}")
            if len(candidates) >= max_combos:
                return candidates

    # 4. Query param combinations
    for op, op_paths in OPERACION_PATHS.items():
        for param in OPERACION_PARAMS[:2]:
            add(f"{root}/propiedades?{param}={op}", f"qprop_{param}_{op}")
            add(f"{root}/buscar?{param}={op}", f"qbuscar_{param}_{op}")
            add(f"{root}/inmuebles?{param}={op}", f"qinm_{param}_{op}")

    # 5. Common listing paths
    for path in ["/propiedades", "/inmuebles", "/listing", "/listings", "/propiedades/venta",
                 "/propiedades/alquiler", "/buscar", "/catalogo"]:
        add(root + path, f"std_{path.lstrip('/')}")

    return candidates[:max_combos]


def _detect_selects(html: str) -> Dict[str, List[str]]:
    """Detect select elements for filter enumeration."""
    soup = BeautifulSoup(html, "html.parser")
    result: Dict[str, List[str]] = {}
    for sel in soup.find_all("select"):
        name = sel.get("name") or sel.get("id") or "unnamed"
        options = []
        for opt in sel.find_all("option"):
            val = opt.get("value", "").strip()
            txt = opt.get_text(strip=True)
            if val and val not in ("", "0", "-1"):
                options.append({"value": val, "text": txt})
        if options:
            result[name] = options
    return result


def _playwright_enumerate_selects(url: str, select_info: Dict[str, List[Dict]]) -> Dict[str, Set[str]]:
    """Use Playwright to enumerate select options and collect property links per option."""
    results: Dict[str, Set[str]] = defaultdict(set)
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        print("  Playwright not available — skipping JS select enumeration")
        return results

    # Focus on operation-related selects
    op_select_keys = [k for k in select_info if any(
        kw in k.lower() for kw in ["operacion", "operation", "tipo_op", "purpose", "op"]
    )]
    tipo_select_keys = [k for k in select_info if any(
        kw in k.lower() for kw in ["tipo", "type", "category", "propiedad"]
    )]

    target_selects = op_select_keys[:2] + tipo_select_keys[:2]
    if not target_selects:
        target_selects = list(select_info.keys())[:3]

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=HEADERS["User-Agent"],
                locale="es-AR",
            )
            page = context.new_page()
            page.goto(url, timeout=25000, wait_until="domcontentloaded")
            time.sleep(2)

            base_domain = _domain(url)

            def collect_visible_links() -> Set[str]:
                links: Set[str] = set()
                try:
                    hrefs = page.eval_on_selector_all(
                        "a[href]",
                        "els => els.map(e => e.href)"
                    )
                    for href in hrefs:
                        if _domain(href) == base_domain and _is_property_url(href):
                            links.add(href.rstrip("/"))
                except Exception:
                    pass
                return links

            for sel_name in target_selects:
                options = select_info.get(sel_name, [])
                selector = f"select[name='{sel_name}'], select[id='{sel_name}']"
                for opt in options[:8]:  # max 8 options per select
                    try:
                        page.goto(url, timeout=20000, wait_until="domcontentloaded")
                        time.sleep(1.5)
                        page.select_option(selector, value=opt["value"])
                        # Some sites submit form, others react to change
                        try:
                            submit = page.query_selector("button[type='submit'], input[type='submit'], .btn-buscar, .search-btn")
                            if submit:
                                submit.click()
                        except Exception:
                            pass
                        time.sleep(2.5)  # wait for AJAX
                        links = collect_visible_links()
                        key = f"{sel_name}={opt['value']}({opt['text']})"
                        results[key].update(links)
                        print(f"    [PW select {sel_name}={opt['text']}] links={len(links)}")
                    except Exception as exc:
                        print(f"    [PW error for {sel_name}={opt.get('value')}]: {str(exc)[:60]}")

            browser.close()
    except Exception as exc:
        print(f"  Playwright global error: {str(exc)[:100]}")

    return results


def discover_domain(
    session,
    base_url: str,
    label: str,
    allow_playwright: bool,
    out_dir: Path,
) -> Dict[str, Any]:
    """Full faceted discovery for one domain."""
    print(f"\n{'='*64}")
    print(f"FACETED DISCOVERY: {label}")
    print(f"URL: {base_url}")
    print(f"{'='*64}")

    domain = _domain(base_url)
    if PROHIBITED_DOMAINS.search(domain):
        print("  BLOCKED: dominio prohibido")
        return {"label": label, "base_url": base_url, "blocked": True}

    result = {
        "label": label,
        "base_url": base_url,
        "property_links_before": 0,
        "property_links_after": 0,
        "combinations_tried": 0,
        "pages_visited": 0,
        "playwright_used": False,
        "select_combos_tried": 0,
        "errors": [],
        "combo_detail": [],
        "all_links": set(),
    }

    # Baseline: base page
    base_html = _fetch(session, base_url)
    if not base_html:
        print("  ERROR: base URL HTTP failed")
        result["errors"].append("base_http_failed")
        return result

    base_links = _extract_property_links(base_html, base_url)
    result["property_links_before"] = len(base_links)
    result["all_links"].update(base_links)
    print(f"  Base page: {len(base_links)} property links")

    # Detect selects for Playwright
    selects = _detect_selects(base_html)
    if selects:
        print(f"  Selects detected: {list(selects.keys())}")

    # Static combinations
    candidates = _generate_static_candidates(base_url)
    candidates.insert(0, (base_url, "base"))  # always include base

    for cand_url, cand_label in candidates:
        if result["combinations_tried"] >= MAX_COMBOS:
            print(f"  MAX_COMBOS ({MAX_COMBOS}) reached")
            break
        result["combinations_tried"] += 1
        time.sleep(RATE_LIMIT)

        if cand_url == base_url:
            html = base_html
        else:
            html = _fetch(session, cand_url)

        if not html:
            result["combo_detail"].append({
                "url": cand_url, "label": cand_label,
                "links": 0, "new": 0, "pag_new": 0, "pag_type": "none", "status": "http_failed",
            })
            continue

        links = _extract_property_links(html, base_url)
        new_links = links - result["all_links"]

        if not links and cand_url != base_url:
            result["combo_detail"].append({
                "url": cand_url, "label": cand_label,
                "links": 0, "new": 0, "pag_new": 0, "pag_type": "none", "status": "empty",
            })
            continue

        result["all_links"].update(links)
        pag_info = _detect_pagination(html, cand_url)

        pag_new: Set[str] = set()
        if pag_info["type"] != "none":
            time.sleep(RATE_LIMIT)
            pag_new, pag_pages = _follow_pagination(session, cand_url, pag_info, links)
            result["all_links"].update(pag_new)
            result["pages_visited"] += pag_pages
        else:
            pag_pages = 1

        result["combo_detail"].append({
            "url": cand_url, "label": cand_label,
            "links": len(links), "new": len(new_links), "pag_new": len(pag_new),
            "pag_type": pag_info["type"], "status": "ok",
        })

        total_new = len(new_links) + len(pag_new)
        if total_new > 0 or cand_url == base_url:
            print(f"  [{cand_label}] links={len(links)} new={len(new_links)} pag_new={len(pag_new)} pag={pag_info['type']}")

    # Playwright select enumeration (if enabled and selects found)
    if allow_playwright and selects:
        print(f"\n  === Playwright select enumeration ===")
        result["playwright_used"] = True
        pw_results = _playwright_enumerate_selects(base_url, selects)
        for combo_key, combo_links in pw_results.items():
            new = combo_links - result["all_links"]
            result["all_links"].update(combo_links)
            result["select_combos_tried"] += 1
            if combo_links:
                print(f"  [PW {combo_key}] total={len(combo_links)} new={len(new)}")
                result["combo_detail"].append({
                    "url": f"playwright://{combo_key}", "label": f"pw_{combo_key}",
                    "links": len(combo_links), "new": len(new), "pag_new": 0,
                    "pag_type": "playwright", "status": "ok",
                })

    result["property_links_after"] = len(result["all_links"])
    gain = result["property_links_after"] - result["property_links_before"]
    print(f"\n  RESULT: before={result['property_links_before']} after={result['property_links_after']} gain=+{gain}")
    print(f"  combos={result['combinations_tried']} pw_combos={result['select_combos_tried']}")

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Faceted listing discovery for any inmobiliaria domain")
    parser.add_argument("--urls", nargs="+", help="Base listing URLs to process (space-separated)")
    parser.add_argument("--csv-input", type=Path, help="CSV with 'url' and 'label' columns")
    parser.add_argument("--allow-playwright", action="store_true", help="Enable Playwright for JS select enumeration")
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--workers", type=int, default=1, help="Parallel workers (1-3)")
    parser.add_argument("--limit", type=int, default=0, help="Max domains to process; 0=all")
    args = parser.parse_args()

    if not HAS_HTTP:
        raise SystemExit("Install: pip install requests beautifulsoup4")

    out_dir = args.out_dir or (REPO / "reports" / "scraping_runs" / f"faceted_discovery_{TIMESTAMP}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Build target list
    targets: List[Tuple[str, str]] = []  # (url, label)

    if args.csv_input:
        csv_path = args.csv_input if args.csv_input.is_absolute() else REPO / args.csv_input
        with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                url = row.get("url") or row.get("base_url") or ""
                label = row.get("label") or row.get("dominio") or _domain(url)
                if url and url.startswith("http"):
                    targets.append((url, label))
    elif args.urls:
        for u in args.urls:
            targets.append((u, _domain(u)))
    else:
        # Default: 5 diagnostic domains
        targets = [
            ("https://zamoranopropiedades.com.ar", "zamoranopropiedades.com.ar"),
            ("https://almironpropiedades.com.ar", "almironpropiedades.com.ar"),
            ("https://olmospropiedades.com.ar", "olmospropiedades.com.ar"),
            ("https://freijopropiedades.com.ar", "freijopropiedades.com.ar"),
            ("https://villegaspropiedades.com", "villegaspropiedades.com"),
        ]

    if args.limit:
        targets = targets[:args.limit]

    print("=" * 68)
    print("FACETED LISTING DISCOVERY")
    print(f"targets={len(targets)}")
    print(f"allow_playwright={args.allow_playwright}")
    print(f"max_combos_per_domain={MAX_COMBOS}")
    print(f"max_pages_per_combo={MAX_PAGES}")
    print(f"out_dir={out_dir}")
    print("supabase_write=false | neon_write=false | no_geocoding=true")
    print("=" * 68)

    session = requests.Session()
    session.headers.update(HEADERS)

    t0 = time.time()
    all_results: List[Dict] = []

    for url, label in targets:
        res = discover_domain(session, url, label, args.allow_playwright, out_dir)
        # Convert set to list for serialization
        res["all_links"] = list(res.get("all_links", set()))
        all_results.append(res)
        time.sleep(2.0)

    elapsed = round(time.time() - t0, 1)

    # ── Reports ──────────────────────────────────────────────────────────────
    # 1. Summary CSV
    summary_csv = out_dir / "property_links_before_after.csv"
    with summary_csv.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "label", "base_url", "links_before", "links_after", "gain",
            "combos", "pages", "playwright_used", "pw_combos", "errors",
        ])
        w.writeheader()
        for r in all_results:
            w.writerow({
                "label": r.get("label"),
                "base_url": r.get("base_url"),
                "links_before": r.get("property_links_before", 0),
                "links_after": r.get("property_links_after", 0),
                "gain": r.get("property_links_after", 0) - r.get("property_links_before", 0),
                "combos": r.get("combinations_tried", 0),
                "pages": r.get("pages_visited", 0),
                "playwright_used": r.get("playwright_used", False),
                "pw_combos": r.get("select_combos_tried", 0),
                "errors": "; ".join(r.get("errors", [])),
            })

    # 2. Combinations CSV
    combo_csv = out_dir / "tested_combinations.csv"
    with combo_csv.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["domain","url","label","links","new","pag_new","pag_type","status"])
        w.writeheader()
        for r in all_results:
            for c in r.get("combo_detail", []):
                c["domain"] = r.get("label")
                w.writerow(c)

    # 3. Discovered URLs CSV
    disc_csv = out_dir / "discovered_listing_urls.csv"
    with disc_csv.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["domain", "url"])
        w.writeheader()
        for r in all_results:
            for u in r.get("all_links", []):
                w.writerow({"domain": r.get("label"), "url": u})

    # 4. Recommendations markdown
    recs = [
        "# Faceted discovery — recomendaciones",
        "",
        f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## Por dominio",
        "",
    ]
    for r in all_results:
        before = r.get("property_links_before", 0)
        after = r.get("property_links_after", 0)
        gain = after - before
        recs.append(f"### {r.get('label')}")
        recs.append(f"- before={before} after={after} gain=+{gain}")
        if gain > 0:
            recs.append(f"- **Mejora posible: +{gain} propiedades adicionales**")
            recs.append("- Acción: agregar rutas de faceted discovery en el scraper")
        elif before == 0 and after == 0:
            recs.append("- Sitio JS-only: propiedades cargadas por AJAX, no accesibles via HTML estático")
            recs.append("- Acción requerida: Playwright + select enumeration para capturar")
        else:
            recs.append("- Sin mejora detectada con faceted discovery estático")
        recs.append("")

    recs += [
        "## Mejora general propuesta para el scraper",
        "",
        "En `_generic_candidate_urls()` (línea 9853 de scraper_propiedades.py):",
        "Agregar generación de combinaciones operacion×tipo:",
        "",
        "```python",
        "# ANTES: solo 16 rutas hardcodeadas",
        "_UNIVERSAL_LISTING_PATHS = ['/propiedades', '/venta', '/alquiler', ...]",
        "",
        "# DESPUÉS: también probar combinaciones",
        "for op_path in ['venta', 'alquiler']:",
        "    for tipo_path in ['casas', 'departamentos', 'terrenos']:",
        "        add(urljoin(root, f'/propiedades/{op_path}/{tipo_path}'))",
        "        add(urljoin(root, f'/{op_path}/{tipo_path}'))",
        "```",
        "",
        "Para sitios JS (AJAX selects):",
        "Usar Playwright para enumerar opciones de select y recolectar links por opción.",
        "",
        "## Seguridad",
        "",
        "- no_toca_supabase: true",
        "- no_toca_neon: true",
        "- no_toca_env: true",
        "- no_commit: true",
        "- no_push: true",
    ]
    (out_dir / "recommendations.md").write_text("\n".join(recs), encoding="utf-8")

    # 5. Summary markdown
    summary_md = [
        "# Faceted listing discovery — summary",
        "",
        f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Elapsed: {elapsed}s",
        "",
        "| Dominio | Links antes | Links después | Ganancia | Playwright |",
        "|---|---|---|---|---|",
    ]
    for r in all_results:
        before = r.get("property_links_before", 0)
        after = r.get("property_links_after", 0)
        summary_md.append(
            f"| {r.get('label')} | {before} | {after} | +{after-before} | {r.get('playwright_used', False)} |"
        )
    (out_dir / "faceted_discovery_summary.md").write_text("\n".join(summary_md), encoding="utf-8")

    # Print final
    print(f"\n{'='*68}")
    print("FACETED DISCOVERY RESULTS")
    print(f"{'='*68}")
    total_gain = 0
    for r in all_results:
        before = r.get("property_links_before", 0)
        after = r.get("property_links_after", 0)
        gain = after - before
        total_gain += gain
        print(f"  {r.get('label')}: before={before} after={after} gain=+{gain}")
    print(f"\ntotal_gain=+{total_gain}")
    print(f"elapsed={elapsed}s")
    print(f"out_dir={out_dir}")
    print("=" * 68)


if __name__ == "__main__":
    main()
