#!/usr/bin/env python
"""PR-BE-URL-06d controlled url_listado update.

Authorized scope:
- Create a backup table for the 1,057 final safe rows.
- Update only public.inmobiliarias_main.url_listado.
- Generate local validation and rollback artifacts.

This script does not run scraping, publish, deploy, push, or create runs.
"""

from __future__ import annotations

import argparse
import csv
import os
import pathlib
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPO_ROOT / "_scratch" / "url_listing_db_preflight" / "final_safe_update_candidates.csv"
DEFAULT_OUT = REPO_ROOT / "_scratch" / "url_listing_update_pr_be_url_06d"
EXPECTED_COUNT = 1057

MAIN_TABLE = ("public", "inmobiliarias_main")
BACKUP_PREFIX = "backup_inmobiliarias_main_url_listado_pr_be_url_06d"
TMP_TABLE = "tmp_url_listado_pr_be_url_06d"

PROHIBITED_URL_RE = re.compile(r"(zonaprop|argenprop|properati)", re.I)
INCOMPATIBLE_DIAGNOSTIC = {"missing_url", "domain_down", "prohibited_source"}
PROHIBITED_COLUMNS = [
    "cms_detectado",
    "estrategia_scraping",
    "diagnostic_status",
    "scraping_readiness",
    "exclude_from_scraping",
    "sitio_activo",
    "activa",
]


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


def is_true(value: Any) -> bool:
    return clean(value).lower() in {"1", "true", "t", "yes", "y"}


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(clean(value)))
    except Exception:
        return default


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def read_csv(path: pathlib.Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: pathlib.Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        keys: list[str] = []
        for row in rows:
            for key in row:
                if key not in keys:
                    keys.append(key)
        fields = keys
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def validate_input(rows: list[dict[str, str]], expected_count: int) -> list[str]:
    errors: list[str] = []
    if len(rows) != expected_count:
        errors.append(f"expected_{expected_count}_rows_got_{len(rows)}")

    seen: Counter[str] = Counter(clean(row.get("source_id")) for row in rows)
    duplicates = [sid for sid, count in seen.items() if count > 1]
    if duplicates:
        errors.append(f"duplicate_source_ids={len(duplicates)}")

    for row in rows:
        sid = clean(row.get("source_id"))
        proposed = clean(row.get("proposed_url_listado"))
        current = clean(row.get("current_url_listado_db"))
        if not sid or to_int(sid) <= 0:
            errors.append(f"invalid_source_id={sid}")
        if clean(row.get("final_classification")) != "final_safe_update":
            errors.append(f"not_final_safe_update source_id={sid}")
        if clean(row.get("confidence")).lower() != "high":
            errors.append(f"not_high_confidence source_id={sid}")
        if to_int(row.get("score")) < 90:
            errors.append(f"score_lt_90 source_id={sid}")
        if to_int(row.get("property_links_count")) < 3:
            errors.append(f"property_links_lt_3 source_id={sid}")
        if not proposed:
            errors.append(f"empty_proposed source_id={sid}")
        if proposed == current:
            errors.append(f"proposed_equals_current source_id={sid}")
        if is_true(row.get("exclude_from_scraping")):
            errors.append(f"excluded source_id={sid}")
        if clean(row.get("current_url_matches_db")).lower() not in {"true", "1", "yes"}:
            errors.append(f"db_mismatch_flag source_id={sid}")
        if clean(row.get("diagnostic_status_db")) in INCOMPATIBLE_DIAGNOSTIC:
            errors.append(f"incompatible_diagnostic source_id={sid}")
        if PROHIBITED_URL_RE.search(proposed) or PROHIBITED_URL_RE.search(clean(row.get("website_url_db"))):
            errors.append(f"prohibited_url source_id={sid}")
    return errors


def connect_db() -> psycopg.Connection:
    load_env()
    db_url = os.getenv("INTERNAL_DB_URL", "").strip()
    if not db_url:
        raise SystemExit("Missing INTERNAL_DB_URL; value was not printed.")
    return psycopg.connect(db_url, row_factory=dict_row, connect_timeout=30)


def table_exists(cur: psycopg.Cursor, schema_name: str, table_name: str) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
          SELECT 1
          FROM information_schema.tables
          WHERE table_schema = %s AND table_name = %s
        )
        """,
        (schema_name, table_name),
    )
    return bool(cur.fetchone()["exists"])


def table_count(cur: psycopg.Cursor, schema_name: str, table_name: str) -> int | None:
    if not table_exists(cur, schema_name, table_name):
        return None
    cur.execute(sql.SQL("SELECT count(*) AS n FROM {}").format(sql.Identifier(schema_name, table_name)))
    return int(cur.fetchone()["n"])


def snapshot_counts(cur: psycopg.Cursor) -> dict[str, int | None]:
    return {
        "public.propiedades": table_count(cur, "public", "propiedades"),
        "public.publish_queue": table_count(cur, "public", "publish_queue"),
        "public.scraping_runs": table_count(cur, "public", "scraping_runs"),
    }


def get_main_columns(cur: psycopg.Cursor) -> set[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'inmobiliarias_main'
        """
    )
    return {row["column_name"] for row in cur.fetchall()}


