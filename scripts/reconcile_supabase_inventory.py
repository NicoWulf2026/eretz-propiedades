#!/usr/bin/env python
"""Reconciliación determinista del write set directo contra Supabase.

El script no abre conexiones ni conoce credenciales. Recibe un snapshot mínimo
generado exclusivamente con SELECT, lo indexa en SQLite y produce artefactos
auditables. Los JSONL grandes permanecen fuera de Git.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import sqlite3
import sys
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from connectors.base import (  # noqa: E402
    MONEDAS_VALIDAS,
    OPERACIONES_VALIDAS,
    TIPOS_VALIDOS,
    calcular_hash_dedup,
    normalizar_url,
)
from scripts.write_eligibility import motivo_rechazo  # noqa: E402

SCHEMA_VERSION = "eretz_supabase_reconciliation_v1"
CLASSIFICATIONS = (
    "EXISTS_UNCHANGED",
    "EXISTS_CHANGED",
    "TRULY_NEW",
    "DUPLICATE_OR_CONFLICT",
    "AGENCY_ID_UNRESOLVED",
    "INVALID_OR_REJECTED",
)
SUBSTANTIVE_FIELDS = (
    "titulo", "descripcion", "precio", "moneda", "tipo_propiedad",
    "operacion", "superficie_total", "superficie_cubierta", "direccion",
    "barrio", "ciudad", "provincia", "latitud", "longitud", "imagenes",
    "ambientes", "dormitorios", "banos",
)
DIGEST_FIELDS = SUBSTANTIVE_FIELDS + ("imagenes_orden",)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip()).lower()


def _number(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return _text(value)
    if not number.is_finite():
        return _text(value)
    return format(number.normalize(), "f")


def _digest(value: str) -> str:
    return hashlib.md5(value.encode("utf-8"), usedforsecurity=False).hexdigest()


def _images(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def digests(record: dict[str, Any]) -> dict[str, str]:
    images = _images(record.get("imagenes"))
    normalizers = {
        "precio": _number,
        "superficie_total": _number,
        "superficie_cubierta": _number,
        "latitud": _number,
        "longitud": _number,
        "ambientes": _number,
        "dormitorios": _number,
        "banos": _number,
    }
    result: dict[str, str] = {}
    for field in SUBSTANTIVE_FIELDS:
        if field == "imagenes":
            result[field] = _digest("\n".join(sorted(images)))
        else:
            result[field] = _digest(normalizers.get(field, _text)(record.get(field)))
    result["imagenes_orden"] = _digest("\n".join(images))
    return result


def _connect(path: Path, configure_journal: bool = True) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute("pragma busy_timeout=30000")
    if configure_journal:
        connection.execute("pragma journal_mode=WAL")
        connection.execute("pragma synchronous=NORMAL")
    connection.execute("pragma temp_store=MEMORY")
    return connection


def _disable_windows_console_echo() -> None:
    """Avoid reflecting large JSON batches when an orchestrator writes to a ConPTY."""
    if os.name != "nt" or not sys.stdin.isatty():
        return
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
    mode = ctypes.c_uint()
    if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        kernel32.SetConsoleMode(handle, mode.value & ~0x0004)  # ENABLE_ECHO_INPUT


def _create_schema(connection: sqlite3.Connection) -> None:
    digest_columns = ",\n".join(f"d_{field} text not null" for field in DIGEST_FIELDS)
    connection.executescript(f"""
        create table metadata(key text primary key, value text not null);
        create table agencies(id integer primary key);
        create table inputs(
            seq integer primary key,
            hash_dedup text not null,
            source_url text not null,
            url_normalizada text not null,
            inmobiliaria_id integer,
            source_listing_id text,
            fingerprint text,
            connector text,
            valid integer not null,
            invalid_reasons text not null,
            {digest_columns}
        );
        create table dbrows(
            relation_name text not null,
            row_id integer not null,
            inmobiliaria_id integer,
            hash_dedup text,
            source_url text,
            url_normalizada text,
            source_listing_id text,
            fingerprint text,
            {digest_columns},
            primary key(relation_name, row_id)
        );
        create table results(
            seq integer primary key,
            classification text not null,
            match_relation text,
            match_id integer,
            match_reason text,
            change_kind text,
            changed_fields text not null,
            non_substantive_fields text not null,
            conflict_agencies text not null,
            notes text not null
        );
        create table input_resolutions(
            url_normalizada text primary key,
            owner_agency_id integer not null,
            category text not null,
            evidence text not null
        );
    """)
    connection.execute("insert into metadata values('schema_version', ?)", (SCHEMA_VERSION,))
    connection.commit()


def _validation_reasons(record: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    hash_value = str(record.get("hash_dedup") or "").strip()
    url = str(record.get("source_url") or "").strip()
    agency = record.get("inmobiliaria_id")
    if not hash_value:
        reasons.append("sin_hash_dedup")
    if not url:
        reasons.append("sin_url")
    elif not normalizar_url(url):
        reasons.append("url_no_normalizable")
    rejected = motivo_rechazo(record)
    if rejected:
        reasons.append(f"url_rechazada:{rejected}")
    if not isinstance(agency, int) or isinstance(agency, bool) or agency <= 0:
        reasons.append("inmobiliaria_id_invalido")
    elif agency > 2_147_483_647:
        reasons.append("inmobiliaria_id_fuera_integer")
    if record.get("moneda") and record["moneda"] not in MONEDAS_VALIDAS:
        reasons.append("moneda_invalida")
    operation = record.get("operacion") or "consultar"
    if operation not in OPERACIONES_VALIDAS:
        reasons.append("operacion_invalida")
    if record.get("tipo_propiedad") and record["tipo_propiedad"] not in TIPOS_VALIDOS:
        reasons.append("tipo_propiedad_invalido")
    if hash_value and isinstance(agency, int) and url:
        expected = calcular_hash_dedup(agency, url)
        if hash_value != expected:
            reasons.append("hash_no_corresponde_agencia_url")
    return sorted(set(reasons))


def _write_report(path: Path, metrics: dict[str, Any]) -> None:
    lines = [
        "# WRITE SET VALIDATION",
        "",
        f"Schema: `{SCHEMA_VERSION}`",
        "",
        "## Invariantes",
        "",
        "| Métrica | Valor | Estado |",
        "| --- | ---: | --- |",
    ]
    checks = [
        ("TOTAL", metrics["total"], metrics["invalid_json"] == 0),
        ("JSON inválido", metrics["invalid_json"], metrics["invalid_json"] == 0),
        ("Hashes únicos", metrics["unique_hashes"], metrics["unique_hashes"] == metrics["total"]),
        ("URLs normalizadas únicas", metrics["unique_urls"], metrics["unique_urls"] == metrics["total"]),
        ("URLs multi-agency", metrics["multi_agency_urls"], metrics["multi_agency_urls"] == 0),
        ("Filas inválidas", metrics["invalid_rows"], metrics["invalid_rows"] == 0),
    ]
    for name, value, passed in checks:
        lines.append(f"| {name} | {value:,} | {'PASS' if passed else 'FAIL'} |")
    lines.extend([
        "",
        "## Cobertura",
        "",
        f"- Agencias declaradas: **{metrics['agencies']:,}**",
        f"- Connectors: `{json.dumps(metrics['connectors'], ensure_ascii=False, sort_keys=True)}`",
        f"- Motivos de rechazo: `{json.dumps(metrics['reasons'], ensure_ascii=False, sort_keys=True)}`",
        "",
        "## Veredicto",
        "",
        "**PASS**" if all(item[2] for item in checks) else "**FAIL — no escribir en Supabase.**",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def prepare(args: argparse.Namespace) -> int:
    source = Path(args.write_set)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    database = output / "SUPABASE_RECONCILIATION.sqlite3"
    if database.exists():
        database.unlink()
    connection = _connect(database)
    connection.execute("pragma synchronous=OFF")
    connection.execute("pragma journal_mode=MEMORY")
    _create_schema(connection)

    seen_hashes: set[str] = set()
    seen_source_urls: set[str] = set()
    seen_urls: dict[str, int] = {}
    multi_urls: set[str] = set()
    agencies: set[int] = set()
    connectors: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    total = invalid_json = invalid_rows = 0
    insert_sql = "insert into inputs values(" + ",".join(["?"] * (10 + len(DIGEST_FIELDS))) + ")"
    pending_values: list[list[Any]] = []

    with source.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            total += 1
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                invalid_json += 1
                continue
            row_reasons = _validation_reasons(record)
            invalid_rows += bool(row_reasons)
            reasons.update(row_reasons)
            hash_value = str(record.get("hash_dedup") or "").strip()
            source_url = str(record.get("source_url") or "")
            normalized = normalizar_url(record.get("source_url"))
            agency = record.get("inmobiliaria_id") if isinstance(record.get("inmobiliaria_id"), int) else None
            if hash_value in seen_hashes:
                reasons["hash_duplicado"] += 1
            seen_hashes.add(hash_value)
            seen_source_urls.add(source_url)
            previous = seen_urls.get(normalized)
            if previous is not None and previous != agency:
                multi_urls.add(normalized)
            else:
                seen_urls[normalized] = agency
            if agency is not None:
                agencies.add(agency)
            connectors[str(record.get("connector") or "unknown")] += 1
            field_digests = digests(record)
            values = [
                line_number, hash_value, str(record.get("source_url") or ""), normalized,
                agency, str(record.get("source_listing_id") or ""),
                str(record.get("fingerprint") or ""), str(record.get("connector") or ""),
                int(not row_reasons), json.dumps(row_reasons, ensure_ascii=False),
            ] + [field_digests[field] for field in DIGEST_FIELDS]
            pending_values.append(values)
            if len(pending_values) >= 1000:
                connection.executemany(insert_sql, pending_values)
                pending_values.clear()
            if total % 10000 == 0:
                connection.commit()
                print(f"validated={total}", flush=True)
    if pending_values:
        connection.executemany(insert_sql, pending_values)
    connection.commit()
    metrics = {
        "total": total,
        "invalid_json": invalid_json,
        "unique_hashes": len(seen_hashes),
        "unique_source_urls": len(seen_source_urls),
        "unique_urls": len(seen_urls),
        "multi_agency_urls": len(multi_urls),
        "invalid_rows": invalid_rows,
        "agencies": len(agencies),
        "connectors": dict(connectors),
        "reasons": dict(reasons),
    }
    connection.execute("insert into metadata values('write_set_metrics', ?)", (json.dumps(metrics),))
    connection.execute("insert into metadata values('write_set_path', ?)", (str(source.resolve()),))
    connection.commit()
    _write_report(output / "WRITE_SET_VALIDATION.md", metrics)
    (output / "WRITE_SET_VALIDATION.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, sort_keys=True))
    return 0 if not invalid_json and not invalid_rows and len(seen_hashes) == total and len(seen_source_urls) == total and len(seen_urls) == total and not multi_urls else 2


def ingest_snapshot(args: argparse.Namespace) -> int:
    _disable_windows_console_echo()
    connection = _connect(Path(args.database))
    columns = [
        "relation_name", "row_id", "inmobiliaria_id", "hash_dedup", "source_url",
        "url_normalizada", "source_listing_id", "fingerprint",
    ] + [f"d_{field}" for field in DIGEST_FIELDS]
    sql = "insert or replace into dbrows(" + ",".join(columns) + ") values(" + ",".join(["?"] * len(columns)) + ")"
    inserted = 0
    for line in sys.stdin:
        if not line.strip():
            continue
        payload = json.loads(line)
        if payload.get("_end"):
            break
        relation = payload["relation"]
        rows = payload.get("rows") or []
        connection.executemany(sql, [
            [relation] + [row.get(column) for column in columns[1:]] for row in rows
        ])
        inserted += len(rows)
        connection.commit()
        print(f"ingested={inserted}", flush=True)
    connection.close()
    return 0


def ingest_agencies(args: argparse.Namespace) -> int:
    _disable_windows_console_echo()
    connection = _connect(Path(args.database))
    for line in sys.stdin:
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict) and payload.get("_end"):
            break
        rows = payload if isinstance(payload, list) else payload.get("rows", [])
        connection.executemany("insert or ignore into agencies(id) values(?)", [(int(row["id"]),) for row in rows])
        connection.commit()
    print(f"agencies={connection.execute('select count(*) from agencies').fetchone()[0]}")
    return 0


def ingest_resolutions(args: argparse.Namespace) -> int:
    connection = _connect(Path(args.database))
    connection.execute("""
        create table if not exists input_resolutions(
            url_normalizada text primary key,
            owner_agency_id integer not null,
            category text not null,
            evidence text not null
        )
    """)
    values = []
    for item in rows_from_jsonl(Path(args.file)):
        values.append((
            item["url_normalizada"], int(item["owner_agency_id"]),
            item["category"], json.dumps(item.get("evidence") or [], ensure_ascii=False),
        ))
    connection.executemany("insert or replace into input_resolutions values(?,?,?,?)", values)
    connection.commit()
    print(f"resolutions={len(values)}")
    return 0


def rows_from_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    for line in path.open(encoding="utf-8"):
        if line.strip():
            yield json.loads(line)


def _sql_text(expression: str) -> str:
    return f"md5(lower(regexp_replace(trim(coalesce(({expression})::text,'')), E'\\\\s+', ' ', 'g')))"


def _sql_number(expression: str) -> str:
    normalized = (
        f"regexp_replace(regexp_replace(({expression})::numeric::text, "
        "'(\\.[0-9]*?)0+$', '\\1'), '\\.$', '')"
    )
    return f"md5(case when ({expression}) is null then '' when ({expression})::numeric=0 then '0' else {normalized} end)"


def snapshot_sql(relation: str, after: int, limit: int) -> str:
    specs = {
        "raw": {
            "table": "internal_scraping.propiedades_raw", "url": "url", "direction": "direccion_raw",
            "source_id": "datos_extra->>'source_listing_id'", "fingerprint": "datos_extra->>'fingerprint'",
            "ambientes": "nullif(datos_extra->>'ambientes','')", "dormitorios": "nullif(datos_extra->>'dormitorios','')",
            "banos": "nullif(datos_extra->>'banos','')", "images": "imagenes", "images_kind": "jsonb",
        },
        "staging": {
            "table": "internal_scraping.propiedades_staging", "url": "url", "direction": "direccion_normalizada",
            "source_id": "null::text", "fingerprint": "null::text", "ambientes": "null::numeric",
            "dormitorios": "null::numeric", "banos": "null::numeric", "images": "imagenes", "images_kind": "jsonb",
        },
        "public": {
            "table": "public.propiedades", "url": "url", "direction": "direccion",
            "source_id": "id_externo", "fingerprint": "null::text", "ambientes": "ambientes",
            "dormitorios": "dormitorios", "banos": "banos", "images": "imagenes", "images_kind": "array",
        },
    }
    spec = specs[relation]
    text_fields = {
        "titulo": "titulo", "descripcion": "descripcion", "moneda": "moneda",
        "tipo_propiedad": "tipo_propiedad", "operacion": "operacion",
        "direccion": spec["direction"], "barrio": "barrio", "ciudad": "ciudad", "provincia": "provincia",
    }
    numeric_fields = {
        "precio": "precio", "superficie_total": "superficie_total", "superficie_cubierta": "superficie_cubierta",
        "latitud": "latitud", "longitud": "longitud", "ambientes": spec["ambientes"],
        "dormitorios": spec["dormitorios"], "banos": spec["banos"],
    }
    selects = [
        "id as row_id", "inmobiliaria_id", "hash_dedup", f"{spec['url']} as source_url",
        "url_normalizada", f"{spec['source_id']} as source_listing_id", f"{spec['fingerprint']} as fingerprint",
    ]
    for field in SUBSTANTIVE_FIELDS:
        if field == "imagenes":
            continue
        expression = text_fields.get(field)
        selects.append(f"{_sql_text(expression) if expression else _sql_number(numeric_fields[field])} as d_{field}")
    if spec["images_kind"] == "jsonb":
        values = f"jsonb_array_elements_text(coalesce({spec['images']}, '[]'::jsonb)) with ordinality as image(value, ordinal)"
    else:
        values = f"unnest(coalesce({spec['images']}, array[]::text[])) with ordinality as image(value, ordinal)"
    clean = "lower(regexp_replace(trim(image.value), E'\\\\s+', ' ', 'g'))"
    selects.append("image_hash.d_imagenes")
    selects.append("image_hash.d_imagenes_orden")
    image_lateral = (
        "left join lateral (select "
        f"md5(coalesce(string_agg({clean}, E'\\n' order by {clean}),'')) as d_imagenes, "
        f"md5(coalesce(string_agg({clean}, E'\\n' order by image.ordinal),'')) as d_imagenes_orden "
        f"from {values}) image_hash on true"
    )
    return (
        "select\n  " + ",\n  ".join(selects) + f"\nfrom {spec['table']}\n"
        f"{image_lateral}\n"
        f"where id > {int(after)}\norder by id\nlimit {int(limit)};"
    )


def targeted_snapshot_sql(relation: str, keys: list[dict[str, Any]]) -> str:
    """Return a SELECT-only snapshot restricted to reconciliation candidates."""
    specs = {
        # source_listing_id is retained in returned candidates but is not used to
        # discover them: it is neither globally unique nor indexed consistently.
        "raw": ("internal_scraping.propiedades_raw", None),
        "staging": ("internal_scraping.propiedades_staging", None),
        "public": ("public.propiedades", None),
    }
    table, external_expression = specs[relation]
    compact_keys = [{
        "h": item.get("hash_dedup") or "",
        "u": item.get("url_normalizada") or "",
        "a": item.get("inmobiliaria_id"),
        "s": item.get("source_listing_id") or "",
    } for item in keys]
    encoded = json.dumps(compact_keys, ensure_ascii=False, separators=(",", ":")).replace("'", "''")
    candidate_queries = [
        f"select d.id from {table} d join keys k on d.hash_dedup=k.h where k.h<>''",
        f"select d.id from {table} d join keys k on d.url_normalizada=k.u where k.u<>''",
    ]
    if external_expression:
        candidate_queries.append(
            f"select d.id from {table} d join keys k on d.inmobiliaria_id=k.a "
            f"and ({external_expression})=k.s where k.s<>''"
        )
    candidates = "\nunion\n".join(candidate_queries)
    base = snapshot_sql(relation, 0, 1)
    base = base.replace("where id > 0\norder by id\nlimit 1;", "where id in (select id from candidate_ids)\norder by id;")
    return (
        "with keys as (select * from json_to_recordset('" + encoded + "'::json) "
        "as k(h text,u text,a bigint,s text)),\n"
        "candidate_ids as (\n" + candidates + "\n)\n" + base
    )


def render_targeted_snapshot_sql(args: argparse.Namespace) -> int:
    connection = _connect(Path(args.database), configure_journal=False)
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        create index if not exists idx_dbrows_hash on dbrows(hash_dedup);
        create index if not exists idx_dbrows_url on dbrows(url_normalizada);
        create index if not exists idx_dbrows_relation_hash on dbrows(relation_name,hash_dedup);
        create index if not exists idx_dbrows_relation_url on dbrows(relation_name,url_normalizada);
    """)
    exclusion = ""
    params: list[Any] = [args.after]
    if args.exclude_relation:
        exclusion = (
            " and not exists (select 1 from dbrows d where d.relation_name=? and d.hash_dedup=i.hash_dedup)"
            " and not exists (select 1 from dbrows d where d.relation_name=? and d.url_normalizada=i.url_normalizada)"
        )
        params.append(args.exclude_relation)
        params.append(args.exclude_relation)
    params.append(args.limit)
    rows = [dict(row) for row in connection.execute(
        "select i.seq,i.hash_dedup,i.url_normalizada,i.inmobiliaria_id,i.source_listing_id "
        "from inputs i where i.seq>?" + exclusion + " order by i.seq limit ?", params)]
    relations = (args.relation,) if args.relation else ("raw", "staging", "public")
    payload = {
        "after": rows[-1]["seq"] if rows else args.after,
        "count": len(rows),
        "queries": {relation: targeted_snapshot_sql(relation, rows) for relation in relations},
    }
    # ASCII transport avoids Windows console-codepage failures on scraped URLs.
    print(json.dumps(payload, ensure_ascii=True))
    return 0


