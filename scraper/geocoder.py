import logging
import re
import time

import requests

from clients import SupabaseClient
from config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_TABLE, SUPABASE_URL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_DELAY = 1.2
USER_AGENT = "InmoLink/1.0 (contacto@inmolink.com.ar)"

SKIP_KEYWORDS = [
    "club de campo", "country", "barrio privado", "loteo", "quiloazas",
    "altos del sauce", "solares del paucke", "nuevos aires", "villa california",
    "entre ríos",
]


class Geocoder:
    def __init__(self, supabase: SupabaseClient) -> None:
        self.supabase = supabase
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def clean_direccion(self, direccion: str) -> str:
        """Limpia la dirección para mejorar los resultados de Nominatim."""
        # Sacar todo lo que viene después de un guión
        direccion = direccion.split("-")[0].strip()
        # Sacar todo lo que viene después de un punto
        direccion = direccion.split(".")[0].strip()
        # Sacar palabras que confunden a Nominatim
        noise = [
            "GALERÍA", "GALERIA", "COLONIAL", "FLORIDA", "TORRE",
            "EDIFICIO", "LOCAL", "PISO", "DPTO", "S/N",
        ]
        for word in noise:
            direccion = re.sub(rf"\b{word}\b", "", direccion, flags=re.IGNORECASE)
        # Normalizar espacios
        direccion = re.sub(r"\s+", " ", direccion).strip()
        return direccion

    def should_skip(self, direccion: str) -> bool:
        """Detecta direcciones que Nominatim no puede geocodificar."""
        lower = direccion.lower()
        return any(kw in lower for kw in SKIP_KEYWORDS)

    def geocode(self, query: str) -> tuple[float, float] | None:
        try:
            response = self.session.get(
                NOMINATIM_URL,
                params={"q": query, "format": "json", "limit": 1, "countrycodes": "AR"},
                timeout=10,
            )

            if response.status_code == 429:
                logger.warning("Rate limit de Nominatim — esperando 10 segundos")
                time.sleep(10)
                return None

            if response.status_code == 403:
                logger.error("Nominatim bloqueó el User-Agent.")
                return None

            response.raise_for_status()
            data = response.json()

            if not data:
                logger.debug(f"Sin resultado: {query}")
                return None

            lat = float(data[0]["lat"])
            lon = float(data[0]["lon"])
            logger.info(f"OK: {query} → ({lat:.5f}, {lon:.5f})")
            return lat, lon

        except requests.RequestException as exc:
            logger.error(f"Error HTTP: {exc}")
            return None
        except (KeyError, ValueError, IndexError) as exc:
            logger.error(f"Error parseando respuesta: {exc}")
            return None
        finally:
            time.sleep(NOMINATIM_DELAY)

    def geocode_with_fallback(self, direccion: str, barrio: str, ciudad: str) -> tuple[float, float] | None:
        """
        Intenta geocodificar con distintas estrategias:
        1. Dirección limpia + ciudad
        2. Dirección limpia sola
        3. Barrio + ciudad (fallback)
        """
        ciudad_str = ciudad or "Santa Fe"

        if direccion:
            # Estrategia 1: dirección limpia + ciudad
            dir_limpia = self.clean_direccion(direccion)
            if self.should_skip(dir_limpia):
                logger.debug(f"Skipping country/barrio privado: {dir_limpia}")
                return None

            result = self.geocode(f"{dir_limpia}, {ciudad_str}, Argentina")
            if result:
                return result

            # Estrategia 2: solo la primera parte de la dirección
            primera_parte = dir_limpia.split(" ")[0:3]
            if len(primera_parte) >= 2:
                result = self.geocode(f"{' '.join(primera_parte)}, {ciudad_str}, Argentina")
                if result:
                    return result

        # Estrategia 3: barrio + ciudad
        if barrio and barrio.lower() not in ["santa fe", "null", ""]:
            if not self.should_skip(barrio):
                result = self.geocode(f"{barrio}, {ciudad_str}, Argentina")
                if result:
                    return result

        return None

    def run(self, limit: int = 500) -> None:
        rows = self.supabase.get_unspecified_locations(limit=limit)

        if not rows:
            logger.info("No hay propiedades pendientes de geocodificación.")
            return

        logger.info(f"{len(rows)} propiedades a geocodificar.")
        ok = 0
        fail = 0

        for row in rows:
            url = row.get("url")
            titulo = row.get("titulo") or ""
            direccion = row.get("direccion") or ""
            barrio = row.get("barrio") or ""
            ciudad = row.get("ciudad") or "Santa Fe"

            # Si no hay dirección, intentar usar el título
            if not direccion and titulo:
                direccion = titulo

            if not url:
                continue

            result = self.geocode_with_fallback(direccion, barrio, ciudad)

            if not result:
                logger.debug(f"Sin resultado para: {direccion or barrio}")
                fail += 1
                continue

            lat, lon = result
            try:
                self.supabase.update_location(url, lat, lon)
                ok += 1
            except Exception as exc:
                logger.error(f"Error guardando {url}: {exc}")
                fail += 1

        logger.info(f"Geocodificación finalizada. OK: {ok} | Fallos: {fail}")


def main() -> None:
    session = requests.Session()
    supabase = SupabaseClient(
        session,
        SUPABASE_URL,
        SUPABASE_SERVICE_ROLE_KEY,
        SUPABASE_TABLE,
    )
    geocoder = Geocoder(supabase)
    geocoder.run()


if __name__ == "__main__":
    main() 