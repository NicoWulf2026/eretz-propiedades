"""
enrich_pipeline.py  —  v2.0
----------------------------
Pipeline de limpieza, corrección y enriquecimiento para inmobiliarias_scraping.

Fases:
  0 · Carga y estadísticas iniciales
  1 · Corrección local (sin internet): nombres, teléfonos, webs, emails, categoría
  2 · Enriquecimiento web (paralelo): contacto, CMS, listado, paginación, antibot
  3 · Guardado incremental en Supabase con retry
  4 · Reporte final

SQL requerido (ejecutar una vez en Supabase antes de correr):
──────────────────────────────────────────────────────────────
  ALTER TABLE inmobiliarias_scraping
    ADD COLUMN IF NOT EXISTS confidence_score     INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS needs_manual_review  BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS enrich_version       TEXT,
    ADD COLUMN IF NOT EXISTS nombre_limpio        TEXT,
    ADD COLUMN IF NOT EXISTS fuente_telefono      TEXT,
    ADD COLUMN IF NOT EXISTS fuente_email         TEXT,
    ADD COLUMN IF NOT EXISTS cms_detectado        TEXT,
    ADD COLUMN IF NOT EXISTS url_listado          TEXT,
    ADD COLUMN IF NOT EXISTS sitio_activo         BOOLEAN,
    ADD COLUMN IF NOT EXISTS tipo_paginacion      TEXT,
    ADD COLUMN IF NOT EXISTS total_propiedades    INTEGER,
    ADD COLUMN IF NOT EXISTS tiene_antibot        BOOLEAN,
    ADD COLUMN IF NOT EXISTS tokko_api_key        TEXT,
    ADD COLUMN IF NOT EXISTS paginas_estimadas    INTEGER,
    ADD COLUMN IF NOT EXISTS ultimo_chequeo       TIMESTAMPTZ;

  CREATE INDEX IF NOT EXISTS idx_scraping_web     ON inmobiliarias_scraping (web);
  CREATE INDEX IF NOT EXISTS idx_scraping_nombre  ON inmobiliarias_scraping (nombre);
  CREATE INDEX IF NOT EXISTS idx_scraping_ciudad  ON inmobiliarias_scraping (ciudad);
──────────────────────────────────────────────────────────────

Dependencias: pip install requests beautifulsoup4 python-dotenv
"""

import os
import re
import time
import random
import logging
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# CONFIG
# =============================================================================

SUPABASE_URL      = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY      = (os.getenv("SUPABASE_SERVICE_ROLE_KEY")
                     or os.getenv("SUPABASE_KEY")
                     or os.getenv("SUPABASE_ANON_KEY", ""))
TABLA             = "inmobiliarias_scraping"
ENRICH_VERSION    = "2.0"
BATCH_SIZE        = 50
WEB_TIMEOUT       = 12
MAX_WORKERS       = 6          # fetches paralelos
PROPS_POR_PAGINA  = 12
CHECKPOINT_FILE   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "checkpoint_enrich.txt")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("enrich")

# =============================================================================
# SUPABASE
# =============================================================================

_SUPA_SESSION = requests.Session()


def _headers(prefer: str = "return=minimal") -> Dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def cargar_registros() -> List[Dict[str, Any]]:
    todos, pagina, tam = [], 0, 1000
    while True:
        desde, hasta = pagina * tam, pagina * tam + tam - 1
        resp = _SUPA_SESSION.get(
            f"{SUPABASE_URL}/rest/v1/{TABLA}",
            headers={**_headers(), "Range-Unit": "items", "Range": f"{desde}-{hasta}"},
            params={"select": "*", "order": "id.asc"},
            timeout=60,
        )
        if resp.status_code == 416:
            break
        resp.raise_for_status()
        lote = resp.json()
        if not lote:
            break
        todos.extend(lote)
        log.info(f"  Cargados {len(todos)}…")
        if len(lote) < tam:
            break
        pagina += 1
    log.info(f"Total: {len(todos)} registros")
    return todos


def patch_registro(rid: int, cambios: Dict[str, Any]) -> bool:
    if not cambios or not rid:
        return True
    url = f"{SUPABASE_URL}/rest/v1/{TABLA}?id=eq.{rid}"
    for intento in range(4):
        try:
            resp = _SUPA_SESSION.patch(url, headers=_headers(), json=cambios, timeout=30)
            if resp.status_code in (200, 204):
                return True
            # Web duplicada → reintentar sin el campo web
            if resp.status_code == 409 and "web" in cambios:
                sin_web = {k: v for k, v in cambios.items() if k != "web"}
                if sin_web:
                    r2 = _SUPA_SESSION.patch(url, headers=_headers(), json=sin_web, timeout=30)
                    if r2.status_code in (200, 204):
                        return True
                return False
            log.warning(f"  PATCH {rid} → {resp.status_code}: {resp.text[:100]}")
            return False
        except Exception as e:
            if intento == 3:
                log.warning(f"  PATCH {rid} falló: {e}")
                return False
            time.sleep(2 ** intento)
    return False


# =============================================================================
# CHECKPOINT
# =============================================================================

def cargar_checkpoint() -> int:
    try:
        with open(CHECKPOINT_FILE) as f:
            return int(f.read().strip())
    except Exception:
        return 0


