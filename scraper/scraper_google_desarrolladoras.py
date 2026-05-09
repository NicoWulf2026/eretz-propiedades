"""
scraper_google_desarrolladoras.py
-----------------------------------
Scraper de Google Maps para desarrolladoras y constructoras de toda Argentina.

Cobertura: 23 provincias + CABA.

Extrae por negocio:
    nombre, direccion, barrio, ciudad, provincia, pais,
    telefono, email, web, rating, resenas, categoria, fuente, fecha_scrapeo

Guarda en CSV local + Supabase (tabla inmobiliarias_scraping, categoria=desarrolladora/constructora).
Deduplicacion global por nombre y por web.

Dependencias:
    pip install playwright requests python-dotenv playwright-stealth
    playwright install chromium
"""

import os
import sys
import csv
import re
import json
import time
import random
import traceback
from datetime import datetime
from urllib.parse import urlparse, unquote_plus, parse_qs

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

try:
    from playwright_stealth import stealth_sync
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False

# =============================================================================
# CONFIGURACION
# =============================================================================

script_dir = os.path.dirname(os.path.abspath(__file__))

try:
    from dotenv import load_dotenv
    _dotenv_path = os.path.join(script_dir, "..", ".env")
    if not os.path.exists(_dotenv_path):
        _dotenv_path = os.path.join(script_dir, ".env")
    load_dotenv(dotenv_path=_dotenv_path)
except ImportError:
    pass

SUPABASE_URL   = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY   = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_KEY")
    or os.getenv("SUPABASE_ANON_KEY", "")
)
SUPABASE_TABLE    = "inmobiliarias_scraping"
SUPABASE_ENDPOINT = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}?on_conflict=nombre"
SUPABASE_HEADERS  = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "resolution=merge-duplicates,return=minimal",
}
SUPABASE_HEADERS_IGNORE = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "resolution=ignore-duplicates,return=minimal",
}

