#!/usr/bin/env python
"""Import locally captured property JSON files into Neon propiedades_raw.

This script only uses INTERNAL_DB_URL. It never reads or writes Supabase.
Default mode is dry-run; pass --commit to persist rows in Neon.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qsl, unquote, urlencode, urlparse

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
DEFAULT_INPUT_DIR = REPO_ROOT / "data" / "scraping_batches" / "captured_20260530"
REPORT_DIR = REPO_ROOT / "reports" / "scraping_autofix"

# Safety net Fix I (global): URLs de imagen nunca son páginas de propiedad.
# Evita importar thumbnails cuyo filename contiene un slug con tipo/operación/ciudad.
_IMAGE_URL_SAFETY_RE = re.compile(
    r"\.(jpg|jpeg|png|gif|webp|jfif|svg|bmp|tiff?|ico|avif|heic)$",
    re.IGNORECASE,
)

RAW_COLUMNS = [
    "scraping_run_item_id",
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
    "direccion_raw",
    "barrio",
    "ciudad",
    "provincia",
    "pais",
    "latitud",
    "longitud",
    "imagenes",
    "datos_extra",
    "status",
]
VALID_OPERATIONS = {"venta", "alquiler", "alquiler_temporario"}
VALID_CURRENCIES = {"ARS", "USD"}
UI_TITLE_PATTERNS = [
    "mover a la izquierda",
    "mover a la derecha",
    "mover hacia arriba",
    "mover hacia abajo",
    "arrastrar",
    "soltar",
]
TRACKING_QUERY_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "wbraid",
    "gbraid",
    "mc_cid",
    "mc_eid",
}
OPERATION_MAP = {
    "venta": "venta",
    "en venta": "venta",
    "sale": "venta",
    "for sale": "venta",
    "alquiler": "alquiler",
    "en alquiler": "alquiler",
    "alq": "alquiler",
    "rent": "alquiler",
    "for rent": "alquiler",
    "temporario": "alquiler_temporario",
    "temporal": "alquiler_temporario",
    "temporaria": "alquiler_temporario",
    "alquiler temporario": "alquiler_temporario",
    "alquiler temporal": "alquiler_temporario",
    "por dia": "alquiler_temporario",
    "por día": "alquiler_temporario",
    "por semana": "alquiler_temporario",
    "short term": "alquiler_temporario",
}

# Fix por familia ASP CMS: inferir operacion desde subfolder de URL de detalle
# Aplica a: /venta/item.asp, /alquiler/item.asp, /temporario/item.asp (y variantes)
_ASP_CMS_OP_PATH_RE = re.compile(
    r"/(?P<op>venta|ventas|alquiler|temporario|alquiler[-_]temporario)"
    r"/(?:item|ver|ampliar|ficha|detalle)\.aspx?\b",
    re.IGNORECASE,
)

# Fix por familia short-ID rural CMS: inferir tipo_propiedad=campo desde URL pattern + hostname
# Aplica a: /ca266.html, /mo340.html, /mi319.html (2-3 letras + 3-6 digitos + .html)
# Solo actua si el hostname contiene señales rurales y el tipo actual no es ya un tipo rural.
_RURAL_SHORTID_URL_RE = re.compile(
    r"/[a-z]{2,3}\d{3,6}\.html?\b",
    re.IGNORECASE,
)
_RURAL_DOMAIN_SIGNALS: frozenset = frozenset({
    "campo", "campos", "rural", "agro", "pampa",
    "hectarea", "hectárea", "haras", "estancia", "chacra",
})
_RURAL_TIPO_VALUES: frozenset = frozenset({
    "campo", "chacra", "estancia", "finca", "quinta",
})
# Detecta títulos que son nombres de archivo del CMS short-ID rural (e.g. "Ca266.Html").
# Fix global — no hardcodear por dominio. Aplica en importer como safety net.
_FILENAME_TITLE_RE = re.compile(r"^[a-zA-Z]{2,4}\d{3,6}\.html?$", re.IGNORECASE)


def infer_operation_from_url_path(url: Any) -> Optional[str]:
    """Red de seguridad — familia ASP CMS: detecta operacion desde subfolder en URL de detalle.

    Solo aplica al patron /venta/item.asp, /alquiler/item.asp, /temporario/item.asp.
    No modifica URLs que no matcheen este patron.
    """
    if not url:
        return None
    m = _ASP_CMS_OP_PATH_RE.search(str(url))
    if not m:
        return None
    seg = m.group("op").lower().replace("-", "_")
    if seg in ("venta", "ventas"):
        return "venta"
    if seg in ("temporario", "alquiler_temporario"):
        return "alquiler_temporario"
    if seg == "alquiler":
        return "alquiler"
    return None


def infer_tipo_from_rural_domain(url: Any, tipo_actual: Optional[str]) -> Optional[str]:
    """Red de seguridad — familia short-ID rural CMS: corrige tipo_propiedad a 'campo'
    cuando la URL es un short-ID (/ca266.html) y el hostname contiene señales rurales.

    Condiciones para actuar:
    - URL path matchea /[a-z]{2,3}\\d{3,6}.html (short-ID: ca266, mo340, mi319)
    - Hostname contiene al menos una señal rural (_RURAL_DOMAIN_SIGNALS)
    - Tipo actual NO es ya un tipo rural correcto (_RURAL_TIPO_VALUES)

    No bloquea el import. Solo sobreescribe tipo_propiedad y registra warning.
    """
    if not url:
        return None
    url_str = str(url)
    if not _RURAL_SHORTID_URL_RE.search(url_str):
        return None
    try:
        hostname = urlparse(url_str).hostname or ""
    except Exception:
        hostname = ""
    if not any(sig in hostname.lower() for sig in _RURAL_DOMAIN_SIGNALS):
        return None
    # No sobreescribir si ya es un tipo rural correcto
    if tipo_actual in _RURAL_TIPO_VALUES:
        return None
    return "campo"


# Tabla de labels legibles para tipos de propiedad (usado en _fix_filename_titulo)
_TIPO_LABEL_MAP: Dict[str, str] = {
    "campo": "Campo", "chacra": "Chacra", "estancia": "Estancia",
    "finca": "Finca", "quinta": "Quinta", "casa": "Casa",
    "departamento": "Departamento", "terreno": "Terreno",
    "local": "Local", "oficina": "Oficina", "cochera": "Cochera",
    "lote": "Lote",
}


def _fix_filename_titulo(
    titulo: Optional[str],
    tipo_propiedad: Optional[str],
    operation: Optional[str],
    provincia: Optional[str],
) -> Optional[str]:
    """Safety net — reemplaza títulos que son nombres de archivo del CMS short-ID rural.

    Detecta e.g. "Ca266.Html", "Mo342.Html", "Mo340.Html" y los sintetiza con
    tipo + operacion + provincia (todos ya resueltos al momento de llamar).
    Fix global — no hardcodea por dominio ni por propiedad.
    Devuelve el nuevo título sintetizado, o None si el título no es un filename.
    """
    if not titulo:
        return None
    if not _FILENAME_TITLE_RE.fullmatch(str(titulo).strip()):
        return None
    tipo_label = _TIPO_LABEL_MAP.get(str(tipo_propiedad or "").lower(), "Propiedad")
    op_str = str(operation or "venta").lower()
    op_label = "en alquiler" if "alquiler" in op_str else "en venta"
    prov = str(provincia or "").strip()
    if prov:
        return f"{tipo_label} {op_label} en {prov}"
    return f"{tipo_label} {op_label}"


try:
    from scraper.scraper_propiedades import (  # type: ignore
        normalize_location_fields as pipeline_normalize_location_fields,
        clean_property_images as pipeline_clean_property_images,
        _normalizar_precio_detalle as pipeline_price_from_text,
        normalizar_tipo as pipeline_normalizar_tipo,
        _is_invalid_scraped_address as pipeline_is_invalid_scraped_address,  # Fix K
        _extract_address_from_titulo as pipeline_extract_address_from_titulo,  # Fix K
    )
except Exception:
    pipeline_normalize_location_fields = None  # type: ignore
    pipeline_clean_property_images = None  # type: ignore
    pipeline_price_from_text = None  # type: ignore
    pipeline_normalizar_tipo = None  # type: ignore
    pipeline_is_invalid_scraped_address = None  # type: ignore  # Fix K
    pipeline_extract_address_from_titulo = None  # type: ignore  # Fix K


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
    cleaned = re.sub(r"\s+", " ", str(value)).strip()
    return cleaned or None


def truncate(value: Any, limit: int) -> Optional[str]:
    cleaned = clean_text(value)
    if not cleaned:
        return None
    return cleaned[:limit]


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

    path = parsed.path or ""
    if parsed.netloc:
        path = re.sub(r"/+", "/", unquote(path)).strip().rstrip("/")
    else:
        path = ""
    path = path.lower()

    query_items = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=False):
        key_clean = key.strip().lower()
        if not key_clean or key_clean in TRACKING_QUERY_PARAMS or key_clean.startswith("utm_"):
            continue
        query_items.append((key_clean, value.strip().lower()))
    query = urlencode(sorted(query_items), doseq=True)

    normalized = f"{host}{path}"
    if query:
        normalized = f"{normalized}?{query}"
    return normalized.rstrip("/")


def normalize_external_id_for_dedup(id_externo: Any) -> str:
    if id_externo is None:
        return ""
    return re.sub(r"\s+", "", str(id_externo).strip().lower())


def hash_propiedad(inmobiliaria_id: Any, id_externo: Any, url: Any) -> str:
    url_key = normalize_property_url_for_dedup(url)
    id_key = normalize_external_id_for_dedup(id_externo)
    if url_key:
        key = f"{inmobiliaria_id}|url|{url_key}"
    elif id_key:
        key = f"{inmobiliaria_id}|id_externo|{id_key}"
    else:
        key = f"{inmobiliaria_id}|sin_identidad|"
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def host_key(url: Any) -> str:
    normalized = normalize_property_url_for_dedup(url)
    if not normalized:
        return ""
    return normalized.split("/", 1)[0].split("?", 1)[0]


def normalize_operation(value: Any) -> Optional[str]:
    cleaned = clean_text(value)
    if not cleaned:
        return None
    key = cleaned.lower()
    if key in VALID_OPERATIONS:
        return key
    return OPERATION_MAP.get(key)


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


def normalize_currency(value: Any) -> Optional[str]:
    cleaned = clean_text(value)
    if not cleaned:
        return None
    cleaned = cleaned.upper()
    if cleaned in {"U$S", "US$", "DOLAR", "DOLARES", "DÓLAR", "DÓLARES"}:
        return "USD"
    if cleaned in {"$", "PESO", "PESOS"}:
        return "ARS"
    return cleaned


def is_ui_contaminated_title(title: Any) -> bool:
    cleaned = clean_text(title)
    if not cleaned:
        return False
    lower = cleaned.lower()
    if any(pattern in lower for pattern in UI_TITLE_PATTERNS):
        return True
    # Rechazar títulos de páginas de listado/categoría — Fix I (global).
    # Patrón: "Terrenos a la venta | Ciudad" / "Casas en venta | Zona Norte"
    # Estas páginas son categorías de WordPress/CMS, no fichas individuales.
    if re.search(
        r"^(?:terrenos?|casas?|departamentos?|deptos?|lotes?|locales?|oficinas?|galpones?|"
        r"cocheras?|ph|monoambientes?|campos?|chalets?|duplex|propiedades?)"
        r"\s+(?:a\s+la\s+|en\s+)?(?:venta|alquiler)\s*\|",
        cleaned, re.I,
    ):
        return True
    return False


def real_images(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    if callable(pipeline_clean_property_images):
        try:
            return list(pipeline_clean_property_images(value))[:10]
        except Exception:
            pass
    images = []
    for item in value:
        if isinstance(item, dict):
            url = item.get("url") or item.get("src") or item.get("href") or item.get("image")
        else:
            url = item
        url_text = clean_text(url)
        if not url_text:
            continue
        lower = url_text.lower()
        if (
            "placeholder" in lower
            or "sin-imagen" in lower
            or "no-image" in lower
            or "logo" in lower
            or "favicon" in lower
            or "facebook" in lower
            or "instagram" in lower
            or "whatsapp" in lower
            or "linkedin" in lower
            or "youtube" in lower
            or "menu" in lower
            or "boton" in lower
            or "btn" in lower
            or "mapa" in lower
            or lower.endswith(".svg")
            or "google" in lower and "map" in lower
        ):
            continue
        images.append(url_text)
        if len(images) >= 10:
            break
    return images


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
    "consultas online",  # Fix K: texto de contacto capturado como dirección
]


def invalid_address_reason(value: Any) -> Optional[str]:
    text = clean_text(value)
    if not text:
        return None
    lowered = text.lower()
    if any(pattern in lowered for pattern in GARBAGE_ADDRESS_PATTERNS):
        return "contaminated_address"
    if re.search(r"\b[a-z0-9-]+\.(?:com\.ar|net\.ar|org\.ar|com|net|org)\b", lowered):
        return "contaminated_address_domain"
    if re.search(r"[\w.%-]+@[\w.-]+\.[A-Za-z]{2,}", text):
        return "address_is_email"
    if re.search(r"(?:\+?\d[\d\s().-]{7,}\d)", text):
        return "address_contains_phone"
    if re.search(r"(?:u\$s|usd|\$|ars)\s*[\d.,]{2,}", lowered):
        return "address_contains_price"
    if re.fullmatch(r"(?:u\$s|usd|\$|ars)?\s*[\d.,]{2,}(?:\s*(?:usd|ars|pesos?))?", lowered):
        return "address_is_price"
    digits = re.findall(r"\d+", text)
    if len(text) > 90 and len(digits) > 2:
        return "address_too_long_numeric"
    # Fix K: detectar fechas, textos de contacto y overflow de descripcion
    if callable(pipeline_is_invalid_scraped_address):
        try:
            if pipeline_is_invalid_scraped_address(text):
                return "invalid_address_content"
        except Exception:
            pass
    return None


def normalize_address_value(value: Any) -> Tuple[Optional[str], Optional[str]]:
    text = truncate(value, 300)
    if not text:
        return None, None
    reason = invalid_address_reason(text)
    if reason:
        return None, reason
    return text, None


def infer_location_from_signals(prop: Dict[str, Any], source_row: Dict[str, str]) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    ciudad = truncate(prop.get("ciudad"), 120)
    provincia = truncate(prop.get("provincia"), 120)
    barrio = truncate(prop.get("barrio"), 120)
    if not callable(pipeline_normalize_location_fields):
        return ciudad, provincia, barrio, None

    urls = [
        prop.get("url"),
        prop.get("sourceUrl") or prop.get("source_url"),
        source_row.get("url"),
        source_row.get("url_listado"),
        source_row.get("web"),
    ]
    description = " ".join(
        str(value or "")
        for value in (
            prop.get("descripcion"),
            prop.get("titulo"),
            prop.get("url"),
            prop.get("sourceUrl") or prop.get("source_url"),
        )
    )
    for candidate_url in urls:
        try:
            normalized = pipeline_normalize_location_fields(
                prop.get("titulo"),
                prop.get("direccion"),
                barrio,
                ciudad,
                provincia,
                prop.get("pais") or "Argentina",
                candidate_url,
                description,
            )
        except Exception:
            normalized = None
        if isinstance(normalized, dict) and normalized.get("location_normalized"):
            return (
                truncate(normalized.get("ciudad"), 120),
                truncate(normalized.get("provincia"), 120),
                truncate(normalized.get("barrio"), 120),
                clean_text(normalized.get("motivo")),
            )
    return ciudad, provincia, barrio, None


def infer_price_from_text(prop: Dict[str, Any]) -> Tuple[Optional[float], Optional[str], Optional[str]]:
    if not callable(pipeline_price_from_text):
        return None, None, None
    text = " ".join(str(value or "") for value in (prop.get("titulo"), prop.get("descripcion"), prop.get("url")))
    try:
        price, currency = pipeline_price_from_text(text)
    except Exception:
        return None, None, None
    if price and price > 0:
        return float(price), normalize_currency(currency) or currency, "price_inferred_from_text"
    return None, None, None


def normalize_type_from_signals(prop: Dict[str, Any]) -> Optional[str]:
    tipo = clean_text(prop.get("tipo_propiedad"))
    if tipo and tipo.lower() != "otro":
        return tipo.lower()
    if callable(pipeline_normalizar_tipo):
        for value in (prop.get("titulo"), prop.get("descripcion"), prop.get("url")):
            try:
                inferred = pipeline_normalizar_tipo(value)
            except Exception:
                inferred = None
            if inferred and inferred != "otro":
                return str(inferred).lower()
    return tipo.lower() if tipo else None


def quality_score(prop: Dict[str, Any], warnings: List[Dict[str, str]]) -> int:
    raw_score = prop.get("score_calidad")
    if raw_score is not None:
        try:
            return max(0, min(100, int(float(raw_score))))
        except Exception:
            pass
    score = 100
    issue_types = {item["issue_type"] for item in warnings}
    if "missing_location" in issue_types:
        score -= 15
    if "missing_type" in issue_types or "invalid_type" in issue_types:
        score -= 15
    if "missing_images" in issue_types:
        score -= 10
    if prop.get("precio") in (None, ""):
        score -= 20
    if "invalid_price" in issue_types or "invalid_currency" in issue_types:
        score -= 20
    if "invalid_operation" in issue_types:
        score -= 20
    return max(0, min(100, score))


def issue(issue_type: str, detail: Any = "") -> Dict[str, str]:
    return {"issue_type": issue_type, "issue_detail": str(detail or "")[:200]}


def latest_batch_csv() -> Optional[Path]:
    batch_dir = REPO_ROOT / "data" / "scraping_batches"
    candidates = sorted(batch_dir.glob("batch_*.csv"), key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def load_batch_rows(path: Path) -> List[Dict[str, str]]:
    csv.field_size_limit(1024 * 1024 * 64)
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def build_source_indexes(rows: Iterable[Dict[str, str]]) -> Tuple[Dict[str, Dict[str, str]], Dict[str, List[Dict[str, str]]]]:
    exact: Dict[str, Dict[str, str]] = {}
    by_host: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in rows:
        for field in ("url", "url_listado", "web", "final_url"):
            value = row.get(field)
            normalized = normalize_property_url_for_dedup(value)
            if normalized:
                exact.setdefault(normalized, row)
            host = host_key(value)
            if host and row not in by_host[host]:
                by_host[host].append(row)
    return exact, by_host


def resolve_source_row(source_url: Any, exact: Dict[str, Dict[str, str]], by_host: Dict[str, List[Dict[str, str]]]) -> Optional[Dict[str, str]]:
    normalized = normalize_property_url_for_dedup(source_url)
    if normalized in exact:
        return exact[normalized]
    host = host_key(source_url)
    matches = by_host.get(host) or []
    if len(matches) == 1:
        return matches[0]
    for row in matches:
        row_url = normalize_property_url_for_dedup(row.get("url") or row.get("url_listado"))
        if row_url and (row_url.startswith(normalized) or normalized.startswith(row_url)):
            return row
    return None


def load_captured_files(input_dir: Path) -> List[Tuple[Path, Dict[str, Any]]]:
    files = sorted(f for f in input_dir.glob("*.json") if not f.name.endswith(".metadata.json"))
    loaded = []
    for path in files:
        with path.open("r", encoding="utf-8") as fh:
            loaded.append((path, json.load(fh)))
    return loaded


def build_raw_candidate(path: Path, payload: Dict[str, Any], prop: Dict[str, Any], source_row: Dict[str, str]) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, str]], bool]:
    issues: List[Dict[str, str]] = []
    hard_reject = False

    try:
        inmobiliaria_id = int(source_row.get("inmobiliaria_id") or prop.get("inmobiliaria_id") or 0)
    except Exception:
        inmobiliaria_id = 0
    if inmobiliaria_id <= 0:
        issues.append(issue("missing_inmobiliaria_id", f"{path.name}: sin inmobiliaria_id real"))
        hard_reject = True

    url = clean_text(prop.get("url"))
    url_normalizada = normalize_property_url_for_dedup(url)
    if not url or not url_normalizada:
        issues.append(issue("missing_url", f"{path.name}: url no normalizable"))
        hard_reject = True

    # Safety net Fix I — rechazar URL de imagen (nunca es una página de propiedad).
    if url and _IMAGE_URL_SAFETY_RE.search(unquote(urlparse(url).path or "").lower()):
        issues.append(issue("url_is_image_file", "URL apunta a un archivo de imagen, no a una página de propiedad"))
        hard_reject = True

    titulo = truncate(prop.get("titulo"), 300)
    if not titulo:
        issues.append(issue("missing_title", f"{path.name}: sin titulo"))
        hard_reject = True
    elif is_ui_contaminated_title(titulo):
        issues.append(issue("ui_contaminated_title", titulo))
        hard_reject = True

    operation = normalize_operation(prop.get("operacion"))
    # Red de seguridad — familia ASP CMS: sobreescribir operacion si el URL path lo indica
    _url_op = infer_operation_from_url_path(url)
    if _url_op and _url_op != operation:
        issues.append(issue("operation_inferred_from_url_path", f"operacion={prop.get('operacion')!r} -> {_url_op}"))
        operation = _url_op
    if not operation:
        issues.append(issue("invalid_operation", f"operacion={prop.get('operacion')}"))

    tipo_propiedad = normalize_type_from_signals(prop)
    # Fix por familia short-ID rural CMS: corregir tipo_propiedad defaulteado por page_text heurístico
    _rural_tipo = infer_tipo_from_rural_domain(url, tipo_propiedad)
    if _rural_tipo:
        issues.append(issue(
            "tipo_inferred_from_rural_domain",
            f"tipo={prop.get('tipo_propiedad')!r} -> {_rural_tipo}",
        ))
        tipo_propiedad = _rural_tipo
    if not tipo_propiedad or tipo_propiedad.lower() == "otro":
        issues.append(issue("missing_type", f"tipo_propiedad={prop.get('tipo_propiedad')}"))

    price = None
    price_inference = None
    if prop.get("precio") not in (None, ""):
        try:
            price = to_float(prop.get("precio"))
            if price is None or price <= 0:
                raise ValueError("non_positive")
        except Exception:
            issues.append(issue("invalid_price", f"precio={prop.get('precio')}"))
            price = None
    if price is None:
        inferred_price, inferred_currency, price_inference = infer_price_from_text(prop)
        if inferred_price is not None:
            price = inferred_price

    currency = normalize_currency(prop.get("moneda"))
    if price is not None and not currency and price_inference:
        _, inferred_currency, _ = infer_price_from_text(prop)
        currency = normalize_currency(inferred_currency)
    if price is not None and currency not in VALID_CURRENCIES:
        issues.append(issue("invalid_currency", f"moneda={prop.get('moneda')}"))

    ciudad, provincia, barrio, location_inference = infer_location_from_signals(prop, source_row)
    if not ciudad and not provincia:
        issues.append(issue("missing_location", "sin ciudad ni provincia"))
    elif location_inference:
        issues.append(issue("location_inferred_from_text", location_inference))

    # Safety net — CMS short-ID rural: sintetizar título si es nombre de archivo
    # (e.g. "Ca266.Html"). Se llama aquí porque tipo_propiedad y provincia ya están resueltos.
    _titulo_fixed = _fix_filename_titulo(titulo, tipo_propiedad, operation, provincia)
    if _titulo_fixed:
        issues.append(issue("titulo_sintetizado_desde_filename", f"{titulo!r} -> {_titulo_fixed!r}"))
        titulo = _titulo_fixed

    images = real_images(prop.get("imagenes"))
    if not images:
        issues.append(issue("missing_images", "sin imagenes reales"))

    hash_dedup = hash_propiedad(inmobiliaria_id, prop.get("id_externo"), url) if inmobiliaria_id > 0 else ""
    if not hash_dedup:
        issues.append(issue("missing_hash", f"{path.name}: sin hash_dedup recalculable"))
        hard_reject = True

    score = quality_score(prop, issues)
    if score < 60:
        issues.append(issue("low_quality_score", f"score_calidad={score}"))

    original_id = prop.get("inmobiliaria_id")
    if original_id not in (None, "", inmobiliaria_id):
        issues.append(issue("source_test_mode_id_rewritten", f"{original_id} -> {inmobiliaria_id}"))

    direccion_raw, address_issue = normalize_address_value(prop.get("direccion"))
    # Fix K: si la direccion es invalida, intentar recuperarla desde el titulo.
    if address_issue and callable(pipeline_extract_address_from_titulo):
        try:
            _addr_from_titulo = pipeline_extract_address_from_titulo(titulo)
            if _addr_from_titulo:
                direccion_raw = _addr_from_titulo
                address_issue = None
        except Exception:
            pass
    if address_issue:
        issues.append(issue("invalid_address", address_issue))

    url_key = normalize_property_url_for_dedup(url)
    cross_agency_signature = "|".join([
        url_key,
        (direccion_raw or "").lower(),
        (ciudad or "").lower(),
        (provincia or "").lower(),
        str(price or ""),
    ]).strip("|")

    datos_extra = {
        "captured_file": path.name,
        "captured_source_url": payload.get("url"),
        "captured_strategy": payload.get("estrategia"),
        "captured_at": payload.get("captured_at") or payload.get("metadata", {}).get("captured_at"),
        "source_scraping_run_item_id": source_row.get("id"),
        "source_inmobiliaria_nombre": source_row.get("inmobiliaria_nombre"),
        "original_inmobiliaria_id": original_id,
        "original_hash_dedup": prop.get("hash_dedup"),
        "id_externo": prop.get("id_externo"),
        "quality_score": score,
        "import_warnings": [item["issue_type"] for item in issues],
        "imported_by": "scripts/import_captured_props_to_neon.py",
        "location_inference": location_inference,
        "price_inference": price_inference,
        "address_issue": address_issue,
        "canonical_url_key": url_key,
        "cross_agency_signature": cross_agency_signature,
        "source_url": prop.get("sourceUrl") or prop.get("source_url") or url,
        "source_url_normalizada": normalize_property_url_for_dedup(prop.get("sourceUrl") or prop.get("source_url") or url),
    }

    raw_row = {
        "scraping_run_item_id": None,
        "inmobiliaria_id": inmobiliaria_id,
        "hash_dedup": hash_dedup,
        "titulo": titulo,
        "descripcion": truncate(prop.get("descripcion"), 500),
        "precio": price,
        "moneda": currency,
        "superficie_total": safe_float(prop.get("superficie_total")),
        "superficie_cubierta": safe_float(prop.get("superficie_cubierta")),
        "tipo_propiedad": tipo_propiedad.lower() if tipo_propiedad else None,
        "operacion": operation,
        "url": url,
        "url_normalizada": url_normalizada,
        "direccion_raw": direccion_raw,
        "barrio": barrio,
        "ciudad": ciudad,
        "provincia": provincia,
        "pais": truncate(prop.get("pais"), 80) or "Argentina",
        "latitud": safe_float(prop.get("latitud")),
        "longitud": safe_float(prop.get("longitud")),
        "imagenes": images,
        "datos_extra": datos_extra,
        "status": "raw",
    }
    return (None if hard_reject else raw_row), issues, hard_reject


def safe_float(value: Any) -> Optional[float]:
    try:
        return to_float(value)
    except Exception:
        return None


def query_existing_hashes(cur, hashes: List[str], table: str, extra_status_filter: str = "") -> set[str]:
    if not hashes:
        return set()
    found: set[str] = set()
    for start in range(0, len(hashes), 200):
        chunk = hashes[start:start + 200]
        placeholders = ", ".join(["%s"] * len(chunk))
        cur.execute(
            f"""
            SELECT hash_dedup
            FROM public.{table}
            WHERE hash_dedup IN ({placeholders})
            {extra_status_filter}
            """,
            chunk,
        )
        found.update(str(row["hash_dedup"]) for row in cur.fetchall())
    return found


def query_cross_agency_urls(cur, url_imm_pairs: List[Tuple[str, int]], table: str) -> set[str]:
    """Return url_normalizada values that exist in `table` with a DIFFERENT inmobiliaria_id.

    Used only for reporting / marking — never to block an import.
    A property published by multiple agencies is legitimate; this just flags it.
    """
    if not url_imm_pairs:
        return set()
    found: set[str] = set()
    for start in range(0, len(url_imm_pairs), 100):
        chunk = url_imm_pairs[start:start + 100]
        urls_only = list({pair[0] for pair in chunk})
        placeholders = ", ".join(["%s"] * len(urls_only))
        try:
            cur.execute(
                f"""
                SELECT DISTINCT url_normalizada, inmobiliaria_id
                FROM public.{table}
                WHERE url_normalizada IN ({placeholders})
                """,
                urls_only,
            )
            rows = cur.fetchall()
        except Exception:
            continue
        db_url_imm = {(str(r["url_normalizada"]), int(r["inmobiliaria_id"] or 0)) for r in rows}
        for url_n, our_imm_id in chunk:
            for db_url, db_imm in db_url_imm:
                if db_url == url_n and db_imm != our_imm_id:
                    found.add(url_n)
                    break
    return found


def detect_office_addresses(
    candidates: List[Tuple[Dict[str, Any], List[Dict[str, str]]]]
) -> Counter:
    """Fix global: detecta y nullifica direcciones de oficina repetidas dentro del batch.

    Una direccion se considera 'de oficina' cuando aparece en >50% de las props
    del mismo host dentro del batch, siempre que haya al menos 5 props del host.

    Reglas:
    - No bloquea el import.
    - Nullifica direccion_raw en todas las props afectadas.
    - Agrega warning 'office_address_suspected' con metadata en datos_extra.
    - No actua sobre props donde direccion_raw ya es None (ya invalida por otro check).
    - No actua si el host tiene <5 props en el batch (umbral poco confiable).
    - No actua si ninguna direccion supera el 50% de frecuencia.

    Retorna Counter con conteo de nuevos issues generados (para actualizar el contador global).
    """
    new_issues: Counter = Counter()

    # Agrupar candidatos por host de URL
    by_host: Dict[str, List[Tuple[Dict[str, Any], List[Dict[str, str]]]]] = defaultdict(list)
    for raw_row, row_issues in candidates:
        h = host_key(raw_row.get("url") or "")
        if h:
            by_host[h].append((raw_row, row_issues))

    for h, group in by_host.items():
        if len(group) < 5:
            # Umbral no confiable con menos de 5 props
            continue

        # Frecuencia de cada direccion no-nula en el grupo
        addr_counts: Counter = Counter()
        for raw_row, _ in group:
            addr = (raw_row.get("direccion_raw") or "").strip()
            if addr:
                addr_counts[addr] += 1

        total = len(group)
        for addr, count in addr_counts.items():
            ratio = count / total
            if ratio <= 0.5:
                continue

            # Direccion aparece en >50% del mismo host -> posible direccion de oficina
            for raw_row, row_issues in group:
                if (raw_row.get("direccion_raw") or "").strip() != addr:
                    continue
                # Registrar contexto en datos_extra antes de nullificar
                datos_extra = raw_row.get("datos_extra")
                if isinstance(datos_extra, dict):
                    datos_extra["original_address"] = addr
                    datos_extra["repeated_address_count"] = count
                    datos_extra["repeated_address_ratio"] = round(ratio, 3)
                    datos_extra["detection_scope"] = "same_domain_same_batch"
                raw_row["direccion_raw"] = None
                row_issues.append(issue(
                    "office_address_suspected",
                    f"addr={addr!r} count={count}/{total} ratio={ratio:.0%} host={h}",
                ))
                new_issues["office_address_suspected"] += 1

    return new_issues


def insert_raw_row(cur, row: Dict[str, Any]) -> Optional[int]:
    columns = ", ".join(RAW_COLUMNS)
    placeholders = ", ".join(["%s"] * len(RAW_COLUMNS))
    values = [json_value(row.get(column)) for column in RAW_COLUMNS]
    cur.execute(
        f"""
        INSERT INTO public.propiedades_raw ({columns})
        VALUES ({placeholders})
        ON CONFLICT (hash_dedup) DO NOTHING
        RETURNING id
        """,
        values,
    )
    inserted = cur.fetchone()
    return int(inserted["id"]) if inserted else None


def insert_issues(cur, raw_id: int, issues: List[Dict[str, str]]) -> None:
    for item in issues:
        cur.execute(
            """
            INSERT INTO public.data_quality_issues (raw_id, issue_type, issue_detail)
            VALUES (%s, %s, %s)
            """,
            [raw_id, item["issue_type"], item["issue_detail"]],
        )


def render_report(summary: Dict[str, Any]) -> str:
    issue_lines = "\n".join(f"- {key}: {value}" for key, value in sorted(summary["issues"].items())) or "- none: 0"
    missing_lines = "\n".join(f"- {key}: {value}" for key, value in sorted(summary["missing_fields"].items())) or "- none: 0"
    rejected_lines = "\n".join(f"- {key}: {value}" for key, value in sorted(summary["rejected_reasons"].items())) or "- none: 0"
    dup = summary["duplicates"]
    return f"""# Import captured props to Neon

