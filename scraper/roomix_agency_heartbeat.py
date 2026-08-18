"""Heartbeat remoto del crawler Roomix Agency Coverage — ERETZ Propiedades.

Diseño (espeja scraper/error_logger.py, mismo contrato de robustez):
  - JSONL append-only local: SIEMPRE primero (durable; sobrevive cortes de red).
  - tabla internal_scraping.roomix_agency_crawl_status: best-effort, SOLO con `db_url`.
  - Conexión a la tabla: EFÍMERA y autocommit (NO comparte transacción con el crawler).
  - Ningún método lanza excepción: el monitor NUNCA puede tumbar ni frenar el crawl.
  - Redacción obligatoria de secretos antes de escribir a archivo o tabla.

Qué NO hace este módulo (por diseño, no por omisión):
  - No es fuente de verdad del crawl. El checkpoint/cursor local manda siempre.
  - No almacena propiedades, precios, descripciones, fotos ni características.
  - No modifica el ritmo, la concurrencia, el orden ni el universo del crawler.
  - No relanza ni mata el crawler ante un STALL: eso se decide fuera.

Integración con el crawler (superficie mínima, 3 llamadas):

    hb = CrawlHeartbeat(run_id="roomix-2026-08", db_url=DB_URL,
                        total_listings=168563, crawler_version="1.4.2")
    hb.start(processed_listings=18120)          # al arrancar/reanudar -> RUNNING

    ...dentro del loop, una vez por ficha (barato, con throttling interno):
    hb.update(processed_listings=n, inmobiliarias=..., oficinas_franquicia=..., ...)

    hb.mark_completed()                          # al agotar universo + delta

`update()` acumula en memoria y sólo escribe cada `min_interval_seconds` (5 min por
defecto) o cada `min_listings_delta` fichas. Nunca hace una escritura por ficha.
"""

from __future__ import annotations

import datetime
import json
import threading
from collections import deque
from pathlib import Path
from typing import Any, Deque, Optional, Tuple

from scraper.error_logger import redact

_REPO = Path(__file__).resolve().parents[1]

# Estados válidos (deben coincidir con roomix_crawl_status_chk en la migración)
STATUS_RUNNING = "RUNNING"
STATUS_PAUSED = "PAUSED"
STATUS_RETRYING = "RETRYING"
STATUS_STALLED = "STALLED"
STATUS_COMPLETED = "COMPLETED"
STATUS_FAILED = "FAILED"

VALID_STATUSES = frozenset({
    STATUS_RUNNING, STATUS_PAUSED, STATUS_RETRYING,
    STATUS_STALLED, STATUS_COMPLETED, STATUS_FAILED,
})

# Un crawler RUNNING sin heartbeat por más de esto se considera potencialmente colgado.
STALE_THRESHOLD_SECONDS = 1800  # 30 min

# Contadores que el crawler puede reportar. Cualquier otra clave se ignora:
# así el heartbeat no puede filtrar datos de propiedades aunque se lo pasen.
_COUNTER_FIELDS = (
    "processed_listings",
    "total_listings",
    "raw_publisher_identities",
    "canonical_publisher_entities",
    "aliases_merged",
    "inmobiliarias",
    "oficinas_franquicia",
    "agentes",
    "developers",
    "unknown",
    "garbage",
    "errors_total",
    "inaccessible_total",
)

# Campos de texto libre admitidos (se redactan y sanitizan antes de persistir).
_TEXT_FIELDS = ("last_checkpoint", "last_listing_ref")

# Columnas escribibles en la tabla. Excluye las GENERATED (completion_pct,
# real_estate_entities), que Postgres calcula y no acepta en el INSERT.
_DB_COLUMNS = (
    "run_id", "status",
    "processed_listings", "total_listings",
    "raw_publisher_identities", "canonical_publisher_entities", "aliases_merged",
    "inmobiliarias", "oficinas_franquicia", "agentes", "developers",
    "unknown", "garbage",
    "errors_total", "inaccessible_total",
    "last_checkpoint", "last_listing_ref",
    "started_at", "last_heartbeat_at", "eta_seconds",
    "matcher_version", "crawler_version",
)

_UPSERT_SQL = """
INSERT INTO internal_scraping.roomix_agency_crawl_status ({cols})
VALUES ({vals})
ON CONFLICT (run_id) DO UPDATE SET {updates}
""".format(
    cols=", ".join(_DB_COLUMNS),
    vals=", ".join(f"%({c})s" for c in _DB_COLUMNS),
    updates=", ".join(
        f"{c} = EXCLUDED.{c}" for c in _DB_COLUMNS if c not in ("run_id", "started_at")
    ),
)


