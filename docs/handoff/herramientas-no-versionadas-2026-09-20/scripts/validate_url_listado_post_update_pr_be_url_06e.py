#!/usr/bin/env python
"""PR-BE-URL-06e diagnostic validation after url_listado update.

Reads the 1,057 updated sources, performs lightweight HTTP diagnostics against
the new listing URLs, and writes local reports only. It never writes DB, raw,
staging, publish_queue, public.propiedades, or scraping runs.
"""

from __future__ import annotations

import argparse
import csv
import html
import os
import pathlib
import random
import re
import threading
import time
import urllib.parse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any

import requests
from scraper.network_security import secure_get


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_UPDATED = REPO_ROOT / "_scratch" / "url_listing_update_pr_be_url_06d" / "updated_rows.csv"
DEFAULT_UPDATE_SUMMARY = REPO_ROOT / "_scratch" / "url_listing_update_pr_be_url_06d" / "update_summary.md"
DEFAULT_POST_UPDATE = REPO_ROOT / "_scratch" / "url_listing_update_pr_be_url_06d" / "post_update_validation.md"
DEFAULT_SOURCE_RESULTS = REPO_ROOT / "_scratch" / "full_scrape_coverage_7004" / "source_results.csv"
DEFAULT_ERRORS = REPO_ROOT / "_scratch" / "full_scrape_coverage_7004" / "errors_detailed.csv"
DEFAULT_TIER_A = REPO_ROOT / "_scratch" / "listing_url_db_dry_run" / "tier_a_auto_update_candidates.csv"
DEFAULT_FINAL_SAFE = REPO_ROOT / "_scratch" / "url_listing_db_preflight" / "final_safe_update_candidates.csv"
DEFAULT_OUT = REPO_ROOT / "_scratch" / "url_listing_post_update_validation"
EXPECTED_COUNT = 1057

USER_AGENT = "ERETZ-URL-Validation/06e (+diagnostic; no publish; no DB writes)"
PROHIBITED_RE = re.compile(r"(zonaprop|argenprop|properati)", re.I)
OPERATION_RE = re.compile(r"\b(venta|ventas|alquiler|alquileres|renta|comprar|emprendimiento|desarrollo)\b", re.I)
TYPE_RE = re.compile(
    r"\b(casa|casas|departamento|departamentos|depto|terreno|lote|local|oficina|galpon|ph|duplex|inmueble|propiedad|propiedades)\b",
    re.I,
)
PRICE_RE = re.compile(r"(u\$s|usd|ars|\$\s*\d|precio|consultar)", re.I)
PAGINATION_RE = re.compile(r"(page=|pagina|paginacion|pagination|siguiente|next|anterior|prev)", re.I)
CARD_RE = re.compile(r"(card|property|propiedad|inmueble|listing|result|item|grid|price|precio)", re.I)
JS_APP_RE = re.compile(r"(__NEXT_DATA__|gatsby|vite|webpack|window\.__|id=[\"']root[\"']|id=[\"']app[\"'])", re.I)
INSTITUTIONAL_RE = re.compile(r"\b(nosotros|quienes somos|contacto|tasaciones|empresa|servicios)\b", re.I)
DETAIL_PATH_RE = re.compile(
    r"(/propiedad/[^/?#]+|/propiedades/[^/?#]+/[^/?#]+|/inmueble/[^/?#]+|/inmuebles/[^/?#]+/[^/?#]+|/detalle/|/ficha/|/venta/[^/?#]+-\d+)",
    re.I,
)
LISTING_PATH_RE = re.compile(
    r"(/propiedades|/inmuebles|/venta|/ventas|/alquiler|/alquileres|/buscar|/busqueda|/listing|/listado|/resultados|/emprendimientos|/desarrollos)",
    re.I,
)


class LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.classes: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {k.lower(): v or "" for k, v in attrs}
        if tag.lower() == "a" and attrs_dict.get("href"):
            self.links.append(attrs_dict["href"])
        cls = attrs_dict.get("class")
        if cls:
            self.classes.append(cls)


