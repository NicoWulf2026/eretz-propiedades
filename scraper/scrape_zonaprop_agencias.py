"""
scrape_zonaprop_agencias.py
Scrapea el directorio de inmobiliarias de ZonaProp y guarda en Supabase
(tabla inmobiliarias_scraping).

Las agencias scrapeadas de ZonaProp alimentan automáticamente al scraper
principal (run.py) a través de load_fuentes_from_db().

Uso:
    python scrape_zonaprop_agencias.py              # scrape + guardar
    python scrape_zonaprop_agencias.py --dry-run    # sin guardar
    python scrape_zonaprop_agencias.py --debug      # logs detallados
    python scrape_zonaprop_agencias.py --provincia "Buenos Aires"
"""

from __future__ import annotations

# === CONGELADO por política ERETZ Propiedades (2026-06-17) ===
# Todo lo relacionado con Zonaprop/Argenprop (incluido discovery de agencias) queda
# congelado hasta autorización explícita. Quitar este guard solo con esa autorización.
import sys as _sys
_sys.exit(
    "CONGELADO (politica ERETZ 2026-06-17): discovery Zonaprop/Argenprop deshabilitado. "
    "Requiere autorizacion explicita para reactivar."
)

import argparse
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

BASE_URL = "https://www.zonaprop.com.ar"
START_URL = "https://www.zonaprop.com.ar/inmobiliarias.bum"

BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-web-security",
]
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Columnas mínimas de la tabla inmobiliarias_scraping
# (nombre, web, ciudad son los campos que usa load_fuentes_from_db en run.py)
TABLA = "inmobiliarias_scraping"

# ---------------------------------------------------------------------------
# Extracción desde __NEXT_DATA__ (Next.js — más confiable que CSS selectors)
# ---------------------------------------------------------------------------

def _extraer_desde_next_data(html: str) -> List[Dict[str, Any]]:
    """
    ZonaProp usa Next.js. El JSON con todos los datos de la página está en
    <script id="__NEXT_DATA__">. Este método es el más confiable.
    """
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", {"id": "__NEXT_DATA__"})
    if not script:
        return []

    try:
        data = json.loads(script.string)
    except (json.JSONDecodeError, TypeError):
        return []

    agencias = []

    def _buscar_agencias(obj: Any, depth: int = 0) -> None:
        """Busca recursivamente listas de agencias dentro del JSON de Next.js."""
        if depth > 12 or not obj:
            return
        if isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict) and _parece_agencia(item):
                    ag = _mapear_agencia_nextdata(item)
                    if ag:
                        agencias.append(ag)
                else:
                    _buscar_agencias(item, depth + 1)
        elif isinstance(obj, dict):
            # Claves que suelen contener el listado de agencias
            for key in ("agencies", "agencias", "items", "results", "data",
                        "listItems", "agency", "realEstates"):
                if key in obj:
                    _buscar_agencias(obj[key], depth + 1)
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    _buscar_agencias(v, depth + 1)

    _buscar_agencias(data)

    # Deduplica por nombre
    seen: set = set()
    result = []
    for ag in agencias:
        key = (ag.get("nombre") or "").strip().lower()
        if key and key not in seen:
            seen.add(key)
            result.append(ag)

    return result


def _parece_agencia(obj: Dict) -> bool:
    """Heurística: ¿este dict del JSON parece ser una agencia inmobiliaria?"""
    keys = set(obj.keys())
    agency_keys = {"name", "nombre", "agencyName", "realEstateName",
                   "phone", "telefono", "web", "website", "logo", "logoUrl",
                   "listingCount", "propertyCount", "slug"}
    return bool(keys & agency_keys)


def _mapear_agencia_nextdata(obj: Dict) -> Optional[Dict[str, Any]]:
    """Mapea un dict del JSON Next.js a los campos de la tabla."""
    nombre = (
        obj.get("name") or obj.get("nombre") or obj.get("agencyName") or
        obj.get("realEstateName") or obj.get("displayName") or ""
    ).strip()
    if not nombre or len(nombre) < 2:
        return None

    web = (
        obj.get("web") or obj.get("website") or obj.get("websiteUrl") or
        obj.get("url") or obj.get("siteUrl") or ""
    ).strip()
    # Ignorar links internos de ZonaProp como web propia
    if web and "zonaprop.com" in web.lower():
        web = ""

    ciudad = (
        obj.get("city") or obj.get("ciudad") or obj.get("location") or
        obj.get("neighborhood") or obj.get("province") or
        obj.get("address", {}).get("city") if isinstance(obj.get("address"), dict) else None or
        ""
    )
    if isinstance(ciudad, dict):
        ciudad = ciudad.get("name") or ciudad.get("label") or ""
    ciudad = str(ciudad).strip() if ciudad else ""

    telefono = (
        obj.get("phone") or obj.get("telefono") or obj.get("phoneNumber") or ""
    )
    if isinstance(telefono, list):
        telefono = telefono[0] if telefono else ""
    telefono = str(telefono).strip() if telefono else ""

    logo = (
        obj.get("logo") or obj.get("logoUrl") or obj.get("logoImage") or
        obj.get("image") or obj.get("avatar") or ""
    )
    if isinstance(logo, dict):
        logo = logo.get("url") or logo.get("src") or ""
    logo = str(logo).strip() if logo else ""

    # Link a la ficha de la inmobiliaria dentro de ZonaProp
    link_zonaprop = (
        obj.get("slug") or obj.get("profileUrl") or obj.get("link") or
        obj.get("pageUrl") or ""
    )
    if link_zonaprop and not link_zonaprop.startswith("http"):
        link_zonaprop = BASE_URL + link_zonaprop

    return {
        "nombre": nombre,
        "web": web or None,
        "ciudad": ciudad or None,
        "telefono": telefono or None,
        "logo": logo or None,
        "link_zonaprop": str(link_zonaprop) if link_zonaprop else None,
        "fuente": "zonaprop",
    }


