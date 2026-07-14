import logging
from typing import Any, Dict, List, Optional, Set
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import SUPABASE_TABLE

logger = logging.getLogger(__name__)

HTTP_CONNECT_TIMEOUT_S = 5
HTTP_READ_TIMEOUT_S = 30
HTTP_FAST_READ_TIMEOUT_S = 15
HTTP_TIMEOUT = (HTTP_CONNECT_TIMEOUT_S, HTTP_READ_TIMEOUT_S)
HTTP_FAST_TIMEOUT = (HTTP_CONNECT_TIMEOUT_S, HTTP_FAST_READ_TIMEOUT_S)


class SessionFactory:
    """Crea una requests.Session con reintentos automáticos para HTTP y Supabase."""

    @staticmethod
    def create() -> requests.Session:
        return SessionFactory.make()

    @staticmethod
    def make() -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=2,
            connect=2,
            read=1,
            status=2,
            other=1,
            backoff_factor=0.25,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PATCH"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "es-AR,es;q=0.9",
        })
        return session


class SupabaseClient:
    def __init__(
        self,
        session: requests.Session,
        url: str,
        key: str,
        table: str = SUPABASE_TABLE,
    ) -> None:
        self.session = session
        self.url = url.rstrip("/")
        self.key = key
        self.table = table
        self._headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=representation",
        }
        self._headers_minimal = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }

    def save(self, payload: Any) -> tuple[bool, str]:
        response = self.session.post(
            f"{self.url}/rest/v1/{self.table}?on_conflict=url",
            headers=self._headers,
            json=payload,
            timeout=HTTP_FAST_TIMEOUT,
        )
        if response.status_code == 201:
            return True, "created"
        if response.status_code == 200:
            return True, "updated"
        raise RuntimeError(
            f"Supabase save error {response.status_code}: {response.text[:300]}"
        )

    def batch_save_only_new(self, new_payloads: List[Dict[str, Any]]) -> int:
        if not new_payloads:
            return 0
        # Plain INSERT — dedup is handled upstream via existing_urls before this call.
        # propiedades.url has no unique constraint, so no on_conflict clause.
        _CHUNK = 20
        total = 0
        insert_headers = {
            "apikey":          self.key,
            "Authorization":   f"Bearer {self.key}",
            "Content-Type":    "application/json",
            "Prefer":          "return=minimal",
        }
        for i in range(0, len(new_payloads), _CHUNK):
            chunk = new_payloads[i : i + _CHUNK]
            response = self.session.post(
                f"{self.url}/rest/v1/{self.table}",
                headers=insert_headers,
                json=chunk,
                timeout=HTTP_TIMEOUT,
            )
            if response.status_code in {200, 201}:
                total += len(chunk)
            elif response.status_code == 409:
                # hash_dedup collision in batch — fall back to row-by-row inserts
                saved, skipped = self._insert_individually(chunk, insert_headers)
                total += saved
                if skipped:
                    logger.info(
                        f"[dedup] {skipped} propiedad(es) omitida(s) por hash_dedup duplicado, "
                        f"{saved} guardada(s) en fallback individual"
                    )
            else:
                raise RuntimeError(
                    f"Supabase batch insert error {response.status_code}: {response.text[:300]}"
                )
        return total

    def _insert_individually(
        self,
        payloads: List[Dict[str, Any]],
        headers: Dict[str, str],
    ) -> tuple[int, int]:
        """Inserta una fila a la vez; retorna (guardadas, omitidas_por_hash_dedup)."""
        saved = 0
        skipped = 0
        for payload in payloads:
            r = self.session.post(
                f"{self.url}/rest/v1/{self.table}",
                headers=headers,
                json=[payload],
                timeout=HTTP_TIMEOUT,
            )
            if r.status_code in {200, 201}:
                saved += 1
            elif r.status_code == 409:
                logger.debug(
                    f"[dedup] hash_dedup duplicate skipped: {payload.get('url', '?')}"
                )
                skipped += 1
            else:
                raise RuntimeError(
                    f"Supabase batch insert error {r.status_code}: {r.text[:300]}"
                )
        return saved, skipped

    def batch_save_only_changed(self, changed_payloads: List[Dict[str, Any]]) -> int:
        if not changed_payloads:
            return 0
        updated = 0
        for payload in changed_payloads:
            url = payload.get("url")
            if not url:
                continue
            safe_payload = {k: v for k, v in payload.items() if k not in ("latitud", "longitud", "url")}
            response = self.session.patch(
                f"{self.url}/rest/v1/{self.table}",
                headers=self._headers_minimal,
                params={"url": f"eq.{url}"},
                json=safe_payload,
                timeout=HTTP_FAST_TIMEOUT,
            )
            if response.status_code not in {200, 204}:
                logger.warning(f"Error actualizando {url}: {response.status_code}")
            else:
                updated += 1
        return updated

    def update_location(self, url: str, latitud: float, longitud: float) -> None:
        response = self.session.patch(
            f"{self.url}/rest/v1/{self.table}",
            headers=self._headers_minimal,
            params={"url": f"eq.{url}"},
            json={"latitud": latitud, "longitud": longitud},
            timeout=HTTP_FAST_TIMEOUT,
        )
        if response.status_code not in {200, 204}:
            raise RuntimeError(
                f"Supabase update_location error {response.status_code}: {response.text[:300]}"
            )

    def get_all_existing_urls(self) -> Set[str]:
        response = self.session.get(
            f"{self.url}/rest/v1/{self.table}",
            headers=self._headers,
            params={"select": "url", "limit": 100_000},
            timeout=HTTP_TIMEOUT,
        )
        response.raise_for_status()
        return {item["url"] for item in response.json() if "url" in item}

    def get_existing_properties(self, urls: List[str]) -> Dict[str, Dict[str, Any]]:
        if not urls:
            return {}

        unique_urls = list(dict.fromkeys(urls))
        results: Dict[str, Dict[str, Any]] = {}

        try:
            results = self._fetch_by_rpc(unique_urls)
            return results
        except Exception as exc:
            logger.debug(f"RPC no disponible, usando GET: {exc}")

        batch_size = 30
        for start in range(0, len(unique_urls), batch_size):
            batch = unique_urls[start : start + batch_size]
            encoded = ",".join(quote(u, safe="") for u in batch)
            response = self.session.get(
                f"{self.url}/rest/v1/{self.table}",
                headers=self._headers,
                params={
                    "select": "*",
                    "url": f"in.({encoded})",
                    "limit": batch_size,
                },
                timeout=HTTP_FAST_TIMEOUT,
            )
            response.raise_for_status()
            for item in response.json():
                if "url" in item:
                    results[item["url"]] = item

        return results

    def _fetch_by_rpc(self, urls: List[str]) -> Dict[str, Dict[str, Any]]:
        batch_size = 50
        results: Dict[str, Dict[str, Any]] = {}
        for start in range(0, len(urls), batch_size):
            batch = urls[start : start + batch_size]
            response = self.session.post(
                f"{self.url}/rest/v1/rpc/get_properties_by_urls",
                headers=self._headers,
                json={"urls": batch},
                timeout=HTTP_FAST_TIMEOUT,
            )
            response.raise_for_status()
            for item in response.json():
                if "url" in item:
                    results[item["url"]] = item
        return results

    def get_unspecified_locations(self, limit: int = 1000) -> List[Dict[str, Any]]:
        response = self.session.get(
            f"{self.url}/rest/v1/{self.table}",
            headers=self._headers,
            params={
                "select": "url,titulo,direccion,barrio,ciudad",
                "or": "(latitud.is.null,longitud.is.null)",
                "limit": limit,
            },
            timeout=HTTP_TIMEOUT,
        )
        response.raise_for_status()
        return [item for item in response.json() if "url" in item]

    def get_active_urls_by_fuente(self, fuente: str) -> List[str]:
        """Devuelve todas las URLs activas de una fuente."""
        response = self.session.get(
            f"{self.url}/rest/v1/{self.table}",
            headers=self._headers,
            params={
                "select": "url",
                "fuente": f"eq.{fuente}",
                "activo": "eq.true",
                "limit": 100_000,
            },
            timeout=HTTP_TIMEOUT,
        )
        response.raise_for_status()
        return [item["url"] for item in response.json() if "url" in item]

    def mark_as_inactive(self, urls: List[str]) -> int:
        """Marca propiedades como inactivas (ya no publicadas)."""
        if not urls:
            return 0
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        updated = 0
        for url in urls:
            response = self.session.patch(
                f"{self.url}/rest/v1/{self.table}",
                headers=self._headers_minimal,
                params={"url": f"eq.{url}"},
                json={"activo": False, "fecha_baja": now},
                timeout=HTTP_FAST_TIMEOUT,
            )
            if response.status_code in {200, 204}:
                updated += 1
        return updated

    def save_historial(self, url: str, campo: str, valor_anterior: str, valor_nuevo: str) -> None:
        """Guarda un cambio en el historial de una propiedad."""
        response = self.session.post(
            f"{self.url}/rest/v1/propiedades_historial",
            headers=self._headers_minimal,
            json={
                "propiedad_url": url,
                "campo": campo,
                "valor_anterior": str(valor_anterior) if valor_anterior is not None else None,
                "valor_nuevo": str(valor_nuevo) if valor_nuevo is not None else None,
            },
            timeout=HTTP_FAST_TIMEOUT,
        )
        if response.status_code not in {200, 201, 204}:
            logger.warning(f"Error guardando historial para {url}: {response.status_code}")
