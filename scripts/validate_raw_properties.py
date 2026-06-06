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
from datetime import datetime
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
  imagenes,
  datos_extra
FROM public.propiedades_raw
WHERE status = 'raw'
ORDER BY id ASC
LIMIT %s
"""

RAW_SELECT_COLUMNS = """
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
  imagenes,
  datos_extra
FROM public.propiedades_raw
"""

SOURCE_FILTERS = {
    "captured_json": ("datos_extra->>'imported_by' = %s", "scripts/import_captured_props_to_neon.py"),
}

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
    from scraper.scraper_propiedades import (
        normalize_property_url_for_dedup,
        OPERACION_MAP,
        normalize_location_fields as pipeline_normalize_location_fields,
        clean_property_images as pipeline_clean_property_images,
        _normalizar_precio_detalle as pipeline_price_from_text,
        normalizar_tipo as pipeline_normalizar_tipo,
    )
except Exception:
    pipeline_normalize_location_fields = None  # type: ignore
    pipeline_clean_property_images = None  # type: ignore
    pipeline_price_from_text = None  # type: ignore
    pipeline_normalizar_tipo = None  # type: ignore
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
    return psycopg.connect(
        db_url,
        row_factory=dict_row,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
        connect_timeout=30,
    )


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


GARBAGE_ADDRESS_PATTERNS = [
    "contacto",
    "oficinas",
    "oficina",
    "telefono",
    "teléfono",
    "tel ",
    "tel:",
    "cel ",
    "cel:",
    "whatsapp",
    "email",
    "mail",
    "www.",
    "http://",
    "https://",
    "inmobiliaria",
    "bienes raices",
    "bienes raíces",
    "consultar precio",
    "usd ",
    "u$s",
    "superficie",
    "expensas",
    "no acepta hipotecario",
    "acepta hipotecario",
    "detalles de la propiedad",
    "estilo a ",
    "matricula",
    "cucicba",
    "cmcpsi",
]


def invalid_address_reason(value: Any) -> Optional[str]:
    text = collapse_spaces(value)
    if not text:
        return None
    lowered = text.lower()
    if any(pattern in lowered for pattern in GARBAGE_ADDRESS_PATTERNS):
        return "contaminated_address"
    if re.search(r"[\w.%-]+@[\w.-]+\.[A-Za-z]{2,}", text):
        return "address_is_email"
    if re.search(r"(?:\+?\d[\d\s().-]{7,}\d)", text):
        return "address_contains_phone"
    if re.search(r"(?:u\$s|usd|\$|ars)\s*[\d.,]{2,}", lowered):
        return "address_contains_price"
    if re.fullmatch(r"(?:u\$s|usd|\$|ars)?\s*[\d.,]{2,}(?:\s*(?:usd|ars|pesos?))?", lowered):
        return "address_is_price"
    if len(text) > 90 and len(re.findall(r"\d+", text)) > 2:
        return "address_too_long_numeric"
    return None


def normalize_address_value(value: Any) -> Tuple[Optional[str], Optional[str]]:
    text = collapse_spaces(value)
    if not text:
        return None, None
    reason = invalid_address_reason(text)
    if reason:
        return None, reason
    return text, None


def clean_images(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    if callable(pipeline_clean_property_images):
        try:
            return list(pipeline_clean_property_images(value))[:10]
        except Exception:
            pass
    out: List[str] = []
    for item in value:
        url = item.get("url") or item.get("src") if isinstance(item, dict) else item
        text = clean_text(url)
        if not text:
            continue
        lower = text.lower()
        if any(token in lower for token in (
            "placeholder", "sin-imagen", "no-image", "logo", "favicon",
            "facebook", "instagram", "whatsapp", "linkedin", "youtube",
            "menu", "boton", "btn", "mapa",
        )):
            continue
        if lower.endswith(".svg") or text.startswith("data:"):
            continue
        out.append(text)
        if len(out) >= 10:
            break
    return out


# Fix global — safety net standalone: tokens de hostname para inferencia de ubicación.
# Espejo compacto del dict en scraper_propiedades._HOSTNAME_LOCATION_TOKENS.
# Solo se activa si pipeline_normalize_location_fields no está disponible O falló.
_HOSTNAME_LOCATION_TOKENS_FALLBACK: List[Tuple[str, Optional[str], str]] = [
    ("cafayate",    "Cafayate",                 "Salta"),
    ("ushuaia",     "Ushuaia",                  "Tierra del Fuego"),
    ("bariloche",   "San Carlos de Bariloche",  "Río Negro"),
    ("neuquen",     "Neuquén",                  "Neuquén"),
    ("resistencia", "Resistencia",              "Chaco"),
    ("necochea",    "Necochea",                 "Buenos Aires"),
    ("olavarria",   "Olavarría",                "Buenos Aires"),
    ("chivilcoy",   "Chivilcoy",                "Buenos Aires"),
    ("tandil",      "Tandil",                   "Buenos Aires"),
    ("formosa",     "Formosa",                  "Formosa"),
    ("posadas",     "Posadas",                  "Misiones"),
    ("jujuy",       "San Salvador de Jujuy",    "Jujuy"),
    ("tucuman",     "San Miguel de Tucumán",     "Tucumán"),
    ("salta",       "Salta",                    "Salta"),
    ("mendoza",     "Mendoza",                  "Mendoza"),
    ("cordoba",     "Córdoba",                  "Córdoba"),
    ("lapampa",     None,                       "La Pampa"),
    ("chubut",      None,                       "Chubut"),
]


def _normalize_key(value: str) -> str:
    """Normalización mínima para comparar tokens de hostname: sin acentos, minúsculas."""
    import unicodedata
    text = unicodedata.normalize("NFKD", value.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", text)


def _infer_location_from_hostname_standalone(url: Any) -> Optional[Tuple[Optional[str], str, str]]:
    """Fallback standalone: infiere (ciudad, provincia, motivo) desde hostname del URL.
    No depende del scraper. Solo actúa si hay exactamente un match no ambiguo.
    """
    if not url:
        return None
    try:
        hostname = urlparse(str(url)).hostname or ""
    except Exception:
        return None
    if not hostname:
        return None
    if hostname.lower().startswith("www."):
        hostname = hostname[4:]
    hostname = re.sub(
        r"\.(?:com\.ar|net\.ar|org\.ar|gob\.ar|gov\.ar|edu\.ar|com|net|org|ar)$",
        "", hostname, flags=re.IGNORECASE,
    )
    base_key = _normalize_key(hostname)
    if not base_key or len(base_key) < 4:
        return None
    matches = []
    for token, ciudad, provincia in _HOSTNAME_LOCATION_TOKENS_FALLBACK:
        token_key = _normalize_key(token)
        if token_key and token_key in base_key:
            matches.append((ciudad, provincia))
    if len(matches) != 1:
        return None
    ciudad, provincia = matches[0]
    return ciudad, provincia, "location_inferred_from_hostname"


def infer_location_from_signals(row: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    ciudad = clean_text(row.get("ciudad"))
    provincia = clean_text(row.get("provincia"))
    barrio = clean_text(row.get("barrio"))
    datos_extra = row.get("datos_extra") if isinstance(row.get("datos_extra"), dict) else {}
    urls = [
        row.get("url"),
        row.get("url_normalizada"),
        datos_extra.get("source_url"),
        datos_extra.get("captured_source_url"),
    ]

    if callable(pipeline_normalize_location_fields):
        description = " ".join(
            str(value or "")
            for value in (
                row.get("descripcion"),
                row.get("titulo"),
                row.get("url"),
                datos_extra.get("source_url"),
                datos_extra.get("captured_source_url"),
            )
        )
        for candidate_url in urls:
            try:
                normalized = pipeline_normalize_location_fields(
                    row.get("titulo"),
                    row.get("direccion_raw"),
                    barrio,
                    ciudad,
                    provincia,
                    row.get("pais") or "Argentina",
                    candidate_url,
                    description,
                )
            except Exception:
                normalized = None
            if isinstance(normalized, dict) and normalized.get("location_normalized"):
                return (
                    clean_text(normalized.get("ciudad")),
                    clean_text(normalized.get("provincia")),
                    clean_text(normalized.get("barrio")),
                    clean_text(normalized.get("motivo")),
                )

    # Safety net: si el pipeline no infirió nada y ciudad/provincia siguen vacías,
    # intentar desde hostname (independiente del scraper).
    if not ciudad and not provincia:
        for candidate_url in urls:
            result = _infer_location_from_hostname_standalone(candidate_url)
            if result:
                inferred_ciudad, inferred_provincia, motivo = result
                return clean_text(inferred_ciudad), inferred_provincia, barrio, motivo

    return ciudad, provincia, barrio, None


def infer_price_from_text(row: Dict[str, Any]) -> Tuple[Optional[float], Optional[str], Optional[str]]:
    if not callable(pipeline_price_from_text):
        return None, None, None
    text = " ".join(str(value or "") for value in (row.get("titulo"), row.get("descripcion"), row.get("url")))
    try:
        price, currency = pipeline_price_from_text(text)
    except Exception:
        return None, None, None
    if price and price > 0:
        return float(price), (clean_text(currency) or "").upper(), "price_inferred_from_text"
    return None, None, None


def normalize_type_from_signals(row: Dict[str, Any]) -> Optional[str]:
    tipo = clean_text(row.get("tipo_propiedad"))
    if tipo and tipo.lower() != "otro":
        return tipo.lower()
    if callable(pipeline_normalizar_tipo):
        for value in (row.get("titulo"), row.get("descripcion"), row.get("url")):
            try:
                inferred = pipeline_normalizar_tipo(value)
            except Exception:
                inferred = None
            if inferred and inferred != "otro":
                return str(inferred).lower()
    return tipo.lower() if tipo else None


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
    price_inference: Optional[str] = None
    invalid_price_present = False
    if precio_present:
        try:
            precio = to_float(precio_raw)
            if precio is None or precio <= 0:
                raise ValueError("non_positive")
        except Exception:
            invalid_price_present = True
            hard_issues.append(issue("invalid_price", f"precio={precio_raw}"))
    if precio is None and not invalid_price_present:
        inferred_price, inferred_currency, price_inference = infer_price_from_text(row)
        if inferred_price is not None:
            precio = inferred_price
    moneda = clean_text(row.get("moneda"))
    moneda = moneda.upper() if moneda else None
    if precio is not None and not moneda and price_inference:
        _, inferred_currency, _ = infer_price_from_text(row)
        moneda = inferred_currency
    if precio is not None and moneda not in {"ARS", "USD"}:
        hard_issues.append(issue("invalid_currency", f"moneda={moneda}"))

    operacion = normalize_operation(row.get("operacion"))
    if not operacion:
        hard_issues.append(issue("invalid_operation", f"operacion={row.get('operacion')}"))

    if hash_dedup and staging_duplicate_exists(cur, hash_dedup):
        duplicate = True
        hard_issues.append(issue("duplicate", f"hash_dedup={hash_dedup} ya existe en propiedades_staging"))

    validation_score = 100
    ciudad, provincia, barrio, location_inference = infer_location_from_signals(row)
    if not ciudad and not provincia:
        validation_score -= 15
        soft_issues.append(issue("missing_location", "sin ciudad ni provincia"))
    elif location_inference:
        soft_issues.append(issue("location_inferred_from_text", location_inference))

    tipo_propiedad = normalize_type_from_signals(row)
    if not tipo_propiedad:
        validation_score -= 15
        soft_issues.append(issue("missing_type", "sin tipo_propiedad"))

    imagenes = clean_images(row.get("imagenes"))
    if not imagenes:
        validation_score -= 10
        soft_issues.append(issue("missing_images", "sin imagenes"))

    if precio is None:
        validation_score -= 20
    elif price_inference:
        soft_issues.append(issue("price_inferred_from_text", price_inference))

    direccion_normalizada, address_issue = normalize_address_value(row.get("direccion_raw"))
    if address_issue:
        validation_score -= 5
        soft_issues.append(issue("invalid_address", address_issue))
    if not direccion_normalizada and (ciudad or provincia):
        validation_score -= 5
        soft_issues.append(issue("geocoding_skipped_approx_location", "sin direccion precisa; no se inventan coordenadas"))

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
        "direccion_normalizada": direccion_normalizada,
        "barrio": barrio,
        "ciudad": ciudad,
        "provincia": provincia,
        "pais": clean_text(row.get("pais")) or "Argentina",
        "latitud": latitud,
        "longitud": longitud,
        "imagenes": imagenes,
        "geocoding_status": (
            "done"
            if latitud is not None and longitud is not None
            else "skipped"
            if not direccion_normalizada and (ciudad or provincia)
            else "pending"
        ),
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


def source_filter_clause(source: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if not source:
        return None, None
    if source not in SOURCE_FILTERS:
        valid = ", ".join(sorted(SOURCE_FILTERS))
        raise SystemExit(f"--source invalido: {source}. Valores validos: {valid}")
    return SOURCE_FILTERS[source]


def fetch_raw_rows(cur, limit: int, source: Optional[str] = None, created_after: Optional[str] = None) -> List[Dict[str, Any]]:
    clauses = ["status = 'raw'"]
    params: List[Any] = []
    source_clause, source_value = source_filter_clause(source)
    if source_clause:
        clauses.append(source_clause)
        params.append(source_value)
    if created_after:
        clauses.append("scraped_at >= %s")
        params.append(created_after)
    params.append(limit)
    where_sql = " AND ".join(clauses)
    sql = f"""
{RAW_SELECT_COLUMNS}
WHERE {where_sql}
ORDER BY id ASC
LIMIT %s
"""
    cur.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


def render_report(summary: Dict[str, Any]) -> str:
    issue_lines = "\n".join(f"- {key}: {value}" for key, value in sorted(summary["issue_counts"].items())) or "- none: 0"
    critical_keys = {
        "missing_hash",
        "missing_inmobiliaria_id",
        "missing_url",
        "missing_title",
        "invalid_price",
        "invalid_currency",
        "invalid_operation",
        "duplicate",
    }
    critical_counts = {key: value for key, value in summary["issue_counts"].items() if key in critical_keys}
    critical_lines = "\n".join(f"- {key}: {value}" for key, value in sorted(critical_counts.items())) or "- none: 0"
    return f"""# Validate imported raw properties

