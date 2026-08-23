#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Reconocer un sitio Wasi sin depender del dominio ni de la marca visible.

Wasi es una plataforma inmobiliaria white-label: la inmobiliaria pone su
dominio, sus colores y su logo, y abajo corre el mismo software. Por eso la
deteccion no puede mirar el hostname -"inmobiliariaX.com.ar" no dice nada- ni
confiar en que la palabra "wasi" aparezca a la vista.

Tampoco alcanza con buscar "wasi" en el HTML. Eso da falsos positivos con
cualquier pagina que enlace a la plataforma y falsos negativos con cualquier
sitio que borre la marca. Se combinan senales de distinto peso:

  FUERTE  una sola confirma: solo la sirve la plataforma
  MEDIA   dos confirman: rasgos del producto, imitables por separado
  DEBIL   nunca alcanzan solas: compatibles con muchos otros sitios

La senal que sostiene el caso dificil es `bundle_white_label`: Wasi sirve desde
el dominio de la inmobiliaria un juego de scripts -/js/v1/<plan>/global.min.js
mas /js/app.js, /js/lazyload.min.js, /js/webp.js- todos con el MISMO numero de
build en el query string. No contiene la palabra "wasi" en ninguna parte, asi
que sobrevive a que la inmobiliaria borre la marca, y el build compartido entre
sitios distintos es lo que prueba que son el mismo producto.