# ---------------------------------------------------------------------------
# Extracción desde HTML (fallback si __NEXT_DATA__ no funciona)
# ---------------------------------------------------------------------------

def _extraer_desde_html(html: str) -> List[Dict[str, Any]]:
    """
    Extrae agencias de las cards de ZonaProp.
    Estructura real: div.directoryCard-module__card-container
    Contiene: nombre (h2), logo (img), link_zonaprop (a href).
    No hay web propia ni ciudad en las cards del listado.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Selector exacto basado en el HTML real de ZonaProp
    cards = (
        soup.select("div[class*='directoryCard-module__card-container']")
        # Fallbacks si ZonaProp cambia el nombre de la clase
        or soup.select("[data-qa='agency-card']")
        or soup.select("[data-qa='realEstate-card']")
        or _cards_from_agency_links(soup)
    )

    logger.debug(f"HTML fallback: {len(cards)} cards encontradas")
    agencias = []
    seen: set = set()

    for card in cards:
        # Nombre — h2 dentro del link del card
        nombre_el = card.select_one("h2[class*='text-content-link-title']") or card.select_one("h2")
        if not nombre_el:
            continue
        nombre = nombre_el.get_text(strip=True)[:200]
        if not nombre or len(nombre) < 2:
            continue
        key = nombre.strip().lower()
        if key in seen:
            continue
        seen.add(key)

        # Link al perfil en ZonaProp (href interno)
        link_zonaprop = None
        link_el = card.select_one("a[class*='text-content-link']") or card.select_one("a[href*='/inmobiliarias/']")
        if link_el:
            href = link_el.get("href", "").strip()
            if href:
                link_zonaprop = href if href.startswith("http") else BASE_URL + href

        # Logo — primera imagen que tenga src de CDN (no iconos)
        logo = None
        for img in card.select("img"):
            src = (img.get("src") or img.get("data-src") or "").strip()
            # Ignorar iconos pequeños (estrellas, flechas, badges)
            if src and ("empresas" in src or "logo" in src.lower()):
                logo = src
                break
        if not logo:
            img = card.select_one("img[class*='logo']")
            if img:
                logo = (img.get("src") or img.get("data-src") or "").strip() or None

        agencias.append({
            "nombre": nombre,
            "web": None,       # No disponible en listado — se puede enriquecer visitando el perfil
            "ciudad": None,    # No disponible en listado
            "telefono": None,  # No disponible en listado (requiere JS)
            "logo": logo or None,
            "link_zonaprop": link_zonaprop or None,
            "fuente": "zonaprop",
        })

    return agencias


def _cards_from_agency_links(soup: BeautifulSoup) -> list:
    """Último recurso: encuentra contenedores padre de links a inmobiliarias."""
    cards = []
    seen_parents: set = set()
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if "/inmobiliarias/" not in href:
            continue
        parent = a.find_parent(("article", "li", "div", "section"))
        if parent and id(parent) not in seen_parents:
            seen_parents.add(id(parent))
            cards.append(parent)
    return cards


# ---------------------------------------------------------------------------
# Paginación ZonaProp
# ---------------------------------------------------------------------------

def _siguiente_pagina(current_url: str, html: str, page_num: int) -> Optional[str]:
    """
    Detecta la URL de la siguiente página.
    ZonaProp usa query param: ?pagina=N
    El selector de paginación tiene data-qa="PAGING_N" y data-qa="PAGING_NEXT".
    """
    soup = BeautifulSoup(html, "html.parser")

    # Verificar si existe el botón para la siguiente página numérica
    next_num = page_num + 1
    next_btn = soup.select_one(f'[data-qa="PAGING_{next_num}"]')
    if next_btn:
        # Construir URL con ?pagina=N
        base_url = re.sub(r"[?&]pagina=\d+", "", current_url).rstrip("?&")
        separator = "&" if "?" in base_url else "?"
        return f"{base_url}{separator}pagina={next_num}"

    # Si no hay botón numérico pero hay flecha "siguiente", también intentar
    next_arrow = soup.select_one('[data-qa="PAGING_NEXT"]')
    if next_arrow:
        base_url = re.sub(r"[?&]pagina=\d+", "", current_url).rstrip("?&")
        separator = "&" if "?" in base_url else "?"
        return f"{base_url}{separator}pagina={next_num}"

    return None


# ---------------------------------------------------------------------------
# Guardado en Supabase
# ---------------------------------------------------------------------------

def _guardar_agencia(session: requests.Session, agencia: Dict[str, Any]) -> bool:
    """Guarda o actualiza una agencia en la tabla inmobiliarias_scraping."""
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    # Upsert por nombre (campo de conflicto)
    resp = session.post(
        f"{SUPABASE_URL.rstrip('/')}/rest/v1/{TABLA}?on_conflict=nombre",
        headers=headers,
        json=agencia,
        timeout=15,
    )
    if resp.status_code in (200, 201, 204):
        return True
    logger.warning(f"Error guardando {agencia.get('nombre')}: {resp.status_code} {resp.text[:200]}")
    return False


def _obtener_nombres_existentes(session: requests.Session) -> set:
    """Devuelve todos los nombres ya en la tabla para evitar duplicados."""
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Range-Unit": "items",
        "Range": "0-99999",
    }
    try:
        resp = session.get(
            f"{SUPABASE_URL.rstrip('/')}/rest/v1/{TABLA}",
            headers=headers,
            params={"select": "nombre"},
            timeout=30,
        )
        resp.raise_for_status()
        nombres = {row["nombre"].strip().lower() for row in resp.json() if row.get("nombre")}
        logger.info(f"Agencias ya en DB: {len(nombres)}")
        return nombres
    except Exception as exc:
        logger.warning(f"No se pudo cargar nombres existentes: {exc}")
        return set()


# ---------------------------------------------------------------------------
# Orquestador principal
# ---------------------------------------------------------------------------

def scrape_zonaprop_agencias(dry_run: bool = False,
                              provincia: Optional[str] = None) -> int:
    """
    Scrapea todas las inmobiliarias de ZonaProp y guarda en Supabase.

    Args:
        dry_run: Si True, no guarda en Supabase (solo imprime).
        provincia: Filtrar por provincia/ciudad (ej: "Buenos Aires").

    Returns:
        Cantidad de agencias guardadas/encontradas.
    """
    import requests as req_lib
    session = req_lib.Session()
    session.headers.update({"User-Agent": BROWSER_UA})

    existentes: set = set()
    if not dry_run:
        existentes = _obtener_nombres_existentes(session)
        logger.info(f"Agencias ya en DB (ZonaProp): {len(existentes)}")

    start_url = START_URL
    if provincia:
        slug = provincia.lower().replace(" ", "-")
        start_url = f"{BASE_URL}/inmobiliarias-{slug}.bum"
        logger.info(f"Filtrando por provincia: {provincia} → {start_url}")

    todas_agencias: List[Dict] = []
    total_guardadas = 0
    pagina = 1
    MAX_PAGINAS = 600  # 10,544 agencias / 20 por página ≈ 528 páginas

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=BROWSER_ARGS)
        context = browser.new_context(
            user_agent=BROWSER_UA,
            viewport={"width": 1366, "height": 900},
            locale="es-AR",
            extra_http_headers={"Accept-Language": "es-AR,es;q=0.9"},
        )
        page = context.new_page()

        # Bloquear imágenes/fonts para ir más rápido
        page.route(
            "**/*.{png,jpg,jpeg,gif,webp,svg,ico,woff,woff2,ttf,eot}",
            lambda route: route.abort(),
        )

        try:
            # ── Cargar página inicial (navegar una sola vez) ────────────────
            logger.info(f"[Página 1] {start_url}")
            page.goto(start_url, timeout=45000, wait_until="domcontentloaded")
            _esperar_cards(page, timeout_ms=30000)

            while pagina <= MAX_PAGINAS:
                # Scroll para lazy loading
                for _ in range(3):
                    page.evaluate("window.scrollBy(0, 600)")
                    page.wait_for_timeout(400)

                html = page.content()
                agencias_pagina = _extraer_desde_html(html)

                logger.info(f"  → {len(agencias_pagina)} agencias")

                if not agencias_pagina:
                    logger.warning("  → 0 agencias. Guardando HTML de diagnóstico...")
                    _guardar_debug_html(html, pagina)
                    logger.warning(
                        f"  → Revisar debug_zonaprop_p{pagina}.html para actualizar selectores."
                    )
                    break

                # ── Guardar / acumular ──────────────────────────────────────
                nuevas_en_pagina = 0
                for ag in agencias_pagina:
                    nombre_key = (ag.get("nombre") or "").strip().lower()
                    if nombre_key in existentes:
                        continue
                    existentes.add(nombre_key)
                    todas_agencias.append(ag)
                    nuevas_en_pagina += 1

                    if not dry_run:
                        ok = _guardar_agencia(session, ag)
                        if ok:
                            total_guardadas += 1

                # Si la página completa no aportó ninguna agencia nueva,
                # ZonaProp está ciclando — no tiene sentido seguir.
                if nuevas_en_pagina == 0:
                    logger.info(
                        f"  → Página {pagina} sin agencias nuevas — "
                        f"fin del directorio ({len(todas_agencias)} únicas encontradas)"
                    )
                    break

                # ── Avanzar a la siguiente página con clic ──────────────────
                # Usar el botón numérico de la siguiente página si existe,
                # o la flecha PAGING_NEXT. Ambos usan XHR sin recargar la página.
                next_page_num = pagina + 1
                next_btn = (
                    page.query_selector(f'[data-qa="PAGING_{next_page_num}"]')
                    or page.query_selector('[data-qa="PAGING_NEXT"]')
                )
                if not next_btn:
                    logger.info(f"  → No hay más páginas (fin en página {pagina})")
                    break

                pagina += 1
                logger.info(f"[Página {pagina}]")

                try:
                    # Esperar respuesta del API de directorio después del clic
                    with page.expect_response(
                        "**/rplis-api/directory**", timeout=15000
                    ):
                        next_btn.click()
                    # Esperar que el DOM se actualice con las nuevas cards
                    page.wait_for_timeout(1500)
                except Exception:
                    # Si no hay respuesta de API en 15s, esperar más tiempo
                    page.wait_for_timeout(5000)

                time.sleep(0.5)

        except Exception as exc:
            logger.error(f"Error en página {pagina}: {exc}")
            try:
                _guardar_debug_html(page.content(), pagina)
            except Exception:
                pass

        try:
            page.close()
            context.close()
            browser.close()
        except Exception:
            pass

    # ── Resumen ─────────────────────────────────────────────────────────────
    logger.info(f"\n{'='*60}")
    logger.info(f"ZonaProp Agencias — RESUMEN")
    logger.info(f"  Páginas scrapeadas : {pagina - 1}")
    logger.info(f"  Agencias nuevas    : {len(todas_agencias)}")
    if not dry_run:
        logger.info(f"  Guardadas en DB    : {total_guardadas}")
    else:
        logger.info(f"  DRY RUN — no se guardó nada")
        logger.info(f"\n  Primeras 15 agencias encontradas:")
        for ag in todas_agencias[:15]:
            zonaprop = ag.get("link_zonaprop") or ""
            logo = "✓" if ag.get("logo") else "–"
            logger.info(f"    {ag['nombre']:45} | logo:{logo} | {zonaprop[-60:]}")
    logger.info(f"{'='*60}")

    return total_guardadas if not dry_run else len(todas_agencias)


def _esperar_cards(page: Any, timeout_ms: int = 30000) -> None:
    """
    Espera hasta que aparezcan las cards de agencias en el DOM.
    ZonaProp a veces muestra un desafío Cloudflare que se resuelve
    automáticamente en ~5-10 segundos antes de cargar el contenido real.
    """
    card_sel = "div[class*='directoryCard-module__card-container']"
    try:
        page.wait_for_selector(card_sel, timeout=timeout_ms, state="attached")
    except Exception:
        # Si no aparecen cards, esperar un poco más y continuar igual
        page.wait_for_timeout(3000)


def _guardar_debug_html(html: str, pagina: int) -> None:
    """Guarda el HTML para diagnóstico cuando no se encuentran agencias."""
    fname = f"debug_zonaprop_p{pagina}.html"
    try:
        with open(fname, "w", encoding="utf-8") as f:
            f.write(html)
        logger.info(f"  → Debug HTML guardado: {fname}")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scrapea el directorio de inmobiliarias de ZonaProp",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python scrape_zonaprop_agencias.py
  python scrape_zonaprop_agencias.py --dry-run
  python scrape_zonaprop_agencias.py --provincia "Buenos Aires"
  python scrape_zonaprop_agencias.py --dry-run --debug
        """,
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="No guardar en Supabase (solo mostrar resultados)")
    parser.add_argument("--debug", action="store_true",
                        help="Activar logs detallados")
    parser.add_argument("--provincia", default=None,
                        help="Filtrar por provincia (ej: 'Buenos Aires', 'Cordoba')")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    scrape_zonaprop_agencias(dry_run=args.dry_run, provincia=args.provincia)
