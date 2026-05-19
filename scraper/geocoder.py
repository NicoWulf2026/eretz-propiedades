from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_KEY")
    or os.getenv("SUPABASE_ANON_KEY", "")
)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_DELAY_SECONDS = 1.2
USER_AGENT = os.getenv(
    "GEOCODER_USER_AGENT",
    "InmocapitalGeocoder/1.0 (geocoding@inmocapital.local)",
)

CITY_BOUNDS = {
    "rosario": (-33.10, -32.80, -60.85, -60.50),
    "santa fe": (-31.80, -31.45, -60.90, -60.45),
    "rafaela": (-31.40, -31.10, -61.70, -61.30),
    "funes": (-33.00, -32.80, -60.90, -60.70),
    "roldan": (-33.00, -32.80, -61.00, -60.80),
    "san jose del rincon": (-31.70, -31.50, -60.65, -60.45),
}
URUGUAY_BOUNDS = (-35.20, -30.00, -58.80, -53.00)
ARGENTINA_BOUNDS = (-56.00, -21.00, -74.00, -53.00)


@dataclass
class GeocodingResult:
    latitud: Optional[float]
    longitud: Optional[float]
    precision_geocoding: Optional[str]
    proveedor: str
    raw_response: Any
    status: str
    error_message: Optional[str] = None
    matched_query: Optional[str] = None
    attempted_queries: Optional[List[str]] = None


@dataclass
class AddressCleaningResult:
    cleaned_address: str
    is_geocodable: bool
    quality: str
    reason: str
    source: str
    raw_value: str
    skipped_sources: Optional[List[Dict[str, str]]] = None
    evaluated_sources: Optional[List[Dict[str, str]]] = None
    readiness: str = "geocoding_not_ready"
    detected_city: Optional[str] = None
    detected_province: Optional[str] = None
    proposed_query: str = ""

    def to_metadata(self) -> Dict[str, Any]:
        return {
            "cleaned_address": self.cleaned_address,
            "is_geocodable": self.is_geocodable,
            "quality": self.quality,
            "reason": self.reason,
            "source": self.source,
            "raw_value": self.raw_value,
            "skipped_sources": self.skipped_sources or [],
            "evaluated_sources": self.evaluated_sources or [],
            "readiness": self.readiness,
            "detected_city": self.detected_city,
            "detected_province": self.detected_province,
            "proposed_query": self.proposed_query,
        }


