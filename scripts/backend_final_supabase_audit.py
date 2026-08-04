#!/usr/bin/env python3
"""Create a read-only, sanitized Supabase metadata/security/performance snapshot."""

from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import psycopg
from dotenv import load_dotenv
from psycopg import sql
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "_scratch/backend_final_closure/SUPABASE_AUDIT"
PLATFORM_SCHEMAS = {"auth", "extensions", "realtime", "storage", "vault"}


def db_url() -> str:
    load_dotenv(ROOT / ".env", override=False)
    value = os.getenv("SUPABASE_DATABASE_URL", "")
    if not value:
        raise RuntimeError("SUPABASE_DATABASE_URL is not configured")
    return value


def serialize(value: Any) -> Any:
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return value


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fields: list[str] | None = None) -> None:
    rows = list(rows)
    fields = fields or (list(rows[0]) if rows else ["status"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: serialize(row.get(key)) for key in fields})


def fetch(cursor: Any, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cursor.execute(query, params)
    return [dict(row) for row in cursor.fetchall()]


def classify(schema: str, name: str, kind: str) -> tuple[str, str]:
    lower = name.casefold()
    if schema in PLATFORM_SCHEMAS:
        return "PRODUCTION", f"Supabase platform-owned {kind}"
    if "backup" in lower or lower.startswith("bak_"):
        return "BACKUP", "Explicit historical backup"
    if schema == "internal_scraping":
        if "raw" in lower:
            return "RAW", "Pipeline A raw layer"
        if "staging" in lower:
            return "STAGING", "Pipeline A staging layer"
        if "publish" in lower:
            return "PUBLISH" if "queue" not in lower else "QUEUE", "Pipeline A publish layer"
        if "run" in lower:
            return "AUDIT", "Pipeline A execution trace"
        if "error" in lower or "quality" in lower or "summary" in lower:
            return "AUDIT", "Pipeline A audit/quality object"
        return "SCRAPER_OUTPUT", "Internal Pipeline A object"
    if kind in {"VIEW", "MATERIALIZED VIEW"}:
        return "FRONTEND_READ_MODEL", "Public derived/read model"
    if name == "propiedades":
        return "SCRAPER_OUTPUT", "Canonical property output"
    if name in {"inmobiliarias_main", "inmobiliarias_scraping", "city_normalization_rules"}:
        return "CONFIGURATION", "Canonical source/configuration object"
    if name in {"scraping_runs", "scraping_run_items"}:
        return "AUDIT", "Legacy/public execution trace"
    if any(token in lower for token in ("raw", "staging")):
        return "STAGING", "Staging object"
    if any(token in lower for token in ("event", "history", "historial", "analysis", "score", "quality", "correction")):
        return "AUDIT", "Data quality/intelligence object"
    return "PRODUCTION", "Public production object"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc).isoformat()

    with psycopg.connect(db_url(), row_factory=dict_row, connect_timeout=60) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        conn.execute("SET statement_timeout = '15min'")
        with conn.cursor() as cur:
            schemas = fetch(
                cur,
                """
                SELECT schema_name
                FROM information_schema.schemata
                WHERE schema_name NOT IN ('pg_catalog', 'information_schema')
                ORDER BY schema_name
                """,
            )
            tables = fetch(
                cur,
                """
                SELECT table_schema, table_name, table_type
                FROM information_schema.tables
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY table_schema, table_name
                """,
            )
            for row in tables:
                row["classification"], row["classification_reason"] = classify(
                    row["table_schema"], row["table_name"], row["table_type"]
                )
            columns = fetch(
                cur,
                """
                SELECT table_schema, table_name, column_name, ordinal_position,
                       data_type, udt_name, is_nullable, column_default,
                       character_maximum_length, numeric_precision, numeric_scale,
                       datetime_precision, is_identity, is_generated
                FROM information_schema.columns
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY table_schema, table_name, ordinal_position
                """,
            )
            constraints = fetch(
                cur,
                """
                SELECT tc.table_schema, tc.table_name, tc.constraint_name,
                       tc.constraint_type, kcu.column_name, kcu.ordinal_position,
                       ccu.table_schema AS foreign_table_schema,
                       ccu.table_name AS foreign_table_name,
                       ccu.column_name AS foreign_column_name,
                       rc.update_rule, rc.delete_rule
                FROM information_schema.table_constraints tc
                LEFT JOIN information_schema.key_column_usage kcu
                  ON kcu.constraint_schema = tc.constraint_schema
                 AND kcu.constraint_name = tc.constraint_name
                LEFT JOIN information_schema.constraint_column_usage ccu
                  ON ccu.constraint_schema = tc.constraint_schema
                 AND ccu.constraint_name = tc.constraint_name
                LEFT JOIN information_schema.referential_constraints rc
                  ON rc.constraint_schema = tc.constraint_schema
                 AND rc.constraint_name = tc.constraint_name
                WHERE tc.table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY tc.table_schema, tc.table_name, tc.constraint_name,
                         kcu.ordinal_position
                """,
            )
            checks = fetch(
                cur,
                """
                SELECT n.nspname AS table_schema, c.relname AS table_name,
                       con.conname AS constraint_name,
                       pg_get_constraintdef(con.oid, true) AS definition,
                       con.convalidated AS validated
                FROM pg_constraint con
                JOIN pg_class c ON c.oid = con.conrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE con.contype = 'c'
                  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
                ORDER BY n.nspname, c.relname, con.conname
                """,
            )
            indexes = fetch(
                cur,
                """
                SELECT schemaname AS table_schema, tablename AS table_name,
                       indexname AS index_name, indexdef
                FROM pg_indexes
                WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
                ORDER BY schemaname, tablename, indexname
                """,
            )
            triggers = fetch(
                cur,
                """
                SELECT event_object_schema AS table_schema,
                       event_object_table AS table_name, trigger_name,
                       event_manipulation, action_timing, action_orientation,
                       action_statement
                FROM information_schema.triggers
                WHERE trigger_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY event_object_schema, event_object_table, trigger_name
                """,
            )
            functions = fetch(
                cur,
                """
                SELECT n.nspname AS function_schema, p.proname AS function_name,
                       pg_get_function_identity_arguments(p.oid) AS identity_arguments,
                       pg_get_function_result(p.oid) AS result_type,
                       l.lanname AS language, p.prosecdef AS security_definer,
                       p.provolatile AS volatility, p.proconfig AS configuration
                FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace
                JOIN pg_language l ON l.oid = p.prolang
                WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
                ORDER BY n.nspname, p.proname, identity_arguments
                """,
            )
            views = fetch(
                cur,
                """
                SELECT table_schema, table_name, is_updatable,
                       is_insertable_into, check_option
                FROM information_schema.views
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY table_schema, table_name
                """,
            )
            matviews = fetch(
                cur,
                """
                SELECT schemaname AS table_schema, matviewname AS table_name,
                       ispopulated, definition
                FROM pg_matviews
                WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
                ORDER BY schemaname, matviewname
                """,
            )
            types = fetch(
                cur,
                """
                SELECT n.nspname AS type_schema, t.typname AS type_name,
                       t.typtype AS type_kind,
                       string_agg(e.enumlabel, ',' ORDER BY e.enumsortorder) AS enum_values
                FROM pg_type t
                JOIN pg_namespace n ON n.oid = t.typnamespace
                LEFT JOIN pg_enum e ON e.enumtypid = t.oid
                WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
                  AND (t.typtype IN ('e','d','c') OR e.enumlabel IS NOT NULL)
                GROUP BY n.nspname, t.typname, t.typtype
                ORDER BY n.nspname, t.typname
                """,
            )
            rls = fetch(
                cur,
                """
                SELECT n.nspname AS table_schema, c.relname AS table_name,
                       c.relrowsecurity AS rls_enabled,
                       c.relforcerowsecurity AS rls_forced
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relkind IN ('r','p')
                  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
                ORDER BY n.nspname, c.relname
                """,
            )
            policies = fetch(
                cur,
                """
                SELECT schemaname AS table_schema, tablename AS table_name,
                       policyname AS policy_name, permissive, roles, cmd,
                       qual, with_check
                FROM pg_policies
                ORDER BY schemaname, tablename, policyname
                """,
            )
            grants = fetch(
                cur,
                """
                SELECT grantor, grantee, table_schema, table_name,
                       privilege_type, is_grantable
                FROM information_schema.role_table_grants
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY grantee, table_schema, table_name, privilege_type
                """,
            )
            default_privileges = fetch(
                cur,
                """
                SELECT pg_get_userbyid(d.defaclrole) AS owner,
                       n.nspname AS schema_name, d.defaclobjtype AS object_type,
                       d.defaclacl::text AS privileges
                FROM pg_default_acl d
                LEFT JOIN pg_namespace n ON n.oid = d.defaclnamespace
                ORDER BY owner, schema_name, object_type
                """,
            )
            sizes = fetch(
                cur,
                """
                SELECT n.nspname AS table_schema, c.relname AS table_name,
                       pg_total_relation_size(c.oid) AS total_bytes,
                       pg_relation_size(c.oid) AS table_bytes,
                       pg_indexes_size(c.oid) AS index_bytes,
                       c.reltuples::bigint AS estimated_rows
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relkind IN ('r','p','m')
                  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
                ORDER BY pg_total_relation_size(c.oid) DESC
                """,
            )
            row_counts: list[dict[str, Any]] = []
            estimate = {
                (row["table_schema"], row["table_name"]): row["estimated_rows"]
                for row in sizes
            }
            for table in tables:
                schema = table["table_schema"]
                name = table["table_name"]
                if table["table_type"] != "BASE TABLE":
                    continue
                exact: int | None = None
                method = "pg_class_estimate"
                if schema in {"public", "internal_scraping"}:
                    cur.execute(
                        sql.SQL("SELECT count(*)::bigint AS n FROM {}.{}").format(
                            sql.Identifier(schema), sql.Identifier(name)
                        )
                    )
                    exact = int(cur.fetchone()["n"])
                    method = "exact"
                row_counts.append(
                    {
                        "table_schema": schema,
                        "table_name": name,
                        "row_count": exact if exact is not None else estimate.get((schema, name), 0),
                        "count_method": method,
                    }
                )
            dependencies = fetch(
                cur,
                """
                SELECT view_schema, view_name, table_schema, table_name
                FROM information_schema.view_table_usage
                WHERE view_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY view_schema, view_name, table_schema, table_name
                """,
            )
            dependencies.extend(
                {
                    "view_schema": row["table_schema"],
                    "view_name": row["table_name"],
                    "table_schema": row["foreign_table_schema"],
                    "table_name": row["foreign_table_name"],
                }
                for row in constraints
                if row["constraint_type"] == "FOREIGN KEY"
            )
            buckets: list[dict[str, Any]] = []
            if any(row["table_schema"] == "storage" and row["table_name"] == "buckets" for row in tables):
                buckets = fetch(
                    cur,
                    """
                    SELECT id, name, public, file_size_limit,
                           allowed_mime_types, created_at, updated_at
                    FROM storage.buckets
                    ORDER BY id
                    """,
                )
            index_usage = fetch(
                cur,
                """
                SELECT s.schemaname AS table_schema, s.relname AS table_name,
                       s.indexrelname AS index_name, s.idx_scan,
                       pg_relation_size(s.indexrelid) AS index_bytes,
                       i.indisunique AS is_unique, i.indisvalid AS is_valid
                FROM pg_stat_user_indexes s
                JOIN pg_index i ON i.indexrelid = s.indexrelid
                ORDER BY s.idx_scan, pg_relation_size(s.indexrelid) DESC
                """,
            )
            table_usage = fetch(
                cur,
                """
                SELECT schemaname AS table_schema, relname AS table_name,
                       seq_scan, seq_tup_read, idx_scan, n_live_tup,
                       n_dead_tup, last_analyze, last_autoanalyze
                FROM pg_stat_user_tables
                ORDER BY seq_tup_read DESC
                """,
            )
            compromised = fetch(
                cur,
                """
                SELECT count(*)::int AS matching_source_rows
                FROM public.inmobiliarias_main
                WHERE coalesce(nombre,'') ~* 'cuba.*plaza|plaza.*cuba'
                """,
            )

    write_csv(out / "schemas.csv", schemas)
    write_csv(out / "tables.csv", tables)
    write_csv(out / "columns.csv", columns)
    write_csv(out / "primary_keys.csv", [r for r in constraints if r["constraint_type"] == "PRIMARY KEY"])
    write_csv(out / "foreign_keys.csv", [r for r in constraints if r["constraint_type"] == "FOREIGN KEY"])
    write_csv(out / "unique_constraints.csv", [r for r in constraints if r["constraint_type"] == "UNIQUE"])
    write_csv(out / "check_constraints.csv", checks)
    write_csv(out / "indexes.csv", indexes)
    write_csv(out / "triggers.csv", triggers)
    write_csv(out / "functions.csv", functions)
    write_csv(out / "views.csv", views)
    write_csv(out / "materialized_views.csv", matviews)
    write_csv(out / "enums_and_types.csv", types)
    write_csv(out / "rls_status.csv", rls)
    write_csv(out / "policies.csv", policies)
    write_csv(out / "grants.csv", grants)
    write_csv(out / "default_privileges.csv", default_privileges)
    write_csv(out / "storage_buckets.csv", buckets)
    write_csv(out / "storage_policies.csv", [r for r in policies if r["table_schema"] == "storage"])
    write_csv(out / "table_sizes.csv", sizes)
    write_csv(out / "row_counts.csv", row_counts)
    write_csv(out / "dependencies.csv", dependencies)
    deprecated = [
        {
            "table_schema": row["table_schema"],
            "table_name": row["table_name"],
            "classification": row["classification"],
            "reason": "Historical backup retained for rollback; review retention separately",
        }
        for row in tables
        if row["classification"] == "BACKUP"
    ]
    unknown = [
        {
            "table_schema": row["table_schema"],
            "table_name": row["table_name"],
            "reason": row["classification_reason"],
        }
        for row in tables
        if row["classification"] == "UNKNOWN"
    ]
    write_csv(out / "deprecated_objects.csv", deprecated)
    write_csv(out / "unknown_objects.csv", unknown)
    write_csv(out / "index_usage.csv", index_usage)
    write_csv(out / "table_usage.csv", table_usage)

    anon_sensitive = [
        row for row in grants
        if row["grantee"] in {"anon", "authenticated"}
        and row["table_schema"] in {"internal_scraping"}
    ]
    security_definer = [row for row in functions if row["security_definer"]]
    unsafe_search_path = [
        row for row in security_definer
        if not row.get("configuration")
        or "search_path" not in str(row.get("configuration"))
    ]
    public_backups = [
        row for row in grants
        if row["grantee"] in {"anon", "authenticated"}
        and "backup" in row["table_name"].casefold()
    ]
    security = {
        "generated_utc": generated,
        "anon_or_authenticated_internal_grants": len(anon_sensitive),
        "anon_or_authenticated_backup_grants": len(public_backups),
        "security_definer_functions": len(security_definer),
        "security_definer_without_explicit_search_path": len(unsafe_search_path),
        "cuba_plaza_matching_sources": compromised[0]["matching_source_rows"] if compromised else 0,
        "cuba_plaza_credential_status": "COMPROMISED_ROTATE_OR_EXCLUDE_NO_SECRET_EXPORTED",
        "secrets_exported": 0,
    }
    (out / "security_audit.json").write_text(
        json.dumps(security, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / "security_audit.md").write_text(
        "# Supabase security audit\n\n"
        f"Generated UTC: {generated}\n\n"
        f"- anon/authenticated grants on `internal_scraping`: {security['anon_or_authenticated_internal_grants']}\n"
        f"- anon/authenticated grants on backup tables: {security['anon_or_authenticated_backup_grants']}\n"
        f"- SECURITY DEFINER functions: {security['security_definer_functions']}\n"
        f"- SECURITY DEFINER functions without explicit search_path: {security['security_definer_without_explicit_search_path']}\n"
        f"- CUBA PLAZA matching source rows: {security['cuba_plaza_matching_sources']}\n"
        "- Historical Tokko credential status: compromised; rotate or exclude. It was not displayed or tested.\n"
        "- Secrets exported: 0\n",
        encoding="utf-8",
    )
    (out / "performance_audit.md").write_text(
        "# Supabase performance audit\n\n"
        f"Generated UTC: {generated}\n\n"
        f"- Relations measured: {len(sizes)}\n"
        f"- Indexes with usage statistics: {len(index_usage)}\n"
        f"- User tables with scan statistics: {len(table_usage)}\n"
        "- No index was created automatically. Existing usage, selectivity, overlap, and write cost must justify each migration.\n",
        encoding="utf-8",
    )
    summary = {
        "generated_utc": generated,
        "schemas": len(schemas),
        "tables_and_views": len(tables),
        "columns": len(columns),
        "views": len(views),
        "materialized_views": len(matviews),
        "functions": len(functions),
        "indexes": len(indexes),
        "policies": len(policies),
        "unknown_objects": len(unknown),
        "deprecated_or_backup_objects": len(deprecated),
        "security": security,
    }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