def _crear_sesion_supabase() -> requests.Session:
    sesion = requests.Session()
    retry = Retry(
        total=4,
        backoff_factor=1.5,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["POST", "GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    sesion.mount("https://", adapter)
    sesion.mount("http://",  adapter)
    return sesion

_SUPA_SESSION: requests.Session = _crear_sesion_supabase()

CSV_FILE        = os.path.join(script_dir, "google_desarrolladoras.csv")
CHECKPOINT_FILE = os.path.join(script_dir, "checkpoint_desarrolladoras.txt")
CSV_FIELDS = [
    "nombre", "direccion", "barrio", "ciudad", "provincia", "pais",
    "telefono", "email", "web", "rating", "resenas", "categoria", "fuente", "fecha_scrapeo",
]

GOOGLE_LUGARES_URL = "https://www.google.com/maps/search/{query}/"

# =============================================================================
# QUERIES — desarrolladoras y constructoras — 23 provincias + CABA
# =============================================================================

QUERIES = [
    # =========================================================================
    # CIUDAD AUTÓNOMA DE BUENOS AIRES (CABA)
    # =========================================================================
    "desarrolladora inmobiliaria caba buenos aires",
    "constructora caba buenos aires",
    "empresa constructora capital federal",
    "desarrollos inmobiliarios caba",
    "developer inmobiliario buenos aires",
    "emprendimientos inmobiliarios caba",
    "constructora edificios caba",
    "desarrolladora barrio palermo buenos aires",
    "constructora barrio palermo buenos aires",
    "desarrolladora barrio belgrano buenos aires",
    "constructora barrio belgrano buenos aires",
    "desarrolladora barrio recoleta buenos aires",
    "constructora barrio recoleta buenos aires",
    "desarrolladora barrio puerto madero buenos aires",
    "constructora barrio puerto madero buenos aires",
    "desarrolladora barrio caballito buenos aires",
    "constructora barrio caballito buenos aires",
    "desarrolladora barrio villa urquiza buenos aires",
    "constructora barrio villa urquiza buenos aires",
    "desarrolladora barrio villa devoto buenos aires",
    "constructora barrio villa devoto buenos aires",
    "desarrolladora barrio almagro buenos aires",
    "constructora barrio almagro buenos aires",
    "desarrolladora barrio flores buenos aires",
    "constructora barrio flores buenos aires",
    "desarrolladora barrio nuñez buenos aires",
    "constructora barrio nuñez buenos aires",
    "desarrolladora barrio saavedra buenos aires",
    "constructora barrio saavedra buenos aires",
    "desarrolladora barrio villa crespo buenos aires",
    "constructora barrio villa crespo buenos aires",
    "desarrolladora barrio colegiales buenos aires",
    "constructora barrio colegiales buenos aires",
    "desarrolladora barrio chacarita buenos aires",
    "constructora barrio villa del parque buenos aires",
    "desarrolladora barrio coghlan buenos aires",
    "constructora barrio monte castro buenos aires",
    "emprendimientos inmobiliarios palermo",
    "emprendimientos inmobiliarios belgrano",
    "torres departamentos caba",
    "constructora edificios departamentos capital federal",

    # =========================================================================
    # BUENOS AIRES PROVINCIA — GBA ZONA NORTE
    # =========================================================================
    "desarrolladora inmobiliaria zona norte gran buenos aires",
    "constructora zona norte gran buenos aires",
    "desarrolladora san isidro buenos aires",
    "constructora san isidro buenos aires",
    "desarrolladora vicente lopez buenos aires",
    "constructora vicente lopez buenos aires",
    "desarrolladora barrio olivos buenos aires",
    "constructora barrio olivos buenos aires",
    "desarrolladora barrio florida buenos aires",
    "constructora barrio florida buenos aires",
    "desarrolladora tigre buenos aires",
    "constructora tigre buenos aires",
    "desarrolladora barrio nordelta tigre",
    "constructora barrio nordelta tigre",
    "desarrolladora pilar buenos aires",
    "constructora pilar buenos aires",
    "desarrolladora barrio del viso pilar",
    "constructora barrio del viso pilar",
    "desarrolladora escobar buenos aires",
    "constructora escobar buenos aires",
    "desarrolladora san fernando buenos aires",
    "constructora san fernando buenos aires",
    "desarrolladora zarate buenos aires",
    "constructora campana buenos aires",
    "emprendimientos inmobiliarios zona norte gba",
    "countrys y barrios privados zona norte",

    # =========================================================================
    # BUENOS AIRES PROVINCIA — GBA ZONA OESTE
    # =========================================================================
    "desarrolladora zona oeste gran buenos aires",
    "constructora zona oeste gran buenos aires",
    "desarrolladora moron buenos aires",
    "constructora moron buenos aires",
    "desarrolladora hurlingham buenos aires",
    "constructora ituzaingo buenos aires",
    "desarrolladora merlo buenos aires",
    "constructora merlo buenos aires",
    "desarrolladora moreno buenos aires",
    "constructora moreno buenos aires",
    "desarrolladora lujan buenos aires",
    "constructora lujan buenos aires",
    "desarrolladora tres de febrero buenos aires",
    "constructora tres de febrero buenos aires",
    "desarrolladora san miguel buenos aires",
    "constructora san miguel buenos aires",

    # =========================================================================
    # BUENOS AIRES PROVINCIA — GBA ZONA SUR
    # =========================================================================
    "desarrolladora zona sur gran buenos aires",
    "constructora zona sur gran buenos aires",
    "desarrolladora lomas de zamora buenos aires",
    "constructora lomas de zamora buenos aires",
    "desarrolladora lanus buenos aires",
    "constructora lanus buenos aires",
    "desarrolladora avellaneda buenos aires",
    "constructora avellaneda buenos aires",
    "desarrolladora quilmes buenos aires",
    "constructora quilmes buenos aires",
    "desarrolladora berazategui buenos aires",
    "constructora berazategui buenos aires",
    "desarrolladora florencio varela buenos aires",
    "constructora florencio varela buenos aires",
    "desarrolladora almirante brown buenos aires",
    "constructora almirante brown buenos aires",
    "desarrolladora esteban echeverria buenos aires",
    "constructora esteban echeverria buenos aires",
    "desarrolladora la matanza buenos aires",
    "constructora la matanza buenos aires",
    "desarrolladora ezeiza buenos aires",
    "constructora ezeiza buenos aires",

    # =========================================================================
    # BUENOS AIRES PROVINCIA — INTERIOR
    # =========================================================================
    "desarrolladora la plata buenos aires",
    "constructora la plata buenos aires",
    "emprendimientos inmobiliarios la plata",
    "constructora barrio city bell la plata",
    "desarrolladora mar del plata",
    "constructora mar del plata",
    "emprendimientos inmobiliarios mar del plata",
    "desarrolladora bahia blanca",
    "constructora bahia blanca",
    "emprendimientos inmobiliarios bahia blanca",
    "desarrolladora tandil buenos aires",
    "constructora tandil buenos aires",
    "desarrolladora pinamar buenos aires",
    "constructora pinamar buenos aires",
    "desarrolladora villa gesell buenos aires",
    "constructora villa gesell buenos aires",
    "desarrolladora necochea buenos aires",
    "constructora olavarria buenos aires",
    "desarrolladora junin buenos aires",
    "constructora pergamino buenos aires",
    "desarrolladora san nicolas buenos aires",
    "constructora san antonio de areco buenos aires",
    "emprendimientos countrys province buenos aires",
    "barrios privados desarrolladora buenos aires",

    # =========================================================================
    # CÓRDOBA CAPITAL
    # =========================================================================
    "desarrolladora inmobiliaria cordoba capital",
    "constructora cordoba capital",
    "empresa constructora cordoba",
    "desarrollos inmobiliarios cordoba",
    "emprendimientos inmobiliarios cordoba capital",
    "constructora edificios departamentos cordoba",
    "desarrolladora barrio nueva cordoba",
    "constructora barrio nueva cordoba",
    "desarrolladora barrio alta cordoba",
    "constructora barrio alta cordoba",
    "desarrolladora barrio cerro de las rosas cordoba",
    "constructora barrio cerro de las rosas cordoba",
    "desarrolladora barrio villa belgrano cordoba",
    "constructora barrio villa belgrano cordoba",
    "desarrolladora barrio arguello cordoba",
    "constructora barrio arguello cordoba",
    "desarrolladora barrio general paz cordoba",
    "constructora barrio general paz cordoba",
    "desarrolladora barrio cofico cordoba",
    "constructora barrio cofico cordoba",
    "desarrolladora barrio jardin cordoba",
    "constructora barrio jardin cordoba",
    "desarrolladora barrio manantiales cordoba",
    "constructora barrio manantiales cordoba",
    "desarrolladora barrio warcalde cordoba",
    "constructora barrio villa cabrera cordoba",
    "desarrolladora barrio chateau carreras cordoba",
    "constructora barrio los naranjos cordoba",
    "emprendimientos inmobiliarios zona norte cordoba",
    "emprendimientos inmobiliarios zona sur cordoba",
    "barrios privados desarrolladora cordoba capital",
    # Gran Córdoba y serrana
    "desarrolladora villa allende cordoba",
    "constructora villa allende cordoba",
    "desarrolladora mendiolaza cordoba",
    "constructora mendiolaza cordoba",
    "desarrolladora la calera cordoba",
    "constructora la calera cordoba",
    "desarrolladora villa carlos paz cordoba",
    "constructora villa carlos paz cordoba",
    "desarrolladora alta gracia cordoba",
    "constructora alta gracia cordoba",
    "desarrolladora rio cuarto cordoba",
    "constructora rio cuarto cordoba",
    "desarrolladora villa maria cordoba",
    "constructora villa maria cordoba",
    "desarrolladora san francisco cordoba",
    "constructora san francisco cordoba",
    "constructora jesus maria cordoba",
    "desarrolladora bell ville cordoba",

    # =========================================================================
    # SANTA FE — ROSARIO Y CAPITAL
    # =========================================================================
    "desarrolladora inmobiliaria rosario santa fe",
    "constructora rosario santa fe",
    "emprendimientos inmobiliarios rosario",
    "desarrollos departamentos rosario",
    "constructora edificios rosario",
    "desarrolladora barrio pichincha rosario",
    "constructora barrio fisherton rosario",
    "desarrolladora barrio puerto norte rosario",
    "constructora barrio alberdi rosario",
    "desarrolladora barrio martin rosario",
    "constructora barrio echesortu rosario",
    "emprendimientos inmobiliarios zona norte rosario",
    "emprendimientos inmobiliarios zona sur rosario",
    "desarrolladora santa fe capital",
    "constructora santa fe capital",
    "desarrolladora funes santa fe",
    "constructora funes santa fe",
    "desarrolladora roldan santa fe",
    "constructora roldan santa fe",
    "desarrolladora rafaela santa fe",
    "constructora rafaela santa fe",
    "desarrolladora venado tuerto santa fe",
    "constructora venado tuerto santa fe",
    "desarrolladora san lorenzo santa fe",
    "constructora casilda santa fe",

    # =========================================================================
    # MENDOZA
    # =========================================================================
    "desarrolladora inmobiliaria mendoza capital",
    "constructora mendoza capital",
    "emprendimientos inmobiliarios mendoza",
    "desarrollos departamentos mendoza",
    "constructora edificios mendoza",
    "desarrolladora barrio primera seccion mendoza",
    "constructora barrio chacras de coria mendoza",
    "desarrolladora godoy cruz mendoza",
    "constructora godoy cruz mendoza",
    "desarrolladora lujan de cuyo mendoza",
    "constructora lujan de cuyo mendoza",
    "desarrolladora barrio vistalba mendoza",
    "constructora barrio vistalba mendoza",
    "desarrolladora guaymallen mendoza",
    "constructora guaymallen mendoza",
    "desarrolladora maipu mendoza",
    "constructora maipu mendoza",
    "desarrolladora las heras mendoza",
    "constructora las heras mendoza",
    "desarrolladora san rafael mendoza",
    "constructora san rafael mendoza",
    "desarrolladora valle de uco mendoza",
    "constructora valle de uco mendoza",
    "emprendimientos inmobiliarios zona este mendoza",
    "barrios privados desarrolladora mendoza",

    # =========================================================================
    # TUCUMÁN
    # =========================================================================
    "desarrolladora inmobiliaria san miguel de tucuman",
    "constructora san miguel de tucuman",
    "emprendimientos inmobiliarios tucuman",
    "desarrollos departamentos tucuman",
    "constructora edificios tucuman",
    "desarrolladora barrio norte tucuman",
    "constructora barrio norte tucuman",
    "desarrolladora barrio yerba buena tucuman",
    "constructora barrio yerba buena tucuman",
    "desarrolladora tafi viejo tucuman",
    "constructora tafi viejo tucuman",
    "desarrolladora lules tucuman",
    "constructora lules tucuman",
    "desarrolladora concepcion tucuman",
    "constructora monteros tucuman",

    # =========================================================================
    # SALTA
    # =========================================================================
    "desarrolladora inmobiliaria salta capital",
    "constructora salta capital",
    "emprendimientos inmobiliarios salta",
    "desarrollos departamentos salta",
    "constructora edificios salta",
    "desarrolladora barrio tres cerritos salta",
    "constructora barrio tres cerritos salta",
    "desarrolladora barrio norte salta",
    "constructora barrio norte salta",
    "desarrolladora san lorenzo salta",
    "constructora san lorenzo salta",
    "desarrolladora cafayate salta",
    "constructora cafayate salta",
    "desarrolladora tartagal salta",
    "constructora general guemes salta",

    # =========================================================================
    # ENTRE RÍOS
    # =========================================================================
    "desarrolladora inmobiliaria parana entre rios",
    "constructora parana entre rios",
    "emprendimientos inmobiliarios parana",
    "desarrolladora concordia entre rios",
    "constructora concordia entre rios",
    "desarrolladora gualeguaychu entre rios",
    "constructora gualeguaychu entre rios",
    "desarrolladora colon entre rios",
    "constructora colon entre rios",
    "constructora concepcion del uruguay entre rios",

    # =========================================================================
    # CORRIENTES
    # =========================================================================
    "desarrolladora inmobiliaria corrientes capital",
    "constructora corrientes capital",
    "emprendimientos inmobiliarios corrientes",
    "desarrolladora barrio norte corrientes",
    "constructora barrio norte corrientes",
    "desarrolladora goya corrientes",
    "constructora goya corrientes",
    "constructora paso de los libres corrientes",

    # =========================================================================
    # CHACO
    # =========================================================================
    "desarrolladora inmobiliaria resistencia chaco",
    "constructora resistencia chaco",
    "emprendimientos inmobiliarios resistencia",
    "desarrolladora barranqueras chaco",
    "constructora barranqueras chaco",
    "desarrolladora saenz peña chaco",
    "constructora saenz peña chaco",
    "constructora villa angela chaco",

    # =========================================================================
    # MISIONES
    # =========================================================================
    "desarrolladora inmobiliaria posadas misiones",
    "constructora posadas misiones",
    "emprendimientos inmobiliarios posadas",
    "desarrolladora barrio norte posadas",
    "constructora barrio norte posadas",
    "desarrolladora obera misiones",
    "constructora obera misiones",
    "desarrolladora puerto iguazu misiones",
    "constructora puerto iguazu misiones",
    "constructora eldorado misiones",

    # =========================================================================
    # NEUQUÉN
    # =========================================================================
    "desarrolladora inmobiliaria neuquen capital",
    "constructora neuquen capital",
    "emprendimientos inmobiliarios neuquen",
    "desarrollos departamentos neuquen",
    "constructora edificios neuquen",
    "desarrolladora barrio alta barda neuquen",
    "constructora barrio alta barda neuquen",
    "desarrolladora cipolletti neuquen",
    "constructora cipolletti neuquen",
    "desarrolladora general roca neuquen",
    "constructora general roca neuquen",
    "desarrolladora san martin de los andes",
    "constructora san martin de los andes",
    "desarrolladora villa la angostura neuquen",
    "constructora villa la angostura neuquen",
    "desarrolladora centenario neuquen",
    "constructora cutral co neuquen",

    # =========================================================================
    # RÍO NEGRO
    # =========================================================================
    "desarrolladora inmobiliaria bariloche rio negro",
    "constructora bariloche rio negro",
    "emprendimientos inmobiliarios bariloche",
    "desarrolladora barrio norte bariloche",
    "constructora barrio norte bariloche",
    "desarrolladora general roca rio negro",
    "constructora general roca rio negro",
    "desarrolladora viedma rio negro",
    "constructora viedma rio negro",
    "desarrolladora el bolson rio negro",
    "constructora el bolson rio negro",
    "constructora allen rio negro",

    # =========================================================================
    # SAN JUAN
    # =========================================================================
    "desarrolladora inmobiliaria san juan capital",
    "constructora san juan capital",
    "emprendimientos inmobiliarios san juan",
    "desarrolladora barrio norte san juan",
    "constructora barrio norte san juan",
    "desarrolladora chimbas san juan",
    "constructora rawson san juan",
    "constructora pocito san juan",
    "desarrolladora caucete san juan",

    # =========================================================================
    # SAN LUIS
    # =========================================================================
    "desarrolladora inmobiliaria san luis capital",
    "constructora san luis capital",
    "emprendimientos inmobiliarios san luis",
    "desarrolladora villa mercedes san luis",
    "constructora villa mercedes san luis",
    "desarrolladora merlo san luis",
    "constructora merlo san luis",
    "constructora la punta san luis",

    # =========================================================================
    # LA PAMPA
    # =========================================================================
    "desarrolladora inmobiliaria santa rosa la pampa",
    "constructora santa rosa la pampa",
    "emprendimientos inmobiliarios santa rosa",
    "desarrolladora general pico la pampa",
    "constructora general pico la pampa",

    # =========================================================================
    # JUJUY
    # =========================================================================
    "desarrolladora inmobiliaria san salvador de jujuy",
    "constructora san salvador de jujuy",
    "emprendimientos inmobiliarios jujuy",
    "desarrolladora barrio alto comedero jujuy",
    "constructora barrio alto comedero jujuy",
    "desarrolladora palpalá jujuy",
    "constructora palpalá jujuy",
    "desarrolladora san pedro de jujuy",
    "constructora perico jujuy",

    # =========================================================================
    # LA RIOJA
    # =========================================================================
    "desarrolladora inmobiliaria la rioja capital",
    "constructora la rioja capital",
    "emprendimientos inmobiliarios la rioja",
    "desarrolladora chilecito la rioja",
    "constructora chilecito la rioja",

    # =========================================================================
    # CATAMARCA
    # =========================================================================
    "desarrolladora inmobiliaria san fernando del valle catamarca",
    "constructora san fernando del valle catamarca",
    "emprendimientos inmobiliarios catamarca",
    "desarrolladora andalgala catamarca",
    "constructora andalgala catamarca",

    # =========================================================================
    # SANTIAGO DEL ESTERO
    # =========================================================================
    "desarrolladora inmobiliaria santiago del estero capital",
    "constructora santiago del estero capital",
    "emprendimientos inmobiliarios santiago del estero",
    "desarrolladora la banda santiago del estero",
    "constructora la banda santiago del estero",
    "constructora termas de rio hondo",

    # =========================================================================
    # FORMOSA
    # =========================================================================
    "desarrolladora inmobiliaria formosa capital",
    "constructora formosa capital",
    "emprendimientos inmobiliarios formosa",
    "constructora clorinda formosa",

    # =========================================================================
    # CHUBUT
    # =========================================================================
    "desarrolladora inmobiliaria comodoro rivadavia chubut",
    "constructora comodoro rivadavia chubut",
    "emprendimientos inmobiliarios comodoro rivadavia",
    "desarrolladora trelew chubut",
    "constructora trelew chubut",
    "desarrolladora puerto madryn chubut",
    "constructora puerto madryn chubut",
    "desarrolladora esquel chubut",
    "constructora esquel chubut",
    "constructora rawson chubut",

    # =========================================================================
    # SANTA CRUZ
    # =========================================================================
    "desarrolladora inmobiliaria rio gallegos santa cruz",
    "constructora rio gallegos santa cruz",
    "emprendimientos inmobiliarios rio gallegos",
    "desarrolladora caleta olivia santa cruz",
    "constructora caleta olivia santa cruz",
    "desarrolladora el calafate santa cruz",
    "constructora el calafate santa cruz",
    "constructora pico truncado santa cruz",

    # =========================================================================
    # TIERRA DEL FUEGO
    # =========================================================================
    "desarrolladora inmobiliaria ushuaia tierra del fuego",
    "constructora ushuaia tierra del fuego",
    "emprendimientos inmobiliarios ushuaia",
    "desarrolladora rio grande tierra del fuego",
    "constructora rio grande tierra del fuego",
    "constructora tolhuin tierra del fuego",
]

# =============================================================================
# CATEGORÍA — detectar si es desarrolladora o constructora desde la query
# =============================================================================

def detectar_tipo_desde_query(query: str) -> str:
    q = query.lower()
    if "constructora" in q or "construccion" in q or "construcciones" in q:
        return "constructora"
    if "desarrolladora" in q or "desarrollos" in q or "developer" in q or "emprendimiento" in q:
        return "desarrolladora"
    return "desarrolladora"

# =============================================================================
# MAPA PROVINCIA — igual al scraper de inmobiliarias
# =============================================================================

_PROVINCIA_MAP = [
    ("tierra del fuego",           "Tierra del Fuego"),
    ("santiago del estero",        "Santiago del Estero"),
    ("entre rios",                 "Entre Ríos"),
    ("rio negro",                  "Río Negro"),
    ("la pampa",                   "La Pampa"),
    ("la rioja",                   "La Rioja"),
    ("san juan",                   "San Juan"),
    ("san luis",                   "San Luis"),
    ("santa cruz",                 "Santa Cruz"),
    ("santa fe",                   "Santa Fe"),
    ("caba",                       "Ciudad Autónoma de Buenos Aires"),
    ("capital federal",            "Ciudad Autónoma de Buenos Aires"),
    ("buenos aires",               "Buenos Aires"),
    ("cordoba",                    "Córdoba"),
    ("mendoza",                    "Mendoza"),
    ("tucuman",                    "Tucumán"),
    ("salta",                      "Salta"),
    ("corrientes",                 "Corrientes"),
    ("chaco",                      "Chaco"),
    ("misiones",                   "Misiones"),
    ("neuquen",                    "Neuquén"),
    ("jujuy",                      "Jujuy"),
    ("catamarca",                  "Catamarca"),
    ("formosa",                    "Formosa"),
    ("chubut",                     "Chubut"),
    ("rosario",                    "Santa Fe"),
    ("parana",                     "Entre Ríos"),
    ("resistencia",                "Chaco"),
    ("posadas",                    "Misiones"),
    ("bariloche",                  "Río Negro"),
    ("ushuaia",                    "Tierra del Fuego"),
    ("rio gallegos",               "Santa Cruz"),
    ("comodoro rivadavia",         "Chubut"),
    ("trelew",                     "Chubut"),
    ("rawson",                     "Chubut"),
    ("neuquen capital",            "Neuquén"),
]


def inferir_ubicacion(query: str) -> dict:
    q = query.lower()
    provincia = ""
    barrio    = ""
    ciudad    = ""

    for clave, nombre in _PROVINCIA_MAP:
        if clave in q:
            provincia = nombre
            break

    if "barrio" in q:
        idx = q.find("barrio") + 6
        resto = q[idx:].strip()
        for clave, _ in _PROVINCIA_MAP:
            resto = resto.replace(clave, "")
        for palabra in ["desarrolladora", "constructora", "emprendimientos",
                        "inmobiliaria", "propiedades", "venta", "capital"]:
            resto = resto.replace(palabra, "")
        barrio = " ".join(resto.split()).title()

    return {"provincia": provincia, "barrio": barrio, "ciudad": ciudad}


# =============================================================================
# CHECKPOINT
# =============================================================================

def cargar_checkpoint() -> int:
    try:
        with open(CHECKPOINT_FILE, "r") as f:
            return int(f.read().strip())
    except Exception:
        return 0


def guardar_checkpoint(idx: int):
    try:
        with open(CHECKPOINT_FILE, "w") as f:
            f.write(str(idx))
    except Exception as e:
        log(f"[WARN] No se pudo guardar checkpoint: {e}")


# =============================================================================
# UTILIDADES
# =============================================================================

def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def random_delay(min_secs: float = 1.5, max_secs: float = 4.0):
    time.sleep(random.uniform(min_secs, max_secs))


def limpiar_texto(txt: str) -> str:
    if not txt:
        return ""
    return re.sub(r"\s+", " ", txt).strip()


def extraer_telefono(texto: str) -> str:
    patron_ar = re.compile(
        r"(?:(?:\+|00)?54[\s\-]?)?(?:9[\s\-]?)?(?:\(0?\d{2,4}\)[\s\-]?|\d{2,4}[\s\-])"
        r"\d{3,4}[\s\-]?\d{3,4}"
    )
    match = patron_ar.search(texto)
    if match:
        return re.sub(r"[^\d+]", "", match.group())
    patron_gen = re.compile(r"[\+]?[\d\s\-\(\)]{7,15}")
    match = patron_gen.search(texto)
    if match:
        resultado = re.sub(r"[^\d+]", "", match.group())
        if len(resultado) >= 7:
            return resultado
    return ""


def limpiar_url(href: str) -> str:
    if not href:
        return ""
    href = href.strip()
    if "/url?q=" in href:
        try:
            parsed = urlparse(href)
            qs = parse_qs(parsed.query)
            real = qs.get("q", [None])[0]
            if real:
                href = unquote_plus(real)
        except Exception:
            return ""
    if href.startswith("//"):
        href = "https:" + href
    if not href.startswith("http"):
        return ""
    try:
        parsed = urlparse(href)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
    except Exception:
        return ""


# =============================================================================
# ALMACENAMIENTO
# =============================================================================

def guardar_csv(datos: dict):
    file_exists = os.path.isfile(CSV_FILE)
    try:
        with open(CSV_FILE, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            if not file_exists:
                writer.writeheader()
                log(f"[CSV] Archivo creado: {os.path.abspath(CSV_FILE)}")
            writer.writerow({k: datos.get(k, "") for k in CSV_FIELDS})
    except Exception as e:
        log(f"   [ERROR-CSV] {e}")


def guardar_supabase(datos: dict):
    if not SUPABASE_URL or not SUPABASE_KEY:
        guardar_csv(datos)
        return

    body = {
        "nombre":             datos.get("nombre", "")      or None,
        "web":                datos.get("web", "")         or None,
        "telefono_principal": datos.get("telefono", "")    or None,
        "email_principal":    datos.get("email", "")       or None,
        "barrio":             datos.get("barrio", "")      or None,
        "ciudad":             datos.get("ciudad", "")      or None,
        "provincia":          datos.get("provincia", "")   or None,
        "pais":               datos.get("pais", "Argentina") or "Argentina",
        "categoria":          datos.get("categoria", "")   or None,
        "estado_scraping":    "ok",
        "ultimo_scrapeo":     datos.get("fecha_scrapeo", ""),
        "fuente":             "google_lugares",
    }
    global _SUPA_SESSION
    payload = json.dumps(body)

    for intento in range(1, 4):
        try:
            r = _SUPA_SESSION.post(
                SUPABASE_ENDPOINT,
                headers=SUPABASE_HEADERS,
                data=payload,
                timeout=15,
            )
            if r.status_code in (200, 201, 204):
                log(f"   [SUPA-OK] {datos.get('nombre')}")
                return
            elif r.status_code == 409:
                # Conflicto de web: hacer PATCH actualizando el registro existente por nombre
                nombre_enc = requests.utils.quote(body.get("nombre", ""), safe="")
                patch_url = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}?nombre=eq.{nombre_enc}"
                patch_body = {k: v for k, v in body.items() if k != "nombre" and v is not None}
                r2 = _SUPA_SESSION.patch(
                    patch_url,
                    headers=SUPABASE_HEADERS,
                    data=json.dumps(patch_body),
                    timeout=15,
                )
                if r2.status_code in (200, 204):
                    log(f"   [SUPA-UPDATE] {datos.get('nombre')} (actualizado)")
                else:
                    log(f"   [SUPA-ERR] HTTP {r2.status_code}: {r2.text[:120]}")
                    guardar_csv(datos)
                return
            else:
                log(f"   [SUPA-ERR] HTTP {r.status_code}: {r.text[:120]}")
                guardar_csv(datos)
                return

        except Exception as e:
            espera = 2 ** intento
            log(f"   [SUPA-REINTENTO {intento}/3] {type(e).__name__}. Reintentando en {espera}s...")
            time.sleep(espera)
            _SUPA_SESSION = _crear_sesion_supabase()

    log(f"   [SUPA-ERR] Falló tras 3 intentos. Usando CSV.")
    guardar_csv(datos)


def guardar(datos: dict):
    guardar_csv(datos)
    guardar_supabase(datos)


# =============================================================================
# SCROLL DEL PANEL
# =============================================================================

def scroll_panel_izquierdo(page, max_intentos: int = 30) -> int:
    log("[SCROLL] Cargando todos los resultados del panel...")
    items_anteriores = -1
    sin_cambio = 0

    for _ in range(max_intentos):
        items_actuales = contar_items(page)
        if items_actuales == items_anteriores:
            sin_cambio += 1
            if sin_cambio >= 3:
                log(f"[SCROLL] Sin cambios. Total: {items_actuales}")
                break
        else:
            sin_cambio = 0
            items_anteriores = items_actuales

        try:
            page.evaluate("""
                () => {
                    const sels = [
                        'div[role="main"] > div',
                        '#search > div > div',
                        'div[data-async-context]',
                        '#rcnt',
                    ];
                    for (const s of sels) {
                        const el = document.querySelector(s);
                        if (el && el.scrollHeight > el.clientHeight) {
                            el.scrollTop += 800; return;
                        }
                    }
                    window.scrollBy(0, 800);
                }
            """)
        except Exception:
            try:
                page.keyboard.press("End")
            except Exception:
                pass

        random_delay(0.8, 1.5)

        try:
            fin = page.locator(
                ":text('Has llegado al final'), :text('No hay mas resultados'), "
                ":text(\"You've reached the end\")"
            ).first
            if fin.is_visible(timeout=500):
                log("[SCROLL] Fin de resultados detectado.")
                break
        except Exception:
            pass

    return contar_items(page)


def contar_items(page) -> int:
    SELS = [
        "a.vwVdIc", "a.vwVdIc.wzN8Ac",
        "div.dbg0pd[role='heading']",
        "div[data-cid]", "div[role='article']",
        "a[href*='ludocid']",
    ]
    for sel in SELS:
        try:
            c = page.locator(sel).count()
            if c > 0:
                return c
        except Exception:
            continue
    return 0


# =============================================================================
# EXTRACCIÓN DE DATOS
# =============================================================================

_NOMBRES_INVALIDOS = {
    "resultados", "sin nombre", "sin título", "sin titulo",
    "google maps", "maps", "cerca", "negocios", "lugares",
}


def extraer_nombre(page) -> str:
    SELS = [
        "h1.DUwDvf",
        "h1.fontHeadlineLarge",
        "div[role='main'] h1",
        "h2.qrShPb span",
        "h1[data-attrid='title']",
        "h2[data-attrid='title'] span",
        "[role='heading'][aria-level='1']",
        "[role='heading'][aria-level='2'] span",
        "h1",
        "[jsaction*='pane.hero'] h1",
        "div[class*='fontHeadline'] h1",
        "div[class*='tAiQdd'] h1",
    ]
    for sel in SELS:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=1500):
                txt = limpiar_texto(loc.inner_text())
                if txt and len(txt) > 1 and txt.lower() not in _NOMBRES_INVALIDOS:
                    return txt
        except Exception:
            continue

    # Fallback 1: extraer desde la URL de Google Maps
    # /maps/place/Nombre+Del+Lugar/@...
    try:
        url = page.url
        m = re.search(r"/maps/place/([^/@]+)", url)
        if m:
            nombre_url = unquote_plus(m.group(1)).replace("+", " ").strip()
            nombre_url = limpiar_texto(nombre_url)
            if nombre_url and len(nombre_url) > 1 and nombre_url.lower() not in _NOMBRES_INVALIDOS:
                return nombre_url
    except Exception:
        pass

    # Fallback 2: título de la pestaña (formato "Nombre - Google Maps")
    try:
        titulo = page.title()
        if " - Google Maps" in titulo:
            nombre_titulo = titulo.replace(" - Google Maps", "").strip()
            nombre_titulo = limpiar_texto(nombre_titulo)
            if nombre_titulo and len(nombre_titulo) > 1 and nombre_titulo.lower() not in _NOMBRES_INVALIDOS:
                return nombre_titulo
    except Exception:
        pass

    return ""


def extraer_direccion(page) -> str:
    SELS = [
        "[data-item-id='address']",
        "button[data-item-id='address']",
        "[aria-label*='direcci']",
        "[aria-label*='irec']",
        "[data-tooltip*='irec']",
        "div[data-attrid='kc:/location/location:address'] span",
        "span[jsan*='address']",
    ]
    for sel in SELS:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=1500):
                txt = limpiar_texto(
                    loc.inner_text() or loc.get_attribute("aria-label") or ""
                )
                if txt:
                    return txt
        except Exception:
            continue
    try:
        bloque = page.locator("div[data-item-id='address'], div[jsaction*='address']").first
        return limpiar_texto(bloque.inner_text())
    except Exception:
        return ""


