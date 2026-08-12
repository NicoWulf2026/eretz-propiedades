"""
run.py — Entry point principal del sistema de scraping ERETZ Propiedades.

Usa sync_playwright + ThreadPoolExecutor para concurrencia real.
Cada worker lanza su propio proceso de browser y procesa un lote de fuentes
en serie. Esto garantiza compatibilidad total con playwright_scraper.py
(que usa sync_api) y evita la mezcla async/sync.

Uso:
    python run.py                        # todas las fuentes
    python run.py --workers 4            # 4 browsers en paralelo
    python run.py --dry-run              # sin guardar en DB
    python run.py --debug                # logs verbosos
    python run.py --skip-specialized     # saltar scrapers especializados
"""

from __future__ import annotations

import argparse
from collections import deque
import gc
import logging
import math
import os
from pathlib import Path
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Set
from urllib.parse import parse_qsl, urlparse

import requests
from playwright.sync_api import TimeoutError as PwTimeout
from playwright.sync_api import sync_playwright

from clients import PartialBatchInsertError, SessionFactory, SupabaseClient
from config import (
    SUPABASE_SERVICE_ROLE_KEY,
    SUPABASE_TABLE,
    SUPABASE_URL,
)
from models import Propiedad

from playwright_scraper import (
    FUENTES,
    FUENTES_NUEVAS,
    _get_next_page_url,
    _goto_safe,
    discover_listing_page_urls,
    parse_cards,
    scrape_9010,
    scrape_apl,
    scrape_cam,
    scrape_casablanca,
    scrape_cisfe,
    scrape_config_sources,
    scrape_detail_page,
    scrape_lenarduzzi,
    scrape_neo,
    scrape_nuevas_no_tokko,
    scrape_pilay,
    scrape_proa,
    scrape_raes,
    scrape_raffin,
    scrape_sofia,
    scrape_sur,
    scroll_to_bottom,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

DEFAULT_WORKERS = 4

BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
]
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

BASE_LISTING_TIMEOUT_MS = 40_000
BASE_DETAIL_TIMEOUT_MS = 20_000
BASE_DETAIL_RETRIES = 0
BASE_RETRY_BACKOFF_S = 0.5
BASE_SOURCE_NO_PROGRESS_S = 120
BASE_SOURCE_HARD_CAP_S = 1_800
ABSOLUTE_SOURCE_HARD_CAP_S = 5_400
PROHIBITED_DETAIL_DOMAINS = {
    "argenprop.com",
    "argenprop.com.ar",
    "properati.com",
    "properati.com.ar",
    "zonaprop.com",
    "zonaprop.com.ar",
}
LISTING_SHELL_DETAIL_SOURCES = {"lissa_propiedades"}
LISTING_SHELL_DETAIL_QUERY_KEYS = {"id", "idprop", "property_id", "propiedad_id"}


def _is_prohibited_detail_url(value: str) -> bool:
    """Fail closed for third-party property portals before navigation."""
    try:
        host = (urlparse(value).hostname or "").lower().rstrip(".")
    except (TypeError, ValueError):
        return True
    return any(
        host == blocked or host.endswith("." + blocked)
        for blocked in PROHIBITED_DETAIL_DOMAINS
    )


def _is_listing_shell_detail_url(detail_url: str, listing_url: str) -> bool:
    """Detect query-driven details that reuse the listing route."""
    try:
        detail = urlparse(detail_url)
        listing = urlparse(listing_url)
    except (TypeError, ValueError):
        return False
    if (
        detail.scheme.lower() not in {"http", "https"}
        or detail.hostname != listing.hostname
        or detail.path.rstrip("/").lower() != listing.path.rstrip("/").lower()
    ):
        return False
    detail_query = {
        key.lower(): value.strip()
        for key, value in parse_qsl(detail.query, keep_blank_values=True)
    }
    return any(detail_query.get(key) for key in LISTING_SHELL_DETAIL_QUERY_KEYS)


def _uses_listing_shell_detail(
    source_key: str,
    detail_url: str,
    listing_url: str,
) -> bool:
    return (
        source_key in LISTING_SHELL_DETAIL_SOURCES
        and _is_listing_shell_detail_url(detail_url, listing_url)
    )


