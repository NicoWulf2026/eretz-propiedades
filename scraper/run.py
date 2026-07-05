"""
run.py — Entry point principal del sistema de scraping InmoCapital.

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
import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

import requests
from playwright.sync_api import TimeoutError as PwTimeout
from playwright.sync_api import sync_playwright

from clients import SessionFactory, SupabaseClient
from config import (
    SOURCE_CONFIGS,
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
) -> int:
    """
    Lanza un browser propio, procesa cada fuente del lote en serie y cierra.
    Retorna cantidad de propiedades nuevas guardadas.
    """
    total = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=BROWSER_ARGS)

        def _new_context():
            return browser.new_context(
                user_agent=BROWSER_UA,
                viewport={"width": 1366, "height": 768},
                locale="es-AR",
            )

        for fuente in fuentes_batch:
            key = fuente.get("key") or fuente.get("nombre", "?")
            url = fuente.get("web", "")
            ciudad = fuente.get("ciudad", "") or ""
            operacion = fuente.get("operacion") or None

            if not url:
                continue

            context = _new_context()
            _source_props_saved = 0
            page = None
            try:
                page = context.new_page()
                logger.info(f"[W{worker_id}][{key}] → {url}")

                # ═══════════════════════════════════════════════════════════
                # FASE 1 — Recolectar todas las URLs del listado (+ paginación)
                # ═══════════════════════════════════════════════════════════
                base_url = "/".join(url.split("/")[:3])
                all_prop_urls: List[str] = []
                visited_listing: set = set()
                pending_pages: List[str] = [url]
                MAX_LISTING_PAGES = 15  # límite de seguridad contra loops

                while pending_pages and len(visited_listing) < MAX_LISTING_PAGES:
                    listing_url = pending_pages.pop(0)
                    if listing_url in visited_listing:
                        continue
                    visited_listing.add(listing_url)

                    ok = _goto_safe(page, listing_url, 40_000)
                    if not ok:
                        logger.warning(f"[W{worker_id}][{key}] No se pudo cargar: {listing_url}")
                        continue

                    page.wait_for_timeout(3000)
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
                    props_basicos = parse_cards(html, operacion, key, base_url, ciudad)
                    for p in props_basicos:
                        if p.url not in all_prop_urls:
                            all_prop_urls.append(p.url)

                    # Detectar paginación numerada (no aplica a Tokko scroll infinito)
                    next_url = _get_next_page_url(html, listing_url)
                    if next_url and next_url not in visited_listing:
                        pending_pages.append(next_url)

                logger.info(
                    f"[W{worker_id}][{key}] {len(all_prop_urls)} URLs en "
                    f"{len(visited_listing)} página(s) de listado"
                )

                # ── Filtrar solo las que no están en DB ──────────────────────
                with lock:
                    nuevas_urls = [u for u in all_prop_urls if u not in existing_urls]

                if not nuevas_urls:
                    logger.debug(f"[W{worker_id}][{key}] Sin propiedades nuevas")
                    continue

                logger.info(f"[W{worker_id}][{key}] {len(nuevas_urls)} fichas nuevas a scrapear")

                # ═══════════════════════════════════════════════════════════
                # FASE 2 — Visitar cada ficha individual para datos completos
                # ═══════════════════════════════════════════════════════════
                inmo_id = fuente.get("inmobiliaria_id")
                propiedades_completas: List[Propiedad] = []
                for i, prop_url in enumerate(nuevas_urls, 1):
                    prop = Propiedad(
                        url=prop_url,
                        titulo="Sin título",
                        fuente=key,
                        ciudad=ciudad or None,
                        operacion=operacion,
                        barrio=ciudad or "Argentina",
                        inmobiliaria_id=inmo_id,
                    )
                    ok = scrape_detail_page(page, prop, key)
                    if ok:
                        # Garantizar barrio mínimo
                        if not prop.barrio:
                            prop.barrio = ciudad or "Argentina"
                        if prop.is_valid():
                            propiedades_completas.append(prop)
                    if i % 10 == 0:
                        logger.debug(
                            f"[W{worker_id}][{key}] Fichas: {i}/{len(nuevas_urls)}"
                        )

                # ── Guardar ──────────────────────────────────────────────────
                with lock:
                    # Re-filtrar por si otro worker guardó algunas en paralelo
                    nuevas_final = [
                        p for p in propiedades_completas
                        if p.url not in existing_urls
                    ]
                    logger.info(
                        f"[W{worker_id}][{key}] {len(nuevas_final)} válidas "
                        f"/ {len(nuevas_urls)} nuevas"
                    )
                    if nuevas_final and not dry_run:
                        saved = supabase.batch_save_only_new(
                            [p.to_payload() for p in nuevas_final]
                        )
                        existing_urls.update(p.url for p in nuevas_final)
                        total += saved
                        _source_props_saved = saved
                        logger.info(f"[W{worker_id}][{key}] Guardadas: {saved}")
                    elif nuevas_final and dry_run:
                        for p in nuevas_final[:3]:
                            logger.info(f"  [DRY] {p.titulo[:60]} | {p.url}")
                        total += len(nuevas_final)

            except PwTimeout:
                logger.warning(f"[W{worker_id}][{key}] Timeout en {url}")
            except Exception as exc:
                logger.error(f"[W{worker_id}][{key}] Error: {exc}", exc_info=True)
            finally:
                if page is not None:
                    try:
                        page.close()
                    except Exception:
                        pass
                try:
                    context.close()
                except Exception:
                    pass
                if on_source_done:
                    on_source_done(key, _source_props_saved)

        try:
            browser.close()
        except Exception:
            pass

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
        description="InmoCapital — Scraper de propiedades",
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
