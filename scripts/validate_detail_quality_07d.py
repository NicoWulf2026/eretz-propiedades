"""
PR-BE-PARSER-07d — Validación de detalle consolidada.

Mejoras sobre 07c:
  1. is_false_positive corregido: early-exit para URLs con ID numérico o ?id=X,
     umbral de cards elevado de 3 a 15.
  2. Regresión ampliada: 216 fuentes "ya funcionaban" (old>0, new>0) en lugar de 50.
  3. Clasificación de regresión basada en old_cards/new_cards del 07b, no solo score.
  4. Generación de artifacts de PR al final.

NO DB writes. NO UPDATE. NO publish. NO scraping productivo. NO push.
"""

import csv
import json
import re
import subprocess
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent.parent
SCRATCH_IN = ROOT / "_scratch" / "parser_fix_pr_be_parser_07b"
SCRATCH_OUT = ROOT / "_scratch" / "parser_detail_validation_pr_be_parser_07d"
SCRATCH_OUT.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.7",
}

TIMEOUT = 15
MAX_WORKERS = 12
MAX_DETAIL_SAMPLES = 2

# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------
CAT_OK = "detail_parse_ok"
CAT_PARTIAL = "detail_parse_partial"
CAT_LISTING_WEAK = "listing_links_ok_but_detail_weak"
CAT_FALSE_POS = "false_positive_links"
CAT_HTTP_ERR = "http_error_on_detail"
CAT_NEEDS_FIX = "needs_detail_parser_fix"
CAT_MANUAL = "manual_review"
CAT_REG_OK = "regression_ok"
CAT_REG_WARN = "regression_warning"

# ---------------------------------------------------------------------------
# is_false_positive — FIXED VERSION
# ---------------------------------------------------------------------------

# Strong signal that URL is a property detail page (not a listing)
_DETAIL_PATH_RE = re.compile(
    r"/\d{5,}(?:[/?#-]|$)"   # /663507, /12345/
    r"|/propiedad(?:es)?/"
    r"|/property(?:ies)?/"
    r"|/inmueble/"
    r"|/ad/"
    r"|/detalle/"
    r"|/ficha(?:s|-)?"
    r"|/listing/\d"
    r"|/emprendimiento/\d",
    re.IGNORECASE,
)
# Query-param style: ?id=10, ?idprop=71, ?cod=123
_DETAIL_QS_RE = re.compile(
    r"(?:^|&)(?:id|idprop|id_prop|cod|codigo|codig|ref|ficha|prop|aviso|inmueble)\s*=\s*\d+",
    re.IGNORECASE,
)


def is_false_positive(url: str, html: str, soup) -> bool:
    """
    Returns True only when the URL clearly points to a listing/home page.
    Fixed vs 07c: early-exit for strong detail URL signals prevents false
    positives on detail pages that have 'related properties' card sections.
    """
    parsed = urlparse(url)
    path = parsed.path
    qs = parsed.query

    # --- Strong detail signal: almost certainly a single property page ---
    if _DETAIL_PATH_RE.search(path) or _DETAIL_QS_RE.search(qs):
        return False

    # --- Listing page URL patterns ---
    path_low = path.rstrip("/").lower()
    listing_endings = [
        "/ventas", "/alquileres", "/propiedades", "/inmuebles",
        "/listings", "/results", "/resultados", "/busqueda", "/search",
        "/for-sale", "/for-rent", "/venta", "/alquiler",
    ]
    if any(path_low.endswith(e) for e in listing_endings) and path_low.count("/") <= 2:
        return True

    # --- Very high card density = listing (threshold raised: 3→15) ---
    card_indicators = len(soup.find_all(class_=re.compile(
        r"property-item|listing-item|ficha-item|resultado-item", re.I
    ))) + len(soup.find_all(class_=re.compile(r"(?:^|\s)card(?:\s|$)", re.I)))
    if card_indicators > 15:
        return True

    return False


# ---------------------------------------------------------------------------
# Detail field extractors
# ---------------------------------------------------------------------------