Fecha: {summary['timestamp']}
Modo: {summary['mode']}
Destino: public.propiedades_raw

## Resumen

- archivos_leidos: {summary['files_read']}
- propiedades_detectadas: {summary['properties_detected']}
- offset: {summary['offset']}
- propiedades_procesadas: {summary['properties_processed']}
- importables: {summary['importable']}
- importadas: {summary['inserted']}
- con_warnings: {summary['with_warnings']}
- rechazadas: {summary['rejected']}
- accion_final: {summary['final_action']}

## Duplicados — detalle por categoría

Nota de negocio: solo se bloquean duplicados exactos de la misma fuente
(mismo inmobiliaria_id + misma URL). Las demás categorías son marcadores
informativos; no bloquean el import.

### Bloqueados (misma publicación exacta)
- duplicate_exact_same_source (dentro del batch): {dup.get('exact_same_source', 0)}
- skipped_duplicate_in_propiedades_raw: {dup.get('skipped_duplicate_in_raw', 0)}
- skipped_duplicate_in_propiedades_staging: {dup.get('skipped_duplicate_in_staging', 0)}

### Marcados — NO bloqueados (publicaciones legítimas)
- possible_cross_agency_duplicate_within_batch: {dup.get('possible_cross_agency_duplicate_within_batch', 0)}
- possible_cross_agency_duplicate_in_neon: {dup.get('possible_cross_agency_duplicate_in_neon', 0)}
- possible_same_address_within_batch: {dup.get('possible_same_address_within_batch', 0)}

