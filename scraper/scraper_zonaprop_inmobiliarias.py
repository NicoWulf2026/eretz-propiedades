"""
Scraper controlado de inmobiliarias desde Zonaprop.
Fuente: https://www.zonaprop.com.ar/inmobiliarias.bum

Uso:
    python scraper/scraper_zonaprop_inmobiliarias.py --max-pages 1 --output data/zonaprop_test.csv --delay 3

Reglas:
    - Solo descubrimiento de inmobiliarias (no copia propiedades).
    - No login, no captcha bypass, no evasion de bloqueos.
    - No toca Supabase, no inserta datos en la base.
    - Si detecta bloqueo real, se detiene.
"""

import argparse
import csv
import os
import re
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

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
    # type: (int, requests.Session) -> Tuple[List[Dict], Optional[str]]
    """Descarga y parsea una pagina del directorio.

    Retorna (lista_de_inmobiliarias, bloqueo_detectado).
    bloqueo_detectado es None si no hay bloqueo.
    """
    url = build_page_url(page_num)
    print("\n[PAGE {}] Descargando: {}".format(page_num, url))

    try:
        resp = session.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
    except requests.exceptions.TooManyRedirects:
        print("  [ERROR] Demasiados redirects para pagina {}.".format(page_num))
        return [], "TooManyRedirects"
    except requests.exceptions.RequestException as exc:
        print("  [ERROR] Error de red: {}".format(exc))
        return [], "RequestException: {}".format(exc)

    print("  Status: {} | Tamanio: {:,} chars".format(resp.status_code, len(resp.text)))

    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    # Buscar cards de inmobiliarias
    cards = soup.select("div[class*='directoryCard-module__card-container']")
    print("  Cards encontradas: {}".format(len(cards)))

    # Detectar bloqueo
    block = detect_block(resp.status_code, html, len(cards))
    if block:
        return [], block

    # Parsear cada card
    results = []
    for card in cards:
        data = parse_card(card, url)
        if data:
            results.append(data)

    print("  Inmobiliarias extraidas: {}".format(len(results)))
    return results, None


def deduplicate(records):
    # type: (List[Dict]) -> List[Dict]
    """Elimina duplicados por nombre + url_perfil_zonaprop."""
    seen = set()
    unique = []
    for rec in records:
        key = (rec["nombre"].strip().lower(), rec["url_perfil_zonaprop"].strip().lower())
        if key not in seen:
            seen.add(key)
            unique.append(rec)
    return unique


def save_csv(records, output_path):
    # type: (List[Dict], str) -> None
    """Guarda los registros en un archivo CSV."""
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print("[INFO] Directorio creado: {}".format(output_dir))

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(records)

    print("[OK] CSV guardado: {} ({} filas)".format(output_path, len(records)))


def print_summary(all_records, pages_processed, per_page, output_path, block_reason):
    # type: (List[Dict], int, List[int], str, Optional[str]) -> None
    """Imprime el resumen de la ejecucion."""
    print("\n" + "=" * 60)
    print("RESUMEN DE EJECUCION")
    print("=" * 60)
    print("Fecha/hora:            {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    print("Paginas procesadas:    {}".format(pages_processed))
    for i, count in enumerate(per_page, 1):
        print("  Pagina {}:            {} inmobiliarias".format(i, count))
    print("Total unicas:          {}".format(len(all_records)))
    print("Archivo generado:      {}".format(output_path))

    if block_reason:
        print("\n[!!] BLOQUEO DETECTADO: {}".format(block_reason))
        print("     El scraper se detuvo por seguridad.")
    else:
        print("\n[OK] Sin bloqueo detectado.")

    # Mostrar primeras 10 inmobiliarias
    if all_records:
        print("\nPrimeras {} inmobiliarias:".format(min(10, len(all_records))))
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
        epilog="Ejemplo: python scraper/scraper_zonaprop_inmobiliarias.py --max-pages 1 --output data/zonaprop_test.csv --delay 3",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=1,
        help="Numero maximo de paginas a procesar (default: 1).",
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
    args = parser.parse_args()

    print("=" * 60)
    print("SCRAPER ZONAPROP INMOBILIARIAS")
    print("=" * 60)
    print("Max paginas: {}".format(args.max_pages))
    print("Output:      {}".format(args.output))
    print("Delay:       {}s".format(args.delay))
    print("Fuente:      {}".format(FUENTE))
    print("URL base:    {}".format(BASE_URL))

    # Crear sesion reutilizable
    session = requests.Session()

    all_records = []
    per_page_counts = []
    pages_processed = 0
    block_reason = None

    for page in range(1, args.max_pages + 1):
        if page > 1:
            print("\n[DELAY] Esperando {}s antes de pagina {}...".format(args.delay, page))
            time.sleep(args.delay)

        records, block = scrape_page(page, session)

        pages_processed += 1
        per_page_counts.append(len(records))
        all_records.extend(records)

        if block:
            block_reason = block
            print("\n[STOP] Bloqueo detectado en pagina {}: {}".format(page, block))
            print("[STOP] Deteniendo scraper por seguridad.")
            break

        # Si no encontramos cards en una pagina, posiblemente llegamos al final
        if not records and page > 1:
            print("\n[INFO] Pagina {} sin resultados. Fin del directorio.".format(page))
            break

    # Deduplicar
    unique_records = deduplicate(all_records)
    if len(unique_records) < len(all_records):
        print("\n[INFO] Duplicados eliminados: {}".format(len(all_records) - len(unique_records)))

    # Guardar CSV
    if unique_records:
        save_csv(unique_records, args.output)
    else:
        print("\n[WARN] No se encontraron inmobiliarias. No se genera CSV.")

    # Resumen
    print_summary(unique_records, pages_processed, per_page_counts, args.output, block_reason)

    session.close()


if __name__ == "__main__":
    main()