def load_env_file(path: pathlib.Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_env() -> None:
    load_env_file(REPO_ROOT / ".env")
    load_env_file(REPO_ROOT / ".env.local")


def clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(clean(value)))
    except Exception:
        return default


def is_true(value: Any) -> bool:
    return clean(value).lower() in {"true", "1", "t", "yes", "y"}


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


def normalize_url(url: str) -> str:
    url = clean(url)
    if not url:
        return ""
    parsed = urllib.parse.urlsplit(url)
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/") or "/"
    return urllib.parse.urlunsplit((scheme, netloc, path, parsed.query, ""))


def base_host(url: str) -> str:
    try:
        return urllib.parse.urlsplit(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def is_homepage(candidate: str, website: str) -> bool:
    c = urllib.parse.urlsplit(candidate)
    w = urllib.parse.urlsplit(website)
    if not c.netloc or not w.netloc:
        return False
    if c.netloc.lower().removeprefix("www.") != w.netloc.lower().removeprefix("www."):
        return False
    return (c.path.rstrip("/") or "/") == "/" and not c.query


def absolute_links(base_url: str, hrefs: list[str]) -> list[str]:
    out: list[str] = []
    for href in hrefs:
        href = html.unescape(clean(href))
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "whatsapp:")):
            continue
        out.append(urllib.parse.urljoin(base_url, href))
    return out


def property_link_score(url: str) -> int:
    parsed = urllib.parse.urlsplit(url)
    path_query = f"{parsed.path}?{parsed.query}".lower()
    score = 0
    if DETAIL_PATH_RE.search(path_query):
        score += 4
    if re.search(r"(propiedad|propiedades|inmueble|inmuebles|listing|ficha|detalle)", path_query):
        score += 2
    if re.search(r"(\d{3,}|[a-z]+-[a-z]+-[a-z]+)", path_query):
        score += 1
    if re.search(r"(contacto|nosotros|tasacion|blog|noticia|staff|empresa)", path_query):
        score -= 3
    return score


def extract_signals(url: str, text: str) -> dict[str, Any]:
    parser = LinkExtractor()
    try:
        parser.feed(text[:3_000_000])
    except Exception:
        pass
    links = absolute_links(url, parser.links)
    host = base_host(url)
    internal_links = [link for link in links if base_host(link) == host]
    property_links = []
    seen = set()
    for link in internal_links:
        norm = normalize_url(link)
        if norm in seen:
            continue
        seen.add(norm)
        if property_link_score(link) >= 3:
            property_links.append(link)

    visible_text = re.sub(r"<script\b.*?</script>", " ", text, flags=re.I | re.S)
    visible_text = re.sub(r"<style\b.*?</style>", " ", visible_text, flags=re.I | re.S)
    visible_text = re.sub(r"<[^>]+>", " ", visible_text)
    visible_text = html.unescape(visible_text)
    class_blob = " ".join(parser.classes)
    combined = f"{visible_text[:500_000]} {class_blob[:200_000]}"

    card_hints = len(CARD_RE.findall(class_blob)) + min(100, len(CARD_RE.findall(visible_text)))
    price_count = len(PRICE_RE.findall(combined))
    operation_count = len(OPERATION_RE.findall(combined))
    type_count = len(TYPE_RE.findall(combined))
    pagination = bool(PAGINATION_RE.search(text) or PAGINATION_RE.search(url))
    js_app = bool(JS_APP_RE.search(text))
    institutional = len(INSTITUTIONAL_RE.findall(combined))

    return {
        "links_detected": len(internal_links),
        "property_links_detected": len(property_links),
        "property_links_sample": " | ".join(property_links[:5]),
        "price_count": price_count,
        "operation_count": operation_count,
        "type_count": type_count,
        "has_price": price_count > 0,
        "has_operation": operation_count > 0,
        "has_type": type_count > 0,
        "has_pagination": pagination,
        "card_hints": card_hints,
        "js_app": js_app,
        "institutional_terms": institutional,
        "html_len": len(text),
    }