def extraer_telefono_panel(page) -> str:
    SELS = [
        "[data-item-id*='phone']",
        "[aria-label*='eléfono']",
        "[aria-label*='elefono']",
        "[aria-label*='hone']",
        "button[data-item-id*='oh']",
    ]
    for sel in SELS:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=1500):
                txt = loc.get_attribute("aria-label") or loc.inner_text() or ""
                tel = extraer_telefono(txt)
                if tel:
                    return tel
        except Exception:
            continue
    try:
        texto = page.locator("div[role='main']").first.inner_text()
        return extraer_telefono(texto)
    except Exception:
        return ""


def extraer_email(page) -> str:
    try:
        links = page.locator("a[href^='mailto:']").all()
        for link in links:
            href = link.get_attribute("href") or ""
            if href.startswith("mailto:"):
                email = href[7:].split("?")[0].strip()
                if "@" in email:
                    return email
    except Exception:
        pass

    SELS = [
        "[data-item-id*='email']",
        "[aria-label*='mail']",
        "[aria-label*='correo']",
    ]
    for sel in SELS:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=1000):
                txt = loc.get_attribute("aria-label") or loc.inner_text() or ""
                if "@" in txt:
                    return txt.strip()
        except Exception:
            continue

    try:
        texto = page.locator("div[role='main']").first.inner_text()
        match = re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", texto)
        if match:
            return match.group()
    except Exception:
        pass
    return ""


