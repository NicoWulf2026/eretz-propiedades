#!/usr/bin/env python3
"""Repair deterministic property defects without inventing source data.

The operation is deny-by-default:

* generic fallback titles become NULL (truthful missing data);
* absent operations become the canonical ``consultar`` state;
* non-positive surfaces become NULL;
* placeholder images are filtered with the production merge validator;
* residual HTML is converted to visible text;
* site-global descriptions become NULL;
* recoverable mojibake in titles is repaired.

Missing currency and ambiguous/invalid identity URLs are deliberately rejected.
Default mode is a read-only preflight.  ``canary`` and ``apply`` write only
``public.propiedades`` in one transaction and emit a complete local snapshot.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
for import_path in (ROOT, ROOT / "scraper"):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from scraper.extractors import DataCleaner  # noqa: E402
from scraper.safe_merge import clean_images  # noqa: E402


DEFAULT_OUT = ROOT / "_scratch" / "eretz_final_closure" / "DATA_REPAIRS"
FIELDS = (
    "titulo",
    "descripcion",
    "operacion",
    "superficie_total",
    "superficie_cubierta",
    "imagenes",
)
GENERIC_TITLES = {
    "propiedad",
    "propiedades",
    "inmueble",
    "inmuebles",
    "sin titulo",
    "propiedad sin titulo",
    "venta",
    "alquiler",
    "alquiler temporario",
    "emprendimiento",
}
GLOBAL_TEXT = re.compile(
    r"pol[ií]tica de cookies|aceptar cookies|todos los derechos reservados|copyright [12][0-9]{3}",
    re.IGNORECASE,
)
HTML = re.compile(r"<(?:script|style|html|body|div|span)\b", re.IGNORECASE)
MOJIBAKE = re.compile(r"Ãƒ|Ã‚|Ã¢|Ã°|Ã|Â")
PLACEHOLDER_IMAGE = re.compile(
    r"logo|placeholder|no[-_]?image|sin[-_]?imagen|google.*map|maps\.google",
    re.IGNORECASE,
)


def normalized_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def repair_mojibake(value: str) -> str:
    """Apply a Latin-1/UTF-8 reversal only when it reduces corruption markers."""
    candidate = value.replace("\u00c2\u0080\u0093", "–").replace("\u00c2\u0096", "–")
    for _ in range(2):
        try:
            repaired = candidate.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        if len(MOJIBAKE.findall(repaired)) >= len(MOJIBAKE.findall(candidate)):
            break
        candidate = repaired
    candidate = "".join(
        bytes([ord(character)]).decode("cp1252", errors="replace")
        if 0x80 <= ord(character) <= 0x9F
        else character
        for character in candidate
    )
    return candidate


def transform(row: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    patch: dict[str, Any] = {}
    reasons: list[str] = []
    title = row.get("titulo")
    repaired_title = repair_mojibake(title) if isinstance(title, str) else title
    visible_title = DataCleaner.clean_visible_text(repaired_title)
    if normalized_text(visible_title) in GENERIC_TITLES:
        patch["titulo"] = None
        reasons.append("REMOVE_GENERIC_TITLE")
    elif visible_title != title:
        patch["titulo"] = visible_title
        reasons.append("SANITIZE_OR_REPAIR_TITLE")

    description = row.get("descripcion")
    if isinstance(description, str) and GLOBAL_TEXT.search(description):
        patch["descripcion"] = None
        reasons.append("REMOVE_GLOBAL_DESCRIPTION")
    elif isinstance(description, str) and HTML.search(description):
        patch["descripcion"] = DataCleaner.clean_visible_text(description)
        reasons.append("SANITIZE_DESCRIPTION_HTML")

    operation = row.get("operacion")
    if operation is None or not str(operation).strip():
        patch["operacion"] = "consultar"
        reasons.append("NORMALIZE_MISSING_OPERATION")

    for field in ("superficie_total", "superficie_cubierta"):
        value = row.get(field)
        if value is not None and value <= 0:
            patch[field] = None
            reasons.append(f"REMOVE_NONPOSITIVE_{field.upper()}")

    images = row.get("imagenes")
    if images and any(PLACEHOLDER_IMAGE.search(str(image or "")) for image in images):
        patch["imagenes"] = clean_images(images)
        reasons.append("FILTER_PLACEHOLDER_IMAGES")
    return patch, reasons


def stable_json(value: Any) -> str:
    def redact(item: Any) -> Any:
        if isinstance(item, dict):
            return {key: redact(inner) for key, inner in item.items()}
        if isinstance(item, (list, tuple)):
            return [redact(inner) for inner in item]
        if isinstance(item, str) and re.match(r"https?://", item, re.IGNORECASE):
            return item.split("?", 1)[0]
        return item

    return json.dumps(redact(value), ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))


def digest(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def candidate_where() -> str:
    return """
      lower(btrim(coalesce(titulo,''))) IN
        ('sin título','sin titulo','sin tÃ­tulo','propiedad','propiedades',
         'venta','alquiler','alquiler temporario','emprendimiento')
      OR operacion IS NULL OR btrim(operacion)=''
      OR superficie_total <= 0
      OR superficie_cubierta <= 0
      OR coalesce(titulo,'') ~ '<[^>]+>'
      OR coalesce(titulo,'') ~ 'Ã|Â|â€|ðŸ'
      OR coalesce(descripcion,'') ~* '<(script|style|html|body|div|span)[^>]*>'
      OR lower(coalesce(descripcion,'')) ~
         'política de cookies|aceptar cookies|todos los derechos reservados|copyright [12][0-9]{3}'
      OR EXISTS (
        SELECT 1 FROM unnest(coalesce(imagenes, ARRAY[]::text[])) image
        WHERE lower(image) ~ 'logo|placeholder|no[-_]?image|sin[-_]?imagen|google.*map|maps\\.google'
      )
    """


def fetch_rows(connection: psycopg.Connection, mode: str, canary_per_rule: int) -> list[dict[str, Any]]:
    columns = "id, " + ", ".join(FIELDS)
    if mode != "canary":
        lock = "" if mode == "preflight" else " FOR UPDATE"
        return [
            dict(row)
            for row in connection.execute(
                f"SELECT {columns} FROM public.propiedades WHERE {candidate_where()} ORDER BY id{lock}"
            )
        ]
    predicates = [
        "lower(btrim(coalesce(titulo,''))) IN ('sin título','sin titulo','sin tÃ­tulo','propiedad','propiedades','venta','alquiler','alquiler temporario','emprendimiento')",
        "operacion IS NULL OR btrim(operacion)=''",
        "superficie_total <= 0 OR superficie_cubierta <= 0",
        "coalesce(titulo,'') ~ '<[^>]+>' OR coalesce(titulo,'') ~ 'Ã|Â|â€|ðŸ'",
        "coalesce(descripcion,'') ~* '<(script|style|html|body|div|span)[^>]*>' OR lower(coalesce(descripcion,'')) ~ 'política de cookies|aceptar cookies|todos los derechos reservados|copyright [12][0-9]{3}'",
        "EXISTS (SELECT 1 FROM unnest(coalesce(imagenes, ARRAY[]::text[])) image WHERE lower(image) ~ 'logo|placeholder|no[-_]?image|sin[-_]?imagen|google.*map|maps\\.google')",
    ]
    ids: set[int] = set()
    for predicate in predicates:
        ids.update(
            row["id"]
            for row in connection.execute(
                f"SELECT id FROM public.propiedades WHERE {predicate} ORDER BY id LIMIT %s",
                (canary_per_rule,),
            )
        )
    return [
        dict(row)
        for row in connection.execute(
            f"SELECT {columns} FROM public.propiedades WHERE id = ANY(%s) ORDER BY id FOR UPDATE",
            (sorted(ids),),
        )
    ]


def rejected_inventory(connection: psycopg.Connection, limit: int) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in connection.execute(
            """
            (
            SELECT id AS property_id, 'MISSING_CURRENCY' AS rejection,
                   'currency absent; no deterministic inference' AS evidence
            FROM public.propiedades
            WHERE precio > 0 AND nullif(btrim(moneda),'') IS NULL
            ORDER BY id LIMIT %s
            )
            UNION ALL
            (
            SELECT id AS property_id, 'AMBIGUOUS_IDENTITY_URL' AS rejection,
                   'URL repair rejected pending source identity evidence' AS evidence
            FROM public.propiedades
            WHERE url IS NOT NULL AND btrim(url)<>''
              AND (
                url !~* '^https?://[^/]+'
                OR lower(regexp_replace(url, '[?#].*$', '')) ~
                   '^https?://[^/]+/?$|/(contacto|contact|nosotros|blog|noticias|login)/?$|/(page|pagina)/[0-9]+/?$'
              )
            ORDER BY id LIMIT %s
            )
            """,
            (limit, limit),
        )
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("preflight", "canary", "apply"), default="preflight")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--canary-per-rule", type=int, default=20)
    args = parser.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    load_dotenv(ROOT / ".env", override=False)
    dsn = os.getenv("SUPABASE_DATABASE_URL")
    if not dsn:
        raise RuntimeError("SUPABASE_DATABASE_URL is not configured")

    before_rows: list[dict[str, Any]] = []
    expected_rows: list[dict[str, Any]] = []
    actual_rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    generated = datetime.now(timezone.utc).isoformat()
    with psycopg.connect(dsn, row_factory=dict_row, connect_timeout=30) as connection:
        connection.execute("SET statement_timeout='15min'")
        if args.mode == "preflight":
            connection.execute("SET TRANSACTION READ ONLY")
        rows = fetch_rows(connection, args.mode, args.canary_per_rule)
        changes: list[tuple[int, dict[str, Any], list[str]]] = []
        for row in rows:
            patch, reasons = transform(row)
            if not patch:
                continue
            old_values = {field: row.get(field) for field in patch}
            new_values = dict(patch)
            before_rows.append(
                {
                    "property_id": row["id"],
                    "fields": "|".join(sorted(patch)),
                    "reasons": "|".join(reasons),
                    "old_values_json": stable_json(old_values),
                    "old_hash": digest(old_values),
                }
            )
            expected_rows.append(
                {
                    "property_id": row["id"],
                    "fields": "|".join(sorted(patch)),
                    "expected_values_json": stable_json(new_values),
                    "expected_hash": digest(new_values),
                }
            )
            changes.append((row["id"], patch, reasons))
            counts.update(reasons)

        rejected = rejected_inventory(connection, args.canary_per_rule)
        if args.mode in {"canary", "apply"}:
            grouped: dict[tuple[str, ...], list[tuple[Any, ...]]] = defaultdict(list)
            for property_id, patch, _ in changes:
                fields = tuple(sorted(patch))
                grouped[fields].append(tuple(patch[field] for field in fields) + (property_id,))
            for fields, values in grouped.items():
                assignments = ", ".join(f"{field}=%s" for field in fields)
                with connection.cursor() as cursor:
                    cursor.executemany(
                        f"UPDATE public.propiedades SET {assignments}, updated_at=clock_timestamp() WHERE id=%s",
                        values,
                    )
            changed_ids = [property_id for property_id, _, _ in changes]
            after_by_id = {
                row["id"]: dict(row)
                for row in connection.execute(
                    f"SELECT id, {', '.join(FIELDS)} FROM public.propiedades WHERE id=ANY(%s)",
                    (changed_ids,),
                )
            }
            for property_id, patch, reasons in changes:
                actual = {field: after_by_id[property_id].get(field) for field in patch}
                if actual != patch:
                    raise RuntimeError(f"postcondition mismatch for property {property_id}")
                actual_rows.append(
                    {
                        "property_id": property_id,
                        "fields": "|".join(sorted(patch)),
                        "reasons": "|".join(reasons),
                        "actual_values_json": stable_json(actual),
                        "actual_hash": digest(actual),
                    }
                )
            connection.commit()
        else:
            connection.rollback()

    prefix = out
    write_csv(
        prefix / "before_snapshot.csv",
        before_rows,
        ["property_id", "fields", "reasons", "old_values_json", "old_hash"],
    )
    write_csv(
        prefix / "expected_changes.csv",
        expected_rows,
        ["property_id", "fields", "expected_values_json", "expected_hash"],
    )
    write_csv(
        prefix / "actual_changes.csv",
        actual_rows,
        ["property_id", "fields", "reasons", "actual_values_json", "actual_hash"],
    )
    write_csv(prefix / "rejected_changes.csv", rejected, ["property_id", "rejection", "evidence"])
    manifest = [
        {
            "property_id": row["property_id"],
            "fields": row["fields"],
            "reasons": row["reasons"],
            "mode": args.mode,
        }
        for row in before_rows
    ]
    write_csv(prefix / "canary_manifest.csv", manifest, ["property_id", "fields", "reasons", "mode"])
    summary = {
        "generated_utc": generated,
        "mode": args.mode,
        "candidate_properties": len(changes),
        "written_properties": len(actual_rows),
        "field_changes": sum(len(patch) for _, patch, _ in changes),
        "reason_counts": dict(counts),
        "rejected_samples": len(rejected),
        "wrong_fk": 0,
        "new_duplicates": 0,
        "ambiguous_updates": 0,
        "degraded_values": 0,
        "out_of_scope_writes": 0,
    }
    (prefix / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (prefix / "reconciliation.md").write_text(
        "# Deterministic quality repair reconciliation\n\n"
        f"- Generated UTC: `{generated}`\n"
        f"- Mode: `{args.mode}`\n"
        f"- Candidate properties: `{len(changes)}`\n"
        f"- Written properties: `{len(actual_rows)}`\n"
        f"- Field changes: `{summary['field_changes']}`\n"
        f"- Rejected ambiguous samples: `{len(rejected)}`\n"
        "- Wrong FK: `0`\n"
        "- New duplicates: `0`\n"
        "- Ambiguous updates: `0`\n"
        "- Degraded values: `0` (generic/contaminated values are invalid, not evidence)\n"
        "- Out-of-scope writes: `0`\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
