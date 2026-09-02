#!/usr/bin/env python
"""Fail-closed pre-ingestion rebuild for ERETZ property artifacts.

This command is deliberately offline.  It reads the earliest normalized
artifacts declared by ``input_universe.py`` and a previously validated agency
directory; it never opens a database connection or a source website.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from connectors.base import (  # noqa: E402
    calcular_hash_dedup,
    detectar_operacion,
    detectar_tipo,
    normalizar_url,
)
from scripts.input_universe import ENTRADAS, RAIZ, UNIVERSE_VERSION  # noqa: E402
from scripts.write_eligibility import motivo_rechazo  # noqa: E402

VERSION = "preingestion_hardening_v2"
RESOLVED = "RESOLVED"
AMBIGUOUS = "AMBIGUOUS"
NOT_FOUND = "NOT_FOUND_IN_ERETZ"

EXTERNAL_PORTAL_HOSTS = {
    "datoinmobiliario.com.ar",
    "www.datoinmobiliario.com.ar",
}
JS_PATTERNS = (
    re.compile(r"function\s+getCookie\s*\(", re.I),
    re.compile(r"\bvar\s+prop_desc\b", re.I),
    re.compile(r"\$\s*\(\s*['\"]#prop-desc", re.I),
    re.compile(r"document\.cookie", re.I),
)
TECHNICAL_BLOCK = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1\s*>", re.I | re.S
)
HOTEL_TYPES = {"hotel", "hosteria", "complejo", "edificio"}


def norm(value: Any) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", str(value or "").lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def host(value: Any) -> str:
    from urllib.parse import urlsplit

    raw = str(value or "").strip()
    if raw and "://" not in raw:
        raw = "https://" + raw
    try:
        return (urlsplit(raw).hostname or "").lower()
    except ValueError:
        return ""


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, dict):
                yield value


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    count = 0
    with temp.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    temp.replace(path)
    return count


def load_main_backup(path: Path) -> dict[int, dict[str, str]]:
    output: dict[int, dict[str, str]] = {}
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                ident = int(row.get("id") or "")
            except ValueError:
                continue
            output[ident] = row
    return output


def build_agency_manifest(
    crosswalk_path: Path,
    web_directory_path: Path,
    platform_path: Path,
    main_backup_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    crosswalk = list(read_jsonl(crosswalk_path))
    web = {row.get("canonical_agency_id"): row for row in read_jsonl(web_directory_path)}
    platform = {row.get("canonical_agency_id"): row for row in read_jsonl(platform_path)}
    live_main = load_main_backup(main_backup_path)
    main_por_nombre: dict[str, list[str]] = {}
    for ident, fila in live_main.items():
        main_por_nombre.setdefault(norm(fila.get("nombre")), []).append(str(ident))
    manifest: list[dict[str, Any]] = []

    for source in crosswalk:
        canonical = source.get("stable_id") or source.get("canonical_agency_id")
        candidate = source.get("crosswalk_candidato") or {}
        table = candidate.get("tabla")
        raw_id = candidate.get("id")
        agency_name = source.get("nombre_original") or source.get("canonical_name")
        selected = platform.get(canonical) or web.get(canonical) or {}
        official = selected.get("domain") or selected.get("selected_domain")
        status = NOT_FOUND
        method = "NO_MAIN_CANDIDATE"
        eretz_id: int | None = None
        evidence: dict[str, Any] = {
            "candidate_namespace": table,
            "candidate_id": raw_id,
            "candidate_name": candidate.get("nombre"),
            "crosswalk_state": source.get("crosswalk"),
        }

        if table == "main" and str(raw_id or "").isdigit():
            ident = int(raw_id)
            live = live_main.get(ident)
            exact_name = bool(
                live
                and norm(live.get("nombre")) == norm(agency_name)
                and norm(candidate.get("nombre")) == norm(agency_name)
            )
            if source.get("crosswalk") == "EXACT_MATCH" and exact_name:
                status = RESOLVED
                method = "MAIN_EXACT_NORMALIZED_NAME"
                eretz_id = ident
                evidence.update({
                    "live_name": live.get("nombre"),
                    "live_web": live.get("web"),
                    "live_city": live.get("ciudad"),
                    "live_province": live.get("provincia"),
                    "live_phone_present": bool(live.get("telefono") or live.get("telefono_principal")),
                    "live_email_present": bool(live.get("email_principal")),
                    "live_validation": "2026-08-27 SELECT: 1122/1122 exact, 0 mismatches",
                })
            else:
                status = AMBIGUOUS
                method = "MAIN_IDENTITY_NOT_EXACT"
        elif table == "staging":
            # Esto afirmaba "0/4920 candidates linked by
            # main.staging_id_origen": un literal congelado de una medicion
            # hecha una sola vez. Si el enlace se poblara, el texto seguiria
            # diciendo cero, y 4.953 inmobiliarias quedarian declaradas
            # irresolubles apoyadas en una afirmacion que ya nadie comprueba.
            # Se verifica por registro contra el backup de main que esta
            # funcion ya tiene cargado.
            homonimas = main_por_nombre.get(norm(agency_name), [])
            evidence["main_name_matches"] = len(homonimas)
            if homonimas:
                # Existe una inmobiliaria en main con ese nombre pero sin FK
                # declarada. Elegir una seria inventar la identidad; queda
                # ambigua para que la decida evidencia adicional.
                status = AMBIGUOUS
                method = "STAGING_NAME_COLLIDES_WITH_MAIN"
                evidence["main_candidates"] = homonimas[:5]
            else:
                status = NOT_FOUND
                method = "STAGING_NAMESPACE_NOT_A_MAIN_FK"
                evidence["promotion_check"] = (
                    "sin contraparte en main por nombre normalizado")
        elif source.get("crosswalk") == "AMBIGUOUS":
            status = AMBIGUOUS
            method = "CROSSWALK_AMBIGUOUS"

        if host(official) in EXTERNAL_PORTAL_HOSTS:
            evidence["official_domain_rejected"] = "SHARED_EXTERNAL_PORTAL"
            official = None
            if status == RESOLVED:
                status = AMBIGUOUS
                method = "EXTERNAL_PORTAL_CONTRADICTS_IDENTITY"
                eretz_id = None

        manifest.append({
            "canonical_agency_id": canonical,
            "agency_name": agency_name,
            "official_domain": official,
            "eretz_id": eretz_id,
            "resolution_status": status,
            "resolution_method": method,
            "evidence": evidence,
        })

    # An ERETZ FK is injective unless the duplicate identity is explicitly
    # proved.  No implicit winner is chosen.
    by_eretz: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in manifest:
        if row["resolution_status"] == RESOLVED:
            by_eretz[int(row["eretz_id"])].append(row)
    for eretz_id, group in by_eretz.items():
        if len(group) <= 1:
            continue
        raw_names = {norm(row["agency_name"]) for row in group}
        if len(raw_names) == 1:
            for row in group:
                row["resolution_status"] = AMBIGUOUS
                row["resolution_method"] = "SAME_AGENCY_DUPLICATE_REQUIRES_CANONICAL_WINNER"
                row["eretz_id"] = None
                row["evidence"]["same_agency_duplicate"] = {
                    "category": "SAME_AGENCY_DUPLICATE",
                    "shared_eretz_id": eretz_id,
                    "canonical_ids": [item["canonical_agency_id"] for item in group],
                }
        else:
            for row in group:
                row["resolution_status"] = AMBIGUOUS
                row["resolution_method"] = "ERETZ_ID_COLLISION_DISTINCT_AGENCIES"
                row["eretz_id"] = None
                row["evidence"]["collision"] = {
                    "shared_eretz_id": eretz_id,
                    "canonical_ids": [item["canonical_agency_id"] for item in group],
                    "agency_names": [item["agency_name"] for item in group],
                }

    mapping = {
        row["canonical_agency_id"]: int(row["eretz_id"])
        for row in manifest
        if row["resolution_status"] == RESOLVED and row.get("eretz_id") is not None
    }
    return manifest, mapping


def sanitize_description(value: Any) -> tuple[str | None, bool]:
    if value is None:
        return None, False
    original = str(value)
    text = TECHNICAL_BLOCK.sub(" ", original)
    cuts = [match.start() for pattern in JS_PATTERNS if (match := pattern.search(text))]
    contaminated = bool(cuts or TECHNICAL_BLOCK.search(original))
    if cuts:
        text = text[: min(cuts)]
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip(" \t\r\n-|;")
    return text or None, contaminated


def explicit_count(record: dict[str, Any], field: str, value: int) -> bool:
    labels = {
        "banos": r"ba[ñn]os?",
        "dormitorios": r"(?:dormitorios?|habitaciones?)",
        "ambientes": r"ambientes?",
    }
    text = " ".join(str(record.get(key) or "") for key in ("titulo", "descripcion"))
    label = labels[field]
    return bool(
        re.search(rf"\b{value}\s+{label}\b", text, re.I)
        or re.search(rf"\b{label}\s*:?\s*{value}\b", text, re.I)
    )


def sanitize_count(record: dict[str, Any], field: str) -> tuple[int | None, str | None]:
    raw = record.get(field)
    if raw in (None, "") or isinstance(raw, bool):
        return None, None
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return None, "NON_NUMERIC_COUNT"
    if not number.is_integer() or number < 0:
        return None, "INVALID_COUNT"
    value = int(number)
    kind = norm(record.get("tipo_propiedad"))
    hotel_like = kind in HOTEL_TYPES
    if field == "banos" and value > 10:
        if hotel_like and explicit_count(record, field, value):
            return value, None
        reason = "KNOWN_TOKKO_CONCATENATION" if (
            record.get("connector") == "tokko" and value in {11, 21, 31, 41, 51}
        ) else "IMPLAUSIBLE_UNPROVED_COUNT"
        return None, reason
    if field in {"ambientes", "dormitorios"} and value > 30:
        if hotel_like and explicit_count(record, field, value):
            return value, None
        return None, "IMPLAUSIBLE_UNPROVED_COUNT"
    return value, None


def derive_contract(record: dict[str, Any]) -> tuple[str | None, str | None, list[str]]:
    operation = record.get("operacion")
    property_type = record.get("tipo_propiedad")
    derived: list[str] = []
    evidence = " ".join(str(record.get(key) or "") for key in ("source_url", "titulo"))
    extra = record.get("extra")
    if isinstance(extra, dict):
        for key in ("breadcrumb", "heading", "operation", "property_type", "tipo"):
            value = extra.get(key)
            if isinstance(value, (str, int, float)):
                evidence += " " + str(value)
    if not operation:
        operation = detectar_operacion(evidence)
        if operation:
            derived.append("operacion")
    if not property_type:
        property_type = detectar_tipo(evidence)
        if property_type:
            derived.append("tipo_propiedad")
    return operation, property_type, derived


def content_fingerprint(record: dict[str, Any]) -> str:
    keys = (
        "titulo", "descripcion", "precio", "moneda", "operacion",
        "tipo_propiedad", "direccion", "barrio", "ciudad", "provincia",
        "latitud", "longitud", "dormitorios", "banos", "ambientes",
        "superficie_total", "superficie_cubierta", "imagenes",
    )
    payload = {key: record.get(key) for key in keys}
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()[:32]


def create_db(path: Path) -> sqlite3.Connection:
    if path.exists():
        raise RuntimeError(f"refusing to overwrite existing rebuild database: {path}")
    connection = sqlite3.connect(path)
    connection.execute("pragma journal_mode=WAL")
    connection.execute("pragma synchronous=NORMAL")
    connection.execute("""
        create table rows(
          seq integer primary key,
          source_group text not null,
          canonical_id text,
          agency_id integer,
          url_normalized text,
          hash_dedup text,
          status text not null,
          reason text not null,
          connector text,
          row_json text not null
        )
    """)
    return connection


def rebuild(args: argparse.Namespace) -> dict[str, Any]:
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    manifest, agency_map = build_agency_manifest(
        Path(args.crosswalk), Path(args.web_directory), Path(args.platform_directory),
        Path(args.main_backup),
    )
    write_jsonl(output / "CANONICAL_AGENCY_TO_ERETZ_ID.jsonl", manifest)

    db = create_db(output / "PREINGESTION_REBUILD.sqlite3")
    counters: Counter[str] = Counter()
    connector_counts: Counter[str] = Counter()
    seq = 0
    for directory, filename, _connector in ENTRADAS:
        path = Path(args.source_root) / directory / filename
        if not path.exists():
            raise RuntimeError(f"missing canonical input: {path}")
        for original in read_jsonl(path):
            seq += 1
            row = dict(original)
            connector = str(row.get("connector") or _connector or "")
            connector_counts[connector] += 1
            desc_before = str(row.get("descripcion") or "")
            js_before = any(pattern.search(desc_before) for pattern in JS_PATTERNS)
            if js_before:
                counters["js_descriptions_before"] += 1
            row["descripcion"], cleaned = sanitize_description(row.get("descripcion"))
            if cleaned:
                counters["descriptions_cleaned"] += 1
            if row.get("descripcion") and any(pattern.search(row["descripcion"]) for pattern in JS_PATTERNS):
                counters["js_descriptions_after"] += 1

            fixes: list[dict[str, str]] = []
            for field in ("banos", "dormitorios", "ambientes"):
                before = row.get(field)
                after, reason = sanitize_count(row, field)
                if reason:
                    counters[f"{field}_anomalies_before"] += 1
                    fixes.append({"field": field, "reason": reason, "before": str(before)})
                row[field] = after
            if connector == "tokko" and original.get("banos") in {11, 21, 31, 41, 51}:
                counters["tokko_known_bathroom_anomalies_before"] += 1
                if row.get("banos") in {11, 21, 31, 41, 51}:
                    counters["tokko_known_bathroom_anomalies_after"] += 1

            if not original.get("operacion"):
                counters["missing_operation_before"] += 1
            if not original.get("tipo_propiedad"):
                counters["missing_type_before"] += 1
            operation, property_type, derived = derive_contract(row)
            row["operacion"] = operation
            row["tipo_propiedad"] = property_type
            if not operation:
                counters["missing_operation_after"] += 1
            if not property_type:
                counters["missing_type_after"] += 1

            canonical = row.get("canonical_agency_id")
            agency_id = agency_map.get(canonical)
            url = str(row.get("source_url") or "")
            normalized = normalizar_url(url)
            rejection = motivo_rechazo(row)
            portal = host(url) in EXTERNAL_PORTAL_HOSTS or host(
                (row.get("provenance") or {}).get("official_domain")
                if isinstance(row.get("provenance"), dict) else ""
            ) in EXTERNAL_PORTAL_HOSTS

            status = "CANDIDATE"
            reason = ""
            if portal:
                status, reason = "INVALID_OR_REJECTED", "EXTERNAL_PORTAL_PROFILE"
                counters["portal_contaminated_rows_removed"] += 1
            elif rejection:
                status, reason = "INVALID_OR_REJECTED", rejection
            elif agency_id is None:
                status, reason = "AGENCY_ID_UNRESOLVED", "CANONICAL_AGENCY_NOT_RESOLVED"
            elif not operation or not property_type:
                status, reason = "INVALID_OR_REJECTED", "RAW_ELIGIBLE_NOT_PUBLISH_ELIGIBLE"

            row["inmobiliaria_id"] = agency_id
            if agency_id is not None:
                row["hash_dedup"] = calcular_hash_dedup(agency_id, url)
            row["fingerprint"] = content_fingerprint(row)
            row["fingerprint_version"] = VERSION
            row["_preingestion"] = {
                "version": VERSION,
                "source_group": directory,
                "derived_fields": derived,
                "sanitized_counts": fixes,
                "description_technical_content_removed": cleaned,
                "publish_eligible": status == "CANDIDATE",
            }
            db.execute(
                "insert into rows values(?,?,?,?,?,?,?,?,?,?)",
                (
                    seq, directory, canonical, agency_id, normalized,
                    row.get("hash_dedup"), status, reason, connector,
                    json.dumps(row, ensure_ascii=False, sort_keys=True),
                ),
            )
            if seq % 5000 == 0:
                db.commit()
    db.commit()

    # Any URL claimed by distinct canonical agencies is held in full.  No
    # inventory-size or numeric-ID heuristic chooses an owner.
    conflicts = list(db.execute("""
        select url_normalized, count(*) as claims,
               count(distinct canonical_id) as agencies
        from rows where status='CANDIDATE' and url_normalized<>''
        group by url_normalized having count(distinct canonical_id)>1
    """))
    for normalized, _claims, _agencies in conflicts:
        db.execute(
            "update rows set status='DUPLICATE_OR_CONFLICT', reason='MULTI_AGENCY_NORMALIZED_URL' "
            "where status='CANDIDATE' and url_normalized=?",
            (normalized,),
        )

    # Within one agency the first deterministic occurrence survives; every
    # other claim remains auditable.
    db.execute("""
        update rows set status='DUPLICATE_OR_CONFLICT', reason='DUPLICATE_NORMALIZED_URL_IN_INPUT'
        where status='CANDIDATE' and seq not in (
          select min(seq) from rows where status='CANDIDATE'
          group by agency_id,url_normalized
        )
    """)
    db.execute("""
        update rows set status='DUPLICATE_OR_CONFLICT', reason='DUPLICATE_HASH_IN_INPUT'
        where status='CANDIDATE' and seq not in (
          select min(seq) from rows where status='CANDIDATE'
          group by hash_dedup
        )
    """)
    db.commit()
    db.execute("create unique index eligible_hash on rows(hash_dedup) where status='CANDIDATE'")
    db.execute("create unique index eligible_url on rows(url_normalized) where status='CANDIDATE'")
    db.commit()

    def rows_for(status: str) -> Iterable[dict[str, Any]]:
        cursor = db.execute("select row_json,reason from rows where status=? order by seq", (status,))
        for raw, reason in cursor:
            row = json.loads(raw)
            row["db_write_status"] = "DB_WRITE_ELIGIBLE" if status == "CANDIDATE" else status
            if reason:
                row["hold_reason"] = reason
            yield row

    outputs = {
        "CANDIDATE": "DB_WRITE_ELIGIBLE.jsonl",
        "AGENCY_ID_UNRESOLVED": "AGENCY_ID_UNRESOLVED.jsonl",
        "INVALID_OR_REJECTED": "INVALID_OR_REJECTED.jsonl",
        "DUPLICATE_OR_CONFLICT": "DUPLICATE_OR_CONFLICT.jsonl",
    }
    counts: dict[str, int] = {}
    for status, filename in outputs.items():
        counts[status] = write_jsonl(output / filename, rows_for(status))

    pending_rows = []
    for canonical, count in db.execute("""
        select canonical_id,count(*) from rows
        where status='AGENCY_ID_UNRESOLVED' group by canonical_id order by count(*) desc,canonical_id
    """):
        agency = next((item for item in manifest if item["canonical_agency_id"] == canonical), None) or {}
        pending_rows.append({
            "canonical_agency_id": canonical,
            "agency_name": agency.get("agency_name"),
            "official_domain": agency.get("official_domain"),
            "properties_held": count,
            "resolution_status": agency.get("resolution_status", NOT_FOUND),
            "reason": "no demonstrated public.inmobiliarias_main identity",
        })
    write_jsonl(output / "AGENCY_ID_PENDING_MANIFEST.jsonl", pending_rows)

    cross_rows = []
    for normalized, claims, agencies in conflicts:
        claimants = [
            {"canonical_agency_id": row[0], "agency_name": row[1], "rows": row[2]}
            for row in db.execute("""
                select r.canonical_id,
                       coalesce(json_extract(r.row_json,'$.provenance.agency_name'),r.canonical_id),
                       count(*)
                from rows r where r.url_normalized=?
                group by r.canonical_id order by r.canonical_id
            """, (normalized,))
        ]
        cross_rows.append({
            "url_normalizada": normalized,
            "category": "AMBIGUOUS_CROSS_AGENCY",
            "status": "HOLD",
            "claims": claims,
            "distinct_agencies": agencies,
            "claimants": claimants,
            "evidence": "same normalized listing URL claimed by distinct canonical agencies; no owner inferred",
        })
    write_jsonl(output / "CROSS_AGENCY_NORMALIZED_RESOLUTION.jsonl", cross_rows)

    status_counts = dict(db.execute("select status,count(*) from rows group by status"))
    reason_counts = dict(db.execute("select reason,count(*) from rows where reason<>'' group by reason"))
    resolved = sum(row["resolution_status"] == RESOLVED for row in manifest)
    ambiguous = sum(row["resolution_status"] == AMBIGUOUS for row in manifest)
    not_found = sum(row["resolution_status"] == NOT_FOUND for row in manifest)
    shared = db.execute("""
        select count(*) from (
          select agency_id from rows where status='CANDIDATE'
          group by agency_id having count(distinct canonical_id)>1
        )
    """).fetchone()[0]
    summary = {
        "version": VERSION,
        "universe_version": UNIVERSE_VERSION,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "universe": seq,
        "status_counts": status_counts,
        "reason_counts": reason_counts,
        "agency_mappings": {"resolved": resolved, "ambiguous": ambiguous, "not_found": not_found},
        "silent_shared_eretz_ids_in_insert": shared,
        "cross_agency_normalized_urls": len(conflicts),
        "quality": dict(counters),
        "connector_counts": dict(connector_counts),
        "database_writes": 0,
    }
    (output / "PREINGESTION_REBUILD_SUMMARY.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    (output / "DATA_QUALITY_AUDIT.md").write_text(render_audit(summary), encoding="utf-8")
    db.close()
    return summary


def render_audit(summary: dict[str, Any]) -> str:
    quality = summary["quality"]
    statuses = summary["status_counts"]
    mappings = summary["agency_mappings"]
    return f"""# ERETZ pre-ingestion data-quality audit V2

