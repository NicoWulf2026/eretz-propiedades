# Dependencias nuevas: pip install playwright beautifulsoup4 requests python-dotenv
# playwright install chromium
"""
scraper_propiedades.py
======================
Scraper de propiedades para inmobiliarias argentinas.
Estrategias (orden de prioridad):
  1. Tokko Broker API
  2. Network Interception (Playwright)
  3. JSON-LD schema
  4. Sitemap crawler
  5. HTML scraper con Playwright (fallback)
  6. ScraperAPI (bypass de bloqueos, auto-activado)
  7. AI Extractor / Groq (último recurso)
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import math
import os
import queue
import random
import re
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
load_dotenv()

# Silenciar warnings de SSL (muchos sitios argentinos tienen certs vencidos/mal configurados)
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
SUPABASE_URL: str = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY: str = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "") or os.environ.get("SUPABASE_KEY", "")

TOKKO_API_BASE = "https://api.tokkobroker.com/api/v1/property/"
TOKKO_LIMIT    = 100
TOKKO_DETAIL_IMAGE_MAX_WORKERS = 10
TOKKO_DETAIL_IMAGE_TIMEOUT = 6
TOKKO_FAKE_IMAGE_EXAMPLES_LIMIT = 8
TOKKO_REAL_IMAGE_EXAMPLES_LIMIT = 8

SCRAPERAPI_KEY: str = os.environ.get("SCRAPERAPI_KEY", "")
GROQ_API_KEY: str   = os.environ.get("GROQ_API_KEY", "")
GROQ_URL            = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL          = "llama-3.1-8b-instant"

USER_AGENTS: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
]

CONTROL_ITEM_TIMEOUT_SECONDS = 180
SIMPLE_ITEM_TIMEOUT_SECONDS = 90
CUSTOM_OR_SITEMAP_ITEM_TIMEOUT_SECONDS = 240
PLAYWRIGHT_ITEM_TIMEOUT_SECONDS = 300
STRATEGY_TIMEOUT_SECONDS: Dict[str, int] = {
    "tokko_api": 45,
    "tokko_html": 150,
    "wordpress_html": 35,
    "network_intercept": 30,
    "static_html": 35,
    "static_html_detail": 45,
    "static_html_tokko_detail": 45,
    "wordpress_sitemap_detail": 90,
    "wordpress_essential_real_estate_detail": 75,
    "wordpress_estatik_detail": 75,
    "wordpress_realhomes_detail": 75,
    "wordpress_generic_detail": 65,
    "custom_listing_detail": 75,
    "json_ld": 20,
    "sitemap": 20,
    "html_scraper": 45,
    "playwright_html": 45,
}
PLAYWRIGHT_LAUNCH_TIMEOUT_MS = 15000
PLAYWRIGHT_NAV_TIMEOUT_MS = 12000
PLAYWRIGHT_LOAD_TIMEOUT_MS = 8000
PLAYWRIGHT_ACTION_TIMEOUT_MS = 2500
PLAYWRIGHT_CLOSE_TIMEOUT_SECONDS = 3.0

FALSE_IMAGE_PATTERNS = (
    "static.tokkobroker.com/tfw/img/prop-icons",
    "/tfw/img/prop-icons",
    "/tfw_images/",
    "tfw_images",
    "/prop-icons/",
    "prop-icons",
    "supcubierta",
    "suptotalconst",
    "supterreno",
    "amenit",
    "surface",
    "superficie",
    "placeholder",
    "no-photo",
    "no_photo",
    "no-image",
    "no_image",
    "sin-imagen",
    "sin_imagen",
    "logo",
    "isotipo",
    "imagotipo",
    "brand",
    "favicon",
    "/web-images/",
    "/users/",
    "_thumbnail",
    "pinterest.com",
    "pin/create",
    "marker",
    "mapa",
    "map",
    "tour",
    "virtual",
    "removebg",
    "facebook.com/tr",
    "connect.facebook.net",
    "googletagmanager.com",
    "google-analytics.com",
    "doubleclick.net",
    "/collect",
    "/pixel",
    "tracking",
)

PROTECTED_UPDATE_FIELDS = {
    "latitud",
    "longitud",
    "imagenes",
    "precio",
    "moneda",
    "precio_usd",
    "precio_ars",
    "superficie_total",
    "superficie_cubierta",
    "superficie_terreno",
    "dormitorios",
    "banos",
    "ambientes",
    "direccion",
    "barrio",
    "ciudad",
    "provincia",
    "inmobiliaria_id",
}
PROTECTED_POSITIVE_NUMBER_FIELDS = {
    "precio",
    "precio_usd",
    "precio_ars",
    "superficie_total",
    "superficie_cubierta",
    "superficie_terreno",
    "dormitorios",
    "banos",
    "ambientes",
}
PROTECTED_TEXT_FIELDS = {"moneda", "direccion", "barrio", "ciudad", "provincia"}
COORDINATE_FIELDS = {"latitud", "longitud"}
MAX_VALID_PRICE_USD = 100_000_000
MAX_VALID_PRICE_ARS = 1_000_000_000_000
MIN_VALID_PUBLIC_PRICE = 1
PROPERTY_INTEGER_RANGES: Dict[str, Tuple[int, int]] = {
    "ambientes": (0, 30),
    "dormitorios": (0, 30),
    "banos": (0, 20),
    "toilettes": (0, 20),
    "cocheras": (0, 50),
    "antiguedad": (0, 300),
    "piso": (0, 200),
}

CITY_COORDINATE_BOUNDS: Dict[str, Tuple[float, float, float, float]] = {
    "rosario": (-33.10, -32.80, -60.85, -60.50),
    "potrero de los funes": (-33.30, -33.15, -66.35, -66.15),
    "potrero de garay": (-31.90, -31.70, -64.65, -64.40),
    "funes": (-33.00, -32.85, -60.95, -60.70),
    "roldan": (-33.00, -32.80, -61.00, -60.80),
    "cordoba": (-31.55, -31.25, -64.35, -64.05),
    "santa fe": (-31.80, -31.45, -60.90, -60.45),
    "san jose del rincon": (-31.70, -31.50, -60.65, -60.45),
}
URUGUAY_COORDINATE_BOUNDS = (-35.20, -30.00, -58.80, -53.00)

def _make_http_session() -> requests.Session:
    s = requests.Session()
    s.trust_env = False
    retry = Retry(total=0, connect=0, read=0, status=0, backoff_factor=0, status_forcelist=[429, 500, 502, 503, 504],
                  allowed_methods=["GET"])
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


PROPERTY_URL_PATTERNS = re.compile(
    r"/(propiedad|property|inmueble|listing|ficha|imovel|prop|detalle)[s]?[/_-]",
    re.IGNORECASE,
)

TIPO_MAP: Dict[str, str] = {
    # Casas
    "casa": "casa", "chalet": "casa", "house": "casa", "duplex": "casa",
    "dúplex": "casa", "townhouse": "casa", "villa": "casa",
    # Departamentos
    "departamento": "departamento", "depto": "departamento",
    "apartment": "departamento", "flat": "departamento", "dpto": "departamento",
    "monoambiente": "departamento", "studio": "departamento",
    # PH
    "ph ": "ph", "p.h": "ph", "penthouse": "ph",
    # Locales
    "local": "local", "comercial": "local", "negocio": "local",
    "fondo de comercio": "local", "galería": "local",
    # Oficinas
    "oficina": "oficina", "office": "oficina", "consultorio": "consultorio",
    # Terrenos
    "terreno": "terreno", "lote": "terreno", "land": "terreno",
    "parcela": "terreno", "fracción": "terreno",
    # Campos
    "campo": "campo", "chacra": "campo", "estancia": "campo",
    "finca": "campo", "quinta": "campo", "establecimiento": "campo",
    # Cocheras
    "cochera": "cochera", "garage": "cochera", "garaje": "cochera",
    "estacionamiento": "cochera",
    # Galpones / depósitos
    "galpon": "galpon", "galpón": "galpon", "nave industrial": "galpon",
    "depósito": "deposito", "deposito": "deposito", "bodega": "deposito",
    "almacén": "deposito",
    # Hoteles
    "hotel": "hotel", "apart hotel": "hotel", "hostería": "hotel",
}

OPERACION_MAP: Dict[str, str] = {
    "venta": "venta", "sale": "venta", "sell": "venta", "compra": "venta",
    "en venta": "venta", "for sale": "venta",
    "alquiler": "alquiler", "alq ": "alquiler", "rent": "alquiler",
    "rental": "alquiler", "arrendamiento": "alquiler", "locación": "alquiler",
    "en alquiler": "alquiler", "for rent": "alquiler",
    "temporario": "alquiler_temporario", "temporal": "alquiler_temporario",
    "vacation": "alquiler_temporario", "turístico": "alquiler_temporario",
    "temporaria": "alquiler_temporario", "por día": "alquiler_temporario",
    "por semana": "alquiler_temporario", "short term": "alquiler_temporario",
}

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Tipo de cambio (dólar blue, API gratuita argentina)
# ---------------------------------------------------------------------------

_tc_cache: Dict[str, Any] = {"valor": None, "ts": 0.0}

def get_tipo_cambio() -> float:
    """Retorna USD→ARS (dólar blue venta). Cachea 1 hora. Fallback: 1200."""
    ahora = time.time()
    if _tc_cache["valor"] and ahora - _tc_cache["ts"] < 3600:
        return _tc_cache["valor"]
    try:
        r = requests.get("https://dolarapi.com/v1/dolares/blue", timeout=3, verify=False)
        tc = float(r.json().get("venta", 0))
        if tc > 0:
            _tc_cache["valor"] = tc
            _tc_cache["ts"] = ahora
            logger.info("Tipo de cambio blue: $%.0f ARS/USD", tc)
            return tc
    except Exception:
        pass
    _tc_cache["valor"] = _tc_cache["valor"] or 1200.0
    _tc_cache["ts"] = ahora
    return _tc_cache["valor"]

def convertir_precio(precio: Optional[float], moneda: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Devuelve (precio_ars, precio_usd) según la moneda original.
    Siempre completa ambos usando el tipo de cambio blue.
    """
    if precio is None:
        return None, None
    tc = get_tipo_cambio()
    if moneda == "USD":
        return round(precio * tc, 0), precio
    elif moneda == "ARS":
        return precio, round(precio / tc, 2) if tc else None
    return precio, None

# ---------------------------------------------------------------------------
# Normalización
# ---------------------------------------------------------------------------

def normalizar_precio(raw: Any) -> Tuple[Optional[float], str]:
    """Detecta moneda y retorna (float|None, currency_code)."""
    if raw is None:
        return None, "ARS"
    text = str(raw).strip()
    # Detectar moneda
    moneda = "ARS"
    if re.search(r"U\$S|USD|US\$|u\$s|dólar|dollar", text, re.IGNORECASE):
        moneda = "USD"
    elif re.search(r"€|EUR", text, re.IGNORECASE):
        moneda = "EUR"
    elif re.search(r"UYU|\$U", text, re.IGNORECASE):
        moneda = "UYU"
    # Extraer número
    digits = re.sub(r"[^\d.,]", "", text)
    if not digits:
        return None, moneda
    # Formato con punto de miles y coma decimal: 1.500.000 / 1.500,50
    if "." in digits and "," in digits:
        if digits.rindex(".") > digits.rindex(","):
            # 1,500.00  →  punto decimal
            digits = digits.replace(",", "")
        else:
            # 1.500,00  →  coma decimal
            digits = digits.replace(".", "").replace(",", ".")
    elif "," in digits:
        # Si hay coma y no punto, podría ser decimal europeo o miles
        parts = digits.split(",")
        if len(parts) == 2 and len(parts[1]) <= 2:
            digits = digits.replace(",", ".")  # decimal
        else:
            digits = digits.replace(",", "")   # separador de miles
    else:
        if "." in digits:
            parts = digits.split(".")
            if digits.count(".") > 1 or (len(parts) == 2 and len(parts[1]) == 3):
                digits = digits.replace(".", "")
    try:
        return float(digits), moneda
    except ValueError:
        return None, moneda


def normalizar_tipo(raw: Any) -> str:
    if not raw:
        return "otro"
    text = str(raw).lower().strip()
    for key, val in TIPO_MAP.items():
        if key in text:
            return val
    return "otro"


def normalizar_operacion(raw: Any) -> str:
    if not raw:
        return "venta"
    text = str(raw).lower().strip()
    for key, val in OPERACION_MAP.items():
        if key in text:
            return val
    return "venta"


def normalizar_superficie(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    text = str(raw)
    m = re.search(r"[\d]+[.,]?[\d]*", text.replace(",", "."))
    if not m:
        return None
    try:
        return float(m.group().replace(",", "."))
    except ValueError:
        return None


def normalizar_int(raw: Any) -> Optional[int]:
    if raw is None:
        return None
    text = re.sub(r"[^\d]", "", str(raw))
    return int(text) if text else None


_DESC_NOISE = re.compile(
    r"(compartí|comparte|seguinos|síguenos|instagram|facebook|whatsapp|"
    r"twitter|linkedin|youtube|tel[eé]fono\s*:?\s*[\d\s\-\+]+|"
    r"copyright|todos los derechos|aviso legal|política de privacidad|"
    r"cookies|newsletter|suscrib[ií]|registr[aá]te|inicia sesión)",
    re.IGNORECASE,
)

def limpiar_descripcion(texto: Optional[str]) -> Optional[str]:
    """Elimina ruido de redes sociales, teléfonos y boilerplate de la descripción."""
    if not texto:
        return None
    lines = []
    for line in texto.splitlines():
        line = line.strip()
        if not line or _DESC_NOISE.search(line):
            continue
        lines.append(line)
    result = " ".join(lines).strip()
    return result if len(result) >= 20 else None


def calcular_score(prop: Dict) -> int:
    """Calcula score de calidad 0-100 localmente antes de guardar."""
    score = 0
    if prop.get("titulo"):         score += 10
    if prop.get("descripcion"):    score += 10
    if prop.get("precio"):         score += 15
    if prop.get("tipo_propiedad") and prop["tipo_propiedad"] != "otro": score += 10
    if prop.get("operacion"):      score += 10
    if prop.get("ciudad"):         score += 10
    if prop.get("direccion"):      score += 10
    if prop.get("superficie_cubierta"): score += 5
    if prop.get("dormitorios"):    score += 5
    imgs = prop.get("imagenes")
    if imgs and len(imgs) > 0:     score += 10
    if prop.get("latitud"):        score += 5
    return min(score, 100)


# ---------------------------------------------------------------------------
# Deduplicación
# ---------------------------------------------------------------------------

_DEDUP_TRACKING_QUERY_PARAMS = {
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


def normalize_property_url_for_dedup(url: Any) -> str:
    """URL canonica para identidad de propiedad."""
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
        if not key_clean or key_clean in _DEDUP_TRACKING_QUERY_PARAMS or key_clean.startswith("utm_"):
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


def hash_propiedad(inmob_id: Any, id_externo: Any, url: Any) -> str:
    url_key = normalize_property_url_for_dedup(url)
    id_key = normalize_external_id_for_dedup(id_externo)
    if url_key:
        key = f"{inmob_id}|url|{url_key}"
    elif id_key:
        key = f"{inmob_id}|id_externo|{id_key}"
    else:
        key = f"{inmob_id}|sin_identidad|"
    return hashlib.sha256(key.encode()).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

class StrategyTimeoutError(TimeoutError):
    """Timeout controlado de item o estrategia."""


class ItemTimeoutError(StrategyTimeoutError):
    """Timeout duro del item completo."""


class SavePropertiesError(RuntimeError):
    """Error controlado cuando Supabase rechaza el guardado de propiedades."""

    def __init__(self, message: str, errors: Optional[List[Dict[str, Any]]] = None) -> None:
        super().__init__(message)
        self.errors = errors or []


def clasificar_error(e: Exception) -> str:
    msg = str(e).lower()
    if "data_integrity_mismatch" in msg:
        return "data_integrity_mismatch"
    if "canonical_id_resolution_failed" in msg:
        return "canonical_id_resolution_failed"
    if "canonical_id_mismatch" in msg:
        return "canonical_id_mismatch"
    if "final_url_domain_mismatch" in msg:
        return "final_url_domain_mismatch"
    if "item_timeout" in msg or isinstance(e, ItemTimeoutError):
        return "item_timeout"
    if "save_failed" in msg or isinstance(e, SavePropertiesError):
        return "save_failed"
    if "site_down" in msg or "dominio_caido" in msg:
        return "site_down"
    if "requires_network_interception" in msg or "network_interception_requerida" in msg:
        return "requires_network_interception"
    if "requires_playwright" in msg or "playwright_requerido" in msg:
        return "requires_playwright"
    if "no_property_links" in msg or "sin_links_propiedad" in msg:
        return "no_property_links"
    if "unsupported_cms" in msg:
        return "unsupported_cms"
    if "empty_site" in msg or "sitio_vacio" in msg:
        return "empty_site"
    if "blocked" in msg or "captcha" in msg or "403" in msg or "429" in msg:
        return "blocked"
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    if "ssl" in msg or "certificate" in msg:
        return "ssl_error"
    if "sin_propiedades" in msg or "no properties" in msg:
        return "sin_propiedades"
    if "parse" in msg or "json" in msg or "beautifulsoup" in msg:
        return "parse_error"
    if "navigation" in msg or "net::" in msg or "connection" in msg:
        return "nav_error"
    return "error_desconocido"


def _deadline_remaining_seconds(deadline: Optional[float]) -> float:
    if deadline is None:
        return float("inf")
    return max(deadline - time.time(), 0.0)


def _check_deadline(deadline: Optional[float], label: str) -> None:
    if deadline is not None and time.time() >= deadline:
        if label == "item":
            raise ItemTimeoutError("item_timeout: Tiempo mÃ¡ximo por inmobiliaria excedido")
        raise StrategyTimeoutError(f"timeout_{label}: excedio el limite configurado")


def _strategy_deadline(inmob: Dict) -> Optional[float]:
    deadline = inmob.get("_strategy_deadline")
    return float(deadline) if deadline else None


def _check_strategy_deadline(inmob: Dict, label: Optional[str] = None) -> None:
    _check_deadline(_strategy_deadline(inmob), label or str(inmob.get("_strategy_name") or "strategy"))


def _bounded_http_timeout(inmob: Dict, requested: int) -> float:
    deadline = _strategy_deadline(inmob)
    _check_deadline(deadline, str(inmob.get("_strategy_name") or "strategy"))
    remaining = _deadline_remaining_seconds(deadline)
    if remaining == float("inf"):
        return requested
    return max(1.0, min(float(requested), remaining))


def _bounded_playwright_timeout_ms(inmob: Dict, requested_ms: int) -> int:
    deadline = _strategy_deadline(inmob)
    _check_deadline(deadline, str(inmob.get("_strategy_name") or "strategy"))
    remaining_ms = int(_deadline_remaining_seconds(deadline) * 1000)
    if remaining_ms <= 0:
        raise StrategyTimeoutError(f"timeout_{inmob.get('_strategy_name') or 'strategy'}: sin tiempo disponible")
    return max(500, min(requested_ms, remaining_ms))


def _run_strategy_with_deadline(
    strategy_name: str,
    inmob: Dict,
    item_deadline: Optional[float],
    func: Callable[[], List[Dict]],
) -> List[Dict]:
    strategy_seconds = STRATEGY_TIMEOUT_SECONDS.get(strategy_name, 45)
    now = time.time()
    strategy_deadline = now + strategy_seconds
    if item_deadline is not None:
        strategy_deadline = min(strategy_deadline, item_deadline)
    if strategy_deadline <= now:
        raise StrategyTimeoutError(f"timeout_{strategy_name}: item sin tiempo disponible")

    previous_deadline = inmob.get("_strategy_deadline")
    previous_name = inmob.get("_strategy_name")
    inmob["_strategy_deadline"] = strategy_deadline
    inmob["_strategy_name"] = strategy_name
    try:
        result = func()
        if not result:
            _check_deadline(strategy_deadline, strategy_name)
        return result
    finally:
        if previous_deadline is None:
            inmob.pop("_strategy_deadline", None)
        else:
            inmob["_strategy_deadline"] = previous_deadline
        if previous_name is None:
            inmob.pop("_strategy_name", None)
        else:
            inmob["_strategy_name"] = previous_name


def _update_strategy_progress(inmob: Dict, strategy_name: str, **kwargs: Any) -> None:
    """Deja progreso consultable si una estrategia corta por timeout."""
    metadata = inmob.setdefault("_scraper_metadata", {})
    progress = metadata.setdefault("strategy_progress", {})
    current = dict(progress.get(strategy_name) or {})
    current.update(kwargs)
    current["strategy"] = strategy_name
    current["updated_at"] = datetime.now(timezone.utc).isoformat()
    progress[strategy_name] = current
    metadata["estrategia_actual"] = strategy_name


def _close_playwright_safely(resource: Any, label: str, timeout: float = PLAYWRIGHT_CLOSE_TIMEOUT_SECONDS) -> bool:
    if resource is None:
        return True
    close_fn = getattr(resource, "close", None) or getattr(resource, "stop", None)
    if not callable(close_fn):
        return True

    try:
        close_fn()
        return True
    except BaseException as exc:
        logger.debug("%s close error: %s", label, exc)
        return False


def _normalize_text_key(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value).lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\b(s[\s.]?r[\s.]?l|s[\s.]?a[\s.]?s|s[\s.]?a)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    stop_words = {
        "inmobiliaria", "inmobiliarias", "propiedad", "propiedades",
        "negocios", "gestion", "real", "estate", "sa", "srl",
        "sas", "ci", "mat", "y", "de", "del", "la", "el",
    }
    return " ".join(part for part in text.split() if part not in stop_words)


def _normalize_web_key(value: Any) -> str:
    if not value:
        return ""
    raw = str(value).strip().lower()
    if not raw:
        return ""
    if not re.match(r"^https?://", raw):
        raw = f"http://{raw.lstrip('/')}"
    try:
        parsed = urlparse(raw)
        host = (parsed.netloc or parsed.path.split("/")[0]).split("@")[-1]
        host = host.split(":")[0].strip().lower()
        if host.startswith("www."):
            host = host[4:]
        return host.rstrip("/")
    except Exception:
        raw = re.sub(r"^https?://", "", raw)
        raw = raw.split("/")[0].split(":")[0]
        return raw[4:] if raw.startswith("www.") else raw


def _same_location(candidate: Dict, ciudad: Any, provincia: Any) -> bool:
    ciudad_key = _normalize_text_key(ciudad)
    provincia_key = _normalize_text_key(provincia)
    cand_ciudad = _normalize_text_key(candidate.get("ciudad"))
    cand_provincia = _normalize_text_key(candidate.get("provincia"))
    city_ok = not ciudad_key or not cand_ciudad or ciudad_key == cand_ciudad
    province_ok = not provincia_key or not cand_provincia or provincia_key == cand_provincia
    return city_ok and province_ok


# ---------------------------------------------------------------------------
# ID integrity helpers
# ---------------------------------------------------------------------------

# ID spaces are intentionally explicit:
# - inmobiliarias_main.id is the canonical agency ID used by propiedades.inmobiliaria_id.
# - inmobiliarias_scraping.id is an operational/source/enrichment ID only.
# - scraping_run_items can contain historical data from either space, so each item
#   must be resolved to inmobiliarias_main.id before properties are saved.

def _agency_item_name(item: Dict[str, Any]) -> str:
    return str(item.get("inmobiliaria_nombre") or item.get("nombre") or "").strip()


def _agency_row_name(row: Optional[Dict[str, Any]]) -> str:
    if not row:
        return ""
    return str(row.get("nombre") or row.get("nombre_limpio") or row.get("nombre_normalizado") or "").strip()


def _unique_domains(*urls: Any) -> List[str]:
    domains: List[str] = []
    for url in urls:
        key = _normalize_web_key(url)
        if key and key not in domains:
            domains.append(key)
    return domains


def _agency_name_compatible(left: Any, right: Any) -> bool:
    left_key = _normalize_text_key(left)
    right_key = _normalize_text_key(right)
    if not left_key or not right_key:
        return True
    if left_key == right_key:
        return True
    left_tokens = set(left_key.split())
    right_tokens = set(right_key.split())
    if not left_tokens or not right_tokens:
        return True
    overlap = left_tokens & right_tokens
    if not overlap:
        return False
    shortest = min(len(left_tokens), len(right_tokens))
    return len(overlap) / max(shortest, 1) >= 0.75


def _agency_row_item_validation(row: Optional[Dict[str, Any]], item: Dict[str, Any]) -> Dict[str, Any]:
    row_name = _agency_row_name(row)
    item_name = _agency_item_name(item)
    row_domains = _unique_domains(
        row.get("web") if row else None,
        row.get("url_listado") if row else None,
    )
    item_domains = _unique_domains(item.get("web"), item.get("url_listado"))
    matching_domains = sorted(set(row_domains) & set(item_domains))
    domain_ok = True
    if row_domains and item_domains:
        domain_ok = bool(matching_domains)
    name_ok = _agency_name_compatible(item_name, row_name)
    return {
        "matches": bool(row and domain_ok and name_ok),
        "name_ok": name_ok,
        "domain_ok": domain_ok,
        "matching_domains": matching_domains,
        "item_name": item_name,
        "row_name": row_name,
        "item_domains": item_domains,
        "row_domains": row_domains,
    }


def _final_url_domain_validation(
    final_url: Optional[str],
    item: Dict[str, Any],
    canonical_resolution: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    final_domain = _normalize_web_key(final_url)
    source_domains = _unique_domains(item.get("web"), item.get("url_listado"))
    main_row = (canonical_resolution or {}).get("main_row") or {}
    source_domains.extend(domain for domain in _unique_domains(main_row.get("web"), main_row.get("url_listado")) if domain not in source_domains)
    if not final_domain:
        return {"valid": True, "reason": "sin_final_url", "final_domain": "", "source_domains": source_domains}
    if not source_domains:
        return {"valid": True, "reason": "sin_dominios_fuente", "final_domain": final_domain, "source_domains": source_domains}
    return {
        "valid": final_domain in source_domains,
        "reason": "domain_match" if final_domain in source_domains else "domain_mismatch",
        "final_domain": final_domain,
        "source_domains": source_domains,
    }


def _effective_final_url(url_usada: Optional[str], strategy_meta: Optional[Dict[str, Any]]) -> Optional[str]:
    metadata = strategy_meta or {}
    diagnostico = metadata.get("diagnostico_inicial") if isinstance(metadata.get("diagnostico_inicial"), dict) else {}
    for candidate in (
        metadata.get("final_url"),
        metadata.get("url_final"),
        diagnostico.get("final_url") if diagnostico else None,
        url_usada,
    ):
        if candidate:
            return str(candidate)
    return None


# ---------------------------------------------------------------------------
# Supabase client
# ---------------------------------------------------------------------------

class SupabasePropiedades:
    """Cliente Supabase orientado a las tablas propiedades y scraping_jobs."""

    _CHUNK = 50
    _PROPERTY_COLUMNS = {
        "id",
        "inmobiliaria_id",
        "url",
        "url_normalizada",
        "id_externo",
        "hash_dedup",
        "titulo",
        "descripcion",
        "precio",
        "moneda",
        "precio_usd",
        "expensas",
        "expensas_moneda",
        "tipo_propiedad",
        "operacion",
        "ambientes",
        "dormitorios",
        "banos",
        "toilettes",
        "cocheras",
        "antiguedad",
        "piso",
        "superficie_total",
        "superficie_cubierta",
        "superficie_terreno",
        "direccion",
        "barrio",
        "ciudad",
        "provincia",
        "pais",
        "latitud",
        "longitud",
        "imagenes",
        "video_url",
        "plano_url",
        "amenities",
        "agente_nombre",
        "agente_telefono",
        "fuente_extraccion",
        "cms_origen",
        "fecha_publicacion",
        "estado",
        "created_at",
        "updated_at",
        "precio_ars",
        "apto_credito",
    }
    _OPTIONAL_PROPERTY_COLUMNS = {"calidad_score"}
    _property_columns_cache: Optional[set] = None
    _SCRAPING_AGENCY_COLUMNS = {"id", "nombre", "web", "ciudad", "provincia"}
    _OPTIONAL_SCRAPING_AGENCY_COLUMNS = {"pais", "fuente", "estado_scraping"}
    _scraping_agency_columns_cache: Optional[set] = None

    def __init__(self) -> None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError("SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY son requeridas en .env")
        self.session = self._make_session()
        self.last_save_protection_stats = _new_update_protection_stats()
        self.last_save_result = {"inserted": 0, "updated": 0, "unchanged": 0, "failed": 0, "errors": []}
        self._headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=representation",
        }
        self._headers_minimal = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        self._headers_rpc = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    @staticmethod
    def _make_session() -> requests.Session:
        s = requests.Session()
        s.trust_env = False
        retry = Retry(
            total=0,
            connect=0,
            read=0,
            status=0,
            backoff_factor=0,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PATCH"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        return s

    # ------ Agencies ------

    def load_agencies(self, cms_filter: Optional[str] = None, solo_con_tokko: bool = False) -> List[Dict]:
        params: Dict[str, Any] = {
            "select": "*",
            "limit": 2000,
        }
        if cms_filter:
            params["cms_detectado"] = f"eq.{cms_filter}"
        if solo_con_tokko:
            params["cms_detectado"] = "eq.tokko"
        r = self.session.get(
            f"{SUPABASE_URL}/rest/v1/inmobiliarias_main",
            headers=self._headers,
            params=params,
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    def _get_scraping_agency_columns(self) -> set:
        if SupabasePropiedades._scraping_agency_columns_cache is not None:
            return SupabasePropiedades._scraping_agency_columns_cache

        columns = set(self._SCRAPING_AGENCY_COLUMNS)
        for column in self._OPTIONAL_SCRAPING_AGENCY_COLUMNS:
            try:
                r = self.session.get(
                    f"{SUPABASE_URL}/rest/v1/inmobiliarias_scraping",
                    headers=self._headers,
                    params={"select": column, "limit": 1},
                    timeout=10,
                )
                if r.status_code == 200:
                    columns.add(column)
            except Exception:
                pass

        SupabasePropiedades._scraping_agency_columns_cache = columns
        return columns

    def _sanitize_scraping_agency_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        columns = self._get_scraping_agency_columns()
        return {key: value for key, value in payload.items() if key in columns and value is not None}

    def _load_scraping_agencies_by_web(self, web: Any) -> List[Dict]:
        web_key = _normalize_web_key(web)
        if not web_key:
            return []
        try:
            r = self.session.get(
                f"{SUPABASE_URL}/rest/v1/inmobiliarias_scraping",
                headers=self._headers,
                params={
                    "select": "id,nombre,web,ciudad,provincia",
                    "web": f"ilike.*{web_key}*",
                    "limit": 25,
                },
                timeout=20,
            )
            if r.status_code == 200:
                return r.json()
        except Exception as exc:
            logger.debug("resolve inmobiliaria web lookup error: %s", exc)
        return []

    def _load_scraping_agencies_by_location(self, ciudad: Any, provincia: Any) -> List[Dict]:
        params: Dict[str, Any] = {
            "select": "id,nombre,web,ciudad,provincia",
            "limit": 1000,
        }
        if ciudad:
            params["ciudad"] = f"ilike.*{str(ciudad).strip()}*"
        if provincia:
            params["provincia"] = f"ilike.*{str(provincia).strip()}*"
        try:
            r = self.session.get(
                f"{SUPABASE_URL}/rest/v1/inmobiliarias_scraping",
                headers=self._headers,
                params=params,
                timeout=30,
            )
            if r.status_code == 200:
                return r.json()
        except Exception as exc:
            logger.debug("resolve inmobiliaria name lookup error: %s", exc)
        return []

    def load_main_agency_by_id(self, agency_id: Any) -> Optional[Dict[str, Any]]:
        if agency_id is None:
            return None
        try:
            r = self.session.get(
                f"{SUPABASE_URL}/rest/v1/inmobiliarias_main",
                headers=self._headers,
                params={
                    "select": "id,nombre,nombre_limpio,nombre_normalizado,web,url_listado,ciudad,provincia,pais,cms_detectado,scraping_id_origen",
                    "id": f"eq.{agency_id}",
                    "limit": 1,
                },
                timeout=12,
            )
            if r.status_code == 200:
                data = r.json()
                return data[0] if data else None
            logger.debug("load_main_agency_by_id %s -> %s %s", agency_id, r.status_code, r.text[:200])
        except Exception as exc:
            logger.debug("load_main_agency_by_id %s error: %s", agency_id, exc)
        return None

    def load_scraping_agency_by_id(self, agency_id: Any) -> Optional[Dict[str, Any]]:
        if agency_id is None:
            return None
        try:
            r = self.session.get(
                f"{SUPABASE_URL}/rest/v1/inmobiliarias_scraping",
                headers=self._headers,
                params={
                    "select": "id,nombre,web,ciudad,provincia",
                    "id": f"eq.{agency_id}",
                    "limit": 1,
                },
                timeout=12,
            )
            if r.status_code == 200:
                data = r.json()
                return data[0] if data else None
            logger.debug("load_scraping_agency_by_id %s -> %s %s", agency_id, r.status_code, r.text[:200])
        except Exception as exc:
            logger.debug("load_scraping_agency_by_id %s error: %s", agency_id, exc)
        return None

    def load_main_agencies_by_scraping_id(self, scraping_id: Any) -> List[Dict[str, Any]]:
        if scraping_id is None:
            return []
        try:
            r = self.session.get(
                f"{SUPABASE_URL}/rest/v1/inmobiliarias_main",
                headers=self._headers,
                params={
                    "select": "id,nombre,nombre_limpio,nombre_normalizado,web,url_listado,ciudad,provincia,pais,cms_detectado,scraping_id_origen",
                    "scraping_id_origen": f"eq.{scraping_id}",
                    "limit": 10,
                },
                timeout=12,
            )
            if r.status_code == 200:
                return r.json()
            logger.debug("load_main_agencies_by_scraping_id %s -> %s %s", scraping_id, r.status_code, r.text[:200])
        except Exception as exc:
            logger.debug("load_main_agencies_by_scraping_id %s error: %s", scraping_id, exc)
        return []

    def find_main_agency_by_web_name(self, web: Any, name: Any) -> Dict[str, Any]:
        web_key = _normalize_web_key(web)
        if not web_key:
            return {"status": "not_found", "candidates": []}

        rows_by_id: Dict[Any, Dict[str, Any]] = {}
        for column in ("web", "url_listado"):
            try:
                r = self.session.get(
                    f"{SUPABASE_URL}/rest/v1/inmobiliarias_main",
                    headers=self._headers,
                    params={
                        "select": "id,nombre,nombre_limpio,nombre_normalizado,web,url_listado,ciudad,provincia,pais,cms_detectado,scraping_id_origen",
                        column: f"ilike.*{web_key}*",
                        "limit": 25,
                    },
                    timeout=15,
                )
                if r.status_code == 200:
                    for row in r.json():
                        rows_by_id[row.get("id")] = row
            except Exception as exc:
                logger.debug("find_main_agency_by_web_name %s lookup error: %s", column, exc)

        candidates: List[Dict[str, Any]] = []
        for row in rows_by_id.values():
            row_domains = _unique_domains(row.get("web"), row.get("url_listado"))
            if web_key not in row_domains:
                continue
            if not _agency_name_compatible(name, _agency_row_name(row)):
                continue
            candidates.append(row)

        if len(candidates) == 1:
            return {"status": "ok", "row": candidates[0], "candidates": candidates}
        if len(candidates) > 1:
            return {"status": "ambiguous", "candidates": candidates}
        return {"status": "not_found", "candidates": []}

    def resolve_canonical_inmobiliaria_id(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve a scraping item to the canonical inmobiliarias_main.id.

        Historical data can contain either ID space in scraping_run_items.inmobiliaria_id.
        This method fails closed when the source row cannot be tied safely to a single
        inmobiliarias_main row.
        """
        run_item_id = item.get("scraping_run_item_id") or item.get("id")
        source_id = item.get("inmobiliaria_id")
        item_name = _agency_item_name(item)
        item_web = item.get("web") or item.get("url_listado")
        attempts: List[Dict[str, Any]] = []

        def _resolution(row: Dict[str, Any], method: str, source_space: str,
                        scraping_row: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
            validation = _agency_row_item_validation(row, item)
            if not validation["matches"]:
                raise ScrapingControlError(
                    "canonical_id_mismatch: la fila canonica no coincide con el item de cola",
                    metadata={
                        "run_item_id": run_item_id,
                        "run_item_inmobiliaria_id": source_id,
                        "metodo_resolucion": method,
                        "source_id_space": source_space,
                        "canonical_main_id": row.get("id"),
                        "validation": validation,
                        "item_snapshot": {
                            "inmobiliaria_nombre": item_name,
                            "web": item.get("web"),
                            "url_listado": item.get("url_listado"),
                            "ciudad": item.get("ciudad"),
                            "provincia": item.get("provincia"),
                        },
                        "main_row": {
                            "id": row.get("id"),
                            "nombre": _agency_row_name(row),
                            "web": row.get("web"),
                            "url_listado": row.get("url_listado"),
                            "ciudad": row.get("ciudad"),
                            "provincia": row.get("provincia"),
                        },
                    },
                    final_url=item.get("url_listado") or item.get("web"),
                )
            return {
                "canonical_main_id": int(row["id"]),
                "inmobiliaria_main_id": int(row["id"]),
                "main_row": row,
                "scraping_row": scraping_row,
                "source_id_space": source_space,
                "run_item_inmobiliaria_id": source_id,
                "metodo_resolucion": method,
                "validation": validation,
                "attempts": attempts,
            }

        main_row = self.load_main_agency_by_id(source_id)
        if main_row:
            validation = _agency_row_item_validation(main_row, item)
            attempts.append({
                "source": "inmobiliarias_main_by_id",
                "id": source_id,
                "row_name": _agency_row_name(main_row),
                "row_web": main_row.get("web"),
                "validation": validation,
            })
            if validation["matches"]:
                return _resolution(main_row, "main_id_match", "main")

        scraping_row = self.load_scraping_agency_by_id(source_id)
        if scraping_row:
            scraping_validation = _agency_row_item_validation(scraping_row, item)
            attempts.append({
                "source": "inmobiliarias_scraping_by_id",
                "id": source_id,
                "row_name": _agency_row_name(scraping_row),
                "row_web": scraping_row.get("web"),
                "validation": scraping_validation,
            })
            if scraping_validation["matches"]:
                linked_rows = self.load_main_agencies_by_scraping_id(source_id)
                attempts.append({
                    "source": "inmobiliarias_main_by_scraping_id_origen",
                    "scraping_id": source_id,
                    "count": len(linked_rows),
                    "ids": [row.get("id") for row in linked_rows],
                })
                if len(linked_rows) == 1:
                    return _resolution(
                        linked_rows[0],
                        "scraping_id_origen_match",
                        "scraping",
                        scraping_row=scraping_row,
                    )
                if len(linked_rows) > 1:
                    raise ScrapingControlError(
                        "canonical_id_resolution_failed: scraping_id_origen apunta a multiples inmobiliarias_main",
                        metadata={
                            "run_item_id": run_item_id,
                            "run_item_inmobiliaria_id": source_id,
                            "candidate_main_ids": [row.get("id") for row in linked_rows],
                            "attempts": attempts,
                        },
                        final_url=item.get("url_listado") or item.get("web"),
                    )

        fallback = self.find_main_agency_by_web_name(item_web, item_name)
        attempts.append({
            "source": "inmobiliarias_main_by_web_name",
            "status": fallback.get("status"),
            "candidate_main_ids": [row.get("id") for row in fallback.get("candidates", [])],
        })
        if fallback.get("status") == "ok":
            return _resolution(fallback["row"], "web_name_match", "fallback_web_name")
        if fallback.get("status") == "ambiguous":
            raise ScrapingControlError(
                "canonical_id_resolution_failed: match por web/nombre ambiguo en inmobiliarias_main",
                metadata={
                    "run_item_id": run_item_id,
                    "run_item_inmobiliaria_id": source_id,
                    "candidate_main_ids": [row.get("id") for row in fallback.get("candidates", [])],
                    "attempts": attempts,
                },
                final_url=item.get("url_listado") or item.get("web"),
            )

        if main_row:
            raise ScrapingControlError(
                "canonical_id_mismatch: inmobiliaria_id apunta a main pero nombre/web no coinciden",
                metadata={
                    "run_item_id": run_item_id,
                    "run_item_inmobiliaria_id": source_id,
                    "attempts": attempts,
                    "main_row": {
                        "id": main_row.get("id"),
                        "nombre": _agency_row_name(main_row),
                        "web": main_row.get("web"),
                        "url_listado": main_row.get("url_listado"),
                    },
                },
                final_url=item.get("url_listado") or item.get("web"),
            )

        raise ScrapingControlError(
            "canonical_id_resolution_failed: no se pudo resolver inmobiliarias_main.id de forma segura",
            metadata={
                "run_item_id": run_item_id,
                "run_item_inmobiliaria_id": source_id,
                "item_snapshot": {
                    "inmobiliaria_nombre": item_name,
                    "web": item.get("web"),
                    "url_listado": item.get("url_listado"),
                    "ciudad": item.get("ciudad"),
                    "provincia": item.get("provincia"),
                },
                "attempts": attempts,
            },
            final_url=item.get("url_listado") or item.get("web"),
        )

    def resolve_scraping_agency(self, item: Dict[str, Any]) -> Dict[str, Any]:
        main_id = item.get("inmobiliaria_id")
        nombre = item.get("inmobiliaria_nombre") or item.get("nombre")
        web = item.get("web") or item.get("url_listado")
        ciudad = item.get("ciudad")
        provincia = item.get("provincia")
        web_key = _normalize_web_key(web)

        if web_key:
            candidates = self._load_scraping_agencies_by_web(web)
            for candidate in candidates:
                if _normalize_web_key(candidate.get("web")) == web_key:
                    return {
                        "inmobiliaria_main_id": main_id,
                        "inmobiliaria_scraping_id": candidate["id"],
                        "metodo_resolucion": "web_match",
                    }
            if len(candidates) == 1:
                candidate = candidates[0]
                return {
                    "inmobiliaria_main_id": main_id,
                    "inmobiliaria_scraping_id": candidate["id"],
                    "metodo_resolucion": "web_match",
                }

        nombre_key = _normalize_text_key(nombre)
        if nombre_key:
            for candidate in self._load_scraping_agencies_by_location(ciudad, provincia):
                candidate_key = _normalize_text_key(candidate.get("nombre"))
                if candidate_key == nombre_key and _same_location(candidate, ciudad, provincia):
                    return {
                        "inmobiliaria_main_id": main_id,
                        "inmobiliaria_scraping_id": candidate["id"],
                        "metodo_resolucion": "name_city_match",
                    }

        payload = self._sanitize_scraping_agency_payload({
            "nombre": nombre or f"Inmobiliaria main {main_id}",
            "web": web,
            "ciudad": ciudad,
            "provincia": provincia,
            "pais": "Argentina",
            "fuente": "inmobiliarias_main",
            "estado_scraping": "pendiente",
        })
        r = self.session.post(
            f"{SUPABASE_URL}/rest/v1/inmobiliarias_scraping",
            headers=self._headers,
            json=payload,
            timeout=30,
        )
        if r.status_code not in {200, 201}:
            # Si hubo carrera por una web unica, reintentar lectura por web antes de fallar.
            if web_key and r.status_code == 409:
                candidates = self._load_scraping_agencies_by_web(web)
                for candidate in candidates:
                    if _normalize_web_key(candidate.get("web")) == web_key:
                        return {
                            "inmobiliaria_main_id": main_id,
                            "inmobiliaria_scraping_id": candidate["id"],
                            "metodo_resolucion": "web_match",
                        }
            raise RuntimeError(f"No se pudo crear inmobiliarias_scraping: {r.status_code} {r.text[:300]}")

        created = r.json()
        row = created[0] if isinstance(created, list) and created else created
        return {
            "inmobiliaria_main_id": main_id,
            "inmobiliaria_scraping_id": row["id"],
            "metodo_resolucion": "created_scraping_agency",
        }

    # ------ Jobs ------

    def load_pending_jobs(self) -> List[Dict]:
        now_iso = datetime.now(timezone.utc).isoformat()
        r = self.session.get(
            f"{SUPABASE_URL}/rest/v1/scraping_jobs",
            headers=self._headers,
            params={
                "select": "*",
                "or": f"(estado.eq.pendiente,and(estado.eq.fallido,proximo_intento.lte.{now_iso}))",
                "order": "prioridad.desc,created_at.asc",
                "limit": 500,
            },
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    def load_all_jobs_for_agencies(self, inmob_ids: List[int]) -> List[Dict]:
        """Carga todos los jobs (cualquier estado) para las agencias dadas."""
        if not inmob_ids:
            return []
        todos = []
        chunk = 200
        for i in range(0, len(inmob_ids), chunk):
            ids_str = ",".join(str(x) for x in inmob_ids[i:i+chunk])
            r = self.session.get(
                f"{SUPABASE_URL}/rest/v1/scraping_jobs",
                headers=self._headers,
                params={
                    "select": "id,inmobiliaria_id,estado,completado_en,intentos,prioridad,url_inicio",
                    "inmobiliaria_id": f"in.({ids_str})",
                    "limit": chunk,
                },
                timeout=30,
            )
            if r.ok:
                todos.extend(r.json())
        return todos

    def _patch_job(self, job_id: int, payload: Dict) -> None:
        """Actualiza campos de un job por ID."""
        try:
            self.session.patch(
                f"{SUPABASE_URL}/rest/v1/scraping_jobs?id=eq.{job_id}",
                headers=self._headers,
                json=payload,
                timeout=10,
            )
        except Exception:
            pass

    def upsert_job(self, job: Dict) -> Dict:
        """Inserción individual — solo se usa como fallback."""
        try:
            r = self.session.post(
                f"{SUPABASE_URL}/rest/v1/scraping_jobs",
                headers=self._headers,
                json=job,
                timeout=10,
            )
            if r.status_code in {200, 201}:
                data = r.json()
                return data[0] if isinstance(data, list) else data
        except Exception:
            pass
        return {**job, "id": -1}

    def bulk_create_jobs(self, jobs: List[Dict]) -> Dict[int, int]:
        """Inserta todos los jobs de una vez. Retorna {inmobiliaria_id: job_id}."""
        if not jobs:
            return {}
        try:
            r = self.session.post(
                f"{SUPABASE_URL}/rest/v1/scraping_jobs",
                headers=self._headers,
                json=jobs,
                timeout=60,
            )
            if r.status_code in {200, 201}:
                created = r.json()
                if isinstance(created, list):
                    return {row["inmobiliaria_id"]: row["id"] for row in created if "id" in row}
        except Exception as e:
            logger.warning("bulk_create_jobs falló: %s", e)
        return {}

    def update_job(self, job_id: int, patch: Dict) -> None:
        r = self.session.patch(
            f"{SUPABASE_URL}/rest/v1/scraping_jobs",
            headers=self._headers_minimal,
            params={"id": f"eq.{job_id}"},
            json=patch,
            timeout=20,
        )
        if r.status_code not in {200, 204}:
            logger.warning("update_job %s → %s", job_id, r.status_code)

    # ------ Scraping control queue ------

    def _rpc(self, function_name: str, payload: Optional[Dict[str, Any]] = None,
             timeout: int = 15) -> Any:
        r = self.session.post(
            f"{SUPABASE_URL}/rest/v1/rpc/{function_name}",
            headers=self._headers_rpc,
            json=payload or {},
            timeout=timeout,
        )
        if r.status_code not in {200, 201, 204}:
            raise RuntimeError(f"RPC {function_name} fallo {r.status_code}: {r.text[:500]}")
        if r.status_code == 204 or not r.text.strip():
            return None
        try:
            return r.json()
        except ValueError:
            return r.text

    def _rpc_with_parameter_fallback(self, function_name: str, payload: Dict[str, Any],
                                     timeout: int = 15) -> Any:
        try:
            return self._rpc(function_name, payload, timeout=timeout)
        except RuntimeError as exc:
            msg = str(exc)
            if "PGRST202" not in msg and "Could not find the function" not in msg:
                raise
            prefixed_payload = {f"p_{key}": value for key, value in payload.items()}
            return self._rpc(function_name, prefixed_payload, timeout=timeout)

    def claim_next_scraping_item(self) -> Optional[Dict]:
        data = self._rpc("claim_next_scraping_item", {}, timeout=10)
        if isinstance(data, list):
            if not data:
                return None
            data = data[0]
        if not isinstance(data, dict) or not data:
            return None
        if all(value is None for value in data.values()):
            return None
        return data

    def load_pending_scraping_items_for_integrity(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Read-only preview of pending queue items for ID-integrity dry runs."""
        r = self.session.get(
            f"{SUPABASE_URL}/rest/v1/scraping_run_items",
            headers=self._headers,
            params={
                "select": "id,scraping_run_id,inmobiliaria_id,inmobiliaria_nombre,ciudad,provincia,web,url_listado,cms_detectado,status,final_url,metadata,created_at",
                "status": "eq.pending",
                "order": "created_at.asc",
                "limit": max(int(limit or 5), 1),
            },
            timeout=15,
        )
        if r.status_code != 200:
            raise RuntimeError(f"No se pudieron leer items pending para dry-run: {r.status_code} {r.text[:300]}")
        rows = r.json()
        for row in rows:
            row["scraping_run_item_id"] = row.get("id")
        return rows

    def start_scraping_item(self, item_id: Any) -> Any:
        return self._rpc_with_parameter_fallback(
            "start_scraping_item",
            {"item_id": item_id},
            timeout=10,
        )

    def finish_scraping_item_success(
        self,
        item_id: Any,
        propiedades_detectadas: int,
        propiedades_nuevas: int,
        propiedades_actualizadas: int,
        propiedades_sin_cambios: int,
        propiedades_error: int,
        final_url: Optional[str],
        metadata_json: Dict[str, Any],
    ) -> Any:
        payload = {
            "item_id": item_id,
            "propiedades_detectadas": propiedades_detectadas,
            "propiedades_nuevas": propiedades_nuevas,
            "propiedades_actualizadas": propiedades_actualizadas,
            "propiedades_sin_cambios": propiedades_sin_cambios,
            "propiedades_error": propiedades_error,
            "final_url": final_url,
            "metadata_json": metadata_json,
        }
        return self._rpc_with_parameter_fallback(
            "finish_scraping_item_success",
            payload,
            timeout=15,
        )

    def finish_scraping_item_error(
        self,
        item_id: Any,
        error_message: str,
        error_type: str,
        http_status: Optional[int],
        final_url: Optional[str],
        metadata_json: Dict[str, Any],
    ) -> Any:
        payload = {
            "item_id": item_id,
            "error_message": error_message[:1000],
            "error_type": error_type,
            "http_status": http_status,
            "final_url": final_url,
            "metadata_json": metadata_json,
        }
        return self._rpc_with_parameter_fallback(
            "finish_scraping_item_error",
            payload,
            timeout=8,
        )

    def close_scraping_run_if_finished(self, run_id: Any) -> Any:
        return self._rpc_with_parameter_fallback(
            "close_scraping_run_if_finished",
            {"run_id": run_id},
            timeout=10,
        )

    # ------ Properties ------

    def get_existing_hashes(self, hashes: List[str]) -> set:
        if not hashes:
            return set()
        r = self.session.post(
            f"{SUPABASE_URL}/rest/v1/rpc/get_existing_hashes",
            headers=self._headers,
            json={"hashes": hashes},
            timeout=20,
        )
        if r.status_code == 200:
            return {row["hash_dedup"] for row in r.json()}
        # Fallback: query directa
        existing: set = set()
        for i in range(0, len(hashes), 100):
            chunk = hashes[i : i + 100]
            quoted = ",".join(f'"{h}"' for h in chunk)
            r2 = self.session.get(
                f"{SUPABASE_URL}/rest/v1/propiedades",
                headers=self._headers,
                params={"select": "hash_dedup", "hash_dedup": f"in.({quoted})"},
                timeout=20,
            )
            if r2.status_code == 200:
                existing.update(row["hash_dedup"] for row in r2.json())
        return existing

    def get_existing_properties_by_hash(self, hashes: List[str]) -> Dict[str, Dict[str, Any]]:
        if not hashes:
            return {}
        columns = self._get_property_columns()
        select_columns = ["hash_dedup"]
        for column in sorted(PROTECTED_UPDATE_FIELDS | {"id"}):
            if column in columns and column not in select_columns:
                select_columns.append(column)

        existing: Dict[str, Dict[str, Any]] = {}
        unique_hashes = sorted({h for h in hashes if h})
        for i in range(0, len(unique_hashes), 100):
            chunk = unique_hashes[i : i + 100]
            quoted = ",".join(f'"{h}"' for h in chunk)
            try:
                r = self.session.get(
                    f"{SUPABASE_URL}/rest/v1/propiedades",
                    headers=self._headers,
                    params={
                        "select": ",".join(select_columns),
                        "hash_dedup": f"in.({quoted})",
                    },
                    timeout=20,
                )
                if r.status_code == 200:
                    for row in r.json():
                        if row.get("hash_dedup"):
                            existing[row["hash_dedup"]] = row
                else:
                    logger.warning("get_existing_properties_by_hash %s: %s", r.status_code, r.text[:200])
            except Exception as exc:
                logger.warning("get_existing_properties_by_hash fallo: %s", str(exc)[:200])
        return existing

    def get_existing_properties_for_dedup(self, propiedades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Carga propiedades existentes por inmobiliaria para deduplicar por URL/id externo.

        La identidad fuerte de una propiedad es:
        1) inmobiliaria_id canonico + URL normalizada,
        2) inmobiliaria_id canonico + id_externo normalizado,
        3) hash_dedup como fallback.
        """
        agency_ids = sorted({
            int(p.get("inmobiliaria_id"))
            for p in propiedades
            if p.get("inmobiliaria_id") is not None and str(p.get("inmobiliaria_id")).isdigit()
        })
        result = {
            "by_url": {},
            "by_url_all": {},
            "by_external": {},
            "by_external_all": {},
            "by_hash": {},
            "duplicate_existing_keys": [],
        }
        if not agency_ids:
            return result

        columns = self._get_property_columns()
        select_columns = ["id", "hash_dedup", "inmobiliaria_id", "url", "url_normalizada", "id_externo"]
        for column in sorted(PROTECTED_UPDATE_FIELDS | {"created_at", "updated_at"}):
            if column in columns and column not in select_columns:
                select_columns.append(column)

        def remember(index: Dict[Any, Dict[str, Any]], key: Any, row: Dict[str, Any], key_type: str) -> None:
            if not key:
                return
            existing = index.get(key)
            if existing is None:
                index[key] = row
                return
            duplicate = {
                "type": key_type,
                "key": str(key)[:300],
                "kept_id": existing.get("id"),
                "duplicate_id": row.get("id"),
            }
            result["duplicate_existing_keys"].append(duplicate)

        for agency_id in agency_ids:
            offset = 0
            page_size = 1000
            while True:
                try:
                    r = self.session.get(
                        f"{SUPABASE_URL}/rest/v1/propiedades",
                        headers=self._headers,
                        params={
                            "select": ",".join(select_columns),
                            "inmobiliaria_id": f"eq.{agency_id}",
                            "order": "id.asc",
                            "limit": page_size,
                            "offset": offset,
                        },
                        timeout=30,
                    )
                    if r.status_code != 200:
                        logger.warning("get_existing_properties_for_dedup %s: %s", r.status_code, r.text[:200])
                        break
                    rows = r.json()
                except Exception as exc:
                    logger.warning("get_existing_properties_for_dedup fallo: %s", str(exc)[:200])
                    break

                for row in rows:
                    row_agency_id = row.get("inmobiliaria_id")
                    if row.get("hash_dedup"):
                        remember(result["by_hash"], row["hash_dedup"], row, "hash")
                    url_key = row.get("url_normalizada") or normalize_property_url_for_dedup(row.get("url"))
                    if url_key and row_agency_id is not None:
                        key = (int(row_agency_id), url_key)
                        result["by_url_all"].setdefault(key, []).append(row)
                        remember(result["by_url"], key, row, "url")
                    external_key = normalize_external_id_for_dedup(row.get("id_externo"))
                    if external_key and row_agency_id is not None:
                        key = (int(row_agency_id), external_key)
                        result["by_external_all"].setdefault(key, []).append(row)
                        remember(result["by_external"], key, row, "id_externo")

                if len(rows) < page_size:
                    break
                offset += page_size

        duplicates = result.get("duplicate_existing_keys") or []
        if duplicates:
            self.last_save_protection_stats["dedup_existing_duplicados"] = len(duplicates)
            examples = self.last_save_protection_stats.setdefault("dedup_existing_duplicados_ejemplos", [])
            examples.extend(duplicates[:5])
        return result

    def _get_property_columns(self) -> set:
        if SupabasePropiedades._property_columns_cache is not None:
            return SupabasePropiedades._property_columns_cache

        columns = set(self._PROPERTY_COLUMNS)
        for column in self._OPTIONAL_PROPERTY_COLUMNS:
            try:
                r = self.session.get(
                    f"{SUPABASE_URL}/rest/v1/propiedades",
                    headers=self._headers,
                    params={"select": column, "limit": 1},
                    timeout=10,
                )
                if r.status_code == 200:
                    columns.add(column)
            except Exception:
                pass

        SupabasePropiedades._property_columns_cache = columns
        return columns

    def _sanitize_property_payload(self, prop: Dict) -> Dict:
        columns = self._get_property_columns()
        clean = dict(prop)
        url_key = normalize_property_url_for_dedup(clean.get("url"))
        if url_key:
            clean["url_normalizada"] = url_key
        else:
            clean.pop("url_normalizada", None)
        clean = sanitize_property_location(clean, getattr(self, "last_save_protection_stats", None))
        clean = apply_agency_location_fallback(clean, getattr(self, "last_save_protection_stats", None))
        clean = normalize_property_location_encoding(clean, getattr(self, "last_save_protection_stats", None))
        clean = sanitize_property_coordinates(clean, getattr(self, "last_save_protection_stats", None))
        clean = sanitize_property_prices(clean, getattr(self, "last_save_protection_stats", None))
        clean = sanitize_property_integers(clean, getattr(self, "last_save_protection_stats", None))
        if "imagenes" in clean:
            raw_images = clean.get("imagenes")
            if isinstance(raw_images, str):
                raw_images = [raw_images]
            elif not isinstance(raw_images, list):
                raw_images = []
            image_clean_stats = _new_image_stats()
            cleaned_images = clean_property_images(raw_images, stats=image_clean_stats)
            stats = getattr(self, "last_save_protection_stats", None)
            if stats is not None:
                stats["imagenes_payload_entrada"] = int(stats.get("imagenes_payload_entrada") or 0) + (1 if raw_images else 0)
                if cleaned_images:
                    stats["imagenes_payload_con_reales"] = int(stats.get("imagenes_payload_con_reales") or 0) + 1
                    stats["imagenes_guardadas_payload"] = int(stats.get("imagenes_guardadas_payload") or 0) + len(cleaned_images)
                elif raw_images:
                    stats["imagenes_payload_sin_reales"] = int(stats.get("imagenes_payload_sin_reales") or 0) + 1
                stats["imagenes_descartadas_sanitizer"] = int(stats.get("imagenes_descartadas_sanitizer") or 0) + int(
                    image_clean_stats.get("imagenes_falsas_descartadas") or 0
                )
                by_reason = stats.setdefault("imagenes_descartadas_sanitizer_por_motivo", {})
                for reason, count in (image_clean_stats.get("imagenes_descartadas_por_motivo") or {}).items():
                    by_reason[reason] = int(by_reason.get(reason) or 0) + int(count or 0)
            clean["imagenes"] = cleaned_images or None

        if "calidad_score" in columns and "calidad_score" not in clean and "score_calidad" in clean:
            clean["calidad_score"] = clean["score_calidad"]

        filtered = {key: value for key, value in clean.items() if key in columns}
        for private_key in (
            "_agency_location_context",
            "_ubicacion_fallback_from_agency",
            "_fallback_ciudad_from_agency",
            "_fallback_provincia_from_agency",
            "_original_city_before_agency_fallback",
            "_original_province_before_agency_fallback",
            "_ciudad_detectada_from_text",
            "_provincia_detectada_from_text",
            "_ciudad_encoding_normalizada",
            "_provincia_encoding_normalizada",
        ):
            if private_key in clean:
                filtered[private_key] = clean.get(private_key)
        dropped = sorted(set(clean) - set(filtered))
        if dropped:
            logger.debug("Campos omitidos en propiedades: %s", ", ".join(dropped))
        return filtered

    def _normalize_payload_batch_keys(self, chunk: List[Dict[str, Any]], columns: set) -> List[Dict[str, Any]]:
        """PostgREST exige que todos los objetos de un batch tengan las mismas keys."""
        if not chunk:
            return []
        keys = sorted(set().union(*(set(item.keys()) for item in chunk)) & set(columns))
        return [{key: item.get(key) for key in keys} for item in chunk]

    def _load_existing_property_by_url_normalizada(
        self,
        agency_id: Any,
        url_normalizada: Any,
        columns: set,
    ) -> Optional[Dict[str, Any]]:
        if agency_id is None or not url_normalizada:
            return None
        try:
            agency_key = int(agency_id)
        except (TypeError, ValueError):
            return None

        select_columns = ["id", "hash_dedup", "inmobiliaria_id", "url", "url_normalizada", "id_externo"]
        for column in sorted(PROTECTED_UPDATE_FIELDS | {"created_at", "updated_at"}):
            if column in columns and column not in select_columns:
                select_columns.append(column)
        try:
            r = self.session.get(
                f"{SUPABASE_URL}/rest/v1/propiedades",
                headers=self._headers,
                params={
                    "select": ",".join([column for column in select_columns if column in columns]),
                    "inmobiliaria_id": f"eq.{agency_key}",
                    "url_normalizada": f"eq.{url_normalizada}",
                    "order": "id.asc",
                    "limit": 1,
                },
                timeout=15,
            )
            if r.status_code == 200:
                rows = r.json()
                return rows[0] if rows else None
            logger.warning("lookup url_normalizada %s: %s", r.status_code, r.text[:200])
        except Exception as exc:
            logger.warning("lookup url_normalizada fallo: %s", str(exc)[:200])
        return None

    @staticmethod
    def _is_unique_url_violation(status_code: int, message: str) -> bool:
        text = (message or "").lower()
        return (
            status_code == 409
            and "idx_propiedades_unique_inmobiliaria_url_normalizada" in text
            and "url_normalizada" in text
        )

    def save_propiedades(self, propiedades: List[Dict]) -> Tuple[int, int]:
        """Guarda nuevas y actualiza existentes sin degradar datos valiosos."""
        self.last_save_result = {"inserted": 0, "updated": 0, "unchanged": 0, "failed": 0, "errors": []}
        if not propiedades:
            return 0, 0

        self.last_save_protection_stats = _new_update_protection_stats()
        propiedades = [self._sanitize_property_payload(p) for p in propiedades]
        propiedades = [p for p in propiedades if p.get("hash_dedup")]
        if not propiedades:
            return 0, 0

        columns = self._get_property_columns()
        identity_index = self.get_existing_properties_for_dedup(propiedades)
        nuevas: List[Dict[str, Any]] = []
        actualizadas: List[Tuple[Dict[str, Any], Dict[str, Any], str]] = []
        matched_existing_hashes: set = set()
        matched_existing_ids: set = set()

        def choose_existing_candidate(candidates: List[Dict[str, Any]], incoming_hash: Any) -> Optional[Dict[str, Any]]:
            if not candidates:
                return None
            if incoming_hash:
                for candidate in candidates:
                    if candidate.get("hash_dedup") == incoming_hash:
                        return candidate
            return candidates[0]

        for prop in propiedades:
            agency_id = prop.get("inmobiliaria_id")
            try:
                agency_key = int(agency_id) if agency_id is not None else None
            except (TypeError, ValueError):
                agency_key = None
            url_key = normalize_property_url_for_dedup(prop.get("url"))
            external_key = normalize_external_id_for_dedup(prop.get("id_externo"))
            existing_prop = None
            match_type = ""
            if agency_key is not None and url_key:
                existing_prop = choose_existing_candidate(
                    identity_index.get("by_url_all", {}).get((agency_key, url_key), []),
                    prop.get("hash_dedup"),
                )
                if existing_prop:
                    match_type = "url_normalizada"
                    self.last_save_protection_stats["dedup_por_url_normalizada"] = int(
                        self.last_save_protection_stats.get("dedup_por_url_normalizada") or 0
                    ) + 1
            if existing_prop is None and agency_key is not None and external_key:
                existing_prop = choose_existing_candidate(
                    identity_index.get("by_external_all", {}).get((agency_key, external_key), []),
                    prop.get("hash_dedup"),
                )
                if existing_prop:
                    match_type = "id_externo"
                    self.last_save_protection_stats["dedup_por_id_externo"] = int(
                        self.last_save_protection_stats.get("dedup_por_id_externo") or 0
                    ) + 1
            if existing_prop is None and prop.get("hash_dedup"):
                existing_prop = identity_index["by_hash"].get(prop.get("hash_dedup"))
                if existing_prop:
                    match_type = "hash_dedup"
                    self.last_save_protection_stats["dedup_por_hash"] = int(
                        self.last_save_protection_stats.get("dedup_por_hash") or 0
                    ) + 1

            if existing_prop:
                if existing_prop.get("hash_dedup"):
                    matched_existing_hashes.add(existing_prop["hash_dedup"])
                if existing_prop.get("id") is not None:
                    matched_existing_ids.add(existing_prop["id"])
                actualizadas.append((prop, existing_prop, match_type))
            else:
                nuevas.append(prop)

        inserted = 0
        updated = 0
        unchanged = 0
        failed = 0
        recovered_unique = 0
        save_errors: List[Dict[str, Any]] = []

        def update_existing_property(
            prop: Dict[str, Any],
            existing_prop: Dict[str, Any],
            match_type: str,
        ) -> bool:
            nonlocal updated, unchanged, failed
            hash_dedup = prop.get("hash_dedup")
            update_payload = build_protected_update_payload(
                incoming=prop,
                existing=existing_prop,
                columns=columns,
                stats=self.last_save_protection_stats,
            )
            if not update_payload:
                unchanged += 1
                return True
            target_id = existing_prop.get("id")
            if not target_id:
                failed += 1
                save_errors.append({
                    "operation": "update",
                    "status_code": "missing_target_id",
                    "message": "No se encontro id de propiedad existente para actualizar",
                    "hash_dedup": hash_dedup,
                    "url": prop.get("url"),
                    "url_normalizada": prop.get("url_normalizada"),
                    "match_type": match_type,
                })
                return False
            r = self.session.patch(
                f"{SUPABASE_URL}/rest/v1/propiedades?id=eq.{target_id}",
                headers=self._headers_minimal,
                json=update_payload,
                timeout=20,
            )
            if r.status_code not in {200, 204}:
                failed += 1
                error = {
                    "operation": "update",
                    "status_code": r.status_code,
                    "message": r.text[:1000],
                    "hash_dedup": hash_dedup,
                    "url": prop.get("url"),
                    "url_normalizada": prop.get("url_normalizada"),
                    "target_id": target_id,
                    "match_type": match_type,
                }
                save_errors.append(error)
                logger.warning("save_propiedades safe update %s: %s", r.status_code, r.text[:500])
                return False
            updated += 1
            return True

        def recover_unique_url_violation(prop: Dict[str, Any], response_text: str) -> bool:
            nonlocal recovered_unique
            if not self._is_unique_url_violation(409, response_text):
                return False
            agency_id = prop.get("inmobiliaria_id")
            url_key = prop.get("url_normalizada") or normalize_property_url_for_dedup(prop.get("url"))
            existing_prop = self._load_existing_property_by_url_normalizada(agency_id, url_key, columns)
            if not existing_prop:
                return False
            recovered_unique += 1
            self.last_save_protection_stats["recovered_from_unique_violation"] = int(
                self.last_save_protection_stats.get("recovered_from_unique_violation") or 0
            ) + 1
            examples = self.last_save_protection_stats.setdefault("unique_violation_recovered_examples", [])
            if len(examples) < 5:
                examples.append({
                    "inmobiliaria_id": agency_id,
                    "url_normalizada": url_key,
                    "existing_id": existing_prop.get("id"),
                })
            logger.info(
                "  Recuperado 409 por url_normalizada: inmobiliaria_id=%s url_normalizada=%s existing_id=%s",
                agency_id,
                url_key,
                existing_prop.get("id"),
            )
            if existing_prop.get("hash_dedup"):
                matched_existing_hashes.add(existing_prop["hash_dedup"])
            if existing_prop.get("id") is not None:
                matched_existing_ids.add(existing_prop["id"])
            return update_existing_property(prop, existing_prop, "url_normalizada_unique_violation")

        def insert_one_after_batch_failure(prop: Dict[str, Any]) -> None:
            nonlocal inserted, failed
            single = self._normalize_payload_batch_keys([prop], columns)
            r_single = self.session.post(
                f"{SUPABASE_URL}/rest/v1/propiedades?on_conflict=hash_dedup",
                headers=self._headers,
                json=single,
                timeout=25,
            )
            if r_single.status_code in {200, 201}:
                inserted += 1
                return
            if self._is_unique_url_violation(r_single.status_code, r_single.text) and recover_unique_url_violation(prop, r_single.text):
                return
            failed += 1
            save_errors.append({
                "operation": "insert",
                "status_code": r_single.status_code,
                "message": r_single.text[:1000],
                "count": 1,
                "hash_dedup": prop.get("hash_dedup"),
                "url": prop.get("url"),
                "url_normalizada": prop.get("url_normalizada"),
            })
            logger.error("save_propiedades insert single %s: %s", r_single.status_code, r_single.text[:500])

        for i in range(0, len(nuevas), self._CHUNK):
            raw_chunk = nuevas[i : i + self._CHUNK]
            chunk = self._normalize_payload_batch_keys(raw_chunk, columns)
            r = self.session.post(
                f"{SUPABASE_URL}/rest/v1/propiedades?on_conflict=hash_dedup",
                headers=self._headers,
                json=chunk,
                timeout=40,
            )
            if r.status_code not in {200, 201}:
                if self._is_unique_url_violation(r.status_code, r.text):
                    logger.warning(
                        "save_propiedades insert batch 409 por url_normalizada; reintentando %d filas individualmente",
                        len(raw_chunk),
                    )
                    for prop in raw_chunk:
                        insert_one_after_batch_failure(prop)
                    continue
                failed += len(raw_chunk)
                error = {
                    "operation": "insert",
                    "status_code": r.status_code,
                    "message": r.text[:1000],
                    "count": len(raw_chunk),
                }
                save_errors.append(error)
                logger.error("save_propiedades insert %s: %s", r.status_code, r.text[:500])
            else:
                inserted += len(raw_chunk)

        for prop, existing_prop, match_type in actualizadas:
            update_existing_property(prop, existing_prop, match_type)

        self.last_save_protection_stats["actualizaciones_seguras"] = updated
        self.last_save_result = {
            "inserted": inserted,
            "updated": updated,
            "unchanged": unchanged,
            "failed": failed,
            "errors": save_errors,
            "recovered_from_unique_violation": recovered_unique,
            "matched_existing_hashes": sorted(matched_existing_hashes),
            "matched_existing_ids": sorted(matched_existing_ids),
        }
        protected_fields = int(self.last_save_protection_stats.get("campos_protegidos_de_null") or 0)
        if protected_fields:
            logger.info(
                "  Proteccion update: %d campos conservados (%d props con coords, %d props con imagenes)",
                protected_fields,
                int(self.last_save_protection_stats.get("coordenadas_conservadas") or 0),
                int(self.last_save_protection_stats.get("imagenes_conservadas") or 0),
            )
        outliers = int(self.last_save_protection_stats.get("coordenadas_descartadas_por_outlier") or 0)
        if outliers:
            logger.info(
                "  Coordenadas descartadas por outlier: %d | ejemplos=%s",
                outliers,
                self.last_save_protection_stats.get("coordenadas_outlier_ejemplos", [])[:3],
            )
        invalid_prices = int(self.last_save_protection_stats.get("precios_descartados_por_invalido") or 0)
        invalid_normalized = int(self.last_save_protection_stats.get("precios_normalizados_descartados") or 0)
        if invalid_prices or invalid_normalized:
            logger.info(
                "  Precios descartados por invalidos: publicados=%d normalizados=%d | ejemplos=%s",
                invalid_prices,
                invalid_normalized,
                self.last_save_protection_stats.get("precios_invalidos_ejemplos", [])[:3],
            )
        normalized_locations = int(self.last_save_protection_stats.get("ubicaciones_normalizadas") or 0)
        if normalized_locations:
            logger.info(
                "  Ubicaciones normalizadas: %d | ejemplos=%s",
                normalized_locations,
                self.last_save_protection_stats.get("ubicaciones_normalizadas_ejemplos", [])[:3],
            )
        invalid_integers = int(self.last_save_protection_stats.get("integers_descartados_por_invalido") or 0)
        if invalid_integers:
            logger.info(
                "  Enteros descartados por invalidos: %d | ejemplos=%s",
                invalid_integers,
                self.last_save_protection_stats.get("integers_invalidos_ejemplos", [])[:3],
            )
        dedup_url = int(self.last_save_protection_stats.get("dedup_por_url_normalizada") or 0)
        dedup_external = int(self.last_save_protection_stats.get("dedup_por_id_externo") or 0)
        dedup_hash = int(self.last_save_protection_stats.get("dedup_por_hash") or 0)
        if dedup_url or dedup_external or dedup_hash:
            logger.info(
                "  Deduplicacion existente: url_normalizada=%d id_externo=%d hash=%d",
                dedup_url,
                dedup_external,
                dedup_hash,
            )
        existing_dups = int(self.last_save_protection_stats.get("dedup_existing_duplicados") or 0)
        if existing_dups:
            logger.warning(
                "  Duplicados historicos detectados por identidad: %d | ejemplos=%s",
                existing_dups,
                self.last_save_protection_stats.get("dedup_existing_duplicados_ejemplos", [])[:3],
            )
        recovered_409 = int(self.last_save_protection_stats.get("recovered_from_unique_violation") or 0)
        if recovered_409:
            logger.info(
                "  Recuperados por 409 url_normalizada: %d | ejemplos=%s",
                recovered_409,
                self.last_save_protection_stats.get("unique_violation_recovered_examples", [])[:3],
            )

        if save_errors and (inserted + updated + unchanged) == 0:
            first_error = save_errors[0]
            raise SavePropertiesError(
                f"save_failed: {first_error.get('operation')} {first_error.get('status_code')}: {first_error.get('message')}",
                errors=save_errors,
            )
        if save_errors:
            logger.warning(
                "  Guardado parcial: inserted=%d updated=%d unchanged=%d failed=%d",
                inserted,
                updated,
                unchanged,
                failed,
            )

        return inserted + updated + unchanged, inserted

    def mark_inactivos(self, inmob_id: int, active_hashes: set) -> int:
        """
        Marca como 'inactivo' las propiedades de esta agencia que ya no
        aparecen en el listado actual. Retorna cuántas se marcaron.
        """
        if not active_hashes:
            return 0
        try:
            r = self.session.get(
                f"{SUPABASE_URL}/rest/v1/propiedades",
                headers=self._headers,
                params={
                    "select": "id,hash_dedup",
                    "inmobiliaria_id": f"eq.{inmob_id}",
                    "estado": "eq.activo",
                    "limit": 2000,
                },
                timeout=30,
            )
            if r.status_code != 200:
                return 0
            db_props = r.json()
            to_deactivate = [p["id"] for p in db_props if p["hash_dedup"] not in active_hashes]
            if not to_deactivate:
                return 0
            ids_str = ",".join(str(i) for i in to_deactivate)
            r2 = self.session.patch(
                f"{SUPABASE_URL}/rest/v1/propiedades?id=in.({ids_str})",
                headers=self._headers_minimal,
                json={"estado": "inactivo"},
                timeout=20,
            )
            count = len(to_deactivate) if r2.status_code in (200, 204) else 0
            if count:
                logger.info("  Marcadas inactivas: %d propiedades de agencia %d", count, inmob_id)
            return count
        except Exception as e:
            logger.debug("mark_inactivos error: %s", e)
            return 0


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def _http_get(url: str, session: requests.Session, timeout: int = 20,
              use_scraper_on_block: bool = True, **kwargs) -> requests.Response:
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    headers.update(kwargs.pop("headers", {}))
    timeout_value = timeout
    if isinstance(timeout, (int, float)):
        timeout_value = (
            max(1.0, min(float(timeout), 2.5)),
            max(1.0, min(float(timeout), 6.0)),
        )
    r = session.get(url, headers=headers, timeout=timeout_value, verify=False, **kwargs)
    # Si bloqueado y tenemos ScraperAPI, reintentar
    if use_scraper_on_block and r.status_code in (403, 429, 503) and SCRAPERAPI_KEY:
        logger.debug("Bloqueado (%s) → reintentando con ScraperAPI: %s", r.status_code, url)
        r = _scraperapi_get(url, session, timeout)
    return r


def _decode_response_text(response: requests.Response) -> str:
    """Devuelve HTML con encoding razonable para evitar mojibake tipo Ã³."""
    try:
        if not response.encoding or response.encoding.lower() in {"iso-8859-1", "windows-1252"}:
            response.encoding = response.apparent_encoding or "utf-8"
    except Exception:
        pass
    return _fix_mojibake_text(response.text)


def _is_fast_site_down_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(marker in msg for marker in (
        "nameresolutionerror",
        "name or service not known",
        "getaddrinfo failed",
        "temporary failure in name resolution",
        "nodename nor servname provided",
        "failed to resolve",
        "no address associated",
        "connection refused",
        "max retries exceeded",
        "too many 502",
        "too many 503",
        "too many 504",
        "responseerror",
    ))


def _fix_mojibake_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\xa0", " ")
    if "Ã" in text or "Â" in text or "â" in text:
        try:
            repaired = text.encode("latin1", errors="ignore").decode("utf-8", errors="ignore")
            if repaired and len(repaired.strip()) >= max(3, int(len(text.strip()) * 0.6)):
                text = repaired
        except Exception:
            pass
    return re.sub(r"\s+", " ", text).strip()


def _scraperapi_get(url: str, session: requests.Session, timeout: int = 30, js_render: bool = False) -> requests.Response:
    """Request via ScraperAPI — bypass blocks, CAPTCHAs, rate limits."""
    if not SCRAPERAPI_KEY:
        return _http_get(url, session, timeout, use_scraper_on_block=False)
    params = {
        "api_key": SCRAPERAPI_KEY,
        "url": url,
        "country_code": "ar",
    }
    if js_render:
        params["render"] = "true"
    api_url = "https://api.scraperapi.com/"
    scraper_timeout = timeout if timeout <= 12 else timeout + 15
    return session.get(api_url, params=params, timeout=scraper_timeout, verify=False)


_GMAPS_RE = re.compile(
    r"(?:@|maps/place/[^/]*/[@]?|q=|center=|ll=)"
    r"(-?\d{1,3}\.\d{4,}),(-?\d{1,3}\.\d{4,})",
    re.IGNORECASE,
)
_GMAPS_EMBED_RE = re.compile(r'src="[^"]*google\.com/maps/embed[^"]*"', re.IGNORECASE)

def extraer_coordenadas_gmaps(html: str) -> Tuple[Optional[float], Optional[float]]:
    """Extrae lat/lon de iframes de Google Maps embebidos en la página."""
    # Buscar en src del iframe
    for m_src in _GMAPS_EMBED_RE.finditer(html):
        m = _GMAPS_RE.search(m_src.group())
        if m:
            try:
                return float(m.group(1)), float(m.group(2))
            except ValueError:
                pass
    # Buscar en todo el HTML (coordenadas sueltas en JS)
    m = _GMAPS_RE.search(html)
    if m:
        try:
            lat, lon = float(m.group(1)), float(m.group(2))
            # Validar rangos Argentina
            if -55 < lat < -21 and -74 < lon < -53:
                return lat, lon
        except ValueError:
            pass
    return None, None


# ---------------------------------------------------------------------------
# Geocodificación (Nominatim / OpenStreetMap — gratuito)
# ---------------------------------------------------------------------------

_GEO_CACHE: Dict[str, Tuple[Optional[float], Optional[float]]] = {}
_GEO_LOCK_NOM = threading.Lock()
_GEO_LAST_NOM = [0.0]


def geocodificar_direccion(
    direccion: str, ciudad: str = "", provincia: str = ""
) -> Tuple[Optional[float], Optional[float]]:
    """
    Convierte una dirección en lat/lon usando Nominatim (OpenStreetMap).
    Gratuito, sin API key. Límite: 1 req/s.
    Cachea resultados en memoria para evitar llamadas repetidas.
    """
    query = ", ".join(filter(None, [direccion, ciudad, provincia, "Argentina"]))
    cache_key = query.lower().strip()
    if not cache_key or len(cache_key) < 5:
        return None, None

    with _GEO_LOCK_NOM:
        if cache_key in _GEO_CACHE:
            return _GEO_CACHE[cache_key]
        espera = 1.1 - (time.time() - _GEO_LAST_NOM[0])
        if espera > 0:
            time.sleep(espera)

    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": 1, "countrycodes": "ar"},
            headers={"User-Agent": "InmoCapital-Scraper/1.0"},
            timeout=10,
            verify=False,
        )
        with _GEO_LOCK_NOM:
            _GEO_LAST_NOM[0] = time.time()
        if r.status_code == 200 and r.json():
            res = r.json()[0]
            lat, lon = float(res["lat"]), float(res["lon"])
            with _GEO_LOCK_NOM:
                _GEO_CACHE[cache_key] = (lat, lon)
            return lat, lon
    except Exception:
        pass

    with _GEO_LOCK_NOM:
        _GEO_CACHE[cache_key] = (None, None)
    return None, None


_AMENITIES_KW: Dict[str, str] = {
    "pileta": "pileta", "piscina": "pileta", "swimming pool": "pileta",
    "gimnasio": "gimnasio", "gym": "gimnasio",
    "parrilla": "parrilla", "quincho": "quincho",
    "seguridad 24": "seguridad 24hs", "vigilancia 24": "seguridad 24hs",
    "portero": "portero eléctrico",
    "lavandería": "lavandería", "laundry": "lavandería", "lavadero": "lavandería",
    "salón de usos múltiples": "sum", "sum ": "sum",
    "terraza": "terraza", "solarium": "solarium",
    "baulera": "baulera",
    "ascensor": "ascensor", "elevator": "ascensor",
    "jardín": "jardín", "jardin": "jardín",
    "balcón": "balcón", "balcon": "balcón",
    "aire acondicionado": "aire acondicionado",
    "calefacción central": "calefacción central", "calefaccion central": "calefacción central",
    "microcine": "microcine", "home cinema": "microcine",
    "coworking": "coworking",
    "pet friendly": "pet friendly", "mascotas permitidas": "mascotas permitidas",
    "bicicletero": "bicicletero",
    "sauna": "sauna", "spa": "spa",
    "cancha de tenis": "cancha de tenis", "paddle": "paddle",
    "generador": "generador",
    "cochera cubierta": "cochera cubierta",
}


def extraer_amenities_html(soup: BeautifulSoup, page_text: str = "") -> Optional[List[str]]:
    """Extrae amenities de elementos HTML y texto de la página."""
    found: set = set()
    text_lower = (page_text or soup.get_text(" ")).lower()

    for sel in [
        '[class*="ameniti"]', '[class*="comodit"]', '[class*="servicio"]',
        '[class*="caracteristic"]', '[class*="feature"]', 'ul li',
        '.tags span', '[class*="tag"]', '[class*="detail"]',
    ]:
        for el in soup.select(sel):
            txt = el.get_text(strip=True).lower()
            if 2 < len(txt) < 60:
                for kw, label in _AMENITIES_KW.items():
                    if kw in txt:
                        found.add(label)

    for kw, label in _AMENITIES_KW.items():
        if kw in text_lower:
            found.add(label)

    return sorted(found) if found else None


_GROQ_LOCK = threading.Lock()
_GROQ_LAST = [0.0]  # timestamp del último request

def _ai_extraer_propiedad(html_text: str, url: str, inmob: Dict) -> Optional[Dict]:
    """
    Última instancia: usa Groq llama para extraer datos estructurados de HTML limpio.
    Solo se llama cuando todas las otras estrategias fallaron.
    """
    if not GROQ_API_KEY:
        return None

    # Limpiar HTML: quitar scripts, styles, nav, footer
    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
        tag.decompose()
    texto = soup.get_text(" ", strip=True)
    # Truncar a 3500 chars para no exceder contexto
    texto = texto[:3500]

    prompt = f"""Sos un extractor de datos de propiedades inmobiliarias argentinas.
Del siguiente texto de una página web, extraé los datos de la propiedad en JSON.
Si un campo no está disponible, usá null.

Campos requeridos:
- titulo (string): título de la publicación
- precio (number): precio numérico sin símbolos
- moneda (string): "USD" o "ARS"
- tipo_propiedad (string): casa/departamento/ph/local/oficina/terreno/campo/cochera/galpon/deposito/hotel/otro
- operacion (string): venta/alquiler/alquiler_temporario
- ambientes (integer o null)
- dormitorios (integer o null)
- banos (integer o null)
- superficie_total (number o null): metros cuadrados
- superficie_cubierta (number o null): metros cuadrados cubiertos
- direccion (string o null)
- barrio (string o null)
- expensas (number o null)
- agente_nombre (string o null)
- agente_telefono (string o null)

Respondé SOLO con el JSON, sin texto adicional.

TEXTO DE LA PÁGINA:
{texto}"""

    # Rate limit: mínimo 2s entre requests Groq
    with _GROQ_LOCK:
        espera = 2.0 - (time.time() - _GROQ_LAST[0])
        if espera > 0:
            time.sleep(espera)

    try:
        resp = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": GROQ_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 400,
            },
            timeout=20,
        )
        with _GROQ_LOCK:
            _GROQ_LAST[0] = time.time()

        if resp.status_code == 429:
            logger.debug("Groq 429 — saltando AI fallback")
            return None
        if resp.status_code != 200:
            return None

        content = resp.json()["choices"][0]["message"]["content"].strip()
        # Extraer JSON del response
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if not m:
            return None
        data = json.loads(m.group())
    except Exception as e:
        logger.debug("AI extractor error: %s", e)
        return None

    precio = data.get("precio")
    moneda = str(data.get("moneda") or "ARS").upper()
    if moneda not in ("USD", "ARS", "EUR", "UYU"):
        moneda = "ARS"
    precio_float = float(precio) if precio else None

    inmob_id = inmob["id"]
    id_ext = ""
    m2 = re.search(r"/(\d{3,})[/_-]?", url)
    if m2:
        id_ext = m2.group(1)

    prop = {
        "inmobiliaria_id":     inmob_id,
        "url":                 url,
        "id_externo":          id_ext,
        "hash_dedup":          hash_propiedad(inmob_id, id_ext, url),
        "titulo":              str(data.get("titulo") or ""),
        "descripcion":         None,
        "precio":              precio_float,
        "moneda":              moneda,
        "precio_ars":          convertir_precio(precio_float, moneda)[0],
        "precio_usd":          convertir_precio(precio_float, moneda)[1],
        "tipo_propiedad":      normalizar_tipo(data.get("tipo_propiedad")),
        "operacion":           normalizar_operacion(data.get("operacion")),
        "ambientes":           normalizar_int(data.get("ambientes")),
        "dormitorios":         normalizar_int(data.get("dormitorios")),
        "banos":               normalizar_int(data.get("banos")),
        "superficie_total":    normalizar_superficie(data.get("superficie_total")),
        "superficie_cubierta": normalizar_superficie(data.get("superficie_cubierta")),
        "expensas":            normalizar_superficie(data.get("expensas")),
        "direccion":           str(data.get("direccion") or ""),
        "barrio":              str(data.get("barrio") or ""),
        "ciudad":              inmob.get("ciudad", ""),
        "provincia":           inmob.get("provincia", ""),
        "pais":                "Argentina",
        "agente_nombre":       str(data.get("agente_nombre") or "") or None,
        "agente_telefono":     str(data.get("agente_telefono") or "") or None,
        "fuente_extraccion":   "ai_fallback",
        "cms_origen":          inmob.get("cms_detectado", ""),
        "estado":              "activo",
    }
    prop["score_calidad"] = calcular_score(prop)
    logger.info("  ✓ AI extrajo: %s %s %s", prop.get("tipo_propiedad"), prop.get("operacion"), prop.get("precio"))
    return prop


_TEL_RE = re.compile(
    r"(?:tel[eé]fono|celular|cel|whatsapp|contacto|llamar)[:\s]*"
    r"([\+\d\s\-\(\)]{7,20})",
    re.IGNORECASE,
)
_TEL_CLEAN_RE = re.compile(r"[^\d\+]")

def extraer_agente(soup: BeautifulSoup) -> Tuple[Optional[str], Optional[str]]:
    """Extrae nombre del agente y teléfono de contacto del HTML."""
    nombre = None
    telefono = None

    # Nombre del agente
    for sel in ['[class*="agent"]', '[class*="asesor"]', '[class*="broker"]',
                '[class*="vendedor"]', '[class*="contacto"] [class*="nombre"]',
                '[class*="contact"] [class*="name"]']:
        el = soup.select_one(sel)
        if el:
            txt = el.get_text(strip=True)
            if 3 < len(txt) < 60:
                nombre = txt
                break

    # Teléfono
    text = soup.get_text(" ")
    m = _TEL_RE.search(text)
    if m:
        tel = _TEL_CLEAN_RE.sub("", m.group(1))
        if 7 <= len(tel) <= 15:
            telefono = m.group(1).strip()

    # Buscar también en links tel:
    for a in soup.select("a[href^='tel:'], a[href^='callto:']"):
        href = a.get("href", "")
        tel = _TEL_CLEAN_RE.sub("", href.replace("tel:", "").replace("callto:", ""))
        if 7 <= len(tel) <= 15:
            telefono = href.replace("tel:", "").replace("callto:", "").strip()
            break

    # WhatsApp links: wa.me/549XXXXXXXXXX
    if not telefono:
        for a in soup.select("a[href*='wa.me/'], a[href*='api.whatsapp.com/send']"):
            href = a.get("href", "")
            m2 = re.search(r"(?:wa\.me|phone=)[\s/]?(\d{7,15})", href)
            if m2:
                telefono = "+" + m2.group(1)
                break

    return nombre, telefono


def _normalize_image_url(raw_url: Any, base_url: str = "") -> Optional[str]:
    if not raw_url:
        return None
    url = str(raw_url).strip().strip("\"'() ")
    if not url or url.startswith("data:") or url.startswith("blob:"):
        return None
    url = re.sub(r"^url\([\"']?|[\"']?\)$", "", url.strip()).strip()
    if url.startswith("//"):
        scheme = urlparse(base_url).scheme or "https"
        url = f"{scheme}:{url}"
    if base_url:
        if re.match(r"^wp-content/", url, re.I):
            url = "/" + url
        elif re.match(r"^uploads/", url, re.I):
            url = "/wp-content/" + url
        elif re.match(r"^/uploads/", url, re.I):
            url = "/wp-content" + url
    if base_url:
        url = urljoin(base_url, url)
    if not url.startswith(("http://", "https://")):
        return None
    return url


def _image_sort_weight(text: str) -> int:
    weight = 0
    for number in re.findall(r"(?:w|width|h|height|ancho|alto)?[=_-]?(\d{2,5})", str(text or "")):
        try:
            value = int(number)
        except ValueError:
            continue
        if 80 <= value <= 5000:
            weight = max(weight, value)
    return weight


def _extract_srcset_urls(srcset: str, base_url: str = "") -> List[str]:
    candidates: List[Tuple[int, str]] = []
    for part in str(srcset or "").split(","):
        tokens = part.strip().split()
        if not tokens:
            continue
        url = _normalize_image_url(tokens[0], base_url)
        if url:
            candidates.append((_image_sort_weight(part), url))
    candidates.sort(reverse=True)
    return [url for _, url in candidates]


def fake_property_image_reason(image_url: Any) -> Optional[str]:
    url = _normalize_image_url(image_url) or str(image_url or "")
    low = unquote(url.lower())
    if not low:
        return "empty_url"
    parsed = urlparse(low)
    path = parsed.path or low
    filename = path.rsplit("/", 1)[-1]
    if path.endswith((".svg", ".ico")):
        return "svg_or_icon_file"
    has_image_extension = bool(re.search(r"\.(?:jpe?g|png|webp|avif)(?:[?#]|$)", path, re.I))
    known_photo_host_path = any(marker in low for marker in (
        "static.tokkobroker.com/water_pics/",
        "static.tokkobroker.com/w_pics/",
        "static.tokkobroker.com/thumbs/",
        "/wp-content/uploads/",
    ))
    if not has_image_extension and not known_photo_host_path:
        return "not_image_url"
    if "/wp-content/themes/" in low or "/wp-content/plugins/" in low:
        return "theme_or_plugin_asset"
    if filename.startswith("cropped-") or "mesa-de-trabajo" in filename:
        return "logo_or_brand"
    if "banner" in filename and "/wp-content/uploads/" not in low:
        return "theme_or_plugin_asset"
    if re.search(r"(?:^|[\/_.-])360(?:[\/_.-]|$)", low):
        return "tour_360"
    for width, height in re.findall(r"(?<!\d)(\d{1,4})[xX](\d{1,4})(?!\d)", low):
        try:
            if int(width) < 180 and int(height) < 180:
                return "tiny_image_dimensions"
        except Exception:
            continue
    for pattern in FALSE_IMAGE_PATTERNS:
        if pattern in low:
            if "prop-icons" in pattern or "sup" in pattern:
                return "tokko_prop_icon"
            if "placeholder" in pattern or "no-photo" in pattern or "no_image" in pattern or "sin-imagen" in pattern:
                return "placeholder"
            if "logo" in pattern or "isotipo" in pattern or "brand" in pattern:
                return "logo_or_brand"
            if "avatar" in pattern:
                return "avatar"
            if "map" in pattern:
                return "map_or_location"
            return "false_image_pattern"
    if re.search(r"(?:icon|ico|amenity|surface|superficie|map)[-_]?\d*\.(?:png|jpe?g|webp|gif)$", path):
        return "icon_or_surface_asset"
    return None


def is_fake_property_image_url(image_url: Any) -> bool:
    return fake_property_image_reason(image_url) is not None


def clean_property_images(
    image_urls: List[Any],
    base_url: str = "",
    stats: Optional[Dict[str, Any]] = None,
) -> List[str]:
    seen: set = set()
    real_images: List[str] = []
    for raw_url in image_urls:
        url = _normalize_image_url(raw_url, base_url)
        if not url or url in seen:
            continue
        seen.add(url)
        fake_reason = fake_property_image_reason(url)
        if fake_reason:
            if stats is not None:
                stats["imagenes_falsas_descartadas"] = int(stats.get("imagenes_falsas_descartadas") or 0) + 1
                by_reason = stats.setdefault("imagenes_descartadas_por_motivo", {})
                by_reason[fake_reason] = int(by_reason.get(fake_reason) or 0) + 1
                examples = stats.setdefault("ejemplos_descartados", [])
                if len(examples) < TOKKO_FAKE_IMAGE_EXAMPLES_LIMIT:
                    examples.append({"url": url, "motivo": fake_reason})
            continue
        real_images.append(url)
        if stats is not None:
            stats["imagenes_reales_detectadas"] = int(stats.get("imagenes_reales_detectadas") or 0) + 1
            examples = stats.setdefault("ejemplos_reales", [])
            if len(examples) < TOKKO_REAL_IMAGE_EXAMPLES_LIMIT:
                examples.append(url)
    return real_images[:60]


def _new_update_protection_stats() -> Dict[str, Any]:
    return {
        "actualizaciones_seguras": 0,
        "coordenadas_conservadas": 0,
        "imagenes_conservadas": 0,
        "campos_protegidos_de_null": 0,
        "campos_invalidos_omitidos": 0,
        "campos_protegidos_por_nombre": {},
        "coordenadas_descartadas_por_outlier": 0,
        "coordenadas_sin_regla_ciudad": 0,
        "coordenadas_outlier_ejemplos": [],
        "precios_descartados_por_invalido": 0,
        "precios_normalizados_descartados": 0,
        "precios_invalidos_ejemplos": [],
        "ubicaciones_normalizadas": 0,
        "ubicaciones_normalizadas_ejemplos": [],
        "integers_descartados_por_invalido": 0,
        "integers_invalidos_ejemplos": [],
        "dedup_por_url_normalizada": 0,
        "dedup_por_id_externo": 0,
        "dedup_por_hash": 0,
        "dedup_existing_duplicados": 0,
        "dedup_existing_duplicados_ejemplos": [],
        "ubicacion_fallback_from_agency": 0,
        "fallback_ciudad_from_agency": 0,
        "fallback_provincia_from_agency": 0,
        "ubicacion_fallback_from_agency_ejemplos": [],
        "ubicaciones_encoding_corregidas": 0,
        "ubicaciones_encoding_corregidas_ejemplos": [],
    }


def _is_blank_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def _positive_number(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _numeric_or_none(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _record_invalid_integer(
    stats: Optional[Dict[str, Any]],
    prop: Dict[str, Any],
    field: str,
    value: Any,
    reason: str,
) -> None:
    if stats is None:
        return
    stats["integers_descartados_por_invalido"] = int(stats.get("integers_descartados_por_invalido") or 0) + 1
    examples = stats.setdefault("integers_invalidos_ejemplos", [])
    if len(examples) < 12:
        examples.append({
            "integer_descartado_por_invalido": True,
            "campo": field,
            "reason": reason,
            "valor_original": value,
            "url": prop.get("url"),
            "estrategia_usada": prop.get("fuente_extraccion") or prop.get("_strategy_name"),
        })


def _reasonable_integer_or_none(
    value: Any,
    min_value: int,
    max_value: int,
) -> Tuple[Optional[int], Optional[str]]:
    if value is None or isinstance(value, bool):
        return None, None
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            return None, "no_es_entero"
        parsed = int(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None, None
        # Evita strings contaminados por concatenacion de muchos numeros.
        digits_only = re.sub(r"\D", "", text)
        if len(digits_only) > 4:
            return None, "string_numerico_concatenado"
        if not re.fullmatch(r"-?\d+(?:\.0+)?", text):
            return None, "formato_no_entero"
        parsed = int(float(text))
    else:
        return None, "tipo_no_entero"

    if parsed < min_value or parsed > max_value:
        return None, f"fuera_de_rango_{min_value}_{max_value}"
    return parsed, None


def sanitize_property_integers(prop: Dict[str, Any], stats: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Descarta enteros contaminados antes de insertar o actualizar."""
    for field, (min_value, max_value) in PROPERTY_INTEGER_RANGES.items():
        if field not in prop:
            continue
        original = prop.get(field)
        parsed, reason = _reasonable_integer_or_none(original, min_value, max_value)
        if reason:
            _record_invalid_integer(stats, prop, field, original, reason)
            prop[field] = None
        elif parsed is not None:
            prop[field] = parsed
        else:
            prop[field] = None
    return prop


def _record_invalid_price(
    stats: Optional[Dict[str, Any]],
    prop: Dict[str, Any],
    field: str,
    value: Any,
    reason: str,
) -> None:
    if stats is None:
        return
    if field == "precio":
        stats["precios_descartados_por_invalido"] = int(stats.get("precios_descartados_por_invalido") or 0) + 1
    else:
        stats["precios_normalizados_descartados"] = int(stats.get("precios_normalizados_descartados") or 0) + 1
    examples = stats.setdefault("precios_invalidos_ejemplos", [])
    if len(examples) < 12:
        examples.append({
            "precio_descartado_por_invalido": True,
            "field": field,
            "reason": reason,
            "precio_original": value,
            "precio": prop.get("precio"),
            "precio_usd": prop.get("precio_usd"),
            "precio_ars": prop.get("precio_ars"),
            "moneda": prop.get("moneda"),
            "url": prop.get("url"),
            "estrategia_usada": prop.get("fuente_extraccion") or prop.get("_strategy_name"),
        })


def _is_invalid_public_price(price: Any, currency: Any) -> Tuple[bool, str]:
    value = _numeric_or_none(price)
    if value is None:
        return False, "null"
    if value <= MIN_VALID_PUBLIC_PRICE:
        return True, "precio_menor_o_igual_a_1"
    currency_code = str(currency or "").upper()
    if currency_code == "USD" and value > MAX_VALID_PRICE_USD:
        return True, "precio_usd_publicado_absurdo"
    if currency_code == "ARS" and value > MAX_VALID_PRICE_ARS:
        return True, "precio_ars_publicado_absurdo"
    return False, "ok"


def sanitize_property_prices(prop: Dict[str, Any], stats: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Normaliza precios invalidos antes de insertar o actualizar propiedades."""
    price = prop.get("precio")
    currency = prop.get("moneda")
    invalid_price, reason = _is_invalid_public_price(price, currency)
    if invalid_price:
        _record_invalid_price(stats, prop, "precio", price, reason)
        prop["precio"] = None
        prop["precio_usd"] = None
        prop["precio_ars"] = None
        return prop

    price_usd = _numeric_or_none(prop.get("precio_usd"))
    if price_usd is not None and price_usd > MAX_VALID_PRICE_USD:
        _record_invalid_price(stats, prop, "precio_usd", prop.get("precio_usd"), "precio_usd_normalizado_absurdo")
        prop["precio_usd"] = None

    price_ars = _numeric_or_none(prop.get("precio_ars"))
    if price_ars is not None and price_ars > MAX_VALID_PRICE_ARS:
        _record_invalid_price(stats, prop, "precio_ars", prop.get("precio_ars"), "precio_ars_normalizado_absurdo")
        prop["precio_ars"] = None

    return prop


def _location_text_key(*values: Any) -> str:
    text = " ".join(str(value or "") for value in values)
    text = unquote(text)
    text = re.sub(r"https?://\S+", lambda m: urlparse(m.group(0)).path, text)
    text = text.replace("_", " ").replace("-", " ").replace("/", " ")
    return _coordinate_location_key(text)


_LOCATION_ALIASES: List[Dict[str, Any]] = [
    {
        "aliases": (
            "potrero de los funes",
            "potrero-de-los-funes",
            "potrero de los funes san luis",
            "potrero de los funes, san luis",
        ),
        "ciudad": "Potrero de los Funes",
        "provincia": "San Luis",
        "motivo": "titulo_url_contiene_potrero_de_los_funes",
        "specific": True,
    },
    {
        "aliases": (
            "potrero de garay",
            "potrero-de-garay",
            "potrero de garay cordoba",
            "potrero de garay, cordoba",
        ),
        "ciudad": "Potrero de Garay",
        "provincia": "Córdoba",
        "motivo": "titulo_url_contiene_potrero_de_garay",
        "specific": True,
        "clear_barrio": True,
    },
    {
        "aliases": ("bahia blanca", "bah\u00eda blanca", "bahia-blanca"),
        "ciudad": "Bah\u00eda Blanca",
        "provincia": "Buenos Aires",
        "motivo": "titulo_url_contiene_bahia_blanca",
        "specific": True,
    },
    {
        "aliases": ("san jose del rincon", "san jose rincon", "san josé del rincón"),
        "ciudad": "San José del Rincón",
        "provincia": "Santa Fe",
    },
    {
        "aliases": ("villa carlos paz",),
        "ciudad": "Villa Carlos Paz",
        "provincia": "Córdoba",
    },
    {
        "aliases": ("san carlos de bariloche", "bariloche"),
        "ciudad": "San Carlos de Bariloche",
        "provincia": "Río Negro",
    },
    {
        "aliases": ("pueblo esther",),
        "ciudad": "Pueblo Esther",
        "provincia": "Santa Fe",
    },
    {
        "aliases": ("roldan", "roldán"),
        "ciudad": "Roldán",
        "provincia": "Santa Fe",
    },
    {
        "aliases": ("rafaela",),
        "ciudad": "Rafaela",
        "provincia": "Santa Fe",
    },
    {
        "aliases": ("cosquin", "cosquín"),
        "ciudad": "Cosquín",
        "provincia": "Córdoba",
    },
    {
        "aliases": ("mar del tuyu", "mar del tuyÃº"),
        "ciudad": "Mar del TuyÃº",
        "provincia": "Buenos Aires",
    },
    {
        "aliases": ("san justo",),
        "ciudad": "San Justo",
        "provincia": "Buenos Aires",
    },
    {
        "aliases": ("mataderos",),
        "ciudad": "Mataderos",
        "provincia": "Capital Federal",
    },
    {
        "aliases": ("tandil",),
        "ciudad": "Tandil",
        "provincia": "Buenos Aires",
    },
    {
        "aliases": ("capital federal", "caba", "ciudad autonoma de buenos aires"),
        "ciudad": "Capital Federal",
        "provincia": "Capital Federal",
    },
    {
        "aliases": ("barracas",),
        "ciudad": "Barracas",
        "provincia": "Capital Federal",
    },
    {
        "aliases": ("sarandi", "sarandÃ­"),
        "ciudad": "SarandÃ­",
        "provincia": "Buenos Aires",
    },
    {
        "aliases": ("wilde",),
        "ciudad": "Wilde",
        "provincia": "Buenos Aires",
    },
    {
        "aliases": ("gerli",),
        "ciudad": "Gerli",
        "provincia": "Buenos Aires",
    },
    {
        "aliases": ("lanus", "lanÃºs"),
        "ciudad": "LanÃºs",
        "provincia": "Buenos Aires",
    },
    {
        "aliases": ("pineyro", "pi\u00f1eyro"),
        "ciudad": "Pi\u00f1eyro",
        "provincia": "Buenos Aires",
    },
    {
        "aliases": ("remedios de escalada",),
        "ciudad": "Remedios de Escalada",
        "provincia": "Buenos Aires",
    },
    {
        "aliases": ("monsenor piaggio", "monse\u00f1or piaggio"),
        "ciudad": "Monse\u00f1or Piaggio",
        "provincia": "Buenos Aires",
    },
    {
        "aliases": ("quilmes",),
        "ciudad": "Quilmes",
        "provincia": "Buenos Aires",
    },
    {
        "aliases": ("brandsen",),
        "ciudad": "Brandsen",
        "provincia": "Buenos Aires",
    },
    {
        "aliases": ("san vicente",),
        "ciudad": "San Vicente",
        "provincia": "Buenos Aires",
    },
    {
        "aliases": ("avellaneda",),
        "ciudad": "Avellaneda",
        "provincia": "Buenos Aires",
    },
]


def _text_contains_location_alias(text: str, alias: str) -> bool:
    alias_key = _coordinate_location_key(alias)
    if not alias_key:
        return False
    return bool(re.search(rf"\b{re.escape(alias_key)}\b", text))


AMBIGUOUS_LOCATION_STREET_NAMES = {"roldan", "brandsen"}


def _has_alias_street_context(text: str, alias_key: str) -> bool:
    if alias_key not in AMBIGUOUS_LOCATION_STREET_NAMES:
        return False
    if alias_key == "roldan" and re.search(r"\bbelisario\s+roldan\b", text):
        return True
    return bool(
        re.search(rf"\b(?:calle|av|avenida|bv|boulevard|pasaje)\s+{re.escape(alias_key)}\b", text)
        or re.search(rf"\b{re.escape(alias_key)}\s+(?:al\s+)?\d{{2,5}}\b", text)
    )


_FUNES_CITY_CONTEXT_ALIASES = (
    "funes city",
    "funes town",
    "funes hills",
    "funes norte",
    "haras de funes",
    "vida club de campo funes",
    "kentucky funes",
    "cantegril funes",
    "aguadas funes",
    "don mateo funes",
)

_GENERIC_MAR_DEL_PLATA_SOURCE_CITY_KEYS = {
    "",
    "costa atlantica",
    "costa argentina",
    "buenos aires",
}

_ROSARIO_CITY_CONTEXT_BARRIOS = (
    "pichincha",
    "echesortu",
    "fisherton",
    "refineria",
    "arroyito",
    "alberdi",
    "abasto",
    "martin",
    "luis agote",
    "nuestra senora de lourdes",
)


def _has_funes_street_context(text: str) -> bool:
    """Evita confundir calles/personas llamadas Funes con la ciudad Funes."""
    if re.search(r"\bfunes\s+(?:al\s+)?\d{2,5}\b", text):
        return True
    return bool(re.search(r"\b(?:dean|pedro\s+lino|jose\s+roque)\s+funes\b", text))


def _has_funes_city_signal(text: str, ciudad: Any = None, provincia: Any = None, barrio: Any = None) -> bool:
    if _text_contains_location_alias(text, "potrero de los funes"):
        return False
    current_city_key = _coordinate_location_key(ciudad)
    current_province_key = _coordinate_location_key(provincia)
    barrio_key = _location_text_key(barrio)

    if current_city_key == "funes":
        return True

    if _has_funes_street_context(text):
        return False

    if current_province_key == "santa fe" and any(alias in barrio_key for alias in _FUNES_CITY_CONTEXT_ALIASES):
        return True

    if re.search(r"\bfunes\s*,\s*santa\s+fe\b", text):
        return True
    if re.search(r"\ben\s+funes\b(?!\s*(?:al\s+)?\d)", text):
        return True
    if re.search(r"\bcountries?\s+b\s+cerrado\s+funes\b", text):
        return True
    return any(_text_contains_location_alias(text, alias) for alias in _FUNES_CITY_CONTEXT_ALIASES)


def _has_rosario_street_context(text: str) -> bool:
    if re.search(r"\brosario\s+(?:al\s+)?\d{1,5}\b", text):
        return True
    return bool(re.search(r"\bcalle\s+rosario\b", text))


def _has_rosario_city_signal(text: str, ciudad: Any = None, provincia: Any = None, barrio: Any = None) -> bool:
    current_city_key = _coordinate_location_key(ciudad)
    current_province_key = _coordinate_location_key(provincia)
    barrio_key = _location_text_key(barrio)

    if current_city_key == "rosario":
        return True

    if _has_rosario_street_context(text):
        return False

    if re.search(r"\brosario\s*,\s*santa\s+fe\b", text):
        return True

    if current_province_key == "santa fe" and re.search(r"\b(?:en|ubicad[oa]\s+en)\s+rosario\b", text):
        return True

    if re.search(r"\b(?:venta|alquiler)\s+(?:/\s*(?:venta|alquiler)\s+)?en\s+rosario\b", text):
        return True

    return current_province_key == "santa fe" and any(alias in barrio_key for alias in _ROSARIO_CITY_CONTEXT_BARRIOS)


def _has_mar_del_plata_street_context(text: str) -> bool:
    if re.search(r"\bmar\s+del\s+plata\s+(?:al\s+)?\d{1,5}\b", text):
        return True
    return bool(re.search(r"\b(?:y|esquina|esq|interseccion|intersecci[oó]n)\s+mar\s+del\s+plata\b", text))


def _has_mar_del_plata_city_signal(text: str, ciudad: Any = None, provincia: Any = None) -> bool:
    current_city_key = _coordinate_location_key(ciudad)

    if _has_mar_del_plata_street_context(text):
        return False

    if current_city_key == "mar del plata":
        return True

    if re.search(r"\bmar\s+del\s+plata\s*,\s*buenos\s+aires\b", text):
        return True

    if re.search(r"\b(?:en|ubicad[oa]\s+en)\s+mar\s+del\s+plata\b", text):
        return True

    return current_city_key in _GENERIC_MAR_DEL_PLATA_SOURCE_CITY_KEYS and _text_contains_location_alias(text, "mar del plata")


def _detect_location_from_text(
    titulo: Any,
    url: Any,
    direccion: Any = None,
    barrio: Any = None,
    descripcion: Any = None,
    ciudad: Any = None,
    provincia: Any = None,
    pais: Any = None,
) -> Optional[Dict[str, str]]:
    text = _location_text_key(titulo, url, direccion, barrio, descripcion, ciudad, provincia, pais)
    if not text:
        return None

    if _text_contains_location_alias(text, "potrero de los funes"):
        return {
            "ciudad": "Potrero de los Funes",
            "provincia": "San Luis",
            "motivo": "titulo_url_contiene_potrero_de_los_funes",
        }

    if _text_contains_location_alias(text, "potrero de garay"):
        return {
            "ciudad": "Potrero de Garay",
            "provincia": "Córdoba",
            "motivo": "titulo_url_contiene_potrero_de_garay",
            "clear_barrio": True,
        }

    if re.search(r"\b(?:en|ubicad[oa]\s+en)\s+santa\s+fe\s+(?:la\s+capital|capital)\b", text) or "ciudad de santa fe" in text:
        return {"ciudad": "Santa Fe", "provincia": "Santa Fe", "motivo": "titulo_url_santa_fe_la_capital"}

    if (
        re.search(r"\b(?:en|ubicad[oa]\s+en)\s+cordoba\s+capital\b", text)
        and not _text_contains_location_alias(text, "potrero de garay")
    ):
        return {"ciudad": "Córdoba", "provincia": "Córdoba", "motivo": "titulo_url_cordoba_capital"}

    if re.search(r"\b(?:en|ubicad[oa]\s+en)\s+9\s+de\s+julio\b(?!\s+\d)", text):
        return {"ciudad": "9 de Julio", "provincia": "Buenos Aires", "motivo": "titulo_url_9_de_julio"}

    if _has_rosario_city_signal(text, ciudad=ciudad, provincia=provincia, barrio=barrio):
        return {"ciudad": "Rosario", "provincia": "Santa Fe", "motivo": "titulo_url_contiene_rosario"}

    if _has_mar_del_plata_city_signal(text, ciudad=ciudad, provincia=provincia):
        return {"ciudad": "Mar del Plata", "provincia": "Buenos Aires", "motivo": "titulo_url_contiene_mar_del_plata"}

    if _text_contains_location_alias(text, "belen de escobar"):
        return {"ciudad": "Belen de Escobar", "provincia": "Buenos Aires", "motivo": "titulo_url_contiene_belen_de_escobar"}

    if _has_funes_city_signal(text, ciudad=ciudad, provincia=provincia, barrio=barrio):
        return {"ciudad": "Funes", "provincia": "Santa Fe", "motivo": "titulo_url_contiene_funes"}

    for rule in _LOCATION_ALIASES:
        for alias in rule["aliases"]:
            alias_key = _coordinate_location_key(alias)
            blocked_aliases = rule.get("blocked_if_contains") or ()
            if any(_text_contains_location_alias(text, blocked) for blocked in blocked_aliases):
                continue
            if _has_alias_street_context(text, alias_key):
                continue
            if re.search(rf"\b{re.escape(alias_key)}\b", text):
                return {
                    "ciudad": rule["ciudad"],
                    "provincia": rule["provincia"],
                    "motivo": rule.get("motivo") or f"titulo_url_contiene_{alias_key.replace(' ', '_')}",
                    "clear_barrio": bool(rule.get("clear_barrio")),
                }
    return None


def _detect_location_from_title_or_url(titulo: Any, url: Any) -> Optional[Dict[str, str]]:
    return _detect_location_from_text(titulo=titulo, url=url)


def _is_suspicious_location_value(value: Any) -> bool:
    return _coordinate_location_key(value) in {
        "santa fe",
        "la capital",
        "rio negro",
        "buenos aires",
        "g b a",
        "gba",
        "g b a zona sur",
        "gba zona sur",
        "gran buenos aires",
        "gran buenos aires zona sur",
        "zona sur",
        "zona norte",
        "zona oeste",
        "castellanos",
        "punilla",
        "maldonado",
    }


def normalize_location_fields(
    titulo: Any,
    direccion: Any,
    barrio: Any,
    ciudad: Any,
    provincia: Any,
    pais: Any,
    url: Any,
    descripcion: Any = None,
) -> Dict[str, Any]:
    detected = _detect_location_from_text(
        titulo=titulo,
        url=url,
        direccion=direccion,
        barrio=barrio,
        descripcion=descripcion,
        ciudad=ciudad,
        provincia=provincia,
        pais=pais,
    )
    current_city = str(ciudad or "").strip()
    current_province = str(provincia or "").strip()
    current_country = str(pais or "Argentina").strip() or "Argentina"
    current_barrio = str(barrio or "").strip()
    result = {
        "ciudad": current_city,
        "provincia": current_province,
        "barrio": current_barrio,
        "pais": current_country,
        "location_normalized": False,
        "motivo": None,
    }
    if not detected:
        return result

    detected_city = canonicalize_location_name(detected["ciudad"])
    detected_province = canonicalize_location_name(detected["provincia"])
    current_city_key = _coordinate_location_key(current_city)
    detected_city_key = _coordinate_location_key(detected_city)
    current_province_key = _coordinate_location_key(current_province)
    detected_province_key = _coordinate_location_key(detected_province)

    should_update_city = (
        not current_city_key
        or current_city_key != detected_city_key
        or (current_city_key == detected_city_key and current_city != detected_city)
        or (_is_suspicious_location_value(current_city) and current_city_key != detected_city_key)
    )
    should_update_province = (
        not current_province_key
        or current_province_key != detected_province_key
        or (current_province_key == detected_province_key and current_province != detected_province)
        or (_is_suspicious_location_value(current_province) and current_province_key != detected_province_key)
    )

    should_clear_barrio = bool(detected.get("clear_barrio")) and bool(current_barrio)

    if (
        not should_update_city
        and not should_update_province
        and not should_clear_barrio
        and _coordinate_location_key(current_country) == "argentina"
    ):
        return result

    result.update({
        "ciudad": detected_city if should_update_city else current_city,
        "provincia": detected_province if should_update_province else current_province,
        "barrio": None if detected.get("clear_barrio") else current_barrio,
        "pais": "Argentina",
        "location_normalized": True,
        "ciudad_original": current_city,
        "provincia_original": current_province,
        "barrio_original": current_barrio,
        "ciudad_final": detected_city if should_update_city else current_city,
        "provincia_final": detected_province if should_update_province else current_province,
        "barrio_final": None if detected.get("clear_barrio") else current_barrio,
        "motivo": detected.get("motivo") or "titulo_url_ciudad_clara",
        "clear_barrio": bool(detected.get("clear_barrio")),
    })
    return result


def _record_location_normalization(stats: Optional[Dict[str, Any]], prop: Dict[str, Any], normalized: Dict[str, Any]) -> None:
    if stats is None or not normalized.get("location_normalized"):
        return
    stats["ubicaciones_normalizadas"] = int(stats.get("ubicaciones_normalizadas") or 0) + 1
    examples = stats.setdefault("ubicaciones_normalizadas_ejemplos", [])
    if len(examples) < 12:
        examples.append({
            "location_normalized": True,
            "ciudad_original": normalized.get("ciudad_original"),
            "provincia_original": normalized.get("provincia_original"),
            "ciudad_detectada_from_text": normalized.get("ciudad_final"),
            "provincia_detectada_from_text": normalized.get("provincia_final"),
            "ciudad_final": normalized.get("ciudad_final"),
            "provincia_final": normalized.get("provincia_final"),
            "barrio_original": normalized.get("barrio_original"),
            "barrio_final": normalized.get("barrio_final"),
            "motivo": normalized.get("motivo"),
            "titulo": prop.get("titulo"),
            "url": prop.get("url"),
            "estrategia_usada": prop.get("fuente_extraccion") or prop.get("_strategy_name"),
        })


def sanitize_property_location(prop: Dict[str, Any], stats: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    normalized = normalize_location_fields(
        prop.get("titulo"),
        prop.get("direccion"),
        prop.get("barrio"),
        prop.get("ciudad"),
        prop.get("provincia"),
        prop.get("pais"),
        prop.get("url"),
        prop.get("descripcion"),
    )
    if not normalized.get("location_normalized"):
        return prop
    _record_location_normalization(stats, prop, normalized)
    prop["ciudad"] = normalized.get("ciudad")
    prop["provincia"] = normalized.get("provincia")
    if normalized.get("clear_barrio"):
        prop["barrio"] = None
    prop["pais"] = normalized.get("pais") or "Argentina"
    prop["_location_normalized"] = True
    prop["_location_normalization_motivo"] = normalized.get("motivo")
    prop["_ciudad_detectada_from_text"] = normalized.get("ciudad_final")
    prop["_provincia_detectada_from_text"] = normalized.get("provincia_final")
    prop["_clear_barrio_due_location_normalization"] = bool(normalized.get("clear_barrio"))
    motivo = str(normalized.get("motivo") or "")
    if motivo == "titulo_url_contiene_potrero_de_garay":
        logger.info(
            "[NORMALIZE_LOCATION] Potrero de Garay corregido: ciudad_anterior=%s provincia_anterior=%s ciudad_final=%s provincia_final=%s url=%s",
            normalized.get("ciudad_original") or "-",
            normalized.get("provincia_original") or "-",
            normalized.get("ciudad_final"),
            normalized.get("provincia_final"),
            prop.get("url"),
        )
    elif motivo == "titulo_url_contiene_potrero_de_los_funes":
        logger.info(
            "[NORMALIZE_LOCATION] Potrero de los Funes corregido: ciudad_anterior=%s provincia_anterior=%s ciudad_final=%s provincia_final=%s url=%s",
            normalized.get("ciudad_original") or "-",
            normalized.get("provincia_original") or "-",
            normalized.get("ciudad_final"),
            normalized.get("provincia_final"),
            prop.get("url"),
        )
    else:
        logger.info(
            "  Ubicacion normalizada | %s, %s -> %s, %s | motivo=%s | url=%s",
            normalized.get("ciudad_original") or "-",
            normalized.get("provincia_original") or "-",
            normalized.get("ciudad_final"),
            normalized.get("provincia_final"),
            normalized.get("motivo"),
            prop.get("url"),
        )
    return prop


GENERIC_CITY_FOR_AGENCY_FALLBACK = {
    "",
    "-",
    "g b a",
    "gba",
    "g b a zona sur",
    "gba zona sur",
    "gran buenos aires",
    "gran buenos aires zona sur",
    "zona sur",
    "zona norte",
    "zona oeste",
    "buenos aires",
    "provincia de buenos aires",
    "argentina",
}


def _needs_agency_city_fallback(value: Any) -> bool:
    key = _coordinate_location_key(value)
    return not key or key in GENERIC_CITY_FOR_AGENCY_FALLBACK


def _needs_agency_province_fallback(value: Any) -> bool:
    return not _useful_text(value)


def _record_agency_location_fallback(
    stats: Optional[Dict[str, Any]],
    prop: Dict[str, Any],
    agency_context: Dict[str, Any],
    fallback_city: bool,
    fallback_province: bool,
) -> None:
    if stats is None or not (fallback_city or fallback_province):
        return
    stats["ubicacion_fallback_from_agency"] = int(stats.get("ubicacion_fallback_from_agency") or 0) + 1
    if fallback_city:
        stats["fallback_ciudad_from_agency"] = int(stats.get("fallback_ciudad_from_agency") or 0) + 1
    if fallback_province:
        stats["fallback_provincia_from_agency"] = int(stats.get("fallback_provincia_from_agency") or 0) + 1
    examples = stats.setdefault("ubicacion_fallback_from_agency_ejemplos", [])
    if len(examples) < 12:
        examples.append({
            "ubicacion_fallback_from_agency": True,
            "fallback_ciudad_from_agency": fallback_city,
            "fallback_provincia_from_agency": fallback_province,
            "ciudad_detectada_from_text": prop.get("_ciudad_detectada_from_text"),
            "provincia_detectada_from_text": prop.get("_provincia_detectada_from_text"),
            "ciudad_original": prop.get("_original_city_before_agency_fallback"),
            "provincia_original": prop.get("_original_province_before_agency_fallback"),
            "ciudad_final": prop.get("ciudad"),
            "provincia_final": prop.get("provincia"),
            "agency_id": agency_context.get("id"),
            "agency_nombre": agency_context.get("nombre"),
            "agency_ciudad": agency_context.get("ciudad"),
            "agency_provincia": agency_context.get("provincia"),
            "titulo": prop.get("titulo"),
            "url": prop.get("url"),
        })


def apply_agency_location_fallback(prop: Dict[str, Any], stats: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Completa ciudad/provincia desde inmobiliarias_main solo cuando la propiedad no trae dato util."""
    agency_context = prop.get("_agency_location_context")
    if not isinstance(agency_context, dict):
        return prop

    agency_city = str(agency_context.get("ciudad") or "").strip()
    agency_province = str(agency_context.get("provincia") or "").strip()
    agency_country = str(agency_context.get("pais") or "").strip() or "Argentina"
    if not agency_city and not agency_province:
        return prop

    original_city = prop.get("ciudad")
    original_province = prop.get("provincia")
    fallback_city = bool(agency_city and _needs_agency_city_fallback(original_city))
    fallback_province = bool(agency_province and _needs_agency_province_fallback(original_province))

    if not fallback_city and not fallback_province:
        return prop

    prop["_original_city_before_agency_fallback"] = original_city
    prop["_original_province_before_agency_fallback"] = original_province
    if fallback_city:
        prop["ciudad"] = agency_city
    if fallback_province:
        prop["provincia"] = agency_province
    if not _useful_text(prop.get("pais")):
        prop["pais"] = agency_country
    prop["_ubicacion_fallback_from_agency"] = True
    prop["_fallback_ciudad_from_agency"] = fallback_city
    prop["_fallback_provincia_from_agency"] = fallback_province
    _record_agency_location_fallback(stats, prop, agency_context, fallback_city, fallback_province)
    return prop


def _useful_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


CANONICAL_LOCATION_NAMES = {
    "sarandi": "Sarand\u00ed",
    "lanus": "Lan\u00fas",
    "mar del tuyu": "Mar del Tuy\u00fa",
    "pineyro": "Pi\u00f1eyro",
    "pin eyro": "Pi\u00f1eyro",
    "remedios de escalada": "Remedios de Escalada",
    "san martin": "San Mart\u00edn",
    "monsenor piaggio": "Monse\u00f1or Piaggio",
    "monse or piaggio": "Monse\u00f1or Piaggio",
    "bahia blanca": "Bah\u00eda Blanca",
    "cordoba": "C\u00f3rdoba",
    "rio negro": "R\u00edo Negro",
    "san jose del rincon": "San Jos\u00e9 del Rinc\u00f3n",
    "roldan": "Rold\u00e1n",
    "cosquin": "Cosqu\u00edn",
    "mar del plata": "Mar del Plata",
    "capital federal": "Capital Federal",
    "buenos aires": "Buenos Aires",
    "santa fe": "Santa Fe",
    "san luis": "San Luis",
}


def _repair_mojibake_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    repaired = text
    for _ in range(3):
        if not any(marker in repaired for marker in ("Ã", "Â", "â")):
            break
        candidate = None
        for encoding in ("latin1", "cp1252"):
            try:
                decoded = repaired.encode(encoding).decode("utf-8")
            except UnicodeError:
                continue
            if decoded != repaired:
                candidate = decoded
                break
        if candidate is None:
            break
        repaired = candidate
    return repaired.strip()


def canonicalize_location_name(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    repaired = _repair_mojibake_text(value)
    key = _coordinate_location_key(repaired)
    return CANONICAL_LOCATION_NAMES.get(key, repaired)


def normalize_property_location_encoding(prop: Dict[str, Any], stats: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    for field in ("ciudad", "provincia", "barrio"):
        original = prop.get(field)
        if not isinstance(original, str) or not original.strip():
            continue
        normalized = canonicalize_location_name(original)
        if normalized == original:
            continue
        prop[field] = normalized
        if field == "ciudad":
            prop["_ciudad_encoding_normalizada"] = normalized
            if prop.get("_ciudad_detectada_from_text") == original:
                prop["_ciudad_detectada_from_text"] = normalized
        elif field == "provincia":
            prop["_provincia_encoding_normalizada"] = normalized
            if prop.get("_provincia_detectada_from_text") == original:
                prop["_provincia_detectada_from_text"] = normalized
        if stats is not None:
            stats["ubicaciones_encoding_corregidas"] = int(stats.get("ubicaciones_encoding_corregidas") or 0) + 1
            examples = stats.setdefault("ubicaciones_encoding_corregidas_ejemplos", [])
            if len(examples) < 12:
                examples.append({
                    "field": field,
                    "valor_original": original,
                    "valor_normalizado": normalized,
                    "titulo": prop.get("titulo"),
                    "url": prop.get("url"),
                    "estrategia_usada": prop.get("fuente_extraccion") or prop.get("_strategy_name"),
                })
    return prop


def _valid_coordinate_pair(values: Dict[str, Any]) -> bool:
    try:
        lat = float(values.get("latitud"))
        lon = float(values.get("longitud"))
    except (TypeError, ValueError):
        return False
    return -90 <= lat <= 90 and -180 <= lon <= 180 and not (lat == 0 and lon == 0)


def _coordinate_location_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def validate_coordinate_for_location(
    lat: Any,
    lon: Any,
    ciudad: Any,
    provincia: Any = None,
    pais: Any = None,
) -> Dict[str, Any]:
    try:
        lat_float = float(lat)
        lon_float = float(lon)
    except (TypeError, ValueError):
        return {
            "valid": False,
            "location_validation": "invalid_coordinate",
            "city_bounds_checked": False,
            "within_city_bounds": False,
        }
    if not (-90 <= lat_float <= 90 and -180 <= lon_float <= 180) or (lat_float == 0 and lon_float == 0):
        return {
            "valid": False,
            "location_validation": "invalid_coordinate",
            "city_bounds_checked": False,
            "within_city_bounds": False,
        }

    city_key = _coordinate_location_key(ciudad)
    province_key = _coordinate_location_key(provincia)
    country_key = _coordinate_location_key(pais)
    is_uruguay = (
        "uruguay" in {country_key, province_key}
        or city_key in {"punta del este", "maldonado", "montevideo"}
        or province_key == "maldonado"
    )
    if is_uruguay:
        min_lat, max_lat, min_lon, max_lon = URUGUAY_COORDINATE_BOUNDS
        inside = min_lat <= lat_float <= max_lat and min_lon <= lon_float <= max_lon
        return {
            "valid": inside,
            "location_validation": "uruguay_bounds_ok" if inside else "uruguay_outlier",
            "city_bounds_checked": True,
            "within_city_bounds": inside,
        }

    bounds = CITY_COORDINATE_BOUNDS.get(city_key)
    if bounds is None:
        return {
            "valid": True,
            "location_validation": "no_rule",
            "city_bounds_checked": False,
            "within_city_bounds": None,
        }
    min_lat, max_lat, min_lon, max_lon = bounds
    inside = min_lat <= lat_float <= max_lat and min_lon <= lon_float <= max_lon
    return {
        "valid": inside,
        "location_validation": "within_city_bounds" if inside else "coordenada_descartada_por_outlier",
        "city_bounds_checked": True,
        "within_city_bounds": inside,
    }


def is_coordinate_valid_for_location(lat: Any, lon: Any, ciudad: Any, provincia: Any, pais: Any) -> bool:
    return bool(validate_coordinate_for_location(lat, lon, ciudad, provincia, pais).get("valid"))


def validate_property_coordinate_context(prop: Dict[str, Any]) -> Dict[str, Any]:
    ciudad = prop.get("ciudad")
    provincia = prop.get("provincia")
    pais = prop.get("pais") or "Argentina"
    validation = validate_coordinate_for_location(prop.get("latitud"), prop.get("longitud"), ciudad, provincia, pais)
    city_key = _coordinate_location_key(ciudad)
    province_key = _coordinate_location_key(provincia)
    barrio_key = _coordinate_location_key(prop.get("barrio"))
    if (
        validation.get("city_bounds_checked")
        and not validation.get("valid")
        and barrio_key in CITY_COORDINATE_BOUNDS
        and (not city_key or city_key == province_key)
    ):
        barrio_validation = validate_coordinate_for_location(
            prop.get("latitud"),
            prop.get("longitud"),
            prop.get("barrio"),
            provincia,
            pais,
        )
        if barrio_validation.get("valid"):
            barrio_validation["location_validation"] = "within_city_bounds_barrio_fallback"
            barrio_validation["ciudad_usada_para_validacion"] = prop.get("barrio")
            return barrio_validation
    validation["ciudad_usada_para_validacion"] = ciudad
    return validation


def _record_coordinate_outlier(stats: Optional[Dict[str, Any]], prop: Dict[str, Any], validation: Dict[str, Any]) -> None:
    if stats is None:
        return
    if validation.get("location_validation") == "no_rule":
        stats["coordenadas_sin_regla_ciudad"] = int(stats.get("coordenadas_sin_regla_ciudad") or 0) + 1
        return
    stats["coordenadas_descartadas_por_outlier"] = int(stats.get("coordenadas_descartadas_por_outlier") or 0) + 1
    examples = stats.setdefault("coordenadas_outlier_ejemplos", [])
    if len(examples) < 10:
        examples.append({
            "ciudad": prop.get("ciudad"),
            "barrio": prop.get("barrio"),
            "provincia": prop.get("provincia"),
            "pais": prop.get("pais"),
            "latitud_descartada": prop.get("latitud"),
            "longitud_descartada": prop.get("longitud"),
            "url": prop.get("url"),
            "location_validation": validation.get("location_validation"),
            "ciudad_usada_para_validacion": validation.get("ciudad_usada_para_validacion"),
        })


def sanitize_property_coordinates(prop: Dict[str, Any], stats: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not any(field in prop for field in COORDINATE_FIELDS):
        return prop
    if not _valid_coordinate_pair(prop):
        prop.pop("latitud", None)
        prop.pop("longitud", None)
        return prop
    validation = validate_property_coordinate_context(prop)
    prop["_location_validation"] = validation.get("location_validation")
    if validation.get("location_validation") == "no_rule":
        _record_coordinate_outlier(stats, prop, validation)
        return prop
    if not validation.get("valid"):
        _record_coordinate_outlier(stats, prop, validation)
        logger.info(
            "[INVALID_COORDS] Coordenadas descartadas por bounds: ciudad=%s provincia=%s lat=%s lon=%s url=%s",
            prop.get("ciudad"),
            prop.get("provincia"),
            prop.get("latitud"),
            prop.get("longitud"),
            prop.get("url"),
        )
        prop.pop("latitud", None)
        prop.pop("longitud", None)
    return prop


def _has_real_images(value: Any) -> bool:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return False
    return bool(clean_property_images(value))


def _is_existing_value_useful(field: str, value: Any) -> bool:
    if field in COORDINATE_FIELDS:
        return value is not None
    if field == "imagenes":
        return _has_real_images(value)
    if field == "inmobiliaria_id":
        return _positive_number(value)
    if field in PROTECTED_POSITIVE_NUMBER_FIELDS:
        return _positive_number(value)
    if field in PROTECTED_TEXT_FIELDS:
        return _useful_text(value)
    return not _is_blank_value(value)


def _is_new_value_safe(field: str, value: Any, incoming: Dict[str, Any]) -> bool:
    if field in COORDINATE_FIELDS:
        return _valid_coordinate_pair(incoming)
    if field == "imagenes":
        return _has_real_images(value)
    if field == "inmobiliaria_id":
        existing_id = incoming.get("_existing_inmobiliaria_id")
        if _positive_number(existing_id) and _positive_number(value):
            return int(float(existing_id)) == int(float(value))
        return _positive_number(value)
    if field in PROTECTED_POSITIVE_NUMBER_FIELDS:
        return _positive_number(value)
    if field in PROTECTED_TEXT_FIELDS:
        if field == "moneda" and not _positive_number(incoming.get("precio")):
            return False
        return _useful_text(value)
    return not _is_blank_value(value)


def _record_protected_field(stats: Optional[Dict[str, Any]], field: str, had_existing_value: bool) -> None:
    if stats is None:
        return
    if had_existing_value:
        stats["campos_protegidos_de_null"] = int(stats.get("campos_protegidos_de_null") or 0) + 1
        by_name = stats.setdefault("campos_protegidos_por_nombre", {})
        by_name[field] = int(by_name.get(field) or 0) + 1
    else:
        stats["campos_invalidos_omitidos"] = int(stats.get("campos_invalidos_omitidos") or 0) + 1


def build_protected_update_payload(
    incoming: Dict[str, Any],
    existing: Dict[str, Any],
    columns: Optional[set] = None,
    stats: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Arma un PATCH que nunca degrada campos valiosos existentes."""
    fallback_city_from_agency = bool(incoming.get("_fallback_ciudad_from_agency"))
    fallback_province_from_agency = bool(incoming.get("_fallback_provincia_from_agency"))
    payload = {
        key: value
        for key, value in incoming.items()
        if key not in {"id", "hash_dedup", "created_at"}
    }
    if columns is not None:
        payload = {key: value for key, value in payload.items() if key in columns}

    payload = sanitize_property_location(payload, stats)
    payload = normalize_property_location_encoding(payload, stats)
    payload = sanitize_property_prices(payload, stats)
    payload = sanitize_property_integers(payload, stats)

    existing_for_rules = dict(existing or {})
    payload["_existing_inmobiliaria_id"] = existing_for_rules.get("inmobiliaria_id")

    if any(field in payload for field in COORDINATE_FIELDS) and not _valid_coordinate_pair(payload):
        protected_coord = False
        for field in COORDINATE_FIELDS:
            if field in payload:
                had_existing = _is_existing_value_useful(field, existing_for_rules.get(field))
                protected_coord = protected_coord or had_existing
                _record_protected_field(stats, field, had_existing)
                payload.pop(field, None)
        if protected_coord and stats is not None:
            stats["coordenadas_conservadas"] = int(stats.get("coordenadas_conservadas") or 0) + 1

    if any(field in payload for field in COORDINATE_FIELDS) and _valid_coordinate_pair(payload):
        location_context = {
            **existing_for_rules,
            **payload,
            "pais": payload.get("pais") or existing_for_rules.get("pais") or "Argentina",
        }
        validation = validate_property_coordinate_context(location_context)
        if validation.get("location_validation") == "no_rule":
            _record_coordinate_outlier(stats, location_context, validation)
        elif not validation.get("valid"):
            for field in COORDINATE_FIELDS:
                if field in payload:
                    had_existing = _is_existing_value_useful(field, existing_for_rules.get(field))
                    _record_protected_field(stats, field, had_existing)
                    payload.pop(field, None)
            if stats is not None:
                stats["coordenadas_conservadas"] = int(stats.get("coordenadas_conservadas") or 0) + 1
            _record_coordinate_outlier(stats, location_context, validation)
            logger.info(
                "[INVALID_COORDS] Coordenadas descartadas por bounds: ciudad=%s provincia=%s lat=%s lon=%s url=%s",
                location_context.get("ciudad"),
                location_context.get("provincia"),
                location_context.get("latitud"),
                location_context.get("longitud"),
                location_context.get("url"),
            )

    if "precio" in payload and not _positive_number(payload.get("precio")):
        for field in ("precio", "moneda", "precio_usd", "precio_ars"):
            if field not in payload:
                continue
            had_existing = _is_existing_value_useful(field, existing_for_rules.get(field))
            _record_protected_field(stats, field, had_existing)
            payload.pop(field, None)

    for field in sorted(PROTECTED_UPDATE_FIELDS - COORDINATE_FIELDS):
        if field not in payload:
            continue
        if field == "imagenes":
            raw_images = payload.get(field)
            if isinstance(raw_images, str):
                raw_images = [raw_images]
            elif not isinstance(raw_images, list):
                raw_images = []
            cleaned = clean_property_images(raw_images)
            payload[field] = cleaned or None
        if field == "barrio" and payload.get("_clear_barrio_due_location_normalization"):
            continue
        if field == "ciudad" and fallback_city_from_agency and not _needs_agency_city_fallback(existing_for_rules.get("ciudad")):
            _record_protected_field(stats, field, True)
            payload.pop(field, None)
            continue
        if field == "provincia" and fallback_province_from_agency and _is_existing_value_useful(field, existing_for_rules.get(field)):
            _record_protected_field(stats, field, True)
            payload.pop(field, None)
            continue
        safe_incoming = _is_new_value_safe(field, payload.get(field), payload)
        if safe_incoming:
            continue
        had_existing = _is_existing_value_useful(field, existing_for_rules.get(field))
        _record_protected_field(stats, field, had_existing)
        if field == "imagenes" and had_existing and stats is not None:
            stats["imagenes_conservadas"] = int(stats.get("imagenes_conservadas") or 0) + 1
        payload.pop(field, None)

    payload.pop("_existing_inmobiliaria_id", None)
    payload.pop("_location_normalized", None)
    payload.pop("_location_normalization_motivo", None)
    payload.pop("_clear_barrio_due_location_normalization", None)
    payload.pop("_location_validation", None)
    payload.pop("_agency_location_context", None)
    payload.pop("_ubicacion_fallback_from_agency", None)
    payload.pop("_fallback_ciudad_from_agency", None)
    payload.pop("_fallback_provincia_from_agency", None)
    payload.pop("_original_city_before_agency_fallback", None)
    payload.pop("_original_province_before_agency_fallback", None)
    payload.pop("_ciudad_detectada_from_text", None)
    payload.pop("_provincia_detectada_from_text", None)
    payload.pop("_ciudad_encoding_normalizada", None)
    payload.pop("_provincia_encoding_normalizada", None)
    return payload


def _collect_json_image_values(value: Any, out: List[str]) -> None:
    if isinstance(value, str):
        if value.startswith(("http://", "https://", "//")):
            out.append(value)
        return
    if isinstance(value, list):
        for item in value:
            _collect_json_image_values(item, out)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            key_low = str(key).lower()
            if key_low in {"image", "images", "photo", "photos", "picture", "pictures", "url", "contenturl", "thumbnailurl"}:
                _collect_json_image_values(item, out)
            elif isinstance(item, (dict, list)):
                _collect_json_image_values(item, out)


def _extraer_imagenes_legacy(soup: BeautifulSoup, base_url: str = "") -> List[str]:
    """Extrae todas las imágenes de una propiedad, incluyendo lazy loading y srcset."""
    fotos: List[str] = []
    seen: set = set()

    img_attrs = ["src", "data-src", "data-lazy-src", "data-original",
                 "data-lazy", "data-url", "data-image", "data-full-src"]

    for img in soup.select(
        '[class*="gallery"] img, [class*="slider"] img, [class*="photo"] img, '
        '.swiper-slide img, [class*="carousel"] img, [class*="lightbox"] img, '
        '[class*="property"] img, [class*="propiedad"] img, '
        'figure img, .fotorama img, .owl-item img'
    ):
        # Intentar todos los atributos
        for attr in img_attrs:
            src = img.get(attr, "")
            if src and src.startswith("http") and src not in seen:
                seen.add(src)
                fotos.append(src)
                break
        # srcset: tomar la imagen de mayor resolución
        srcset = img.get("srcset", "") or img.get("data-srcset", "")
        if srcset:
            parts = [p.strip().split(" ")[0] for p in srcset.split(",") if p.strip()]
            for src in parts:
                if src.startswith("http") and src not in seen:
                    seen.add(src)
                    fotos.append(src)

    # Buscar también en atributos data-background (sliders CSS)
    for el in soup.select('[data-background], [data-bg], [style*="background-image"]'):
        bg = el.get("data-background") or el.get("data-bg", "")
        if not bg:
            style = el.get("style", "")
            m = re.search(r'url\(["\']?(https?://[^"\')\s]+)', style)
            bg = m.group(1) if m else ""
        if bg and bg.startswith("http") and bg not in seen:
            seen.add(bg)
            fotos.append(bg)

    return fotos[:60]  # máximo 60 fotos


def extraer_imagenes(
    soup: BeautifulSoup,
    base_url: str = "",
    stats: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Extrae solo fotos reales de una ficha, descartando iconos y placeholders."""
    candidates: List[str] = []
    source_by_url: Dict[str, str] = {}

    def add_candidate(raw: Any, source: str) -> None:
        normalized = _normalize_image_url(raw, base_url)
        if not normalized:
            return
        candidates.append(str(raw))
        source_by_url.setdefault(normalized, source)

    def add_embedded_image_candidates(value: Any, source: str) -> None:
        text = str(value or "")
        if not text:
            return
        text = html.unescape(text).replace("\\/", "/")
        for match in re.findall(
            r"(?:https?:)?//[^\"'\s<>\\]+?\.(?:jpe?g|png|webp|avif)(?:\?[^\"'\s<>\\]*)?",
            text,
            flags=re.I,
        ):
            add_candidate(match, source)
        for match in re.findall(
            r"(?:static\.tokkobroker\.com|storage\.tokkobroker\.com|cdn[^\"'\s<>\\]*|uploads?)[^\"'\s<>\\]+?\.(?:jpe?g|png|webp|avif)(?:\?[^\"'\s<>\\]*)?",
            text,
            flags=re.I,
        ):
            if match.startswith(("http://", "https://", "//")):
                add_candidate(match, source)
            elif match.startswith("static.tokkobroker.com") or match.startswith("storage.tokkobroker.com"):
                add_candidate(f"https://{match}", source)
            else:
                add_candidate(match, source)

    img_attrs = [
        "src",
        "data-src",
        "data-lazy-src",
        "data-original",
        "data-lazy",
        "data-url",
        "data-image",
        "data-full-src",
        "data-large",
        "data-big",
        "data-zoom-image",
    ]

    for img in soup.find_all("img"):
        for attr in img_attrs:
            src = img.get(attr, "")
            if src:
                add_candidate(src, attr)
        for attr in ("srcset", "data-srcset", "data-lazy-srcset"):
            srcset = img.get(attr, "")
            if srcset:
                for srcset_url in _extract_srcset_urls(str(srcset), base_url):
                    add_candidate(srcset_url, attr)

    for tag in soup.find_all(True):
        for attr, value in (tag.attrs or {}).items():
            attr_low = str(attr).lower()
            if attr_low in img_attrs or "srcset" in attr_low:
                continue
            if not (
                attr_low.startswith("data-")
                or "image" in attr_low
                or "photo" in attr_low
                or "thumb" in attr_low
                or "gallery" in attr_low
                or "background" in attr_low
                or "style" == attr_low
            ):
                continue
            if isinstance(value, (list, tuple)):
                value = " ".join(str(item) for item in value)
            add_embedded_image_candidates(value, f"attr_{attr_low}")

    for source in soup.find_all("source"):
        for attr in ("srcset", "data-srcset", "src", "data-src"):
            value = source.get(attr, "")
            if not value:
                continue
            if "srcset" in attr:
                for srcset_url in _extract_srcset_urls(str(value), base_url):
                    add_candidate(srcset_url, f"source_{attr}")
            else:
                add_candidate(value, f"source_{attr}")

    for el in soup.select("[data-background], [data-bg], [data-background-image], [style*='background']"):
        for attr in ("data-background", "data-bg", "data-background-image"):
            value = el.get(attr, "")
            if value:
                add_candidate(value, attr)
        style = el.get("style", "") or ""
        for match in re.findall(r"url\([\"']?([^\"')\s]+)", style, flags=re.I):
            add_candidate(match, "background_style")

    for meta in soup.select(
        "meta[property='og:image'], meta[property='og:image:secure_url'], "
        "meta[name='twitter:image'], meta[itemprop='image']"
    ):
        content = meta.get("content", "")
        if content:
            add_candidate(content, "meta")

    for script in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        raw = script.string or script.get_text("", strip=True)
        if not raw:
            continue
        before = len(candidates)
        try:
            json_candidates: List[str] = []
            _collect_json_image_values(json.loads(raw), json_candidates)
            for image_url in json_candidates:
                add_candidate(image_url, "json_ld")
        except Exception:
            continue
        if stats is not None and len(candidates) > before:
            stats["json_ld_scripts_con_imagenes"] = int(stats.get("json_ld_scripts_con_imagenes") or 0) + 1

    for script in soup.find_all("script"):
        raw_script = script.string or script.get_text("", strip=False)
        if raw_script:
            add_embedded_image_candidates(raw_script, "script_regex")

    html_text = str(soup)
    for match in re.findall(
        r"https?:\\?/\\?/[^\"'\s<>]+?\.(?:jpe?g|png|webp|avif)(?:\?[^\"'\s<>]*)?",
        html_text,
        flags=re.I,
    ):
        add_candidate(match.replace("\\/", "/"), "html_regex")
    add_embedded_image_candidates(html_text, "html_regex")

    images = clean_property_images(candidates, base_url=base_url, stats=stats)
    if stats is not None:
        source_counts = stats.setdefault("fuentes_imagenes", {})
        for image_url in images:
            normalized = _normalize_image_url(image_url, base_url) or image_url
            source = source_by_url.get(normalized, "unknown")
            source_counts[source] = int(source_counts.get(source) or 0) + 1
    return images


def _new_image_stats() -> Dict[str, Any]:
    return {
        "imagenes_reales_detectadas": 0,
        "imagenes_falsas_descartadas": 0,
        "imagenes_descartadas_por_motivo": {},
        "ejemplos_reales": [],
        "ejemplos_descartados": [],
        "fuentes_imagenes": {},
        "json_ld_scripts_con_imagenes": 0,
    }


def _tokko_image_stats(inmob: Dict) -> Dict[str, Any]:
    stats = inmob.get("_tokko_image_stats")
    if not isinstance(stats, dict):
        stats = _new_image_stats()
        inmob["_tokko_image_stats"] = stats
    return stats


def _merge_image_stats(target: Dict[str, Any], source: Dict[str, Any]) -> None:
    for key in ("imagenes_reales_detectadas", "imagenes_falsas_descartadas", "json_ld_scripts_con_imagenes"):
        target[key] = int(target.get(key) or 0) + int(source.get(key) or 0)

    target_sources = target.setdefault("fuentes_imagenes", {})
    for source_name, count in (source.get("fuentes_imagenes") or {}).items():
        target_sources[source_name] = int(target_sources.get(source_name) or 0) + int(count or 0)

    target_reasons = target.setdefault("imagenes_descartadas_por_motivo", {})
    for reason, count in (source.get("imagenes_descartadas_por_motivo") or {}).items():
        target_reasons[reason] = int(target_reasons.get(reason) or 0) + int(count or 0)

    for key, limit in (
        ("ejemplos_reales", TOKKO_REAL_IMAGE_EXAMPLES_LIMIT),
        ("ejemplos_descartados", TOKKO_FAKE_IMAGE_EXAMPLES_LIMIT),
    ):
        target_list = target.setdefault(key, [])
        for value in source.get(key, []) or []:
            if value not in target_list and len(target_list) < limit:
                target_list.append(value)


def _count_real_image_props(props: List[Dict]) -> Tuple[int, int]:
    with_images = sum(1 for prop in props if prop.get("imagenes"))
    return with_images, max(len(props) - with_images, 0)


def _fetch_tokko_detail_images(prop: Dict, inmob: Dict) -> Tuple[Dict, List[str], Dict[str, Any], Optional[str]]:
    stats = _new_image_stats()
    url = prop.get("url")
    if not url:
        return prop, [], stats, "sin_url_detalle"
    try:
        _check_strategy_deadline(inmob, "tokko_html")
        worker_session = _make_http_session()
        timeout = min(TOKKO_DETAIL_IMAGE_TIMEOUT, _bounded_http_timeout(inmob, TOKKO_DETAIL_IMAGE_TIMEOUT))
        response = _http_get(str(url), worker_session, timeout=timeout)
        if response.status_code != 200:
            return prop, [], stats, f"HTTP {response.status_code}"
        soup = BeautifulSoup(_decode_response_text(response), "html.parser")
        images = extraer_imagenes(soup, str(url), stats)
        if images:
            logger.debug("[IMAGE_EXTRACTION] propiedad=%s imagenes_detectadas=%d url=%s", prop.get("id_externo"), len(images), url)
        else:
            logger.debug("[IMAGE_EXTRACTION_WARN] sin imagenes reales url=%s", url)
        return prop, images, stats, None
    except Exception as exc:
        return prop, [], stats, f"{type(exc).__name__}: {str(exc)[:180]}"


def _enrich_tokko_detail_images(resultados: List[Dict], session: requests.Session, inmob: Dict) -> Dict[str, Any]:
    stats = _tokko_image_stats(inmob)
    for prop in resultados:
        raw_images = prop.get("imagenes") or []
        prop["imagenes"] = clean_property_images(raw_images if isinstance(raw_images, list) else [raw_images], stats=stats) or None

    missing = [prop for prop in resultados if not prop.get("imagenes") and prop.get("url")]
    detail_errors: List[str] = []
    details_checked = 0
    _update_strategy_progress(
        inmob,
        str(inmob.get("_strategy_name") or "tokko_html"),
        detail_image_urls_total=len(missing),
        detail_image_urls_processed=0,
        detail_image_urls_remaining=len(missing),
    )

    if missing:
        remaining = _deadline_remaining_seconds(_strategy_deadline(inmob))
        if remaining <= 6:
            with_images, without_images = _count_real_image_props(resultados)
            return {
                "propiedades_con_fotos_reales": with_images,
                "propiedades_sin_fotos_reales": without_images,
                "detalles_consultados_para_fotos": details_checked,
                "detalles_pendientes_sin_consultar": len(missing),
                "imagenes_falsas_descartadas": int(stats.get("imagenes_falsas_descartadas") or 0),
                "imagenes_descartadas_por_motivo": dict(stats.get("imagenes_descartadas_por_motivo") or {}),
                "imagenes_reales_detectadas": int(stats.get("imagenes_reales_detectadas") or 0),
                "fuentes_imagenes": dict(stats.get("fuentes_imagenes") or {}),
                "metodo_extraccion_imagenes": "tokko_card_y_detalle_http",
                "metodos_extraccion_imagenes_usados": sorted((stats.get("fuentes_imagenes") or {}).keys()),
                "json_ld_scripts_con_imagenes": int(stats.get("json_ld_scripts_con_imagenes") or 0),
                "ejemplos_imagenes_descartadas": stats.get("ejemplos_descartados", [])[:TOKKO_FAKE_IMAGE_EXAMPLES_LIMIT],
                "ejemplos_imagenes_reales": stats.get("ejemplos_reales", [])[:TOKKO_REAL_IMAGE_EXAMPLES_LIMIT],
                "errores_detalle_imagenes": ["sin_tiempo_para_detalles"],
            }
        max_workers = max(1, min(TOKKO_DETAIL_IMAGE_MAX_WORKERS, len(missing)))
        detail_budget = max(1.0, remaining - 5.0)
        timeout = max(1.0, min(detail_budget, max(TOKKO_DETAIL_IMAGE_TIMEOUT * len(missing) / max_workers, 1.0)))
        executor = ThreadPoolExecutor(max_workers=max_workers)
        try:
            futures = [executor.submit(_fetch_tokko_detail_images, prop, inmob) for prop in missing]
            for future in as_completed(futures, timeout=timeout):
                prop, images, detail_stats, error = future.result()
                _merge_image_stats(stats, detail_stats)
                details_checked += 1
                if images:
                    prop["imagenes"] = images
                    raw_json = prop.get("raw_json") if isinstance(prop.get("raw_json"), dict) else {}
                    raw_json["detalle_imagenes"] = True
                    raw_json["imagenes_reales"] = len(images)
                    prop["raw_json"] = raw_json
                elif error and len(detail_errors) < 6:
                    detail_errors.append(f"{prop.get('url')}: {error}")
                _update_strategy_progress(
                    inmob,
                    str(inmob.get("_strategy_name") or "tokko_html"),
                    detail_image_urls_total=len(missing),
                    detail_image_urls_processed=details_checked,
                    detail_image_urls_remaining=max(len(missing) - details_checked, 0),
                    propiedades_con_fotos_reales=_count_real_image_props(resultados)[0],
                    errores_detalle_imagenes=detail_errors[-5:],
                )
        except Exception as exc:
            if type(exc).__name__ == "TimeoutError":
                pending = max(len(missing) - details_checked, 0)
                detail_errors.append(f"presupuesto_detalles_agotado: {pending} pendientes sin consultar")
            else:
                detail_errors.append(f"detalle_imagenes: {type(exc).__name__}: {str(exc)[:180]}")
            _update_strategy_progress(
                inmob,
                str(inmob.get("_strategy_name") or "tokko_html"),
                detail_image_urls_total=len(missing),
                detail_image_urls_processed=details_checked,
                detail_image_urls_remaining=max(len(missing) - details_checked, 0),
                propiedades_con_fotos_reales=_count_real_image_props(resultados)[0],
                errores_detalle_imagenes=detail_errors[-5:],
            )
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    with_images, without_images = _count_real_image_props(resultados)
    return {
        "propiedades_con_fotos_reales": with_images,
        "propiedades_sin_fotos_reales": without_images,
        "detalles_consultados_para_fotos": details_checked,
        "detalles_pendientes_sin_consultar": max(len(missing) - details_checked, 0),
        "imagenes_falsas_descartadas": int(stats.get("imagenes_falsas_descartadas") or 0),
        "imagenes_descartadas_por_motivo": dict(stats.get("imagenes_descartadas_por_motivo") or {}),
        "imagenes_reales_detectadas": int(stats.get("imagenes_reales_detectadas") or 0),
        "fuentes_imagenes": dict(stats.get("fuentes_imagenes") or {}),
        "metodo_extraccion_imagenes": "tokko_card_y_detalle_http",
        "metodos_extraccion_imagenes_usados": sorted((stats.get("fuentes_imagenes") or {}).keys()),
        "json_ld_scripts_con_imagenes": int(stats.get("json_ld_scripts_con_imagenes") or 0),
        "ejemplos_imagenes_descartadas": stats.get("ejemplos_descartados", [])[:TOKKO_FAKE_IMAGE_EXAMPLES_LIMIT],
        "ejemplos_imagenes_reales": stats.get("ejemplos_reales", [])[:TOKKO_REAL_IMAGE_EXAMPLES_LIMIT],
        "errores_detalle_imagenes": detail_errors,
    }


# ---------------------------------------------------------------------------
# Strategy 1: Tokko Broker API
# ---------------------------------------------------------------------------

def _map_tokko_property(obj: Dict, inmob: Dict) -> Dict:
    """Convierte un objeto de la API Tokko al schema de propiedades."""
    # Operaciones / precios
    precio = None
    moneda = "USD"
    operacion = "venta"
    try:
        ops = obj.get("operations", [])
        if ops:
            op0 = ops[0]
            operacion = normalizar_operacion(op0.get("operation_type", ""))
            prices = op0.get("prices", [])
            if prices:
                p = prices[0]
                precio_raw = p.get("price", 0)
                moneda_raw = p.get("currency", "USD")
                precio = float(precio_raw) if precio_raw else None
                moneda = "USD" if "USD" in str(moneda_raw).upper() else "ARS"
    except Exception:
        pass

    # Fotos
    fotos: List[str] = []
    for ph in obj.get("photos", []):
        img = ph.get("image") or ph.get("original") or ph.get("thumb", "")
        if img:
            fotos.append(img)
    fotos = clean_property_images(fotos, stats=_tokko_image_stats(inmob))

    # Tags / amenities
    amenities = [t.get("name", "") for t in obj.get("tags", []) if t.get("name")]

    # Ubicación
    loc = obj.get("location", {}) or {}

    # Superficie
    sup_total   = normalizar_superficie(obj.get("total_surface"))
    sup_cubierta = normalizar_superficie(obj.get("roofed_surface"))

    inmob_id = inmob["id"]
    id_ext   = str(obj.get("id", ""))
    url_prop = obj.get("web_url", "") or ""

    prop = {
        "inmobiliaria_id":     inmob_id,
        "url":                 url_prop or None,
        "id_externo":          id_ext,
        "hash_dedup":          hash_propiedad(inmob_id, id_ext, url_prop),
        "titulo":              obj.get("publication_title", ""),
        "descripcion":         limpiar_descripcion(obj.get("description", "")),
        "precio":              precio,
        "moneda":              moneda,
        "precio_ars":          convertir_precio(precio, moneda)[0],
        "precio_usd":          convertir_precio(precio, moneda)[1],
        "tipo_propiedad":      normalizar_tipo(obj.get("type", {}).get("name", "") if isinstance(obj.get("type"), dict) else obj.get("type", "")),
        "operacion":           operacion,
        "ambientes":           normalizar_int(obj.get("environments") or obj.get("total_environments")),
        "dormitorios":         normalizar_int(obj.get("suite_amount")),
        "banos":               normalizar_int(obj.get("bathroom_amount")),
        "cocheras":            normalizar_int(obj.get("parking_lot_amount")),
        "superficie_total":    sup_total,
        "superficie_cubierta": sup_cubierta,
        "direccion":           obj.get("real_address", "") or obj.get("address", ""),
        "barrio":              loc.get("divisions", [{}])[0].get("name", "") if loc.get("divisions") else "",
        "ciudad":              loc.get("name", "") or inmob.get("ciudad", ""),
        "provincia":           inmob.get("provincia", ""),
        "pais":                "Argentina",
        "latitud":             float(obj["latitude"])  if obj.get("latitude")  else None,
        "longitud":            float(obj["longitude"]) if obj.get("longitude") else None,
        "imagenes":            fotos or None,
        "video_url":           obj.get("video", None),
        "amenities":           amenities or None,
        "raw_json":            obj,
        "agente_nombre":       obj.get("contact", {}).get("name") if isinstance(obj.get("contact"), dict) else None,
        "agente_telefono":     obj.get("contact", {}).get("phone") if isinstance(obj.get("contact"), dict) else None,
        "apto_credito":        obj.get("accepts_credits") or None,
        "apto_profesional":    obj.get("professional") or None,
        "fuente_extraccion":   "tokko_api",
        "cms_origen":          "tokko",
        "estado":              "activo",
    }
    prop["score_calidad"] = calcular_score(prop)
    return prop


def _fetch_tokko_detail(obj_id: str, key: str, session: requests.Session, inmob: Optional[Dict] = None) -> Optional[Dict]:
    """Obtiene datos completos de una propiedad individual via Tokko API."""
    try:
        if inmob is not None and _strategy_deadline(inmob) is not None:
            _check_strategy_deadline(inmob, str(inmob.get("_strategy_name") or "tokko_api"))
        url = f"{TOKKO_API_BASE}{obj_id}/?key={key}&format=json&lang=es"
        timeout = _bounded_http_timeout(inmob, 6) if inmob is not None and _strategy_deadline(inmob) is not None else 20
        r = _http_get(url, session, timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def strategy_tokko_api(inmob: Dict, session: requests.Session) -> List[Dict]:
    key = inmob.get("tokko_api_key", "")
    if not key:
        raise ValueError("sin_tokko_key")

    resultados: List[Dict] = []
    offset = 0
    total_count = None

    while True:
        if _strategy_deadline(inmob) is not None:
            _check_strategy_deadline(inmob, "tokko_api")
        url = (
            f"{TOKKO_API_BASE}?key={key}&limit={TOKKO_LIMIT}"
            f"&offset={offset}&format=json&lang=es"
        )
        try:
            timeout = _bounded_http_timeout(inmob, 12) if _strategy_deadline(inmob) is not None else 30
            r = _http_get(url, session, timeout=timeout)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            raise RuntimeError(f"Tokko API error: {e}") from e

        objects = data.get("objects", [])
        if total_count is None:
            total_count = data.get("meta", {}).get("total_count", 0)

        def _fetch_and_map(obj):
            try:
                obj_id = str(obj.get("id", ""))
                # Enriquecer con detalle si faltan campos clave
                if obj_id and (not obj.get("description") or not obj.get("latitude")):
                    detail = _fetch_tokko_detail(obj_id, key, session, inmob)
                    if detail and isinstance(detail, dict):
                        # Merge: el detalle prevalece para campos vacíos
                        for field in ("description", "latitude", "longitude",
                                      "real_address", "photos", "tags",
                                      "contact", "accepts_credits"):
                            if detail.get(field) and not obj.get(field):
                                obj[field] = detail[field]
                        # Fotos: usar las del detalle si tiene más
                        if detail.get("photos") and len(detail["photos"]) > len(obj.get("photos", [])):
                            obj["photos"] = detail["photos"]
                return _map_tokko_property(obj, inmob)
            except Exception as exc:
                logger.debug("Tokko map error: %s", exc)
                return None

        # Fetch detail en paralelo (5 workers)
        mapped: List[Optional[Dict]] = []
        executor = ThreadPoolExecutor(max_workers=5)
        try:
            futures = [executor.submit(_fetch_and_map, obj) for obj in objects]
            timeout = None
            if _strategy_deadline(inmob) is not None:
                timeout = max(1.0, _deadline_remaining_seconds(_strategy_deadline(inmob)))
            for future in as_completed(futures, timeout=timeout):
                try:
                    mapped.append(future.result())
                except Exception:
                    pass
        except TimeoutError as exc:
            raise StrategyTimeoutError("timeout_tokko_api: excedio el limite configurado") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        resultados.extend(p for p in mapped if p is not None)

        offset += TOKKO_LIMIT
        if not objects or (total_count and offset >= total_count):
            break
        time.sleep(0.5)

    return resultados


TOKKO_HTML_EXTRACTOR_VERSION = "tokko_html_v3_images"

_TOKKO_LISTING_PATHS = [
    "/Propiedades", "/propiedades", "/PROPIEDADES",
    "/Venta", "/venta", "/VENTA",
    "/Alquiler", "/alquiler", "/ALQUILER",
    "/Ventas", "/ventas",
    "/Alquileres", "/alquileres",
    "/Inmuebles", "/inmuebles",
    "/Emprendimientos", "/emprendimientos",
    "/Desarrollos", "/desarrollos",
    "/buscar", "/Buscar", "/",
]

_TOKKO_LISTING_KEYWORDS = (
    "propiedades", "propiedad", "venta", "ventas", "alquiler",
    "alquileres", "inmuebles", "buscar", "desarrollo", "desarrollos",
    "emprendimiento", "emprendimientos",
)


def _is_tokko_html(html: str) -> bool:
    low = (html or "").lower()
    return (
        "tokkobroker" in low
        or "static.tokkobroker.com" in low
        or "loaded_props_ids" in low
        or "resultados-list" in low
        or "prop-id=" in low
    )


def _detect_tokko_template(html: str) -> str:
    low = (html or "").lower()
    if "resultados-list" in low or "prop-id=" in low or "loaded_props_ids" in low:
        return "tokko_classic"
    if "tokkobroker" in low or "static.tokkobroker.com" in low:
        return "tokko_custom"
    return "unknown"


def _tokko_base_url(inmob: Dict, fallback_url: str = "") -> str:
    raw = inmob.get("web") or fallback_url or inmob.get("url_listado") or ""
    parsed = urlparse(raw)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return raw.rstrip("/")


def _url_host_variants(url: Optional[str]) -> List[str]:
    if not url:
        return []
    raw = _normalize_queue_url(url)
    parsed = urlparse(raw)
    if not parsed.netloc:
        return [raw]

    hosts = [parsed.netloc]
    if parsed.netloc.startswith("www."):
        hosts.append(parsed.netloc[4:])
    else:
        hosts.append(f"www.{parsed.netloc}")

    variants: List[str] = []
    for scheme in ("https", "http"):
        for host in hosts:
            variant = urlunparse(parsed._replace(scheme=scheme, netloc=host))
            if variant not in variants:
                variants.append(variant)
    return variants


_NON_DIAGNOSTIC_PATH_RE = re.compile(
    r"(^|/)(contacto|contact|nosotros|quienes-somos|quienes_somos|tasaciones|tasacion|servicios|login|admin|wp-admin)(/|$)",
    re.I,
)

_DIAGNOSTIC_USEFUL_PATHS = (
    "/propiedades", "/inmuebles", "/venta", "/ventas", "/alquiler", "/alquileres",
    "/emprendimientos", "/desarrollos", "/listing", "/listings",
)


def _url_origin(url: str) -> str:
    parsed = urlparse(_normalize_queue_url(url))
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return _normalize_queue_url(url).rstrip("/")


def normalize_start_url_for_diagnosis(url: Optional[str]) -> Dict[str, Any]:
    """Genera puntos de entrada utiles para diagnosticar, evitando paginas tipo contacto."""
    normalized = _normalize_queue_url(url)
    parsed = urlparse(normalized)
    if not parsed.netloc:
        return {
            "url_original": url,
            "url_normalizada": normalized,
            "url_inicial_era_contacto": False,
            "url_base_derivada": normalized,
            "candidate_urls": [normalized] if normalized else [],
            "base_variants": [normalized] if normalized else [],
            "subfolder_bases": [],
        }

    path = parsed.path or "/"
    path_key = unquote(path).lower()
    is_non_useful = bool(_NON_DIAGNOSTIC_PATH_RE.search(path_key))

    origin = f"{parsed.scheme}://{parsed.netloc}"
    subfolder_bases: List[str] = []
    parts = [part for part in path.strip("/").split("/") if part]
    if len(parts) >= 2 and is_non_useful:
        subfolder_bases.append(urljoin(origin + "/", parts[0].strip("/") + "/"))
    elif len(parts) >= 1 and parts[0].lower() in {"web", "site", "sitio"}:
        subfolder_bases.append(urljoin(origin + "/", parts[0].strip("/") + "/"))

    candidate_roots = [origin + "/"] + subfolder_bases
    candidate_urls: List[str] = []

    def add(candidate: str) -> None:
        for variant in _url_host_variants(candidate):
            clean = variant.rstrip("/") + ("/" if urlparse(variant).path in {"", "/"} else "")
            if clean not in candidate_urls:
                candidate_urls.append(clean)

    if not is_non_useful:
        add(normalized)
    for root in candidate_roots:
        add(root)
    for useful_path in _DIAGNOSTIC_USEFUL_PATHS:
        for root in candidate_roots:
            add(urljoin(root, useful_path.lstrip("/")))

    return {
        "url_original": url,
        "url_normalizada": normalized,
        "url_inicial_era_contacto": is_non_useful,
        "url_base_derivada": candidate_roots[0] if candidate_roots else origin + "/",
        "candidate_urls": candidate_urls[:80],
        "base_variants": list(dict.fromkeys(_url_host_variants(origin + "/"))),
        "subfolder_bases": subfolder_bases,
    }


def _add_query_param(url: str, key: str, value: Any) -> str:
    parsed = urlparse(url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    params[key] = str(value)
    return urlunparse(parsed._replace(query=urlencode(params)))


def _extract_tokko_internal_listing_links(html: str, current_url: str) -> List[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    parsed = urlparse(current_url)
    domain = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else current_url.rstrip("/")
    links: List[str] = []
    for a in soup.select("nav a[href], header a[href], #menu a[href], a[href]"):
        href = (a.get("href") or "").strip()
        text = a.get_text(" ", strip=True).lower()
        href_low = href.lower()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        if not any(kw in href_low or kw in text for kw in _TOKKO_LISTING_KEYWORDS):
            continue
        full = urljoin(domain + "/", href)
        if urlparse(full).netloc == urlparse(domain).netloc and full not in links:
            links.append(full)
    return links


def _tokko_candidate_urls(inmob: Dict, first_html: str = "", first_url: str = "") -> List[str]:
    urls: List[str] = []

    def add(url: Optional[str]) -> None:
        if not url:
            return
        clean = str(url).strip()
        if not clean:
            return
        if not re.match(r"^https?://", clean, re.IGNORECASE):
            clean = "https://" + clean.lstrip("/")
        if clean not in urls:
            urls.append(clean)

    for variant in _url_host_variants(inmob.get("url_listado")):
        add(variant)
    for variant in _url_host_variants(inmob.get("web")):
        add(variant)
    if first_html and first_url:
        for link in _extract_tokko_internal_listing_links(first_html, first_url):
            add(link)

    base_candidates = _url_host_variants(_tokko_base_url(inmob, first_url))
    for base in base_candidates:
        if base:
            for path in _TOKKO_LISTING_PATHS:
                add(urljoin(base.rstrip("/") + "/", path.lstrip("/")))

    return urls[:40]


def _parse_tokko_markers(html: str) -> Dict[str, Tuple[float, float]]:
    markers: Dict[str, Tuple[float, float]] = {}
    pattern = re.compile(
        r"add_new_marker\(\s*['\"](?P<id>\d+)['\"]\s*,\s*"
        r"(?P<lat>-?\d+(?:\.\d+)?)\s*,\s*(?P<lon>-?\d+(?:\.\d+)?)\s*\)",
        re.I,
    )
    for match in pattern.finditer(html or ""):
        try:
            markers[match.group("id")] = (float(match.group("lat")), float(match.group("lon")))
        except Exception:
            pass
    return markers


def _tokko_direct_price_text(card) -> str:
    price_el = card.select_one(".prop-valor-nro, [class*='prop-valor'], [class*='precio'], [class*='price']")
    if not price_el:
        return ""
    direct = " ".join(
        text.strip()
        for text in price_el.find_all(string=True, recursive=False)
        if text and text.strip()
    )
    if direct:
        return direct
    text = price_el.get_text(" ", strip=True)
    match = re.search(r"(?:USD|US\$|U\$S|\$)\s*[\d.,]+", text, re.I)
    return match.group(0) if match else text


def _parse_tokko_type_operation_location(text: str, inmob: Dict) -> Tuple[str, str, str, str]:
    tipo = normalizar_tipo(text)
    operacion = normalizar_operacion(text)
    barrio = ""
    ciudad = inmob.get("ciudad", "") or ""

    match = re.search(
        r"^\s*(?P<tipo>.+?)\s+en\s+(?P<op>venta|alquiler|temporario)\s+en\s+(?P<loc>.+)$",
        text or "",
        re.I,
    )
    if match:
        tipo = normalizar_tipo(match.group("tipo"))
        operacion = normalizar_operacion(match.group("op"))
        location = re.sub(r"\s+", " ", match.group("loc")).strip()
        parts = [p.strip() for p in location.split(",") if p.strip()]
        if parts:
            barrio = parts[0]
        if len(parts) >= 2:
            ciudad = parts[-1]

    return tipo, operacion, barrio, ciudad


def _parse_tokko_listing_cards(html: str, source_url: str, inmob: Dict) -> List[Dict]:
    soup = BeautifulSoup(html or "", "html.parser")
    image_stats = _tokko_image_stats(inmob)
    markers = _parse_tokko_markers(html)
    cards = (
        soup.select("#propiedades > li[prop-id]")
        or soup.select("ul.resultados-list > li[prop-id]")
        or soup.select("#prop-list li[prop-id]")
        or soup.select("li[prop-id]")
    )

    propiedades: List[Dict] = []
    for card in cards:
        try:
            prop_id = str(card.get("prop-id") or "").strip()
            link = card.select_one('a[href^="/p/"], a[href*="/p/"], a[href]')
            href = (link.get("href") if link else "") or ""
            url_prop = urljoin(source_url, href) if href else urljoin(source_url, f"/p/{prop_id}")
            if not prop_id:
                m = re.search(r"/p/(\d+)", url_prop)
                prop_id = m.group(1) if m else ""
            if not prop_id and not url_prop:
                continue

            tipo_ub = ""
            tipo_el = card.select_one(".prop-desc-tipo-ub, [class*='tipo-ub'], [class*='tipo']")
            if tipo_el:
                tipo_ub = tipo_el.get_text(" ", strip=True)
            direccion = ""
            dir_el = card.select_one(".prop-desc-dir, [class*='desc-dir'], [class*='direccion']")
            if dir_el:
                direccion = dir_el.get_text(" ", strip=True)

            img = card.select_one("img.dest-img, .prop-img img, img")
            imagenes: List[str] = []
            img_title = ""
            if img:
                src = (img.get("src") or img.get("data-src") or img.get("data-original") or "").strip()
                if src:
                    imagenes.extend(clean_property_images([src], base_url=source_url, stats=image_stats))
                srcset = img.get("srcset") or img.get("data-srcset") or ""
                if srcset:
                    imagenes.extend(clean_property_images(_extract_srcset_urls(str(srcset), source_url), stats=image_stats))
                img_title = (img.get("title") or img.get("alt") or "").strip()

            title = img_title
            title = re.sub(r"^Foto\s+", "", title, flags=re.I).strip()
            if not title:
                title = " ".join(part for part in (tipo_ub, direccion) if part).strip()
            if not title:
                title = urlparse(url_prop).path.rstrip("/").split("/")[-1].replace("-", " ").title()

            precio_raw = _tokko_direct_price_text(card)
            precio, moneda = normalizar_precio(precio_raw)
            precio_ars, precio_usd = convertir_precio(precio, moneda)

            tipo, operacion, barrio, ciudad = _parse_tokko_type_operation_location(tipo_ub, inmob)
            if not tipo or tipo == "otro":
                tipo = normalizar_tipo(title)
            if not barrio:
                barrio = inmob.get("ciudad", "") or ""
            if not ciudad:
                ciudad = inmob.get("ciudad", "") or ""

            data_texts = [
                el.get_text(" ", strip=True)
                for el in card.select(".prop-data, .prop-data2, [class*='prop-data']")
                if el.get_text(" ", strip=True)
            ]
            total_area = None
            rooms = None
            for txt in data_texts:
                if total_area is None and re.search(r"m\s*(?:2|Â²|²)", txt, re.I):
                    total_area = normalizar_superficie(txt)
                elif rooms is None:
                    maybe_room = normalizar_int(txt)
                    if maybe_room and 0 < maybe_room < 20:
                        rooms = maybe_room

            lat = lon = None
            if prop_id in markers:
                lat, lon = markers[prop_id]

            prop = {
                "inmobiliaria_id":     inmob["id"],
                "url":                 url_prop or None,
                "id_externo":          prop_id,
                "hash_dedup":          hash_propiedad(inmob["id"], prop_id, url_prop),
                "titulo":              title,
                "descripcion":         limpiar_descripcion(" - ".join(p for p in (tipo_ub, direccion) if p)),
                "precio":              precio,
                "moneda":              moneda,
                "precio_ars":          precio_ars,
                "precio_usd":          precio_usd,
                "tipo_propiedad":      tipo,
                "operacion":           operacion,
                "ambientes":           rooms,
                "superficie_total":    total_area,
                "direccion":           direccion,
                "barrio":              barrio,
                "ciudad":              ciudad,
                "provincia":           inmob.get("provincia", ""),
                "pais":                "Argentina",
                "latitud":             lat,
                "longitud":            lon,
                "imagenes":            imagenes or None,
                "fuente_extraccion":   "tokko_html",
                "cms_origen":          "tokko",
                "estado":              "activo",
                "raw_json":            {"source": "tokko_html_card", "prop_id": prop_id},
            }
            prop["score_calidad"] = calcular_score(prop)
            propiedades.append(prop)
        except Exception as exc:
            logger.debug("Tokko HTML card parse error: %s", exc)

    return propiedades


def _dedupe_props(props: List[Dict]) -> List[Dict]:
    seen: set = set()
    deduped: List[Dict] = []
    for prop in props:
        key = prop.get("hash_dedup") or prop.get("url") or prop.get("id_externo")
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(prop)
    return deduped


def strategy_tokko_html(inmob: Dict, session: requests.Session) -> List[Dict]:
    url_inicial = inmob.get("url_listado") or inmob.get("web", "")
    if not url_inicial:
        raise ValueError("sin_url_listado")

    _check_strategy_deadline(inmob, "tokko_html")
    urls_probadas: List[str] = []
    errores_relevantes: List[str] = []
    resultados: List[Dict] = []
    paginas_leidas = 0
    first_html = ""
    internal_links_detected = 0
    templates_detected: List[str] = []
    motivo_sin_propiedades = "sin_cards_tokko"

    try:
        r0 = _http_get(url_inicial, session, timeout=_bounded_http_timeout(inmob, 20))
        first_html = r0.text if r0.status_code == 200 else ""
    except Exception as exc:
        errores_relevantes.append(f"{url_inicial}: {type(exc).__name__}: {str(exc)[:180]}")

    candidates = _tokko_candidate_urls(inmob, first_html=first_html, first_url=url_inicial)
    _update_strategy_progress(
        inmob,
        "tokko_html",
        listing_urls_total=len(candidates),
        listing_urls_processed=0,
        propiedades_detectadas=0,
        paginas_leidas=0,
    )

    idx = 0
    while idx < len(candidates):
        candidate = candidates[idx]
        idx += 1
        _check_strategy_deadline(inmob, "tokko_html")
        if candidate in urls_probadas:
            continue
        urls_probadas.append(candidate)
        try:
            if candidate == url_inicial and first_html:
                html = first_html
            else:
                r = _http_get(candidate, session, timeout=_bounded_http_timeout(inmob, 15))
                if r.status_code != 200:
                    errores_relevantes.append(f"{candidate}: HTTP {r.status_code}")
                    motivo_sin_propiedades = f"http_{r.status_code}"
                    continue
                html = r.text

            template = _detect_tokko_template(html)
            if template not in templates_detected:
                templates_detected.append(template)
            new_links = _extract_tokko_internal_listing_links(html, candidate)
            internal_links_detected += len(new_links)
            for link in new_links:
                if link not in candidates and link not in urls_probadas:
                    candidates.append(link)

            if not _is_tokko_html(html):
                motivo_sin_propiedades = "plantilla_no_tokko" if template == "unknown" else "tokko_sin_cards_clasicas"
                continue

            page_props = _parse_tokko_listing_cards(html, candidate, inmob)
            if page_props:
                paginas_leidas += 1
                resultados.extend(page_props)
                _update_strategy_progress(
                    inmob,
                    "tokko_html",
                    listing_urls_total=len(candidates),
                    listing_urls_processed=len(urls_probadas),
                    listing_urls_remaining=max(len(candidates) - len(urls_probadas), 0),
                    paginas_leidas=paginas_leidas,
                    propiedades_detectadas=len(resultados),
                    current_url=candidate,
                )

                max_pages = min(int(inmob.get("paginas_estimadas") or 12), 30)
                for page_num in range(2, max_pages + 1):
                    _check_strategy_deadline(inmob, "tokko_html")
                    if _deadline_remaining_seconds(_strategy_deadline(inmob)) <= 8:
                        errores_relevantes.append("paginacion_tokko_detenida_por_presupuesto")
                        break
                    next_url = _add_query_param(candidate, "p", page_num)
                    urls_probadas.append(next_url)
                    try:
                        pr = _http_get(next_url, session, timeout=_bounded_http_timeout(inmob, 10))
                        if pr.status_code != 200 or "--NoMoreProperties--" in pr.text:
                            break
                        more_props = _parse_tokko_listing_cards(pr.text, next_url, inmob)
                        if not more_props:
                            break
                        before = len(resultados)
                        resultados.extend(more_props)
                        resultados = _dedupe_props(resultados)
                        paginas_leidas += 1
                        _update_strategy_progress(
                            inmob,
                            "tokko_html",
                            listing_urls_total=len(candidates),
                            listing_urls_processed=len(urls_probadas),
                            listing_urls_remaining=max(len(candidates) - len(urls_probadas), 0),
                            paginas_leidas=paginas_leidas,
                            propiedades_detectadas=len(resultados),
                            current_url=next_url,
                            page_num=page_num,
                        )
                        if len(resultados) == before:
                            break
                    except Exception as exc:
                        errores_relevantes.append(f"{next_url}: {type(exc).__name__}: {str(exc)[:180]}")
                        break

                resultados = _dedupe_props(resultados)
                image_metadata = _enrich_tokko_detail_images(resultados, session, inmob)
                inmob["_scraper_metadata"] = {
                    "urls_probadas": urls_probadas,
                    "cantidad_paginas": paginas_leidas,
                    "cantidad_links_internos_detectados": internal_links_detected,
                    "plantilla_tokko_detectada": templates_detected[0] if templates_detected else "unknown",
                    "plantillas_tokko_detectadas": templates_detected,
                    "extractor_tokko_version": TOKKO_HTML_EXTRACTOR_VERSION,
                    **image_metadata,
                    "errores_relevantes": errores_relevantes[-5:],
                }
                logger.info(
                    "  Tokko HTML: %d propiedades en %d paginas (%s)",
                    len(resultados), paginas_leidas, candidate,
                )
                logger.info(
                    "  Tokko fotos reales: %d con fotos, %d sin fotos, %d falsas descartadas",
                    image_metadata["propiedades_con_fotos_reales"],
                    image_metadata["propiedades_sin_fotos_reales"],
                    image_metadata["imagenes_falsas_descartadas"],
                )
                if image_metadata.get("ejemplos_imagenes_reales"):
                    logger.info("  Ejemplos fotos reales: %s", image_metadata["ejemplos_imagenes_reales"][:3])
                if image_metadata.get("ejemplos_imagenes_descartadas"):
                    logger.info("  Ejemplos descartadas: %s", image_metadata["ejemplos_imagenes_descartadas"][:3])
                if image_metadata.get("fuentes_imagenes"):
                    logger.info("[IMAGE_EXTRACTION_SOURCE] %s", image_metadata["fuentes_imagenes"])
                return resultados

        except Exception as exc:
            errores_relevantes.append(f"{candidate}: {type(exc).__name__}: {str(exc)[:180]}")
            continue
        _update_strategy_progress(
            inmob,
            "tokko_html",
            listing_urls_total=len(candidates),
            listing_urls_processed=len(urls_probadas),
            listing_urls_remaining=max(len(candidates) - len(urls_probadas), 0),
            paginas_leidas=paginas_leidas,
            propiedades_detectadas=len(resultados),
            current_url=candidate,
            errores_relevantes=errores_relevantes[-5:],
        )

    image_stats = _tokko_image_stats(inmob)
    inmob["_scraper_metadata"] = {
        "urls_probadas": urls_probadas,
        "cantidad_paginas": paginas_leidas,
        "cantidad_links_internos_detectados": internal_links_detected,
        "plantilla_tokko_detectada": templates_detected[0] if templates_detected else "unknown",
        "plantillas_tokko_detectadas": templates_detected,
        "motivo_sin_propiedades": motivo_sin_propiedades,
        "extractor_tokko_version": TOKKO_HTML_EXTRACTOR_VERSION,
        "imagenes_falsas_descartadas": int(image_stats.get("imagenes_falsas_descartadas") or 0),
        "imagenes_descartadas_por_motivo": dict(image_stats.get("imagenes_descartadas_por_motivo") or {}),
        "fuentes_imagenes": dict(image_stats.get("fuentes_imagenes") or {}),
        "metodo_extraccion_imagenes": "tokko_card_y_detalle_http",
        "metodos_extraccion_imagenes_usados": sorted((image_stats.get("fuentes_imagenes") or {}).keys()),
        "ejemplos_imagenes_descartadas": image_stats.get("ejemplos_descartados", [])[:TOKKO_FAKE_IMAGE_EXAMPLES_LIMIT],
        "errores_relevantes": errores_relevantes[-5:],
    }
    raise RuntimeError("sin_propiedades: tokko_html no encontro propiedades")


# ---------------------------------------------------------------------------
# Strategy 2: Network Interception (Playwright)
# ---------------------------------------------------------------------------

def _looks_like_property_list(data: Any) -> bool:
    """Heurística: JSON que contiene una lista con >=3 objetos con precio o título."""
    def check_list(lst: list) -> bool:
        if len(lst) < 3:
            return False
        hits = 0
        for item in lst[:10]:
            if not isinstance(item, dict):
                continue
            keys = {k.lower() for k in item}
            if keys & {"price", "precio", "title", "titulo", "address", "direccion"}:
                hits += 1
        return hits >= 2

    if isinstance(data, list):
        return check_list(data)
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list) and check_list(v):
                return True
    return False


def _extract_list_from_json(data: Any) -> List[Dict]:
    if isinstance(data, list):
        return [i for i in data if isinstance(i, dict)]
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list) and len(v) >= 3:
                items = [i for i in v if isinstance(i, dict)]
                if items:
                    return items
    return []


def _generic_map_json(item: Dict, inmob: Dict) -> Dict:
    """Mapeo genérico de un objeto JSON interceptado."""
    def get(*keys):
        for k in keys:
            for dk in item:
                if dk.lower() == k.lower():
                    return item[dk]
        return None

    raw_precio = get("price", "precio", "valor", "monto")
    precio, moneda = normalizar_precio(raw_precio)
    url_prop = get("url", "web_url", "link", "permalink", "href") or ""
    if url_prop and not url_prop.startswith("http"):
        url_prop = urljoin(inmob.get("web", ""), url_prop)
    id_ext = str(get("id", "codigo", "ref", "reference") or "")

    inmob_id = inmob["id"]
    prop = {
        "inmobiliaria_id":     inmob_id,
        "url":                 url_prop or None,
        "id_externo":          id_ext,
        "hash_dedup":          hash_propiedad(inmob_id, id_ext, url_prop),
        "titulo":              str(get("title", "titulo", "publication_title", "name") or ""),
        "descripcion":         limpiar_descripcion(str(get("description", "descripcion", "body") or "")),
        "precio":              precio,
        "moneda":              moneda,
        "precio_ars":          convertir_precio(precio, moneda)[0],
        "precio_usd":          convertir_precio(precio, moneda)[1],
        "tipo_propiedad":      normalizar_tipo(get("type", "tipo", "property_type", "category")),
        "operacion":           normalizar_operacion(get("operation", "operacion", "operation_type", "tipo_operacion")),
        "ambientes":           normalizar_int(get("rooms", "ambientes", "suite_amount")),
        "dormitorios":         normalizar_int(get("bedrooms", "dormitorios", "bedroom_amount")),
        "banos":               normalizar_int(get("bathrooms", "banos", "bathroom_amount")),
        "superficie_total":    normalizar_superficie(get("total_surface", "superficie", "area", "size")),
        "superficie_cubierta": normalizar_superficie(get("roofed_surface", "covered_area", "superficie_cubierta")),
        "direccion":           str(get("address", "direccion", "real_address", "location") or ""),
        "ciudad":              str(get("city", "ciudad") or inmob.get("ciudad", "")),
        "provincia":           str(get("province", "provincia", "state") or inmob.get("provincia", "")),
        "pais":                "Argentina",
        "latitud":             float(get("latitude", "lat")) if get("latitude", "lat") else None,
        "longitud":            float(get("longitude", "lon", "lng")) if get("longitude", "lon", "lng") else None,
        "imagenes":            None,
        "fuente_extraccion":   "network_intercept",
        "cms_origen":          inmob.get("cms_detectado", ""),
        "estado":              "activo",
    }
    prop["score_calidad"] = calcular_score(prop)
    return prop


_TOKKO_KEY_RE = re.compile(r"[?&](?:key|api_key)=([a-zA-Z0-9_\-]{20,80})")


def strategy_network_intercept(inmob: Dict, pw_context, session: Optional[requests.Session] = None) -> List[Dict]:
    """Abre la página con Playwright e intercepta respuestas JSON con propiedades.
    Si detecta una llamada a api.tokkobroker.com, extrae la key y usa la API directamente."""
    url_listado = inmob.get("url_listado") or inmob.get("web", "")
    if not url_listado:
        raise ValueError("sin_url_listado")
    if pw_context is None:
        raise RuntimeError("network_intercept deshabilitado: Playwright no inicializado")

    _check_strategy_deadline(inmob, "network_intercept")
    captured: List[Dict] = []
    detected_api_url: Optional[str] = None
    detected_tokko_key: Optional[str] = None
    lock = threading.Lock()
    stop_capture = threading.Event()

    def handle_response(response):
        nonlocal detected_api_url, detected_tokko_key
        if stop_capture.is_set():
            return
        resp_url = response.url

        # Detectar llamadas a Tokko API
        if "tokkobroker.com" in resp_url and "/api/" in resp_url and detected_tokko_key is None:
            m = _TOKKO_KEY_RE.search(resp_url)
            if m:
                with lock:
                    detected_tokko_key = m.group(1)
            return  # No procesar el JSON aquí; lo haremos via API directamente

        ct = response.headers.get("content-type", "")
        if "json" not in ct:
            return
        try:
            data = response.json()
            if _looks_like_property_list(data):
                items = _extract_list_from_json(data)
                with lock:
                    for item in items:
                        try:
                            captured.append(_generic_map_json(item, inmob))
                        except Exception:
                            pass
                    if detected_api_url is None:
                        detected_api_url = response.url
        except Exception:
            pass

    page = pw_context.new_page()
    try:
        page.set_default_timeout(PLAYWRIGHT_ACTION_TIMEOUT_MS)
        page.set_default_navigation_timeout(PLAYWRIGHT_NAV_TIMEOUT_MS)
        page.on("response", handle_response)
        _playwright_goto(page, url_listado, retries=2, timeout_ms=_bounded_playwright_timeout_ms(inmob, PLAYWRIGHT_NAV_TIMEOUT_MS))
        _human_scroll(page, deadline=_strategy_deadline(inmob))
        page.wait_for_load_state("networkidle", timeout=_bounded_playwright_timeout_ms(inmob, PLAYWRIGHT_LOAD_TIMEOUT_MS))

        if not detected_tokko_key:
            try:
                _check_strategy_deadline(inmob, "network_intercept")
                detected_tokko_key = _buscar_tokko_key_en_html(page.content())
            except Exception:
                pass

        # Si detectamos Tokko key, usamos la API completa
        if detected_tokko_key:
            # Guardar la key para futuras ejecuciones
            inmob["tokko_api_key"] = detected_tokko_key
            try:
                db = SupabasePropiedades()
                db.session.patch(
                    f"{SUPABASE_URL}/rest/v1/inmobiliarias_main",
                    headers=db._headers_minimal,
                    params={"id": f"eq.{inmob['id']}"},
                    json={"tokko_api_key": detected_tokko_key},
                    timeout=10,
                )
            except Exception:
                pass
            http_session = session or _make_http_session()
            return strategy_tokko_api(inmob, http_session)

        # Paginación si detectamos otra API
        if detected_api_url and captured:
            page_num = 2
            while page_num <= 50:
                _check_strategy_deadline(inmob, "network_intercept")
                next_url = _guess_next_api_url(detected_api_url, page_num)
                if not next_url:
                    break
                prev_count = len(captured)
                page.evaluate(f"fetch('{next_url}')")
                time.sleep(1.5)
                if len(captured) == prev_count:
                    break
                page_num += 1
    finally:
        stop_capture.set()
        try:
            page.remove_listener("response", handle_response)
        except Exception:
            pass
        _close_playwright_safely(page, "network_intercept page")

    if not captured:
        raise RuntimeError("sin_propiedades: network intercept no encontró datos")
    return captured


def _guess_next_api_url(base_url: str, page_num: int) -> Optional[str]:
    """Intenta construir la URL de la siguiente página de la API interceptada."""
    # offset= pattern
    m = re.search(r"offset=(\d+)", base_url)
    if m:
        offset_val = int(m.group(1))
        limit_m = re.search(r"limit=(\d+)", base_url)
        limit_val = int(limit_m.group(1)) if limit_m else 20
        new_offset = limit_val * (page_num - 1)
        return re.sub(r"offset=\d+", f"offset={new_offset}", base_url)
    # page= pattern
    m2 = re.search(r"[?&]page=(\d+)", base_url)
    if m2:
        return re.sub(r"(page=)\d+", f"\\g<1>{page_num}", base_url)
    # p= pattern
    m3 = re.search(r"[?&]p=(\d+)", base_url)
    if m3:
        return re.sub(r"(p=)\d+", f"\\g<1>{page_num}", base_url)
    return None


# ---------------------------------------------------------------------------
# Strategy 3: JSON-LD
# ---------------------------------------------------------------------------

_JSONLD_TYPES = {
    "RealEstateListing", "Apartment", "House", "SingleFamilyResidence",
    "Residence", "Product", "LodgingBusiness", "Place",
}


def _parse_jsonld_item(item: Dict, inmob: Dict, source_url: str) -> Optional[Dict]:
    schema_type = item.get("@type", "")
    if isinstance(schema_type, list):
        schema_type = schema_type[0]

    offer = item.get("offers", {}) or {}
    if isinstance(offer, list):
        offer = offer[0] if offer else {}

    raw_precio = offer.get("price") or item.get("price")
    moneda_raw = offer.get("priceCurrency", "ARS")
    precio, moneda = normalizar_precio(raw_precio)
    if moneda == "ARS" and moneda_raw:
        moneda = "USD" if "USD" in moneda_raw.upper() else "ARS"

    url_prop = item.get("url") or source_url
    id_ext   = str(item.get("identifier", "") or item.get("productID", "") or "")
    inmob_id = inmob["id"]

    addr = item.get("address", {}) or {}
    if isinstance(addr, str):
        direccion = addr
        ciudad = inmob.get("ciudad", "")
        barrio = ""
    else:
        direccion = addr.get("streetAddress", "")
        ciudad    = addr.get("addressLocality", "") or inmob.get("ciudad", "")
        barrio    = addr.get("addressRegion", "")

    geo = item.get("geo", {}) or {}
    lat_raw = geo.get("latitude")
    lon_raw = geo.get("longitude")
    lat = float(lat_raw) if lat_raw is not None else None
    lon = float(lon_raw) if lon_raw is not None else None

    fotos: List[str] = []
    imgs = item.get("image", [])
    if isinstance(imgs, str):
        fotos = [imgs]
    elif isinstance(imgs, list):
        for img in imgs:
            if isinstance(img, str):
                fotos.append(img)
            elif isinstance(img, dict):
                fotos.append(img.get("url", ""))
    fotos = clean_property_images(fotos)

    prop = {
        "inmobiliaria_id":     inmob_id,
        "url":                 url_prop,
        "id_externo":          id_ext,
        "hash_dedup":          hash_propiedad(inmob_id, id_ext, url_prop),
        "titulo":              item.get("name", ""),
        "descripcion":         limpiar_descripcion(item.get("description", "")),
        "precio":              precio,
        "moneda":              moneda,
        "precio_ars":          convertir_precio(precio, moneda)[0],
        "precio_usd":          convertir_precio(precio, moneda)[1],
        "tipo_propiedad":      normalizar_tipo(schema_type),
        "operacion":           normalizar_operacion(item.get("businessFunction", "")),
        "ambientes":           normalizar_int(item.get("numberOfRooms")),
        "dormitorios":         normalizar_int(item.get("numberOfBedrooms")),
        "banos":               normalizar_int(item.get("numberOfBathroomsTotal")),
        "superficie_total":    normalizar_superficie(item.get("floorSize", {}).get("value") if isinstance(item.get("floorSize"), dict) else item.get("floorSize")),
        "direccion":           direccion,
        "barrio":              barrio,
        "ciudad":              ciudad,
        "provincia":           inmob.get("provincia", ""),
        "pais":                "Argentina",
        "latitud":             lat,
        "longitud":            lon,
        "imagenes":            [f for f in fotos if f] or None,
        "fuente_extraccion":   "json_ld",
        "cms_origen":          inmob.get("cms_detectado", ""),
        "estado":              "activo",
    }
    prop["score_calidad"] = calcular_score(prop)
    return prop


def strategy_json_ld(inmob: Dict, session: requests.Session) -> List[Dict]:
    url_listado = inmob.get("url_listado") or inmob.get("web", "")
    if not url_listado:
        raise ValueError("sin_url_listado")

    _check_strategy_deadline(inmob, "json_ld")
    resultados: List[Dict] = []
    detail_urls: List[str] = []

    def _extract_from_html(html: str, base_url: str):
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(tag.string or "")
            except Exception:
                continue
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                schema_type = item.get("@type", "")
                if isinstance(schema_type, list):
                    schema_type = schema_type[0]
                if schema_type in _JSONLD_TYPES:
                    try:
                        parsed = _parse_jsonld_item(item, inmob, base_url)
                        if parsed:
                            resultados.append(parsed)
                    except Exception as exc:
                        logger.debug("jsonld parse: %s", exc)
        # Collect property links
        for a in soup.find_all("a", href=True):
            href = urljoin(base_url, a["href"])
            if PROPERTY_URL_PATTERNS.search(href) and href not in detail_urls:
                detail_urls.append(href)

    r = _http_get(url_listado, session, timeout=_bounded_http_timeout(inmob, 12))
    r.raise_for_status()
    _extract_from_html(r.text, url_listado)

    # Visit detail pages to get JSON-LD
    visited = 0
    for durl in detail_urls[:200]:
        _check_strategy_deadline(inmob, "json_ld")
        try:
            time.sleep(0.3)
            dr = _http_get(durl, session, timeout=_bounded_http_timeout(inmob, 6))
            if dr.status_code == 200:
                _extract_from_html(dr.text, durl)
            visited += 1
        except Exception:
            pass

    if not resultados:
        raise RuntimeError("sin_propiedades: json-ld no encontró datos")
    return resultados


def _sitemap_detail_urls_for_base(base_url: str, session: requests.Session, inmob: Dict) -> List[str]:
    parsed = urlparse(base_url)
    base = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else base_url.rstrip("/")
    return [url for url in _fetch_sitemap_urls(base, session, inmob) if _looks_like_real_property_url(url)]


def strategy_wordpress_sitemap_detail(inmob: Dict, session: requests.Session) -> List[Dict]:
    """Extractor WordPress/Houzez: prioriza sitemap y parsea fichas de detalle por HTTP."""
    _check_strategy_deadline(inmob, "wordpress_sitemap_detail")
    base_candidates = _url_host_variants(inmob.get("web") or inmob.get("url_listado"))
    if inmob.get("url_listado"):
        base_candidates.extend(_url_host_variants(inmob.get("url_listado")))
    base_candidates = list(dict.fromkeys(base_candidates))

    urls_probadas: List[str] = []
    detail_urls: List[str] = []
    errores_relevantes: List[str] = []

    for base in base_candidates[:6]:
        _check_strategy_deadline(inmob, "wordpress_sitemap_detail")
        if not base or base in urls_probadas:
            continue
        urls_probadas.append(base)
        try:
            for detail_url in _sitemap_detail_urls_for_base(base, session, inmob):
                if detail_url not in detail_urls:
                    detail_urls.append(detail_url)
        except Exception as exc:
            errores_relevantes.append(f"{base}: {type(exc).__name__}: {str(exc)[:180]}")
        if detail_urls:
            break

    if not detail_urls:
        raise RuntimeError("no_property_links: wordpress_sitemap_detail sin URLs de propiedades")

    resultados: List[Dict] = []

    def _fetch_one(detail_url: str) -> Optional[Dict]:
        try:
            _check_strategy_deadline(inmob, "wordpress_sitemap_detail")
            prop = _extract_detail_page(detail_url, inmob, session)
            if prop:
                prop["fuente_extraccion"] = "wordpress_sitemap_detail"
                prop["cms_origen"] = inmob.get("cms_detectado") or "wordpress"
            time.sleep(random.uniform(0.12, 0.3))
            return prop
        except StrategyTimeoutError:
            raise
        except Exception:
            return None

    max_urls = min(len(detail_urls), 300)
    executor = ThreadPoolExecutor(max_workers=6)
    try:
        futures = {executor.submit(_fetch_one, detail_url): detail_url for detail_url in detail_urls[:max_urls]}
        timeout = max(1.0, _deadline_remaining_seconds(_strategy_deadline(inmob)))
        for future in as_completed(futures, timeout=timeout):
            try:
                prop = future.result()
                if prop:
                    resultados.append(prop)
            except Exception:
                pass
    except TimeoutError:
        errores_relevantes.append("wordpress_sitemap_detail_detenido_por_timeout")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    resultados = _dedupe_props(resultados)
    inmob["_scraper_metadata"] = {
        **dict(inmob.get("_scraper_metadata") or {}),
        "wordpress_sitemap_urls_probadas": urls_probadas,
        "wordpress_sitemap_urls_detectadas": len(detail_urls),
        "cantidad_paginas": len(detail_urls),
        "errores_relevantes": errores_relevantes[-8:],
    }
    if not resultados:
        raise RuntimeError("parsing_failed: wordpress_sitemap_detail encontro URLs pero no datos extraibles")
    logger.info("  WordPress sitemap detail: %d propiedades desde %d URLs", len(resultados), len(detail_urls))
    return resultados


# ---------------------------------------------------------------------------
# Strategy 4: Sitemap crawler
# ---------------------------------------------------------------------------

SITEMAP_PATHS = [
    "/sitemap.xml",
    "/wp-sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap-propiedades.xml",
    "/sitemap-properties.xml",
    "/sitemap-inmuebles.xml",
    "/property-sitemap.xml",
    "/propiedades-sitemap.xml",
    "/inmuebles-sitemap.xml",
    "/page-sitemap.xml",
    "/post-sitemap.xml",
]


def _fetch_sitemap_urls(base: str, session: requests.Session, inmob: Optional[Dict] = None) -> List[str]:
    prop_urls: List[str] = []
    for path in SITEMAP_PATHS:
        if inmob is not None:
            _check_strategy_deadline(inmob, "sitemap")
        try:
            timeout = _bounded_http_timeout(inmob, 8) if inmob is not None else 20
            r = _http_get(urljoin(base, path), session, timeout=timeout)
            if r.status_code != 200:
                continue
            root = ET.fromstring(r.text)
            ns  = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            # Sitemap index
            for sitemap_tag in root.findall(".//sm:sitemap/sm:loc", ns):
                sub_url = sitemap_tag.text.strip() if sitemap_tag.text else ""
                if sub_url:
                    try:
                        if inmob is not None:
                            _check_strategy_deadline(inmob, "sitemap")
                        timeout = _bounded_http_timeout(inmob, 6) if inmob is not None else 20
                        sub_r = _http_get(sub_url, session, timeout=timeout)
                        if sub_r.status_code == 200:
                            sub_root = ET.fromstring(sub_r.text)
                            for loc in sub_root.findall(".//sm:url/sm:loc", ns):
                                u = loc.text.strip() if loc.text else ""
                                if u and PROPERTY_URL_PATTERNS.search(u):
                                    prop_urls.append(u)
                    except Exception:
                        pass
            # Direct urls
            for loc_tag in root.findall(".//sm:url/sm:loc", ns):
                u = loc_tag.text.strip() if loc_tag.text else ""
                if u and PROPERTY_URL_PATTERNS.search(u):
                    prop_urls.append(u)
            if prop_urls:
                break
        except Exception:
            continue
    return list(dict.fromkeys(prop_urls))  # deduplicate preserving order


def _extract_detail_page(url: str, inmob: Dict, session: requests.Session) -> Optional[Dict]:
    """Extrae datos de una página de detalle. Usa ScraperAPI si falla, AI si todo falla."""
    bounded_strategy = inmob.get("_strategy_name") in {
        "sitemap",
        "wordpress_html",
        "static_html",
        "static_html_detail",
        "static_html_tokko_detail",
        "wordpress_sitemap_detail",
        "wordpress_essential_real_estate_detail",
        "wordpress_estatik_detail",
        "wordpress_realhomes_detail",
        "wordpress_generic_detail",
    }
    if bounded_strategy:
        _check_strategy_deadline(inmob, str(inmob.get("_strategy_name") or "detail"))
    raw_html = None

    # Intento 1: request directo
    try:
        timeout = _bounded_http_timeout(inmob, 6) if bounded_strategy else 20
        r = _http_get(url, session, timeout=timeout)
        if r.status_code == 200:
            raw_html = _decode_response_text(r)
    except Exception:
        pass

    # Intento 2: ScraperAPI si falló o bloqueado
    if not raw_html and SCRAPERAPI_KEY and not bounded_strategy:
        try:
            r2 = _scraperapi_get(url, session, timeout=30, js_render=False)
            if r2.status_code == 200:
                raw_html = _decode_response_text(r2)
                logger.debug("ScraperAPI OK para %s", url)
        except Exception:
            pass

    if not raw_html:
        return None

    soup = BeautifulSoup(raw_html, "html.parser")

    # Intentar JSON-LD primero
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                t = item.get("@type", "")
                if isinstance(t, list):
                    t = t[0]
                if t in _JSONLD_TYPES:
                    prop_jsonld = _parse_jsonld_item(item, inmob, url)
                    if prop_jsonld:
                        html_images = extraer_imagenes(soup, url)
                        if html_images and not _has_real_images(prop_jsonld.get("imagenes")):
                            prop_jsonld["imagenes"] = html_images
                            raw_json = prop_jsonld.get("raw_json") if isinstance(prop_jsonld.get("raw_json"), dict) else {}
                            raw_json["imagenes_enriquecidas_desde_html"] = True
                            raw_json["imagenes_reales"] = len(html_images)
                            prop_jsonld["raw_json"] = raw_json
                        return prop_jsonld
        except Exception:
            pass

    # Fallback: extracción heurística HTML
    prop = _html_extract_detail(soup, url, inmob, raw_html)

    # Último recurso: IA
    if prop is None and GROQ_API_KEY:
        prop = _ai_extraer_propiedad(raw_html, url, inmob)

    return prop


_GENERIC_BAD_TITLES = {
    "descripcion",
    "descripción",
    "detalle",
    "propiedad",
    "sin titulo",
    "sin título",
    "propiedad sin titulo",
    "propiedad sin título",
    "los resultados de su busqueda",
    "los resultados de su búsqueda",
}


_PROPERTY_TITLE_HINTS = re.compile(
    r"(venta|alquiler|casa|departamento|depto|monoambiente|terreno|lote|local|cochera|"
    r"galpon|galp[oó]n|oficina|ph|ambiente|dormitorio|m2|pozo)",
    re.I,
)


def _looks_like_agency_title(value: Any) -> bool:
    text = _fix_mojibake_text(value)
    low = text.lower()
    if _PROPERTY_TITLE_HINTS.search(low):
        return False
    return any(marker in low for marker in (
        "inmobiliaria",
        "propiedades",
        "bienes raices",
        "bienes raíces",
        "operaciones inmobiliarias",
        "real estate",
    ))


def _is_useful_scraped_title(value: Any) -> bool:
    text = _fix_mojibake_text(value)
    if len(text) < 5:
        return False
    if _looks_like_agency_title(text):
        return False
    key = _normalize_text_key(text)
    if key in {_normalize_text_key(title) for title in _GENERIC_BAD_TITLES}:
        return False
    if re.fullmatch(r"(descripcion|descripci[oó]n|detalle|propiedad)\s*:?", text, re.I):
        return False
    return True


def _title_from_detail_url(url: str) -> str:
    path = unquote(urlparse(url).path or "")
    slug = path.rstrip("/").split("/")[-1]
    slug = re.sub(r"^(propiedad|property|inmueble|ficha|detalle)[-_]?\d*[-_/]?", "", slug, flags=re.I)
    slug = re.sub(r"\b\d{4,}\b", " ", slug)
    slug = re.sub(r"[-_]+", " ", slug)
    slug = _fix_mojibake_text(slug)
    return slug.title() if _is_useful_scraped_title(slug) else ""


def _first_meta_content(soup: BeautifulSoup, *selectors: str) -> str:
    for selector in selectors:
        el = soup.select_one(selector)
        if el:
            content = el.get("content") or el.get("value") or ""
            content = _fix_mojibake_text(content)
            if content:
                return content
    return ""


def _extract_price_from_text(text: str) -> Tuple[Optional[float], str]:
    fixed = _fix_mojibake_text(text)
    patterns = [
        r"(?:U\$S|US\$|USD)\s*[\d.,]{3,}",
        r"\$\s*[\d.,]{4,}",
        r"(?:ARS|Pesos?)\s*[\d.,]{4,}",
    ]
    for pattern in patterns:
        match = re.search(pattern, fixed, flags=re.I)
        if not match:
            continue
        precio, moneda = normalizar_precio(match.group(0))
        if precio and precio > 0:
            return precio, moneda
    return None, "ARS"


def _normalizar_precio_detalle(raw: Any) -> Tuple[Optional[float], str]:
    fixed = _fix_mojibake_text(raw)
    if not fixed:
        return None, "ARS"
    precise_price, precise_currency = _extract_price_from_text(fixed)
    if precise_price:
        if precise_currency == "USD" and precise_price < 1000:
            return None, precise_currency
        if precise_currency == "ARS" and precise_price < 10000:
            return None, precise_currency
        return precise_price, precise_currency
    # Evita convertir textos largos con direccion/superficie/telefono en un precio concatenado.
    if len(fixed) > 80 or len(re.findall(r"\d+", fixed)) > 2:
        return None, "ARS"
    price, currency = normalizar_precio(fixed)
    if price and ((currency == "USD" and price < 1000) or (currency == "ARS" and price < 10000)):
        return None, currency
    return price, currency


def _extract_address_from_text(text: str) -> str:
    fixed = _fix_mojibake_text(text)
    match = re.search(
        r"\b([A-ZÁÉÍÓÚÑa-záéíóúñ][A-ZÁÉÍÓÚÑa-záéíóúñ.\s]{2,35}\s+\d{2,5}(?:\s*[A-Z]{0,2})?)\b",
        fixed,
    )
    return _fix_mojibake_text(match.group(1)) if match else ""


def _html_extract_detail(soup: BeautifulSoup, url: str, inmob: Dict,
                         raw_html: str = "") -> Optional[Dict]:
    """Extracción heurística de datos de detalle desde HTML."""
    def find_text(*selectors):
        for sel in selectors:
            el = soup.select_one(sel)
            if el:
                text = _fix_mojibake_text(el.get_text(" ", strip=True))
                if text:
                    return text
        return ""

    title_candidates = [
        find_text("h1", ".property-title", ".titulo", ".listing-title"),
        _title_from_detail_url(url),
        _first_meta_content(soup, "meta[property='og:title']", "meta[name='twitter:title']"),
        find_text("title"),
    ]
    title = next((candidate for candidate in title_candidates if _is_useful_scraped_title(candidate)), "")
    desc = find_text(
        ".description", ".descripcion", '[class*="description"]',
        '[class*="descripcion"]', ".property-description", "article p",
    )
    if not desc:
        desc = _first_meta_content(soup, "meta[property='og:description']", "meta[name='description']")
    precio_raw = find_text(
        ".property-price", ".listing-price", ".price", ".precio",
        '[class*="precio"]', '[class*="price"]', "[itemprop='price']",
    )
    precio, moneda = _normalizar_precio_detalle(precio_raw)
    page_text = _fix_mojibake_text(soup.get_text(" ", strip=True))
    if not precio:
        precio, moneda = _normalizar_precio_detalle(page_text)

    tipo_raw = find_text('[class*="tipo"]', '[class*="type"]', ".property-type") or title or page_text[:300]
    op_raw   = find_text('[class*="operaci"]', '[class*="operation"]') or title or url

    address_raw = find_text(
        ".address", ".direccion", ".location", '[class*="address"]',
        '[class*="direccion"]', '[class*="location"]',
    )
    if not address_raw:
        address_raw = _extract_address_from_text(page_text)

    ambientes    = normalizar_int(find_text('[class*="ambiente"]', '[class*="room"]', '[class*="environment"]'))
    dormitorios  = normalizar_int(find_text('[class*="dormitor"]', '[class*="bedroom"]', '[class*="suite"]', '[class*="habitac"]'))
    banos        = normalizar_int(find_text('[class*="bano"]', '[class*="bathroom"]', '[class*="bath"]', '[class*="toilette"]'))
    cocheras     = normalizar_int(find_text('[class*="cochera"]', '[class*="garage"]', '[class*="parking"]', '[class*="estacion"]'))
    sup_cubierta = normalizar_superficie(find_text('[class*="cubierta"]', '[class*="roofed"]', '[class*="covered"]'))
    sup_text     = find_text('[class*="surface"]', '[class*="superficie"]', '[class*="area"]', '[class*="m2"]')
    sup_total    = normalizar_superficie(sup_text)

    exp_raw = find_text('[class*="expens"]', '[class*="expense"]', '[class*="gasto"]')
    expensas, expensas_moneda = (None, None)
    if exp_raw:
        ev, em = normalizar_precio(exp_raw)
        expensas, expensas_moneda = ev, em

    piso = find_text('[class*="piso"]', '[class*="floor"]', '[class*="planta"]') or None

    page_text_lower = page_text.lower()
    apto_credito      = bool(re.search(r"apto\s+cr[eé]dito|acepta\s+cr[eé]dito|cr[eé]dito\s+hipotecario", page_text_lower))
    apto_profesional  = bool(re.search(r"apto\s+profesional|uso\s+profesional", page_text_lower))

    # Video URL (YouTube/Vimeo embed)
    video_url = None
    for iframe in soup.find_all("iframe", src=True):
        src = iframe.get("src", "")
        if "youtube" in src or "youtu.be" in src or "vimeo" in src:
            video_url = src
            break

    # Plano URL (PDF o link con "plano" en href/texto)
    plano_url = None
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        txt_a = a.get_text(strip=True).lower()
        if re.search(r"plano|floor.?plan|blueprint", href + " " + txt_a, re.I):
            plano_url = urljoin(url, href)
            break

    # Amenities
    amenities = extraer_amenities_html(soup, page_text_lower)

    # Fotos con extractor mejorado
    detail_image_stats = _new_image_stats()
    fotos = extraer_imagenes(soup, url, detail_image_stats)
    aggregate_image_stats = inmob.setdefault("_image_extraction_stats", _new_image_stats())
    _merge_image_stats(aggregate_image_stats, detail_image_stats)

    # Agente
    agente_nombre, agente_telefono = extraer_agente(soup)

    # Coordenadas desde Google Maps
    lat, lon = extraer_coordenadas_gmaps(raw_html or str(soup))

    inmob_id = inmob["id"]
    id_ext   = ""
    m = re.search(r"/(\d{3,})[/_-]?", url)
    if m:
        id_ext = m.group(1)

    if not _is_useful_scraped_title(title) and precio:
        title = _title_from_detail_url(url) or "Propiedad"

    if not _is_useful_scraped_title(title) and not precio:
        return None

    precio_ars, precio_usd = convertir_precio(precio, moneda)
    prop = {
        "inmobiliaria_id":     inmob_id,
        "url":                 url,
        "id_externo":          id_ext,
        "hash_dedup":          hash_propiedad(inmob_id, id_ext, url),
        "titulo":              title,
        "descripcion":         limpiar_descripcion(desc),
        "precio":              precio,
        "moneda":              moneda,
        "precio_ars":          precio_ars,
        "precio_usd":          precio_usd,
        "tipo_propiedad":      normalizar_tipo(tipo_raw),
        "operacion":           normalizar_operacion(op_raw),
        "ambientes":           ambientes,
        "dormitorios":         dormitorios,
        "banos":               banos,
        "cocheras":            cocheras,
        "superficie_total":    sup_total,
        "superficie_cubierta": sup_cubierta,
        "expensas":            expensas,
        "expensas_moneda":     expensas_moneda,
        "piso":                piso,
        "apto_credito":        apto_credito or None,
        "apto_profesional":    apto_profesional or None,
        "direccion":           address_raw,
        "ciudad":              inmob.get("ciudad", ""),
        "provincia":           inmob.get("provincia", ""),
        "pais":                "Argentina",
        "latitud":             lat,
        "longitud":            lon,
        "imagenes":            fotos or None,
        "video_url":           video_url,
        "plano_url":           plano_url,
        "amenities":           amenities,
        "agente_nombre":       agente_nombre,
        "agente_telefono":     agente_telefono,
        "fuente_extraccion":   str(inmob.get("_strategy_name") or "static_html"),
        "cms_origen":          inmob.get("cms_detectado", ""),
        "estado":              "activo",
    }
    prop["score_calidad"] = calcular_score(prop)
    return prop


def strategy_sitemap(inmob: Dict, session: requests.Session) -> List[Dict]:
    _check_strategy_deadline(inmob, "sitemap")
    base = inmob.get("web", "")
    parsed = urlparse(base)
    base = f"{parsed.scheme}://{parsed.netloc}"

    urls = _fetch_sitemap_urls(base, session, inmob)
    if not urls:
        raise RuntimeError("sin_propiedades: sitemap sin URLs de propiedades")

    resultados: List[Dict] = []

    def _fetch_one(url: str) -> Optional[Dict]:
        try:
            _check_strategy_deadline(inmob, "sitemap")
            prop = _extract_detail_page(url, inmob, session)
            time.sleep(random.uniform(0.2, 0.5))
            return prop
        except StrategyTimeoutError:
            raise
        except Exception:
            return None

    executor = ThreadPoolExecutor(max_workers=5)
    try:
        futures = {executor.submit(_fetch_one, u): u for u in urls[:500]}
        for future in as_completed(futures, timeout=max(1.0, _deadline_remaining_seconds(_strategy_deadline(inmob)))):
            try:
                prop = future.result()
                if prop:
                    resultados.append(prop)
            except Exception:
                pass
    except TimeoutError:
        logger.warning("  Sitemap timeout: se corta extraccion de detalles")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    if not resultados:
        raise RuntimeError("sin_propiedades: sitemap URLs encontradas pero sin datos extraíbles")
    return resultados


# ---------------------------------------------------------------------------
# Strategy 4b: WordPress lightweight extractor (HTTP-only)
# ---------------------------------------------------------------------------

_WORDPRESS_LISTING_KEYWORDS = (
    "propiedades", "propiedad", "inmuebles", "inmueble", "venta", "ventas",
    "alquiler", "alquileres", "emprendimiento", "emprendimientos",
    "desarrollo", "desarrollos", "ver mas", "ver más", "detalle",
)

_WORDPRESS_LISTING_PATHS = [
    "/", "/propiedades", "/propiedad", "/inmuebles", "/inmueble",
    "/ventas", "/venta", "/alquileres", "/alquiler",
    "/emprendimientos", "/desarrollos",
]

_WORDPRESS_REST_TYPES = [
    "propiedad", "propiedades", "inmueble", "inmuebles",
    "property", "properties", "estate_property", "real-estate",
]


def _detect_wordpress_plugin(html: str) -> str:
    low = (html or "").lower()
    if "houzez" in low:
        return "houzez"
    if "realhomes" in low or "inspiry" in low or "rh_prop_card" in low or "rh-property" in low:
        return "realhomes"
    if "essential-real-estate" in low or "/essential-real-estate/" in low or "ere-property" in low or "ere-" in low:
        return "essential_real_estate"
    if "estatik" in low or "es_property" in low or "es-listing" in low or "es-property" in low:
        return "estatik"
    if "wp-content" in low or "wp-json" in low or "wordpress" in low:
        return "wordpress_generic"
    return "unknown"


def _extract_keyword_internal_links(html: str, current_url: str, keywords: Tuple[str, ...]) -> List[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    parsed = urlparse(current_url)
    domain = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else current_url.rstrip("/")
    links: List[str] = []
    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        text = a.get_text(" ", strip=True).lower()
        href_low = href.lower()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        if not any(kw in href_low or kw in text for kw in keywords):
            continue
        full = urljoin(domain + "/", href)
        if urlparse(full).netloc == urlparse(domain).netloc and full not in links:
            links.append(full)
    return links


def _wordpress_candidate_urls(inmob: Dict, first_html: str = "", first_url: str = "") -> List[str]:
    urls: List[str] = []

    def add(url: Optional[str]) -> None:
        if not url:
            return
        clean = _normalize_queue_url(str(url).split("#", 1)[0])
        if _is_noise_property_url(clean):
            return
        if clean and clean not in urls:
            urls.append(clean)

    for variant in _url_host_variants(inmob.get("url_listado")):
        add(variant)
    for variant in _url_host_variants(inmob.get("web")):
        add(variant)
    if first_html and first_url:
        for link in _extract_keyword_internal_links(first_html, first_url, _WORDPRESS_LISTING_KEYWORDS):
            add(link)
    for base in _url_host_variants(inmob.get("web") or first_url):
        for path in _WORDPRESS_LISTING_PATHS:
            add(urljoin(base.rstrip("/") + "/", path.lstrip("/")))
    return urls[:40]


def _extract_wordpress_property_links(html: str, current_url: str) -> List[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    links = _extract_keyword_internal_links(html, current_url, _WORDPRESS_LISTING_KEYWORDS)
    selectors = [
        ".property a[href]", ".propiedad a[href]", ".inmueble a[href]",
        "[class*='property'] a[href]", "[class*='propiedad'] a[href]",
        "[class*='inmueble'] a[href]", "article a[href]",
        "a[href*='propiedad']", "a[href*='inmueble']", "a[href*='property']",
    ]
    for selector in selectors:
        for a in soup.select(selector):
            href = (a.get("href") or "").strip()
            if not href:
                continue
            full = urljoin(current_url, href)
            if urlparse(full).netloc == urlparse(current_url).netloc and full not in links:
                links.append(full)
    return links[:300]


_WORDPRESS_PLUGIN_LISTING_PATHS: Dict[str, Tuple[str, ...]] = {
    "essential_real_estate": (
        "/", "/properties/", "/property/", "/property-status/for-sale/",
        "/property-status/venta/", "/property-status/alquiler/",
        "/property-type/casa/", "/property-type/departamento/",
        "/property-type/local/", "/property-type/terreno/", "/venta/", "/alquiler/",
        "/?post_type=property",
    ),
    "estatik": (
        "/", "/propiedades/", "/propiedad/", "/properties/", "/property/",
        "/venta/", "/ventas/", "/alquiler/", "/alquileres/",
        "/?post_type=properties", "/?post_type=property",
    ),
    "realhomes": (
        "/", "/properties/", "/property/", "/propiedades/",
        "/property-status/venta/", "/property-status/alquiler/",
        "/property-status/for-sale/", "/property-status/for-rent/",
        "/property-type/casa/", "/property-type/departamento/",
        "/property-type/terreno/", "/property-type/local/",
        "/venta/", "/alquiler/",
    ),
    "wordpress_generic": (
        "/", "/propiedades/", "/propiedad/", "/properties/", "/property/",
        "/inmuebles/", "/inmueble/", "/venta/", "/ventas/", "/alquiler/",
        "/alquileres/",
    ),
}

_WORDPRESS_PLUGIN_MAX_LISTING_PAGES: Dict[str, int] = {
    "essential_real_estate": 28,
    "estatik": 36,
    "realhomes": 28,
    "wordpress_generic": 22,
}

_WORDPRESS_PLUGIN_MAX_DETAILS: Dict[str, int] = {
    "essential_real_estate": 180,
    "estatik": 220,
    "realhomes": 180,
    "wordpress_generic": 140,
}


def _wordpress_plugin_strategy_name(plugin: str) -> str:
    normalized = (plugin or "wordpress_generic").strip().lower()
    if normalized in {"essential_real_estate", "estatik", "realhomes"}:
        return f"wordpress_{normalized}_detail"
    return "wordpress_generic_detail"


def _wordpress_base_url(url: str) -> str:
    parsed = urlparse(_normalize_queue_url(url))
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return _normalize_queue_url(url).rstrip("/")


def _same_site_url(url: str, base_url: str) -> bool:
    return bool(urlparse(url).netloc) and urlparse(url).netloc == urlparse(base_url).netloc


def _looks_like_wordpress_plugin_property_url(url: str, plugin: str = "wordpress_generic") -> bool:
    if not url or _is_noise_property_url(url):
        return False
    parsed = urlparse(str(url))
    path = unquote((parsed.path or "").lower()).strip("/")
    if not path:
        return False
    if re.search(r"^(property-status|property-type|property-feature|property-city|property-state|estado|tipo-propiedad|categoria|category|tag)/", path):
        return False
    if path in {
        "property", "properties", "propiedad", "propiedades", "inmueble", "inmuebles",
        "venta", "ventas", "alquiler", "alquileres",
    }:
        return False

    first = path.split("/", 1)[0]
    slug = path.split("/", 1)[1] if "/" in path else ""
    if plugin == "essential_real_estate":
        return first in {"property", "properties"} and len(slug) >= 6
    if plugin == "estatik":
        return first in {"propiedad", "propiedades", "property", "properties", "inmueble", "inmuebles"} and len(slug) >= 6
    if plugin == "realhomes":
        return first in {"property", "properties", "propiedad", "propiedades"} and len(slug) >= 6
    return _looks_like_real_property_url(url)


def _extract_wordpress_plugin_property_links(html: str, current_url: str, plugin: str) -> List[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    current_netloc = urlparse(current_url).netloc
    links: List[str] = []
    selectors = [
        "a[href*='/property/']", "a[href*='/properties/']",
        "a[href*='/propiedad/']", "a[href*='/propiedades/']",
        "a[href*='/inmueble/']", "a[href*='/inmuebles/']",
        ".property a[href]", ".property-item a[href]", ".property-listing a[href]",
        ".ere-property a[href]", "[class*='ere-property'] a[href]",
        "[class*='es-listing'] a[href]", "[class*='es-property'] a[href]",
        "[class*='rh_prop_card'] a[href]", "[class*='rh-property'] a[href]",
        "article a[href]", ".card a[href]",
    ]
    for selector in selectors:
        for a in soup.select(selector):
            href = (a.get("href") or "").strip()
            if not href:
                continue
            full = urljoin(current_url, href).split("#", 1)[0]
            if urlparse(full).netloc != current_netloc:
                continue
            if _looks_like_wordpress_plugin_property_url(full, plugin) and full not in links:
                links.append(full)

    script_patterns = (
        r"""["']([^"']*/(?:property|properties|propiedad|propiedades|inmueble|inmuebles)/[^"']{6,})["']""",
        r"""https?://[^\s"'<>]+/(?:property|properties|propiedad|propiedades|inmueble|inmuebles)/[^\s"'<>]+""",
    )
    for pattern in script_patterns:
        for match in re.findall(pattern, html or "", flags=re.I):
            candidate = match if isinstance(match, str) else match[0]
            full = urljoin(current_url, candidate).split("#", 1)[0]
            if urlparse(full).netloc != current_netloc:
                continue
            if _looks_like_wordpress_plugin_property_url(full, plugin) and full not in links:
                links.append(full)
    return links[:500]


def _looks_like_wordpress_listing_url(url: str, base_url: str, plugin: str) -> bool:
    if not url or _is_noise_property_url(url):
        return False
    if not _same_site_url(url, base_url):
        return False
    if _looks_like_wordpress_plugin_property_url(url, plugin):
        return False
    path = unquote((urlparse(url).path or "").lower()).strip("/")
    query = (urlparse(url).query or "").lower()
    listing_markers = (
        "property-status", "property-type", "property-city", "property-state",
        "properties", "property", "propiedades", "propiedad", "inmuebles",
        "inmueble", "venta", "ventas", "alquiler", "alquileres", "page",
    )
    query_markers = ("post_type=property", "post_type=properties", "paged=", "es_")
    return any(marker in path for marker in listing_markers) or any(marker in query for marker in query_markers)


def _extract_wordpress_listing_links(html: str, current_url: str, base_url: str, plugin: str) -> List[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    links: List[str] = []
    selectors = [
        "a[rel='next']", "link[rel='next']", ".pagination a[href]",
        ".page-numbers a[href]", ".nav-links a[href]", "a[href*='/page/']",
        "a[href*='paged=']", "a[href*='page=']",
        "a[href*='property-status']", "a[href*='property-type']",
        "a[href*='propiedades']", "a[href*='properties']",
    ]
    for selector in selectors:
        for node in soup.select(selector):
            href = (node.get("href") or "").strip()
            text = node.get_text(" ", strip=True).lower()
            if not href:
                continue
            full = urljoin(current_url, href).split("#", 1)[0]
            if not _looks_like_wordpress_listing_url(full, base_url, plugin):
                continue
            if (
                re.search(r"/page/\d+", full, re.I)
                or re.search(r"[?&](paged|page)=\d+", full, re.I)
                or any(word in text for word in ("siguiente", "next", ">", "mas", "mÃ¡s"))
                or "property-status" in full.lower()
                or "property-type" in full.lower()
            ):
                if full not in links:
                    links.append(full)
    for link in _extract_keyword_internal_links(html, current_url, _WORDPRESS_LISTING_KEYWORDS):
        if _looks_like_wordpress_listing_url(link, base_url, plugin) and link not in links:
            links.append(link)
    return links[:120]


def _wordpress_plugin_candidate_urls(inmob: Dict, first_html: str = "", first_url: str = "", plugin: str = "wordpress_generic") -> List[str]:
    urls: List[str] = []

    def add(url: Optional[str]) -> None:
        if not url:
            return
        clean = _normalize_queue_url(str(url).split("#", 1)[0])
        if clean and not _is_noise_property_url(clean) and clean not in urls:
            urls.append(clean)

    for variant in _url_host_variants(inmob.get("url_listado")):
        add(variant)
    for variant in _url_host_variants(inmob.get("web")):
        add(variant)
    base_sources = _url_host_variants(inmob.get("web") or first_url or inmob.get("url_listado"))
    for base in base_sources:
        root = _wordpress_base_url(base)
        for path in _WORDPRESS_PLUGIN_LISTING_PATHS.get(plugin, _WORDPRESS_PLUGIN_LISTING_PATHS["wordpress_generic"]):
            add(urljoin(root.rstrip("/") + "/", path.lstrip("/")))
    if first_html and first_url:
        base = _wordpress_base_url(first_url)
        for link in _extract_wordpress_listing_links(first_html, first_url, base, plugin):
            add(link)
    return urls[:80]


def _extract_wordpress_details_from_urls(
    detail_urls: List[str],
    inmob: Dict,
    session: requests.Session,
    strategy_name: str,
    plugin: str,
    max_details: int,
) -> Tuple[List[Dict], List[str]]:
    resultados: List[Dict] = []
    errores_relevantes: List[str] = []

    def _fetch_one(detail_url: str) -> Optional[Dict]:
        try:
            _check_strategy_deadline(inmob, strategy_name)
            prop = _extract_detail_page(detail_url, inmob, session)
            if prop:
                prop["fuente_extraccion"] = strategy_name
                prop["cms_origen"] = inmob.get("cms_detectado") or "wordpress"
            time.sleep(random.uniform(0.05, 0.18))
            return prop
        except StrategyTimeoutError:
            raise
        except Exception:
            return None

    urls = detail_urls[:max_details]
    _update_strategy_progress(
        inmob,
        strategy_name,
        detail_urls_total=len(urls),
        detail_urls_processed=0,
        detail_urls_remaining=len(urls),
    )
    executor = ThreadPoolExecutor(max_workers=6)
    try:
        futures = {executor.submit(_fetch_one, detail_url): detail_url for detail_url in urls}
        timeout = max(1.0, _deadline_remaining_seconds(_strategy_deadline(inmob)))
        processed = 0
        for future in as_completed(futures, timeout=timeout):
            processed += 1
            try:
                prop = future.result()
                if prop:
                    resultados.append(prop)
            except StrategyTimeoutError:
                raise
            except Exception:
                pass
            _update_strategy_progress(
                inmob,
                strategy_name,
                detail_urls_total=len(urls),
                detail_urls_processed=processed,
                detail_urls_remaining=max(len(urls) - processed, 0),
                propiedades_detectadas=len(resultados),
            )
    except TimeoutError:
        errores_relevantes.append(f"{strategy_name}_detalles_detenidos_por_timeout")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    return _dedupe_props(resultados), errores_relevantes


def _extract_wordpress_details_sequential(
    detail_urls: List[str],
    inmob: Dict,
    session: requests.Session,
    strategy_name: str,
    max_details: int,
) -> Tuple[List[Dict], List[str]]:
    """Detalle HTTP estable para plugins sensibles a concurrencia."""
    resultados: List[Dict] = []
    errores_relevantes: List[str] = []
    urls = detail_urls[:max_details]
    _update_strategy_progress(
        inmob,
        strategy_name,
        detail_urls_total=len(urls),
        detail_urls_processed=0,
        detail_urls_remaining=len(urls),
    )
    for index, detail_url in enumerate(urls, start=1):
        _check_strategy_deadline(inmob, strategy_name)
        if _deadline_remaining_seconds(_strategy_deadline(inmob)) <= 4:
            errores_relevantes.append(f"{strategy_name}_detalles_detenidos_por_presupuesto")
            break
        try:
            prop = _extract_detail_page(detail_url, inmob, session)
            if prop:
                prop["fuente_extraccion"] = strategy_name
                prop["cms_origen"] = inmob.get("cms_detectado") or "wordpress"
                resultados.append(prop)
            time.sleep(random.uniform(0.06, 0.18))
        except Exception as exc:
            if len(errores_relevantes) < 10:
                errores_relevantes.append(f"{detail_url}: {type(exc).__name__}: {str(exc)[:160]}")
        _update_strategy_progress(
            inmob,
            strategy_name,
            detail_urls_total=len(urls),
            detail_urls_processed=index,
            detail_urls_remaining=max(len(urls) - index, 0),
            propiedades_detectadas=len(resultados),
        )
    return _dedupe_props(resultados), errores_relevantes


def _strategy_wordpress_plugin_detail(inmob: Dict, session: requests.Session, plugin: str) -> List[Dict]:
    strategy_name = _wordpress_plugin_strategy_name(plugin)
    url_inicial = inmob.get("url_listado") or inmob.get("web", "")
    if not url_inicial:
        raise ValueError("sin_url_listado")

    _check_strategy_deadline(inmob, strategy_name)
    urls_probadas: List[str] = []
    detail_urls: List[str] = []
    errores_relevantes: List[str] = []
    plugin_detectado = plugin or "wordpress_generic"
    first_html = ""
    final_url = _normalize_queue_url(url_inicial)

    try:
        r0 = _http_get(final_url, session, timeout=_bounded_http_timeout(inmob, 7), use_scraper_on_block=False)
        if r0.status_code == 200:
            first_html = _decode_response_text(r0)
            final_url = r0.url or final_url
            detected = _detect_wordpress_plugin(first_html)
            if detected != "unknown":
                plugin_detectado = detected
    except Exception as exc:
        errores_relevantes.append(f"{final_url}: {type(exc).__name__}: {str(exc)[:180]}")

    base_url = _wordpress_base_url(final_url)
    candidates = _wordpress_plugin_candidate_urls(inmob, first_html, final_url, plugin_detectado)
    max_listing_pages = _WORDPRESS_PLUGIN_MAX_LISTING_PAGES.get(plugin_detectado, 22)
    max_details = _WORDPRESS_PLUGIN_MAX_DETAILS.get(plugin_detectado, 140)

    idx = 0
    while idx < len(candidates) and len(urls_probadas) < max_listing_pages:
        _check_strategy_deadline(inmob, strategy_name)
        if _deadline_remaining_seconds(_strategy_deadline(inmob)) <= 10:
            errores_relevantes.append(f"{strategy_name}_listados_detenidos_por_presupuesto")
            break
        candidate = candidates[idx]
        idx += 1
        if candidate in urls_probadas:
            continue
        urls_probadas.append(candidate)
        try:
            if candidate == final_url and first_html:
                html = first_html
            else:
                r = _http_get(candidate, session, timeout=_bounded_http_timeout(inmob, 6), use_scraper_on_block=False)
                if r.status_code != 200:
                    errores_relevantes.append(f"{candidate}: HTTP {r.status_code}")
                    continue
                html = _decode_response_text(r)
            detected = _detect_wordpress_plugin(html)
            if plugin_detectado in {"unknown", "wordpress_generic"} and detected != "unknown":
                plugin_detectado = detected
            candidate_detail_links = list(dict.fromkeys(
                [
                    url for url in _extract_generic_property_links(html, candidate)
                    if _looks_like_wordpress_plugin_property_url(url, plugin_detectado) or _looks_like_real_property_url(url)
                ]
                + _extract_wordpress_plugin_property_links(html, candidate, plugin_detectado)
            ))
            for link in candidate_detail_links:
                if link not in detail_urls:
                    detail_urls.append(link)
            for link in _extract_wordpress_listing_links(html, candidate, base_url, plugin_detectado):
                if link not in candidates and link not in urls_probadas:
                    candidates.append(link)
            if len(detail_urls) >= max_details:
                break
        except Exception as exc:
            errores_relevantes.append(f"{candidate}: {type(exc).__name__}: {str(exc)[:180]}")
        _update_strategy_progress(
            inmob,
            strategy_name,
            listing_urls_total=min(len(candidates), max_listing_pages),
            listing_urls_processed=len(urls_probadas),
            listing_urls_remaining=max(min(len(candidates), max_listing_pages) - len(urls_probadas), 0),
            detail_urls_total=len(detail_urls),
            errores_relevantes=errores_relevantes[-5:],
        )

    if not detail_urls:
        raise RuntimeError(f"no_property_links: {strategy_name} sin URLs reales de propiedades")

    if plugin_detectado == "estatik":
        resultados, detail_errors = _extract_wordpress_details_sequential(
            detail_urls,
            inmob,
            session,
            strategy_name,
            max_details=max_details,
        )
    else:
        resultados, detail_errors = _extract_wordpress_details_from_urls(
            detail_urls,
            inmob,
            session,
            strategy_name,
            plugin_detectado,
            max_details=max_details,
        )
    errores_relevantes.extend(detail_errors)
    with_images, without_images = _count_real_image_props(resultados)
    image_stats = inmob.get("_image_extraction_stats") if isinstance(inmob.get("_image_extraction_stats"), dict) else {}
    inmob["_scraper_metadata"] = {
        **dict(inmob.get("_scraper_metadata") or {}),
        "plugin_detectado": plugin_detectado,
        "primary_strategy": strategy_name,
        "urls_probadas": urls_probadas,
        "cantidad_paginas": len(urls_probadas),
        "urls_validas_detectadas": len(detail_urls),
        "property_links_count": len(detail_urls),
        "wordpress_detail_urls_sample": detail_urls[:12],
        "imagenes_detectadas": with_images,
        "imagenes_guardadas": sum(len(clean_property_images(prop.get("imagenes") or [])) for prop in resultados),
        "imagenes_descartadas": int(image_stats.get("imagenes_falsas_descartadas") or 0),
        "motivo_descartes": dict(image_stats.get("imagenes_descartadas_por_motivo") or {}),
        "fuentes_imagenes": dict(image_stats.get("fuentes_imagenes") or {}),
        "propiedades_con_fotos_reales": with_images,
        "propiedades_sin_fotos_reales": without_images,
        "errores_relevantes": errores_relevantes[-10:],
    }
    if not resultados:
        raise RuntimeError(f"parsing_failed: {strategy_name} encontro links pero no datos extraibles")
    logger.info(
        "  %s: %d propiedades desde %d URLs validas (%s)",
        strategy_name,
        len(resultados),
        len(detail_urls),
        plugin_detectado,
    )
    return resultados


def strategy_wordpress_essential_real_estate_detail(inmob: Dict, session: requests.Session) -> List[Dict]:
    return _strategy_wordpress_plugin_detail(inmob, session, "essential_real_estate")


def strategy_wordpress_estatik_detail(inmob: Dict, session: requests.Session) -> List[Dict]:
    metadata = dict(inmob.get("_scraper_metadata") or {})
    metadata["plugin_detectado"] = "estatik"
    metadata["estatik_extractor_mode"] = "static_html_detail_validated"
    inmob["_scraper_metadata"] = metadata
    props = strategy_static_html(inmob, session)
    for prop in props:
        prop["fuente_extraccion"] = "wordpress_estatik_detail"
        prop["cms_origen"] = inmob.get("cms_detectado") or "wordpress"
    inmob["_scraper_metadata"] = {
        **metadata,
        **dict(inmob.get("_scraper_metadata") or {}),
        "plugin_detectado": "estatik",
        "primary_strategy": "wordpress_estatik_detail",
        "estatik_extractor_mode": "static_html_detail_validated",
    }
    return props


def strategy_wordpress_realhomes_detail(inmob: Dict, session: requests.Session) -> List[Dict]:
    return _strategy_wordpress_plugin_detail(inmob, session, "realhomes")


def strategy_wordpress_generic_detail(inmob: Dict, session: requests.Session) -> List[Dict]:
    return _strategy_wordpress_plugin_detail(inmob, session, "wordpress_generic")


_UNIVERSAL_LISTING_KEYWORDS = (
    "propiedades", "propiedad", "inmuebles", "inmueble", "venta", "ventas",
    "alquiler", "alquileres", "emprendimiento", "emprendimientos",
    "desarrollo", "desarrollos", "buscar", "resultado", "listado",
    "ficha", "detalle", "ver-mas", "ver-más", "ver mas", "ver más",
)

_UNIVERSAL_LISTING_PATHS = [
    "/", "/propiedades", "/propiedades/", "/propiedad", "/inmuebles",
    "/inmuebles/", "/venta", "/Venta", "/ventas", "/Ventas",
    "/alquiler", "/Alquiler", "/alquileres", "/buscar", "/busqueda",
    "/emprendimientos", "/desarrollos",
]

_NON_PROPERTY_URL_PATTERNS = re.compile(
    r"(subi-tu-propiedad|publica(?:r)?-tu-propiedad|tasacion|tasaciones|contacto|"
    r"nosotros|quienes-somos|blog|noticia|noticias|prensa|servicio|equipo|staff|login|wp-admin|"
    r"whatsapp|wa\.me|facebook|instagram|linkedin|youtube|twitter|x\.com|"
    r"mapa|maps|property-outside|tr_uuid|[?&]fp=)",
    re.I,
)


def _is_noise_property_url(url: str) -> bool:
    if not url:
        return True
    low = unquote(str(url).strip().lower())
    if not low:
        return True
    if low.startswith(("mailto:", "tel:", "whatsapp:", "javascript:", "#")):
        return True
    parsed = urlparse(low)
    if parsed.netloc in {
        "wa.me",
        "api.whatsapp.com",
        "web.whatsapp.com",
        "facebook.com",
        "www.facebook.com",
        "instagram.com",
        "www.instagram.com",
        "linkedin.com",
        "www.linkedin.com",
        "youtube.com",
        "www.youtube.com",
        "x.com",
        "twitter.com",
    }:
        return True
    if _NON_PROPERTY_URL_PATTERNS.search(low):
        return True
    query_keys = {key.lower() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
    if query_keys & {"tr_uuid", "fp", "fbclid", "gclid", "utm_source", "utm_medium", "utm_campaign"}:
        return True
    return False


def _looks_like_real_property_url(url: str) -> bool:
    if _is_noise_property_url(url):
        return False
    parsed = urlparse(str(url))
    path = unquote((parsed.path or "").lower()).strip("/")
    if not path:
        return False
    if path in {
        "propiedades", "propiedad", "inmuebles", "inmueble", "venta", "ventas",
        "alquiler", "alquileres", "buscar", "busqueda", "emprendimientos", "desarrollos",
    }:
        return False
    if re.search(r"^(estado|tipo-propiedad|property-type|categoria|category)/", path):
        return False
    if re.search(r"^(property-status|property-feature|property-city|property-state|location|tag)/", path):
        return False
    singular_slug_match = re.search(r"(^|/)(property|propiedad|inmueble|ficha|detalle)/([^/?#]{6,})$", path, re.I)
    if singular_slug_match:
        slug = singular_slug_match.group(3).strip("/").lower()
        if slug not in {
            "venta", "ventas", "alquiler", "alquileres", "propiedades", "properties",
            "inmuebles", "buscar", "busqueda", "mapa",
        }:
            return True
    detail_patterns = (
        r"(^|/)p/\d{3,}",
        r"(^|/)propiedad[-/]\d{3,}",
        r"(^|/)property[-/]\d{3,}",
        r"(^|/)inmueble[-/]\d{3,}",
        r"(^|/)ficha[-/]\d{3,}",
        r"(^|/)detalle[-/]\d{3,}",
        r"(^|/)propiedades/[^/]{8,}",
        r"(^|/)inmuebles/[^/]{8,}",
    )
    return any(re.search(pattern, path, re.I) for pattern in detail_patterns)


def _extract_generic_property_links(html: str, current_url: str) -> List[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    current_netloc = urlparse(current_url).netloc
    links: List[str] = []
    selectors = [
        "a[href*='propiedad']", "a[href*='propiedades']",
        "a[href*='inmueble']", "a[href*='inmuebles']",
        "a[href*='ficha']", "a[href*='detalle']",
        "a[href*='/p/']", "a[href*='venta']", "a[href*='alquiler']",
        "[class*='property'] a[href]", "[class*='propiedad'] a[href]",
        "[class*='inmueble'] a[href]", "[class*='listing'] a[href]",
        "[class*='resultado'] a[href]", "article a[href]", ".card a[href]",
    ]
    for selector in selectors:
        for a in soup.select(selector):
            href = (a.get("href") or "").strip()
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue
            full = urljoin(current_url, href)
            parsed = urlparse(full)
            if parsed.netloc != current_netloc:
                continue
            text = a.get_text(" ", strip=True).lower()
            combined = f"{full.lower()} {text}"
            if _looks_like_real_property_url(full) or (
                PROPERTY_URL_PATTERNS.search(full)
                and not _is_noise_property_url(full)
                and any(word in combined for word in ("venta", "alquiler", "dormitorio", "ambiente", "terreno", "casa", "departamento"))
            ):
                if full not in links:
                    links.append(full)
    return links[:400]


def _looks_like_custom_listing_url(url: str) -> bool:
    if not url or _is_noise_property_url(url):
        return False
    parsed = urlparse(str(url))
    path = unquote((parsed.path or "").lower()).rstrip("/")
    query = unquote(parsed.query or "").lower()
    if path.endswith("/listing") or path.endswith("/listings") or path == "listing" or path == "listings":
        return True
    if "listing" in path and any(marker in query for marker in ("user_id=", "purpose=", "type=", "page=")):
        return True
    return False


def _looks_like_custom_property_url(url: str, link_text: str = "") -> bool:
    if not url or _is_noise_property_url(url):
        return False
    parsed = urlparse(str(url))
    path = unquote((parsed.path or "").lower()).strip("/")
    if not path:
        return False
    if re.search(r"^(blog|prensa|desarrollos?|contactenos?|contacto|nosotros|login)(/|$)", path):
        return False
    if re.search(r"^(ad|avisos?|ficha|detalle|propiedad|inmueble)/[^/?#]{8,}", path):
        text = _fix_mojibake_text(link_text).lower()
        if any(noise in text for noise in ("ingresar", "contacto", "instagram", "facebook", "desarrollado")):
            return False
        return True
    return _looks_like_real_property_url(url)


def _extract_custom_listing_urls(html: str, current_url: str) -> List[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    current_netloc = urlparse(current_url).netloc
    urls: List[str] = []

    def add(candidate: str) -> None:
        full = urljoin(current_url, candidate).split("#", 1)[0]
        if urlparse(full).netloc != current_netloc:
            return
        if _looks_like_custom_listing_url(full) and full not in urls:
            urls.append(full)

    for a in soup.select("a[href]"):
        add((a.get("href") or "").strip())

    for match in re.findall(r"""["']([^"']*(?:/listing|listing\?)[^"']*)["']""", html or "", flags=re.I):
        add(match)

    user_ids = re.findall(r"user_id=(\d+)", html or "", flags=re.I)
    base = f"{urlparse(current_url).scheme}://{current_netloc}" if current_netloc else current_url.rstrip("/")
    for user_id in list(dict.fromkeys(user_ids))[:3]:
        for purpose in ("sale", "rent", "temporary_rental", "temporary_rent"):
            add(f"{base}/listing?user_id={user_id}&purpose={purpose}")

    return urls[:120]


def _extract_custom_property_links(html: str, current_url: str) -> List[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    current_netloc = urlparse(current_url).netloc
    links: List[str] = []

    def add(candidate: str, text: str = "") -> None:
        full = urljoin(current_url, candidate).split("#", 1)[0]
        if urlparse(full).netloc != current_netloc:
            return
        if _looks_like_custom_property_url(full, text) and full not in links:
            links.append(full)

    selectors = [
        "a[href*='/ad/']", "a[href*='/aviso/']", "a[href*='/ficha/']",
        "a[href*='/detalle/']", "a[href*='/propiedad/']", "a[href*='/inmueble/']",
        "[class*='listing'] a[href]", "[class*='property'] a[href]",
        "[class*='propiedad'] a[href]", "[class*='inmueble'] a[href]",
        ".card a[href]", "article a[href]",
    ]
    for selector in selectors:
        for a in soup.select(selector):
            add((a.get("href") or "").strip(), a.get_text(" ", strip=True))

    for match in re.findall(r"""["']([^"']*/(?:ad|aviso|ficha|detalle|propiedad|inmueble)/[^"']{8,})["']""", html or "", flags=re.I):
        add(match)
    return links[:500]


def _generic_candidate_urls(inmob: Dict, first_html: str = "", first_url: str = "") -> List[str]:
    urls: List[str] = []

    def add(url: Optional[str]) -> None:
        if not url:
            return
        clean = _normalize_queue_url(str(url).split("#", 1)[0])
        if clean and clean not in urls:
            urls.append(clean)

    for raw in (inmob.get("url_listado"), inmob.get("web"), first_url):
        start_info = normalize_start_url_for_diagnosis(raw)
        for candidate in start_info.get("candidate_urls") or []:
            add(candidate)
    for variant in _url_host_variants(inmob.get("url_listado")):
        add(variant)
    for variant in _url_host_variants(inmob.get("web")):
        add(variant)
    if first_html and first_url:
        for link in _extract_keyword_internal_links(first_html, first_url, _UNIVERSAL_LISTING_KEYWORDS):
            add(link)
    for base in _url_host_variants(inmob.get("web") or first_url):
        for path in _UNIVERSAL_LISTING_PATHS:
            add(urljoin(base.rstrip("/") + "/", path.lstrip("/")))
    return urls[:50]


def _custom_listing_candidate_urls(inmob: Dict, first_html: str = "", first_url: str = "") -> List[str]:
    urls: List[str] = []

    def add(url: Optional[str]) -> None:
        if not url:
            return
        clean = _normalize_queue_url(str(url).split("#", 1)[0])
        if clean and not _is_noise_property_url(clean) and clean not in urls:
            urls.append(clean)

    for variant in _url_host_variants(inmob.get("url_listado")):
        if _looks_like_custom_listing_url(variant):
            add(variant)
    for variant in _url_host_variants(inmob.get("web")):
        add(variant)
    if first_html and first_url:
        for link in _extract_custom_listing_urls(first_html, first_url):
            add(link)
    for base in _url_host_variants(inmob.get("web") or first_url):
        root = base.rstrip("/") + "/"
        add(urljoin(root, "listing"))
        add(urljoin(root, "listings"))
        add(urljoin(root, "listing?purpose=sale"))
        add(urljoin(root, "listing?purpose=rent"))
    return urls[:80]


def _parse_custom_listing_cards(html: str, source_url: str, inmob: Dict) -> List[Dict]:
    """Extrae propiedades directamente desde cards cuando no hay pagina detalle."""
    soup = BeautifulSoup(html or "", "html.parser")
    selectors = [
        "[class*='listing']", "[class*='property']", "[class*='propiedad']",
        "[class*='inmueble']", ".card", "article",
    ]
    cards = []
    for selector in selectors:
        found = [
            node for node in soup.select(selector)
            if len(node.get_text(" ", strip=True)) >= 80
            and re.search(r"(venta|alquiler|usd|u\$s|\$|amb|m2|mÂ²|departamento|casa|lote|terreno)", node.get_text(" ", strip=True), re.I)
        ]
        if len(found) >= 2:
            cards = found[:80]
            break

    props: List[Dict] = []
    for idx, card in enumerate(cards, start=1):
        text = _fix_mojibake_text(card.get_text(" ", strip=True))
        if not text or len(text) < 80:
            continue
        link = card.select_one("a[href]")
        url_prop = urljoin(source_url, link.get("href")) if link and link.get("href") else f"{source_url}#card-{idx}"
        if _is_noise_property_url(url_prop) or _looks_like_custom_listing_url(url_prop):
            url_prop = f"{source_url}#card-{idx}"

        title = ""
        for selector in ("h1", "h2", "h3", "h4", "[class*='title']", "[class*='titulo']"):
            el = card.select_one(selector)
            if el and _is_useful_scraped_title(el.get_text(" ", strip=True)):
                title = _fix_mojibake_text(el.get_text(" ", strip=True))
                break
        if not title and link:
            title = _fix_mojibake_text(link.get_text(" ", strip=True))
        if not _is_useful_scraped_title(title):
            title = _title_from_detail_url(url_prop)
        if not _is_useful_scraped_title(title):
            continue

        precio, moneda = _normalizar_precio_detalle(text)
        precio_ars, precio_usd = convertir_precio(precio, moneda)
        direccion = _extract_address_from_text(text)
        imagenes = clean_property_images(extraer_imagenes(card, source_url), base_url=source_url)
        id_ext = ""
        match = re.search(r"/(?:ad|aviso|ficha|detalle|propiedad|inmueble)/([^/?#]+)", url_prop, re.I)
        if match:
            id_ext = match.group(1)[:120]

        prop = {
            "inmobiliaria_id": inmob["id"],
            "url": url_prop,
            "id_externo": id_ext or f"card-{idx}",
            "hash_dedup": hash_propiedad(inmob["id"], id_ext or f"card-{idx}", url_prop),
            "titulo": title,
            "descripcion": limpiar_descripcion(text[:1200]),
            "precio": precio,
            "moneda": moneda,
            "precio_ars": precio_ars,
            "precio_usd": precio_usd,
            "tipo_propiedad": normalizar_tipo(text),
            "operacion": normalizar_operacion(text or source_url),
            "ambientes": normalizar_int(re.search(r"(\d+)\s*amb", text, re.I).group(1)) if re.search(r"(\d+)\s*amb", text, re.I) else None,
            "superficie_total": normalizar_superficie(text),
            "direccion": direccion,
            "ciudad": inmob.get("ciudad", ""),
            "provincia": inmob.get("provincia", ""),
            "pais": "Argentina",
            "imagenes": imagenes or None,
            "fuente_extraccion": "custom_listing_detail",
            "cms_origen": inmob.get("cms_detectado") or "custom",
            "estado": "activo",
        }
        prop["score_calidad"] = calcular_score(prop)
        props.append(prop)
    return _dedupe_props(props)


def strategy_custom_listing_detail(inmob: Dict, session: requests.Session) -> List[Dict]:
    """Extractor HTTP para sitios custom con listados /listing?... y fichas /ad/..."""
    strategy_name = "custom_listing_detail"
    url_inicial = inmob.get("url_listado") or inmob.get("web", "")
    if not url_inicial:
        raise ValueError("sin_url_listado")

    _check_strategy_deadline(inmob, strategy_name)
    first_html = ""
    final_url = _normalize_queue_url(url_inicial)
    urls_detectadas: List[str] = []
    urls_probadas: List[str] = []
    detail_urls: List[str] = []
    errores_relevantes: List[str] = []
    card_props: List[Dict] = []

    try:
        r0 = _http_get(final_url, session, timeout=_bounded_http_timeout(inmob, 8), use_scraper_on_block=False)
        if r0.status_code == 200:
            first_html = _decode_response_text(r0)
            final_url = r0.url or final_url
    except Exception as exc:
        errores_relevantes.append(f"{final_url}: {type(exc).__name__}: {str(exc)[:180]}")

    candidates = _custom_listing_candidate_urls(inmob, first_html=first_html, first_url=final_url)
    urls_detectadas = [url for url in candidates if _looks_like_custom_listing_url(url)]
    if not urls_detectadas and _looks_like_custom_listing_url(final_url):
        urls_detectadas.append(final_url)
    if not urls_detectadas:
        raise RuntimeError("no_property_links: custom_listing_detail sin URLs /listing")

    idx = 0
    while idx < len(urls_detectadas) and len(urls_probadas) < 35:
        _check_strategy_deadline(inmob, strategy_name)
        if _deadline_remaining_seconds(_strategy_deadline(inmob)) <= 8:
            errores_relevantes.append("custom_listing_detenido_por_presupuesto")
            break
        listing_url = urls_detectadas[idx]
        idx += 1
        if listing_url in urls_probadas:
            continue
        urls_probadas.append(listing_url)
        try:
            if listing_url == final_url and first_html:
                html = first_html
            else:
                r = _http_get(listing_url, session, timeout=_bounded_http_timeout(inmob, 7), use_scraper_on_block=False)
                if r.status_code != 200:
                    errores_relevantes.append(f"{listing_url}: HTTP {r.status_code}")
                    continue
                html = _decode_response_text(r)
            for link in _extract_custom_listing_urls(html, listing_url):
                if link not in urls_detectadas and link not in urls_probadas:
                    urls_detectadas.append(link)
            for link in _extract_custom_property_links(html, listing_url):
                if link not in detail_urls:
                    detail_urls.append(link)
            if not detail_urls:
                card_props.extend(_parse_custom_listing_cards(html, listing_url, inmob))
            if len(detail_urls) >= 180:
                break
        except Exception as exc:
            errores_relevantes.append(f"{listing_url}: {type(exc).__name__}: {str(exc)[:180]}")

    resultados: List[Dict] = []
    for detail_url in detail_urls[:180]:
        _check_strategy_deadline(inmob, strategy_name)
        if _deadline_remaining_seconds(_strategy_deadline(inmob)) <= 4:
            errores_relevantes.append("custom_listing_detalles_detenidos_por_presupuesto")
            break
        try:
            prop = _extract_detail_page(detail_url, inmob, session)
            if prop:
                prop["fuente_extraccion"] = strategy_name
                prop["cms_origen"] = inmob.get("cms_detectado") or "custom"
                resultados.append(prop)
            time.sleep(random.uniform(0.05, 0.16))
        except Exception as exc:
            if len(errores_relevantes) < 10:
                errores_relevantes.append(f"{detail_url}: {type(exc).__name__}: {str(exc)[:160]}")

    resultados = _dedupe_props(resultados + card_props)
    inmob["_scraper_metadata"] = {
        **dict(inmob.get("_scraper_metadata") or {}),
        "custom_listing_urls_detectadas": len(urls_detectadas),
        "custom_listing_urls_probadas": urls_probadas,
        "custom_listing_links_propiedad_detectados": len(detail_urls),
        "custom_listing_detail_urls_sample": detail_urls[:12],
        "cantidad_paginas": len(urls_probadas),
        "errores_relevantes": errores_relevantes[-10:],
    }
    if not detail_urls and not card_props:
        raise RuntimeError("no_property_links: custom_listing_detail no encontro fichas ni cards reales")
    if not resultados:
        raise RuntimeError("parsing_failed: custom_listing_detail encontro links pero no datos extraibles")
    logger.info("  Custom listing: %d propiedades desde %d fichas", len(resultados), len(detail_urls))
    return resultados


def strategy_static_html(inmob: Dict, session: requests.Session) -> List[Dict]:
    """Extractor HTTP genérico: descubre links internos y parsea detalles sin browser."""
    url_inicial = inmob.get("url_listado") or inmob.get("web", "")
    if not url_inicial:
        raise ValueError("sin_url_listado")

    _check_strategy_deadline(inmob, "static_html")
    urls_probadas: List[str] = []
    detail_urls: List[str] = []
    errores_relevantes: List[str] = []
    first_html = ""
    http_statuses: List[int] = []

    try:
        r0 = _http_get(url_inicial, session, timeout=_bounded_http_timeout(inmob, 10))
        http_statuses.append(r0.status_code)
        first_html = r0.text if r0.status_code == 200 else ""
    except Exception as exc:
        errores_relevantes.append(f"{url_inicial}: {type(exc).__name__}: {str(exc)[:180]}")

    candidates = _generic_candidate_urls(inmob, first_html=first_html, first_url=url_inicial)
    for candidate in candidates:
        _check_strategy_deadline(inmob, "static_html")
        if _deadline_remaining_seconds(_strategy_deadline(inmob)) <= 8:
            errores_relevantes.append("static_html_detenido_por_presupuesto")
            break
        if candidate in urls_probadas:
            continue
        urls_probadas.append(candidate)
        try:
            if candidate == url_inicial and first_html:
                html = first_html
                status = 200
            else:
                r = _http_get(candidate, session, timeout=_bounded_http_timeout(inmob, 8))
                status = r.status_code
                http_statuses.append(status)
                if status != 200:
                    continue
                html = r.text
            for link in _extract_generic_property_links(html, candidate):
                if link not in detail_urls:
                    detail_urls.append(link)
            if len(detail_urls) >= 80:
                break
        except Exception as exc:
            errores_relevantes.append(f"{candidate}: {type(exc).__name__}: {str(exc)[:180]}")
        _update_strategy_progress(
            inmob,
            "static_html",
            listing_urls_total=len(candidates),
            listing_urls_processed=len(urls_probadas),
            listing_urls_remaining=max(len(candidates) - len(urls_probadas), 0),
            detail_urls_total=len(detail_urls),
            errores_relevantes=errores_relevantes[-5:],
        )

    resultados: List[Dict] = []
    detail_slice = detail_urls[:120]
    _update_strategy_progress(
        inmob,
        "static_html",
        detail_urls_total=len(detail_slice),
        detail_urls_processed=0,
        detail_urls_remaining=len(detail_slice),
    )
    for index, durl in enumerate(detail_slice, start=1):
        _check_strategy_deadline(inmob, "static_html")
        if _deadline_remaining_seconds(_strategy_deadline(inmob)) <= 4:
            errores_relevantes.append("static_html_detalles_detenidos_por_presupuesto")
            break
        try:
            prop = _extract_detail_page(durl, inmob, session)
            if prop:
                prop["fuente_extraccion"] = "static_html"
                resultados.append(prop)
        except Exception as exc:
            if len(errores_relevantes) < 8:
                errores_relevantes.append(f"{durl}: {type(exc).__name__}: {str(exc)[:180]}")
        _update_strategy_progress(
            inmob,
            "static_html",
            detail_urls_total=len(detail_slice),
            detail_urls_processed=index,
            detail_urls_remaining=max(len(detail_slice) - index, 0),
            propiedades_detectadas=len(resultados),
            errores_relevantes=errores_relevantes[-5:],
        )

    inmob["_scraper_metadata"] = {
        **dict(inmob.get("_scraper_metadata") or {}),
        "static_html_urls_probadas": urls_probadas,
        "static_html_links_propiedad_detectados": len(detail_urls),
        "static_html_http_statuses": http_statuses[-10:],
        "errores_relevantes": errores_relevantes[-8:],
    }

    if not detail_urls:
        raise RuntimeError("no_property_links: static_html no encontro links de propiedades")
    if not resultados:
        raise RuntimeError("parsing_failed: static_html encontro links pero no datos extraibles")
    return _dedupe_props(resultados)


def strategy_static_html_detail(inmob: Dict, session: requests.Session) -> List[Dict]:
    props = strategy_static_html(inmob, session)
    for prop in props:
        prop["fuente_extraccion"] = "static_html_detail"
    return props


def strategy_static_html_tokko_detail(inmob: Dict, session: requests.Session) -> List[Dict]:
    props = strategy_static_html(inmob, session)
    for prop in props:
        prop["fuente_extraccion"] = "static_html_tokko_detail"
        prop["cms_origen"] = "tokko"
    return props


def _wordpress_rest_links(base_url: str, session: requests.Session, inmob: Dict) -> Tuple[List[str], List[str]]:
    parsed = urlparse(base_url)
    base = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else base_url.rstrip("/")
    links: List[str] = []
    detected_types: List[str] = []
    for post_type in _WORDPRESS_REST_TYPES:
        _check_strategy_deadline(inmob, "wordpress_html")
        api_url = f"{base}/wp-json/wp/v2/{post_type}?per_page=50"
        try:
            r = _http_get(api_url, session, timeout=_bounded_http_timeout(inmob, 5), use_scraper_on_block=False)
            if r.status_code != 200:
                continue
            data = r.json()
            if not isinstance(data, list) or not data:
                continue
            detected_types.append(post_type)
            for item in data:
                if isinstance(item, dict) and item.get("link") and item["link"] not in links:
                    links.append(item["link"])
        except Exception:
            continue
    return links, detected_types


def strategy_wordpress_html(inmob: Dict, session: requests.Session) -> List[Dict]:
    url_inicial = inmob.get("url_listado") or inmob.get("web", "")
    if not url_inicial:
        raise ValueError("sin_url_listado")

    _check_strategy_deadline(inmob, "wordpress_html")
    urls_probadas: List[str] = []
    errores_relevantes: List[str] = []
    detail_urls: List[str] = []
    resultados: List[Dict] = []
    links_internos = 0
    plugin_detectado = "unknown"
    rest_types: List[str] = []
    first_html = ""

    try:
        r0 = _http_get(url_inicial, session, timeout=_bounded_http_timeout(inmob, 10), use_scraper_on_block=False)
        first_html = r0.text if r0.status_code == 200 else ""
        plugin_detectado = _detect_wordpress_plugin(first_html)
    except Exception as exc:
        errores_relevantes.append(f"{url_inicial}: {type(exc).__name__}: {str(exc)[:180]}")

    candidates = _wordpress_candidate_urls(inmob, first_html, url_inicial)
    idx = 0
    while idx < len(candidates):
        candidate = candidates[idx]
        idx += 1
        _check_strategy_deadline(inmob, "wordpress_html")
        if candidate in urls_probadas:
            continue
        urls_probadas.append(candidate)
        try:
            if candidate == url_inicial and first_html:
                html = first_html
            else:
                r = _http_get(candidate, session, timeout=_bounded_http_timeout(inmob, 8), use_scraper_on_block=False)
                if r.status_code != 200:
                    errores_relevantes.append(f"{candidate}: HTTP {r.status_code}")
                    continue
                html = r.text

            detected = _detect_wordpress_plugin(html)
            if plugin_detectado == "unknown" and detected != "unknown":
                plugin_detectado = detected
            new_listing_links = _extract_keyword_internal_links(html, candidate, _WORDPRESS_LISTING_KEYWORDS)
            links_internos += len(new_listing_links)
            for link in new_listing_links:
                if link not in candidates and link not in urls_probadas:
                    candidates.append(link)
            for link in _extract_wordpress_property_links(html, candidate):
                if link not in detail_urls:
                    detail_urls.append(link)
        except Exception as exc:
            errores_relevantes.append(f"{candidate}: {type(exc).__name__}: {str(exc)[:180]}")

    rest_links, rest_types = _wordpress_rest_links(url_inicial, session, inmob)
    for link in rest_links:
        if link not in detail_urls:
            detail_urls.append(link)

    for durl in detail_urls[:120]:
        _check_strategy_deadline(inmob, "wordpress_html")
        prop = _extract_detail_page(durl, inmob, session)
        if prop:
            prop["fuente_extraccion"] = "wordpress_html"
            prop["cms_origen"] = inmob.get("cms_detectado") or "wordpress"
            resultados.append(prop)

    resultados = _dedupe_props(resultados)
    inmob["_scraper_metadata"] = {
        "urls_probadas": urls_probadas,
        "cantidad_paginas": len(urls_probadas),
        "cantidad_links_internos_detectados": links_internos,
        "cantidad_links_propiedad_detectados": len(detail_urls),
        "wordpress_plugin_detectado": plugin_detectado,
        "wordpress_rest_types_detectados": rest_types,
        "motivo_sin_propiedades": "sin_links_propiedad" if not detail_urls else "links_sin_datos_extraibles",
        "errores_relevantes": errores_relevantes[-5:],
    }
    if not resultados:
        raise RuntimeError("sin_propiedades: wordpress_html no encontro propiedades")
    logger.info("  WordPress HTML: %d propiedades (%s)", len(resultados), plugin_detectado)
    return resultados


# ---------------------------------------------------------------------------
# Playwright helpers
# ---------------------------------------------------------------------------

def _playwright_goto(page: Page, url: str, retries: int = 2, timeout_ms: int = PLAYWRIGHT_NAV_TIMEOUT_MS) -> None:
    for attempt in range(retries):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            return
        except PlaywrightError as e:
            if attempt == retries - 1:
                raise
            wait = min(2 ** attempt + random.uniform(0, 1), 3)
            logger.debug("goto retry %d: %s — esperando %.1fs", attempt + 1, e, wait)
            time.sleep(wait)


def _human_scroll(page: Page, deadline: Optional[float] = None) -> None:
    """Simula scroll humano para evitar detección."""
    try:
        page.mouse.move(random.randint(100, 800), random.randint(100, 600))
        for _ in range(random.randint(2, 4)):
            _check_deadline(deadline, "playwright_scroll")
            page.evaluate(f"window.scrollBy(0, {random.randint(200, 500)})")
            time.sleep(random.uniform(0.2, 0.5))
    except Exception:
        pass


def _make_playwright_context(pw, headless: bool = True):
    browser = pw.chromium.launch(
        headless=headless,
        timeout=PLAYWRIGHT_LAUNCH_TIMEOUT_MS,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-web-security",
        ],
    )
    context = browser.new_context(
        user_agent=random.choice(USER_AGENTS),
        locale="es-AR",
        timezone_id="America/Argentina/Buenos_Aires",
        viewport={"width": 1280, "height": 800},
        extra_http_headers={"Accept-Language": "es-AR,es;q=0.9"},
        ignore_https_errors=True,  # ignorar certs vencidos/mal configurados
    )
    context.set_default_timeout(PLAYWRIGHT_ACTION_TIMEOUT_MS)
    context.set_default_navigation_timeout(PLAYWRIGHT_NAV_TIMEOUT_MS)
    # Block heavy resources
    context.route(
        "**/*",
        lambda route: route.abort()
        if route.request.resource_type in {"image", "media", "font", "stylesheet"}
        else route.continue_(),
    )
    return browser, context


# ---------------------------------------------------------------------------
# Strategy 5: HTML scraper with Playwright (fallback)
# ---------------------------------------------------------------------------

_CARD_SELECTORS = [
    "#propiedades > li[prop-id]", "ul.resultados-list > li[prop-id]",
    "#prop-list li[prop-id]", "li[prop-id]",
    ".property-card", ".propiedad", ".listing-item", ".property-item",
    ".real-estate-item", "article.property", "[class*='property-card']",
    "[class*='listing-card']", "[class*='prop-card']", "[class*='inmueble']",
    ".rh_list_card", ".card-property", ".item-property",
    "[data-property]", "[data-listing]",
]

_PRICE_SELECTORS = [
    ".price", ".precio", "[class*='price']", "[class*='precio']",
    ".property-price", ".listing-price", "span.amount",
]

_TITLE_SELECTORS = [
    "h2", "h3", ".property-title", ".titulo", "[class*='title']",
    "[class*='titulo']", ".listing-title", "a.title",
]

_LINK_SELECTORS = ["a[href]"]

_PAGINATION_URL_PATTERNS = [
    (r"\?page=(\d+)", "?page={}"),
    (r"\?p=(\d+)",    "?p={}"),
    (r"/page/(\d+)/", "/page/{}/"),
    (r"\?pag=(\d+)",  "?pag={}"),
    (r"&p=(\d+)",     "&p={}"),
    (r"offset=(\d+)", "offset={}"),
]


def _count_selector(page: Page, selector: str) -> int:
    try:
        return int(page.eval_on_selector_all(selector, "els => els.length"))
    except Exception:
        return 0


def _infer_card_selector(page: Page) -> Optional[str]:
    for sel in _CARD_SELECTORS:
        count = _count_selector(page, sel)
        if count >= 3:
            return sel
    return None


def _extract_cards_from_page(page: Page, card_sel: str, inmob: Dict, base_url: str) -> List[str]:
    """Extrae URLs de propiedades de los cards en la página actual."""
    urls: List[str] = []
    _check_strategy_deadline(inmob, "html_scraper")
    try:
        hrefs = page.eval_on_selector_all(
            f"{card_sel} a[href]",
            "els => els.map(el => el.getAttribute('href')).filter(Boolean)",
        )
    except Exception:
        hrefs = []
    for href in hrefs:
        full = urljoin(base_url, href)
        if PROPERTY_URL_PATTERNS.search(full) or urlparse(full).netloc == urlparse(base_url).netloc:
            urls.append(full)
    return list(dict.fromkeys(urls))


def _detect_next_page_url(current_url: str, page: Page) -> Optional[str]:
    """Detecta la URL de la siguiente página."""
    # Patrón en URL actual
    for pattern, template in _PAGINATION_URL_PATTERNS:
        m = re.search(pattern, current_url)
        if m:
            current_page = int(m.group(1))
            next_page = current_page + 1
            new_url = re.sub(pattern, template.format(next_page), current_url)
            return new_url

    # Si no tiene parámetro de página, intentar ?page=2
    sep = "&" if "?" in current_url else "?"
    return current_url + sep + "page=2"


def _handle_click_pagination(page: Page) -> bool:
    """Intenta hacer click en el botón Siguiente. Retorna True si tuvo éxito."""
    next_selectors = [
        "a[rel='next']", ".next", ".siguiente", "[class*='next']",
        "a:has-text('Siguiente')", "a:has-text('siguiente')",
        "a:has-text('>')", "button:has-text('>')",
        ".pagination .next", "[aria-label='Next']",
    ]
    for sel in next_selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=2000):
                btn.click(timeout=PLAYWRIGHT_ACTION_TIMEOUT_MS)
                page.wait_for_load_state("networkidle", timeout=PLAYWRIGHT_LOAD_TIMEOUT_MS)
                return True
        except Exception:
            pass
    return False


def _playwright_extract_detail(page: Page, url: str, inmob: Dict) -> Optional[Dict]:
    """Extrae datos de una página de detalle con Playwright (con imágenes activas)."""
    # Habilitar imágenes para esta página
    page.unroute("**/*")
    try:
        _check_strategy_deadline(inmob, "html_scraper")
        _playwright_goto(page, url, retries=1, timeout_ms=_bounded_playwright_timeout_ms(inmob, PLAYWRIGHT_NAV_TIMEOUT_MS))
        _human_scroll(page, deadline=_strategy_deadline(inmob))
        page.wait_for_load_state("networkidle", timeout=_bounded_playwright_timeout_ms(inmob, PLAYWRIGHT_LOAD_TIMEOUT_MS))

        def find_text(*sels):
            for sel in sels:
                try:
                    _check_strategy_deadline(inmob, "html_scraper")
                    el = page.locator(sel).first
                    t = el.inner_text(timeout=_bounded_playwright_timeout_ms(inmob, PLAYWRIGHT_ACTION_TIMEOUT_MS)).strip()
                    if t:
                        return t
                except Exception:
                    pass
            return ""

        title = find_text("h1", ".property-title", ".titulo", "[class*='title']")
        precio_raw = find_text(*_PRICE_SELECTORS)
        precio, moneda = normalizar_precio(precio_raw)
        desc = find_text(".description", ".descripcion", "[class*='description']", "article")
        tipo_raw = find_text("[class*='tipo']", "[class*='type']")
        op_raw   = find_text("[class*='operaci']", "[class*='operation']")
        address  = find_text(".address", ".direccion", "[class*='address']", "[class*='location']")

        ambientes   = normalizar_int(find_text("[class*='ambiente']", "[class*='room']", "[class*='environment']"))
        dormitorios = normalizar_int(find_text("[class*='dormitor']", "[class*='bedroom']", "[class*='suite']", "[class*='habitac']"))
        banos       = normalizar_int(find_text("[class*='bano']", "[class*='bathroom']", "[class*='bath']", "[class*='toilette']"))
        cocheras    = normalizar_int(find_text("[class*='cochera']", "[class*='garage']", "[class*='parking']"))
        sup_raw     = find_text("[class*='surface']", "[class*='superficie']", "[class*='area']", "[class*='m2']")
        sup_total   = normalizar_superficie(sup_raw)
        sup_cubierta = normalizar_superficie(find_text("[class*='cubierta']", "[class*='roofed']", "[class*='covered']"))

        # Expensas
        exp_raw = find_text("[class*='expens']", "[class*='expense']", "[class*='gasto']")
        expensas, expensas_moneda = (None, None)
        if exp_raw:
            ev, em = normalizar_precio(exp_raw)
            expensas, expensas_moneda = ev, em

        # Piso
        piso = find_text("[class*='piso']", "[class*='floor']", "[class*='planta']") or None

        # Apto crédito
        try:
            page_text_lower = page.inner_text("body", timeout=_bounded_playwright_timeout_ms(inmob, PLAYWRIGHT_ACTION_TIMEOUT_MS)).lower()
        except Exception:
            page_text_lower = ""
        apto_credito = bool(re.search(r"apto\s+cr[eé]dito|acepta\s+cr[eé]dito|cr[eé]dito\s+hipotecario", page_text_lower))
        apto_profesional = bool(re.search(r"apto\s+profesional|uso\s+profesional", page_text_lower))

        # HTML completo para extractores avanzados
        try:
            raw_html = page.content()
        except Exception:
            raw_html = ""
        soup_pw = BeautifulSoup(raw_html, "html.parser")

        # Fotos con extractor mejorado
        fotos = extraer_imagenes(soup_pw, url)

        # Agente
        agente_nombre, agente_telefono = extraer_agente(soup_pw)

        # Coordenadas Google Maps
        lat_gm, lon_gm = extraer_coordenadas_gmaps(raw_html)

        inmob_id = inmob["id"]
        id_ext   = ""
        m = re.search(r"/(\d{3,})[/_-]?", url)
        if m:
            id_ext = m.group(1)

        if not title and not precio:
            return None

        precio_ars, precio_usd = convertir_precio(precio, moneda)
        prop = {
            "inmobiliaria_id":     inmob_id,
            "url":                 url,
            "id_externo":          id_ext,
            "hash_dedup":          hash_propiedad(inmob_id, id_ext, url),
            "titulo":              title,
            "descripcion":         limpiar_descripcion(desc),
            "precio":              precio,
            "moneda":              moneda,
            "precio_ars":          precio_ars,
            "precio_usd":          precio_usd,
            "tipo_propiedad":      normalizar_tipo(tipo_raw),
            "operacion":           normalizar_operacion(op_raw),
            "ambientes":           ambientes,
            "dormitorios":         dormitorios,
            "banos":               banos,
            "cocheras":            cocheras,
            "superficie_total":    sup_total,
            "superficie_cubierta": sup_cubierta,
            "expensas":            expensas,
            "expensas_moneda":     expensas_moneda,
            "piso":                piso,
            "apto_credito":        apto_credito or None,
            "apto_profesional":    apto_profesional or None,
            "direccion":           address,
            "ciudad":              inmob.get("ciudad", ""),
            "provincia":           inmob.get("provincia", ""),
            "pais":                "Argentina",
            "latitud":             lat_gm,
            "longitud":            lon_gm,
            "imagenes":            fotos or None,
            "agente_nombre":       agente_nombre,
            "agente_telefono":     agente_telefono,
            "fuente_extraccion":   "html_scraper",
            "cms_origen":          inmob.get("cms_detectado", ""),
            "estado":              "activo",
        }
        prop["score_calidad"] = calcular_score(prop)
        return prop
    finally:
        # Restaurar bloqueo de recursos
        page.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in {"image", "media", "font", "stylesheet"}
            else route.continue_(),
        )


def strategy_html_playwright(inmob: Dict, pw_context) -> List[Dict]:
    url_listado = inmob.get("url_listado") or inmob.get("web", "")
    if not url_listado:
        raise ValueError("sin_url_listado")

    _check_strategy_deadline(inmob, "html_scraper")
    tipo_pag = inmob.get("tipo_paginacion", "url") or "url"
    resultados: List[Dict] = []
    detail_urls: List[str] = []

    page = pw_context.new_page()
    try:
        page.set_default_timeout(PLAYWRIGHT_ACTION_TIMEOUT_MS)
        page.set_default_navigation_timeout(PLAYWRIGHT_NAV_TIMEOUT_MS)
        _playwright_goto(page, url_listado, retries=2, timeout_ms=_bounded_playwright_timeout_ms(inmob, PLAYWRIGHT_NAV_TIMEOUT_MS))
        _human_scroll(page, deadline=_strategy_deadline(inmob))
        page.wait_for_load_state("networkidle", timeout=_bounded_playwright_timeout_ms(inmob, PLAYWRIGHT_LOAD_TIMEOUT_MS))

        card_sel = _infer_card_selector(page)
        if not card_sel:
            raise RuntimeError("sin_propiedades: no se detectaron cards de propiedades")

        empty_pages = 0
        max_pages = inmob.get("paginas_estimadas") or 50
        current_url = url_listado
        page_num = 1

        while page_num <= max_pages:
            _check_strategy_deadline(inmob, "html_scraper")
            new_urls = _extract_cards_from_page(page, card_sel, inmob, current_url)
            before = len(detail_urls)
            for u in new_urls:
                if u not in detail_urls:
                    detail_urls.append(u)
            added = len(detail_urls) - before

            if added == 0:
                empty_pages += 1
                if empty_pages >= 2:
                    break
            else:
                empty_pages = 0

            # Paginación
            if tipo_pag == "scroll_infinito":
                _check_strategy_deadline(inmob, "html_scraper")
                prev_height = page.evaluate("document.body.scrollHeight")
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(min(1.0, max(0.1, _deadline_remaining_seconds(_strategy_deadline(inmob)))))
                new_height = page.evaluate("document.body.scrollHeight")
                if new_height == prev_height:
                    break
            elif tipo_pag == "click":
                if not _handle_click_pagination(page):
                    break
                current_url = page.url
            else:  # url-based
                next_url = _detect_next_page_url(current_url, page)
                if not next_url or next_url == current_url:
                    break
                try:
                    _playwright_goto(page, next_url, retries=1, timeout_ms=_bounded_playwright_timeout_ms(inmob, PLAYWRIGHT_NAV_TIMEOUT_MS))
                    _human_scroll(page, deadline=_strategy_deadline(inmob))
                    page.wait_for_load_state("networkidle", timeout=_bounded_playwright_timeout_ms(inmob, PLAYWRIGHT_LOAD_TIMEOUT_MS))
                    # Verificar que la página cargó contenido
                    if _count_selector(page, card_sel) == 0:
                        break
                    current_url = page.url
                except Exception:
                    break

            page_num += 1
            time.sleep(min(random.uniform(0.5, 1.2), max(0.1, _deadline_remaining_seconds(_strategy_deadline(inmob)))))

    finally:
        _close_playwright_safely(page, "html_scraper listing page")

    if not detail_urls:
        raise RuntimeError("sin_propiedades: html_scraper no encontró URLs")

    # Visitar páginas de detalle
    detail_page = pw_context.new_page()
    try:
        detail_page.set_default_timeout(PLAYWRIGHT_ACTION_TIMEOUT_MS)
        detail_page.set_default_navigation_timeout(PLAYWRIGHT_NAV_TIMEOUT_MS)
        for durl in detail_urls[:300]:
            _check_strategy_deadline(inmob, "html_scraper")
            try:
                prop = _playwright_extract_detail(detail_page, durl, inmob)
                if prop:
                    resultados.append(prop)
                time.sleep(min(random.uniform(0.3, 0.8), max(0.1, _deadline_remaining_seconds(_strategy_deadline(inmob)))))
            except Exception as exc:
                logger.debug("detail extract error %s: %s", durl, exc)
    finally:
        _close_playwright_safely(detail_page, "html_scraper detail page")

    if not resultados:
        raise RuntimeError("sin_propiedades: html_scraper extrajo URLs pero no datos")
    return resultados


# ---------------------------------------------------------------------------
# Strategy dispatcher
# ---------------------------------------------------------------------------

_TOKKO_KEY_HTML_RE = re.compile(
    r'tokkobroker\.com[^\'"<]{0,300}/api/[^\'"<]{0,300}[?&](?:key|api_key)=([a-zA-Z0-9_\-]{20,80})',
    re.I,
)
_TOKKO_KEY_JS_RE = re.compile(
    r'(?:tokko[_\-\s]*(?:key|broker[_\-\s]*key)|api[_\-\s]*key)\s*[=:]\s*["\']([a-zA-Z0-9_\-]{20,80})["\']',
    re.I,
)
_TOKKO_UUID_RE = re.compile(
    r'tokko[^\'"]{0,60}[\'"]([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})[\'"]',
    re.I,
)
_LISTING_PATHS = [
    "/Propiedades", "/propiedades", "/propiedades/", "/Venta", "/venta", "/venta/",
    "/alquiler", "/alquiler/", "/ventas", "/ventas/",
    "/inmuebles", "/inmuebles/", "/listings", "/listings/",
    "/properties", "/properties/", "/buscar", "/",
]
_CARD_SELECTORS_DETECT = [
    "#propiedades > li[prop-id]", "ul.resultados-list > li[prop-id]",
    "#prop-list li[prop-id]", "li[prop-id]",
    ".property-card", ".propiedad-card", ".prop-card", ".listing-card",
    ".property-item", ".propiedad-item", ".prop-item",
    ".property-list-item", ".propiedad-list-item",
    "[class*='propert']", "[class*='propiedad']", "[class*='inmueble']",
    "[class*='listing']", "[class*='prop-']",
    "article.property", "article.propiedad", "article.inmueble",
    ".card-propiedad", ".ficha-propiedad", ".ficha-inmueble",
    ".grid-property", ".grid-propiedad", ".resultado", ".result-item",
    ".property", ".propiedad",
]


def _buscar_tokko_key_en_html(content: str) -> Optional[str]:
    """Busca la API key de Tokko en el HTML/JS de una página."""
    m = _TOKKO_KEY_HTML_RE.search(content)
    if m:
        return m.group(1)
    m = _TOKKO_UUID_RE.search(content)
    if m:
        return m.group(1)
    m = _TOKKO_KEY_JS_RE.search(content)
    if m:
        return m.group(1)
    soup = BeautifulSoup(content or "", "html.parser")
    for tag in soup.find_all("script", src=True):
        src = tag.get("src") or ""
        if "tokko" not in src.lower():
            continue
        m = _TOKKO_KEY_RE.search(src)
        if m:
            return m.group(1)
    return None


def _tiene_cards(page, min_cards: int = 3) -> bool:
    for sel in _CARD_SELECTORS_DETECT:
        try:
            if _count_selector(page, sel) >= min_cards:
                return True
        except Exception:
            pass
    return False


def detect_strategy(inmob: Dict, session: requests.Session, pw_context) -> Dict:
    """
    Fase de detección: visita el sitio y determina la mejor estrategia sin scrapear.
    Retorna un dict con los campos a guardar en inmobiliarias_main:
      estrategia_scraping, tokko_api_key (si la detectó), url_listado
    """
    url = inmob.get("url_listado") or inmob.get("web", "")
    resultado: Dict = {"estrategia_scraping": None}

    if not url:
        resultado["estrategia_scraping"] = "sin_url"
        return resultado

    if inmob.get("tokko_api_key"):
        resultado["estrategia_scraping"] = "tokko_api"
        return resultado

    # --- HTTP rápido: buscar Tokko key en HTML, JSON-LD y Sitemap ---
    try:
        r = _http_get(url, session, timeout=12)
        html = r.text
        # 1. Tokko key embebida en JS
        key = _buscar_tokko_key_en_html(html)
        if key:
            resultado["tokko_api_key"] = key
            resultado["estrategia_scraping"] = "tokko_api"
            return resultado
        # 2. JSON-LD
        soup = BeautifulSoup(html, "lxml")
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(tag.string or "")
                items = data if isinstance(data, list) else [data]
                for item in items:
                    t = item.get("@type", "")
                    if isinstance(t, list): t = t[0]
                    if t in _JSONLD_TYPES:
                        resultado["estrategia_scraping"] = "json_ld"
                        return resultado
            except Exception:
                pass
    except Exception:
        pass

    # 3. Sitemap
    base_url = url.rstrip("/")
    for sitemap_path in ["/sitemap.xml", "/sitemap_index.xml", "/sitemap-property.xml",
                         "/sitemap-propiedades.xml", "/sitemap-listings.xml"]:
        try:
            r = _http_get(base_url + sitemap_path, session, timeout=8)
            if r.status_code == 200 and PROPERTY_URL_PATTERNS.search(r.text):
                resultado["estrategia_scraping"] = "sitemap"
                return resultado
        except Exception:
            pass

    # --- Browser: detectar Tokko via network o HTML cards ---
    detected_tokko_key: Optional[str] = None

    def handle_resp(response):
        nonlocal detected_tokko_key
        if "api.tokkobroker.com" in response.url and detected_tokko_key is None:
            m = _TOKKO_KEY_RE.search(response.url)
            if m:
                detected_tokko_key = m.group(1)

    parsed = urlparse(url)
    homepage = f"{parsed.scheme}://{parsed.netloc}"

    page = pw_context.new_page()
    try:
        page.set_default_timeout(PLAYWRIGHT_ACTION_TIMEOUT_MS)
        page.set_default_navigation_timeout(PLAYWRIGHT_NAV_TIMEOUT_MS)
        page.on("response", handle_resp)

        # Cargar la URL original
        _playwright_goto(page, url, retries=2, timeout_ms=PLAYWRIGHT_NAV_TIMEOUT_MS)
        _human_scroll(page)
        try:
            page.wait_for_load_state("networkidle", timeout=PLAYWRIGHT_LOAD_TIMEOUT_MS)
        except Exception:
            pass

        # Buscar Tokko key en HTML renderizado
        if not detected_tokko_key:
            try:
                key = _buscar_tokko_key_en_html(page.content())
                if key:
                    detected_tokko_key = key
            except Exception:
                pass

        # Si no hay Tokko todavía, probar páginas de listado típicas
        if not detected_tokko_key and not _tiene_cards(page):
            for path in _LISTING_PATHS:
                listing_url = homepage + path
                if listing_url.rstrip("/") == url.rstrip("/"):
                    continue
                try:
                    _playwright_goto(page, listing_url, retries=1, timeout_ms=PLAYWRIGHT_NAV_TIMEOUT_MS)
                    try:
                        page.wait_for_load_state("networkidle", timeout=PLAYWRIGHT_LOAD_TIMEOUT_MS)
                    except Exception:
                        pass
                    if detected_tokko_key:
                        break
                    try:
                        key = _buscar_tokko_key_en_html(page.content())
                        if key:
                            detected_tokko_key = key
                            break
                    except Exception:
                        pass
                    if _tiene_cards(page):
                        break
                except Exception:
                    pass

        # Determinar estrategia final
        if detected_tokko_key:
            resultado["tokko_api_key"] = detected_tokko_key
            resultado["estrategia_scraping"] = "tokko_api"
        elif _tiene_cards(page):
            resultado["estrategia_scraping"] = "html"
        else:
            resultado["estrategia_scraping"] = "sin_estrategia"

    finally:
        _close_playwright_safely(page, "detect_strategy page")

    return resultado


def _save_estrategia(db: "SupabasePropiedades", inmob_id: int, fields: Dict) -> None:
    """Guarda la estrategia detectada en inmobiliarias_main."""
    campos = {k: v for k, v in fields.items() if v is not None}
    if not campos:
        return
    try:
        db.session.patch(
            f"{SUPABASE_URL}/rest/v1/inmobiliarias_main",
            headers=db._headers_minimal,
            params={"id": f"eq.{inmob_id}"},
            json=campos,
            timeout=10,
        )
    except Exception as e:
        logger.debug("_save_estrategia error: %s", e)


def _count_html_cards(html: str) -> int:
    soup = BeautifulSoup(html or "", "html.parser")
    max_count = 0
    for selector in _CARD_SELECTORS_DETECT:
        try:
            max_count = max(max_count, len(soup.select(selector)))
        except Exception:
            continue
    return max_count


def _is_site_down_status(status: Optional[int]) -> bool:
    return isinstance(status, int) and status in {500, 502, 503, 504, 521, 522, 523, 524}


def _site_down_reason_from_status(status: Optional[int]) -> str:
    if status is None:
        return "sin_respuesta"
    if status in {502, 503, 504}:
        return f"http_{status}"
    if status in {521, 522, 523, 524}:
        return f"cloudflare_{status}"
    if status >= 500:
        return f"http_{status}"
    return ""


def _site_down_reason_from_exception(exc: BaseException) -> str:
    msg = str(exc).lower()
    for status_code in ("502", "503", "504"):
        if f"too many {status_code}" in msg or f"{status_code} error responses" in msg:
            return f"http_{status_code}"
    if any(marker in msg for marker in (
        "nameresolutionerror", "name or service not known", "getaddrinfo failed",
        "temporary failure in name resolution", "nodename nor servname",
        "failed to resolve", "no address associated", "11001",
    )):
        return "dns_error"
    if any(marker in msg for marker in ("ssl", "certificate", "cert")):
        return "ssl_error"
    if any(marker in msg for marker in ("timed out", "timeout", "read timed out")):
        return "timeout"
    if any(marker in msg for marker in ("connection refused", "connection aborted", "connection reset", "max retries exceeded")):
        return "connection_error"
    return "connection_error" if _is_fast_site_down_error(exc) else "http_error"


def _looks_like_developer_project_url(url: str) -> bool:
    if not url or _is_noise_property_url(url):
        return False
    parsed = urlparse(str(url))
    path = unquote((parsed.path or "").lower()).strip("/")
    if not path:
        return False
    if re.search(r"^(blog|noticia|noticias|prensa|contactenos?|contacto|nosotros|login)(/|$)", path):
        return False
    if path in {"desarrollos", "desarrollo", "emprendimientos", "emprendimiento", "proyectos", "proyecto"}:
        return False
    return bool(re.search(r"(^|/)(desarrollos?|emprendimientos?|proyectos?)/[^/?#]{6,}", path, re.I))


def _extract_script_property_signals(html: str, current_url: str) -> Dict[str, List[str]]:
    """Busca URLs inmobiliarias dentro de scripts embebidos sin ejecutar JS."""
    soup = BeautifulSoup(html or "", "html.parser")
    script_text = "\n".join(script.get_text(" ", strip=False) for script in soup.find_all("script"))
    links: List[str] = []
    listings: List[str] = []
    projects: List[str] = []
    current_netloc = urlparse(current_url).netloc

    def add(raw: str) -> None:
        if not raw:
            return
        candidate = raw.replace("\\/", "/").strip()
        if candidate.startswith(("http://", "https://", "/")):
            full = urljoin(current_url, candidate).split("#", 1)[0]
        else:
            return
        if current_netloc and urlparse(full).netloc != current_netloc:
            return
        if _looks_like_real_property_url(full):
            if full not in links:
                links.append(full)
        elif _looks_like_custom_listing_url(full):
            if full not in listings:
                listings.append(full)
        elif _looks_like_developer_project_url(full):
            if full not in projects:
                projects.append(full)

    for match in re.findall(r"""https?://[^"'\\<>\s]+|/[^"'\\<>\s]*(?:propiedad|property|inmueble|ficha|detalle|listing|desarrollo|emprendimiento|proyecto)[^"'\\<>\s]*""", script_text, flags=re.I):
        add(match)

    return {
        "property_urls": links[:200],
        "listing_urls": listings[:100],
        "project_urls": projects[:100],
    }


def _extract_developer_project_links(html: str, current_url: str) -> List[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    current_netloc = urlparse(current_url).netloc
    links: List[str] = []
    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        full = urljoin(current_url, href).split("#", 1)[0]
        if current_netloc and urlparse(full).netloc != current_netloc:
            continue
        if _looks_like_developer_project_url(full) and full not in links:
            links.append(full)
    return links[:200]


def _fetch_sitemap_urls_for_diagnosis(base: str, session: requests.Session) -> Tuple[List[str], List[str], List[str], List[str]]:
    prop_urls: List[str] = []
    project_urls: List[str] = []
    tried: List[str] = []
    errors: List[str] = []
    parsed_base = urlparse(_normalize_queue_url(base))
    root_base = f"{parsed_base.scheme}://{parsed_base.netloc}" if parsed_base.scheme and parsed_base.netloc else base.rstrip("/")
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    def collect_from_xml(xml_text: str) -> Tuple[List[str], List[str], List[str]]:
        nested: List[str] = []
        props: List[str] = []
        projects: List[str] = []
        try:
            root = ET.fromstring(xml_text)
        except Exception:
            return nested, props, projects
        for sitemap_tag in root.findall(".//sm:sitemap/sm:loc", ns):
            sub_url = sitemap_tag.text.strip() if sitemap_tag.text else ""
            if sub_url:
                nested.append(sub_url)
        for loc_tag in root.findall(".//sm:url/sm:loc", ns):
            loc = loc_tag.text.strip() if loc_tag.text else ""
            if not loc:
                continue
            if _looks_like_real_property_url(loc):
                props.append(loc)
            elif _looks_like_developer_project_url(loc):
                projects.append(loc)
        return nested, props, projects

    for path in SITEMAP_PATHS:
        sitemap_url = urljoin(root_base.rstrip("/") + "/", path.lstrip("/"))
        tried.append(sitemap_url)
        try:
            response = _http_get(sitemap_url, session, timeout=4, use_scraper_on_block=False)
            if response.status_code != 200:
                continue
            nested, props, projects = collect_from_xml(_decode_response_text(response))
            prop_urls.extend(props)
            project_urls.extend(projects)
            for sub_url in nested[:12]:
                tried.append(sub_url)
                try:
                    sub_response = _http_get(sub_url, session, timeout=4, use_scraper_on_block=False)
                    if sub_response.status_code != 200:
                        continue
                    _, sub_props, sub_projects = collect_from_xml(_decode_response_text(sub_response))
                    prop_urls.extend(sub_props)
                    project_urls.extend(sub_projects)
                except Exception as sub_exc:
                    errors.append(f"{sub_url}: {type(sub_exc).__name__}: {str(sub_exc)[:140]}")
            if prop_urls or project_urls:
                break
        except Exception as exc:
            errors.append(f"{sitemap_url}: {type(exc).__name__}: {str(exc)[:140]}")
            if _site_down_reason_from_exception(exc) == "dns_error":
                break
    return (
        list(dict.fromkeys(prop_urls)),
        list(dict.fromkeys(project_urls)),
        tried,
        errors,
    )


def _wordpress_rest_links_for_diagnosis(base_url: str, session: requests.Session, plugin: str = "wordpress_generic") -> Tuple[List[str], List[str], List[str], List[str]]:
    parsed = urlparse(_normalize_queue_url(base_url))
    base = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else base_url.rstrip("/")
    links: List[str] = []
    detected_types: List[str] = []
    tried: List[str] = []
    errors: List[str] = []
    rest_types = list(dict.fromkeys(_WORDPRESS_REST_TYPES + ["pages", "posts"]))
    for post_type in rest_types:
        api_url = f"{base}/wp-json/wp/v2/{post_type}?per_page=50"
        tried.append(api_url)
        try:
            response = _http_get(api_url, session, timeout=4, use_scraper_on_block=False)
            if response.status_code != 200:
                continue
            data = response.json()
            if not isinstance(data, list) or not data:
                continue
            useful_links = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                link = str(item.get("link") or "")
                if link and (
                    _looks_like_wordpress_plugin_property_url(link, plugin)
                    or _looks_like_real_property_url(link)
                    or _looks_like_developer_project_url(link)
                ):
                    useful_links.append(link)
            if useful_links:
                detected_types.append(post_type)
                for link in useful_links:
                    if link not in links:
                        links.append(link)
        except Exception as exc:
            errors.append(f"{api_url}: {type(exc).__name__}: {str(exc)[:140]}")
            if _site_down_reason_from_exception(exc) == "dns_error":
                break
    return links[:300], detected_types, tried, errors


def _html_requires_js(html: str, property_links_count: int = 0, cards_count: int = 0) -> bool:
    low = (html or "").lower()
    js_markers = (
        "__next_data__", "next/static", "data-reactroot", "id=\"root\"",
        "id=\"app\"", "vue", "nuxt", "window.__initial_state__",
        "apollo-state", "webpack", "vite", "chunk.js", "main.js",
        "app.js", "window.__", "data-v-app", "ng-version",
    )
    if any(marker in low for marker in js_markers) and property_links_count == 0 and cards_count == 0:
        return True
    body_text = BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)
    loading_markers = ("cargando", "loading", "please enable javascript", "habilite javascript")
    return (
        len(body_text) < 300 and len(re.findall(r"<script\b", html or "", re.I)) >= 5
    ) or (
        len(body_text) < 500
        and any(marker in low for marker in loading_markers)
        and len(re.findall(r"<script\b", html or "", re.I)) >= 3
    )


def _jsonld_type_count(html: str) -> int:
    count = 0
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            schema_type = item.get("@type", "")
            if isinstance(schema_type, list):
                schema_type = schema_type[0] if schema_type else ""
            if schema_type in _JSONLD_TYPES:
                count += 1
    return count


def classify_diagnostic_failure(
    diagnostic: Dict[str, Any],
    allow_playwright: bool = False,
    allow_network_interception: bool = False,
) -> str:
    technologies = set(diagnostic.get("tecnologias_detectadas") or [])
    property_links_count = int(diagnostic.get("property_links_count") or 0)
    sitemap_count = int(diagnostic.get("sitemap_property_urls_count") or 0)
    custom_listing_count = int(diagnostic.get("custom_listing_urls_count") or 0)
    rest_count = int(diagnostic.get("wordpress_rest_property_urls_count") or 0)
    project_count = int(diagnostic.get("developer_project_urls_count") or 0)
    cards_count = int(diagnostic.get("cards_posibles") or 0)
    plugin = str(diagnostic.get("wordpress_plugin_detectado") or "").strip().lower()
    possible_detail_urls = diagnostic.get("posibles_urls_detalle") or []
    has_real_detail_urls = any(_looks_like_real_property_url(str(url)) for url in possible_detail_urls)

    # Las senales scrapeables tienen prioridad sobre errores parciales de rutas
    # alternativas. Un timeout en /venta no debe tapar que ya vimos Tokko + fichas.
    if "tokko_html" in technologies and (property_links_count > 0 or has_real_detail_urls or cards_count > 0):
        return "scrapeable_tokko"
    if "tokko_api" in technologies:
        return "scrapeable_tokko_api"
    if (
        "wordpress" in technologies
        and plugin in {"essential_real_estate", "estatik", "realhomes"}
        and property_links_count > 0
    ):
        return f"scrapeable_wordpress_{plugin}"
    if "wordpress" in technologies and sitemap_count > 0:
        return "scrapeable_wordpress_sitemap"
    if "wordpress" in technologies and rest_count > 0:
        return "scrapeable_wordpress_rest"
    if "wordpress" in technologies and property_links_count > 0:
        if plugin and plugin not in {"unknown", "wordpress_generic"}:
            return f"scrapeable_wordpress_{plugin}"
        return "scrapeable_wordpress_html"
    if custom_listing_count > 0:
        return "scrapeable_custom_listing"
    if property_links_count > 0:
        return "scrapeable_static_html"
    if sitemap_count > 0:
        return "scrapeable_sitemap"
    if project_count > 0:
        return "scrapeable_developer_projects"

    status = diagnostic.get("http_status")
    if status is None or diagnostic.get("site_down"):
        return "site_down_confirmed"
    if _is_site_down_status(status):
        return "site_down_confirmed"
    if status in {403, 429} or diagnostic.get("blocked"):
        return "blocked"
    if diagnostic.get("html_empty"):
        return "empty_site"

    if diagnostic.get("requires_network_interception") and not allow_network_interception:
        return "requires_network_interception"
    if diagnostic.get("requires_playwright") and not allow_playwright:
        return "requires_playwright"
    if property_links_count == 0 and sitemap_count == 0 and custom_listing_count == 0 and rest_count == 0 and project_count == 0:
        return "no_property_links_confirmed"
    if diagnostic.get("unsupported_cms"):
        return "unsupported_cms"
    return "parsing_failed"


def diagnose_inmob(
    inmob: Dict,
    session: requests.Session,
    pw_context=None,
    allow_playwright: bool = False,
    allow_network_interception: bool = False,
) -> Dict[str, Any]:
    """Diagnostico universal sin guardar propiedades ni consumir cola."""
    started_at = time.time()
    url_inicial = inmob.get("url_listado") or inmob.get("web", "")
    start_infos: List[Dict[str, Any]] = []
    for raw_url in (url_inicial, inmob.get("web")):
        if raw_url:
            start_infos.append(normalize_start_url_for_diagnosis(raw_url))
    primary_start_info = start_infos[0] if start_infos else normalize_start_url_for_diagnosis(url_inicial)
    base_variants: List[str] = []
    subfolder_bases: List[str] = []
    derived_candidates: List[str] = []
    for info in start_infos:
        for key, target in (
            ("base_variants", base_variants),
            ("subfolder_bases", subfolder_bases),
            ("candidate_urls", derived_candidates),
        ):
            for value in info.get(key) or []:
                if value and value not in target:
                    target.append(value)

    diagnostic: Dict[str, Any] = {
        "url_original": url_inicial,
        "url_inicial": url_inicial,
        "url_normalizada": _normalize_queue_url(url_inicial),
        "url_usada": None,
        "url_diagnostico_usada": None,
        "url_base_derivada": primary_start_info.get("url_base_derivada"),
        "url_inicial_era_contacto": any(bool(info.get("url_inicial_era_contacto")) for info in start_infos),
        "rutas_alternativas_probadas": [],
        "route_diagnostics": [],
        "sitemap_urls_probadas": [],
        "rest_api_probada": [],
        "scripts_json_detectados": 0,
        "motivo_no_scrapeable": None,
        "tecnologias_detectadas": [],
        "extractores_posibles": [],
        "posibles_urls_listado": [],
        "posibles_urls_detalle": [],
        "property_links_count": 0,
        "custom_listing_urls_count": 0,
        "developer_project_urls_count": 0,
        "wordpress_rest_property_urls_count": 0,
        "cards_posibles": 0,
        "json_ld_property_items": 0,
        "sitemap_property_urls_count": 0,
        "requires_js": False,
        "requires_playwright": False,
        "requires_network_interception": False,
        "blocked": False,
        "site_down": False,
        "html_empty": False,
        "http_statuses": [],
        "failed_base_variants": [],
        "site_down_reason": None,
        "elapsed_seconds": 0,
    }
    if not url_inicial:
        diagnostic["site_down"] = True
        diagnostic["site_down_reason"] = "sin_url"
        diagnostic["classification"] = "site_down_confirmed"
        return diagnostic

    first_html = ""
    final_url = diagnostic["url_normalizada"]
    candidates: List[str] = []

    def add_candidate(candidate: Optional[str]) -> None:
        if not candidate:
            return
        clean = _normalize_queue_url(str(candidate).split("#", 1)[0])
        if clean and clean not in candidates:
            candidates.append(clean)

    for candidate in derived_candidates:
        add_candidate(candidate)
    for candidate in _generic_candidate_urls(inmob, first_url=final_url):
        add_candidate(candidate)
    diagnostic["posibles_urls_listado"] = candidates[:30]
    diagnostic["rutas_alternativas_probadas"] = candidates[1:30]
    fast_site_down_errors = 0
    site_down_statuses = 0
    tried_fetch_urls: List[str] = []
    html_pages: List[Tuple[str, str]] = []
    base_set = {
        _normalize_queue_url(value).rstrip("/")
        for value in (base_variants + subfolder_bases)
        if value
    }
    failed_base_variants: List[str] = []
    minimum_base_probe_count = min(4, len(candidates))

    def is_base_candidate(candidate: str) -> bool:
        normalized = _normalize_queue_url(candidate).rstrip("/")
        return normalized in base_set

    for candidate in candidates[:8]:
        tried_fetch_urls.append(candidate)
        try:
            response = _http_get(candidate, session, timeout=5, use_scraper_on_block=False)
            diagnostic["http_statuses"].append(response.status_code)
            diagnostic["http_status"] = response.status_code
            final_url = response.url or candidate
            diagnostic["final_url"] = final_url
            if response.status_code in {403, 429}:
                diagnostic["blocked"] = True
            if _is_site_down_status(response.status_code):
                diagnostic["site_down"] = True
                diagnostic["site_down_reason"] = diagnostic.get("site_down_reason") or _site_down_reason_from_status(response.status_code)
                site_down_statuses += 1
                if site_down_statuses >= 3 and len(tried_fetch_urls) >= minimum_base_probe_count:
                    break
            if response.status_code == 200 and response.text:
                first_html = _decode_response_text(response)
                if first_html.strip():
                    html_pages.append((first_html, final_url))
                    diagnostic["url_diagnostico_usada"] = final_url
                else:
                    diagnostic["html_empty"] = True
                break
        except Exception as exc:
            diagnostic.setdefault("errores_http", []).append(f"{candidate}: {type(exc).__name__}: {str(exc)[:180]}")
            if _is_fast_site_down_error(exc):
                fast_site_down_errors += 1
                diagnostic["site_down"] = True
                reason = _site_down_reason_from_exception(exc)
                diagnostic["site_down_reason"] = diagnostic.get("site_down_reason") or reason
                if is_base_candidate(candidate) and candidate not in failed_base_variants:
                    failed_base_variants.append(candidate)
                if fast_site_down_errors >= 2:
                    break

    diagnostic["failed_base_variants"] = failed_base_variants

    if not first_html:
        diagnostic["html_empty"] = not diagnostic.get("site_down")
        if diagnostic.get("site_down") and not diagnostic.get("site_down_reason"):
            diagnostic["site_down_reason"] = "sin_respuesta"
        diagnostic["elapsed_seconds"] = round(time.time() - started_at, 2)
        if diagnostic.get("site_down"):
            diagnostic["motivo_no_scrapeable"] = diagnostic.get("site_down_reason") or "site_down"
        else:
            diagnostic["motivo_no_scrapeable"] = "html_vacio_o_sin_respuesta"
        diagnostic["classification"] = classify_diagnostic_failure(diagnostic, allow_playwright, allow_network_interception)
        return diagnostic

    # Escaneo liviano de rutas inmobiliarias alternativas. Esto evita diagnosticar
    # toda la inmobiliaria desde una pagina tipo contacto o landing institucional.
    for candidate in candidates[:16]:
        if len(html_pages) >= 9:
            break
        if candidate in tried_fetch_urls or candidate == final_url:
            continue
        tried_fetch_urls.append(candidate)
        try:
            response = _http_get(candidate, session, timeout=4, use_scraper_on_block=False)
            diagnostic["http_statuses"].append(response.status_code)
            if response.status_code in {403, 429}:
                diagnostic["blocked"] = True
            if _is_site_down_status(response.status_code):
                site_down_statuses += 1
                diagnostic["site_down_reason"] = diagnostic.get("site_down_reason") or _site_down_reason_from_status(response.status_code)
                continue
            if response.status_code != 200 or not response.text:
                continue
            html = _decode_response_text(response)
            if html.strip():
                html_pages.append((html, response.url or candidate))
        except Exception as exc:
            diagnostic.setdefault("errores_http", []).append(f"{candidate}: {type(exc).__name__}: {str(exc)[:180]}")
            if _is_fast_site_down_error(exc):
                reason = _site_down_reason_from_exception(exc)
                diagnostic["site_down_reason"] = diagnostic.get("site_down_reason") or reason
                if is_base_candidate(candidate) and candidate not in failed_base_variants:
                    failed_base_variants.append(candidate)

    diagnostic["rutas_alternativas_probadas"] = tried_fetch_urls
    diagnostic["failed_base_variants"] = failed_base_variants
    combined_html = "\n".join(html for html, _ in html_pages)

    key = _buscar_tokko_key_en_html(combined_html)
    if key:
        diagnostic["tokko_api_key_detectada"] = True
        diagnostic["tecnologias_detectadas"].append("tokko_api")
        diagnostic["extractores_posibles"].append("tokko_api")
    if _is_tokko_html(combined_html) or "tokko" in str(inmob.get("cms_detectado") or "").lower():
        diagnostic["tecnologias_detectadas"].append("tokko_html")
        diagnostic["extractores_posibles"].append("tokko_html")

    wp_plugin = "unknown"
    for page_html, _ in html_pages:
        detected_plugin = _detect_wordpress_plugin(page_html)
        if detected_plugin != "unknown":
            wp_plugin = detected_plugin
            break
    cms_hint = str(inmob.get("cms_detectado") or inmob.get("cms") or "").lower()
    if wp_plugin == "unknown" and "wordpress" in cms_hint:
        wp_plugin = "wordpress_generic"
    if wp_plugin != "unknown":
        diagnostic["wordpress_plugin_detectado"] = wp_plugin
        diagnostic["tecnologias_detectadas"].append("wordpress")
        diagnostic["extractores_posibles"].append("wordpress_html")
        diagnostic["extractores_posibles"].append(_wordpress_plugin_strategy_name(wp_plugin))

    generic_property_links: List[str] = []
    plugin_property_links: List[str] = []
    listing_links: List[str] = []
    custom_listing_urls: List[str] = []
    developer_project_urls: List[str] = []
    script_property_urls: List[str] = []
    script_listing_urls: List[str] = []
    script_project_urls: List[str] = []
    jsonld_count = 0
    cards_count = 0
    route_diagnostics: List[Dict[str, Any]] = []

    for page_html, page_url in html_pages:
        page_generic_links = _extract_generic_property_links(page_html, page_url)
        generic_property_links.extend(page_generic_links)
        page_plugin_links: List[str] = []
        if wp_plugin != "unknown":
            page_plugin_links = _extract_wordpress_plugin_property_links(page_html, page_url, wp_plugin)
            plugin_property_links.extend(page_plugin_links)
        page_listing_links = [
            link for link in _extract_keyword_internal_links(page_html, page_url, _UNIVERSAL_LISTING_KEYWORDS)
            if not _is_noise_property_url(link)
        ]
        listing_links.extend(page_listing_links)
        page_custom_listing_urls = _extract_custom_listing_urls(page_html, page_url)
        custom_listing_urls.extend(page_custom_listing_urls)
        if _looks_like_custom_listing_url(page_url):
            custom_listing_urls.append(page_url)
        page_developer_project_urls = _extract_developer_project_links(page_html, page_url)
        developer_project_urls.extend(page_developer_project_urls)
        script_signals = _extract_script_property_signals(page_html, page_url)
        page_script_property_urls = script_signals["property_urls"]
        page_script_listing_urls = script_signals["listing_urls"]
        page_script_project_urls = script_signals["project_urls"]
        script_property_urls.extend(page_script_property_urls)
        script_listing_urls.extend(page_script_listing_urls)
        script_project_urls.extend(page_script_project_urls)
        if any(script_signals.values()):
            diagnostic["scripts_json_detectados"] += 1
        page_jsonld_count = _jsonld_type_count(page_html)
        jsonld_count += page_jsonld_count
        page_cards_count = _count_html_cards(page_html)
        cards_count = max(cards_count, page_cards_count)

        route_extractors: List[str] = []
        if _is_tokko_html(page_html):
            route_extractors.append("tokko_html")
        if wp_plugin != "unknown":
            route_extractors.append(_wordpress_plugin_strategy_name(wp_plugin))
        if page_generic_links or page_plugin_links or page_script_property_urls:
            route_extractors.append("static_html")
        if page_custom_listing_urls:
            route_extractors.append("custom_listing_detail")
        if page_jsonld_count:
            route_extractors.append("json_ld")

        discard_reasons: List[str] = []
        if not (page_generic_links or page_plugin_links or page_script_property_urls):
            discard_reasons.append("sin_links_detalle_estaticos")
        if _is_tokko_html(page_html) and page_cards_count > 0:
            discard_reasons.append("tokko_detectado_debe_probar_rutas_tokko")
        elif page_cards_count > 0:
            discard_reasons.append("cards_sin_links_detalle")
        if not route_extractors:
            discard_reasons.append("sin_extractor_liviano_detectado")

        route_diagnostics.append({
            "url": page_url,
            "tokko_template": _detect_tokko_template(page_html),
            "wordpress_plugin": wp_plugin if wp_plugin != "unknown" else None,
            "generic_property_links_count": len(page_generic_links),
            "plugin_property_links_count": len(page_plugin_links),
            "script_property_urls_count": len(page_script_property_urls),
            "listing_links_count": len(page_listing_links),
            "custom_listing_urls_count": len(page_custom_listing_urls),
            "developer_project_urls_count": len(page_developer_project_urls),
            "cards_posibles": page_cards_count,
            "json_ld_property_items": page_jsonld_count,
            "requires_js": _html_requires_js(page_html, len(page_generic_links) + len(page_plugin_links) + len(page_script_property_urls), page_cards_count),
            "extractores_detectados": list(dict.fromkeys(route_extractors)),
            "motivos_descarte": discard_reasons,
        })
        if not diagnostic.get("url_usada") and (
            page_generic_links
            or page_plugin_links
            or page_script_property_urls
            or page_custom_listing_urls
            or page_cards_count > 0
        ):
            diagnostic["url_usada"] = page_url

    diagnostic["route_diagnostics"] = route_diagnostics[:30]

    if wp_plugin != "unknown":
        property_links = [
            url for url in list(dict.fromkeys(plugin_property_links + generic_property_links + script_property_urls))
            if _looks_like_wordpress_plugin_property_url(url, wp_plugin) or _looks_like_real_property_url(url)
        ]
    else:
        property_links = [url for url in list(dict.fromkeys(generic_property_links + script_property_urls)) if _looks_like_real_property_url(url)]

    custom_listing_urls = list(dict.fromkeys(custom_listing_urls + script_listing_urls))
    developer_project_urls = list(dict.fromkeys(developer_project_urls + script_project_urls))
    diagnostic["property_links_count"] = len(property_links)
    diagnostic["urls_validas_detectadas"] = len([url for url in property_links if _looks_like_real_property_url(url) or _looks_like_wordpress_plugin_property_url(url, wp_plugin)])
    diagnostic["posibles_urls_detalle"] = property_links[:20]
    diagnostic["custom_listing_urls_count"] = len(custom_listing_urls)
    diagnostic["custom_listing_urls_detectadas"] = custom_listing_urls[:30]
    diagnostic["developer_project_urls_count"] = len(developer_project_urls)
    diagnostic["developer_project_urls_detectadas"] = developer_project_urls[:20]
    diagnostic["posibles_urls_listado"] = list(dict.fromkeys(diagnostic["posibles_urls_listado"] + listing_links + custom_listing_urls))[:30]
    if custom_listing_urls:
        diagnostic["extractores_posibles"].append("custom_listing_detail")
    if property_links:
        diagnostic["extractores_posibles"].append("static_html")

    diagnostic["cards_posibles"] = cards_count
    if cards_count >= 3 and "static_html" not in diagnostic["extractores_posibles"]:
        diagnostic["extractores_posibles"].append("static_html")

    diagnostic["json_ld_property_items"] = jsonld_count
    if jsonld_count:
        diagnostic["extractores_posibles"].append("json_ld")

    parsed = urlparse(final_url)
    base = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else final_url
    try:
        sitemap_urls, sitemap_project_urls, sitemap_tried, sitemap_errors = _fetch_sitemap_urls_for_diagnosis(base, session)
        diagnostic["sitemap_urls_probadas"] = sitemap_tried
        if sitemap_errors:
            diagnostic.setdefault("errores_http", []).extend(f"sitemap: {err}" for err in sitemap_errors[:8])
        diagnostic["sitemap_property_urls_count"] = len(sitemap_urls)
        if sitemap_project_urls:
            developer_project_urls = list(dict.fromkeys(developer_project_urls + sitemap_project_urls))
            diagnostic["developer_project_urls_count"] = len(developer_project_urls)
            diagnostic["developer_project_urls_detectadas"] = developer_project_urls[:20]
        if sitemap_urls:
            diagnostic["extractores_posibles"].append("sitemap")
            diagnostic["posibles_urls_detalle"] = list(dict.fromkeys(diagnostic["posibles_urls_detalle"] + sitemap_urls[:20]))[:30]
    except Exception as exc:
        diagnostic.setdefault("errores_http", []).append(f"sitemap: {type(exc).__name__}: {str(exc)[:180]}")

    if "wordpress" in diagnostic["tecnologias_detectadas"]:
        try:
            rest_links, rest_types, rest_tried, rest_errors = _wordpress_rest_links_for_diagnosis(base, session, wp_plugin)
            diagnostic["rest_api_probada"] = rest_tried
            diagnostic["wordpress_rest_types_detectados"] = rest_types
            rest_property_links = [
                link for link in rest_links
                if _looks_like_wordpress_plugin_property_url(link, wp_plugin) or _looks_like_real_property_url(link)
            ]
            rest_project_links = [link for link in rest_links if _looks_like_developer_project_url(link)]
            diagnostic["wordpress_rest_property_urls_count"] = len(rest_property_links)
            if rest_property_links:
                diagnostic["extractores_posibles"].append("wordpress_rest")
                diagnostic["posibles_urls_detalle"] = list(dict.fromkeys(diagnostic["posibles_urls_detalle"] + rest_property_links[:20]))[:30]
                property_links = list(dict.fromkeys(property_links + rest_property_links))
                diagnostic["property_links_count"] = len(property_links)
                diagnostic["urls_validas_detectadas"] = len([url for url in property_links if _looks_like_real_property_url(url) or _looks_like_wordpress_plugin_property_url(url, wp_plugin)])
            if rest_project_links:
                developer_project_urls = list(dict.fromkeys(developer_project_urls + rest_project_links))
                diagnostic["developer_project_urls_count"] = len(developer_project_urls)
                diagnostic["developer_project_urls_detectadas"] = developer_project_urls[:20]
            if rest_errors:
                diagnostic.setdefault("errores_http", []).extend(f"rest: {err}" for err in rest_errors[:8])
        except Exception as exc:
            diagnostic.setdefault("errores_http", []).append(f"rest: {type(exc).__name__}: {str(exc)[:180]}")

    if developer_project_urls and "developer_projects" not in diagnostic["extractores_posibles"]:
        diagnostic["extractores_posibles"].append("developer_projects")

    requires_js = _html_requires_js(combined_html, len(property_links), cards_count)
    diagnostic["requires_js"] = requires_js
    diagnostic["requires_playwright"] = requires_js and not property_links and not jsonld_count and not diagnostic["sitemap_property_urls_count"]
    diagnostic["requires_network_interception"] = (
        "tokko" in " ".join(diagnostic["tecnologias_detectadas"])
        and not key
        and diagnostic["requires_playwright"]
    )

    if allow_playwright and pw_context is not None:
        page = None
        try:
            page = pw_context.new_page()
            page.set_default_timeout(PLAYWRIGHT_ACTION_TIMEOUT_MS)
            page.set_default_navigation_timeout(PLAYWRIGHT_NAV_TIMEOUT_MS)
            _playwright_goto(page, final_url, retries=1, timeout_ms=PLAYWRIGHT_NAV_TIMEOUT_MS)
            _human_scroll(page)
            try:
                page.wait_for_load_state("networkidle", timeout=PLAYWRIGHT_LOAD_TIMEOUT_MS)
            except Exception:
                pass
            rendered_html = page.content()
            rendered_links = _extract_generic_property_links(rendered_html, page.url)
            diagnostic["playwright_cards_posibles"] = _count_html_cards(rendered_html)
            diagnostic["playwright_property_links_count"] = len(rendered_links)
            if rendered_links:
                diagnostic["requires_playwright"] = True
                diagnostic["extractores_posibles"].append("html_scraper")
                diagnostic["posibles_urls_detalle"] = list(dict.fromkeys(diagnostic["posibles_urls_detalle"] + rendered_links[:20]))[:30]
        except Exception as exc:
            diagnostic["playwright_error"] = f"{type(exc).__name__}: {str(exc)[:180]}"
        finally:
            _close_playwright_safely(page, "diagnose page")

    if not property_links and not diagnostic["sitemap_property_urls_count"] and not custom_listing_urls and not developer_project_urls:
        if diagnostic.get("requires_playwright"):
            diagnostic["motivo_no_scrapeable"] = "html_responde_pero_contenido_cargado_por_js"
        else:
            diagnostic["motivo_no_scrapeable"] = "sin_fichas_reales_tras_rutas_alternativas"

    diagnostic["extractores_posibles"] = list(dict.fromkeys(diagnostic["extractores_posibles"]))
    diagnostic["tecnologias_detectadas"] = list(dict.fromkeys(diagnostic["tecnologias_detectadas"])) or ["unknown"]
    diagnostic["elapsed_seconds"] = round(time.time() - started_at, 2)
    diagnostic["classification"] = classify_diagnostic_failure(diagnostic, allow_playwright, allow_network_interception)
    return diagnostic


def _diagnostic_expected_property_count(diagnostic: Dict[str, Any]) -> int:
    """Estimacion conservadora para quality scoring.

    Los contadores de cards pueden inflarse por grillas, filtros o skeletons.
    Se priorizan URLs reales y sitemaps; las cards solo empujan el esperado de
    forma acotada para no rechazar resultados validos por ruido visual.
    """
    property_links = int(diagnostic.get("property_links_count") or 0)
    valid_urls = int(diagnostic.get("urls_validas_detectadas") or 0)
    sitemap_count = int(diagnostic.get("sitemap_property_urls_count") or 0)
    custom_listing_count = int(diagnostic.get("custom_listing_urls_count") or 0)
    cards = int(diagnostic.get("cards_posibles") or 0)
    url_signal = max(property_links, valid_urls)
    if sitemap_count >= 5:
        return max(sitemap_count, url_signal)
    if url_signal > 0:
        card_cap = min(cards, max(url_signal * 2, url_signal))
        return max(url_signal, card_cap)
    if sitemap_count > 0:
        return sitemap_count
    if custom_listing_count > 0:
        return max(min(custom_listing_count * 6, 60), custom_listing_count)
    if cards >= 6:
        return min(cards, 40)
    return max(cards, 0)


def _strategy_plan_noop(reason: str, diagnostic: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "primary_strategy": None,
        "fallback_strategies": [],
        "reason": reason,
        "expected_property_count": _diagnostic_expected_property_count(diagnostic),
        "confidence": "high",
        "requires_playwright": bool(diagnostic.get("requires_playwright")),
        "requires_network_interception": bool(diagnostic.get("requires_network_interception")),
        "should_save_strategy_for_future": False,
        "classification": diagnostic.get("classification"),
        "discarded_extractors": diagnostic.get("extractores_posibles") or [],
    }


def _detail_urls_have_tokko_classic_shape(diagnostic: Dict[str, Any]) -> bool:
    urls = diagnostic.get("posibles_urls_detalle") or []
    return any(re.search(r"/p/\d{3,}", str(url), re.I) for url in urls)


def _detail_urls_have_real_property_shape(diagnostic: Dict[str, Any]) -> bool:
    return any(_looks_like_real_property_url(str(url)) for url in (diagnostic.get("posibles_urls_detalle") or []))


def select_best_scraping_strategy(diagnostic: Dict[str, Any], history: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Selecciona una estrategia principal a partir del diagnostico, sin ejecutar extractores al azar."""
    history = history or {}
    classification = str(diagnostic.get("classification") or "")
    technologies = set(diagnostic.get("tecnologias_detectadas") or [])
    extractores_posibles = list(diagnostic.get("extractores_posibles") or [])
    property_links = int(diagnostic.get("property_links_count") or 0)
    sitemap_count = int(diagnostic.get("sitemap_property_urls_count") or 0)
    custom_listing_count = int(diagnostic.get("custom_listing_urls_count") or 0)
    cards = int(diagnostic.get("cards_posibles") or 0)
    plugin = str(diagnostic.get("wordpress_plugin_detectado") or "").strip().lower()
    expected = _diagnostic_expected_property_count(diagnostic)

    no_scrapeable = {
        "site_down", "blocked", "empty_site", "no_property_links",
        "site_down_confirmed", "no_property_links_confirmed",
        "unsupported_cms", "tracking_only",
    }
    if classification in no_scrapeable:
        return _strategy_plan_noop(classification, diagnostic)

    primary: Optional[str] = None
    fallbacks: List[str] = []
    reason = ""
    confidence = "medium"

    saved_strategy = history.get("best_scraping_strategy") or history.get("last_successful_strategy")
    if saved_strategy in {
        "tokko_html",
        "static_html_tokko_detail",
        "wordpress_sitemap_detail",
        "wordpress_essential_real_estate_detail",
        "wordpress_estatik_detail",
        "wordpress_realhomes_detail",
        "wordpress_generic_detail",
        "custom_listing_detail",
        "static_html_detail",
        "playwright_html",
        "network_interception",
    }:
        primary = str(saved_strategy)
        reason = f"estrategia historica: {saved_strategy}"
        confidence = "high"

    if primary is None and "wordpress" in technologies:
        if plugin in {"essential_real_estate", "estatik", "realhomes"}:
            primary = _wordpress_plugin_strategy_name(plugin)
            fallbacks = ["static_html_detail"]
            if plugin == "realhomes" and sitemap_count >= max(5, property_links):
                fallbacks.insert(0, "wordpress_sitemap_detail")
            elif sitemap_count >= 20:
                fallbacks.append("wordpress_sitemap_detail")
            reason = f"wordpress/{plugin} con extractor especifico; links={property_links}, cards={cards}, sitemap={sitemap_count}"
            confidence = "high" if property_links > 0 or cards >= 6 else "medium"
        elif plugin in {"houzez"} and sitemap_count >= 5:
            primary = "wordpress_sitemap_detail"
            fallbacks = ["wordpress_generic_detail", "static_html_detail"]
            reason = f"wordpress/{plugin} con sitemap de propiedades ({sitemap_count} URLs)"
            confidence = "high" if sitemap_count >= 20 else "medium"
        elif sitemap_count > 0:
            primary = "wordpress_sitemap_detail"
            fallbacks = ["wordpress_generic_detail", "static_html_detail"]
            reason = f"wordpress/{plugin or 'generic'} con sitemap de propiedades ({sitemap_count} URLs)"
            confidence = "high" if sitemap_count >= 20 else "medium"
        elif classification == "scrapeable_wordpress_rest":
            primary = "wordpress_generic_detail"
            fallbacks = ["static_html_detail"]
            reason = "wordpress con REST API mostrando URLs de propiedades"
            confidence = "medium"
        elif property_links > 0:
            primary = "wordpress_generic_detail"
            fallbacks = ["static_html_detail"]
            reason = f"wordpress con links HTML de propiedades ({property_links})"
            confidence = "medium"

    if primary is None and "tokko_api" in technologies:
        primary = "tokko_api"
        fallbacks = ["tokko_html", "static_html_tokko_detail"]
        reason = "Tokko API key detectada"
        confidence = "high"

    if primary is None and "tokko_html" in technologies:
        if _detail_urls_have_tokko_classic_shape(diagnostic) and cards >= 3:
            primary = "tokko_html"
            fallbacks = ["static_html_tokko_detail", "json_ld", "sitemap"]
            reason = f"Tokko clasico con cards HTML ({cards}) y URLs /p/"
            confidence = "high"
        elif property_links > 0 or _detail_urls_have_real_property_shape(diagnostic):
            primary = "static_html_tokko_detail"
            fallbacks = ["tokko_html", "static_html_detail", "json_ld"]
            reason = "Tokko custom/estatico: hay fichas reales pero no cards clasicas suficientes"
            confidence = "medium"
        elif classification == "scrapeable_tokko" or cards > 0 or "tokko_html" in extractores_posibles:
            primary = "tokko_html"
            fallbacks = ["static_html_tokko_detail", "json_ld", "sitemap"]
            reason = (
                "Tokko detectado sin links estaticos de detalle; "
                "se prueban rutas Tokko conocidas (/Venta, /Propiedades, /Alquiler)"
            )
            confidence = "medium"

    if primary is None and (classification == "scrapeable_custom_listing" or custom_listing_count > 0):
        primary = "custom_listing_detail"
        fallbacks = ["static_html_detail"]
        reason = f"custom listing con URLs /listing detectadas ({custom_listing_count})"
        confidence = "medium"

    if primary is None and sitemap_count > 0:
        primary = "sitemap"
        fallbacks = ["static_html_detail", "json_ld"]
        reason = f"sitemap con URLs de propiedades ({sitemap_count})"
        confidence = "medium"

    if primary is None and property_links > 0 and _detail_urls_have_real_property_shape(diagnostic):
        primary = "static_html_detail"
        fallbacks = ["json_ld"]
        reason = f"HTML estatico con links reales de propiedades ({property_links})"
        confidence = "medium"

    if primary is None and classification == "scrapeable_developer_projects":
        primary = "static_html_detail"
        fallbacks = ["json_ld"]
        reason = "sitio con fichas de desarrollos/emprendimientos detectadas"
        confidence = "low"

    if primary is None and diagnostic.get("requires_playwright"):
        primary = "playwright_html"
        fallbacks = ["network_interception"] if diagnostic.get("requires_network_interception") else []
        reason = "HTML requiere renderizado JS"
        confidence = "low"

    if primary is None and diagnostic.get("requires_network_interception"):
        primary = "network_interception"
        fallbacks = ["playwright_html"]
        reason = "diagnostico sugiere APIs/XHR como fuente principal"
        confidence = "low"

    if primary is None:
        return _strategy_plan_noop(classification or "no_property_links", diagnostic)

    ordered = []
    for strategy in [primary] + fallbacks:
        if strategy and strategy not in ordered:
            ordered.append(strategy)
    primary = ordered[0]
    fallbacks = ordered[1:]
    discarded = [extractor for extractor in extractores_posibles if extractor not in ordered]
    return {
        "primary_strategy": primary,
        "fallback_strategies": fallbacks,
        "reason": reason,
        "expected_property_count": int(expected),
        "confidence": confidence,
        "requires_playwright": primary == "playwright_html" or "playwright_html" in fallbacks,
        "requires_network_interception": primary == "network_interception" or "network_interception" in fallbacks,
        "should_save_strategy_for_future": confidence in {"high", "medium"} and primary not in {"playwright_html", "network_interception"},
        "classification": classification,
        "discarded_extractors": discarded,
    }


def _is_absurd_property_price(prop: Dict[str, Any]) -> bool:
    invalid, _ = _is_invalid_public_price(prop.get("precio"), prop.get("moneda"))
    return invalid


def _ratio(count: int, total: int) -> float:
    return round(count / total, 3) if total else 0.0


def _sanitize_scraped_props_for_quality(props: List[Dict[str, Any]], metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Aplica guardas centrales antes de puntuar y antes de devolver props del test."""
    stats = metadata.setdefault("quality_sanitization_stats", _new_update_protection_stats())
    sanitized: List[Dict[str, Any]] = []
    for prop in props or []:
        clean = dict(prop)
        clean = sanitize_property_location(clean, stats)
        clean = sanitize_property_coordinates(clean, stats)
        clean = sanitize_property_prices(clean, stats)
        clean = sanitize_property_integers(clean, stats)
        raw_images = clean.get("imagenes")
        if isinstance(raw_images, str):
            raw_images = [raw_images]
        if isinstance(raw_images, list):
            clean["imagenes"] = clean_property_images(raw_images) or None
        sanitized.append(clean)
    return sanitized


def evaluate_scrape_quality(
    props: List[Dict],
    strategy_plan: Dict[str, Any],
    diagnostic: Dict[str, Any],
) -> Dict[str, Any]:
    total = len(props or [])
    expected = int(strategy_plan.get("expected_property_count") or 0)
    diagnostic_property_links = int(diagnostic.get("property_links_count") or 0)
    diagnostic_sitemap_count = int(diagnostic.get("sitemap_property_urls_count") or 0)
    if total == 0:
        return {
            "accepted": False,
            "score": 0,
            "total": 0,
            "issues": ["sin_propiedades"],
            "expected_property_count": expected,
        }

    accepts_custom_urls = (
        strategy_plan.get("primary_strategy") == "custom_listing_detail"
        or diagnostic.get("classification") == "scrapeable_custom_listing"
    )
    url_real_count = sum(
        1
        for prop in props
        if _looks_like_real_property_url(str(prop.get("url") or ""))
        or (accepts_custom_urls and _looks_like_custom_property_url(str(prop.get("url") or "")))
    )
    useful_title_count = sum(1 for prop in props if _is_useful_scraped_title(prop.get("titulo")))
    valid_price_count = sum(1 for prop in props if _positive_number(prop.get("precio")))
    image_count = sum(1 for prop in props if _has_real_images(prop.get("imagenes")))
    address_count = sum(1 for prop in props if _useful_text(prop.get("direccion")) or _useful_text(prop.get("barrio")))
    generic_title_count = total - useful_title_count
    absurd_price_count = sum(1 for prop in props if _is_absurd_property_price(prop))

    url_ratio = _ratio(url_real_count, total)
    title_ratio = _ratio(useful_title_count, total)
    price_ratio = _ratio(valid_price_count, total)
    image_ratio = _ratio(image_count, total)
    address_ratio = _ratio(address_count, total)

    issues: List[str] = []
    strong_missing_signal = diagnostic_sitemap_count >= 20 or diagnostic_property_links >= 30
    if strong_missing_signal and expected >= 50 and total < max(10, int(expected * 0.08)):
        issues.append(f"too_few_vs_expected:{total}/{expected}")
    if url_ratio < 0.6:
        issues.append("urls_invalidas")
    if title_ratio < 0.5:
        issues.append("titulos_genericos")
    if price_ratio < 0.2:
        issues.append("precios_insuficientes")
    if absurd_price_count:
        issues.append("precios_absurdos")
    if image_ratio == 0:
        issues.append("sin_fotos_reales")

    score = 0
    score += min(20, total * 2)
    score += int(url_ratio * 15)
    score += int(title_ratio * 20)
    score += int(price_ratio * 15)
    score += int(image_ratio * 10)
    score += int(address_ratio * 10)
    score += 10 if absurd_price_count == 0 else 0
    accepted = score >= 55 and "too_few_vs_expected" not in " ".join(issues) and url_ratio >= 0.6 and title_ratio >= 0.5
    if absurd_price_count:
        accepted = False

    return {
        "accepted": bool(accepted),
        "score": int(score),
        "total": total,
        "expected_property_count": expected,
        "url_real_ratio": url_ratio,
        "useful_title_ratio": title_ratio,
        "valid_price_ratio": price_ratio,
        "real_images_ratio": image_ratio,
        "address_ratio": address_ratio,
        "generic_title_count": generic_title_count,
        "absurd_price_count": absurd_price_count,
        "issues": issues,
    }


def run_best_strategy(
    inmob: Dict,
    session: requests.Session,
    pw_context,
    allow_playwright_fallback: bool = True,
    allow_network_interception: bool = True,
    item_deadline: Optional[float] = None,
    allow_explicit_strategy_fallback: bool = False,
) -> Tuple[List[Dict], str]:
    """
    Ejecuta la mejor estrategia para una agencia.
    Si ya tiene estrategia_scraping guardada, va directo a ella.
    Si no, prueba en orden hasta encontrar una que funcione.
    """
    estrategia_guardada = inmob.get("estrategia_scraping")
    is_tokko_candidate = (
        str(inmob.get("cms_detectado") or "").lower() == "tokko"
        or estrategia_guardada in {"tokko_api", "tokko_html"}
        or "tokko" in str(inmob.get("web") or "").lower()
        or "tokko" in str(inmob.get("url_listado") or "").lower()
    )
    cms_text = str(inmob.get("cms_detectado") or "").lower()
    is_wordpress_candidate = (
        "wordpress" in cms_text
        or cms_text == "wp"
        or estrategia_guardada == "wordpress_html"
        or "wp-content" in str(inmob.get("web") or "").lower()
    )
    tokko_html_failed = False
    attempts: List[Dict[str, Any]] = []
    inmob.setdefault("_scraper_metadata", {})["extractores_intentados"] = attempts

    def call(strategy_name: str, func: Callable[[], List[Dict]]) -> List[Dict]:
        _check_deadline(item_deadline, "item")
        started = time.time()
        _update_strategy_progress(
            inmob,
            strategy_name,
            status="running",
            elapsed_seconds=0,
            item_remaining_seconds=round(_deadline_remaining_seconds(item_deadline), 2)
            if item_deadline is not None else None,
        )
        try:
            result = _run_strategy_with_deadline(strategy_name, inmob, item_deadline, func)
            attempts.append({
                "extractor": strategy_name,
                "status": "success",
                "propiedades": len(result),
                "tiempo_segundos": round(time.time() - started, 2),
            })
            _update_strategy_progress(
                inmob,
                strategy_name,
                status="success",
                propiedades=len(result),
                elapsed_seconds=round(time.time() - started, 2),
            )
            inmob.setdefault("_scraper_metadata", {})["extractores_intentados"] = attempts
            return result
        except Exception as exc:
            attempts.append({
                "extractor": strategy_name,
                "status": "error",
                "error_type": clasificar_error(exc),
                "error_message": str(exc)[:240],
                "tiempo_segundos": round(time.time() - started, 2),
            })
            _update_strategy_progress(
                inmob,
                strategy_name,
                status="error",
                error_type=clasificar_error(exc),
                error_message=str(exc)[:240],
                elapsed_seconds=round(time.time() - started, 2),
            )
            inmob.setdefault("_scraper_metadata", {})["extractores_intentados"] = attempts
            raise

    def network_available() -> bool:
        if allow_network_interception and pw_context is not None:
            return True
        inmob.setdefault("_scraper_metadata", {})["network_interception_skipped"] = True
        logger.info("  Network Interception omitido por configuracion (--allow-network-interception no activo)")
        return False

    def call_network() -> List[Dict]:
        if not network_available():
            raise RuntimeError("network_intercept omitido por configuracion")
        return call("network_intercept", lambda: strategy_network_intercept(inmob, pw_context, session))

    def execute_selected_strategy(strategy_name: str) -> List[Dict]:
        if strategy_name == "tokko_api":
            return call("tokko_api", lambda: strategy_tokko_api(inmob, session))
        if strategy_name == "tokko_html":
            return call("tokko_html", lambda: strategy_tokko_html(inmob, session))
        if strategy_name == "static_html_tokko_detail":
            return call("static_html_tokko_detail", lambda: strategy_static_html_tokko_detail(inmob, session))
        if strategy_name == "static_html_detail":
            return call("static_html_detail", lambda: strategy_static_html_detail(inmob, session))
        if strategy_name == "static_html":
            return call("static_html", lambda: strategy_static_html(inmob, session))
        if strategy_name == "custom_listing_detail":
            return call("custom_listing_detail", lambda: strategy_custom_listing_detail(inmob, session))
        if strategy_name == "wordpress_sitemap_detail":
            return call("wordpress_sitemap_detail", lambda: strategy_wordpress_sitemap_detail(inmob, session))
        if strategy_name == "wordpress_essential_real_estate_detail":
            return call(
                "wordpress_essential_real_estate_detail",
                lambda: strategy_wordpress_essential_real_estate_detail(inmob, session),
            )
        if strategy_name == "wordpress_estatik_detail":
            return call("wordpress_estatik_detail", lambda: strategy_wordpress_estatik_detail(inmob, session))
        if strategy_name == "wordpress_realhomes_detail":
            return call("wordpress_realhomes_detail", lambda: strategy_wordpress_realhomes_detail(inmob, session))
        if strategy_name == "wordpress_generic_detail":
            return call("wordpress_generic_detail", lambda: strategy_wordpress_generic_detail(inmob, session))
        if strategy_name == "wordpress_html":
            return call("wordpress_html", lambda: strategy_wordpress_html(inmob, session))
        if strategy_name == "json_ld":
            return call("json_ld", lambda: strategy_json_ld(inmob, session))
        if strategy_name == "sitemap":
            return call("sitemap", lambda: strategy_sitemap(inmob, session))
        if strategy_name == "network_interception":
            return call_network()
        if strategy_name == "playwright_html":
            if not allow_playwright_fallback or pw_context is None:
                inmob.setdefault("_scraper_metadata", {})["playwright_fallback_skipped"] = True
                raise RuntimeError("requires_playwright: playwright_html omitido por configuracion")
            return call("playwright_html", lambda: strategy_html_playwright(inmob, pw_context))
        raise RuntimeError(f"unsupported_cms: estrategia no implementada {strategy_name}")

    diagnostic = diagnose_inmob(
        inmob,
        session,
        pw_context=pw_context if allow_playwright_fallback else None,
        allow_playwright=allow_playwright_fallback,
        allow_network_interception=allow_network_interception,
    )
    strategy_plan = select_best_scraping_strategy(
        diagnostic,
        history={
            "best_scraping_strategy": inmob.get("best_scraping_strategy"),
            "last_successful_strategy": inmob.get("last_successful_strategy"),
        },
    )
    supported_explicit_strategies = {
        "tokko_api",
        "tokko_html",
        "static_html_tokko_detail",
        "static_html_detail",
        "static_html",
        "custom_listing_detail",
        "wordpress_sitemap_detail",
        "wordpress_essential_real_estate_detail",
        "wordpress_estatik_detail",
        "wordpress_realhomes_detail",
        "wordpress_generic_detail",
        "wordpress_html",
        "json_ld",
        "sitemap",
        "network_interception",
        "playwright_html",
    }
    if (
        allow_explicit_strategy_fallback
        and not strategy_plan.get("primary_strategy")
        and estrategia_guardada in supported_explicit_strategies
    ):
        explicit_fallbacks = {
            "tokko_html": ["static_html_tokko_detail", "static_html_detail", "json_ld", "sitemap"],
            "wordpress_html": ["wordpress_generic_detail", "static_html_detail", "sitemap"],
            "static_html": ["static_html_detail", "json_ld"],
        }
        strategy_plan = {
            "primary_strategy": estrategia_guardada,
            "fallback_strategies": explicit_fallbacks.get(str(estrategia_guardada), []),
            "reason": "test-url con CMS/estrategia explicita tras diagnostico parcial",
            "expected_property_count": _diagnostic_expected_property_count(diagnostic),
            "confidence": "low",
            "requires_playwright": estrategia_guardada == "playwright_html",
            "requires_network_interception": estrategia_guardada == "network_interception",
            "should_save_strategy_for_future": False,
            "classification": diagnostic.get("classification"),
            "discarded_extractors": diagnostic.get("extractores_posibles") or [],
        }
    metadata = inmob.setdefault("_scraper_metadata", {})
    metadata.update({
        "diagnostico_inicial": diagnostic,
        "strategy_plan": strategy_plan,
        "plugin_detectado": diagnostic.get("wordpress_plugin_detectado"),
        "estrategia_elegida": strategy_plan.get("primary_strategy"),
        "primary_strategy": strategy_plan.get("primary_strategy"),
        "motivo_eleccion_estrategia": strategy_plan.get("reason"),
        "expected_property_count": strategy_plan.get("expected_property_count"),
        "property_links_count": diagnostic.get("property_links_count"),
        "custom_listing_urls_detectadas": diagnostic.get("custom_listing_urls_detectadas"),
        "custom_listing_urls_count": diagnostic.get("custom_listing_urls_count"),
        "cards_posibles": diagnostic.get("cards_posibles"),
        "urls_validas_detectadas": diagnostic.get("urls_validas_detectadas"),
        "extractores_descartados": strategy_plan.get("discarded_extractors", []),
        "extractores_ejecutados": attempts,
    })

    primary_strategy = strategy_plan.get("primary_strategy")
    if not primary_strategy:
        classification = strategy_plan.get("classification") or diagnostic.get("classification") or "no_property_links"
        raise RuntimeError(f"{classification}: sin estrategia scrapeable segun diagnostico")

    logger.info("  Diagnostico: %s", diagnostic.get("classification"))
    logger.info("  Estrategia elegida: %s (%s)", primary_strategy, strategy_plan.get("reason"))

    candidate_strategies = [primary_strategy] + list(strategy_plan.get("fallback_strategies") or [])
    quality_results: List[Dict[str, Any]] = []
    last_error: Optional[BaseException] = None
    skipped_reasons: List[str] = []
    for index, strategy_name in enumerate(candidate_strategies):
        if strategy_name == "network_interception" and not allow_network_interception:
            skipped_reasons.append("requires_network_interception")
            attempts.append({
                "extractor": strategy_name,
                "status": "skipped",
                "reason": "allow_network_interception_false",
            })
            continue
        if strategy_name == "playwright_html" and (not allow_playwright_fallback or pw_context is None):
            skipped_reasons.append("requires_playwright")
            attempts.append({
                "extractor": strategy_name,
                "status": "skipped",
                "reason": "allow_playwright_false",
            })
            continue

        try:
            logger.info("  -> Ejecutando estrategia %s", strategy_name)
            props = execute_selected_strategy(strategy_name)
            strategy_runtime_metadata = dict(inmob.get("_scraper_metadata") or {})
            metadata.update(strategy_runtime_metadata)
            metadata["extractores_ejecutados"] = attempts
            inmob["_scraper_metadata"] = metadata
            props = _sanitize_scraped_props_for_quality(props, metadata)
            quality = evaluate_scrape_quality(props, strategy_plan, diagnostic)
            quality["strategy"] = strategy_name
            quality_results.append(quality)
            metadata["resultado_calidad"] = quality
            metadata["resultados_calidad_por_estrategia"] = quality_results
            if quality.get("accepted"):
                metadata["fallback_usado"] = index > 0
                metadata["estrategia_final"] = strategy_name
                metadata["should_save_strategy_for_future"] = bool(strategy_plan.get("should_save_strategy_for_future"))
                logger.info("  Calidad aceptada: score=%s props=%s", quality.get("score"), len(props))
                return props, strategy_name
            logger.warning(
                "  Calidad insuficiente en %s: score=%s issues=%s",
                strategy_name,
                quality.get("score"),
                quality.get("issues"),
            )
        except Exception as exc:
            strategy_runtime_metadata = dict(inmob.get("_scraper_metadata") or {})
            metadata.update(strategy_runtime_metadata)
            metadata["extractores_ejecutados"] = attempts
            inmob["_scraper_metadata"] = metadata
            last_error = exc
            logger.warning("  Estrategia %s fallo: %s", strategy_name, str(exc)[:240])
            continue

    metadata["resultado_calidad"] = quality_results[-1] if quality_results else None
    metadata["resultados_calidad_por_estrategia"] = quality_results
    if not quality_results and "requires_playwright" in skipped_reasons:
        raise RuntimeError("requires_playwright: sitio requiere renderizado JS y --allow-playwright no esta habilitado")
    if not quality_results and "requires_network_interception" in skipped_reasons:
        raise RuntimeError("requires_network_interception: sitio requiere inspeccion de red y --allow-network-interception no esta habilitado")
    if last_error and not quality_results:
        raise last_error
    issues = (quality_results[-1].get("issues") if quality_results else []) or []
    if issues:
        metadata["rejected_reason"] = issues
    raise RuntimeError(f"parsing_failed: ninguna estrategia alcanzo calidad minima; issues={issues}")

    # --- Ir directo a la estrategia guardada (con fallback automático) ---
    if estrategia_guardada == "tokko_api" and inmob.get("tokko_api_key"):
        logger.info("  → Tokko API (guardada)")
        try:
            props = call("tokko_api", lambda: strategy_tokko_api(inmob, session))
            return props, "tokko_api"
        except Exception as e:
            logger.warning("  Tokko falló: %s — probando Network Intercept", e)
            if network_available():
                try:
                    props = call_network()
                    return props, "network_intercept"
                except Exception:
                    pass

    if estrategia_guardada == "json_ld":
        logger.info("  → JSON-LD (guardada)")
        try:
            props = call("json_ld", lambda: strategy_json_ld(inmob, session))
            return props, "json_ld"
        except Exception as e:
            logger.warning("  JSON-LD falló: %s — probando Sitemap", e)
            try:
                props = call("sitemap", lambda: strategy_sitemap(inmob, session))
                return props, "sitemap"
            except Exception:
                pass

    if estrategia_guardada == "sitemap":
        logger.info("  → Sitemap (guardada)")
        try:
            props = call("sitemap", lambda: strategy_sitemap(inmob, session))
            return props, "sitemap"
        except Exception as e:
            logger.warning("  Sitemap falló: %s — probando JSON-LD", e)
            try:
                props = call("json_ld", lambda: strategy_json_ld(inmob, session))
                return props, "json_ld"
            except Exception:
                pass

    if estrategia_guardada == "html" and not allow_playwright_fallback:
        logger.info("  HTML Playwright omitido por configuracion (--allow-playwright-fallback no activo)")
        inmob.setdefault("_scraper_metadata", {})["playwright_fallback_skipped"] = True
        estrategia_guardada = None

    if estrategia_guardada == "html":
        logger.info("  → HTML Playwright (guardada)")
        try:
            props = call("html_scraper", lambda: strategy_html_playwright(inmob, pw_context))
            return props, "html_scraper"
        except Exception as e:
            logger.warning("  HTML falló: %s — probando Network Intercept", e)
            if network_available():
                try:
                    props = call_network()
                    return props, "network_intercept"
                except Exception:
                    pass

    if estrategia_guardada == "tokko_html":
        logger.info("  -> Tokko HTML (guardada)")
        try:
            props = call("tokko_html", lambda: strategy_tokko_html(inmob, session))
            return props, "tokko_html"
        except Exception as e:
            tokko_html_failed = True
            logger.warning("  Tokko HTML fallo: %s", e)

    if estrategia_guardada == "wordpress_html":
        logger.info("  -> WordPress HTML (guardada)")
        try:
            props = call("wordpress_html", lambda: strategy_wordpress_html(inmob, session))
            return props, "wordpress_html"
        except Exception as e:
            logger.warning("  WordPress HTML fallo: %s", e)

    if estrategia_guardada == "static_html":
        logger.info("  -> Static HTML (guardada)")
        try:
            props = call("static_html", lambda: strategy_static_html(inmob, session))
            return props, "static_html"
        except Exception as e:
            logger.warning("  Static HTML fallo: %s", e)

    if estrategia_guardada == "sin_estrategia":
        # Dar una última oportunidad con Network Intercept
        if network_available():
            try:
                props = call_network()
                return props, "network_intercept"
            except Exception:
                pass
        raise RuntimeError("sin_propiedades: sitio sin estrategia viable confirmada")

    # --- Fallback completo: probar todas en orden (primera vez o re-detección) ---

    # 1. Tokko API key conocida
    if inmob.get("tokko_api_key"):
        try:
            logger.info("  → Tokko API")
            props = call("tokko_api", lambda: strategy_tokko_api(inmob, session))
            return props, "tokko_api"
        except Exception as e:
            logger.warning("  Tokko falló: %s", e)

    # 2. Network Interception (detecta Tokko key on-the-fly)
    try:
        logger.info("  → Network Interception")
        props = call_network()
        return props, "network_intercept"
    except Exception as e:
        logger.warning("  Network Intercept falló: %s", e)

    if is_tokko_candidate and not tokko_html_failed:
        try:
            logger.info("  -> Tokko HTML")
            props = call("tokko_html", lambda: strategy_tokko_html(inmob, session))
            return props, "tokko_html"
        except Exception as e:
            tokko_html_failed = True
            logger.warning("  Tokko HTML fallo: %s", e)

    if is_wordpress_candidate:
        try:
            logger.info("  -> WordPress HTML")
            props = call("wordpress_html", lambda: strategy_wordpress_html(inmob, session))
            return props, "wordpress_html"
        except Exception as e:
            logger.warning("  WordPress HTML fallo: %s", e)

    try:
        logger.info("  -> Static HTML")
        props = call("static_html", lambda: strategy_static_html(inmob, session))
        return props, "static_html"
    except Exception as e:
        logger.warning("  Static HTML fallo: %s", e)

    # 3. JSON-LD
    try:
        logger.info("  → JSON-LD")
        props = call("json_ld", lambda: strategy_json_ld(inmob, session))
        return props, "json_ld"
    except Exception as e:
        logger.warning("  JSON-LD falló: %s", e)

    # 4. Sitemap
    try:
        logger.info("  → Sitemap")
        props = call("sitemap", lambda: strategy_sitemap(inmob, session))
        return props, "sitemap"
    except Exception as e:
        logger.warning("  Sitemap falló: %s", e)

    # 5. HTML Playwright (último recurso)
    logger.info("  → HTML Playwright (último recurso)")
    if not allow_playwright_fallback:
        inmob.setdefault("_scraper_metadata", {})["playwright_fallback_skipped"] = True
        diagnostic = diagnose_inmob(
            inmob,
            session,
            pw_context=None,
            allow_playwright=False,
            allow_network_interception=allow_network_interception,
        )
        diagnostic["extractores_intentados"] = attempts
        inmob.setdefault("_scraper_metadata", {})["diagnostico_universal"] = diagnostic
        classification = diagnostic.get("classification") or "requires_playwright"
        raise RuntimeError(f"{classification}: html_playwright omitido por configuracion")
    props = call("html_scraper", lambda: strategy_html_playwright(inmob, pw_context))
    return props, "html_scraper"


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

def _make_detect_session() -> requests.Session:
    """Sesión HTTP para detección: sin reintentos en DNS/conexión, falla rápido."""
    s = requests.Session()
    s.trust_env = False
    retry = Retry(
        total=0,              # sin reintentos — falla rápido
        connect=0,
        read=1,               # 1 reintento solo para read timeouts
        status_forcelist=[429, 500, 502, 503],
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


def _detect_http_only(inmob: Dict, session: requests.Session) -> Dict:
    """
    Detección rápida SIN browser: JSON-LD y Sitemap vía HTTP.
    Retorna el resultado si encuentra algo, o {"estrategia_scraping": None} si no.
    """
    url = inmob.get("url_listado") or inmob.get("web", "")
    if not url:
        return {"estrategia_scraping": "sin_url"}

    # Tokko ya conocida
    if inmob.get("tokko_api_key"):
        return {"estrategia_scraping": "tokko_api"}

    # JSON-LD
    _DNS_KEYWORDS = (
        "nameresolutionerror", "name or service not known",
        "getaddrinfo failed", "nodename nor servname",
        "no address associated", "[-2]", "[-3]", "11001",
    )

    def _es_dns_error(exc: Exception) -> bool:
        msg = str(exc).lower()
        return any(kw in msg for kw in _DNS_KEYWORDS)

    r_inicial = None
    try:
        r_inicial = _http_get(url, session, timeout=12)
        soup = BeautifulSoup(r_inicial.text, "lxml")
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(tag.string or "")
                items = data if isinstance(data, list) else [data]
                for item in items:
                    t = item.get("@type", "")
                    if isinstance(t, list): t = t[0]
                    if t in _JSONLD_TYPES:
                        return {"estrategia_scraping": "json_ld"}
            except Exception:
                pass
    except requests.exceptions.ConnectionError as e:
        if _es_dns_error(e):
            return {"estrategia_scraping": "dominio_caido"}
        # SSL, connection refused, etc. → dejar que el browser lo intente
        return {"estrategia_scraping": None}
    except Exception:
        # Timeout u otro error → no sabemos si está caído, browser decide
        return {"estrategia_scraping": None}

    # Sitemap
    base_url = url if r_inicial is None else r_inicial.url  # url final tras redirects
    for path in ["/sitemap.xml", "/sitemap_index.xml", "/sitemap-property.xml",
                 "/sitemap-propiedades.xml", "/sitemap-listings.xml"]:
        try:
            r = _http_get(urljoin(base_url, path), session, timeout=6)
            if r.status_code == 200 and PROPERTY_URL_PATTERNS.search(r.text):
                return {"estrategia_scraping": "sitemap"}
        except Exception:
            pass

    # Sin resultado HTTP → necesita browser
    return {"estrategia_scraping": None}


def detect_worker_fn(
    agency_queue: queue.Queue,
    db: "SupabasePropiedades",
    total: int,
    counter: list,
    lock: threading.Lock,
    stats: dict,
) -> None:
    """Worker HTTP-only para detección. Sin browser (evita problemas de threading con Playwright)."""
    session = _make_detect_session()

    while True:
        try:
            inmob = agency_queue.get_nowait()
        except queue.Empty:
            break

        with lock:
            counter[0] += 1
            idx = counter[0]

        nombre = inmob.get("nombre", inmob.get("web", "?"))
        ya_tiene = inmob.get("estrategia_scraping")

        if ya_tiene and ya_tiene not in ("sin_estrategia", "sin_url", None):
            with lock:
                stats[ya_tiene] = stats.get(ya_tiene, 0) + 1
            if idx % 100 == 0:
                logger.info("[%d/%d] progreso...", idx, total)
            agency_queue.task_done()
            continue

        try:
            resultado = _detect_http_only(inmob, session)
            estrategia = resultado.get("estrategia_scraping") or "necesita_browser"
            if resultado.get("estrategia_scraping"):
                _save_estrategia(db, inmob["id"], resultado)
            logger.info("[%d/%d] %s → %s", idx, total, nombre[:40], estrategia)
            with lock:
                stats[estrategia] = stats.get(estrategia, 0) + 1
        except Exception as exc:
            logger.debug("detect error %s: %s", nombre, exc)
            with lock:
                stats["error"] = stats.get("error", 0) + 1
        finally:
            agency_queue.task_done()


def worker_fn(
    job_queue: queue.Queue,
    db: SupabasePropiedades,
    total: int,
    counter: list,
    lock: threading.Lock,
) -> None:
    session = SupabasePropiedades._make_session()

    with sync_playwright() as pw:
        browser, pw_context = _make_playwright_context(pw)
        try:
            while True:
                try:
                    job, inmob = job_queue.get_nowait()
                except queue.Empty:
                    break

                with lock:
                    counter[0] += 1
                    idx = counter[0]

                nombre = inmob.get("nombre", inmob.get("web", "?"))
                logger.info("[%d/%d] %s — iniciando", idx, total, nombre)

                # Marcar como corriendo
                db.update_job(job["id"], {
                    "estado": "corriendo",
                    "iniciado_en": datetime.now(timezone.utc).isoformat(),
                    "intentos": job.get("intentos", 0) + 1,
                })

                try:
                    props, estrategia = run_best_strategy(inmob, session, pw_context)
                    total_ext, nuevas = db.save_propiedades(props)
                    props = [sanitize_property_location(prop, None) for prop in props]

                    # Geocodificar propiedades sin coordenadas
                    geo_count = 0
                    for prop in props:
                        if (prop.get("latitud") is None and
                                (prop.get("direccion") or prop.get("ciudad"))):
                            lat, lon = geocodificar_direccion(
                                prop.get("direccion", ""),
                                prop.get("ciudad", ""),
                                prop.get("provincia", ""),
                            )
                            if lat and lon:
                                validation = validate_property_coordinate_context({
                                    **prop,
                                    "latitud": lat,
                                    "longitud": lon,
                                })
                                if not validation.get("valid"):
                                    logger.info(
                                        "  Geocoding omitido por outlier | ciudad=%s provincia=%s lat=%s lon=%s",
                                        prop.get("ciudad"),
                                        prop.get("provincia"),
                                        lat,
                                        lon,
                                    )
                                    continue
                                # Actualizar en BD por hash
                                try:
                                    db.session.patch(
                                        f"{SUPABASE_URL}/rest/v1/propiedades"
                                        f"?hash_dedup=eq.{prop['hash_dedup']}",
                                        headers=db._headers_minimal,
                                        json={"latitud": lat, "longitud": lon},
                                        timeout=10,
                                    )
                                    geo_count += 1
                                except Exception:
                                    pass

                    # Marcar inactivas las propiedades que ya no están en el listado
                    active_hashes = {p["hash_dedup"] for p in props}
                    inactivos = db.mark_inactivos(inmob["id"], active_hashes)

                    logger.info(
                        "[%d/%d] %s → %s: %d extraídas, %d nuevas, %d geocodif., %d inactivas",
                        idx, total, nombre, estrategia, total_ext, nuevas, geo_count, inactivos,
                    )
                    db.update_job(job["id"], {
                        "estado": "completado",
                        "estrategia": estrategia,
                        "propiedades_extraidas": total_ext,
                        "propiedades_nuevas": nuevas,
                        "completado_en": datetime.now(timezone.utc).isoformat(),
                        "ultimo_error_tipo": None,
                        "ultimo_error_msg": None,
                    })

                except Exception as exc:
                    tipo_error = clasificar_error(exc)
                    intentos = job.get("intentos", 0) + 1
                    max_intentos = job.get("max_intentos", 4)
                    proximo = None

                    if intentos < max_intentos:
                        delay = min(2 ** intentos * 60, 3600)  # backoff exponencial, max 1h
                        proximo = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
                        nuevo_estado = "fallido"
                    else:
                        nuevo_estado = "fallido"

                    logger.error(
                        "[%d/%d] %s → ERROR (%s): %s",
                        idx, total, nombre, tipo_error, str(exc)[:200],
                    )
                    db.update_job(job["id"], {
                        "estado": nuevo_estado,
                        "ultimo_error_tipo": tipo_error,
                        "ultimo_error_msg": str(exc)[:500],
                        "intentos": intentos,
                        "proximo_intento": proximo,
                        "completado_en": datetime.now(timezone.utc).isoformat(),
                    })

                finally:
                    job_queue.task_done()
        finally:
            _close_playwright_safely(pw_context, "legacy playwright context")
            _close_playwright_safely(browser, "legacy playwright browser")


# ---------------------------------------------------------------------------
# Supabase scraping control runner
# ---------------------------------------------------------------------------

class ScrapingControlError(RuntimeError):
    def __init__(
        self,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
        final_url: Optional[str] = None,
        http_status: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.metadata = metadata or {}
        self.final_url = final_url
        self.http_status = http_status


def _normalize_queue_url(url: Optional[str]) -> str:
    if not url:
        return ""
    clean = str(url).strip()
    if not clean:
        return ""
    if not re.match(r"^https?://", clean, re.IGNORECASE):
        clean = f"https://{clean.lstrip('/')}"
    return clean


def _queue_candidate_urls(item: Dict) -> List[str]:
    urls: List[str] = []
    for key in ("url_listado", "web"):
        clean = _normalize_queue_url(item.get(key))
        if clean and clean not in urls:
            urls.append(clean)
    return urls


def _item_timeout_seconds(item: Dict, allow_playwright: bool = False, strategy_hint: Optional[str] = None) -> int:
    if allow_playwright:
        return PLAYWRIGHT_ITEM_TIMEOUT_SECONDS
    hint = " ".join(
        str(value or "").lower()
        for value in (
            strategy_hint,
            item.get("cms_detectado"),
            item.get("url_listado"),
            item.get("web"),
        )
    )
    if any(marker in hint for marker in ("custom_listing", "/listing", "listing?", "sitemap")):
        return CUSTOM_OR_SITEMAP_ITEM_TIMEOUT_SECONDS
    if any(marker in hint for marker in ("wordpress", "tokko", "static_html")):
        return CONTROL_ITEM_TIMEOUT_SECONDS
    return CONTROL_ITEM_TIMEOUT_SECONDS


def _strategy_from_cms(cms_detectado: Optional[str]) -> Optional[str]:
    cms = (cms_detectado or "").strip().lower()
    if cms in {"tokko_api"}:
        return "tokko_api"
    if cms in {"tokko", "tokko broker"}:
        return "tokko_html"
    if "wordpress" in cms or cms in {"wp", "wordpress_html"}:
        return "wordpress_html"
    if cms in {"json_ld", "schema", "schema_org"}:
        return "json_ld"
    if cms == "sitemap":
        return "sitemap"
    if cms in {"html", "html_scraper"}:
        return "html"
    return None


def _queue_item_to_inmob(
    item: Dict,
    url_usada: str,
    canonical_resolution: Optional[Dict[str, Any]] = None,
) -> Dict:
    estrategia = _strategy_from_cms(item.get("cms_detectado"))
    main_row = (canonical_resolution or {}).get("main_row") or {}
    canonical_id = (canonical_resolution or {}).get("canonical_main_id") or item.get("inmobiliaria_id")
    inmob = {
        "id": canonical_id,
        "nombre": item.get("inmobiliaria_nombre") or item.get("nombre") or "Sin nombre",
        "ciudad": item.get("ciudad"),
        "provincia": item.get("provincia"),
        "web": _normalize_queue_url(item.get("web")) or url_usada,
        "url_listado": url_usada,
        "cms_detectado": item.get("cms_detectado"),
        "prioridad_scraping_score": item.get("prioridad_scraping_score"),
        "total_propiedades_normalizado": item.get("total_propiedades_normalizado"),
        "_run_item_inmobiliaria_id": item.get("inmobiliaria_id"),
        "_canonical_inmobiliaria_main_id": canonical_id,
        "_canonical_inmobiliaria_nombre": _agency_row_name(main_row),
        "_canonical_inmobiliaria_web": main_row.get("web"),
    }
    if estrategia:
        inmob["estrategia_scraping"] = estrategia
    return inmob


def _extract_http_status(exc: Optional[BaseException]) -> Optional[int]:
    if exc is None:
        return None
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    match = re.search(r"\b(?:HTTP|status(?: code)?)\s*:?\s*(\d{3})\b", str(exc), re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _queue_metadata(
    item: Dict,
    started_at: float,
    url_usada: Optional[str],
    estrategia_usada: Optional[str],
    cantidad_paginas: int,
    errores_relevantes: Optional[List[str]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {
        "cms_detectado": item.get("cms_detectado"),
        "url_usada": url_usada,
        "tiempo_estimado": round(time.time() - started_at, 2),
        "estrategia_usada": estrategia_usada,
        "cantidad_paginas": cantidad_paginas,
    }
    if errores_relevantes:
        metadata["errores_relevantes"] = errores_relevantes[-5:]
    if extra:
        metadata.update(extra)
    return metadata


def _item_timeout_control_error(
    item: Dict,
    started_at: float,
    timeout_seconds: int,
    url_usada: Optional[str],
    estrategia_actual: Optional[str],
    fase_actual: str,
    extra: Optional[Dict[str, Any]] = None,
) -> ScrapingControlError:
    elapsed = round(time.time() - started_at, 2)
    metadata = _queue_metadata(
        item=item,
        started_at=started_at,
        url_usada=url_usada,
        estrategia_usada=estrategia_actual or "item_timeout",
        cantidad_paginas=0,
        errores_relevantes=["Tiempo mÃ¡ximo por inmobiliaria excedido"],
        extra={
            "timeout_seconds": timeout_seconds,
            "elapsed_seconds": elapsed,
            "estrategia_actual": estrategia_actual,
            "fase_actual": fase_actual,
            **(extra or {}),
        },
    )
    return ScrapingControlError(
        "item_timeout: Tiempo mÃ¡ximo por inmobiliaria excedido",
        metadata=metadata,
        final_url=url_usada,
        http_status=None,
    )


def _scrape_queue_item(
    item: Dict,
    session: requests.Session,
    pw_context,
    started_at: float,
    canonical_resolution: Optional[Dict[str, Any]] = None,
    allow_playwright_fallback: bool = False,
    allow_network_interception: bool = False,
) -> Tuple[List[Dict], str, str, List[str], Dict[str, Any]]:
    urls = _queue_candidate_urls(item)
    if not urls:
        metadata = _queue_metadata(
            item=item,
            started_at=started_at,
            url_usada=None,
            estrategia_usada="sin_url",
            cantidad_paginas=0,
            errores_relevantes=["Item sin url_listado ni web"],
        )
        raise ScrapingControlError("Item sin url_listado ni web", metadata=metadata)

    errores_relevantes: List[str] = []
    last_exc: Optional[BaseException] = None
    last_url: Optional[str] = None
    timeout_seconds = _item_timeout_seconds(item, allow_playwright_fallback or allow_network_interception)
    item_deadline = started_at + timeout_seconds

    for idx, url_usada in enumerate(urls, start=1):
        try:
            _check_deadline(item_deadline, "item")
        except ItemTimeoutError as exc:
            raise _item_timeout_control_error(
                item,
                started_at,
                timeout_seconds,
                last_url,
                "sin_estrategia",
                "antes_de_probar_url",
                {"errores_relevantes": errores_relevantes},
            ) from exc
        last_url = url_usada
        inmob = _queue_item_to_inmob(item, url_usada, canonical_resolution=canonical_resolution)
        inmob["_item_timeout_seconds"] = timeout_seconds
        logger.info("URL usada: %s", url_usada)
        logger.info("CMS detectado: %s", item.get("cms_detectado") or "sin dato")

        try:
            props, estrategia = run_best_strategy(
                inmob,
                session,
                pw_context,
                allow_playwright_fallback=allow_playwright_fallback,
                allow_network_interception=allow_network_interception,
                item_deadline=item_deadline,
            )
            strategy_meta = dict(inmob.get("_scraper_metadata") or {})
            if strategy_meta.get("errores_relevantes"):
                errores_relevantes.extend(strategy_meta["errores_relevantes"])
            if props or idx == len(urls):
                return props, estrategia, url_usada, errores_relevantes, strategy_meta
            errores_relevantes.append(f"{url_usada}: sin propiedades detectadas; probando fallback")
            logger.warning("Sin propiedades en URL principal; probando fallback si existe")
        except Exception as exc:
            if isinstance(exc, ItemTimeoutError) or clasificar_error(exc) == "item_timeout":
                strategy_meta = dict(inmob.get("_scraper_metadata") or {})
                raise _item_timeout_control_error(
                    item,
                    started_at,
                    timeout_seconds,
                    url_usada,
                    strategy_meta.get("estrategia_final") or strategy_meta.get("estrategia_elegida") or strategy_meta.get("primary_strategy"),
                    "scraping",
                    strategy_meta,
                ) from exc
            last_exc = exc
            error_msg = f"{url_usada}: {type(exc).__name__}: {str(exc)[:300]}"
            errores_relevantes.append(error_msg)
            logger.warning("Fallo URL %s: %s", url_usada, str(exc)[:250])
            if idx == len(urls):
                metadata = _queue_metadata(
                    item=item,
                    started_at=started_at,
                    url_usada=last_url,
                    estrategia_usada="sin_estrategia",
                    cantidad_paginas=0,
                    errores_relevantes=errores_relevantes,
                    extra=dict(inmob.get("_scraper_metadata") or {}),
                )
                raise ScrapingControlError(
                    str(exc)[:1000],
                    metadata=metadata,
                    final_url=last_url,
                    http_status=_extract_http_status(last_exc),
                ) from exc

    metadata = _queue_metadata(
        item=item,
        started_at=started_at,
        url_usada=last_url,
        estrategia_usada="sin_estrategia",
        cantidad_paginas=0,
        errores_relevantes=errores_relevantes,
    )
    raise ScrapingControlError(
        "No se pudo scrapear el item",
        metadata=metadata,
        final_url=last_url,
        http_status=_extract_http_status(last_exc),
    )


def _metadata_indicates_partial_extraction(strategy_meta: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(strategy_meta, dict):
        return False
    error_text = " | ".join(str(value) for value in strategy_meta.get("errores_relevantes") or [])
    if re.search(r"timeout|presupuesto|detenido|pendientes sin consultar", error_text, re.I):
        return True
    progress = strategy_meta.get("strategy_progress")
    if isinstance(progress, dict):
        for data in progress.values():
            if not isinstance(data, dict):
                continue
            for key in ("detail_urls_remaining", "listing_urls_remaining"):
                try:
                    if int(data.get(key) or 0) > 0 and int(data.get("propiedades_detectadas") or 0) > 0:
                        return True
                except (TypeError, ValueError):
                    continue
    return False


def _save_queue_properties(
    db: SupabasePropiedades,
    item: Dict,
    props: List[Dict],
    item_deadline: Optional[float] = None,
    canonical_resolution: Optional[Dict[str, Any]] = None,
    strategy_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    _check_deadline(item_deadline, "item")
    agency_resolution = canonical_resolution or db.resolve_canonical_inmobiliaria_id(item)
    main_id = agency_resolution["canonical_main_id"]
    scraping_row = agency_resolution.get("scraping_row") or {}
    main_row = agency_resolution.get("main_row") or {}
    scraping_id = scraping_row.get("id") or main_row.get("scraping_id_origen")
    method = agency_resolution["metodo_resolucion"]
    logger.info(
        "Resolucion inmobiliaria canonica: run_item_id=%s run_item_inmobiliaria_id=%s main_id=%s scraping_id=%s metodo=%s",
        item.get("scraping_run_item_id") or item.get("id"),
        item.get("inmobiliaria_id"),
        main_id, scraping_id, method,
    )

    for prop in props:
        prop["inmobiliaria_id"] = main_id
        prop["_agency_location_context"] = {
            "id": main_id,
            "nombre": _agency_row_name(main_row),
            "ciudad": main_row.get("ciudad"),
            "provincia": main_row.get("provincia"),
            "pais": main_row.get("pais") or "Argentina",
        }
        prop["hash_dedup"] = hash_propiedad(main_id, prop.get("id_externo"), prop.get("url"))

    props_with_images, props_without_images = _count_real_image_props(props)
    image_urls_detected = 0
    for prop in props:
        raw_images = prop.get("imagenes") or []
        if isinstance(raw_images, str):
            raw_images = [raw_images]
        if isinstance(raw_images, list):
            image_urls_detected += len(clean_property_images(raw_images))

    try:
        _check_deadline(item_deadline, "item")
        total_ext, nuevas = db.save_propiedades(props)
    except SavePropertiesError as exc:
        save_protection = dict(getattr(db, "last_save_protection_stats", {}) or {})
        save_result = dict(getattr(db, "last_save_result", {}) or {})
        save_protection["save_result"] = save_result
        save_protection["save_errors"] = exc.errors
        save_protection["image_save_diagnostics"] = {
            "imagenes_detectadas": props_with_images,
            "propiedades_sin_imagenes_detectadas": props_without_images,
            "imagenes_urls_detectadas": image_urls_detected,
            "imagenes_guardadas": int(save_protection.get("imagenes_guardadas_payload") or 0),
            "imagenes_descartadas": int(save_protection.get("imagenes_descartadas_sanitizer") or 0),
            "motivo_descartes": save_protection.get("imagenes_descartadas_sanitizer_por_motivo", {}),
            "imagenes_conservadas_existentes": int(save_protection.get("imagenes_conservadas") or 0),
        }
        db.last_save_protection_stats = save_protection
        raise SavePropertiesError(str(exc), errors=exc.errors) from exc

    save_protection = dict(getattr(db, "last_save_protection_stats", {}) or {})
    save_result = dict(getattr(db, "last_save_result", {}) or {})
    save_protection["save_result"] = save_result
    save_protection["image_save_diagnostics"] = {
        "imagenes_detectadas": props_with_images,
        "propiedades_sin_imagenes_detectadas": props_without_images,
        "imagenes_urls_detectadas": image_urls_detected,
        "imagenes_guardadas": int(save_protection.get("imagenes_guardadas_payload") or 0),
        "imagenes_descartadas": int(save_protection.get("imagenes_descartadas_sanitizer") or 0),
        "motivo_descartes": save_protection.get("imagenes_descartadas_sanitizer_por_motivo", {}),
        "imagenes_conservadas_existentes": int(save_protection.get("imagenes_conservadas") or 0),
    }
    for prop in props:
        sanitize_property_location(prop, None)
    propiedades_error = int(save_result.get("failed") or max(len(props) - total_ext, 0))

    geo_count = 0
    geocoding_skipped_by_budget = 0
    for prop in props:
        if item_deadline is not None and _deadline_remaining_seconds(item_deadline) <= 6:
            geocoding_skipped_by_budget += 1
            logger.info("  Geocoding omitido por presupuesto de item agotado")
            break
        _check_deadline(item_deadline, "item")
        if prop.get("latitud") is None and (prop.get("direccion") or prop.get("ciudad")):
            lat, lon = geocodificar_direccion(
                prop.get("direccion", ""),
                prop.get("ciudad", ""),
                prop.get("provincia", ""),
            )
            if lat and lon:
                validation = validate_property_coordinate_context({
                    **prop,
                    "latitud": lat,
                    "longitud": lon,
                })
                if not validation.get("valid"):
                    _record_coordinate_outlier(save_protection, {
                        **prop,
                        "latitud": lat,
                        "longitud": lon,
                    }, validation)
                    logger.info(
                        "  Geocoding omitido por outlier | ciudad=%s provincia=%s lat=%s lon=%s hash=%s",
                        prop.get("ciudad"),
                        prop.get("provincia"),
                        lat,
                        lon,
                        prop.get("hash_dedup"),
                    )
                    continue
                try:
                    db.session.patch(
                        f"{SUPABASE_URL}/rest/v1/propiedades"
                        f"?hash_dedup=eq.{prop['hash_dedup']}",
                        headers=db._headers_minimal,
                        json={"latitud": lat, "longitud": lon},
                        timeout=10,
                    )
                    geo_count += 1
                except Exception:
                    pass

    inactivos = 0
    inactivos_omitidos_por_timeout = False
    inactivos_omitidos_por_extraccion_parcial = _metadata_indicates_partial_extraction(strategy_meta)
    if props and main_id:
        if inactivos_omitidos_por_extraccion_parcial:
            logger.info("  Marcado de inactivos omitido: extraccion parcial o detenida por presupuesto")
        elif item_deadline is not None and _deadline_remaining_seconds(item_deadline) <= 4:
            inactivos_omitidos_por_timeout = True
            logger.info("  Marcado de inactivos omitido por presupuesto de item agotado")
        else:
            _check_deadline(item_deadline, "item")
            matched_existing_hashes = set((save_result.get("matched_existing_hashes") or []))
            active_hashes = {p["hash_dedup"] for p in props if p.get("hash_dedup")} | matched_existing_hashes
            inactivos = db.mark_inactivos(int(main_id), active_hashes)

    return {
        "propiedades_detectadas": len(props),
        "propiedades_nuevas": int(save_result.get("inserted") or nuevas),
        "propiedades_actualizadas": int(save_result.get("updated") or 0),
        "propiedades_sin_cambios": int(save_result.get("unchanged") or 0),
        "propiedades_error": propiedades_error,
        "geocodificadas": geo_count,
        "geocoding_omitido_por_timeout": geocoding_skipped_by_budget,
        "propiedades_inactivas_marcadas": inactivos,
        "inactivos_omitidos_por_timeout": inactivos_omitidos_por_timeout,
        "inactivos_omitidos_por_extraccion_parcial": inactivos_omitidos_por_extraccion_parcial,
        "inmobiliaria_main_id": main_id,
        "inmobiliaria_scraping_id": scraping_id,
        "metodo_resolucion_inmobiliaria": method,
        "canonical_resolution": {
            "run_item_inmobiliaria_id": agency_resolution.get("run_item_inmobiliaria_id"),
            "canonical_main_id": agency_resolution.get("canonical_main_id"),
            "source_id_space": agency_resolution.get("source_id_space"),
            "metodo_resolucion": agency_resolution.get("metodo_resolucion"),
            "validation": agency_resolution.get("validation"),
        },
        "proteccion_actualizacion": save_protection,
        "image_save_diagnostics": save_protection.get("image_save_diagnostics", {}),
    }


def _process_scraping_control_item(
    db: SupabasePropiedades,
    item: Dict,
    session: requests.Session,
    pw_context,
    allow_playwright_fallback: bool = False,
    allow_network_interception: bool = False,
) -> Dict[str, Any]:
    started_at = time.time()
    timeout_seconds = _item_timeout_seconds(item, allow_playwright_fallback or allow_network_interception)
    item_deadline = started_at + timeout_seconds
    item_id = item.get("scraping_run_item_id")
    if not item_id:
        raise ScrapingControlError("Item sin scraping_run_item_id")

    db.start_scraping_item(item_id)
    try:
        _check_deadline(item_deadline, "item")
    except ItemTimeoutError as exc:
        raise _item_timeout_control_error(item, started_at, timeout_seconds, None, "start_scraping_item", "inicio") from exc

    canonical_resolution = db.resolve_canonical_inmobiliaria_id(item)
    main_row = canonical_resolution.get("main_row") or {}
    logger.info(
        "Preflight ID | run=%s item=%s run_item_inmobiliaria_id=%s canonical_main_id=%s source_space=%s",
        item.get("scraping_run_id"),
        item_id,
        item.get("inmobiliaria_id"),
        canonical_resolution.get("canonical_main_id"),
        canonical_resolution.get("source_id_space"),
    )
    logger.info(
        "Preflight agencia | item='%s' web='%s' | main='%s' web='%s'",
        item.get("inmobiliaria_nombre"),
        item.get("web") or item.get("url_listado"),
        _agency_row_name(main_row),
        main_row.get("web") or main_row.get("url_listado"),
    )

    try:
        props, estrategia, url_usada, errores_relevantes, strategy_meta = _scrape_queue_item(
            item=item,
            session=session,
            pw_context=pw_context,
            started_at=started_at,
            canonical_resolution=canonical_resolution,
            allow_playwright_fallback=allow_playwright_fallback,
            allow_network_interception=allow_network_interception,
        )
        _check_deadline(item_deadline, "item")
    except ItemTimeoutError as exc:
        raise _item_timeout_control_error(item, started_at, timeout_seconds, None, "sin_estrategia", "scraping") from exc

    final_url = _effective_final_url(url_usada, strategy_meta)
    final_validation = _final_url_domain_validation(final_url, item, canonical_resolution)
    if not final_validation.get("valid"):
        metadata = _queue_metadata(
            item=item,
            started_at=started_at,
            url_usada=url_usada,
            estrategia_usada=estrategia,
            cantidad_paginas=int(strategy_meta.get("cantidad_paginas") or (1 if url_usada else 0)),
            errores_relevantes=errores_relevantes + ["Dominio final no coincide con la inmobiliaria del item"],
            extra={
                "diagnostico_inicial": strategy_meta.get("diagnostico_inicial"),
                "strategy_plan": strategy_meta.get("strategy_plan"),
                "canonical_resolution": {
                    "run_item_inmobiliaria_id": canonical_resolution.get("run_item_inmobiliaria_id"),
                    "canonical_main_id": canonical_resolution.get("canonical_main_id"),
                    "source_id_space": canonical_resolution.get("source_id_space"),
                    "metodo_resolucion": canonical_resolution.get("metodo_resolucion"),
                    "validation": canonical_resolution.get("validation"),
                },
                "final_url_validation": final_validation,
                "propiedades_detectadas": len(props),
            },
        )
        raise ScrapingControlError(
            "final_url_domain_mismatch: el dominio final no coincide con la web/url_listado del item",
            metadata=metadata,
            final_url=final_url,
            http_status=None,
        )

    try:
        counts = _save_queue_properties(
            db,
            item,
            props,
            item_deadline=item_deadline,
            canonical_resolution=canonical_resolution,
            strategy_meta=strategy_meta,
        )
    except ItemTimeoutError as exc:
        raise _item_timeout_control_error(
            item,
            started_at,
            timeout_seconds,
            url_usada,
            estrategia,
            "guardado_geocoding",
            {
                "diagnostico_inicial": strategy_meta.get("diagnostico_inicial"),
                "strategy_plan": strategy_meta.get("strategy_plan"),
                "propiedades_detectadas": len(props),
            },
        ) from exc
    except SavePropertiesError as exc:
        metadata_extra = {
            "diagnostico_inicial": strategy_meta.get("diagnostico_inicial"),
            "strategy_plan": strategy_meta.get("strategy_plan"),
            "estrategia_usada": estrategia,
            "propiedades_detectadas": len(props),
            "canonical_resolution": {
                "run_item_inmobiliaria_id": canonical_resolution.get("run_item_inmobiliaria_id"),
                "canonical_main_id": canonical_resolution.get("canonical_main_id"),
                "source_id_space": canonical_resolution.get("source_id_space"),
                "metodo_resolucion": canonical_resolution.get("metodo_resolucion"),
                "validation": canonical_resolution.get("validation"),
            },
            "final_url_validation": final_validation,
            "save_errors": exc.errors,
            "proteccion_actualizacion": dict(getattr(db, "last_save_protection_stats", {}) or {}),
            "save_result": dict(getattr(db, "last_save_result", {}) or {}),
        }
        combined_errors = errores_relevantes + [str(exc)[:1000]]
        metadata = _queue_metadata(
            item=item,
            started_at=started_at,
            url_usada=url_usada,
            estrategia_usada=estrategia,
            cantidad_paginas=int(strategy_meta.get("cantidad_paginas") or (1 if url_usada else 0)),
            errores_relevantes=combined_errors,
            extra=metadata_extra,
        )
        raise ScrapingControlError(
            str(exc)[:1000],
            metadata=metadata,
            final_url=url_usada,
            http_status=None,
        ) from exc
    metadata_extra = {
        "geocodificadas": counts["geocodificadas"],
        "geocoding_omitido_por_timeout": counts.get("geocoding_omitido_por_timeout", 0),
        "propiedades_inactivas_marcadas": counts["propiedades_inactivas_marcadas"],
        "inactivos_omitidos_por_timeout": counts.get("inactivos_omitidos_por_timeout", False),
        "inactivos_omitidos_por_extraccion_parcial": counts.get("inactivos_omitidos_por_extraccion_parcial", False),
        "inmobiliaria_main_id": counts["inmobiliaria_main_id"],
        "inmobiliaria_scraping_id": counts["inmobiliaria_scraping_id"],
        "metodo_resolucion_inmobiliaria": counts["metodo_resolucion_inmobiliaria"],
        "canonical_resolution": counts.get("canonical_resolution", {}),
        "final_url_validation": final_validation,
        "proteccion_actualizacion": counts.get("proteccion_actualizacion", {}),
        "image_save_diagnostics": counts.get("image_save_diagnostics", {}),
    }
    for key, value in strategy_meta.items():
        if key not in {"cantidad_paginas", "errores_relevantes"}:
            metadata_extra[key] = value
    combined_errors = errores_relevantes + list(strategy_meta.get("errores_relevantes") or [])
    metadata = _queue_metadata(
        item=item,
        started_at=started_at,
        url_usada=url_usada,
        estrategia_usada=estrategia,
        cantidad_paginas=int(strategy_meta.get("cantidad_paginas") or (1 if url_usada else 0)),
        errores_relevantes=combined_errors,
        extra=metadata_extra,
    )

    return {
        **counts,
        "estrategia_usada": estrategia,
        "final_url": final_url,
        "metadata_json": metadata,
    }


def run_integrity_dry_run(max_items: Optional[int] = 5) -> None:
    """
    Read-only queue integrity check.

    It does not claim items, does not start/finish items, does not scrape URLs and
    does not save properties. It verifies that pending queue items can be resolved
    to the canonical inmobiliarias_main.id that would be used for propiedades.
    """
    db = SupabasePropiedades()
    limit = max_items if max_items is not None and max_items > 0 else 5
    items = db.load_pending_scraping_items_for_integrity(limit=limit)

    safe = 0
    failed = 0
    final_url_mismatch = 0
    canonical_failed = 0

    logger.info("=" * 60)
    logger.info("DRY-RUN INTEGRIDAD DE IDS")
    logger.info("Items pending revisados: %d", len(items))
    logger.info("No se reclama cola, no se scrapea y no se guarda nada.")

    if not items:
        logger.info("No hay items pending para revisar.")

    for item in items:
        item_id = item.get("scraping_run_item_id") or item.get("id")
        logger.info("-" * 60)
        logger.info(
            "Item %s | run=%s | run_item_inmobiliaria_id=%s | nombre=%s | web=%s",
            item_id,
            item.get("scraping_run_id"),
            item.get("inmobiliaria_id"),
            item.get("inmobiliaria_nombre"),
            item.get("web") or item.get("url_listado"),
        )
        try:
            resolution = db.resolve_canonical_inmobiliaria_id(item)
            main_row = resolution.get("main_row") or {}
            validation = resolution.get("validation") or {}
            final_validation = (
                _final_url_domain_validation(item.get("final_url"), item, resolution)
                if item.get("final_url")
                else {"valid": True, "reason": "runtime_validation_pending", "final_domain": "", "source_domains": _unique_domains(item.get("web"), item.get("url_listado"))}
            )
            if not final_validation.get("valid"):
                final_url_mismatch += 1
                failed += 1
                logger.error(
                    "NO SAFE | final_url_domain_mismatch | final_url=%s final_domain=%s source_domains=%s",
                    item.get("final_url"),
                    final_validation.get("final_domain"),
                    final_validation.get("source_domains"),
                )
                continue
            safe += 1
            logger.info(
                "SAFE | canonical_main_id=%s | main='%s' | main_web='%s' | metodo=%s | source_space=%s",
                resolution.get("canonical_main_id"),
                _agency_row_name(main_row),
                main_row.get("web") or main_row.get("url_listado"),
                resolution.get("metodo_resolucion"),
                resolution.get("source_id_space"),
            )
            logger.info(
                "Validacion | name_ok=%s domain_ok=%s matching_domains=%s final_url_check=%s",
                validation.get("name_ok"),
                validation.get("domain_ok"),
                validation.get("matching_domains"),
                final_validation.get("reason"),
            )
        except Exception as exc:
            failed += 1
            error_type = clasificar_error(exc)
            if error_type in {"canonical_id_resolution_failed", "canonical_id_mismatch", "data_integrity_mismatch"}:
                canonical_failed += 1
            logger.error("NO SAFE | %s | %s", error_type, str(exc)[:500])
            metadata = getattr(exc, "metadata", None)
            if metadata:
                logger.info("Metadata error: %s", json.dumps(metadata, ensure_ascii=False)[:2000])

    logger.info("=" * 60)
    logger.info("RESUMEN DRY-RUN INTEGRIDAD")
    logger.info("safe_to_scrape_save: %d", safe)
    logger.info("failed: %d", failed)
    logger.info("canonical_resolution_failed/mismatch: %d", canonical_failed)
    logger.info("final_url_domain_mismatch: %d", final_url_mismatch)
    logger.info("=" * 60)


def run_controlled_queue(
    max_items: Optional[int] = None,
    allow_playwright_fallback: bool = False,
    allow_network_interception: bool = False,
) -> None:
    """
    Ejecuta el scraper usando el sistema de control de Supabase:
    claim_next_scraping_item -> start -> success/error -> close run.
    """
    t_inicio = time.time()
    db = SupabasePropiedades()
    processed = 0
    success = 0
    failed = 0
    interrupted = False
    skipped_integrity = 0
    skipped_final_domain = 0
    total_detected = 0
    total_new = 0
    total_updated = 0
    total_unchanged = 0
    total_property_errors = 0

    if max_items is not None and max_items <= 0:
        elapsed = time.time() - t_inicio
        logger.info("No se procesan items porque max_items=%s", max_items)
        logger.info("=" * 60)
        logger.info("SCRAPING CONTROLADO FINALIZADO")
        logger.info("Items procesados: 0")
        logger.info("Exitos: 0")
        logger.info("Errores: 0")
        logger.info("Tiempo total: %.1f s (%.1f min)", elapsed, elapsed / 60)
        logger.info("=" * 60)
        return

    session = SupabasePropiedades._make_session()
    use_playwright = allow_playwright_fallback or allow_network_interception

    pw = None
    browser = None
    pw_context = None
    if use_playwright:
        pw = sync_playwright().start()
        browser, pw_context = _make_playwright_context(pw)
    try:
        try:
            while max_items is None or processed < max_items:
                item = db.claim_next_scraping_item()
                if not item:
                    logger.info("No hay items pendientes")
                    break

                processed += 1
                item_id = item.get("scraping_run_item_id")
                run_id = item.get("scraping_run_id")
                nombre = item.get("inmobiliaria_nombre") or f"inmobiliaria {item.get('inmobiliaria_id')}"
                item_started_at = time.time()

                logger.info("=" * 60)
                logger.info("Inmobiliaria tomada: %s", nombre)
                logger.info("Run item: %s | Run: %s", item_id, run_id)
                logger.info("Ciudad/provincia: %s, %s", item.get("ciudad") or "-", item.get("provincia") or "-")
                logger.info("Prioridad scraping: %s", item.get("prioridad_scraping_score"))

                try:
                    result = _process_scraping_control_item(
                        db,
                        item,
                        session,
                        pw_context,
                        allow_playwright_fallback=allow_playwright_fallback,
                        allow_network_interception=allow_network_interception,
                    )
                    db.finish_scraping_item_success(
                        item_id=item_id,
                        propiedades_detectadas=result["propiedades_detectadas"],
                        propiedades_nuevas=result["propiedades_nuevas"],
                        propiedades_actualizadas=result["propiedades_actualizadas"],
                        propiedades_sin_cambios=result["propiedades_sin_cambios"],
                        propiedades_error=result["propiedades_error"],
                        final_url=result["final_url"],
                        metadata_json=result["metadata_json"],
                    )
                    success += 1
                    total_detected += int(result.get("propiedades_detectadas") or 0)
                    total_new += int(result.get("propiedades_nuevas") or 0)
                    total_updated += int(result.get("propiedades_actualizadas") or 0)
                    total_unchanged += int(result.get("propiedades_sin_cambios") or 0)
                    total_property_errors += int(result.get("propiedades_error") or 0)
                    logger.info(
                        "Integridad ID final | item=%s run_item_inmobiliaria_id=%s canonical_main_id=%s final_url=%s",
                        item_id,
                        item.get("inmobiliaria_id"),
                        (result.get("metadata_json") or {}).get("canonical_resolution", {}).get("canonical_main_id"),
                        result.get("final_url"),
                    )
                    logger.info("Propiedades detectadas: %d", result["propiedades_detectadas"])
                    logger.info("Nuevas: %d", result["propiedades_nuevas"])
                    logger.info("Actualizadas: %d", result["propiedades_actualizadas"])
                    logger.info("Sin cambios: %d", result["propiedades_sin_cambios"])
                    logger.info("Errores: %d", result["propiedades_error"])
                    logger.info("Estado final: success")
                except KeyboardInterrupt:
                    interrupted = True
                    failed += 1
                    metadata = _queue_metadata(
                        item=item,
                        started_at=item_started_at,
                        url_usada=item.get("url_listado") or item.get("web"),
                        estrategia_usada="manual_interrupt",
                        cantidad_paginas=0,
                        errores_relevantes=["Interrumpido manualmente"],
                    )
                    logger.warning("Estado final: manual_interrupt")
                    try:
                        db.finish_scraping_item_error(
                            item_id=item_id,
                            error_message="Interrumpido manualmente",
                            error_type="manual_interrupt",
                            http_status=None,
                            final_url=item.get("url_listado") or item.get("web"),
                            metadata_json=metadata,
                        )
                    except Exception as close_exc:
                        logger.error("No se pudo registrar interrupcion del item %s: %s", item_id, close_exc)
                    break
                except Exception as exc:
                    failed += 1
                    control_exc = exc if isinstance(exc, ScrapingControlError) else None
                    metadata = (
                        control_exc.metadata
                        if control_exc
                        else _queue_metadata(
                            item=item,
                            started_at=item_started_at,
                            url_usada=None,
                            estrategia_usada="error",
                            cantidad_paginas=0,
                            errores_relevantes=[str(exc)[:500]],
                        )
                    )
                    final_url = control_exc.final_url if control_exc else None
                    http_status = (
                        control_exc.http_status
                        if control_exc and control_exc.http_status is not None
                        else _extract_http_status(exc)
                    )
                    error_type = clasificar_error(exc)
                    if error_type in {
                        "data_integrity_mismatch",
                        "canonical_id_resolution_failed",
                        "canonical_id_mismatch",
                    }:
                        skipped_integrity += 1
                    if error_type == "final_url_domain_mismatch":
                        skipped_final_domain += 1

                    logger.error("Estado final: error (%s): %s", error_type, str(exc)[:500])
                    try:
                        db.finish_scraping_item_error(
                            item_id=item_id,
                            error_message=str(exc),
                            error_type=error_type,
                            http_status=http_status,
                            final_url=final_url,
                            metadata_json=metadata,
                        )
                    except Exception as close_exc:
                        logger.error("No se pudo registrar error del item %s: %s", item_id, close_exc)
                finally:
                    if run_id and not interrupted:
                        try:
                            db.close_scraping_run_if_finished(run_id)
                        except Exception as exc:
                            logger.warning("No se pudo cerrar run %s si estaba finalizado: %s", run_id, exc)
                    elif run_id and interrupted:
                        logger.info("Interrupcion manual: se omite cierre de run %s para no bloquear", run_id)

        finally:
            if use_playwright:
                _close_playwright_safely(pw_context, "playwright context")
                _close_playwright_safely(browser, "playwright browser")
    finally:
        if use_playwright:
            _close_playwright_safely(pw, "playwright driver")

    elapsed = time.time() - t_inicio
    logger.info("=" * 60)
    logger.info("SCRAPING CONTROLADO FINALIZADO")
    logger.info("Items procesados: %d", processed)
    logger.info("Exitos: %d", success)
    logger.info("Errores: %d", failed)
    logger.info("Omitidos por integridad ID: %d", skipped_integrity)
    logger.info("Omitidos por final_url_domain_mismatch: %d", skipped_final_domain)
    logger.info("Propiedades detectadas: %d", total_detected)
    logger.info("Propiedades nuevas: %d", total_new)
    logger.info("Propiedades actualizadas: %d", total_updated)
    logger.info("Propiedades sin cambios: %d", total_unchanged)
    logger.info("Propiedades con error: %d", total_property_errors)
    logger.info("Tiempo total: %.1f s (%.1f min)", elapsed, elapsed / 60)
    logger.info("=" * 60)


# ---------------------------------------------------------------------------
# Legacy queue runner
# ---------------------------------------------------------------------------

def run(
    max_workers: int = 4,
    cms_filter: Optional[str] = None,
    solo_con_tokko: bool = False,
    detect_only: bool = False,
    refresh_horas: int = 24,
) -> None:
    """
    Punto de entrada principal.
    Con detect_only=True: solo detecta estrategias y las guarda, sin scrapear.
    Con detect_only=False: usa estrategias guardadas y scrapea propiedades.
    """
    t_inicio = time.time()
    db = SupabasePropiedades()

    # 1. Cargar agencias
    logger.info("Cargando agencias activas...")
    agencies = db.load_agencies(cms_filter=cms_filter, solo_con_tokko=solo_con_tokko)
    if not agencies:
        logger.warning("No se encontraron agencias activas. Abortando.")
        return
    logger.info("Agencias encontradas: %d", len(agencies))

    # =========================================================
    # MODO DETECT-ONLY: detectar estrategias sin scrapear
    # =========================================================
    if detect_only:
        logger.info("=" * 60)
        logger.info("MODO DETECCIÓN — sin scrapear propiedades")
        logger.info("=" * 60)

        agency_q: queue.Queue = queue.Queue()
        for a in agencies:
            agency_q.put(a)

        total = len(agencies)
        counter = [0]
        lock = threading.Lock()
        stats: dict = {}
        actual_workers = min(max_workers, total)

        threads: List[threading.Thread] = []
        for _ in range(actual_workers):
            t = threading.Thread(
                target=detect_worker_fn,
                args=(agency_q, db, total, counter, lock, stats),
                daemon=True,
            )
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        # Fase 2: browser para los que necesitan Playwright (Tokko key detection)
        necesitan_browser = [a for a in agencies
                             if not a.get("estrategia_scraping")
                             or a.get("estrategia_scraping") == "necesita_browser"]

        if necesitan_browser:
            logger.info("Fase 2 — detección con browser: %d sitios", len(necesitan_browser))
            http_session = _make_detect_session()  # sin reintentos → falla rápido en sitios lentos
            with sync_playwright() as pw:
                browser_inst, pw_context = _make_playwright_context(pw)
                try:
                    for i, inmob in enumerate(necesitan_browser, 1):
                        nombre = inmob.get("nombre", inmob.get("web", "?"))
                        logger.info("[%d/%d] %s — browser detect...", i, len(necesitan_browser), nombre[:40])
                        try:
                            resultado = detect_strategy(inmob, http_session, pw_context)
                            estrategia = resultado.get("estrategia_scraping", "sin_estrategia")
                            _save_estrategia(db, inmob["id"], resultado)
                            logger.info("  → %s", estrategia)
                            stats[estrategia] = stats.get(estrategia, 0) + 1
                            # Quitar el conteo previo de "necesita_browser"
                            stats["necesita_browser"] = max(0, stats.get("necesita_browser", 1) - 1)
                        except Exception as exc:
                            logger.warning("  browser detect error: %s", exc)
                            stats["error"] = stats.get("error", 0) + 1
                finally:
                    try:
                        browser_inst.close()
                    except Exception:
                        pass

        elapsed = time.time() - t_inicio
        logger.info("=" * 60)
        logger.info("DETECCIÓN COMPLETADA en %.1f min", elapsed / 60)
        for k, v in sorted(stats.items(), key=lambda x: -x[1]):
            if v > 0:
                logger.info("  %-20s : %d", k, v)
        logger.info("=" * 60)
        return

    # =========================================================
    # MODO SCRAPING NORMAL
    # =========================================================

    # 2. Crear/cargar jobs
    logger.info("Creando scraping_jobs...")

    # Cargar todos los jobs existentes (pendiente, fallido Y completado)
    existing_jobs = db.load_all_jobs_for_agencies([a["id"] for a in agencies])
    existing_by_inmob = {j["inmobiliaria_id"]: j for j in existing_jobs}

    REFRESH_HORAS = refresh_horas  # controlado por --incremental (6h) o default (24h)
    ahora_utc = datetime.now(timezone.utc)

    job_pairs: List[Tuple[Dict, Dict]] = []
    new_jobs_data: List[Dict] = []
    jobs_a_resetear: List[int] = []

    for inmob in agencies:
        inmob_id = inmob["id"]
        job = existing_by_inmob.get(inmob_id)

        if job is None:
            # No existe → crear
            new_jobs_data.append({
                "inmobiliaria_id": inmob_id,
                "estado": "pendiente",
                "prioridad": 10 if inmob.get("tokko_api_key") else 5,
                "url_inicio": inmob.get("url_listado") or inmob.get("web", ""),
                "intentos": 0,
                "max_intentos": 4,
            })
        elif job["estado"] == "completado":
            # Completado → verificar si pasaron 24 horas para refrescar
            completado_en = job.get("completado_en")
            if completado_en:
                try:
                    ts = datetime.fromisoformat(completado_en.replace("Z", "+00:00"))
                    if (ahora_utc - ts).total_seconds() >= REFRESH_HORAS * 3600:
                        jobs_a_resetear.append(job["id"])
                        job_pairs.append(({**job, "estado": "pendiente", "intentos": 0}, inmob))
                        continue
                except Exception:
                    pass
            # Completado recientemente → saltar
        else:
            # pendiente o fallido → encolar
            job_pairs.append((job, inmob))

    # Resetear jobs completados que necesitan refresh
    if jobs_a_resetear:
        logger.info("Reseteando %d jobs para refresh diario...", len(jobs_a_resetear))
        for jid in jobs_a_resetear:
            db._patch_job(jid, {"estado": "pendiente", "intentos": 0, "completado_en": None})

    if new_jobs_data:
        logger.info("Insertando %d jobs nuevos en batch...", len(new_jobs_data))
        created_map = db.bulk_create_jobs(new_jobs_data)
        for jdata in new_jobs_data:
            inmob_id = jdata["inmobiliaria_id"]
            inmob = next((a for a in agencies if a["id"] == inmob_id), None)
            if inmob is None:
                continue
            job_id = created_map.get(inmob_id, -1)
            job_pairs.append(({**jdata, "id": job_id}, inmob))

    total = len(job_pairs)
    logger.info("Jobs a procesar: %d", total)

    # 3. Poblar queue
    job_q: queue.Queue = queue.Queue()
    for pair in job_pairs:
        job_q.put(pair)

    counter = [0]
    lock = threading.Lock()
    actual_workers = min(max_workers, total)

    # 4. Lanzar workers
    threads: List[threading.Thread] = []
    for _ in range(actual_workers):
        t = threading.Thread(
            target=worker_fn,
            args=(job_q, db, total, counter, lock),
            daemon=True,
        )
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    # 5. Resumen
    elapsed = time.time() - t_inicio
    logger.info("=" * 60)
    logger.info("SCRAPING COMPLETADO")
    logger.info("  Agencias procesadas : %d", total)
    logger.info("  Workers usados      : %d", actual_workers)
    logger.info("  Tiempo total        : %.1f s (%.1f min)", elapsed, elapsed / 60)

    # Stats finales desde DB
    try:
        r = db.session.get(
            f"{SUPABASE_URL}/rest/v1/scraping_jobs",
            headers=db._headers,
            params={
                "select": "estado",
                "inmobiliaria_id": f"in.({','.join(str(a['id']) for a in agencies)})",
                "limit": 1000,
            },
            timeout=20,
        )
        if r.status_code == 200:
            from collections import Counter
            stats = Counter(j["estado"] for j in r.json())
            logger.info("  Completados  : %d", stats.get("completado", 0))
            logger.info("  Fallidos     : %d", stats.get("fallido", 0))
            logger.info("  Pendientes   : %d", stats.get("pendiente", 0))
    except Exception:
        pass

    logger.info("=" * 60)


# ---------------------------------------------------------------------------
# Technical single URL tester
# ---------------------------------------------------------------------------

def test_single_url(
    url: str,
    cms: Optional[str] = None,
    allow_playwright_fallback: bool = False,
    allow_network_interception: bool = False,
) -> None:
    """Prueba una URL puntual sin consumir items de la cola ni guardar propiedades."""
    started_at = time.time()
    session = SupabasePropiedades._make_session()
    estrategia = _strategy_from_cms(cms)
    inmob: Dict[str, Any] = {
        "id": 0,
        "nombre": "test-url",
        "web": url,
        "url_listado": url,
        "cms_detectado": cms,
        "ciudad": "",
        "provincia": "",
    }
    if estrategia:
        inmob["estrategia_scraping"] = estrategia

    use_playwright = allow_playwright_fallback or allow_network_interception
    pw = browser = pw_context = None
    try:
        if use_playwright:
            pw = sync_playwright().start()
            browser, pw_context = _make_playwright_context(pw)
        props, strategy = run_best_strategy(
            inmob,
            session,
            pw_context,
            allow_playwright_fallback=allow_playwright_fallback,
            allow_network_interception=allow_network_interception,
            item_deadline=started_at + CONTROL_ITEM_TIMEOUT_SECONDS,
            allow_explicit_strategy_fallback=True,
        )
        metadata = dict(inmob.get("_scraper_metadata") or {})
        logger.info("=" * 60)
        logger.info("TEST URL FINALIZADO")
        logger.info("URL: %s", url)
        logger.info("CMS: %s", cms or "sin dato")
        logger.info("Estrategia usada: %s", strategy)
        logger.info("Propiedades detectadas: %d", len(props))
        con_fotos, sin_fotos = _count_real_image_props(props)
        logger.info("Propiedades con fotos reales: %d", con_fotos)
        logger.info("Propiedades sin fotos reales: %d", sin_fotos)
        logger.info("Metadata: %s", json.dumps(metadata, ensure_ascii=False)[:3000])
        for prop in props[:5]:
            images = prop.get("imagenes") or []
            first_image = images[0] if images else "sin foto real"
            logger.info(
                " - %s | %s %s | fotos=%d | %s | %s",
                prop.get("titulo"),
                prop.get("moneda"),
                prop.get("precio"),
                len(images),
                first_image,
                prop.get("url"),
            )
        logger.info("=" * 60)
    except Exception as exc:
        metadata = dict(inmob.get("_scraper_metadata") or {})
        logger.error("TEST URL ERROR (%s): %s", clasificar_error(exc), str(exc)[:500])
        if metadata:
            logger.info("Metadata: %s", json.dumps(metadata, ensure_ascii=False)[:3000])
    finally:
        if use_playwright:
            _close_playwright_safely(pw_context, "test-url playwright context")
            _close_playwright_safely(browser, "test-url playwright browser")
            _close_playwright_safely(pw, "test-url playwright driver")


def diagnose_single_url(
    url: str,
    cms: Optional[str] = None,
    allow_playwright: bool = False,
    allow_network_interception: bool = False,
) -> None:
    """Diagnostica una URL sin consumir cola ni guardar propiedades."""
    session = SupabasePropiedades._make_session()
    estrategia = _strategy_from_cms(cms)
    inmob: Dict[str, Any] = {
        "id": 0,
        "nombre": "diagnose-url",
        "web": url,
        "url_listado": url,
        "cms_detectado": cms,
        "ciudad": "",
        "provincia": "",
    }
    if estrategia:
        inmob["estrategia_scraping"] = estrategia

    pw = browser = pw_context = None
    try:
        if allow_playwright:
            pw = sync_playwright().start()
            browser, pw_context = _make_playwright_context(pw)
        diagnostic = diagnose_inmob(
            inmob,
            session,
            pw_context=pw_context,
            allow_playwright=allow_playwright,
            allow_network_interception=allow_network_interception,
        )
        strategy_plan = select_best_scraping_strategy(diagnostic)
        logger.info("=" * 60)
        logger.info("DIAGNOSTICO URL")
        logger.info("URL: %s", url)
        logger.info("Tecnologia detectada: %s", ", ".join(diagnostic.get("tecnologias_detectadas") or []))
        logger.info("Extractores posibles: %s", ", ".join(diagnostic.get("extractores_posibles") or []))
        logger.info("HTTP status: %s", diagnostic.get("http_status"))
        logger.info("Final URL: %s", diagnostic.get("final_url"))
        logger.info("Links propiedad: %s", diagnostic.get("property_links_count"))
        logger.info("Cards posibles: %s", diagnostic.get("cards_posibles"))
        logger.info("Sitemap propiedades: %s", diagnostic.get("sitemap_property_urls_count"))
        logger.info("JSON-LD items: %s", diagnostic.get("json_ld_property_items"))
        logger.info("Requiere JS: %s", diagnostic.get("requires_js"))
        logger.info("Requiere Playwright: %s", diagnostic.get("requires_playwright"))
        logger.info("Requiere Network Interception: %s", diagnostic.get("requires_network_interception"))
        logger.info("Clasificacion: %s", diagnostic.get("classification"))
        logger.info("Estrategia sugerida: %s", strategy_plan.get("primary_strategy"))
        logger.info("Motivo estrategia: %s", strategy_plan.get("reason"))
        logger.info("Detalle JSON: %s", json.dumps(diagnostic, ensure_ascii=False)[:5000])
        logger.info("Strategy plan JSON: %s", json.dumps(strategy_plan, ensure_ascii=False)[:3000])
        logger.info("=" * 60)
    finally:
        if allow_playwright:
            _close_playwright_safely(pw_context, "diagnose-url playwright context")
            _close_playwright_safely(browser, "diagnose-url playwright browser")
            _close_playwright_safely(pw, "diagnose-url playwright driver")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scraper de propiedades para inmobiliarias argentinas")
    parser.add_argument("--workers",      type=int, default=4,    help="Workers paralelos (default: 4)")
    parser.add_argument("--cms",          type=str, default=None, help="Filtrar por CMS (ej: tokko, wordpress)")
    parser.add_argument("--solo-tokko",   action="store_true",    help="Solo agencias Tokko")
    parser.add_argument("--detect-only",  action="store_true",
                        help="Solo detectar estrategia de scraping por sitio, sin scrapear propiedades")
    parser.add_argument("--incremental",  action="store_true",
                        help="Solo scrapear agencias no actualizadas en las últimas 6 horas")
    parser.add_argument("--max-items",    type=int, default=None,
                        help="Limite de items a procesar desde scraping_run_items (ej: 5)")
    parser.add_argument("--test-url",     type=str, default=None,
                        help="Probar una URL puntual sin consumir cola")
    parser.add_argument("--diagnose-url", type=str, default=None,
                        help="Diagnosticar una URL sin consumir cola ni guardar propiedades")
    parser.add_argument("--technical-review", action="store_true",
                        help="Modo tecnico: habilita Network Interception y fallback Playwright con timeouts")
    parser.add_argument("--retry-errors", action="store_true",
                        help="Alias de modo tecnico para reintentos manuales controlados")
    parser.add_argument("--allow-network-interception", action="store_true",
                        help="Permitir Network Interception con Playwright en modo cola (default: desactivado)")
    parser.add_argument("--allow-playwright-fallback", action="store_true",
                        help="Permitir fallback HTML Playwright en modo cola (default: desactivado)")
    parser.add_argument("--allow-playwright", action="store_true",
                        help="Alias de --allow-playwright-fallback")
    parser.add_argument("--legacy-jobs",  action="store_true",
                        help="Usar el flujo anterior basado en scraping_jobs")
    parser.add_argument("--integrity-dry-run", action="store_true",
                        help="Validar IDs canonicos de items pending sin consumir cola, scrapear ni guardar")
    args = parser.parse_args()

    technical_mode = args.technical_review or args.retry_errors
    allow_network = args.allow_network_interception or technical_mode
    allow_playwright = args.allow_playwright_fallback or args.allow_playwright or technical_mode

    if args.integrity_dry_run:
        run_integrity_dry_run(max_items=args.max_items)
    elif args.diagnose_url:
        diagnose_single_url(
            url=args.diagnose_url,
            cms=args.cms,
            allow_playwright=allow_playwright,
            allow_network_interception=allow_network,
        )
    elif args.test_url:
        test_single_url(
            url=args.test_url,
            cms=args.cms,
            allow_playwright_fallback=allow_playwright,
            allow_network_interception=allow_network,
        )
    elif args.legacy_jobs or args.detect_only:
        run(
            max_workers=args.workers,
            cms_filter=args.cms,
            solo_con_tokko=args.solo_tokko,
            detect_only=args.detect_only,
            refresh_horas=6 if args.incremental else 24,
        )
    else:
        run_controlled_queue(
            max_items=args.max_items,
            allow_playwright_fallback=allow_playwright,
            allow_network_interception=allow_network,
        )