### Totales en Neon (antes de este import)
- duplicate_in_propiedades_raw: {dup.get('duplicate_in_propiedades_raw', 0)}
- duplicate_in_propiedades_staging: {dup.get('duplicate_in_propiedades_staging', 0)}

## Campos faltantes principales

{missing_lines}

## Issues por tipo

{issue_lines}

## Rechazos

{rejected_lines}

## Seguridad

- no_toca_supabase: true
- no_publica_supabase: true
- no_toca_publish_queue: true
- no_modifica_env: true
- no_borra_datos: true
- no_commit_git: true
- no_push_git: true
- duplicados_cross_agency_NO_bloqueados: true
- duplicados_misma_direccion_NO_bloqueados: true
"""


def write_report(summary: Dict[str, Any], report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_report(summary), encoding="utf-8")


def update_master_progress(summary: Dict[str, Any], report_path: Path) -> None:
    master_path = REPORT_DIR / "master_progress.md"
    master_path.parent.mkdir(parents=True, exist_ok=True)
    entry = (
        f"\n\n## Import captured props {summary['timestamp']}\n\n"
        f"- Modo: {summary['mode']}\n"
        f"- Archivos leidos: {summary['files_read']}\n"
        f"- Propiedades detectadas: {summary['properties_detected']}\n"
        f"- Offset: {summary['offset']}\n"
        f"- Propiedades procesadas: {summary['properties_processed']}\n"
        f"- Importables: {summary['importable']}\n"
        f"- Importadas: {summary['inserted']}\n"
        f"- Rechazadas: {summary['rejected']}\n"
        f"- Duplicados bloqueados (misma fuente): {summary['duplicates'].get('skipped_duplicate_in_raw', 0) + summary['duplicates'].get('skipped_duplicate_in_staging', 0) + summary['duplicates'].get('exact_same_source', 0)}\n"
        f"- Marcados cross-agency (no bloqueados): {summary['duplicates'].get('possible_cross_agency_duplicate_in_neon', 0) + summary['duplicates'].get('possible_cross_agency_duplicate_within_batch', 0)}\n"
        f"- Destino: public.propiedades_raw\n"
        f"- Reporte: {safe_relative_path(report_path)}\n"
        f"- Confirmacion: no .env, no borrado, no commit, no push, no publicacion masiva Supabase, no pipeline commit, no cambios destructivos.\n"
    )
    try:
        if master_path.exists():
            current = master_path.read_text(encoding="utf-8", errors="ignore")
        else:
            current = "# Scraping autofix master progress\n"
        master_path.write_text(current.rstrip() + entry + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"warning: no pude actualizar master_progress.md: {exc}", file=sys.stderr)


def safe_relative_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except Exception:
        return str(path)


def print_summary(summary: Dict[str, Any], report_path: Path) -> None:
    print("=" * 72)
    print("IMPORT CAPTURED PROPS TO NEON")
    print(f"mode={summary['mode']}")
    print("target=public.propiedades_raw")
    print("supabase_write=false")
    print("-" * 72)
    print(f"archivos_leidos={summary['files_read']}")
    print(f"propiedades_detectadas={summary['properties_detected']}")
    print(f"offset={summary['offset']}")
    print(f"propiedades_procesadas={summary['properties_processed']}")
    print(f"importables={summary['importable']}")
    print(f"importadas={summary['inserted']}")
    print(f"con_warnings={summary['with_warnings']}")
    print(f"rechazadas={summary['rejected']}")
    dup = summary["duplicates"]
    print("duplicados_bloqueados:")
    print(f"  duplicate_exact_same_source_batch={dup.get('exact_same_source', 0)}")
    print(f"  skipped_duplicate_in_propiedades_raw={dup.get('skipped_duplicate_in_raw', 0)}")
    print(f"  skipped_duplicate_in_propiedades_staging={dup.get('skipped_duplicate_in_staging', 0)}")
    print("duplicados_marcados_no_bloqueados:")
    print(f"  possible_cross_agency_within_batch={dup.get('possible_cross_agency_duplicate_within_batch', 0)}")
    print(f"  possible_cross_agency_in_neon={dup.get('possible_cross_agency_duplicate_in_neon', 0)}")
    print(f"  possible_same_address_within_batch={dup.get('possible_same_address_within_batch', 0)}")
    print("campos_faltantes_principales:")
    if summary["missing_fields"]:
        for key, value in sorted(summary["missing_fields"].items()):
            print(f"  {key}: {value}")
    else:
        print("  none: 0")
    print("issues_por_tipo:")
    if summary["issues"]:
        for key, value in sorted(summary["issues"].items()):
            print(f"  {key}: {value}")
    else:
        print("  none: 0")
    print(f"accion_final={summary['final_action']}")
    print(f"report={report_path}")
    print("=" * 72)


def main() -> None:
    parser = argparse.ArgumentParser(description="Importar JSON capturados a Neon propiedades_raw")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR, help="Directorio con JSON capturados")
    parser.add_argument("--batch-csv", type=Path, default=None, help="CSV de tanda para resolver inmobiliaria_id real")
    parser.add_argument("--offset", type=int, default=0, help="Cantidad de propiedades iniciales a saltear")
    parser.add_argument("--limit", type=int, default=0, help="Maximo de propiedades a procesar; 0 procesa todas")
    parser.add_argument("--dry-run", action="store_true", help="Analizar y hacer rollback/no escribir")
    parser.add_argument("--commit", action="store_true", help="Persistir cambios en Neon")
    parser.add_argument("--report", type=Path, default=None, help="Ruta del reporte markdown")
    args = parser.parse_args()

    if args.dry_run and args.commit:
        raise SystemExit("Usar --dry-run o --commit, no ambos")
    if not args.dry_run and not args.commit:
        args.dry_run = True
    if args.offset < 0:
        raise SystemExit("--offset no puede ser negativo")
    if args.limit < 0:
        raise SystemExit("--limit no puede ser negativo")
    if not args.input_dir.exists():
        raise SystemExit(f"No existe input-dir: {args.input_dir}")

    mode = "commit" if args.commit else "dry-run"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    report_path = args.report or (REPORT_DIR / f"import_captured_{timestamp}.md")
    if not report_path.is_absolute():
        report_path = REPO_ROOT / report_path
    batch_csv = args.batch_csv or latest_batch_csv()
    if not batch_csv or not batch_csv.exists():
        raise SystemExit("No encontre batch_*.csv para resolver inmobiliaria_id real.")

    db_url = internal_db_config()
    batch_rows = load_batch_rows(batch_csv)
    exact_index, host_index = build_source_indexes(batch_rows)
    captured = load_captured_files(args.input_dir)

    candidates: List[Tuple[Dict[str, Any], List[Dict[str, str]]]] = []
    issues = Counter()
    missing_fields = Counter()
    rejected_reasons = Counter()
    files_read = len(captured)
    properties_detected = 0
    properties_processed = 0
    rejected = 0
    with_warnings = 0

    for path, payload in captured:
        props = payload.get("props")
        if not isinstance(props, list):
            rejected_reasons["invalid_file_structure"] += 1
            continue
        source_row = resolve_source_row(payload.get("url"), exact_index, host_index)
        if source_row is None:
            rejected_reasons["source_not_found_in_batch"] += len(props)
            rejected += len(props)
            properties_detected += len(props)
            continue
        for prop in props:
            if properties_detected < args.offset:
                properties_detected += 1
                continue
            if args.limit and properties_processed >= args.limit:
                break
            properties_detected += 1
            properties_processed += 1
            if not isinstance(prop, dict):
                rejected += 1
                rejected_reasons["invalid_prop_structure"] += 1
                continue
            raw_row, row_issues, hard_reject = build_raw_candidate(path, payload, prop, source_row)
            for item in row_issues:
                issues[item["issue_type"]] += 1
                if item["issue_type"].startswith("missing_"):
                    missing_fields[item["issue_type"]] += 1
            if hard_reject or raw_row is None:
                rejected += 1
                if row_issues:
                    rejected_reasons[row_issues[0]["issue_type"]] += 1
                else:
                    rejected_reasons["unknown"] += 1
                continue
            if row_issues:
                with_warnings += 1
            candidates.append((raw_row, row_issues))
        if args.limit and properties_processed >= args.limit:
            break

    # Fix global: nullificar direcciones de oficina repetidas dentro del batch
    office_new_issues = detect_office_addresses(candidates)
    issues.update(office_new_issues)

    hashes = [row["hash_dedup"] for row, _ in candidates]
    duplicate_counts = Counter()
    inserted = 0
    unique_candidates: List[Tuple[Dict[str, Any], List[Dict[str, str]]]] = []
    seen_hashes: set[str] = set()
    # Within-batch: track URLs and addresses independently of hash to detect
    # cross-agency same-URL and same-address cases (marking only, never blocking).
    seen_urls_by_imm: Dict[str, int] = {}   # url_normalizada → first inmobiliaria_id seen
    seen_addrs: set[str] = set()             # normalized address key

    for raw_row, row_issues in candidates:
        hash_dedup = raw_row["hash_dedup"]
        if hash_dedup in seen_hashes:
            # Exact same publication (same source + same URL) in this batch — skip.
            duplicate_counts["exact_same_source"] += 1
            issues["duplicate_exact_same_source"] += 1
            continue
        seen_hashes.add(hash_dedup)

        url_n = raw_row.get("url_normalizada") or ""
        our_imm = int(raw_row.get("inmobiliaria_id") or 0)

        if url_n:
            first_imm = seen_urls_by_imm.get(url_n)
            if first_imm is None:
                seen_urls_by_imm[url_n] = our_imm
            elif first_imm != our_imm:
                # Same URL, different agency within this batch — mark, do NOT block.
                raw_row["datos_extra"]["possible_cross_agency_duplicate_within_batch"] = True
                issues["possible_cross_agency_duplicate_within_batch"] += 1

        addr_key = "|".join(filter(None, [
            (raw_row.get("direccion_raw") or "").lower().strip()[:80],
            (raw_row.get("ciudad") or "").lower().strip(),
            (raw_row.get("provincia") or "").lower().strip(),
        ]))
        if addr_key and len(addr_key) > 5:
            if addr_key in seen_addrs:
                # Same address in this batch — mark, do NOT block.
                raw_row["datos_extra"]["possible_same_address_within_batch"] = True
                issues["possible_same_address_within_batch"] += 1
            else:
                seen_addrs.add(addr_key)

        unique_candidates.append((raw_row, row_issues))

    # Flush within-batch marked counts into duplicate_counts for consistent reporting.
    duplicate_counts["possible_cross_agency_duplicate_within_batch"] = issues["possible_cross_agency_duplicate_within_batch"]
    duplicate_counts["possible_same_address_within_batch"] = issues["possible_same_address_within_batch"]

    with connect_internal_db(db_url) as conn:
        with conn.cursor() as cur:
            raw_duplicates = query_existing_hashes(cur, hashes, "propiedades_raw")
            staging_duplicates = query_existing_hashes(
                cur,
                hashes,
                "propiedades_staging",
                "AND status != 'rejected'",
            )
            duplicate_counts["duplicate_in_propiedades_raw"] = len(raw_duplicates)
            duplicate_counts["duplicate_in_propiedades_staging"] = len(staging_duplicates - raw_duplicates)
            duplicate_hashes = raw_duplicates | staging_duplicates

            # Cross-agency URL check: same URL in Neon with a different inmobiliaria_id.
            # This marks, but never blocks import — cross-agency is a legitimate business case.
            url_imm_pairs = [
                (row["url_normalizada"], int(row["inmobiliaria_id"] or 0))
                for row, _ in unique_candidates
                if row.get("url_normalizada") and row.get("inmobiliaria_id")
            ]
            cross_agency_urls_raw = query_cross_agency_urls(cur, url_imm_pairs, "propiedades_raw")
            cross_agency_urls_staging = query_cross_agency_urls(cur, url_imm_pairs, "propiedades_staging")
            cross_agency_urls = cross_agency_urls_raw | cross_agency_urls_staging
            duplicate_counts["possible_cross_agency_duplicate_in_neon"] = len(cross_agency_urls)

            importable_candidates = []
            for raw_row, row_issues in unique_candidates:
                if raw_row["hash_dedup"] in raw_duplicates:
                    issues["duplicate_in_propiedades_raw"] += 1
                    duplicate_counts["skipped_duplicate_in_raw"] += 1
                    continue
                if raw_row["hash_dedup"] in staging_duplicates:
                    issues["duplicate_in_propiedades_staging"] += 1
                    duplicate_counts["skipped_duplicate_in_staging"] += 1
                    continue
                url_n = raw_row.get("url_normalizada") or ""
                if url_n in cross_agency_urls:
                    # Same URL found in Neon under a different agency — mark, do NOT skip.
                    raw_row["datos_extra"]["possible_cross_agency_duplicate_in_neon"] = True
                    issues["possible_cross_agency_duplicate_in_neon"] += 1
                importable_candidates.append((raw_row, row_issues))

            if args.commit:
                for raw_row, row_issues in importable_candidates:
                    cur.execute("SAVEPOINT import_captured_raw_row")
                    try:
                        raw_id = insert_raw_row(cur, raw_row)
                        if raw_id is None:
                            duplicate_counts["conflict_on_insert"] += 1
                            cur.execute("RELEASE SAVEPOINT import_captured_raw_row")
                            continue
                        insert_issues(cur, raw_id, row_issues)
                        inserted += 1
                        cur.execute("RELEASE SAVEPOINT import_captured_raw_row")
                    except Exception as exc:
                        cur.execute("ROLLBACK TO SAVEPOINT import_captured_raw_row")
                        cur.execute("RELEASE SAVEPOINT import_captured_raw_row")
                        issues["processing_error"] += 1
                        rejected_reasons[f"processing_error: {str(exc)[:120]}"] += 1
                conn.commit()
                final_action = "commit"
            else:
                conn.rollback()
                final_action = "dry-run/no-writes"

    summary = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "mode": mode,
        "files_read": files_read,
        "properties_detected": properties_detected,
        "properties_processed": properties_processed,
        "offset": args.offset,
        "importable": len(importable_candidates),
        "inserted": inserted,
        "with_warnings": with_warnings,
        "rejected": rejected,
        "duplicates": duplicate_counts,
        "issues": issues,
        "missing_fields": missing_fields,
        "rejected_reasons": rejected_reasons,
        "final_action": final_action,
    }
    write_report(summary, report_path)
    update_master_progress(summary, report_path)
    print_summary(summary, report_path)


if __name__ == "__main__":
    main()