class SupabaseGeocodingClient:
    def __init__(self, url: str, key: str) -> None:
        if not url or not key:
            raise RuntimeError("Faltan SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY/SUPABASE_KEY en .env")
        self.url = url
        self.key = key
        self.session = self._make_session()
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        self.headers_minimal = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }

    @staticmethod
    def _make_session() -> requests.Session:
        session = requests.Session()
        session.trust_env = False
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PATCH"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def get_pending_batch(self, limit: int) -> List[Dict[str, Any]]:
        response = self.session.get(
            f"{self.url}/rest/v1/v_next_geocoding_batch",
            headers=self.headers,
            params={"select": "*", "limit": limit},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def existing_result(self, propiedad_id: Any, direccion_geocoding: str) -> Optional[Dict[str, Any]]:
        response = self.session.get(
            f"{self.url}/rest/v1/geocoding_results",
            headers=self.headers,
            params={
                "select": "propiedad_id,direccion_geocoding,status",
                "propiedad_id": f"eq.{propiedad_id}",
                "direccion_geocoding": f"eq.{direccion_geocoding}",
                "limit": 1,
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        return data[0] if data else None

    def save_result(self, payload: Dict[str, Any]) -> str:
        response = self.session.post(
            f"{self.url}/rest/v1/geocoding_results",
            headers=self.headers,
            json=payload,
            timeout=20,
        )
        if response.status_code in {200, 201}:
            return "saved"
        if response.status_code == 409:
            return "duplicate"
        raise RuntimeError(
            f"geocoding_results insert {response.status_code}: {response.text[:500]}"
        )

    def get_success_results_batch(self, limit: int) -> List[Dict[str, Any]]:
        response = self.session.get(
            f"{self.url}/rest/v1/geocoding_results",
            headers=self.headers,
            params={
                "select": "id,propiedad_id,direccion_geocoding,latitud,longitud,precision_geocoding,proveedor,raw_response,status",
                "status": "eq.success",
                "latitud": "not.is.null",
                "longitud": "not.is.null",
                "order": "id.desc",
                "limit": limit,
            },
            timeout=20,
        )
        response.raise_for_status()
        return response.json()

    def update_property_coordinates(self, propiedad_id: Any, latitud: float, longitud: float) -> str:
        response = self.session.patch(
            f"{self.url}/rest/v1/propiedades",
            headers=self.headers_minimal,
            params={"id": f"eq.{propiedad_id}"},
            json={"latitud": latitud, "longitud": longitud},
            timeout=20,
        )
        if response.status_code in {200, 204}:
            return "updated"
        raise RuntimeError(
            f"propiedades update {response.status_code}: {response.text[:500]}"
        )

    def get_property_location_context(self, propiedad_id: Any) -> Dict[str, Any]:
        response = self.session.get(
            f"{self.url}/rest/v1/propiedades",
            headers=self.headers,
            params={
                "select": "id,ciudad,provincia,pais,latitud,longitud",
                "id": f"eq.{propiedad_id}",
                "limit": 1,
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        return data[0] if data else {}

    def get_properties_with_coordinates(self, limit: int) -> List[Dict[str, Any]]:
        response = self.session.get(
            f"{self.url}/rest/v1/propiedades",
            headers=self.headers,
            params={
                "select": "id,titulo,direccion,barrio,ciudad,provincia,pais,latitud,longitud",
                "latitud": "not.is.null",
                "longitud": "not.is.null",
                "order": "updated_at.desc",
                "limit": limit,
            },
            timeout=20,
        )
        response.raise_for_status()
        return response.json()


class NominatimProvider:
    name = "nominatim"

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "es-AR,es;q=0.9",
        })

    def geocode(self, query: str) -> GeocodingResult:
        try:
            response = self.session.get(
                NOMINATIM_URL,
                params={
                    "q": query,
                    "format": "jsonv2",
                    "limit": 1,
                    "countrycodes": "ar",
                    "addressdetails": 1,
                },
                timeout=15,
            )
            if response.status_code == 429:
                return GeocodingResult(
                    None, None, None, self.name, {"status_code": 429},
                    "error", "Rate limit de Nominatim",
                )
            if response.status_code == 403:
                return GeocodingResult(
                    None, None, None, self.name, {"status_code": 403},
                    "error", "Nominatim bloqueo el User-Agent",
                )
            response.raise_for_status()
            data = response.json()
            if not data:
                return GeocodingResult(
                    None, None, None, self.name, [],
                    "error", "Sin resultados de geocoding",
                )

            first = data[0]
            lat = float(first["lat"])
            lon = float(first["lon"])
            return GeocodingResult(
                lat,
                lon,
                _infer_precision(first),
                self.name,
                first,
                "success",
                None,
            )
        except requests.RequestException as exc:
            return GeocodingResult(None, None, None, self.name, _safe_error(exc), "error", str(exc)[:500])
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            return GeocodingResult(None, None, None, self.name, _safe_error(exc), "error", f"Respuesta invalida: {exc}")
        finally:
            time.sleep(NOMINATIM_DELAY_SECONDS)


def _infer_precision(item: Dict[str, Any]) -> str:
    addresstype = str(item.get("addresstype") or "").lower()
    osm_type = str(item.get("type") or "").lower()
    place_rank = item.get("place_rank")
    if addresstype in {"house", "building"} or osm_type in {"house", "building"}:
        return "exact"
    if addresstype in {"road", "street"} or osm_type in {"residential", "tertiary", "secondary", "primary"}:
        return "street"
    if addresstype in {"neighbourhood", "suburb", "quarter", "city", "town"}:
        return "area"
    try:
        if place_rank is not None and int(place_rank) >= 26:
            return "street"
    except (TypeError, ValueError):
        pass
    return "approximate"


def _safe_error(exc: BaseException) -> Dict[str, Any]:
    return {"error": type(exc).__name__, "message": str(exc)[:500]}


def normalize_place_key(value: Any) -> str:
    text = str(value or "").strip()
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", ascii_text.lower()).strip()


def evaluate_city_bounds(
    latitud: Optional[float],
    longitud: Optional[float],
    ciudad_final: Any,
    provincia_final: Any = None,
    pais: Any = None,
) -> Tuple[Optional[bool], bool]:
    city_key = normalize_place_key(ciudad_final)
    province_key = normalize_place_key(provincia_final)
    country_key = normalize_place_key(pais)
    is_uruguay = (
        "uruguay" in {country_key, province_key}
        or city_key in {"punta del este", "maldonado", "montevideo"}
        or province_key == "maldonado"
    )
    if is_uruguay and latitud is not None and longitud is not None:
        min_lat, max_lat, min_lon, max_lon = URUGUAY_BOUNDS
        return min_lat <= latitud <= max_lat and min_lon <= longitud <= max_lon, True

    bounds = CITY_BOUNDS.get(city_key)
    if bounds is None or latitud is None or longitud is None:
        return None, False

    min_lat, max_lat, min_lon, max_lon = bounds
    return min_lat <= latitud <= max_lat and min_lon <= longitud <= max_lon, True


def is_coordinate_valid_for_location(
    lat: Any,
    lon: Any,
    ciudad: Any,
    provincia: Any = None,
    pais: Any = None,
) -> bool:
    try:
        lat_float = float(lat)
        lon_float = float(lon)
    except (TypeError, ValueError):
        return False
    if not (-90 <= lat_float <= 90 and -180 <= lon_float <= 180) or (lat_float == 0 and lon_float == 0):
        return False
    within_bounds, checked = evaluate_city_bounds(lat_float, lon_float, ciudad, provincia, pais)
    return bool(within_bounds) if checked else True


def parse_metadata_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"true", "t", "1", "yes", "y", "si", "sí"}:
        return True
    if normalized in {"false", "f", "0", "no", "n"}:
        return False
    return default


def parse_coordinate_pair(lat: Any, lon: Any) -> Tuple[Optional[float], Optional[float]]:
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None, None


def is_coordinate_inside_argentina(lat: Any, lon: Any) -> bool:
    lat_float, lon_float = parse_coordinate_pair(lat, lon)
    if lat_float is None or lon_float is None:
        return False
    min_lat, max_lat, min_lon, max_lon = ARGENTINA_BOUNDS
    return min_lat <= lat_float <= max_lat and min_lon <= lon_float <= max_lon


def split_address_segments(text: str, row: Dict[str, Any], source: str) -> List[str]:
    cleaned = normalize_address_text(text)
    if source == "direccion_geocoding_limpia":
        city_keys = {
            normalize_place_key(row.get("ciudad_final")),
            normalize_place_key(row.get("provincia_final")),
            "argentina",
        }
        kept_parts = []
        for part in cleaned.split(","):
            part_key = normalize_place_key(part)
            if part_key in city_keys:
                break
            kept_parts.append(part)
        cleaned = ", ".join(kept_parts).strip(" ,") or cleaned

    normalized = re.sub(r"\s*[-–—|•]\s*", " - ", cleaned)
    pieces = []
    for part in re.split(r"\s+-\s+|,", normalized):
        part = normalize_address_text(part)
        if part:
            pieces.append(part)
    if cleaned and not pieces:
        pieces.append(cleaned)
    return pieces


def normalize_address_text(text: Any) -> str:
    value = str(text or "").replace("\u00a0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip(" ,.-")


UI_ADDRESS_BLOCKERS: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bgaler[ií]a\s+de\s+im[aá]genes\b", re.IGNORECASE), "texto_ui_galeria_de_imagenes"),
    (re.compile(r"\bver\s+fotos?\b", re.IGNORECASE), "texto_ui_ver_fotos"),
    (re.compile(r"\bcompartir\b", re.IGNORECASE), "texto_ui_compartir"),
    (re.compile(r"\bcasa\s+central\b", re.IGNORECASE), "texto_ui_casa_central"),
    (re.compile(r"\bpropiedades\s+relacionadas\b", re.IGNORECASE), "texto_ui_propiedades_relacionadas"),
    (re.compile(r"\bcontactate\b", re.IGNORECASE), "texto_ui_contactate"),
    (re.compile(r"\benviar\s+mensaje\b", re.IGNORECASE), "texto_ui_enviar_mensaje"),
    (re.compile(r"\bb[uú]squeda\s+de\s+propiedades\b", re.IGNORECASE), "texto_ui_busqueda_propiedades"),
    (re.compile(r"\btipo\s+de\s+operaci[oó]n\b", re.IGNORECASE), "texto_ui_tipo_operacion"),
    (re.compile(r"\btipo\s+de\s+propiedad\b", re.IGNORECASE), "texto_ui_tipo_propiedad"),
    (re.compile(r"\bseleccione\s+ubicaci[oó]n\b", re.IGNORECASE), "texto_ui_seleccione_ubicacion"),
    (re.compile(r"\bambientes\b", re.IGNORECASE), "texto_ui_ambientes"),
    (re.compile(r"\bhabitaciones\b", re.IGNORECASE), "texto_ui_habitaciones"),
    (re.compile(r"\bgarages\b", re.IGNORECASE), "texto_ui_garages"),
    (re.compile(r"\bavanzado\b", re.IGNORECASE), "texto_ui_avanzado"),
    (re.compile(r"\bbuscar\b", re.IGNORECASE), "texto_ui_buscar"),
]


REAL_ESTATE_NOISE_PATTERNS: List[re.Pattern[str]] = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b\d+\s+dormitorios?\b",
        r"\b(?:un|una|dos|tres|cuatro|cinco|seis)\s+dormitorios?\b",
        r"\bdormitorios?\b",
        r"\bmonoambiente\b",
        r"\bcontra\s*frente\b",
        r"\bcontrafrente\b",
        r"\bfrente\b",
        r"\bbalc[oó]n\b",
        r"\bcocheras?\b",
        r"\bpiscina\b",
        r"\bexcelente\b",
        r"\boportunidad\b",
        r"\bopci[oó]n\b",
        r"\bretasad[ao]\b",
        r"\bestado\b",
        r"\bnuevo\b",
        r"\ba\s+estrenar\b",
    )
]