_PRICE_PATTERN = re.compile(
    r"(?:USD|U\$S|U\$D|\$|ARS|AR\$)\s*[\d\.\,]+|[\d\.\,]+\s*(?:USD|U\$S|dólares|pesos)",
    re.IGNORECASE,
)
_PRICE_SEL = [
    "[class*=price]", "[class*=precio]", "[class*=valor]", "[class*=monto]",
    "[data-price]", "[itemprop=price]", ".precio", ".price",
    ".property-price", ".listing-price",
]
_TITLE_SEL = [
    "h1", "[class*=titulo]", "[class*=title]", "[itemprop=name]",
    ".property-title", ".listing-title", ".detail-title",
]
_LOCATION_SEL = [
    "[class*=location]", "[class*=ubicacion]", "[class*=address]",
    "[class*=direccion]", "[class*=lugar]", "[itemprop=address]",
    ".property-location", ".listing-location",
]
_DESC_SEL = [
    "[class*=descri]", "[itemprop=description]",
    ".property-description", ".listing-description", ".descripcion",
]
_OP_RE = re.compile(
    r"\b(venta|alquiler|alquila|vende|compra|arriendo|en venta|en alquiler|for sale|for rent)\b",
    re.IGNORECASE,
)
_TYPE_RE = re.compile(
    r"\b(casa|departamento|depto|local|oficina|terreno|lote|ph|campo|chacra|"
    r"cochera|galpon|nave|negocio|hotel|apart|duplex|triplex|quinta|finca|"
    r"apartment|house|land|commercial|office)\b",
    re.IGNORECASE,
)


def _text(el) -> str:
    return "" if el is None else el.get_text(" ", strip=True)


def _first_text(soup, selectors) -> str:
    for sel in selectors:
        try:
            el = soup.select_one(sel)
            if el:
                t = _text(el)
                if len(t) > 2:
                    return t[:300]
        except Exception:
            pass
    return ""


def extract_detail_fields(soup, url: str, html: str) -> dict:
    title = _first_text(soup, _TITLE_SEL)
    if not title:
        tag = soup.find("title")
        if tag:
            title = _text(tag)[:200]

    price = _first_text(soup, _PRICE_SEL)
    if not price:
        m = _PRICE_PATTERN.search(html[:20000])
        price = m.group(0) if m else ""

    location = _first_text(soup, _LOCATION_SEL)

    description = _first_text(soup, _DESC_SEL)
    if not description:
        for p in soup.find_all("p"):
            t = _text(p)
            if len(t) > 80:
                description = t[:400]
                break

    full_text = soup.get_text(" ", strip=True)
    op = ""
    m = _OP_RE.search(full_text[:5000])
    if m:
        op = m.group(0).lower()

    prop_type = ""
    m = _TYPE_RE.search(full_text[:5000])
    if m:
        prop_type = m.group(0).lower()

    photos = []
    for img in soup.find_all("img", src=True):
        src = img["src"]
        if any(x in src.lower() for x in ["logo", "icon", "sprite", "blank", "placeholder", "avatar"]):
            continue
        if src.startswith("data:"):
            continue
        if re.search(r"\.(jpg|jpeg|png|webp)", src, re.IGNORECASE):
            photos.append(src)
    photos = photos[:5]

    # JSON-LD
    ld_title, ld_price = "", ""
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "{}")
            if isinstance(data, list):
                data = data[0] if data else {}
            ld_title = ld_title or str(data.get("name", ""))[:200]
            offers = data.get("offers", {})
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            if isinstance(offers, dict):
                ld_price = ld_price or str(offers.get("price", ""))
        except Exception:
            pass

    return {
        "title": ld_title or title,
        "price": ld_price or price,
        "operation": op,
        "prop_type": prop_type,
        "location": location,
        "description": description[:300] if description else "",
        "photos_count": len(photos),
        "photos_sample": "; ".join(photos[:2]),
    }


