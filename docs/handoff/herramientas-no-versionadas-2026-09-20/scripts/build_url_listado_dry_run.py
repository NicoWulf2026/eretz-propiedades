#!/usr/bin/env python
"""Build a conservative url_listado DB dry-run proposal.

PR-BE-URL-06b is intentionally read-only:
- consumes local CSV proposal files
- writes local reports under _scratch/
- generates SQL preview only
- never connects to DB and never executes UPDATE
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.parse
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


OUTPUT_FIELDS = [
    "source_id",
    "source_name",
    "website_url",
    "current_url_listado",
    "proposed_url_listado",
    "tier",
    "confidence",
    "score",
    "property_links_count",
    "evidence",
    "detected_from",
    "estimated_property_yield",
    "risk",
    "recommended_action",
    "sql_preview",
]


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


def to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or str(value).strip() == "":
            return default
        return int(float(str(value).strip()))
    except Exception:
        return default


def is_true(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "t", "yes", "y", "si", "sí"}


def clean(value: Any) -> str:
    return str(value or "").strip()


def normalize_url(value: str) -> str:
    raw = clean(value)
    if not raw:
        return ""
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw
    try:
        p = urllib.parse.urlsplit(raw)
    except Exception:
        return raw.strip().lower()
    path = (p.path or "/").rstrip("/") or "/"
    query = p.query
    return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), path, query, ""))


def host_of(url: str) -> str:
    try:
        return urllib.parse.urlsplit(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def is_homepage_url(candidate: str, website: str) -> bool:
    c = normalize_url(candidate)
    w = normalize_url(website)
    if not c or not w:
        return False
    if host_of(c) != host_of(w):
        return False
    try:
        cp = urllib.parse.urlsplit(c)
    except Exception:
        return False
    return (cp.path or "/") in {"", "/"} and not cp.query


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
    # Detail slugs commonly include a property type + operation + numeric id.
    has_type = re.search(r"(casa|departamento|depto|terreno|lote|local|oficina|ph|duplex|galpon)", last)
    has_operation = re.search(r"(venta|alquiler|renta)", last)
    has_id = re.search(r"(^|[-_])(?:p|id)?\d{3,}($|[-_])", last) or re.search(r"\d{5,}", last)
    if has_type and has_operation and has_id:
        return True
    singular_type = r"(casa|departamento|depto|terreno|lote|local|oficina|ph|duplex|galpon)"
    if re.search(rf"^(venta|alquiler|renta)-{singular_type}-.+", last):
        return True
    if re.search(rf"^{singular_type}-(en-)?(venta|alquiler|renta)-.+", last):
        return True
    if re.search(r"(propiedad|inmueble|property)[-/][^/?]*\d{3,}", path):
        return True
    return False


def sql_quote(value: str) -> str:
    return "'" + clean(value).replace("'", "''") + "'"


def make_sql(row: Dict[str, Any]) -> str:
    source_id = to_int(row.get("source_id"))
    proposed = clean(row.get("proposed_url_listado"))
    current = clean(row.get("current_url_listado"))
    return (
        "UPDATE public.inmobiliarias_main\n"
        f"SET url_listado = {sql_quote(proposed)}\n"
        f"WHERE id = {source_id}\n"
        f"  AND COALESCE(url_listado, '') = {sql_quote(current)};"
    )


def has_strong_evidence(row: Dict[str, str]) -> bool:
    evidence = clean(row.get("evidence")).lower()
    property_links = to_int(row.get("property_links_count"))
    has_property_links = property_links >= 3 and "property_links" in evidence
    has_operation = is_true(row.get("has_operation_signals")) or "operation_terms" in evidence
    has_type = is_true(row.get("has_property_type_signals")) or "type_terms" in evidence
    has_price_or_pagination = (
        is_true(row.get("has_price_signals"))
        or is_true(row.get("has_pagination"))
        or "price_signals" in evidence
        or "pagination" in evidence
    )
    return has_property_links and has_operation and has_type and has_price_or_pagination


def is_tier_a(row: Dict[str, str]) -> bool:
    proposed = clean(row.get("proposed_listing_url"))
    website = clean(row.get("website_url"))
    current = clean(row.get("current_listing_url"))
    return (
        clean(row.get("confidence")).lower() == "high"
        and to_int(row.get("score")) >= 90
        and to_int(row.get("property_links_count")) >= 3
        and not is_true(row.get("is_homepage"))
        and not is_true(row.get("is_property_detail"))
        and not looks_like_detail_url(proposed)
        and not is_true(row.get("is_prohibited"))
        and proposed != ""
        and normalize_url(proposed) != normalize_url(website)
        and normalize_url(proposed) != normalize_url(current)
        and not is_homepage_url(proposed, website)
        and clean(row.get("http_status")) == "200"
        and has_strong_evidence(row)
        and clean(row.get("final_category")) == "found_high_confidence"
    )


def is_tier_b(row: Dict[str, str]) -> bool:
    confidence = clean(row.get("confidence")).lower()
    final_category = clean(row.get("final_category"))
    score = to_int(row.get("score"))
    links = to_int(row.get("property_links_count"))
    proposed = clean(row.get("proposed_listing_url"))
    if (
        is_true(row.get("is_prohibited"))
        or is_true(row.get("is_homepage"))
        or is_true(row.get("is_property_detail"))
        or looks_like_detail_url(clean(row.get("proposed_listing_url")))
    ):
        return False
    if not proposed:
        return False
    if confidence == "high" and links < 3 and final_category == "found_high_confidence":
        return True
    if confidence == "medium" and final_category == "found_medium_confidence":
        return True
    if is_true(row.get("requires_playwright")):
        return True
    has_some_signals = (
        links > 0
        or is_true(row.get("has_operation_signals"))
        or is_true(row.get("has_property_type_signals"))
        or is_true(row.get("has_price_signals"))
        or is_true(row.get("has_pagination"))
    )
    if proposed and has_some_signals and score >= 50 and final_category in {
        "found_high_confidence",
        "found_medium_confidence",
        "requires_playwright_to_confirm",
    }:
        return True
    return False


def classify(row: Dict[str, str]) -> str:
    if is_tier_a(row):
        return "A"
    if is_tier_b(row):
        return "B"
    return "C"


def recommended_action_for_tier(tier: str) -> str:
    if tier == "A":
        return "future_auto_update_candidate_after_authorization"
    if tier == "B":
        return "manual_review_or_playwright_confirmation"
    return "no_update"


def map_row(row: Dict[str, str], tier: str) -> Dict[str, Any]:
    out = {
        "source_id": clean(row.get("source_id")),
        "source_name": clean(row.get("source_name")),
        "website_url": clean(row.get("website_url")),
        "current_url_listado": clean(row.get("current_listing_url")),
        "proposed_url_listado": clean(row.get("proposed_listing_url")),
        "tier": tier,
        "confidence": clean(row.get("confidence")),
        "score": to_int(row.get("score")),
        "property_links_count": to_int(row.get("property_links_count")),
        "evidence": clean(row.get("evidence")),
        "detected_from": clean(row.get("detected_from")),
        "estimated_property_yield": to_int(row.get("estimated_property_yield")),
        "risk": clean(row.get("risk")),
        "recommended_action": recommended_action_for_tier(tier),
        "sql_preview": "",
        "_raw": row,
    }
    if tier == "A":
        out["sql_preview"] = make_sql(out)
    return out


def table(rows: Sequence[Dict[str, Any]], fields: Sequence[str], limit: int = 20) -> str:
    subset = list(rows)[:limit]
    if not subset:
        return "_Sin filas._\n"
    lines = ["| " + " | ".join(fields) + " |", "| " + " | ".join(["---"] * len(fields)) + " |"]
    for row in subset:
        vals = []
        for field in fields:
            value = str(row.get(field, ""))
            value = value.replace("|", "\\|").replace("\n", " ")
            if len(value) > 90:
                value = value[:87] + "..."
            vals.append(value)
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines) + "\n"


def validate(tier_a: List[Dict[str, Any]], all_rows: List[Dict[str, Any]], sql_text: str) -> List[str]:
    errors: List[str] = []
    raw_by_id = {row["source_id"]: row.get("_raw", {}) for row in all_rows}
    seen = Counter(row["source_id"] for row in all_rows)
    dupes = [sid for sid, count in seen.items() if count > 1]
    if dupes:
        errors.append(f"duplicated_source_id={len(dupes)}")
    for row in tier_a:
        raw = raw_by_id.get(row["source_id"], {})
        prefix = f"source_id={row['source_id']}"
        if is_true(raw.get("is_prohibited")):
            errors.append(f"tier_a_prohibited {prefix}")
        if is_true(raw.get("is_homepage")) or is_homepage_url(row["proposed_url_listado"], row["website_url"]):
            errors.append(f"tier_a_home {prefix}")
        if is_true(raw.get("is_property_detail")):
            errors.append(f"tier_a_detail {prefix}")
        if looks_like_detail_url(row["proposed_url_listado"]):
            errors.append(f"tier_a_detail_heuristic {prefix}")
        if row["property_links_count"] < 3:
            errors.append(f"tier_a_links_lt_3 {prefix}")
        if clean(raw.get("http_status")) != "200":
            errors.append(f"tier_a_http_not_200 {prefix}")
        if not row["proposed_url_listado"]:
            errors.append(f"tier_a_empty_proposed_url {prefix}")
        if normalize_url(row["proposed_url_listado"]) == normalize_url(row["website_url"]):
            errors.append(f"tier_a_proposed_equals_website {prefix}")
    set_lines = [line.strip().lower() for line in sql_text.splitlines() if line.strip().lower().startswith("set ")]
    bad_set = [line for line in set_lines if not re.fullmatch(r"set\s+url_listado\s*=.+", line)]
    if bad_set:
        errors.append("sql_preview_sets_unexpected_column")
    forbidden_column_patterns = [
        "cms_detectado",
        "estrategia_scraping",
        "diagnostic_status",
        "scraping_readiness",
        "exclude_from_scraping",
        "sitio_activo",
        r"\bactiva\b",
    ]
    lower_sql = sql_text.lower()
    for token in forbidden_column_patterns:
        if re.search(token, lower_sql):
            errors.append(f"sql_preview_forbidden_token={token}")
    forbidden_tables = ["publish_queue", "propiedades_staging", "propiedades_raw", "public.propiedades"]
    for token in forbidden_tables:
        if token in lower_sql:
            errors.append(f"sql_preview_forbidden_token={token}")
    return errors


def write_sql(path: Path, tier_a: Sequence[Dict[str, Any]]) -> str:
    lines = [
        "-- DRY RUN ONLY",
        "-- DO NOT EXECUTE WITHOUT EXPLICIT AUTHORIZATION",
        "-- PR-BE-URL-06b: preview only for Tier A url_listado candidates",
        "-- No DB writes were executed by this generator.",
        "",
        "BEGIN;",
        "",
    ]
    for row in tier_a:
        lines.append(f"-- source_id={row['source_id']} source_name={row['source_name']}")
        lines.append(make_sql(row))
        lines.append("")
    lines.extend(["ROLLBACK;", ""])
    sql_text = "\n".join(lines)
    path.write_text(sql_text, encoding="utf-8")
    return sql_text


def write_docs(
    out: Path,
    original_count: int,
    tier_a: List[Dict[str, Any]],
    tier_b: List[Dict[str, Any]],
    tier_c: List[Dict[str, Any]],
    validation_errors: List[str],
) -> None:
    top_a = sorted(tier_a, key=lambda r: (to_int(r["estimated_property_yield"]), to_int(r["score"])), reverse=True)
    top_b = sorted(tier_b, key=lambda r: (to_int(r["estimated_property_yield"]), to_int(r["score"])), reverse=True)
    summary = f"""# PR-BE-URL-06b — Safe set + DB dry-run de url_listado

_Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}_

## Resultado
- Total propuestas originales: **{original_count}**
- Tier A — update automático futuro: **{len(tier_a)}**
- Tier B — revisión manual: **{len(tier_b)}**
- Tier C — no update: **{len(tier_c)}**
- SQL preview generado: `url_update_preview.sql`
- DB writes ejecutados: **0**
- Publish/scraping productivo/runs/push/deploy/frontend: **0**

## Recomendación
Sí: si luego se autoriza una fase real, recomendaría UPDATE futuro **solo para Tier A**, después de revisar manualmente el top 20/50 por impacto y correr un dry-run DB separado.

## Top 20 Tier A por impacto
{table(top_a, ['source_id', 'source_name', 'current_url_listado', 'proposed_url_listado', 'score', 'property_links_count', 'estimated_property_yield', 'evidence'], 20)}

## Top 20 Tier B por impacto
{table(top_b, ['source_id', 'source_name', 'current_url_listado', 'proposed_url_listado', 'confidence', 'score', 'property_links_count', 'estimated_property_yield', 'evidence'], 20)}

## Riesgos
- Tier A sigue siendo heurístico: hay que validar muestra manual antes de UPDATE real.
- Sitios custom pueden inflar señales por textos comunes, aunque se exigieron links de propiedad.
- URLs con query params pueden ser correctas pero frágiles si el sitio cambia.
- Algunos medium/high con `property_links_count < 3` quedaron en Tier B por prudencia.

