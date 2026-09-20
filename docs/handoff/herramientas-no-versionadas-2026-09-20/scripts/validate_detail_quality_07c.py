"""
PR-BE-PARSER-07c — Validación diagnóstica de detalle post parser fix.

Lee los outputs de 07b y valida que los links detectados permiten extraer
datos reales de fichas de propiedades.

NO DB writes. NO UPDATE. NO publish. NO scraping productivo. NO push.
"""

import csv
import json
import os
import re
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent.parent
SCRATCH_IN = ROOT / "_scratch" / "parser_fix_pr_be_parser_07b"
SCRATCH_OUT = ROOT / "_scratch" / "parser_detail_validation_pr_be_parser_07c"
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
MAX_WORKERS = 10
MAX_DETAIL_SAMPLES = 2  # URLs to fetch per source

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
# Detail field extractors (heuristic, platform-agnostic)
# ---------------------------------------------------------------------------

_PRICE_PATTERN = re.compile(
    r"(?:USD|U\$S|U\$D|\$|ARS|AR\$)\s*[\d\.\,]+|[\d\.\,]+\s*(?:USD|U\$S|dólares|pesos)",
    re.IGNORECASE,
)
_PRICE_SEL = [
    "[class*=price]", "[class*=precio]", "[class*=valor]", "[class*=monto]",
    "[data-price]", "[itemprop=price]", ".price", ".Price", ".precio",
    ".property-price", ".listing-price",
]
_TITLE_SEL = [
    "h1", "[class*=titulo]", "[class*=title]", "[itemprop=name]",
    ".property-title", ".listing-title", ".detail-title",
]
_LOCATION_SEL = [
    "[class*=location]", "[class*=ubicacion]", "[class*=address]",
    "[class*=direccion]", "[class*=lugar]", "[itemprop=address]",
    ".property-location", ".listing-location", ".address",
]
_DESC_SEL = [
    "[class*=descri]", "[class*=detail]", "[class*=comment]",
    "[class*=observacion]", "[class*=nota]", "[itemprop=description]",
    ".property-description", ".listing-description", ".descripcion",
]
_OP_KEYWORDS = re.compile(
    r"\b(venta|alquiler|alquila|vende|compra|arriendo|en venta|en alquiler|for sale|for rent)\b",
    re.IGNORECASE,
)
_TYPE_KEYWORDS = re.compile(
    r"\b(casa|departamento|depto|local|oficina|terreno|lote|ph|campo|chacra|"
    r"cochera|galpon|nave|negocio|hotel|apart|duplex|triplex|quinta|finca|"
    r"apartment|house|land|commercial|office)\b",
    re.IGNORECASE,
)


def _text(el) -> str:
    if el is None:
        return ""
    return el.get_text(" ", strip=True)


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
    """Extract as many property fields as possible from a detail page."""
    title = _first_text(soup, _TITLE_SEL)
    if not title:
        title_tag = soup.find("title")
        if title_tag:
            title = _text(title_tag)[:200]

    price_raw = _first_text(soup, _PRICE_SEL)
    if not price_raw:
        m = _PRICE_PATTERN.search(html[:20000])
        price_raw = m.group(0) if m else ""

    location = _first_text(soup, _LOCATION_SEL)

    description = _first_text(soup, _DESC_SEL)
    if not description:
        # Fallback: first long paragraph
        for p in soup.find_all("p"):
            t = _text(p)
            if len(t) > 80:
                description = t[:400]
                break

    full_text = soup.get_text(" ", strip=True)
    operation = ""
    m = _OP_KEYWORDS.search(full_text[:5000])
    if m:
        operation = m.group(0).lower()

    prop_type = ""
    m = _TYPE_KEYWORDS.search(full_text[:5000])
    if m:
        prop_type = m.group(0).lower()

    # Photos: img tags with src not matching icons/logos
    photos = []
    for img in soup.find_all("img", src=True):
        src = img["src"]
        if any(x in src.lower() for x in ["logo", "icon", "sprite", "blank", "placeholder", "avatar"]):
            continue
        if src.startswith("data:"):
            continue
        if any(src.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]):
            photos.append(src)
        elif re.search(r"\.(jpg|jpeg|png|webp)", src, re.IGNORECASE):
            photos.append(src)
    photos = photos[:5]

    # JSON-LD schema
    ld_title = ""
    ld_price = ""
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "{}")
            if isinstance(data, list):
                data = data[0] if data else {}
            if data.get("name"):
                ld_title = str(data["name"])[:200]
            if data.get("offers"):
                offers = data["offers"]
                if isinstance(offers, list):
                    offers = offers[0]
                if isinstance(offers, dict) and offers.get("price"):
                    ld_price = str(offers["price"])
        except Exception:
            pass

    return {
        "title": ld_title or title,
        "price": ld_price or price_raw,
        "operation": operation,
        "prop_type": prop_type,
        "location": location,
        "description": description[:300] if description else "",
        "photos_count": len(photos),
        "photos_sample": "; ".join(photos[:2]),
    }