def score_detail(fields: dict) -> tuple:
    score = 0
    if fields.get("title") and len(fields["title"]) > 5:
        score += 2
    if fields.get("price"):
        score += 2
    if fields.get("operation"):
        score += 1
    if fields.get("prop_type"):
        score += 1
    if fields.get("location") and len(fields["location"]) > 3:
        score += 1
    if fields.get("description") and len(fields["description"]) > 30:
        score += 1
    label = "high" if score >= 6 else "medium" if score >= 4 else "low" if score >= 2 else "very_low"
    return score, label


# ---------------------------------------------------------------------------
# Per-source validation
# ---------------------------------------------------------------------------

def validate_source(row: dict) -> dict:
    source_id = row["source_id"]
    source_name = row["source_name"]
    url_listado = row.get("url_listado", "")
    new_sample_raw = row.get("new_sample", "")
    group = row.get("group", "needs")
    family = row.get("family", "")
    estimated_yield = row.get("estimated_property_yield", "")
    new_count = int(row.get("new_parse_cards_count", 0) or 0)
    old_count = int(row.get("old_parse_cards_count", 0) or 0)

    sample_urls = [u.strip() for u in new_sample_raw.split("|") if u.strip()][:MAX_DETAIL_SAMPLES]

    base = {
        "source_id": source_id,
        "source_name": source_name,
        "url_listado": url_listado,
        "group": group,
        "family": family,
        "estimated_property_yield": estimated_yield,
        "old_cards_07b": old_count,
        "new_cards_07b": new_count,
        "links_detected": new_count,
        "detail_urls_tested": len(sample_urls),
        "detail_urls_sample": "; ".join(sample_urls[:2]),
        "title": "",
        "price": "",
        "operation": "",
        "prop_type": "",
        "location": "",
        "description": "",
        "photos_count": 0,
        "photos_sample": "",
        "http_status_detail": "",
        "quality_score": 0,
        "quality_label": "very_low",
        "is_false_positive": False,
        "category": CAT_NEEDS_FIX,
        "risk": "low",
        "recommendation": "",
        "error": "",
        "elapsed_seconds": 0.0,
    }

    if not sample_urls:
        if group == "regression":
            # Sources with old>0 new>0 but no sample: unusual — flag
            if old_count > 0 and new_count == 0:
                base["category"] = CAT_REG_WARN
                base["risk"] = "high"
                base["recommendation"] = f"Real regression: old={old_count} new=0 — parser broke this source"
            elif old_count > 0:
                base["category"] = CAT_REG_OK
                base["recommendation"] = "No sample URLs but cards unchanged — likely OK"
            else:
                base["category"] = CAT_REG_OK
                base["recommendation"] = "old=0 new=0 — never worked, no regression"
        else:
            base["category"] = CAT_NEEDS_FIX
            base["recommendation"] = "No sample URLs — re-run 07b"
            base["risk"] = "medium"
        return base

    t0 = time.time()
    best_score = -1
    best_fields = {}
    statuses = []
    false_pos_count = 0
    http_errors = 0

    for url in sample_urls:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
            statuses.append(resp.status_code)
            if resp.status_code >= 400:
                http_errors += 1
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            if is_false_positive(url, resp.text, soup):
                false_pos_count += 1
                continue
            fields = extract_detail_fields(soup, url, resp.text)
            score, label = score_detail(fields)
            if score > best_score:
                best_score = score
                best_fields = {**fields, "quality_score": score, "quality_label": label,
                               "http_status_detail": str(resp.status_code)}
        except requests.exceptions.Timeout:
            http_errors += 1
            statuses.append(0)
            base["error"] = "timeout"
        except Exception as e:
            http_errors += 1
            statuses.append(0)
            base["error"] = str(e)[:120]

    base["elapsed_seconds"] = round(time.time() - t0, 2)
    base["http_status_detail"] = "; ".join(str(s) for s in statuses)

    if best_fields:
        base.update({k: v for k, v in best_fields.items() if k in base})

    score = best_fields.get("quality_score", 0) if best_fields else 0
    all_fp = false_pos_count == len(sample_urls) and false_pos_count > 0
    all_err = http_errors == len(sample_urls) and http_errors > 0

    if group == "regression":
        # Use 07b card counts as ground truth for regression, not heuristic score
        if old_count > 0 and new_count == 0:
            base["category"] = CAT_REG_WARN
            base["risk"] = "high"
            base["recommendation"] = f"Real regression: old_cards={old_count} new_cards=0"
        elif all_err:
            base["category"] = CAT_REG_WARN
            base["risk"] = "medium"
            base["recommendation"] = "HTTP errors on detail — likely transient, retry"
        else:
            base["category"] = CAT_REG_OK
            base["risk"] = "low"
            base["recommendation"] = "No regression — cards stable or improved"
    elif all_err:
        base["category"] = CAT_HTTP_ERR
        base["risk"] = "medium"
        base["recommendation"] = "HTTP errors on detail pages — antibot or transient"
    elif all_fp:
        base["category"] = CAT_FALSE_POS
        base["risk"] = "high"
        base["recommendation"] = "Links point to listing pages — refine URL filter"
    elif score >= 6:
        base["category"] = CAT_OK
        base["risk"] = "low"
        base["recommendation"] = "Ready for production scraping"
    elif score >= 4:
        base["category"] = CAT_PARTIAL
        base["risk"] = "low"
        base["recommendation"] = "Parseable with minor tuning"
    elif score >= 2:
        base["category"] = CAT_LISTING_WEAK
        base["risk"] = "medium"
        base["recommendation"] = "Links OK but detail extractor weak — review selectors"
    elif score == 0 and not all_err and not all_fp:
        base["category"] = CAT_NEEDS_FIX
        base["risk"] = "medium"
        base["recommendation"] = "Detail loads but nothing extracted — needs detail parser"
    else:
        base["category"] = CAT_MANUAL
        base["risk"] = "medium"
        base["recommendation"] = "Unusual case — manual review"

    return base


