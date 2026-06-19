"""
Importa inmobiliarias descubiertas desde Zonaprop hacia inmobiliarias_staging.

Por defecto corre en dry-run. Solo inserta cuando se usa --commit.
No escribe web ni url_listado con perfiles de Zonaprop.
"""

from __future__ import annotations

# === CONGELADO por política ERETZ Propiedades (2026-06-17) ===
# Todo lo relacionado con Zonaprop/Argenprop (incluido import de discovery) queda
# congelado hasta autorización explícita. Quitar este guard solo con esa autorización.
import sys as _sys
_sys.exit(
    "CONGELADO (politica ERETZ 2026-06-17): import Zonaprop/Argenprop deshabilitado. "
    "Requiere autorizacion explicita para reactivar."
)

import argparse
import csv
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import requests

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "data" / "zonaprop_total.csv"
TARGET_TABLE = "inmobiliarias_staging"
SOURCE_NAME = "zonaprop_inmobiliarias"
REQUIRED_STAGING_COLUMNS = {"url_perfil_zonaprop", "metadata_zonaprop"}


@dataclass
class ImportReport:
    filas_leidas: int = 0
    insertadas: int = 0
    omitidas_main: int = 0
    omitidas_scraping: int = 0
    omitidas_staging: int = 0
    omitidas_csv_url_duplicada: int = 0
    omitidas_sin_nombre_o_url: int = 0
    errores: int = 0
    ejemplos_insertadas: List[Dict[str, Any]] = field(default_factory=list)
    ejemplos_duplicados_main: List[Dict[str, Any]] = field(default_factory=list)
    ejemplos_duplicados_scraping: List[Dict[str, Any]] = field(default_factory=list)
    ejemplos_duplicados_staging: List[Dict[str, Any]] = field(default_factory=list)
    ejemplos_errores: List[Dict[str, Any]] = field(default_factory=list)
    advertencias: List[str] = field(default_factory=list)

    def add_example(self, key: str, value: Dict[str, Any], limit: int = 8) -> None:
        bucket = getattr(self, key)
        if len(bucket) < limit:
            bucket.append(value)


def load_env() -> Tuple[str, str]:
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")
    else:
        env_path = ROOT / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not line or line.strip().startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
        or ""
    )
    if not url or not key:
        raise RuntimeError("Faltan SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY/SUPABASE_KEY en .env")
    return url, key


def make_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    return session


def headers(key: str, prefer: Optional[str] = None) -> Dict[str, str]:
    result = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        result["Prefer"] = prefer
    return result