ROUTE_ADDRESS_RE = re.compile(
    r"\b(?:ruta|rn|rp)\s*(?:nacional|provincial|prov\.?|nac\.?)?\s*\d{1,4}(?:\s*(?:km|kil[oó]metro)\s*\d{1,4})?\b",
    re.IGNORECASE,
)


def ui_address_block_reason(text: Any) -> Optional[str]:
    value = normalize_address_text(text)
    if not value:
        return None
    key = normalize_place_key(value)
    key_reasons = {
        "galeria de imagenes": "texto_ui_galeria_de_imagenes",
        "ver fotos": "texto_ui_ver_fotos",
        "compartir": "texto_ui_compartir",
        "casa central": "texto_ui_casa_central",
        "propiedades relacionadas": "texto_ui_propiedades_relacionadas",
        "contactate": "texto_ui_contactate",
        "enviar mensaje": "texto_ui_enviar_mensaje",
        "busqueda de propiedades": "texto_ui_busqueda_propiedades",
        "tipo de operacion": "texto_ui_tipo_operacion",
        "tipo de propiedad": "texto_ui_tipo_propiedad",
        "seleccione ubicacion": "texto_ui_seleccione_ubicacion",
        "ambientes": "texto_ui_ambientes",
        "habitaciones": "texto_ui_habitaciones",
        "garages": "texto_ui_garages",
        "avanzado": "texto_ui_avanzado",
        "buscar": "texto_ui_buscar",
    }
    for marker, reason in key_reasons.items():
        if marker in key:
            return reason
    for pattern, reason in UI_ADDRESS_BLOCKERS:
        if pattern.search(value):
            return reason
    return None


def strip_ui_noise(text: str) -> str:
    value = normalize_address_text(text)
    for pattern, _reason in UI_ADDRESS_BLOCKERS:
        value = pattern.sub(" ", value)
    value = re.sub(r"\s*[|•]\s*", " ", value)
    for pattern in (
        r"\bgaler\S*\s+de\s+im\S*genes\b",
        r"\bver\s+fotos?\b",
        r"\bcompartir\b",
        r"\bcasa\s+central\b",
        r"\bpropiedades\s+relacionadas\b",
        r"\bcontactate\b",
        r"\benviar\s+mensaje\b",
        r"\bb\S*squeda\s+de\s+propiedades\b",
        r"\btipo\s+de\s+operaci\S*n\b",
        r"\btipo\s+de\s+propiedad\b",
        r"\bseleccione\s+ubicaci\S*n\b",
        r"\bambientes\b",
        r"\bhabitaciones\b",
        r"\bgarages\b",
        r"\bavanzado\b",
        r"\bbuscar\b",
    ):
        value = re.sub(pattern, " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*[.]{1,}\s*", " ", value)
    return normalize_address_text(value)


def strip_real_estate_noise(text: str) -> str:
    value = normalize_address_text(text)
    for pattern in REAL_ESTATE_NOISE_PATTERNS:
        value = pattern.sub(" ", value)
    value = re.sub(r"\s*[.]{1,}\s*", " ", value)
    value = re.sub(r"\s{2,}", " ", value)
    return normalize_address_text(value)


def is_route_address(value: str) -> bool:
    return bool(ROUTE_ADDRESS_RE.search(normalize_address_text(value)))


def has_reliable_location_context(row: Dict[str, Any]) -> bool:
    ciudad = normalize_place_key(row.get("ciudad_final") or row.get("ciudad"))
    provincia = normalize_place_key(row.get("provincia_final") or row.get("provincia"))
    if not ciudad or not provincia:
        return False
    if ciudad in {"argentina", "santa fe argentina", "buenos aires argentina"}:
        return False
    return True


KNOWN_LOCALITIES: List[Tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\bvilla\s+constituci[oÃ³]n\b", re.IGNORECASE), "Villa Constitución", "Santa Fe"),
    (re.compile(r"\brosario\b", re.IGNORECASE), "Rosario", "Santa Fe"),
    (re.compile(r"\bsanta\s+fe\b", re.IGNORECASE), "Santa Fe", "Santa Fe"),
    (re.compile(r"\bfunes\b", re.IGNORECASE), "Funes", "Santa Fe"),
    (re.compile(r"\brold[aÃ¡]n\b", re.IGNORECASE), "Roldán", "Santa Fe"),
    (re.compile(r"\bsan\s+jos[eÃ©]\s+del\s+rinc[oÃ³]n\b", re.IGNORECASE), "San José del Rincón", "Santa Fe"),
    (re.compile(r"\bpueblo\s+esther\b", re.IGNORECASE), "Pueblo Esther", "Santa Fe"),
    (re.compile(r"\brafaela\b", re.IGNORECASE), "Rafaela", "Santa Fe"),
]