def guardar_checkpoint(ultimo_id: int):
    try:
        with open(CHECKPOINT_FILE, "w") as f:
            f.write(str(ultimo_id))
    except Exception:
        pass


# =============================================================================
# NORMALIZACION
# =============================================================================

_RE_DIGITS   = re.compile(r"\D")
_RE_EMAIL    = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
_RE_URL      = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.I)

_RUIDO_NOMBRE = re.compile(
    r"\b(ver mapa|abierto|cerrado|califica|reseña|sin reseñas|google|maps|"
    r"ver sitio|sitio web|abrir|nuevo|verificado|reclamado|sponsored|"
    r"patrocinado|anuncio)\b",
    re.IGNORECASE,
)

_DOMINIOS_INVALIDOS: Set[str] = {
    "google.com", "facebook.com", "instagram.com", "twitter.com", "x.com",
    "youtube.com", "whatsapp.com", "gmail.com", "hotmail.com", "outlook.com",
    "zonaprop.com.ar", "argenprop.com", "mercadolibre.com.ar", "linkedin.com",
    "tiktok.com",
}

_EMAILS_INVALIDOS = {"example@", "noreply@", "no-reply@", "test@", "email@",
                     "correo@", "info@info", "admin@admin"}


def quitar_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def limpiar_nombre(nombre: Optional[str]) -> Optional[str]:
    if not nombre:
        return None
    n = nombre.strip()
    n = _RUIDO_NOMBRE.sub("", n)
    n = re.sub(r"\s{2,}", " ", n).strip()
    # Quitar si empieza con número de rating (e.g. "4.2 Inmobiliaria")
    n = re.sub(r"^\d+[.,]\d+\s+", "", n)
    # Quitar si termina con caracteres raros
    n = re.sub(r"[·•|]+$", "", n).strip()
    return n if len(n) >= 3 else None


def normalizar_nombre_clave(nombre: str) -> str:
    """Clave para comparación de similitud entre nombres."""
    n = quitar_acentos(nombre.lower().strip())
    n = re.sub(r"\b(s\.?a\.?|s\.?r\.?l\.?|s\.?a\.?s\.?|s\.?a\.?c\.?|"
               r"inmobiliaria|propiedades|negocios|bienes raices|"
               r"real estate|broker)\b", "", n)
    return re.sub(r"[^\w]", "", n)


def normalizar_telefono(tel: Optional[str]) -> Optional[str]:
    if not tel:
        return None
    digits = _RE_DIGITS.sub("", str(tel))
    if not digits or len(digits) < 7:
        return None
    if len(digits) == 10:
        return f"+54{digits}"
    if len(digits) == 11 and digits.startswith("0"):
        return f"+54{digits[1:]}"
    if len(digits) == 12 and digits.startswith("54"):
        return f"+{digits}"
    if len(digits) == 13 and digits.startswith("549"):
        return f"+{digits}"
    return digits if len(digits) >= 7 else None


def normalizar_web(web: Optional[str]) -> Optional[str]:
    if not web:
        return None
    w = web.strip().lower().replace(" ", "")
    if not w:
        return None
    if not w.startswith("http"):
        w = "https://" + w
    return w.rstrip("/")


def normalizar_email(email: Optional[str]) -> Optional[str]:
    if not email:
        return None
    e = email.strip().lower()
    return e if _RE_EMAIL.match(e) and not any(x in e for x in _EMAILS_INVALIDOS) else None


def es_web_valida(web: Optional[str]) -> bool:
    if not web:
        return False
    try:
        parsed = urlparse(web)
        dominio = parsed.netloc.lower().replace("www.", "")
        return (dominio not in _DOMINIOS_INVALIDOS
                and bool(_RE_URL.match(web))
                and len(dominio) > 3)
    except Exception:
        return False


def es_telefono_valido(tel: Optional[str]) -> bool:
    if not tel:
        return False
    digits = _RE_DIGITS.sub("", tel)
    return 7 <= len(digits) <= 15


# =============================================================================
# CIUDAD → PROVINCIA
# =============================================================================

