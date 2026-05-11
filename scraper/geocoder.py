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

    def to_metadata(self) -> Dict[str, Any]:
        return {
            "cleaned_address": self.cleaned_address,
            "is_geocodable": self.is_geocodable,
            "quality": self.quality,
            "reason": self.reason,
            "source": self.source,
            "raw_value": self.raw_value,
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
                "select": "propiedad_id,direccion_geocoding,latitud,longitud,precision_geocoding,proveedor,raw_response,status",
                "status": "eq.success",
                "latitud": "not.is.null",
                "longitud": "not.is.null",
                "order": "propiedad_id.asc",
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
                "select": "id,ciudad,provincia",
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
                "select": "id,titulo,direccion,barrio,ciudad,provincia,latitud,longitud",
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
) -> Tuple[Optional[bool], bool]:
    city_key = normalize_place_key(ciudad_final)
    bounds = CITY_BOUNDS.get(city_key)
    if bounds is None or latitud is None or longitud is None:
        return None, False

    min_lat, max_lat, min_lon, max_lon = bounds
    return min_lat <= latitud <= max_lat and min_lon <= longitud <= max_lon, True


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
    value = strip_unit_suffix(strip_real_estate_prefixes(segment))
    value = re.sub(r"\b(?:piso|depto|dpto|dto|unidad|uf)\b.*$", "", value, flags=re.IGNORECASE)
    value = normalize_address_text(value)

    if not value:
        return None

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
        ("direccion_limpia", row.get("direccion_limpia")),
        ("direccion_geocoding_limpia", row.get("direccion_geocoding_limpia")),
        ("titulo", row.get("titulo")),
    ]
    best: Optional[Tuple[int, str, str, str]] = None

    for source, raw_value in sources:
        raw_text = normalize_address_text(raw_value)
        if not raw_text:
            continue
        segments = split_address_segments(raw_text, row, source)
        for index, segment in enumerate(segments):
            candidate = extract_street_number_address(segment)
            if not candidate:
                continue
            score = score_address_candidate(candidate, index, source)
            if best is None or score > best[0]:
                best = (score, candidate, source, raw_text)

    if best is not None:
        _, cleaned_address, source, raw_value = best
        result = AddressCleaningResult(
            cleaned_address=cleaned_address,
            is_geocodable=True,
            quality="alta",
            reason="calle_altura_detectada",
            source=source,
            raw_value=raw_value,
        )
        row["_address_cleaning"] = result
        return result

    raw_fallback = normalize_address_text(
        row.get("direccion_limpia")
        or row.get("direccion_geocoding_limpia")
        or row.get("titulo")
        or ""
    )
    result = AddressCleaningResult(
        cleaned_address="",
        is_geocodable=False,
        quality="muy_baja",
        reason="sin_calle_altura_confiable",
        source="none",
        raw_value=raw_fallback,
    )
    row["_address_cleaning"] = result
    return result