def detect_city_in_raw(text: Any, row: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    raw = normalize_address_text(text)
    if not raw:
        return None, None
    key = normalize_place_key(raw)
    key_localities = [
        ("villa constitucion", "Villa Constitución", "Santa Fe"),
        ("rosario", "Rosario", "Santa Fe"),
        ("san jose del rincon", "San José del Rincón", "Santa Fe"),
        ("pueblo esther", "Pueblo Esther", "Santa Fe"),
        ("roldan", "Roldán", "Santa Fe"),
        ("funes", "Funes", "Santa Fe"),
        ("rafaela", "Rafaela", "Santa Fe"),
    ]
    for marker, city, province in key_localities:
        if marker in key:
            return city, province
    for pattern, city, province in KNOWN_LOCALITIES:
        if pattern.search(raw):
            return city, province

    row_city = str(row.get("ciudad_final") or row.get("ciudad") or "").strip()
    row_province = str(row.get("provincia_final") or row.get("provincia") or "").strip()
    if row_city and normalize_place_key(row_city) in key:
        return row_city, row_province or None
    return None, None


def useful_context_value(value: Any) -> str:
    text = normalize_address_text(value)
    if not text:
        return ""
    if ui_address_block_reason(text):
        return ""
    key = normalize_place_key(text)
    if key in {
        "argentina",
        "santa fe argentina",
        "buenos aires argentina",
        "seleccione ubicacion",
        "sin barrio",
        "sin dato",
    }:
        return ""
    return text


def build_query_from_parts(base: str, city: Any, province: Any, country: Any = "Argentina") -> str:
    base_clean = normalize_address_text(base)
    city_clean = normalize_address_text(city)
    province_clean = normalize_address_text(province)
    country_clean = normalize_address_text(country) or "Argentina"
    parts = [base_clean]
    lower = base_clean.lower()
    if city_clean and city_clean.lower() not in lower:
        parts.append(city_clean)
    if province_clean and province_clean.lower() not in lower:
        parts.append(province_clean)
    if country_clean and country_clean.lower() not in lower:
        parts.append(country_clean)
    return re.sub(r"\s+", " ", ", ".join(part for part in parts if part)).strip(" ,")


def strip_real_estate_prefixes(text: str) -> str:
    value = normalize_address_text(text)
    prefixes = [
        r"venta",
        r"alquiler",
        r"en venta",
        r"en alquiler",
        r"departamento",
        r"depto\.?",
        r"monoambiente",
        r"casa al frente a reciclar",
        r"casa",
        r"cochera",
        r"local",
        r"loft en",
        r"loft",
        r"piso exclusivo",
        r"piso",
        r"oficina",
        r"terreno",
        r"lote",
        r"premium",
        r"\d+\s+dormitorios?\.?",
        r"\d+\s+ambientes?\.?",
    ]
    pattern = re.compile(r"^(?:" + "|".join(prefixes) + r")\b\s*", flags=re.IGNORECASE)
    previous = None
    while previous != value:
        previous = value
        value = pattern.sub("", value).strip(" ,.-")
    return normalize_address_text(value)


def strip_unit_suffix(text: str) -> str:
    value = normalize_address_text(text)
    suffix_patterns = [
        r"\s+(?:piso|p)\s*\d{1,2}\s*[A-Za-z]?$",
        r"\s+(?:depto|dpto|dto|unidad|uf)\s*[A-Za-z0-9]+$",
        r"\s+(?:pb|planta baja|ss)$",
        r"\s+\d{1,2}\s+[A-Za-z]$",
    ]
    for pattern in suffix_patterns:
        value = re.sub(pattern, "", value, flags=re.IGNORECASE).strip(" ,.-")
    return normalize_address_text(value)


def extract_street_number_address(segment: str) -> Optional[str]:
    value = strip_ui_noise(segment)
    value = strip_unit_suffix(strip_real_estate_prefixes(value))
    value = strip_real_estate_noise(value)
    value = strip_real_estate_prefixes(value)
    value = re.sub(r"\b(?:piso|depto|dpto|dto|unidad|uf)\b.*$", "", value, flags=re.IGNORECASE)
    value = normalize_address_text(value)

    if not value:
        return None

    route_match = ROUTE_ADDRESS_RE.search(value)
    if route_match:
        route_value = normalize_address_text(route_match.group(0))
        if not is_generic_address(route_value):
            return route_value

    matches = list(re.finditer(r"\b\d{2,5}\b", value))
    if not matches:
        return None

    house_number_match = matches[-1]
    base = value[:house_number_match.end()]
    base = strip_unit_suffix(normalize_address_text(base))

    if is_generic_address(base):
        return None
    return base


def is_generic_address(value: str) -> bool:
    text = normalize_address_text(value)
    key = normalize_place_key(text)
    if not text or key in {"argentina", "rosario", "santa fe", "rosario santa fe argentina"}:
        return True
    if "casa central" in key:
        return True
    if ui_address_block_reason(text):
        return True
    if re.fullmatch(r"\d{1,5}", text):
        return True
    if not re.search(r"\b\d{2,5}\b", text):
        return True
    if not re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]", text):
        return True
    generic_keys = {
        "piso exclusivo",
        "loft",
        "loft en",
        "casa",
        "departamento",
        "depto",
        "monoambiente",
        "cochera",
        "local",
        "oficina",
    }
    if key in generic_keys:
        return True
    return False


def score_address_candidate(candidate: str, segment_index: int, source: str) -> int:
    score = 0
    numbers = [int(match.group(0)) for match in re.finditer(r"\b\d{2,5}\b", candidate)]
    if numbers and numbers[-1] >= 100:
        score += 10
    elif numbers:
        score += 3
    if source == "direccion_limpia":
        score += 5
    elif source == "direccion_geocoding_limpia":
        score += 3
    elif source == "titulo":
        score += 1
    score += min(segment_index, 4)
    if re.search(r"\b(?:monoambiente|loft|cochera|departamento|casa|local|piso)\b", candidate, flags=re.IGNORECASE):
        score -= 3
    return score


