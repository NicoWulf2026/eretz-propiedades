#!/usr/bin/env python
"""PR-BE-URL-06c read-only DB preflight for url_listado updates.

This script:
- reads local Tier A proposals
- reads public.inmobiliarias_main through Supabase REST GET only
- writes local reports and SQL previews
- never executes UPDATE, publish, scraping runs, or DB writes
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import time
import urllib.parse
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import requests
from scraper.network_security import secure_get


REPO_ROOT = Path(__file__).resolve().parents[1]

OUTPUT_FIELDS = [
    "source_id",
    "source_name",
    "website_url_csv",
    "website_url_db",
    "current_url_listado_csv",
    "current_url_listado_db",
    "proposed_url_listado",
    "final_classification",
    "confidence",
    "score",
    "property_links_count",
    "estimated_property_yield",
    "db_exists",
    "db_unique",
    "website_compatible",
    "current_url_matches_db",
    "exclude_from_scraping",
    "diagnostic_status_db",
    "scraping_readiness_db",
    "safety_reasons",
    "db_mismatch_reasons",
    "manual_review_reasons",
    "evidence",
    "risk",
    "recommended_action",
]

DB_COLUMN_SETS = [
    [
        "id",
        "nombre",
        "web",
        "url_listado",
        "cms_detectado",
        "estrategia_scraping",
        "diagnostic_status",
        "scraping_readiness",
        "exclude_from_scraping",
        "exclude_reason",
        "sitio_activo",
        "activa",
    ],
    [
        "id",
        "nombre",
        "web",
        "url_listado",
        "diagnostic_status",
        "scraping_readiness",
        "exclude_from_scraping",
        "exclude_reason",
        "sitio_activo",
        "activa",
    ],
    ["id", "nombre", "web", "url_listado", "diagnostic_status", "scraping_readiness", "exclude_from_scraping"],
    ["id", "nombre", "web", "url_listado"],
]

PROHIBITED_HOST_RE = re.compile(
    r"(^|\.)("
    r"zonaprop\.com|argenprop\.com|properati\.com|mercadolibre\.com|inmuebles\.clarin\.com"
    r")$",
    re.I,
)
INCOMPATIBLE_DIAGNOSTIC = {
    "missing_url",
    "domain_down",
    "dominio_caido",
    "prohibited_source",
    "skipped_prohibited_source",
    "skipped_missing_url",
}
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
PRICE_RE = re.compile(r"(?:u\s?\$s|usd|ars|\$)\s*[0-9][0-9\.\,]{2,}", re.I)


def load_env_file_silent(path: Path) -> None:
    """Load env values without printing or modifying the file."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_env_silent() -> None:
    load_env_file_silent(REPO_ROOT / ".env")
    load_env_file_silent(REPO_ROOT / ".env.local")


