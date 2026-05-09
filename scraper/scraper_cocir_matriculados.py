"""
scraper_cocir_matriculados.py
------------------------------
Scraper de matriculados de COCIR (Colegio de Corredores Inmobiliarios de Rosario).
URL: https://cocir.org.ar/paginas/matriculados

Estrategia:
  - Busca con cada letra del abecedario para cubrir todos los corredores
  - Deduplica por número de matrícula
  - Solo guarda registros que tienen inmobiliaria asignada
  - Guarda en CSV local + Supabase (tabla: inmobiliarias_scraping_clean)

Dependencias: pip install playwright requests python-dotenv
               playwright install chromium
"""

import os
import re
import csv
import sys
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

load_dotenv()

# =============================================================================
# CONFIGURACION
# =============================================================================

URL_BASE     = "https://cocir.org.ar/paginas/matriculados"
LETRAS       = list("abcdefghijklmnopqrstuvwxyz")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY", "")
TABLA        = "inmobiliarias_scraping_clean"
CSV_FILE     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cocir_matriculados.csv")
SEL_INPUT    = "input[type='text']"
SEL_FILAS    = "table tbody tr"

CSV_FIELDS = [
    "nombre", "telefono", "email", "direccion",
    "ciudad", "provincia", "categoria", "fuente",
    "matricula_cocir", "estado_matricula", "fecha_scrapeo",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("cocir")

# =============================================================================
# SUPABASE
# =============================================================================

def _supa_headers() -> Dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }


def guardar_supabase(registros: List[Dict[str, Any]]) -> int:
    if not SUPABASE_URL or not SUPABASE_KEY or not registros:
        return 0
    mapeados = [m for r in registros if (m := _mapear_registro(r))]
    if not mapeados:
        return 0
    url = f"{SUPABASE_URL}/rest/v1/{TABLA}?on_conflict=matricula_cocir"
    # Intentar batch
    try:
        resp = requests.post(url, headers=_supa_headers(), json=mapeados, timeout=30)
        if resp.status_code in (200, 201, 204):
            return len(mapeados)
        log.warning(f"Batch error {resp.status_code}: {resp.text[:150]} — reintentando uno a uno")
    except Exception as e:
        log.warning(f"Batch excepción: {e} — reintentando uno a uno")
    # Fallback uno por uno
    ok = 0
    for rec in mapeados:
        try:
            r = requests.post(url, headers=_supa_headers(), json=[rec], timeout=15)
            if r.status_code in (200, 201, 204):
                ok += 1
            else:
                log.warning(f"  Error {r.status_code} mat={rec.get('matricula_cocir')}: {r.text[:80]}")
        except Exception as e:
            log.warning(f"  Excepción mat={rec.get('matricula_cocir')}: {e}")
    return ok


def _mapear_registro(r: Dict[str, Any]) -> Dict[str, Any]:
    """Convierte registro COCIR → esquema inmobiliarias_scraping_clean."""
    inmobiliaria = (r.get("inmobiliaria") or "").strip()
    if not inmobiliaria:
        return {}
    return {
        "nombre":          inmobiliaria,
        "telefono":        r.get("telefono") or None,
        "email":           r.get("email") or None,
        "direccion":       r.get("direccion") or None,
        "ciudad":          "Rosario",
        "provincia":       "Santa Fe",
        "categoria":       "corredor inmobiliario",
        "fuente":          "cocir",
        "matricula_cocir": r.get("matricula") or None,
        "estado_matricula": r.get("estado") or "activo",
        "fecha_scrapeo":   r.get("fecha_scrapeo"),
    }


# =============================================================================
# CSV
# =============================================================================

def guardar_csv(registros: List[Dict[str, Any]]):
    mapeados = [m for r in registros if (m := _mapear_registro(r))]
    if not mapeados:
        return
    existe = os.path.isfile(CSV_FILE)
    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        if not existe:
            writer.writeheader()
        writer.writerows(mapeados)


# =============================================================================
# EXTRACCION DE DATOS
# =============================================================================