def prepare_address_for_geocoding(row: Dict[str, Any]) -> AddressCleaningResult:
    if isinstance(row.get("_address_cleaning"), AddressCleaningResult):
        return row["_address_cleaning"]

    sources = [
        ("direccion", row.get("direccion")),
        ("direccion_limpia", row.get("direccion_limpia")),
        ("direccion_geocoding_limpia", row.get("direccion_geocoding_limpia")),
        ("titulo", row.get("titulo")),
        ("barrio", row.get("barrio")),
    ]
    best: Optional[Tuple[int, str, str, str, str, str, Optional[str], Optional[str], bool]] = None
    skipped_sources: List[Dict[str, str]] = []
    evaluated_sources: List[Dict[str, str]] = []
    primary_raw_value = ""

    for source, raw_value in sources:
        raw_text = normalize_address_text(raw_value)
        if not raw_text:
            continue
        if not primary_raw_value:
            primary_raw_value = raw_text
        detected_city, detected_province = detect_city_in_raw(raw_text, row)
        blocked_reason = ui_address_block_reason(raw_text)
        cleaned_source = strip_ui_noise(raw_text) if blocked_reason else raw_text
        evaluated_sources.append({
            "source": source,
            "raw_value": raw_text[:240],
            "cleaned_value": cleaned_source[:240],
            "ui_noise_reason": blocked_reason or "",
            "detected_city": detected_city or "",
            "detected_province": detected_province or "",
        })
        if blocked_reason:
            skipped_sources.append({
                "source": source,
                "reason": f"{blocked_reason}_limpiado_para_buscar_direccion",
                "raw_value": raw_text[:240],
            })
        if not cleaned_source:
            continue
        segments = split_address_segments(cleaned_source, row, source)
        for index, segment in enumerate(segments):
            blocked_segment_reason = ui_address_block_reason(segment)
            if blocked_segment_reason:
                skipped_sources.append({
                    "source": source,
                    "reason": f"{blocked_segment_reason}_segmento_omitido",
                    "raw_value": segment[:240],
                })
                continue
            candidate = extract_street_number_address(segment)
            if not candidate:
                continue
            is_route = is_route_address(candidate)
            if is_route and not has_reliable_location_context(row):
                skipped_sources.append({
                    "source": source,
                    "reason": "ruta_sin_contexto_ciudad_provincia_confiable",
                    "raw_value": segment[:240],
                })
                continue
            score = score_address_candidate(candidate, index, source)
            quality = "media" if is_route else "alta"
            reason = "ruta_geocodificable_con_contexto" if is_route else "calle_altura_detectada"
            if blocked_reason:
                score -= 4
                quality = "media" if not is_route else "media"
                reason = f"{reason}_tras_limpiar_texto_ui"
            if best is None or score > best[0]:
                best = (
                    score,
                    candidate,
                    source,
                    raw_text,
                    quality,
                    reason,
                    detected_city,
                    detected_province,
                    is_route,
                )

    if best is not None:
        _, cleaned_address, source, raw_value, quality, reason, detected_city, detected_province, is_route = best
        city_for_query = detected_city or row.get("ciudad_final") or row.get("ciudad")
        province_for_query = detected_province or row.get("provincia_final") or row.get("provincia")
        proposed_query = build_query_from_parts(cleaned_address, city_for_query, province_for_query, row.get("pais"))
        readiness = "geocoding_ready_review" if is_route or quality != "alta" else "geocoding_ready_safe"
        result = AddressCleaningResult(
            cleaned_address=cleaned_address,
            is_geocodable=readiness == "geocoding_ready_safe",
            quality=quality,
            reason=reason,
            source=source,
            raw_value=raw_value,
            skipped_sources=skipped_sources,
            evaluated_sources=evaluated_sources,
            readiness=readiness,
            detected_city=detected_city,
            detected_province=detected_province,
            proposed_query=proposed_query,
        )
        row["_address_cleaning"] = result
        return result

    barrio = useful_context_value(row.get("barrio"))
    ciudad = useful_context_value(row.get("ciudad_final") or row.get("ciudad"))
    provincia = useful_context_value(row.get("provincia_final") or row.get("provincia"))
    pais = useful_context_value(row.get("pais")) or "Argentina"
    if barrio and ciudad and provincia:
        proposed_query = build_query_from_parts(barrio, ciudad, provincia, pais)
        result = AddressCleaningResult(
            cleaned_address=barrio,
            is_geocodable=False,
            quality="media",
            reason="sin_calle_altura_fallback_barrio_ciudad",
            source="barrio_ciudad",
            raw_value=primary_raw_value or barrio,
            skipped_sources=skipped_sources,
            evaluated_sources=evaluated_sources,
            readiness="geocoding_ready_review",
            detected_city=ciudad,
            detected_province=provincia,
            proposed_query=proposed_query,
        )
        row["_address_cleaning"] = result
        return result
    if ciudad and provincia:
        proposed_query = build_query_from_parts(ciudad, "", provincia, pais)
        result = AddressCleaningResult(
            cleaned_address=ciudad,
            is_geocodable=False,
            quality="baja",
            reason="sin_calle_altura_fallback_ciudad_provincia",
            source="ciudad_provincia",
            raw_value=primary_raw_value or ciudad,
            skipped_sources=skipped_sources,
            evaluated_sources=evaluated_sources,
            readiness="geocoding_ready_review",
            detected_city=ciudad,
            detected_province=provincia,
            proposed_query=proposed_query,
        )
        row["_address_cleaning"] = result
        return result

    raw_fallback = primary_raw_value or normalize_address_text(
        row.get("direccion")
        or row.get("direccion_limpia")
        or row.get("direccion_geocoding_limpia")
        or row.get("barrio")
        or row.get("ciudad_final")
        or row.get("titulo")
        or ""
    )
    result = AddressCleaningResult(
        cleaned_address="",
        is_geocodable=False,
        quality="muy_baja",
        reason=(skipped_sources[0]["reason"] if skipped_sources else "sin_calle_altura_confiable"),
        source="none",
        raw_value=raw_fallback,
        skipped_sources=skipped_sources,
        evaluated_sources=evaluated_sources,
        readiness="geocoding_not_ready",
        proposed_query="",
    )
    row["_address_cleaning"] = result
    return result


def normalize_query(row: Dict[str, Any]) -> str:
    address_cleaning = prepare_address_for_geocoding(row)
    if address_cleaning.readiness != "geocoding_ready_safe":
        return ""

    if address_cleaning.proposed_query:
        return address_cleaning.proposed_query

    ciudad = address_cleaning.detected_city or row.get("ciudad_final") or row.get("ciudad")
    provincia = address_cleaning.detected_province or row.get("provincia_final") or row.get("provincia")
    return build_query_from_parts(address_cleaning.cleaned_address, ciudad, provincia, row.get("pais"))


def build_query_variants(row: Dict[str, Any]) -> List[str]:
    primary = normalize_query(row)
    if not primary:
        return []

    variants = [primary]
    replacements = [
        (r"\bPte\.?\s+Roca\b", "Presidente Roca"),
        (r"\bPte\.?\s+Roca\b", "Roca"),
        (r"\b1ro\.?\s+de\s+Mayo\b", "Primero de Mayo"),
        (r"\b1ro\.?\s+de\s+Mayo\b", "1 de Mayo"),
        ("\\b1(?:\\u00b0|\\u00ba)\\s+de\\s+Mayo\\b", "Primero de Mayo"),
        ("\\b1(?:\\u00b0|\\u00ba)\\s+de\\s+Mayo\\b", "1 de Mayo"),
    ]

    for pattern, replacement in replacements:
        if re.search(pattern, primary, flags=re.IGNORECASE):
            variants.append(re.sub(pattern, replacement, primary, flags=re.IGNORECASE))

    return _dedupe_queries(variants)


def _dedupe_queries(queries: List[str]) -> List[str]:
    seen = set()
    unique: List[str] = []
    for query in queries:
        normalized = re.sub(r"\s+", " ", query).strip(" ,")
        key = normalized.lower()
        if normalized and key not in seen:
            unique.append(normalized)
            seen.add(key)
    return unique


def classify_geocoding_quality(status: str, precision: Optional[str]) -> Tuple[str, bool, bool]:
    if status != "success":
        return "low", False, True

    normalized = str(precision or "").lower()
    if normalized == "exact":
        return "high", True, False
    if normalized in {"street", "interpolated"}:
        return "medium", True, False
    if normalized == "area":
        return "low", False, True
    return "low", False, True