_CIUDAD_A_PROVINCIA: Dict[str, str] = {
    # Buenos Aires
    "mar del plata": "Buenos Aires", "la plata": "Buenos Aires",
    "bahia blanca": "Buenos Aires", "quilmes": "Buenos Aires",
    "lomas de zamora": "Buenos Aires", "tigre": "Buenos Aires",
    "san isidro": "Buenos Aires", "vicente lopez": "Buenos Aires",
    "morón": "Buenos Aires", "moron": "Buenos Aires",
    "tres de febrero": "Buenos Aires", "pilar": "Buenos Aires",
    "campana": "Buenos Aires", "zarate": "Buenos Aires",
    "tandil": "Buenos Aires", "necochea": "Buenos Aires",
    "lujan": "Buenos Aires", "mercedes": "Buenos Aires",
    "san martin": "Buenos Aires", "avellaneda": "Buenos Aires",
    "lanus": "Buenos Aires", "florencio varela": "Buenos Aires",
    "berazategui": "Buenos Aires", "ezeiza": "Buenos Aires",
    "merlo": "Buenos Aires", "moreno": "Buenos Aires",
    "ituzaingo": "Buenos Aires",
    # CABA
    "buenos aires": "Ciudad Autónoma de Buenos Aires",
    "caba": "Ciudad Autónoma de Buenos Aires",
    "capital federal": "Ciudad Autónoma de Buenos Aires",
    "palermo": "Ciudad Autónoma de Buenos Aires",
    "belgrano": "Ciudad Autónoma de Buenos Aires",
    "caballito": "Ciudad Autónoma de Buenos Aires",
    "recoleta": "Ciudad Autónoma de Buenos Aires",
    "san telmo": "Ciudad Autónoma de Buenos Aires",
    "villa crespo": "Ciudad Autónoma de Buenos Aires",
    "flores": "Ciudad Autónoma de Buenos Aires",
    "almagro": "Ciudad Autónoma de Buenos Aires",
    "boedo": "Ciudad Autónoma de Buenos Aires",
    "microcentro": "Ciudad Autónoma de Buenos Aires",
    "retiro": "Ciudad Autónoma de Buenos Aires",
    "nuñez": "Ciudad Autónoma de Buenos Aires",
    "saavedra": "Ciudad Autónoma de Buenos Aires",
    # Córdoba
    "cordoba": "Córdoba", "córdoba": "Córdoba",
    "villa carlos paz": "Córdoba", "carlos paz": "Córdoba",
    "rio cuarto": "Córdoba", "bell ville": "Córdoba",
    "alta gracia": "Córdoba", "villa maria": "Córdoba",
    "rio tercero": "Córdoba",
    # Santa Fe
    "santa fe": "Santa Fe", "rosario": "Santa Fe",
    "rafaela": "Santa Fe", "venado tuerto": "Santa Fe",
    "reconquista": "Santa Fe", "santo tome": "Santa Fe",
    "san lorenzo": "Santa Fe", "villa gobernador galvez": "Santa Fe",
    "esperanza": "Santa Fe", "galvez": "Santa Fe",
    # Mendoza
    "mendoza": "Mendoza", "san rafael": "Mendoza",
    "godoy cruz": "Mendoza", "lujan de cuyo": "Mendoza",
    "maipu": "Mendoza",
    # Tucumán
    "tucuman": "Tucumán", "san miguel de tucuman": "Tucumán",
    "tafi viejo": "Tucumán", "banda del rio sali": "Tucumán",
    # Salta
    "salta": "Salta", "tartagal": "Salta",
    # Neuquén
    "neuquen": "Neuquén", "san martin de los andes": "Neuquén",
    "villa la angostura": "Neuquén",
    # Río Negro
    "bariloche": "Río Negro", "viedma": "Río Negro",
    "cipolletti": "Río Negro", "allen": "Río Negro",
    # Entre Ríos
    "parana": "Entre Ríos", "concepcion del uruguay": "Entre Ríos",
    "concordia": "Entre Ríos", "gualeguaychu": "Entre Ríos",
    # Misiones
    "posadas": "Misiones", "oberá": "Misiones", "eldorado": "Misiones",
    # Corrientes
    "corrientes": "Corrientes", "goya": "Corrientes",
    # Jujuy
    "san salvador de jujuy": "Jujuy", "jujuy": "Jujuy",
    # Chaco
    "resistencia": "Chaco", "chaco": "Chaco",
    # Formosa
    "formosa": "Formosa",
    # La Rioja
    "la rioja": "La Rioja",
    # San Juan
    "san juan": "San Juan",
    # San Luis
    "san luis": "San Luis", "villa mercedes": "San Luis",
    # Catamarca
    "catamarca": "Catamarca",
    # La Pampa
    "santa rosa": "La Pampa",
    # Chubut
    "comodoro rivadavia": "Chubut", "trelew": "Chubut", "rawson": "Chubut",
    "esquel": "Chubut",
    # Santa Cruz
    "rio gallegos": "Santa Cruz", "caleta olivia": "Santa Cruz",
    # Tierra del Fuego
    "ushuaia": "Tierra del Fuego", "rio grande": "Tierra del Fuego",
}


def provincia_desde_ciudad(ciudad: Optional[str]) -> Optional[str]:
    if not ciudad:
        return None
    clave = quitar_acentos(ciudad.lower().strip())
    return _CIUDAD_A_PROVINCIA.get(clave)


def inferir_provincia_texto(texto: str) -> Optional[str]:
    texto_norm = quitar_acentos(texto.lower())
    for clave, prov in _CIUDAD_A_PROVINCIA.items():
        if clave in texto_norm:
            return prov
    return None


# =============================================================================
# SIMILITUD DE NOMBRES (anti-duplicado)
# =============================================================================

def similitud(a: str, b: str) -> float:
    return SequenceMatcher(None, normalizar_nombre_clave(a),
                           normalizar_nombre_clave(b)).ratio()


def es_probable_duplicado(nombre: str, existentes: Set[str], umbral: float = 0.92) -> bool:
    clave = normalizar_nombre_clave(nombre)
    for ex in existentes:
        if SequenceMatcher(None, clave, ex).ratio() >= umbral:
            return True
    return False


# =============================================================================
# HTTP
# =============================================================================

_HEADERS_WEB = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0.0.0 Safari/537.36"),
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_WEB_SESSION = requests.Session()


