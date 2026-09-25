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
from .texto import normalizar_campos, sin_bloques_no_textuales
from .formularios import bajar_formulario
from .base import (Bloqueado, Connector, ErrorPermanente, ErrorTransitorio,
                   Fuente, PropiedadNormalizada, a_numero, detectar_moneda,
                   detectar_operacion, detectar_tipo, identidad_de_imagen,
                   imagenes_de_fichas_vecinas, limpiar)

# Familias de atributo que un rotulo puede fundir. Si una celda nombra dos, el
# numero que la sigue no se puede asignar a ninguna.
ETIQUETAS_ATRIBUTO_COMPUESTO = (
    r"dormitorios?|habitaciones?|ambientes?|ba[nñ]os?|cocheras?|garages?")

# Los atributos numericos que una ficha suele tabular. Sirven para decidir si
# la pagina los presenta como ``Rotulo N`` o como prosa.
ETIQUETAS_ATRIBUTO = (r"ambientes?|dormitorios?|habitaciones?|ba[nñ]os?"
                      r"|cocheras?|toilettes?")

# El rotulo con el que cada atributo contable se publica. Vive aca, y no en el
# auditor, para que la senal de fuente y la extraccion no puedan quedar leyendo
# etiquetas distintas para el mismo campo.
# Las etiquetas son PALABRAS ENTERAS. Sin los limites, `ambientes?` matchea
# adentro de "Monoambiente", y en `benitezullo.com.ar` el primer "ambiente" del
# cuerpo esta en un `<meta og:title content="Departamento Monoambiente...">`:
# el lector se quedaba ahi y devolvia nada, con el `<li>Ambientes <span>1</span>`
# a la vista mas abajo. `Banos` funcionaba solo porque no aparece en ningun
# meta.
#
# "Monoambiente", "semiambiente" y "subambiente" no son la etiqueta
# "Ambientes": son el tipo de propiedad.
ETIQUETAS_DE_CONTEO = {
    "dormitorios": r"\b(?:dormitorios?|habitaciones?)\b",
    "banos": r"\b(?:ba[nñ]os?|toilettes?)\b",
    "ambientes": r"\bambientes?\b",
}

# Rutas donde un frontend propio suele exponer el catalogo Tokko.
RUTAS_TOKKO_PROXY = ("/api/tokko/properties", "/api/properties",
                     "/api/tokko/property")

# Cuantas paginas de categoria se recorren. El menu de una inmobiliaria
# tiene pocas; mas que esto es recorrer el sitio entero de un tercero.
MAX_CATEGORIAS = 12

# Paginado del proxy Tokko y tope de seguridad.
PAGINA_TOKKO_PROXY = 50
TOPE_TOKKO_PROXY = 5000
# Cuantas veces se repite el barrido completo. Cuatro es el mismo numero que
# usa `connectors/tokko.py` contra la misma API, y por la misma razon: el
# conjunto viene reordenado entre pedidos.
MAX_BARRIDOS_TOKKO_PROXY = 4

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
# Algunas plataformas intercalan un segmento antes del id:
# /propiedad/detalle/104/GARCIA-Y-RAFAELA. El patron general exige que el id
# venga pegado a la palabra clave, asi que esas fichas quedaban invisibles y el
# sitio se reportaba sin inventario.
#
# Se pide un segmento NUMERICO seguido del slug, no cualquier ruta anidada: un
# catalogo como /propiedades/venta/casas no tiene numero y no entra.
RE_FICHA_ANIDADA = re.compile(
    r"/(?:propiedad(?:es)?|inmueble[s]?|ficha[s]?|listing[s]?|propert(?:y|ies))/"
    r"(?:[a-z0-9-]+/)?\d{2,}/[^/?#]+/?$", re.I)

# La operacion adelante y la ficha al fondo:
# /venta/casa/martinez/cordoba-al-2900-martinez-casa-en-lote-propio-3-ambientes
# `RE_FICHA` ya conoce `venta` y `alquiler` como seccion, pero exige que la
# ficha cuelgue DIRECTAMENTE de ahi, y estos sitios intercalan tipo y zona.
# `andradeinmobiliaria.com.ar` publica dos propiedades y figuraba sin
# inventario; el corte por lote lo delato al repetirse la firma.
#
# El slug final tiene que tener cuatro o mas palabras: con menos, la ruta es
# una categoria -/venta/casa/martinez- y tomarla por ficha inventaria
# propiedades que no existen.
# Paginas que sirve el HOSTING cuando el sitio dejo de existir: cuenta
# suspendida, dominio en venta, dominio vencido. No son la web de una
# inmobiliaria sin propiedades: son la ausencia de la web.
#
# `ventasprop.com` devuelve "Account Suspended" con ciento veinte caracteres
# de texto. Quedaba en NEEDS_FIX para siempre, esperando un arreglo nuestro
# que no existe, cuando lo que corresponde decir es que la fuente ya no
# publica.
#
# Y no siempre es el hosting: la PLATAFORMA tambien da de baja la pagina de su
# cliente y sirve su propio aviso en el dominio de la inmobiliaria.
# `alderinmobiliaria.com` devuelve 866 bytes que dicen "Pagina no disponible en
# Wasi - La pagina que solicitaste no existe o no se encuentra disponible". Eso
# no es una variante que no sepamos leer: es una fuente que dejo de publicar.
#
# Estas formas son mas generales que las de arriba y por eso dependen del tope
# de texto: un sitio vivo nunca tiene menos de 600 caracteres visibles.
RE_FUERA_DE_SERVICIO = re.compile(
    r"account\s+suspended|cuenta\s+suspendida|this\s+domain\s+(?:is\s+)?"
    r"(?:for\s+sale|has\s+expired)|dominio\s+(?:en\s+venta|expirado)|"
    r"site\s+temporarily\s+unavailable|suspended\s+account|"
    r"p[aá]gina\s+no\s+disponible|no\s+se\s+encuentra\s+disponible|"
    r"page\s+(?:is\s+)?(?:not|no\s+longer)\s+available", re.I)

# Una pagina de baja es CHICA. Un sitio real que mencione "account suspended"
# en una nota tiene miles de caracteres, y confundirlos daria de baja una
# inmobiliaria viva.
TOPE_DE_PAGINA_DE_BAJA = 600


# Un sitio hecho con un framework sirve un cascaron minimo y un `<noscript>`
# que suele decir exactamente "esta pagina no esta disponible sin JavaScript".
# Es texto corto y contiene la frase, o sea que entra por las dos condiciones
# nuevas, y dar de baja una inmobiliaria VIVA es el mas caro de los dos
# errores posibles.
RE_PIDE_JAVASCRIPT = re.compile(r"javascript|habilit\w*\s+js\b", re.I)


def fuera_de_servicio(html: str) -> str | None:
    """El motivo por el que este host no esta sirviendo un sitio, si lo hay."""
    cuerpo = sin_bloques_no_textuales(html)
    texto = re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", cuerpo)).strip()
    if len(texto) > TOPE_DE_PAGINA_DE_BAJA:
        return None
    if RE_PIDE_JAVASCRIPT.search(texto):
        return None
    hallazgo = RE_FUERA_DE_SERVICIO.search(texto)
    return hallazgo.group(0).lower() if hallazgo else None


RE_FICHA_OPERACION = re.compile(
    r"^/(?:venta|alquiler|alquiler-temporario|venta-alquiler)/"
    r"(?:[a-z0-9-]+/){1,3}"
    r"[a-z0-9]+(?:-[a-z0-9]+){3,}/?$", re.I)

RE_FICHA_RAIZ = re.compile(
    r"^/(\d{3,})-[a-z0-9-]*(venta|alquiler|casa|departamento|depto|terreno|"
    r"lote|ph|local|oficina|galpon|campo|cochera|quinta|duplex|chalet)"
    r"[a-z0-9-]*/?$", re.I)

# Rutas de orden del LISTADO que por tener varios guiones parecen slugs de
# ficha. En BuscadorProp eran dos propiedades fantasma por inmobiliaria.
#
# Y `/cdn-cgi/`, la ruta reservada de Cloudflare: nunca es contenido del sitio.
# Su «AI Labyrinth» siembra enlaces a articulos inventados para los bots
# (`fernandez marull` 59 de 59, `crestale` 59 de 131, el 25-09).
RE_NO_FICHA = re.compile(
    r"/propiedades/(?:destacadas|mas-nuevas|mas-viejas|"
    r"precio-(?:mayor|menor)-a-(?:mayor|menor))/?$|^/cdn-cgi/"
    # Taxonomias de WordPress: /estado-propiedad/venta (`garbero`) lista
    # avisos, no es uno.
    r"|^/(?:(?:estado|tipo|ciudad|zona|barrio|caracteristica|categoria|localidad)"
    r"-(?:de-)?propiedad(?:es)?|property-(?:status|type|city|area|feature|label|state))/",
    re.I)

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
# Con que URL se identifica la pagina, dicho por ella misma. El orden de los
# atributos varia entre temas, asi que se toma la etiqueta entera y despues el
# valor: exigir `rel` antes que `href` es como se pierde la mitad de los sitios.
RE_ETIQUETA_CANONICA = re.compile(
    r'<link\b[^>]*\brel=["\']canonical["\'][^>]*>', re.I)
RE_ETIQUETA_OG_URL = re.compile(
    r'<meta\b[^>]*\bproperty=["\']og:url["\'][^>]*>', re.I)
RE_HREF = re.compile(r'\bhref=["\']([^"\']+)', re.I)
RE_CONTENT = re.compile(r'\bcontent=["\']([^"\']+)', re.I)
RE_IMG = re.compile(r'https?://[^\s"\'<>]+?\.(?:jpe?g|png|webp)', re.I)
# El menos NO es opcional. Argentina esta entera en el hemisferio sur y
# oeste, y con el signo opcional el patron de WordPress tomo pares como
# "50.774, 50.7708" y ubico 752 propiedades fuera del pais.
RE_COORD = re.compile(r'"?(?:latitude|lat)"?\s*[:=]\s*"?(-[23456]\d\.\d{3,})"?'
                      r'.{0,80}?"?(?:longitude|lng|lon)"?\s*[:=]\s*"?(-[567]\d\.\d{3,})"?',
                      re.S | re.I)

# Los mapas de Leaflet no nombran los campos: `L.marker([-34.474951,
# -58.521113])`. `RE_COORD` exige la clave adelante, asi que
# `andradeinmobiliaria.com.ar` publicaba la coordenada de sus dos propiedades
# en el mapa y nosotros la reportabamos como no extraida.
#
# Se conservan los mismos rangos que el patron con clave -latitud entre -20 y
# -60, longitud entre -50 y -79- y el signo obligatorio: con el signo opcional,
# el patron de WordPress tomo pares como "50.774, 50.7708" y ubico 752
# propiedades fuera del pais.
RE_COORD_ARREGLO = re.compile(
    r"\[\s*(-[23456]\d\.\d{3,})\s*,\s*(-[567]\d\.\d{3,})\s*\]")

# Evidencia de que una pagina publica UNA propiedad. Se usa solo sobre las urls
# que entraron por la forma verificada de su fuente: la forma dice donde mirar,
# la pagina dice si hay una propiedad. Una nota del blog habla de venta y de
# dormitorios, pero no suele traer un precio con moneda al lado.
RE_OPERACION_TXT = re.compile(r"\b(en venta|en alquiler|venta|alquiler|se vende|"
                              r"se alquila)\b", re.I)
# Lo que describe un inmueble y no una nota. Se piden DOS distintos:
# "superficie" sola aparece en cualquier texto sobre el mercado.
# `mts2` es la misma unidad que `m2` y es como la escribe media Argentina.
# `alianza real estate` publica un terreno con «Precio: Consulte», «Area:
# 382-mts2», «Dormitorios: 2», lista de comodidades y 16 fotos. Sin precio
# numerico la regla exige cuatro atributos distintos y reconocia tres -bano,
# cochera, dormitorio-; el cuarto era la superficie y no se veia.
#
# Se agrega la UNIDAD y no la palabra `area`. `area` aparece en prosa -«el
# area de influencia», «gran area verde»- y aflojaria el umbral por el mismo
# lado que este comentario ya advertia para `superficie`. Una unidad no tiene
# ese problema.
RE_ATRIBUTOS_TXT = re.compile(r"\b(dormitorio|ambiente|ba[nñ]o|superficie|"
                              r"m(?:ts)?2|m(?:ts)?²|cubierta|cochera|"
                              r"antig[uü]edad)", re.I)
RE_EDITORIAL = re.compile(r'"@type"\s*:\s*"?(Article|NewsArticle|BlogPosting)|'
                          r'property="og:type"\s+content="article"', re.I)
# Un precio CON MONEDA al lado, que es lo que el comentario de arriba ya venia
# diciendo que distingue una ficha de una nota y no estaba implementado. Un
# numero suelto no alcanza: "Analisis de la superficie construida en 2026"
# tiene un numero y una palabra de atributo, y no es una propiedad.
# `u$d` estaba afuera, y en Argentina se escribe tanto como `u$s`. Medido el
# 2026-09-21 sobre una ficha real de 120 agencias: 8 la escriben asi, y tres
# de esas ocho usan `u$d` Y otra forma en la misma pagina -`belvedere`,
# `bondar`, `carames`-. `brunetti propiedades` tiene precio en 70 de 428
# fichas y escribe `U$D`; `cipollone` perdio un lote de 9 fotos que publicaba
# «U$D 70.000»; `cordoba propiedades` perdio dos fichas de 31 y 53 fotos que
# decian «U$D 45.000».
#
# El `$` suelto no las salvaba: despues del `$` viene una `D` y no un digito.
RE_PRECIO_CON_MONEDA = re.compile(
    r"(?:u\$[sd]|us\$|usd|ars|\$)\s*\d[\d.,]*"
    r"|\d[\d.,]*\s*(?:d[oó]lares|pesos|usd|ars)\b", re.I)
FOTOS_MINIMAS = 3

# Cuantos atributos distintos tiene que reconocer una ficha para aceptarse SIN
# precio numerico. Sale de medir, no de elegir: de las 53 paginas
# institucionales que el guardian de forma rechazo en todo el corpus, 45
# tienen cero atributos y ninguna llega a cuatro. El hueco entre 1 y 4 es lo
# que hace seguro el corte.
ATRIBUTOS_SIN_PRECIO = 4


# `src` con ruta relativa, y los atributos con los que los sitios difieren la
# carga. La url se resuelve contra la de la ficha.
# La comilla simple es tan valida como la doble en HTML, y `corporacion
# inmobiliaria` escribe `src='https://gvamax.ar/...'`: sus cinco fotos por
# ficha no se veian por eso, antes incluso de llegar al asunto de la
# extension.
RE_IMG_ATRIBUTO = re.compile(
    r"<img[^>]{0,400}?\s(?:data-src|data-lazy-src|data-original|src)="
    r"(?:\"([^\"]{4,400})\"|'([^']{4,400})')", re.I)
