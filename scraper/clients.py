import logging
from typing import Any, Dict, List, Optional, Set
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import SUPABASE_TABLE
from safe_merge import (
    ACCEPTED_IMPROVEMENT,
    ACCEPTED_SOURCE_CHANGE,
    REJECTED_AMBIGUOUS_IDENTITY,
    REJECTED_CROSS_PROPERTY_CONTAMINATION,
    UNCHANGED_EQUAL,
    build_merge_plan,
)

logger = logging.getLogger(__name__)

HTTP_CONNECT_TIMEOUT_S = 5
HTTP_READ_TIMEOUT_S = 30
HTTP_FAST_READ_TIMEOUT_S = 15
HTTP_TIMEOUT = (HTTP_CONNECT_TIMEOUT_S, HTTP_READ_TIMEOUT_S)
HTTP_FAST_TIMEOUT = (HTTP_CONNECT_TIMEOUT_S, HTTP_FAST_READ_TIMEOUT_S)

_MERGE_SELECT_FIELDS = (
    "id,inmobiliaria_id,url,url_normalizada,id_externo,hash_dedup,"
    "titulo,descripcion,precio,moneda,tipo_propiedad,operacion,"
    "ambientes,dormitorios,banos,superficie_total,direccion,barrio,ciudad,"
    "latitud,longitud,imagenes,fuente_extraccion,estado,created_at,updated_at"
)