def clear_snapshot(args: argparse.Namespace) -> int:
    connection = _connect(Path(args.database))
    deleted = connection.execute("select count(*) from dbrows").fetchone()[0]
    connection.execute("delete from dbrows")
    connection.commit()
    print(f"deleted_local_snapshot_rows={deleted}")
    return 0


def render_snapshot_sql(args: argparse.Namespace) -> int:
    print(snapshot_sql(args.relation, args.after, args.limit))
    return 0


def _candidate(connection: sqlite3.Connection, row: sqlite3.Row) -> tuple[sqlite3.Row | None, str, list[int]]:
    normalized = row["url_normalizada"]
    agency = row["inmobiliaria_id"]
    conflicts = []
    if normalized:
        conflicts = [item[0] for item in connection.execute(
            "select distinct inmobiliaria_id from dbrows where url_normalizada=? and inmobiliaria_id is not null and inmobiliaria_id<>?",
            (normalized, agency),
        )]
    priorities = {"internal_scraping.propiedades_raw": 0, "internal_scraping.propiedades_staging": 1, "public.propiedades": 2}
    queries = [
        ("HASH_DEDUP", "select * from dbrows where hash_dedup=?", (row["hash_dedup"],)),
        ("AGENCY_URL", "select * from dbrows where inmobiliaria_id=? and url_normalizada=?", (agency, normalized)),
        ("AGENCY_EXTERNAL_ID", "select * from dbrows where inmobiliaria_id=? and source_listing_id=? and source_listing_id<>''", (agency, row["source_listing_id"])),
    ]
    for reason, sql, params in queries:
        matches = list(connection.execute(sql, params))
        if matches:
            matches.sort(key=lambda match: priorities.get(match["relation_name"], 99))
            return matches[0], reason, sorted(conflicts)
    return None, "", sorted(conflicts)