def classify_result(
    http_status: int,
    original_url: str,
    final_url: str,
    website_url: str,
    signals: dict[str, Any],
    error: str,
) -> tuple[str, str, bool, bool, bool, str, str]:
    if error:
        return ("unexpected_error", "none", False, False, True, "unexpected_error", error)
    if http_status < 200 or http_status >= 400:
        return ("http_error", "none", False, False, True, "http_error", f"http_status={http_status}")
    if PROHIBITED_RE.search(final_url):
        return ("manual_review", "none", False, False, True, "prohibited_redirect", "redirected_to_prohibited_portal")
    if is_homepage(final_url, website_url) and not LISTING_PATH_RE.search(original_url):
        return ("redirect_problem", "low", False, False, True, "redirect_home", "redirected_to_home")

    property_links = to_int(signals.get("property_links_detected"))
    links = to_int(signals.get("links_detected"))
    cards = to_int(signals.get("card_hints"))
    has_price = bool(signals.get("has_price"))
    has_operation = bool(signals.get("has_operation"))
    has_type = bool(signals.get("has_type"))
    pagination = bool(signals.get("has_pagination"))
    js_app = bool(signals.get("js_app"))
    institutional_terms = to_int(signals.get("institutional_terms"))
    strong_listing = has_operation and has_type and (has_price or pagination)

    if property_links >= 3 and strong_listing:
        return ("success_after_url_fix", "high", True, False, False, "", "property_links_and_listing_signals")
    if property_links >= 1 and (has_operation or has_type or has_price):
        return ("partial_after_url_fix", "medium", False, True, False, "", "some_property_links_and_signals")
    if property_links == 0 and cards >= 12 and strong_listing:
        return ("needs_parser_fix", "medium", False, False, True, "parser_no_links", "cards_and_signals_without_detail_links")
    if property_links < 3 and cards >= 8 and (has_operation and has_type):
        return ("needs_parser_fix", "medium", False, False, True, "parser_low_links", "listing_signals_but_low_detail_links")
    if links <= 5 and js_app and (has_operation or has_type or has_price or len(str(signals.get("html_len"))) > 0):
        return ("needs_playwright", "low", False, False, True, "js_rendered", "low_static_links_js_app")
    if property_links == 0 and (has_operation or has_type or has_price) and not strong_listing:
        return ("partial_after_url_fix", "low", False, True, False, "", "listing_terms_without_detail_links")
    if institutional_terms > 5 and not strong_listing and property_links == 0:
        return ("listing_url_bad_after_update", "low", False, False, True, "institutional_page", "institutional_content_no_listing")
    if property_links == 0:
        return ("still_no_property_links", "none", False, False, True, "no_property_links", "no_property_links_detected")
    return ("manual_review", "low", False, False, True, "ambiguous", "ambiguous_listing_signals")