def limpiar(texto: Optional[str]) -> str:
    if not texto:
        return ""
    return " ".join(texto.strip().split())


def extraer_matricula(texto: str) -> str:
    m = re.search(r"\d+", texto)
    return m.group(0) if m else ""


def parsear_fila_cocir(fila_el) -> Optional[Dict[str, Any]]:
    """
    Columnas reales de COCIR (6 tds):
      [0] Nombre + foto + estado
      [1] Número de matrícula
      [2] Imagen del sello (sin texto)
      [3] Nombre de la inmobiliaria
      [4] Dirección (calle + ciudad en líneas separadas)
      [5] Teléfono + Email
    """
    try:
        celdas = fila_el.locator("td").all()
        if len(celdas) < 4:
            return None

        ahora = datetime.now(timezone.utc).isoformat()

        # Matrícula (col 1)
        matricula = extraer_matricula(celdas[1].inner_text())
        if not matricula:
            return None

        # Estado desde col 0
        col0 = celdas[0].inner_text().lower()
        estado = "activo"
        for s in ("inactivo", "suspendido", "baja"):
            if s in col0:
                estado = s
                break

        # Inmobiliaria (col 3)
        inmobiliaria = limpiar(celdas[3].inner_text()) if len(celdas) > 3 else ""

        # Dirección (col 4) — primera línea = calle, segunda = ciudad
        direccion = ""
        if len(celdas) > 4:
            lineas = [l.strip() for l in celdas[4].inner_text().splitlines() if l.strip()]
            # Tomar la primera línea que no sea solo código postal
            for linea in lineas:
                if not re.match(r"^\(\d+\)", linea):
                    direccion = linea
                    break

        # Contacto (col 5) — teléfono y email en líneas separadas
        telefono = ""
        email = ""
        if len(celdas) > 5:
            for linea in celdas[5].inner_text().splitlines():
                linea = linea.strip()
                if "@" in linea:
                    email = linea.lower()
                elif re.search(r"\d{6,}", linea):
                    telefono = re.sub(r"\D", "", linea)

        return {
            "matricula":   matricula,
            "inmobiliaria": inmobiliaria,
            "telefono":    telefono,
            "email":       email,
            "direccion":   direccion,
            "estado":      estado,
            "fecha_scrapeo": ahora,
        }

    except Exception as e:
        log.debug(f"Error parseando fila: {e}")
        return None


# =============================================================================
# BUSQUEDA — click confiable en el botón BUSCAR
# =============================================================================

def buscar(page, letra: str) -> bool:
    """
    Escribe la letra en el input y dispara la búsqueda.
    Usa mouse real sobre el botón BUSCAR — el único método que funciona en COCIR.
    """
    try:
        inp = page.locator(SEL_INPUT).first
        inp.click()
        page.wait_for_timeout(200)
        page.keyboard.press("Control+a")
        page.keyboard.press("Backspace")
        page.wait_for_timeout(150)
        page.keyboard.type(letra, delay=100)
        page.wait_for_timeout(400)
    except Exception as e:
        log.warning(f"  Error escribiendo '{letra}': {e}")
        return False

    # Método 1: Playwright native click por texto (ARIA)
    clickeado = False
    try:
        btn = page.get_by_role("button", name=re.compile(r"buscar", re.IGNORECASE))
        if btn.count() > 0:
            btn.first.scroll_into_view_if_needed()
            page.wait_for_timeout(100)
            btn.first.click(timeout=3000)
            clickeado = True
            log.info("  Botón BUSCAR clickeado (Playwright native)")
    except Exception as e:
        log.debug(f"  Native click falló: {e}")

    # Método 2: Obtener coordenadas del botón y usar mouse real
    if not clickeado:
        try:
            coords = page.evaluate("""
                () => {
                    const all = document.querySelectorAll('button, input[type="submit"]');
                    for (const el of all) {
                        const txt = (el.textContent || el.value || '').trim().toUpperCase();
                        if (txt.includes('BUSCAR')) {
                            const r = el.getBoundingClientRect();
                            if (r.width > 0 && r.height > 0) {
                                return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
                            }
                        }
                    }
                    return null;
                }
            """)
            if coords:
                page.mouse.click(coords["x"], coords["y"])
                clickeado = True
                log.info(f"  Botón BUSCAR clickeado con mouse en ({coords['x']:.0f}, {coords['y']:.0f})")
        except Exception as e:
            log.debug(f"  Mouse click falló: {e}")

    # Método 3: Enter en el input (último recurso)
    if not clickeado:
        page.locator(SEL_INPUT).first.press("Enter")
        log.info("  Búsqueda enviada con Enter (fallback final)")

    # Esperar resultados
    try:
        page.wait_for_selector(SEL_FILAS, timeout=20000)
        page.wait_for_timeout(800)
        return True
    except PlaywrightTimeout:
        page.screenshot(path=f"debug_cocir_{letra}.png")
        log.warning(f"  Timeout esperando resultados para '{letra}'. Screenshot guardado.")
        return False


