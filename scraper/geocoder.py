from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
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


@dataclass
class GeocodingResult:
    latitud: Optional[float]
    longitud: Optional[float]
    precision_geocoding: Optional[str]
    proveedor: str
    raw_response: Any
    status: str
    error_message: Optional[str] = None


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
            allowed_methods=["GET", "POST"],
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


def normalize_query(row: Dict[str, Any]) -> str:
    base = str(row.get("direccion_geocoding_limpia") or "").strip()
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
        query = normalize_query(row)
        logger.info("propiedad_id=%s | direccion=%s", propiedad_id, query or "-")

        if not query:
            result = GeocodingResult(None, None, None, provider.name, None, "error", "direccion_geocoding_limpia vacia")
            if dry_run:
                logger.info("[dry-run] status=error | %s", result.error_message)
                failed += 1
                continue
            client.save_result(build_payload(row, "", result))
            failed += 1
            continue

        existing = client.existing_result(propiedad_id, query)
        if existing:
            skipped += 1
            logger.info("skip=duplicate | status_existente=%s", existing.get("status"))
            continue

        if dry_run:
            logger.info("[dry-run] se geocodificaria con proveedor=%s", provider.name)
            continue

        result = provider.geocode(query)
        payload = build_payload(row, query, result)
        save_status = client.save_result(payload)

        if result.status == "success":
            ok += 1
            logger.info(
                "status=success | lat=%.6f | lon=%.6f | precision=%s | save=%s",
                result.latitud,
                result.longitud,
                result.precision_geocoding,
                save_status,
            )
        else:
            failed += 1
            logger.info("status=error | error=%s | save=%s", result.error_message, save_status)

    logger.info("Geocoding finalizado | success=%d | error=%d | skipped=%d", ok, failed, skipped)


def main() -> None:
    parser = argparse.ArgumentParser(description="Geocoder de Inmocapital basado en cola Supabase")
    parser.add_argument("--limit", type=int, default=20, help="Cantidad maxima de propiedades a leer de v_next_geocoding_batch")
    parser.add_argument("--dry-run", action="store_true", help="Leer pendientes y mostrar acciones sin llamar proveedor ni guardar")
    args = parser.parse_args()
    run(limit=max(args.limit, 0), dry_run=args.dry_run)


if __name__ == "__main__":
    main()