def fetch_one(row: dict[str, str], session: requests.Session, timeout: float) -> dict[str, Any]:
    source_id = clean(row.get("source_id"))
    source_name = clean(row.get("source_name"))
    website_url = clean(row.get("website_url"))
    new_url = clean(row.get("new_url_listado"))
    old_url = clean(row.get("old_url_listado"))
    previous_status = clean(row.get("previous_status"))
    previous_error_category = clean(row.get("previous_error_category"))
    estimated_yield = to_int(row.get("estimated_property_yield"))
    error = ""
    status = 0
    final_url = ""
    elapsed = 0.0
    text = ""
    try:
        started = time.perf_counter()
        resp = secure_get(session, new_url, timeout=(8, timeout))
        elapsed = round(time.perf_counter() - started, 3)
        status = resp.status_code
        final_url = resp.url
        content_type = resp.headers.get("content-type", "")
        if "text" in content_type or "html" in content_type or not content_type:
            text = resp.text or ""
        else:
            text = ""
    except Exception as exc:
        error = type(exc).__name__

    signals = extract_signals(final_url or new_url, text) if text else {
        "links_detected": 0,
        "property_links_detected": 0,
        "property_links_sample": "",
        "price_count": 0,
        "operation_count": 0,
        "type_count": 0,
        "has_price": False,
        "has_operation": False,
        "has_type": False,
        "has_pagination": False,
        "card_hints": 0,
        "js_app": False,
        "institutional_terms": 0,
        "html_len": len(text),
    }
    category, parse_quality, is_success, is_partial, is_failed, error_type, notes = classify_result(
        status, new_url, final_url or new_url, website_url, signals, error
    )
    properties_parsed = signals["property_links_detected"]
    if category == "needs_parser_fix":
        properties_parsed = 0
    evidence = (
        f"http={status}; links={signals['links_detected']}; property_links={signals['property_links_detected']}; "
        f"cards={signals['card_hints']}; price={signals['price_count']}; operation={signals['operation_count']}; "
        f"type={signals['type_count']}; pagination={signals['has_pagination']}; elapsed={elapsed}s"
    )
    return {
        "source_id": source_id,
        "source_name": source_name,
        "website_url": website_url,
        "old_url_listado": old_url,
        "new_url_listado": new_url,
        "previous_status": previous_status,
        "previous_error_category": previous_error_category,
        "new_status": category,
        "http_status": status,
        "final_url_after_redirect": final_url,
        "links_detected": signals["links_detected"],
        "property_links_detected": signals["property_links_detected"],
        "property_links_sample": signals["property_links_sample"],
        "properties_parsed": properties_parsed,
        "parse_quality": parse_quality,
        "error_type": error_type,
        "needs_parser_fix": category == "needs_parser_fix",
        "needs_playwright": category == "needs_playwright",
        "needs_manual_review": category == "manual_review",
        "is_success": is_success,
        "is_partial": is_partial,
        "is_failed": is_failed,
        "estimated_property_yield": estimated_yield,
        "score": to_int(row.get("score")),
        "evidence": evidence,
        "notes": notes,
    }


def db_snapshot() -> dict[str, int | None | str]:
    load_env()
    db_url = os.getenv("INTERNAL_DB_URL", "").strip()
    if not db_url:
        return {"error": "missing_internal_db_url"}
    try:
        import psycopg
        from psycopg import sql
        from psycopg.rows import dict_row
        conn = psycopg.connect(db_url, row_factory=dict_row, connect_timeout=30)
        conn.autocommit = True
        out: dict[str, int | None | str] = {}
        with conn.cursor() as cur:
            cur.execute("SET default_transaction_read_only = on")
            for table in [("public", "propiedades"), ("public", "publish_queue"), ("public", "scraping_runs")]:
                schema, name = table
                cur.execute(
                    """
                    SELECT EXISTS (
                      SELECT 1 FROM information_schema.tables
                      WHERE table_schema = %s AND table_name = %s
                    ) AS exists
                    """,
                    (schema, name),
                )
                if not cur.fetchone()["exists"]:
                    out[f"{schema}.{name}"] = None
                    continue
                cur.execute(sql.SQL("SELECT count(*) AS n FROM {}").format(sql.Identifier(schema, name)))
                out[f"{schema}.{name}"] = int(cur.fetchone()["n"])
        conn.close()
        return out
    except Exception as exc:
        return {"error": str(exc)[:160]}


def md_table(rows: list[dict[str, Any]], fields: list[str], limit: int = 20) -> str:
    subset = rows[:limit]
    if not subset:
        return "_Sin filas._"
    lines = ["| " + " | ".join(fields) + " |", "| " + " | ".join(["---"] * len(fields)) + " |"]
    for row in subset:
        values = []
        for field in fields:
            value = clean(row.get(field)).replace("|", "\\|")
            if len(value) > 120:
                value = value[:117] + "..."
            values.append(value)
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def merge_inputs(updated: list[dict[str, str]], final_safe: list[dict[str, str]], source_results: list[dict[str, str]]) -> list[dict[str, str]]:
    safe_by_id = {clean(row.get("source_id")): row for row in final_safe}
    prev_by_id = {clean(row.get("source_id")): row for row in source_results}
    rows: list[dict[str, str]] = []
    for row in updated:
        sid = clean(row.get("source_id"))
        safe = safe_by_id.get(sid, {})
        prev = prev_by_id.get(sid, {})
        rows.append({
            "source_id": sid,
            "source_name": clean(row.get("source_name") or safe.get("source_name") or prev.get("source_name")),
            "website_url": clean(safe.get("website_url_db") or safe.get("website_url_csv") or prev.get("website_url")),
            "old_url_listado": clean(row.get("old_url_listado")),
            "new_url_listado": clean(row.get("new_url_listado")),
            "previous_status": clean(prev.get("final_status")),
            "previous_error_category": clean(prev.get("error_category")),
            "previous_property_links_count": clean(prev.get("property_links_count")),
            "previous_properties_parsed": clean(prev.get("properties_parsed")),
            "estimated_property_yield": clean(row.get("estimated_property_yield")),
            "score": clean(row.get("score")),
        })
    return rows