def create_temp_candidates(cur: psycopg.Cursor, rows: list[dict[str, str]]) -> None:
    cur.execute(
        sql.SQL(
            """
            CREATE TEMP TABLE {} (
              id integer PRIMARY KEY,
              source_name text,
              old_url_listado text,
              new_url_listado text,
              website_url_csv text,
              website_url_db text,
              confidence text,
              score integer,
              property_links_count integer,
              estimated_property_yield integer,
              evidence text,
              risk text
            ) ON COMMIT DROP
            """
        ).format(sql.Identifier(TMP_TABLE))
    )
    payload = [
        (
            to_int(row["source_id"]),
            clean(row.get("source_name")),
            clean(row.get("current_url_listado_db")),
            clean(row.get("proposed_url_listado")),
            clean(row.get("website_url_csv")),
            clean(row.get("website_url_db")),
            clean(row.get("confidence")),
            to_int(row.get("score")),
            to_int(row.get("property_links_count")),
            to_int(row.get("estimated_property_yield")),
            clean(row.get("evidence")),
            clean(row.get("risk")),
        )
        for row in rows
    ]
    cur.executemany(
        sql.SQL(
            """
            INSERT INTO {} (
              id, source_name, old_url_listado, new_url_listado, website_url_csv,
              website_url_db, confidence, score, property_links_count,
              estimated_property_yield, evidence, risk
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """
        ).format(sql.Identifier(TMP_TABLE)),
        payload,
    )


def db_precheck(cur: psycopg.Cursor, expected_count: int) -> list[str]:
    errors: list[str] = []
    cur.execute(sql.SQL("SELECT count(*) AS n FROM {}").format(sql.Identifier(TMP_TABLE)))
    tmp_count = int(cur.fetchone()["n"])
    if tmp_count != expected_count:
        errors.append(f"temp_candidate_count_expected_{expected_count}_got_{tmp_count}")

    cur.execute(
        sql.SQL(
            """
            SELECT t.id
            FROM {} t
            LEFT JOIN public.inmobiliarias_main i ON i.id = t.id
            WHERE i.id IS NULL
            """
        ).format(sql.Identifier(TMP_TABLE))
    )
    missing = cur.fetchall()
    if missing:
        errors.append(f"missing_in_db={len(missing)}")

    cur.execute(
        sql.SQL(
            """
            SELECT count(*) AS n
            FROM {} t
            JOIN public.inmobiliarias_main i ON i.id = t.id
            WHERE COALESCE(i.url_listado, '') <> COALESCE(t.old_url_listado, '')
            """
        ).format(sql.Identifier(TMP_TABLE))
    )
    mismatches = int(cur.fetchone()["n"])
    if mismatches:
        errors.append(f"current_url_listado_mismatch={mismatches}")

    cur.execute(
        sql.SQL(
            """
            SELECT count(*) AS n
            FROM {} t
            JOIN public.inmobiliarias_main i ON i.id = t.id
            WHERE COALESCE(t.new_url_listado, '') = ''
               OR COALESCE(t.new_url_listado, '') = COALESCE(i.url_listado, '')
               OR COALESCE(i.exclude_from_scraping, false) = true
               OR COALESCE(i.diagnostic_status, '') IN ('missing_url', 'domain_down', 'prohibited_source')
               OR COALESCE(t.confidence, '') <> 'high'
               OR t.score < 90
               OR t.property_links_count < 3
            """
        ).format(sql.Identifier(TMP_TABLE))
    )
    unsafe = int(cur.fetchone()["n"])
    if unsafe:
        errors.append(f"unsafe_rows_in_db_precheck={unsafe}")
    return errors


