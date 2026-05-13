"""
Scraper controlado de inmobiliarias desde Zonaprop.
Fuente: https://www.zonaprop.com.ar/inmobiliarias.bum

Uso basico:
    python scraper/scraper_zonaprop_inmobiliarias.py --max-pages 1 --output data/zonaprop_test.csv --delay 3

Uso para reanudar desde pagina 178:
    python scraper/scraper_zonaprop_inmobiliarias.py --start-page 178 --max-pages 20 --output data/zonaprop_resume.csv --delay 12

Uso con append a CSV existente:
    python scraper/scraper_zonaprop_inmobiliarias.py --start-page 178 --max-pages 20 --output data/zonaprop_total.csv --delay 12 --append

Reglas:
    - Solo descubrimiento de inmobiliarias (no copia propiedades).
    - No login, no captcha bypass, no evasion de bloqueos.
    - No toca Supabase, no inserta datos en la base.
    - Si detecta bloqueo real, se detiene y guarda lo recolectado.
"""

import argparse
import csv
import os
import re
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuracion
# ---------------------------------------------------------------------------

BASE_URL = "https://www.zonaprop.com.ar/inmobiliarias.bum"
FUENTE = "zonaprop_inmobiliarias"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}

CSV_COLUMNS = [
    "nombre",
    "url_perfil_zonaprop",
    "publica_desde",
    "nivel",
    "calificaciones",
    "avisos_compra",
    "avisos_alquiler",
    "ciudad",
    "provincia",
    "fuente",
    "pagina_origen",
]

# Textos que indican bloqueo real (se buscan en el body visible, no en scripts)
BLOCK_SIGNALS = [
    "access denied",
    "too many requests",
    "cf-challenge",
    "cloudflare challenge",
    "please verify you are a human",
    "captcha challenge required",
]

# HTTP status codes que son reintenteables (errores temporales del servidor)
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 520, 521, 522, 523, 524}


# ---------------------------------------------------------------------------
# Funciones auxiliares
# ---------------------------------------------------------------------------


def build_page_url(page_num):
    # type: (int) -> str
    """Construye la URL para la pagina dada."""
    if page_num <= 1:
        return BASE_URL
    return "{}?pagina={}".format(BASE_URL, page_num)


def detect_block(status_code, html, cards_found):
    # type: (int, str, int) -> Optional[str]
    """Detecta si la respuesta indica un bloqueo real.

    Retorna un string descriptivo del bloqueo, o None si no hay bloqueo.
    """
    if status_code == 403:
        return "HTTP 403 Forbidden"
    if status_code == 429:
        return "HTTP 429 Too Many Requests"
    if status_code >= 500:
        return "HTTP {} Server Error".format(status_code)

    # Extraer solo el texto visible del body (sin scripts ni styles)
    soup_check = BeautifulSoup(html, "html.parser")
    for tag in soup_check.find_all(["script", "style", "noscript"]):
        tag.decompose()
    body_text = soup_check.get_text(" ", strip=True).lower()

    for signal in BLOCK_SIGNALS:
        if signal in body_text:
            return "Texto de bloqueo detectado: '{}'".format(signal)

    # Si hay mencion de captcha en el body visible Y no encontramos cards
    if "captcha" in body_text and cards_found == 0:
        return "Captcha activo sin cards visibles"

    return None


def is_retryable_error(block_reason):
    # type: (Optional[str]) -> bool
    """Determina si un error de bloqueo es reintentable (error temporal del servidor)."""
    if not block_reason:
        return False
    # Errores HTTP 5xx y 429 son reintenteables
    for code in RETRYABLE_STATUS_CODES:
        if "HTTP {}".format(code) in block_reason:
            return True
    return False