def write_docs(out: pathlib.Path, results: list[dict[str, Any]], before_snapshot: dict[str, Any], after_snapshot: dict[str, Any]) -> None:
    counts = Counter(row["new_status"] for row in results)
    success = [r for r in results if r["new_status"] == "success_after_url_fix"]
    partial = [r for r in results if r["new_status"] == "partial_after_url_fix"]
    failed = [r for r in results if r["new_status"] not in {"success_after_url_fix", "partial_after_url_fix"}]
    parser = [r for r in results if r["new_status"] == "needs_parser_fix"]
    playwright = [r for r in results if r["new_status"] == "needs_playwright"]
    manual = [r for r in results if r["new_status"] == "manual_review"]
    url_bad = [r for r in results if r["new_status"] in {"listing_url_bad_after_update", "redirect_problem", "http_error"}]
    links_total = sum(to_int(r.get("property_links_detected")) for r in results)
    parsed_total = sum(to_int(r.get("properties_parsed")) for r in results)
    top_recovered = sorted(success + partial, key=lambda r: (to_int(r.get("estimated_property_yield")), to_int(r.get("property_links_detected"))), reverse=True)
    top_failed = sorted(failed, key=lambda r: (to_int(r.get("estimated_property_yield")), to_int(r.get("property_links_detected"))), reverse=True)
    before_status = Counter(clean(r.get("previous_status")) or "unknown" for r in results)
    after_status = Counter(clean(r.get("new_status")) or "unknown" for r in results)

    comparison = []
    for row in results:
        comparison.append({
            "source_id": row["source_id"],
            "source_name": row["source_name"],
            "previous_status": row["previous_status"],
            "previous_error_category": row["previous_error_category"],
            "new_status": row["new_status"],
            "old_url_listado": row["old_url_listado"],
            "new_url_listado": row["new_url_listado"],
            "previous_property_links_count": row.get("previous_property_links_count", ""),
            "new_property_links_detected": row["property_links_detected"],
            "new_properties_parsed": row["properties_parsed"],
            "estimated_property_yield": row["estimated_property_yield"],
        })
    write_csv(out / "before_after_comparison.csv", comparison)
    write_csv(out / "top_recovered_by_yield.csv", top_recovered[:100])
    write_csv(out / "top_still_failed_by_yield.csv", top_failed[:100])

    category_lines = "\n".join(f"- {k}: {v}" for k, v in sorted(counts.items()))
    before_lines = "\n".join(f"- {k}: {v}" for k, v in before_status.most_common(20))
    after_lines = "\n".join(f"- {k}: {v}" for k, v in after_status.most_common(20))
    summary = f"""# PR-BE-URL-06e post-update validation summary

Generated: {datetime.now(timezone.utc).isoformat()}

## Resultado
- Total fuentes validadas: **{len(results)}**
- success_after_url_fix: **{len(success)}**
- partial_after_url_fix: **{len(partial)}**
- still_failed_after_url_fix: **{len(failed)}**
- needs_parser_fix: **{len(parser)}**
- needs_playwright: **{len(playwright)}**
- problema de URL aun: **{len(url_bad)}**
- total property links detectados: **{links_total}**
- total propiedades parseadas en modo diagnostico: **{parsed_total}**

## Categorias finales
{category_lines}

## Top 20 recuperadas por impacto
{md_table(top_recovered, ['source_id', 'source_name', 'previous_status', 'new_status', 'estimated_property_yield', 'property_links_detected', 'properties_parsed', 'new_url_listado'])}

## Top 20 que siguen fallando por impacto
{md_table(top_failed, ['source_id', 'source_name', 'previous_status', 'new_status', 'estimated_property_yield', 'property_links_detected', 'error_type', 'notes', 'new_url_listado'])}

## Comparacion before/after
### Before
{before_lines}

### After
{after_lines}

## DB snapshots read-only
- before: {before_snapshot}
- after: {after_snapshot}

## Riesgos
- Validacion HTTP/HTML liviana; no escribe DB ni visita cada ficha en profundidad.
- `properties_parsed` es conteo diagnostico de fichas/links inferidos desde el listado, no una importacion productiva.
- Sitios JS pueden requerir Playwright para confirmar.
- Algunos sitios pueden variar por rate limit, region o user-agent.

## Siguiente PR recomendado
PR-BE-URL-06f: validacion controlada de scraping en lotes chicos sobre las recuperadas, sin publish, midiendo success real del parser por familia/CMS.
"""
    (out / "post_update_validation_summary.md").write_text(summary, encoding="utf-8")

    risk = """# Risk assessment

- No se escribio DB ni raw/staging.
- La medicion usa requests HTTP livianos, por lo que puede subestimar sitios renderizados por JavaScript.
- Las fuentes `needs_parser_fix` ya muestran señales inmobiliarias, pero requieren ajuste de parser antes de productivizar.
- Las fuentes `needs_playwright` no deben considerarse fallidas definitivas sin una confirmacion Playwright.
"""
    (out / "risk_assessment.md").write_text(risk, encoding="utf-8")
    recommendation = """# Next step recommendation

No publicar ni correr pipeline productivo todavia.

Recomendacion: tomar las fuentes `success_after_url_fix` de mayor impacto y correr un PR separado de scraping
diagnostico en minilotes, sin escritura en raw/staging ni publish, para medir parser success real y priorizar
familias que aun quedan en `needs_parser_fix` o `needs_playwright`.
"""
    (out / "next_step_recommendation.md").write_text(recommendation, encoding="utf-8")