def extraer_web(page) -> str:
    SELS = [
        "a[data-item-id='authority']",
        "a[aria-label*='itio web']",
        "a[aria-label*='ebsite']",
        "a.yYlJEf:has-text('Sitio web')",
        "a.yYlJEf.Q7PwXb:has-text('Sitio web')",
        "a[href*='http'][jsname]:not([href*='google'])",
    ]
    for sel in SELS:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=2000):
                url = limpiar_url(loc.get_attribute("href") or "")
                if url and "google.com" not in url:
                    return url
        except Exception:
            continue
    try:
        links = page.locator("div[role='main'] a[href^='http']").all()
        for link in links:
            href = link.get_attribute("href") or ""
            if "google.com" not in href:
                url = limpiar_url(href)
                if url:
                    return url
    except Exception:
        pass
    return ""


def extraer_rating_resenas(page) -> tuple:
    rating, resenas = "", ""
    try:
        loc = page.locator(
            "span[aria-label*='stella'], span[aria-label*='star'], "
            "div[aria-label*='star'], div[aria-label*='stella']"
        ).first
        if loc.is_visible(timeout=1500):
            lbl = loc.get_attribute("aria-label") or ""
            m = re.search(r"[\d,\.]+", lbl)
            if m:
                rating = m.group().replace(",", ".")
    except Exception:
        pass
    try:
        loc = page.locator(
            "span[aria-label*='eseña'], span[aria-label*='eview'], "
            "button[aria-label*='eseña']"
        ).first
        if loc.is_visible(timeout=1000):
            lbl = loc.get_attribute("aria-label") or loc.inner_text() or ""
            m = re.search(r"[\d\.]+", lbl.replace(",", ""))
            if m:
                resenas = m.group()
    except Exception:
        pass
    return rating, resenas


