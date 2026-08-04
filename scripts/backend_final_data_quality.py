#!/usr/bin/env python3
"""Efficient full-row quality audit for the canonical ERETZ property dataset."""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "_scratch/backend_final_closure/DATA_QUALITY"
ANOMALY_FIELDS = [
    "property_id",
    "inmobiliaria_id",
    "fuente_extraccion",
    "url",
    "field",
    "anomaly_type",
    "category",
    "root_cause",
    "severity",
    "detail",
]

# SQL predicates are fixed source code, never user input.
RULES = [
    ("url", "MISSING_URL", "INTERNAL_CORRECTABLE", "VALIDATION", "critical", "url IS NULL OR btrim(url) = ''", "missing property URL"),
    ("url", "INVALID_URL_FORMAT", "AMBIGUOUS", "IDENTITY", "high", "url IS NOT NULL AND btrim(url) <> '' AND url !~* '^https?://[^/]+'", "invalid historical URL; replacement requires source identity evidence"),
    ("url", "OPERATION_CATEGORY_URL", "HISTORICAL_DEBT", "VALIDATION", "critical", "lower(regexp_replace(coalesce(url,''), '[?#].*$', '')) ~ '/properties/operation/(forsale|forrent)/?$'", "operation/category route"),
    ("url", "PROHIBITED_PORTAL_URL", "HISTORICAL_DEBT", "VALIDATION", "critical", "lower(coalesce(url,'')) ~ 'https?://([^/]+\\.)?(zonaprop|argenprop|properati)\\.(com|com\\.ar)(/|$)'", "prohibited portal"),
    ("url", "HOME_OR_NON_DETAIL_URL", "AMBIGUOUS", "IDENTITY", "high", "lower(regexp_replace(coalesce(url,''), '[?#].*$', '')) ~ '^https?://[^/]+/?$|/(contacto|contact|nosotros|blog|noticias|login)/?$|/(page|pagina)/[0-9]+/?$'", "non-detail historical route; replacement requires source identity evidence"),
    ("url_normalizada", "MISSING_NORMALIZED_URL", "AMBIGUOUS", "DEDUPLICATION", "medium", "url IS NOT NULL AND btrim(url) <> '' AND (url_normalizada IS NULL OR btrim(url_normalizada) = '')", "canonical key withheld because safe preflight found an identity collision"),
    ("titulo", "MISSING_TITLE", "EXTERNAL_SOURCE_MISSING_DATA", "DETAIL_PARSER", "high", "titulo IS NULL OR btrim(titulo) = ''", "blank title"),
    ("titulo", "FALLBACK_TITLE", "INTERNAL_CORRECTABLE", "DETAIL_PARSER", "high", "lower(btrim(coalesce(titulo,''))) IN ('sin título','sin titulo','propiedad','propiedades')", "generic fallback title"),
    ("titulo", "GENERIC_OPERATION_TITLE", "INTERNAL_CORRECTABLE", "DETAIL_PARSER", "medium", "lower(btrim(coalesce(titulo,''))) IN ('venta','alquiler','alquiler temporario','emprendimiento')", "operation used as title"),
    ("titulo", "HTML_IN_TITLE", "INTERNAL_CORRECTABLE", "HTML_SELECTOR", "high", "coalesce(titulo,'') ~ '<[^>]+>'", "HTML markup in title"),
    ("titulo", "ENCODING_IN_TITLE", "INTERNAL_CORRECTABLE", "ENCODING", "high", "coalesce(titulo,'') ~ 'Ã|Â|â€|ðŸ'", "mojibake in title"),
    ("descripcion", "MISSING_DESCRIPTION", "EXTERNAL_SOURCE_MISSING_DATA", "DETAIL_PARSER", "medium", "descripcion IS NULL OR btrim(descripcion) = ''", "blank description"),
    ("descripcion", "SHORT_DESCRIPTION", "AMBIGUOUS", "DETAIL_PARSER", "low", "descripcion IS NOT NULL AND length(btrim(descripcion)) BETWEEN 1 AND 39", "description shorter than 40 chars"),
    ("descripcion", "HTML_IN_DESCRIPTION", "INTERNAL_CORRECTABLE", "HTML_SELECTOR", "high", "coalesce(descripcion,'') ~* '<(script|style|html|body|div|span)[^>]*>'", "HTML/script markup"),
    ("descripcion", "GLOBAL_TEXT_IN_DESCRIPTION", "INTERNAL_CORRECTABLE", "HTML_SELECTOR", "medium", "lower(coalesce(descripcion,'')) ~ 'política de cookies|aceptar cookies|todos los derechos reservados|copyright [12][0-9]{3}'", "site-global text"),
    ("precio", "NEGATIVE_PRICE", "INTERNAL_CORRECTABLE", "NORMALIZATION", "critical", "precio < 0", "negative price"),
    ("precio", "ZERO_PRICE", "AMBIGUOUS", "NORMALIZATION", "medium", "precio = 0", "zero price"),
    ("precio", "PRICE_OUTLIER_HIGH", "AMBIGUOUS", "NORMALIZATION", "high", "precio > 1000000000000", "price exceeds deterministic bound"),
    ("moneda", "MISSING_CURRENCY", "EXTERNAL_SOURCE_MISSING_DATA", "SOURCE_MISSING_DATA", "high", "precio IS NOT NULL AND precio > 0 AND nullif(btrim(moneda),'') IS NULL", "source currency is absent and cannot be inferred safely"),
    ("moneda", "INVALID_CURRENCY", "INTERNAL_CORRECTABLE", "NORMALIZATION", "high", "precio IS NOT NULL AND precio > 0 AND nullif(btrim(moneda),'') IS NOT NULL AND lower(btrim(moneda)) NOT IN ('ars','usd','eur','pesos','dólares','dolares')", "unsupported non-empty currency"),
    ("operacion", "MISSING_OPERATION", "INTERNAL_CORRECTABLE", "FIELD_MAPPING", "high", "operacion IS NULL OR btrim(operacion) = ''", "missing operation"),
    ("operacion", "INVALID_OPERATION", "INTERNAL_CORRECTABLE", "NORMALIZATION", "high", "operacion IS NOT NULL AND btrim(operacion) <> '' AND lower(btrim(operacion)) NOT IN ('venta','alquiler','alquiler_temporario','alquiler temporario','venta_y_alquiler','permuta','emprendimiento','consultar','otra','otro')", "unsupported operation"),
    ("tipo_propiedad", "MISSING_PROPERTY_TYPE", "INTERNAL_CORRECTABLE", "FIELD_MAPPING", "medium", "tipo_propiedad IS NULL OR btrim(tipo_propiedad) = ''", "missing property type"),
    ("ubicacion", "MISSING_LOCATION", "EXTERNAL_SOURCE_MISSING_DATA", "DETAIL_PARSER", "medium", "coalesce(nullif(btrim(direccion),''),nullif(btrim(barrio),''),nullif(btrim(ciudad),''),nullif(btrim(provincia),'')) IS NULL", "no location fields"),
    ("latitud,longitud", "PARTIAL_COORDINATES", "INTERNAL_CORRECTABLE", "FIELD_MAPPING", "high", "(latitud IS NULL) <> (longitud IS NULL)", "only one coordinate"),
    ("latitud,longitud", "COORDINATES_OUTSIDE_ARGENTINA", "AMBIGUOUS", "NORMALIZATION", "high", "latitud IS NOT NULL AND longitud IS NOT NULL AND (latitud NOT BETWEEN -56 AND -21 OR longitud NOT BETWEEN -75 AND -52)", "coordinates outside Argentina bounds"),
    ("superficie_total", "INVALID_TOTAL_SURFACE", "INTERNAL_CORRECTABLE", "NORMALIZATION", "high", "superficie_total IS NOT NULL AND superficie_total <= 0", "non-positive total surface"),
    ("superficie_cubierta", "INVALID_COVERED_SURFACE", "INTERNAL_CORRECTABLE", "NORMALIZATION", "high", "superficie_cubierta IS NOT NULL AND superficie_cubierta <= 0", "non-positive covered surface"),
    ("superficies", "COVERED_EXCEEDS_TOTAL", "AMBIGUOUS", "FIELD_MAPPING", "high", "superficie_total > 0 AND superficie_cubierta > superficie_total", "covered surface exceeds total"),
    ("caracteristicas", "NEGATIVE_FEATURE_COUNT", "INTERNAL_CORRECTABLE", "NORMALIZATION", "high", "least(coalesce(ambientes,0),coalesce(dormitorios,0),coalesce(banos,0),coalesce(toilettes,0),coalesce(cocheras,0),coalesce(antiguedad,0)) < 0", "negative feature count"),
    ("caracteristicas", "FEATURE_COUNT_OUTLIER", "AMBIGUOUS", "NORMALIZATION", "medium", "coalesce(ambientes,0)>30 OR coalesce(dormitorios,0)>30 OR coalesce(banos,0)>20 OR coalesce(cocheras,0)>50 OR coalesce(antiguedad,0)>300", "feature count outside deterministic bound"),
    ("imagenes", "MISSING_IMAGES", "EXTERNAL_SOURCE_MISSING_DATA", "DETAIL_PARSER", "medium", "coalesce(cardinality(imagenes),0)=0", "no images"),
    ("imagenes", "PLACEHOLDER_IMAGES", "INTERNAL_CORRECTABLE", "VALIDATION", "high", "EXISTS (SELECT 1 FROM unnest(coalesce(imagenes, ARRAY[]::text[])) image WHERE lower(image) ~ 'logo|placeholder|no[-_]?image|sin[-_]?imagen|google.*map|maps\\.google')", "placeholder/global image"),
    ("contacto", "MISSING_CONTACT", "EXTERNAL_SOURCE_MISSING_DATA", "DETAIL_PARSER", "low", "coalesce(nullif(btrim(agente_nombre),''),nullif(btrim(agente_telefono),'')) IS NULL", "no property contact"),
    ("fecha_publicacion", "FUTURE_PUBLICATION_DATE", "INTERNAL_CORRECTABLE", "TIMEZONE", "high", "fecha_publicacion > now() + interval '1 day'", "future publication date"),
    ("created_at,updated_at", "TIMESTAMP_ORDER_INVALID", "INTERNAL_CORRECTABLE", "TIMEZONE", "high", "updated_at IS NOT NULL AND created_at IS NOT NULL AND updated_at < created_at", "updated_at precedes created_at"),
    ("inmobiliaria_id", "ORPHAN_AGENCY_FK", "HISTORICAL_DEBT", "FK_RESOLUTION", "critical", "inmobiliaria_id IS NULL OR NOT EXISTS (SELECT 1 FROM public.inmobiliarias_main i WHERE i.id=p.inmobiliaria_id)", "missing agency FK"),
]