def create_backup(cur: psycopg.Cursor, backup_name: str, expected_count: int, existing_cols: set[str]) -> int:
    # Build explicitly so the backup has the required minimum columns first.
    extra_cols = [col for col in ["cms_detectado", "estrategia_scraping", "sitio_activo", "activa"] if col in existing_cols]
    extra_select = sql.SQL("")
    if extra_cols:
        extra_select = sql.SQL(",\n          ") + sql.SQL(",\n          ").join(
            sql.SQL("i.{col}").format(col=sql.Identifier(col)) for col in extra_cols
        )

    backup_ident = sql.Identifier("public", backup_name)
    cur.execute(
        sql.SQL(
            """
            CREATE TABLE {backup_ident} AS
            SELECT
              i.id,
              i.nombre,
              i.web AS website_url,
              i.url_listado AS old_url_listado,
              t.new_url_listado AS new_url_listado,
              i.diagnostic_status,
              i.scraping_readiness,
              i.exclude_from_scraping
              {extra_select},
              now() AT TIME ZONE 'utc' AS backup_created_at
            FROM public.inmobiliarias_main i
            JOIN {tmp_ident} t ON t.id = i.id
            WHERE COALESCE(i.url_listado, '') = COALESCE(t.old_url_listado, '')
            """
        ).format(backup_ident=backup_ident, tmp_ident=sql.Identifier(TMP_TABLE), extra_select=extra_select)
    )
    cur.execute(sql.SQL("SELECT count(*) AS n FROM {}").format(backup_ident))
    backup_count = int(cur.fetchone()["n"])
    if backup_count != expected_count:
        raise RuntimeError(f"backup_count_expected_{expected_count}_got_{backup_count}")
    return backup_count


def run_update(cur: psycopg.Cursor) -> list[dict[str, Any]]:
    cur.execute(
        sql.SQL(
            """
            UPDATE public.inmobiliarias_main AS i
            SET url_listado = t.new_url_listado
            FROM {tmp_ident} t
            WHERE i.id = t.id
              AND COALESCE(i.url_listado, '') = COALESCE(t.old_url_listado, '')
              AND COALESCE(t.new_url_listado, '') <> ''
            RETURNING i.id AS source_id, t.source_name, t.old_url_listado,
                      t.new_url_listado, i.url_listado AS db_url_listado_after,
                      t.estimated_property_yield, t.score, t.property_links_count,
                      t.evidence, t.risk
            """
        ).format(tmp_ident=sql.Identifier(TMP_TABLE))
    )
    return [dict(row) for row in cur.fetchall()]


def collect_not_updated(cur: psycopg.Cursor) -> list[dict[str, Any]]:
    cur.execute(
        sql.SQL(
            """
            SELECT t.id AS source_id, t.source_name, t.old_url_listado,
                   t.new_url_listado, i.url_listado AS db_url_listado_after,
                   CASE
                     WHEN i.id IS NULL THEN 'missing_in_db'
                     WHEN COALESCE(i.url_listado, '') <> COALESCE(t.new_url_listado, '') THEN 'url_not_updated'
                     ELSE ''
                   END AS reason
            FROM {tmp_ident} t
            LEFT JOIN public.inmobiliarias_main i ON i.id = t.id
            WHERE i.id IS NULL OR COALESCE(i.url_listado, '') <> COALESCE(t.new_url_listado, '')
            ORDER BY t.id
            """
        ).format(tmp_ident=sql.Identifier(TMP_TABLE))
    )
    return [dict(row) for row in cur.fetchall()]