def detectar_captcha(page) -> bool:
    titulo = page.title().lower()
    if any(w in titulo for w in ["unusual traffic", "captcha", "verifica", "robot",
                                  "before you continue", "our systems"]):
        return True
    try:
        if page.locator(
            "form#captcha-form, div#captcha, iframe[src*='recaptcha'], "
            "div[id*='challenge'], #recaptcha"
        ).count() > 0:
            return True
    except Exception:
        pass
    return False


def extraer_categoria_google(page) -> str:
    SELS = [
        "button.DkEaL",
        "span.mgr77e",
        "div.fontBodyMedium.dmRWX",
        "button[jsaction*='category']",
        "[data-attrid*='category'] span",
    ]
    for sel in SELS:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=1000):
                txt = limpiar_texto(loc.inner_text())
                if txt and len(txt) > 1:
                    return txt
        except Exception:
            continue
    return ""


def extraer_ciudad_de_direccion(direccion: str) -> str:
    if not direccion:
        return ""
    partes = [p.strip() for p in direccion.split(",")]
    if len(partes) >= 2:
        for parte in reversed(partes[1:]):
            parte_limpia = re.sub(r"\d", "", parte).strip()
            if len(parte_limpia) > 2:
                return parte.strip()
    return ""


# =============================================================================
# PROCESAMIENTO DE UN RESULTADO
# =============================================================================