def _fetch(url: str, timeout: int = WEB_TIMEOUT) -> Tuple[Optional[str], int]:
    """Descarga HTML con fallback a www. Devuelve (html, status)."""
    for target in [url, _con_www(url)]:
        if not target:
            continue
        try:
            resp = _WEB_SESSION.get(target, headers=_HEADERS_WEB,
                                    timeout=timeout, allow_redirects=True)
            if resp.status_code == 200:
                resp.encoding = resp.apparent_encoding or "utf-8"
                return resp.text, 200
        except Exception:
            continue
    return None, 0


def _con_www(url: str) -> Optional[str]:
    try:
        p = urlparse(url)
        if "www." not in p.netloc:
            return f"{p.scheme}://www.{p.netloc}{p.path}"
    except Exception:
        pass
    return None


def _fetch_contacto(url_base: str) -> Optional[str]:
    """Intenta páginas de contacto adicionales."""
    parsed = urlparse(url_base)
    dominio = f"{parsed.scheme}://{parsed.netloc}"
    for path in ["/contacto", "/contact", "/contactanos", "/quienes-somos",
                 "/nosotros", "/about", "/about-us"]:
        html, status = _fetch(f"{dominio}{path}", timeout=8)
        if html and status == 200:
            return html
    return None


# =============================================================================
# CMS DETECTION
# =============================================================================

_CMS_FIRMAS: Dict[str, List[str]] = {
    "tokko": ["tokkobroker.com", "TokkoWidget", "tokko_key", "api.tokkobroker",
               "tokko-widget", "data-tokko", "tokko.com"],
    "wordpress": ["wp-content/", "wp-includes/", "/wp-json/", "wp-login.php"],
    "wix": ["wix.com", "_wixCIDX", "static.wixstatic.com", "wixsite.com"],
    "webflow": ["webflow.com", "assets-global.website-files.com"],
    "shopify": ["cdn.shopify.com", "myshopify.com"],
    "squarespace": ["squarespace.com", "sqspcdn.com"],
    "nexo": ["nexoinmuebles.com", "nexo.com.ar"],
    "inmoweb": ["inmoweb.com.ar"],
    "properati": ["properati.com"],
    "zonaprop": ["zonaprop.com.ar"],
    "argenprop": ["argenprop.com"],
}


def detectar_cms(html: str, url: str) -> str:
    muestra = html[:60000].lower()
    url_l = url.lower()
    for cms, firmas in _CMS_FIRMAS.items():
        for f in firmas:
            if f.lower() in muestra or f.lower() in url_l:
                return cms
    return "custom"


# =============================================================================
# ANTIBOT
# =============================================================================

_ANTIBOT_FIRMAS = [
    "cf-browser-verification", "cloudflare", "checking your browser",
    "ray id", "turnstile", "captcha", "recaptcha", "hcaptcha",
    "ddos-guard", "just a moment", "verifying you are human",
]


def detectar_antibot(html: str, status: int) -> bool:
    if status in (403, 503, 429):
        return True
    if not html:
        return False
    return any(f in html[:5000].lower() for f in _ANTIBOT_FIRMAS)


# =============================================================================
# TOKKO API KEY
# =============================================================================

_RE_TOKKO_KEY  = re.compile(
    r"""(?:tokko[_\-]?key|api[_\-]?key|apiKey)\s*[=:'"]+\s*['"]?([a-zA-Z0-9\-_]{20,50})['"]?""",
    re.IGNORECASE)
_RE_TOKKO_UUID = re.compile(
    r"""tokko[^'"]{0,30}['"]([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})['"]""",
    re.IGNORECASE)


def detectar_tokko_key(html: str) -> Optional[str]:
    for pat in (_RE_TOKKO_UUID, _RE_TOKKO_KEY):
        m = pat.search(html)
        if m:
            return m.group(1)
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script", src=True):
        src = tag.get("src", "")
        if "tokko" in src.lower():
            m2 = re.search(r"[?&]key=([a-zA-Z0-9\-_]{20,50})", src)
            if m2:
                return m2.group(1)
    return None


# =============================================================================
# CONTACTO (teléfono + email)
# =============================================================================

_RE_TEL = re.compile(
    r"(?:\+54|0054|011|0\d{2,4})[\s\-]?(?:15[\s\-]?)?\d{4}[\s\-]?\d{4}"
    r"|\+54\s?9?\s?\d{2,4}[\s\-]?\d{4}[\s\-]?\d{4}"
    r"|\(\d{2,4}\)\s?\d{4}[\s\-]?\d{4}",
)
_RE_EMAIL_WEB = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