def db_url() -> str:
    load_dotenv(ROOT / ".env", override=False)
    value = os.getenv("SUPABASE_DATABASE_URL", "")
    if not value:
        raise RuntimeError("SUPABASE_DATABASE_URL is not configured")
    return value


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def fetch(cursor: Any, query: str) -> list[dict[str, Any]]:
    cursor.execute(query)
    return [dict(row) for row in cursor.fetchall()]


def anomaly_query(rule: tuple[str, ...]) -> str:
    field, name, category, root, severity, predicate, detail = rule

    def escaped(value: str) -> str:
        return value.replace("'", "''")

    return f"""
        SELECT p.id AS property_id, p.inmobiliaria_id, p.fuente_extraccion,
               p.url, '{escaped(field)}' AS field,
               '{escaped(name)}' AS anomaly_type,
               '{escaped(category)}' AS category,
               '{escaped(root)}' AS root_cause,
               '{escaped(severity)}' AS severity,
               '{escaped(detail)}' AS detail
        FROM public.propiedades p
        WHERE {predicate}
    """


def stream_anomalies(
    conn: psycopg.Connection,
    out: Path,
) -> tuple[dict[tuple[str, str, str, str], dict[str, Any]], Counter[str], int]:
    """Stream anomaly evidence to disk instead of retaining the universe in RAM."""
    row_path = out / "row_level_anomalies.csv"
    cross_path = out / "cross_field_anomalies.csv"
    progress_path = out / "progress.json"
    grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    categories: Counter[str] = Counter()
    total = 0
    with (
        row_path.open("w", encoding="utf-8", newline="") as row_handle,
        cross_path.open("w", encoding="utf-8", newline="") as cross_handle,
    ):
        row_writer = csv.DictWriter(row_handle, fieldnames=ANOMALY_FIELDS)
        cross_writer = csv.DictWriter(cross_handle, fieldnames=ANOMALY_FIELDS)
        row_writer.writeheader()
        cross_writer.writeheader()
        for index, rule in enumerate(RULES, 1):
            rule_rows = 0
            with conn.cursor(name=f"quality_rule_{index}") as cur:
                cur.itersize = 2_000
                cur.execute(anomaly_query(rule))
                while batch := cur.fetchmany(2_000):
                    records = [dict(row) for row in batch]
                    row_writer.writerows(records)
                    cross_writer.writerows(
                        row
                        for row in records
                        if "," in row["field"]
                        or row["field"]
                        in {
                            "ubicacion",
                            "superficies",
                            "caracteristicas",
                            "contacto",
                        }
                    )
                    for row in records:
                        key = (
                            row["anomaly_type"],
                            row["category"],
                            row["root_cause"],
                            row["severity"],
                        )
                        item = grouped.setdefault(
                            key,
                            {
                                "anomaly_type": row["anomaly_type"],
                                "category": row["category"],
                                "root_cause": row["root_cause"],
                                "severity": row["severity"],
                                "affected_rows": 0,
                                "affected_sources": set(),
                            },
                        )
                        item["affected_rows"] += 1
                        if row.get("fuente_extraccion"):
                            item["affected_sources"].add(row["fuente_extraccion"])
                        categories[row["category"]] += 1
                    rule_rows += len(records)
                    total += len(records)
            row_handle.flush()
            cross_handle.flush()
            progress_path.write_text(
                json.dumps(
                    {
                        "status": "running",
                        "rules_completed": index,
                        "rules_total": len(RULES),
                        "last_rule": rule[1],
                        "last_rule_rows": rule_rows,
                        "anomalies_written": total,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
    progress_path.write_text(
        json.dumps(
            {
                "status": "anomaly_stream_complete",
                "rules_completed": len(RULES),
                "rules_total": len(RULES),
                "anomalies_written": total,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return grouped, categories, total


def load_streamed_anomalies(
    out: Path,
) -> tuple[dict[tuple[str, str, str, str], dict[str, Any]], Counter[str], int]:
    """Rebuild aggregates from a completed local stream without querying rules again."""
    progress = json.loads((out / "progress.json").read_text(encoding="utf-8"))
    if progress.get("status") != "anomaly_stream_complete":
        raise RuntimeError("anomaly stream is not complete and cannot be reused")
    grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    categories: Counter[str] = Counter()
    total = 0
    with (out / "row_level_anomalies.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        for row in csv.DictReader(handle):
            key = (
                row["anomaly_type"],
                row["category"],
                row["root_cause"],
                row["severity"],
            )
            item = grouped.setdefault(
                key,
                {
                    "anomaly_type": row["anomaly_type"],
                    "category": row["category"],
                    "root_cause": row["root_cause"],
                    "severity": row["severity"],
                    "affected_rows": 0,
                    "affected_sources": set(),
                },
            )
            item["affected_rows"] += 1
            if row.get("fuente_extraccion"):
                item["affected_sources"].add(row["fuente_extraccion"])
            categories[row["category"]] += 1
            total += 1
    if total != int(progress.get("anomalies_written") or -1):
        raise RuntimeError("stream row count does not match its completion checkpoint")
    return grouped, categories, total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--reuse-anomaly-stream",
        action="store_true",
        help="reuse a completed row_level_anomalies.csv and rerun only summaries",
    )
    args = parser.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc).isoformat()
    with psycopg.connect(db_url(), row_factory=dict_row, connect_timeout=60) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        conn.execute("SET statement_timeout = '15min'")
        if args.reuse_anomaly_stream:
            grouped, category_counts, anomaly_count = load_streamed_anomalies(out)
        else:
            grouped, category_counts, anomaly_count = stream_anomalies(conn, out)
        with conn.cursor() as cur:
            duplicates = {}
            for key, expression, predicate, group_expression in [
                ("url", "url", "url IS NOT NULL AND btrim(url)<>''", "inmobiliaria_id, url"),
                ("url_normalizada", "url_normalizada", "url_normalizada IS NOT NULL AND btrim(url_normalizada)<>''", "inmobiliaria_id, url_normalizada"),
                ("hash_dedup", "hash_dedup", "hash_dedup IS NOT NULL AND btrim(hash_dedup)<>''", "hash_dedup"),
            ]:
                rows = fetch(
                    cur,
                    f"""
                    SELECT {expression} AS duplicate_key, count(*)::int AS duplicate_count,
                           array_agg(id ORDER BY id) AS property_ids,
                           count(DISTINCT inmobiliaria_id)::int AS agency_count
                    FROM public.propiedades
                    WHERE {predicate}
                    GROUP BY {group_expression}
                    HAVING count(*) > 1
                    ORDER BY count(*) DESC, {expression}
                    """,
                )
                duplicates[key] = rows
                write_csv(
                    out / f"duplicate_by_{key}.csv",
                    rows,
                    ["duplicate_key", "duplicate_count", "property_ids", "agency_count"],
                )
            source_quality = fetch(
                cur,
                """
                SELECT p.inmobiliaria_id, max(i.nombre) AS inmobiliaria,
                       max(p.fuente_extraccion) AS fuente_extraccion,
                       max(i.cms_detectado) AS cms, max(i.estrategia_scraping) AS parser_family,
                       count(*)::bigint AS total_rows,
                       count(*) FILTER (WHERE p.titulo IS NULL OR btrim(p.titulo)='') AS missing_title,
                       count(*) FILTER (WHERE p.descripcion IS NULL OR btrim(p.descripcion)='') AS missing_description,
                       count(*) FILTER (WHERE p.precio IS NULL OR p.precio<=0) AS missing_or_invalid_price,
                       count(*) FILTER (WHERE p.operacion IS NULL OR btrim(p.operacion)='') AS missing_operation,
                       count(*) FILTER (WHERE p.tipo_propiedad IS NULL OR btrim(p.tipo_propiedad)='') AS missing_type,
                       count(*) FILTER (WHERE coalesce(nullif(btrim(p.direccion),''),nullif(btrim(p.barrio),''),nullif(btrim(p.ciudad),''),nullif(btrim(p.provincia),'')) IS NULL) AS missing_location,
                       count(*) FILTER (WHERE coalesce(cardinality(p.imagenes),0)=0) AS missing_images,
                       count(*) FILTER (WHERE p.latitud IS NOT NULL AND p.longitud IS NOT NULL) AS with_coordinates
                FROM public.propiedades p
                LEFT JOIN public.inmobiliarias_main i ON i.id=p.inmobiliaria_id
                GROUP BY p.inmobiliaria_id
                ORDER BY total_rows DESC
                """,
            )
            cms_quality = fetch(
                cur,
                """
                SELECT coalesce(i.cms_detectado,'UNCLASSIFIED') AS cms,
                       count(*)::bigint AS total_rows,
                       count(*) FILTER (WHERE p.titulo IS NULL OR btrim(p.titulo)='') AS missing_title,
                       count(*) FILTER (WHERE p.descripcion IS NULL OR btrim(p.descripcion)='') AS missing_description,
                       count(*) FILTER (WHERE p.precio IS NULL OR p.precio<=0) AS missing_or_invalid_price,
                       count(*) FILTER (WHERE coalesce(cardinality(p.imagenes),0)=0) AS missing_images
                FROM public.propiedades p
                LEFT JOIN public.inmobiliarias_main i ON i.id=p.inmobiliaria_id
                GROUP BY coalesce(i.cms_detectado,'UNCLASSIFIED')
                ORDER BY total_rows DESC
                """,
            )
            parser_quality = fetch(
                cur,
                """
                SELECT coalesce(i.estrategia_scraping,'UNCLASSIFIED') AS parser_family,
                       count(*)::bigint AS total_rows,
                       count(*) FILTER (WHERE p.titulo IS NULL OR btrim(p.titulo)='') AS missing_title,
                       count(*) FILTER (WHERE p.descripcion IS NULL OR btrim(p.descripcion)='') AS missing_description,
                       count(*) FILTER (WHERE p.precio IS NULL OR p.precio<=0) AS missing_or_invalid_price,
                       count(*) FILTER (WHERE coalesce(cardinality(p.imagenes),0)=0) AS missing_images
                FROM public.propiedades p
                LEFT JOIN public.inmobiliarias_main i ON i.id=p.inmobiliaria_id
                GROUP BY coalesce(i.estrategia_scraping,'UNCLASSIFIED')
                ORDER BY total_rows DESC
                """,
            )
            table_summary = fetch(
                cur,
                """
                SELECT 'public.propiedades' AS table_name, count(*)::bigint AS total_rows,
                       count(DISTINCT inmobiliaria_id)::bigint AS distinct_agencies,
                       count(*) FILTER (
                         WHERE lower(coalesce(estado,'')) IN ('activo','activa')
                       )::bigint AS active_rows,
                       count(*) FILTER (
                         WHERE lower(coalesce(estado,'')) NOT IN ('activo','activa')
                       )::bigint AS non_active_rows,
                       min(created_at) AS min_created_at, max(created_at) AS max_created_at,
                       min(updated_at) AS min_updated_at, max(updated_at) AS max_updated_at
                FROM public.propiedades
                """,
            )
            agency_anomalies = fetch(
                cur,
                """
                SELECT id AS agency_id, nombre, slug, web, url_listado,
                       cms_detectado, estrategia_scraping,
                       CASE
                         WHEN nombre IS NULL OR btrim(nombre)='' THEN 'MISSING_NAME'
                         WHEN slug IS NULL OR btrim(slug)='' THEN 'MISSING_SLUG'
                         WHEN web IS NULL OR btrim(web)='' THEN 'MISSING_WEB'
                         WHEN web !~* '^https?://' THEN 'INVALID_WEB'
                         WHEN url_listado IS NULL OR btrim(url_listado)='' THEN 'MISSING_LISTING_URL'
                         WHEN scraping_id_origen IS NULL THEN 'MISSING_SOURCE_ID'
                         ELSE 'NO_ACTION_REQUIRED'
                       END AS classification
                FROM public.inmobiliarias_main
                ORDER BY id
                """,
            )

    write_csv(out / "table_quality_summary.csv", table_summary, list(table_summary[0]))
    source_fields = list(source_quality[0]) if source_quality else ["status"]
    write_csv(out / "source_quality_summary.csv", source_quality, source_fields)
    write_csv(out / "inmobiliaria_quality_summary.csv", source_quality, source_fields)
    write_csv(out / "cms_quality_summary.csv", cms_quality, list(cms_quality[0]) if cms_quality else ["status"])
    write_csv(out / "parser_family_quality_summary.csv", parser_quality, list(parser_quality[0]) if parser_quality else ["status"])
    write_csv(
        out / "developer_quality_summary.csv",
        [{"status": "NOT_PRESENT", "detail": "No canonical developer table or desarrolladora_id column exists in the audited schema"}],
        ["status", "detail"],
    )
    write_csv(
        out / "agency_row_anomalies.csv",
        agency_anomalies,
        list(agency_anomalies[0]) if agency_anomalies else ["status"],
    )

    matrix = []
    for item in grouped.values():
        affected = item["affected_rows"]
        internal = item["category"] == "INTERNAL_CORRECTABLE"
        priority = "P0" if item["severity"] == "critical" and internal else "P1" if internal and affected >= 100 else "P2"
        matrix.append(
            {
                "anomaly_type": item["anomaly_type"],
                "category": item["category"],
                "root_cause": item["root_cause"],
                "severity": item["severity"],
                "affected_rows": affected,
                "affected_sources": len(item["affected_sources"]),
                "priority": priority,
            }
        )
    matrix.sort(key=lambda row: (row["priority"], -row["affected_rows"], row["anomaly_type"]))
    matrix_fields = ["anomaly_type", "category", "root_cause", "severity", "affected_rows", "affected_sources", "priority"]
    write_csv(out / "root_cause_matrix.csv", matrix, matrix_fields)
    write_csv(out / "fix_priority_matrix.csv", matrix, matrix_fields)
    write_csv(out / "column_level_anomalies.csv", matrix, matrix_fields)
    write_csv(out / "column_quality_profile.csv", matrix, matrix_fields)

    flag_rows = [
        {
            "flag": rule[1].casefold(),
            "field": rule[0],
            "severity": rule[4],
            "category": rule[2],
            "rule": rule[5],
            "persistence": "derived_view_or_query",
        }
        for rule in RULES
    ]
    write_csv(
        out / "quality_flag_definitions.csv",
        flag_rows,
        ["flag", "field", "severity", "category", "rule", "persistence"],
    )
    summary = {
        "generated_utc": generated,
        "properties": int(table_summary[0]["total_rows"]),
        "anomalies": anomaly_count,
        "anomaly_families": len(matrix),
        "internal_correctable_rows": category_counts["INTERNAL_CORRECTABLE"],
        "historical_debt_rows": category_counts["HISTORICAL_DEBT"],
        "ambiguous_rows": category_counts["AMBIGUOUS"],
        "external_quality_rows": category_counts["EXTERNAL_SOURCE_MISSING_DATA"],
        "duplicate_groups": {key: len(rows) for key, rows in duplicates.items()},
        "sources": len(source_quality),
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