def _volver_al_listado(page):
    """Vuelve al listado de resultados usando el botón interno de Google Maps."""
    if "/maps/place/" not in page.url:
        return
    # Intentar con el botón flecha "Volver" que existe en el panel de detalle
    SELS_BACK = [
        "button[aria-label='Volver']",
        "button[aria-label='Back']",
        "button[jsaction*='back']",
        "div[role='button'][aria-label*='olver']",
        "button.hjuVxf",
        "button.VfPpkd-icon-button",
        "[data-tooltip='Volver']",
        "[data-tooltip='Back']",
    ]
    for sel in SELS_BACK:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=1500):
                btn.click(timeout=3000)
                # Esperar a que el panel de lista vuelva a aparecer
                try:
                    page.wait_for_selector("a.vwVdIc, div[data-cid]", timeout=5000)
                except Exception:
                    pass
                random_delay(0.8, 1.5)
                return
        except Exception:
            continue
    # Fallback: go_back del navegador
    try:
        page.go_back(wait_until="domcontentloaded", timeout=10000)
        try:
            page.wait_for_selector("a.vwVdIc, div[data-cid]", timeout=5000)
        except Exception:
            pass
        random_delay(1.0, 2.0)
    except Exception as e:
        log(f"   [WARN] go_back fallido: {e}")