def extraer_telefonos(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    raw = []
    for a in soup.find_all("a", href=re.compile(r"^tel:")):
        raw.append(a["href"].replace("tel:", "").strip())
    raw.extend(_RE_TEL.findall(soup.get_text(" ", strip=True)))
    seen, result = set(), []
    for t in raw:
        n = normalizar_telefono(t)
        if n and n not in seen:
            seen.add(n)
            result.append(n)
    return result


def extraer_emails(html: str, dominio: str = "") -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    raw = []
    for a in soup.find_all("a", href=re.compile(r"^mailto:")):
        e = a["href"].replace("mailto:", "").split("?")[0].strip().lower()
        raw.append(e)
    raw.extend(m.lower() for m in _RE_EMAIL_WEB.findall(soup.get_text(" ", strip=True)))
    seen, result = set(), []
    for e in raw:
        ne = normalizar_email(e)
        if ne and ne not in seen:
            seen.add(ne)
            result.append(ne)
    propios  = [e for e in result if dominio and dominio in e]
    externos = [e for e in result if e not in propios]
    return propios + externos


# =============================================================================
# URL LISTADO + PAGINACION + PROPIEDADES
# =============================================================================

_KW_LISTADO = ["propiedades", "inmuebles", "listings", "properties",
               "ventas", "alquileres", "venta", "alquiler",
               "en-venta", "en-alquiler", "catalogo", "buscar"]

_PATHS_LISTADO = ["/propiedades", "/inmuebles", "/ventas", "/alquileres",
                  "/listings", "/properties", "/catalogo", "/buscar",
                  "/propiedades-en-venta", "/venta", "/alquiler"]

_SCROLL_KW  = ["infinite", "infiniteScroll", "lazyload", "IntersectionObserver",
               "loadMore", "cargar-mas"]
_CLICK_KW   = ["siguiente", "next", "btn-next", "pagination", "paginacion"]
_RE_PAG_URL = re.compile(r"[?&](page|pagina|p|pg)=\d+|/page[/-]\d+", re.I)
_RE_TOTAL   = re.compile(r"(\d[\d\.,]{0,5})\s*(?:propiedades?|inmuebles?|resultados?|listings?)",
                          re.IGNORECASE)


def buscar_url_listado(html: str, url_base: str) -> Optional[str]:
    soup   = BeautifulSoup(html, "html.parser")
    parsed = urlparse(url_base)
    dominio = f"{parsed.scheme}://{parsed.netloc}"

    for tag in soup.find_all(["nav", "header", "ul"], limit=6):
        for a in tag.find_all("a", href=True):
            if any(kw in a["href"].lower() or kw in a.get_text().lower()
                   for kw in _KW_LISTADO):
                full = urljoin(dominio, a["href"])
                if dominio in full:
                    return full

    for a in soup.find_all("a", href=True):
        if any(kw in a["href"].lower() for kw in _KW_LISTADO):
            full = urljoin(dominio, a["href"])
            if dominio in full and len(full) < 150:
                return full

    for path in _PATHS_LISTADO:
        cand = f"{dominio}{path}"
        try:
            r = _WEB_SESSION.head(cand, headers=_HEADERS_WEB,
                                  timeout=5, allow_redirects=True)
            if r.status_code == 200:
                return cand
        except Exception:
            continue
    return None


def detectar_paginacion(html: str, url: str = "") -> str:
    if not html:
        return "desconocido"
    for kw in _SCROLL_KW:
        if kw.lower() in html:
            return "scroll_infinito"
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        if _RE_PAG_URL.search(a["href"]):
            return "url"
    if url and _RE_PAG_URL.search(url):
        return "url"
    if any(kw.lower() in html.lower() for kw in _CLICK_KW):
        return "click"
    return "url"


def estimar_propiedades(html: str) -> Tuple[Optional[int], Optional[int]]:
    if not html:
        return None, None
    texto = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    for m in _RE_TOTAL.findall(texto):
        try:
            n = int(m.replace(".", "").replace(",", ""))
            if 1 <= n <= 100_000:
                return n, max(1, -(-n // PROPS_POR_PAGINA))
        except ValueError:
            continue
    return None, None


# =============================================================================
# FASE 3 — GOOGLE MAPS (Playwright)
# =============================================================================

_RE_CALLE = re.compile(
    r"(?:(?:calle|av\.?|avenida|bv\.?|boulevard|pasaje|pje\.?)\s+)?"
    r"[A-ZÁÉÍÓÚÑ][a-záéíóúñA-Z\s\.]{3,40}\s+\d{2,5}",
    re.IGNORECASE,
)


def buscar_en_google_maps(page, nombre: str, ciudad: str) -> Dict[str, Any]:
    """
    Busca la inmobiliaria en Google Maps y extrae teléfono, dirección y web
    del panel lateral. Reutiliza una sola página de Playwright.
    """
    query = f"{nombre} {ciudad} inmobiliaria"
    url   = f"https://www.google.com/maps/search/{requests.utils.quote(query)}"

    try:
        page.goto(url, timeout=20000, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # Si aparece lista de resultados, clickear el primero
        primer_resultado = page.locator("a[href*='/maps/place/']").first
        if primer_resultado.count() > 0:
            primer_resultado.click()
            page.wait_for_timeout(2000)

        datos: Dict[str, Any] = {}

        # Teléfono — aparece en botones con aria-label que empieza con el número
        for sel in [
            "button[data-item-id^='phone']",
            "button[aria-label*='Teléfono']",
            "a[href^='tel:']",
        ]:
            try:
                el = page.locator(sel).first
                if el.count() > 0:
                    raw = (el.get_attribute("aria-label") or
                           el.get_attribute("href") or
                           el.inner_text())
                    raw = raw.replace("Teléfono:", "").replace("tel:", "").strip()
                    tel = normalizar_telefono(raw)
                    if tel:
                        datos["telefono"]       = tel
                        datos["fuente_telefono"] = "google_maps"
                        break
            except Exception:
                continue

        # Dirección — botón con data-item-id="address"
        for sel in [
            "button[data-item-id='address']",
            "button[aria-label*='Dirección']",
        ]:
            try:
                el = page.locator(sel).first
                if el.count() > 0:
                    addr = el.get_attribute("aria-label") or el.inner_text()
                    addr = addr.replace("Dirección:", "").strip()
                    if addr and len(addr) > 5:
                        datos["direccion"] = addr
                        break
            except Exception:
                continue

        # Web — link externo en el panel
        for sel in [
            "a[data-item-id='authority']",
            "a[aria-label*='Sitio web']",
            "a[href^='http'][data-value='Sitio web']",
        ]:
            try:
                el = page.locator(sel).first
                if el.count() > 0:
                    href = el.get_attribute("href") or ""
                    if es_web_valida(href):
                        datos["web"] = href
                        break
            except Exception:
                continue

        return datos

    except Exception as e:
        log.debug(f"  Maps error '{nombre}': {e}")
        return {}


def buscar_datos_faltantes_lote(registros: List[Dict[str, Any]]) -> List[Tuple[int, Dict]]:
    """
    Abre UN browser de Playwright y recorre la lista de registros buscando
    en Google Maps. Devuelve lista de (id, cambios).
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    resultados: List[Tuple[int, Dict]] = []
    total = len(registros)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled",
                  "--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"),
            locale="es-AR",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        for n, r in enumerate(registros, 1):
            rid    = r["id"]
            nombre = (r.get("nombre") or "").strip()
            ciudad = (r.get("ciudad") or "").strip()

            if not nombre:
                continue

            necesita_tel = not es_telefono_valido(r.get("telefono"))
            necesita_dir = not r.get("direccion")
            necesita_web = not es_web_valida(r.get("web"))

            if not (necesita_tel or necesita_dir or necesita_web):
                continue

            meta = buscar_en_google_maps(page, nombre, ciudad)

            # Filtrar solo lo que falta
            cambios: Dict[str, Any] = {}
            if necesita_tel and meta.get("telefono"):
                cambios["telefono"]        = meta["telefono"]
                cambios["fuente_telefono"] = meta["fuente_telefono"]
            if necesita_dir and meta.get("direccion"):
                cambios["direccion"] = meta["direccion"]
            if necesita_web and meta.get("web"):
                cambios["web"] = meta["web"]

            if cambios:
                resultados.append((rid, cambios))
                log.info(f"  [{n}/{total}] {nombre[:45]} → {list(cambios.keys())}")
            else:
                if n % 50 == 0 or n <= 3:
                    encontrados = len(resultados)
                    log.info(f"  [{n}/{total}] — sin datos ({encontrados} encontrados)")

            page.wait_for_timeout(random.randint(800, 1500))

        browser.close()

    return resultados


# =============================================================================
# CONFIDENCE SCORE
# =============================================================================

def calcular_confidence(r: Dict[str, Any]) -> int:
    score = 0
    if r.get("nombre"):                                                   score += 15
    if limpiar_nombre(r.get("nombre")) == r.get("nombre"):               score += 5
    if es_web_valida(r.get("web")):                                       score += 15
    if r.get("ciudad"):                                                   score += 10
    if r.get("provincia"):                                                score += 10
    if es_telefono_valido(r.get("telefono")):                                  score += 25
    if r.get("direccion"):                                                score += 10
    if r.get("categoria"):                                                score += 5
    if r.get("cms_detectado"):                                            score += 3
    if r.get("url_listado"):                                              score += 2
    return min(score, 100)


def necesita_revision(r: Dict[str, Any]) -> bool:
    nombre = r.get("nombre") or ""
    return bool(
        len(nombre) < 5
        or re.search(r"\d{4,}", nombre)
        or calcular_confidence(r) < 30
        or not r.get("ciudad")
    )


# =============================================================================
# FASE 1 — CORRECCION LOCAL
# =============================================================================

_CATEG_DESARROLLADORA = ["desarrolladora", "desarrollos", "developer",
                         "emprendimiento", "emprendimientos", "fideicomiso"]
_CATEG_CONSTRUCTORA   = ["constructora", "construccion", "construcciones",
                         "ingenieria", "arquitectura", "obra", "obras"]


def correccion_local(registro: Dict[str, Any]) -> Dict[str, Any]:
    cambios: Dict[str, Any] = {}

    # Nombre limpio
    nombre_orig = registro.get("nombre") or ""
    nombre_limpio = limpiar_nombre(nombre_orig)
    if nombre_limpio and nombre_limpio != nombre_orig:
        cambios["nombre_limpio"] = nombre_limpio

    # Web normalizada
    web = normalizar_web(registro.get("web"))
    if web and es_web_valida(web) and web != registro.get("web"):
        cambios["web"] = web

    # Teléfono
    tel_raw = registro.get("telefono")
    tel_norm = normalizar_telefono(tel_raw)
    if tel_norm and tel_norm != tel_raw:
        cambios["telefono"] = tel_norm
        if not registro.get("fuente_telefono"):
            cambios["fuente_telefono"] = "normalizacion"

    # Provincia desde ciudad
    if not registro.get("provincia"):
        prov = provincia_desde_ciudad(registro.get("ciudad"))
        if prov:
            cambios["provincia"] = prov

    # Categoría
    if not registro.get("categoria"):
        nombre_n = quitar_acentos(nombre_orig.lower())
        if any(p in nombre_n for p in _CATEG_DESARROLLADORA):
            cambios["categoria"] = "desarrolladora"
        elif any(p in nombre_n for p in _CATEG_CONSTRUCTORA):
            cambios["categoria"] = "constructora"
        else:
            cambios["categoria"] = "inmobiliaria"

    return cambios


# =============================================================================
# FASE 2 — ENRIQUECIMIENTO WEB
# =============================================================================

def enriquecer_web(registro: Dict[str, Any]) -> Dict[str, Any]:
    """Visita el sitio y extrae todos los metadatos. Thread-safe."""
    web = registro.get("web")
    ahora = datetime.now(timezone.utc).isoformat()

    if not es_web_valida(web):
        return {"sitio_activo": False, "ultimo_chequeo": ahora}

    html, status = _fetch(web)

    if not html or status == 0:
        return {"sitio_activo": False, "tiene_antibot": False,
                "ultimo_chequeo": ahora}

    tiene_antibot = detectar_antibot(html, status)
    resultado: Dict[str, Any] = {
        "sitio_activo": True,
        "tiene_antibot": tiene_antibot,
        "ultimo_chequeo": ahora,
        "cms_detectado": detectar_cms(html, web),
    }

    # Tokko API key
    if resultado["cms_detectado"] == "tokko":
        key = detectar_tokko_key(html)
        if key:
            resultado["tokko_api_key"] = key

    if tiene_antibot:
        return resultado

    dominio = urlparse(web).netloc.replace("www.", "")
    html_contacto = _fetch_contacto(web) if not tiene_antibot else None
    html_combinado = html + (html_contacto or "")

    # Teléfono
    if not es_telefono_valido(registro.get("telefono")):
        tels = extraer_telefonos(html_combinado)
        if tels:
            resultado["telefono"] = tels[0]
            resultado["fuente_telefono"] = "web"

    # Provincia
    if not registro.get("provincia") or registro.get("provincia", "").lower() == "argentina":
        texto = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
        prov = inferir_provincia_texto(texto[:5000])
        if prov:
            resultado["provincia"] = prov

    # URL listado + paginación + propiedades
    url_listado = buscar_url_listado(html, web)
    if url_listado:
        resultado["url_listado"] = url_listado
        html_list, _ = _fetch(url_listado)
        if html_list:
            resultado["tipo_paginacion"] = detectar_paginacion(html_list, url_listado)
            total, pags = estimar_propiedades(html_list)
            if total:
                resultado["total_propiedades"] = total
            if pags:
                resultado["paginas_estimadas"] = pags
    else:
        resultado["tipo_paginacion"] = detectar_paginacion(html, web)
        total, pags = estimar_propiedades(html)
        if total:
            resultado["total_propiedades"] = total
        if pags:
            resultado["paginas_estimadas"] = pags

    return resultado


# =============================================================================
# PIPELINE PRINCIPAL
# =============================================================================

def run():
    if not SUPABASE_URL or not SUPABASE_KEY:
        log.error("Faltan SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY en .env")
        return

    log.info("=" * 65)
    log.info(f"ENRICH PIPELINE v{ENRICH_VERSION} — {TABLA}")
    log.info("=" * 65)

    registros = cargar_registros()
    if not registros:
        log.warning("Sin registros.")
        return

    # Stats iniciales
    total = len(registros)
    con_web     = sum(1 for r in registros if es_web_valida(r.get("web")))
    sin_tel     = sum(1 for r in registros if not es_telefono_valido(r.get("telefono")))
    sin_prov    = sum(1 for r in registros if not r.get("provincia"))
    sin_cms     = sum(1 for r in registros if not r.get("cms_detectado"))
    avg_conf    = sum(calcular_confidence(r) for r in registros) / total
    log.info(f"Total          : {total}")
    log.info(f"Con web válida : {con_web}")
    log.info(f"Sin teléfono   : {sin_tel}")
    log.info(f"Sin provincia  : {sin_prov}")
    log.info(f"Sin CMS        : {sin_cms}")
    log.info(f"Confidence avg : {avg_conf:.1f}/100")
    log.info("-" * 65)

    # Checkpoint
    ultimo_id = cargar_checkpoint()
    if ultimo_id:
        registros = [r for r in registros if r.get("id", 0) > ultimo_id]
        log.info(f"Retomando desde id > {ultimo_id} → {len(registros)} pendientes")

    # -------------------------------------------------------------------------
    # FASE 1 — corrección local (rápida, sin internet)
    # -------------------------------------------------------------------------
    log.info("FASE 1: corrección local…")
    cambios_fase1: List[Tuple[int, Dict]] = []
    for r in registros:
        cambios = correccion_local(r)
        if cambios:
            cambios["enrich_version"] = ENRICH_VERSION
            cambios["confidence_score"] = calcular_confidence({**r, **cambios})
            cambios["needs_manual_review"] = necesita_revision({**r, **cambios})
            cambios_fase1.append((r["id"], cambios))

    log.info(f"  {len(cambios_fase1)} registros con correcciones locales")

    # Guardar fase 1 inmediatamente
    f1_ok = 0
    for j in range(0, len(cambios_fase1), BATCH_SIZE):
        for rid, cambios in cambios_fase1[j:j + BATCH_SIZE]:
            if patch_registro(rid, cambios):
                f1_ok += 1
    log.info(f"  Fase 1 guardada: {f1_ok}/{len(cambios_fase1)}")

    # -------------------------------------------------------------------------
    # FASE 2 — enriquecimiento web (paralelo)
    # -------------------------------------------------------------------------
    con_web_regs = [r for r in registros if es_web_valida(r.get("web"))]
    log.info(f"FASE 2: enriquecimiento web ({len(con_web_regs)} sitios, {MAX_WORKERS} workers)…")

    cambios_fase2: List[Tuple[int, Dict]] = []
    enriquecidos = errores = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futuros = {pool.submit(enriquecer_web, r): r for r in con_web_regs}
        for n, futuro in enumerate(as_completed(futuros), 1):
            r = futuros[futuro]
            rid = r["id"]
            nombre = (r.get("nombre") or f"id={rid}")[:40]
            try:
                meta = futuro.result()
                if meta:
                    # Calcular confidence con datos actualizados
                    meta["enrich_version"]    = ENRICH_VERSION
                    meta["confidence_score"]  = calcular_confidence({**r, **meta})
                    meta["needs_manual_review"] = necesita_revision({**r, **meta})
                    cambios_fase2.append((rid, meta))

                    campos = [k for k, v in meta.items()
                              if v is not None and k not in
                              ("ultimo_chequeo", "enrich_version",
                               "confidence_score", "needs_manual_review")]
                    if campos:
                        enriquecidos += 1
                        log.info(f"  [{n}/{len(con_web_regs)}] {nombre} → {campos}")

            except Exception as e:
                errores += 1
                log.warning(f"  [{n}] {nombre}: {e}")

            guardar_checkpoint(rid)

            # Guardar batch parcial cada 50 completados
            if len(cambios_fase2) % BATCH_SIZE == 0 and cambios_fase2:
                for _rid, _cambios in cambios_fase2[-BATCH_SIZE:]:
                    patch_registro(_rid, _cambios)
                log.info(f"  Lote parcial guardado ({len(cambios_fase2)} acumulados)")

            # Delay respetuoso entre requests
            time.sleep(random.uniform(0.2, 0.6))

    # Guardar todos los de fase 2 (idempotente — patch por id)
    f2_ok = 0
    for rid, cambios in cambios_fase2:
        if patch_registro(rid, cambios):
            f2_ok += 1

    # -------------------------------------------------------------------------
    # FASE 3 — búsqueda web para registros con datos faltantes
    # -------------------------------------------------------------------------
    # Recargar para incluir lo ya enriquecido en fases 1 y 2
    registros_act = cargar_registros()
    incompletos = [
        r for r in registros_act
        if (not es_telefono_valido(r.get("telefono"))
            or not r.get("direccion")
            or not es_web_valida(r.get("web")))
        and (r.get("nombre") or "").strip()
    ]
    log.info(f"FASE 3: búsqueda web para {len(incompletos)} registros incompletos…")

    # Fase 3 corre en el thread principal con un solo browser Playwright
    cambios_fase3 = buscar_datos_faltantes_lote(incompletos)
    f3_enriquecidos = len(cambios_fase3)

    # Agregar metadatos y guardar
    incompletos_idx = {r["id"]: r for r in incompletos}
    f3_ok = 0
    for rid, cambios in cambios_fase3:
        r_orig = incompletos_idx.get(rid, {})
        cambios["enrich_version"]     = ENRICH_VERSION
        cambios["confidence_score"]   = calcular_confidence({**r_orig, **cambios})
        cambios["needs_manual_review"] = necesita_revision({**r_orig, **cambios})
        if patch_registro(rid, cambios):
            f3_ok += 1
    log.info(f"  Fase 3: {f3_enriquecidos} encontrados, {f3_ok} guardados")

    # Limpiar checkpoint
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)

    # Stats finales
    registros_fin = cargar_registros()
    avg_conf_fin  = sum(calcular_confidence(r) for r in registros_fin) / len(registros_fin)
    tokko_n  = sum(1 for r in registros_fin if r.get("cms_detectado") == "tokko")
    activos  = sum(1 for r in registros_fin if r.get("sitio_activo") is True)
    antibot  = sum(1 for r in registros_fin if r.get("tiene_antibot") is True)
    revision = sum(1 for r in registros_fin if r.get("needs_manual_review") is True)

    log.info("=" * 65)
    log.info(f"Fase 1 actualizados     : {f1_ok}")
    log.info(f"Fase 2 enriquecidos     : {enriquecidos}  |  guardados: {f2_ok}")
    log.info(f"Fase 3 encontrados      : {f3_enriquecidos}  |  guardados: {f3_ok}")
    log.info(f"Errores web             : {errores}")
    log.info(f"Confidence promedio     : {avg_conf:.1f} → {avg_conf_fin:.1f}/100")
    log.info(f"Sitios activos          : {activos}")
    log.info(f"Con antibot             : {antibot}")
    log.info(f"Tokko Broker            : {tokko_n}")
    log.info(f"Necesitan revisión      : {revision}")
    log.info("=" * 65)


if __name__ == "__main__":
    run()
