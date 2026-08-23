#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Detecta la plataforma tecnica de un sitio inmobiliario.

El objetivo no es catalogar por catalogar: es evitar escribir 1.992 scrapers.
Si doscientas inmobiliarias corren sobre Tokko, un conector cubre las
doscientas. Lo que se busca en cada sitio es, en este orden:

  1. una API o feed que ya devuelva las propiedades estructuradas;
  2. un sitemap de propiedades;
  3. HTML servido por el servidor, parseable sin navegador;
  4. y recien al final, algo que exija ejecutar JavaScript.

Cada nivel es mucho mas barato de scrapear que el siguiente, asi que la
deteccion prioriza encontrar el mas barato disponible, no el mas evidente.

Todo sale del HTML publico ya descargado. No usa buscadores, no consume APIs
pagas y no descarga propiedades.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Iterable

DETECTOR_VERSION = "platform_detector_v2"


def _cargar_fingerprint_wasi():
    """El fingerprint de Wasi vive aparte porque combina senales, no es un regex.

    Se carga defensivamente: a este modulo lo cargan por ruta varios scripts,
    sin la raiz del repo en sys.path, y una falla de import aca dejaria sin
    clasificar el universo entero y no solo Wasi.
    """
    try:
        from scripts.wasi_fingerprint import fingerprint
        return fingerprint
    except ImportError:
        pass
    ruta = Path(__file__).resolve().parent / "wasi_fingerprint.py"
    if not ruta.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location("wasi_fingerprint", ruta)
        mod = importlib.util.module_from_spec(spec)
        sys.modules.setdefault("wasi_fingerprint", mod)
        spec.loader.exec_module(mod)
        return mod.fingerprint
    except Exception:
        return None


_fingerprint_wasi = _cargar_fingerprint_wasi()

# Estrategias, de mas barata a mas cara.
API_DIRECT = "API_DIRECT"
WORDPRESS_API = "WORDPRESS_API"
TOKKO_CONNECTOR = "TOKKO_CONNECTOR"
JSON_EMBEDDED = "JSON_EMBEDDED"
SITEMAP = "SITEMAP"
SSR_HTML = "SSR_HTML"
JS_BROWSER = "JS_BROWSER"
CUSTOM_CONNECTOR = "CUSTOM_CONNECTOR"
MANUAL_REVIEW = "MANUAL_REVIEW"

# Plataformas inmobiliarias del mercado argentino. Son las que mas rinden:
# una sola integracion cubre todos sus clientes.
PLATAFORMAS_INMO = {
    "TOKKO": (r"tokkobroker|tokko-?broker|tokkocdn|api\.tokkobroker\.com", TOKKO_CONNECTOR),
    "MEDIACORE": (r"mediacore\.|mediacorecdn|medialabs", API_DIRECT),
    "SIVAL": (r"sival\.com\.ar|sivalweb", CUSTOM_CONNECTOR),
    "SIINCO": (r"siinco\.com|siincoweb", CUSTOM_CONNECTOR),
    "INMOUP": (r"inmoup\.com\.ar", API_DIRECT),
    "REDINMOBILIARIA": (r"redinmobiliaria\.com", CUSTOM_CONNECTOR),
    # WASI no esta aca: se resuelve con `_fingerprint_wasi`, que combina
    # senales. El regex `wasi\.co|wasiapp` tomaba por cliente a cualquier
    # pagina que apenas enlazara la plataforma, y se le escapaba cualquier
    # sitio que borrara la marca -que es justo lo que hace un white-label-.
    "EASYBROKER": (r"easybroker\.com", API_DIRECT),
    "PROPPIT": (r"proppit\.com", CUSTOM_CONNECTOR),
    "INMOBIQ": (r"inmobiq\.com", CUSTOM_CONNECTOR),
    "SOFTINMO": (r"softinmo|soft-?inmobiliario", CUSTOM_CONNECTOR),
    "KEYSOFT": (r"keysoft\.com\.ar", CUSTOM_CONNECTOR),
}

