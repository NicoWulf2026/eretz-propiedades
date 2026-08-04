#!/usr/bin/env python3
"""Preflight or apply the deterministic historical property FK repair."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import psycopg
from dotenv import load_dotenv
from psycopg import sql
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_AUDIT = ROOT / "_scratch/codex_autonomous_scraping/prior_fk_write_audit.csv"
DEFAULT_OUT = ROOT / "_scratch/codex_autonomous_scraping/historical_fk_repair"
PROTECTED_RELATIONS = (
    "public.inmobiliarias_main",
    "public.scraping_runs",
    "public.scraping_run_items",
    "public.publish_queue",
    "internal_scraping.publish_queue",
    "internal_scraping.propiedades_raw",
    "internal_scraping.propiedades_staging",
)
CANDIDATE_FIELDS = (
    "property_id",
    "fuente_extraccion",
    "current_inmobiliaria_id",
    "expected_inmobiliaria_id",
    "source_name",
    "actual_agency_name",
    "expected_agency_name",
    "url",
    "property_domain",
    "expected_domains",
    "mapping_type",
    "confidence",
    "name_compatible",
    "domain_compatible",
    "exact_url_conflict",
    "normalized_url_conflict",
    "hash_conflict",
    "target_set_duplicate",
    "classification",
)


def _load_db_url() -> str:
    load_dotenv(ROOT / ".env", override=False)
    value = os.getenv("SUPABASE_DATABASE_URL", "") or os.getenv("INTERNAL_DB_URL", "")
    if not value:
        raise RuntimeError("INTERNAL_DB_URL is not configured")
    return value


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _normalized(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = text.encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", ascii_text).strip()


def _domain(value: Any) -> str:
    try:
        return urlparse(str(value or "")).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _compatible_name(source_name: Any, agency_name: Any) -> bool:
    source = _normalized(source_name)
    agency = _normalized(agency_name)
    return bool(source and agency and (source == agency or source in agency or agency in source))


def _compatible_domain(property_url: Any, agency: dict[str, Any]) -> tuple[bool, set[str]]:
    property_domain = _domain(property_url)
    agency_domains = {_domain(agency.get("web")), _domain(agency.get("url_listado"))} - {""}
    compatible = bool(
        property_domain
        and any(
            property_domain == domain
            or property_domain.endswith("." + domain)
            or domain.endswith("." + property_domain)
            for domain in agency_domains
        )
    )
    return compatible, agency_domains


def _mapping_values(groups: list[dict[str, str]]) -> tuple[sql.SQL, list[Any]]:
    placeholders = sql.SQL(",").join(sql.SQL("(%s,%s,%s)") for _ in groups)
    params: list[Any] = []
    for group in groups:
        params.extend((
            group["manifest_slug"],
            int(group["actual_inmobiliaria_id"]),
            int(group["expected_inmobiliaria_id"]),
        ))
    return placeholders, params


def _fetch_candidates(cursor: Any, groups: list[dict[str, str]]) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    placeholders, params = _mapping_values(groups)
    cursor.execute(
        "SELECT id, nombre, web, url_listado FROM public.inmobiliarias_main ORDER BY id"
    )
    agencies = {int(row["id"]): dict(row) for row in cursor.fetchall()}
    cursor.execute(
        sql.SQL(
            """
            WITH mappings(slug, actual_id, expected_id) AS (VALUES {})
            SELECT p.id AS property_id, p.inmobiliaria_id AS current_inmobiliaria_id,
                   p.fuente_extraccion, p.url, p.url_normalizada, p.hash_dedup,
                   mappings.expected_id AS expected_inmobiliaria_id,
                   EXISTS (
                       SELECT 1 FROM public.propiedades q
                       WHERE q.id <> p.id AND q.inmobiliaria_id = mappings.expected_id
                         AND p.url IS NOT NULL AND p.url <> '' AND q.url = p.url
                   ) AS exact_url_conflict,
                   EXISTS (
                       SELECT 1 FROM public.propiedades q
                       WHERE q.id <> p.id AND q.inmobiliaria_id = mappings.expected_id
                         AND p.url_normalizada IS NOT NULL AND p.url_normalizada <> ''
                         AND q.url_normalizada = p.url_normalizada
                   ) AS normalized_url_conflict,
                   EXISTS (
                       SELECT 1 FROM public.propiedades q
                       WHERE q.id <> p.id AND p.hash_dedup IS NOT NULL AND p.hash_dedup <> ''
                         AND q.hash_dedup = p.hash_dedup
                   ) AS hash_conflict
            FROM public.propiedades p
            JOIN mappings
              ON p.fuente_extraccion = mappings.slug
             AND p.inmobiliaria_id = mappings.actual_id
            ORDER BY p.id
            """
        ).format(placeholders),
        params,
    )
    return [dict(row) for row in cursor.fetchall()], agencies


def _classify(
    raw: list[dict[str, Any]],
    groups: list[dict[str, str]],
    agencies: dict[int, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    source_by_key = {
        (group["manifest_slug"], int(group["expected_inmobiliaria_id"])): group
        for group in groups
    }
    target_key_counts = Counter(
        (row["expected_inmobiliaria_id"], row.get("url") or "")
        for row in raw if row.get("url")
    )
    candidates: list[dict[str, Any]] = []
    safe: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    for row in raw:
        expected_id = int(row["expected_inmobiliaria_id"])
        current_id = int(row["current_inmobiliaria_id"])
        group = source_by_key[(str(row["fuente_extraccion"]), expected_id)]
        expected = agencies.get(expected_id, {})
        actual = agencies.get(current_id, {})
        name_ok = _compatible_name(group.get("source_name"), expected.get("nombre"))
        domain_ok, expected_domains = _compatible_domain(row.get("url"), expected)
        target_set_duplicate = bool(
            row.get("url") and target_key_counts[(expected_id, row["url"])] > 1
        )
        conflicts = bool(
            row["exact_url_conflict"]
            or row["normalized_url_conflict"]
            or row["hash_conflict"]
            or target_set_duplicate
        )
        deterministic = bool(
            expected and actual and expected_id != current_id and name_ok and not conflicts
        )
        if deterministic:
            classification = "deterministic_safe"
            confidence = "deterministic"
        elif conflicts:
            classification = "blocked_duplicate_at_target"
            confidence = "ambiguous"
        elif not name_ok:
            classification = "blocked_identity_mismatch"
            confidence = "ambiguous"
        else:
            classification = "blocked_incomplete_mapping"
            confidence = "ambiguous"
        record = {
            "property_id": row["property_id"],
            "fuente_extraccion": row["fuente_extraccion"],
            "current_inmobiliaria_id": current_id,
            "expected_inmobiliaria_id": expected_id,
            "source_name": group.get("source_name", ""),
            "actual_agency_name": actual.get("nombre", ""),
            "expected_agency_name": expected.get("nombre", ""),
            "url": row.get("url") or "",
            "property_domain": _domain(row.get("url")),
            "expected_domains": ";".join(sorted(expected_domains)),
            "mapping_type": "unique_manifest_slug_to_canonical_id",
            "confidence": confidence,
            "name_compatible": name_ok,
            "domain_compatible": domain_ok,
            "exact_url_conflict": row["exact_url_conflict"],
            "normalized_url_conflict": row["normalized_url_conflict"],
            "hash_conflict": row["hash_conflict"],
            "target_set_duplicate": target_set_duplicate,
            "classification": classification,
        }
        candidates.append(record)
        (safe if deterministic else ambiguous).append(record)
    return candidates, safe, ambiguous


def _relation_counts(cursor: Any) -> dict[str, int | None]:
    result: dict[str, int | None] = {}
    for relation in PROTECTED_RELATIONS:
        cursor.execute("SELECT to_regclass(%s)::text AS relation", (relation,))
        if not cursor.fetchone()["relation"]:
            result[relation] = None
            continue
        cursor.execute(sql.SQL("SELECT count(*)::bigint AS n FROM {}").format(
            sql.SQL(".").join(sql.Identifier(part) for part in relation.split("."))
        ))
        result[relation] = cursor.fetchone()["n"]
    return result


def _preview_sql(path: Path, safe: list[dict[str, Any]]) -> None:
    lines = [
        "-- DRY RUN ONLY",
        "-- Historical FK deterministic safe set",
        "-- Updates only public.propiedades.inmobiliaria_id",
        "WITH mapping(property_id, old_inmobiliaria_id, new_inmobiliaria_id) AS (",
        "  VALUES",
    ]
    for index, row in enumerate(safe):
        comma = "," if index < len(safe) - 1 else ""
        lines.append(
            f"    ({int(row['property_id'])}, {int(row['current_inmobiliaria_id'])}, "
            f"{int(row['expected_inmobiliaria_id'])}){comma}"
        )
    lines.extend([
        ")",
        "UPDATE public.propiedades AS p",
        "SET inmobiliaria_id = mapping.new_inmobiliaria_id",
        "FROM mapping",
        "WHERE p.id = mapping.property_id",
        "  AND p.inmobiliaria_id = mapping.old_inmobiliaria_id;",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_preflight(
    out: Path,
    candidates: list[dict[str, Any]],
    safe: list[dict[str, Any]],
    ambiguous: list[dict[str, Any]],
) -> None:
    _write_csv(out / "historical_fk_candidates.csv", candidates, CANDIDATE_FIELDS)
    _write_csv(out / "historical_fk_safe.csv", safe, CANDIDATE_FIELDS)
    _write_csv(out / "historical_fk_ambiguous.csv", ambiguous, CANDIDATE_FIELDS)
    _write_csv(out / "historical_fk_no_change.csv", [], CANDIDATE_FIELDS)
    _preview_sql(out / "update_preview.sql", safe)
    out.joinpath("backup_plan.md").write_text(
        "# Historical FK backup plan\n\n"
        "The apply phase must create a full-row `public.backup_propiedades_historical_fk_*` table "
        "inside the same transaction before updating. The closed safe IDs, old FK and proposed FK "
        "are revalidated under row locks. If backup count or any safety gate differs, the transaction rolls back.\n",
        encoding="utf-8",
    )
    out.joinpath("rollback.sql").write_text(
        "-- Generated with the exact backup table name only after a successful apply.\n",
        encoding="utf-8",
    )
    out.joinpath("post_validation.md").write_text(
        "# Historical FK repair preflight\n\n"
        f"- Candidates: {len(candidates)}\n"
        f"- Deterministic safe: {len(safe)}\n"
        f"- Ambiguous or duplicate-at-target: {len(ambiguous)}\n"
        "- DB writes: 0\n"
        "- UPDATE executed: no\n",
        encoding="utf-8",
    )


def _copy_safe(cursor: Any, safe: list[dict[str, Any]]) -> None:
    cursor.execute(
        "CREATE TEMP TABLE fk_safe ("
        "property_id bigint PRIMARY KEY, old_id integer NOT NULL, new_id integer NOT NULL"
        ") ON COMMIT DROP"
    )
    with cursor.copy("COPY fk_safe (property_id, old_id, new_id) FROM STDIN") as copy:
        for row in safe:
            copy.write_row((
                int(row["property_id"]),
                int(row["current_inmobiliaria_id"]),
                int(row["expected_inmobiliaria_id"]),
            ))


def _apply(out: Path, groups: list[dict[str, str]]) -> dict[str, Any]:
    safe_csv = _read_csv(out / "historical_fk_safe.csv")
    if not safe_csv:
        raise RuntimeError("The safe set is empty")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_name = f"backup_propiedades_historical_fk_{timestamp}"
    with psycopg.connect(_load_db_url(), row_factory=dict_row, connect_timeout=60) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '30s'")
            cursor.execute("SET LOCAL statement_timeout = '15min'")
            live_raw, agencies = _fetch_candidates(cursor, groups)
            _, live_safe, _ = _classify(live_raw, groups, agencies)
            csv_triples = sorted(
                (int(row["property_id"]), int(row["current_inmobiliaria_id"]), int(row["expected_inmobiliaria_id"]))
                for row in safe_csv
            )
            live_triples = sorted(
                (int(row["property_id"]), int(row["current_inmobiliaria_id"]), int(row["expected_inmobiliaria_id"]))
                for row in live_safe
            )
            if csv_triples != live_triples:
                raise RuntimeError("Live deterministic set drifted from the closed CSV safe set")
            before_relations = _relation_counts(cursor)
            cursor.execute("SELECT count(*)::bigint AS n FROM public.propiedades")
            properties_before = cursor.fetchone()["n"]
            _copy_safe(cursor, live_safe)
            cursor.execute(
                """
                SELECT p.id
                FROM public.propiedades p
                JOIN fk_safe s ON s.property_id = p.id
                WHERE p.inmobiliaria_id = s.old_id
                ORDER BY p.id
                FOR UPDATE OF p
                """
            )
            locked_rows = cursor.fetchall()
            if len(locked_rows) != len(live_safe):
                raise RuntimeError(
                    f"Locked row count drift: {len(locked_rows)} != {len(live_safe)}"
                )
            cursor.execute(
                """
                SELECT count(*)::int AS n
                FROM fk_safe s
                JOIN public.propiedades p ON p.id = s.property_id
                WHERE p.inmobiliaria_id = s.old_id
                  AND NOT EXISTS (
                      SELECT 1 FROM public.propiedades q
                      WHERE q.id <> p.id AND q.inmobiliaria_id = s.new_id
                        AND (
                            (p.url IS NOT NULL AND p.url <> '' AND q.url = p.url)
                            OR (p.url_normalizada IS NOT NULL AND p.url_normalizada <> ''
                                AND q.url_normalizada = p.url_normalizada)
                            OR (p.hash_dedup IS NOT NULL AND p.hash_dedup <> ''
                                AND q.hash_dedup = p.hash_dedup)
                        )
                  )
                """
            )
            locked_safe = cursor.fetchone()["n"]
            if locked_safe != len(live_safe):
                raise RuntimeError(f"In-transaction safe count drift: {locked_safe} != {len(live_safe)}")
            cursor.execute(
                sql.SQL(
                    "CREATE TABLE public.{} AS "
                    "SELECT p.*, s.new_id AS proposed_inmobiliaria_id, now() AS backup_created_at "
                    "FROM public.propiedades p JOIN fk_safe s ON s.property_id = p.id "
                    "ORDER BY p.id"
                ).format(sql.Identifier(backup_name))
            )
            cursor.execute(sql.SQL("SELECT count(*)::int AS n FROM public.{}").format(sql.Identifier(backup_name)))
            backup_count = cursor.fetchone()["n"]
            if backup_count != len(live_safe):
                raise RuntimeError(f"Backup count mismatch: {backup_count} != {len(live_safe)}")
            # The table's generic BEFORE UPDATE trigger mutates updated_at. Keep it
            # session-local and disabled so the final row differs only by its FK.
            cursor.execute("SET LOCAL session_replication_role = 'replica'")
            cursor.execute(
                """
                UPDATE public.propiedades p
                SET inmobiliaria_id = s.new_id
                FROM fk_safe s
                WHERE p.id = s.property_id AND p.inmobiliaria_id = s.old_id
                """
            )
            updated = cursor.rowcount
            if updated != len(live_safe):
                raise RuntimeError(f"UPDATE count mismatch: {updated} != {len(live_safe)}")
            cursor.execute("SET LOCAL session_replication_role = 'origin'")
            cursor.execute(
                sql.SQL(
                    "SELECT count(*)::int AS n FROM public.propiedades p "
                    "JOIN public.{} b ON b.id = p.id "
                    "WHERE p.inmobiliaria_id = b.proposed_inmobiliaria_id "
                    "AND (to_jsonb(p) - 'inmobiliaria_id') = "
                    "(to_jsonb(b) - 'inmobiliaria_id' - 'proposed_inmobiliaria_id' - 'backup_created_at')"
                ).format(sql.Identifier(backup_name))
            )
            exact_rows = cursor.fetchone()["n"]
            if exact_rows != updated:
                raise RuntimeError(f"Non-FK column drift detected: {exact_rows} != {updated}")
            cursor.execute(
                """
                SELECT count(*)::int AS n FROM (
                    SELECT p.inmobiliaria_id, p.url
                    FROM public.propiedades p JOIN fk_safe s ON s.property_id = p.id
                    WHERE p.url IS NOT NULL AND p.url <> ''
                    GROUP BY p.inmobiliaria_id, p.url HAVING count(*) > 1
                ) d
                """
            )
            duplicate_groups = cursor.fetchone()["n"]
            if duplicate_groups:
                raise RuntimeError(f"FK repair would leave {duplicate_groups} duplicate target groups")
            cursor.execute("SELECT count(*)::bigint AS n FROM public.propiedades")
            properties_after = cursor.fetchone()["n"]
            after_relations = _relation_counts(cursor)
            if properties_before != properties_after or before_relations != after_relations:
                raise RuntimeError("Protected relation count drift detected")
        conn.commit()

    rollback = (
        "-- ROLLBACK PREVIEW - DO NOT EXECUTE WITHOUT EXPLICIT AUTHORIZATION\n"
        "BEGIN;\n"
        "UPDATE public.propiedades p\n"
        "SET inmobiliaria_id = b.inmobiliaria_id\n"
        f"FROM public.{backup_name} b\n"
        "WHERE p.id = b.id AND p.inmobiliaria_id = b.proposed_inmobiliaria_id;\n"
        "COMMIT;\n"
    )
    out.joinpath("rollback.sql").write_text(rollback, encoding="utf-8")
    result = {
        "backup_table": f"public.{backup_name}",
        "safe_rows": len(live_safe),
        "updated_rows": updated,
        "non_fk_exact_rows": exact_rows,
        "duplicate_groups_created": duplicate_groups,
        "properties_before": properties_before,
        "properties_after": properties_after,
        "protected_relations_unchanged": before_relations == after_relations,
    }
    out.joinpath("post_validation.md").write_text(
        "# Historical FK repair post-validation\n\n"
        f"- Backup: `{result['backup_table']}`\n"
        f"- Safe rows: {result['safe_rows']}\n"
        f"- Updated rows: {result['updated_rows']}\n"
        f"- Rows with all non-FK columns unchanged: {result['non_fk_exact_rows']}\n"
        f"- Duplicate target groups created: {result['duplicate_groups_created']}\n"
        f"- Properties before / after: {properties_before} / {properties_after}\n"
        f"- Protected relation counts unchanged: {result['protected_relations_unchanged']}\n"
        "- Transaction: committed\n",
        encoding="utf-8",
    )
    out.joinpath("backup_table_name.txt").write_text(result["backup_table"] + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--mode", choices=("preflight", "apply"), default="preflight")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    groups = _read_csv(args.audit)
    if len(groups) != 331 or len({row["manifest_slug"] for row in groups}) != 331:
        raise RuntimeError("Historical audit must contain 331 unique source mappings")

    if args.mode == "apply":
        result = _apply(args.out, groups)
        print(json.dumps(result, ensure_ascii=False))
        return 0

    with psycopg.connect(_load_db_url(), row_factory=dict_row, connect_timeout=60) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            raw, agencies = _fetch_candidates(cursor, groups)
    candidates, safe, ambiguous = _classify(raw, groups, agencies)
    _write_preflight(args.out, candidates, safe, ambiguous)
    print(json.dumps({
        "candidates": len(candidates),
        "safe": len(safe),
        "ambiguous": len(ambiguous),
        "db_writes": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