# El enlace del visor de fotos (lightbox): `<a href="fotos/x.jpeg">`.
RE_ENLACE_A_FOTO = re.compile(
    r"<a[^>]{0,400}?\shref=(?:\"([^\"]{4,400})\"|'([^']{4,400})')", re.I)

# Un descriptor de `srcset`: el ancho o la densidad que va DESPUES de la url.
RE_DESCRIPTOR = re.compile(r"^\d+(?:\.\d+)?[wx]$", re.I)


def _url_del_atributo(crudo: str) -> str:
    """La url de un `src`, aunque el nombre del archivo tenga espacios.

    Esto era `crudo.split()[0]`, y partia el nombre en el primer espacio.
    `cometto inmobiliaria` publica `images/propiedades/IMG_3859 (1).JPG` y lo
    que quedaba era `images/propiedades/IMG_3859`, que devuelve 404. En
    `bottai` costaba 71 de 232 fotos.

    Mientras `_imagenes_de` exigia extension el estropicio no se notaba: la
    url truncada se caia sola por no terminar en `.jpg`. Al dejar de exigirla
    -para recuperar las fotos sin extension de `chambouleyron` y
    `corporacion`- esa url rota habria empezado a entrar. Lo vi al probar el
    arreglo contra la pagina real de `cometto`, no despues.

    Un `src` lleva UNA url, asi que cortar por espacios no tiene sentido. El
    unico caso donde el valor trae algo mas es un descriptor de `srcset`
    -`foto.jpg 2x`-, y ese se reconoce por su forma en vez de asumirlo.
    """
    valor = (crudo or "").strip()
    if not valor:
        return ""
    partes = valor.split()
    if len(partes) > 1 and RE_DESCRIPTOR.match(partes[-1]):
        return " ".join(partes[:-1])
    return valor
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
    t = sin_bloques_no_textuales(html)
    t = unescape(t)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", unescape(t).replace("\xa0", " "))


def sin_marcado_comentado(html: str) -> str:
    """Quita el marcado que vive dentro de un comentario HTML.

    Un comentario no lo muestra ningun navegador: no es contenido publicado.
    Alagna deja el bloque de ambientes comentado, con la `X` de la plantilla
    adentro; leerlo hacia creer que la fuente provee un dato que nadie ve, y
    exigia extraer un valor que no existe.

    Los `<script>` envueltos en `<!-- //-->` son el patron viejo de esconder
    JavaScript de navegadores antiguos, no marcado muerto: ahi puede viajar el
    JSON-LD de la ficha, asi que esos comentarios se conservan.
    """
    def decidir(coincidencia):
        bloque = coincidencia.group(0)
        return bloque if "<script" in bloque.lower() else " "

    return re.sub(r"<!--.*?-->", decidir, html or "", flags=re.S)


RE_VENTA_CERCA = re.compile(r"\b(en\s+venta|se\s+vende|vendo|venta)\b", re.I)
RE_ALQUILER_CERCA = re.compile(r"\b(en\s+alquiler|se\s+alquila|alquiler)\b", re.I)
RE_TEMPORARIO_CERCA = re.compile(r"\b(temporari[oa]|temporal)\b", re.I)
# Cuanto texto se mira a cada lado del precio. Con 60 caracteres entran las
# formas medidas -«En venta U$S 440.000», «USD 30.000 En venta», «Venta: USD
# 33.000»- y no entra la propiedad de al lado.
CERCA_DEL_PRECIO = 60


def formas_del_precio(precio: Any) -> "re.Pattern | None":
    """El mismo numero como puede estar escrito en la pagina.

    440000 se publica «440.000», «440,000» o «440 000`. Se arma el patron
    desde el entero que ya extrajimos en vez de buscar cualquier numero:
    anclar en ESTE precio es lo que distingue el aviso de sus vecinos.
    """
    try:
        entero = int(round(float(precio)))
    except (TypeError, ValueError):
        return None
    if entero <= 0:
        return None
    crudo, partes = str(entero), []
    while len(crudo) > 3:
        partes.insert(0, crudo[-3:])
        crudo = crudo[:-3]
    partes.insert(0, crudo)
    cuerpo = r"[.,\s]?".join(re.escape(p) for p in partes)
    return re.compile(rf"(?<![\d.,]){cuerpo}(?![\d])")


def operacion_junto_al_precio(texto: str, precio: Any) -> str | None:
    """La operacion escrita al lado del precio de ESTA propiedad.

    Es la senal que distingue el aviso del resto de la pagina, y hacia falta
    porque el menu y el buscador dicen «Venta | Alquiler` en todas las fichas
    y dejan la ficha «ambigua» aunque el aviso lo diga clarisimo:

        conti      «En venta U$S 440.000»      263 de 290 sin operacion
        atencio    «USD 30.000 En venta»       256 de 328
        eckert     «Venta : USD 248.800»        27 de  31

    Se ancla en el precio ya extraido y no en cualquier numero: las
    «Ultimas propiedades» del pie tienen sus propios precios y su propia
    operacion, y son las del vecino. Por eso tampoco alcanza con mirar el
    primer precio de la pagina.

    Si las apariciones de este precio no coinciden todas en la misma
    operacion, no devuelve nada: `bottai` publica un buscador con «Venta
    Alquiler» y ahi la pagina no esta diciendo cual es.
    """
    patron = formas_del_precio(precio)
    if patron is None or not texto:
        return None
    vistas: set[str] = set()
    for m in patron.finditer(texto):
        ventana = texto[max(0, m.start() - CERCA_DEL_PRECIO):
                        m.end() + CERCA_DEL_PRECIO]
        if RE_ALQUILER_CERCA.search(ventana):
            vistas.add("alquiler_temporario"
                       if RE_TEMPORARIO_CERCA.search(ventana) else "alquiler")
        if RE_VENTA_CERCA.search(ventana):
            vistas.add("venta")
    return vistas.pop() if len(vistas) == 1 else None


# Donde un aviso cuelga la cosa que se publica. `RealEstateListing` describe
# el AVISO -nombre, descripcion, oferta- y el inmueble va adentro: la
# direccion, las coordenadas y los ambientes de `alagna` estan en su
# `mainEntity`, que es un `Place`. Mirar solo el nodo de arriba deja la ficha
# sin ciudad teniendo `addressLocality: Rosario` escrito ahi abajo.
#
# Se mira UNICAMENTE dentro del nodo ya elegido. La regla que impide completar
# una propiedad con los datos de otra no se toca: lo que cuelga de este aviso
# es de este aviso.
ENTIDAD_DEL_AVISO = ("mainEntity", "itemOffered", "about", "item")


def _de_su_entidad(nodo: dict, clave: str) -> Any:
    """`clave` buscada en la entidad que cuelga de ESTE nodo."""
    for puerta in ENTIDAD_DEL_AVISO:
        adentro = nodo.get(puerta)
        if isinstance(adentro, list):
            adentro = adentro[0] if adentro else None
        if isinstance(adentro, dict) and adentro.get(clave) is not None:
            return adentro[clave]
    return None


def identidades_de_la_pagina(html: str, url: str) -> set[str]:
    """Con que URLs se identifica ESTA pagina: la pedida y la que declara.

    `alagna propiedades` publica en su sitemap
    `/alquiler/local/local-comercial-...-centro` y la misma pagina declara
    `rel="canonical"` y `og:url` con el id al final:
    `/alquiler/local/local-comercial-...-centro-8408054`. Su JSON-LD usa esa
    segunda forma.

    El filtro de identidad de `_de_json_ld` comparaba solo contra la URL
    pedida, no encontraba ningun nodo que coincidiera y **descartaba el JSON-LD
    entero**: 0 de 229 fichas con ciudad, teniendo la fuente
    `addressLocality: Rosario` escrito en el contrato publico de todas. La
    agencia paro la cola por «la fuente publica ciudad y la extraccion fallo»,
    y tenia razon.

    El filtro sigue siendo estricto -su motivo es que los campos de una
    propiedad no completen los de otra- y lo unico que cambia es contra que se
    compara: la identidad de una pagina es la que la pagina declara, no la que
    nosotros hayamos usado para pedirla.
    """
    identidades = {url}
    for patron, valor in ((RE_ETIQUETA_CANONICA, RE_HREF),
                          (RE_ETIQUETA_OG_URL, RE_CONTENT)):
        etiqueta = patron.search(html or "")
        if not etiqueta:
            continue
        encontrado = valor.search(etiqueta.group(0))
        if encontrado:
            identidades.add(unescape(encontrado.group(1)).strip())
    return identidades


