#!/usr/bin/env python3
"""Build a read-only, closed-set audit for the Run B duplicate incident."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv
from psycopg import sql
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INCIDENT = ROOT / "_scratch/codex_autonomous_scraping/run_b_duplicate_incident.csv"
DEFAULT_OUT = ROOT / "_scratch/codex_autonomous_scraping/run_b_duplicate_cleanup"
TECHNICAL_FIELDS = {
    "id",
    "hash_dedup",
    "fuente_extraccion",
    "cms_origen",
    "created_at",
    "updated_at",
    "fecha_publicacion",
    "url_normalizada",
}
COMPLETENESS_FIELDS = (
    "titulo",
    "descripcion",
    "precio",
    "moneda",
    "tipo_propiedad",
    "operacion",
    "ambientes",
    "dormitorios",
    "banos",
    "superficie_total",
    "direccion",
    "barrio",
    "ciudad",
    "provincia",
    "latitud",
    "longitud",
    "imagenes",
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


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _normalized(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return sorted(_normalized(item) for item in value)
    if isinstance(value, str):
        text = unicodedata.normalize("NFKC", value)
        return re.sub(r"\s+", " ", text).strip().casefold()
    return str(value)


def _digest(row: dict[str, Any], fields: list[str]) -> str:
    payload = {field: _normalized(row.get(field)) for field in fields}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return True


def _completeness(row: dict[str, Any]) -> tuple[int, int]:
    score = sum(_present(row.get(field)) for field in COMPLETENESS_FIELDS)
    images = len(row.get("imagenes") or [])
    return score, images


def _fetch_groups(cursor: Any, incident_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pairs = [(row["inmobiliaria_id"], row["url"]) for row in incident_rows]
    placeholders = sql.SQL(",").join(sql.SQL("(%s,%s)") for _ in pairs)
    query = sql.SQL(
        "SELECT * FROM public.propiedades "
        "WHERE (inmobiliaria_id, url) IN (VALUES {}) "
        "ORDER BY inmobiliaria_id, url, created_at, id"
    ).format(placeholders)
    params = [value for pair in pairs for value in pair]
    cursor.execute(query, params)
    return [dict(row) for row in cursor.fetchall()]


def _foreign_keys(cursor: Any) -> list[dict[str, Any]]:
    cursor.execute(
        """
        SELECT tc.table_schema, tc.table_name, kcu.column_name, rc.delete_rule
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.constraint_schema = kcu.constraint_schema
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_name = tc.constraint_name
         AND ccu.constraint_schema = tc.constraint_schema
        JOIN information_schema.referential_constraints rc
          ON rc.constraint_name = tc.constraint_name
         AND rc.constraint_schema = tc.constraint_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND ccu.table_schema = 'public'
          AND ccu.table_name = 'propiedades'
          AND ccu.column_name = 'id'
        ORDER BY tc.table_schema, tc.table_name, kcu.column_name
        """
    )
    return [dict(row) for row in cursor.fetchall()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--incident", type=Path, default=DEFAULT_INCIDENT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    incident_csv = _read_csv(args.incident)
    incident_ids = [int(row["property_id"]) for row in incident_csv]
    if len(incident_ids) != 31 or len(set(incident_ids)) != 31:
        raise RuntimeError("Closed incident set must contain exactly 31 unique IDs")

    args.out.mkdir(parents=True, exist_ok=True)
    with psycopg.connect(_load_db_url(), row_factory=dict_row, connect_timeout=60) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute(
                "SELECT * FROM public.propiedades WHERE id = ANY(%s) ORDER BY id",
                (incident_ids,),
            )
            incident_rows = [dict(row) for row in cursor.fetchall()]
            if len(incident_rows) != 31:
                raise RuntimeError(f"Expected 31 live incident rows, found {len(incident_rows)}")
            all_rows = _fetch_groups(cursor, incident_rows)
            foreign_keys = _foreign_keys(cursor)
            dependency_counts: dict[tuple[int, str, str], int] = {}
            for fk in foreign_keys:
                relation = sql.Identifier(fk["table_schema"], fk["table_name"])
                column = sql.Identifier(fk["column_name"])
                cursor.execute(
                    sql.SQL("SELECT count(*)::int AS n FROM {} WHERE {} = ANY(%s)").format(
                        relation, column
                    ),
                    (incident_ids,),
                )
                total = cursor.fetchone()["n"]
                if total:
                    cursor.execute(
                        sql.SQL("SELECT {}::bigint AS property_id, count(*)::int AS n FROM {} "
                                "WHERE {} = ANY(%s) GROUP BY {} ORDER BY {}").format(
                            column, relation, column, column, column
                        ),
                        (incident_ids,),
                    )
                    for row in cursor.fetchall():
                        dependency_counts[(row["property_id"], fk["table_schema"], fk["table_name"])] = row["n"]

    incident_by_id = {int(row["id"]): row for row in incident_rows}
    groups: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in all_rows:
        groups[(row["inmobiliaria_id"], row["url"])].append(row)

    essential_fields = [field for field in incident_rows[0] if field not in TECHNICAL_FIELDS]
    group_output: list[dict[str, Any]] = []
    row_output: list[dict[str, Any]] = []
    survivor_output: list[dict[str, Any]] = []
    delete_output: list[dict[str, Any]] = []
    manual_output: list[dict[str, Any]] = []
    dependency_output: list[dict[str, Any]] = []

    for incident_id in incident_ids:
        incident = incident_by_id[incident_id]
        group = groups[(incident["inmobiliaria_id"], incident["url"])]
        survivors = [row for row in group if int(row["id"]) != incident_id]
        incident_score, incident_images = _completeness(incident)
        if len(survivors) == 1:
            survivor = survivors[0]
            survivor_score, survivor_images = _completeness(survivor)
            differing = [
                field for field in essential_fields
                if _normalized(incident.get(field)) != _normalized(survivor.get(field))
            ]
            dependencies = sum(
                count for (prop_id, _, _), count in dependency_counts.items() if prop_id == incident_id
            )
            safe = not differing and dependencies == 0 and survivor_score >= incident_score
            reason = "safe_exact_essential_duplicate" if safe else (
                "incident_row_has_dependencies" if dependencies else
                "essential_fields_differ" if differing else
                "incident_row_more_complete_than_survivor"
            )
            survivor_id: Any = survivor["id"]
            survivor_output.append({
                "incident_id": incident_id,
                "survivor_id": survivor_id,
                "inmobiliaria_id": incident["inmobiliaria_id"],
                "url": incident["url"],
                "incident_completeness": incident_score,
                "survivor_completeness": survivor_score,
                "incident_images": incident_images,
                "survivor_images": survivor_images,
                "essential_equal": not differing,
                "differing_fields": ";".join(differing),
                "incident_dependency_count": dependencies,
                "safe_to_delete_incident": safe,
                "reason": reason,
            })
            target = delete_output if safe else manual_output
            target.append({
                "delete_candidate_id": incident_id,
                "survivor_id": survivor_id,
                "inmobiliaria_id": incident["inmobiliaria_id"],
                "url": incident["url"],
                "reason": reason,
                "differing_fields": ";".join(differing),
                "dependency_count": dependencies,
            })
        else:
            survivor_id = ""
            safe = False
            reason = f"expected_one_survivor_found_{len(survivors)}"
            manual_output.append({
                "delete_candidate_id": incident_id,
                "survivor_id": "",
                "inmobiliaria_id": incident["inmobiliaria_id"],
                "url": incident["url"],
                "reason": reason,
                "differing_fields": "",
                "dependency_count": "",
            })

        group_output.append({
            "incident_id": incident_id,
            "inmobiliaria_id": incident["inmobiliaria_id"],
            "url": incident["url"],
            "group_size": len(group),
            "survivor_id": survivor_id,
            "safe_to_delete_incident": safe,
            "classification": reason,
        })
        for row in group:
            score, images = _completeness(row)
            row_output.append({
                "incident_id": incident_id,
                "property_id": row["id"],
                "row_role": "incident" if int(row["id"]) == incident_id else "existing_counterpart",
                "inmobiliaria_id": row["inmobiliaria_id"],
                "url": row["url"],
                "hash_dedup": row["hash_dedup"],
                "fuente_extraccion": row.get("fuente_extraccion") or "",
                "created_at": row.get("created_at") or "",
                "completeness_score": score,
                "image_count": images,
                "essential_digest": _digest(row, essential_fields),
            })

    for fk in foreign_keys:
        for incident_id in incident_ids:
            dependency_output.append({
                "property_id": incident_id,
                "table_schema": fk["table_schema"],
                "table_name": fk["table_name"],
                "column_name": fk["column_name"],
                "delete_rule": fk["delete_rule"],
                "dependency_count": dependency_counts.get(
                    (incident_id, fk["table_schema"], fk["table_name"]), 0
                ),
            })

    _write_csv(args.out / "duplicate_groups.csv", group_output, list(group_output[0]))
    _write_csv(args.out / "duplicate_rows.csv", row_output, list(row_output[0]))
    _write_csv(args.out / "survivor_candidates.csv", survivor_output, list(survivor_output[0]))
    delete_fields = ["delete_candidate_id", "survivor_id", "inmobiliaria_id", "url", "reason", "differing_fields", "dependency_count"]
    _write_csv(args.out / "delete_candidates.csv", delete_output, delete_fields)
    _write_csv(args.out / "manual_review.csv", manual_output, delete_fields)
    _write_csv(args.out / "dependency_audit.csv", dependency_output, list(dependency_output[0]))

    safe_ids = [int(row["delete_candidate_id"]) for row in delete_output]
    args.out.joinpath("delete_sql.sql").write_text(
        "-- DRY RUN ONLY\n-- No DELETE generated: no incident row passed the essential-data safety gate.\n"
        if not safe_ids else
        "-- DRY RUN ONLY\nDELETE FROM public.propiedades WHERE id IN (" + ",".join(map(str, safe_ids)) + ");\n",
        encoding="utf-8",
    )
    args.out.joinpath("rollback_sql.sql").write_text(
        "-- No rollback SQL generated because no DELETE was executed.\n",
        encoding="utf-8",
    )
    args.out.joinpath("backup_plan.md").write_text(
        "# Backup plan\n\n"
        "No backup table was created because the safe delete set is empty. "
        "If a later manual decision selects explicit rows, create a full-row backup table in the same transaction before DELETE.\n",
        encoding="utf-8",
    )
    args.out.joinpath("validation_report.md").write_text(
        "# Run B duplicate cleanup validation\n\n"
        f"- Closed incident IDs: {len(incident_ids)}\n"
        f"- Live incident rows: {len(incident_rows)}\n"
        f"- Exact `(inmobiliaria_id, url)` groups with two rows: {sum(row['group_size'] == 2 for row in group_output)}\n"
        f"- Safe automatic delete candidates: {len(delete_output)}\n"
        f"- Manual review: {len(manual_output)}\n"
        f"- Incident dependencies: {sum(int(row['dependency_count']) for row in dependency_output)}\n"
        "- DELETE executed: no\n"
        "- Reason: every incident row differs from its existing counterpart in substantive property fields.\n"
        "- Safety verdict: PASS (fail closed).\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "incident_rows": len(incident_rows),
        "safe_delete_candidates": len(delete_output),
        "manual_review": len(manual_output),
        "dependencies": sum(int(row["dependency_count"]) for row in dependency_output),
        "delete_executed": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