def clean_spaces(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def strip_accents(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def normalize_name(value: Any) -> str:
    text = strip_accents(clean_spaces(value).lower())
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def maybe_fix_mojibake(value: str) -> Tuple[str, Optional[str]]:
    if not re.search(r"[ÃÂ�]", value or ""):
        return value, None
    try:
        fixed = value.encode("latin-1").decode("utf-8")
    except Exception:
        return value, f"posible_mojibake_sin_correccion: {value}"
    original_bad = len(re.findall(r"[ÃÂ�]", value))
    fixed_bad = len(re.findall(r"[ÃÂ�]", fixed))
    if fixed and fixed_bad < original_bad:
        return fixed, f"mojibake_corregido: {value} -> {fixed}"
    return value, f"posible_mojibake_sin_correccion: {value}"


def parse_optional_int(value: Any) -> Optional[int]:
    text = clean_spaces(value)
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def read_csv_rows(path: Path, limit: Optional[int]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(row)
            if limit is not None and len(rows) >= limit:
                break
    return rows


def fetch_table_rows(
    session: requests.Session,
    base_url: str,
    key: str,
    table: str,
    select: str,
    page_size: int = 1000,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    start = 0
    while True:
        req_headers = headers(key)
        req_headers["Range-Unit"] = "items"
        req_headers["Range"] = f"{start}-{start + page_size - 1}"
        response = session.get(
            f"{base_url}/rest/v1/{table}",
            headers=req_headers,
            params={"select": select},
            timeout=30,
        )
        if not response.ok:
            raise RuntimeError(f"No se pudo leer {table}: {response.status_code} {response.text[:400]}")
        batch = response.json()
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return rows


def fetch_existing_normalized_names(
    session: requests.Session,
    base_url: str,
    key: str,
    table: str,
) -> Set[str]:
    rows = fetch_table_rows(session, base_url, key, table, "nombre,nombre_normalizado")
    names: Set[str] = set()
    for row in rows:
        candidate = row.get("nombre_normalizado") or row.get("nombre")
        normalized = normalize_name(candidate)
        if normalized:
            names.add(normalized)
    return names


def get_table_columns(session: requests.Session, base_url: str, key: str, table: str) -> Set[str]:
    response = session.get(
        f"{base_url}/rest/v1/",
        headers={**headers(key), "Accept": "application/openapi+json"},
        timeout=30,
    )
    if not response.ok:
        raise RuntimeError(f"No se pudo leer OpenAPI schema: {response.status_code} {response.text[:300]}")
    data = response.json()
    schemas = data.get("definitions") or (data.get("components") or {}).get("schemas") or {}
    schema = schemas.get(table) or schemas.get(f"public.{table}") or {}
    props = schema.get("properties") if isinstance(schema, dict) else {}
    return set(props.keys()) if isinstance(props, dict) else set()


def fetch_existing_staging_urls(
    session: requests.Session,
    base_url: str,
    key: str,
    report: ImportReport,
    staging_columns: Set[str],
) -> Set[str]:
    if "url_perfil_zonaprop" not in staging_columns:
        report.advertencias.append(
            "inmobiliarias_staging no tiene url_perfil_zonaprop; "
            "dry-run continua, pero --commit queda bloqueado hasta aplicar schema."
        )
        return set()
    rows = fetch_table_rows(session, base_url, key, TARGET_TABLE, "url_perfil_zonaprop")
    return {
        clean_spaces(row.get("url_perfil_zonaprop")).lower()
        for row in rows
        if clean_spaces(row.get("url_perfil_zonaprop"))
    }


# --- Claves fijas que SIEMPRE deben estar en cada payload ---
PAYLOAD_KEYS = [
    "nombre",
    "nombre_limpio",
    "nombre_normalizado",
    "web",
    "url_listado",
    "ciudad",
    "provincia",
    "pais",
    "fuente",
    "estado_scraping",
    "needs_manual_review",
    "url_perfil_zonaprop",
    "metadata_zonaprop",
]


def build_payload(row: Dict[str, str]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    raw_name = clean_spaces(row.get("nombre"))
    url_perfil = clean_spaces(row.get("url_perfil_zonaprop"))
    if not raw_name or not url_perfil:
        return None, "sin_nombre_o_url"

    clean_name, revision_note = maybe_fix_mojibake(raw_name)
    nombre_limpio = clean_spaces(clean_name)
    nombre_normalizado = normalize_name(nombre_limpio)
    if not nombre_normalizado:
        return None, "nombre_normalizado_vacio"

    metadata: Dict[str, Any] = {
        "publica_desde": parse_optional_int(row.get("publica_desde")),
        "nivel": parse_optional_int(row.get("nivel")),
        "calificaciones": parse_optional_int(row.get("calificaciones")),
        "avisos_compra": parse_optional_int(row.get("avisos_compra")),
        "avisos_alquiler": parse_optional_int(row.get("avisos_alquiler")),
        "pagina_origen": clean_spaces(row.get("pagina_origen")) or None,
    }

    # Advertencias (mojibake, etc.) van DENTRO de metadata, nunca como columna aparte
    if revision_note:
        metadata["revision_notas"] = revision_note

    payload: Dict[str, Any] = {
        "nombre": nombre_limpio,
        "nombre_limpio": nombre_limpio,
        "nombre_normalizado": nombre_normalizado,
        "web": None,
        "url_listado": None,
        "ciudad": None,
        "provincia": None,
        "pais": "Argentina",
        "fuente": SOURCE_NAME,
        "estado_scraping": "pendiente_enriquecimiento",
        "needs_manual_review": True,
        "url_perfil_zonaprop": url_perfil,
        "metadata_zonaprop": metadata,
    }
    return payload, None


def validate_batch_keys(
    payloads: Sequence[Dict[str, Any]],
    batch_start: int,
) -> List[Dict[str, Any]]:
    """Valida que todas las filas de un batch tengan exactamente las mismas claves.

    Retorna lista de inconsistencias encontradas. Lista vacía = OK.
    """
    if not payloads:
        return []
    expected_keys = set(PAYLOAD_KEYS)
    inconsistencies: List[Dict[str, Any]] = []
    for local_idx, row in enumerate(payloads):
        row_keys = set(row.keys())
        extra = row_keys - expected_keys
        missing = expected_keys - row_keys
        if extra or missing:
            inconsistencies.append({
                "indice_local": batch_start + local_idx,
                "nombre": row.get("nombre", "?"),
                "url_perfil_zonaprop": row.get("url_perfil_zonaprop", "?"),
                "claves_extra": sorted(extra) if extra else [],
                "claves_faltantes": sorted(missing) if missing else [],
            })
    return inconsistencies


def insert_batches(
    session: requests.Session,
    base_url: str,
    key: str,
    payloads: Sequence[Dict[str, Any]],
    batch_size: int = 500,
) -> Tuple[int, List[Dict[str, Any]]]:
    inserted = 0
    errors: List[Dict[str, Any]] = []
    for start in range(0, len(payloads), batch_size):
        batch = list(payloads[start : start + batch_size])

        # --- Validación pre-insert: todas las filas deben tener las mismas claves ---
        key_issues = validate_batch_keys(batch, start)
        if key_issues:
            errors.append({
                "batch_start": start,
                "status": "VALIDACION_CLAVES",
                "error": f"{len(key_issues)} filas con claves inconsistentes",
                "detalles": key_issues[:10],
            })
            continue  # No enviar este batch a Supabase

        response = session.post(
            f"{base_url}/rest/v1/{TARGET_TABLE}",
            headers=headers(key, prefer="return=minimal"),
            json=batch,
            timeout=60,
        )
        if response.status_code in {200, 201, 204}:
            inserted += len(batch)
            continue
        errors.append({
            "batch_start": start,
            "status": response.status_code,
            "error": response.text[:800],
        })
    return inserted, errors


def prepare_import(args: argparse.Namespace) -> Tuple[ImportReport, List[Dict[str, Any]], Set[str]]:
    base_url, key = load_env()
    session = make_session()
    report = ImportReport()

    staging_columns = get_table_columns(session, base_url, key, TARGET_TABLE)
    missing_columns = REQUIRED_STAGING_COLUMNS - staging_columns
    if missing_columns:
        report.advertencias.append(f"faltan_columnas_staging: {sorted(missing_columns)}")

    rows = read_csv_rows(Path(args.csv), args.limit)
    report.filas_leidas = len(rows)

    existing_main = fetch_existing_normalized_names(session, base_url, key, "inmobiliarias_main")
    existing_scraping = fetch_existing_normalized_names(session, base_url, key, "inmobiliarias_scraping")
    existing_staging_urls = fetch_existing_staging_urls(session, base_url, key, report, staging_columns)

    seen_csv_urls: Set[str] = set()
    payloads: List[Dict[str, Any]] = []

    for index, row in enumerate(rows, start=1):
        try:
            payload, error = build_payload(row)
            if error or payload is None:
                report.omitidas_sin_nombre_o_url += 1
                report.add_example("ejemplos_errores", {"fila": index, "motivo": error, "row": row})
                continue

            url_key = clean_spaces(payload.get("url_perfil_zonaprop")).lower()
            if url_key in seen_csv_urls:
                report.omitidas_csv_url_duplicada += 1
                continue
            seen_csv_urls.add(url_key)

            normalized = str(payload["nombre_normalizado"])
            if normalized in existing_main:
                report.omitidas_main += 1
                report.add_example("ejemplos_duplicados_main", {
                    "fila": index,
                    "nombre": payload["nombre"],
                    "nombre_normalizado": normalized,
                    "url_perfil_zonaprop": payload["url_perfil_zonaprop"],
                })
                continue

            if normalized in existing_scraping:
                report.omitidas_scraping += 1
                report.add_example("ejemplos_duplicados_scraping", {
                    "fila": index,
                    "nombre": payload["nombre"],
                    "nombre_normalizado": normalized,
                    "url_perfil_zonaprop": payload["url_perfil_zonaprop"],
                })
                continue

            if url_key in existing_staging_urls:
                report.omitidas_staging += 1
                report.add_example("ejemplos_duplicados_staging", {
                    "fila": index,
                    "nombre": payload["nombre"],
                    "url_perfil_zonaprop": payload["url_perfil_zonaprop"],
                })
                continue

            payloads.append(payload)
            report.add_example("ejemplos_insertadas", payload)
        except Exception as exc:
            report.errores += 1
            report.add_example("ejemplos_errores", {
                "fila": index,
                "error": f"{type(exc).__name__}: {str(exc)[:300]}",
                "row": row,
            })

    # --- Validación global de claves uniformes antes de retornar ---
    if payloads:
        key_issues = validate_batch_keys(payloads, 0)
        if key_issues:
            report.errores += len(key_issues)
            for issue in key_issues[:10]:
                report.add_example("ejemplos_errores", {
                    "motivo": "claves_inconsistentes",
                    **issue,
                })
            report.advertencias.append(
                f"ABORTAR: {len(key_issues)} payloads con claves inconsistentes. "
                "Revisar build_payload()."
            )

    report.insertadas = len(payloads)
    return report, payloads, missing_columns


def print_report(report: ImportReport, dry_run: bool) -> None:
    output = {
        "modo": "dry-run" if dry_run else "commit",
        "filas_leidas": report.filas_leidas,
        "insertaria" if dry_run else "insertadas": report.insertadas,
        "omitidas_por_duplicado_en_main": report.omitidas_main,
        "omitidas_por_duplicado_en_scraping": report.omitidas_scraping,
        "omitidas_por_duplicado_en_staging": report.omitidas_staging,
        "omitidas_por_url_duplicada_en_csv": report.omitidas_csv_url_duplicada,
        "omitidas_sin_nombre_o_url": report.omitidas_sin_nombre_o_url,
        "errores": report.errores,
        "advertencias": report.advertencias,
        "ejemplos_insertadas": report.ejemplos_insertadas,
        "ejemplos_duplicados_main": report.ejemplos_duplicados_main,
        "ejemplos_duplicados_scraping": report.ejemplos_duplicados_scraping,
        "ejemplos_duplicados_staging": report.ejemplos_duplicados_staging,
        "ejemplos_errores": report.ejemplos_errores,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Importa Zonaprop CSV a inmobiliarias_staging.")
    parser.add_argument("--csv", default=str(DEFAULT_CSV), help="CSV de entrada.")
    parser.add_argument("--limit", type=int, default=None, help="Limita filas leídas desde el CSV.")
    parser.add_argument("--batch-size", type=int, default=500, help="Tamaño de batch para inserts (default: 500).")
    parser.add_argument("--dry-run", action="store_true", help="No inserta; solo informa qué haría.")
    parser.add_argument("--commit", action="store_true", help="Inserta registros nuevos en staging.")
    args = parser.parse_args(argv)
    if args.dry_run and args.commit:
        parser.error("Usar --dry-run o --commit, no ambos.")
    if not args.dry_run and not args.commit:
        args.dry_run = True
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.limit is not None and args.limit <= 0:
        raise SystemExit("--limit debe ser mayor a 0")

    report, payloads, missing_columns = prepare_import(args)
    if args.commit:
        if missing_columns:
            report.errores += 1
            report.add_example("ejemplos_errores", {
                "motivo": "schema_incompleto",
                "faltan_columnas": sorted(missing_columns),
            })
            print_report(report, dry_run=False)
            return 2
        base_url, key = load_env()
        inserted, insert_errors = insert_batches(
            make_session(), base_url, key, payloads, batch_size=args.batch_size
        )
        report.insertadas = inserted
        report.errores += len(insert_errors)
        for error in insert_errors[:8]:
            report.add_example("ejemplos_errores", error)
        print_report(report, dry_run=False)
        return 1 if insert_errors else 0

    print_report(report, dry_run=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
