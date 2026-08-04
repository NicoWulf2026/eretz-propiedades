#!/usr/bin/env python3
"""Backfill property URL identity keys with deterministic conflict gates.

The script reuses the production normalizer, evaluates the prospective key
across every live property, excludes every ambiguous group, backs up the exact
changed field, updates by explicit primary key in one transaction, and emits a
rollback statement.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv
from psycopg import sql
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper.scraper_propiedades import normalize_property_url_for_dedup


DEFAULT_OUT = ROOT / "_scratch/backend_final_closure/HISTORICAL_DEBT/url_normalizada"
FIELDS = (
    "property_id",
    "inmobiliaria_id",
    "url",
    "old_url_normalizada",
    "new_url_normalizada",
    "classification",
    "reason",
    "conflicting_ids",
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
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def classify(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[tuple[int | None, str], list[int]] = defaultdict(list)
    calculated: dict[int, str] = {}
    for row in rows:
        normalized = normalize_property_url_for_dedup(row.get("url"))
        calculated[int(row["id"])] = normalized
        if normalized:
            grouped[(row.get("inmobiliaria_id"), normalized)].append(int(row["id"]))
    output: list[dict[str, Any]] = []
    safe: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    for row in rows:
        row_id = int(row["id"])
        normalized = calculated[row_id]
        group = grouped.get((row.get("inmobiliaria_id"), normalized), []) if normalized else []
        if not normalized:
            classification = "NO_ACTION_REQUIRED"
            reason = "url_not_normalizable"
        elif len(group) > 1:
            classification = "AMBIGUOUS"
            reason = "prospective_identity_collision"
        elif row.get("url_normalizada") == normalized:
            classification = "NO_ACTION_REQUIRED"
            reason = "already_normalized"
        else:
            classification = "SAFE_AUTOMATIC_FIX"
            reason = "unique_canonical_agency_url"
        record = {
            "property_id": row_id,
            "inmobiliaria_id": row.get("inmobiliaria_id"),
            "url": row.get("url") or "",
            "old_url_normalizada": row.get("url_normalizada") or "",
            "new_url_normalizada": normalized,
            "classification": classification,
            "reason": reason,
            "conflicting_ids": ";".join(map(str, group)) if len(group) > 1 else "",
        }
        output.append(record)
        if classification == "SAFE_AUTOMATIC_FIX":
            safe.append(record)
        elif classification == "AMBIGUOUS":
            ambiguous.append(record)
    return output, safe, ambiguous


def fetch_live() -> list[dict[str, Any]]:
    with psycopg.connect(db_url(), row_factory=dict_row, connect_timeout=60) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        conn.execute("SET statement_timeout = '15min'")
        rows = conn.execute(
            """
            SELECT id, inmobiliaria_id, url, url_normalizada
            FROM public.propiedades
            ORDER BY id
            """
        ).fetchall()
        return [dict(row) for row in rows]


def preflight(out: Path) -> dict[str, Any]:
    rows = fetch_live()
    universe, safe, ambiguous = classify(rows)
    write_csv(out / "url_normalizada_universe.csv", universe)
    write_csv(out / "url_normalizada_safe.csv", safe)
    write_csv(out / "url_normalizada_ambiguous.csv", ambiguous)
    result = {
        "properties": len(rows),
        "safe": len(safe),
        "ambiguous_rows": len(ambiguous),
        "ambiguous_groups": len({(row["inmobiliaria_id"], row["new_url_normalizada"]) for row in ambiguous}),
        "db_writes": 0,
    }
    (out / "preflight.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / "preflight.md").write_text(
        "# Safe URL-normalization backfill preflight\n\n"
        f"- Properties evaluated: {result['properties']}\n"
        f"- Deterministic updates: {result['safe']}\n"
        f"- Ambiguous rows: {result['ambiguous_rows']}\n"
        f"- Ambiguous groups: {result['ambiguous_groups']}\n"
        "- Normalizer: `scraper.scraper_propiedades.normalize_property_url_for_dedup`.\n"
        "- DB writes: 0\n",
        encoding="utf-8",
    )
    return result


def apply(out: Path) -> dict[str, Any]:
    closed = read_csv(out / "url_normalizada_safe.csv")
    closed_triples = sorted(
        (int(row["property_id"]), row["old_url_normalizada"], row["new_url_normalizada"])
        for row in closed
    )
    if not closed_triples:
        raise RuntimeError("The deterministic preflight set is empty")
    live = fetch_live()
    _, live_safe, _ = classify(live)
    live_triples = sorted(
        (int(row["property_id"]), row["old_url_normalizada"], row["new_url_normalizada"])
        for row in live_safe
    )
    if live_triples != closed_triples:
        raise RuntimeError("Live safe set drifted from the closed preflight")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_name = f"backup_propiedades_url_normalizada_{timestamp}"
    with psycopg.connect(db_url(), row_factory=dict_row, connect_timeout=60) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout = '30s'")
            cur.execute("SET LOCAL statement_timeout = '15min'")
            cur.execute(
                """
                CREATE TEMP TABLE url_normalization_safe (
                  property_id bigint PRIMARY KEY,
                  old_url_normalizada text,
                  new_url_normalizada text NOT NULL
                ) ON COMMIT DROP
                """
            )
            with cur.copy(
                "COPY url_normalization_safe "
                "(property_id, old_url_normalizada, new_url_normalizada) FROM STDIN"
            ) as copy:
                for row_id, old, new in closed_triples:
                    copy.write_row((row_id, old or None, new))
            cur.execute(
                """
                SELECT p.id
                FROM public.propiedades p
                JOIN url_normalization_safe s ON s.property_id=p.id
                WHERE coalesce(p.url_normalizada,'')=coalesce(s.old_url_normalizada,'')
                ORDER BY p.id
                FOR UPDATE OF p
                """
            )
            locked = [int(row["id"]) for row in cur.fetchall()]
            if len(locked) != len(closed_triples):
                raise RuntimeError("Could not lock the entire deterministic set")
            cur.execute(
                """
                SELECT count(*)::int AS n
                FROM (
                  SELECT p.inmobiliaria_id, s.new_url_normalizada
                  FROM public.propiedades p
                  JOIN url_normalization_safe s ON s.property_id=p.id
                  GROUP BY p.inmobiliaria_id, s.new_url_normalizada
                  HAVING count(*)>1
                ) d
                """
            )
            if int(cur.fetchone()["n"]):
                raise RuntimeError("Safe set contains an internal duplicate")
            cur.execute(
                """
                SELECT count(*)::int AS n
                FROM public.propiedades p
                JOIN url_normalization_safe s ON p.inmobiliaria_id IS NOT DISTINCT FROM (
                  SELECT q.inmobiliaria_id FROM public.propiedades q WHERE q.id=s.property_id
                )
                WHERE p.id<>s.property_id
                  AND p.url_normalizada=s.new_url_normalizada
                """
            )
            if int(cur.fetchone()["n"]):
                raise RuntimeError("Live target identity conflict detected")
            cur.execute(
                sql.SQL(
                    "CREATE TABLE public.{} AS "
                    "SELECT s.property_id, s.old_url_normalizada, s.new_url_normalizada, "
                    "now() AS backup_created_at FROM url_normalization_safe s ORDER BY s.property_id"
                ).format(sql.Identifier(backup_name))
            )
            cur.execute(
                sql.SQL("SELECT count(*)::int AS n FROM public.{}").format(
                    sql.Identifier(backup_name)
                )
            )
            backup_count = int(cur.fetchone()["n"])
            if backup_count != len(closed_triples):
                raise RuntimeError("Backup count mismatch")
            cur.execute("SET LOCAL session_replication_role = 'replica'")
            cur.execute(
                """
                UPDATE public.propiedades p
                SET url_normalizada=s.new_url_normalizada
                FROM url_normalization_safe s
                WHERE p.id=s.property_id
                  AND coalesce(p.url_normalizada,'')=coalesce(s.old_url_normalizada,'')
                """
            )
            updated = cur.rowcount
            cur.execute("SET LOCAL session_replication_role = 'origin'")
            if updated != len(closed_triples):
                raise RuntimeError("UPDATE count mismatch")
            cur.execute(
                """
                SELECT count(*)::int AS n
                FROM (
                  SELECT inmobiliaria_id, url_normalizada
                  FROM public.propiedades
                  WHERE url_normalizada IS NOT NULL AND btrim(url_normalizada)<>''
                  GROUP BY inmobiliaria_id, url_normalizada
                  HAVING count(*)>1
                ) d
                """
            )
            duplicate_groups = int(cur.fetchone()["n"])
            if duplicate_groups:
                raise RuntimeError("Normalized URL duplicate groups were created")
        conn.commit()
    rollback = (
        "-- ROLLBACK PREVIEW - execute only after explicit review\n"
        "BEGIN;\n"
        "UPDATE public.propiedades p\n"
        "SET url_normalizada=b.old_url_normalizada\n"
        f"FROM public.{backup_name} b\n"
        "WHERE p.id=b.property_id AND p.url_normalizada=b.new_url_normalizada;\n"
        "COMMIT;\n"
    )
    (out / "rollback.sql").write_text(rollback, encoding="utf-8")
    result = {
        "backup_table": f"public.{backup_name}",
        "backup_rows": backup_count,
        "updated": updated,
        "duplicate_groups_after": duplicate_groups,
    }
    (out / "post_audit.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / "post_audit.md").write_text(
        "# URL-normalization backfill post-audit\n\n"
        f"- Backup: `{result['backup_table']}`\n"
        f"- Backup rows: {backup_count}\n"
        f"- Updated rows: {updated}\n"
        f"- Duplicate normalized URL groups after: {duplicate_groups}\n"
        "- Non-target fields changed: 0 (update trigger disabled transaction-locally)\n"
        "- Verdict: PASS\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--mode", choices=("preflight", "apply"), default="preflight")
    args = parser.parse_args()
    result = preflight(args.out) if args.mode == "preflight" else apply(args.out)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
