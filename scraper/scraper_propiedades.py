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
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

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
STRATEGY_TIMEOUT_SECONDS: Dict[str, int] = {
    "tokko_api": 45,
    "tokko_html": 45,
    "wordpress_html": 35,
    "network_intercept": 30,
    "json_ld": 20,
    "sitemap": 20,
    "html_scraper": 45,
}
PLAYWRIGHT_LAUNCH_TIMEOUT_MS = 15000
PLAYWRIGHT_NAV_TIMEOUT_MS = 12000
PLAYWRIGHT_LOAD_TIMEOUT_MS = 8000
PLAYWRIGHT_ACTION_TIMEOUT_MS = 2500
PLAYWRIGHT_CLOSE_TIMEOUT_SECONDS = 3.0

def _make_http_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504],
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

def hash_propiedad(inmob_id: Any, id_externo: Any, url: Any) -> str:
    key = f"{inmob_id}|{id_externo or ''}|{url or ''}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

class StrategyTimeoutError(TimeoutError):
    """Timeout controlado de item o estrategia."""


def clasificar_error(e: Exception) -> str:
    msg = str(e).lower()
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    if "403" in msg or "429" in msg or "blocked" in msg or "captcha" in msg:
        return "blocked"
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
# Supabase client
# ---------------------------------------------------------------------------