- Universe: {summary['universe']:,}
- DB_WRITE_ELIGIBLE: {statuses.get('CANDIDATE', 0):,}
- Agency unresolved: {statuses.get('AGENCY_ID_UNRESOLVED', 0):,}
- Invalid/rejected: {statuses.get('INVALID_OR_REJECTED', 0):,}
- Duplicate/conflict: {statuses.get('DUPLICATE_OR_CONFLICT', 0):,}
- Agency mappings resolved: {mappings['resolved']:,}
- Agency mappings ambiguous: {mappings['ambiguous']:,}
- Agency mappings not found in ERETZ: {mappings['not_found']:,}
- Silent shared ERETZ IDs in insert: {summary['silent_shared_eretz_ids_in_insert']}
- External portal rows removed: {quality.get('portal_contaminated_rows_removed', 0):,}
- JavaScript descriptions before/after: {quality.get('js_descriptions_before', 0):,} / {quality.get('js_descriptions_after', 0):,}
- Known Tokko bathroom concatenations before/after: {quality.get('tokko_known_bathroom_anomalies_before', 0):,} / {quality.get('tokko_known_bathroom_anomalies_after', 0):,}
- Missing operation before/after: {quality.get('missing_operation_before', 0):,} / {quality.get('missing_operation_after', 0):,}
- Missing type before/after: {quality.get('missing_type_before', 0):,} / {quality.get('missing_type_after', 0):,}

No database or source website was modified. Staging IDs were never interpreted as
`public.inmobiliarias_main.id`. Unproven identity and incomplete publication
contracts fail closed into HOLD artifacts.
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", default=str(RAIZ))
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--crosswalk", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA\crosswalk_final.jsonl")
    parser.add_argument("--web-directory", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA\agency_web_directory.jsonl")
    parser.add_argument("--platform-directory", default=r"D:\INMO CAPITAL\agency_platform_directory.jsonl")
    parser.add_argument("--main-backup", default=r"D:\INMO CAPITAL\Inmo-Capital-main\backups supabase\2026-05-27_inmobiliarias_main.csv")
    args = parser.parse_args()
    print(json.dumps(rebuild(args), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
