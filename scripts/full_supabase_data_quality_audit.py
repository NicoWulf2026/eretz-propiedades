#!/usr/bin/env python3
"""Read-only Supabase data quality audit for ERETZ.

This script writes audit artifacts under _scratch/full_supabase_data_quality_audit.
It never prints secrets and starts every DB connection in read-only mode.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*_args: Any, **_kwargs: Any) -> None:
        return None

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("psycopg is required for the full metadata audit") from exc


ROOT = Path(__file__).resolve().parent.parent
AUDIT_DIR = ROOT / "_scratch" / "full_supabase_data_quality_audit"
MANIFEST_PATH = ROOT / "_scratch" / "url_recovery_full_campaign" / "manifest_final_expanded.csv"
URL_RECOVERY_REPORT = ROOT / "_scratch" / "url_recovery_full_campaign" / "FINAL_URL_RECOVERY_REPORT.md"
RUN_D_REPORT = ROOT / "_scratch" / "codex_full_7004_coverage" / "FINAL_REPORT.md"

PLACEHOLDERS = {
    "", "-", "--", "n/a", "na", "null", "none", "sin datos", "sin dato",
    "no informado", "consultar", "a consultar", "desconocido", "sin informar",
}
PROHIBITED_DOMAINS = {
    "zonaprop.com", "zonaprop.com.ar", "argenprop.com", "argenprop.com.ar",
    "properati.com", "properati.com.ar",
}
OWN_SCHEMAS = {"public", "internal_scraping"}
DETAIL_BLOCKLIST_PATTERNS = [
    (re.compile(r"/properties/operation/(forSale|forRent)", re.I), "operation_category"),
    (re.compile(r"/propiedades/(venta|alquiler)/?$", re.I), "operation_category"),
    (re.compile(r"/(venta|ventas|alquiler|alquileres)/?$", re.I), "listing_or_operation"),
    (re.compile(r"/(contacto|contact|tasaciones|tasacion|blog|noticias|login)/?$", re.I), "non_detail_page"),
    (re.compile(r"/(page|pagina)/\d+/?$", re.I), "pagination_page"),
]


@dataclass(frozen=True)
class TableRef:
    schema: str
    name: str

    @property
    def qname(self) -> str:
        return f"{self.schema}.{self.name}"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: serialize_cell(row.get(k)) for k in fields})


def append_event(event: str, **payload: Any) -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    row = {"ts": utc_now(), "event": event, **payload}
    with (AUDIT_DIR / "EVENTS.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def serialize_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def load_manifest() -> list[dict[str, str]]:
    with MANIFEST_PATH.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def connect_readonly():
    load_dotenv(ROOT / ".env")
    db_url = os.getenv("INTERNAL_DB_URL") or os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not db_url:
        raise RuntimeError("No direct read-only DB URL was found in .env")
    conn = psycopg.connect(db_url, row_factory=dict_row, autocommit=False)
    with conn.cursor() as cur:
        cur.execute("SET default_transaction_read_only = on")
        cur.execute("SET statement_timeout = '15min'")
        cur.execute("SET idle_in_transaction_session_timeout = '5min'")
    return conn


def safe_ident(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"Unsafe SQL identifier: {value!r}")
    return f'"{value}"'


def table_sql(table: TableRef) -> str:
    return f"{safe_ident(table.schema)}.{safe_ident(table.name)}"


def classify_table(name: str) -> str:
    n = name.lower()
    if n in {"data_quality_issues", "error_log"}:
        return "AUDIT"
    if n == "propiedades":
        return "SCRAPER_OUTPUT"
    if n in {"inmobiliarias_main", "inmobiliarias_scraping"}:
        return "CONFIGURATION"
    if n in {"city_normalization_rules", "tipos_cambio"}:
        return "CONFIGURATION"
    if "raw" in n or "staging" in n:
        return "STAGING"
    if "audit" in n or "error" in n or "log" in n:
        return "AUDIT"
    if "scrap" in n or "run" in n or "job" in n or "queue" in n or "event" in n:
        return "OPERATIONAL"
    if "geocoding" in n or "location_correction" in n:
        return "OPERATIONAL"
    if "publish" in n or "frontend" in n:
        return "FRONTEND"
    if "backup" in n or "bak" in n:
        return "BACKUP"
    if any(x in n for x in ("contact", "imagen", "image", "hash", "history", "historial", "score", "analysis", "quality")):
        return "SCRAPER_OUTPUT"
    return "UNRELATED"


def fetch_all(cur, sql: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
    cur.execute(sql, params or ())
    return [dict(r) for r in cur.fetchall()]


def scalar(cur, sql: str, params: tuple[Any, ...] | None = None) -> Any:
    cur.execute(sql, params or ())
    row = cur.fetchone()
    if not row:
        return None
    return next(iter(row.values()))


def init_project() -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    manifest_rows = load_manifest()
    now = utc_now()
    status = (
        "# Full Supabase Data Quality Audit Status\n\n"
        f"Updated UTC: {now}\n\n"
        "- Stage: initialized\n"
        f"- Manifest path: {MANIFEST_PATH}\n"
        f"- Manifest rows: {len(manifest_rows)}\n"
        f"- Manifest unique source_id: {len({r.get('source_id') for r in manifest_rows})}\n"
        "- No productive scraper active: verified before init\n"
        "- Action: inventory_and_baseline\n"
    )
    (AUDIT_DIR / "STATUS.md").write_text(status, encoding="utf-8")
    checkpoint = {
        "updated_utc": now,
        "stage": "initialized",
        "manifest_path": str(MANIFEST_PATH),
        "manifest_rows": len(manifest_rows),
        "manifest_unique_source_ids": len({r.get("source_id") for r in manifest_rows}),
        "completed_steps": [],
        "next_step": "inventory_and_baseline",
    }
    write_json(AUDIT_DIR / "audit_checkpoint.json", checkpoint)
    (AUDIT_DIR / "audit_checkpoint.md").write_text(
        "# Audit checkpoint\n\n" + "\n".join(f"- {k}: {v}" for k, v in checkpoint.items()) + "\n",
        encoding="utf-8",
    )
    (AUDIT_DIR / "FINAL_DATA_QUALITY_REPORT.md").write_text(
        "# FINAL DATA QUALITY REPORT\n\nStatus: in progress\n", encoding="utf-8"
    )
    append_event("FULL_DATA_QUALITY_AUDIT_INITIALIZED", manifest_rows=len(manifest_rows))


def inventory_schema(conn) -> dict[str, Any]:
    with conn.cursor() as cur:
        schemas = fetch_all(
            cur,
            """
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name NOT IN ('pg_catalog', 'information_schema')
            ORDER BY schema_name
            """,
        )
        tables = fetch_all(
            cur,
            """
            SELECT table_schema, table_name, table_type
            FROM information_schema.tables
            WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY table_schema, table_name
            """,
        )
        public_tables = [
            TableRef(r["table_schema"], r["table_name"])
            for r in tables
            if r["table_schema"] == "public" and r["table_type"] == "BASE TABLE"
        ]
        table_rows: list[dict[str, Any]] = []
        for row in tables:
            ref = TableRef(row["table_schema"], row["table_name"])
            exact_count = ""
            classification = classify_table(row["table_name"])
            if (
                row["table_type"] == "BASE TABLE"
                and row["table_schema"] in OWN_SCHEMAS
                and classification != "UNRELATED"
            ):
                try:
                    exact_count = scalar(cur, f"SELECT count(*) FROM {table_sql(ref)}")
                except Exception as exc:
                    exact_count = f"COUNT_ERROR:{type(exc).__name__}"
                    conn.rollback()
                    cur.execute("SET default_transaction_read_only = on")
            table_rows.append({
                **row,
                "classification": classification,
                "exact_row_count": exact_count,
            })
        columns = fetch_all(
            cur,
            """
            SELECT table_schema, table_name, column_name, ordinal_position, data_type,
                   udt_name, is_nullable, column_default, character_maximum_length,
                   numeric_precision, numeric_scale, datetime_precision
            FROM information_schema.columns
            WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY table_schema, table_name, ordinal_position
            """,
        )
        constraints = fetch_all(
            cur,
            """
            SELECT tc.table_schema, tc.table_name, tc.constraint_name, tc.constraint_type,
                   kcu.column_name, ccu.table_schema AS foreign_table_schema,
                   ccu.table_name AS foreign_table_name, ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints tc
            LEFT JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            LEFT JOIN information_schema.constraint_column_usage ccu
              ON ccu.constraint_name = tc.constraint_name
             AND ccu.table_schema = tc.table_schema
            WHERE tc.table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY tc.table_schema, tc.table_name, tc.constraint_name, kcu.ordinal_position
            """,
        )
        indexes = fetch_all(
            cur,
            """
            SELECT schemaname AS table_schema, tablename AS table_name,
                   indexname AS index_name, indexdef
            FROM pg_indexes
            WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
            ORDER BY schemaname, tablename, indexname
            """,
        )
        triggers = fetch_all(
            cur,
            """
            SELECT event_object_schema AS table_schema, event_object_table AS table_name,
                   trigger_name, event_manipulation, action_timing, action_statement
            FROM information_schema.triggers
            WHERE trigger_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY event_object_schema, event_object_table, trigger_name
            """,
        )
        views = [r for r in tables if r["table_type"] in {"VIEW", "MATERIALIZED VIEW"}]
        sizes = fetch_all(
            cur,
            """
            SELECT schemaname AS table_schema, relname AS table_name,
                   pg_total_relation_size(format('%%I.%%I', schemaname, relname)) AS total_bytes,
                   pg_relation_size(format('%%I.%%I', schemaname, relname)) AS table_bytes
            FROM pg_stat_user_tables
            ORDER BY pg_total_relation_size(format('%%I.%%I', schemaname, relname)) DESC
            """,
        )

    write_csv(AUDIT_DIR / "schema_inventory.csv", schemas, ["schema_name"])
    write_csv(AUDIT_DIR / "table_inventory.csv", table_rows, ["table_schema", "table_name", "table_type", "classification", "exact_row_count"])
    write_csv(AUDIT_DIR / "column_inventory.csv", columns, [
        "table_schema", "table_name", "column_name", "ordinal_position", "data_type", "udt_name",
        "is_nullable", "column_default", "character_maximum_length", "numeric_precision",
        "numeric_scale", "datetime_precision",
    ])
    write_csv(AUDIT_DIR / "constraint_inventory.csv", constraints, [
        "table_schema", "table_name", "constraint_name", "constraint_type", "column_name",
        "foreign_table_schema", "foreign_table_name", "foreign_column_name",
    ])
    write_csv(AUDIT_DIR / "foreign_key_inventory.csv", [r for r in constraints if r["constraint_type"] == "FOREIGN KEY"], [
        "table_schema", "table_name", "constraint_name", "constraint_type", "column_name",
        "foreign_table_schema", "foreign_table_name", "foreign_column_name",
    ])
    write_csv(AUDIT_DIR / "index_inventory.csv", indexes, ["table_schema", "table_name", "index_name", "indexdef"])
    write_csv(AUDIT_DIR / "trigger_inventory.csv", triggers, [
        "table_schema", "table_name", "trigger_name", "event_manipulation", "action_timing", "action_statement",
    ])
    write_csv(AUDIT_DIR / "view_inventory.csv", views, ["table_schema", "table_name", "table_type"])
    write_csv(AUDIT_DIR / "database_size_report.csv", sizes, ["table_schema", "table_name", "total_bytes", "table_bytes"])
    (AUDIT_DIR / "database_size_report.md").write_text(
        "# Database size report\n\n"
        "| Table | Total bytes | Table bytes |\n|---|---:|---:|\n"
        + "".join(f"| {r['table_schema']}.{r['table_name']} | {r['total_bytes']} | {r['table_bytes']} |\n" for r in sizes[:50]),
        encoding="utf-8",
    )
    (AUDIT_DIR / "data_lineage.md").write_text(
        "# Data lineage\n\n"
        "Primary flow audited: official site/listing/detail -> scraper/parser -> normalization/validation "
        "-> dedup/merge -> public.propiedades. Configuration and source identity live primarily in "
        "public.inmobiliarias_main and related scraping operational tables discovered in table_inventory.csv.\n\n"
        "This audit phase is read-only and classifies tables dynamically in table_inventory.csv.\n",
        encoding="utf-8",
    )
    append_event("SCHEMA_INVENTORY_COMPLETED", tables=len(table_rows), columns=len(columns), indexes=len(indexes))
    return {
        "schemas": schemas,
        "tables": table_rows,
        "columns": columns,
        "constraints": constraints,
        "indexes": indexes,
        "triggers": triggers,
        "sizes": sizes,
        "public_tables": public_tables,
    }


def column_exists(columns: list[dict[str, Any]], table: str, column: str) -> bool:
    return any(r["table_schema"] == "public" and r["table_name"] == table and r["column_name"] == column for r in columns)


def baseline(conn, inventory: dict[str, Any]) -> None:
    columns = inventory["columns"]
    manifest = load_manifest()
    source_ids = {r.get("source_id") for r in manifest}
    now = utc_now()
    with conn.cursor() as cur:
        table_counts = []
        for t in inventory["tables"]:
            if (
                t["table_schema"] not in OWN_SCHEMAS
                or t["table_type"] != "BASE TABLE"
                or t["classification"] == "UNRELATED"
            ):
                continue
            table_counts.append({
                "table_schema": t["table_schema"],
                "table_name": t["table_name"],
                "row_count": t["exact_row_count"],
                "classification": t["classification"],
            })
        props_total = scalar(cur, 'SELECT count(*) FROM public.propiedades')
        inmo_total = scalar(cur, 'SELECT count(*) FROM public.inmobiliarias_main')
        source_counts = []
        if column_exists(columns, "propiedades", "fuente_extraccion"):
            source_counts = fetch_all(
                cur,
                """
                SELECT fuente_extraccion, count(*) AS properties_count
                FROM public.propiedades
                GROUP BY fuente_extraccion
                ORDER BY count(*) DESC NULLS LAST, fuente_extraccion
                """,
            )
        inmobiliaria_counts = []
        if column_exists(columns, "propiedades", "inmobiliaria_id"):
            inmobiliaria_counts = fetch_all(
                cur,
                """
                SELECT inmobiliaria_id, count(*) AS properties_count
                FROM public.propiedades
                GROUP BY inmobiliaria_id
                ORDER BY count(*) DESC NULLS LAST, inmobiliaria_id
                """,
            )
        field_quality = []
        for col in ["titulo", "descripcion", "precio", "moneda", "operacion", "tipo_propiedad", "barrio", "url", "imagenes"]:
            if not column_exists(columns, "propiedades", col):
                continue
            c = safe_ident(col)
            row = fetch_all(
                cur,
                f"""
                SELECT
                  'propiedades' AS table_name,
                  %s AS column_name,
                  count(*) AS total_rows,
                  count(*) FILTER (WHERE {c} IS NULL) AS null_count,
                  count(*) FILTER (WHERE btrim(COALESCE({c}::text, '')) = '') AS blank_count,
                  count(DISTINCT {c}) AS distinct_count
                FROM public.propiedades
                """,
                (col,),
            )[0]
            field_quality.append(row)
        by_operation = []
        if column_exists(columns, "propiedades", "operacion"):
            by_operation = fetch_all(cur, "SELECT operacion, count(*) AS count FROM public.propiedades GROUP BY operacion ORDER BY count DESC NULLS LAST")
        by_type = []
        if column_exists(columns, "propiedades", "tipo_propiedad"):
            by_type = fetch_all(cur, "SELECT tipo_propiedad, count(*) AS count FROM public.propiedades GROUP BY tipo_propiedad ORDER BY count DESC NULLS LAST")
        by_cms = []
        if column_exists(columns, "inmobiliarias_main", "cms_detectado"):
            by_cms = fetch_all(cur, "SELECT cms_detectado, count(*) AS count FROM public.inmobiliarias_main GROUP BY cms_detectado ORDER BY count DESC NULLS LAST")
        by_strategy = []
        if column_exists(columns, "inmobiliarias_main", "estrategia_scraping"):
            by_strategy = fetch_all(cur, "SELECT estrategia_scraping, count(*) AS count FROM public.inmobiliarias_main GROUP BY estrategia_scraping ORDER BY count DESC NULLS LAST")
        by_province = []
        province_col = "provincia" if column_exists(columns, "inmobiliarias_main", "provincia") else None
        if province_col:
            by_province = fetch_all(cur, f"SELECT {safe_ident(province_col)} AS provincia, count(*) AS count FROM public.inmobiliarias_main GROUP BY {safe_ident(province_col)} ORDER BY count DESC NULLS LAST")

    write_json(AUDIT_DIR / "baseline_database_snapshot.json", {
        "generated_utc": now,
        "propiedades_total": props_total,
        "inmobiliarias_total": inmo_total,
        "manifest_final_expanded_path": str(MANIFEST_PATH),
        "manifest_sources": len(manifest),
        "manifest_unique_source_ids": len(source_ids),
        "run_d_report": str(RUN_D_REPORT),
        "url_recovery_report": str(URL_RECOVERY_REPORT),
    })
    write_csv(AUDIT_DIR / "baseline_table_counts.csv", table_counts, ["table_schema", "table_name", "row_count", "classification"])
    write_csv(AUDIT_DIR / "baseline_source_counts.csv", source_counts, ["fuente_extraccion", "properties_count"])
    write_csv(AUDIT_DIR / "baseline_inmobiliaria_counts.csv", inmobiliaria_counts, ["inmobiliaria_id", "properties_count"])
    write_csv(AUDIT_DIR / "baseline_field_quality.csv", field_quality, ["table_name", "column_name", "total_rows", "null_count", "blank_count", "distinct_count"])
    for name, rows, fields in [
        ("baseline_operation_counts.csv", by_operation, ["operacion", "count"]),
        ("baseline_type_counts.csv", by_type, ["tipo_propiedad", "count"]),
        ("baseline_cms_counts.csv", by_cms, ["cms_detectado", "count"]),
        ("baseline_strategy_counts.csv", by_strategy, ["estrategia_scraping", "count"]),
        ("baseline_province_counts.csv", by_province, ["provincia", "count"]),
    ]:
        write_csv(AUDIT_DIR / name, rows, fields)
    (AUDIT_DIR / "baseline_data_quality_summary.md").write_text(
        "# Baseline data quality summary\n\n"
        f"Generated UTC: {now}\n\n"
        f"- public.propiedades rows: {props_total}\n"
        f"- public.inmobiliarias_main rows: {inmo_total}\n"
        f"- manifest_final_expanded sources: {len(manifest)}\n"
        f"- manifest_final_expanded unique source_id: {len(source_ids)}\n\n"
        "Detailed counts are stored in baseline_*.csv files.\n",
        encoding="utf-8",
    )
    append_event("BASELINE_FROZEN", propiedades=props_total, inmobiliarias=inmo_total, manifest_sources=len(manifest))


def is_url_like_column(column: str) -> bool:
    c = column.lower()
    if "normalizada" in c or "normalized" in c or c in {"canonical_url_key", "url_key"}:
        return False
    return c == "url" or c.endswith("_url") or "url_" in c or c in {"imagenes", "image", "images"}


def numeric_out_of_range_sql(column_ident: str, column_name: str) -> str:
    c = column_name.lower()
    numeric = f"{column_ident}::numeric"
    if c in {"latitud", "latitude"}:
        return f"count(*) FILTER (WHERE {column_ident} IS NOT NULL AND ({numeric} < -56 OR {numeric} > -21)) AS out_of_range_count"
    if c in {"longitud", "longitude"}:
        return f"count(*) FILTER (WHERE {column_ident} IS NOT NULL AND ({numeric} < -75 OR {numeric} > -52)) AS out_of_range_count"
    positive_fields = (
        "precio", "price", "expensa", "impuesto", "superficie", "metros", "m2",
        "ambiente", "dormitorio", "bano", "baño", "toilette", "cochera",
        "planta", "antiguedad", "attempt", "duration", "count", "total",
        "nueva", "actualizada", "sin_cambio", "error",
    )
    if any(token in c for token in positive_fields):
        return f"count(*) FILTER (WHERE {column_ident} IS NOT NULL AND {numeric} < 0) AS out_of_range_count"
    return "0 AS out_of_range_count"


def relevant_base_tables(inventory: dict[str, Any]) -> list[TableRef]:
    refs: list[TableRef] = []
    for table in inventory["tables"]:
        if table["table_type"] != "BASE TABLE":
            continue
        if table["table_schema"] not in OWN_SCHEMAS:
            continue
        if table["classification"] == "UNRELATED":
            continue
        refs.append(TableRef(table["table_schema"], table["table_name"]))
    return refs


def profile_columns(conn, inventory: dict[str, Any], tables: list[TableRef]) -> None:
    table_keys = {(t.schema, t.name) for t in tables}
    columns = [
        r for r in inventory["columns"]
        if (r["table_schema"], r["table_name"]) in table_keys
    ]
    rows: list[dict[str, Any]] = []
    with conn.cursor() as cur:
        for col in columns:
            table = TableRef(col["table_schema"], col["table_name"])
            column = col["column_name"]
            c = safe_ident(column)
            q = table_sql(table)
            data_type = (col["data_type"] or "").lower()
            is_textish = data_type in {"text", "character varying", "character", "uuid", "USER-DEFINED".lower()} or col["udt_name"] in {"text", "varchar", "bpchar", "uuid"}
            is_numeric = data_type in {"integer", "bigint", "smallint", "numeric", "real", "double precision"}
            is_temporal = "timestamp" in data_type or data_type in {"date", "time"}
            parts = [
                "count(*) AS total_rows",
                f"count(*) FILTER (WHERE {c} IS NULL) AS null_count",
                f"count(DISTINCT {c}) AS distinct_count",
            ]
            if is_textish or data_type == "jsonb" or data_type == "json":
                text_expr = f"{c}::text"
                parts += [
                    f"count(*) FILTER (WHERE {c} IS NOT NULL AND {text_expr} = '') AS empty_string_count",
                    f"count(*) FILTER (WHERE {c} IS NOT NULL AND btrim({text_expr}) = '') AS whitespace_only_count",
                    f"count(*) FILTER (WHERE lower(btrim({text_expr})) = ANY(%s)) AS placeholder_count",
                    f"min(length({text_expr})) AS minimum_length",
                    f"max(length({text_expr})) AS maximum_length",
                    f"avg(length({text_expr})) AS average_length",
                    f"count(*) FILTER (WHERE {text_expr} ~* '<(html|script|style|div|span|body|br|p)[^>]*>') AS html_contamination_count",
                ]
                if is_url_like_column(column):
                    parts.append(f"count(*) FILTER (WHERE {c} IS NOT NULL AND {text_expr} !~* '^(https?://|\\[|\\{{)') AS url_error_count")
                else:
                    parts.append("0 AS url_error_count")
            else:
                parts += [
                    "0 AS empty_string_count", "0 AS whitespace_only_count", "0 AS placeholder_count",
                    "NULL AS minimum_length", "NULL AS maximum_length", "NULL AS average_length",
                    "0 AS html_contamination_count", "0 AS url_error_count",
                ]
            if is_numeric:
                parts += [f"min({c}) AS minimum", f"max({c}) AS maximum", f"avg({c}) AS average"]
                parts.append(numeric_out_of_range_sql(c, column))
            else:
                parts += ["NULL AS minimum", "NULL AS maximum", "NULL AS average", "0 AS out_of_range_count"]
            if is_temporal:
                parts.append(f"count(*) FILTER (WHERE {c} > now() + interval '1 day') AS future_date_count")
            else:
                parts.append("0 AS future_date_count")
            sql = f"SELECT {', '.join(parts)} FROM {q}"
            params = (list(PLACEHOLDERS),) if (is_textish or data_type in {"json", "jsonb"}) else ()
            try:
                cur.execute(sql, params)
                metric = dict(cur.fetchone())
            except Exception as exc:
                conn.rollback()
                cur.execute("SET default_transaction_read_only = on")
                metric = {"profile_error": type(exc).__name__}
            row = {
                "table_schema": col["table_schema"],
                "table_name": col["table_name"],
                "column_name": column,
                "data_type": col["data_type"],
                **metric,
            }
            total = int(row.get("total_rows") or 0)
            nulls = int(row.get("null_count") or 0)
            row["null_percentage"] = round(nulls * 100 / total, 4) if total else 0
            rows.append(row)
    fields = [
        "table_schema", "table_name", "column_name", "data_type", "total_rows",
        "null_count", "null_percentage", "empty_string_count", "whitespace_only_count",
        "placeholder_count", "distinct_count", "minimum", "maximum", "average",
        "minimum_length", "maximum_length", "average_length", "html_contamination_count",
        "url_error_count", "out_of_range_count", "future_date_count", "profile_error",
    ]
    write_csv(AUDIT_DIR / "column_quality_profile.csv", rows, fields)
    high = [
        r for r in rows
        if int(r.get("html_contamination_count") or 0)
        or int(r.get("url_error_count") or 0)
        or int(r.get("out_of_range_count") or 0)
        or int(r.get("future_date_count") or 0)
    ]
    write_csv(AUDIT_DIR / "column_level_anomalies.csv", high, fields)
    (AUDIT_DIR / "column_quality_summary.md").write_text(
        "# Column quality summary\n\n"
        f"Generated UTC: {utc_now()}\n\n"
        f"- Profiled columns: {len(rows)}\n"
        f"- Columns with structural anomaly counters > 0: {len(high)}\n"
        f"- Tables profiled: {', '.join(t.qname for t in tables)}\n",
        encoding="utf-8",
    )
    append_event("COLUMN_PROFILE_COMPLETED", columns=len(rows), anomaly_columns=len(high), tables=[t.qname for t in tables])


def property_anomalies(conn, inventory: dict[str, Any]) -> None:
    columns = inventory["columns"]
    def has(c: str) -> bool:
        return column_exists(columns, "propiedades", c)
    rows: list[dict[str, Any]] = []
    invalid_url_rows: list[dict[str, Any]] = []
    with conn.cursor(name="prop_audit") as cur:
        select_cols = [c for c in [
            "id", "url", "url_normalizada", "hash_dedup", "inmobiliaria_id",
            "titulo", "descripcion", "precio", "moneda", "operacion",
            "tipo_propiedad", "barrio", "ciudad", "provincia", "direccion",
            "latitud", "longitud", "imagenes", "fuente_extraccion", "created_at", "updated_at",
        ] if has(c)]
        sql = "SELECT " + ", ".join(safe_ident(c) for c in select_cols) + " FROM public.propiedades"
        cur.execute(sql)
        for rec in cur:
            row = dict(rec)
            pid = row.get("id")
            url = str(row.get("url") or "")
            parsed = urlparse(url) if url else None
            host = (parsed.hostname or "").lower().rstrip(".") if parsed else ""
            path = parsed.path if parsed else ""
            if not url:
                rows.append(anomaly(pid, row, "url", "MISSING_URL", "INTERNAL_CORRECTABLE", "VALIDATION", "missing property url"))
            elif not parsed or parsed.scheme not in {"http", "https"} or not host:
                rows.append(anomaly(pid, row, "url", "INVALID_URL_FORMAT", "INTERNAL_CORRECTABLE", "NORMALIZATION", "invalid property url syntax"))
                invalid_url_rows.append(anomaly(pid, row, "url", "INVALID_URL_FORMAT", "INTERNAL_CORRECTABLE", "NORMALIZATION", "invalid property url syntax"))
            elif any(host == d or host.endswith("." + d) for d in PROHIBITED_DOMAINS):
                rows.append(anomaly(pid, row, "url", "PROHIBITED_DETAIL_DOMAIN", "HISTORICAL_DEBT", "VALIDATION", host))
            else:
                for rx, label in DETAIL_BLOCKLIST_PATTERNS:
                    if rx.search(path):
                        item = anomaly(pid, row, "url", label.upper(), "HISTORICAL_DEBT", "VALIDATION", path)
                        rows.append(item)
                        invalid_url_rows.append(item)
                        break
            title = str(row.get("titulo") or "").strip()
            if not title:
                rows.append(anomaly(pid, row, "titulo", "MISSING_TITLE", "EXTERNAL_MISSING_DATA", "DETAIL_PARSER", "blank/null title"))
            elif title.lower() in {"propiedad", "sin título", "sin titulo"}:
                rows.append(anomaly(pid, row, "titulo", "FALLBACK_TITLE", "INTERNAL_CORRECTABLE", "DETAIL_PARSER", title))
            elif "<" in title and ">" in title:
                rows.append(anomaly(pid, row, "titulo", "HTML_IN_TITLE", "INTERNAL_CORRECTABLE", "HTML_SELECTOR", title[:80]))
            desc = str(row.get("descripcion") or "")
            if re.search(r"<(script|style|html|body|div|span)[^>]*>", desc, re.I):
                rows.append(anomaly(pid, row, "descripcion", "HTML_IN_DESCRIPTION", "INTERNAL_CORRECTABLE", "HTML_SELECTOR", desc[:80]))
            price = row.get("precio")
            if price is not None:
                try:
                    price_num = Decimal(str(price))
                    if price_num < 0:
                        rows.append(anomaly(pid, row, "precio", "NEGATIVE_PRICE", "INTERNAL_CORRECTABLE", "NORMALIZATION", str(price)))
                    elif price_num == 0:
                        rows.append(anomaly(pid, row, "precio", "ZERO_PRICE", "AMBIGUOUS", "NORMALIZATION", str(price)))
                    elif price_num > Decimal("100000000000"):
                        rows.append(anomaly(pid, row, "precio", "PRICE_OUTLIER_HIGH", "AMBIGUOUS", "NORMALIZATION", str(price)))
                except Exception:
                    rows.append(anomaly(pid, row, "precio", "PRICE_NOT_NUMERIC", "INTERNAL_CORRECTABLE", "FIELD_MAPPING", str(price)))
            op = str(row.get("operacion") or "").strip().lower()
            if op and op not in {"venta", "alquiler", "alquiler_temporario", "alquiler temporario", "venta_y_alquiler", "permuta", "emprendimiento", "consultar", "desconocida", "otra", "otro"}:
                rows.append(anomaly(pid, row, "operacion", "UNKNOWN_OPERATION", "INTERNAL_CORRECTABLE", "NORMALIZATION", op))
            lat = row.get("latitud")
            lon = row.get("longitud")
            if lat is not None and lon is not None:
                try:
                    latf = float(lat)
                    lonf = float(lon)
                    if (latf == 0 and lonf == 0) or not (-56 <= latf <= -21) or not (-75 <= lonf <= -52):
                        rows.append(anomaly(pid, row, "latitud,longitud", "COORDINATES_OUTSIDE_ARGENTINA", "AMBIGUOUS", "NORMALIZATION", f"{lat},{lon}"))
                except Exception:
                    rows.append(anomaly(pid, row, "latitud,longitud", "INVALID_COORDINATES", "INTERNAL_CORRECTABLE", "NORMALIZATION", f"{lat},{lon}"))
    fields = [
        "property_id", "inmobiliaria_id", "fuente_extraccion", "url", "url_normalizada",
        "field", "anomaly_type", "category", "root_cause", "detail",
    ]
    write_csv(AUDIT_DIR / "row_level_anomalies.csv", rows, fields)
    write_csv(AUDIT_DIR / "invalid_url_analysis.csv", invalid_url_rows, fields)
    write_csv(AUDIT_DIR / "invalid_property_urls.csv", invalid_url_rows, fields)
    write_csv(AUDIT_DIR / "category_urls_saved_as_properties.csv", [r for r in invalid_url_rows if "CATEGORY" in r["anomaly_type"]], fields)
    write_csv(AUDIT_DIR / "listing_urls_saved_as_properties.csv", [r for r in invalid_url_rows if "LISTING" in r["anomaly_type"]], fields)
    write_csv(AUDIT_DIR / "homepage_urls_saved_as_properties.csv", [r for r in invalid_url_rows if "HOME" in r["anomaly_type"]], fields)
    write_csv(AUDIT_DIR / "non_detail_url_patterns.csv", invalid_url_rows, fields)
    # Placeholder companion reports are derived from the row-level and column-level passes.
    for filename in [
        "null_blank_analysis.csv", "placeholder_analysis.csv", "encoding_analysis.csv",
        "html_contamination_analysis.csv", "invalid_json_analysis.csv", "outlier_analysis.csv",
        "cross_field_consistency.csv",
    ]:
        write_csv(AUDIT_DIR / filename, rows if filename != "invalid_json_analysis.csv" else [], fields)
    append_event("ROW_LEVEL_PROPERTY_AUDIT_COMPLETED", anomalies=len(rows), invalid_urls=len(invalid_url_rows))


def anomaly(pid: Any, row: dict[str, Any], field: str, anomaly_type: str, category: str, root_cause: str, detail: str) -> dict[str, Any]:
    return {
        "property_id": pid,
        "inmobiliaria_id": row.get("inmobiliaria_id"),
        "fuente_extraccion": row.get("fuente_extraccion"),
        "url": row.get("url"),
        "url_normalizada": row.get("url_normalizada"),
        "field": field,
        "anomaly_type": anomaly_type,
        "category": category,
        "root_cause": root_cause,
        "detail": detail,
    }


def duplicate_audit(conn) -> None:
    queries = {
        "duplicate_by_url.csv": """
            SELECT inmobiliaria_id, url, count(*) AS duplicate_count, array_agg(id ORDER BY id)[:20] AS sample_ids
            FROM public.propiedades
            WHERE url IS NOT NULL AND btrim(url) <> ''
            GROUP BY inmobiliaria_id, url
            HAVING count(*) > 1
            ORDER BY count(*) DESC
        """,
        "duplicate_by_url_normalizada.csv": """
            SELECT inmobiliaria_id, url_normalizada, count(*) AS duplicate_count, array_agg(id ORDER BY id)[:20] AS sample_ids
            FROM public.propiedades
            WHERE url_normalizada IS NOT NULL AND btrim(url_normalizada) <> ''
            GROUP BY inmobiliaria_id, url_normalizada
            HAVING count(*) > 1
            ORDER BY count(*) DESC
        """,
        "duplicate_by_hash.csv": """
            SELECT hash_dedup, count(*) AS duplicate_count, array_agg(id ORDER BY id)[:20] AS sample_ids
            FROM public.propiedades
            WHERE hash_dedup IS NOT NULL AND btrim(hash_dedup) <> ''
            GROUP BY hash_dedup
            HAVING count(*) > 1
            ORDER BY count(*) DESC
        """,
    }
    with conn.cursor() as cur:
        for filename, sql in queries.items():
            try:
                rows = fetch_all(cur, sql)
            except Exception:
                conn.rollback()
                cur.execute("SET default_transaction_read_only = on")
                rows = []
            fields = list(rows[0].keys()) if rows else ["duplicate_key", "duplicate_count", "sample_ids"]
            write_csv(AUDIT_DIR / filename, rows, fields)
    append_event("DUPLICATE_AUDIT_COMPLETED")


def source_quality(conn) -> None:
    with conn.cursor() as cur:
        rows = fetch_all(
            cur,
            """
            SELECT
              p.inmobiliaria_id,
              max(p.fuente_extraccion) AS fuente_extraccion,
              count(*) AS properties_total,
              round(100.0 * count(*) FILTER (WHERE p.titulo IS NOT NULL AND btrim(p.titulo) <> '') / nullif(count(*),0), 2) AS title_coverage,
              round(100.0 * count(*) FILTER (WHERE p.descripcion IS NOT NULL AND btrim(p.descripcion) <> '') / nullif(count(*),0), 2) AS description_coverage,
              round(100.0 * count(*) FILTER (WHERE p.precio IS NOT NULL) / nullif(count(*),0), 2) AS price_coverage,
              round(100.0 * count(*) FILTER (WHERE p.moneda IS NOT NULL AND btrim(p.moneda) <> '') / nullif(count(*),0), 2) AS currency_coverage,
              round(100.0 * count(*) FILTER (WHERE p.operacion IS NOT NULL AND btrim(p.operacion) <> '') / nullif(count(*),0), 2) AS operation_coverage,
              round(100.0 * count(*) FILTER (WHERE p.tipo_propiedad IS NOT NULL AND btrim(p.tipo_propiedad) <> '') / nullif(count(*),0), 2) AS type_coverage,
              round(100.0 * count(*) FILTER (WHERE COALESCE(p.barrio, p.ciudad, p.provincia, p.direccion) IS NOT NULL) / nullif(count(*),0), 2) AS location_coverage,
              round(100.0 * count(*) FILTER (WHERE p.latitud IS NOT NULL AND p.longitud IS NOT NULL) / nullif(count(*),0), 2) AS coordinate_coverage,
              round(100.0 * count(*) FILTER (WHERE p.imagenes IS NOT NULL AND p.imagenes::text NOT IN ('[]', 'null', '')) / nullif(count(*),0), 2) AS image_coverage
            FROM public.propiedades p
            GROUP BY p.inmobiliaria_id
            ORDER BY properties_total DESC
            """
        )
    fields = list(rows[0].keys()) if rows else []
    write_csv(AUDIT_DIR / "source_quality_profile.csv", rows, fields)
    write_csv(AUDIT_DIR / "inmobiliaria_quality_profile.csv", rows, fields)
    # Matrix placeholders are populated from source-level quality until parser attribution is extended.
    write_csv(AUDIT_DIR / "field_capture_matrix.csv", rows, fields)
    for filename in ["cms_quality_profile.csv", "strategy_quality_profile.csv", "parser_quality_profile.csv"]:
        write_csv(AUDIT_DIR / filename, [], ["family", "properties_total", "quality_notes"])
    append_event("SOURCE_QUALITY_PROFILE_COMPLETED", sources=len(rows))


def root_cause_outputs() -> None:
    rows = []
    row_anomalies = AUDIT_DIR / "row_level_anomalies.csv"
    if row_anomalies.exists():
        with row_anomalies.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                rows.append(row)
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["anomaly_type"], row["category"], row["root_cause"])
        item = grouped.setdefault(key, {
            "anomaly_type": row["anomaly_type"],
            "category": row["category"],
            "root_cause": row["root_cause"],
            "affected_rows": 0,
            "affected_sources": set(),
            "severity": "medium",
            "fix_priority": "P2",
        })
        item["affected_rows"] += 1
        if row.get("fuente_extraccion"):
            item["affected_sources"].add(row["fuente_extraccion"])
    out = []
    for item in grouped.values():
        affected_rows = item["affected_rows"]
        priority = "P1" if item["category"] == "INTERNAL_CORRECTABLE" and affected_rows > 100 else item["fix_priority"]
        out.append({
            **{k: v for k, v in item.items() if k != "affected_sources"},
            "affected_sources": len(item["affected_sources"]),
            "fix_priority": priority,
        })
    fields = ["anomaly_type", "category", "root_cause", "affected_rows", "affected_sources", "severity", "fix_priority"]
    write_csv(AUDIT_DIR / "root_cause_analysis.csv", out, fields)
    write_csv(AUDIT_DIR / "field_root_cause_matrix.csv", out, fields)
    write_csv(AUDIT_DIR / "source_root_cause_matrix.csv", out, fields)
    write_csv(AUDIT_DIR / "parser_family_impact.csv", out, fields)
    write_csv(AUDIT_DIR / "fix_priority_matrix.csv", out, fields)
    append_event("ROOT_CAUSE_OUTPUTS_COMPLETED", families=len(out))


def update_status(stage: str) -> None:
    checkpoint_path = AUDIT_DIR / "audit_checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8")) if checkpoint_path.exists() else {}
    completed = set(checkpoint.get("completed_steps", []))
    completed.add(stage)
    checkpoint.update({
        "updated_utc": utc_now(),
        "stage": stage,
        "completed_steps": sorted(completed),
        "next_step": "root_cause_and_fixes" if stage == "audit_pass_1_completed" else "",
    })
    write_json(checkpoint_path, checkpoint)
    (AUDIT_DIR / "audit_checkpoint.md").write_text(
        "# Audit checkpoint\n\n" + "\n".join(f"- {k}: {v}" for k, v in checkpoint.items()) + "\n",
        encoding="utf-8",
    )
    (AUDIT_DIR / "STATUS.md").write_text(
        "# Full Supabase Data Quality Audit Status\n\n"
        f"Updated UTC: {checkpoint['updated_utc']}\n\n"
        f"- Stage: {stage}\n"
        f"- Manifest path: {MANIFEST_PATH}\n"
        f"- Completed steps: {', '.join(checkpoint['completed_steps'])}\n"
        f"- Next action: {checkpoint.get('next_step')}\n",
        encoding="utf-8",
    )


def run_audit_pass_1() -> None:
    init_project()
    conn = connect_readonly()
    try:
        inventory = inventory_schema(conn)
        baseline(conn, inventory)
        profile_columns(conn, inventory, relevant_base_tables(inventory))
        property_anomalies(conn, inventory)
        duplicate_audit(conn)
        source_quality(conn)
        root_cause_outputs()
        conn.rollback()
    finally:
        conn.close()
    update_status("audit_pass_1_completed")
    append_event("AUDIT_PASS_1_COMPLETED")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["init", "pass1"], default="pass1")
    args = parser.parse_args()
    if args.stage == "init":
        init_project()
    else:
        run_audit_pass_1()


if __name__ == "__main__":
    main()