class SupabasePropiedades:
    """Cliente Supabase orientado a las tablas propiedades y scraping_jobs."""

    _CHUNK = 50
    _PROPERTY_COLUMNS = {
        "id",
        "inmobiliaria_id",
        "url",
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
        retry = Retry(
            total=3,
            backoff_factor=0.5,
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
            timeout=15,
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

        if "calidad_score" in columns and "calidad_score" not in clean and "score_calidad" in clean:
            clean["calidad_score"] = clean["score_calidad"]

        filtered = {key: value for key, value in clean.items() if key in columns}
        dropped = sorted(set(clean) - set(filtered))
        if dropped:
            logger.debug("Campos omitidos en propiedades: %s", ", ".join(dropped))
        return filtered

    def save_propiedades(self, propiedades: List[Dict]) -> Tuple[int, int]:
        """Guarda en batch con upsert on hash_dedup. Retorna (total, nuevas)."""
        if not propiedades:
            return 0, 0

        propiedades = [self._sanitize_property_payload(p) for p in propiedades]
        propiedades = [p for p in propiedades if p.get("hash_dedup")]
        if not propiedades:
            return 0, 0

        hashes = [p["hash_dedup"] for p in propiedades]
        existing = self.get_existing_hashes(hashes)
        nuevas = [p for p in propiedades if p["hash_dedup"] not in existing]
        actualizadas = [p for p in propiedades if p["hash_dedup"] in existing]

        inserted = 0
        for i in range(0, len(nuevas), self._CHUNK):
            chunk = nuevas[i : i + self._CHUNK]
            r = self.session.post(
                f"{SUPABASE_URL}/rest/v1/propiedades?on_conflict=hash_dedup",
                headers=self._headers,
                json=chunk,
                timeout=40,
            )
            if r.status_code not in {200, 201}:
                logger.error("save_propiedades insert %s: %s", r.status_code, r.text[:200])
            else:
                inserted += len(chunk)

        for i in range(0, len(actualizadas), self._CHUNK):
            chunk = actualizadas[i : i + self._CHUNK]
            r = self.session.post(
                f"{SUPABASE_URL}/rest/v1/propiedades?on_conflict=hash_dedup",
                headers=self._headers,
                json=chunk,
                timeout=40,
            )
            if r.status_code not in {200, 201}:
                logger.warning("save_propiedades upsert %s: %s", r.status_code, r.text[:200])

        return len(propiedades), inserted

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
    r = session.get(url, headers=headers, timeout=timeout, verify=False, **kwargs)
    # Si bloqueado y tenemos ScraperAPI, reintentar
    if use_scraper_on_block and r.status_code in (403, 429, 503) and SCRAPERAPI_KEY:
        logger.debug("Bloqueado (%s) → reintentando con ScraperAPI: %s", r.status_code, url)
        r = _scraperapi_get(url, session, timeout)
    return r


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


def extraer_imagenes(soup: BeautifulSoup, base_url: str = "") -> List[str]:
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


TOKKO_HTML_EXTRACTOR_VERSION = "tokko_html_v2"

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
                    imagenes.append(urljoin(source_url, src))
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

                max_pages = min(int(inmob.get("paginas_estimadas") or 12), 30)
                for page_num in range(2, max_pages + 1):
                    _check_strategy_deadline(inmob, "tokko_html")
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
                        if len(resultados) == before:
                            break
                    except Exception as exc:
                        errores_relevantes.append(f"{next_url}: {type(exc).__name__}: {str(exc)[:180]}")
                        break

                resultados = _dedupe_props(resultados)
                inmob["_scraper_metadata"] = {
                    "urls_probadas": urls_probadas,
                    "cantidad_paginas": paginas_leidas,
                    "cantidad_links_internos_detectados": internal_links_detected,
                    "plantilla_tokko_detectada": templates_detected[0] if templates_detected else "unknown",
                    "plantillas_tokko_detectadas": templates_detected,
                    "extractor_tokko_version": TOKKO_HTML_EXTRACTOR_VERSION,
                    "errores_relevantes": errores_relevantes[-5:],
                }
                logger.info(
                    "  Tokko HTML: %d propiedades en %d paginas (%s)",
                    len(resultados), paginas_leidas, candidate,
                )
                return resultados

        except Exception as exc:
            errores_relevantes.append(f"{candidate}: {type(exc).__name__}: {str(exc)[:180]}")
            continue

    inmob["_scraper_metadata"] = {
        "urls_probadas": urls_probadas,
        "cantidad_paginas": paginas_leidas,
        "cantidad_links_internos_detectados": internal_links_detected,
        "plantilla_tokko_detectada": templates_detected[0] if templates_detected else "unknown",
        "plantillas_tokko_detectadas": templates_detected,
        "motivo_sin_propiedades": motivo_sin_propiedades,
        "extractor_tokko_version": TOKKO_HTML_EXTRACTOR_VERSION,
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


# ---------------------------------------------------------------------------
# Strategy 4: Sitemap crawler
# ---------------------------------------------------------------------------

SITEMAP_PATHS = [
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap-propiedades.xml",
    "/sitemap-properties.xml",
    "/sitemap-inmuebles.xml",
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
    bounded_strategy = inmob.get("_strategy_name") in {"sitemap", "wordpress_html"}
    if bounded_strategy:
        _check_strategy_deadline(inmob, str(inmob.get("_strategy_name") or "detail"))
    raw_html = None

    # Intento 1: request directo
    try:
        timeout = _bounded_http_timeout(inmob, 6) if bounded_strategy else 20
        r = _http_get(url, session, timeout=timeout)
        if r.status_code == 200:
            raw_html = r.text
    except Exception:
        pass

    # Intento 2: ScraperAPI si falló o bloqueado
    if not raw_html and SCRAPERAPI_KEY and not bounded_strategy:
        try:
            r2 = _scraperapi_get(url, session, timeout=30, js_render=False)
            if r2.status_code == 200:
                raw_html = r2.text
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
                    return _parse_jsonld_item(item, inmob, url)
        except Exception:
            pass

    # Fallback: extracción heurística HTML
    prop = _html_extract_detail(soup, url, inmob, raw_html)

    # Último recurso: IA
    if prop is None and GROQ_API_KEY:
        prop = _ai_extraer_propiedad(raw_html, url, inmob)

    return prop


def _html_extract_detail(soup: BeautifulSoup, url: str, inmob: Dict,
                         raw_html: str = "") -> Optional[Dict]:
    """Extracción heurística de datos de detalle desde HTML."""
    def find_text(*selectors):
        for sel in selectors:
            el = soup.select_one(sel)
            if el:
                return el.get_text(strip=True)
        return ""

    title = find_text(
        "h1", ".property-title", ".titulo", '[class*="title"]',
        '[class*="titulo"]', ".listing-title",
    )
    desc = find_text(
        ".description", ".descripcion", '[class*="description"]',
        '[class*="descripcion"]', ".property-description", "article p",
    )
    precio_raw = find_text(
        ".price", ".precio", '[class*="price"]', '[class*="precio"]',
        ".property-price", ".listing-price",
    )
    precio, moneda = normalizar_precio(precio_raw)

    tipo_raw = find_text('[class*="tipo"]', '[class*="type"]', ".property-type")
    op_raw   = find_text('[class*="operaci"]', '[class*="operation"]')

    address_raw = find_text(
        ".address", ".direccion", ".location", '[class*="address"]',
        '[class*="direccion"]', '[class*="location"]',
    )

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

    page_text_lower = soup.get_text(" ").lower()
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
    fotos = extraer_imagenes(soup, url)

    # Agente
    agente_nombre, agente_telefono = extraer_agente(soup)

    # Coordenadas desde Google Maps
    lat, lon = extraer_coordenadas_gmaps(raw_html or str(soup))

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
        "fuente_extraccion":   "sitemap",
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
    if "realhomes" in low or "inspiry" in low:
        return "realhomes"
    if "essential-real-estate" in low or "ere-" in low:
        return "essential_real_estate"
    if "estatik" in low:
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


def run_best_strategy(
    inmob: Dict,
    session: requests.Session,
    pw_context,
    allow_playwright_fallback: bool = True,
    allow_network_interception: bool = True,
    item_deadline: Optional[float] = None,
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

    def call(strategy_name: str, func: Callable[[], List[Dict]]) -> List[Dict]:
        _check_deadline(item_deadline, "item")
        return _run_strategy_with_deadline(strategy_name, inmob, item_deadline, func)

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
        if is_tokko_candidate:
            if allow_network_interception:
                raise RuntimeError("sin_propiedades: tokko sin datos tras tokko_html/network/json_ld/sitemap; html_playwright omitido")
            raise RuntimeError("sin_propiedades: tokko sin datos tras tokko_html/json_ld/sitemap; network_intercept/html_playwright omitidos")
        raise RuntimeError("sin_propiedades: html_playwright omitido por configuracion")
    props = call("html_scraper", lambda: strategy_html_playwright(inmob, pw_context))
    return props, "html_scraper"


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

def _make_detect_session() -> requests.Session:
    """Sesión HTTP para detección: sin reintentos en DNS/conexión, falla rápido."""
    s = requests.Session()
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


def _queue_item_to_inmob(item: Dict, url_usada: str) -> Dict:
    estrategia = _strategy_from_cms(item.get("cms_detectado"))
    inmob = {
        "id": item.get("inmobiliaria_id"),
        "nombre": item.get("inmobiliaria_nombre") or item.get("nombre") or "Sin nombre",
        "ciudad": item.get("ciudad"),
        "provincia": item.get("provincia"),
        "web": _normalize_queue_url(item.get("web")) or url_usada,
        "url_listado": url_usada,
        "cms_detectado": item.get("cms_detectado"),
        "prioridad_scraping_score": item.get("prioridad_scraping_score"),
        "total_propiedades_normalizado": item.get("total_propiedades_normalizado"),
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


def _scrape_queue_item(
    item: Dict,
    session: requests.Session,
    pw_context,
    started_at: float,
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
    item_deadline = started_at + CONTROL_ITEM_TIMEOUT_SECONDS

    for idx, url_usada in enumerate(urls, start=1):
        _check_deadline(item_deadline, "item")
        last_url = url_usada
        inmob = _queue_item_to_inmob(item, url_usada)
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


def _save_queue_properties(db: SupabasePropiedades, item: Dict, props: List[Dict]) -> Dict[str, Any]:
    agency_resolution = db.resolve_scraping_agency(item)
    main_id = agency_resolution.get("inmobiliaria_main_id")
    scraping_id = agency_resolution["inmobiliaria_scraping_id"]
    method = agency_resolution["metodo_resolucion"]
    logger.info(
        "Resolucion inmobiliaria: main_id=%s scraping_id=%s metodo=%s",
        main_id, scraping_id, method,
    )

    for prop in props:
        prop["inmobiliaria_id"] = scraping_id
        prop["hash_dedup"] = hash_propiedad(scraping_id, prop.get("id_externo"), prop.get("url"))

    hashes = [p.get("hash_dedup") for p in props if p.get("hash_dedup")]
    existing_hashes = db.get_existing_hashes(hashes)
    expected_new = sum(1 for h in hashes if h not in existing_hashes)
    expected_existing = sum(1 for h in hashes if h in existing_hashes)

    total_ext, nuevas = db.save_propiedades(props)
    propiedades_error = max(len(props) - total_ext, 0)

    geo_count = 0
    for prop in props:
        if prop.get("latitud") is None and (prop.get("direccion") or prop.get("ciudad")):
            lat, lon = geocodificar_direccion(
                prop.get("direccion", ""),
                prop.get("ciudad", ""),
                prop.get("provincia", ""),
            )
            if lat and lon:
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
    if props and scraping_id:
        active_hashes = {p["hash_dedup"] for p in props if p.get("hash_dedup")}
        inactivos = db.mark_inactivos(int(scraping_id), active_hashes)

    return {
        "propiedades_detectadas": len(props),
        "propiedades_nuevas": nuevas,
        "propiedades_actualizadas": max(expected_existing, total_ext - expected_new),
        "propiedades_sin_cambios": 0,
        "propiedades_error": propiedades_error,
        "geocodificadas": geo_count,
        "propiedades_inactivas_marcadas": inactivos,
        "inmobiliaria_main_id": main_id,
        "inmobiliaria_scraping_id": scraping_id,
        "metodo_resolucion_inmobiliaria": method,
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
    item_deadline = started_at + CONTROL_ITEM_TIMEOUT_SECONDS
    item_id = item.get("scraping_run_item_id")
    if not item_id:
        raise ScrapingControlError("Item sin scraping_run_item_id")

    db.start_scraping_item(item_id)
    _check_deadline(item_deadline, "item")

    props, estrategia, url_usada, errores_relevantes, strategy_meta = _scrape_queue_item(
        item=item,
        session=session,
        pw_context=pw_context,
        started_at=started_at,
        allow_playwright_fallback=allow_playwright_fallback,
        allow_network_interception=allow_network_interception,
    )
    _check_deadline(item_deadline, "item")
    counts = _save_queue_properties(db, item, props)
    metadata_extra = {
        "geocodificadas": counts["geocodificadas"],
        "propiedades_inactivas_marcadas": counts["propiedades_inactivas_marcadas"],
        "inmobiliaria_main_id": counts["inmobiliaria_main_id"],
        "inmobiliaria_scraping_id": counts["inmobiliaria_scraping_id"],
        "metodo_resolucion_inmobiliaria": counts["metodo_resolucion_inmobiliaria"],
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
        "final_url": url_usada,
        "metadata_json": metadata,
    }


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
        )
        metadata = dict(inmob.get("_scraper_metadata") or {})
        logger.info("=" * 60)
        logger.info("TEST URL FINALIZADO")
        logger.info("URL: %s", url)
        logger.info("CMS: %s", cms or "sin dato")
        logger.info("Estrategia usada: %s", strategy)
        logger.info("Propiedades detectadas: %d", len(props))
        logger.info("Metadata: %s", json.dumps(metadata, ensure_ascii=False)[:3000])
        for prop in props[:5]:
            logger.info(" - %s | %s %s | %s", prop.get("titulo"), prop.get("moneda"), prop.get("precio"), prop.get("url"))
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
    parser.add_argument("--technical-review", action="store_true",
                        help="Modo tecnico: habilita Network Interception y fallback Playwright con timeouts")
    parser.add_argument("--retry-errors", action="store_true",
                        help="Alias de modo tecnico para reintentos manuales controlados")
    parser.add_argument("--allow-network-interception", action="store_true",
                        help="Permitir Network Interception con Playwright en modo cola (default: desactivado)")
    parser.add_argument("--allow-playwright-fallback", action="store_true",
                        help="Permitir fallback HTML Playwright en modo cola (default: desactivado)")
    parser.add_argument("--legacy-jobs",  action="store_true",
                        help="Usar el flujo anterior basado en scraping_jobs")
    args = parser.parse_args()

    technical_mode = args.technical_review or args.retry_errors
    allow_network = args.allow_network_interception or technical_mode
    allow_playwright = args.allow_playwright_fallback or technical_mode

    if args.test_url:
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
