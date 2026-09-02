#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Connector generico para sitios propios — implementacion numero cuatro.

Las 826 fuentes que el mapa no pudo atribuir a ninguna plataforma no son 826
problemas distintos. Miradas por como publican, se agrupan:

  260 tienen sitemap · 160 traen JSON embebido · 445 sirven HTML con listados

Escribir un scraper por inmobiliaria seria absurdo. Este connector no conoce
ningun sitio en particular: usa lo que la web abierta estandarizo hace anos
—sitemaps y schema.org— y solo cae al HTML cuando no hay nada mejor.

  1. SITEMAP: el indice lista las fichas y evita recorrer el sitio a ciegas.
  2. JSON-LD: schema.org publica precio, moneda, superficie y ubicacion ya
     tipados. Cuando esta, es mejor que cualquier heuristica.
  3. Meta og: titulo e imagen con formato garantizado.
  4. Texto con etiquetas: ultimo recurso, y explicitamente conservador.

Un sitio que no ofrece ninguna de las cuatro cosas se reporta como no
soportado. Preferimos decir "no la supimos leer" antes que devolver cero y que
parezca que la inmobiliaria no publica.
"""
from __future__ import annotations

import json
import re
import unicodedata
import urllib.parse
from html import unescape
from typing import Any, Iterator

from .coherencia import NO_ES_FOTO, revisar
from .formularios import bajar_formulario
from .base import (Bloqueado, Connector, ErrorPermanente, ErrorTransitorio,
                   Fuente, PropiedadNormalizada, a_numero, detectar_moneda,
                   detectar_operacion, detectar_tipo, identidad_de_imagen,
                   imagenes_de_fichas_vecinas, limpiar,
                   sin_fichas_vecinas)

# Los atributos numericos que una ficha suele tabular. Sirven para decidir si
# la pagina los presenta como ``Rotulo N`` o como prosa.
ETIQUETAS_ATRIBUTO = (r"ambientes?|dormitorios?|habitaciones?|ba[nñ]os?"
                      r"|cocheras?|toilettes?")

SITEMAPS = ("/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml",
            "/sitemap-index.xml", "/sitemapindex.xml")

# Una URL de ficha lleva la seccion Y algo que la identifica: un id numerico o
# un slug largo. Sin ese segundo requisito, "/propiedades/" -la pagina de
# listado- entraria como si fuera una propiedad.
# `ad` es "aviso", y lo usa una plataforma entera: 97 inmobiliarias publican en
# /ad/<slug> y las 97 figuraban como "no publica inventario" solo porque esa
# seccion no estaba en la lista. El prefijo de seccion mantiene el patron
# acotado: no se afloja nada para las demas.
RE_FICHA = re.compile(
    r"/(?:propiedad(?:es)?|inmueble[s]?|emprendimiento[s]?|ficha[s]?|"
    r"propert(?:y|ies)|listing[s]?|aviso[s]?|anuncio[s]?|ad|venta|alquiler)/"
    r"(?:[^/?#]*?(?:\d{3,}|[a-z0-9]+(?:-[a-z0-9]+){2,}))/?$", re.I)

# Muchos frontends propios cuelgan la ficha de la RAIZ, sin seccion:
# /8471-venta-casa-3-ambientes-en-adrogue. Ni el patron de Tokko ni el de arriba
# la ven. Para que un id suelto en la raiz no arrastre cualquier pagina, se
# exige que el slug diga de que se trata.
RE_FICHA_RAIZ = re.compile(
    r"^/(\d{3,})-[a-z0-9-]*(venta|alquiler|casa|departamento|depto|terreno|"
    r"lote|ph|local|oficina|galpon|campo|cochera|quinta|duplex|chalet)"
    r"[a-z0-9-]*/?$", re.I)

# Rutas de orden del LISTADO que por tener varios guiones parecen slugs de
# ficha. En BuscadorProp eran dos propiedades fantasma por inmobiliaria.
RE_NO_FICHA = re.compile(
    r"/propiedades/(?:destacadas|mas-nuevas|mas-viejas|"
    r"precio-(?:mayor|menor)-a-(?:mayor|menor))/?$", re.I)

# Traduccion de la FORMA descubierta de una fuente a un patron de ruta.
# La forma la produjo el descubrimiento (/p-1749_departamento -> /<slug-con-id>)
# y la verificacion bajo tres fichas de ese sitio para confirmar que esa forma
# publica propiedades y no notas. Traducirla aca deja el patron global intacto:
# se habilita la forma de ESA fuente, no de las 2.258 restantes.
FORMA_A_REGEX = {
    "<num>": r"\d+",
    "<slug>": r"[a-z0-9]+(?:-[a-z0-9]+){2,}",
    "<slug-con-id>": r"[a-z0-9][a-z0-9_.-]*\d{3,}[a-z0-9_.-]*",
    "<otro>": r"[^/]+",
}


def patron_de_forma(forma: str) -> "re.Pattern | None":
    """El patron de ruta de una forma verificada. None si no se puede traducir."""
    if not forma or not forma.startswith("/"):
        return None
    tramos = [t for t in forma.split("/") if t]
    if not tramos:
        return None
    partes = []
    for t in tramos:
        if t in FORMA_A_REGEX:
            partes.append(FORMA_A_REGEX[t])
        elif re.fullmatch(r"[a-z0-9-]{1,24}", t, re.I):
            partes.append(re.escape(t.lower()))
        else:
            return None            # forma que no se entiende: no se habilita
    return re.compile("^/" + "/".join(partes) + "/?$", re.I)


RE_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
RE_LD = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S | re.I)
RE_IMG = re.compile(r'https?://[^\s"\'<>]+?\.(?:jpe?g|png|webp)', re.I)
# El menos NO es opcional. Argentina esta entera en el hemisferio sur y
# oeste, y con el signo opcional el patron de WordPress tomo pares como
# "50.774, 50.7708" y ubico 752 propiedades fuera del pais.
RE_COORD = re.compile(r'"?(?:latitude|lat)"?\s*[:=]\s*"?(-[23456]\d\.\d{3,})"?'
                      r'.{0,80}?"?(?:longitude|lng|lon)"?\s*[:=]\s*"?(-[567]\d\.\d{3,})"?',
                      re.S | re.I)

# Evidencia de que una pagina publica UNA propiedad. Se usa solo sobre las urls
# que entraron por la forma verificada de su fuente: la forma dice donde mirar,
# la pagina dice si hay una propiedad. Una nota del blog habla de venta y de
# dormitorios, pero no suele traer un precio con moneda al lado.
RE_OPERACION_TXT = re.compile(r"\b(en venta|en alquiler|venta|alquiler|se vende|"
                              r"se alquila)\b", re.I)
# Lo que describe un inmueble y no una nota. Se piden DOS distintos:
# "superficie" sola aparece en cualquier texto sobre el mercado.
RE_ATRIBUTOS_TXT = re.compile(r"\b(dormitorio|ambiente|ba[nñ]o|superficie|"
                              r"m2|m²|cubierta|cochera|antig[uü]edad)", re.I)
RE_EDITORIAL = re.compile(r'"@type"\s*:\s*"?(Article|NewsArticle|BlogPosting)|'
                          r'property="og:type"\s+content="article"', re.I)
FOTOS_MINIMAS = 3


# `src` con ruta relativa, y los atributos con los que los sitios difieren la
# carga. La url se resuelve contra la de la ficha.
RE_IMG_ATRIBUTO = re.compile(
    r"<img[^>]{0,400}?\s(?:data-src|data-lazy-src|data-original|src)="
    r"\"([^\"]{4,400})\"", re.I)
RE_EXTENSION = re.compile(r"\.(?:jpe?g|png|webp|avif)(?:$|[?#])", re.I)
RE_WP_IMAGE_SIZE = re.compile(
    r"-(\d{2,4})x(\d{2,4})(?=\.[a-z]{3,4}(?:$|[?#]))", re.I)
# El filtro vive en el modulo compartido: la extraccion y la correccion de lo
# ya extraido tienen que descartar exactamente lo mismo.
RE_NO_ES_FOTO = NO_ES_FOTO

MAX_SITEMAPS = 25
MAX_FICHAS = 4000


def _sin_variantes_wordpress(urls: list[str]) -> list[str]:
    """Conserva una sola version de cada imagen generada por WordPress."""
    best: dict[str, tuple[float, str]] = {}
    order: list[str] = []
    for url in urls:
        base = RE_WP_IMAGE_SIZE.sub("", url)
        match = RE_WP_IMAGE_SIZE.search(url)
        priority = (float("inf") if match is None
                    else int(match.group(1)) * int(match.group(2)))
        if base not in best:
            order.append(base)
            best[base] = (priority, url)
        elif priority > best[base][0]:
            best[base] = (priority, url)
    return [best[base][1] for base in order]


def _imagenes_galeria_wordpress(html: str, source_url: str) -> list[str]:
    """Fotos enlazadas por la galeria de una ficha editorial WordPress.

    Las cámaras y teléfonos suelen nombrar los archivos ``WhatsApp-Image``.
    El filtro genérico descarta correctamente iconos de WhatsApp, pero aplicado
    al nombre de una foto real también la perdería. Dentro de una galería Divi,
    el enlace a la imagen completa es evidencia estructural suficiente; aun
    así se excluyen nombres inequívocos de plantilla.
    """
    if not re.search(r"\bet_pb_gallery\b", html or "", re.I):
        return []
    images: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r'<a\b[^>]{0,500}\bhref=["\']([^"\']+)["\']',
                             html or "", re.I):
        url = urllib.parse.urljoin(source_url, unescape(match.group(1)))
        if not RE_EXTENSION.search(url):
            continue
        if re.search(r"/(?:logo|header-(?:venta|alquiler)|favicon|icon[-_.])", url,
                     re.I):
            continue
        canonical = identidad_de_imagen(url)
        if canonical not in seen:
            seen.add(canonical)
            images.append(canonical)
    return _sin_variantes_wordpress(images)


def _texto(html: str) -> str:
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html or "", flags=re.S | re.I)
    t = unescape(t)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", unescape(t).replace("\xa0", " "))


def cuerpo_principal(html: str) -> str:
    """Parte de la ficha anterior a relacionadas/footer.

    Los contadores y atributos del vecino no describen esta propiedad. Leer el
    documento entero produjo dormitorios>ambientes que el guardián debió
    descartar; el dato nunca debió entrar al parser.
    """
    return re.split(
        r"id=[\"'](?:relacionadas|bottom)[\"']|<footer\b|"
        r"<div[^>]+class=[\"'][^\"']*titulo_prod_int[^\"']*[\"'][^>]*>\s*"
        r"Otras\s+Propiedades\s*</div>",
                    html or "", maxsplit=1, flags=re.I)[0]


def sin_filtros_catalogo(html: str) -> str:
    """Quita opciones del buscador embebidas junto a la ficha legacy."""
    return re.sub(
        r"<label[^>]+name=[\"']search_filter[^\"']*[\"'][^>]*>.*?</label>",
        " ", html or "", flags=re.I | re.S)


def normalizar_texto_campos(texto: str) -> str:
    """Repara etiquetas visibles rotas por decodificacion legacy.

    Algunos portales sirven ``Ba�os``/``Ba�o`` aunque el resto del HTML
    sea utilizable. La misma normalizacion se comparte con el auditor para que
    una senal de fuente y su extraccion nunca usen alfabetos distintos.
    """
    return (texto or "").replace("Ba�os", "Baños").replace("ba�os", "baños") \
        .replace("Ba�o", "Baño").replace("ba�o", "baño")


def _aplanar_ld(dato: Any) -> Iterator[dict]:
    """schema.org se anida de formas distintas segun quien lo genere."""
    if isinstance(dato, list):
        for x in dato:
            yield from _aplanar_ld(x)
    elif isinstance(dato, dict):
        yield dato
        for clave in ("@graph", "itemListElement", "mainEntity", "offers", "item"):
            if clave in dato:
                yield from _aplanar_ld(dato[clave])


class GenericoConnector(Connector):
    nombre = "generico"
    variantes_soportadas = (
        "SITEMAP", "LISTADO_HTML", "WORDPRESS_CATEGORY_CATALOG",
        "MAPAPROP_HTML")

    @staticmethod
    def _patron_de(fuente: Fuente) -> "re.Pattern | None":
        return patron_de_forma((fuente.extra or {}).get("patron_ficha") or "")

    @staticmethod
    def _patron_raiz_local(html: str) -> "re.Pattern | None":
        """Forma /p-<id>_<slug>, habilitada solo para la fuente observada.

        Tres enlaces distintos son la evidencia minima. Cada detalle entra con
        por_forma=True y el guardian lo valida; no se afloja el patron global.
        """
        rutas = {"/" + urllib.parse.urlparse(m.group(1)).path.lstrip("/")
                 for m in re.finditer(r'href="([^"]{4,300})"', html or "", re.I)}
        candidatas = {ruta for ruta in rutas
                      if re.match(r"^/p-\d{3,}_[a-z0-9_-]+/?$", ruta, re.I)}
        if len(candidatas) < 3:
            return None
        return re.compile(r"^/p-\d{3,}_[a-z0-9_-]+/?$", re.I)

    @staticmethod
    def _patron_portal_offset_local(html: str) -> "re.Pattern | None":
        """Fichas `/venta|alquiler/<tipo>/<slug>-<id>` de portales legacy."""
        rutas = {urllib.parse.urlparse(m.group(1)).path
                 for m in re.finditer(r'href="([^"]{4,400})"', html or "", re.I)}
        candidatas = {ruta for ruta in rutas if re.fullmatch(
            r"/(?:venta|alquiler)/[^/]+/[^/]+-\d{3,}/?", ruta, re.I)}
        if len(candidatas) < 3:
            return None
        return re.compile(r"^/(?:venta|alquiler)/[^/]+/[^/]+-\d{3,}/?$", re.I)

    @staticmethod
    def _portal_catalogo(html: str, operation: str, code: int) -> dict[str, Any] | None:
        form = re.search(
            r'<form[^>]+name="frm_propiedades"[^>]*>(.*?)</form>',
            html or "", re.I | re.S)
        if not form:
            return None
        block = form.group(1)

        def hidden(name: str) -> str | None:
            match = re.search(
                rf'<input[^>]+name="{re.escape(name)}"[^>]+value="([^"]*)"',
                block, re.I)
            return match.group(1) if match else None

        page_match = re.search(r'class="numero">\s*1/(\d+)\s*<', html, re.I)
        pages = int(page_match.group(1)) if page_match else 1
        section, session = hidden("id_section"), hidden("ssnId_session")
        if not section or not session:
            return None
        return {"operation": operation, "code": code, "html": html,
                "pages": pages, "id_section": section, "session": session}

    @staticmethod
    def _patron_catalogo_numerico(urls: list[str]) -> "re.Pattern | None":
        """Familia fuerte observada dentro del catalogo de esta fuente.

        Algunos CMS mezclan en `/propiedades` las fichas `/propiedad/<id>` con
        links de filtros `/propiedades/<localidad>`. Si aparecen al menos tres
        ids numericos distintos, esa familia es evidencia mas fuerte que el
        patron global y evita publicar filtros como si fueran inmuebles.
        """
        rutas = {urllib.parse.urlparse(url).path for url in urls}
        numericas = {ruta for ruta in rutas
                     if re.fullmatch(r"/propiedad/\d+/?", ruta, re.I)}
        if len(numericas) < 3:
            return None
        return re.compile(r"^/propiedad/\d+/?$", re.I)

    @staticmethod
    def _fichas_query_en(html: str, base: str) -> list[str]:
        """Fichas PHP con id numerico, habilitadas por su catalogo local.

        No se agregan al patron global: se aceptan unicamente cuando aparecen
        al menos tres ids distintos dentro de los resultados oficiales de la
        misma fuente.
        """
        host = urllib.parse.urlparse(base).netloc.lower().replace("www.", "")
        salida: dict[str, str] = {}
        for match in re.finditer(r'href=["\']([^"\']{4,400})', html or "", re.I):
            url = urllib.parse.urljoin(base, unescape(match.group(1)))
            parsed = urllib.parse.urlparse(url)
            if parsed.netloc.lower().replace("www.", "") != host:
                continue
            if not re.fullmatch(r"/propiedad\.php", parsed.path, re.I):
                continue
            listing_id = (urllib.parse.parse_qs(parsed.query).get("id") or [""])[0]
            if not re.fullmatch(r"\d{3,}", listing_id):
                continue
            salida.setdefault(listing_id, url.split("#", 1)[0])
        return list(salida.values())

    @staticmethod
    def _total_declarado_en(html: str) -> int | None:
        """Total humano del catalogo, aun cuando el numero tenga markup."""
        match = re.search(
            r"Se encontraron(?:\s|<[^>]+>)*([\d.]+)"
            r"(?:\s|<[^>]+>)*resultados",
            html or "", re.I)
        if not match:
            return None
        try:
            return int(match.group(1).replace(".", ""))
        except ValueError:
            return None

    def _catalogo_wordpress_por_categoria(
            self, html_home: str, base: str) -> dict[str, Any] | None:
        """Inventario editorial WordPress probado por catalogo y REST.

        Algunos sitios chicos publican cada inmueble como un ``post`` comun,
        clasificado en ``venta`` o ``alquiler``. No alcanza con que el sitio
        use WordPress ni con que una nota tenga esa categoria: exigimos que la
        portada enlace los catalogos oficiales, que cada catalogo renderice
        articulos Divi con la categoria correspondiente y que el conteo y las
        URLs coincidan exactamente con la API publica de WordPress.

        Esa triple evidencia evita confundir noticias de mercado con
        propiedades y, a diferencia de raspar solo la primera grilla, prueba
        que no se omitieron fichas paginadas.
        """
        parsed_base = urllib.parse.urlparse(base)
        expected_host = parsed_base.netloc.lower().replace("www.", "")
        catalog_urls: dict[str, str] = {}
        for match in re.finditer(r'href=["\']([^"\']{4,400})', html_home or "", re.I):
            url = urllib.parse.urljoin(base + "/", unescape(match.group(1)))
            parsed = urllib.parse.urlparse(url)
            if parsed.netloc.lower().replace("www.", "") != expected_host:
                continue
            operation_match = re.fullmatch(r"/(venta|alquiler)/?", parsed.path, re.I)
            if operation_match:
                operation = operation_match.group(1).lower()
                catalog_urls.setdefault(operation, url.split("#", 1)[0])
        if not catalog_urls or "wp-content" not in (html_home or "").lower():
            return None

        categories_url = (
            f"{base}/wp-json/wp/v2/categories?per_page=100"
            "&_fields=id,name,slug,count")
        try:
            categories = json.loads(self.descargador.bajar(categories_url))
        except (ValueError, ErrorTransitorio, ErrorPermanente, Bloqueado):
            return None
        if not isinstance(categories, list):
            return None
        selected: dict[str, dict[str, Any]] = {}
        for category in categories:
            slug = str((category or {}).get("slug") or "").lower()
            if slug not in catalog_urls:
                continue
            category_id = (category or {}).get("id")
            count = (category or {}).get("count")
            if not isinstance(category_id, int) or not isinstance(count, int):
                continue
            if count > 0:
                selected[slug] = {"id": category_id, "count": count}
        declared = sum(item["count"] for item in selected.values())
        if declared < 3 or declared > MAX_FICHAS:
            return None

        catalog_links: dict[str, set[str]] = {}
        for operation, category in selected.items():
            try:
                catalog_html = self.descargador.bajar(catalog_urls[operation])
            except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                return None
            blocks = re.findall(
                rf'<article\b[^>]*class=["\'][^"\']*\bcategory-{operation}\b'
                rf'[^"\']*["\'][^>]*>(.*?)</article>',
                catalog_html, re.I | re.S)
            links: set[str] = set()
            for block in blocks:
                for match in re.finditer(r'href=["\']([^"\']{4,400})', block, re.I):
                    url = urllib.parse.urljoin(base + "/", unescape(match.group(1)))
                    parsed = urllib.parse.urlparse(url)
                    if parsed.netloc.lower().replace("www.", "") == expected_host:
                        links.add(url.split("#", 1)[0].rstrip("/"))
            if len(links) != category["count"]:
                return None
            catalog_links[operation] = links

        category_ids = ",".join(str(item["id"]) for item in selected.values())
        fields = "id,link,slug,title,categories"
        posts: list[dict[str, Any]] = []
        for page in range(1, 1 + (declared + 99) // 100):
            url = (f"{base}/wp-json/wp/v2/posts?categories={category_ids}"
                   f"&per_page=100&page={page}&_fields={fields}")
            try:
                rows = json.loads(self.descargador.bajar(url))
            except (ValueError, ErrorTransitorio, ErrorPermanente, Bloqueado):
                return None
            if not isinstance(rows, list):
                return None
            posts.extend(row for row in rows if isinstance(row, dict))

        by_id = {item["id"]: operation for operation, item in selected.items()}
        verified: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for post in posts:
            listing_id = str(post.get("id") or "")
            link = str(post.get("link") or "").split("#", 1)[0].rstrip("/")
            operations = {by_id[category_id] for category_id in post.get("categories") or []
                          if category_id in by_id}
            parsed = urllib.parse.urlparse(link)
            if (not listing_id or not link or len(operations) != 1
                    or parsed.netloc.lower().replace("www.", "") != expected_host):
                return None
            operation = next(iter(operations))
            if link not in catalog_links.get(operation, set()) or listing_id in seen_ids:
                return None
            seen_ids.add(listing_id)
            title_value = post.get("title")
            if isinstance(title_value, dict):
                title_value = title_value.get("rendered")
            verified.append({"id": listing_id, "url": link + "/",
                             "operation": operation,
                             "title": limpiar(_texto(str(title_value or "")))})
        if len(verified) != declared:
            return None
        return {"posts": verified, "total": declared,
                "catalog_urls": catalog_urls}

    @staticmethod
    def _fichas_mapaprop_en(html: str, base: str) -> list[str]:
        """Fichas del catalogo MAPAPROP, sin aceptar links institucionales.

        La plataforma repite cada URL en imagen, titulo y CTA. La ruta fuerte
        termina en los ids numericos de cliente y propiedad; exigir ambos evita
        convertir ``/propiedad/`` o formularios de consulta en avisos.
        """
        expected_host = urllib.parse.urlparse(base).netloc.lower().replace("www.", "")
        found: dict[str, str] = {}
        for match in re.finditer(r'href=["\']([^"\']{4,600})', html or "", re.I):
            url = urllib.parse.urljoin(base + "/", unescape(match.group(1)))
            parsed = urllib.parse.urlparse(url)
            if parsed.netloc.lower().replace("www.", "") != expected_host:
                continue
            if not re.fullmatch(
                    r"/propiedad/[a-z0-9][a-z0-9-]*-\d{1,8}-\d{3,}/?",
                    parsed.path, re.I):
                continue
            canonical = urllib.parse.urlunparse(
                (parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))
            found.setdefault(canonical, canonical)
        return list(found.values())

    def _catalogo_mapaprop(self, html_home: str,
                           base: str) -> dict[str, Any] | None:
        """Detecta MAPAPROP solo con marca, buscador y resultados coherentes."""
        if not re.search(r"powered\s+by\s+MAPAPROP", _texto(html_home), re.I):
            return None
        expected_host = urllib.parse.urlparse(base).netloc.lower().replace("www.", "")
        candidates: list[tuple[int, str]] = []
        for match in re.finditer(r'href=["\']([^"\']{4,600})', html_home or "", re.I):
            # ``html.unescape`` interpreta el prefijo ``&curren`` dentro de
            # ``&currency`` como la entidad ¤. Solo decodificamos el ampersand
            # que realmente puede venir escapado en un atributo URL.
            href = (match.group(1).replace("&amp;", "&")
                    .replace("&#38;", "&").replace("&#x26;", "&"))
            url = urllib.parse.urljoin(base + "/", href)
            parsed = urllib.parse.urlparse(url)
            query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
            if (parsed.netloc.lower().replace("www.", "") == expected_host
                    and parsed.path.rstrip("/").lower() == "/buscar"
                    and (query.get("view") or [""])[0].lower() == "list"):
                # En el menu conviven "Venta", "Alquiler" y "Propiedades".
                # El inventario completo es el buscador con filtros vacios;
                # tomar el primer link certificaria solo una operacion.
                restrictive = sum(bool((query.get(key) or [""])[0].strip())
                                  for key in ("type", "operation", "zone1",
                                              "currency", "priceFrom", "priceTo"))
                candidates.append((restrictive, url.split("#", 1)[0]))
        if not candidates:
            return None
        search_url = min(candidates, key=lambda item: item[0])[1]
        try:
            catalog_html = self.descargador.bajar(search_url)
        except (ErrorTransitorio, ErrorPermanente, Bloqueado):
            return None
        listings = self._fichas_mapaprop_en(catalog_html, base)
        total_match = re.search(
            r"Se\s+encontraron(?:\s|<[^>]+>)*([\d.]+)"
            r"(?:\s|<[^>]+>)*propiedades", catalog_html, re.I)
        if not total_match or len(listings) < 3:
            return None
        declared = int(total_match.group(1).replace(".", ""))
        if declared < len(listings) or declared > MAX_FICHAS:
            return None
        # La primera pagina debe enlazar la siguiente cuando declara mas filas.
        # Sin esa evidencia no asumimos una convencion de paginacion por marca.
        page_links = {
            int(value)
            for href in re.findall(r'href=["\']([^"\']+)', catalog_html, re.I)
            for value in (urllib.parse.parse_qs(
                urllib.parse.urlparse(href.replace("&amp;", "&")
                                      .replace("&#38;", "&")
                                      .replace("&#x26;", "&")).query
            ).get("page") or [])
            if str(value).isdigit()
        }
        if declared > len(listings) and 1 not in page_links:
            return None
        parsed_search = urllib.parse.urlparse(search_url)
        query_pairs = urllib.parse.parse_qsl(parsed_search.query, keep_blank_values=True)
        query_pairs = [(key, value) for key, value in query_pairs if key != "page"]
        return {"listing_url": urllib.parse.urlunparse((
                    parsed_search.scheme, parsed_search.netloc, parsed_search.path,
                    parsed_search.params, urllib.parse.urlencode(query_pairs), "")),
                "html_first": catalog_html, "first_listings": listings,
                "per_page": len(listings), "total": declared}

    @staticmethod
    def _detalle_mapaprop(html: str, url: str) -> dict[str, Any]:
        """Extrae solo bloques rotulados por MAPAPROP; no interpreta prosa libre."""
        result: dict[str, Any] = {}
        description = re.search(
            r'<div[^>]+class=["\'][^"\']*\bdescription\b[^"\']*["\'][^>]*>'
            r'.*?<p[^>]*>(.*?)</p>', html or "", re.I | re.S)
        if description:
            value = limpiar(_texto(description.group(1)))
            if value and len(value) >= 20:
                result["descripcion"] = value

        label_map = {
            "Calle": "direccion", "Localidad/Barrio": "barrio",
            "Municipio": "ciudad", "Provincia": "provincia",
        }
        for label, field in label_map.items():
            match = re.search(
                rf'<strong[^>]*>\s*{re.escape(label)}\s*:\s*</strong>'
                r'\s*([^<]{1,180})', html or "", re.I)
            if match:
                value = limpiar(_texto(match.group(1)))
                if value:
                    result[field] = value

        price = re.search(
            r'class=["\'][^"\']*\bprice\b[^"\']*["\'][^>]*>\s*'
            r'(?:Valor\s*:\s*)?(USD|U\$S|US\$|ARS|\$)\s*([\d][\d.,]{1,15})',
            html or "", re.I)
        if price:
            result["moneda"] = detectar_moneda(price.group(1))
            result["precio"] = a_numero(price.group(2))

        for field, label in (("superficie_total", "total"),
                             ("superficie_cubierta", "cubierta")):
            surface = re.search(
                rf"([\d][\d.,]*)\s*m(?:2|²)?\s+de\s+superficie\s+{label}",
                _texto(html or ""), re.I)
            if surface:
                result[field] = a_numero(surface.group(1))

        images: list[str] = []
        for raw in RE_IMG.findall(html or ""):
            image = unescape(raw).rstrip("\\")
            parsed = urllib.parse.urlparse(image)
            if (parsed.netloc.lower() != "images.mapaprop.app"
                    or "/photos/" not in parsed.path.lower()
                    or re.search(r"t\.(?:jpe?g|png|webp)$", parsed.path, re.I)):
                continue
            canonical = identidad_de_imagen(urllib.parse.urljoin(url, image))
            if canonical not in images:
                images.append(canonical)
        result["imagenes"] = images
        return result

    # ------------------------------------------------- Bitrix24 Landing
    @staticmethod
    def _nodo_landing(article: str, sufijo: str) -> str | None:
        """Texto de un nodo `landing-block-node-card-<sufijo>` de la tarjeta.

        El token de clase se compara ENTERO. `-card-price` y
        `-card-price-subtitle` comparten prefijo, y un match laxo devuelve
        "Valor de Venta" como si fuera el precio: un dato inventado que ademas
        parece correcto.

        Se balancea el tag porque la descripcion trae `<p>` anidados; cortar en
        el primer cierre devolveria la primera linea y perderia el resto sin
        que nada falle.
        """
        apertura = re.search(
            r'<(?P<tag>div|h[1-6]|p|span)\b[^>]*class="[^"]*'
            r'\blanding-block-node-card-' + re.escape(sufijo) +
            r'(?![\w-])[^"]*"[^>]*>', article, re.I)
        if not apertura:
            return None
        tag = apertura.group("tag").lower()
        resto = article[apertura.end():]
        profundidad = 1
        for cierre in re.finditer(rf"<(/?){tag}\b", resto, re.I):
            profundidad += -1 if cierre.group(1) else 1
            if profundidad == 0:
                return limpiar(_texto(resto[:cierre.start()])) or None
        return limpiar(_texto(resto)) or None

    def _catalogo_bitrix_landing(self, html: str,
                                 base: str) -> dict[str, Any] | None:
        """Tarjetas de propiedad publicadas en una landing de Bitrix24 Sites.

        Bitrix24 arma sitios de UNA sola pagina: no hay ficha por propiedad, ni
        enlace, ni sitemap. El inventario vive como bloques `landing-block-...`
        dentro de la portada. Por eso todos los detectores que buscan URLs de
        ficha se van vacios y el sitio parece no publicar nada cuando si
        publica.

        Solo entran las tarjetas CON precio. Las que no lo tienen son los
        bloques de servicio de la plantilla —"Tasaciones", "Venta en
        exclusiva"— y contarlas como inmuebles inflaria el inventario con
        texto de marketing.
        """
        if not re.search(r"cdn\.bitrix24\.[a-z]{2,3}/|/bitrix/js/landing/",
                         html or "", re.I):
            return None

        filas: list[dict[str, Any]] = []
        for article in re.findall(r"<article\b.*?</article>", html or "",
                                  re.S | re.I):
            precio = self._nodo_landing(article, "price")
            titulo = self._nodo_landing(article, "title")
            if not precio or not titulo:
                continue
            imagenes: list[str] = []
            for raw in re.findall(r'data-src="([^"]+)"', article):
                imagen = identidad_de_imagen(
                    urllib.parse.urljoin(base, unescape(raw)))
                if imagen and imagen not in imagenes:
                    imagenes.append(imagen)
            # Unico identificador que la fuente emite por tarjeta: el id de
            # archivo que Bitrix le asigna a la imagen. No hay id de propiedad
            # ni enlace propio, pero este es de la fuente y no inventado.
            file_id = re.search(r'data-fileid="(\d+)"', article)
            filas.append({"titulo": titulo, "precio_texto": precio,
                          "subtitulo": self._nodo_landing(article,
                                                          "price-subtitle"),
                          "descripcion": self._nodo_landing(article, "text"),
                          "imagenes": imagenes,
                          "file_id": file_id.group(1) if file_id else None})
        if not filas:
            return None
        return {"rows": filas, "total": len(filas)}

    @staticmethod
    def _clave_landing(titulo: str, indice: int,
                       file_id: str | None = None) -> str:
        """Identificador estable de una tarjeta sin URL propia.

        Se prefiere el `data-fileid` de Bitrix: lo emite la fuente, es unico
        por construccion y no depende del orden de lectura. El slug del titulo
        queda de respaldo, pero es peor identidad —dos lotes pueden llamarse
        igual y la clave los fusionaria en una sola propiedad—, y el indice es
        el ultimo recurso porque cambia si reordenan las tarjetas.
        """
        if file_id:
            return f"f{file_id}"
        plano = unicodedata.normalize("NFKD", titulo)
        plano = plano.encode("ascii", "ignore").decode()
        slug = re.sub(r"[^a-z0-9]+", "-", plano.lower()).strip("-")
        return slug or f"tarjeta-{indice}"

    # ---------------------------------------------------------------- discover
    def discover(self, fuente: Fuente) -> dict[str, Any]:
        p = urllib.parse.urlparse(fuente.official_url)
        base = f"{p.scheme}://{p.netloc}"
        plan: dict[str, Any] = {"base": base, "variante": "SIN_INVENTARIO",
                                "soportada": False, "total_declarado": None}

        propia = self._patron_de(fuente)

        # --- 1. sitemap ----------------------------------------------------
        indices, fichas = [], []
        for ruta in SITEMAPS:
            try:
                cuerpo = self.descargador.bajar(base + ruta)
            except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                continue
            if "<" not in cuerpo:
                continue
            locs = RE_LOC.findall(cuerpo)
            fichas += [u for u in locs
                       if self._es_ficha_url(u, propia)
                       and self._mismo_sitio(u, base)]
            indices += [u for u in locs if u.lower().endswith((".xml", ".xml.gz"))]
            if fichas or indices:
                break

        # Un indice de sitemaps apunta a otros sitemaps. Se abren solo los que
        # prometen fichas: bajar el de imagenes o el de notas es gasto puro.
        for sub in [u for u in indices
                    if re.search(r"(propiedad|inmueble|listing|propert|aviso|post|page)",
                                 u, re.I)][:MAX_SITEMAPS]:
            try:
                cuerpo = self.descargador.bajar(sub)
            except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                continue
            fichas += [u for u in RE_LOC.findall(cuerpo)
                       if self._es_ficha_url(u, propia)
                       and self._mismo_sitio(u, base)]
            if len(fichas) >= MAX_FICHAS:
                break

        if fichas:
            vistas, limpias = set(), []
            for u in fichas:
                c = u.split("#")[0].rstrip("/")
                if c not in vistas:
                    vistas.add(c)
                    limpias.append(u)
            plan.update({"variante": "SITEMAP", "soportada": True,
                         "fichas": limpias[:MAX_FICHAS],
                         "total_declarado": len(limpias)})
            return plan

        # --- 2. listado en HTML --------------------------------------------
        try:
            html = self.descargador.bajar(fuente.official_url)
        except (ErrorTransitorio, ErrorPermanente, Bloqueado):
            return plan
        # Xintel/Amaira deja el catalogo HTML vacio y lo hidrata desde su API
        # publica. Las credenciales que siguen son identificadores publicados
        # por el propio JavaScript del sitio; nunca se persisten en resultados.
        xintel_inm = re.search(
            r'["\']inm["\']\s*:\s*["\']([^"\']+)["\']', html, re.I)
        xintel_key = re.search(
            r'["\']apiK["\']\s*:\s*["\']([^"\']+)["\']', html, re.I)
        if "xintelapi.com.ar" in html.lower() and xintel_inm and xintel_key:
            plan.update({"variante": "XINTEL_API", "soportada": True,
                         "xintel_inm": xintel_inm.group(1),
                         "xintel_key": xintel_key.group(1),
                         "total_declarado": None})
            return plan
        php_ajax_catalog = self._catalogo_php_ajax(html, base)
        if php_ajax_catalog is not None:
            plan.update({"variante": "PHP_AJAX_SEARCH", "soportada": True,
                         "php_ajax_rows": php_ajax_catalog["rows"],
                         "total_declarado": php_ajax_catalog["total"],
                         "catalogo_runtime_verificado": True})
            return plan
        wordpress_catalog = self._catalogo_wordpress_por_categoria(html, base)
        if wordpress_catalog is not None:
            plan.update({"variante": "WORDPRESS_CATEGORY_CATALOG",
                         "soportada": True,
                         "fichas_wordpress": wordpress_catalog["posts"],
                         "total_declarado": wordpress_catalog["total"],
                         "catalogo_runtime_verificado": True})
            return plan
        mapaprop_catalog = self._catalogo_mapaprop(html, base)
        if mapaprop_catalog is not None:
            plan.update({"variante": "MAPAPROP_HTML", "soportada": True,
                         "listing_url": mapaprop_catalog["listing_url"],
                         "html_first": mapaprop_catalog["html_first"],
                         "fichas_home": mapaprop_catalog["first_listings"],
                         "per_page": mapaprop_catalog["per_page"],
                         "total_declarado": mapaprop_catalog["total"],
                         "catalogo_runtime_verificado": True})
            return plan
        # Bitrix24 Sites publica todo en la portada, sin ficha ni sitemap. Va
        # antes de las heuristicas de HTML generico porque esas buscan enlaces
        # de ficha y aca no existe ninguno: sin este detector el sitio se
        # reporta como no soportado y su inventario real queda invisible.
        bitrix_catalog = self._catalogo_bitrix_landing(html, base)
        if bitrix_catalog is not None:
            plan.update({"variante": "BITRIX_LANDING_CARDS", "soportada": True,
                         "bitrix_rows": bitrix_catalog["rows"],
                         "total_declarado": bitrix_catalog["total"],
                         "catalogo_runtime_verificado": True})
            return plan
        # Algunos sitios PHP enlazan el inventario como `propiedades.php` en
        # vez de `/propiedades`. Si ese catalogo oficial declara de manera
        # explicita que no hay inmuebles, dos corridas pueden certificar cero
        # sin inventar una variante ni tratar una ausencia probada como fallo.
        # No se infiere vacio por falta de cards: la frase explicita es la
        # evidencia conservadora que permite fallar cerrado.
        empty_catalog = re.compile(
            r"No\s+se\s+encontraron\s+inmuebles\s+publicados\s+por\s+este\s+vendedor",
            re.I)
        catalog_candidates: list[str] = []
        for match in re.finditer(r'href=["\']([^"\']{4,400})', html or "", re.I):
            candidate = urllib.parse.urljoin(fuente.official_url, unescape(match.group(1)))
            parsed = urllib.parse.urlparse(candidate)
            if (parsed.netloc.lower().replace("www.", "")
                    != p.netloc.lower().replace("www.", "")):
                continue
            if not re.fullmatch(r"/(?:propiedades|inmuebles)(?:\.php)?/?", parsed.path,
                                re.I):
                continue
            canonical = candidate.split("#", 1)[0]
            if canonical not in catalog_candidates:
                catalog_candidates.append(canonical)
        for catalog_url in catalog_candidates:
            try:
                catalog_html = self.descargador.bajar(catalog_url)
            except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                continue
            if empty_catalog.search(_texto(catalog_html)):
                plan.update({"variante": "EMPTY_CATALOG_HTML", "soportada": True,
                             "total_declarado": 0, "listing_url": catalog_url,
                             "empty_catalog_explicit": True})
                return plan
        # Sitios PHP propios enlazan desde la portada a los catalogos por
        # operacion y publican cada ficha como `propiedad.php?id=<id>`. La
        # familia se habilita solo si el catalogo oficial muestra >=3 ids.
        catalog_urls: list[str] = []
        for match in re.finditer(r'href=["\']([^"\']{4,400})', html or "", re.I):
            url = urllib.parse.urljoin(base, unescape(match.group(1)))
            parsed = urllib.parse.urlparse(url)
            query = urllib.parse.parse_qs(parsed.query)
            operation = (query.get("operacion") or [""])[0]
            if (parsed.netloc.lower().replace("www.", "")
                    == p.netloc.lower().replace("www.", "")
                    and re.fullmatch(r"/resultados\.php", parsed.path, re.I)
                    and operation.lower() in {"venta", "alquiler"}):
                canonical = base + "/resultados.php?" + urllib.parse.urlencode(
                    {"operacion": operation.title()})
                if canonical not in catalog_urls:
                    catalog_urls.append(canonical)
        query_fichas: dict[str, str] = {}
        for catalog_url in catalog_urls:
            try:
                catalog_html = self.descargador.bajar(catalog_url)
            except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                continue
            for url in self._fichas_query_en(catalog_html, base):
                listing_id = (urllib.parse.parse_qs(
                    urllib.parse.urlparse(url).query).get("id") or [""])[0]
                query_fichas.setdefault(listing_id, url)
        if len(query_fichas) >= 3:
            plan.update({"variante": "QUERY_CATALOG_HTML", "soportada": True,
                         "fichas_home": list(query_fichas.values()),
                         "total_declarado": len(query_fichas),
                         "catalogo_runtime_verificado": True})
            return plan
        portal_pattern = self._patron_portal_offset_local(html)
        if portal_pattern is not None:
            catalogs = []
            for operation, code in (("venta", 2), ("alquiler", 1)):
                try:
                    catalog_html = self.descargador.bajar(base + "/" + operation)
                except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                    continue
                catalog = self._portal_catalogo(catalog_html, operation, code)
                if catalog and self._fichas_en(catalog_html, base, portal_pattern):
                    catalogs.append(catalog)
            if catalogs:
                plan.update({"variante": "PORTAL_OFFSET_HTML", "soportada": True,
                             "total_declarado": None,
                             "patron_runtime": portal_pattern,
                             "catalogo_runtime_verificado": True,
                             "portal_catalogs": catalogs})
                return plan
        runtime = propia or self._patron_raiz_local(html)
        enlaces = self._fichas_en(html, base, runtime)
        listado = base + "/propiedades"
        if urllib.parse.urlparse(fuente.official_url).path.rstrip("/") != "/propiedades":
            try:
                html_listado = self.descargador.bajar(listado)
            except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                html_listado = ""
            runtime_listado = runtime or self._patron_raiz_local(html_listado)
            enlaces_listado = self._fichas_en(html_listado, base, runtime_listado)
            catalogo_explicito = bool(re.search(
                r"Se encontraron\s+[\d.]+\s+resultados|"
                r"params\.append\(['\"]infinito['\"]|id=['\"]prop-list['\"]",
                html_listado, re.I))
            if enlaces_listado and (catalogo_explicito
                                     or len(enlaces_listado) > len(enlaces)):
                html, enlaces, runtime = html_listado, enlaces_listado, runtime_listado
        else:
            listado = fuente.official_url
        if enlaces:
            patron_catalogo = self._patron_catalogo_numerico(enlaces)
            if patron_catalogo is not None:
                enlaces = [url for url in enlaces
                           if patron_catalogo.match(urllib.parse.urlparse(url).path)]
            total = self._total_declarado_en(html)
            plan.update({"variante": "LISTADO_HTML", "soportada": True,
                         "fichas_home": enlaces, "html_home": html,
                         "listing_url": listado, "total_declarado": total,
                         "patron_runtime": runtime,
                         "patron_catalogo": patron_catalogo,
                         "catalogo_runtime_verificado": bool(runtime and not propia)})
        return plan

    @staticmethod
    def _es_ficha_url(u: str, propia: "re.Pattern | None" = None) -> bool:
        ruta = urllib.parse.urlparse(u).path
        return not RE_NO_FICHA.search(ruta) and bool(RE_FICHA.search(u) or RE_FICHA_RAIZ.search(ruta)
                    or (propia is not None and propia.match(ruta)))

    @staticmethod
    def _solo_por_forma(u: str, propia: "re.Pattern | None") -> bool:
        """La url entro unicamente por la forma verificada de esta fuente.

        Se anota para que el detalle la compruebe: una forma de raiz amplia
        -/<slug>- tambien alcanza /quienes-somos, y una pagina institucional no
        puede terminar publicada como propiedad.
        """
        if propia is None:
            return False
        ruta = urllib.parse.urlparse(u).path
        return bool(propia.match(ruta)) and not (RE_FICHA.search(u)
                                                 or RE_FICHA_RAIZ.search(ruta))

    @staticmethod
    def _fichas_en(html: str, base: str, extra: "re.Pattern | None" = None) -> list[str]:
        """Los enlaces a fichas del HTML.

        `extra` es la forma verificada de ESTA fuente. Existe para no tener que
        aflojar el patron global: 65 sitios publican sus fichas en la raiz y se
        comprobo una por una -bajando tres paginas de cada uno- que traen precio
        con moneda, operacion y fotos. Habilitar esa forma para ellos no afloja
        nada para los otros 2.258.
        """
        host = urllib.parse.urlparse(base).netloc.lower().replace("www.", "")
        salida, vistas = [], set()
        for m in re.finditer(r'href="([^"]{4,300})"', html or ""):
            u = urllib.parse.urljoin(base, m.group(1))
            if urllib.parse.urlparse(u).netloc.lower().replace("www.", "") != host:
                continue
            ruta = urllib.parse.urlparse(u).path
            if RE_NO_FICHA.search(ruta) or not (RE_FICHA.search(u) or RE_FICHA_RAIZ.search(ruta)
                    or (extra is not None and extra.match(ruta))):
                continue
            c = u.split("#")[0].rstrip("/")
            if c not in vistas:
                vistas.add(c)
                salida.append(u)
        return salida

    # ----------------------------------------------------------- fetch_listing
    def fetch_listing(self, fuente: Fuente, plan: dict[str, Any]) -> Iterator[dict]:
        if not plan.get("soportada"):
            return
        if plan["variante"] == "EMPTY_CATALOG_HTML":
            return
        propia = plan.get("patron_runtime") or self._patron_de(fuente)
        if plan["variante"] == "SITEMAP":
            for i, u in enumerate(plan["fichas"], 1):
                yield {"source_listing_id": self._id_de(u), "source_url": u,
                       "pagina": 1 + i // 100,
                       "por_forma": self._solo_por_forma(u, propia)}
            return

        base = plan["base"]
        patron_catalogo = plan.get("patron_catalogo")

        def pertenece_al_catalogo(url: str) -> bool:
            return (patron_catalogo is None
                    or bool(patron_catalogo.match(urllib.parse.urlparse(url).path)))

        vistas: set[str] = set()
        if plan.get("variante") == "PORTAL_OFFSET_HTML":
            propia = plan.get("patron_runtime")
            duplicados = 0
            for catalog_index, catalog in enumerate(plan.get("portal_catalogs") or []):
                for page in range(1, int(catalog["pages"]) + 1):
                    if page == 1:
                        html = catalog["html"]
                    else:
                        params = urllib.parse.urlencode({
                            "action": "portal/show",
                            "id_section": catalog["id_section"],
                            "ssnId_session": catalog["session"],
                            "offset": (page - 1) * 12,
                            f"search_filter[cntProp_tipo_opt][{catalog['code']}]":
                                catalog["code"],
                        })
                        try:
                            html = self.descargador.bajar(base + "/index.php?" + params)
                        except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                            break
                    for url in self._fichas_en(html, base, propia):
                        canonical = url.rstrip("/")
                        if canonical in vistas:
                            duplicados += 1
                            continue
                        vistas.add(canonical)
                        yield {"source_listing_id": self._id_de(url),
                               "source_url": url,
                               "pagina": catalog_index * 1000 + page,
                               "por_forma": True,
                               "catalogo_runtime_verificado": True}
            self.duplicados_origen = duplicados
            return
        if plan["variante"] == "XINTEL_API":
            totals: list[int] = []
            duplicates = 0
            for operation_index, operation in enumerate(("v", "a")):
                # El frontend oficial inicia en cero. Empezar en uno omite
                # exactamente las primeras seis fichas de cada operacion.
                # `datos.paginas` usa piso (11 fichas / 6 => 1) y omite la
                # pagina parcial final. La unica terminacion confiable es una
                # respuesta sin filas, igual que el scroll infinito oficial.
                for page in range(0, 1000):
                    query = urllib.parse.urlencode({
                        "json": "resultados.fichas",
                        "inm": plan["xintel_inm"],
                        "apiK": plan["xintel_key"],
                        "utf8decode": plan["xintel_key"],
                        "page": page,
                        "tipo_operacion": operation,
                        # Xintel puede aceptar otro valor para calcular la
                        # cantidad de paginas pero seguir devolviendo seis
                        # filas. Usar el contrato del frontend evita cortar el
                        # inventario despues de la primera pagina.
                        "rppagina": 6,
                    })
                    body = self.descargador.bajar(
                        "https://xintelapi.com.ar/?" + query)
                    try:
                        response = json.loads(body)
                    except ValueError as error:
                        raise ErrorTransitorio("Xintel devolvio JSON invalido") from error
                    result = response.get("resultado") or {}
                    rows = result.get("fichas") or []
                    data = result.get("datos") or {}
                    if page == 0:
                        total = data.get("cantidadFichas") or data.get("cantidad")
                        if str(total or "").isdigit():
                            totals.append(int(total))
                    if not isinstance(rows, list) or not rows:
                        break
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        friendly = str(row.get("amigable") or "").strip("/")
                        if not friendly:
                            continue
                        url = urllib.parse.urljoin(base + "/", friendly)
                        canonical = url.rstrip("/")
                        if canonical in vistas:
                            duplicates += 1
                            continue
                        vistas.add(canonical)
                        listing_id = (row.get("inmueble_id") or row.get("id")
                                      or self._id_de(url))
                        yield {"source_listing_id": str(listing_id),
                               "source_url": url,
                               "pagina": operation_index * 1000 + page + 1,
                               "xintel": row}
            plan["total_declarado"] = sum(totals) if totals else None
            self.duplicados_origen = duplicates
            return
        if plan["variante"] == "QUERY_CATALOG_HTML":
            for url in plan.get("fichas_home") or []:
                yield {"source_listing_id": self._id_de(url),
                       "source_url": url, "pagina": 1, "por_forma": True,
                       "catalogo_runtime_verificado": True}
            return
        if plan["variante"] == "BITRIX_LANDING_CARDS":
            # La tarjeta no tiene URL propia. El fragmento NO sirve como
            # identidad: `hash_dedup` normaliza la URL con urlparse, que
            # descarta el fragmento, y las tarjetas colapsaban en un unico
            # hash pisandose entre si. El discriminador va en el query, que la
            # normalizacion si conserva, sobre la pagina donde la propiedad
            # esta realmente publicada.
            for indice, row in enumerate(plan.get("bitrix_rows") or [], 1):
                clave = self._clave_landing(row["titulo"], indice,
                                            row.get("file_id"))
                query = urllib.parse.urlencode({"eretz_ficha": clave})
                yield {"source_listing_id": clave,
                       "source_url": f"{base}/?{query}",
                       "pagina": 1, "bitrix_card": row,
                       "catalogo_runtime_verificado": True}
            return
        if plan["variante"] == "PHP_AJAX_SEARCH":
            for row in plan.get("php_ajax_rows") or []:
                operation = str(row["operacion"]).upper()
                listing_id = str(row["idcasa"])
                query = urllib.parse.urlencode({"id": listing_id,
                                                "op": operation})
                yield {"source_listing_id": listing_id,
                       "source_url": f"{base}/ficha.php?{query}",
                       "pagina": 1, "php_ajax": row,
                       "catalogo_runtime_verificado": True}
            return
        if plan["variante"] == "WORDPRESS_CATEGORY_CATALOG":
            for row in plan.get("fichas_wordpress") or []:
                yield {"source_listing_id": row["id"],
                       "source_url": row["url"], "pagina": 1,
                       "por_forma": True,
                       "operacion_catalogo": row["operation"],
                       "titulo_catalogo": row.get("title"),
                       "wordpress_category_catalog": True,
                       "catalogo_runtime_verificado": True}
            return
        if plan["variante"] == "MAPAPROP_HTML":
            total = int(plan["total_declarado"])
            per_page = max(1, int(plan.get("per_page") or 1))
            max_pages = min(1000, (total + per_page - 1) // per_page + 2)
            duplicates = 0
            for page in range(max_pages):
                if len(vistas) >= total:
                    break
                if page == 0:
                    html = plan["html_first"]
                else:
                    separator = "&" if "?" in plan["listing_url"] else "?"
                    html = self.descargador.bajar(
                        f'{plan["listing_url"]}{separator}page={page}')
                rows = self._fichas_mapaprop_en(html, base)
                if not rows:
                    break
                for url in rows:
                    canonical = url.rstrip("/")
                    if canonical in vistas:
                        duplicates += 1
                        continue
                    vistas.add(canonical)
                    yield {"source_listing_id": self._id_de(url),
                           "source_url": url, "pagina": page + 1,
                           "por_forma": True, "mapaprop_catalog": True,
                           "catalogo_runtime_verificado": True}
            self.duplicados_origen = duplicates
            return
        pendientes = [url for url in (plan.get("fichas_home") or [])
                      if pertenece_al_catalogo(url)]
        for u in pendientes:
            c = u.rstrip("/")
            if c in vistas:
                continue
            vistas.add(c)
            yield {"source_listing_id": self._id_de(u), "source_url": u, "pagina": 1,
                   "por_forma": self._solo_por_forma(u, propia),
                   "catalogo_runtime_verificado": plan.get("catalogo_runtime_verificado", False)}

        # BuscadorProp pagina mediante JSON con fragmentos HTML. No se puede
        # leer como HTML crudo porque las comillas de href vienen escapadas.
        # Se prueba antes de los patrones genericos y se detiene al agotarse.
        listado = plan.get("listing_url") or (base + "/propiedades")
        separador = "&" if "?" in listado else "?"
        patron_infinito = listado + separador + "infinito=1&pagina={n}"

        # Paginacion por convencion: /page/N y ?page=N son las dos formas que
        # cubren casi todo. Se corta apenas una no aporta fichas nuevas.
        # La RAIZ tambien puede ser el listado. Una plataforma entera pagina
        # asi -abinmobiliaria.com.ar?page=2- y sin este patron el connector solo
        # veia las 18 fichas de la portada: la fuente tenia 46.
        # Que la paginacion se AGOTE y que se INTERRUMPA se veian igual aguas
        # abajo, y no significan lo mismo: llegar al final prueba que eso es
        # todo lo que la fuente sirve por este camino, mientras que cortar por
        # un error no prueba nada sobre el inventario restante.
        self.paginacion_interrumpida = False
        for patron in (patron_infinito, "{b}/propiedades/page/{n}/", "{b}/propiedades?page={n}",
                       "{b}?page={n}"):
            inicio_patron = len(vistas)
            duplicados_patron = 0
            sin_nuevas = 0
            interrumpido = False
            for n in range(2, 60):
                try:
                    html = self.descargador.bajar(patron.format(b=base, n=n))
                except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                    interrumpido = True
                    break
                if html.lstrip().startswith("["):
                    try:
                        fragmentos = json.loads(html)
                        html = "".join(x for x in fragmentos if isinstance(x, str))
                    except ValueError:
                        pass
                nuevas = 0
                for u in self._fichas_en(html, base, propia):
                    if not pertenece_al_catalogo(u):
                        continue
                    c = u.rstrip("/")
                    if c in vistas:
                        duplicados_patron += 1
                        continue
                    vistas.add(c)
                    nuevas += 1
                    yield {"source_listing_id": self._id_de(u), "source_url": u,
                           "pagina": n, "por_forma": self._solo_por_forma(u, propia),
                           "catalogo_runtime_verificado": plan.get("catalogo_runtime_verificado", False)}
                if nuevas == 0:
                    sin_nuevas += 1
                    if sin_nuevas >= 2:
                        break
                else:
                    sin_nuevas = 0
            if len(vistas) > inicio_patron:
                self.duplicados_origen = duplicados_patron
                self.paginacion_interrumpida = interrumpido
                break

    @staticmethod
    def _id_de(url: str) -> str:
        """Id de la plataforma si lo hay; si no, el slug. Nunca un hash propio:
        tiene que poder rastrearse hasta la ficha de origen."""
        parsed = urllib.parse.urlparse(url)
        query_id = (urllib.parse.parse_qs(parsed.query).get("id") or [""])[0]
        if re.fullmatch(r"\d{3,}", query_id):
            return query_id
        ruta = parsed.path.rstrip("/")
        ultimo = ruta.rsplit("/", 1)[-1] if "/" in ruta else ruta
        m = re.search(r"-(\d{3,})$", ultimo) or re.search(r"(\d{3,})", ultimo)
        return m.group(1) if m else (ultimo or url)[:120]

    # --------------------------------------------------------------- normalize
    def normalize(self, crudo: dict, fuente: Fuente) -> PropiedadNormalizada | None:
        if crudo.get("php_ajax"):
            return self._normalizar_php_ajax(crudo, fuente)
        if crudo.get("bitrix_card"):
            return self._normalizar_bitrix_landing(crudo, fuente)
        url = crudo["source_url"]
        try:
            html = self.descargador.bajar(url)
        except ErrorPermanente as e:
            # La URL sigue viniendo del catalogo oficial de esta misma
            # corrida. Un 404/410 aislado puede ser una ventana de cache entre
            # listado y detalle; se registra para que el runner haga una sola
            # comprobacion diferida. Si la baja es real, esa comprobacion
            # vuelve a fallar y la certificacion conserva el detalle fallido.
            self.anotar_error(fuente, "detalle_permanente", e)
            return None
        except (ErrorTransitorio, Bloqueado) as e:
            self.anotar_error(fuente, "detalle", e)
            return None
        if not html or len(html) < 400:
            return None
        if crudo.get("xintel"):
            return self._normalizar_xintel(crudo, fuente, html)

        principal = cuerpo_principal(html)
        texto = normalizar_texto_campos(_texto(sin_filtros_catalogo(principal)))
        # Un emprendimiento contiene fichas de unidades debajo de ``UNIDADES``.
        # Esos ambientes/precios/operaciones pertenecen a las unidades, no al
        # desarrollo padre. Mezclarlos inventa atributos para el proyecto.
        es_emprendimiento = (
            "/emprendimiento/" in urllib.parse.urlparse(url).path.lower())
        principal_campos = (re.split(
            r">\s*UNIDADES\s*<", principal, maxsplit=1, flags=re.I)[0]
            if es_emprendimiento else principal)
        texto_campos = normalizar_texto_campos(
            _texto(sin_filtros_catalogo(principal_campos)))
        datos = self._de_json_ld(html)
        mapaprop = (self._detalle_mapaprop(html, url)
                    if crudo.get("mapaprop_catalog") else {})

        titulo = (limpiar(str(crudo.get("titulo_catalogo") or ""))
                  or self._titulo_de_la_ficha(html, datos, fuente))
        if not titulo:
            m = re.search(r"<title[^>]*>(.{1,200}?)</title>", html, re.S | re.I)
            titulo = limpiar(unescape(m.group(1))) if m else None

        descripcion = mapaprop.get("descripcion") or datos.get("descripcion")
        if not descripcion:
            m = re.search(r'<meta[^>]+(?:name|property)="(?:og:)?description"'
                          r'[^>]+content="([^"]{20,600})"', html, re.I)
            descripcion = limpiar(unescape(m.group(1))) if m else None
        if not descripcion:
            # Portales legacy sin metadata: una seccion rotulada
            # "Descripcion" es evidencia explicita y acotada. No se toma
            # prosa libre de toda la pagina ni contenido relacionado.
            m = re.search(
                r'<div[^>]+class="[^"]*title_blue[^"]*"[^>]*>\s*'
                r'Descripci(?:[oó]|&oacute;)n\s*</div>\s*'
                r'<div[^>]*>(.*?)</div>',
                principal, re.I | re.S)
            visible = limpiar(_texto(m.group(1))) if m else None
            descripcion = visible if visible and len(visible) >= 20 else None
        if not descripcion and crudo.get("wordpress_category_catalog"):
            # En Divi, el contenido de la ficha vive en el unico ``article``
            # y no lleva el rotulo "Descripcion". La URL ya fue cruzada
            # contra categoria, catalogo y REST; por eso es seguro tomar solo
            # ese cuerpo y cortarlo antes de los CTA/footer del sitio.
            article = re.search(r"<article\b[^>]*>(.*?)</article>", principal,
                                re.I | re.S)
            visible = _texto(article.group(1)).strip() if article else ""
            if titulo and visible.lower().startswith(titulo.lower()):
                visible = visible[len(titulo):].lstrip(" :-")
            visible = re.split(
                r"Consultar\s+por\s+esta\s+propiedad|Regresar|"
                r"Encontr[aá]\s+lo\s+que\s+est[aá]s\s+buscando",
                visible, maxsplit=1, flags=re.I)[0]
            descripcion = limpiar(visible) if len(visible.strip()) >= 20 else None
        if not descripcion:
            # Sitios PHP propios usan un separador visual seguido de un unico
            # parrafo enriquecido. La etiqueta explicita acota el contenido y
            # evita tomar menus, contacto o propiedades relacionadas.
            m = re.search(
                r'<div[^>]+class=["\'][^"\']*separador-titulo[^"\']*["\']'
                r'[^>]*>\s*Descripci(?:[oó]|&oacute;)n\s*</div>\s*'
                r'<p[^>]*>(.*?)</p>', principal, re.I | re.S)
            visible = limpiar(_texto(m.group(1))) if m else None
            descripcion = visible if visible and len(visible) >= 20 else None

        precio = mapaprop.get("precio", datos.get("precio"))
        moneda = mapaprop.get("moneda") or datos.get("moneda")
        if precio is None:
            # Solo con moneda explicita al lado. Un numero suelto en el texto
            # puede ser cualquier cosa, y un precio equivocado se publica sin
            # que nadie lo note.
            m = re.search(r"(USD|U\$S|US\$|\$|ARS)\s*([\d][\d.,]{2,15})", texto)
            if m:
                moneda = moneda or detectar_moneda(m.group(1))
                precio = a_numero(m.group(2))

        gallery_images = (_imagenes_galeria_wordpress(principal, url)
                          if crudo.get("wordpress_category_catalog") else
                          mapaprop.get("imagenes") or [])
        image_candidates = (gallery_images if gallery_images else
                            (datos.get("imagenes") or [])
                            + self._imagenes_de(principal, url))
        imagenes, vistas = [], set()
        for u in image_candidates:
            u = identidad_de_imagen(urllib.parse.urljoin(url, u))
            if u in vistas or (not gallery_images and RE_NO_ES_FOTO.search(u)):
                continue
            vistas.add(u)
            imagenes.append(u)
        if crudo.get("wordpress_category_catalog"):
            imagenes = _sin_variantes_wordpress([
                image for image in imagenes
                if not re.search(r"/header-(?:venta|alquiler)(?:[-.])", image, re.I)
            ])

        if crudo.get("por_forma") and not self._confirma_ficha(
                html, texto, precio, imagenes, datos.get("tipo_ld"),
                crudo.get("catalogo_runtime_verificado", False)):
            self.descartadas_por_forma = getattr(self, "descartadas_por_forma", 0) + 1
            # Se guarda cual y con que evidencia. Una url descartada en silencio
            # es indistinguible de una que nunca existio, y si el guardian se
            # equivoca no queda forma de darse cuenta.
            if not hasattr(self, "descartes"):
                self.descartes: list[dict] = []
            if len(self.descartes) < 500:
                self.descartes.append({
                    "canonical_agency_id": fuente.canonical_agency_id,
                    "source_url": url,
                    "patron_ficha": (fuente.extra or {}).get("patron_ficha"),
                    "precio": precio,
                    "tipo_ld": datos.get("tipo_ld"),
                    "operacion_en_texto": bool(RE_OPERACION_TXT.search(texto or "")),
                    "fotos": len(imagenes),
                    "editorial": bool(RE_EDITORIAL.search(html or "")),
                    "titulo": (titulo or "")[:120],
                })
            # Entro por la forma y la pagina no muestra una propiedad. Se
            # descarta en silencio: no es un error de la fuente ni del
            # connector, es la forma alcanzando una pagina que no era ficha.
            return None

        # Recien aca se sacan las fotos de las fichas vecinas. Va DESPUES de
        # confirmar: el guardian de forma exige fotos, y una ficha real cuyas
        # unicas imagenes visibles eran del carrusel de relacionadas quedaria
        # descartada por un filtro nuestro. Se limpia lo que se guarda, no lo
        # que se usa para decidir si la pagina es una propiedad.
        ajenas = {identidad_de_imagen(urllib.parse.urljoin(url, u))
                  for u in imagenes_de_fichas_vecinas(html, url)}
        if ajenas:
            imagenes = [u for u in imagenes
                        if identidad_de_imagen(u) not in ajenas]

        lat, lon = datos.get("lat"), datos.get("lon")
        if lat is None:
            m = RE_COORD.search(html)
            if m:
                lat, lon = float(m.group(1)), float(m.group(2))

        campos = {
            "latitud": lat,
            "longitud": lon,
            "precio": precio,
            "moneda": moneda,
            "operacion": (detectar_operacion(f"{titulo or ''} {url}")
                          or crudo.get("operacion_catalogo")
                          or self._operacion_en_la_ficha(texto_campos)),
            # El tipo tambien puede estar solo en el cuerpo. Se mira el
            # arranque de la ficha: mas abajo empiezan las "propiedades
            # relacionadas" y el tipo del vecino no es el de esta.
            "tipo_propiedad": (detectar_tipo(titulo)
                               or detectar_tipo(urllib.parse.unquote(
                                   urllib.parse.urlparse(url).path)
                                   .replace(".php", " ").replace("-", " "))
                               or detectar_tipo(texto_campos[:300])
                               or self._tipo_en_la_ficha(principal)),
            "dormitorios": None if es_emprendimiento else self._cuenta_de_ficha(
                principal, texto_campos, r"dormitorios?|habitaciones?",
                datos.get("dorm")),
            "banos": None if es_emprendimiento else self._cuenta_de_ficha(
                principal, texto_campos, r"ba[nñ]os?|toilettes?", datos.get("banos")),
            "ambientes": None if es_emprendimiento else self._cuenta_de_ficha(
                principal, texto_campos, r"ambientes?", None),
            "superficie_total": (mapaprop.get("superficie_total")
                                 or datos.get("sup_total")
                                 or self._sup(texto_campos, r"total|terreno")),
            "superficie_cubierta": (mapaprop.get("superficie_cubierta")
                                    or datos.get("sup_cubierta")
                                    or self._sup(texto_campos, r"cubiert|construid")),
        }
        # La aritmetica de inmuebles vive en un modulo aparte: la comparten el
        # connector y la correccion de lo ya extraido, y asi no pueden divergir.
        fuera = revisar(campos)
        lat, lon = campos["latitud"], campos["longitud"]
        precio, moneda = campos["precio"], campos["moneda"]
        descartados = ({"atributos_descartados": ",".join(fuera)} if fuera else {})

        # Un numero sin moneda no es un precio: entre pesos y dolares hay un
        # factor de mil. Se guarda el numero aparte para no perder el dato, y
        # el campo queda vacio en vez de publicar un valor que puede estar mil
        # veces equivocado.
        precio_sin_moneda = None
        if precio is not None and not moneda:
            precio_sin_moneda, precio = precio, None

        estado_fuente = self._estado_fuente(titulo)
        direccion = (mapaprop.get("direccion") or datos.get("direccion")
                     or self._direccion_de(principal))
        if (not direccion and crudo.get("wordpress_category_catalog") and titulo
                and re.search(r"\b\d{2,5}\b", titulo)
                and len(titulo) <= 120):
            # El catalogo usa la direccion publicada como titulo. Solo se
            # conserva cuando hay una altura explicita; un nombre de barrio o
            # desarrollo no se convierte artificialmente en direccion.
            direccion = titulo
        source_fields = None
        if crudo.get("wordpress_category_catalog"):
            source_fields = {
                "titulo": bool(titulo), "descripcion": bool(descripcion),
                "precio": bool(re.search(
                    r"(?:USD|U\$S|US\$|ARS|\$)\s*[\d][\d.,]{2,15}", texto)),
                "moneda": bool(re.search(r"(?:USD|U\$S|US\$|ARS|\$)\s*[\d]", texto)),
                "operacion": bool(crudo.get("operacion_catalogo")),
                "tipo_propiedad": bool(campos["tipo_propiedad"]),
                "direccion": bool(direccion), "barrio": False,
                "ciudad": bool(datos.get("ciudad")),
                "provincia": bool(datos.get("provincia")),
                "ambientes": bool(re.search(r"\b\d+\s+ambientes?\b", texto_campos, re.I)),
                "dormitorios": bool(re.search(r"\b\d+\s+dormitorios?\b", texto_campos, re.I)),
                "banos": bool(re.search(r"\b\d+\s+ba[nñ]os?\b", texto_campos, re.I)),
                "superficie_total": bool(re.search(
                    r"superficie\s+total|terreno\s*:?\s*[\d.,]+\s*m", texto_campos, re.I)),
                "superficie_cubierta": bool(re.search(
                    r"superficie\s+cubierta|cubiert[ao]\s*:?\s*[\d.,]+\s*m",
                    texto_campos, re.I)),
                "latitud": lat is not None, "longitud": lon is not None,
                "imagenes": bool(imagenes),
            }
        elif crudo.get("mapaprop_catalog"):
            source_fields = {
                "titulo": bool(titulo), "descripcion": bool(mapaprop.get("descripcion")),
                "precio": mapaprop.get("precio") is not None,
                "moneda": bool(mapaprop.get("moneda")),
                "operacion": bool(campos["operacion"]),
                "tipo_propiedad": bool(campos["tipo_propiedad"]),
                "direccion": bool(mapaprop.get("direccion")),
                "barrio": bool(mapaprop.get("barrio")),
                "ciudad": bool(mapaprop.get("ciudad")),
                "provincia": bool(mapaprop.get("provincia")),
                "ambientes": bool(re.search(r"\b\d+\s+Ambientes?\b", texto_campos, re.I)),
                "dormitorios": bool(re.search(r"\b\d+\s+dormitorio", texto_campos, re.I)),
                "banos": bool(re.search(r"\b\d+\s+ba[nñ]o", texto_campos, re.I)),
                "superficie_total": bool(re.search(
                    r"\d+(?:[.,]\d+)?\s*m[²2]?\s+de\s+superficie\s+total",
                    texto_campos, re.I)),
                "superficie_cubierta": bool(re.search(
                    r"\d+(?:[.,]\d+)?\s*m[²2]?\s+de\s+superficie\s+cubierta",
                    texto_campos, re.I)),
                "latitud": lat is not None, "longitud": lon is not None,
                "imagenes": bool(mapaprop.get("imagenes")),
            }
        return PropiedadNormalizada(
            canonical_agency_id=fuente.canonical_agency_id,
            source_listing_id=str(crudo["source_listing_id"]),
            source_url=url,
            connector=self.nombre,
            titulo=titulo,
            descripcion=(descripcion or "")[:4000] or None,
            precio=precio,
            moneda=moneda,
            operacion=campos["operacion"],
            tipo_propiedad=campos["tipo_propiedad"],
            direccion=direccion,
            barrio=mapaprop.get("barrio"),
            ciudad=mapaprop.get("ciudad") or datos.get("ciudad"),
            provincia=mapaprop.get("provincia") or datos.get("provincia"),
            latitud=lat,
            longitud=lon,
            dormitorios=campos["dormitorios"],
            banos=campos["banos"],
            ambientes=campos["ambientes"],
            superficie_total=campos["superficie_total"],
            superficie_cubierta=campos["superficie_cubierta"],
            imagenes=imagenes[:40],
            extra={k: v for k, v in {
                                     "via": ("wordpress_category_catalog"
                                             if crudo.get("wordpress_category_catalog")
                                             else "mapaprop_html"
                                             if crudo.get("mapaprop_catalog")
                                             else datos.get("via") or "html"),
                                     "source_fields_provided": source_fields,
                                     "tipo_ld": datos.get("tipo_ld"),
                                     "precio_sin_moneda": precio_sin_moneda,
                                     "estado_fuente": estado_fuente,
                                     **descartados}.items() if v},
            inmobiliaria_id=fuente.inmobiliaria_id,
            provenance={"connector": self.nombre,
                        "official_domain": f"{urllib.parse.urlparse(url).scheme}://"
                                           f"{urllib.parse.urlparse(url).netloc}",
                        "agency_name": fuente.agency_name,
                        "canonical_agency_id": fuente.canonical_agency_id,
                        "source_platform": "SITIO_PROPIO",
                        "pagina_listado": crudo.get("pagina")},
        )

    def _catalogo_php_ajax(self, html: str,
                           base: str) -> dict[str, Any] | None:
        """Detecta el catalogo JSON que hidrata sitios PHP propios.

        La familia se habilita solamente cuando JavaScript del mismo host
        publica conjuntamente el endpoint, los parametros de busqueda y la
        ficha por id. Luego ambas operaciones deben devolver un JSON completo
        y autoconsistente. No se persiste el payload crudo: algunos portales
        legacy exponen campos internos que ERETZ no necesita.
        """
        expected_host = urllib.parse.urlparse(base).netloc.lower().replace(
            "www.", "")
        scripts: list[str] = []
        for src in re.findall(r'<script[^>]+src=["\']([^"\']+)', html or "", re.I):
            url = urllib.parse.urljoin(base + "/", unescape(src))
            parsed = urllib.parse.urlparse(url)
            if parsed.netloc.lower().replace("www.", "") != expected_host:
                continue
            if not parsed.path.lower().endswith(".js") or url in scripts:
                continue
            scripts.append(url)
        # Los bundles de negocio suelen cargarse despues de una docena de
        # vendors. Priorizarlos evita que un tope de cortesia deje afuera
        # precisamente ``main.js`` y certifique cero por orden de tags.
        scripts.sort(key=lambda url: (
            0 if re.search(r"/(?:main|custom|app|search|ficha|config)[^/]*\.js$",
                           urllib.parse.urlparse(url).path, re.I) else 1,
            url,
        ))
        javascript = ""
        for url in scripts[:12]:
            try:
                javascript += "\n" + self.descargador.bajar(url)
            except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                continue
        endpoint_match = re.search(
            r'["\'](?:\.\.?/)*ajax/search\.php["\']', javascript, re.I)
        if (not endpoint_match or "searchParams" not in javascript
                or not re.search(r"ficha\.php\?id=", javascript, re.I)
                or not re.search(r'operacion\s*:\s*["\'][VA]["\']',
                                 javascript, re.I)):
            return None

        endpoint = urllib.parse.urljoin(base + "/", "ajax/search.php")
        allowed = {
            "idcasa", "direccion", "dirreal", "nro", "piso", "dto",
            "moneda", "monto", "comodidad", "mapdir", "latlng",
            "dormitorios", "banos", "ambientes", "autos", "garage",
            "sup_cub", "sup_lote", "sup_total", "lotex", "lotey",
            "val_exp", "descripcion", "subtipo", "localidad", "operacion",
            "fotos", "totalCount",
        }
        rows_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        declared_total = 0
        for operation, currency in (("V", "D"), ("A", "P")):
            body = bajar_formulario(
                self.descargador,
                endpoint,
                {
                    "searchParams[operacion]": operation,
                    "searchParams[orden]": "ASC",
                    "searchParams[moneda]": currency,
                },
                8_000_000,
            )
            try:
                response = json.loads(body)
            except ValueError as error:
                raise ErrorTransitorio(
                    "catalogo PHP AJAX devolvio JSON invalido") from error
            if not isinstance(response, list):
                return None
            declared = None
            for raw in response:
                if not isinstance(raw, dict):
                    return None
                listing_id = str(raw.get("idcasa") or "")
                row_operation = str(raw.get("operacion") or "").upper()
                if (not listing_id.isdigit() or row_operation != operation
                        or not isinstance(raw.get("fotos") or [], list)):
                    return None
                row_total = raw.get("totalCount")
                if str(row_total or "").isdigit():
                    declared = int(row_total)
                sanitized = {key: raw[key] for key in allowed if key in raw}
                rows_by_key[(listing_id, operation)] = sanitized
            if declared is not None and declared != len(response):
                return None
            declared_total += declared if declared is not None else len(response)
        if len(rows_by_key) < 3 or declared_total != len(rows_by_key):
            return None
        return {"rows": list(rows_by_key.values()), "total": declared_total}

    def _normalizar_bitrix_landing(self, crudo: dict,
                                   fuente: Fuente) -> PropiedadNormalizada:
        """Normaliza una tarjeta de landing de Bitrix24.

        La fuente publica poco y hay que resistir la tentacion de completar el
        resto. Lo que no esta en la tarjeta queda en None: ni ambientes, ni
        superficie, ni ubicacion. La operacion solo se afirma cuando el
        subtitulo la dice ("Valor de Venta"); un lote sin esa leyenda queda sin
        operacion antes que con una supuesta.
        """
        row = dict(crudo.get("bitrix_card") or {})
        titulo = limpiar(str(row.get("titulo") or "")) or None
        descripcion = limpiar(str(row.get("descripcion") or "")) or None

        precio_texto = str(row.get("precio_texto") or "")
        precio = a_numero(precio_texto)
        if precio is not None and precio <= 0:
            precio = None
        moneda = detectar_moneda(precio_texto) if precio is not None else None

        # El subtitulo es el unico lugar donde la fuente declara la operacion.
        # El titulo la insinua a veces ("LOTE EN...") pero insinuar no alcanza.
        subtitulo = str(row.get("subtitulo") or "")
        operacion = detectar_operacion(subtitulo)
        tipo = detectar_tipo(" ".join(p for p in (titulo, descripcion) if p))

        return PropiedadNormalizada(
            canonical_agency_id=fuente.canonical_agency_id,
            source_listing_id=str(crudo["source_listing_id"]),
            source_url=str(crudo["source_url"]),
            connector="generico",
            titulo=titulo, descripcion=descripcion,
            precio=precio, moneda=moneda,
            operacion=operacion, tipo_propiedad=tipo,
            imagenes=list(row.get("imagenes") or []),
            extra={"plataforma": "BITRIX24_LANDING",
                   "pagina_de_origen": crudo["source_url"].split("?")[0],
                   # La fuente no publica ficha individual: el parametro de la
                   # URL lo agregamos nosotros para distinguir una tarjeta de
                   # otra, no es una direccion que el sitio publique.
                   "url_de_ficha_sintetica": True,
                   "identificador_de_origen": row.get("file_id"),
                   "precio_publicado": precio_texto or None,
                   "subtitulo_publicado": limpiar(subtitulo) or None},
        )

    def _normalizar_php_ajax(self, crudo: dict,
                             fuente: Fuente) -> PropiedadNormalizada:
        """Normaliza exclusivamente el payload publico del catalogo oficial."""
        row = dict(crudo.get("php_ajax") or {})

        def number(*names: str) -> float | None:
            for name in names:
                parsed = a_numero(row.get(name))
                if parsed is not None:
                    return parsed
            return None

        def count(*names: str) -> int | None:
            value = number(*names)
            return int(value) if value is not None and 0 < value <= 99 else None

        operation_code = str(row.get("operacion") or "").upper()
        operation = {"V": "venta", "A": "alquiler"}.get(operation_code)
        price = number("monto")
        if price is not None and price <= 0:
            price = None
        currency = detectar_moneda(str(row.get("moneda") or "")) if price else None
        latitude = longitude = None
        coordinates = str(row.get("latlng") or "")
        match = re.fullmatch(
            r"\s*(-?\d{1,3}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*",
            coordinates)
        if match:
            latitude, longitude = float(match.group(1)), float(match.group(2))

        address = limpiar(str(row.get("dirreal") or row.get("direccion") or ""))
        number_value = limpiar(str(row.get("nro") or ""))
        if address and number_value and number_value.lower() not in address.lower():
            address = f"{address} {number_value}"
        subtype = limpiar(str(row.get("subtipo") or ""))
        locality = limpiar(str(row.get("localidad") or ""))
        operation_label = "Venta" if operation == "venta" else "Alquiler"
        title_parts = [subtype, f"en {operation_label}" if operation else None,
                       f"en {address}" if address else None,
                       f"de {locality}" if locality else None]
        title = " ".join(part for part in title_parts if part) or None
        description = limpiar(str(row.get("comodidad") or "")) or None
        images: list[str] = []
        for raw_image in row.get("fotos") or []:
            image = identidad_de_imagen(urllib.parse.urljoin(
                crudo["source_url"], str(raw_image)))
            if image not in images and not NO_ES_FOTO.search(image):
                images.append(image)

        normalized_subtype = unicodedata.normalize("NFKD", subtype.lower())
        normalized_subtype = "".join(
            character for character in normalized_subtype
            if not unicodedata.combining(character))
        local_types = {
            "triplex": "casa", "piso": "departamento",
            "hectarea": "terreno", "hotel": "otro",
        }
        property_type = detectar_tipo(normalized_subtype)
        if property_type is None:
            for label, canonical in local_types.items():
                if re.search(rf"\b{label}\b", normalized_subtype):
                    property_type = canonical
                    break
        fields = {
            "latitud": latitude,
            "longitud": longitude,
            "precio": price,
            "moneda": currency,
            "operacion": operation,
            "tipo_propiedad": property_type,
            "dormitorios": count("dormitorios"),
            "banos": count("banos"),
            "ambientes": count("ambientes"),
            "superficie_total": number("sup_total", "sup_lote"),
            "superficie_cubierta": number("sup_cub"),
        }
        discarded = revisar(fields)
        source_fields = {
            "titulo": title is not None,
            "descripcion": description is not None,
            "precio": price is not None,
            "moneda": currency is not None,
            "operacion": operation is not None,
            "tipo_propiedad": bool(subtype),
            "direccion": bool(address),
            "barrio": False,
            "ciudad": bool(locality),
            "provincia": bool((fuente.extra or {}).get("province")),
            "ambientes": fields["ambientes"] is not None,
            "dormitorios": fields["dormitorios"] is not None,
            "banos": fields["banos"] is not None,
            "superficie_total": fields["superficie_total"] is not None,
            "superficie_cubierta": fields["superficie_cubierta"] is not None,
            "latitud": latitude is not None,
            "longitud": longitude is not None,
            "imagenes": bool(images),
        }
        extra = {
            "via": "php_ajax_search",
            "source_fields_provided": source_fields,
            "expensas": number("val_exp"),
        }
        if discarded:
            extra["atributos_descartados"] = ",".join(discarded)
        url = crudo["source_url"]
        return PropiedadNormalizada(
            canonical_agency_id=fuente.canonical_agency_id,
            source_listing_id=str(crudo["source_listing_id"]),
            source_url=url, connector=self.nombre,
            titulo=title, descripcion=description,
            precio=fields["precio"], moneda=fields["moneda"],
            operacion=fields["operacion"],
            tipo_propiedad=fields["tipo_propiedad"],
            direccion=address or None,
            ciudad=locality or (fuente.extra or {}).get("city"),
            provincia=(fuente.extra or {}).get("province"),
            latitud=fields["latitud"], longitud=fields["longitud"],
            dormitorios=fields["dormitorios"], banos=fields["banos"],
            ambientes=fields["ambientes"],
            superficie_total=fields["superficie_total"],
            superficie_cubierta=fields["superficie_cubierta"],
            imagenes=images[:40], extra=extra,
            inmobiliaria_id=fuente.inmobiliaria_id,
            provenance={"connector": self.nombre,
                        "official_domain": (
                            f"{urllib.parse.urlparse(url).scheme}://"
                            f"{urllib.parse.urlparse(url).netloc}"),
                        "agency_name": fuente.agency_name,
                        "canonical_agency_id": fuente.canonical_agency_id,
                        "source_platform": "PHP_AJAX_SEARCH",
                        "pagina_listado": crudo.get("pagina")},
        )

    def _normalizar_xintel(self, crudo: dict, fuente: Fuente,
                           html: str) -> PropiedadNormalizada:
        """Normaliza la API estructurada que hidrata las fichas Xintel."""
        row = dict(crudo.get("xintel") or {})

        def script_value(name: str) -> str | None:
            match = re.search(
                rf'["\']{re.escape(name)}["\']\s*:\s*["\']([^"\']+)["\']',
                html, re.I)
            return match.group(1) if match else None

        detail_params = {name: script_value(name)
                         for name in ("suc", "global", "apiK", "id")}
        images = [row.get("img_princ")] if row.get("img_princ") else []
        province = None
        if all(detail_params.values()):
            query = urllib.parse.urlencode({
                "json": "fichas.propiedades",
                "suc": detail_params["suc"],
                "global": detail_params["global"],
                "apiK": detail_params["apiK"],
                "id": detail_params["id"],
                "compartida": "false",
            })
            body = self.descargador.bajar("https://xintelapi.com.ar/?" + query)
            try:
                result = (json.loads(body).get("resultado") or {})
            except ValueError as error:
                raise ErrorTransitorio("Xintel devolvio detalle JSON invalido") from error
            details = result.get("ficha") or []
            if details and isinstance(details[0], dict):
                row.update(details[0])
            if isinstance(result.get("img"), list):
                images = result["img"]
            province = result.get("provincia")

        def number(*names: str) -> float | None:
            for name in names:
                value = row.get(name)
                parsed = a_numero(value)
                if parsed is not None:
                    return parsed
            return None

        def count(*names: str) -> int | None:
            value = number(*names)
            return int(value) if value is not None and 0 < value <= 99 else None

        price_text = str(row.get("precio") or "")
        price_match = re.search(r"(U\$S|USD|ARS|\$)\s*([\d.,]+)", price_text, re.I)
        currency = detectar_moneda(price_match.group(1)) if price_match else None
        price = a_numero(price_match.group(2)) if price_match else None
        fields = {
            "latitud": number("latitud", "in_lat"),
            "longitud": number("longitud", "in_lon"),
            "precio": price,
            "moneda": currency,
            "operacion": detectar_operacion(str(row.get("operacion") or "")),
            "tipo_propiedad": (detectar_tipo(str(
                row.get("tipo") or row.get("titulo") or ""))
                or ("local" if re.search(
                    r"\b(?:negocio|comercio)\b",
                    str(row.get("tipo") or row.get("titulo") or ""), re.I)
                    else None)),
            "dormitorios": count("cantidad_dormitorios"),
            "banos": count("cantidad_banos", "in_ban", "in_bao"),
            "ambientes": count("cantidad_ambientes"),
            "superficie_total": number("in_sto", "in_sut", "in_sup"),
            "superficie_cubierta": number("in_cub"),
        }
        discarded = revisar(fields)
        clean_images = []
        seen = set()
        for image in images:
            if not image:
                continue
            current = identidad_de_imagen(str(image))
            if current in seen or NO_ES_FOTO.search(current):
                continue
            seen.add(current)
            clean_images.append(current)
        description = row.get("in_des")
        if str(description).lower() in {"", "false", "none", "null"}:
            description = None
        url = crudo["source_url"]
        source_fields = {
            "titulo": bool(row.get("titulo")),
            "descripcion": bool(description),
            "precio": price is not None,
            "moneda": currency is not None,
            "operacion": bool(row.get("operacion")),
            "tipo_propiedad": bool(row.get("tipo") or row.get("titulo")),
            "direccion": bool(row.get("direccion_completa")),
            "barrio": bool(row.get("in_bar")),
            "ciudad": bool(row.get("in_loc")),
            "provincia": bool(province),
            "ambientes": count("cantidad_ambientes") is not None,
            "dormitorios": count("cantidad_dormitorios") is not None,
            "banos": count("cantidad_banos", "in_ban", "in_bao") is not None,
            "superficie_total": number("in_sto", "in_sut", "in_sup") is not None,
            "superficie_cubierta": number("in_cub") is not None,
            "latitud": number("latitud", "in_lat") is not None,
            "longitud": number("longitud", "in_lon") is not None,
            "imagenes": bool(clean_images),
        }
        return PropiedadNormalizada(
            canonical_agency_id=fuente.canonical_agency_id,
            source_listing_id=str(crudo["source_listing_id"]),
            source_url=url,
            connector=self.nombre,
            titulo=limpiar(str(row.get("titulo") or "")) or None,
            descripcion=limpiar(str(description))[:4000] if description else None,
            precio=fields["precio"], moneda=fields["moneda"],
            operacion=fields["operacion"], tipo_propiedad=fields["tipo_propiedad"],
            direccion=limpiar(str(row.get("direccion_completa") or "")) or None,
            barrio=limpiar(str(row.get("in_bar") or "")) or None,
            ciudad=limpiar(str(row.get("in_loc") or "")) or None,
            provincia=limpiar(str(province or "")) or None,
            latitud=fields["latitud"], longitud=fields["longitud"],
            dormitorios=fields["dormitorios"], banos=fields["banos"],
            ambientes=fields["ambientes"],
            superficie_total=fields["superficie_total"],
            superficie_cubierta=fields["superficie_cubierta"],
            imagenes=clean_images[:40],
            extra={"via": "xintel_api", "source_fields_provided": source_fields, **(
                {"atributos_descartados": ",".join(discarded)} if discarded else {})},
            inmobiliaria_id=fuente.inmobiliaria_id,
            provenance={"connector": self.nombre,
                        "official_domain": (f"{urllib.parse.urlparse(url).scheme}://"
                                            f"{urllib.parse.urlparse(url).netloc}"),
                        "agency_name": fuente.agency_name,
                        "canonical_agency_id": fuente.canonical_agency_id,
                        "source_platform": "XINTEL",
                        "pagina_listado": crudo.get("pagina")},
        )

    @staticmethod
    def _imagenes_de(html: str, url: str) -> list[str]:
        """Las fotos de la ficha, esten escritas como esten.

        Mirar solo urls absolutas dejaba en cero a los sitios que sirven
        sus fotos con ruta relativa -<img src="/imagenes/494/IMG.jpg">-, que
        son muchos. Una fuente perdio 268 fichas reales por eso: el guardian
        las veia sin una sola foto, y las que si entraban entraban sin
        galeria.
        """
        crudas = list(RE_IMG.findall(html or ""))
        for m in RE_IMG_ATRIBUTO.finditer(html or ""):
            crudas.append(m.group(1).split()[0] if m.group(1).strip() else "")
        salida, vistas = [], set()
        for u in crudas:
            if not u:
                continue
            u = identidad_de_imagen(urllib.parse.urljoin(url, unescape(u.strip())))
            if not RE_EXTENSION.search(u):
                continue
            if u in vistas or RE_NO_ES_FOTO.search(u):
                continue
            vistas.add(u)
            salida.append(u)
        return salida

    @staticmethod
    def _direccion_de(html: str) -> str | None:
        """Direccion visible de la ficha cuando el JSON-LD la omite.

        Solo acepta el bloque estructural de direccion del cuerpo principal.
        Un icono, el mapa o una direccion de relacionadas no alcanzan.
        """
        for bloque in re.findall(
                r"<p[^>]+class=[\"'][^\"']*direccion[^\"']*[\"'][^>]*>"
                r"(.*?)</p>", html or "", re.I | re.S):
            texto = limpiar(_texto(bloque))
            if texto and len(texto) >= 4:
                return texto
        return None

    @staticmethod
    def _titulo_de_la_ficha(html: str, datos: dict, fuente: Fuente) -> str | None:
        """El titulo de la propiedad, no el de la inmobiliaria.

        Varios sitios ponen el mismo og:title en todas sus paginas -"Altura
        Propiedades"- y con eso el tipo de propiedad queda en blanco: no hay de
        donde leerlo. El h1 de la ficha, en cambio, dice "Local en Belgrano".

        Se prueban las fuentes en orden y se descarta la que sea solamente el
        nombre de la inmobiliaria.
        """
        candidatos = [datos.get("titulo")]
        for patron in (r'<meta[^>]+property="og:title"[^>]+content="([^"]{1,200})"',
                       r"<h1[^>]*>(.{3,200}?)</h1>",
                       r"<title[^>]*>(.{1,200}?)</title>"):
            m = re.search(patron, html, re.S | re.I)
            if m:
                candidatos.append(limpiar(unescape(re.sub(r"<[^>]+>", " ", m.group(1)))))

        agencia = (fuente.agency_name or "").lower().strip()
        for c in candidatos:
            if not c:
                continue
            limpio = re.split(r"\s*[|–—]\s*", c)[0].strip()
            if agencia and limpio.lower() in (agencia, agencia.replace("  ", " ")):
                continue          # es el nombre de la inmobiliaria, no la ficha
            return c
        return next((c for c in candidatos if c), None)

    @staticmethod
    def _operacion_en_la_ficha(texto: str) -> str | None:
        """La operacion cuando el titulo y la url no la dicen.

        Un tercio de las fichas de sitios propios titulan "Departamento 2
        ambientes" y nada mas. El cuerpo si lo dice, pero el menu de la pagina
        tambien -"Ventas | Alquileres"-, asi que solo se acepta cuando aparece
        UNA de las dos operaciones en el arranque de la ficha. Si aparecen las
        dos, la pagina no esta diciendo cual es: se deja vacio antes que elegir.
        """
        # Un rotulo explicito manda, este donde este: "Operacion: Venta" no se
        # puede confundir con el menu.
        rotulo = re.search(r"operaci[oó]n\s*:?\s*(venta|alquiler|"
                           r"alquiler temporario)", texto or "", re.I)
        if rotulo:
            return rotulo.group(1).lower().replace(" ", "_")

        if re.search(r"\balquiler\s+inicial\b", texto or "", re.I):
            return "alquiler"
        # El estado consumado conserva la semantica de la operacion aunque el
        # aviso ya no publique precio: "Alquilada" no debe quedar sin tipo de
        # operacion. "Reservado" solo no alcanza porque puede ser venta o renta.
        if re.search(r"\balquilad[oa]\b", texto or "", re.I):
            return "alquiler"
        if re.search(r"\bvendid[oa]\b", texto or "", re.I):
            return "venta"

        arranque = (texto or "")[:600].lower()
        venta = bool(re.search(r"\b(en venta|se vende|venta)\b", arranque))
        alquiler = bool(re.search(r"\b(en alquiler|se alquila|alquiler)\b", arranque))
        if venta == alquiler:
            return None
        if alquiler and re.search(r"\b(temporario|temporal)\b", arranque):
            return "alquiler_temporario"
        return "venta" if venta else "alquiler"

    @staticmethod
    def _confirma_ficha(html: str, texto: str, precio, imagenes: list,
                        tipo_ld: str | None = None,
                        catalogo_verificado: bool = False) -> bool:
        """La pagina publica una propiedad: operacion, fotos y precio o schema.

        Es el mismo criterio con el que se verificaron las formas antes de
        habilitarlas, aplicado ahora ficha por ficha: precio o schema, Y
        operacion o dos atributos, Y fotos.

        Pedir la operacion SIEMPRE costo 21 fichas reales de una sola
        fuente -"Casa en 2 plantas con piscina", 210.000 dolares, 190
        fotos- que publican la operacion en un rotulo que no queda en el
        texto. Dos atributos alcanzan para saber que la pagina describe
        un inmueble, y asi lo decia la regla con la que se verificaron
        las 283 paginas. Sobre las 283 paginas que
        se bajaron para verificar, acepta el 96,9% de las que venian de una
        forma confirmada y solo el 4,5% de las que venian de una forma
        descartada.

        Se acepta tambien la ficha que declara un inmueble en schema.org sin
        precio: "consultar precio" es una propiedad publicada, no una nota, y el
        tipo de schema.org lo dice con la misma claridad que el precio. Sobre
        esas 283 paginas la concesion no admitio ninguna pagina de mas.
        """
        # Algunos portales legacy etiquetan todas sus fichas como
        # ``og:type=article``. Esa declaracion sigue bloqueando formas amplias,
        # pero no debe invalidar una URL que vino de un catalogo inmobiliario
        # paginado y verificado en runtime.
        if RE_EDITORIAL.search(html or "") and not catalogo_verificado:
            return False
        t = texto or ""
        describe = (bool(RE_OPERACION_TXT.search(t))
                    or len({x.lower() for x in RE_ATRIBUTOS_TXT.findall(t)}) >= 2)
        fotos_suficientes = (len(imagenes) >= FOTOS_MINIMAS
                             or (catalogo_verificado and len(imagenes) >= 1))
        return ((precio is not None or bool(tipo_ld) or catalogo_verificado) and describe
                and fotos_suficientes)

    @staticmethod
    def _estado_fuente(titulo: str | None) -> str | None:
        inicio = (titulo or "").strip().lower()
        for estado in ("reservado", "reservada", "vendido", "vendida",
                       "alquilado", "alquilada"):
            if inicio.startswith(estado):
                return estado
        return None

    # --------------------------------------------------------------- schema.org
    @staticmethod
    def _de_json_ld(html: str) -> dict[str, Any]:
        """Lo que schema.org publica ya tipado.

        Cuando esta, gana sobre cualquier heuristica de texto: es un contrato
        publico, no una convencion visual que cambia con el tema del sitio.
        """
        out: dict[str, Any] = {}
        for bloque in RE_LD.findall(html):
            try:
                # Algunos proveedores emiten saltos de linea literales dentro
                # de strings JSON-LD. Son invalidos bajo strict=True pero el
                # resto del objeto sigue siendo JSON inequívoco y publico.
                dato = json.loads(bloque.strip(), strict=False)
            except ValueError:
                continue
            for nodo in _aplanar_ld(dato):
                tipo = str(nodo.get("@type") or "")
                if tipo and not re.search(
                        r"(Residence|Apartment|House|Product|Offer|RealEstate|"
                        r"SingleFamily|Place|Accommodation)", tipo, re.I):
                    continue
                out.setdefault("tipo_ld", tipo or None)
                out.setdefault("via", "json-ld")
                if not out.get("titulo"):
                    out["titulo"] = limpiar(nodo.get("name"))
                if not out.get("descripcion"):
                    out["descripcion"] = limpiar(nodo.get("description"))
                oferta = nodo if "price" in nodo else (nodo.get("offers") or {})
                if isinstance(oferta, list):
                    oferta = oferta[0] if oferta else {}
                if isinstance(oferta, dict):
                    if out.get("precio") is None:
                        out["precio"] = a_numero(oferta.get("price"))
                    if not out.get("moneda"):
                        m = (oferta.get("priceCurrency") or "").upper().strip()
                        out["moneda"] = m if m in ("ARS", "USD") else None
                dire = nodo.get("address")
                if isinstance(dire, dict):
                    out.setdefault("direccion", limpiar(dire.get("streetAddress")))
                    out.setdefault("ciudad", limpiar(dire.get("addressLocality")))
                    out.setdefault("provincia", limpiar(dire.get("addressRegion")))
                geo = nodo.get("geo")
                if isinstance(geo, dict) and out.get("lat") is None:
                    try:
                        out["lat"] = float(geo.get("latitude"))
                        out["lon"] = float(geo.get("longitude"))
                    except (TypeError, ValueError):
                        pass
                img = nodo.get("image")
                if img:
                    urls = img if isinstance(img, list) else [img]
                    out.setdefault("imagenes", [u for u in urls if isinstance(u, str)])
        for k in ("lat", "lon"):
            v = out.get(k)
            if v is not None and not (-74 <= v <= -21):
                out[k] = None
        return out

    @staticmethod
    def _cuenta(texto: str, etiqueta: str, previo: Any) -> int | None:
        if previo:
            try:
                n = int(previo)
                return n if 1 <= n <= 99 else None
            except (TypeError, ValueError):
                pass
        # Un rotulo con dos puntos no admite ambiguedad y manda sobre todo lo
        # demas. En una ficha real ``baño sauna ... Ambientes: 5 Dormitorios: 4
        # Baños: 5`` buscar el numero ANTES del rotulo tomaba el 5 de
        # ambientes como dormitorios y el 4 como baños.
        for rotulo in re.finditer(
                rf"(?:{etiqueta})\s*:\s*(\d{{1,2}})\b", texto, re.I):
            if 1 <= int(rotulo.group(1)) <= 99:
                return int(rotulo.group(1))
        # Sin dos puntos la adyacencia es ambigua y hay que resolverla mirando
        # la ficha entera: "Ambientes 3 Dormitorios 2" es una tabla y el numero
        # va DESPUES del rotulo; "3 dormitorios 2 baños" es prosa y va ANTES.
        # Elegir mal no deja el campo vacio: le pone el numero del campo
        # vecino, que parece correcto y despues no se distingue de un dato
        # real. Antes se leia siempre como prosa, y las fichas con tabla
        # quedaban con los valores corridos un lugar.
        if GenericoConnector._es_tabla_de_atributos(texto):
            hallazgo = re.search(
                rf"(?:{etiqueta})\s*(\d{{1,2}})\b", texto, re.I)
        else:
            # Cero en los CMS suele ser placeholder, no una afirmacion de que
            # la propiedad carece del atributo. Si la descripcion publica una
            # cantidad positiva explicita, se conserva; los filtros del
            # catalogo ya fueron excluidos del auditor.
            #
            # El limite de palabra evita leer el "2" de "196 m2 Ambientes"
            # como si fuera la cantidad de ambientes.
            hallazgo = re.search(
                rf"\b([1-9]\d?)\s*(?:{etiqueta})", texto, re.I)
        if not hallazgo:
            return None
        valor = int(hallazgo.group(1))
        return valor if 1 <= valor <= 99 else None

    @staticmethod
    def _es_tabla_de_atributos(texto: str) -> bool:
        """Si la ficha lista los atributos como ``Rotulo N`` y no como prosa.

        Se decide una vez por ficha y con TODOS los rotulos conocidos, no con
        el que se esta leyendo: un solo campo no alcanza para distinguir los
        dos formatos, y equivocarse corre todos los valores un lugar.
        """
        despues = len(re.findall(
            rf"(?:{ETIQUETAS_ATRIBUTO})\s*\d{{1,2}}\b", texto, re.I))
        antes = len(re.findall(
            rf"\b[1-9]\d?\s*(?:{ETIQUETAS_ATRIBUTO})", texto, re.I))
        return despues > antes

    @staticmethod
    def _mismo_sitio(url: str, base: str) -> bool:
        """Si la url pertenece al sitio de la inmobiliaria.

        El sitemap de requenapropiedades.com.ar publica sus fichas como
        `http://requenav2.test/propiedad/...`: el hostname local del
        desarrollador quedo publicado en produccion. Esas urls no responden,
        pero el problema mayor es el otro: si respondieran, cada propiedad
        quedaria guardada con identidad y enlace en un host que no es el de la
        inmobiliaria, porque `hash_dedup` se calcula sobre la url normalizada.

        Los subdominios propios si entran: una ficha en
        `fichas.inmobiliaria.com.ar` sigue siendo de esa inmobiliaria.
        """
        def host(valor: str) -> str:
            neto = urllib.parse.urlparse(valor).netloc.lower()
            return neto[4:] if neto.startswith("www.") else neto

        propio, ajeno = host(base), host(url)
        if not ajeno:
            return True
        if not propio:
            return False
        return (ajeno == propio or ajeno.endswith("." + propio)
                or propio.endswith("." + ajeno))

    @staticmethod
    def _tipo_en_la_ficha(html: str) -> str | None:
        """El tipo declarado en su propio elemento, como chip de categoria.

        El titulo no siempre lo dice: "3 AMBIENTES AL FRENTE" describe el aviso
        sin nombrar que es. La ficha igual lo publica en un <li> o <span> cuyo
        contenido es solo el tipo, y no leerlo dejaba 35 de 193 avisos de una
        inmobiliaria sin el campo que decide si la propiedad se puede publicar.

        Si aparece MAS DE UN tipo distinto no se afirma ninguno: eso es el menu
        de categorias del sitio -"Casas", "Departamentos", "Terrenos"-, no la
        etiqueta de esta ficha, y elegir el primero le pondria a cada aviso el
        tipo que figure mas arriba en la navegacion.
        """
        tipos = set()
        for match in re.finditer(
                r"<(?:li|span)[^>]*>\s*([^<>]{3,24}?)\s*</(?:li|span)>",
                html or "", re.I):
            texto = match.group(1).strip()
            # Un elemento con una frase es texto de la ficha, no una etiqueta.
            if len(texto.split()) > 2:
                continue
            tipo = detectar_tipo(texto)
            if tipo:
                tipos.add(tipo)
        return tipos.pop() if len(tipos) == 1 else None

    @staticmethod
    def _cuenta_de_ficha(html: str, texto: str, etiqueta: str,
                         previo: Any) -> int | None:
        """Prioriza la pareja label/valor estructural de portales legacy."""
        marcado = normalizar_texto_campos(unescape(html or ""))
        rotulo = re.search(
            rf'<div[^>]+class=["\'][^"\']*desc[^"\']*["\'][^>]*>\s*'
            rf'(?:{etiqueta})\s*</div>\s*'
            rf'<div[^>]+class=["\'][^"\']*valor[^"\']*["\'][^>]*>\s*'
            rf'(\d{{1,2}})\b', marcado, re.I)
        if rotulo and 1 <= int(rotulo.group(1)) <= 99:
            return int(rotulo.group(1))
        rotulo = re.search(
            rf'(?:{etiqueta})\s*'
            rf'<span[^>]+class=["\'][^"\']*number[^"\']*["\'][^>]*>\s*'
            rf'(\d{{1,2}})\b', marcado, re.I)
        if rotulo and 1 <= int(rotulo.group(1)) <= 99:
            return int(rotulo.group(1))
        # La forma general de una fila de atributos, sin depender del nombre
        # de la clase: un elemento que contiene SOLO el rotulo, seguido de otro
        # que contiene SOLO el numero. Aqui no hay ambiguedad -la estructura
        # dice que valor pertenece a que rotulo-, mientras que sobre el texto
        # aplanado "Ambientes 3 Dormitorios 2" y "3 dormitorios 2 baños" se ven
        # iguales y elegir mal corre todos los valores un lugar.
        celda = r"(?:span|div|dd|dt|td|li|p|b|strong)"
        rotulo = re.search(
            rf"<{celda}[^>]*>\s*(?:{etiqueta})\s*</{celda}>\s*"
            rf"<{celda}[^>]*>\s*(\d{{1,2}})\s*</{celda}>", marcado, re.I)
        if rotulo and 1 <= int(rotulo.group(1)) <= 99:
            return int(rotulo.group(1))
        return GenericoConnector._cuenta(texto, etiqueta, previo)

    @staticmethod
    def _sup(texto: str, etiqueta: str) -> float | None:
        m = re.search(rf"(?:{etiqueta})[^\d]{{0,18}}([\d.,]{{2,9}})\s*m", texto, re.I) or \
            re.search(rf"([\d.,]{{2,9}})\s*m[²2]\s*(?:{etiqueta})", texto, re.I)
        if not m:
            return None
        v = a_numero(m.group(1))
        return v if v and 5 <= v <= 100_000 else None