def changed_columns_counts(cur: psycopg.Cursor, backup_name: str, existing_cols: set[str]) -> dict[str, int]:
    backup_ident = sql.Identifier("public", backup_name)
    counts: dict[str, int] = {}
    for col in PROHIBITED_COLUMNS:
        if col not in existing_cols:
            counts[col] = -1
            continue
        cur.execute(
            sql.SQL(
                """
                SELECT count(*) AS n
                FROM public.inmobiliarias_main i
                JOIN {backup_ident} b ON b.id = i.id
                WHERE i.{col} IS DISTINCT FROM b.{col}
                """
            ).format(backup_ident=backup_ident, col=sql.Identifier(col))
        )
        counts[col] = int(cur.fetchone()["n"])
    return counts


def generate_rollback_sql(path: pathlib.Path, backup_name: str) -> None:
    text = f"""-- PR-BE-URL-06d rollback
-- Execute only if rollback is explicitly authorized.
-- Restores public.inmobiliarias_main.url_listado from public.{backup_name}.

BEGIN;

UPDATE public.inmobiliarias_main AS i
SET url_listado = b.old_url_listado
FROM public.{backup_name} AS b
WHERE i.id = b.id
  AND COALESCE(i.url_listado, '') = COALESCE(b.new_url_listado, '');

COMMIT;
"""
    path.write_text(text, encoding="utf-8")


def md_table(rows: list[dict[str, Any]], fields: list[str], limit: int = 20) -> str:
    subset = rows[:limit]
    if not subset:
        return "_Sin filas._"
    lines = ["| " + " | ".join(fields) + " |", "| " + " | ".join(["---"] * len(fields)) + " |"]
    for row in subset:
        lines.append("| " + " | ".join(clean(row.get(field)).replace("|", "\\|") for field in fields) + " |")
    return "\n".join(lines)