Fecha: {summary['timestamp']}
Modo: {summary['mode']}
Origen: {summary['source'] or 'all_raw'}
Destino: public.propiedades_staging

## Resumen

- raw_detectadas: {summary['read_count']}
- candidatas_a_staging: {summary['validated_count']}
- pasaron_a_staging: {summary['validated_count'] if summary['mode'] == 'commit' else 0}
- rechazadas: {summary['rejected_count']}
- warnings: {summary['warning_count']}
- duplicadas: {summary['duplicate_count']}
- accion_final: {summary['final_action']}

## Issues principales

{issue_lines}

## Campos criticos faltantes o invalidos

{critical_lines}

## Seguridad

- no_toca_supabase: true
- no_publica_supabase: true
- no_toca_publish_queue: true
- no_modifica_env: true
- no_borra_datos: true
- no_commit_git: true
- no_push_git: true
"""


def safe_relative_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except Exception:
        return str(path)


def write_report(summary: Dict[str, Any], report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_report(summary), encoding="utf-8")


def update_master_progress(summary: Dict[str, Any], report_path: Path) -> None:
    master_path = REPO_ROOT / "reports" / "scraping_autofix" / "master_progress.md"
    master_path.parent.mkdir(parents=True, exist_ok=True)
    entry = (
        f"\n\n## Validate imported raw {summary['timestamp']}\n\n"
        f"- Modo: {summary['mode']}\n"
        f"- Origen: {summary['source'] or 'all_raw'}\n"
        f"- Raw detectadas: {summary['read_count']}\n"
        f"- Candidatas a staging: {summary['validated_count']}\n"
        f"- Rechazadas: {summary['rejected_count']}\n"
        f"- Warnings: {summary['warning_count']}\n"
        f"- Duplicadas: {summary['duplicate_count']}\n"
        f"- Accion final: {summary['final_action']}\n"
        f"- Reporte: {safe_relative_path(report_path)}\n"
        f"- Confirmacion: no .env, no borrado, no commit, no push, no publicacion masiva Supabase, no publish_queue, no pipeline commit, no cambios destructivos.\n"
    )
    try:
        if master_path.exists():
            current = master_path.read_text(encoding="utf-8", errors="ignore")
        else:
            current = "# Scraping autofix master progress\n"
        master_path.write_text(current.rstrip() + entry + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"warning: no pude actualizar master_progress.md: {exc}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validar propiedades_raw en Neon y pasarlas a staging")
    parser.add_argument("--limit", type=int, default=50, help="Cantidad maxima de filas raw a procesar")
    parser.add_argument("--source", choices=sorted(SOURCE_FILTERS), help="Filtrar raw por origen seguro")
    parser.add_argument("--created-after", help="Filtrar raw por scraped_at >= valor ISO/timestamptz")
    parser.add_argument("--report", type=Path, help="Ruta de reporte markdown")
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
    print(f"source={args.source or 'all_raw'}")
    if args.created_after:
        print(f"created_after={args.created_after}")
    print("target=internal_db")
    print("-" * 72)

    with connect_internal_db(db_url) as conn:
        with conn.cursor() as cur:
            rows = fetch_raw_rows(cur, args.limit, args.source, args.created_after)
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
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    report_path = args.report or (
        REPO_ROOT / "reports" / "scraping_autofix" / f"validate_imported_raw_{timestamp}.md"
    )
    if not report_path.is_absolute():
        report_path = REPO_ROOT / report_path
    warning_count = sum(issue_counts.values())
    summary = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "mode": "commit" if args.commit else "dry-run",
        "source": args.source,
        "read_count": read_count,
        "validated_count": validated_count,
        "rejected_count": rejected_count,
        "warning_count": warning_count,
        "duplicate_count": duplicate_count,
        "issue_counts": issue_counts,
        "final_action": final_action,
    }
    write_report(summary, report_path)
    update_master_progress(summary, report_path)
    print(f"report={report_path}")
    print("=" * 72)


if __name__ == "__main__":
    main()