def supabase_config() -> Tuple[str, str]:
    load_env_silent()
    url = (
        os.getenv("SUPABASE_URL")
        or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
        or ""
    ).rstrip("/")
    key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_KEY")
        or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
        or ""
    )
    if not url or not key:
        raise SystemExit("Missing Supabase environment variables; values were not printed.")
    return url, key


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        raise SystemExit(f"Missing input: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return [dict(row) for row in csv.DictReader(f)]


def write_csv(path: Path, rows: Sequence[Dict[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def clean(value: Any) -> str:
    return str(value or "").strip()


def to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or str(value).strip() == "":
            return default
        return int(float(str(value).strip()))
    except Exception:
        return default


def is_true(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "t", "yes", "y", "si", "sí"}


def normalize_url(value: str) -> str:
    raw = clean(value)
    if not raw:
        return ""
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw
    try:
        p = urllib.parse.urlsplit(raw)
    except Exception:
        return raw.lower()
    path = (p.path or "/").rstrip("/") or "/"
    return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), path, p.query, ""))


def host_of(url: str) -> str:
    try:
        return urllib.parse.urlsplit(normalize_url(url)).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def is_prohibited_url(url: str) -> bool:
    host = host_of(url)
    return bool(host and PROHIBITED_HOST_RE.search(host))


def is_homepage_url(candidate: str, website: str) -> bool:
    c = normalize_url(candidate)
    w = normalize_url(website)
    if not c or not w or host_of(c) != host_of(w):
        return False
    try:
        p = urllib.parse.urlsplit(c)
    except Exception:
        return False
    return (p.path or "/") in {"", "/"} and not p.query


def looks_like_detail_url(value: str) -> bool:
    url = normalize_url(value)
    try:
        p = urllib.parse.urlsplit(url)
    except Exception:
        return False
    path = (p.path or "/").lower().strip("/")
    if not path:
        return False
    segments = [s for s in path.split("/") if s]
    first = segments[0] if segments else ""
    last = segments[-1] if segments else ""
    if len(segments) >= 2 and (
        first.startswith("prop-")
        or first.startswith("prop_")
        or first.startswith("propiedad-")
        or first.startswith("inmueble-")
    ):
        return True
    if first in {"detalle", "detalles", "ficha", "property", "properties"} and len(segments) >= 2:
        return True
    if first in {"nota", "notas", "blog", "noticia", "noticias"}:
        return True
    singular_type = r"(casa|departamento|depto|terreno|lote|local|oficina|ph|duplex|galpon)"
    if re.search(rf"^(venta|alquiler|renta)-{singular_type}-.+", last):
        return True
    if re.search(rf"^{singular_type}-(en-)?(venta|alquiler|renta)-.+", last):
        return True
    if re.search(r"(propiedad|inmueble|property)[-/][^/?]*\d{3,}", path):
        return True
    return False


def compatible_website(csv_url: str, db_url: str) -> bool:
    if not csv_url or not db_url:
        return False
    csv_host = host_of(csv_url)
    db_host = host_of(db_url)
    if not csv_host or not db_host:
        return False
    return csv_host == db_host or csv_host.endswith("." + db_host) or db_host.endswith("." + csv_host)


def exact_url_match(csv_url: str, db_url: str) -> bool:
    return clean(csv_url) == clean(db_url)


def sql_quote(value: str) -> str:
    return "'" + clean(value).replace("'", "''") + "'"


def db_headers(key: str) -> Dict[str, str]:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }


def chunked(items: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def fetch_db_rows(base_url: str, key: str, source_ids: Sequence[int]) -> Dict[str, List[Dict[str, Any]]]:
    session = requests.Session()
    session.headers.update(db_headers(key))
    by_id: Dict[str, List[Dict[str, Any]]] = {}
    for chunk in chunked(list(source_ids), 150):
        ids = ",".join(str(i) for i in chunk)
        url = f"{base_url}/rest/v1/inmobiliarias_main"
        resp = None
        last_error = ""
        for cols in DB_COLUMN_SETS:
            params = {
                "select": ",".join(cols),
                "id": f"in.({ids})",
                "order": "id.asc",
            }
            resp = session.get(url, params=params, timeout=40)
            if resp.status_code < 400:
                break
            last_error = resp.text[:300]
        if resp is None or resp.status_code >= 400:
            raise RuntimeError(f"Supabase read failed status={getattr(resp, 'status_code', 'NA')}: {last_error}")
        for row in resp.json():
            sid = str(row.get("id"))
            by_id.setdefault(sid, []).append(row)
    return by_id


def db_website(row: Dict[str, Any]) -> str:
    return clean(row.get("web") or row.get("website_url") or row.get("url"))


def classify_row(csv_row: Dict[str, str], db_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    sid = clean(csv_row.get("source_id"))
    db_exists = len(db_rows) > 0
    db_unique = len(db_rows) == 1
    db_row = db_rows[0] if db_rows else {}
    website_csv = clean(csv_row.get("website_url"))
    website_db = db_website(db_row)
    current_csv = clean(csv_row.get("current_url_listado"))
    current_db = clean(db_row.get("url_listado"))
    proposed = clean(csv_row.get("proposed_url_listado"))
    diagnostic = clean(db_row.get("diagnostic_status")).lower()
    readiness = clean(db_row.get("scraping_readiness")).lower()
    exclude = is_true(db_row.get("exclude_from_scraping"))

    mismatch: List[str] = []
    safety: List[str] = []
    manual: List[str] = []

    if not db_exists:
        mismatch.append("source_id_not_found")
    if db_exists and not db_unique:
        mismatch.append("source_id_not_unique")
    if db_exists and not compatible_website(website_csv, website_db):
        mismatch.append("website_mismatch")
    if db_exists and not exact_url_match(current_csv, current_db):
        mismatch.append("current_url_listado_mismatch")

    if not proposed:
        safety.append("empty_proposed_url")
    if proposed and normalize_url(proposed) == normalize_url(current_db):
        safety.append("proposed_equals_current_db")
    if is_prohibited_url(proposed) or is_prohibited_url(website_csv) or is_prohibited_url(website_db):
        safety.append("prohibited_portal")
    if exclude:
        safety.append("exclude_from_scraping_true")
    if diagnostic in INCOMPATIBLE_DIAGNOSTIC:
        safety.append(f"incompatible_diagnostic_status:{diagnostic}")
    if readiness in {"excluded", "prohibited"}:
        safety.append(f"incompatible_scraping_readiness:{readiness}")
    if is_homepage_url(proposed, website_db or website_csv):
        safety.append("proposed_homepage")
    if looks_like_detail_url(proposed):
        safety.append("proposed_property_detail")
    if to_int(csv_row.get("property_links_count")) < 3:
        safety.append("property_links_lt_3")
    if to_int(csv_row.get("score")) < 90:
        safety.append("score_lt_90")
    if clean(csv_row.get("confidence")).lower() != "high":
        safety.append("confidence_not_high")

    if not diagnostic:
        manual.append("diagnostic_status_missing_in_db")
    if not website_db:
        manual.append("website_missing_in_db")

    if mismatch:
        classification = "blocked_by_db_mismatch"
        action = "do_not_update_until_db_diff_reviewed"
    elif safety:
        classification = "blocked_by_safety"
        action = "do_not_update"
    elif manual:
        classification = "needs_manual_review"
        action = "manual_review_before_update"
    else:
        classification = "final_safe_update"
        action = "eligible_for_future_update_after_authorization"

    return {
        "source_id": sid,
        "source_name": clean(csv_row.get("source_name") or db_row.get("nombre")),
        "website_url_csv": website_csv,
        "website_url_db": website_db,
        "current_url_listado_csv": current_csv,
        "current_url_listado_db": current_db,
        "proposed_url_listado": proposed,
        "final_classification": classification,
        "confidence": clean(csv_row.get("confidence")),
        "score": to_int(csv_row.get("score")),
        "property_links_count": to_int(csv_row.get("property_links_count")),
        "estimated_property_yield": to_int(csv_row.get("estimated_property_yield")),
        "db_exists": db_exists,
        "db_unique": db_unique,
        "website_compatible": db_exists and compatible_website(website_csv, website_db),
        "current_url_matches_db": db_exists and exact_url_match(current_csv, current_db),
        "exclude_from_scraping": exclude,
        "diagnostic_status_db": diagnostic,
        "scraping_readiness_db": readiness,
        "safety_reasons": ";".join(safety),
        "db_mismatch_reasons": ";".join(mismatch),
        "manual_review_reasons": ";".join(manual),
        "evidence": clean(csv_row.get("evidence")),
        "risk": clean(csv_row.get("risk")),
        "recommended_action": action,
    }


def update_sql(rows: Sequence[Dict[str, Any]]) -> str:
    lines = [
        "-- DRY RUN ONLY",
        "-- DO NOT EXECUTE WITHOUT EXPLICIT AUTHORIZATION",
        "-- PR-BE-URL-06c",
        "-- Preview only: updates public.inmobiliarias_main.url_listado for final_safe_update rows.",
        "",
        "BEGIN;",
        "",
        "UPDATE public.inmobiliarias_main AS i",
        "SET url_listado = v.new_url_listado",
        "FROM (VALUES",
    ]
    value_lines = []
    for row in rows:
        value_lines.append(
            f"  ({to_int(row['source_id'])}, {sql_quote(row['current_url_listado_db'])}, {sql_quote(row['proposed_url_listado'])})"
        )
    lines.append(",\n".join(value_lines))
    lines.extend(
        [
            ") AS v(id, old_url_listado, new_url_listado)",
            "WHERE i.id = v.id",
            "  AND COALESCE(i.url_listado, '') = COALESCE(v.old_url_listado, '');",
            "",
            "ROLLBACK;",
            "",
        ]
    )
    return "\n".join(lines)


def rollback_sql(rows: Sequence[Dict[str, Any]]) -> str:
    lines = [
        "-- DRY RUN ONLY",
        "-- DO NOT EXECUTE WITHOUT EXPLICIT AUTHORIZATION",
        "-- PR-BE-URL-06c rollback preview",
        "",
        "BEGIN;",
        "",
        "UPDATE public.inmobiliarias_main AS i",
        "SET url_listado = v.old_url_listado",
        "FROM (VALUES",
    ]
    value_lines = []
    for row in rows:
        value_lines.append(
            f"  ({to_int(row['source_id'])}, {sql_quote(row['current_url_listado_db'])}, {sql_quote(row['proposed_url_listado'])})"
        )
    lines.append(",\n".join(value_lines))
    lines.extend(
        [
            ") AS v(id, old_url_listado, new_url_listado)",
            "WHERE i.id = v.id",
            "  AND COALESCE(i.url_listado, '') = COALESCE(v.new_url_listado, '');",
            "",
            "ROLLBACK;",
            "",
        ]
    )
    return "\n".join(lines)


def html_signals(text: str) -> Dict[str, Any]:
    lower = text.lower()
    operation = any(t in lower for t in ["venta", "alquiler", "comprar", "renta"])
    ptype = any(t in lower for t in ["casa", "departamento", "terreno", "lote", "local", "oficina", "ph"])
    price = bool(PRICE_RE.search(text))
    cards = len(re.findall(r"\b(card|property|propiedad|inmueble|listing|resultado|item)\b", lower))
    links = len(re.findall(r"<a\s+[^>]*href=", text, re.I))
    pagination = any(t in lower for t in ["siguiente", "anterior", "page=", "página", "pagina"])
    return {
        "operation": operation,
        "property_type": ptype,
        "price": price,
        "cards": cards,
        "links": links,
        "pagination": pagination,
    }


def http_spotcheck(rows: Sequence[Dict[str, Any]], out: Path, timeout: float) -> List[Dict[str, Any]]:
    top = sorted(rows, key=lambda r: (to_int(r["estimated_property_yield"]), to_int(r["score"])), reverse=True)[:50]
    remaining = [r for r in rows if r["source_id"] not in {x["source_id"] for x in top}]
    rng = random.Random(606)
    sample = rng.sample(remaining, min(50, len(remaining))) if remaining else []
    selected = top + sample
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,*/*"})
    results = []
    for idx, row in enumerate(selected, 1):
        url = row["proposed_url_listado"]
        started = time.monotonic()
        status = ""
        final_url = ""
        error = ""
        text = ""
        try:
            resp = secure_get(session, url, timeout=(8, timeout))
            status = str(resp.status_code)
            final_url = resp.url
            ctype = resp.headers.get("content-type", "")
            if "html" in ctype or "text" in ctype or not ctype:
                text = resp.text[:180_000]
        except Exception as exc:
            error = type(exc).__name__
        signals = html_signals(text)
        redirects_home = is_homepage_url(final_url or url, row["website_url_db"] or row["website_url_csv"])
        prohibited = is_prohibited_url(final_url or url)
        ok = (
            status == "200"
            and not redirects_home
            and not prohibited
            and (signals["links"] >= 3 or signals["cards"] >= 3)
            and (signals["operation"] or signals["property_type"])
        )
        results.append(
            {
                "source_id": row["source_id"],
                "source_name": row["source_name"],
                "proposed_url_listado": url,
                "sample_group": "top50" if idx <= len(top) else "random50",
                "http_status": status,
                "final_url_after_redirect": final_url,
                "error": error,
                "redirects_home": redirects_home,
                "is_prohibited": prohibited,
                "has_operation_signal": signals["operation"],
                "has_property_type_signal": signals["property_type"],
                "has_price_signal": signals["price"],
                "links_count_light": signals["links"],
                "card_hints_light": signals["cards"],
                "has_pagination_signal": signals["pagination"],
                "spotcheck_ok": ok,
                "elapsed_ms": int((time.monotonic() - started) * 1000),
            }
        )
    return results


def write_csv_generic(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    write_csv(path, rows, fields)


def md_table(rows: Sequence[Dict[str, Any]], fields: Sequence[str], limit: int = 20) -> str:
    subset = list(rows)[:limit]
    if not subset:
        return "_Sin filas._\n"
    out = ["| " + " | ".join(fields) + " |", "| " + " | ".join(["---"] * len(fields)) + " |"]
    for row in subset:
        vals = []
        for f in fields:
            v = str(row.get(f, "")).replace("|", "\\|").replace("\n", " ")
            if len(v) > 90:
                v = v[:87] + "..."
            vals.append(v)
        out.append("| " + " | ".join(vals) + " |")
    return "\n".join(out) + "\n"


def validate_outputs(safe: Sequence[Dict[str, Any]], all_rows: Sequence[Dict[str, Any]], update_text: str, rollback_text: str) -> List[str]:
    errors = []
    seen = Counter(r["source_id"] for r in all_rows)
    dupes = [sid for sid, n in seen.items() if n > 1]
    if dupes:
        errors.append(f"duplicate_source_id={len(dupes)}")
    forbidden_tokens = [
        "cms_detectado",
        "estrategia_scraping",
        "diagnostic_status",
        "scraping_readiness",
        "exclude_from_scraping",
        "sitio_activo",
        r"\bactiva\b",
        "publish_queue",
        "propiedades_staging",
        "propiedades_raw",
        "public.propiedades",
    ]
    lower_update = update_text.lower()
    lower_rollback = rollback_text.lower()
    for token in forbidden_tokens:
        if re.search(token, lower_update):
            errors.append(f"update_sql_forbidden_token={token}")
        if re.search(token, lower_rollback):
            errors.append(f"rollback_sql_forbidden_token={token}")
    if "update public.inmobiliarias_main" not in lower_update:
        errors.append("update_sql_missing_target_table")
    if "set url_listado" not in lower_update:
        errors.append("update_sql_missing_url_listado_set")
    for row in safe:
        sid = row["source_id"]
        if row["exclude_from_scraping"]:
            errors.append(f"safe_excluded source_id={sid}")
        if row["diagnostic_status_db"] in INCOMPATIBLE_DIAGNOSTIC:
            errors.append(f"safe_incompatible_diagnostic source_id={sid}")
        if not row["proposed_url_listado"]:
            errors.append(f"safe_empty_proposed source_id={sid}")
        if normalize_url(row["proposed_url_listado"]) == normalize_url(row["current_url_listado_db"]):
            errors.append(f"safe_proposed_equals_current source_id={sid}")
        if is_homepage_url(row["proposed_url_listado"], row["website_url_db"] or row["website_url_csv"]):
            errors.append(f"safe_home source_id={sid}")
        if looks_like_detail_url(row["proposed_url_listado"]):
            errors.append(f"safe_detail source_id={sid}")
        if to_int(row["property_links_count"]) < 3:
            errors.append(f"safe_links_lt_3 source_id={sid}")
        if to_int(row["score"]) < 90:
            errors.append(f"safe_score_lt_90 source_id={sid}")
        if clean(row["confidence"]).lower() != "high":
            errors.append(f"safe_confidence_not_high source_id={sid}")
        if is_prohibited_url(row["proposed_url_listado"]) or is_prohibited_url(row["website_url_db"]):
            errors.append(f"safe_prohibited source_id={sid}")
    return errors


def write_docs(out: Path, rows: List[Dict[str, Any]], spot: List[Dict[str, Any]], validation: List[str]) -> None:
    safe = [r for r in rows if r["final_classification"] == "final_safe_update"]
    db_mismatch = [r for r in rows if r["final_classification"] == "blocked_by_db_mismatch"]
    safety = [r for r in rows if r["final_classification"] == "blocked_by_safety"]
    manual = [r for r in rows if r["final_classification"] == "needs_manual_review"]
    top = sorted(safe, key=lambda r: (to_int(r["estimated_property_yield"]), to_int(r["score"])), reverse=True)[:20]
    spot_counts = Counter("ok" if r["spotcheck_ok"] else "fail" for r in spot)
    spot_fail = [r for r in spot if not r["spotcheck_ok"]]

    summary = f"""# PR-BE-URL-06c — DB preflight real + validación final

_Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}_

## Resultado
- Total Tier A inicial: **{len(rows)}**
- Final Safe Update: **{len(safe)}**
- Blocked by DB mismatch: **{len(db_mismatch)}**
- Blocked by safety: **{len(safety)}**
- Needs manual review: **{len(manual)}**
- HTTP spotcheck: **{len(spot)}** URLs; OK={spot_counts['ok']} FAIL={spot_counts['fail']}
- DB writes: **0**
- UPDATE ejecutados: **0**
- Publish/scraping productivo/runs/push/deploy/frontend: **0**

## Top 20 Final Safe Update por impacto
{md_table(top, ['source_id', 'source_name', 'current_url_listado_db', 'proposed_url_listado', 'score', 'property_links_count', 'estimated_property_yield'], 20)}

## Spotcheck fallidos o dudosos
{md_table(spot_fail, ['source_id', 'source_name', 'sample_group', 'http_status', 'error', 'redirects_home', 'links_count_light', 'card_hints_light', 'spotcheck_ok'], 30)}

## Recomendación
Conviene pedir autorización para UPDATE real **solo si** se acepta el riesgo residual del spotcheck y se limita la ejecución al archivo `final_safe_update_candidates.csv`. Si se quiere máxima prudencia, excluir previamente los spotcheck fallidos/dudosos y regenerar un set final aún más chico.
"""
    (out / "db_preflight_summary.md").write_text(summary, encoding="utf-8")

    report = f"""# DB validation report

## Validaciones obligatorias
{md_table([{'validation': e} for e in validation] if validation else [{'validation': 'OK - no blocking validation errors'}], ['validation'], 100)}

## Clasificación
- final_safe_update: {len(safe)}
- blocked_by_db_mismatch: {len(db_mismatch)}
- blocked_by_safety: {len(safety)}
- needs_manual_review: {len(manual)}
"""
    (out / "db_validation_report.md").write_text(report, encoding="utf-8")

    spot_md = f"""# HTTP spotcheck report

Spotcheck liviano sobre top 50 por impacto + 50 aleatorias de Final Safe Update.

- Total evaluadas: {len(spot)}
- OK: {spot_counts['ok']}
- Fail/dudosas: {spot_counts['fail']}

## Fail/dudosas
{md_table(spot_fail, ['source_id', 'source_name', 'proposed_url_listado', 'sample_group', 'http_status', 'error', 'redirects_home', 'is_prohibited', 'has_operation_signal', 'has_property_type_signal', 'links_count_light', 'card_hints_light'], 100)}
"""
    (out / "http_spotcheck_report.md").write_text(spot_md, encoding="utf-8")

    (out / "risk_assessment.md").write_text(
        """# Risk assessment

## Riesgos restantes
- El preflight valida estado actual de DB, pero la DB puede cambiar antes del UPDATE real.
- El spotcheck HTTP es liviano; no reemplaza un scrape controlado posterior.
- Algunas URLs con query params pueden ser frágiles.
- Algunos sitios pueden devolver HTML diferente por región, rate limit o user-agent.
- Si se ejecuta más adelante, hacerlo con backup y transacción.
""",
        encoding="utf-8",
    )
    (out / "next_step_recommendation.md").write_text(
        """# Next step recommendation

No ejecutar UPDATE todavía.

Recomendación:
1. Revisar `final_safe_update_candidates.csv`.
2. Revisar `http_spotcheck_report.md`.
3. Si se acepta el riesgo, pedir autorización explícita para una fase PR-BE-URL-06d de UPDATE real.
4. En esa fase, ejecutar solo `final_update_preview.sql` revisado, con backup previo y conteo de filas afectadas.
5. Luego correr validación controlada sobre las fuentes actualizadas.
""",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only DB preflight for url_listado Tier A candidates")
    parser.add_argument("--input-tier-a", required=True)
    parser.add_argument("--input-diff", required=True)
    parser.add_argument("--input-preview-sql", required=True)
    parser.add_argument("--input-summary", required=True)
    parser.add_argument("--input-best", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--http-timeout", type=float, default=8.0)
    parser.add_argument("--skip-http", action="store_true")
    parser.add_argument("--commit", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.commit:
        raise SystemExit("--commit is not authorized in PR-BE-URL-06c")

    tier_a = read_csv(Path(args.input_tier_a))
    read_csv(Path(args.input_diff))
    Path(args.input_preview_sql).read_text(encoding="utf-8", errors="ignore")
    Path(args.input_summary).read_text(encoding="utf-8", errors="ignore")
    read_csv(Path(args.input_best))

    base_url, key = supabase_config()
    source_ids = [to_int(row["source_id"]) for row in tier_a]
    db_by_id = fetch_db_rows(base_url, key, source_ids)

    classified = [classify_row(row, db_by_id.get(clean(row.get("source_id")), [])) for row in tier_a]
    safe = [r for r in classified if r["final_classification"] == "final_safe_update"]
    db_mismatch = [r for r in classified if r["final_classification"] == "blocked_by_db_mismatch"]
    safety = [r for r in classified if r["final_classification"] == "blocked_by_safety"]
    manual = [r for r in classified if r["final_classification"] == "needs_manual_review"]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    update_text = update_sql(safe)
    rollback_text = rollback_sql(safe)
    (out / "final_update_preview.sql").write_text(update_text, encoding="utf-8")
    (out / "final_rollback_preview.sql").write_text(rollback_text, encoding="utf-8")

    validation = validate_outputs(safe, classified, update_text, rollback_text)

    spot = [] if args.skip_http else http_spotcheck(safe, out, args.http_timeout)

    write_csv(out / "final_safe_update_candidates.csv", safe, OUTPUT_FIELDS)
    write_csv(out / "blocked_by_db_mismatch.csv", db_mismatch, OUTPUT_FIELDS)
    write_csv(out / "blocked_by_safety.csv", safety, OUTPUT_FIELDS)
    write_csv(out / "needs_manual_review.csv", manual, OUTPUT_FIELDS)
    write_csv(out / "final_url_listado_diff.csv", classified, OUTPUT_FIELDS)
    write_csv_generic(out / "http_spotcheck.csv", spot)
    write_docs(out, classified, spot, validation)

    print(f"tier_a_initial={len(tier_a)}")
    print(f"final_safe_update={len(safe)}")
    print(f"blocked_by_db_mismatch={len(db_mismatch)}")
    print(f"blocked_by_safety={len(safety)}")
    print(f"needs_manual_review={len(manual)}")
    print(f"http_spotcheck_total={len(spot)}")
    print(f"http_spotcheck_ok={sum(1 for r in spot if r.get('spotcheck_ok'))}")
    print(f"http_spotcheck_fail={sum(1 for r in spot if not r.get('spotcheck_ok'))}")
    print(f"validation_errors={len(validation)}")
    print(f"out={out}")
    print("db_writes=0")
    print("updates=0")
    print("publish=0")
    print("scraping_productivo=0")
    print("runs=0")
    print("push_deploy_frontend=0")


if __name__ == "__main__":
    main()