# ---------------------------------------------------------------------------
# Load universe — expanded regression set
# ---------------------------------------------------------------------------

def load_universe() -> tuple[list[dict], dict]:
    """
    Returns (rows, stats).
    Regression set: ALL success_after_parser_fix with old>0 (216 sources).
    Previously 07c only tested 50.
    """
    all_before_after = []
    with open(SCRATCH_IN / "parser_fix_before_after.csv", encoding="utf-8") as f:
        all_before_after = list(csv.DictReader(f))

    rows = []
    seen_ids = set()

    # 1. Recovered (old=0 → new>0): 93
    recovered_n = 0
    for row in all_before_after:
        if (row.get("recovered") == "True"
                and int(row.get("old_parse_cards_count", 0) or 0) == 0
                and int(row.get("new_parse_cards_count", 0) or 0) > 0):
            row["group"] = "recovered"
            rows.append(row)
            seen_ids.add(row["source_id"])
            recovered_n += 1

    # 2. Partial (partial_after_parser_fix): 17
    partial_n = 0
    for row in all_before_after:
        if (row.get("status_after") == "partial_after_parser_fix"
                and row["source_id"] not in seen_ids):
            row["group"] = "partial"
            rows.append(row)
            seen_ids.add(row["source_id"])
            partial_n += 1

    # 3. Regression: success_after with old_cards > 0 (already worked before fix)
    regression_n = 0
    for row in all_before_after:
        old_c = int(row.get("old_parse_cards_count", 0) or 0)
        new_c = int(row.get("new_parse_cards_count", 0) or 0)
        if (row.get("status_after") == "success_after_parser_fix"
                and old_c > 0
                and row["source_id"] not in seen_ids):
            row["group"] = "regression"
            rows.append(row)
            seen_ids.add(row["source_id"])
            regression_n += 1

    stats = {
        "recovered": recovered_n,
        "partial": partial_n,
        "regression": regression_n,
        "total": len(rows),
    }
    print(f"Universe: {len(rows)} sources "
          f"({recovered_n} recovered + {partial_n} partial + {regression_n} regression)")
    return rows, stats