Modulo puro: no pide nada a la red. Recibe el HTML ya descargado.
"""
from __future__ import annotations

import re
import urllib.parse

FINGERPRINT_VERSION = "wasi_fingerprint_v1"

WASI = "WASI"

# --------------------------------------------------------------------------
# Senales
# --------------------------------------------------------------------------
# Una sola alcanza: nada de esto lo escribe la inmobiliaria, lo sirve Wasi.
FUERTES: dict[str, tuple[str, str]] = {
    "meta_author_wasi": (
        r"<meta[^>]*name=[\"']author[\"'][^>]*content=[\"'][^\"']*wasi\.co[^\"']*[\"']",
        "la plataforma se firma en <meta name=author>"),
    "meta_designer_wasi": (
        r"<meta[^>]*name=[\"']designer[\"'][^>]*content=[\"'][^\"']*wasi\.co[^\"']*[\"']",
        "la plataforma se firma en <meta name=Designer>"),
    # El CDN de fotos, con su ruta: un enlace suelto a wasi.co no cuenta.
    "cdn_imagenes": (
        r"https?://images?\.wasi\.co/(?:inmuebles|empresas|usuarios)/",
        "las fotos de las propiedades salen del CDN de Wasi"),
    # image.wasi.co/<base64> es el manipulador de imagenes de la plataforma.
    "cdn_manipulador": (
        r"https?://image\.wasi\.co/eyJ",
        "las fotos pasan por el manipulador de imagenes de Wasi"),
}

# El juego de scripts white-label. Se evalua aparte porque no es un regex
# suelto: exige que global.min.js y sus hermanos compartan numero de build.
RE_GLOBAL = re.compile(
    r"/js/v1/([a-z0-9]{2,12})/global\.min\.js\?v(\d{6,14})", re.I)
RE_HERMANO = re.compile(
    r"/js/(?:app|lazyload\.min|webp)\.js\?v(\d{6,14})", re.I)

# Dos alcanzan: son rasgos del producto, y cualquiera por separado podria
# aparecer en otro sitio.
MEDIAS: dict[str, tuple[str, str]] = {
    "param_lax_business_type": (
        r"[?&;]lax_business_type=",
        "el buscador usa el parametro lax_business_type"),
    "param_id_property_type": (
        r"[?&;]id_property_type=\d+",
        "los filtros usan id_property_type"),
    "paginas_main_htm": (
        r"main-[a-z0-9\-]{3,40}\.htm\b",
        "las paginas institucionales son main-<algo>.htm"),
    "clase_blq_precio": (
        r"class=[\"'][^\"']*\bblq_precio\b",
        "el bloque de precio es .blq_precio"),
    "clases_tipo_negocio": (
        r"class=[\"'][^\"']*\btype-(?:rent|sale|transfer|temporary_rent)\b",
        "el tipo de operacion se marca con .type-rent / .type-sale"),
    "globales_locale": (
        r"\blang_locale\s*=(?s:.){0,400}?\biso_country\s*=",
        "declara las globales lang_locale e iso_country"),
    "powered_by_wasi": (
        r"powered\s*by\s*:?\s*(?:<[^>]+>\s*)*[^<]{0,20}wasi\.co",
        "el pie declara la plataforma"),
}

# Nunca alcanzan solas.
DEBILES: dict[str, tuple[str, str]] = {
    "texto_wasi": (r"\bwasi\b", "aparece la palabra wasi"),
    "ficha_slug_id": (r"href=[\"'][^\"']*/[a-z0-9\-]{6,120}/\d{5,12}[\"']",
                      "hay rutas <slug>/<id numerico>"),
    "ruta_busqueda_s": (r"href=[\"'][^\"']*/s/[a-z0-9\-]{2,60}[\"'/?]",
                        "el listado cuelga de /s/<algo>"),
    "bootstrap_select": (r"bootstrap-select@1\.14\.0-beta3",
                         "usa la misma version de bootstrap-select"),
}

# Wasi hospeda sitios propios bajo inmo.co. Es evidencia real, pero es del
# hostname: se usa como senal MEDIA, no como atajo, para que la deteccion no
# dependa del dominio.
RE_HOST_WASI = re.compile(r"(?:^|\.)inmo\.co$", re.I)

_DESC_EXTRA = {
    "bundle_white_label": "sirve el juego de scripts white-label de Wasi",
    "host_wasi": "esta hospedado en inmo.co, el dominio propio de Wasi",
}


def _busca(html: str, tabla: dict[str, tuple[str, str]]) -> list[str]:
    return [k for k, (patron, _) in tabla.items()
            if re.search(patron, html, re.I)]


def _describir(clave: str) -> str:
    for tabla in (FUERTES, MEDIAS, DEBILES):
        if clave in tabla:
            return tabla[clave][1]
    return _DESC_EXTRA.get(clave, clave)


def bundle_white_label(html: str) -> dict | None:
    """El juego de scripts que Wasi sirve desde el dominio de la inmobiliaria.

    Exige que global.min.js y al menos un hermano compartan build. Un
    /js/app.js suelto lo tiene medio internet; que los cuatro archivos lleven
    el mismo `?v<build>` y que el plan contratado vaya en la ruta es del
    producto, y no menciona la marca en ningun lado.
    """
    m = RE_GLOBAL.search(html or "")
    if not m:
        return None
    plan, build = m.group(1), m.group(2)
    if build not in RE_HERMANO.findall(html or ""):
        return None
    return {"plan": plan, "build": build}


def host_de(url: str) -> str:
    return urllib.parse.urlparse(url or "").netloc.split(":")[0].lower()


def fingerprint(html: str, url: str = "") -> dict:
    """Decide si el HTML servido corresponde a un sitio Wasi.

    Devuelve siempre las senales encontradas, tambien cuando da negativo: un
    negativo sin evidencia no se puede auditar despues.
    """
    html = html or ""
    fuertes = _busca(html, FUERTES)
    medias = _busca(html, MEDIAS)
    debiles = _busca(html, DEBILES)

    bundle = bundle_white_label(html)
    if bundle:
        fuertes.append("bundle_white_label")
    if RE_HOST_WASI.search(host_de(url)):
        medias.append("host_wasi")

    if fuertes:
        es, confianza = True, "alta"
        motivo = "senal fuerte: " + _describir(sorted(fuertes)[0])
    elif len(medias) >= 2:
        es, confianza = True, "media"
        motivo = ("senales medias combinadas: "
                  + "; ".join(_describir(k) for k in sorted(medias)[:3]))
    elif medias:
        es, confianza = False, "insuficiente"
        motivo = "una sola senal media no alcanza: " + _describir(medias[0])
    elif debiles:
        es, confianza = False, "insuficiente"
        motivo = ("solo senales debiles: "
                  + "; ".join(_describir(k) for k in sorted(debiles)))
    else:
        es, confianza = False, "ninguna"
        motivo = "no hay ninguna senal de Wasi"

    return {
        "es_wasi": es,
        "confianza": confianza,
        "motivo": motivo,
        "senales_fuertes": sorted(fuertes),
        "senales_medias": sorted(medias),
        "senales_debiles": sorted(debiles),
        "plan": (bundle or {}).get("plan"),
        "build": (bundle or {}).get("build"),
        "fingerprint_version": FINGERPRINT_VERSION,
    }


# --------------------------------------------------------------------------
# Rutas del producto: sirven para enumerar, no para detectar
# --------------------------------------------------------------------------
# La ficha vive en la raiz: /<slug>/<id>. Ese id es el mismo que la ficha
# muestra como "Codigo", asi que es un identificador estable de la fuente y no
# hay que fabricar ninguno.
RE_FICHA_WASI = re.compile(r"^/([a-z0-9\-]{4,140})/(\d{5,12})/?$", re.I)


# El menu declara cuantas propiedades hay de cada tipo y operacion:
#   <a class="dropdown-item" href=".../s/casa/ventas?id_property_type=1&business_type[0]=for_sale">Casa (63)</a>
RE_ANCLA_MENU = re.compile(
    r"href=[\"']([^\"']*id_property_type=\d+[^\"']*)[\"'][^>]*>\s*([^<]{1,80}?)"
    r"\((\d{1,6})\)\s*<", re.I)


def inventario_declarado(html: str) -> dict:
    """Cuantas propiedades dice tener el sitio, segun su propio menu.

    Se cuenta por ENLACE, no por etiqueta. El mismo filtro aparece dos veces en
    la pagina con dos textos distintos -"Chalet (15)" en el desplegable y
    "Chalet En Venta (15)" en el listado lateral-, asi que contar etiquetas
    duplicaba el inventario: cuatro sitios declaraban exactamente el doble de
    lo que su sitemap enumeraba, y el 0,5 clavado era el que delataba el error,
    no una falla del sitemap.

    Sigue siendo una aproximacion: el sitemap es la enumeracion de referencia.
    """
    por_operacion: dict[str, int] = {}
    vistos: set[tuple[str, str]] = set()
    for href, _etiqueta, n in RE_ANCLA_MENU.findall(html or ""):
        h = href.replace("&amp;", "&")
        q = urllib.parse.parse_qs(urllib.parse.urlparse(h).query)
        tipo = (q.get("id_property_type") or [""])[0]
        operacion = (q.get("business_type[0]") or q.get("business_type%5B0%5D")
                     or [""])[0].lower()
        if not tipo or not operacion or (operacion, tipo) in vistos:
            continue
        vistos.add((operacion, tipo))
        por_operacion[operacion] = por_operacion.get(operacion, 0) + int(n)
    return {"por_operacion": por_operacion,
            "total": sum(por_operacion.values()) or None}


def es_ficha(url_o_ruta: str) -> bool:
    ruta = urllib.parse.urlparse(url_o_ruta or "").path or (url_o_ruta or "")
    return bool(RE_FICHA_WASI.match(ruta))


def id_de_ficha(url_o_ruta: str) -> str | None:
    ruta = urllib.parse.urlparse(url_o_ruta or "").path or (url_o_ruta or "")
    m = RE_FICHA_WASI.match(ruta)
    return m.group(2) if m else None