def reconcile(args: argparse.Namespace) -> int:
    database = Path(args.database)
    connection = _connect(database)
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        create index if not exists idx_inputs_url on inputs(url_normalizada);
        create index if not exists idx_inputs_agency_url on inputs(inmobiliaria_id,url_normalizada);
        create index if not exists idx_dbrows_hash on dbrows(hash_dedup);
        create index if not exists idx_dbrows_url on dbrows(url_normalizada);
        create index if not exists idx_dbrows_agency_url on dbrows(inmobiliaria_id,url_normalizada);
        create index if not exists idx_dbrows_agency_external on dbrows(inmobiliaria_id,source_listing_id);
        delete from results;
    """)
    known_agencies = {row[0] for row in connection.execute("select id from agencies")}
    counts: Counter[str] = Counter()
    fields: Counter[str] = Counter()
    change_kinds: Counter[str] = Counter()
    input_rows = connection.execute("select * from inputs order by seq")
    for index, row in enumerate(input_rows, 1):
        classification = ""
        match = None
        reason = ""
        changed: list[str] = []
        non_substantive: list[str] = []
        conflict_agencies: list[int] = []
        notes: list[str] = []
        if not row["valid"]:
            classification = "INVALID_OR_REJECTED"
            notes = json.loads(row["invalid_reasons"])
        elif row["inmobiliaria_id"] not in known_agencies:
            classification = "AGENCY_ID_UNRESOLVED"
            notes = ["inmobiliaria_id no existe en public.inmobiliarias_main"]
        else:
            input_conflicts = [item[0] for item in connection.execute(
                "select distinct inmobiliaria_id from inputs where url_normalizada=? and seq<>? and inmobiliaria_id is not null",
                (row["url_normalizada"], row["seq"]),
            )]
            resolution = connection.execute(
                "select * from input_resolutions where url_normalizada=?", (row["url_normalizada"],)
            ).fetchone()
            if input_conflicts and (resolution is None or resolution["owner_agency_id"] != row["inmobiliaria_id"]):
                classification = "DUPLICATE_OR_CONFLICT"
                conflict_agencies = sorted(set(input_conflicts))
                notes = ["URL normalizada duplicada dentro del write set"]
            else:
                if resolution is not None:
                    notes.append(f"conflicto resuelto a favor de agencia {resolution['owner_agency_id']}: {resolution['category']}")
                match, reason, conflict_agencies = _candidate(connection, row)
                if conflict_agencies and (resolution is None or resolution["owner_agency_id"] != row["inmobiliaria_id"]):
                    classification = "DUPLICATE_OR_CONFLICT"
                    notes.append("URL normalizada presente bajo otra inmobiliaria en Supabase")
                elif match is None:
                    classification = "TRULY_NEW"
            if match is not None and not classification:
                for field in SUBSTANTIVE_FIELDS:
                    if row[f"d_{field}"] != match[f"d_{field}"]:
                        changed.append(field)
                if row["d_imagenes"] == match["d_imagenes"] and row["d_imagenes_orden"] != match["d_imagenes_orden"]:
                    non_substantive.append("orden_imagenes")
                fingerprint_changed = bool(
                    match["relation_name"] == "internal_scraping.propiedades_raw"
                    and row["fingerprint"] and match["fingerprint"]
                    and row["fingerprint"] != match["fingerprint"]
                )
                classification = "EXISTS_CHANGED" if changed or fingerprint_changed else "EXISTS_UNCHANGED"
                if fingerprint_changed and not changed:
                    notes.append("fingerprint cambió sin diferencia en campos comparables")
                if changed and row["fingerprint"] and match["fingerprint"] and row["fingerprint"] == match["fingerprint"]:
                    notes.append("fingerprint coincide pero los campos comparables difieren")
        change_kind = None
        if classification == "EXISTS_CHANGED":
            change_kind = "SUBSTANTIVE_CHANGE" if changed else "NON_SUBSTANTIVE_CHANGE"
            change_kinds[change_kind] += 1
        counts[classification] += 1
        fields.update(changed)
        connection.execute(
            "insert into results values(?,?,?,?,?,?,?,?,?,?)",
            (
                row["seq"], classification,
                match["relation_name"] if match else None,
                match["row_id"] if match else None,
                reason or None, change_kind,
                json.dumps(changed, ensure_ascii=False),
                json.dumps(non_substantive, ensure_ascii=False),
                json.dumps(conflict_agencies), json.dumps(notes, ensure_ascii=False),
            ),
        )
        if index % 5000 == 0:
            connection.commit()
            print(f"reconciled={index}", flush=True)
    connection.commit()
    total = sum(counts.values())
    if set(counts) - set(CLASSIFICATIONS) or total != connection.execute("select count(*) from inputs").fetchone()[0]:
        raise RuntimeError("la reconciliación no cierra")
    metrics = {"total": total, "classifications": dict(counts), "changed_fields": dict(fields), "change_kinds": dict(change_kinds)}
    connection.execute("insert or replace into metadata values('reconciliation_metrics', ?)", (json.dumps(metrics),))
    connection.commit()
    print(json.dumps(metrics, ensure_ascii=False, sort_keys=True))
    return 0


def export(args: argparse.Namespace) -> int:
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    connection = _connect(Path(args.database))
    connection.row_factory = sqlite3.Row
    metrics = json.loads(connection.execute("select value from metadata where key='reconciliation_metrics'").fetchone()[0])
    with (output / "SUPABASE_RECONCILIATION.jsonl").open("w", encoding="utf-8") as reconciliation, (output / "SUPABASE_WRITE_PLAN.jsonl").open("w", encoding="utf-8") as plan:
        for row in connection.execute("""
            select i.seq,i.hash_dedup,i.source_url,i.url_normalizada,i.inmobiliaria_id,
                   i.source_listing_id,i.connector,r.*
            from inputs i join results r using(seq) order by i.seq
        """):
            item = dict(row)
            item["changed_fields"] = json.loads(item["changed_fields"])
            item["non_substantive_fields"] = json.loads(item["non_substantive_fields"])
            item["conflict_agencies"] = json.loads(item["conflict_agencies"])
            item["notes"] = json.loads(item["notes"])
            reconciliation.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
            action = {
                "EXISTS_UNCHANGED": "NOOP",
                "EXISTS_CHANGED": "UPDATE_CANDIDATE",
                "TRULY_NEW": "INSERT",
            }.get(item["classification"], "HOLD")
            plan.write(json.dumps({
                "input_seq": item["seq"], "hash_dedup": item["hash_dedup"],
                "source_url": item["source_url"], "url_normalizada": item["url_normalizada"],
                "inmobiliaria_id": item["inmobiliaria_id"], "classification": item["classification"],
                "action": action, "changed_fields": item["changed_fields"], "notes": item["notes"],
            }, ensure_ascii=False, sort_keys=True) + "\n")
    classifications = metrics["classifications"]
    lines = [
        "# SUPABASE RECONCILIATION SUMMARY", "",
        f"Total analizado: **{metrics['total']:,}**", "",
        "| Categoría | Filas |", "| --- | ---: |",
    ]
    for classification in CLASSIFICATIONS:
        lines.append(f"| {classification} | {classifications.get(classification, 0):,} |")
    lines.extend([
        "", f"Suma: **{sum(classifications.values()):,}**", "",
        "## Cambios por campo", "",
        "```json", json.dumps(metrics["changed_fields"], ensure_ascii=False, indent=2, sort_keys=True), "```", "",
        "## Política", "",
        "- `EXISTS_UNCHANGED` → `NOOP`",
        "- `EXISTS_CHANGED` → `UPDATE_CANDIDATE`; no se amplían privilegios.",
        "- `TRULY_NEW` → `INSERT` candidato, sujeto a canary mínimo.",
        "- Conflictos, agencias no resueltas e inválidos → `HOLD`.",
        "- No se ejecutó `UPDATE`, `DELETE` ni desactivación por ausencia.",
    ])
    (output / "SUPABASE_RECONCILIATION_SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    commands = root.add_subparsers(dest="command", required=True)
    command = commands.add_parser("prepare")
    command.add_argument("--write-set", required=True)
    command.add_argument("--output-dir", required=True)
    command.set_defaults(func=prepare)
    command = commands.add_parser("ingest-snapshot")
    command.add_argument("--database", required=True)
    command.set_defaults(func=ingest_snapshot)
    command = commands.add_parser("ingest-agencies")
    command.add_argument("--database", required=True)
    command.set_defaults(func=ingest_agencies)
    command = commands.add_parser("ingest-resolutions")
    command.add_argument("--database", required=True)
    command.add_argument("--file", required=True)
    command.set_defaults(func=ingest_resolutions)
    command = commands.add_parser("render-snapshot-sql")
    command.add_argument("--relation", required=True, choices=("raw", "staging", "public"))
    command.add_argument("--after", type=int, default=0)
    command.add_argument("--limit", type=int, default=2000)
    command.set_defaults(func=render_snapshot_sql)
    command = commands.add_parser("render-targeted-snapshot-sql")
    command.add_argument("--database", required=True)
    command.add_argument("--after", type=int, default=0)
    command.add_argument("--limit", type=int, default=1000)
    command.add_argument("--relation", choices=("raw", "staging", "public"))
    command.add_argument("--exclude-relation")
    command.set_defaults(func=render_targeted_snapshot_sql)
    command = commands.add_parser("clear-snapshot")
    command.add_argument("--database", required=True)
    command.set_defaults(func=clear_snapshot)
    command = commands.add_parser("reconcile")
    command.add_argument("--database", required=True)
    command.set_defaults(func=reconcile)
    command = commands.add_parser("export")
    command.add_argument("--database", required=True)
    command.add_argument("--output-dir", required=True)
    command.set_defaults(func=export)
    return root


if __name__ == "__main__":
    arguments = parser().parse_args()
    raise SystemExit(arguments.func(arguments))