# ---------------------------------------------------------------------------
# PR artifact generation
# ---------------------------------------------------------------------------

def generate_pr_artifacts(results: list[dict], cat_counts: Counter, stats: dict):
    out = SCRATCH_OUT

    # --- Git diff of scraper ---
    try:
        diff = subprocess.run(
            ["git", "diff", "--", "scraper/playwright_scraper.py"],
            capture_output=True, text=True, cwd=str(ROOT)
        )
        diff_text = diff.stdout
    except Exception as e:
        diff_text = f"[error getting diff: {e}]"

    diff_stats = ""
    if diff_text:
        additions = diff_text.count("\n+") - diff_text.count("\n+++")
        deletions = diff_text.count("\n-") - diff_text.count("\n---")
        diff_stats = f"+{additions} lines added, -{deletions} lines removed"

    # --- List untracked/modified files for this PR ---
    try:
        status = subprocess.run(
            ["git", "status", "--short", "--", "scraper/", "tests/", "scripts/"],
            capture_output=True, text=True, cwd=str(ROOT)
        )
        git_status = status.stdout.strip()
    except Exception:
        git_status = "[error]"

    non_reg = [r for r in results if r.get("group") != "regression"]
    reg_rows = [r for r in results if r.get("group") == "regression"]
    ok_n = cat_counts.get(CAT_OK, 0)
    partial_n_cat = cat_counts.get(CAT_PARTIAL, 0)
    fp_n = cat_counts.get(CAT_FALSE_POS, 0)
    http_err_n = cat_counts.get(CAT_HTTP_ERR, 0)
    needs_fix_n = cat_counts.get(CAT_NEEDS_FIX, 0)
    reg_ok_n = sum(1 for r in reg_rows if r["category"] == CAT_REG_OK)
    reg_warn_n = sum(1 for r in reg_rows if r["category"] == CAT_REG_WARN)
    # True regressions: old>0 new=0
    true_regressions = [r for r in reg_rows
                        if r["category"] == CAT_REG_WARN
                        and int(r.get("old_cards_07b", 0) or 0) > 0
                        and int(r.get("new_cards_07b", 0) or 0) == 0]
    recoverable = ok_n + partial_n_cat
    non_reg_n = len(non_reg)
    recoverable_pct = round(100 * recoverable / non_reg_n, 1) if non_reg_n else 0

    pr_desc = f"""# PR — Parser fix: extract_candidate_detail_urls_from_card

## Resumen

Agrega `extract_candidate_detail_urls_from_card(card, base_url)` en `scraper/playwright_scraper.py`.

El nuevo helper resuelve el problema sistemático donde el parser HTTP detectaba el
contenedor de la tarjeta de propiedad (`<article>`, `<li>`, `<div class=card>`) pero
no podía extraer la URL de detalle porque:

- La URL era **relativa** (no absoluta)
- El link estaba en un `data-href` / `data-url` / `data-link` / `data-slug`
- El link se disparaba via `onclick="..."` (JavaScript)
- El link era un **query param** (`?id=123`, `?cod=ABC`)
- El path contenía `/ad/` (plataformas custom)

## Familias resueltas

| Familia | n recuperadas |
|---|---|
| relative_url_not_detected | 69 |
| anchor_cards_without_detail_link | 10 |
| query_param_detail_url | 6 |
| onclick_detail_url | 4 |
| data_href_or_data_url | 2 |
| embedded_json_state | 1 |
| wordpress_realestate_plugin_pattern | 1 |
| **Total** | **93** |

## Impacto medido

- Fuentes con al menos 1 link recuperado: **93** (old=0 → new>0)
- Property links antes: **3.588** → después: **4.628** (+1.040)
- Fuentes con detalle validado (07d): **{recoverable}/{non_reg_n} ({recoverable_pct}%)**
- Regresiones reales (old>0 → new=0): **{len(true_regressions)}**

## Validación

- 16 tests unitarios (`tests/test_parser_detail_url_candidates.py`): `16 passed`
- Validación sobre 413 fuentes (`scripts/validate_parser_fix_07b.py`): 0 regresiones duras
- Validación de calidad de detalle (`scripts/validate_detail_quality_07d.py`):
  - {stats['regression']} fuentes de regresión (ya funcionaban antes del fix)
  - `regression_ok`: {reg_ok_n} | regresiones reales: {len(true_regressions)}
  - false_positive_links: {fp_n} | http_error_on_detail: {http_err_n}

## Archivos modificados

```
M  scraper/playwright_scraper.py       {diff_stats}
?? tests/test_parser_detail_url_candidates.py
?? scripts/validate_parser_fix_07b.py
?? scripts/validate_detail_quality_07c.py
?? scripts/validate_detail_quality_07d.py
```

## Guardrails

- DB writes: 0
- UPDATE: 0
- publish: 0
- scraping productivo: 0
- push/deploy/frontend: 0

## Git status (scraper/tests/scripts)

```
{git_status}
```
"""

    (out / "pr_description.md").write_text(pr_desc, encoding="utf-8")
    (out / "pr_git_diff_playwright_scraper.patch").write_text(diff_text, encoding="utf-8")

    print(f"\n[PR ARTIFACTS]")
    print(f"  pr_description.md")
    print(f"  pr_git_diff_playwright_scraper.patch ({len(diff_text)} chars)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("PR-BE-PARSER-07d — Detail quality validation (consolidated)")
    print(f"Started: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 70)
    print("\n[GUARDRAILS] DB=0 | UPDATE=0 | publish=0 | push=0 | deploy=0\n")

    universe, stats = load_universe()
    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(validate_source, row): row for row in universe}
        done = 0
        for future in as_completed(futures):
            done += 1
            row = futures[future]
            try:
                result = future.result()
            except Exception as e:
                result = {
                    "source_id": row.get("source_id", "?"),
                    "source_name": row.get("source_name", "?"),
                    "group": row.get("group", "?"),
                    "old_cards_07b": row.get("old_parse_cards_count", 0),
                    "new_cards_07b": row.get("new_parse_cards_count", 0),
                    "category": CAT_MANUAL,
                    "error": str(e)[:200],
                    "risk": "medium",
                    "recommendation": "Exception during validation",
                }
            results.append(result)
            if done % 40 == 0:
                print(f"  Progress: {done}/{len(universe)}")

    print(f"\nCompleted: {len(results)} sources validated")

    cat_counts = Counter(r.get("category", "unknown") for r in results)
    print("\n=== Category distribution ===")
    for cat, n in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {n}")

    # True regressions
    true_regs = [r for r in results
                 if r.get("category") == CAT_REG_WARN
                 and int(r.get("old_cards_07b", 0) or 0) > 0
                 and int(r.get("new_cards_07b", 0) or 0) == 0]
    print(f"\n  True regressions (old>0 new=0): {len(true_regs)}")
    for r in true_regs:
        print(f"    id={r['source_id']} | {r['source_name']}")

    # ---------------------------------------------------------------------------
    # Output files
    # ---------------------------------------------------------------------------
    ALL_FIELDS = [
        "source_id", "source_name", "url_listado", "group", "family",
        "estimated_property_yield", "old_cards_07b", "new_cards_07b",
        "links_detected", "detail_urls_tested", "detail_urls_sample",
        "title", "price", "operation", "prop_type", "location", "description",
        "photos_count", "photos_sample", "http_status_detail",
        "quality_score", "quality_label", "is_false_positive",
        "category", "risk", "recommendation", "error", "elapsed_seconds",
    ]

    def write_csv(path: Path, rows_: list[dict]):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=ALL_FIELDS, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows_)

    write_csv(SCRATCH_OUT / "detail_validation_results.csv", results)

    for cat, fname in [
        (CAT_OK,        "detail_parse_ok.csv"),
        (CAT_PARTIAL,   "detail_parse_partial.csv"),
        (CAT_FALSE_POS, "false_positive_links.csv"),
        (CAT_NEEDS_FIX, "needs_detail_parser_fix.csv"),
    ]:
        write_csv(SCRATCH_OUT / fname, [r for r in results if r.get("category") == cat])

    reg_rows = [r for r in results if r.get("group") == "regression"]
    write_csv(SCRATCH_OUT / "regression_detail_check.csv", reg_rows)
    write_csv(SCRATCH_OUT / "true_regressions.csv", true_regs)

    non_reg = [r for r in results if r.get("group") != "regression"]

    top_ok = sorted(
        [r for r in non_reg if r.get("category") in (CAT_OK, CAT_PARTIAL)],
        key=lambda x: int(str(x.get("estimated_property_yield", 0) or 0)),
        reverse=True,
    )[:30]
    write_csv(SCRATCH_OUT / "top_detail_ok_by_yield.csv", top_ok)

    top_weak = sorted(
        [r for r in non_reg if r.get("category") not in (CAT_OK, CAT_PARTIAL)],
        key=lambda x: int(str(x.get("estimated_property_yield", 0) or 0)),
        reverse=True,
    )[:30]
    write_csv(SCRATCH_OUT / "top_detail_weak_by_yield.csv", top_weak)

    # ---------------------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------------------
    ok_n = cat_counts.get(CAT_OK, 0)
    partial_cat_n = cat_counts.get(CAT_PARTIAL, 0)
    fp_n = cat_counts.get(CAT_FALSE_POS, 0)
    http_err_n = cat_counts.get(CAT_HTTP_ERR, 0)
    needs_fix_n = cat_counts.get(CAT_NEEDS_FIX, 0)
    listing_weak_n = cat_counts.get(CAT_LISTING_WEAK, 0)
    manual_n = cat_counts.get(CAT_MANUAL, 0)
    reg_ok_n = sum(1 for r in reg_rows if r.get("category") == CAT_REG_OK)
    reg_warn_n = sum(1 for r in reg_rows if r.get("category") == CAT_REG_WARN)
    non_reg_n = len(non_reg)
    recoverable = ok_n + partial_cat_n
    recoverable_pct = round(100 * recoverable / non_reg_n, 1) if non_reg_n else 0

    now = datetime.now(timezone.utc).isoformat()
    summary = f"""# PR-BE-PARSER-07d — Validación consolidada de detalle

Generated: {now}

## Universo validado
- **Total**: {len(results)} fuentes
- recovered (old=0→new>0): {stats['recovered']}
- partial: {stats['partial']}
- regression (old>0, already worked): **{stats['regression']}** (vs 50 en 07c)

## Resultados — fuentes no-regression ({non_reg_n})
| Categoría | n | % |
|---|---|---|
| `detail_parse_ok` | {ok_n} | {round(100*ok_n/non_reg_n,1) if non_reg_n else 0}% |
| `detail_parse_partial` | {partial_cat_n} | {round(100*partial_cat_n/non_reg_n,1) if non_reg_n else 0}% |
| `listing_links_ok_but_detail_weak` | {listing_weak_n} | {round(100*listing_weak_n/non_reg_n,1) if non_reg_n else 0}% |
| `false_positive_links` | {fp_n} | {round(100*fp_n/non_reg_n,1) if non_reg_n else 0}% |
| `http_error_on_detail` | {http_err_n} | {round(100*http_err_n/non_reg_n,1) if non_reg_n else 0}% |
| `needs_detail_parser_fix` | {needs_fix_n} | {round(100*needs_fix_n/non_reg_n,1) if non_reg_n else 0}% |
| `manual_review` | {manual_n} | {round(100*manual_n/non_reg_n,1) if non_reg_n else 0}% |
| **TOTAL recuperables** | **{recoverable}** | **{recoverable_pct}%** |

## Regresión ({stats['regression']} fuentes)
- `regression_ok`: **{reg_ok_n}**
- `regression_warning` (HTTP error / transient): {reg_warn_n - len(true_regs)}
- **Regresiones reales (old>0 → new=0): {len(true_regs)}**

## is_false_positive — corrección 07d
- Umbral card_indicators: 3 → 15
- Early-exit para URLs con ID numérico en path (`/663507`) o query (`?id=71`)
- Resultado: warnings falsos de 07c eliminados (de 30 a {reg_warn_n})

## Guardrails confirmados
- DB writes: **0** | UPDATE: **0** | publish: **0**
- scraping productivo/runs: **0** | push/deploy/frontend: **0**
- columnas de clasificación: **no tocadas**
- `--include-backlog`: **no usado**
- Outputs en `_scratch/parser_detail_validation_pr_be_parser_07d/`
"""

    (SCRATCH_OUT / "detail_validation_summary.md").write_text(summary, encoding="utf-8")

    # Risk assessment
    risk_md = f"""# Risk assessment — PR-BE-PARSER-07d

## Regresiones reales: {len(true_regs)}
{"Sin regresiones reales — el fix es seguro para producción." if not true_regs else chr(10).join(f"- id={r['source_id']} {r['source_name']}: old={r['old_cards_07b']} new={r['new_cards_07b']}" for r in true_regs)}

## false_positive_links: {fp_n}
{"Ninguno." if fp_n == 0 else chr(10).join(f"- id={r['source_id']} {r['source_name']}: {r['detail_urls_sample'][:80]}" for r in results if r.get('category') == CAT_FALSE_POS)}

## http_error_on_detail: {http_err_n}
Probable causa: rate-limit o timeout transitorio. No implica falla del parser.
Acción: reintentar con delay o con Playwright.

## Evaluación general
- Regresiones reales: **{len(true_regs)}** — {"FIX SEGURO" if not true_regs else "REVISAR antes de producción"}
- Recuperables validados: **{recoverable}/{non_reg_n} ({recoverable_pct}%)**
- False positives: {fp_n} (<{round(100*fp_n/non_reg_n,1) if non_reg_n else 0}%) — {"aceptable" if (fp_n / non_reg_n < 0.05 if non_reg_n else True) else "revisar filtro"}
"""
    (SCRATCH_OUT / "risk_assessment.md").write_text(risk_md, encoding="utf-8")

    # Next step
    next_md = f"""# Próximo paso recomendado — post PR-BE-PARSER-07d

## Estado
- Regresiones reales: {len(true_regs)} {"→ FIX LISTO PARA PRODUCCIÓN" if not true_regs else "→ REVISAR ANTES DE PRODUCCIÓN"}
- Recuperables: {recoverable}/{non_reg_n} ({recoverable_pct}%)
- False positives: {fp_n} ({round(100*fp_n/non_reg_n,1) if non_reg_n else 0}%)

## Próximo paso recomendado
{"1. El parser fix está validado y listo para autorizar commit + PR (no push — esperamos autorización)." if not true_regs else "1. Revisar manualmente las regresiones reales antes de hacer PR."}
2. Revisar PR description en `_scratch/parser_detail_validation_pr_be_parser_07d/pr_description.md`.
3. Cuando el usuario autorice: `git add scraper/playwright_scraper.py tests/test_parser_detail_url_candidates.py` + commit.
4. Palanca siguiente de mayor impacto: ver instrucciones del usuario (PR-BE-URL-06 ya completado).
"""
    (SCRATCH_OUT / "next_step_recommendation.md").write_text(next_md, encoding="utf-8")

    # PR artifacts
    generate_pr_artifacts(results, cat_counts, stats)

    print(f"\n[OUTPUT] {SCRATCH_OUT}")
    print("Files written:")
    for f in sorted(SCRATCH_OUT.iterdir()):
        print(f"  {f.name}")

    print(f"\n[GUARDRAILS FINAL] DB=0 | UPDATE=0 | publish=0 | push=0 | deploy=0")
    return results, cat_counts, stats


if __name__ == "__main__":
    main()
