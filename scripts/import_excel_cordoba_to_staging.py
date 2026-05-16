"""
Importa inmobiliarias desde Excel de CPI Córdoba hacia inmobiliarias_staging.
Por defecto corre en dry-run.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import pandas as pd
import requests

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXCEL = ROOT / "data" / "Inmobiliairas  r.xlsx"
TARGET_TABLE = "inmobiliarias_staging"
SOURCE_NAME = "excel_colegio_cpi_cordoba"

PAYLOAD_KEYS = [
    "nombre",
    "nombre_limpio",
    "nombre_normalizado",
    "direccion",
    "barrio",
    "ciudad",
    "provincia",
    "pais",
    "telefono",
    "web",
    "url_listado",
    "fuente",
    "estado_scraping",
    "needs_manual_review",
    "revision_notas",
    "metadata_zonaprop",
]


@dataclass
class ImportReport:
    filas_leidas: int = 0
    filas_utiles: int = 0
    duplicados_internos: int = 0
    registros_unicos_post_dedupe: int = 0
    omitidas_main: int = 0
    omitidas_scraping: int = 0
    omitidas_staging: int = 0
    insertaria: int = 0
    errores: int = 0
    ejemplos_insertaria: List[Dict[str, Any]] = field(default_factory=list)
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
        raise RuntimeError("Faltan SUPABASE_URL y SUPABASE_KEY en .env")
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
    if pd.isna(value) or value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def strip_accents(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def normalize_name(value: Any) -> str:
    text = strip_accents(clean_spaces(value).lower())
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def clean_phone(value: Any) -> Optional[str]:
    text = clean_spaces(value)
    if not text or text == "nan":
        return None
    cleaned = re.sub(r"[^0-9+]", "", text)
    return cleaned if cleaned else None


def fetch_table_rows(
    session: requests.Session, base_url: str, key: str, table: str, select: str, page_size: int = 1000
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


def fetch_existing_normalized_names(session: requests.Session, base_url: str, key: str, table: str) -> Set[str]:
    rows = fetch_table_rows(session, base_url, key, table, "nombre,nombre_normalizado")
    names: Set[str] = set()
    for row in rows:
        candidate = row.get("nombre_normalizado") or row.get("nombre")
        normalized = normalize_name(candidate)
        if normalized:
            names.add(normalized)
    return names


def validate_batch_keys(payloads: Sequence[Dict[str, Any]], batch_start: int) -> List[Dict[str, Any]]:
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
                "claves_extra": sorted(extra) if extra else [],
                "claves_faltantes": sorted(missing) if missing else [],
            })
    return inconsistencies


def build_payload(row: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    nombre_fantasia = clean_spaces(row.get("nombre_fantasia"))
    titular = clean_spaces(row.get("titular"))
    
    nombre_limpio = nombre_fantasia if nombre_fantasia and nombre_fantasia != "nan" else titular
    if not nombre_limpio or nombre_limpio == "nan":
        return None, "sin_nombre"
        
    nombre_normalizado = normalize_name(nombre_limpio)
    if not nombre_normalizado:
        return None, "nombre_normalizado_vacio"

    metadata = {
        "titular": titular if titular != "nan" else None,
        "nombre_fantasia": nombre_fantasia if nombre_fantasia != "nan" else None,
        "titular_asociado": clean_spaces(row.get("titular_asociado")),
        "matricula": clean_spaces(row.get("matricula")),
        "telefono_1": clean_spaces(row.get("telefono_1")),
        "telefono_2": clean_spaces(row.get("telefono_2")),
        "direccion": clean_spaces(row.get("direccion")),
        "barrio": clean_spaces(row.get("barrio")),
        "ciudad": clean_spaces(row.get("ciudad")),
        "provincia": clean_spaces(row.get("provincia")),
        "pais": clean_spaces(row.get("pais")),
        "estado": clean_spaces(row.get("estado")),
        "fuente_colegio": clean_spaces(row.get("fuente_colegio")),
        "observaciones": clean_spaces(row.get("observaciones")),
        "cantidad_duplicados_internos": row.get("cantidad_duplicados_internos", 0),
        "telefonos_extra": row.get("telefonos_extra", []),
        "matriculas_extra": row.get("matriculas_extra", []),
        "titulares_extra": row.get("titulares_extra", []),
    }

    # Limpiar metadata None o vacios para diccionarios
    metadata = {k: v for k, v in metadata.items() if v not in (None, "", "nan", [])}

    provincia = "Córdoba" if metadata.get("provincia") else None
    pais = "Argentina" if metadata.get("pais") else None
    telefono = clean_phone(metadata.get("telefono_1")) or clean_phone(metadata.get("telefono_2"))

    payload: Dict[str, Any] = {
        "nombre": nombre_limpio,
        "nombre_limpio": nombre_limpio,
        "nombre_normalizado": nombre_normalizado,
        "direccion": metadata.get("direccion"),
        "barrio": metadata.get("barrio"),
        "ciudad": metadata.get("ciudad"),
        "provincia": provincia,
        "pais": pais,
        "telefono": telefono,
        "web": None,
        "url_listado": None,
        "fuente": SOURCE_NAME,
        "estado_scraping": "pendiente_enriquecimiento",
        "needs_manual_review": True,
        "revision_notas": "Importado desde Excel CPI Córdoba. Requiere enriquecimiento para encontrar web real.",
        "metadata_zonaprop": metadata,
    }
    
    return payload, None


def process_excel(path: Path, limit: Optional[int]) -> Tuple[List[Dict[str, Any]], ImportReport]:
    report = ImportReport()
    
    try:
        df = pd.read_excel(path, sheet_name="CORDOBA", header=None)
    except Exception as e:
        report.advertencias.append(f"Error al leer Excel: {e}")
        return [], report
        
    df = df.iloc[:limit] if limit else df
    report.filas_leidas = len(df)
    
    df.columns = [
        "titular", "nombre_fantasia", "titular_asociado", "matricula", "telefono_1", "telefono_2",
        "direccion", "barrio", "ciudad", "provincia", "pais", "estado", "fuente_colegio", "observaciones"
    ]
    
    # Pre-procesamiento de columnas string
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(lambda x: clean_spaces(str(x)) if not pd.isna(x) else None)
    
    # Fix encoding CPI Crdoba -> CPI Córdoba
    # Usamos string normalizado si no hay regex complicado
    df["fuente_colegio"] = df["fuente_colegio"].astype(str).str.replace(r"CPI C.*rdoba", "CPI Córdoba", regex=True)
    df["fuente_colegio"] = df["fuente_colegio"].str.replace("CPI Crdoba", "CPI Córdoba")

    # Mapear a diccionarios
    rows_dict = df.to_dict(orient="records")
    
    util_rows: List[Dict[str, Any]] = []
    
    for row in rows_dict:
        nf = str(row.get("nombre_fantasia")) if not pd.isna(row.get("nombre_fantasia")) else ""
        t = str(row.get("titular")) if not pd.isna(row.get("titular")) else ""
        if nf.strip() or t.strip():
            util_rows.append(row)
            
    report.filas_utiles = len(util_rows)
    
    # Deduplicar internamente
    grouped = {}
    for row in util_rows:
        nf = str(row.get("nombre_fantasia")) if not pd.isna(row.get("nombre_fantasia")) else ""
        t = str(row.get("titular")) if not pd.isna(row.get("titular")) else ""
        n_limpio = nf if nf.strip() and nf != "nan" else t
        n_norm = normalize_name(n_limpio)
        
        if not n_norm:
            continue
            
        if n_norm not in grouped:
            grouped[n_norm] = [row]
        else:
            grouped[n_norm].append(row)
            
    deduped_rows = []
    for n_norm, group in grouped.items():
        base_row = group[0].copy()
        if len(group) > 1:
            report.duplicados_internos += (len(group) - 1)
            base_row["cantidad_duplicados_internos"] = len(group) - 1
            
            telefonos_extra = set()
            matriculas_extra = set()
            titulares_extra = set()
            
            for dup in group[1:]:
                if str(dup.get("telefono_1")) not in ("nan", "None", ""): telefonos_extra.add(str(dup["telefono_1"]))
                if str(dup.get("telefono_2")) not in ("nan", "None", ""): telefonos_extra.add(str(dup["telefono_2"]))
                if str(dup.get("matricula")) not in ("nan", "None", ""): matriculas_extra.add(str(dup["matricula"]))
                if str(dup.get("titular")) not in ("nan", "None", ""): titulares_extra.add(str(dup["titular"]))
                if str(dup.get("titular_asociado")) not in ("nan", "None", ""): titulares_extra.add(str(dup["titular_asociado"]))
                
            if telefonos_extra: base_row["telefonos_extra"] = list(telefonos_extra)
            if matriculas_extra: base_row["matriculas_extra"] = list(matriculas_extra)
            if titulares_extra: base_row["titulares_extra"] = list(titulares_extra)
            
        deduped_rows.append(base_row)
        
    report.registros_unicos_post_dedupe = len(deduped_rows)
    return deduped_rows, report


def insert_batches(
    session: requests.Session, base_url: str, key: str, payloads: Sequence[Dict[str, Any]], batch_size: int = 500
) -> Tuple[int, List[Dict[str, Any]]]:
    inserted = 0
    errors: List[Dict[str, Any]] = []
    for start in range(0, len(payloads), batch_size):
        batch = list(payloads[start : start + batch_size])

        key_issues = validate_batch_keys(batch, start)
        if key_issues:
            errors.append({
                "batch_start": start,
                "status": "VALIDACION_CLAVES",
                "error": f"{len(key_issues)} filas con claves inconsistentes",
                "detalles": key_issues[:10],
            })
            continue

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


def prepare_import(args: argparse.Namespace) -> Tuple[ImportReport, List[Dict[str, Any]]]:
    base_url, key = load_env()
    session = make_session()

    deduped_rows, report = process_excel(Path(args.excel), args.limit)

    existing_main = fetch_existing_normalized_names(session, base_url, key, "inmobiliarias_main")
    existing_scraping = fetch_existing_normalized_names(session, base_url, key, "inmobiliarias_scraping")
    existing_staging = fetch_existing_normalized_names(session, base_url, key, TARGET_TABLE)

    payloads: List[Dict[str, Any]] = []

    for index, row in enumerate(deduped_rows, start=1):
        try:
            payload, error = build_payload(row)
            if error or payload is None:
                report.add_example("ejemplos_errores", {"fila_interna": index, "motivo": error, "nombre": str(row.get("nombre_fantasia") or row.get("titular"))})
                continue

            normalized = str(payload["nombre_normalizado"])
            
            if normalized in existing_main:
                report.omitidas_main += 1
                report.add_example("ejemplos_duplicados_main", {"nombre": payload["nombre"]})
                continue

            if normalized in existing_scraping:
                report.omitidas_scraping += 1
                report.add_example("ejemplos_duplicados_scraping", {"nombre": payload["nombre"]})
                continue

            if normalized in existing_staging:
                report.omitidas_staging += 1
                report.add_example("ejemplos_duplicados_staging", {"nombre": payload["nombre"]})
                continue

            payloads.append(payload)
            report.add_example("ejemplos_insertaria", payload)
            
        except Exception as exc:
            report.errores += 1
            report.add_example("ejemplos_errores", {"fila_interna": index, "error": f"{type(exc).__name__}: {str(exc)[:300]}"})

    if payloads:
        key_issues = validate_batch_keys(payloads, 0)
        if key_issues:
            report.errores += len(key_issues)
            for issue in key_issues[:10]:
                report.add_example("ejemplos_errores", {"motivo": "claves_inconsistentes", **issue})
            report.advertencias.append(f"ABORTAR: {len(key_issues)} payloads con claves inconsistentes.")

    report.insertaria = len(payloads)
    return report, payloads


def print_report(report: ImportReport, dry_run: bool) -> None:
    output = {
        "modo": "dry-run" if dry_run else "commit",
        "filas_leidas": report.filas_leidas,
        "filas_utiles": report.filas_utiles,
        "duplicados_internos": report.duplicados_internos,
        "registros_unicos_post_dedupe": report.registros_unicos_post_dedupe,
        "omitidas_por_duplicado_en_main": report.omitidas_main,
        "omitidas_por_duplicado_en_scraping": report.omitidas_scraping,
        "omitidas_por_duplicado_en_staging": report.omitidas_staging,
        "insertaria" if dry_run else "insertadas": report.insertaria,
        "errores": report.errores,
        "advertencias": report.advertencias,
        "ejemplos_insertaria": report.ejemplos_insertaria,
        "ejemplos_duplicados_main": report.ejemplos_duplicados_main,
        "ejemplos_duplicados_scraping": report.ejemplos_duplicados_scraping,
        "ejemplos_duplicados_staging": report.ejemplos_duplicados_staging,
        "ejemplos_errores": report.ejemplos_errores,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Importa Excel Córdoba a inmobiliarias_staging.")
    parser.add_argument("--excel", default=str(DEFAULT_EXCEL), help="Excel de entrada.")
    parser.add_argument("--limit", type=int, default=None, help="Limita filas leídas desde el Excel.")
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

    report, payloads = prepare_import(args)
    if args.commit:
        base_url, key = load_env()
        inserted, insert_errors = insert_batches(
            make_session(), base_url, key, payloads, batch_size=args.batch_size
        )
        report.insertaria = inserted
        report.errores += len(insert_errors)
        for error in insert_errors[:8]:
            report.add_example("ejemplos_errores", error)
        print_report(report, dry_run=False)
        return 1 if insert_errors else 0

    print_report(report, dry_run=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