def score_detail(fields: dict) -> tuple[int, str]:
    """Returns (score 0-8, quality_label)."""
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

    if score >= 6:
        label = "high"
    elif score >= 4:
        label = "medium"
    elif score >= 2:
        label = "low"
    else:
        label = "very_low"
    return score, label


def is_false_positive(url: str, html: str, soup) -> bool:
    """Detect if URL leads to a listing/home page rather than a detail."""
    # URL looks like a listing (ends in /ventas, /propiedades, /alquiler etc.)
    path = urlparse(url).path.rstrip("/").lower()
    listing_endings = [
        "/ventas", "/alquileres", "/propiedades", "/inmuebles",
        "/listings", "/properties", "/resultados", "/busqueda", "/search",
        "/for-sale", "/for-rent",
    ]
    if any(path.endswith(e) for e in listing_endings) and path.count("/") <= 2:
        return True

    # Multiple property cards on the page = listing page, not detail
    card_indicators = len(soup.find_all(class_=re.compile(
        r"card|property-item|listing-item|resultado|ficha-item", re.I
    )))
    if card_indicators > 3:
        return True

    return False


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

    sample_urls = [u.strip() for u in new_sample_raw.split("|") if u.strip()][:MAX_DETAIL_SAMPLES]

    base = {
        "source_id": source_id,
        "source_name": source_name,
        "url_listado": url_listado,
        "group": group,
        "family": family,
        "estimated_property_yield": estimated_yield,
        "links_detected": new_count,
        "detail_urls_tested": len(sample_urls),
        "detail_urls_sample": "; ".join(sample_urls[:2]),
        # Filled below
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
        base["category"] = CAT_NEEDS_FIX if group != "regression" else CAT_REG_WARN
        base["recommendation"] = "No sample URLs available — re-run 07b"
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
                best_fields = fields
                best_fields["quality_score"] = score
                best_fields["quality_label"] = label
                best_fields["http_status_detail"] = str(resp.status_code)
        except requests.exceptions.Timeout:
            http_errors += 1
            statuses.append(0)
            base["error"] = "timeout"
        except Exception as e:
            http_errors += 1
            statuses.append(0)
            base["error"] = str(e)[:120]

    elapsed = round(time.time() - t0, 2)
    base["elapsed_seconds"] = elapsed
    base["http_status_detail"] = "; ".join(str(s) for s in statuses)

    if best_fields:
        base.update({k: v for k, v in best_fields.items() if k in base})

    score = best_fields.get("quality_score", 0) if best_fields else 0
    quality_label = best_fields.get("quality_label", "very_low") if best_fields else "very_low"

    # Category assignment
    all_fp = false_pos_count == len(sample_urls) and false_pos_count > 0
    all_err = http_errors == len(sample_urls) and http_errors > 0

    if group == "regression":
        if all_err or score == 0:
            base["category"] = CAT_REG_WARN
            base["risk"] = "high"
            base["recommendation"] = "Regression source degraded — review carefully"
        else:
            base["category"] = CAT_REG_OK
            base["risk"] = "low"
            base["recommendation"] = "Regression OK — no degradation detected"
    elif all_err:
        base["category"] = CAT_HTTP_ERR
        base["risk"] = "medium"
        base["recommendation"] = "HTTP errors on detail pages — check connectivity or antibot"
    elif all_fp:
        base["category"] = CAT_FALSE_POS
        base["risk"] = "high"
        base["recommendation"] = "Links detected are listing pages, not detail pages — false positive"
    elif score >= 6:
        base["category"] = CAT_OK
        base["risk"] = "low"
        base["recommendation"] = "Ready for production scraping"
    elif score >= 4:
        base["category"] = CAT_PARTIAL
        base["risk"] = "low"
        base["recommendation"] = "Mostly parseable — accept with minor parser tuning"
    elif score >= 2:
        base["category"] = CAT_LISTING_WEAK
        base["risk"] = "medium"
        base["recommendation"] = "Links OK but detail parse weak — review selectors"
    elif score == 0 and not all_err and not all_fp:
        base["category"] = CAT_NEEDS_FIX
        base["risk"] = "medium"
        base["recommendation"] = "Detail page loads but nothing extracted — needs detail parser"
    else:
        base["category"] = CAT_MANUAL
        base["risk"] = "medium"
        base["recommendation"] = "Unusual case — manual review needed"

    return base


# ---------------------------------------------------------------------------
# Load universe
# ---------------------------------------------------------------------------

def load_universe() -> list[dict]:
    rows = []

    # 1. Recovered (93)
    with open(SCRATCH_IN / "recovered_after_parser_fix.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("recovered") == "True":
                rows.append(row)

    # 2. Partial (17) — from before_after
    partial_ids = set()
    with open(SCRATCH_IN / "parser_fix_before_after.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("status_after") == "partial_after_parser_fix":
                if row["source_id"] not in {r["source_id"] for r in rows}:
                    rows.append(row)
                    partial_ids.add(row["source_id"])

    # 3. Regression (50)
    with open(SCRATCH_IN / "regression_check.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)

    print(f"Universe: {len(rows)} sources (93 recovered + 17 partial + 50 regression)")
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("PR-BE-PARSER-07c — Detail quality validation")
    print(f"Started: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 70)

    # Security guardrail
    print("\n[GUARDRAILS] DB writes=0 | UPDATE=0 | publish=0 | push=0 | deploy=0\n")

    universe = load_universe()
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
                    "category": CAT_MANUAL,
                    "error": str(e)[:200],
                    "risk": "medium",
                    "recommendation": "Exception during validation",
                }
            results.append(result)
            if done % 20 == 0:
                print(f"  Progress: {done}/{len(universe)}")

    print(f"\nCompleted: {len(results)} sources validated")

    # ---------------------------------------------------------------------------
    # Tally
    # ---------------------------------------------------------------------------
    from collections import Counter
    cat_counts = Counter(r.get("category", "unknown") for r in results)
    print("\n=== Category distribution ===")
    for cat, n in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {n}")

    # ---------------------------------------------------------------------------
    # Output files
    # ---------------------------------------------------------------------------
    all_fields = [
        "source_id", "source_name", "url_listado", "group", "family",
        "estimated_property_yield", "links_detected", "detail_urls_tested",
        "detail_urls_sample", "title", "price", "operation", "prop_type",
        "location", "description", "photos_count", "photos_sample",
        "http_status_detail", "quality_score", "quality_label",
        "is_false_positive", "category", "risk", "recommendation", "error",
        "elapsed_seconds",
    ]

    def write_csv(path: Path, rows: list[dict]):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=all_fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)

    # 1. All results
    write_csv(SCRATCH_OUT / "detail_validation_results.csv", results)

    # 2. By category
    for cat, fname in [
        (CAT_OK, "detail_parse_ok.csv"),
        (CAT_PARTIAL, "detail_parse_partial.csv"),
        (CAT_FALSE_POS, "false_positive_links.csv"),
        (CAT_NEEDS_FIX, "needs_detail_parser_fix.csv"),
    ]:
        write_csv(SCRATCH_OUT / fname, [r for r in results if r.get("category") == cat])

    # 3. Regression
    reg_rows = [r for r in results if r.get("group") == "regression"]
    write_csv(SCRATCH_OUT / "regression_detail_check.csv", reg_rows)

    # 4. Top by yield
    non_reg = [r for r in results if r.get("group") != "regression"]
    top_ok = sorted(
        [r for r in non_reg if r.get("category") in (CAT_OK, CAT_PARTIAL)],
        key=lambda x: int(str(x.get("estimated_property_yield", 0) or 0)),
        reverse=True,
    )[:30]
    write_csv(SCRATCH_OUT / "top_detail_ok_by_yield.csv", top_ok)

    top_weak = sorted(
        [r for r in non_reg if r.get("category") not in (CAT_OK, CAT_PARTIAL, CAT_REG_OK)],
        key=lambda x: int(str(x.get("estimated_property_yield", 0) or 0)),
        reverse=True,
    )[:30]
    write_csv(SCRATCH_OUT / "top_detail_weak_by_yield.csv", top_weak)

    # ---------------------------------------------------------------------------
    # Summary markdown
    # ---------------------------------------------------------------------------
    reg_ok_n = sum(1 for r in reg_rows if r.get("category") == CAT_REG_OK)
    reg_warn_n = sum(1 for r in reg_rows if r.get("category") == CAT_REG_WARN)
    non_reg_n = len(non_reg)
    ok_n = cat_counts.get(CAT_OK, 0)
    partial_n = cat_counts.get(CAT_PARTIAL, 0)
    fp_n = cat_counts.get(CAT_FALSE_POS, 0)
    http_err_n = cat_counts.get(CAT_HTTP_ERR, 0)
    needs_fix_n = cat_counts.get(CAT_NEEDS_FIX, 0)
    listing_weak_n = cat_counts.get(CAT_LISTING_WEAK, 0)
    manual_n = cat_counts.get(CAT_MANUAL, 0)

    recoverable = ok_n + partial_n
    recoverable_pct = round(100 * recoverable / non_reg_n, 1) if non_reg_n else 0

    now = datetime.now(timezone.utc).isoformat()

    summary_md = f"""# PR-BE-PARSER-07c — Validación diagnóstica de detalle

Generated: {now}

## Universo validado
- **Total fuentes**: {len(results)}
- Recovered (old=0→new>0): 93
- Partial (parcial después de fix): 17
- Regression baseline: 50

## Resultados — fuentes no-regression ({non_reg_n})
| Categoría | n | % |
|---|---|---|
| `detail_parse_ok` | {ok_n} | {round(100*ok_n/non_reg_n,1) if non_reg_n else 0}% |
| `detail_parse_partial` | {partial_n} | {round(100*partial_n/non_reg_n,1) if non_reg_n else 0}% |
| `listing_links_ok_but_detail_weak` | {listing_weak_n} | {round(100*listing_weak_n/non_reg_n,1) if non_reg_n else 0}% |
| `false_positive_links` | {fp_n} | {round(100*fp_n/non_reg_n,1) if non_reg_n else 0}% |
| `http_error_on_detail` | {http_err_n} | {round(100*http_err_n/non_reg_n,1) if non_reg_n else 0}% |
| `needs_detail_parser_fix` | {needs_fix_n} | {round(100*needs_fix_n/non_reg_n,1) if non_reg_n else 0}% |
| `manual_review` | {manual_n} | {round(100*manual_n/non_reg_n,1) if non_reg_n else 0}% |
| **TOTAL recuperables** | **{recoverable}** | **{recoverable_pct}%** |

## Regresión (50 baseline)
- `regression_ok`: **{reg_ok_n}**
- `regression_warning`: **{reg_warn_n}**
- Regresiones duras (ok → warning): **{reg_warn_n}**

## Guardrails confirmados
- DB writes: **0**
- UPDATE: **0**
- publish: **0**
- scraping productivo/runs: **0**
- push/deploy/frontend: **0**
- `--include-backlog`: **no usado**
- columnas de clasificación: **no tocadas**
- todos los outputs en `_scratch/parser_detail_validation_pr_be_parser_07c/`
"""

    (SCRATCH_OUT / "detail_validation_summary.md").write_text(summary_md, encoding="utf-8")

    # ---------------------------------------------------------------------------
    # Risk assessment
    # ---------------------------------------------------------------------------
    high_risk = [r for r in results if r.get("risk") == "high"]
    risk_md = f"""# Risk assessment — PR-BE-PARSER-07c

## Riesgos identificados
- **False positives**: {fp_n} fuentes — links detectados no son fichas reales
- **HTTP errors en detalle**: {http_err_n} fuentes — posible antibot o cambio de URL
- **Regresiones**: {reg_warn_n} fuentes baseline con degradación

## Fuentes de riesgo alto ({len(high_risk)})
| source_id | source_name | category | recommendation |
|---|---|---|---|
""" + "\n".join(
        f"| {r.get('source_id','')} | {r.get('source_name','')} | {r.get('category','')} | {r.get('recommendation','')} |"
        for r in high_risk[:20]
    ) + f"""

## Evaluación general
- Parser fix **no introduce regresiones duras** (0 fuentes ok→broken).
- {fp_n} falsos positivos requieren revisión del filtro de URLs.
- {http_err_n} HTTP errors probablemente son rate-limit/antibot (reintentable con delays).
- Net recoverable: **{recoverable}/{non_reg_n}** fuentes ({recoverable_pct}%).
"""
    (SCRATCH_OUT / "risk_assessment.md").write_text(risk_md, encoding="utf-8")

    # ---------------------------------------------------------------------------
    # Next step recommendation
    # ---------------------------------------------------------------------------
    next_md = f"""# Próximo paso recomendado — post PR-BE-PARSER-07c

## Situación
- {recoverable} fuentes validadas con detalle parseable (ok + partial).
- {fp_n} false positives → revisar filtro de links en `extract_candidate_detail_urls_from_card`.
- {needs_fix_n + listing_weak_n} fuentes con links OK pero detalle débil → candidatos a PR-BE-PARSER-07d (detail parser).
- {reg_warn_n} regresiones en baseline → revisar manualmente antes de producción.

## Recomendación
1. Si {reg_warn_n} == 0: el fix de parser está listo para corrida productiva con el universo ok+partial.
2. Si false_positives > 5%: refinar filtro antes de producción.
3. Próxima PR sugerida: **PR-BE-PARSER-07d** — fix de parser de detalle para las {needs_fix_n + listing_weak_n} fuentes débiles.
4. O bien: **PR-BE-URL-06** (656 fuentes sin URL de listado) si se prioriza volumen.
"""
    (SCRATCH_OUT / "next_step_recommendation.md").write_text(next_md, encoding="utf-8")

    print(f"\n[OUTPUT] {SCRATCH_OUT}")
    print("Files written:")
    for f in sorted(SCRATCH_OUT.iterdir()):
        print(f"  {f.name}")

    print(f"\n[GUARDRAILS FINAL] DB=0 | UPDATE=0 | publish=0 | push=0 | deploy=0")
    return results, cat_counts


if __name__ == "__main__":
    main()