def normalize_query(row: Dict[str, Any]) -> str:
    address_cleaning = prepare_address_for_geocoding(row)
    if not address_cleaning.is_geocodable:
        return ""

    base = address_cleaning.cleaned_address
    ciudad = str(row.get("ciudad_final") or "").strip()
    provincia = str(row.get("provincia_final") or "").strip()
    parts = [base]
    lower = base.lower()
    if ciudad and ciudad.lower() not in lower:
        parts.append(ciudad)
    if provincia and provincia.lower() not in lower:
        parts.append(provincia)
    if "argentina" not in lower:
        parts.append("Argentina")
    query = ", ".join(part for part in parts if part)
    return re.sub(r"\s+", " ", query).strip(" ,")


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
        "ciudad_final": ciudad_final,
        "provincia_final": provincia_final,
        "calidad_geocoding": address_cleaning.quality if address_cleaning else None,
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

    confidence_level = metadata.get("confidence_level")
    if not confidence_level:
        confidence_level, _, _ = classify_geocoding_quality(
            str(row.get("status") or ""),
            row.get("precision_geocoding"),
        )

    if "should_apply_to_property" in metadata:
        should_apply = bool(metadata.get("should_apply_to_property"))
    else:
        _, should_apply, _ = classify_geocoding_quality(
            str(row.get("status") or ""),
            row.get("precision_geocoding"),
        )

    within_city_bounds = metadata.get("within_city_bounds")
    city_bounds_checked = metadata.get("city_bounds_checked")
    if city_bounds_checked is None:
        city = metadata.get("ciudad_final")
        province = metadata.get("provincia_final")
        if city_context:
            city = city or city_context.get("ciudad") or city_context.get("ciudad_final")
            province = province or city_context.get("provincia") or city_context.get("provincia_final")
        try:
            latitud = float(row["latitud"])
            longitud = float(row["longitud"])
        except (KeyError, TypeError, ValueError):
            latitud = None
            longitud = None
        within_city_bounds, city_bounds_checked = evaluate_city_bounds(latitud, longitud, city)
        if city_bounds_checked and within_city_bounds is False:
            confidence_level = "low"
            should_apply = False

    confidence_allowed = str(confidence_level or "").lower() in {"high", "medium"}
    city_gate = within_city_bounds is True if city_bounds_checked else True
    can_apply = bool(should_apply and confidence_allowed and city_gate)
    return {
        "can_apply": can_apply,
        "confidence_level": confidence_level,
        "should_apply_to_property": should_apply,
        "within_city_bounds": within_city_bounds,
        "city_bounds_checked": city_bounds_checked,
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
        address_cleaning=address_cleaning,
    )
    return last_result, attempted_queries


def build_payload(row: Dict[str, Any], query: str, result: GeocodingResult) -> Dict[str, Any]:
    return {
        "propiedad_id": row.get("propiedad_id"),
        "direccion_geocoding": query,
        "latitud": result.latitud,
        "longitud": result.longitud,
        "precision_geocoding": result.precision_geocoding,
        "proveedor": result.proveedor,
        "raw_response": result.raw_response,
        "status": result.status,
        "error_message": result.error_message,
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
        logger.info(
            "propiedad_id=%s | direccion=%s | calidad_limpieza=%s | source=%s | variantes=%d",
            propiedad_id,
            query or "-",
            address_cleaning.quality,
            address_cleaning.source,
            len(queries),
        )

        if not query:
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
                address_cleaning=address_cleaning,
            )
            if dry_run:
                logger.info(
                    "[dry-run] status=error | %s | raw=%s",
                    result.error_message,
                    address_cleaning.raw_value or "-",
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
        quality_metadata = (
            get_inmocapital_metadata(payload.get("raw_response"))
        )

        if result.status == "success":
            ok += 1
            logger.info(
                "status=success | lat=%.6f | lon=%.6f | precision=%s | confidence=%s | apply=%s | bounds=%s | matched_query=%s | save=%s",
                result.latitud,
                result.longitud,
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
                result.error_message,
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
    applied = 0
    skipped = 0
    failed = 0

    for row in rows:
        propiedad_id = row.get("propiedad_id")
        precision = row.get("precision_geocoding")
        city_context = client.get_property_location_context(propiedad_id)
        decision = get_geocoding_apply_decision(row, city_context)
        logger.info(
            "propiedad_id=%s | precision=%s | confidence=%s | should_apply_to_property=%s | bounds=%s | bounds_checked=%s",
            propiedad_id,
            precision,
            decision.get("confidence_level"),
            decision.get("should_apply_to_property"),
            decision.get("within_city_bounds"),
            decision.get("city_bounds_checked"),
        )

        if not decision.get("can_apply"):
            skipped += 1
            logger.info("skip=needs_review | no se aplica a propiedades")
            continue

        try:
            latitud = float(row["latitud"])
            longitud = float(row["longitud"])
        except (KeyError, TypeError, ValueError) as exc:
            failed += 1
            logger.info("status=error | coordenadas invalidas | %s", exc)
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

    logger.info("Aplicacion finalizada | applied=%d | skipped=%d | error=%d", applied, skipped, failed)


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
        try:
            latitud = float(row["latitud"])
            longitud = float(row["longitud"])
        except (KeyError, TypeError, ValueError) as exc:
            invalid += 1
            logger.info("propiedad_id=%s | status=invalid_coordinates | %s", propiedad_id, exc)
            continue

        within_city_bounds, city_bounds_checked = evaluate_city_bounds(latitud, longitud, ciudad)
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