# CMS y frameworks genericos.
GENERICAS = {
    "WORDPRESS": (r"wp-content|wp-includes|wp-json|/wp-admin", WORDPRESS_API),
    "WIX": (r"wix\.com|wixstatic|_wixCssImports|wixsite", JS_BROWSER),
    "WEBFLOW": (r"webflow\.(com|io)|data-wf-page", SSR_HTML),
    "SQUARESPACE": (r"squarespace\.com|static1\.squarespace", SSR_HTML),
    "NEXTJS": (r"__NEXT_DATA__|/_next/static", JSON_EMBEDDED),
    "NUXT": (r"__NUXT__|/_nuxt/", JSON_EMBEDDED),
    "ANGULAR": (r"ng-version=|angular\.min\.js|_nghost", JS_BROWSER),
    "REACT_SPA": (r"data-reactroot|react-dom|__REACT_DEVTOOLS", JS_BROWSER),
    "VUE": (r"data-v-[0-9a-f]{8}|vue\.min\.js", JS_BROWSER),
    "LARAVEL": (r"laravel_session|/vendor/laravel|csrf-token", SSR_HTML),
    "DJANGO": (r"csrfmiddlewaretoken|__admin_media_prefix__", SSR_HTML),
    "JOOMLA": (r"/media/jui/|joomla", SSR_HTML),
    "DRUPAL": (r"drupal\.settings|/sites/default/files", SSR_HTML),
}

# Rutas que suelen listar propiedades. Sirven para confirmar que el sitio
# publica inventario y no es solo institucional.
#
# El separador de adelante admite la barra de una ruta absoluta pero tambien la
# comilla de un href relativo: muchos sitios PHP escriben href="propiedades.php"
# sin barra, y exigirla los volvia invisibles para el detector. Pedir ALGUN
# separador sigue impidiendo que "amilicipropiedades.com" cuente como listado.
RUTAS_LISTADO = re.compile(
    r"""[/"'=?&.](propiedades|propiedad|inmuebles|inmueble|emprendimientos|"""
    r"""fichas?|listado|listados|resultados|venta|ventas|alquiler|alquileres|"""
    r"""buscar|busqueda|search|properties|operacion|destacados)\b""", re.I)

# Endpoints de datos visibles en el propio HTML.
ENDPOINTS_JSON = re.compile(
    r"[\"'](/(?:api|wp-json|graphql|rest|ajax|data)/[^\"'\s]{0,120})[\"']", re.I)


def _texto(sitio: dict) -> str:
    return " ".join(str(sitio.get(k) or "") for k in ("html", "texto", "titulo"))


def detectar_plataforma(sitio: dict) -> tuple[str | None, str | None, float]:
    """Devuelve (plataforma, estrategia, confianza).

    Las plataformas inmobiliarias se buscan ANTES que los CMS genericos: un
    Tokko montado sobre WordPress se scrapea por Tokko, no por WordPress, y
    detectar el CMS primero mandaria al conector equivocado.

    Wasi va primero de todo, y por la misma razon llevada un paso mas: su
    white-label corre sobre Laravel, asi que el detector generico lo etiqueta
    LARAVEL -que es el framework de abajo, no la forma en que publica- y lo
    manda a parsear HTML a ciegas teniendo un sitemap completo al lado.
    """
    blob = _texto(sitio)
    if not blob.strip():
        return None, None, 0.0

    if _fingerprint_wasi is not None:
        fp = _fingerprint_wasi(blob, sitio.get("url") or "")
        if fp["es_wasi"]:
            # SITEMAP y no API_DIRECT: Wasi tiene API, pero pide id_company y
            # wasi_token, que el sitio publico no expone. Prometer una API que
            # despues pide credenciales manda al connector a una puerta cerrada.
            return "WASI", SITEMAP, 0.95 if fp["confianza"] == "alta" else 0.8

    for nombre, (patron, estrategia) in PLATAFORMAS_INMO.items():
        if re.search(patron, blob, re.I):
            return nombre, estrategia, 0.9

    for nombre, (patron, estrategia) in GENERICAS.items():
        if re.search(patron, blob, re.I):
            return nombre, estrategia, 0.75

    m = re.search(r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']([^"\']{2,60})',
                  blob, re.I)
    if m:
        return m.group(1).strip().upper()[:30], SSR_HTML, 0.5

    return None, None, 0.0