def write_reports(
    out: pathlib.Path,
    backup_name: str,
    expected: int,
    backup_count: int,
    updated_rows: list[dict[str, Any]],
    not_updated_rows: list[dict[str, Any]],
    counts_before: dict[str, int | None],
    counts_after: dict[str, int | None],
    changed_counts: dict[str, int],
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "backup_table_name.txt").write_text(f"public.{backup_name}\n", encoding="utf-8")
    write_csv(out / "updated_rows.csv", updated_rows)
    write_csv(out / "not_updated_rows.csv", not_updated_rows)
    generate_rollback_sql(out / "rollback_sql.sql", backup_name)

    changed_errors = {k: v for k, v in changed_counts.items() if v not in (0, -1)}
    protected_count_lines = "\n".join(
        f"- {name}: before={counts_before.get(name)} after={counts_after.get(name)}"
        for name in sorted(counts_before)
    )
    changed_column_lines = "\n".join(
        f"- {col}: {'missing_column' if count == -1 else count}"
        for col, count in changed_counts.items()
    )
    top = sorted(
        updated_rows,
        key=lambda row: (to_int(row.get("estimated_property_yield")), to_int(row.get("score"))),
        reverse=True,
    )[:20]

    summary = f"""# PR-BE-URL-06d update summary

Generated: {datetime.now(timezone.utc).isoformat()}

## Result
- Backup table: `public.{backup_name}`
- Expected update count: **{expected}**
- Backup rows: **{backup_count}**
- Updated rows: **{len(updated_rows)}**
- Not updated rows: **{len(not_updated_rows)}**
- Changed prohibited columns: **{len(changed_errors)}**

## Top 20 updated by estimated impact
{md_table(top, ['source_id', 'source_name', 'old_url_listado', 'new_url_listado', 'estimated_property_yield', 'score', 'property_links_count'])}

## Protected tables count snapshot
{protected_count_lines}
"""
    (out / "update_summary.md").write_text(summary, encoding="utf-8")

    post = f"""# Post-update validation

- Expected rows: {expected}
- Backup rows: {backup_count}
- Updated rows: {len(updated_rows)}
- Not updated rows: {len(not_updated_rows)}
- Update count exact: {len(updated_rows) == expected}
- Backup count exact: {backup_count == expected}
- public.propiedades unchanged by count: {counts_before.get('public.propiedades') == counts_after.get('public.propiedades')}
- public.publish_queue unchanged by count: {counts_before.get('public.publish_queue') == counts_after.get('public.publish_queue')}
- public.scraping_runs unchanged by count: {counts_before.get('public.scraping_runs') == counts_after.get('public.scraping_runs')}
- Scraping productivo: 0
- Publish: 0
- Runs created by this script: 0
- Push/deploy/frontend: 0
"""
    (out / "post_update_validation.md").write_text(post, encoding="utf-8")

    changed_doc = f"""# Changed columns validation

Compared affected rows against `public.{backup_name}` after the UPDATE.

## Prohibited columns
{changed_column_lines}

## Result
{"OK - only url_listado changed for affected rows." if not changed_errors else "ERROR - prohibited column changed."}
"""
    (out / "changed_columns_validation.md").write_text(changed_doc, encoding="utf-8")

    recommendation = """# Next step recommendation

Do not run productive scraping yet.

Recommended next phase: controlled scraping validation for the updated sources,
starting with a small batch from the highest-impact rows, measuring transition
from previous listing-url errors to success before expanding coverage.
"""
    (out / "next_step_recommendation.md").write_text(recommendation, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply PR-BE-URL-06d url_listado update")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--expected-count", type=int, default=EXPECTED_COUNT)
    args = parser.parse_args()

    input_path = pathlib.Path(args.input)
    out = pathlib.Path(args.out)
    if not input_path.exists():
        raise SystemExit(f"Missing input: {input_path}")

    rows = read_csv(input_path)
    input_errors = validate_input(rows, args.expected_count)
    if input_errors:
        raise SystemExit("Input validation failed: " + "; ".join(input_errors[:20]))

    backup_name = f"{BACKUP_PREFIX}_{now_stamp()}"
    updated_rows: list[dict[str, Any]] = []
    not_updated_rows: list[dict[str, Any]] = []
    counts_before: dict[str, int | None] = {}
    counts_after: dict[str, int | None] = {}
    changed_counts: dict[str, int] = {}
    backup_count = 0

    conn = connect_db()
    try:
        with conn:
            with conn.cursor() as cur:
                existing_cols = get_main_columns(cur)
                required_cols = {"id", "nombre", "web", "url_listado", "diagnostic_status", "scraping_readiness", "exclude_from_scraping"}
                missing_required = sorted(required_cols - existing_cols)
                if missing_required:
                    raise RuntimeError(f"missing_required_columns={','.join(missing_required)}")

                counts_before = snapshot_counts(cur)
                create_temp_candidates(cur, rows)
                db_errors = db_precheck(cur, args.expected_count)
                if db_errors:
                    raise RuntimeError("DB precheck failed: " + "; ".join(db_errors[:20]))

                backup_count = create_backup(cur, backup_name, args.expected_count, existing_cols)
                updated_rows = run_update(cur)
                not_updated_rows = collect_not_updated(cur)
                counts_after = snapshot_counts(cur)
                changed_counts = changed_columns_counts(cur, backup_name, existing_cols)

                changed_errors = {k: v for k, v in changed_counts.items() if v not in (0, -1)}
                if len(updated_rows) != args.expected_count:
                    raise RuntimeError(f"updated_count_expected_{args.expected_count}_got_{len(updated_rows)}")
                if not_updated_rows:
                    raise RuntimeError(f"not_updated_rows={len(not_updated_rows)}")
                if changed_errors:
                    raise RuntimeError(f"prohibited_columns_changed={changed_errors}")
                if counts_before != counts_after:
                    raise RuntimeError(f"protected_table_counts_changed before={counts_before} after={counts_after}")

        write_reports(out, backup_name, args.expected_count, backup_count, updated_rows, not_updated_rows, counts_before, counts_after, changed_counts)
    finally:
        conn.close()

    print(f"backup_table=public.{backup_name}")
    print(f"expected={args.expected_count}")
    print(f"updated={len(updated_rows)}")
    print(f"not_updated={len(not_updated_rows)}")
    print(f"out={out}")
    print("scraping_productivo=0")
    print("publish=0")
    print("runs=0")
    print("push_deploy_frontend=0")


if __name__ == "__main__":
    main()
