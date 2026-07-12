#!/usr/bin/env python3
"""Read-only baseline and write reconciliation for autonomous Pipeline A runs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row


REPO_ROOT = Path(__file__).resolve().parent.parent
PROTECTED_AGENCY_COLUMNS = (
    "cms_detectado",
    "estrategia_scraping",
    "diagnostic_status",
    "scraping_readiness",
    "exclude_from_scraping",
    "sitio_activo",
    "activa",
    "url_listado",
)
WRITE_AUDIT_FIELDS = (
    "run_id",
    "property_id",
    "source_id_expected",
    "inmobiliaria_id_written",
    "fk_match",
    "url",
    "normalized_url",
    "duplicate_status",
    "created_at",
)


def _load_db_url() -> str:
    load_dotenv(REPO_ROOT / ".env", override=False)
    value = os.getenv("INTERNAL_DB_URL", "")
    if not value:
        raise RuntimeError("INTERNAL_DB_URL is not configured")
    return value


def _read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _slug(name: Any, source_id: Any) -> str:
    return re.sub(r"[^a-z0-9_]", "_", str(name or "").lower())[:40].strip("_") or f"src_{source_id}"


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _stable_digest(rows: list[dict[str, Any]]) -> str:
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=_json_value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _relation_snapshot(cursor, relation: str) -> dict[str, Any]:
    cursor.execute("SELECT to_regclass(%s)::text AS relation", (relation,))
    found = cursor.fetchone()["relation"]
    if not found:
        return {"relation": relation, "exists": False, "count": None}
    cursor.execute(f"SELECT count(*) AS count FROM {found}")
    return {"relation": found, "exists": True, "count": cursor.fetchone()["count"]}


def _database_snapshot(cursor, manifest: list[dict[str, str]]) -> dict[str, Any]:
    source_ids = sorted({int(row["source_id"]) for row in manifest})
    cursor.execute(
        """
        SELECT count(*) AS count, max(id)::text AS max_id, max(created_at) AS max_created_at
        FROM public.propiedades
        """
    )
    properties = dict(cursor.fetchone())
    cursor.execute(
        f"""
        SELECT id, nombre, {', '.join(PROTECTED_AGENCY_COLUMNS)}
        FROM public.inmobiliarias_main
        WHERE id = ANY(%s)
        ORDER BY id
        """,
        (source_ids,),
    )
    agencies = [dict(row) for row in cursor.fetchall()]
    relations = [
        _relation_snapshot(cursor, "public.publish_queue"),
        _relation_snapshot(cursor, "internal_scraping.publish_queue"),
        _relation_snapshot(cursor, "internal_scraping.propiedades_raw"),
        _relation_snapshot(cursor, "internal_scraping.propiedades_staging"),
        _relation_snapshot(cursor, "internal_scraping.inmobiliarias_staging"),
        _relation_snapshot(cursor, "public.inmobiliarias_staging"),
        _relation_snapshot(cursor, "internal_scraping.scraping_runs"),
        _relation_snapshot(cursor, "internal_scraping.scraping_run_items"),
        _relation_snapshot(cursor, "public.scraping_runs"),
        _relation_snapshot(cursor, "public.scraping_run_items"),
    ]
    return {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "properties": {key: _json_value(value) for key, value in properties.items()},
        "relations": relations,
        "agency_rows": [{key: _json_value(value) for key, value in row.items()} for row in agencies],
        "agency_digest": _stable_digest(agencies),
    }


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _manifest_map(manifest: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in manifest:
        slug = row.get("manifest_slug") or _slug(row.get("source_name"), row.get("source_id"))
        if slug in result:
            raise RuntimeError(f"Duplicate manifest slug: {slug}")
        result[slug] = row
    return result


def _fetch_inserted(cursor, since: str) -> list[dict[str, Any]]:
    cursor.execute(
        """
        SELECT p.id, p.inmobiliaria_id, p.fuente_extraccion, p.url,
               p.url_normalizada, p.hash_dedup, p.created_at,
               EXISTS (
                   SELECT 1 FROM public.propiedades q
                   WHERE q.id <> p.id AND q.inmobiliaria_id = p.inmobiliaria_id
                     AND p.url IS NOT NULL AND p.url <> '' AND q.url = p.url
               ) AS duplicate_exact,
               EXISTS (
                   SELECT 1 FROM public.propiedades q
                   WHERE q.id <> p.id AND q.inmobiliaria_id = p.inmobiliaria_id
                     AND p.url_normalizada IS NOT NULL AND p.url_normalizada <> ''
                     AND q.url_normalizada = p.url_normalizada
               ) AS duplicate_normalized,
               EXISTS (
                   SELECT 1 FROM public.propiedades q
                   WHERE q.id <> p.id AND p.hash_dedup IS NOT NULL AND p.hash_dedup <> ''
                     AND q.hash_dedup = p.hash_dedup
               ) AS duplicate_hash
        FROM public.propiedades p
        WHERE p.created_at >= %s::timestamptz
        ORDER BY p.created_at, p.id
        """,
        (since,),
    )
    return [dict(row) for row in cursor.fetchall()]


def _audit_rows(inserted: list[dict[str, Any]], manifest: list[dict[str, str]], run_id: str) -> list[dict[str, Any]]:
    by_slug = _manifest_map(manifest)
    rows = []
    for prop in inserted:
        source = by_slug.get(str(prop.get("fuente_extraccion") or ""))
        expected = str(source.get("inmobiliaria_id") or source.get("source_id")) if source else ""
        actual = str(prop.get("inmobiliaria_id") or "")
        duplicate_flags = [
            name
            for name, active in (
                ("exact", prop.get("duplicate_exact")),
                ("normalized", prop.get("duplicate_normalized")),
                ("hash", prop.get("duplicate_hash")),
            )
            if active
        ]
        rows.append({
            "run_id": run_id,
            "property_id": prop.get("id"),
            "source_id_expected": expected,
            "inmobiliaria_id_written": actual,
            "fk_match": bool(source and expected == actual),
            "url": prop.get("url") or "",
            "normalized_url": prop.get("url_normalizada") or "",
            "duplicate_status": ";".join(duplicate_flags) if duplicate_flags else "unique",
            "created_at": _json_value(prop.get("created_at")),
        })
    return rows


def _relation_counts(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {row["relation"]: row.get("count") for row in snapshot.get("relations", []) if row.get("exists")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mode", choices=("baseline", "post"), required=True)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--since")
    parser.add_argument("--run-id", default="pipeline_a")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    manifest = _read_manifest(args.manifest)

    with psycopg.connect(_load_db_url(), row_factory=dict_row) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            snapshot = _database_snapshot(cursor, manifest)
            if args.mode == "baseline":
                path = args.out / "db_baseline.json"
                path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"baseline={path} properties={snapshot['properties']['count']} sources={len(manifest)}")
                return 0

            if not args.baseline or not args.baseline.exists():
                raise RuntimeError("--baseline is required in post mode")
            baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
            since = args.since or baseline["captured_at_utc"]
            inserted = _fetch_inserted(cursor, since)

    audit_rows = _audit_rows(inserted, manifest, args.run_id)
    _write_csv(args.out / "write_audit.csv", audit_rows, WRITE_AUDIT_FIELDS)
    before_relations = _relation_counts(baseline)
    after_relations = _relation_counts(snapshot)
    relation_drift = {
        name: {"before": count, "after": after_relations.get(name)}
        for name, count in before_relations.items()
        if after_relations.get(name) != count
    }
    fk_errors = sum(str(row["fk_match"]).lower() != "true" for row in audit_rows)
    duplicate_errors = sum(row["duplicate_status"] != "unique" for row in audit_rows)
    agency_changed = baseline.get("agency_digest") != snapshot.get("agency_digest")
    property_delta = int(snapshot["properties"]["count"]) - int(baseline["properties"]["count"])
    count_reconciled = property_delta == len(inserted)
    passed = not fk_errors and not duplicate_errors and not agency_changed and not relation_drift and count_reconciled
    report = [
        "# Pipeline A write audit",
        "",
        f"- Run: {args.run_id}",
        f"- Baseline UTC: {baseline['captured_at_utc']}",
        f"- Properties before: {baseline['properties']['count']}",
        f"- Properties after: {snapshot['properties']['count']}",
        f"- Property count delta: {property_delta}",
        f"- Inserted rows fetched: {len(inserted)}",
        f"- Count reconciled: {count_reconciled}",
        f"- FK mismatches: {fk_errors}",
        f"- Duplicate inserts: {duplicate_errors}",
        f"- Protected agency rows changed: {agency_changed}",
        f"- Protected relation count drift: {json.dumps(relation_drift, ensure_ascii=False)}",
        f"- Result: {'PASS' if passed else 'FAIL'}",
        "",
        "Transaction mode: READ ONLY. This audit performed zero DB writes.",
    ]
    (args.out / "write_audit_summary.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    (args.out / "db_post_snapshot.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"inserted={len(inserted)} fk_errors={fk_errors} duplicates={duplicate_errors} result={'PASS' if passed else 'FAIL'}")
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
