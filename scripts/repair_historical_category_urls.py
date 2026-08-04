#!/usr/bin/env python3
"""Audit or remove historical operation-category rows from public.propiedades.

The apply path is fail-closed: it accepts only the exact preflight ID set,
requires zero dependent rows, creates a full-row backup in the same
transaction, deletes by explicit primary key, and writes a reproducible
rollback statement after commit.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv
from psycopg import sql
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "_scratch/backend_final_closure/HISTORICAL_DEBT"
APPLY_CONFIRMATION = "HUMAN_APPROVED_BACKUP_PREFLIGHT_DELETE"
URL_PREDICATE = (
    "lower(regexp_replace(coalesce(url, ''), '[?#].*$', '')) "
    "~ '/properties/operation/(forsale|forrent)/?$'"
)
EVIDENCE_FIELDS = (
    "id",
    "inmobiliaria_id",
    "fuente_extraccion",
    "url",
    "url_normalizada",
    "titulo",
    "descripcion",
    "id_externo",
    "hash_dedup",
    "created_at",
    "dependency_count",
    "classification",
)


def db_url() -> str:
    load_dotenv(ROOT / ".env", override=False)
    value = os.getenv("SUPABASE_DATABASE_URL", "")
    if not value:
        raise RuntimeError("SUPABASE_DATABASE_URL is not configured")
    return value


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EVIDENCE_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_preflight(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def foreign_keys(cursor: Any) -> list[dict[str, Any]]:
    cursor.execute(
        """
        SELECT tc.table_schema, tc.table_name, kcu.column_name, rc.delete_rule
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON kcu.constraint_schema = tc.constraint_schema
         AND kcu.constraint_name = tc.constraint_name
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_schema = tc.constraint_schema
         AND ccu.constraint_name = tc.constraint_name
        JOIN information_schema.referential_constraints rc
          ON rc.constraint_schema = tc.constraint_schema
         AND rc.constraint_name = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND ccu.table_schema = 'public'
          AND ccu.table_name = 'propiedades'
          AND ccu.column_name = 'id'
        ORDER BY tc.table_schema, tc.table_name, kcu.column_name
        """
    )
    return [dict(row) for row in cursor.fetchall()]


def fetch_rows(cursor: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cursor.execute(
        f"""
        SELECT id, inmobiliaria_id, fuente_extraccion, url, url_normalizada,
               titulo, descripcion, id_externo, hash_dedup, created_at
        FROM public.propiedades
        WHERE {URL_PREDICATE}
        ORDER BY id
        """
    )
    rows = [dict(row) for row in cursor.fetchall()]
    ids = [int(row["id"]) for row in rows]
    dependencies: list[dict[str, Any]] = []
    by_id = {row_id: 0 for row_id in ids}
    if ids:
        for fk in foreign_keys(cursor):
            relation = sql.Identifier(fk["table_schema"], fk["table_name"])
            column = sql.Identifier(fk["column_name"])
            cursor.execute(
                sql.SQL(
                    "SELECT {}::bigint AS property_id, count(*)::int AS n "
                    "FROM {} WHERE {} = ANY(%s) GROUP BY {} ORDER BY {}"
                ).format(column, relation, column, column, column),
                (ids,),
            )
            counts = {int(row["property_id"]): int(row["n"]) for row in cursor.fetchall()}
            for row_id in ids:
                count = counts.get(row_id, 0)
                by_id[row_id] += count
                dependencies.append(
                    {
                        "property_id": row_id,
                        "table_schema": fk["table_schema"],
                        "table_name": fk["table_name"],
                        "column_name": fk["column_name"],
                        "delete_rule": fk["delete_rule"],
                        "dependency_count": count,
                    }
                )
    for row in rows:
        row["dependency_count"] = by_id[int(row["id"])]
        row["classification"] = (
            "SAFE_AUTOMATIC_FIX"
            if row["dependency_count"] == 0
            and str(row.get("titulo") or "").strip().casefold() in {"", "sin título", "sin titulo"}
            else "AMBIGUOUS"
        )
    return rows, dependencies


def render_explicit_delete(ids: list[int]) -> str:
    if not ids:
        return "-- Empty deterministic set; no DELETE is permitted.\n"
    values = ", ".join(str(value) for value in ids)
    return (
        "-- PREVIEW ONLY. The executable path revalidates the closed ID set.\n"
        "BEGIN;\n"
        f"DELETE FROM public.propiedades WHERE id IN ({values});\n"
        "COMMIT;\n"
    )


def validate_apply_authorization(mode: str, confirmation: str | None) -> None:
    """Require a deliberate second factor before the destructive apply path."""
    if mode == "apply" and confirmation != APPLY_CONFIRMATION:
        raise RuntimeError(
            "Destructive apply refused: specific human approval, backup and "
            f"preflight are required; pass --confirm-apply {APPLY_CONFIRMATION}"
        )


def preflight(out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    with psycopg.connect(db_url(), row_factory=dict_row, connect_timeout=60) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        with conn.cursor() as cursor:
            rows, dependencies = fetch_rows(cursor)
    safe = [row for row in rows if row["classification"] == "SAFE_AUTOMATIC_FIX"]
    ambiguous = [row for row in rows if row["classification"] != "SAFE_AUTOMATIC_FIX"]
    write_csv(out / "batch017_invalid_rows.csv", rows)
    write_csv(out / "batch017_deterministic_rows.csv", safe)
    write_csv(out / "batch017_ambiguous_rows.csv", ambiguous)
    dep_fields = (
        "property_id",
        "table_schema",
        "table_name",
        "column_name",
        "delete_rule",
        "dependency_count",
    )
    with (out / "batch017_dependency_audit.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=dep_fields)
        writer.writeheader()
        writer.writerows(dependencies)
    ids = [int(row["id"]) for row in safe]
    (out / "batch017_cleanup.sql").write_text(render_explicit_delete(ids), encoding="utf-8")
    (out / "batch017_backup.sql").write_text(
        "-- Backup is created transactionally by this script's --mode apply path.\n"
        "-- The generated table contains the full live rows plus backup_created_at.\n",
        encoding="utf-8",
    )
    (out / "batch017_rollback.sql").write_text(
        "-- Generated with the exact backup relation after a successful apply.\n",
        encoding="utf-8",
    )
    (out / "batch017_evidence.md").write_text(
        "# Historical operation-category URL evidence\n\n"
        f"- Recalculated live universe: {len(rows)}\n"
        f"- Deterministic invalid rows: {len(safe)}\n"
        f"- Ambiguous rows: {len(ambiguous)}\n"
        f"- Rows with dependencies: {sum(bool(row['dependency_count']) for row in rows)}\n"
        "- URL rule: exact `/properties/operation/forSale|forRent` operation route.\n"
        "- All deterministic rows have a blank or `Sin título` fallback title.\n"
        "- Current parser guard: `tests/test_parser_detail_url_candidates.py::test_reject_operation_category_routes`.\n"
        "- DB writes during preflight: 0.\n",
        encoding="utf-8",
    )
    result = {
        "detected": len(rows),
        "deterministic": len(safe),
        "ambiguous": len(ambiguous),
        "dependencies": sum(int(row["dependency_count"]) for row in rows),
        "db_writes": 0,
    }
    (out / "batch017_preflight.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def apply(out: Path) -> dict[str, Any]:
    closed = read_preflight(out / "batch017_deterministic_rows.csv")
    closed_ids = sorted(int(row["id"]) for row in closed)
    if not closed_ids:
        raise RuntimeError("The deterministic preflight set is empty")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_name = f"backup_propiedades_category_urls_{timestamp}"
    with psycopg.connect(db_url(), row_factory=dict_row, connect_timeout=60) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '30s'")
            cursor.execute("SET LOCAL statement_timeout = '15min'")
            live_rows, _ = fetch_rows(cursor)
            live_safe = [
                row for row in live_rows if row["classification"] == "SAFE_AUTOMATIC_FIX"
            ]
            live_ids = sorted(int(row["id"]) for row in live_safe)
            if live_ids != closed_ids:
                raise RuntimeError("Live deterministic set drifted from the closed preflight")
            if any(int(row["dependency_count"]) for row in live_safe):
                raise RuntimeError("Dependent rows detected; refusing DELETE")
            cursor.execute(
                "SELECT count(*)::bigint AS n FROM public.propiedades"
            )
            before = int(cursor.fetchone()["n"])
            cursor.execute(
                "SELECT id FROM public.propiedades WHERE id = ANY(%s) ORDER BY id FOR UPDATE",
                (closed_ids,),
            )
            if [int(row["id"]) for row in cursor.fetchall()] != closed_ids:
                raise RuntimeError("Could not lock the entire deterministic set")
            cursor.execute(
                sql.SQL(
                    "CREATE TABLE public.{} AS "
                    "SELECT p.*, now() AS backup_created_at "
                    "FROM public.propiedades p WHERE p.id = ANY(%s) ORDER BY p.id"
                ).format(sql.Identifier(backup_name)),
                (closed_ids,),
            )
            cursor.execute(
                sql.SQL("SELECT count(*)::int AS n FROM public.{}").format(
                    sql.Identifier(backup_name)
                )
            )
            backup_count = int(cursor.fetchone()["n"])
            if backup_count != len(closed_ids):
                raise RuntimeError("Backup count mismatch")
            cursor.execute(
                "DELETE FROM public.propiedades WHERE id = ANY(%s)", (closed_ids,)
            )
            deleted = cursor.rowcount
            if deleted != len(closed_ids):
                raise RuntimeError("DELETE count mismatch")
            cursor.execute(
                f"SELECT count(*)::int AS n FROM public.propiedades WHERE {URL_PREDICATE}"
            )
            remaining = int(cursor.fetchone()["n"])
            if remaining:
                raise RuntimeError(f"Operation-category rows remain: {remaining}")
            cursor.execute(
                "SELECT count(*)::bigint AS n FROM public.propiedades"
            )
            after = int(cursor.fetchone()["n"])
            if before - after != deleted:
                raise RuntimeError("Property count delta mismatch")
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'propiedades'
                ORDER BY ordinal_position
                """
            )
            columns = [row["column_name"] for row in cursor.fetchall()]
        conn.commit()
    column_sql = ", ".join(f'"{name}"' for name in columns)
    rollback = (
        "-- ROLLBACK PREVIEW - execute only after an explicit review\n"
        "BEGIN;\n"
        f"INSERT INTO public.propiedades ({column_sql})\n"
        f"SELECT {column_sql} FROM public.{backup_name} b\n"
        "WHERE NOT EXISTS (SELECT 1 FROM public.propiedades p WHERE p.id = b.id);\n"
        "COMMIT;\n"
    )
    (out / "batch017_rollback.sql").write_text(rollback, encoding="utf-8")
    result = {
        "backup_table": f"public.{backup_name}",
        "detected": len(closed_ids),
        "backup_rows": backup_count,
        "deleted": deleted,
        "remaining": remaining,
        "properties_before": before,
        "properties_after": after,
    }
    (out / "batch017_post_audit.md").write_text(
        "# Batch017 historical invalid-row post-audit\n\n"
        f"- Backup: `{result['backup_table']}`\n"
        f"- Recalculated deterministic rows: {result['detected']}\n"
        f"- Backup rows: {result['backup_rows']}\n"
        f"- Rows deleted by explicit ID: {result['deleted']}\n"
        f"- Matching operation-category rows remaining: {result['remaining']}\n"
        f"- Properties before / after: {before} / {after}\n"
        "- Valid rows affected: 0\n"
        "- Dependency drift: 0\n"
        "- Transaction: committed\n"
        "- Verdict: PASS\n",
        encoding="utf-8",
    )
    (out / "batch017_apply_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--mode", choices=("preflight", "apply"), default="preflight")
    parser.add_argument("--confirm-apply")
    args = parser.parse_args()
    validate_apply_authorization(args.mode, args.confirm_apply)
    result = preflight(args.out) if args.mode == "preflight" else apply(args.out)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