def enrich_raw_response(
    raw_response: Any,
    *,
    result: GeocodingResult,
    primary_query: str,
    matched_query: Optional[str],
    attempted_queries: List[str],
    ciudad_final: Any = None,
    provincia_final: Any = None,
    pais: Any = None,
    address_cleaning: Optional[AddressCleaningResult] = None,
) -> Dict[str, Any]:
    confidence_level, should_apply, needs_review = classify_geocoding_quality(
        result.status,
        result.precision_geocoding,
    )
    within_city_bounds, city_bounds_checked = evaluate_city_bounds(
        result.latitud,
        result.longitud,
        ciudad_final,
        provincia_final,
        pais,
    )
    if result.status == "success" and city_bounds_checked and within_city_bounds is False:
        confidence_level = "low"
        should_apply = False
        needs_review = True

    quality_metadata = {
        "confidence_level": confidence_level,
        "should_apply_to_property": should_apply,
        "within_city_bounds": within_city_bounds,
        "city_bounds_checked": city_bounds_checked,
        "location_validation": (
            "within_city_bounds"
            if city_bounds_checked and within_city_bounds is True
            else "coordenada_descartada_por_outlier"
            if city_bounds_checked and within_city_bounds is False
            else "no_rule"
        ),
        "ciudad_final": ciudad_final,
        "provincia_final": provincia_final,
        "pais": pais,
        "calidad_geocoding": address_cleaning.quality if address_cleaning else None,
        "geocoding_readiness": address_cleaning.readiness if address_cleaning else None,
        "direccion_propuesta": address_cleaning.proposed_query if address_cleaning else None,
        "ciudad_detectada_en_raw": address_cleaning.detected_city if address_cleaning else None,
        "provincia_detectada_en_raw": address_cleaning.detected_province if address_cleaning else None,
        "address_cleaning": address_cleaning.to_metadata() if address_cleaning else None,
        "needs_review": needs_review,
        "quality_flag": "baja_confianza" if needs_review else "aplicable",
        "primary_query": primary_query,
        "matched_query": matched_query,
        "attempted_queries": attempted_queries,
        "precision_geocoding": result.precision_geocoding,
    }

    if isinstance(raw_response, dict):
        enriched = dict(raw_response)
        enriched["inmocapital"] = quality_metadata
        enriched["_inmocapital"] = quality_metadata
        return enriched

    return {
        "provider_response": raw_response,
        "inmocapital": quality_metadata,
        "_inmocapital": quality_metadata,
    }


def get_inmocapital_metadata(raw_response: Any) -> Dict[str, Any]:
    if not isinstance(raw_response, dict):
        return {}
    metadata = raw_response.get("inmocapital")
    if isinstance(metadata, dict):
        return metadata
    legacy_metadata = raw_response.get("_inmocapital")
    return legacy_metadata if isinstance(legacy_metadata, dict) else {}