class PartialBatchInsertError(RuntimeError):
    """An insert failed after one or more payloads were already confirmed."""

    def __init__(self, message: str, saved_payloads: List[Dict[str, Any]]) -> None:
        super().__init__(message)
        self.saved_payloads = list(saved_payloads)
        self.saved_count = len(self.saved_payloads)


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
            # Retrying a plain INSERT after a read timeout can duplicate a row
            # when PostgreSQL committed but the response never reached us.
            allowed_methods=["GET", "PATCH"],
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
        saved_payloads: List[Dict[str, Any]] = []
        insert_headers = {
            "apikey":          self.key,
            "Authorization":   f"Bearer {self.key}",
            "Content-Type":    "application/json",
            "Prefer":          "return=minimal",
        }
        for i in range(0, len(new_payloads), _CHUNK):
            chunk = new_payloads[i : i + _CHUNK]
            try:
                response = self.session.post(
                    f"{self.url}/rest/v1/{self.table}",
                    headers=insert_headers,
                    json=chunk,
                    timeout=HTTP_TIMEOUT,
                )
            except Exception as exc:
                raise PartialBatchInsertError(
                    f"Supabase insert interrupted after {total} confirmed row(s): {exc}",
                    saved_payloads,
                ) from exc
            if response.status_code in {200, 201}:
                total += len(chunk)
                saved_payloads.extend(chunk)
            elif response.status_code == 409:
                # hash_dedup collision in batch — fall back to row-by-row inserts
                try:
                    saved, skipped, individual_payloads = self._insert_individually(
                        chunk, insert_headers
                    )
                except PartialBatchInsertError as exc:
                    raise PartialBatchInsertError(
                        str(exc), saved_payloads + exc.saved_payloads
                    ) from exc
                total += saved
                saved_payloads.extend(individual_payloads)
                if skipped:
                    logger.info(
                        f"[dedup] {skipped} propiedad(es) omitida(s) por hash_dedup duplicado, "
                        f"{saved} guardada(s) en fallback individual"
                    )
            else:
                raise PartialBatchInsertError(
                    f"Supabase batch insert error {response.status_code}: {response.text[:300]}",
                    saved_payloads,
                )
        return total

    def filter_new_exact_urls(
        self, payloads: List[Dict[str, Any]]
    ) -> tuple[List[Dict[str, Any]], int]:
        """Fail-closed exact URL guard scoped by canonical inmobiliaria_id."""
        if not payloads:
            return [], 0

        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for payload in payloads:
            agency_id = payload.get("inmobiliaria_id")
            url = str(payload.get("url") or "")
            if agency_id is None or not url:
                raise RuntimeError("Exact URL guard requires inmobiliaria_id and url")
            grouped.setdefault(str(agency_id), []).append(payload)

        existing_keys: Set[tuple[str, str]] = set()
        for agency_id, agency_payloads in grouped.items():
            urls = list(dict.fromkeys(str(payload["url"]) for payload in agency_payloads))
            for start in range(0, len(urls), 20):
                batch = urls[start : start + 20]
                # PostgREST accepts quoted values inside in(...). Pre-quoting
                # with percent escapes is incorrect because requests escapes
                # the percent signs again and the query silently matches zero.
                encoded = ",".join(
                    f'"{url.replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"'
                    for url in batch
                )
                try:
                    response = self.session.get(
                        f"{self.url}/rest/v1/{self.table}",
                        headers=self._headers_minimal,
                        params={
                            "select": "inmobiliaria_id,url",
                            "inmobiliaria_id": f"eq.{agency_id}",
                            "url": f"in.({encoded})",
                            "limit": str(len(batch)),
                        },
                        timeout=HTTP_FAST_TIMEOUT,
                    )
                except Exception as exc:
                    raise RuntimeError(f"Exact URL guard request failed: {exc}") from exc
                if response.status_code != 200:
                    raise RuntimeError(
                        f"Exact URL guard HTTP {response.status_code}: {response.text[:300]}"
                    )
                rows = response.json()
                if not isinstance(rows, list):
                    raise RuntimeError("Exact URL guard returned a non-list payload")
                existing_keys.update(
                    (str(row.get("inmobiliaria_id")), str(row.get("url")))
                    for row in rows
                    if isinstance(row, dict)
                    and row.get("inmobiliaria_id") is not None
                    and row.get("url")
                )

        filtered = [
            payload
            for payload in payloads
            if (str(payload["inmobiliaria_id"]), str(payload["url"])) not in existing_keys
        ]
        return filtered, len(payloads) - len(filtered)

    @staticmethod
    def _postgrest_in(values: List[Any]) -> str:
        encoded = ",".join(
            f'"{str(value).replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"'
            for value in values
        )
        return f"in.({encoded})"

    def _fetch_merge_candidates(
        self, payloads: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Load only rows touched by strong identity evidence, fail closed."""
        from models import _normalize_url_for_hash

        lookups: List[tuple[str, List[Any], Optional[Any]]] = []
        urls = sorted({str(p.get("url")) for p in payloads if p.get("url")})
        normalized_urls = sorted(
            {
                str(p.get("url_normalizada") or _normalize_url_for_hash(p.get("url")))
                for p in payloads
                if p.get("url_normalizada") or p.get("url")
            }
        )
        hashes = sorted({str(p.get("hash_dedup")) for p in payloads if p.get("hash_dedup")})
        lookups.extend(
            [
                ("url", urls, None),
                ("url_normalizada", normalized_urls, None),
                ("hash_dedup", hashes, None),
            ]
        )
        external_by_agency: Dict[str, List[str]] = {}
        for payload in payloads:
            external = str(payload.get("id_externo") or "").strip()
            agency = payload.get("inmobiliaria_id")
            if external and agency is not None:
                external_by_agency.setdefault(str(agency), []).append(external)
        for agency, values in external_by_agency.items():
            lookups.append(("id_externo", sorted(set(values)), agency))

        result: Dict[str, Dict[str, Any]] = {}
        for field, values, agency in lookups:
            for start in range(0, len(values), 20):
                chunk = values[start : start + 20]
                params = {
                    "select": _MERGE_SELECT_FIELDS,
                    field: self._postgrest_in(chunk),
                    "limit": "1000",
                }
                if agency is not None:
                    params["inmobiliaria_id"] = f"eq.{agency}"
                try:
                    response = self.session.get(
                        f"{self.url}/rest/v1/{self.table}",
                        headers=self._headers_minimal,
                        params=params,
                        timeout=HTTP_TIMEOUT,
                    )
                except Exception as exc:
                    raise RuntimeError(f"Safe merge identity lookup failed: {exc}") from exc
                if response.status_code != 200:
                    raise RuntimeError(
                        f"Safe merge identity lookup HTTP {response.status_code}: "
                        f"{response.text[:300]}"
                    )
                rows = response.json()
                if not isinstance(rows, list):
                    raise RuntimeError("Safe merge identity lookup returned a non-list payload")
                for row in rows:
                    if isinstance(row, dict) and row.get("id") is not None:
                        result[str(row["id"])] = row
        return list(result.values())

    def _call_merge_rpc(self, function: str, payload: Dict[str, Any]) -> Any:
        response = self.session.post(
            f"{self.url}/rest/v1/rpc/{function}",
            headers=self._headers,
            json=payload,
            timeout=HTTP_TIMEOUT,
        )
        if response.status_code not in {200, 201}:
            raise RuntimeError(
                f"Safe merge RPC {function} HTTP {response.status_code}: "
                f"{response.text[:300]}"
            )
        body = response.json()
        if not isinstance(body, (dict, int)):
            raise RuntimeError(f"Safe merge RPC {function} returned an invalid payload")
        return body

    def batch_save_safe_merge(
        self,
        payloads: List[Dict[str, Any]],
        *,
        source_id: Any,
        run_id: str,
        dry_run: bool = False,
    ) -> Dict[str, int]:
        """Insert or improve properties through the audited, atomic RPCs only."""
        stats = {
            "input": len(payloads),
            "inserted": 0,
            "existing_matched": 0,
            "existing_improved": 0,
            "fields_improved": 0,
            "fields_rejected": 0,
            "unchanged_fields": 0,
            "ambiguous_identity": 0,
            "db_inserts": 0,
            "db_updates": 0,
            "audit_rows": 0,
        }
        if not payloads:
            return stats
        if not str(source_id or "").strip() or not str(run_id or "").strip():
            raise RuntimeError("Safe merge requires source_id and run_id")

        candidates = self._fetch_merge_candidates(payloads)
        for payload in payloads:
            plan = build_merge_plan(payload, candidates, source_id=source_id)
            audits = plan.get("audit") or []
            stats["fields_improved"] += sum(
                1
                for entry in audits
                if entry.get("decision") in {ACCEPTED_IMPROVEMENT, ACCEPTED_SOURCE_CHANGE}
            )
            stats["fields_rejected"] += sum(
                1 for entry in audits if str(entry.get("decision") or "").startswith("REJECTED_")
            )
            stats["unchanged_fields"] += sum(
                1 for entry in audits if entry.get("decision") == UNCHANGED_EQUAL
            )

            if plan["status"] == "rejected":
                if any(
                    entry.get("decision")
                    in {REJECTED_AMBIGUOUS_IDENTITY, REJECTED_CROSS_PROPERTY_CONTAMINATION}
                    for entry in audits
                ):
                    stats["ambiguous_identity"] += 1
                if not dry_run:
                    result = self._call_merge_rpc(
                        "record_property_merge_audit",
                        {
                            "p_property_id": None,
                            "p_source_id": str(source_id),
                            "p_run_id": str(run_id),
                            "p_audit": audits,
                        },
                    )
                    stats["audit_rows"] += int(result if isinstance(result, int) else 0)
                continue

            if plan["status"] == "insert":
                if dry_run:
                    stats["inserted"] += 1
                    continue
                result = self._call_merge_rpc(
                    "insert_property_safe",
                    {
                        "p_payload": plan["payload"],
                        "p_source_id": str(source_id),
                        "p_run_id": str(run_id),
                        "p_audit": audits,
                    },
                )
                if result.get("status") != "inserted":
                    raise RuntimeError(f"Safe insert returned unexpected status: {result}")
                stats["inserted"] += 1
                stats["db_inserts"] += 1
                stats["audit_rows"] += int(result.get("audit_rows") or 0)
                inserted = dict(plan["payload"])
                inserted["id"] = result.get("property_id")
                candidates.append(inserted)
                continue

            existing = plan["property"]
            stats["existing_matched"] += 1
            patch = plan.get("patch") or {}
            if patch:
                stats["existing_improved"] += 1
            if dry_run:
                continue
            result = self._call_merge_rpc(
                "apply_property_safe_merge",
                {
                    "p_property_id": existing["id"],
                    "p_inmobiliaria_id": existing["inmobiliaria_id"],
                    "p_expected_url": existing.get("url"),
                    "p_expected_hash_dedup": existing.get("hash_dedup"),
                    "p_expected_fuente_extraccion": existing.get("fuente_extraccion"),
                    "p_patch": patch,
                    "p_source_id": str(source_id),
                    "p_run_id": str(run_id),
                    "p_audit": audits,
                },
            )
            if patch and result.get("status") != "updated":
                raise RuntimeError(f"Safe merge failed to apply accepted patch: {result}")
            if patch:
                stats["db_updates"] += 1
                existing.update(patch)
            stats["audit_rows"] += int(result.get("audit_rows") or 0)
        return stats

    def _insert_individually(
        self,
        payloads: List[Dict[str, Any]],
        headers: Dict[str, str],
    ) -> tuple[int, int, List[Dict[str, Any]]]:
        """Insert rows individually and retain the exact confirmed payloads."""
        saved = 0
        skipped = 0
        saved_payloads: List[Dict[str, Any]] = []
        for payload in payloads:
            try:
                r = self.session.post(
                    f"{self.url}/rest/v1/{self.table}",
                    headers=headers,
                    json=[payload],
                    timeout=HTTP_TIMEOUT,
                )
            except Exception as exc:
                raise PartialBatchInsertError(
                    f"Supabase individual insert interrupted after {saved} confirmed row(s): {exc}",
                    saved_payloads,
                ) from exc
            if r.status_code in {200, 201}:
                saved += 1
                saved_payloads.append(payload)
            elif r.status_code == 409:
                logger.debug(
                    f"[dedup] hash_dedup duplicate skipped: {payload.get('url', '?')}"
                )
                skipped += 1
            else:
                raise PartialBatchInsertError(
                    f"Supabase batch insert error {r.status_code}: {r.text[:300]}",
                    saved_payloads,
                )
        return saved, skipped, saved_payloads

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