# =============================================================================
# SCRAPER PRINCIPAL
# =============================================================================

def scraper_cocir():
    log.info("=" * 60)
    log.info("SCRAPER COCIR — Matriculados Rosario")
    log.info(f"URL: {URL_BASE}")
    log.info(f"CSV: {CSV_FILE}")
    log.info("=" * 60)

    vistos: Set[str] = set()
    todos_registros: List[Dict] = []
    total_supabase = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="es-AR",
            viewport={"width": 1400, "height": 900},
        )
        page = context.new_page()

        try:
            log.info("Cargando página...")
            page.goto(URL_BASE, timeout=30000, wait_until="networkidle")
            page.wait_for_timeout(2000)

            for letra in LETRAS:
                log.info(f"\n--- Letra: '{letra}' ---")

                if not buscar(page, letra):
                    log.warning(f"  Saltando '{letra}'")
                    continue

                pagina = 1
                while True:
                    filas = page.locator(SEL_FILAS).all()
                    log.info(f"  Página {pagina}: {len(filas)} filas")

                    nuevos = 0
                    lote: List[Dict] = []

                    for fila in filas:
                        try:
                            datos = parsear_fila_cocir(fila)
                            if not datos:
                                continue
                            clave = datos["matricula"]
                            if clave in vistos:
                                continue
                            vistos.add(clave)
                            todos_registros.append(datos)
                            lote.append(datos)
                            nuevos += 1

                            if len(lote) >= 50:
                                guardar_csv(lote)
                                n = guardar_supabase(lote)
                                total_supabase += n
                                log.info(f"  → Guardados {n}/{len(lote)} | total: {len(todos_registros)}")
                                lote = []

                        except Exception as e:
                            log.debug(f"Error fila: {e}")

                    if lote:
                        guardar_csv(lote)
                        n = guardar_supabase(lote)
                        total_supabase += n
                        log.info(f"  → Guardados {n}/{len(lote)} | total: {len(todos_registros)}")

                    log.info(f"  Nuevos: {nuevos}")

                    # Paginación
                    siguiente = None
                    for sel in ["[aria-label='Next']", "[aria-label='Siguiente']",
                                "a:has-text('Siguiente')", ".pagination .next",
                                "li.next a", f"a:has-text('{pagina + 1}')"]:
                        try:
                            btn = page.locator(sel).first
                            if btn.is_visible(timeout=400) and btn.is_enabled():
                                siguiente = btn
                                break
                        except Exception:
                            continue

                    if not siguiente or nuevos == 0:
                        break

                    siguiente.click()
                    page.wait_for_timeout(1500)
                    pagina += 1

        except Exception as e:
            log.error(f"Error fatal: {e}")
            try:
                page.screenshot(path="debug_cocir_error.png")
            except Exception:
                pass
        finally:
            browser.close()

    log.info("=" * 60)
    log.info(f"Total registros únicos    : {len(todos_registros)}")
    log.info(f"Guardados en Supabase     : {total_supabase}")
    log.info(f"CSV                       : {CSV_FILE}")
    log.info("=" * 60)


if __name__ == "__main__":
    scraper_cocir()