def extract_text_field(card_text, pattern):
    # type: (str, str) -> str
    """Extrae un valor numerico asociado a un patron de texto dentro de la card."""
    match = re.search(pattern, card_text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""


def parse_card(card, page_url):
    # type: (...) -> Optional[Dict]
    """Extrae los datos de una card de inmobiliaria.

    Retorna un dict con los campos, o None si no se pudo extraer.
    """
    # Nombre: buscar en h2 dentro de la card
    h2 = card.select_one("h2")
    nombre = h2.get_text(strip=True) if h2 else ""

    if not nombre:
        return None

    # Link al perfil
    link_el = card.select_one("a[href*='/inmobiliarias/']")
    url_perfil = ""
    if link_el:
        href = link_el.get("href", "")
        if "-inmuebles" in href:
            if href.startswith("/"):
                url_perfil = "https://www.zonaprop.com.ar" + href
            else:
                url_perfil = href

    if not url_perfil:
        return None

    # Texto completo de la card para extraer campos
    card_text = card.get_text(" ", strip=True)

    # Publica desde (anio)
    publica_desde = extract_text_field(card_text, r"Publica\s+desde\s+(\d{4})")

    # Nivel
    nivel = extract_text_field(card_text, r"Nivel\s+(\d+)")

    # Calificaciones: "Ver N calificaciones" o "Ver N calificacion"
    calificaciones = extract_text_field(
        card_text, r"Ver\s+(\d+)\s+calificacion"
    )

    # Avisos compra: "N Avisos compra" o "N Aviso compra"
    avisos_compra = extract_text_field(
        card_text, r"(\d[\d.]*)\s+Avisos?\s+compra"
    )
    # Limpiar separadores de miles (1.234 -> 1234)
    if avisos_compra:
        avisos_compra = avisos_compra.replace(".", "")

    # Avisos alquiler: "N Avisos alquiler" o "N Aviso alquiler"
    avisos_alquiler = extract_text_field(
        card_text, r"(\d[\d.]*)\s+Avisos?\s+alquiler"
    )
    if avisos_alquiler:
        avisos_alquiler = avisos_alquiler.replace(".", "")

    return {
        "nombre": nombre,
        "url_perfil_zonaprop": url_perfil,
        "publica_desde": publica_desde,
        "nivel": nivel,
        "calificaciones": calificaciones,
        "avisos_compra": avisos_compra,
        "avisos_alquiler": avisos_alquiler,
        "ciudad": "",
        "provincia": "",
        "fuente": FUENTE,
        "pagina_origen": page_url,
    }


def scrape_page(page_num, session):
    # type: (int, requests.Session) -> Tuple[List[Dict], Optional[str], int]
    """Descarga y parsea una pagina del directorio.

    Retorna (lista_de_inmobiliarias, bloqueo_detectado, status_code).
    bloqueo_detectado es None si no hay bloqueo.
    """
    url = build_page_url(page_num)
    print("\n[PAGE {}] Descargando: {}".format(page_num, url))

    try:
        resp = session.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
    except requests.exceptions.TooManyRedirects:
        print("  [ERROR] Demasiados redirects para pagina {}.".format(page_num))
        return [], "TooManyRedirects", 0
    except requests.exceptions.RequestException as exc:
        print("  [ERROR] Error de red: {}".format(exc))
        return [], "RequestException: {}".format(exc), 0

    print("  Status: {} | Tamanio: {:,} chars".format(resp.status_code, len(resp.text)))

    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    # Buscar cards de inmobiliarias
    cards = soup.select("div[class*='directoryCard-module__card-container']")
    print("  Cards encontradas: {}".format(len(cards)))

    # Detectar bloqueo
    block = detect_block(resp.status_code, html, len(cards))
    if block:
        return [], block, resp.status_code

    # Parsear cada card
    results = []
    for card in cards:
        data = parse_card(card, url)
        if data:
            results.append(data)

    print("  Inmobiliarias extraidas: {}".format(len(results)))
    return results, None, resp.status_code


def deduplicate(records):
    # type: (List[Dict]) -> List[Dict]
    """Elimina duplicados por nombre + url_perfil_zonaprop."""
    seen = set()  # type: Set[Tuple[str, str]]
    unique = []
    for rec in records:
        key = (rec["nombre"].strip().lower(), rec["url_perfil_zonaprop"].strip().lower())
        if key not in seen:
            seen.add(key)
            unique.append(rec)
    return unique


def load_existing_csv(csv_path):
    # type: (str) -> Tuple[List[Dict], Set[Tuple[str, str]]]
    """Carga un CSV existente y retorna los registros y un set de claves para dedup."""
    records = []
    keys = set()  # type: Set[Tuple[str, str]]
    if not os.path.exists(csv_path):
        return records, keys
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                records.append(row)
                key = (
                    row.get("nombre", "").strip().lower(),
                    row.get("url_perfil_zonaprop", "").strip().lower(),
                )
                keys.add(key)
        print("[INFO] CSV existente cargado: {} ({} registros)".format(csv_path, len(records)))
    except Exception as exc:
        print("[WARN] No se pudo leer CSV existente: {}".format(exc))
    return records, keys


def save_csv(records, output_path, append_mode=False):
    # type: (List[Dict], str, bool) -> None
    """Guarda los registros en un archivo CSV."""
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print("[INFO] Directorio creado: {}".format(output_dir))

    if append_mode and os.path.exists(output_path):
        # Cargar existentes, agregar nuevos, deduplicar y guardar
        existing, existing_keys = load_existing_csv(output_path)
        new_count = 0
        for rec in records:
            key = (rec["nombre"].strip().lower(), rec["url_perfil_zonaprop"].strip().lower())
            if key not in existing_keys:
                existing.append(rec)
                existing_keys.add(key)
                new_count += 1
        records = existing
        print("[INFO] Modo append: {} nuevos agregados, {} total".format(new_count, len(records)))

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(records)

    print("[OK] CSV guardado: {} ({} filas)".format(output_path, len(records)))


def print_summary(all_records, pages_processed, per_page, output_path,
                  block_reason, start_page, last_page):
    # type: (List[Dict], int, List[Tuple[int, int]], str, Optional[str], int, int) -> None
    """Imprime el resumen de la ejecucion."""
    print("\n" + "=" * 60)
    print("RESUMEN DE EJECUCION")
    print("=" * 60)
    print("Fecha/hora:            {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    print("Pagina inicio:         {}".format(start_page))
    print("Ultima pagina:         {}".format(last_page))
    print("Paginas procesadas:    {}".format(pages_processed))
    for page_num, count in per_page:
        print("  Pagina {:>4d}:          {} inmobiliarias".format(page_num, count))
    print("Total unicas (sesion): {}".format(len(all_records)))
    print("Archivo generado:      {}".format(output_path))

    if block_reason:
        print("\n[!!] BLOQUEO DETECTADO: {}".format(block_reason))
        print("     Ultima pagina intentada: {}".format(last_page))
        print("     El scraper se detuvo por seguridad.")
        print("     Para reanudar, usar: --start-page {}".format(last_page))
    else:
        print("\n[OK] Sin bloqueo detectado.")

    # Mostrar primeras 10 inmobiliarias de esta sesion
    if all_records:
        print("\nPrimeras {} inmobiliarias (esta sesion):".format(min(10, len(all_records))))
        print("-" * 60)
        for i, rec in enumerate(all_records[:10], 1):
            print(
                "  {:2d}. {}  | Nivel: {}  | Calif: {}  | Compra: {}  | Alquiler: {}  | Desde: {}".format(
                    i,
                    rec["nombre"],
                    rec["nivel"] or "-",
                    rec["calificaciones"] or "-",
                    rec["avisos_compra"] or "-",
                    rec["avisos_alquiler"] or "-",
                    rec["publica_desde"] or "-",
                )
            )
    print("=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Scraper controlado de inmobiliarias desde Zonaprop.",
        epilog=(
            "Ejemplos:\n"
            "  Primera corrida:  python scraper/scraper_zonaprop_inmobiliarias.py --max-pages 5 --output data/zonaprop.csv --delay 10\n"
            "  Reanudar:         python scraper/scraper_zonaprop_inmobiliarias.py --start-page 178 --max-pages 20 --output data/zonaprop_resume.csv --delay 12\n"
            "  Append:           python scraper/scraper_zonaprop_inmobiliarias.py --start-page 178 --max-pages 20 --output data/zonaprop.csv --delay 12 --append"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=1,
        help="Numero maximo de paginas a procesar (default: 1).",
    )
    parser.add_argument(
        "--start-page",
        type=int,
        default=1,
        help="Pagina inicial para reanudar scraping (default: 1).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/zonaprop_inmobiliarias.csv",
        help="Ruta del archivo CSV de salida (default: data/zonaprop_inmobiliarias.csv).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=3.0,
        help="Segundos de espera entre requests (default: 3).",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="Reintentos por pagina ante errores temporales (default: 2).",
    )
    parser.add_argument(
        "--backoff",
        type=float,
        default=60.0,
        help="Segundos extra de espera tras error 520/429/5xx (default: 60).",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        default=False,
        help="Agregar resultados a CSV existente sin duplicar.",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("SCRAPER ZONAPROP INMOBILIARIAS")
    print("=" * 60)
    print("Pagina inicio: {}".format(args.start_page))
    print("Max paginas:   {}".format(args.max_pages))
    print("Output:        {}".format(args.output))
    print("Delay:         {}s".format(args.delay))
    print("Max retries:   {}".format(args.max_retries))
    print("Backoff:       {}s".format(args.backoff))
    print("Append:        {}".format(args.append))
    print("Fuente:        {}".format(FUENTE))
    print("URL base:      {}".format(BASE_URL))

    # Crear sesion reutilizable
    session = requests.Session()

    all_records = []  # type: List[Dict]
    per_page_info = []  # type: List[Tuple[int, int]]
    pages_processed = 0
    block_reason = None
    last_page = args.start_page

    end_page = args.start_page + args.max_pages  # exclusive
    for page in range(args.start_page, end_page):
        last_page = page

        # Delay entre paginas (no antes de la primera)
        if page > args.start_page:
            print("\n[DELAY] Esperando {}s antes de pagina {}...".format(args.delay, page))
            time.sleep(args.delay)

        # Intentar la pagina con reintentos
        records = []
        block = None
        status_code = 0
        attempts = 0

        while attempts <= args.max_retries:
            if attempts > 0:
                wait_time = args.backoff * attempts
                print("  [RETRY {}/{}] Esperando {}s antes de reintentar pagina {}...".format(
                    attempts, args.max_retries, wait_time, page
                ))
                time.sleep(wait_time)

            records, block, status_code = scrape_page(page, session)
            attempts += 1

            # Si no hay bloqueo y tenemos resultados, exito
            if not block and len(records) > 0:
                break

            # Si hay bloqueo reintentable, seguir intentando
            if block and is_retryable_error(block):
                print("  [WARN] Error reintentable: {}".format(block))
                if attempts <= args.max_retries:
                    continue
                else:
                    print("  [FAIL] Se agotaron los reintentos para pagina {}.".format(page))
                    break

            # Si hay bloqueo no reintentable (403, captcha, etc.), cortar
            if block and not is_retryable_error(block):
                print("  [FAIL] Bloqueo no reintentable: {}".format(block))
                break

            # Si 0 resultados sin bloqueo, reintentar una vez
            if not block and len(records) == 0:
                if attempts <= args.max_retries:
                    print("  [WARN] 0 inmobiliarias en pagina {}. Reintentando...".format(page))
                    continue
                else:
                    print("  [INFO] Pagina {} devolvio 0 inmobiliarias tras reintentos.".format(page))
                    break

        # Registrar resultados de esta pagina
        pages_processed += 1
        per_page_info.append((page, len(records)))
        all_records.extend(records)

        # Si hay bloqueo definitivo, guardar lo que tenemos y cortar
        if block:
            block_reason = block
            print("\n[STOP] Bloqueo en pagina {}: {}".format(page, block))
            print("[STOP] Guardando {} inmobiliarias recolectadas antes de detenerse.".format(
                len(all_records)
            ))
            break

        # Si 0 resultados tras reintentos y no es la primera pagina del rango
        if len(records) == 0 and page > args.start_page:
            print("\n[INFO] Pagina {} sin resultados tras reintentos. Posible fin del directorio.".format(page))
            break

    # Deduplicar los registros de esta sesion
    unique_records = deduplicate(all_records)
    if len(unique_records) < len(all_records):
        print("\n[INFO] Duplicados eliminados: {}".format(len(all_records) - len(unique_records)))

    # Guardar CSV (siempre guardar si tenemos datos, incluso con bloqueo)
    if unique_records:
        save_csv(unique_records, args.output, append_mode=args.append)
    else:
        print("\n[WARN] No se encontraron inmobiliarias nuevas. No se genera CSV.")

    # Resumen
    print_summary(
        unique_records, pages_processed, per_page_info,
        args.output, block_reason, args.start_page, last_page
    )

    session.close()


if __name__ == "__main__":
    main()