def _nombre_desde_panel(item) -> str:
    """Extrae el nombre del item directamente desde el panel sin clickear."""
    SELS_PANEL = [
        ".qBF1Pd",          # clase común en resultados de Maps
        ".fontHeadlineSmall",
        "span[class*='fontHeadline']",
        "div[class*='fontHeadline']",
        ".NrDZNb",
        "span[jsan*='t_el']",
        "div[aria-label]",
    ]
    for sel in SELS_PANEL:
        try:
            loc = item.locator(sel).first
            txt = limpiar_texto(loc.inner_text())
            if txt and len(txt) > 1 and txt.lower() not in _NOMBRES_INVALIDOS:
                return txt
        except Exception:
            continue
    # Fallback: aria-label del propio item
    try:
        label = item.get_attribute("aria-label") or ""
        txt = limpiar_texto(label.split("\n")[0])
        if txt and len(txt) > 1 and txt.lower() not in _NOMBRES_INVALIDOS:
            return txt
    except Exception:
        pass
    return ""


def procesar_resultado(page, idx: int, total: int, vistos: set,
                       ubicacion_query: dict, categoria_query: str) -> dict | None:
    ITEM_SELS = [
        "a.vwVdIc", "a.vwVdIc.wzN8Ac",
        "div[data-cid]", "div[role='article']",
    ]
    item = None
    for sel in ITEM_SELS:
        try:
            items = page.locator(sel).all()
            if idx < len(items):
                item = items[idx]
                break
        except Exception:
            continue

    if not item:
        log(f"   [WARN] Item #{idx+1} no encontrado.")
        return None

    # Chequeo rápido de duplicado desde el panel (sin clickear)
    nombre_panel = _nombre_desde_panel(item)
    if nombre_panel:
        clave_panel = nombre_panel.lower().strip()
        if clave_panel in vistos:
            log(f"   [DUP-FAST] '{nombre_panel}' (salteado sin clickear)")
            return None

    url_antes = page.url

    for intento in range(3):
        try:
            item.scroll_into_view_if_needed(timeout=3000)
            random_delay(0.5, 1.0)
            item.click(timeout=5000)
            break
        except Exception as e:
            if intento == 2:
                log(f"   [WARN] Click fallido en #{idx+1}: {e}")
                return None
            random_delay(1, 2)

    try:
        page.wait_for_url("**/maps/place/**", timeout=8000)
    except PlaywrightTimeoutError:
        for sel_det in ["h1.DUwDvf", "h1.fontHeadlineLarge", "div[role='main'] h1"]:
            try:
                page.wait_for_selector(sel_det, timeout=4000)
                break
            except Exception:
                continue

    # Si la URL no cambió, el click no navegó — salteamos
    if page.url == url_antes:
        log(f"   [SKIP] #{idx+1}: click no navegó.")
        return None

    random_delay(1.5, 3.0)

    nombre = extraer_nombre(page)
    if not nombre:
        # Segundo intento: esperar un poco más por si el DOM aún carga
        page.wait_for_timeout(2000)
        nombre = extraer_nombre(page)
    if not nombre:
        log(f"   [SKIP] #{idx+1}: nombre vacío.")
        _volver_al_listado(page)
        return None

    clave = nombre.lower().strip()
    if clave in vistos:
        log(f"   [DUP] '{nombre}'")
        _volver_al_listado(page)
        return None
    vistos.add(clave)

    direccion = extraer_direccion(page)
    telefono  = extraer_telefono_panel(page)
    email     = extraer_email(page)
    web       = extraer_web(page)
    rating, resenas = extraer_rating_resenas(page)

    # Categoría: primero la de Google Maps, sino la inferida desde la query
    categoria_google = extraer_categoria_google(page)
    categoria = categoria_google or categoria_query

    if web:
        clave_web = web.lower().rstrip("/")
        if clave_web in vistos:
            log(f"   [DUP-WEB] '{web}'")
            _volver_al_listado(page)
            return "DUP"
        vistos.add(clave_web)

    ciudad = extraer_ciudad_de_direccion(direccion) or ubicacion_query.get("ciudad", "")
    barrio = ubicacion_query.get("barrio", "")

    datos = {
        "nombre":        nombre,
        "direccion":     direccion,
        "barrio":        barrio,
        "ciudad":        ciudad,
        "provincia":     ubicacion_query.get("provincia", ""),
        "pais":          "Argentina",
        "telefono":      telefono,
        "email":         email,
        "web":           web,
        "rating":        rating,
        "resenas":       resenas,
        "categoria":     categoria,
        "fuente":        "google_lugares",
        "fecha_scrapeo": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    log(
        f"   [{idx+1}/{total}] {nombre} | "
        f"cat={categoria or '-'} | "
        f"tel={telefono or '-'} | web={web or '-'} | {ubicacion_query.get('provincia','')}"
    )

    _volver_al_listado(page)
    return datos


# =============================================================================
# SCRAPER DE UNA QUERY
# =============================================================================

def scrapear_query(page, query: str, vistos: set) -> int:
    url = GOOGLE_LUGARES_URL.format(query=query.replace(" ", "+"))
    log(f"\n[QUERY] '{query}'")
    log(f"[URL]   {url}")

    ubicacion_query  = inferir_ubicacion(query)
    categoria_query  = detectar_tipo_desde_query(query)

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        random_delay(2, 4)
    except PlaywrightTimeoutError:
        log(f"[ERROR] Timeout: {url}")
        return 0
    except Exception as e:
        log(f"[ERROR] {e}")
        return 0

    try:
        btn = page.locator(
            "button:has-text('Aceptar todo'), button:has-text('Accept all'), "
            "button:has-text('Aceptar'), button[aria-label*='Accept']"
        ).first
        if btn.is_visible(timeout=4000):
            btn.click()
            log("[INFO] Cookies aceptadas.")
            random_delay(1.5, 2.5)
    except Exception:
        pass

    log(f"[INFO] Título: {page.title()[:65]}")

    if detectar_captcha(page):
        log("[CAPTCHA] Google está pidiendo verificación. Pausando 90 segundos...")
        try:
            path = os.path.join(script_dir, "debug_captcha_desarrolladoras.png")
            page.screenshot(path=path)
            log(f"[CAPTCHA] Screenshot: {os.path.abspath(path)}")
        except Exception:
            pass
        time.sleep(90)
        if detectar_captcha(page):
            log("[CAPTCHA] Sigue bloqueado. Saltando query.")
            return 0

    total_items = scroll_panel_izquierdo(page)
    log(f"[INFO] Items detectados: {total_items}")

    if total_items == 0:
        log("[WARN] Sin items.")
        return 0

    guardados = 0
    dups_consecutivos = 0
    for idx in range(total_items):
        try:
            datos = procesar_resultado(
                page, idx, total_items, vistos,
                ubicacion_query, categoria_query
            )
            if datos == "DUP":
                dups_consecutivos += 1
                if dups_consecutivos >= 2:
                    log(f"   [CORTE] 2 duplicados consecutivos — pasando a la siguiente query.")
                    break
                random_delay(2, 4)
                continue
            dups_consecutivos = 0
            if datos:
                guardar(datos)
                guardados += 1
            random_delay(2, 4)
        except Exception as e:
            log(f"   [ERROR] Item #{idx+1}: {e}")
            continue

    return guardados


# =============================================================================
# MAIN
# =============================================================================

def main():
    log("=" * 65)
    log("SCRAPER GOOGLE — Desarrolladoras y Constructoras — Argentina")
    log(f"Supabase : {SUPABASE_ENDPOINT}")
    log(f"CSV      : {os.path.abspath(CSV_FILE)}")
    log(f"Stealth  : {'ACTIVADO' if STEALTH_AVAILABLE else 'NO disponible'}")
    log(f"Queries  : {len(QUERIES)}")
    log("=" * 65)

    inicio = cargar_checkpoint()
    if inicio > 0:
        log(f"[CHECKPOINT] Retomando desde query #{inicio + 1} de {len(QUERIES)}")
    else:
        log("[CHECKPOINT] Empezando desde el inicio.")

    vistos: set = set()

    with sync_playwright() as p:
        browser = None
        try:
            browser = p.chromium.launch(
                headless=False,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1400, "height": 900},
                locale="es-AR",
                device_scale_factor=1,
                is_mobile=False,
            )
            page = context.new_page()

            if STEALTH_AVAILABLE:
                stealth_sync(page)
                log("[INFO] Stealth aplicado.")

            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = { runtime: {} };
            """)

            total_global = 0
            for i, query in enumerate(QUERIES, start=1):
                if i - 1 < inicio:
                    continue
                log(f"\n[{i}/{len(QUERIES)}] '{query}'")
                try:
                    guardados = scrapear_query(page, query, vistos)
                    total_global += guardados
                    log(f"[FIN-QUERY] {guardados} nuevos | acumulado: {total_global}")
                except Exception as e:
                    log(f"[ERROR-QUERY] {e}")
                    log(traceback.format_exc())
                guardar_checkpoint(i)
                if i < len(QUERIES):
                    random_delay(4, 8)

            log(f"\n{'='*65}")
            log(f"[COMPLETADO] Total guardados: {total_global}")
            log(f"CSV: {os.path.abspath(CSV_FILE)}")
            log("=" * 65)

        except Exception as e:
            log(f"[ERROR FATAL] {e}")
            log(traceback.format_exc())
        finally:
            if browser:
                try:
                    browser.close()
                    log("[INFO] Navegador cerrado.")
                except Exception:
                    pass


if __name__ == "__main__":
    main()