def cuerpo_principal(html: str) -> str:
    """Parte de la ficha anterior a relacionadas/footer.

    Los contadores y atributos del vecino no describen esta propiedad. Leer el
    documento entero produjo dormitorios>ambientes que el guardián debió
    descartar; el dato nunca debió entrar al parser.
    """
    html = sin_marcado_comentado(html)
    # RealHomes (`fernando villalba`): sus similares van en
    # `rh_property__similar_properties`, elegidas al azar en cada carga; sus
    # «Habitaciones» daban 4 dormitorios a una parcela de 1,3 ha.
    return re.split(
        r"id=[\"'](?:relacionadas|bottom)[\"']|<footer\b|"
        r"class=[\"'][^\"']*rh_property__similar_properties|"
        # Y la plantilla de `berrueta` (Template3): el tooltip «Cochera» de una
        # tarjeta relacionada era el unico tipo que veia la ficha, y 24
        # departamentos quedaban guardados como cocheras.
        r"class=[\"'][^\"']*ficha__related|"
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

    Delega en `connectors.texto`, que es la UNICA etapa de normalizacion del
    pipeline. Antes esto era una tabla escrita a mano con cuatro reemplazos
    -`Ba�os`, `ba�os`, `Ba�o`, `ba�o`- y nada mas: cubria la palabra que
    alguien recordo el dia que la vio romperse.

    La version central repara el mojibake que se puede demostrar y reconoce
    contra un vocabulario declarado los tokens donde la fuente ya perdio el
    byte, asi que ahora tambien vuelven `Descripcion`, `Antiguedad`, `Codigo`,
    `Ano` y el resto del vocabulario, sin escribir una linea por palabra.

    La misma normalizacion se comparte con el auditor para que una senal de
    fuente y su extraccion nunca usen alfabetos distintos.
    """
    return normalizar_campos(texto)



def _entero(valor: Any) -> int | None:
    """Un entero razonable, o nada. Nunca un cero inventado."""
    try:
        n = int(float(valor))
    except (TypeError, ValueError):
        return None
    return n if 1 <= n <= 99 else None


def _decimal(valor: Any) -> float | None:
    try:
        n = float(valor)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _coordenada(valor: Any) -> float | None:
    try:
        n = float(valor)
    except (TypeError, ValueError):
        return None
    return n if n != 0 else None


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

    # Palabras que, en una ruta, dicen que eso es un inmueble. No se reusa
    # `RE_FICHA` a proposito: aca la pregunta es que forma APRENDER, no que
    # ruta aceptar, y mezclarlas ataria el aprendizaje al patron que se quiere
    # complementar.
    _PALABRAS_DE_FICHA = (r"propiedad(?:es)?|inmueble[s]?|emprendimiento[s]?|"
                          r"ficha[s]?|propert(?:y|ies)|listing[s]?|aviso[s]?|"
                          r"casa|departamento|depto|terreno|lote|ph|local|"
                          r"oficina|galpon|campo|cochera|quinta|duplex|chalet")

    @staticmethod
    def _forma_de_ruta(ruta: str) -> str | None:
        """La ruta con su identificador y su slug reemplazados por comodines.

        Devuelve None si la ruta no tiene un identificador de tres digitos o
        mas, o si nada en ella dice que se trata de un inmueble. Las dos cosas
        juntas: `/quienes-somos` no tiene id, y `/2024/09/nota-del-blog` tiene
        numero pero no palabra.
        """
        segmentos = [s for s in (ruta or "").strip("/").split("/") if s]
        if not segmentos or len(segmentos) > 3:
            return None
        if not re.search(r"\d{3,}", ruta):
            return None
        partes = []
        for segmento in segmentos:
            m = re.fullmatch(r"([A-Za-z][A-Za-z-]*)([-_])(\d{3,})"
                             r"(?:([-_])([A-Za-z0-9_-]+))?", segmento)
            if m:
                cola = f"{m.group(4)}<slug>" if m.group(5) else ""
                partes.append(f"{m.group(1)}{m.group(2)}<id>{cola}")
                continue
            m = re.fullmatch(r"(\d{3,})([-_])([A-Za-z0-9_-]+)", segmento)
            if m:
                partes.append(f"<id>{m.group(2)}<slug>")
                continue
            if re.fullmatch(r"\d{3,}", segmento):
                partes.append("<id>")
                continue
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", segmento):
                partes.append(segmento.lower())
                continue
            return None
        return "/" + "/".join(partes)

    @staticmethod
    def _regex_de_forma(forma: str) -> "re.Pattern":
        partes = []
        for segmento in forma.strip("/").split("/"):
            trozo = ""
            for pedazo in re.split(r"(<id>|<slug>)", segmento):
                if pedazo == "<id>":
                    trozo += r"\d{3,}"
                elif pedazo == "<slug>":
                    trozo += r"[A-Za-z0-9_-]+"
                elif pedazo:
                    trozo += re.escape(pedazo)
            partes.append(trozo)
        return re.compile("^/" + "/".join(partes) + "/?$", re.I)

    @staticmethod
    def _patron_raiz_local(html: str) -> "re.Pattern | None":
        """La forma de ficha de ESTA fuente, aprendida de sus propios enlaces.

        Tres rutas distintas de la misma forma son la evidencia minima. Cada
        detalle entra con `por_forma=True` y `_confirma_ficha` lo valida uno
        por uno; no se afloja el patron global.

        Antes reconocia UNA sola forma -/p-<id>_<slug>- y la idea era buena con
        la implementacion cableada. El escaneo de las 50 agencias NEEDS_FIX con
        cero enumeradas mostro que 14 de 49 publican fichas con formas que
        ningun patron nuestro ve, y varias llevan identificador:

            /propiedad-9871962-venta-casa-en-funes      fios
            /p/7525662-Casa-en-Venta-en-Salvador-Maria  andrea gianfelice
            /inmueble_6076                              bottai

        Se exige un id de tres digitos Y una palabra que diga de que se trata.
        Las dos juntas son mucho mas dificiles de cumplir por accidente que
        cualquiera sola, y lo que queda afuera son justamente los dos falsos
        amigos conocidos: la navegacion institucional -sin id- y el blog con
        fechas -sin palabra-.

        Lo que hace seguro generalizar esto es el guardian que ya existe:
        sobre las 283 paginas con que se verifico, `_confirma_ficha` acepta el
        96,9 % de las formas confirmadas y solo el 4,5 % de las descartadas.
        """
        rutas = set()
        for m in re.finditer(r'href="([^"]{4,300})"', html or "", re.I):
            partes = urllib.parse.urlparse(m.group(1))
            if partes.query:
                # Una paginacion -/propiedades?pagina=2- no es una ficha.
                continue
            rutas.add("/" + partes.path.lstrip("/"))
        por_forma: dict[str, set[str]] = {}
        for ruta in rutas:
            forma = GenericoConnector._forma_de_ruta(ruta)
            if forma:
                por_forma.setdefault(forma, set()).add(ruta)
        # La palabra que dice "esto es un inmueble" se le pide a la FORMA, no a
        # cada ruta. `andrea gianfelice` publica /p/7525662-Casa-en-Venta-...,
        # /p/2494510-Lote-en-Canning y /p/6731093-Haras-Santa-Cecilia-en-Lobos:
        # las tres son fichas y la tercera no nombra ningun tipo. Exigirsela a
        # cada una dejaba la forma en dos ejemplos y por debajo del minimo.
        candidatas = [
            (len(rutas_de_la_forma), forma)
            for forma, rutas_de_la_forma in por_forma.items()
            if len(rutas_de_la_forma) >= 3
            and any(re.search(GenericoConnector._PALABRAS_DE_FICHA, r, re.I)
                    for r in rutas_de_la_forma)]
        if not candidatas:
            return None
        candidatas.sort(reverse=True)
        return GenericoConnector._regex_de_forma(candidatas[0][1])

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
            # `U\$D` va aca tambien. Esta es la TERCERA copia de la misma
            # regla -las otras dos son RE_PRECIO_CON_MONEDA y la busqueda de
            # precio visible- y arreglar dos y dejar una es el patron que ya
            # costo caro hoy en otros tres lugares del repo.
            r'(?:Valor\s*:\s*)?(USD|U\$[SD]|US\$|ARS|\$)\s*([\d][\d.,]{1,15})',
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

    @staticmethod
    def _rutas_de_categoria(html: str, base: str) -> list[str]:
        """Paginas de categoria que la portada enlaza, en su propio orden.

        Un catalogo estatico no vive en una ruta unica: el menu lleva a una
        pagina por tipo -casas, departamentos, lotes, alquileres- y las fichas
        cuelgan de ahi. `almadimatteo.com.ar` publica 28 propiedades asi y el
        enumerador no bajaba ese nivel, con lo cual el sitio pasaba por vacio.

        Se lee la navegacion que el sitio declara, no una ruta adivinada, y se
        exige que la categoria sea del rubro: seguir cualquier enlace del menu
        seria recorrer "quienes somos" y "contacto".
        """
        patron = re.compile(
            r"(?:casas?ychalets?|casas|chalets|departamentos?|deptos?|duplex|"
            r"ph\b|lotes|terrenos|locales|galpones|cocheras|campos|quintas|"
            r"oficinas|emprendimientos|alquileres?|ventas?)", re.I)
        vistos: list[str] = []
        for coincidencia in re.finditer(r'href=["\']([^"\']+)["\']', html or ""):
            destino = urllib.parse.urljoin(base + "/", unescape(coincidencia.group(1)))
            if not destino.startswith(base):
                continue
            ruta = urllib.parse.urlparse(destino).path
            if not re.search(r"\.(?:html?|php|aspx)$", ruta, re.I):
                continue
            # La palabra del rubro tiene que estar en el NOMBRE DEL ARCHIVO, no
            # en cualquier parte de la ruta. `casasychalets/casasychalets.html`
            # es una categoria; `casasychalets/Aroca/Aroca.html` es una casa, y
            # mirar la ruta entera las confundia y perdia la propiedad.
            if not patron.search(ruta.rsplit("/", 1)[-1]):
                continue
            limpio = destino.split("#")[0]
            if limpio not in vistos:
                vistos.append(limpio)
        return vistos[:MAX_CATEGORIAS]

    @staticmethod
    def _catalogo_de_selector(cuerpo: str, pagina: str,
                              base: str) -> list[str]:
        """Fichas enlazadas desde un `<select>` de navegacion.

        `amipropiedades.com.ar` publica sus 27 propiedades en un desplegable
        "POR CODIGO" -`<option value="../propiedades/375-venta-casa...html">`-
        y no en un solo `<a>`. Leyendo unicamente `href`, un sitio entero con
        catalogo declarado figuraba como SIN_INVENTARIO y el triage lo paro
        como posible perdida de inventario, que es exactamente lo que era.

        No hace falta adivinar por la forma de la URL: un `<select>` cuyas
        opciones apuntan a varios documentos del propio sitio ES el indice del
        catalogo. Lo dice el sitio con su propia navegacion, y eso es mejor
        evidencia que cualquier patron que pudieramos inventar.

        Se exigen TRES destinos distintos: con uno o dos, el desplegable puede
        ser un selector de idioma, de sucursal o de moneda.
        """
        fichas: list[str] = []
        for bloque in re.finditer(r"(?is)<select\b[^>]*>(.*?)</select>", cuerpo):
            destinos: list[str] = []
            for opcion in re.finditer(
                    r'(?is)<option[^>]*\bvalue=["\']([^"\']+)["\']',
                    bloque.group(1)):
                crudo = unescape(opcion.group(1)).strip()
                if not re.search(r"\.(?:html?|php|aspx)$", crudo, re.I):
                    continue
                destino = urllib.parse.urljoin(pagina, crudo).split("#")[0]
                if destino.startswith(base) and destino not in destinos:
                    destinos.append(destino)
            if len(destinos) >= 3:
                fichas.extend(destinos)
        return fichas

    def _catalogo_por_categorias(self, html: str, base: str,
                                 propia: "re.Pattern | None") -> list[str] | None:
        """Fichas alcanzables recorriendo las paginas de categoria.

        Devuelve None cuando no hay catalogo por categorias, para que el
        detector siguiente tenga su turno. Una lista vacia y un None significan
        cosas distintas y confundirlas es como se declara vacio un sitio lleno.
        """
        categorias = self._rutas_de_categoria(html, base)
        if len(categorias) < 2:
            return None
        fichas: list[str] = []
        vistas: set[str] = set()
        # La portada tambien enlaza fichas directamente -lo destacado del mes-,
        # y mirar solo las categorias las perdia: en `almadimatteo.com.ar` eran
        # seis de veintiocho.
        paginas: list[tuple[str, str]] = [(base + "/", html)]
        for categoria in categorias:
            try:
                paginas.append((categoria, self.descargador.bajar(categoria)))
            except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                continue
        for categoria, cuerpo in paginas:
            # La navegacion por desplegable no pasa por la regla de
            # profundidad: no hay nada que inferir cuando el sitio puso la
            # ficha en su propio indice. En `amipropiedades.com.ar` la ficha
            # vive ADEMAS al mismo nivel que su categoria
            # -`/propiedades/casas.html` y `/propiedades/146-....html`-, asi
            # que la regla de profundidad la habria descartado igual.
            for destino in self._catalogo_de_selector(cuerpo, categoria, base):
                if destino in vistas or destino in categorias:
                    continue
                vistas.add(destino)
                fichas.append(destino)
            for coincidencia in re.finditer(r'href=["\']([^"\']+)["\']', cuerpo):
                destino = urllib.parse.urljoin(categoria, unescape(coincidencia.group(1)))
                if not destino.startswith(base):
                    continue
                ruta = urllib.parse.urlparse(destino).path
                if not re.search(r"\.(?:html?|php|aspx)$", ruta, re.I):
                    continue
                # La ficha vive MAS ABAJO que su categoria. Ese salto de nivel
                # es lo que la separa de la navegacion, que apunta al mismo
                # nivel o hacia arriba.
                # Una ficha cuelga MAS ABAJO que la pagina que la enlaza.
                # Desde la portada hace falta un nivel extra: ahi el segundo
                # nivel son las categorias, no las propiedades.
                minimo = urllib.parse.urlparse(categoria).path.count("/")
                if categoria.rstrip("/") == base:
                    # Desde la portada lo que separa una ficha de una categoria
                    # no es la profundidad -`emprendimientos/calle9.html` es una
                    # propiedad y vive al mismo nivel que `lotes/lotes.html`-
                    # sino no ser una de las categorias ya identificadas, que se
                    # descartan unas lineas mas abajo.
                    minimo = 1
                if ruta.count("/") <= minimo:
                    continue
                limpio = destino.split("#")[0]
                if limpio in vistas or limpio in categorias:
                    continue
                vistas.add(limpio)
                fichas.append(limpio)
        return fichas or None

    def _catalogo_tokko_proxy(self, base: str) -> dict[str, Any] | None:
        """Un frontend propio que sirve el catalogo Tokko desde su mismo host.

        `alta.com.ar` es Next.js: el HTML inicial no trae ninguna propiedad y
        el catalogo se hidrata desde `/api/tokko/properties`, en el MISMO
        origen. Sin ejecutar JavaScript el sitio parece vacio, y publica 16.

        No se prueba un dominio: se prueba una FORMA -un endpoint propio que
        devuelve `{count, objects}` con objetos de Tokko-, que es reutilizable
        por cualquier sitio construido asi.
        """
        for ruta in RUTAS_TOKKO_PROXY:
            try:
                cuerpo = self.descargador.bajar(
                    f"{base}{ruta}?limit=1&offset=0")
            except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                continue
            try:
                dato = json.loads(cuerpo)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(dato, dict):
                continue
            objetos = dato.get("objects")
            if not isinstance(objetos, list) or "count" not in dato:
                continue
            try:
                total = int(dato["count"])
            except (TypeError, ValueError):
                continue
            return {"ruta": ruta, "total": total}
        return None

    def _plan_desde_la_raiz(self, fuente: Fuente, base: str, p: Any,
                            _desde_la_raiz: bool) -> dict[str, Any] | None:
        """El catalogo de la raiz, cuando la url declarada es una subpagina.

        `altos servicios inmobiliarios` figura como `/page/empresa-1`, que no
        enlaza ninguna ficha, mientras la raiz publica su catalogo en
        `/listing` con veinte propiedades. Leer solo lo declarado hacia pasar
        por vacio a un sitio lleno.

        Devuelve None cuando no hay raiz que probar o cuando la raiz tampoco
        sirve, para que el llamador siga con lo que ya tenia.
        """
        if _desde_la_raiz or not p.path.strip("/"):
            return None
        try:
            desde_raiz = self.discover(
                Fuente(canonical_agency_id=fuente.canonical_agency_id,
                       agency_name=fuente.agency_name,
                       official_url=base + "/",
                       inmobiliaria_id=fuente.inmobiliaria_id,
                       detected_platform=fuente.detected_platform,
                       extra=fuente.extra),
                _desde_la_raiz=True)
        except (ErrorTransitorio, ErrorPermanente, Bloqueado):
            return None
        if not desde_raiz.get("soportada"):
            return None
        desde_raiz["entrada_corregida"] = base + "/"
        desde_raiz["entrada_declarada"] = fuente.official_url
        return desde_raiz

    # ---------------------------------------------------------------- discover
    def discover(self, fuente: Fuente,
                 _desde_la_raiz: bool = False) -> dict[str, Any]:
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

        # --- 1.b catalogo servido por el propio frontend --------------------
        # Antes de leer el HTML: un frontend que hidrata desde su propia API no
        # va a mostrar ninguna propiedad en el documento inicial, y mirarlo
        # primero solo confirma un vacio que no existe.
        proxy = self._catalogo_tokko_proxy(base)
        if proxy is not None:
            plan.update({"variante": "TOKKO_PROXY_JSON", "soportada": True,
                         "tokko_proxy_ruta": proxy["ruta"],
                         "total_declarado": proxy["total"]})
            return plan

        # --- 2. listado en HTML --------------------------------------------
        try:
            html = self.descargador.bajar(fuente.official_url)
            baja = fuera_de_servicio(html)
            if baja:
                # Preguntarle el catalogo a un dominio suspendido es preguntarle
                # a nadie. Se corta aca y se dice por que.
                plan["fuera_de_servicio"] = baja
                return plan
        except (ErrorTransitorio, ErrorPermanente, Bloqueado):
            # No poder LEER la portada no es lo mismo que leerla y que no
            # publique nada. Devolver el plan vacio las hacia indistinguibles:
            # `varelanegociosinmobiliarios.com` no respondio en 102 s y salio
            # como `SIN_INVENTARIO`, o sea como una inmobiliaria sin
            # propiedades, y de ahi el triage lo leyo como una perdida
            # sistematica de inventario de radio FAMILIA y paro la cola.
            #
            # `NO_INVENTORY_CONFIRMED` y `BLOCKED_EXTERNAL` son estados
            # terminales distintos justamente por esto.
            desde_raiz = self._plan_desde_la_raiz(fuente, base, p,
                                                  _desde_la_raiz)
            if desde_raiz is not None:
                return desde_raiz
            # Que la raiz tampoco se pueda leer confirma que el problema es
            # llegar al sitio. Se propaga para que el runner lo diga.
            raise
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
        ruta_propia = urllib.parse.urlparse(fuente.official_url).path.rstrip("/")
        ya_es_el_catalogo = ruta_propia == "/propiedades"
        listado = fuente.official_url if ya_es_el_catalogo else base + "/propiedades"
        # Se prueba /propiedades por convencion, pero tambien los catalogos que
        # la pagina de la fuente enlaza: alianzarealestate.com.ar publica el
        # suyo en /ventas/listado y con una sola ruta fija se reportaba sin
        # inventario teniendo doce fichas. Seguir la navegacion del sitio no es
        # adivinar una ruta, es leer la que el sitio declara.
        #
        # Y esta exploracion corre SIEMPRE, tambien cuando la fuente registrada
        # ya es /propiedades. Antes ese caso se saltaba entero, con el supuesto
        # de que si la fuente apunta al catalogo el catalogo esta ahi. Es cierto
        # en la mayoria de los sitios y falso en los que reparten el listado en
        # una segunda ruta: `fios consultoria` registra /propiedades, esa pagina
        # declara 266 y enlaza catorce `listado.php?...&pagina=N`, y las fichas
        # estan en esas y no en ella. La agencia enumeraba CERO y paraba la cola
        # con radio FAMILIA.
        candidatos = ([] if ya_es_el_catalogo else [base + "/propiedades"])
        candidatos += [c for c in self._catalogos_enlazados(html, base)
                       if c.rstrip("/") != fuente.official_url.rstrip("/")]
        if candidatos:
            for candidato in candidatos:
                try:
                    html_listado = self.descargador.bajar(candidato)
                except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                    continue
                runtime_listado = runtime or self._patron_raiz_local(html_listado)
                enlaces_listado = self._fichas_en(html_listado, base,
                                                  runtime_listado)
                catalogo_explicito = bool(re.search(
                    r"Se encontraron\s+[\d.]+\s+resultados|"
                    r"params\.append\(['\"]infinito['\"]|id=['\"]prop-list['\"]",
                    html_listado, re.I))
                if enlaces_listado and (catalogo_explicito
                                        or len(enlaces_listado) > len(enlaces)):
                    html, enlaces = html_listado, enlaces_listado
                    runtime, listado = runtime_listado, candidato
                    if catalogo_explicito:
                        break
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
        # --- ultimo recurso: catalogo repartido en paginas de categoria -----
        # Va al final a proposito: cualquier detector especifico describe mejor
        # al sitio que recorrerle el menu. Solo cuando ninguno reconocio la
        # forma se sigue la navegacion, que es lo unico que queda antes de
        # declarar vacio un sitio que puede estar lleno.
        fichas_categoria = self._catalogo_por_categorias(html, base, propia)
        if fichas_categoria:
            plan.update({"variante": "CATEGORY_HTML_CATALOG", "soportada": True,
                         "fichas": fichas_categoria[:MAX_FICHAS],
                         "total_declarado": len(fichas_categoria)})
            return plan

        # La url declarada puede ser una subpagina institucional. `altos
        # servicios inmobiliarios` figura como `/page/empresa-1`, que no
        # enlaza ninguna ficha, mientras la raiz publica su catalogo en
        # `/listing` con veinte propiedades. Leer solo lo declarado hacia pasar
        # por vacio a un sitio lleno.
        #
        # Se intenta una sola vez y solo cuando ya no quedaba nada por probar,
        # asi que el costo es una peticion extra unicamente en el caso que de
        # otro modo se perderia entero.
        desde_raiz = self._plan_desde_la_raiz(fuente, base, p, _desde_la_raiz)
        if desde_raiz is not None:
            return desde_raiz

        return plan

    @staticmethod
    def _es_un_archivo(ruta: str) -> bool:
        """Una imagen, un PDF o una hoja de estilo no es una ficha.

        `building inmobiliaria` publica 77 propiedades y nosotros guardamos
        **297**: 220 de esas eran las FOTOS. Sus imagenes cuelgan de
        `/storage/properties/209/original_6aa2a3a24d3b3.jpg`, que para
        `RE_FICHA_ANIDADA` es indistinguible de una ficha -seccion
        `properties`, id `209`, un ultimo segmento cualquiera-. Cada una entro
        como una propiedad con `titulo: None`, `operacion: None` y un precio
        sacado de la nada: el 74 % del inventario de esa agencia era inventado.

        La regla ya existia y este archivo no la usaba. `scraper/detail_urls`
        descarta esas extensiones desde siempre; el `_es_ficha_url` de aca
        tenia su propio criterio y nunca se entero. Por eso se importa la
        lista de alla en vez de escribir una segunda: asi es exactamente como
        dos copias de la misma regla terminan diciendo cosas distintas.
        """
        # Import diferido a proposito: `scraper.detail_urls` trae
        # BeautifulSoup y este modulo evita pagar eso al importarse. Misma
        # razon que en `_fichas_en`.
        from scraper.detail_urls import _DETAIL_STATIC_EXTENSIONS
        return ruta.lower().endswith(_DETAIL_STATIC_EXTENSIONS)

    @staticmethod
    def _es_ficha_url(u: str, propia: "re.Pattern | None" = None) -> bool:
        ruta = urllib.parse.urlparse(u).path
        if GenericoConnector._es_un_archivo(ruta):
            return False
        return not RE_NO_FICHA.search(ruta) and bool(
            RE_FICHA.search(u) or RE_FICHA_ANIDADA.search(ruta)
            or RE_FICHA_RAIZ.search(ruta)
            or RE_FICHA_OPERACION.search(ruta)
            or (propia is not None and propia.match(ruta)))

    @staticmethod
    def _solo_por_forma(u: str, propia: "re.Pattern | None") -> bool:
        """La url entro unicamente por la forma verificada de esta fuente.

        Se anota para que el detalle la compruebe: una forma de raiz amplia
        -/<slug>- tambien alcanza /quienes-somos, y una pagina institucional no
        puede terminar publicada como propiedad.
        """
        # A recovered shape is only a candidate, whether it came from the
        # shared historical detector or a source-specific pattern.
        return not GenericoConnector._es_ficha_url(u)

    @staticmethod
    def _fichas_en(html: str, base: str, extra: "re.Pattern | None" = None) -> list[str]:
        """Los enlaces a fichas del HTML.

        `extra` es la forma verificada de ESTA fuente. Existe para no tener que
        aflojar el patron global: 65 sitios publican sus fichas en la raiz y se
        comprobo una por una -bajando tres paginas de cada uno- que traen precio
        con moneda, operacion y fotos. Habilitar esa forma para ellos no afloja
        nada para los otros 2.258.
        """
        from bs4 import BeautifulSoup
        from scraper.detail_urls import (extract_candidate_detail_urls_from_card,
                                         extract_candidate_detail_urls_from_document)
        host = (urllib.parse.urlparse(base).hostname or '').lower().removeprefix('www.')
        salida, vistas = [], set()
        soup = BeautifulSoup(html or '', 'html.parser')
        recovered = [url for url, _ in extract_candidate_detail_urls_from_document(soup, base)]
        for card in soup.select("article, [class*='property'], [class*='propiedad'], [class*='listing'], [class*='card']"):
            recovered.extend(extract_candidate_detail_urls_from_card(card, base))
        hrefs = [urllib.parse.urljoin(base, a.get('href', '')) for a in soup.select('a[href]')]
        recovered_set = set(recovered)
        for u in hrefs + recovered:
            if (urllib.parse.urlparse(u).hostname or '').lower().removeprefix('www.') != host:
                continue
            if RE_NO_FICHA.search(urllib.parse.urlparse(u).path):
                continue
            # Se pregunta al reconocedor, no se repite su logica: estaba
            # duplicada aca y agregar una forma nueva en `_es_ficha_url` no
            # tenia ningun efecto sobre la enumeracion. Una regla escrita dos
            # veces es una regla que miente en uno de los dos lados.
            if not GenericoConnector._es_ficha_url(u, extra) and u not in recovered_set:
                continue
            c = u.split("#")[0].rstrip("/")
            if c not in vistas:
                vistas.add(c)
                salida.append(u)
        soup.decompose()
        return salida

    # ----------------------------------------------------------- fetch_listing
    def fetch_listing(self, fuente: Fuente, plan: dict[str, Any]) -> Iterator[dict]:
        if not plan.get("soportada"):
            return
        if plan["variante"] == "EMPTY_CATALOG_HTML":
            return
        propia = plan.get("patron_runtime") or self._patron_de(fuente)
        if plan["variante"] == "TOKKO_PROXY_JSON":
            # `limit`/`offset` con corte por respuesta vacia. No se confia en
            # `count` para terminar: un total declarado que miente cortaria la
            # enumeracion antes de tiempo, y perder inventario en silencio es
            # justamente lo que este connector viene a evitar.
            #
            # Y se repite el barrido, por la misma razon que `connectors/
            # tokko.py` ya tenia documentada y resuelta:
            #
            #   "Tokko reordena el conjunto entre pedidos: dos barridos
            #    identicos devuelven subconjuntos distintos, asi que una sola
            #    pasada deja afuera entre un 6% y un 14% del inventario aunque
            #    recorra todas las paginas que el total declarado implica."
            #
            # Esta estrategia lee la MISMA API desde el frontend propio de la
            # agencia y no habia heredado la contramedida. `alta inmobiliaria`
            # dio 16 en una corrida y 18 en la siguiente, once segundos
            # despues: 11 % faltante, dentro de esa banda. La cola lo leyo
            # como no idempotente y paro con radio COMPARTIDO, que detiene a
            # los dos workers.
            base_ = plan["base"]
            ruta = plan["tokko_proxy_ruta"]
            declarado = plan.get("total_declarado")
            vistos: set[str] = set()
            pagina = 0
            for _ in range(MAX_BARRIDOS_TOKKO_PROXY):
                antes = len(vistos)
                offset = 0
                while offset < TOPE_TOKKO_PROXY:
                    pagina += 1
                    try:
                        cuerpo = self.descargador.bajar(
                            f"{base_}{ruta}?limit={PAGINA_TOKKO_PROXY}"
                            f"&offset={offset}")
                    except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                        # Cortar por red caida no es haber llegado al final.
                        self.paginacion_interrumpida = True
                        break
                    try:
                        objetos = (json.loads(cuerpo) or {}).get("objects") or []
                    except (json.JSONDecodeError, TypeError):
                        break
                    if not objetos:
                        break
                    for objeto in objetos:
                        identificador = str(objeto.get("id") or "").strip()
                        if not identificador or identificador in vistos:
                            continue
                        vistos.add(identificador)
                        yield {"source_listing_id": identificador,
                               "source_url": f"{base_}/propiedad/{identificador}",
                               "pagina": pagina,
                               "tokko_objeto": objeto}
                    offset += PAGINA_TOKKO_PROXY
                # Otro barrido solo si el anterior aporto algo Y todavia falta
                # material. Repetir sin freno multiplicaria los pedidos a una
                # fuente ajena por el numero de barridos.
                if len(vistos) == antes:
                    break
                if declarado and len(vistos) >= int(declarado):
                    break
            return
        if plan["variante"] in ("SITEMAP", "CATEGORY_HTML_CATALOG"):
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
        from scraper.detail_urls import detail_query_identifier, _DETAIL_QUERY_KEYS
        query_id = detail_query_identifier(url)
        if query_id is not None:
            return query_id
        if any(k.lower() in _DETAIL_QUERY_KEYS for k in urllib.parse.parse_qs(parsed.query, keep_blank_values=True)):
            # Preserve evidence of an ambiguous identity, never collapse it
            # into "ficha.php". The write gate rejects this serialized ID.
            return url
        # Se tomaba el PRIMER numero de tres o mas cifras del ultimo segmento,
        # y en un slug ese numero suele ser otra cosa: la superficie
        # (`lote-de-1200-m2-en-venta` -> `1200`), la altura de la calle
        # (`/properties/446609/genova-1327-casa` -> `1327`, con el id real un
        # segmento antes) o un codigo al que se le cortaba la letra (`alas`
        # publica `venta-...-d104` y `venta-...-k104`, y las dos quedaban como
        # `104` dentro de la misma agencia). Medido sobre 10.337 fichas de
        # `generico`: 968 compartian id con otra de SU agencia y 2.190 con la de
        # otra; con el orden de abajo, 639 y 846, y lo que queda son en buena
        # parte la misma ficha publicada con dos rutas, donde el id igual dice
        # la verdad.
        #
        # El orden, del indicio mas fuerte al mas debil:
        #   1. un codigo al final del slug, con hasta cuatro letras delante:
        #      `...-57931`, `inmueble_6076`, `...-a222`, `...-ficha-flm423`;
        #   2. un segmento que es solo un numero: `/propiedad/882/chalet`;
        #   3. un numero al principio del slug: `/7920515-departamento-...`;
        #   4. si no, el slug entero. Nunca un numero suelto del medio.
        segmentos = [s for s in parsed.path.split("/") if s]
        ultimo = segmentos[-1] if segmentos else ""
        m = re.search(r"[-_]([a-z]{0,4}\d{3,})$", ultimo, re.I)
        if m:
            return m.group(1)
        for segmento in reversed(segmentos):
            if re.fullmatch(r"\d{3,}", segmento):
                return segmento
        m = re.match(r"^(?:[a-z]{1,3}[-_])?(\d{3,})[-_]", ultimo, re.I)
        if m:
            return m.group(1)
        return (ultimo or url)[:120]

    # --------------------------------------------------------------- normalize
    def normalize(self, crudo: dict, fuente: Fuente) -> PropiedadNormalizada | None:
        if crudo.get("php_ajax"):
            return self._normalizar_php_ajax(crudo, fuente)
        if crudo.get("bitrix_card"):
            return self._normalizar_bitrix_landing(crudo, fuente)
        if crudo.get("tokko_objeto"):
            # El objeto ya vino completo en el listado y la ficha se arma en el
            # navegador: bajarla costaria una peticion por propiedad para leer
            # menos de lo que ya tenemos.
            return self._normalizar_tokko_proxy(crudo, fuente)
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
        # Una ficha Xintel que entro por el camino HTML tambien se lee de la
        # API. Sin JavaScript, la plantilla muestra el titulo «en», la
        # descripcion vacia (`<p class="txtobs"></p>`) y dos fotos:
        # `cannonepropiedades.com.ar` se guardaba asi en sus 16 fichas, y la
        # API trae titulo, descripcion, coordenadas y 20 a 28 fotos. La senal
        # es la que la propia plantilla usa para pedir el detalle.
        if crudo.get("xintel") or self._es_ficha_xintel(html):
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
        datos = self._de_json_ld(html, url)
        if not datos.get("tipo_ld") and self._es_pagina_contenedora(principal, url):
            return self._a_revision(url, fuente)
        mapaprop = (self._detalle_mapaprop(html, url)
                    if crudo.get("mapaprop_catalog") else {})

        titulo = (limpiar(str(crudo.get("titulo_catalogo") or ""))
                  or self._titulo_de_la_ficha(html, datos, fuente))
        if not titulo:
            m = re.search(r"<title[^>]*>(.{1,200}?)</title>", html, re.S | re.I)
            titulo = limpiar(unescape(m.group(1))) if m else None
        if (not datos.get("tipo_ld") and not crudo.get("titulo_catalogo")
                and self._es_titulo_del_sitio(titulo, fuente)
                and len(self._fichas_en(principal, url)) >= 8):
            # Una pagina que solo se titula con el nombre de la inmobiliaria y
            # enlaza 8 o mas fichas es un LISTADO: `bottai`
            # (`inmuebles_list_Venta_seleccione_…`, 225 enlaces), `conti`
            # (`propiedades.php?tipoPropiedad=16`), `cannone`
            # (`propiedades.php?ope=v&p=0`) se guardaban como fichas con el
            # precio de un aviso de la grilla. Medido sobre ~170 fichas reales
            # de las agencias generico: 0 falsos positivos.
            return self._a_revision(url, fuente)

        descripcion = mapaprop.get("descripcion") or datos.get("descripcion")
        # El meta description se lee, pero va DESPUES de los rotulos
        # explicitos de la ficha. Muchos sitios ponen el mismo texto
        # institucional en todas sus paginas -«AB Negocios Inmobiliarios es
        # una inmobiliaria de la ciudad de Rafaela…»- y la ficha tiene debajo
        # su «Descripcion de la Propiedad». Tomando el meta primero, el rotulo
        # no se leia nunca y el runner, con razon, descartaba el texto
        # repetido: 28 agencias, 1.774 fichas (medido 2026-09-24). En 22 de 68
        # fichas sondeadas el rotulo trae la descripcion propia donde el meta
        # traia el eslogan del sitio o un resumen de una linea.
        meta = None
        if not descripcion:
            m = re.search(r'<meta[^>]+(?:name|property)="(?:og:)?description"'
                          r'[^>]+content="([^"]{20,600})"', html, re.I)
            meta = limpiar(unescape(m.group(1))) if m else None
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
        if (not descripcion and meta is None
                and crudo.get("wordpress_category_catalog")):
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

        if not descripcion:
            # Regla general en vez del enesimo patron por sitio: un rotulo cuyo
            # texto es EXACTAMENTE "Descripcion", seguido del bloque que lo
            # sigue. Los patrones de arriba estan atados a nombres de clase
            # concretos -title_blue, separador-titulo- y no cubren
            # alejoandresen.com.ar, que usa <h3>Descripcion</h3><p>...</p>.
            #
            # Se exige que el rotulo sea solo eso: un <p> que MENCIONE la
            # palabra es prosa de la ficha, y tomar lo que le sigue traeria
            # cualquier cosa.
            descripcion = self._descripcion_rotulada(principal)
        if descripcion and meta and self._es_su_comienzo(descripcion, meta):
            # El rotulo solo trajo el comienzo de lo que el meta dice entero:
            # `funesinmobiliaria` rotula «VENTA - Casa de 4 dormitorios -
            # Roldan.» y el meta sigue con la descripcion.
            descripcion = meta
        if not descripcion:
            descripcion = meta

        precio = mapaprop.get("precio", datos.get("precio"))
        moneda = mapaprop.get("moneda") or datos.get("moneda")
        if precio is None or moneda is None:
            # Solo con moneda explicita al lado. Un numero suelto en el texto
            # puede ser cualquier cosa, y un precio equivocado se publica sin
            # que nadie lo note.
            # Sin `re.I` se perdia `u$s 85.000` en minuscula, que es como lo
            # escriben las fuentes que arman la ficha a mano.
            # Y sin `U\$D` se perdia el precio ENTERO de las fuentes que lo
            # escriben con D. No alcanzaba con arreglar el guardian de forma:
            # el guardian decide si la ficha entra, esta expresion decide si
            # el precio se lee. Ver el comentario de RE_PRECIO_CON_MONEDA.
            m = re.search(r"(USD|U\$[SD]|US\$|\$|ARS)\s*([\d][\d.,]{2,15})",
                          texto, re.I)
            if m:
                visible = a_numero(m.group(2))
                # La moneda de otra cifra (expensas, otra unidad) no puede
                # completar un precio estructurado. Se exige concordancia.
                if precio is None or visible == a_numero(precio):
                    moneda = moneda or detectar_moneda(m.group(1))
                    if precio is None:
                        precio = visible

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
        if not gallery_images and len(imagenes) < FOTOS_MINIMAS:
            # Solo como respaldo: con fotos propias el visor suele enlazar la
            # version grande de las mismas, y sumarlas duplicaria la galeria.
            for u in self._fotos_de_enlaces(principal, url):
                if u not in vistas:
                    vistas.add(u)
                    imagenes.append(u)

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
            m = RE_COORD.search(html) or RE_COORD_ARREGLO.search(html)
            if m:
                lat, lon = float(m.group(1)), float(m.group(2))

        campos = {
            "latitud": lat,
            "longitud": lon,
            "precio": precio,
            "moneda": moneda,
            "operacion": (detectar_operacion(f"{titulo or ''} {url}")
                          or crudo.get("operacion_catalogo")
                          or self._operacion_en_la_ficha(texto_campos, precio)
                          or self._operacion_de_la_etiqueta(principal_campos)
                          or self._operacion_desde_title(html)),
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
                principal, texto_campos, ETIQUETAS_DE_CONTEO["dormitorios"],
                datos.get("dorm")),
            "banos": None if es_emprendimiento else self._cuenta_de_ficha(
                principal, texto_campos, ETIQUETAS_DE_CONTEO["banos"], datos.get("banos")),
            "ambientes": None if es_emprendimiento else (
                self._cuenta_de_ficha(principal, texto_campos,
                                      ETIQUETAS_DE_CONTEO["ambientes"],
                                      datos.get("ambientes"))
                or self._ambientes_del_titulo(titulo)),
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
        # Un rotulo que funde dos atributos no se pudo asignar a ninguno. Eso
        # es la validacion funcionando, no un fallo de extraccion: la
        # certificacion los trata distinto y uno de los dos bloquea.
        marcado_campos = normalizar_texto_campos(unescape(principal or ""))
        for nombre, etiqueta in (("dormitorios", r"dormitorios?|habitaciones?"),
                                 ("ambientes", r"ambientes?"),
                                 ("banos", r"ba[nñ]os?|toilettes?"),
                                 ("cocheras", r"cocheras?|garages?")):
            if (campos.get(nombre) is None
                    and self._rotulo_compuesto(marcado_campos, etiqueta)
                    and nombre not in fuera):
                fuera.append(nombre)
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
                     or self._direccion_de(principal)
                     or self._par_rotulado(principal, r"direcci[oó]n"))
        # «Barrio: Remedios de Escalada, Lanús, Buenos Aires» (`bardi`): con
        # tres tramos o mas son barrio, ciudad y provincia, como la ficha los
        # escribe. La geografia compartida los valida despues contra el
        # catalogo («Lanús» resuelve exacto; lo que no resuelve no se afirma).
        barrio_par = ciudad_par = provincia_par = None
        # Solo «Barrio»: «Ubicación» es tambien la posicion en el edificio
        # («Ubicación: Frente» en la misma ficha de bardi).
        ubicacion_par = self._par_rotulado(principal, r"barrio")
        if ubicacion_par:
            tramos = [t.strip() for t in ubicacion_par.split(",") if t.strip()]
            barrio_par = tramos[0] if tramos else None
            if len(tramos) >= 3:
                ciudad_par, provincia_par = tramos[1], tramos[-1]
                if barrio_par.casefold() == ciudad_par.casefold():
                    barrio_par = None
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
            # «627 Visitas al momento» al final de la descripcion (`ferrari`,
            # `bottega`, `diaz collins`: 173 fichas) es un contador que nuestra
            # propia visita incrementa: con el, la segunda corrida nunca es
            # igual a la primera. No describe a la propiedad.
            descripcion=(re.sub(r"\s*\b\d[\d.,]*\s+visitas\s+al\s+momento\s*$", "",
                                descripcion or "", flags=re.I)[:4000] or None),
            precio=precio,
            moneda=moneda,
            operacion=campos["operacion"],
            tipo_propiedad=campos["tipo_propiedad"],
            direccion=direccion,
            barrio=mapaprop.get("barrio") or datos.get("barrio") or barrio_par,
            ciudad=mapaprop.get("ciudad") or datos.get("ciudad") or ciudad_par,
            provincia=(mapaprop.get("provincia") or datos.get("provincia")
                       or provincia_par),
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

    def _normalizar_tokko_proxy(self, crudo: dict,
                                fuente: Fuente) -> PropiedadNormalizada | None:
        """Arma la propiedad con el objeto que ya trajo la API del sitio.

        No se baja la ficha: el objeto de Tokko viene completo en el listado, y
        en estos frontends la ficha es una pagina que se arma en el navegador,
        asi que pedirla costaria una peticion por propiedad para leer menos.

        Nada se inventa. Lo que el objeto no trae queda en None y el contrato
        de propiedad decide despues en que superficies puede aparecer.
        """
        objeto = crudo.get("tokko_objeto") or {}
        if not objeto:
            return None

        def texto(valor: Any) -> str | None:
            if isinstance(valor, dict):
                valor = valor.get("name") or valor.get("nombre")
            valor = limpiar(str(valor)) if valor not in (None, "") else None
            return valor or None

        # Tokko publica una operacion por propiedad, con su precio adentro.
        operacion = precio = moneda = None
        for op in (objeto.get("operations") or []):
            if not isinstance(op, dict):
                continue
            operacion = detectar_operacion(str(op.get("operation_type") or "")) \
                or operacion
            for p in (op.get("prices") or []):
                if isinstance(p, dict) and p.get("price"):
                    precio = a_numero(str(p.get("price")))
                    moneda = detectar_moneda(str(p.get("currency") or ""))
                    break
            if precio is not None:
                break

        ubicacion = objeto.get("location") or {}
        imagenes = [i.get("image") for i in (objeto.get("photos") or [])
                    if isinstance(i, dict) and i.get("image")]

        propiedad = PropiedadNormalizada(
            canonical_agency_id=fuente.canonical_agency_id,
            source_listing_id=str(crudo["source_listing_id"]),
            source_url=crudo["source_url"],
            connector="generico",
            inmobiliaria_id=fuente.inmobiliaria_id,
            titulo=texto(objeto.get("publication_title")) or texto(objeto.get("address")),
            descripcion=texto(objeto.get("description")),
            operacion=operacion,
            tipo_propiedad=texto(objeto.get("type")),
            precio=precio,
            moneda=moneda,
            direccion=texto(objeto.get("address")),
            barrio=texto(ubicacion.get("name")),
            provincia=texto(ubicacion.get("state")),
            latitud=_coordenada(objeto.get("geo_lat")),
            longitud=_coordenada(objeto.get("geo_long")),
            ambientes=_entero(objeto.get("room_amount")),
            dormitorios=_entero(objeto.get("suite_amount")),
            banos=_entero(objeto.get("bathroom_amount")),
            superficie_total=_decimal(objeto.get("total_surface")),
            superficie_cubierta=_decimal(objeto.get("roofed_surface")),
            imagenes=imagenes,
            extra={"tokko_proxy": True},
        )
        return propiedad

    @staticmethod
    def _es_ficha_xintel(html: str) -> bool:
        """La ficha trae los cuatro parametros con que pide su detalle."""
        return all(re.search(rf'["\']{nombre}["\']\s*:\s*["\'][^"\']+["\']', html or "", re.I)
                   for nombre in ("suc", "global", "apiK", "id"))

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
        # Sin el detalle, la ficha quedaba con la fila del listado -una foto,
        # sin coordenadas- y esos campos se marcaban como no provistos por la
        # fuente: una ausencia inventada. `bondar` lo sufrio en 3 fichas de una
        # corrida y 1 de la otra. Las 10 agencias Xintel publican siempre los
        # parametros; si faltan, o la API no devuelve la ficha, es un fallo del
        # detalle y se cuenta como tal.
        if not all(detail_params.values()):
            raise ErrorTransitorio("la ficha Xintel no trae los parametros del detalle")
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
        if not details or not isinstance(details[0], dict):
            raise ErrorTransitorio("Xintel no devolvio la ficha")
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
        # El texto de la ficha viaja en `in_obs`, como HTML escapado. `in_des`
        # es una BANDERA -«True»/«False»-: leerla como descripcion guardo
        # «True» en 256 fichas y perdio el texto en otras 1.014, en las 10
        # agencias Xintel (medido 2026-09-24); ninguna tenia la real.
        description = limpiar(_texto(unescape(str(row.get("in_obs") or "")))) or None
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
            # La API compone el titulo y escribe el cero de ambientes a veces
            # «0 ambientes» y a veces «monoambiente ambientes», con o sin
            # entidades: `bondar` nunca repetia sus titulos entre corridas.
            titulo=re.sub(r"\s+(?:0|monoambiente)\s+ambientes\s*$", "",
                          limpiar(unescape(str(row.get("titulo") or ""))) or "",
                          flags=re.I) or None,
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

        Ese arreglo avanzo un paso y se detuvo, y el 2026-09-21 costo 46
        propiedades reales en dos agencias, con dos formas distintas de la
        misma causa:

          - `chambouleyron` publica `<img src="uploads/foto341-1" />`, sin
            extension NI cabecera Content-Type. Las baje: son JPEG de 380 a
            520 KB. Sus 16 fichas traian precio y operacion y se rechazaron
            por no llegar a FOTOS_MINIMAS.
          - `corporacion inmobiliaria` publica
            `<img src='https://gvamax.ar/serverdata/554/Fotos/Fi158411.554'>`.
            Ahi fallan DOS cosas: la comilla simple, que `RE_IMG_ATRIBUTO` no
            contemplaba, y el sufijo `.554` -el id de la agencia- que no es
            una extension conocida. Sus 30 fichas se perdieron y lo que si
            entraba eran cinco piezas de adorno: el logo de la plataforma, las
            flechas del carrusel y dos sellos de colegiacion.

        La regla nueva no afloja parejo, y la distincion es la que importa:

          - lo que sale de un `src` de `<img>` **es una imagen por
            construccion**, asi que exigirle extension es redundante;
          - lo que se pesca del texto suelto con `RE_IMG` no tiene esa
            garantia, y ahi la extension se sigue exigiendo.

        Un respaldo por `Content-Type` no servia: el servidor de
        `chambouleyron` no manda ninguno y el de `corporacion` manda
        `image/jpeg`, asi que resolvia uno de los dos casos.
        """
        del_texto = list(RE_IMG.findall(html or ""))
        de_etiqueta = []
        for m in RE_IMG_ATRIBUTO.finditer(html or ""):
            de_etiqueta.append(_url_del_atributo(m.group(1) or m.group(2) or ""))
        salida, vistas = [], set()
        for u, exige_extension in ([(x, True) for x in del_texto]
                                   + [(x, False) for x in de_etiqueta]):
            if not u:
                continue
            u = identidad_de_imagen(urllib.parse.urljoin(url, unescape(u.strip())))
            if exige_extension and not RE_EXTENSION.search(u):
                continue
            if u in vistas or RE_NO_ES_FOTO.search(u):
                continue
            vistas.add(u)
            salida.append(u)
        return salida

    @staticmethod
    def _fotos_de_enlaces(html: str, url: str) -> list[str]:
        """Las fotos que la ficha solo publica como enlace de su visor.

        `forchino` perdio 19 fichas reales -precio, operacion, 20 fotos- por
        no llegar a FOTOS_MINIMAS: el `<img>` del carrusel esta comentado y
        las fotos quedan como `<a href="fotos/imagen_…jpeg" class=
        "popup-image">` y como fondo CSS. Un enlace no es una imagen por
        construccion, asi que se exige la extension, como a lo que se pesca
        del texto suelto.
        """
        salida, vistas = [], set()
        for m in RE_ENLACE_A_FOTO.finditer(html or ""):
            u = _url_del_atributo(m.group(1) or m.group(2) or "")
            if not u:
                continue
            u = identidad_de_imagen(urllib.parse.urljoin(url, unescape(u.strip())))
            # En la RUTA: un «compartir en Pinterest» lleva la foto en la
            # query (`?media=…/foto.jpg`) y no es una foto de la ficha.
            if (not RE_EXTENSION.search(urllib.parse.urlparse(u).path)
                    or u in vistas or RE_NO_ES_FOTO.search(u)):
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
    def _par_rotulado(html: str, etiqueta: str) -> str | None:
        """El valor de un par rotulo/valor: <p>Dirección</p><p>Av. Rosales 515</p>.

        Solo la estructura -rotulo solo en su elemento, valor en el siguiente
        y sin marcado adentro-: el texto aplanado no dice donde termina el
        valor. `bardi` publica asi direccion y barrio en sus 90 fichas.
        """
        m = re.search(
            rf"<(p|span|dt|th|td|div|label|strong|h[1-6])\b[^>]*>\s*(?:{etiqueta})\s*:?\s*"
            rf"</\1>\s*<(p|span|dd|td|div)\b[^>]*>\s*([^<>]{{2,150}}?)\s*</\2>",
            html or "", re.I)
        return limpiar(unescape(m.group(3))) if m else None

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
        # El tope de 200 es para el TEXTO del titulo, no para su marcado: el h1
        # de `cortespropiedades.com.ar` son dos spans con sangria -mas de 200
        # caracteres de HTML para 60 de texto- y no entraba.
        for patron in (r'<meta[^>]+property="og:title"[^>]+content="([^"]{1,200})"',
                       r"<h1[^>]*>(.{3,2000}?)</h1>",
                       r"<title[^>]*>(.{1,200}?)</title>"):
            m = re.search(patron, html, re.S | re.I)
            if m:
                visible = limpiar(unescape(re.sub(r"<[^>]+>", " ", m.group(1))))
                if visible and len(visible) <= 200:
                    candidatos.append(visible)

        agencia = (fuente.agency_name or "").lower().strip()
        restos: list[str] = []
        for c in candidatos:
            if not c:
                continue
            partes = re.split(r"\s*[|–—]\s*", c)
            limpio = partes[0].strip()
            if agencia and limpio.lower() in (agencia, agencia.replace("  ", " ")):
                # Es el nombre de la inmobiliaria, no la ficha. Pero puede venir
                # DELANTE del titulo: `cortespropiedades.com.ar` publica el h1
                # «Cortes Propiedades | Departamento 1 dormitorio en villa
                # sarita» y se descartaba entero; las 23 fichas quedaban
                # tituladas con el nombre de la agencia. Lo que sigue se guarda
                # como segunda opcion: un candidato limpio sigue ganando, y un
                # «Agencia | Inicio» no le quita el lugar a un h1 bueno.
                resto = " | ".join(p.strip() for p in partes[1:] if p.strip())
                if len(resto) >= 8:
                    restos.append(resto)
                continue
            return c
        if restos:
            return restos[0]
        return next((c for c in candidatos if c), None)

    @staticmethod
    def _es_titulo_del_sitio(titulo: str | None, fuente: Fuente) -> bool:
        """El titulo es solo el nombre de la inmobiliaria, antes del separador."""
        def plano(texto: str) -> str:
            texto = unicodedata.normalize("NFKD", texto or "")
            texto = "".join(c for c in texto if not unicodedata.combining(c))
            return re.sub(r"\s+", " ", texto).strip().lower()
        nombre = plano(fuente.agency_name)
        primero = plano(re.split(r"\s*[|–—-]\s*", titulo or "")[0])
        return bool(nombre) and primero == nombre

    def _a_revision(self, url: str, fuente: Fuente) -> None:
        """Una pagina que no es ficha: se cuenta como detalle a revisar.

        No es prueba de que la fuente este vacia. El runner la cuenta como
        detalle fallido, asi que dos errores iguales no pueden volverse
        CERTIFIED_COMPLETE.
        """
        if not hasattr(self, "descartes"):
            self.descartes = []
        if len(self.descartes) < 500:
            self.descartes.append({"source_url": url,
                                   "canonical_agency_id": fuente.canonical_agency_id,
                                   "motivo": "PAGINA_CONTENEDORA_REQUIERE_REVISION"})
        return None

    @staticmethod
    def _es_pagina_contenedora(html: str, url: str | None = None) -> bool:
        """A generic catalogue heading AND an explicit filter form, not a slug.

        Never reject an incomplete property because price/images are missing.
        A shared institutional title alone is not sufficient evidence either.
        """
        heading = re.search(r"<h1\b[^>]*>(.*?)</h1>", html or "", re.I | re.S)
        if not heading:
            return False
        titulo = _texto(heading.group(1)).strip().lower()
        if re.fullmatch(
                r"propiedades|inmuebles|cat[aá]logo(?: de propiedades)?|listado(?: de propiedades)?",
                titulo):
            return any(re.search(r"\b(?:aplicar\s+filtros|filtrar)\b", _texto(form), re.I)
                       for form in re.findall(r"<form\b[^>]*>(.*?)</form>", html or "", re.I | re.S))
        # La pagina de una CATEGORIA: «Oficinas en Venta», «DEPARTAMENTOS EN
        # VENTA O EN ALQUILER», con la grilla de avisos debajo. `cbdestino` y
        # `casablanca` las guardaron como fichas, con el tipo y la operacion
        # sacados del encabezado y hasta el precio de un aviso de la grilla.
        # Se exige un tipo EN PLURAL seguido de la operacion, sin cifras, y al
        # menos 5 fichas enlazadas; el llamador ya descarto las paginas con
        # JSON-LD de propiedad. «Propiedades» a secas no alcanza: es el
        # encabezado de sitio de muchas fichas reales. Medido sobre 157 fichas
        # reales de las agencias generico: 0 falsos positivos.
        plano = "".join(c for c in unicodedata.normalize("NFKD", titulo)
                        if not unicodedata.combining(c))
        plano = re.sub(r"\s+", " ", plano).strip()
        # Una ficha lleva su id en la ruta; una categoria no. `fogliese`
        # publica un emprendimiento de lotes como
        # /propiedad/186944_lotes-en-venta-zona-turistica-tematica/, titulado
        # «Lotes En Venta …» y con 6 relacionadas: con esto quedaba afuera y
        # paraba la familia. Las categorias medidas (/Casa-en-venta,
        # /venta-casas-posadas/, /inmuebles/salones-para-venta) no tienen id.
        if url and re.search(r"\d{4,}", urllib.parse.urlparse(url).path):
            return False
        # Tambien la categoria titulada con el tipo SOLO, en singular:
        # `fios.com.ar/Casa-en-venta` tiene de encabezado «Casa» y 23 fichas
        # debajo. Con 5 o mas fichas enlazadas y sin JSON-LD, 0 falsos
        # positivos sobre ~170 fichas reales (2026-09-25).
        sueltos = (r"casas?|departamentos?|deptos?|ph|duplex|oficinas?|locales?|terrenos?|"
                   r"lotes?|galpon(?:es)?|cocheras?|campos?|quintas?|chacras?|fincas?|"
                   r"salon(?:es)?|depositos?")
        if re.fullmatch(sueltos, plano):
            return len(GenericoConnector._fichas_en(html, url)) >= 5 if url else False
        tipos = (r"casas|departamentos|deptos|duplex|oficinas|locales|terrenos|lotes|"
                 r"galpones|cocheras|campos|quintas|chacras|fincas|salones|naves|depositos")
        if not re.fullmatch(
                rf"(?:{tipos})(?:\s*(?:,|y|e|o)\s*(?:{tipos}))*\s+(?:en|para|de)\s+"
                rf"(?:venta|alquiler)\b[^0-9]{{0,60}}", re.sub(r"\s+", " ", plano)):
            return False
        return len(GenericoConnector._fichas_en(html, url)) >= 5 if url else False

    @staticmethod
    def _operacion_desde_title(html: str) -> str | None:
        """Fallback acotado al titulo del documento, nunca al menu del sitio."""
        title = re.search(r"<title\b[^>]*>(.*?)</title>", html or "", re.I | re.S)
        return (GenericoConnector._operacion_en_la_ficha(_texto(title.group(1)))
                if title else None)

    @staticmethod
    def _operacion_de_la_etiqueta(html: str) -> str | None:
        """Un elemento cuyo texto ENTERO es «En venta» o «En alquiler».

        La plantilla `/ad/` (filippini, altos servicios, amadeo, caruso, emir,
        clavero…) marca la ficha con `<div class="sale"><div>En Venta</div>
        </div>` y nada mas la dice: el menu repite «Venta Alquiler Temporal» y
        el precio queda lejos. 205 de 380 fichas de esas 13 agencias estaban
        sin operacion (medido 2026-09-24). El menu dice «Venta» a secas; la
        etiqueta lleva el «En». Si aparecen dos operaciones distintas -las
        etiquetas de propiedades relacionadas- no se elige ninguna.
        """
        marcado = normalizar_texto_campos(unescape(html or ""))
        halladas = {m.group(1).lower().replace(" ", "_")
                    for m in re.finditer(
                        r">\s*en\s+(alquiler\s+temporario|venta|alquiler)\s*<",
                        marcado, re.I)}
        halladas = {re.sub(r"_+", "_", h) for h in halladas}
        if not halladas:
            # Sin «En»: `cantale` (<span class="rounded-full …">Venta</span>) y
            # `altos` (<span class="tag tag--op">Venta</span>). Solo en <span>
            # o <div> -el menu va en <a>- y con la misma regla de una sola
            # operacion. Muestra de 25 fichas que ya tenian operacion: donde
            # la etiqueta aparece (6), coincide en las 6.
            halladas = {re.sub(r"\s+", "_", m.group(1).lower()) for m in re.finditer(
                r"<(?:span|div)\b[^>]*>\s*(alquiler\s+temporario|venta|alquiler)\s*"
                r"</(?:span|div)>", marcado, re.I)}
        return halladas.pop() if len(halladas) == 1 else None

    @staticmethod
    def _operacion_en_la_ficha(texto: str, precio: Any = None) -> str | None:
        """La operacion cuando el titulo y la url no la dicen.

        Un tercio de las fichas de sitios propios titulan "Departamento 2
        ambientes" y nada mas. El cuerpo si lo dice, pero el menu de la pagina
        tambien -"Ventas | Alquileres"-, asi que solo se acepta cuando aparece
        UNA de las dos operaciones en el arranque de la ficha. Si aparecen las
        dos, la pagina no esta diciendo cual es: se deja vacio antes que elegir.

        El ORDEN de las cinco preguntas es el arreglo, no un detalle.
        `alquilad[oa]` estaba antes que todo lo demas y convirtio **64
        propiedades en venta en alquileres**: «IDEAL INVERSIONISTAS, SE VENDE
        ALQUILADO» y «SE VENDE ALQUILADO!!!» son ventas con inquilino adentro,
        y las publicamos como alquiler. Un dato equivocado es peor que uno
        vacio: el que busca comprar no las ve y el que busca alquilar las ve y
        no puede alquilarlas.

        Lo que la propiedad ES manda sobre el estado en que ESTA. El estado
        consumado sigue sirviendo -para eso se escribio- pero ultimo, cuando
        la pagina no dijo la operacion de ninguna otra forma.
        """
        # Un rotulo explicito manda, este donde este: "Operacion: Venta" no se
        # puede confundir con el menu.
        # «alquiler temporario» va ANTES que «alquiler»: en el orden inverso la
        # alternativa larga no ganaba nunca. Y «Tipo de operación En venta»
        # (la plantilla `/site/properties/`: ferrari, ciam, bottega, espina)
        # tambien es un rotulo; el «en» solo se acepta detras de «tipo de», no
        # en prosa como «excelente operación en alquiler».
        rotulo = (re.search(r"tipo\s+de\s+operaci[oó]n\s*:?\s*en\s+"
                            r"(alquiler temporario|venta|alquiler)\b", texto or "", re.I)
                  or re.search(r"operaci[oó]n\s*:?\s*(alquiler temporario|venta|alquiler)\b",
                               texto or "", re.I))
        if rotulo:
            return rotulo.group(1).lower().replace(" ", "_")

        if re.search(r"\balquiler\s+inicial\b", texto or "", re.I):
            return "alquiler"

        arranque = (texto or "")[:600].lower()
        venta = bool(re.search(r"\b(en venta|se vende|venta)\b", arranque))
        alquiler = bool(re.search(r"\b(en alquiler|se alquila|alquiler)\b", arranque))
        if venta != alquiler:
            if alquiler and re.search(r"\b(temporario|temporal)\b", arranque):
                return "alquiler_temporario"
            return "venta" if venta else "alquiler"

        junto_al_precio = operacion_junto_al_precio(texto, precio)
        if junto_al_precio:
            return junto_al_precio

        # El estado consumado, y SOLO cuando el aviso ya no publica precio.
        #
        # Esa condicion es la que la regla decia tener y no tenia: se escribio
        # para que «Alquilada» no dejara sin operacion a un aviso que ya no
        # publica precio. Con precio adelante significa otra cosa. `bottai`
        # cierra sus descripciones con el estado -«...cocina, lavadero y patio
        # pequeno. Primer piso por escalera. Alquilado. Precio: U$S55.000»- y
        # eso es un departamento EN VENTA con inquilino adentro: 48 de sus
        # propiedades quedaron publicadas como alquileres de 55.000 a 250.000
        # dolares. Lo mismo en `alma di matteo` -«IDEAL INVERSIONISTAS, SE
        # VENDE ALQUILADO»- y en `buhler` -«En venta USD 33.000 ... Alquilado
        # hasta 30-09-2026»-.
        #
        # 64 propiedades tenian el estado consumado en su texto y las 64
        # estaban guardadas como alquiler. Con precio, el aviso esta vivo y la
        # operacion tiene que salir de lo que el aviso dice; si no lo dice, se
        # queda vacia. Un campo vacio se puede completar despues; uno
        # equivocado se publica.
        if not precio:
            if re.search(r"\balquilad[oa]\b", texto or "", re.I):
                return "alquiler"
            if re.search(r"\bvendid[oa]\b", texto or "", re.I):
                return "venta"
        return None

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
        atributos = {x.lower() for x in RE_ATRIBUTOS_TXT.findall(t)}
        describe = bool(RE_OPERACION_TXT.search(t)) or len(atributos) >= 2
        # UN atributo alcanza si la pagina ademas publica precio.
        #
        # `alma di matteo` perdio sus 6 fichas por esta clausula y quedo en
        # cero. Son propiedades reales, hechas a mano en HTML estatico:
        # "Ranelagh Oeste - Calle 120", U$S 130.000, 8 fotos, 20x54 mts, y UN
        # solo atributo reconocido -`cochera`-, sin la palabra "venta" en el
        # texto porque el aviso dice "Se escuchan propuestas". Lo mismo
        # `Bosco Building`, U$S 118.000, con `ambiente`.
        #
        # Se exige el precio CON MONEDA en el texto, no un numero suelto.
        # Un test que ya existia lo mordio y tenia razon: "Analisis de la
        # superficie construida en 2026" trae un numero y una palabra de
        # atributo, y es una nota de mercado. La regla del censo decia
        # "precio con moneda" y el comentario de `RE_OPERACION_TXT` ya lo
        # anticipaba -«una nota del blog no suele traer un precio con moneda
        # al lado»-; faltaba implementarlo.
        #
        # El precio es el discriminante, y esta medido: de los 100 rechazos
        # del guardian registrados en TODO el corpus, ninguno traia precio.
        # `area_cliente.php?sec=sol` y `quienes-somos.php` no publican uno.
        # Con esta concesion ninguno de los 100 entraria.
        #
        # Ademas acerca la regla a la que verifico las formas -"precio con
        # moneda, operacion o atributos, y fotos", un O entre las tres-.
        # `_confirma_ficha` decia ser ese mismo criterio y era mas estricto:
        # exigia precio Y ademas operacion o dos atributos. Con el cambio
        # sigue siendo mas estricto que el censo, no menos.
        if (not describe and precio is not None and atributos
                and RE_PRECIO_CON_MONEDA.search(t)):
            describe = True
        # La ausencia de fotos no invalida una ficha cuya pertenencia al
        # catalogo ya se demostro. Las formas amplias siguen exigiendo fotos.
        fotos_suficientes = catalogo_verificado or len(imagenes) >= FOTOS_MINIMAS
        # Sin precio numerico, pero describiendo el inmueble en detalle.
        #
        # La concesion de "consultar precio" ya estaba razonada mas arriba
        # -«es una propiedad publicada, no una nota»- y estaba implementada
        # SOLO para schema.org. Las otras cuatro fichas de `alma di matteo`
        # publican `Precio Consulte` con cinco atributos reconocidos
        # -ambiente, bano, cochera, cubierta, dormitorio- y ocho fotos, y no
        # tienen JSON-LD. Quedaban afuera por no traer un numero.
        #
        # El umbral sale de los datos, no de la intuicion. Medidas las 53
        # paginas institucionales distintas que el guardian rechazo en todo el
        # corpus: 45 tienen CERO atributos reconocidos, 4 tienen uno, y
        # NINGUNA llega a cuatro. Las unicas cuatro con cuatro o mas son
        # justamente las propiedades reales de esta agencia. El hueco entre 1
        # y 4 es lo que hace seguro el corte.
        #
        # Incluye las paginas de portal de `gama` -`historia.php`,
        # `galerias.html`-, que era el riesgo que habia que descartar: tienen
        # cero o un atributo, no cuatro.
        describe_en_detalle = len(atributos) >= ATRIBUTOS_SIN_PRECIO
        return ((precio is not None or bool(tipo_ld) or catalogo_verificado
                 or describe_en_detalle) and describe and fotos_suficientes)

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
    def _de_json_ld(html: str, url: str | None = None) -> dict[str, Any]:
        """Lo que schema.org publica ya tipado.

        Cuando esta, gana sobre cualquier heuristica de texto: es un contrato
        publico, no una convencion visual que cambia con el tema del sitio.
        """
        out: dict[str, Any] = {}
        candidatos: list[tuple[int, str, dict]] = []
        for bloque in RE_LD.findall(html):
            try:
                # Algunos proveedores emiten saltos de linea literales dentro
                # de strings JSON-LD. Son invalidos bajo strict=True pero el
                # resto del objeto sigue siendo JSON inequívoco y publico.
                dato = json.loads(bloque.strip(), strict=False)
            except ValueError:
                continue
            for nodo in _aplanar_ld(dato):
                tipos = nodo.get("@type") or []
                tipos = [tipos] if isinstance(tipos, str) else tipos
                if not isinstance(tipos, list):
                    continue
                # `CommercialRealEstate` no es de schema.org pero lo publica
                # `elgart` con la direccion; sin el, solo entraba el `Offer`
                # hijo y la ficha se quedaba sin localidad.
                permitidos = {"Residence", "Apartment", "House", "Product", "Offer",
                              "RealEstateListing", "SingleFamilyResidence", "Place",
                              "Accommodation", "ApartmentComplex", "CommercialRealEstate"}
                tipos = [t.rsplit("/", 1)[-1] for t in tipos if isinstance(t, str)]
                tipo = next((t for t in tipos if t in permitidos), None)
                # RealEstateAgent describe una agencia, no su inventario.
                # WebSite/Organization sin tipo tampoco prueban una ficha.
                if not tipo:
                    continue
                concretos = {"Residence", "Apartment", "House", "RealEstateListing",
                             "SingleFamilyResidence", "Accommodation", "ApartmentComplex",
                             "CommercialRealEstate"}
                # Flattening also yields nested Offer nodes. They are not a
                # second property and must not compete with their parent.
                prioridad = 0 if tipo in concretos else (2 if tipo == 'Offer' else 1)
                # A Place with the office address is not property evidence.
                if tipo == "Place" and not nodo.get("offers"):
                    continue
                candidatos.append((prioridad, tipo, nodo))
        if not candidatos:
            return out
        if url:
            def identidad(value):
                if not isinstance(value, str):
                    return None
                return urllib.parse.urldefrag(urllib.parse.urljoin(url, value))[0].rstrip('/')
            objetivos = {identidad(u) for u in identidades_de_la_pagina(html, url)}

            def es_de_esta_pagina(nodo: dict) -> bool:
                if any(identidad(nodo.get(key)) in objetivos for key in ('url', '@id')):
                    return True
                # Un `Product` sin url propia se identifica por su OFERTA, que
                # es la que lleva la url. Sin esto, al sumar la identidad
                # declarada, la oferta aplanada coincidia sola y le ganaba al
                # producto que la contiene: el aviso quedaba con `titulo: None`
                # teniendo el nombre escrito un nivel mas arriba.
                ofertas = nodo.get('offers')
                ofertas = ofertas if isinstance(ofertas, list) else [ofertas]
                return any(isinstance(o, dict) and identidad(o.get('url')) in objetivos
                           for o in ofertas)

            coincidentes = [item for item in candidatos if es_de_esta_pagina(item[2])]
            if coincidentes:
                candidatos = coincidentes
            else:
                candidatos = [item for item in candidatos
                              if not any(item[2].get(key) for key in ('url', '@id'))]
        if not candidatos:
            return out
        prioridad = min(item[0] for item in candidatos)
        candidatos = [item for item in candidatos if item[0] == prioridad]
        # Never complete one property's fields from another property's node.
        # Identical duplicate responsive blocks can safely be collapsed.
        unicos = {json.dumps(item[2], sort_keys=True, ensure_ascii=False): item
                  for item in candidatos}
        if len(unicos) != 1:
            return out
        _, tipo, nodo = next(iter(unicos.values()))
        out["tipo_ld"] = tipo
        out["via"] = "json-ld"
        out["titulo"] = limpiar(nodo.get("name"))
        out["descripcion"] = limpiar(nodo.get("description"))
        oferta = nodo if "price" in nodo else (nodo.get("offers") or {})
        if isinstance(oferta, list):
            oferta = oferta[0] if oferta else {}
        if isinstance(oferta, dict):
            out["precio"] = a_numero(oferta.get("price"))
            moneda = oferta.get("priceCurrency")
            m = moneda.upper().strip() if isinstance(moneda, str) else ''
            out["moneda"] = m if m in ("ARS", "USD") else None
        dire = nodo.get("address") or _de_su_entidad(nodo, "address")
        if isinstance(dire, dict):
            # Algunos sitios escriben entidades HTML dentro del JSON:
            # «San Miguel de Tucum&aacute;n». Se desescapa aca, en la fuente.
            def texto_de(valor: Any) -> str | None:
                return limpiar(unescape(valor)) if isinstance(valor, str) else limpiar(valor)
            out["direccion"] = texto_de(dire.get("streetAddress"))
            out["ciudad"] = texto_de(dire.get("addressLocality"))
            out["provincia"] = texto_de(dire.get("addressRegion"))
            # `fenixxweb.com` pone la localidad aca y el departamento en
            # `addressLocality`; la geografia compartida decide cual es cual.
            # Si repite la ciudad no agrega nada y no se afirma como barrio.
            barrio = texto_de(dire.get("addressNeighborhood"))
            if barrio and (barrio or "").strip().lower() != (out["ciudad"] or "").strip().lower():
                out["barrio"] = barrio
        # Los conteos que schema.org publica tipados. `normalize` ya los pedia
        # -`datos.get("dorm")`, `datos.get("banos")`- y nunca se escribian: el
        # contrato publico de la ficha quedaba sin leer y los conteos salian
        # solo del texto.
        #
        # Medido sobre 58 fichas reales con JSON-LD: dormitorios coincide con
        # el texto en 30 de 30, banos en 8 de 8, ambientes en 13 de 15. Y en
        # las dos de ambientes que no coinciden el que estaba mal era el
        # TEXTO: la ficha muestra «+4 Ambientes» -un contador que topa en
        # cuatro- y la descripcion y el JSON-LD dicen 5. `floorSize` no se
        # usa: no dice si es superficie total o cubierta, y en 2 de 8 no
        # coincidia con la total.
        for clave, destino in (("numberOfRooms", "ambientes"),
                               ("numberOfBedrooms", "dorm"),
                               ("numberOfBathroomsTotal", "banos"),
                               ("numberOfBathrooms", "banos")):
            if out.get(destino) is not None:
                continue
            valor = nodo.get(clave)
            if valor is None:
                valor = _de_su_entidad(nodo, clave)
            if isinstance(valor, dict):
                valor = valor.get("value")
            numero = a_numero(valor)
            if numero is not None and float(numero).is_integer() and 1 <= numero <= 99:
                out[destino] = int(numero)
        # Los mismos conteos como `additionalProperty`: pares nombre/valor
        # que el sitio declara uno por uno. `baroninmobiliaria.com.ar` es una
        # app Next.js que muestra los conteos recien en el navegador; en el
        # HTML solo estan aca -«Ambientes 4», «Dormitorios 3»- y la casa
        # salia sin ninguno. Se exige el nombre EXACTO del atributo: «Baños
        # en suite» o «Ambientes de servicio» son otra cosa y no se leen.
        # Medido: 1 de 98 agencias generico publica asi (2026-09-24).
        extras = nodo.get("additionalProperty")
        for par in (extras if isinstance(extras, list) else []):
            if not isinstance(par, dict):
                continue
            nombre = "".join(
                c for c in unicodedata.normalize(
                    "NFKD", normalizar_texto_campos(str(par.get("name") or "")))
                if not unicodedata.combining(c)).strip().lower()
            destino = {"ambientes": "ambientes", "dormitorios": "dorm",
                       "banos": "banos"}.get(nombre)
            if not destino or out.get(destino) is not None:
                continue
            numero = a_numero(par.get("value"))
            if numero is not None and float(numero).is_integer() and 1 <= numero <= 99:
                out[destino] = int(numero)
        geo = nodo.get("geo") or _de_su_entidad(nodo, "geo")
        if isinstance(geo, dict):
            try:
                lat, lon = float(geo.get("latitude")), float(geo.get("longitude"))
                out["lat"], out["lon"] = lat, lon
            except (TypeError, ValueError, OverflowError):
                pass
        img = nodo.get("image")
        if img:
            urls = img if isinstance(img, list) else [img]
            out["imagenes"] = [u for u in urls if isinstance(u, str)]
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
        #
        # Y un numero con «+» -«+4 Ambientes», «Ambientes: 4+»- es un piso, no
        # una cantidad: el contador de la ficha topa ahi. Leerlo como 4 guardaba
        # 4 en una casa que la misma ficha describe como «de 5 ambientes». Se
        # saltea y, si la ficha dice la cantidad en otro lado, se toma esa.
        for rotulo in re.finditer(
                rf"(?:{etiqueta})\s*:\s*(\d{{1,2}})\b(?!\s*\+)", texto, re.I):
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
                rf"(?:{etiqueta})\s*(\d{{1,2}})\b(?!\s*\+)", texto, re.I)
        else:
            # Cero en los CMS suele ser placeholder, no una afirmacion de que
            # la propiedad carece del atributo. Si la descripcion publica una
            # cantidad positiva explicita, se conserva; los filtros del
            # catalogo ya fueron excluidos del auditor.
            #
            # El limite de palabra evita leer el "2" de "196 m2 Ambientes"
            # como si fuera la cantidad de ambientes.
            hallazgo = re.search(
                rf"(?<!\+)\b([1-9]\d?)\s*(?:{etiqueta})", texto, re.I)
        if not hallazgo:
            return None
        valor = int(hallazgo.group(1))
        return valor if 1 <= valor <= 99 else None

    @staticmethod
    def _ambientes_del_titulo(titulo: str | None) -> int | None:
        """Los ambientes que la ficha solo dice en su titulo.

        `bardi` rotula dormitorios y banos como pares y titula «Casa de 5
        Ambientes»: la tabla estructurada corta, con razon, la caida al texto
        plano, y el titulo quedaba sin leer. 156 fichas en 21 agencias.

        Solo un titulo de UNA unidad: en los 46 que discrepaban con el cuerpo
        el titulo nombraba varias («Casa de 3 amb. + depto. de 2 amb.») y el
        cuerpo sumaba.
        """
        if not titulo:
            return None
        hallazgos = re.findall(r"(?<![\d+])\b([1-9])\s*amb(?:ientes?\b|\.)",
                               titulo, re.I)
        if len(hallazgos) != 1 or re.search(
                r"\+|monoamb|\b(?:casas|deptos|departamentos|unidades|"
                r"locales|en\s+block)\b", titulo, re.I):
            return None
        return int(hallazgos[0])

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
        # Tambien <p>: la plantilla de `berrueta` publica el tipo como
        # <p class="highlights__text">Departamentos</p> junto a «Sin cochera».
        # Medido sobre 31 fichas de 31 agencias generico: cambia 1, y a mejor.
        for match in re.finditer(
                r"<(?:li|span|p)[^>]*>\s*([^<>]{3,24}?)\s*</(?:li|span|p)>",
                html or "", re.I):
            texto = match.group(1).strip()
            # Un elemento con una frase es texto de la ficha, no una etiqueta.
            # «Sin cochera» dice lo que la propiedad NO tiene.
            if len(texto.split()) > 2 or re.match(r"sin\b", texto, re.I):
                continue
            tipo = detectar_tipo(texto)
            if tipo:
                tipos.add(tipo)
        return tipos.pop() if len(tipos) == 1 else None

    @staticmethod
    def _cuenta_de_ficha(html: str, texto: str, etiqueta: str,
                         previo: Any) -> int | None:
        """Prioriza la pareja label/valor estructural de portales legacy."""
        # Lo que la ficha publica tipado en schema.org manda: es un contrato
        # publico, no una convencion visual. Hoy `previo` solo lo llena
        # `_de_json_ld`; ver alli lo medido.
        try:
            tipado = int(previo) if previo is not None else None
        except (TypeError, ValueError):
            tipado = None
        if tipado is not None and 1 <= tipado <= 99:
            return tipado
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
        # Los encabezados y `figure` tambien se usan como celda de rotulo y de
        # valor: alejoandresen.com.ar publica <h6>Baños</h6><figure>2</figure>,
        # que es la misma pareja estructural con otras etiquetas.
        celda = r"(?:span|div|dd|dt|td|th|li|p|b|strong|h[1-6]|figure)"
        rotulo = re.search(
            rf"<{celda}[^>]*>\s*(?:{etiqueta})\s*</{celda}>\s*"
            rf"<{celda}[^>]*>\s*(\d{{1,2}})\s*</{celda}>", marcado, re.I)
        if rotulo and 1 <= int(rotulo.group(1)) <= 99:
            return int(rotulo.group(1))
        # La misma pareja, con un ICONO delante del numero. El tema RealHomes
        # publica `<span>Dormitorios</span><div><svg>…</svg><span
        # class="figure">4</span></div>`, y la forma de arriba exige que la
        # celda del valor contenga SOLO el numero: `alas propiedades` perdia
        # asi los dormitorios en 120 de sus 206 fichas.
        #
        # No se afloja hacia el texto aplanado: ahi la ficha dice «ID de la
        # propiedad: A222 Dormitorios 4», y el numero antes de la palabra es
        # 222. Se exige la misma estructura -rotulo solo en su celda, valor en
        # la siguiente- y que el TEXTO VISIBLE de la celda del valor sea
        # unicamente el numero, con el icono y los envoltorios afuera.
        sin_iconos = re.sub(r"<svg\b.*?</svg>", " ", marcado, flags=re.I | re.S)
        for pareja in re.finditer(
                rf"<{celda}[^>]*>\s*(?:{etiqueta})\s*</{celda}>\s*"
                rf"<(div|span|dd|td|li|p)\b[^>]*>(.{{0,400}}?)</\1>",
                sin_iconos, re.I | re.S):
            visible = re.sub(r"<[^>]+>", " ", pareja.group(2)).strip()
            if re.fullmatch(r"\d{1,2}", visible) and 1 <= int(visible) <= 99:
                return int(visible)
        # El rotulo suelto adentro de la celda y el valor en un HIJO:
        # `<li>Ambientes <span>1</span></li>`. La forma de arriba exige que el
        # rotulo este solo en su propio elemento y no ve esta, que es de las
        # mas comunes.
        #
        # `benitezullo.com.ar` la usa, y el resultado no era solo perder
        # `ambientes`: al caer al texto plano, que busca el numero ANTES del
        # rotulo, `banos` leia el valor de AMBIENTES. Ahi valian los dos 1 y
        # parecia correcto; con "Ambientes 3 Banos 2" habria guardado banos=3.
        rotulo = re.search(
            rf"<{celda}[^>]*>\s*(?:{etiqueta})\s*"
            rf"<{celda}[^>]*>\s*(\d{{1,2}})\s*</{celda}>", marcado, re.I)
        if rotulo and 1 <= int(rotulo.group(1)) <= 99:
            return int(rotulo.group(1))
        if GenericoConnector._es_tabla_estructurada(marcado):
            # La ficha presenta sus atributos como pares rotulo/valor: lo
            # demostro al menos uno que si se leyo de la estructura. En ese
            # formato el numero va DESPUES del rotulo, asi que caer al texto
            # plano no deja el campo vacio: le pone el del campo anterior.
            #
            # alagnapropiedades.com.ar publica "Cocheras 2 Ambientes X" -con X
            # de plantilla sin completar- y de ahi salia ambientes=2, el 2 de
            # las cocheras. Peor: la validacion veia dormitorios 3 > ambientes
            # 2, un par imposible, y descartaba LOS DOS. Una extraccion mala
            # destruia un dato bueno.
            return None
        if GenericoConnector._rotulo_compuesto(marcado, etiqueta):
            # El rotulo funde dos atributos -"Dormitorios/Ambientes 2"- y no se
            # puede saber a cual corresponde el numero. Caer al texto plano es
            # peor que no contestar: ahi el patron narrativo agarra el numero
            # del campo VECINO. En esa ficha "Baños 2 Dormitorios/Ambientes 2"
            # daba ambientes=2 tomando el 2 de los baños, y coincidia de puro
            # azar; con baños 3 habria guardado 3.
            return None
        return GenericoConnector._cuenta(texto, etiqueta, previo)

    @staticmethod
    def _es_su_comienzo(parte: str, entero: str) -> bool:
        """Si `entero` empieza con `parte` y dice mas: la misma prosa, cortada."""
        def plano(texto: str) -> str:
            return re.sub(r"[\W_]+", " ", texto or "").strip().lower()
        corto, largo = plano(parte), plano(entero)
        return bool(corto) and len(largo) > len(corto) and largo.startswith(corto)

    @staticmethod
    def _descripcion_rotulada(html: str) -> str | None:
        """El bloque que sigue a un rotulo de descripcion.

        Dos cosas que la version anterior no contemplaba, ambas vistas en
        `almadimatteo.com.ar`, donde la descripcion no se leia en ninguna de
        sus veinticinco fichas:

        - el rotulo puede traer una coletilla: "Descripcion DE LA PROPIEDAD".
          Se acepta una corta, porque una larga ya no es un rotulo sino texto.
          Tambien un adjetivo de una lista cerrada: «Descripcion ampliada»
          (`cortespropiedades.com.ar`, que la sirve dentro de un textarea).
        - la fuente puede servir la vocal acentuada rota. Es el mismo problema
          de alfabetos distintos que ya aparecio entre la senal de fuente y su
          extraccion, y entre el guardian de tabla y su marcado.
        """
        bloque = r"(?:p|div|section|article|td)"
        # El rotulo puede venir envuelto en el enlace de un acordeon:
        # <h4><a href="#collapseTwo">Descripción</a></h4> (`alianza`).
        rotulo = r"(?:h[1-6]|div|span|strong|b|p|td)"
        # `.` cubre la vocal rota que sirven algunas fuentes legacy.
        acento = r"(?:[o\u00f3]|&oacute;|.)"
        m = re.search(
            rf"<{rotulo}[^>]*>\s*(?:<a\b[^>]*>\s*)?Descripci{acento}n"
            rf"(?:\s+(?:de|del)\s+(?:la\s+|el\s+)?[\w\u00c0-\u017f]{{3,20}}"
            rf"|\s+(?:ampliada|completa|general))?"
            # El rotulo puede venir repetido -la misma maqueta lo pone en el
            # encabezado y en la celda-, y entre el rotulo y el texto puede
            # haber envoltorios vacios.
            rf"\s*:?\s*(?:</a>\s*)?</{rotulo}>"
            rf"(?:\s*<[^>]*>\s*|\s*Descripci{acento}n[^<]{{0,25}}\s*)*?"
            rf"<{bloque}[^>]*>(.*?)</{bloque}>",
            html or "", re.I | re.S)
        if m:
            visible = limpiar(_texto(m.group(1)))
            if visible and len(visible) >= 20:
                return visible

        # El primer bloque puede ser un envoltorio vacio. `almadimatteo.com.ar`
        # pone el rotulo dos veces -una por variante responsive- y despues
        # anida divs con una tabla vacia antes del texto; buscar "el bloque
        # siguiente" encontraba el vacio y devolvia nada.
        #
        # Lo que una persona lee es el texto que sigue al rotulo hasta el
        # proximo encabezado. Eso es lo que se toma, acotado para no arrastrar
        # la pagina entera.
        etiqueta = re.search(
            rf"<{rotulo}[^>]*>\s*(?:<a\b[^>]*>\s*)?Descripci{acento}n"
            rf"(?:\s+(?:de|del)\s+(?:la\s+|el\s+)?[\w\u00c0-\u017f]{{3,20}}"
            rf"|\s+(?:ampliada|completa|general))?"
            rf"\s*:?\s*(?:</a>\s*)?</{rotulo}>", html or "", re.I | re.S)
        if not etiqueta:
            return None
        # Sin scripts ANTES de cortar: `resto[:6000]` partia un `<script>` que
        # empezaba adentro de la ventana y cerraba afuera, y sin su cierre el
        # codigo pasaba como texto. `cbdestino.com.ar` guardo asi 4.000
        # caracteres de JavaScript -con un token CSRF distinto en cada
        # corrida- como descripcion de 16 fichas.
        resto = sin_bloques_no_textuales((html or "")[etiqueta.end():])
        # La misma maqueta repite el rotulo, una vez por variante responsive.
        # Cortar en "el proximo encabezado" caia sobre ese duplicado y dejaba
        # el texto entero afuera.
        repeticion = re.compile(
            rf"\A\s*(?:<[^>]*>\s*)*?<{rotulo}[^>]*>\s*Descripci{acento}n"
            rf"[^<]{{0,25}}</{rotulo}>", re.I | re.S)
        while True:
            otro = repeticion.match(resto)
            if not otro:
                break
            resto = resto[otro.end():]
        corte = re.search(r"<h[1-6]\b|<footer\b", resto, re.I)
        if corte:
            resto = resto[:corte.start()]
        visible = limpiar(_texto(resto[:6000]))
        return visible if visible and len(visible) >= 20 else None

    @staticmethod
    def _catalogos_enlazados(html: str, base: str) -> list[str]:
        """Los catalogos que la portada enlaza, en su propio orden.

        Probar una ruta fija -/propiedades- deja afuera a los sitios que
        publican su listado en otro lado. Seguir la navegacion del sitio no es
        adivinar: es leer la ruta que el sitio declara.

        Se acotan a unos pocos para no recorrer el menu entero de una fuente
        ajena, y se ignora la raiz, que ya se bajo.
        """
        vistos: list[str] = []
        patron = re.compile(
            r"(?:listado|propiedades|inmuebles|emprendimientos|catalogo|"
            r"resultados|ventas|alquileres|buscar)", re.I)
        for coincidencia in re.finditer(r'href="([^"]+)"', html or ""):
            destino = urllib.parse.urljoin(base, unescape(coincidencia.group(1)))
            if not destino.startswith(base):
                continue
            ruta = urllib.parse.urlparse(destino).path.rstrip("/")
            if not ruta or not patron.search(ruta):
                continue
            limpio = destino.split("#")[0]
            if limpio not in vistos:
                vistos.append(limpio)
            if len(vistos) >= 4:
                break
        return vistos

    @staticmethod
    def _es_tabla_estructurada(marcado: str) -> bool:
        """Si la ficha presenta sus atributos como pares rotulo/valor.

        Lo decide la estructura, no un conteo sobre el texto: alcanza con que
        UN atributo conocido aparezca como celda de rotulo seguida de celda con
        su numero. Intentar deducirlo del texto aplanado ya fallo, porque las
        paginas traen tabla Y descripcion y la prosa gana por mayoria.
        """
        # Se normaliza igual que en `_cuenta_de_ficha`. Leer el marcado crudo
        # dejaba la regla ciega a las fichas cuya unica fila tabulada es
        # `Baños`: el portal la sirve con la enye rota y la etiqueta no
        # coincidia, asi que una tabla real pasaba por prosa.
        marcado = normalizar_texto_campos(unescape(marcado or ""))
        celda = r"(?:span|div|dd|dt|td|th|li|p|b|strong|h[1-6]|figure)"
        return bool(re.search(
            rf"<{celda}[^>]*>\s*(?:{ETIQUETAS_ATRIBUTO_COMPUESTO})\s*"
            rf"</{celda}>\s*<{celda}[^>]*>\s*\d{{1,2}}\s*</{celda}>",
            marcado, re.I))

    @staticmethod
    def _rotulo_compuesto(marcado: str, etiqueta: str) -> bool:
        """Si la etiqueta vive en una celda junto a OTRO atributo conocido."""
        celda = r"(?:span|div|dd|dt|td|th|li|p|b|strong|h[1-6]|figure)"
        for bloque in re.finditer(
                rf"<{celda}[^>]*>([^<>]{{1,60}})</{celda}>", marcado or "",
                re.I):
            contenido = bloque.group(1)
            if not re.search(etiqueta, contenido, re.I):
                continue
            otros = {m.group(0).lower() for m in re.finditer(
                ETIQUETAS_ATRIBUTO_COMPUESTO, contenido, re.I)}
            if len(otros) > 1:
                return True
        return False

    @staticmethod
    def _sup(texto: str, etiqueta: str) -> float | None:
        # `Terreno 127 m x 50 m` es una MEDIDA, no un area: leer el primer
        # numero guarda el ANCHO del lote como si fuera su superficie.
        # `arbinipropiedades.com.ar` lo publica asi en la prosa, y ademas de
        # ensuciar el dato hacia que la senal de fuente dijera que la ficha
        # publica superficie_total cuando el extractor -con razon- se negaba.
        # El triage leyo esa discrepancia como defecto de radio FAMILIA y
        # paro las dos colas.
        #
        # La guarda es sobre la DIMENSION y no sobre cualquier letra: asi no
        # se pierde "300 metros cuadrados", que es legitimo.
        m = re.search(rf"(?:{etiqueta})[^\d]{{0,18}}([\d.,]{{2,9}})\s*m"
                      rf"(?!\s*[x×]\s*\d)", texto, re.I) or \
            re.search(rf"([\d.,]{{2,9}})\s*m[²2]\s*(?:{etiqueta})", texto, re.I)
        if not m:
            return None
        v = a_numero(m.group(1))
        return v if v and 5 <= v <= 100_000 else None