def validate_outputs(results: list[dict[str, Any]], before_snapshot: dict[str, Any], after_snapshot: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if len(results) != EXPECTED_COUNT:
        errors.append(f"expected_{EXPECTED_COUNT}_results_got_{len(results)}")
    if before_snapshot != after_snapshot:
        errors.append(f"db_snapshots_changed before={before_snapshot} after={after_snapshot}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="PR-BE-URL-06e post-update diagnostic validation")
    parser.add_argument("--updated", default=str(DEFAULT_UPDATED))
    parser.add_argument("--update-summary", default=str(DEFAULT_UPDATE_SUMMARY))
    parser.add_argument("--post-update", default=str(DEFAULT_POST_UPDATE))
    parser.add_argument("--source-results", default=str(DEFAULT_SOURCE_RESULTS))
    parser.add_argument("--errors-detailed", default=str(DEFAULT_ERRORS))
    parser.add_argument("--tier-a", default=str(DEFAULT_TIER_A))
    parser.add_argument("--final-safe", default=str(DEFAULT_FINAL_SAFE))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=12.0)
    parser.add_argument("--seed", type=int, default=606)
    parser.add_argument("--include-backlog", action="store_true")
    args = parser.parse_args()

    if args.include_backlog:
        raise SystemExit("--include-backlog is not authorized in PR-BE-URL-06e")

    required_paths = [
        pathlib.Path(args.updated),
        pathlib.Path(args.update_summary),
        pathlib.Path(args.post_update),
        pathlib.Path(args.source_results),
        pathlib.Path(args.errors_detailed),
        pathlib.Path(args.tier_a),
        pathlib.Path(args.final_safe),
    ]
    missing = [str(path) for path in required_paths if not path.exists()]
    if missing:
        raise SystemExit("Missing required inputs: " + "; ".join(missing))

    updated = read_csv(pathlib.Path(args.updated))
    if len(updated) != EXPECTED_COUNT:
        raise SystemExit(f"Expected {EXPECTED_COUNT} updated rows, got {len(updated)}")
    ids = [clean(row.get("source_id")) for row in updated]
    duplicate_ids = [sid for sid, count in Counter(ids).items() if count > 1]
    if duplicate_ids:
        raise SystemExit(f"Duplicate source_id values: {len(duplicate_ids)}")

    final_safe = read_csv(pathlib.Path(args.final_safe))
    source_results = read_csv(pathlib.Path(args.source_results))
    read_csv(pathlib.Path(args.errors_detailed))
    read_csv(pathlib.Path(args.tier_a))

    rows = merge_inputs(updated, final_safe, source_results)
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    before_snapshot = db_snapshot()
    random.seed(args.seed)
    shuffled = list(rows)
    random.shuffle(shuffled)
    lock = threading.Lock()
    completed = 0
    results: list[dict[str, Any]] = []

    def make_session() -> requests.Session:
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
        return session

    thread_local = threading.local()

    def worker(row: dict[str, str]) -> dict[str, Any]:
        if not hasattr(thread_local, "session"):
            thread_local.session = make_session()
        return fetch_one(row, thread_local.session, args.timeout)

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = [executor.submit(worker, row) for row in shuffled]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            with lock:
                completed += 1
                if completed % 100 == 0 or completed == len(shuffled):
                    print(f"validated={completed}/{len(shuffled)}")

    results.sort(key=lambda r: to_int(r["source_id"]))
    after_snapshot = db_snapshot()
    validation_errors = validate_outputs(results, before_snapshot, after_snapshot)

    write_csv(out / "post_update_validation_results.csv", results)
    success = [r for r in results if r["new_status"] == "success_after_url_fix"]
    partial = [r for r in results if r["new_status"] == "partial_after_url_fix"]
    failed = [r for r in results if r["new_status"] not in {"success_after_url_fix", "partial_after_url_fix"}]
    parser_rows = [r for r in results if r["new_status"] == "needs_parser_fix"]
    playwright_rows = [r for r in results if r["new_status"] == "needs_playwright"]
    manual_rows = [r for r in results if r["new_status"] == "manual_review"]
    write_csv(out / "success_after_url_fix.csv", success)
    write_csv(out / "partial_after_url_fix.csv", partial)
    write_csv(out / "still_failed_after_url_fix.csv", failed)
    write_csv(out / "needs_parser_fix.csv", parser_rows)
    write_csv(out / "needs_playwright.csv", playwright_rows)
    write_csv(out / "manual_review.csv", manual_rows)
    write_docs(out, results, before_snapshot, after_snapshot)

    validation_text = [
        "# Validation guardrails",
        "",
        f"- zero DB writes: True",
        f"- zero UPDATE: True",
        f"- zero publish: True",
        f"- zero public.propiedades changes by count: {before_snapshot.get('public.propiedades') == after_snapshot.get('public.propiedades')}",
        f"- zero publish_queue changes by count: {before_snapshot.get('public.publish_queue') == after_snapshot.get('public.publish_queue')}",
        f"- zero productive runs created by count: {before_snapshot.get('public.scraping_runs') == after_snapshot.get('public.scraping_runs')}",
        "- zero push/deploy/frontend: True",
        "- --include-backlog used: False",
        "- prohibited columns touched: False",
        "- outputs under _scratch: True",
        "",
        "## Errors",
    ]
    validation_text.extend(f"- {err}" for err in validation_errors)
    if not validation_errors:
        validation_text.append("_Sin errores._")
    (out / "validation_guardrails.md").write_text("\n".join(validation_text) + "\n", encoding="utf-8")

    print(f"total={len(results)}")
    print(f"success_after_url_fix={len(success)}")
    print(f"partial_after_url_fix={len(partial)}")
    print(f"still_failed_after_url_fix={len(failed)}")
    print(f"needs_parser_fix={len(parser_rows)}")
    print(f"needs_playwright={len(playwright_rows)}")
    print(f"links_detected={sum(to_int(r.get('property_links_detected')) for r in results)}")
    print(f"properties_parsed={sum(to_int(r.get('properties_parsed')) for r in results)}")
    print(f"validation_errors={len(validation_errors)}")
    print(f"out={out}")


if __name__ == "__main__":
    main()