def _utcnow_iso(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat()


def sanitize_ref(value: Optional[Any]) -> Optional[str]:
    """Sanitiza una referencia de listing: quita querystring/fragment y redacta.

    Se guarda sólo para poder ubicar el punto del crawl, nunca contenido comercial.
    """
    if value is None:
        return None
    s = str(value).split("#", 1)[0].split("?", 1)[0]
    return redact(s)


def is_stalled(
    last_heartbeat_at: Optional[Any],
    status: Optional[str],
    *,
    now: Optional[float] = None,
    threshold_seconds: int = STALE_THRESHOLD_SECONDS,
) -> bool:
    """¿El crawler parece colgado? Decisión de LECTURA, externa al crawler.

    Sólo un RUNNING cuyo último heartbeat supere el umbral cuenta como STALLED.
    Un COMPLETED/PAUSED/FAILED viejo no es un stall. Ante datos ilegibles: False
    (no inventar un stall por un parseo fallido).
    """
    if status != STATUS_RUNNING:
        return False
    if last_heartbeat_at is None:
        return False
    try:
        if isinstance(last_heartbeat_at, datetime.datetime):
            dt = last_heartbeat_at
        else:
            dt = datetime.datetime.fromisoformat(str(last_heartbeat_at))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        now_ts = now if now is not None else datetime.datetime.now(
            datetime.timezone.utc).timestamp()
        return (now_ts - dt.timestamp()) > threshold_seconds
    except Exception:
        return False


class CrawlHeartbeat:
    """Espejo de telemetría del crawler. Ninguna operación puede romper el crawl."""

    def __init__(
        self,
        *,
        run_id: str,
        db_url: Optional[str] = None,
        total_listings: Optional[int] = None,
        crawler_version: Optional[str] = None,
        matcher_version: Optional[str] = None,
        min_interval_seconds: int = 300,
        min_listings_delta: int = 250,
        eta_window_seconds: int = 900,
        sample_interval_seconds: int = 30,
        jsonl_path: Optional[Path] = None,
        time_fn=None,
    ) -> None:
        self.run_id = str(run_id)
        self._db_url = db_url  # nunca se serializa ni se loguea
        self._time = time_fn or (
            lambda: datetime.datetime.now(datetime.timezone.utc).timestamp())
        self._lock = threading.Lock()

        self._min_interval = max(int(min_interval_seconds), 0)
        self._min_delta = max(int(min_listings_delta), 1)
        self._eta_window = max(int(eta_window_seconds), 1)
        self._sample_interval = max(int(sample_interval_seconds), 0)

        now = self._time()
        self._started_at = now
        self._last_flush_at: Optional[float] = None
        self._last_flush_processed = 0
        self._last_sample_at: Optional[float] = None
        self._samples: Deque[Tuple[float, int]] = deque()

        self._status = STATUS_RUNNING
        self._stats = {f: 0 for f in _COUNTER_FIELDS}
        self._stats["total_listings"] = total_listings
        self._text = {f: None for f in _TEXT_FIELDS}
        self._crawler_version = crawler_version
        self._matcher_version = matcher_version

        if jsonl_path is not None:
            self._jsonl_path = Path(jsonl_path)
        else:
            d = _REPO / "logs"
            self._jsonl_path = d / f"roomix_agency_heartbeat_{self.run_id}.jsonl"

    # -- API pública ---------------------------------------------------------

    def start(self, **counters: Any) -> None:
        """Arranque o reanudación. Fija RUNNING y emite un heartbeat inmediato."""
        self.update(status=STATUS_RUNNING, force=True, **counters)

    def update(self, *, status: Optional[str] = None, force: bool = False,
               **counters: Any) -> None:
        """Acumula contadores y escribe sólo si toca (throttling). Nunca lanza."""
        try:
            with self._lock:
                now = self._time()
                if status is not None and status in VALID_STATUSES:
                    if status != self._status:
                        force = True
                    self._status = status

                for key, value in counters.items():
                    if key in _COUNTER_FIELDS:
                        self._stats[key] = value
                    elif key in _TEXT_FIELDS:
                        self._text[key] = sanitize_ref(value)
                    # claves desconocidas se descartan en silencio: el heartbeat
                    # no puede convertirse en un canal de datos de propiedades.

                self._record_sample(now)
                if force or self._should_flush(now):
                    payload = self._build_payload(now)
                    self._last_flush_at = now
                    self._last_flush_processed = self._processed()
                else:
                    return
            # Fuera del lock: la E/S no bloquea al crawler.
            self._emit(payload)
        except Exception:
            return  # el monitor jamás propaga un error al crawl

    def set_status(self, status: str, **counters: Any) -> None:
        self.update(status=status, force=True, **counters)

    def mark_completed(self, **counters: Any) -> None:
        self.update(status=STATUS_COMPLETED, force=True, **counters)

    def mark_failed(self, **counters: Any) -> None:
        self.update(status=STATUS_FAILED, force=True, **counters)

    def snapshot(self) -> dict:
        """Payload actual sin escribir nada (para tests y reporting)."""
        with self._lock:
            return self._build_payload(self._time())

    # -- Interno -------------------------------------------------------------

    def _processed(self) -> int:
        try:
            return int(self._stats.get("processed_listings") or 0)
        except Exception:
            return 0

    def _should_flush(self, now: float) -> bool:
        if self._last_flush_at is None:
            return True
        if (now - self._last_flush_at) >= self._min_interval:
            return True
        return (self._processed() - self._last_flush_processed) >= self._min_delta

    def _record_sample(self, now: float) -> None:
        """Muestra para el ETA. Se toma como mucho cada `sample_interval_seconds`."""
        if self._last_sample_at is not None and \
                (now - self._last_sample_at) < self._sample_interval:
            return
        self._last_sample_at = now
        self._samples.append((now, self._processed()))
        cutoff = now - self._eta_window
        while len(self._samples) > 2 and self._samples[0][0] < cutoff:
            self._samples.popleft()

    def _eta_seconds(self, now: float) -> Optional[int]:
        """ETA por throughput RECIENTE (ventana móvil), no promedio histórico.

        Aproximado por definición: no es un deadline.
        """
        total = self._stats.get("total_listings")
        if not total or total <= 0:
            return None
        processed = self._processed()
        remaining = int(total) - processed
        if remaining <= 0:
            return 0
        if len(self._samples) < 2:
            return None
        t0, p0 = self._samples[0]
        t1, p1 = self._samples[-1]
        dt, dp = t1 - t0, p1 - p0
        if dt <= 0 or dp <= 0:
            return None
        return int(remaining / (dp / dt))

    def _build_payload(self, now: float) -> dict:
        payload = {
            "run_id": self.run_id,
            "status": self._status,
            "started_at": _utcnow_iso(self._started_at),
            "last_heartbeat_at": _utcnow_iso(now),
            "eta_seconds": self._eta_seconds(now),
            "matcher_version": self._matcher_version,
            "crawler_version": self._crawler_version,
        }
        for f in _COUNTER_FIELDS:
            payload[f] = self._stats.get(f)
        for f in _TEXT_FIELDS:
            payload[f] = self._text.get(f)

        # Derivados: espejan las columnas GENERATED de la tabla. Se incluyen en el
        # JSONL para que el archivo local sea legible por sí solo, y se excluyen
        # del INSERT (Postgres los calcula).
        inm = int(payload.get("inmobiliarias") or 0)
        ofi = int(payload.get("oficinas_franquicia") or 0)
        payload["real_estate_entities"] = inm + ofi

        total = payload.get("total_listings")
        processed = int(payload.get("processed_listings") or 0)
        payload["completion_pct"] = (
            round(min(processed / total, 1.0) * 100, 3)
            if total and total > 0 else None
        )
        return payload

    def _emit(self, payload: dict) -> None:
        self._write_jsonl(payload)          # 1) durable, siempre
        if self._db_url:
            self._write_table(payload)      # 2) best-effort, aislado

    def _write_jsonl(self, payload: dict) -> None:
        try:
            self._jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(payload, ensure_ascii=False)
            with open(self._jsonl_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
        except Exception:
            pass  # un fallo de archivo nunca frena el crawl

    def _write_table(self, payload: dict) -> None:
        """UPSERT con conexión EFÍMERA propia, aislada de la del crawler.

        Si Supabase está caído, el crawl sigue: queda el JSONL y el próximo
        heartbeat reintenta con el estado acumulado (es idempotente por run_id).
        """
        conn = None
        try:
            import psycopg  # import diferido: el JSONL no exige psycopg
            rec = {c: payload.get(c) for c in _DB_COLUMNS}
            # autocommit=False a propósito: SET LOCAL ROLE sólo surte efecto dentro
            # de una transacción, y SET LOCAL (no SET) es lo seguro bajo pooler.
            conn = psycopg.connect(self._db_url)
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute("SET LOCAL ROLE eretz_roomix_heartbeat_writer")
                    cur.execute(_UPSERT_SQL, rec)
        except Exception:
            pass  # DB caída / upsert inválido -> sólo queda el JSONL. Nunca propagar.
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