def detectar_api(sitio: dict) -> list[str]:
    """Endpoints de datos que el propio HTML deja a la vista."""
    blob = _texto(sitio)
    vistos, out = set(), []
    for m in ENDPOINTS_JSON.finditer(blob):
        ruta = m.group(1)
        if ruta in vistos:
            continue
        vistos.add(ruta)
        out.append(ruta)
        if len(out) >= 8:
            break
    return out


def tiene_json_embebido(sitio: dict) -> bool:
    """JSON-LD o estado embebido: propiedades sin ejecutar JavaScript."""
    blob = _texto(sitio)
    return bool(re.search(r'application/ld\+json|__NEXT_DATA__|__NUXT__|'
                          r'window\.__INITIAL_STATE__|window\.__DATA__', blob, re.I))


def tiene_listados(sitio: dict) -> bool:
    return bool(RUTAS_LISTADO.search(_texto(sitio)))


def requiere_js(sitio: dict, plataforma: str | None) -> bool:
    """El HTML servido no trae inventario y la plataforma es de las que pintan
    en el cliente."""
    if plataforma in ("WIX", "ANGULAR", "REACT_SPA", "VUE"):
        return not tiene_json_embebido(sitio)
    texto = str(sitio.get("texto") or "")
    # Muy poco texto servido y muchos scripts: lo pinta el navegador.
    return len(texto) < 400 and str(sitio.get("html") or "").count("<script") > 8


def elegir_estrategia(sitio: dict, plataforma: str | None,
                      estrategia_plataforma: str | None,
                      sitemap_propiedades: bool) -> str:
    """La mas barata que el sitio permita.

    El orden importa mas que la deteccion: una API estructurada ahorra un parser
    entero, y un sitemap ahorra recorrer el sitio a ciegas.
    """
    if estrategia_plataforma in (TOKKO_CONNECTOR, API_DIRECT, WORDPRESS_API):
        return estrategia_plataforma
    if detectar_api(sitio):
        return API_DIRECT
    if tiene_json_embebido(sitio):
        return JSON_EMBEDDED
    if sitemap_propiedades:
        return SITEMAP
    if requiere_js(sitio, plataforma):
        return JS_BROWSER
    if tiene_listados(sitio):
        return SSR_HTML
    # Responde y es un sitio real, pero no se le vio inventario en la home.
    # Eso no lo vuelve imposible: lo vuelve algo que hay que mirar a mano.
    return MANUAL_REVIEW


# Prioridad: cuantas fuentes cubre un conector, y que tan barato es construirlo.
PRIORIDAD_POR_ESTRATEGIA = {
    TOKKO_CONNECTOR: 0, API_DIRECT: 0, WORDPRESS_API: 0,
    JSON_EMBEDDED: 1, SITEMAP: 1,
    SSR_HTML: 2, CUSTOM_CONNECTOR: 2,
    JS_BROWSER: 3, MANUAL_REVIEW: 3,
}


def prioridad(estrategia: str, fuentes_en_grupo: int) -> str:
    """Un grupo grande con estrategia barata es lo primero que conviene
    construir; uno chico que exige navegador es lo ultimo."""
    base = PRIORIDAD_POR_ESTRATEGIA.get(estrategia, 3)
    if fuentes_en_grupo >= 100 and base <= 1:
        base = 0
    elif fuentes_en_grupo < 5 and base < 3:
        base += 1
    return f"P{min(base, 3)}"


def clasificar(sitio: dict, sitemap_propiedades: bool = False) -> dict:
    plataforma, estrategia_plat, conf = detectar_plataforma(sitio)
    apis = detectar_api(sitio)
    estrategia = elegir_estrategia(sitio, plataforma, estrategia_plat, sitemap_propiedades)
    return {
        "detected_platform": plataforma or "UNKNOWN",
        "platform_confidence": conf,
        "detected_framework": plataforma,
        "detected_api": apis,
        "sitemap": sitemap_propiedades,
        "requires_js": requiere_js(sitio, plataforma),
        "has_listings": tiene_listados(sitio),
        "json_embedded": tiene_json_embebido(sitio),
        "strategy": estrategia,
        "detector_version": DETECTOR_VERSION,
    }