def _source_int(source: Dict[str, Any], key: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(float(source.get(key, default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def calculate_source_hard_cap(source: Dict[str, Any], detail_count: int) -> int:
    """Budget grows with demonstrated work but always has an absolute ceiling."""
    configured = str(source.get("source_hard_cap_s") or "").strip()
    if configured:
        return _source_int(
            source,
            "source_hard_cap_s",
            BASE_SOURCE_HARD_CAP_S,
            300,
            ABSOLUTE_SOURCE_HARD_CAP_S,
        )
    dynamic = max(BASE_SOURCE_HARD_CAP_S, 300 + max(0, detail_count) * 10)
    return min(ABSOLUTE_SOURCE_HARD_CAP_S, dynamic)


def _listing_seed_score(prop: Propiedad) -> int:
    """Prefer the richest duplicate card when snapshots expose the same URL."""
    return sum(
        (
            bool(prop.titulo and prop.titulo.strip()),
            prop.precio is not None,
            bool(prop.moneda),
            bool(prop.direccion),
            bool(prop.barrio),
            prop.tipo_propiedad not in (None, "", "otro"),
            bool(prop.descripcion),
            bool(prop.imagenes),
            prop.dormitorios is not None,
            prop.banos is not None,
            prop.ambientes is not None,
            prop.metros is not None,
        )
    )


def _property_from_listing_seed(
    seed: Optional[Propiedad],
    *,
    url: str,
    fuente: str,
    ciudad: Optional[str],
    operacion: Optional[str],
    inmobiliaria_id: Optional[int],
) -> Propiedad:
    """Keep trustworthy card data while the detail page enriches it in place."""
    if seed is None:
        return Propiedad(
            url=url,
            titulo="Sin título",
            fuente=fuente,
            ciudad=ciudad or None,
            operacion=operacion,
            barrio=ciudad or "Argentina",
            inmobiliaria_id=inmobiliaria_id,
        )
    return Propiedad(
        url=url,
        titulo=seed.titulo or "Sin título",
        precio=seed.precio,
        moneda=seed.moneda,
        direccion=seed.direccion,
        barrio=seed.barrio or ciudad or "Argentina",
        barrio_normalizado=seed.barrio_normalizado,
        tipo_propiedad=seed.tipo_propiedad or "otro",
        descripcion=seed.descripcion or "",
        dormitorios=seed.dormitorios,
        banos=seed.banos,
        ambientes=seed.ambientes,
        metros=seed.metros,
        imagenes=list(seed.imagenes or []),
        ciudad=seed.ciudad or ciudad or None,
        operacion=seed.operacion or operacion,
        latitud=seed.latitud,
        longitud=seed.longitud,
        fuente=fuente,
        inmobiliaria_id=inmobiliaria_id,
    )


def _property_from_listing_shell_seed(
    seed: Optional[Propiedad],
    *,
    url: str,
    fuente: str,
    ciudad: Optional[str],
    operacion: Optional[str],
    inmobiliaria_id: Optional[int],
) -> Optional[Propiedad]:
    """Build a card-only property, rejecting shells without a valid card identity."""
    if seed is None:
        return None
    prop = _property_from_listing_seed(
        seed,
        url=url,
        fuente=fuente,
        ciudad=ciudad,
        operacion=operacion,
        inmobiliaria_id=inmobiliaria_id,
    )
    return prop if prop.is_valid() else None

# Fix-S: límite de browsers activos simultáneamente entre todos los workers.
# Configurable por env MAX_ACTIVE_BROWSERS, con techo absoluto de 2.
# FairSemaphore reemplaza threading.Semaphore para garantizar orden FIFO estricto
# y eliminar el starvation observado en V10 (W2 esperó 168 min sin slot).


class FairSemaphore:
    """Semáforo FIFO sobre threading.Condition + deque.

    threading.Semaphore no garantiza orden entre threads en espera: el thread
    que acaba de liberar puede re-adquirir antes que los que llevan más tiempo
    esperando (starvation). FairSemaphore corrige esto: cada thread coloca un
    token propio en la cola y solo avanza cuando ese token está primero en la
    cola Y hay capacidad disponible.

    Interfaz idéntica a threading.Semaphore: soporta 'with', acquire(), release().
    Thread-safe. Compatible con Windows. Sin dependencias externas.
    """

    def __init__(self, value: int = 1) -> None:
        if value < 1:
            raise ValueError("FairSemaphore value must be >= 1")
        self._capacity = value
        self._cond = threading.Condition(threading.Lock())
        self._queue: deque = deque()

    def acquire(self) -> None:
        token = object()
        with self._cond:
            self._queue.append(token)
            # Esperar hasta ser el primero en la cola Y haber capacidad disponible.
            # FIFO garantizado: cada thread solo avanza cuando su propio token
            # está en la posición 0. notify_all() en release() despierta a todos
            # para que re-evalúen la condición; solo el primero procede.
            while self._queue[0] is not token or self._capacity == 0:
                self._cond.wait()
            self._queue.popleft()
            self._capacity -= 1

    def release(self) -> None:
        with self._cond:
            self._capacity += 1
            self._cond.notify_all()

    def __enter__(self) -> "FairSemaphore":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        # Siempre libera, incluso si el bloque with lanzó una excepción.
        self.release()


_ACTIVE_BROWSER_SEM = FairSemaphore(
    min(2, max(1, int(os.environ.get("MAX_ACTIVE_BROWSERS", "2"))))
)


def _sanitize_source_error(value: Any) -> str:
    """Keep structured outputs useful without leaking credentials."""
    text = str(value or "")
    text = re.sub(
        r"([?&](?:key|apikey|api_key|token|access_token)=)[^&\s]+",
        r"\1<redacted>",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"(Bearer\s+)[A-Za-z0-9._~+/=-]+",
        r"\1<redacted>",
        text,
        flags=re.IGNORECASE,
    )
    return text[:500]


def classify_source_metrics(
    *,
    pages: int,
    listings_seen: int,
    details_requested: int,
    valid_properties: int,
    db_writes: int,
    had_timeout: bool,
    had_error: bool,
    dry_run: bool,
    ambiguous_identity: int = 0,
) -> tuple[str, str, str, bool]:
    """Return status, classification, error_type and retryability."""
    if had_timeout and valid_properties > 0:
        return (
            "PARTIAL_SUCCESS_TIMEOUT",
            "FALSE_POSITIVE",
            "source_budget_exhausted_after_partial_success",
            True,
        )
    if had_timeout:
        return "TIMEOUT", "INTERNAL_RETRYABLE", "playwright_timeout", True
    if had_error:
        return "INTERNAL_ERROR", "INTERNAL_RETRYABLE", "unhandled_exception", True
    if pages == 0:
        return "REMOTE_HTTP_ERROR", "EXTERNAL_RETRYABLE", "navigation_failed", True
    if listings_seen == 0:
        return "PARSER_ERROR", "INTERNAL_CORRECTABLE", "no_property_links", True
    if details_requested == 0:
        return "SUCCESS_NO_NEW", "SUCCESS", "", False
    if valid_properties == 0:
        if details_requested <= 2 and listings_seen > details_requested:
            return (
                "DATA_QUALITY_EXTERNAL",
                "EXTERNAL_FINAL",
                "residual_incomplete_properties",
                False,
            )
        return "DATA_QUALITY_ERROR", "INTERNAL_CORRECTABLE", "no_valid_properties", True
    if ambiguous_identity > 0:
        return (
            "IDENTITY_CONFLICT",
            "FALSE_POSITIVE",
            "identity_guardrail_rejection",
            False,
        )
    if dry_run or db_writes == valid_properties:
        return "SUCCESS_NEW", "SUCCESS", "", False
    # batch_save_only_new only returns fewer rows when the DB unique hash guard
    # rejects duplicates during its row-by-row 409 fallback. Any real HTTP/DB
    # failure raises and sets had_error above; a clean partial result is dedup.
    if 0 <= db_writes < valid_properties:
        return "SUCCESS_WITH_DEDUP", "SUCCESS", "", False
    return "DB_ERROR", "INTERNAL_RETRYABLE", "invalid_insert_count", True

# ---------------------------------------------------------------------------
# Diagnostico de memoria — TRACE_MEMORY=1 (default: apagado / OFF)
# Con TRACE_MEMORY=0 (default) todo el codigo de este bloque es dead-code:
# los if _TRACE_MEMORY: se evaluan False y no se ejecuta nada.
# Sin impacto en scraping, dedup, saves, semaforo ni dry_run.
# ---------------------------------------------------------------------------

_TRACE_MEMORY: bool = os.environ.get("TRACE_MEMORY", "0") == "1"
_TM_SNAP_S0 = None  # tracemalloc.Snapshot | None — se setea en _tm_init()


def _tm_init() -> None:
    """Inicia tracemalloc y toma snapshot S0 (baseline global). Solo si TRACE_MEMORY=1."""
    global _TM_SNAP_S0
    if not _TRACE_MEMORY:
        return
    import tracemalloc
    out_dir = Path(
        os.environ.get(
            "TRACE_MEMORY_DIR",
            str(Path(__file__).resolve().parent.parent / "_scratch" / "tm_diag"),
        )
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("_TM_RESOLVED_DIR", str(out_dir))
    tracemalloc.start(25)
    gc.collect()
    _TM_SNAP_S0 = tracemalloc.take_snapshot()
    logger.info(f"[TRACEMALLOC] Iniciado | nframe=25 | S0 tomado | out_dir={out_dir}")


def _tm_log_source(
    worker_id: int,
    key: str,
    n: int,
    elapsed_s: float,
    snap_s1,
    snap_s2,
    snap_s3,
    rss_s1: float,
    rss_s2: float,
    rss_s3: float,
    tm_s1: tuple,
    tm_s3: tuple,
    gc_cnt_pre: tuple,
    gc_collected: int,
    hijos: int,
    tree_rss: float,
) -> None:
    """Escribe reporte tracemalloc de una fuente en tm_diag/. Solo con TRACE_MEMORY=1."""
    out_dir = Path(os.environ.get("_TM_RESOLVED_DIR", "_scratch/tm_diag"))
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    diff_s3_s1 = snap_s3.compare_to(snap_s1, "lineno")
    diff_s3_s2 = snap_s3.compare_to(snap_s2, "lineno")
    diff_global = snap_s3.compare_to(_TM_SNAP_S0, "filename") if _TM_SNAP_S0 else []

    top20_net  = [str(s) for s in diff_s3_s1[:20]]
    top10_gc   = [str(s) for s in diff_s3_s2[:10]]
    top10_glob = [str(s) for s in diff_global[:10]]

    report_lines: List[str] = [
        "=" * 65,
        f"[TM] FUENTE #{n:02d} | W{worker_id} | key={key}",
        f"[TM] timestamp_utc   : {ts}",
        f"[TM] elapsed         : {elapsed_s:.1f}s  ({elapsed_s / 60:.1f} min)",
        "",
        f"[TM] RSS parent (MB) : S1={rss_s1:.2f}  "
        f"S2(post-close)={rss_s2:.2f}  S3(post-gc)={rss_s3:.2f}",
        f"[TM] delta_rss_mb    : {rss_s3 - rss_s1:+.2f}  (neto S3-S1 por fuente)",
        f"[TM] RSS tree   (MB) : {tree_rss:.2f}  |  hijos={hijos}",
        "",
        f"[TM] tm_current (MB) : S1={tm_s1[0] / 1e6:.3f}  S3={tm_s3[0] / 1e6:.3f}  "
        f"delta={(tm_s3[0] - tm_s1[0]) / 1e6:+.3f}",
        f"[TM] tm_peak    (MB) : S1={tm_s1[1] / 1e6:.3f}  S3={tm_s3[1] / 1e6:.3f}",
        "",
        f"[TM] gc_count_before : gen0={gc_cnt_pre[0]}  gen1={gc_cnt_pre[1]}  gen2={gc_cnt_pre[2]}",
        f"[TM] gc_collected    : {gc_collected}  objetos recolectados (Fix-A)",
        "",
        "[TM] TOP 20 diff S3-S1 (net leak por fuente — candidatos a leak si > 0):",
    ]
    report_lines += (
        [f"     {line}" for line in top20_net]
        if top20_net
        else ["     (sin diferencias — heap estable post gc.collect)"]
    )
    report_lines += [
        "",
        "[TM] TOP 10 diff S3-S2 (lo que gc.collect limpio mas alla de browser.close):",
    ]
    report_lines += (
        [f"     {line}" for line in top10_gc]
        if top10_gc
        else ["     (sin diferencias — browser.close ya limpio todo)"]
    )
    report_lines += [
        "",
        "[TM] TOP 10 global S3-S0 (acumulado desde inicio del proceso, por modulo):",
    ]
    report_lines += (
        [f"     {line}" for line in top10_glob]
        if top10_glob
        else ["     (S0 no disponible o sin diferencias)"]
    )
    report_lines.append("=" * 65)

    report = "\n".join(report_lines) + "\n"
    fname = out_dir / f"tm_{n:02d}_{key[:35]}.txt"
    try:
        fname.write_text(report, encoding="utf-8")
    except Exception as _e:
        logger.warning(f"[TM] No se pudo escribir {fname}: {_e}")

    csv_path = out_dir / "tm_timeline.csv"
    write_header = not csv_path.exists()
    try:
        with open(csv_path, "a", encoding="utf-8") as _f:
            if write_header:
                _f.write(
                    "ts_utc,worker_id,n,key,elapsed_s,"
                    "rss_s1_mb,rss_s2_mb,rss_s3_mb,delta_rss_mb,"
                    "tm_current_s1_mb,tm_current_s3_mb,delta_tm_mb,"
                    "tm_peak_s3_mb,gc_collected,hijos,tree_rss_mb\n"
                )
            _f.write(
                f"{ts},{worker_id},{n},{key},{elapsed_s:.1f},"
                f"{rss_s1:.2f},{rss_s2:.2f},{rss_s3:.2f},{rss_s3 - rss_s1:+.2f},"
                f"{tm_s1[0] / 1e6:.3f},{tm_s3[0] / 1e6:.3f},"
                f"{(tm_s3[0] - tm_s1[0]) / 1e6:+.3f},"
                f"{tm_s3[1] / 1e6:.3f},{gc_collected},{hijos},{tree_rss:.2f}\n"
            )
    except Exception as _e:
        logger.warning(f"[TM] No se pudo escribir CSV: {_e}")


# S0 se toma al cargar el modulo si TRACE_MEMORY=1.
# Con TRACE_MEMORY=0 (default) esta linea es un no-op inmediato.
if _TRACE_MEMORY:
    _tm_init()


# ---------------------------------------------------------------------------
# Carga de fuentes desde Supabase
# ---------------------------------------------------------------------------


def load_fuentes_from_db(session: requests.Session) -> List[Dict[str, Any]]:
    """Lee inmobiliarias_scraping y genera una fuente venta + alquiler por inmobiliaria."""
    try:
        headers = {
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        }
        resp = session.get(
            f"{SUPABASE_URL.rstrip('/')}/rest/v1/inmobiliarias_scraping",
            headers=headers,
            params={"select": "nombre,web,ciudad", "web": "not.is.null", "limit": 5000},
            timeout=20,
        )
        resp.raise_for_status()
        rows = resp.json()

        if not rows:
            logger.warning("Tabla inmobiliarias_scraping vacía — usando fuentes hardcodeadas")
            return []

        # URLs que no son sitios propios de una inmobiliaria — no scrapeables
        SKIP_URL_PATTERNS = [
            # Redes sociales
            "facebook.com", "instagram.com", "twitter.com", "x.com",
            "tiktok.com", "linkedin.com", "youtube.com", "youtu.be",
            # Portales inmobiliarios (no scrapar, son competencia/portales)
            "mercadolibre.com", "argenprop.com", "zonaprop.com", "properati.com",
            "navent.com", "inmuebles24.com", "mitula.com.ar", "nuroa.com.ar",
            "vivareal.com", "imovelweb.com", "bluepillow.com",
            # Mensajería y redes de contacto
            "linktr.ee", "wa.me", "whatsapp.com", "t.me", "telegram.me",
            # Acortadores de URL y blogs genéricos
            "bit.ly", "walink.co", "tinyurl.com", "short.link",
            "wordpress.com", "blogspot.com", "wixsite.com",
            # Mapas / directorios
            "maps.google", "google.com", "yelp.com",
            # Sitios de viaje / turismo / alquiler vacacional (no son inmobiliarias)
            "airbnb.com", "booking.com", "tripadvisor.com",
            "wanderlust-ways.eu", "colonturismo.tur.ar",
        ]

        fuentes = []
        skipped_no_url = 0
        skipped_social = 0
        skipped_dup = 0
        seen_domains: Set[str] = set()

        for row in rows:
            web = (row.get("web") or "").strip()
            nombre = (row.get("nombre") or "").strip()
            if not web:
                continue

            # ── Validar que sea una URL real (descarta direcciones físicas y CP) ──
            # Muchos registros de Google Maps tienen la dirección física como web:
            # "C1416EQC Cdad. Autónoma de Buenos Aires", "Av. La Plata 3501", etc.
            if not web.startswith(("http://", "https://")):
                skipped_no_url += 1
                logger.debug(f"Saltando web inválida (no es URL): {web}")
                continue

            # ── Filtrar URLs de redes sociales y portales no scrapeables ──────────
            if any(pat in web.lower() for pat in SKIP_URL_PATTERNS):
                skipped_social += 1
                logger.debug(f"Saltando URL no scrapeable: {web}")
                continue

            # ── Deduplicar por dominio normalizado (www.X == X) ──────────────────
            try:
                parsed = urlparse(web)
                domain = parsed.netloc.lower()
                if domain.startswith("www."):
                    domain = domain[4:]
            except Exception:
                domain = web
            if domain in seen_domains:
                skipped_dup += 1
                logger.debug(f"Saltando dominio duplicado: {domain}")
                continue
            seen_domains.add(domain)

            key = (
                nombre.lower().replace(" ", "_")[:40]
                if nombre
                else web.split("//")[-1].split("/")[0]
            )
            # Una sola fuente por inmobiliaria — la operación se detecta por card.
            # Antes se generaban /Venta y /Alquiler por separado, lo que causaba
            # el doble de requests y fallaba en sitios que no son Tokko Broker.
            fuentes.append(
                {
                    "key": key,
                    "web": web.rstrip("/"),
                    "web_base": web,
                    "ciudad": row.get("ciudad") or "",
                    "operacion": None,   # detectado por card en parse_cards
                    "tipo_cms": "tokko",
                }
            )

        logger.info(
            f"Fuentes desde DB: {len(rows)} registros → {len(fuentes)} fuentes válidas "
            f"({skipped_no_url} sin URL, {skipped_social} redes sociales/portales, "
            f"{skipped_dup} dominios duplicados)"
        )
        return fuentes

    except Exception as exc:
        logger.warning(f"No se pudo leer DB: {exc} — usando fallback hardcodeado")
        return []


def build_fuentes_hardcoded() -> List[Dict[str, Any]]:
    """
    Fallback: convierte FUENTES + FUENTES_NUEVAS al formato estándar.
    Mantiene cada URL de venta y alquiler por separado para maximizar cobertura.
    Deduplica solo por URL exacta (no por dominio) para evitar visitar la misma página dos veces.
    """
    seen_urls: Set[str] = set()
    result: List[Dict[str, Any]] = []

    for f in FUENTES + FUENTES_NUEVAS:
        raw_url = f.get("url", "")
        if not raw_url or raw_url in seen_urls:
            continue
        seen_urls.add(raw_url)

        result.append(
            {
                "key": f["key"],
                "web": raw_url,
                "ciudad": f.get("ciudad", ""),
                "operacion": f.get("operacion"),
                "tipo_cms": "tokko",
            }
        )

    logger.info(f"Fuentes hardcodeadas: {len(FUENTES + FUENTES_NUEVAS)} entradas → {len(result)} URLs únicas")
    return result


# ---------------------------------------------------------------------------
# Worker: un browser por lote de fuentes
# ---------------------------------------------------------------------------


def _scrape_batch(
    fuentes_batch: List[Dict[str, Any]],
    supabase: SupabaseClient,
    existing_urls: Set[str],
    lock: threading.Lock,
    dry_run: bool,
    worker_id: int,
    on_source_done=None,
    metrics_log=None,
    safe_merge_existing: bool = False,
    run_id: Optional[str] = None,
) -> int:
    """
    Lanza un browser propio por fuente (Fix-E), procesa cada fuente en serie y cierra.
    Retorna cantidad de propiedades nuevas guardadas.

    Fix-B: sync_playwright() se abre y cierra por fuente (dentro del semáforo),
    liberando el estado interno de Playwright/pyee entre fuentes.
    Fix-C: referencias grandes se anulan en el finally externo, después de pw.__exit__,
    para que gc.collect() opere sin objetos Playwright vivos.
    gc.collect() y on_source_done() corren después de pw.__exit__: el node.exe ya
    terminó cuando se mide la RAM.
    """
    total = 0
    _tm_iter: int = 0
    _tm_t0: float = time.time() if _TRACE_MEMORY else 0.0
    for fuente in fuentes_batch:
        key = fuente.get("key") or fuente.get("nombre", "?")
        url = fuente.get("web", "")
        ciudad = fuente.get("ciudad", "") or ""
        operacion = fuente.get("operacion") or None

        if not url:
            continue

        t_source_start = time.time()
        _started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        t_sem_acquired = t_source_start   # pre-init; overwritten inside semaphore
        _n_listado = _n_nuevas = _n_validas = 0
        _pages_loaded = _navigation_failures = 0
        _had_timeout = _had_error = False
        _error_sanitized = ""
        _navigation_events: List[Dict[str, Any]] = []
        _listing_timeout_count = _detail_timeout_count = _detail_error_count = 0
        _details_succeeded = _detail_retry_attempts = 0
        _source_abort_reason = ""
        _last_progress_at = time.monotonic()
        _listing_timeout_ms = _source_int(
            fuente, "listing_timeout_ms", BASE_LISTING_TIMEOUT_MS, 5_000, 60_000
        )
        _detail_timeout_ms = _source_int(
            fuente, "detail_timeout_ms", BASE_DETAIL_TIMEOUT_MS, 5_000, 45_000
        )
        _detail_retries = _source_int(
            fuente, "detail_retries", BASE_DETAIL_RETRIES, 0, 2
        )
        _retry_backoff_s = max(
            0.1,
            min(2.0, float(fuente.get("retry_backoff_s") or BASE_RETRY_BACKOFF_S)),
        )
        _source_no_progress_s = _source_int(
            fuente,
            "source_no_progress_s",
            BASE_SOURCE_NO_PROGRESS_S,
            60,
            600,
        )
        _source_hard_cap_s = calculate_source_hard_cap(fuente, 0)

        def _record_navigation(event: Dict[str, Any]) -> None:
            nonlocal _listing_timeout_count, _detail_timeout_count, _detail_error_count
            _navigation_events.append(event)
            if event.get("status") == "timeout":
                if event.get("stage") == "listing":
                    _listing_timeout_count += 1
                elif event.get("stage") == "detail":
                    _detail_timeout_count += 1
            elif event.get("status") == "error" and event.get("stage") == "detail":
                _detail_error_count += 1

        # -- S1: snapshot baseline de esta fuente (antes del semáforo) -------
        if _TRACE_MEMORY:
            import tracemalloc
            import psutil as _psutil
            _tm_iter    += 1
            _snap_s1     = tracemalloc.take_snapshot()
            _tm_s1       = tracemalloc.get_traced_memory()
            _psutil_proc = _psutil.Process()
            _rss_s1      = _psutil_proc.memory_info().rss / 1e6
            _gc_cnt_pre  = gc.get_count()
        with _ACTIVE_BROWSER_SEM:                           # Fix-S: slot adquirido antes del launch
            t_sem_acquired = time.time()
            _source_browser_started = time.monotonic()
            _last_progress_at = _source_browser_started
            browser = None
            context = None
            page = None
            _source_props_saved = 0
            _source_db_writes = 0
            _source_merge_stats: Dict[str, int] = {}
            # Fix-C: pre-inicializar referencias grandes a None dentro del semáforo,
            # fuera del try, para que el finally externo pueda anularlas de forma
            # segura sin riesgo de UnboundLocalError si el try falla antes de asignarlas.
            all_prop_urls         = None
            listing_props_by_url  = None
            props_basicos         = None
            visited_listing       = None
            pending_pages         = None
            html                  = None
            initial_html          = None
            nuevas_urls           = None
            nuevas_final          = None
            propiedades_completas = None
            try:
                with sync_playwright() as pw:               # Fix-B: pw por fuente, dentro del semáforo
                    try:
                        browser = pw.chromium.launch(headless=True, args=BROWSER_ARGS)
                        context = browser.new_context(
                            user_agent=BROWSER_UA,
                            viewport={"width": 1366, "height": 768},
                            locale="es-AR",
                        )
                        page = context.new_page()
                        logger.info(f"[W{worker_id}][{key}] → {url}")

                        # ═══════════════════════════════════════════════════════════
                        # FASE 1 — Recolectar todas las URLs del listado (+ paginación)
                        # ═══════════════════════════════════════════════════════════
                        base_url = "/".join(url.split("/")[:3])
                        all_prop_urls = []
                        listing_props_by_url = {}
                        visited_listing = set()
                        pending_pages = [url]
                        MAX_LISTING_PAGES = 15  # límite de seguridad contra loops

                        while pending_pages and len(visited_listing) < MAX_LISTING_PAGES:
                            if time.monotonic() - _source_browser_started > _source_hard_cap_s:
                                _source_abort_reason = "source_hard_cap"
                                _had_timeout = True
                                break
                            listing_url = pending_pages.pop(0)
                            if listing_url in visited_listing:
                                continue
                            visited_listing.add(listing_url)

                            ok = _goto_safe(
                                page,
                                listing_url,
                                _listing_timeout_ms,
                                navigation_callback=_record_navigation,
                                stage="listing",
                            )
                            if not ok:
                                _navigation_failures += 1
                                logger.warning(f"[W{worker_id}][{key}] No se pudo cargar: {listing_url}")
                                if time.monotonic() - _last_progress_at > _source_no_progress_s:
                                    _source_abort_reason = "source_no_progress"
                                    _had_timeout = True
                                    break
                                continue

                            _pages_loaded += 1
                            _last_progress_at = time.monotonic()

                            page.wait_for_timeout(3000)
                            try:
                                page.wait_for_selector(
                                    'a[href*="/propiedad/"], a[href*="/inmueble/"], '
                                    'a[href*="/home-details/"], a[href*="/p/"], '
                                    '[class*="property-card"], .pcard',
                                    state="attached",
                                    timeout=8000,
                                )
                            except Exception:
                                pass
                            current_listing_base_url = (
                                "/".join(page.url.split("/")[:3])
                                if page.url.startswith(("http://", "https://"))
                                else base_url
                            )
                            initial_html = page.content()
                            scroll_to_bottom(page)

                            # Esperar renderizado JS de precios/cards
                            try:
                                page.wait_for_selector(
                                    "[class*='price'],[class*='precio'],"
                                    ".prop-precio,.property-price,.aviso-precio",
                                    state="visible", timeout=4000,
                                )
                            except Exception:
                                pass

                            html = page.content()
                            props_basicos = []
                            for snapshot_html in dict.fromkeys((initial_html, html)):
                                if snapshot_html:
                                    props_basicos.extend(
                                        parse_cards(
                                            snapshot_html,
                                            operacion,
                                            key,
                                            current_listing_base_url,
                                            ciudad,
                                        )
                                    )
                            for frame in page.frames[1:6]:
                                frame_url = frame.url or ""
                                frame_host = urlparse(frame_url).netloc.lower()
                                if (
                                    not frame_url.startswith(("http://", "https://"))
                                    or any(blocked in frame_host for blocked in (
                                        "google.", "googletagmanager.", "facebook.",
                                        "recaptcha.", "addtoany.", "abrachat.",
                                        "zonaprop.", "argenprop.", "properati.",
                                    ))
                                ):
                                    continue
                                try:
                                    frame_html = frame.content()
                                    frame_base = f"{urlparse(frame_url).scheme}://{frame_host}"
                                    props_basicos.extend(
                                        parse_cards(frame_html, operacion, key, frame_base, ciudad)
                                    )
                                except Exception as exc:
                                    logger.debug(
                                        f"[W{worker_id}][{key}] iframe omitido: "
                                        f"{_sanitize_source_error(exc)}"
                                    )
                            if not props_basicos:
                                alternatives = discover_listing_page_urls(
                                    html or initial_html or "",
                                    listing_url,
                                )
                                if base_url.rstrip("/") != listing_url.rstrip("/"):
                                    alternatives.append(base_url)
                                for alternative in alternatives:
                                    if (
                                        alternative not in visited_listing
                                        and alternative not in pending_pages
                                    ):
                                        pending_pages.append(alternative)
                            else:
                                # Parsing a rendered listing is meaningful progress.
                                # Without this refresh, large JS pages can exceed the
                                # no-progress window before the first detail starts.
                                _last_progress_at = time.monotonic()
                            for p in props_basicos:
                                if p.url not in all_prop_urls:
                                    all_prop_urls.append(p.url)
                                current_seed = listing_props_by_url.get(p.url)
                                if (
                                    current_seed is None
                                    or _listing_seed_score(p) > _listing_seed_score(current_seed)
                                ):
                                    listing_props_by_url[p.url] = p

                            # Detectar paginación numerada (no aplica a Tokko scroll infinito)
                            next_url = _get_next_page_url(html, listing_url)
                            if next_url and next_url not in visited_listing:
                                pending_pages.append(next_url)

                        blocked_detail_count = sum(
                            1 for prop_url in all_prop_urls
                            if _is_prohibited_detail_url(prop_url)
                        )
                        if blocked_detail_count:
                            logger.warning(
                                f"[W{worker_id}][{key}] Portales de terceros bloqueados: "
                                f"{blocked_detail_count}"
                            )
                            all_prop_urls = [
                                prop_url for prop_url in all_prop_urls
                                if not _is_prohibited_detail_url(prop_url)
                            ]

                        logger.info(
                            f"[W{worker_id}][{key}] {len(all_prop_urls)} URLs en "
                            f"{len(visited_listing)} página(s) de listado"
                        )
                        _n_listado = len(all_prop_urls)

                        # ── Filtrar solo las que no están en DB ──────────────────────
                        with lock:
                            nuevas_urls = (
                                list(all_prop_urls)
                                if safe_merge_existing
                                else [u for u in all_prop_urls if u not in existing_urls]
                            )
                        _n_nuevas = len(nuevas_urls)
                        _source_hard_cap_s = calculate_source_hard_cap(fuente, _n_nuevas)

                        if not nuevas_urls:
                            logger.debug(f"[W{worker_id}][{key}] Sin propiedades nuevas")
                            continue

                        logger.info(f"[W{worker_id}][{key}] {len(nuevas_urls)} fichas nuevas a scrapear")

                        # ═══════════════════════════════════════════════════════════
                        # FASE 2 — Visitar cada ficha individual para datos completos
                        # ═══════════════════════════════════════════════════════════
                        inmo_id = fuente.get("inmobiliaria_id")
                        propiedades_completas = []
                        for i, prop_url in enumerate(nuevas_urls, 1):
                            if _is_prohibited_detail_url(prop_url):
                                logger.warning(
                                    f"[W{worker_id}][{key}] Portal de terceros bloqueado "
                                    "antes de navegar ficha"
                                )
                                continue
                            now_mono = time.monotonic()
                            if now_mono - _source_browser_started > _source_hard_cap_s:
                                _source_abort_reason = "source_hard_cap"
                                _had_timeout = True
                                break
                            if now_mono - _last_progress_at > _source_no_progress_s:
                                _source_abort_reason = "source_no_progress"
                                _had_timeout = True
                                break
                            listing_seed = listing_props_by_url.get(prop_url)
                            prop = _property_from_listing_seed(
                                listing_seed,
                                url=prop_url,
                                fuente=key,
                                ciudad=ciudad or None,
                                operacion=operacion,
                                inmobiliaria_id=inmo_id,
                            )
                            ok = False
                            if _uses_listing_shell_detail(key, prop_url, url):
                                # This route is still the listing shell. Its global
                                # h1, prices, images and specs can belong to another
                                # card, so only the isolated card seed is trusted.
                                shell_prop = _property_from_listing_shell_seed(
                                    listing_seed,
                                    url=prop_url,
                                    fuente=key,
                                    ciudad=ciudad or None,
                                    operacion=operacion,
                                    inmobiliaria_id=inmo_id,
                                )
                                ok = shell_prop is not None
                                if ok:
                                    prop = shell_prop
                                    _details_succeeded += 1
                                    _last_progress_at = time.monotonic()
                                logger.info(
                                    f"[W{worker_id}][{key}] LISTING_SHELL_DETAIL "
                                    f"card_only={bool(ok)}"
                                )
                            for attempt in (
                                range(1, _detail_retries + 2) if not ok else ()
                            ):
                                event_start = len(_navigation_events)
                                ok = scrape_detail_page(
                                    page,
                                    prop,
                                    key,
                                    timeout=_detail_timeout_ms,
                                    navigation_callback=_record_navigation,
                                    attempt=attempt,
                                )
                                if ok:
                                    _details_succeeded += 1
                                    _last_progress_at = time.monotonic()
                                    break
                                latest = (
                                    _navigation_events[-1]
                                    if len(_navigation_events) > event_start
                                    else {}
                                )
                                if latest.get("status") != "timeout" or attempt > _detail_retries:
                                    break
                                _detail_retry_attempts += 1
                                time.sleep(_retry_backoff_s * attempt)
                                if time.monotonic() - _last_progress_at > _source_no_progress_s:
                                    _source_abort_reason = "source_no_progress"
                                    _had_timeout = True
                                    break
                            if ok:
                                # Garantizar barrio mínimo
                                if not prop.barrio:
                                    prop.barrio = ciudad or "Argentina"
                                if prop.is_valid():
                                    propiedades_completas.append(prop)
                            if _source_abort_reason:
                                break
                            if i % 10 == 0:
                                logger.debug(
                                    f"[W{worker_id}][{key}] Fichas: {i}/{len(nuevas_urls)}"
                                )

                        if _source_abort_reason:
                            _error_sanitized = _source_abort_reason
                            logger.warning(
                                f"[W{worker_id}][{key}] Fuente interrumpida: "
                                f"{_source_abort_reason} | completadas={_details_succeeded}/"
                                f"{len(nuevas_urls)}"
                            )

                        # ── Guardar ──────────────────────────────────────────────────
                        with lock:
                            # Re-filtrar por si otro worker guardó algunas en paralelo
                            nuevas_final = (
                                list(propiedades_completas)
                                if safe_merge_existing
                                else [
                                    p for p in propiedades_completas
                                    if p.url not in existing_urls
                                ]
                            )
                            _n_validas = len(nuevas_final)
                            logger.info(
                                f"[W{worker_id}][{key}] {len(nuevas_final)} válidas "
                                f"/ {len(nuevas_urls)} nuevas"
                            )
                            if nuevas_final and safe_merge_existing:
                                if not run_id:
                                    raise RuntimeError("Safe merge mode requires an audited run_id")
                                payloads = [p.to_payload() for p in nuevas_final]
                                _source_merge_stats = supabase.batch_save_safe_merge(
                                    payloads,
                                    source_id=fuente.get("source_id"),
                                    run_id=run_id,
                                    dry_run=dry_run,
                                )
                                _source_props_saved = int(
                                    _source_merge_stats.get("db_inserts", 0)
                                )
                                _source_db_writes = (
                                    _source_props_saved
                                    + int(_source_merge_stats.get("db_updates", 0))
                                )
                                existing_urls.update(p.url for p in nuevas_final)
                                total += _source_props_saved
                                logger.info(
                                    f"[W{worker_id}][{key}] Safe merge: "
                                    f"inserts={_source_props_saved} "
                                    f"updates={_source_merge_stats.get('db_updates', 0)} "
                                    f"matched={_source_merge_stats.get('existing_matched', 0)}"
                                )
                            elif nuevas_final and not dry_run:
                                payloads = [p.to_payload() for p in nuevas_final]
                                try:
                                    saved = supabase.batch_save_only_new(payloads)
                                except PartialBatchInsertError as exc:
                                    _source_props_saved = exc.saved_count
                                    _source_db_writes = exc.saved_count
                                    total += exc.saved_count
                                    existing_urls.update(
                                        str(payload.get("url"))
                                        for payload in exc.saved_payloads
                                        if payload.get("url")
                                    )
                                    logger.warning(
                                        f"[W{worker_id}][{key}] INSERT parcial confirmado: "
                                        f"{exc.saved_count}"
                                    )
                                    raise
                                existing_urls.update(p.url for p in nuevas_final)
                                total += saved
                                _source_props_saved = saved
                                _source_db_writes = saved
                                logger.info(f"[W{worker_id}][{key}] Guardadas: {saved}")
                            elif nuevas_final and dry_run:
                                for p in nuevas_final[:3]:
                                    logger.info(f"  [DRY] {p.titulo[:60]} | {p.url}")
                                total += len(nuevas_final)

                    except PwTimeout:
                        _had_timeout = True
                        _error_sanitized = "Playwright timeout"
                        logger.warning(f"[W{worker_id}][{key}] Timeout en {url}")
                    except Exception as exc:
                        _had_error = True
                        _error_sanitized = _sanitize_source_error(exc)
                        logger.error(f"[W{worker_id}][{key}] Error: {_error_sanitized}")
                    finally:
                        if page is not None:
                            try:
                                page.close()
                            except Exception:
                                pass
                        if context is not None:
                            try:
                                context.close()
                            except Exception:
                                pass
                        if browser is not None:
                            try:
                                browser.close()
                            except Exception:
                                pass
                # ← sync_playwright() cerrado: pw.__exit__ corrió, node.exe terminado (Fix-B)
            finally:
                # Fix-C: anular referencias grandes DESPUÉS de pw.__exit__.
                # Pre-inicializadas a None dentro del sem → nunca UnboundLocalError.
                all_prop_urls         = None
                listing_props_by_url  = None
                props_basicos         = None
                visited_listing       = None
                pending_pages         = None
                html                  = None
                initial_html          = None
                nuevas_urls           = None
                nuevas_final          = None
                propiedades_completas = None
                # -- S2 / S3: snapshots post pw.__exit__ + Fix-C, luego post-gc --
                if _TRACE_MEMORY:
                    _snap_s2      = tracemalloc.take_snapshot()       # S2: post pw.__exit__ + Fix-C
                    _rss_s2       = _psutil_proc.memory_info().rss / 1e6
                    _gc_collected = gc.collect()                       # Fix-A (captura resultado)
                    _snap_s3      = tracemalloc.take_snapshot()       # S3: post gc.collect
                    _tm_s3        = tracemalloc.get_traced_memory()
                    _rss_s3       = _psutil_proc.memory_info().rss / 1e6
                    _tree_rss_b   = _psutil_proc.memory_info().rss
                    _hijos_count  = 0
                    for _c in _psutil_proc.children(recursive=True):
                        try:
                            _tree_rss_b  += _c.memory_info().rss
                            _hijos_count += 1
                        except (_psutil.NoSuchProcess, _psutil.AccessDenied):
                            pass
                    _tm_log_source(
                        worker_id    = worker_id,
                        key          = key,
                        n            = _tm_iter,
                        elapsed_s    = time.time() - _tm_t0,
                        snap_s1      = _snap_s1,
                        snap_s2      = _snap_s2,
                        snap_s3      = _snap_s3,
                        rss_s1       = _rss_s1,
                        rss_s2       = _rss_s2,
                        rss_s3       = _rss_s3,
                        tm_s1        = _tm_s1,
                        tm_s3        = _tm_s3,
                        gc_cnt_pre   = _gc_cnt_pre,
                        gc_collected = _gc_collected,
                        hijos        = _hijos_count,
                        tree_rss     = _tree_rss_b / 1e6,
                    )
                else:
                    gc.collect()                                       # Fix-A (sin TRACE_MEMORY)
                if on_source_done:
                    on_source_done(key, _source_props_saved)
                if metrics_log is not None:
                    _source_time_s = round(time.time() - t_source_start, 1)
                    _sem_wait_s    = round(t_sem_acquired - t_source_start, 1)
                    _finished_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    _status, _classification, _error_type, _retryable = classify_source_metrics(
                        pages=_pages_loaded,
                        listings_seen=_n_listado,
                        details_requested=_n_nuevas,
                        valid_properties=_n_validas,
                        db_writes=_source_db_writes,
                        had_timeout=_had_timeout,
                        had_error=_had_error,
                        dry_run=dry_run,
                        ambiguous_identity=int(
                            _source_merge_stats.get("ambiguous_identity", 0)
                        ),
                    )
                    try:
                        import psutil as _metrics_psutil
                        _memory_mb = round(_metrics_psutil.Process().memory_info().rss / 1_048_576, 1)
                    except Exception:
                        _memory_mb = ""
                    metric = {
                        "ts_utc":         _finished_at,
                        "worker_id":      worker_id,
                        "key":            key,
                        "source_id":      fuente.get("source_id", ""),
                        "inmobiliaria_id": fuente.get("inmobiliaria_id", ""),
                        "nombre":         fuente.get("_manifest_name") or fuente.get("nombre") or key,
                        "started_at":     _started_at,
                        "finished_at":    _finished_at,
                        "source_time_s":  _source_time_s,
                        "sem_wait_s":     _sem_wait_s,
                        "browser_time_s": round(_source_time_s - _sem_wait_s, 1),
                        "status":          _status,
                        "classification":  _classification,
                        "pages":           _pages_loaded,
                        "n_listado":      _n_listado,
                        "n_nuevas":       _n_nuevas,
                        "n_validas":      _n_validas,
                        "props_saved":    _source_props_saved,
                        "existing_properties_matched": int(
                            _source_merge_stats.get("existing_matched", 0)
                        ),
                        "existing_properties_improved": int(
                            _source_merge_stats.get("existing_improved", 0)
                        ),
                        "fields_improved": int(
                            _source_merge_stats.get("fields_improved", 0)
                        ),
                        "fields_rejected": int(
                            _source_merge_stats.get("fields_rejected", 0)
                        ),
                        "db_inserts": int(
                            _source_merge_stats.get("db_inserts", _source_props_saved)
                        ),
                        "db_updates": int(
                            _source_merge_stats.get("db_updates", 0)
                        ),
                        "ambiguous_identity": int(
                            _source_merge_stats.get("ambiguous_identity", 0)
                        ),
                        "merge_audit_rows": int(
                            _source_merge_stats.get("audit_rows", 0)
                        ),
                        "duplicates_skipped": (
                            0
                            if safe_merge_existing
                            else (
                                max(0, _n_listado - _n_nuevas)
                                + max(0, _n_validas - _source_props_saved)
                            )
                        ),
                        "had_timeout":    _had_timeout,
                        "had_error":      _had_error,
                        "http_status":     "" if _pages_loaded else "navigation_failed",
                        "error_type":      _error_type,
                        "error_sanitized": _error_sanitized,
                        "retryable":       _retryable,
                        "retry_count":     0,
                        "memory_peak_mb":  _memory_mb,
                        "navigation_failures": _navigation_failures,
                        "listing_timeout_count": _listing_timeout_count,
                        "detail_timeout_count": _detail_timeout_count,
                        "detail_error_count": _detail_error_count,
                        "details_succeeded": _details_succeeded,
                        "detail_retry_attempts": _detail_retry_attempts,
                        "source_abort_reason": _source_abort_reason,
                        "listing_timeout_ms": _listing_timeout_ms,
                        "detail_timeout_ms": _detail_timeout_ms,
                        "detail_retries": _detail_retries,
                        "source_no_progress_s": _source_no_progress_s,
                        "source_hard_cap_s": _source_hard_cap_s,
                    }
                    with lock:
                        metrics_log.append(metric)
        # ← _ACTIVE_BROWSER_SEM liberado (Fix-S): slot disponible para el próximo source

    return total


# ---------------------------------------------------------------------------
# Scrapers especializados: cada uno obtiene su propio browser
# ---------------------------------------------------------------------------


def _run_pw_scraper(
    fn,
    supabase: SupabaseClient,
    existing_urls: Set[str],
    dry_run: bool,
) -> None:
    """Ejecuta un scraper especializado que necesita un BrowserContext sync."""
    if dry_run:
        logger.info(f"[{fn.__name__}] Saltado en dry-run")
        return
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=BROWSER_ARGS)
        context = browser.new_context(
            user_agent=BROWSER_UA,
            viewport={"width": 1366, "height": 768},
            locale="es-AR",
        )
        try:
            logger.info(f"[{fn.__name__}] Iniciando...")
            fn(supabase, existing_urls, context)
            logger.info(f"[{fn.__name__}] Completo")
        except Exception as exc:
            logger.error(f"[{fn.__name__}] Error: {exc}", exc_info=True)
        finally:
            try:
                context.close()
                browser.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Runner principal
# ---------------------------------------------------------------------------


def _split_batches(items: List, n: int) -> List[List]:
    """Divide una lista en n sublistas lo más equitativas posible."""
    if not items:
        return []
    size = math.ceil(len(items) / n)
    return [items[i : i + size] for i in range(0, len(items), size)]


def run(
    workers: int = DEFAULT_WORKERS,
    filtro_tipo: Optional[str] = None,
    dry_run: bool = False,
    skip_specialized: bool = False,
) -> None:
    """
    Orquestador principal:
      Fase 1 — fuentes Tokko genéricas en paralelo (ThreadPoolExecutor)
      Fase 2 — fuentes SOURCE_CONFIGS (config.py)
      Fase 3 — scrapers especializados (APL, Raffin, etc.)
    """
    session = SessionFactory.make()
    supabase = SupabaseClient(session, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_TABLE)

    # Cargar URLs ya existentes
    logger.info("Cargando URLs existentes desde Supabase...")
    existing_urls: Set[str] = set()
    try:
        existing_urls = supabase.get_all_existing_urls()
        logger.info(f"  {len(existing_urls)} URLs en DB")
    except Exception as exc:
        logger.warning(f"No se pudieron cargar URLs existentes: {exc}")

    # Cargar fuentes
    fuentes_db = load_fuentes_from_db(session)
    fuentes = fuentes_db if fuentes_db else build_fuentes_hardcoded()

    if filtro_tipo:
        fuentes = [f for f in fuentes if f.get("tipo_cms", "") == filtro_tipo]
        logger.info(f"Filtro tipo='{filtro_tipo}': {len(fuentes)} fuentes")

    logger.info(f"Total fuentes: {len(fuentes)} | workers: {workers}")

    lock = threading.Lock()
    t_start = time.time()
    total_guardadas = 0

    # ── Fase 1: fuentes genéricas Tokko en paralelo ───────────────────────────
    batches = _split_batches(fuentes, workers)
    logger.info(f"Fase 1: {len(fuentes)} fuentes en {len(batches)} lotes")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                _scrape_batch, batch, supabase, existing_urls, lock, dry_run, i
            ): i
            for i, batch in enumerate(batches)
        }
        for future in as_completed(futures):
            wid = futures[future]
            try:
                guardadas = future.result()
                total_guardadas += guardadas
                logger.info(f"[W{wid}] Lote completo — {guardadas} guardadas")
            except Exception as exc:
                logger.error(f"[W{wid}] Worker falló: {exc}", exc_info=True)

    # ── Fase 2: fuentes config.py ─────────────────────────────────────────────
    if not filtro_tipo or filtro_tipo == "config":
        logger.info("Fase 2: scrape_config_sources")
        _run_pw_scraper(scrape_config_sources, supabase, existing_urls, dry_run)

    # ── Fase 3: scrapers especializados ──────────────────────────────────────
    if not skip_specialized:
        logger.info("Fase 3: scrapers especializados")

        # Playwright-based: corren en paralelo, cada uno con su propio browser
        pw_scrapers = [
            scrape_apl,
            scrape_raffin,
            scrape_pilay,
            scrape_raes,
            scrape_nuevas_no_tokko,
        ]
        with ThreadPoolExecutor(max_workers=len(pw_scrapers)) as executor:
            futures_pw = {
                executor.submit(
                    _run_pw_scraper, fn, supabase, existing_urls, dry_run
                ): fn.__name__
                for fn in pw_scrapers
            }
            for future in as_completed(futures_pw):
                name = futures_pw[future]
                try:
                    future.result()
                except Exception as exc:
                    logger.error(f"[{name}] Error: {exc}")

        # HTTP-only: en serie para respetar rate limits
        if not dry_run:
            http_scrapers = [
                scrape_9010,
                scrape_lenarduzzi,
                scrape_cisfe,
                scrape_cam,
                scrape_sofia,
                scrape_casablanca,
                scrape_proa,
                scrape_sur,
                scrape_neo,
            ]
            for fn in http_scrapers:
                try:
                    logger.info(f"[{fn.__name__}] Iniciando...")
                    fn(supabase, existing_urls, session)
                    logger.info(f"[{fn.__name__}] Completo")
                except Exception as exc:
                    logger.error(f"[{fn.__name__}] Error: {exc}", exc_info=True)

    elapsed = time.time() - t_start
    logger.info(
        f"\n{'='*55}\n"
        f"SCRAPING COMPLETO\n"
        f"  Fuentes Fase 1     : {len(fuentes)}\n"
        f"  Guardadas Fase 1   : {total_guardadas}\n"
        f"  (Fases 2 y 3 guardan directamente — ver logs por scraper)\n"
        f"  Tiempo total       : {elapsed:.0f}s ({elapsed/60:.1f} min)\n"
        f"{'='*55}"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="ERETZ Propiedades — Scraper de propiedades",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python run.py
  python run.py --workers 6
  python run.py --dry-run --debug
  python run.py --skip-specialized
        """,
    )
    p.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"Browsers paralelos (default: {DEFAULT_WORKERS})",
    )
    p.add_argument(
        "--fuentes",
        metavar="TIPO",
        help="Filtrar por tipo de CMS: tokko | config",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Ejecutar sin guardar en Supabase",
    )
    p.add_argument(
        "--skip-specialized",
        action="store_true",
        dest="skip_specialized",
        help="Saltar scrapers especializados (APL, Raffin, etc.)",
    )
    p.add_argument("--debug", action="store_true", help="Activar logging DEBUG")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    run(
        workers=args.workers,
        filtro_tipo=args.fuentes,
        dry_run=args.dry_run,
        skip_specialized=args.skip_specialized,
    )
