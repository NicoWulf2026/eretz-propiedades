#!/usr/bin/env python
"""Validate Neon propiedades_raw rows into propiedades_staging.

This script only uses INTERNAL_DB_URL. It never reads or writes Supabase.
Default mode is dry-run; pass --commit to persist changes.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, unquote, urlparse

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

RAW_SELECT_SQL = """
SELECT
  id,
  scraping_run_item_id,
  inmobiliaria_id,
  hash_dedup,
  titulo,
  descripcion,
  precio,
  moneda,
  superficie_total,
  superficie_cubierta,
  tipo_propiedad,
  operacion,
  url,
  url_normalizada,
  direccion_raw,
  barrio,
  ciudad,
  provincia,
  pais,
  latitud,
  longitud,
  imagenes
FROM public.propiedades_raw
WHERE status = 'raw'
ORDER BY id ASC
LIMIT %s
"""

STAGING_COLUMNS = [
    "raw_id",
    "inmobiliaria_id",
    "hash_dedup",
    "titulo",
    "descripcion",
    "precio",
    "moneda",
    "superficie_total",
    "superficie_cubierta",
    "tipo_propiedad",
    "operacion",
    "url",
    "url_normalizada",
    "direccion_normalizada",
    "barrio",
    "ciudad",
    "provincia",
    "pais",
    "latitud",
    "longitud",
    "imagenes",
    "geocoding_status",
    "validation_score",
    "status",
]


try:
    from scraper.scraper_propiedades import normalize_property_url_for_dedup, OPERACION_MAP
except Exception:
    OPERACION_MAP: Dict[str, str] = {
        "venta": "venta",
        "sale": "venta",
        "sell": "venta",
        "compra": "venta",
        "en venta": "venta",
        "for sale": "venta",
        "alquiler": "alquiler",
        "alq": "alquiler",
        "rent": "alquiler",
        "rental": "alquiler",
        "arrendamiento": "alquiler",
        "locacion": "alquiler",
        "locación": "alquiler",
        "en alquiler": "alquiler",
        "for rent": "alquiler",
        "temporario": "alquiler_temporario",
        "temporal": "alquiler_temporario",
        "temporaria": "alquiler_temporario",
        "alquiler temporario": "alquiler_temporario",
        "alquiler temporal": "alquiler_temporario",
        "vacation": "alquiler_temporario",
        "turistico": "alquiler_temporario",
        "turístico": "alquiler_temporario",
        "por dia": "alquiler_temporario",
        "por día": "alquiler_temporario",
        "por semana": "alquiler_temporario",
        "short term": "alquiler_temporario",
    }

    def normalize_property_url_for_dedup(url: Any) -> str:
        if not url:
            return ""
        raw = unquote(str(url).strip())
        if not raw:
            return ""
        if not re.match(r"^https?://", raw, re.IGNORECASE):
            raw = f"http://{raw.lstrip('/')}"
        try:
            parsed = urlparse(raw)
        except Exception:
            return re.sub(r"\s+", "", raw.lower()).rstrip("/")
        host = (parsed.netloc or parsed.path.split("/")[0]).split("@")[-1]
        host = host.split(":")[0].strip().lower()
        if host.startswith("www."):
            host = host[4:]
        path = re.sub(r"/+", "/", unquote(parsed.path or "")).strip().rstrip("/").lower()
        query_items = []
        for key, value in parse_qsl(parsed.query, keep_blank_values=False):
            key_clean = key.strip().lower()
            if key_clean.startswith("utm_") or key_clean in {"fbclid", "gclid", "wbraid", "gbraid"}:
                continue
            query_items.append((key_clean, value.strip()))
        query = "&".join(f"{key}={value}" for key, value in sorted(query_items))
        return f"{host}{path}" + (f"?{query}" if query else "")


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_env() -> None:
    load_env_file(REPO_ROOT / ".env")
    load_env_file(REPO_ROOT / ".env.local")


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def internal_db_config() -> str:
    load_env()
    db_url = os.getenv("INTERNAL_DB_URL", "").strip()
    if not env_flag("USE_INTERNAL_DB", default=False):
        raise SystemExit("USE_INTERNAL_DB no esta en true; abortando para no usar una DB equivocada.")
    if not db_url:
        raise SystemExit("Falta INTERNAL_DB_URL; abortando.")
    return db_url


def connect_internal_db(db_url: str):
    try:
        import psycopg  # type: ignore
        from psycopg.rows import dict_row  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Falta instalar psycopg/psycopg-binary para usar INTERNAL_DB_URL.") from exc
    return psycopg.connect(db_url, row_factory=dict_row)


def json_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        try:
            from psycopg.types.json import Jsonb  # type: ignore
            return Jsonb(value)
        except Exception:
            return json.dumps(value, ensure_ascii=False)
    return value


def clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def collapse_spaces(value: Any) -> Optional[str]:
    cleaned = clean_text(value)
    if not cleaned:
        return None
    return re.sub(r"\s+", " ", cleaned)


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value).strip()
    if not raw:
        return None
    normalized = raw.replace(".", "").replace(",", ".") if "," in raw else raw
    return float(normalized)


def normalize_operation(value: Any) -> Optional[str]:
    cleaned = clean_text(value)
    if not cleaned:
        return None
    key = re.sub(r"\s+", " ", cleaned.lower())
    if key in {"venta", "alquiler", "alquiler_temporario"}:
        return key
    mapped = OPERACION_MAP.get(key)
    return mapped if mapped in {"venta", "alquiler", "alquiler_temporario"} else None


def valid_argentina_coordinates(lat: Optional[float], lon: Optional[float]) -> bool:
    if lat is None or lon is None:
        return False
    return -55 <= lat <= -21 and -74 <= lon <= -53


def truncate_detail(value: Any) -> str:
    return str(value or "")[:200]


def issue(issue_type: str, detail: Any = "") -> Dict[str, str]:
    return {"issue_type": issue_type, "issue_detail": truncate_detail(detail)}


def staging_duplicate_exists(cur, hash_dedup: str) -> bool:
    cur.execute(
        """
        SELECT id
        FROM public.propiedades_staging
        WHERE hash_dedup = %s
          AND status != 'rejected'
        LIMIT 1
        """,
        [hash_dedup],
    )
    return cur.fetchone() is not None


def build_validation(cur, row: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, str]], bool]:
    raw_id = row.get("id")
    hard_issues: List[Dict[str, str]] = []
    soft_issues: List[Dict[str, str]] = []
    duplicate = False

    hash_dedup = clean_text(row.get("hash_dedup"))
    if not hash_dedup:
        hard_issues.append(issue("missing_hash", f"raw_id={raw_id} sin hash_dedup"))

    try:
        inmobiliaria_id = int(row.get("inmobiliaria_id"))
        if inmobiliaria_id <= 0:
            raise ValueError("non_positive")
    except Exception:
        inmobiliaria_id = None
        hard_issues.append(issue("missing_inmobiliaria_id", f"raw_id={raw_id} sin inmobiliaria_id valido"))

    url = clean_text(row.get("url"))
    url_normalizada = normalize_property_url_for_dedup(url)
    if not url_normalizada:
        hard_issues.append(issue("missing_url", f"raw_id={raw_id} sin url normalizable"))

    titulo = clean_text(row.get("titulo"))
    if not titulo:
        hard_issues.append(issue("missing_title", f"raw_id={raw_id} sin titulo"))

    precio_raw = row.get("precio")
    precio_present = precio_raw is not None and str(precio_raw).strip() != ""
    precio: Optional[float] = None
    if precio_present:
        try:
            precio = to_float(precio_raw)
            if precio is None or precio <= 0:
                raise ValueError("non_positive")
        except Exception:
            hard_issues.append(issue("invalid_price", f"precio={precio_raw}"))
    moneda = clean_text(row.get("moneda"))
    moneda = moneda.upper() if moneda else None
    if precio is not None and moneda not in {"ARS", "USD"}:
        hard_issues.append(issue("invalid_currency", f"moneda={moneda}"))

    operacion = normalize_operation(row.get("operacion"))
    if not operacion:
        hard_issues.append(issue("invalid_operation", f"operacion={row.get('operacion')}"))

    if hash_dedup and staging_duplicate_exists(cur, hash_dedup):
        duplicate = True
        hard_issues.append(issue("duplicate", f"hash_dedup={hash_dedup} ya existe en propiedades_staging"))

    validation_score = 100
    ciudad = clean_text(row.get("ciudad"))
    provincia = clean_text(row.get("provincia"))
    if not ciudad and not provincia:
        validation_score -= 15
        soft_issues.append(issue("missing_location", "sin ciudad ni provincia"))

    tipo_propiedad = clean_text(row.get("tipo_propiedad"))
    tipo_propiedad = tipo_propiedad.lower() if tipo_propiedad else None
    if not tipo_propiedad:
        validation_score -= 15
        soft_issues.append(issue("missing_type", "sin tipo_propiedad"))

    imagenes = row.get("imagenes")
    if not isinstance(imagenes, list):
        imagenes = []
    imagenes = imagenes[:10]
    if not imagenes:
        validation_score -= 10
        soft_issues.append(issue("missing_images", "sin imagenes"))

    if precio is None:
        validation_score -= 20

    latitud = to_float(row.get("latitud"))
    longitud = to_float(row.get("longitud"))
    if latitud is not None or longitud is not None:
        if not valid_argentina_coordinates(latitud, longitud):
            latitud = None
            longitud = None
            validation_score -= 10
            soft_issues.append(issue("invalid_coordinates", "coordenadas fuera de Argentina"))

    all_issues = hard_issues + soft_issues
    if hard_issues:
        return None, all_issues, duplicate

    staging_row = {
        "raw_id": raw_id,
        "inmobiliaria_id": inmobiliaria_id,
        "hash_dedup": hash_dedup,
        "titulo": titulo,
        "descripcion": (clean_text(row.get("descripcion")) or "")[:1000],
        "precio": precio,
        "moneda": moneda,
        "superficie_total": to_float(row.get("superficie_total")),
        "superficie_cubierta": to_float(row.get("superficie_cubierta")),
        "tipo_propiedad": tipo_propiedad,
        "operacion": operacion,
        "url": url,
        "url_normalizada": url_normalizada,
        "direccion_normalizada": collapse_spaces(row.get("direccion_raw")),
        "barrio": clean_text(row.get("barrio")),
        "ciudad": ciudad,
        "provincia": provincia,
        "pais": clean_text(row.get("pais")) or "Argentina",
        "latitud": latitud,
        "longitud": longitud,
        "imagenes": imagenes,
        "geocoding_status": "done" if latitud is not None and longitud is not None else "pending",
        "validation_score": max(0, validation_score),
        "status": "staging",
    }
    return staging_row, all_issues, duplicate


def insert_staging(cur, staging_row: Dict[str, Any]) -> None:
    placeholders = ", ".join(["%s"] * len(STAGING_COLUMNS))
    columns = ", ".join(STAGING_COLUMNS)
    values = [json_value(staging_row.get(column)) for column in STAGING_COLUMNS]
    cur.execute(
        f"INSERT INTO public.propiedades_staging ({columns}) VALUES ({placeholders})",
        values,
    )


def insert_issues(cur, raw_id: Any, issues: List[Dict[str, str]]) -> None:
    for item in issues:
        cur.execute(
            """
            INSERT INTO public.data_quality_issues (raw_id, issue_type, issue_detail)
            VALUES (%s, %s, %s)
            """,
            [raw_id, item["issue_type"], item["issue_detail"]],
        )


def update_raw_status(cur, raw_id: Any, status: str) -> None:
    cur.execute(
        "UPDATE public.propiedades_raw SET status = %s WHERE id = %s",
        [status, raw_id],
    )


def process_row(cur, row: Dict[str, Any]) -> Tuple[str, List[Dict[str, str]], bool]:
    raw_id = row.get("id")
    cur.execute("SAVEPOINT validate_raw_row")
    try:
        staging_row, issues, duplicate = build_validation(cur, row)
        if staging_row is None:
            insert_issues(cur, raw_id, issues)
            update_raw_status(cur, raw_id, "rejected")
            cur.execute("RELEASE SAVEPOINT validate_raw_row")
            return "rejected", issues, duplicate
        insert_staging(cur, staging_row)
        insert_issues(cur, raw_id, issues)
        update_raw_status(cur, raw_id, "validated")
        cur.execute("RELEASE SAVEPOINT validate_raw_row")
        return "validated", issues, duplicate
    except Exception as exc:
        cur.execute("ROLLBACK TO SAVEPOINT validate_raw_row")
        processing_issue = issue("processing_error", exc)
        insert_issues(cur, raw_id, [processing_issue])
        update_raw_status(cur, raw_id, "rejected")
        cur.execute("RELEASE SAVEPOINT validate_raw_row")
        return "rejected", [processing_issue], False


def fetch_raw_rows(cur, limit: int) -> List[Dict[str, Any]]:
    cur.execute(RAW_SELECT_SQL, [limit])
    return [dict(row) for row in cur.fetchall()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Validar propiedades_raw en Neon y pasarlas a staging")
    parser.add_argument("--limit", type=int, default=50, help="Cantidad maxima de filas raw a procesar")
    parser.add_argument("--dry-run", action="store_true", help="Procesar y hacer rollback")
    parser.add_argument("--commit", action="store_true", help="Persistir cambios en Neon")
    args = parser.parse_args()

    if args.limit <= 0:
        raise SystemExit("--limit debe ser mayor a 0")
    if args.dry_run and args.commit:
        raise SystemExit("Usar --dry-run o --commit, no ambos")
    if not args.dry_run and not args.commit:
        args.dry_run = True

    db_url = internal_db_config()
    issue_counts: Counter[str] = Counter()
    read_count = 0
    validated_count = 0
    rejected_count = 0
    duplicate_count = 0

    print("=" * 72)
    print("VALIDATE RAW PROPERTIES")
    print(f"mode={'commit' if args.commit else 'dry-run'}")
    print(f"limit={args.limit}")
    print("target=internal_db")
    print("-" * 72)

    with connect_internal_db(db_url) as conn:
        with conn.cursor() as cur:
            rows = fetch_raw_rows(cur, args.limit)
            read_count = len(rows)
            for row in rows:
                status, issues, duplicate = process_row(cur, row)
                if status == "validated":
                    validated_count += 1
                else:
                    rejected_count += 1
                if duplicate:
                    duplicate_count += 1
                for item in issues:
                    issue_counts[item["issue_type"]] += 1
        if args.commit:
            conn.commit()
            final_action = "commit"
        else:
            conn.rollback()
            final_action = "rollback"

    print(f"filas_leidas={read_count}")
    print(f"validadas={validated_count}")
    print(f"rechazadas={rejected_count}")
    print(f"duplicadas={duplicate_count}")
    print("issues_por_tipo:")
    if issue_counts:
        for issue_type, count in sorted(issue_counts.items()):
            print(f"  {issue_type}: {count}")
    else:
        print("  none: 0")
    print(f"accion_final={final_action}")
    print("=" * 72)


if __name__ == "__main__":
    main()