def get_geocoding_apply_decision(
    row: Dict[str, Any],
    city_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    raw_response = row.get("raw_response")
    metadata = get_inmocapital_metadata(raw_response)
    skip_reasons: List[str] = []

    status = str(row.get("status") or "").lower()
    if status != "success":
        skip_reasons.append("status_not_success")

    latitud, longitud = parse_coordinate_pair(row.get("latitud"), row.get("longitud"))
    if latitud is None or longitud is None:
        skip_reasons.append("missing_coordinates")
    elif not is_coordinate_inside_argentina(latitud, longitud):
        skip_reasons.append("outside_argentina_bounds")

    confidence_level = metadata.get("confidence_level")
    if not confidence_level:
        confidence_level, _, _ = classify_geocoding_quality(
            str(row.get("status") or ""),
            row.get("precision_geocoding"),
        )

    if "should_apply_to_property" in metadata:
        should_apply = parse_metadata_bool(metadata.get("should_apply_to_property"))
    else:
        _, should_apply, _ = classify_geocoding_quality(
            str(row.get("status") or ""),
            row.get("precision_geocoding"),
        )

    needs_review = parse_metadata_bool(metadata.get("needs_review"), default=False)
    quality_flag = str(metadata.get("quality_flag") or "").strip().lower()
    location_validation = str(metadata.get("location_validation") or "").strip().lower()
    within_city_bounds = metadata.get("within_city_bounds")
    city_bounds_checked = metadata.get("city_bounds_checked")
    if city_bounds_checked is None:
        city = metadata.get("ciudad_final")
        province = metadata.get("provincia_final")
        pais = metadata.get("pais")
        if city_context:
            city = city or city_context.get("ciudad") or city_context.get("ciudad_final")
            province = province or city_context.get("provincia") or city_context.get("provincia_final")
            pais = pais or city_context.get("pais")
        within_city_bounds, city_bounds_checked = evaluate_city_bounds(latitud, longitud, city, province, pais)
        if city_bounds_checked and within_city_bounds is False:
            confidence_level = "low"
            should_apply = False
    if not location_validation:
        if within_city_bounds is True:
            location_validation = "within_city_bounds"
        elif within_city_bounds is False:
            location_validation = "outside_city_bounds"

    confidence_allowed = str(confidence_level or "").lower() in {"high", "medium"}
    if not should_apply:
        skip_reasons.append("should_apply_false")
    if needs_review:
        skip_reasons.append("needs_review_true")
    if quality_flag == "baja_confianza":
        skip_reasons.append("quality_flag_baja_confianza")
    if location_validation != "within_city_bounds":
        skip_reasons.append("location_validation_not_within_city_bounds")
    if not confidence_allowed:
        skip_reasons.append("confidence_not_allowed")

    can_apply = not skip_reasons
    return {
        "can_apply": can_apply,
        "confidence_level": confidence_level,
        "should_apply_to_property": should_apply,
        "needs_review": needs_review,
        "quality_flag": quality_flag or None,
        "location_validation": location_validation or None,
        "within_city_bounds": within_city_bounds,
        "city_bounds_checked": city_bounds_checked,
        "skip_reason": ",".join(dict.fromkeys(skip_reasons)) or None,
    }


def should_apply_geocoding_result(
    row: Dict[str, Any],
    city_context: Optional[Dict[str, Any]] = None,
) -> bool:
    return bool(get_geocoding_apply_decision(row, city_context).get("can_apply"))


def geocode_with_fallbacks(
    provider: NominatimProvider,
    queries: List[str],
    row: Dict[str, Any],
) -> Tuple[GeocodingResult, List[str]]:
    attempted_queries: List[str] = []
    last_result: Optional[GeocodingResult] = None
    best_result: Optional[GeocodingResult] = None
    best_query: Optional[str] = None
    best_rank = -1
    primary_query = queries[0] if queries else ""
    address_cleaning = prepare_address_for_geocoding(row)

    for query in queries:
        attempted_queries.append(query)
        result = provider.geocode(query)
        result.attempted_queries = list(attempted_queries)

        if result.status == "success":
            confidence_level, _, _ = classify_geocoding_quality(
                result.status,
                result.precision_geocoding,
            )
            within_city_bounds, city_bounds_checked = evaluate_city_bounds(
                result.latitud,
                result.longitud,
                row.get("ciudad_final"),
                row.get("provincia_final"),
                row.get("pais"),
            )
            if city_bounds_checked and within_city_bounds is False:
                confidence_level = "low"
            rank = {"high": 3, "medium": 2, "low": 1}.get(confidence_level, 0)
            if rank > best_rank:
                best_result = result
                best_query = query
                best_rank = rank
            if rank == 3:
                break

        last_result = result

    if best_result is not None:
        best_result.matched_query = best_query
        best_result.attempted_queries = list(attempted_queries)
        best_result.raw_response = enrich_raw_response(
            best_result.raw_response,
            result=best_result,
            primary_query=primary_query,
            matched_query=best_query,
            attempted_queries=list(attempted_queries),
            ciudad_final=row.get("ciudad_final"),
            provincia_final=row.get("provincia_final"),
            pais=row.get("pais"),
            address_cleaning=address_cleaning,
        )
        return best_result, attempted_queries

    if last_result is None:
        last_result = GeocodingResult(None, None, None, provider.name, None, "error", "Sin direccion para geocodificar")

    last_result.matched_query = None
    last_result.attempted_queries = list(attempted_queries)
    last_result.raw_response = enrich_raw_response(
        last_result.raw_response,
        result=last_result,
        primary_query=primary_query,
        matched_query=None,
        attempted_queries=list(attempted_queries),
        ciudad_final=row.get("ciudad_final"),
        provincia_final=row.get("provincia_final"),
        pais=row.get("pais"),
        address_cleaning=address_cleaning,
    )
    return last_result, attempted_queries


def build_payload(row: Dict[str, Any], query: str, result: GeocodingResult) -> Dict[str, Any]:
    latitud = result.latitud
    longitud = result.longitud
    status = result.status
    error_message = result.error_message
    metadata = get_inmocapital_metadata(result.raw_response)
    if (
        result.status == "success"
        and metadata.get("city_bounds_checked")
        and metadata.get("within_city_bounds") is False
    ):
        logger.info(
            "coordenada_descartada_por_outlier | propiedad_id=%s | ciudad=%s | provincia=%s | lat=%s | lon=%s",
            row.get("propiedad_id"),
            row.get("ciudad_final"),
            row.get("provincia_final"),
            latitud,
            longitud,
        )
        latitud = None
        longitud = None
        status = "error"
        error_message = "geocoding_coordinates_discarded_by_outlier_validation"
    elif result.status == "success" and not is_coordinate_inside_argentina(latitud, longitud):
        logger.info(
            "coordenada_descartada_por_bounds_argentina | propiedad_id=%s | lat=%s | lon=%s",
            row.get("propiedad_id"),
            latitud,
            longitud,
        )
        latitud = None
        longitud = None
        status = "error"
        error_message = "geocoding_coordinates_outside_argentina_bounds"

    if status == "success" and (latitud is None or longitud is None):
        status = "error"
        error_message = error_message or "geocoding_coordinates_missing"

    return {
        "propiedad_id": row.get("propiedad_id"),
        "direccion_geocoding": query,
        "latitud": latitud,
        "longitud": longitud,
        "precision_geocoding": result.precision_geocoding,
        "proveedor": result.proveedor,
        "raw_response": result.raw_response,
        "status": status,
        "error_message": error_message,
    }


def run(limit: int, dry_run: bool = False) -> None:
    client = SupabaseGeocodingClient(SUPABASE_URL, SUPABASE_KEY)
    provider = NominatimProvider()
    rows = client.get_pending_batch(limit)

    if not rows:
        logger.info("No hay propiedades pendientes en v_next_geocoding_batch.")
        return

    logger.info("Propiedades pendientes recibidas: %d | dry_run=%s", len(rows), dry_run)
    ok = 0
    failed = 0
    skipped = 0

    for row in rows:
        propiedad_id = row.get("propiedad_id")
        address_cleaning = prepare_address_for_geocoding(row)
        queries = build_query_variants(row)
        query = queries[0] if queries else ""
        display_query = query or address_cleaning.proposed_query
        evaluated_sources = [
            item.get("source", "")
            for item in (address_cleaning.evaluated_sources or [])
            if item.get("source")
        ]
        logger.info(
            "propiedad_id=%s | raw=%s | fuentes=%s | fuente_elegida=%s | direccion_final=%s | ciudad_final=%s | ciudad_detectada_en_raw=%s | calidad_limpieza=%s | readiness=%s | motivo=%s | variantes=%d",
            propiedad_id,
            address_cleaning.raw_value or "-",
            ",".join(evaluated_sources) or "-",
            address_cleaning.source,
            display_query or "-",
            row.get("ciudad_final") or "-",
            address_cleaning.detected_city or "-",
            address_cleaning.quality,
            address_cleaning.readiness,
            address_cleaning.reason,
            len(queries),
        )

        if not query:
            if address_cleaning.readiness == "geocoding_ready_review":
                logger.info(
                    "%s status=review | no se geocodifica en modo seguro inicial | propuesta=%s | raw=%s | fuentes_evaluadas=%s",
                    "[dry-run]" if dry_run else "skip",
                    address_cleaning.proposed_query or "-",
                    address_cleaning.raw_value or "-",
                    json.dumps(address_cleaning.evaluated_sources or [], ensure_ascii=False),
                )
                skipped += 1
                continue
            result = GeocodingResult(
                None,
                None,
                None,
                provider.name,
                None,
                "error",
                f"direccion_no_geocodificable: {address_cleaning.reason}",
            )
            result.raw_response = enrich_raw_response(
                result.raw_response,
                result=result,
                primary_query="",
                matched_query=None,
                attempted_queries=[],
                ciudad_final=row.get("ciudad_final"),
                provincia_final=row.get("provincia_final"),
                pais=row.get("pais"),
                address_cleaning=address_cleaning,
            )
            if dry_run:
                logger.info(
                    "[dry-run] status=error | %s | raw=%s | skipped_sources=%s",
                    result.error_message,
                    address_cleaning.raw_value or "-",
                    json.dumps(address_cleaning.skipped_sources or [], ensure_ascii=False),
                )
                failed += 1
                continue
            blocked_query = normalize_address_text(
                row.get("direccion_geocoding_limpia")
                or row.get("direccion_limpia")
                or address_cleaning.raw_value
            )
            if blocked_query:
                existing = client.existing_result(propiedad_id, blocked_query)
                if existing:
                    skipped += 1
                    logger.info("skip=duplicate | status_existente=%s", existing.get("status"))
                    continue
            client.save_result(build_payload(row, blocked_query, result))
            failed += 1
            continue

        existing = client.existing_result(propiedad_id, query)
        if existing:
            skipped += 1
            logger.info("skip=duplicate | status_existente=%s", existing.get("status"))
            continue

        if dry_run:
            logger.info(
                "[dry-run] se geocodificaria con proveedor=%s | urls_probadas=%s",
                provider.name,
                json.dumps(queries, ensure_ascii=False),
            )
            continue

        result, attempted_queries = geocode_with_fallbacks(provider, queries, row)
        payload = build_payload(row, query, result)
        save_status = client.save_result(payload)
        payload_status = payload.get("status")
        quality_metadata = (
            get_inmocapital_metadata(payload.get("raw_response"))
        )

        if payload_status == "success":
            ok += 1
            logger.info(
                "status=success | lat=%.6f | lon=%.6f | precision=%s | confidence=%s | apply=%s | bounds=%s | matched_query=%s | save=%s",
                payload.get("latitud"),
                payload.get("longitud"),
                result.precision_geocoding,
                quality_metadata.get("confidence_level"),
                quality_metadata.get("should_apply_to_property"),
                quality_metadata.get("within_city_bounds"),
                result.matched_query or query,
                save_status,
            )
        else:
            failed += 1
            logger.info(
                "status=error | error=%s | apply=%s | intentos=%d | save=%s",
                payload.get("error_message"),
                quality_metadata.get("should_apply_to_property"),
                len(attempted_queries),
                save_status,
            )

    logger.info("Geocoding finalizado | success=%d | error=%d | skipped=%d", ok, failed, skipped)


def apply_valid_results(limit: int, dry_run: bool = False) -> None:
    client = SupabaseGeocodingClient(SUPABASE_URL, SUPABASE_KEY)
    rows = client.get_success_results_batch(limit)

    if not rows:
        logger.info("No hay resultados exitosos en geocoding_results para aplicar.")
        return

    logger.info("Resultados candidatos recibidos: %d | dry_run=%s", len(rows), dry_run)
    applicable = 0
    applied = 0
    skipped = 0
    failed = 0

    for row in rows:
        result_id = row.get("id")
        propiedad_id = row.get("propiedad_id")
        precision = row.get("precision_geocoding")
        city_context = client.get_property_location_context(propiedad_id)
        decision = get_geocoding_apply_decision(row, city_context)
        logger.info(
            "geocoding_result_id=%s | propiedad_id=%s | precision=%s | confidence=%s | should_apply=%s | location_validation=%s | quality_flag=%s | needs_review=%s | bounds=%s | bounds_checked=%s | skip_reason=%s",
            result_id,
            propiedad_id,
            precision,
            decision.get("confidence_level"),
            decision.get("should_apply_to_property"),
            decision.get("location_validation"),
            decision.get("quality_flag"),
            decision.get("needs_review"),
            decision.get("within_city_bounds"),
            decision.get("city_bounds_checked"),
            decision.get("skip_reason") or "-",
        )

        if not decision.get("can_apply"):
            skipped += 1
            logger.info(
                "skip=%s | no se aplica a propiedades.id=%s",
                decision.get("skip_reason") or "not_applicable",
                propiedad_id,
            )
            continue
        applicable += 1

        try:
            latitud = float(row["latitud"])
            longitud = float(row["longitud"])
        except (KeyError, TypeError, ValueError) as exc:
            failed += 1
            logger.info("status=error | coordenadas invalidas | %s", exc)
            continue

        if not is_coordinate_valid_for_location(
            latitud,
            longitud,
            city_context.get("ciudad") or city_context.get("ciudad_final"),
            city_context.get("provincia") or city_context.get("provincia_final"),
            city_context.get("pais"),
        ):
            skipped += 1
            logger.info(
                "skip=coordenada_descartada_por_outlier | propiedad_id=%s | ciudad=%s | provincia=%s | lat=%.6f | lon=%.6f",
                propiedad_id,
                city_context.get("ciudad") or city_context.get("ciudad_final"),
                city_context.get("provincia") or city_context.get("provincia_final"),
                latitud,
                longitud,
            )
            continue

        if dry_run:
            applied += 1
            logger.info("[dry-run] se actualizaria propiedades.id=%s | lat=%.6f | lon=%.6f", propiedad_id, latitud, longitud)
            continue

        try:
            save_status = client.update_property_coordinates(propiedad_id, latitud, longitud)
            applied += 1
            logger.info("status=%s | propiedades.id=%s | lat=%.6f | lon=%.6f", save_status, propiedad_id, latitud, longitud)
        except RuntimeError as exc:
            failed += 1
            logger.info("status=error | no se pudo actualizar propiedades.id=%s | %s", propiedad_id, exc)

    logger.info(
        "Aplicacion finalizada | candidates=%d | applicable=%d | updated=%d | skipped=%d | error=%d",
        len(rows),
        applicable,
        applied,
        skipped,
        failed,
    )


def validate_applied_results(limit: int) -> None:
    client = SupabaseGeocodingClient(SUPABASE_URL, SUPABASE_KEY)
    rows = client.get_properties_with_coordinates(limit)

    if not rows:
        logger.info("No hay propiedades con coordenadas para validar.")
        return

    logger.info("Propiedades con coordenadas recibidas: %d", len(rows))
    inside = 0
    outside = 0
    no_bounds = 0
    invalid = 0

    for row in rows:
        propiedad_id = row.get("id")
        ciudad = row.get("ciudad")
        provincia = row.get("provincia")
        pais = row.get("pais")
        try:
            latitud = float(row["latitud"])
            longitud = float(row["longitud"])
        except (KeyError, TypeError, ValueError) as exc:
            invalid += 1
            logger.info("propiedad_id=%s | status=invalid_coordinates | %s", propiedad_id, exc)
            continue

        within_city_bounds, city_bounds_checked = evaluate_city_bounds(latitud, longitud, ciudad, provincia, pais)
        if not city_bounds_checked:
            no_bounds += 1
            logger.info(
                "propiedad_id=%s | ciudad=%s | provincia=%s | status=no_bounds_configured | lat=%.6f | lon=%.6f",
                propiedad_id,
                ciudad,
                provincia,
                latitud,
                longitud,
            )
            continue

        if within_city_bounds:
            inside += 1
            logger.info(
                "propiedad_id=%s | ciudad=%s | status=within_bounds | lat=%.6f | lon=%.6f",
                propiedad_id,
                ciudad,
                latitud,
                longitud,
            )
            continue

        outside += 1
        logger.warning(
            "propiedad_id=%s | ciudad=%s | provincia=%s | status=outside_bounds | direccion=%s | lat=%.6f | lon=%.6f",
            propiedad_id,
            ciudad,
            provincia,
            row.get("direccion") or "-",
            latitud,
            longitud,
        )

    logger.info(
        "Validacion finalizada | within_bounds=%d | outside_bounds=%d | no_bounds=%d | invalid=%d",
        inside,
        outside,
        no_bounds,
        invalid,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Geocoder de Inmocapital basado en cola Supabase")
    parser.add_argument("--limit", type=int, default=20, help="Cantidad maxima de propiedades a leer de v_next_geocoding_batch")
    parser.add_argument("--dry-run", action="store_true", help="Leer pendientes y mostrar acciones sin llamar proveedor ni guardar")
    parser.add_argument(
        "--apply-valid-results",
        action="store_true",
        help="Aplicar a propiedades solo resultados con should_apply_to_property=true",
    )
    parser.add_argument(
        "--validate-applied-results",
        action="store_true",
        help="Detectar propiedades ya actualizadas con coordenadas fuera de bounds por ciudad",
    )
    args = parser.parse_args()
    limit = max(args.limit, 0)
    if args.validate_applied_results:
        validate_applied_results(limit=limit)
    elif args.apply_valid_results:
        apply_valid_results(limit=limit, dry_run=args.dry_run)
    else:
        run(limit=limit, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