## Validaciones
{table([{'validation': e} for e in validation_errors] if validation_errors else [{'validation': 'OK - no blocking validation errors'}], ['validation'], 50)}
"""
    (out / "url_update_dry_run_summary.md").write_text(summary, encoding="utf-8")

    validation = f"""# Validation report

## Checks
- Tier A no tiene prohibidas.
- Tier A no tiene home.
- Tier A no tiene ficha individual.
- Tier A no tiene `property_links_count < 3`.
- Tier A no tiene `http_status != 200`.
- Tier A no tiene proposed URL vacía.
- Tier A no tiene proposed URL igual a website_url.
- No hay duplicados por `source_id`.
- SQL preview solo usa `SET url_listado = ...`.
- SQL preview no toca columnas prohibidas.
- No hubo DB writes, publish, scraping productivo, push, deploy ni frontend.

## Resultado
{table([{'validation': e} for e in validation_errors] if validation_errors else [{'validation': 'OK'}], ['validation'], 100)}
"""
    (out / "validation_report.md").write_text(validation, encoding="utf-8")

    rollback = """# Rollback plan

No se ejecutó ningún UPDATE en esta fase.

Si más adelante se autoriza un UPDATE real:
1. Exportar backup previo de `id`, `nombre`, `web`, `url_listado`.
2. Guardar el CSV exacto de Tier A usado para la actualización.
3. Ejecutar primero SELECT/diff en DB, sin UPDATE.
4. Si se autoriza UPDATE real, hacerlo en transacción y registrar cantidad afectada.
5. Rollback lógico: restaurar `url_listado` desde el backup por `id`.
6. Validar con corrida controlada de cobertura solo sobre fuentes actualizadas.
"""
    (out / "rollback_plan.md").write_text(rollback, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build conservative url_listado dry-run reports")
    parser.add_argument("--input-best", required=True)
    parser.add_argument("--input-high", required=True)
    parser.add_argument("--input-medium", required=True)
    parser.add_argument("--input-top-impact", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--commit", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.commit:
        raise SystemExit("--commit is not authorized in PR-BE-URL-06b")

    # Inputs are intentionally loaded to make missing-file failures explicit.
    best = read_csv(Path(args.input_best))
    read_csv(Path(args.input_high))
    read_csv(Path(args.input_medium))
    read_csv(Path(args.input_top_impact))

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    mapped: List[Dict[str, Any]] = []
    for row in best:
        tier = classify(row)
        mapped.append(map_row(row, tier))

    tier_a = [r for r in mapped if r["tier"] == "A"]
    tier_b = [r for r in mapped if r["tier"] == "B"]
    tier_c = [r for r in mapped if r["tier"] == "C"]
    top_a = sorted(tier_a, key=lambda r: (to_int(r["estimated_property_yield"]), to_int(r["score"])), reverse=True)
    top_b = sorted(tier_b, key=lambda r: (to_int(r["estimated_property_yield"]), to_int(r["score"])), reverse=True)

    sql_text = write_sql(out / "url_update_preview.sql", tier_a)
    validation_errors = validate(tier_a, mapped, sql_text)

    clean_rows = [{k: v for k, v in row.items() if not k.startswith("_")} for row in mapped]
    write_csv(out / "url_listado_diff.csv", clean_rows, OUTPUT_FIELDS)
    write_csv(out / "tier_a_auto_update_candidates.csv", [{k: v for k, v in row.items() if not k.startswith("_")} for row in tier_a], OUTPUT_FIELDS)
    write_csv(out / "tier_b_manual_review.csv", [{k: v for k, v in row.items() if not k.startswith("_")} for row in tier_b], OUTPUT_FIELDS)
    write_csv(out / "tier_c_no_update.csv", [{k: v for k, v in row.items() if not k.startswith("_")} for row in tier_c], OUTPUT_FIELDS)
    write_csv(out / "top_tier_a_by_impact.csv", [{k: v for k, v in row.items() if not k.startswith("_")} for row in top_a[:50]], OUTPUT_FIELDS)
    write_csv(out / "top_tier_b_by_impact.csv", [{k: v for k, v in row.items() if not k.startswith("_")} for row in top_b[:50]], OUTPUT_FIELDS)
    write_docs(out, len(best), tier_a, tier_b, tier_c, validation_errors)

    print(f"original_total={len(best)}")
    print(f"tier_a={len(tier_a)}")
    print(f"tier_b={len(tier_b)}")
    print(f"tier_c={len(tier_c)}")
    print(f"validation_errors={len(validation_errors)}")
    print(f"sql_preview={out / 'url_update_preview.sql'}")
    print("db_writes=0")
    print("publish=0")
    print("scraping_productivo=0")
    print("push_deploy_frontend=0")


if __name__ == "__main__":
    main()
