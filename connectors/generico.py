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

import hashlib
import json
import dataclasses
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
                   detectar_operacion, detectar_tipo, ficha_sin_contenido,
                   geografia, identidad_de_imagen, imagenes_de_fichas_vecinas,
                   limpiar)

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
    # «Cuartos de baño»: el tema RealHomes en castellano (`inversiones
    # inmobiliarias`, Puerto Madryn: 3 de 6 fichas sin baños).
    "banos": r"\b(?:(?:cuartos?\s+de\s+)?ba[nñ]os?|toilettes?)\b",
    # «1 amb. | 1 baños | 0 cochera» (`bras neves`, WordPress: 10 de 15 fichas
    # sin ambientes). Es la misma forma que el auditor ya reconoce como senal
    # de la fuente (`agency_certifier`, «amb.» con punto): sin el punto, «amb»
    # tambien abrevia «ambiente» suelto en prosa y no se acepta.
    "ambientes": r"\b(?:ambientes?\b|amb\.)",
}

# Conteos escritos con letras en la prosa: «casa de cuatro dormitorios y un
# baño» (`pozzobon`, `ente`). Hasta diez: mas alla nadie lo escribe asi.
NUMEROS_EN_LETRAS = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3,
                     "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
                     "ocho": 8, "nueve": 9, "diez": 10}

# Rutas donde un frontend propio suele exponer el catalogo Tokko.
RUTAS_TOKKO_PROXY = ("/api/tokko/properties", "/api/properties",
                     "/api/tokko/property")

# Un frontend Next.js que hidrata su catalogo desde un Strapi PROPIO (`diego
# martin`: diegogmartin.onrender.com/api/propiedades, sin clave). La url la
# publica el JavaScript del propio sitio; se reconoce por la forma de Strapi.
RE_API_STRAPI = re.compile(
    r"[\"'`](https://[a-z0-9.\-]+/api/(propiedades|inmuebles|properties))\?", re.I)
# Strapi v3 propio en el subdominio `api.` (sin el prefijo /api de v4):
# `paladino` llama a https://api.paladinopropiedades.com.ar/inmuebles desde su
# JavaScript y arma cada ficha /inmueble/<slug> en el navegador.
RE_API_STRAPI_V3 = re.compile(
    r"[\"'`](https://api\.[a-z0-9.\-]+)/(inmuebles|propiedades|properties)[\"'`?]", re.I)
# Paginas chicas: con 25 por pagina el Strapi de `diego martin` (Render) corta
# la respuesta de la segunda; con 10, las seis salen enteras.
PAGINA_STRAPI = 10
TOPE_PAGINAS_STRAPI = 80

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

# Rotulos de la superficie total. «Sup. Lote 1340 m²» (`conti`, 74 fichas que
# guardaban el lote de una tarjeta vecina); «Lote» a secas no: «Lote 12
# Manzana 3» es un numero de lote.
ETIQUETA_SUP_TOTAL = r"total|terreno|sup(?:erficie)?\.?\s*(?:del\s+)?lote"
# Y de la cubierta. «13.00m² semicubiertos» no es la cubierta: sin la guarda,
# `matias sosa` guardaba como cubierta el numero que seguia a «semicubiertos».
ETIQUETA_SUP_CUBIERTA = r"(?<!semi)cubiert|construid"
# Rotulos de superficie que pueden ir DESPUES de su numero («94m2 cub»): raiz
# que se busca y una palabra de muestra para saber si es el propio rotulo.
SUPERFICIES_VECINAS = (("cub", "cubierta"), ("semicub", "semicubierta"),
                       ("constru", "construida"), ("descub", "descubierta"),
                       ("tot", "total"), ("terreno", "terreno"), ("lote", "lote"))

# Parametro de paginacion que el listado DECLARA en sus propios enlaces.
PARAMS_DE_PAGINA = ("start", "pagina", "page", "offset", "pg", "p")
TOPE_PAGINAS_DECLARADAS = 200

# Terravirtual (`blangiforti`, `g calvo`): la ficha es /ficha/<md5>. Sus
# catalogos enlazan /propiedades/ficha/<md5>, que el sitio responde con el
# LISTADO (23 tarjetas, sin bloque de ficha), y la portada //ficha/<md5>.
# CRM TIV Tecnogestion: el buscador declara «N inmuebles encontrados» y sirve
# las fichas de a 10; la portada muestra un subconjunto que ROTA en cada carga.
# El resto lo pide el propio sitio con `POST /Buscar/CargaMasInmueblesParam`
# (scroll infinito) y los filtros vacios del formulario. Medido el 2026-10-02:
# `campal` 147 declaradas y 147 enumeradas en 16 pedidos; antes 37-38 que
# cambiaban entre corridas. Y 16 agencias TIV estaban CERTIFIED_COMPLETE con
# la portada sola (`bts` 26 de 893, `coseglia` 21 de 340): falso completo.
RE_TIV = re.compile(r"cdn\.tecnogestion\.com\.ar|CRM Inmobiliario TIV", re.I)
RE_TIV_TOTAL = re.compile(r"(\d[\d.]{0,7})\s+inmuebles?\s+encontrados?", re.I)
RE_TIV_FICHA = re.compile(r"""href=["'](/inmueble/[^"'#?\s]+-lp\d+)["']""", re.I)
TIV_POR_PAGINA = 10
TIV_FORMULARIO = {
    "Orden": "8", "SucursalID": "", "Operacion": "", "Producto": "", "Ubicacion": "",
    "PrecioDesde": "", "PrecioHasta": "", "IncluirEmprendimientos": "1", "Dormitorios": "",
    "Antiguedad": "", "DescripcionBusqueda": "", "ConCochera": "0", "AptoProfesional": "0",
    "ConBalcon": "0", "ConBalconTerraza": "0", "ConDependencia": "0", "Amoblado": "0",
    "ConVigilancia": "0", "Mapa": "False", "Geolocalizacion": "", "AptoCreditoHipotecario": "false",
}

RE_FICHA_TERRAVIRTUAL = re.compile(r"^/+(?:propiedades/)?ficha/([0-9a-f]{32})/?$", re.I)

# La pagina entera dice que la ficha ya no existe.
RE_FICHA_INEXISTENTE = re.compile(
    r"(?:la\s+)?(?:propiedad|inmueble|aviso|ficha)\s+(?:inexistente|no\s+existe"
    r"|no\s+encontrad[ao]|no\s+disponible)\.?", re.I)

# Ficha Xintel/Amaira embebida: la pagina de la agencia es un marco y la
# ficha -con los parametros del detalle- vive en el iframe del proveedor.
RE_IFRAME_AMAIRA = re.compile(
    r"""<iframe[^>]+src=["'](https://ficha\.amaira\.com\.ar/[^"']+)["']""", re.I)

# Y la ficha Amaira pasada como parametro de una pagina propia:
# /ficha?url=https%3A%2F%2Fficha.amaira.com.ar%2Fnue%2Fficha.php%3Fficha%3DRAL102
# (`lar`, 111 fichas). La pagina propia la carga con JavaScript; la ficha real
# es la del proveedor que la agencia misma declara.
RE_FICHA_AMAIRA_EN_QUERY = re.compile(
    r"[?&]url=(https?(?::|%3A)(?://|%2F%2F)ficha\.amaira\.com\.ar[^&#]+)", re.I)


PROVINCIAS_AR = {
    "buenos aires", "catamarca", "chaco", "chubut", "cordoba", "corrientes",
    "entre rios", "formosa", "jujuy", "la pampa", "la rioja", "mendoza",
    "misiones", "neuquen", "rio negro", "salta", "san juan", "san luis",
    "santa cruz", "santa fe", "santiago del estero", "tierra del fuego",
    "tucuman", "caba", "capital federal", "ciudad autonoma de buenos aires",
}


def _es_provincia(texto: str) -> bool:
    plano = "".join(c for c in unicodedata.normalize("NFKD", (texto or "").lower())
                    if not unicodedata.combining(c))
    plano = re.sub(r"^(?:provincia\s+de\s+|pcia\.?\s+(?:de\s+)?)", "", plano.strip())
    return plano in PROVINCIAS_AR


def ficha_amaira_en_query(url: str) -> str | None:
    """La url de la ficha Amaira que la pagina propia recibe por parametro."""
    m = RE_FICHA_AMAIRA_EN_QUERY.search(url or "")
    return urllib.parse.unquote(m.group(1)) if m else None


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
    # Tambien con extension: /propiedad/275-corrientes-sn.html (`ramirez`).
    r"(?:[^/?#]*?(?:\d{3,}|[a-z0-9]+(?:-[a-z0-9]+){2,}))(?:\.html?|\.php)?/?$"
    # Y el id numerico ADELANTE con un slug corto o cortado: /propiedad/263-
    # chubut.html, /propiedad/273-l-molinas-2192-.html (`ramirez`, 10 fichas
    # reales con 2 a 17 fotos descartadas por forma). Id + extension es la
    # forma de una ficha servida por un CMS propio, no la de una seccion.
    r"|/(?:propiedad(?:es)?|inmueble[s]?|ficha[s]?)/\d+-[a-z0-9-]+\.(?:html?|php)$", re.I)

# La ficha servida por un script con el id en la query:
# /venta/item.asp?t=Propiedad-en-El-Bosque&id=192 (`innoa`, ASP). Sin esto, las
# 22 fichas sin precio de la agencia -de 4 a 17 fotos, operacion y tipo en el
# titulo- se descartaban por forma. Seccion de operacion o de propiedad + script
# + `id` numerico: no es la forma de un listado ni de una pagina institucional.
RE_URL_CON_TOKEN = re.compile(
    r"(?:<img\b[^<>]*?src=[\"']?\s*)?https?://\S*?eyJ[A-Za-z0-9_\-+/=%]{40,}[^\s\"'<>]*"
    r"(?:[\"']?\s*/?>)?")

# Una seccion de DETALLE con id numerico y slug: /comprar_detalle_vacis/216/
# 9_de_julio_306 (`diego vacis`). La palabra «detalle» + id es la forma de una
# ficha; el listado (/comprar_vacis) no la tiene.
RE_FICHA_DETALLE = re.compile(r"/[a-z0-9_-]*detalle[a-z0-9_-]*/\d{1,8}/[^/?#]+/?$", re.I)

RE_GIF = re.compile(r"\.gif(?:[?#]|$)", re.I)

RE_FICHA_CON_ID = re.compile(
    r"/(?:venta|alquiler|propiedad(?:es)?|inmueble[s]?|ficha[s]?)/[a-z_-]*\.(?:asp|aspx|php)"
    r"\?(?:[^#]*&)?id=\d+(?:&|#|$)", re.I)

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

# La plantilla «<tipo>-<operacion>-<lugar>_<id>_propiedad-inmobiliaria.html»
# (`bartolini`: 295 fichas en la raiz). Sin forma global entraban por forma, y
# el guardian exige tres fotos a una candidata por forma: 30 fichas reales con
# precio, operacion y 0 a 2 fotos se perdian como detalles fallidos y paraban
# la agencia. El id entre guiones bajos + el sufijo fijo es la forma de una
# ficha; las categorias del mismo sitio (/departamento-en-venta.html) no lo
# tienen.
RE_FICHA_ID_PROPIEDAD_INMOBILIARIA = re.compile(
    r"^/[^/?#]+_\d{4,}_propiedad-inmobiliaria\.html?$", re.I)

# Rutas de orden del LISTADO que por tener varios guiones parecen slugs de
# ficha. En BuscadorProp eran dos propiedades fantasma por inmobiliaria.
#
# Y `/cdn-cgi/`, la ruta reservada de Cloudflare: nunca es contenido del sitio.
# Su «AI Labyrinth» siembra enlaces a articulos inventados para los bots
# (`fernandez marull` 59 de 59, `crestale` 59 de 131, el 25-09).
RE_NO_FICHA = re.compile(
    # Categorias en la raiz con la operacion en PLURAL: /ventas-casas,
    # /alquileres-departamentos-2-dormitorios (`arquitectura inmobiliaria`,
    # tienda DonWeb SitioSimple): se guardaban 17 categorias como propiedades
    # con el precio de su primer producto. Las fichas usan el singular
    # (/venta-dr-riva-1000) o el tipo (/casa-3-dormitorios-…).
    r"^/(?:alquileres|ventas)(?:-[a-z0-9-]+)?/?$|"
    # Los listados por operacion de Kiteprop: /site/properties/sale y
    # /site/properties/rental (`linkasa`: se guardaban como dos propiedades).
    r"/properties/(?:sale|rental|rent|temporary)/?$|"
    # El indice de emprendimientos, sin slug: /emprendimientos.php (`jorge
    # martinez`, `irujo`). Las fichas /emprendimientos/<slug> siguen entrando.
    r"^/emprendimientos?(?:\.(?:php|html?|aspx?))?/?$|"
    # Tambien con la operacion delante: /propiedades/venta_mas-nuevas
    # (`fandino`, 10 ordenes del listado enumerados como fichas el 26-09).
    r"/propiedades/(?:(?:venta|alquiler)[_-])?(?:destacadas|mas-nuevas|mas-viejas|"
    r"precio-(?:mayor|menor)-a-(?:mayor|menor))/?$|^/cdn-cgi/"
    # Taxonomias de WordPress: /estado-propiedad/venta (`garbero`) lista
    # avisos, no es uno.
    r"|^/(?:(?:estado|tipo|ciudad|zona|barrio|caracteristica|categoria|localidad)"
    r"-(?:de-)?propiedad(?:es)?|property-(?:status|type|city|area|feature|label|state))/"
    # Filtros del catalogo como ruta: /propiedades-venta/tipo/casa-1/dormitorios/
    # 2-dormitorios-9/ (`cuini`, 16 del menu enumeradas como fichas).
    # Y el catalogo mismo, con o sin ?tipo=2 (`cuini`, 26-09: 4 de 41).
    r"|^/propiedades-(?:venta|alquiler)/(?:(?:tipo|dormitorios|ciudad|zona|barrio)/|$)"
    # Un resultado de busqueda no es una ficha: /buscar/alquileres
    # (`global inmobiliaria`).
    # Y /resultado/1/1/10/campo-en-venta/ (`lizio albarello`, 9 de 25).
    r"|^/(?:buscar|busqueda|resultados?)(?:/|$)"
    # Y la pagina N del listado: /propiedades/pagina-3/ es un listado.
    r"|/(?:pagina|page)[-/]\d+/?$",
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
# `long` tambien: WPResidence escribe `data-cur_lat="-34.58" data-cur_long=
# "-58.49"` (`berardi`, 16 fichas sin coordenada en el Regression Gate 28-09).
# `lang` tambien: el tema inspiry-real-places escribe `{"lat":"-32.94",
# "lang":"-60.64"}` (`gonzalez theyler`, 41 de 44 fichas sin coordenada). El
# valor tiene que ser una coordenada: un `"lang":"es"` no coincide.
# Comillas simples tambien: el plugin Estatik publica
# `data-latitude='-38.8411258' data-longitude='-68.1291336'` (`portanko`, 35 de
# 42 fichas sin coordenada, 29-09).
RE_COORD = re.compile(r"""["']?(?:latitude|lat)["']?\s*[:=]\s*["']?(-[23456]\d\.\d{3,})["']?"""
                      r""".{0,80}?["']?(?:longitude|long|lang|lng|lon)["']?\s*[:=]\s*["']?(-[567]\d\.\d{3,})["']?""",
                      re.S | re.I)

# Y en castellano, SOLO en las dos formas verificadas: el atributo del mapa de
# la ficha `<div id="propertyMap" data-latitud="-38.26" data-longitud="-57.85">`
# (`ballarre` 247 y `zamorano` 143 fichas sin coordenada, 28-09) y la variable
# `const latitud = -31.65; const longitud = -60.71;` (`bottai`, que ademas
# tiene `[-32.9468, -60.6393]` «Rosario como fallback» y de ahi salia la
# coordenada). Una clave `latitud:` suelta en un objeto puede ser la de la
# CIUDAD (`mercado-unico`: `ciudad:{nombre:"Arroyo Leyes",latitud:-31.585}`).
RE_COORD_ES = re.compile(
    r"""(?:data-latitud\s*=\s*["']|\b(?:const|let|var)\s+latitud\s*=\s*)(-[23456]\d\.\d{3,})"""
    r""".{0,80}?(?:data-longitud\s*=\s*["']|\b(?:const|let|var)\s+longitud\s*=\s*)(-[567]\d\.\d{3,})""",
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
# Parametros con los que un listado enlaza una ficha que ya tiene su id: dicen
# desde que categoria se llego, no cual es la ficha.
PARAMS_DE_CONTEXTO = frozenset({
    "tipo", "operacion", "operacionabuscar", "tipoope", "inmueble",
    "pagina", "page", "pagenum", "orden", "order"})


def _url_y_parametros(url: str) -> tuple[str, tuple]:
    p = urllib.parse.urlsplit(url.split("#")[0])
    return (f"{p.netloc.lower()}{p.path.rstrip('/')}",
            tuple(sorted(urllib.parse.parse_qsl(p.query, keep_blank_values=True))))


# La URL de una CATEGORIA, en las dos formas inequivocas medidas: el segmento
# «{tipos}_{operacion}_{localidad}» / «{operacion}_destacadas» (la convencion de
# Inmobiliatica: `calzetta` /propiedades/lotes_venta_lomas-de-zamora, `civeira`
# /propiedades/venta_destacadas) y la ruta exacta «/{operacion}/{tipos}» (`pagano`
# /venta/casas). Se enumeraban como fichas: 9 guardadas en 4 agencias, todas
# tituladas «Propiedades» o con el nombre de la agencia y el menu como
# descripcion, y 3 de `pagano` contadas como fichas fallidas. Sin cifras en la
# ruta ni query: una ficha lleva su id. Radio sobre 55.861 fichas guardadas:
# 9 aciertos, 0 falsos positivos.
_TIPOS_PLURALES = (r"casas|departamentos|deptos|duplex|oficinas|locales|terrenos|lotes|"
                   r"galpones|cocheras|campos|quintas|chacras|fincas|salones|depositos|"
                   r"propiedades|inmuebles|emprendimientos|casaquintas|chalets|ph")
_OPERACIONES = (r"venta|ventas|alquiler|alquileres|alquiler-temporal|"
                r"alquiler-temporario|temporario")
RE_URL_DE_CATEGORIA = re.compile(
    rf"^/(?:.*/)?(?:(?:{_TIPOS_PLURALES})_(?:{_OPERACIONES})(?:_[a-z0-9\-]+)?|"
    rf"(?:{_OPERACIONES})_destacadas|(?:{_OPERACIONES})/(?:{_TIPOS_PLURALES}))/?$", re.I)


# Y los archivos de taxonomia de WordPress: `peirano` guardo 16 «Archivos de la
# categoria 3 amb. con dep.» / «Archivo de la etiqueta: …» como propiedades. Las
# bases del nucleo (`/category/`, `/tag/`, `/author/`) son siempre archivos, con o
# sin cifras. Radio sobre 55.861 fichas guardadas: esas 16, ninguna otra.
RE_ARCHIVO_WORDPRESS = re.compile(r"/(?:category|tag|author)/", re.I)


def es_url_de_categoria(url: str) -> bool:
    partes = urllib.parse.urlparse(url or "")
    ruta = urllib.parse.unquote(partes.path).lower()
    if RE_ARCHIVO_WORDPRESS.search(ruta):
        return True
    return (not partes.query and not re.search(r"\d", ruta)
            and bool(RE_URL_DE_CATEGORIA.search(ruta)))


def _clave_sin_slug(url: str) -> tuple | None:
    """Identidad de una ficha cuya query trae UN id numerico y UN texto-slug.

    `(host, ruta, id numerico, resto de la query)` si la query tiene exactamente
    un parametro numerico y exactamente un parametro de texto con guiones; None
    en cualquier otro caso (la regla no toca nada que no tenga esa forma).
    """
    partes = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qsl(partes.query, keep_blank_values=True)
    numericos = [(k, v) for k, v in query if v.isdigit()]
    slugs = [(k, v) for k, v in query
             if not v.isdigit() and "-" in v and re.fullmatch(r"(?=.*[A-Za-z])[\w\-%.]+", v)]
    if len(numericos) != 1 or len(slugs) != 1:
        return None
    resto = tuple(sorted((k, v) for k, v in query if (k, v) not in slugs))
    return (partes.netloc.lower().removeprefix("www."), partes.path.lower(), resto)


def _sin_contexto_del_listado(url: str) -> tuple[str, tuple] | None:
    """La misma ficha sin los parametros de contexto, o None si no tiene."""
    ruta, params = _url_y_parametros(url)
    propios = tuple(kv for kv in params if kv[0].lower() not in PARAMS_DE_CONTEXTO)
    if not propios or len(propios) == len(params):
        return None
    return ruta, propios


def _id_de_ficha_en_la_query(url: str) -> bool:
    """`product.php?id=343`: un id numerico en la query de un archivo que no se
    llama como un listado."""
    partes = urllib.parse.urlsplit(url)
    archivo = partes.path.rsplit("/", 1)[-1].lower()
    if re.search(r"propiedad|inmueble|listado|categor|busca|resultado|index|todos", archivo):
        return False
    return bool(re.search(r"(?:^|&)(?:id|codigo|cod|ficha|recordid)=\d+(?:&|$)",
                          partes.query, re.I))


RE_UBICACION_EN_TITULO = re.compile(
    r"\ben\s+(?:venta|alquiler(?:\s+temporario|\s+por\s+temporada|\s+para\s+estudiantes)?)"
    r"\s+en\s+([^,|:]{2,40}),\s*([^,|:\-–]{3,40}?)\s*(?:[-–|]|$)", re.I)


def _ubicacion_del_titulo(titulo: Any) -> tuple[str | None, str | None]:
    """`(barrio, ciudad)` de «… en Venta en Barrio, Ciudad - Precio», o `(None, None)`.

    El sufijo de la agencia («… :: Inmobiliaria Ballarre», «… | Lazzaro») no es
    parte de la ubicacion. Un «barrio» con numeros es una direccion, no se toma.
    """
    texto = re.sub(r"\s*(?:::|\|).*$", "", str(titulo or ""))
    m = RE_UBICACION_EN_TITULO.search(texto)
    if not m:
        return None, None
    barrio, ciudad = m.group(1).strip(), m.group(2).strip()
    # Solo una ciudad que el catalogo resuelve como LOCALIDAD: «entre San
    # Lorenzo y Avellaneda» (`insabella`) o «Punilla» (un departamento,
    # `castro y compania`) no se toman, ni tampoco su barrio.
    if re.search(r"\d", ciudad) or re.match(r"(?i)entre\b", ciudad):
        return None, None
    try:
        if not geografia().resolver_localidad(ciudad).resuelta:
            return None, None
    except (OSError, ValueError):
        return None, None
    # «Las Malvinas - Las Malvinas»: el ultimo tramo es el barrio.
    barrio = barrio.split(" - ")[-1].strip()
    return (None if re.search(r"\d", barrio) or barrio.casefold() == ciudad.casefold()
            else barrio), ciudad


# Credencial PUBLICA de cliente de Xintel (politica del usuario, 2026-09-28).
# Solo en contexto Xintel (su host en el mismo documento) y con la forma que
# usa el frontend: el par `inm` + `apiK` de la llamada, o el bloque de
# configuracion `xintel: { empresa, apiKey }`. Una clave rotulada como secreta,
# privada o token no es configuracion publica de cliente y no se usa.
RE_HOST_XINTEL = re.compile(r"xintelapi\.com\.ar|xintel\.com\.ar/api", re.I)
RE_XINTEL_INM = re.compile(r"""["']?\b(?:inm|empresa|codemp)["']?\s*:\s*["']([A-Za-z0-9]{2,8})["']""")
RE_XINTEL_CLAVE = re.compile(r"""["']?\b(apiK|apiKey)["']?\s*:\s*["']([A-Za-z0-9]{15,40})["']""")
RE_XINTEL_BLOQUE = re.compile(r"""\bxintel\s*:\s*\{(.{0,2000}?)\}""", re.S | re.I)
RE_ROTULO_SECRETO = re.compile(r"secret|privad|private|token|bearer|password|contrase", re.I)


def credencial_xintel_en(texto: str) -> tuple[str, str] | None:
    """`(inm, apiK)` si el documento publica la credencial de cliente de Xintel."""
    if not texto or not RE_HOST_XINTEL.search(texto):
        return None
    ventanas = [m.group(1) for m in RE_XINTEL_BLOQUE.finditer(texto)]
    # La llamada del frontend: `url: 'https://xintel.com.ar/api/', data: {inm, apiK}`.
    for host in RE_HOST_XINTEL.finditer(texto):
        ventanas.append(texto[max(0, host.start() - 600): host.end() + 600])
    for ventana in ventanas:
        inm, clave = RE_XINTEL_INM.search(ventana), RE_XINTEL_CLAVE.search(ventana)
        if not (inm and clave):
            continue
        alrededor = ventana[max(0, clave.start() - 60): clave.end() + 20]
        if RE_ROTULO_SECRETO.search(alrededor):
            return None
        return inm.group(1), clave.group(2)
    return None


def _procedencia_credencial(fuente: Fuente, url: str, clave: str) -> dict[str, str]:
    """Rastro de la credencial SIN su valor: tipo, proveedor, donde y de quien."""
    return {"tipo": "PUBLIC_CLIENT_CREDENTIAL", "provider": "Xintel", "source_url": url,
            "agency": fuente.canonical_agency_id,
            "clave_sha256_12": hashlib.sha256(clave.encode("utf-8")).hexdigest()[:12]}


# Elementor + JetEngine: desde el encabezado «Descripcion», el primer campo
# dinamico cuyo contenido es prosa (sin cruzar su `</div>`). Ver `esnal`.
RE_DESCRIPCION_JETENGINE = re.compile(
    r"<h[1-6][^>]*>\s*Descripci(?:[oó]|&oacute;)n\s*\.?\s*</h[1-6]>"
    r".{0,10000}?"
    r"class=\"jet-listing-dynamic-field__content\"[^>]*>"
    r"((?:(?!</div>).){120,4000})</div>",
    re.S | re.I)

# `background-image: url(…)` dentro de un atributo `style` del elemento -no de
# una hoja <style>, donde viven los banners del sitio-, con o sin comillas.
RE_FONDO_CSS = re.compile(
    r"\sstyle\s*=\s*(?:\"[^\"]{0,300}?|'[^']{0,300}?)background(?:-image)?\s*:\s*"
    r"url\(\s*(&quot;|')?([^\"'()\s&]{4,400}?)(?:&quot;|')?\s*\)", re.I)

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


def _moneda_del_signo(signo: str) -> str | None:
    """La moneda de un signo de precio, con `U$`/`U$$` como dolares.

    `detectar_moneda` busca claves por inclusion y en «U$» encuentra el `$`:
    pesos. Se resuelve aca y no en `base` para no cambiar la regla de todos
    los conectores de arrastre.
    """
    if re.fullmatch(r"u\$\$?", (signo or "").strip(), re.I):
        return "USD"
    return detectar_moneda(signo)


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


def con_cierres_normales(html: str) -> str:
    """`</h1 >` es `</h1>`: HTML admite espacio antes del `>` de cierre.

    La plantilla de Coding & Company (`matias sosa`) cierra TODO asi -`</h1 >`,
    `</h6 >`, `</span >`- y cada regla escrita contra `</h1>` quedaba ciega:
    el titulo salia del `<title>` del sitio, la descripcion del meta («A custom
    site made by Coding & Company») y el corte en «Otras propiedades» no
    cortaba, asi que 14 fotos de tarjetas vecinas -elegidas al azar en cada
    carga- entraban a la galeria y la agencia no era idempotente.
    """
    return re.sub(r"</([a-zA-Z][a-zA-Z0-9]*)\s+>", r"</\1>", html or "")


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
        inicio = max(0, m.start() - CERCA_DEL_PRECIO)
        ventana = texto[inicio:m.end() + CERCA_DEL_PRECIO]
        precio_en_ventana = (m.start() - inicio, m.end() - inicio)

        def distancia(regex: "re.Pattern") -> int | None:
            lejos = [min(abs(x.start() - precio_en_ventana[1]),
                         abs(precio_en_ventana[0] - x.end()))
                     for x in regex.finditer(ventana)]
            return min(lejos) if lejos else None

        alquiler, venta = distancia(RE_ALQUILER_CERCA), distancia(RE_VENTA_CERCA)
        # Las dos en la ventana: gana la PEGADA al precio si la otra esta
        # lejos. `lurati` publica «USD 22.000 - EN VENTA» con el menu «Venta
        # Alquiler» 57 caracteres antes: el menu no es el aviso. Si las dos
        # estan cerca, la pagina no dice cual es y no se elige.
        if alquiler is not None and venta is not None:
            if venta <= 15 and alquiler >= 40:
                alquiler = None
            elif alquiler <= 15 and venta >= 40:
                venta = None
        if alquiler is not None:
            vistas.add("alquiler_temporario"
                       if RE_TEMPORARIO_CERCA.search(ventana) else "alquiler")
        if venta is not None:
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
    html = con_cierres_normales(sin_marcado_comentado(html))
    # RealHomes (`fernando villalba`): sus similares van en
    # `rh_property__similar_properties`, elegidas al azar en cada carga; sus
    # «Habitaciones» daban 4 dormitorios a una parcela de 1,3 ha.
    # `id="bottom"` corta solo en un elemento de la pagina, no en una figura
    # de un SVG: el icono de menu de `cometto` es <path id="bottom"> en la
    # cabecera, y la ficha entera -precio, superficie, fotos- quedaba afuera
    # (15 de 15 descartadas por forma, 0 propiedades).
    return re.split(
        r"<(?!(?:path|g|line|rect|circle|ellipse|polygon|polyline|use|symbol|svg)\b)"
        r"[a-z][a-z0-9]*\b[^>]*\bid=[\"'](?:relacionadas|bottom)[\"']|<footer\b|"
        r"class=[\"'][^\"']*rh_property__similar_properties|"
        # Y la plantilla de `berrueta` (Template3): el tooltip «Cochera» de una
        # tarjeta relacionada era el unico tipo que veia la ficha, y 24
        # departamentos quedaban guardados como cocheras.
        r"class=[\"'][^\"']*ficha__related|"
        # Tema WordPress inspiry-real-places (`gonzalez theyler`): «Propiedades
        # Similares» y «Destacadas» van en la barra lateral, despues de la
        # ficha; su precio y su tipo se leian como los de la propiedad.
        r"class=[\"'][^\"']*\bsimilar-properties\b|"
        r"class=[\"'][^\"']*\bInspiry_Featured_Properties_Widget\b|"
        r"<div[^>]+class=[\"'][^\"']*titulo_prod_int[^\"']*[\"'][^>]*>\s*"
        r"Otras\s+Propiedades\s*</div>|"
        # Y como encabezado: Coding & Company (`matias sosa`) titula
        # <h5>Otras propiedades</h5> sobre tarjetas de fichas vecinas.
        # Y con coletilla y marcado: `moyano` titula «Otras propiedades
        # <em>parecidas.</em>» y el «1 baño» / «2 baños» de la tarjeta vecina
        # -al azar en cada carga- dejaba la agencia no idempotente.
        r"<h[1-6]\b[^>]*>\s*Otras(?:\s|<[^>]+>)+propiedades"
        r"(?:(?:\s|<[^>]+>)+(?:parecidas|similares|relacionadas))?"
        r"(?:\s|<[^>]+>|[.:])*</h[1-6]>|"
        # La navegacion «← anterior | siguiente →» de WordPress (`mattioli`,
        # tema wpcasa): el titulo de la ficha vecina -«Depto 4 Amb.»- hacia
        # que el auditor exigiera ambientes a un lote.
        r"class=[\"'][^\"']*\bpost-navigation\b|"
        # «Similar Listings» de WPResidence (`berardi`): la tarjeta vecina «110m2
        # totales, 94m2 cub» le daba superficie 94 a todas sus fichas.
        r"(?:class|id)=[\"'][^\"']*\bproperty_similar_listings\b|"
        # El encabezado escrito, sin clase propia: `piccardo` (grvende.com.ar)
        # pone <h6 class="heading">Propiedades relacionadas</h6> y debajo las
        # tarjetas de otras fichas con «Ambientes 3 / Baños 1». Una ficha sin
        # esos rotulos se quedaba con los de la primera vecina, y la tabla de
        # la vecina ademas apagaba la lectura de su propia descripcion.
        # Con marcado adentro tambien: Terravirtual (`blangiforti`) titula
        # <h2><strong>Propiedades</strong> que te <strong>pueden</strong>
        # Interesar</h2>, y el «Galpon de 3 Amb.» de una vecina hacia que el
        # auditor exigiera ambientes a una ficha que publica «Ambientes: 0».
        r"<h[1-6]\b[^>]*>(?:\s|<[^>]+>)*Propiedades(?:\s|<[^>]+>)+"
        r"(?:relacionadas|similares|parecidas|que(?:\s|<[^>]+>)+te(?:\s|<[^>]+>)+"
        r"(?:pueden|podr(?:i|\u00ed)an)(?:\s|<[^>]+>)+interesar)",
                    html or "", maxsplit=1, flags=re.I)[0]


def sin_filtros_catalogo(html: str) -> str:
    """Quita opciones del buscador embebidas junto a la ficha legacy.

    Y los desplegables: `lazzaro` (Inmobiliatica) repite en cada ficha el
    buscador con <select id="dormitorios"><option>Dormitorios</option>
    <option>1</option>…, que aplanado dice «Dormitorios 1 2 3» y el auditor
    lo tomaba como un dato de la ficha. Un <select> es un control, nunca un
    atributo publicado de la propiedad.
    """
    html = re.sub(
        r"<label[^>]+name=[\"']search_filter[^\"']*[\"'][^>]*>.*?</label>",
        " ", html or "", flags=re.I | re.S)
    # Y las casillas: el buscador de Houzez (`o feely`) repite en cada ficha
    # «Tipo de operacion» con <label><input type="checkbox" value="alquiler">
    # Alquiler</label>, y la senal daba la operacion por publicada en 74
    # emprendimientos que no la dicen. Una casilla es un control, no un dato.
    html = re.sub(
        r"<label\b[^>]*>(?:(?!</?label\b).){0,400}?"
        r"<input\b[^>]*\btype=[\"']?(?:checkbox|radio)\b[^>]*>"
        r"(?:(?!</?label\b).){0,400}?</label>",
        " ", html, flags=re.I | re.S)
    return re.sub(r"<select\b.*?</select>", " ", html, flags=re.I | re.S)


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


# Una barra invertida que no abre un escape JSON valido.
RE_ESCAPE_INVALIDO = re.compile(r'\\(?!["\\/bfnrtu])')


def json_ld_tolerante(bloque: str) -> Any:
    """El JSON-LD de la ficha, o None si no es JSON.

    Algunos proveedores emiten saltos de linea literales dentro de los strings
    (invalidos bajo strict=True, pero el resto del objeto es inequivoco). Y
    `blanco propiedades` escribe barras sueltas en la descripcion -«\\ »,
    «\\-»-: `Invalid \\escape` descartaba el bloque ENTERO, con la
    `addressLocality` adentro. Se reintenta con esas barras como literales,
    que es lo que el autor escribio; nada mas cambia.
    """
    texto = (bloque or "").strip()
    try:
        return json.loads(texto, strict=False)
    except ValueError:
        pass
    try:
        return json.loads(RE_ESCAPE_INVALIDO.sub(r"\\\\", texto), strict=False)
    except ValueError:
        return None


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


class _DescargasDelDescubrimiento:
    """El descargador de siempre, recordando lo que ya contesto en un descubrimiento.

    Recuerda las respuestas y los rechazos definitivos (404/410, 403/429): un
    sitemap que no existe no aparece a los dos segundos. Un error transitorio
    NO se recuerda, para no convertir un corte momentaneo en una respuesta.
    """

    def __init__(self, descargador: Any):
        self._descargador = descargador
        self._respuestas: dict[str, str | Exception] = {}

    def bajar(self, url: str) -> str:
        previa = self._respuestas.get(url)
        if isinstance(previa, Exception):
            raise previa
        if previa is not None:
            return previa
        try:
            cuerpo = self._descargador.bajar(url)
        except (ErrorPermanente, Bloqueado) as error:
            self._respuestas[url] = error
            raise
        self._respuestas[url] = cuerpo
        return cuerpo

    def __getattr__(self, nombre: str) -> Any:
        return getattr(self._descargador, nombre)

    def __setattr__(self, nombre: str, valor: Any) -> None:
        # `bajar_formulario` suma sus pedidos al descargador: la suma tiene que
        # llegar al real, no quedar en esta envoltura que se tira al terminar.
        if nombre in ("_descargador", "_respuestas"):
            object.__setattr__(self, nombre, valor)
        else:
            setattr(self._descargador, nombre, valor)


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

    def _catalogo_gvamax(self, html: str, base: str) -> list[str] | None:
        """Catalogo de la plataforma GVAmax, que el sitio hidrata por POST.

        `grupo azor` y `livia renovell` enlazan gvamax.com.ar y su buscador
        llama `API_GetInmuebles()`, que hace POST a `Php/api.inmuebles.php` del
        MISMO sitio con los filtros del formulario (o, t, d, l, b). Con los
        filtros vacios -lo que el sitio pide al cargar- devuelve todas las
        fichas `detalle.php?id=p<n>-i<m>`. Sin esto las dos figuraban sin
        inventario (37 y 48 fichas).
        """
        if "gvamax.com.ar" not in (html or "").lower():
            return None
        try:
            cuerpo = bajar_formulario(
                self.descargador, f"{base}/Php/api.inmuebles.php",
                {"o": "", "t": "", "d": "", "l": "", "b": "", "gclid": ""})
        except (ErrorTransitorio, ErrorPermanente, Bloqueado):
            return None
        fichas: list[str] = []
        for crudo in re.findall(r"""href=["']\.?/?(detalle\.php\?id=p\d+-i\d+)["']""",
                                cuerpo or "", re.I):
            u = f"{base}/{crudo}"
            if u not in fichas:
                fichas.append(u)
        return fichas or None

    def _catalogo_por_tipo(self, html: str, portada: str,
                           base: str) -> dict[str, Any] | None:
        """Catalogo que la portada carga por TIPO con un POST propio.

        Plantilla Oestesi/Argencasas (`david rodriguez`, 365 declaradas): la
        portada no enlaza fichas; cada boton `onclick="buscar('Casa')"` carga
        `buscar.php` con `{type, page}` por POST y el resultado trae las fichas
        `propiedad-detalle.php?id=N` con su paginacion (`data-page`). Se exige
        la forma entera -los botones y la llamada `.load(... {page, type})`- y
        se leen solo los tipos que el propio sitio ofrece.
        """
        carga = re.search(
            r"""\.load\(\s*["']([\w\-/]+\.php)["']\s*,\s*\{\s*["']page["']\s*:\s*page\s*,"""
            r"""\s*["']type["']\s*:\s*event""", html or "")
        tipos = list(dict.fromkeys(re.findall(
            r"""onclick=["']buscar\(\s*'([^'"]{2,40})'\s*\)""", html or "")))
        if not carga or not tipos:
            return None
        endpoint = urllib.parse.urljoin(portada, carga.group(1))
        declarado = sum(int(n) for n in re.findall(
            r"""onclick=["']buscar\('[^']+'\)[^>]*>(?:(?!onclick=).){0,400}?(\d{1,5})\s+Propiedades""",
            html, re.S | re.I)) or None
        fichas: list[str] = []
        interrumpida = False
        for tipo in tipos:
            ultima, pagina = 1, 1
            while pagina <= min(ultima, 100):
                formulario = {"type": tipo} if pagina == 1 else {"page": pagina, "type": tipo}
                try:
                    cuerpo = bajar_formulario(self.descargador, endpoint, formulario)
                except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                    interrumpida = True
                    break
                for crudo in re.findall(r"""href=["']([^"'#]+)["']""", cuerpo or ""):
                    u = urllib.parse.urljoin(endpoint, unescape(crudo))
                    # Detalle del propio sitio: `propiedad-detalle.php?id=116`.
                    # `_es_ficha_url` no acepta un .php con id en la query, y
                    # aca la pagina ya es el resultado de la busqueda del sitio.
                    if (re.search(r"/[\w\-]*(?:propiedad|inmueble|ficha|detalle)[\w\-]*"
                                  r"\.php\?(?:[^#]*&)?id=\d+", u, re.I)
                            and self._mismo_sitio(u, base) and u not in fichas):
                        fichas.append(u)
                ultima = max([ultima] + [int(n) for n in re.findall(
                    r"""data-page=["'](\d{1,3})["']""", cuerpo or "")])
                pagina += 1
        if not fichas:
            return None
        return {"fichas": fichas[:MAX_FICHAS], "declarado": declarado,
                "interrumpida": interrumpida}

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
            r'(?:Valor\s*:\s*)?(USD|U\$[SD]|U\$\$?|US\$|ARS|\$)\s*([\d][\d.,]{1,15})',
            html or "", re.I)
        if price:
            result["moneda"] = _moneda_del_signo(price.group(1))
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
            archivo = ruta.rsplit("/", 1)[-1]
            # Rubros menos comunes solo como archivo ENTERO: `ramirez` enlaza
            # /tipos/cabanas.html y /tipos/islas.html junto a casas y campos, y
            # sin reconocerlas como categoria se enumeraban como fichas y
            # fallaban (2 detalles fallidos por corrida). Como palabra suelta
            # «islas» tambien es el nombre de una calle en una ficha.
            if not (patron.search(archivo)
                    or re.fullmatch(r"(?:caba(?:n|ñ|%c3%b1)as|islas)\.(?:html?|php)",
                                    archivo, re.I)):
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
        def raiz_de(cuerpo: str, pagina: str) -> str:
            # <base href> manda sobre la url de la pagina: `ramirez` enlaza
            # «propiedad/275-….html» desde /tipos/casas.html con
            # <base href="https://www.ramirez-inmobiliaria.com.ar/">, y unirlo
            # a la categoria daba /tipos/propiedad/… y /tipos/tipos/… (175 404).
            declarada = re.search(r"<base\b[^>]*href=[\"']([^\"']+)[\"']", cuerpo or "", re.I)
            if not declarada:
                return pagina
            ruta = urllib.parse.urlparse(urllib.parse.urljoin(pagina, declarada.group(1))).path
            return base + (ruta if ruta.startswith("/") else "/" + ruta)

        for categoria, cuerpo in paginas:
            raiz = raiz_de(cuerpo, categoria)
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
                destino = urllib.parse.urljoin(raiz, unescape(coincidencia.group(1)))
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

    def _catalogo_tiv(self, base: str) -> dict[str, Any] | None:
        """Total declarado y primeras fichas del buscador de TIV, o None."""
        try:
            html = self.descargador.bajar(f"{base}/buscar/inmuebles/")
        except (ErrorTransitorio, ErrorPermanente, Bloqueado):
            return None
        total = RE_TIV_TOTAL.search(html or "")
        if not total:
            return None
        fichas = list(dict.fromkeys(
            urllib.parse.urljoin(base + "/", h) for h in RE_TIV_FICHA.findall(html or "")))
        return {"total": int(total.group(1).replace(".", "")), "fichas": fichas}

    def _credencial_xintel_publica(self, html: str, portada: str,
                                   base: str) -> dict[str, Any] | None:
        """Credencial de CLIENTE de Xintel que el sitio oficial publica al navegador.

        Politica decidida por el usuario el 2026-09-28: se usa read-only
        cuando la publica explicitamente el sitio oficial, es parte de lo que
        recibe el navegador y es la que el frontend usa para consultar su
        propio catalogo. HTML y JavaScript propio se tratan igual.

        Se revisa, en este orden y solo en el MISMO sitio: la portada, sus
        scripts propios y la pagina del catalogo que enlaza. Un script de otro
        dominio no cuenta (no es configuracion del sitio), y tampoco una clave
        rotulada como secreta o token. Nunca se usa una clave para otra
        inmobiliaria: la credencial queda en el plan de ESTA fuente.
        """
        fuentes: list[tuple[str, str]] = [(portada, html)]
        for src in re.findall(r"""<script[^>]+src=["']([^"']+\.js[^"']*)["']""", html or "", re.I)[:12]:
            u = urllib.parse.urljoin(portada, unescape(src))
            if self._mismo_sitio(u, base):
                fuentes.append((u, None))
        for href in re.findall(r"""href=["']([^"'#?]*propiedades[^"'#?]*)["']""", html or "", re.I)[:2]:
            u = urllib.parse.urljoin(portada, unescape(href))
            if self._mismo_sitio(u, base) and u.rstrip("/") != portada.rstrip("/"):
                fuentes.append((u, None))
        vistas: set[str] = set()
        for url, texto in fuentes:
            if url in vistas:
                continue
            vistas.add(url)
            if texto is None:
                try:
                    texto = self.descargador.bajar(url)
                except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                    continue
            par = credencial_xintel_en(texto)
            if par:
                return {"inm": par[0], "clave": par[1], "source_url": url}
        return None

    def _catalogo_strapi(self, html: str, base: str) -> dict[str, Any] | None:
        """Un Strapi propio que el frontend del sitio consulta sin clave.

        `diego martin` (Next.js) no trae ninguna propiedad en el HTML: el
        catalogo sale de `https://<host>/api/propiedades?populate=*` y cada
        ficha es `/propiedades/{id}`, armada en el navegador. Se exige todo:
        la url de la API en el JavaScript PROPIO del sitio, que responda con la
        forma de Strapi (`data[].id/attributes`, `meta.pagination.total`) y
        que la ruta publica de la ficha exista (la pagina `[id]` del sitio).
        """
        chunks = sorted(set(re.findall(
            r"src=[\"'](/_next/static/chunks/app/[^\"']+\.js)[\"']", html or "")))[:8]
        api = coleccion = None
        for chunk in chunks:
            try:
                js = self.descargador.bajar(base + chunk)
            except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                continue
            m = RE_API_STRAPI.search(js or "")
            if m:
                api, coleccion = m.group(1), m.group(2)
                break
        if not api:
            return None
        try:
            dato = json.loads(self.descargador.bajar(
                f"{api}?populate=*&pagination[page]=1&pagination[pageSize]=1"))
            primero = dato["data"][0]
            total = int(dato["meta"]["pagination"]["total"])
            identificador = int(primero["id"])
            if not isinstance(primero.get("attributes"), dict):
                return None
        except (ErrorTransitorio, ErrorPermanente, Bloqueado, ValueError,
                KeyError, IndexError, TypeError):
            return None
        for ruta in dict.fromkeys((coleccion, "propiedad", "propiedades", "inmueble")):
            try:
                ficha = self.descargador.bajar(f"{base}/{ruta}/{identificador}")
            except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                continue
            if f"/app/{ruta}/%5Bid%5D/" in (ficha or ""):
                return {"api": api, "ruta": ruta, "total": total}
        return None

    def _strapi_v3_por_slug(self, html: str, url: str) -> tuple[dict, str] | None:
        """El objeto Strapi v3 de una ficha que el sitio arma en el navegador.

        `paladino` (Next.js): las 43 fichas del sitemap (/inmueble/<slug>) son
        cascarones -«ficha sin contenido» 43 de 43- y el sitio las llena con
        `GET https://api.<host>/inmuebles` (Strapi v3, sin clave; robots.txt
        sin Disallow, 2026-10-01). Se exige la url de la API en el JavaScript
        PROPIO del sitio, que `/count` responda un numero y que el filtro por
        slug devuelva UN solo objeto con ese mismo slug. Se pide solo ese
        objeto (~26 KB), no el catalogo entero (1,2 MB).
        """
        partes = urllib.parse.urlparse(url)
        host = partes.netloc.lower()
        cache = self.__dict__.setdefault("_strapi_v3_por_host", {})
        if host not in cache:
            cache[host] = None
            base = f"{partes.scheme}://{partes.netloc}"
            chunks = list(dict.fromkeys(re.findall(
                r"src=[\"'](/_next/static/chunks/[^\"']+\.js)[\"']", html or "")))[:12]
            for chunk in chunks:
                try:
                    js = self.descargador.bajar(base + chunk)
                except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                    continue
                m = RE_API_STRAPI_V3.search(js or "")
                if not m:
                    continue
                api = f"{m.group(1)}/{m.group(2)}"
                try:
                    if int(str(self.descargador.bajar(f"{api}/count")).strip()) > 0:
                        cache[host] = api
                except (ErrorTransitorio, ErrorPermanente, Bloqueado, ValueError):
                    pass
                break
        api = cache[host]
        slug = urllib.parse.unquote(partes.path.rstrip("/").rsplit("/", 1)[-1])
        if not api or not slug:
            return None
        try:
            lista = json.loads(self.descargador.bajar(
                f"{api}?slug={urllib.parse.quote(slug)}&_limit=2"))
        except (ErrorTransitorio, ErrorPermanente, Bloqueado, ValueError, TypeError):
            return None
        if not isinstance(lista, list) or len(lista) != 1:
            return None
        objeto = lista[0]
        if not isinstance(objeto, dict) or objeto.get("slug") != slug:
            return None
        return objeto, api.rsplit("/", 1)[0]

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
        """Descubre con memoria de lo ya bajado, solo mientras dura el descubrimiento.

        Las variantes se prueban una detras de otra y varias vuelven a pedir lo
        mismo: medido en 14 agencias, 47 de 233 pedidos eran repetidos (los
        tres sitemaps dos veces al reintentar desde la raiz, el listado dos o
        tres veces). La memoria vive lo que vive esta llamada: el listado y las
        fichas se leen de nuevo, y la segunda corrida de la certificacion no ve
        nada de la primera.
        """
        if isinstance(self.descargador, _DescargasDelDescubrimiento):
            return self._descubrir(fuente, _desde_la_raiz)
        original = self.descargador
        self.descargador = _DescargasDelDescubrimiento(original)
        try:
            return self._descubrir(fuente, _desde_la_raiz)
        finally:
            self.descargador = original

    def _descubrir(self, fuente: Fuente,
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
        # TIV Tecnogestion: el catalogo entero esta detras del buscador (ver
        # RE_TIV). Solo si el buscador DECLARA su total: sin total no hay contra
        # que verificar la paginacion, y se sigue por el camino de siempre.
        if RE_TIV.search(html or ""):
            tiv = self._catalogo_tiv(base)
            if tiv is not None:
                plan.update({"variante": "TIV_BUSQUEDA", "soportada": True,
                             "tiv_base": base, "tiv_primeras": tiv["fichas"],
                             "total_declarado": tiv["total"],
                             "catalogo_runtime_verificado": True})
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
                         "xintel_credencial": _procedencia_credencial(
                             fuente, fuente.official_url, xintel_key.group(1)),
                         "total_declarado": None})
            return plan
        # La misma credencial PUBLICA de cliente, cuando el frontend la movio de
        # la portada a su JavaScript propio (`aloise`: config.js) o a la pagina
        # del catalogo (`labastida`: /propiedades). Politica del 28-09: se usa
        # read-only, solo si la sirve el sitio oficial al navegador y en
        # contexto Xintel. Ver `_credencial_xintel_publica`.
        if "xintel" in html.lower():
            publica = self._credencial_xintel_publica(html, fuente.official_url, base)
            if publica is not None:
                plan.update({"variante": "XINTEL_API", "soportada": True,
                             "xintel_inm": publica["inm"],
                             "xintel_key": publica["clave"],
                             "xintel_credencial": _procedencia_credencial(
                                 fuente, publica["source_url"], publica["clave"]),
                             "total_declarado": None})
                return plan
        if "/_next/static/" in html:
            strapi = self._catalogo_strapi(html, base)
            if strapi is not None:
                plan.update({"variante": "STRAPI_API", "soportada": True,
                             "strapi_api": strapi["api"],
                             "strapi_ruta": strapi["ruta"],
                             "total_declarado": strapi["total"],
                             "catalogo_runtime_verificado": True})
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
        por_tipo = self._catalogo_por_tipo(html, fuente.official_url, base)
        if por_tipo is not None:
            plan.update({"variante": "BUSQUEDA_POR_TIPO", "soportada": True,
                         "fichas": por_tipo["fichas"],
                         "total_declarado": por_tipo["declarado"],
                         "paginacion_interrumpida_en_discover": por_tipo["interrumpida"],
                         "catalogo_runtime_verificado": True})
            return plan
        gvamax = self._catalogo_gvamax(html, base)
        if gvamax:
            plan.update({"variante": "GVAMAX_API", "soportada": True,
                         "fichas_gvamax": gvamax, "total_declarado": None,
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
        html_portada = html
        candidatos = ([] if ya_es_el_catalogo else [base + "/propiedades"])
        candidatos += [c for c in self._catalogos_enlazados(html, base)
                       if c.rstrip("/") != fuente.official_url.rstrip("/")]
        paginados: list[tuple[str, str]] = []
        if candidatos:
            for candidato in candidatos:
                try:
                    html_listado = self.descargador.bajar(candidato)
                except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                    continue
                runtime_listado = runtime or self._patron_raiz_local(html_listado)
                enlaces_listado = self._fichas_en(html_listado, base,
                                                  runtime_listado)
                if enlaces_listado and self._declara_paginacion(html_listado, candidato):
                    paginados.append((candidato, html_listado))
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
            if paginados:
                plan["catalogos_paginados"] = paginados
            if self._declara_paginacion(html, listado):
                grilla = self._fichas_en(self._solo_el_listado(html), base, runtime)
                if grilla:
                    plan["fichas_home"] = grilla
            resultados: list[str] = []
            # Y las categorias en la raiz con la operacion en plural
            # (/ventas-casas, /alquileres-departamentos-2-dormitorios): la
            # tienda DonWeb de `arquitectura inmobiliaria` muestra 8 fichas en
            # /propiedades y 30 repartidas en sus categorias, enlazadas desde
            # el listado y no desde la portada.
            for crudo in re.findall(r'href=["\']([^"\']+)["\']',
                                    (html_portada or "") + (html or "")):
                destino = urllib.parse.urljoin(base + "/", unescape(crudo)).split("#")[0]
                if (self._mismo_sitio(destino, base)
                        and re.match(r"^/(?:resultados?/|(?:alquileres|ventas)(?:-[a-z0-9-]+)?/?$)",
                                     urllib.parse.urlparse(destino).path, re.I)
                        and destino not in resultados):
                    resultados.append(destino)
            fichas_resultados: list[str] = []
            for pagina_resultado in resultados[:MAX_CATEGORIAS * 2]:
                try:
                    cuerpo_resultado = self.descargador.bajar(pagina_resultado)
                except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                    continue
                for u in self._fichas_en(self._solo_el_listado(cuerpo_resultado), base, runtime):
                    if u not in fichas_resultados:
                        fichas_resultados.append(u)
            if fichas_resultados:
                plan["fichas_de_resultados"] = fichas_resultados
            mapa, extra_fichas = self._catalogos_por_operacion(html_portada, base, runtime)
            if mapa:
                plan["operacion_por_ficha"] = mapa
                plan["fichas_por_operacion"] = extra_fichas
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
            or RE_FICHA_CON_ID.search(u)
            or RE_FICHA_DETALLE.search(ruta)
            or (ficha_amaira_en_query(u) is not None and "ficha=" in ficha_amaira_en_query(u))
            or RE_FICHA_RAIZ.search(ruta)
            or RE_FICHA_ID_PROPIEDAD_INMOBILIARIA.search(ruta)
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
        from scraper.detail_urls import (_looks_like_detail_url, _onclick_urls,
                                         extract_candidate_detail_urls_from_card,
                                         extract_candidate_detail_urls_from_document)
        host = (urllib.parse.urlparse(base).hostname or '').lower().removeprefix('www.')
        salida, vistas = [], set()
        soup = BeautifulSoup(html or '', 'html.parser')
        recovered = [url for url, _ in extract_candidate_detail_urls_from_document(soup, base)]
        for card in soup.select("article, [class*='property'], [class*='propiedad'], [class*='listing'], [class*='card']"):
            recovered.extend(extract_candidate_detail_urls_from_card(card, base))
        # Tarjetas que navegan por `onclick` sin enlace: `aris propiedades`
        # publica sus doce fichas como `<li onclick="location.href='ficha.php?
        # ficha=ARI2829'" class="col-sm-6 ...">`, sin clase de tarjeta ni
        # `href`, y se enumeraban 4 (las del carrusel). Solo entra lo que el
        # detector conservador acepta como ficha, y el detalle la confirma.
        for elemento in soup.select("[onclick]"):
            for crudo in _onclick_urls(str(elemento.get("onclick") or "")):
                u = urllib.parse.urljoin(base, crudo)
                if _looks_like_detail_url(u, base):
                    recovered.append(u)
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
            partes = urllib.parse.urlparse(u)
            terravirtual = RE_FICHA_TERRAVIRTUAL.match(partes.path)
            if terravirtual:
                u = f"{partes.scheme}://{partes.netloc}/ficha/{terravirtual.group(1).lower()}"
            c = u.split("#")[0].rstrip("/")
            if c not in vistas:
                vistas.add(c)
                salida.append(u)
        soup.decompose()
        return salida

    # ----------------------------------------------------------- fetch_listing
    def _catalogos_por_operacion(self, html: str, base: str,
                                 runtime: "re.Pattern | None"
                                 ) -> tuple[dict[str, str], list[tuple[str, str]]]:
        """Operacion de cada ficha segun los catalogos gemelos de venta y alquiler.

        `bottai` publica la operacion SOLO en el catalogo que la lista
        -`inmuebles_list_Venta_...` e `inmuebles_list_Alquiler_...`, 219 y 93
        fichas- y ninguna en la ficha: 180 salian sin operacion. Se exige que
        la portada enlace los DOS catalogos con la misma ruta salvo la palabra
        de la operacion; una ficha listada en ambos queda sin operacion. Las
        fichas de esos catalogos que la enumeracion no vio se agregan despues.
        """
        # Tambien en plural: `blangiforti` enlaza /ventas (174) y /alquileres
        # (3, dos que /ventas no lista) y esas dos quedaban fuera.
        token = re.compile(r"(?<![a-z])(ventas?|alquiler(?:es)?)(?![a-z])", re.I)
        singular = {"ventas": "venta", "alquileres": "alquiler"}
        gemelos: dict[str, dict[str, str]] = {}
        for coincidencia in re.finditer(r'href=["\']([^"\']+)["\']', html or ""):
            destino = urllib.parse.urljoin(base + "/", unescape(coincidencia.group(1)))
            if not self._mismo_sitio(destino, base):
                continue
            partes = urllib.parse.urlparse(destino)
            ruta = partes.path + ("?" + partes.query if partes.query else "")
            hallados = token.findall(ruta)
            if len(hallados) != 1:
                continue
            clave = token.sub("{op}", ruta).lower()
            operacion = singular.get(hallados[0].lower(), hallados[0].lower())
            gemelos.setdefault(clave, {}).setdefault(operacion, destino.split("#")[0])
        par = next((v for v in gemelos.values() if set(v) == {"venta", "alquiler"}), None)
        if not par:
            return {}, []
        por_url: dict[str, set[str]] = {}
        orden: list[str] = []
        for operacion, catalogo in par.items():
            try:
                cuerpo = self.descargador.bajar(catalogo)
            except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                return {}, []
            for u in self._fichas_en(cuerpo, base, runtime):
                c = u.split("#")[0].rstrip("/")
                if c not in por_url:
                    orden.append(u)
                por_url.setdefault(c, set()).add(operacion)
        mapa = {c: next(iter(ops)) for c, ops in por_url.items() if len(ops) == 1}
        return mapa, [(u, mapa[u.split("#")[0].rstrip("/")]) for u in orden
                      if u.split("#")[0].rstrip("/") in mapa]

    def fetch_listing(self, fuente: Fuente, plan: dict[str, Any]) -> Iterator[dict]:
        """Las candidatas, sin la misma ficha repetida con el contexto del listado.

        `guillermo rodriguez` enlaza cada ficha dos veces: `detalles.php?id=1449`
        y `detalles.php?id=1449&tipo=25&operacion=0` (desde la categoria). La
        identidad se guarda por URL, asi que las dos entrarian como propiedades
        distintas. Se descarta la larga SOLO si la corta tambien se enumero: un
        sitio que publica unicamente la forma larga conserva su identidad.
        """
        # Por enumeracion: las variantes que lo cuentan lo reasignan adentro.
        self.duplicados_origen = 0
        items = list(self._candidatas(fuente, plan))
        enumeradas = {_url_y_parametros(i["source_url"]) for i in items}
        # La misma ficha con otro texto descriptivo en la query (`ballarre` 97,
        # `zamorano` 53): `ver-propiedad-venta.asp?id=Venta-de-Casa-3-ambientes-
        # en-Miramar&codigo=5889` y `?id=Venta-de-Casa-en-Miramar&codigo=5889`
        # son la misma casa -el servidor ignora `id`, hasta `id=cualquier-cosa`
        # la devuelve-. Se queda la URL menor, para que dos corridas elijan igual.
        elegida_por_ficha: dict[tuple, str] = {}
        for item in items:
            clave = _clave_sin_slug(item["source_url"])
            if clave is not None:
                previa = elegida_por_ficha.get(clave)
                elegida_por_ficha[clave] = min(previa, item["source_url"]) if previa else item["source_url"]
        repetidas = 0
        self.categorias_descartadas = 0
        for item in items:
            if es_url_de_categoria(item["source_url"]):
                self.categorias_descartadas += 1
                continue
            corta = _sin_contexto_del_listado(item["source_url"])
            if corta is not None and corta in enumeradas:
                repetidas += 1
                continue
            clave = _clave_sin_slug(item["source_url"])
            if clave is not None and elegida_por_ficha[clave] != item["source_url"]:
                repetidas += 1
                continue
            yield item
        # Una categoria descartada ES un registro declarado (el sitemap la lista) y
        # ya esta contabilizada: sin sumarla, `1832 negocios inmobiliarios`
        # (67 declaradas, 3 categorias) figuraba con la enumeracion incompleta y
        # paraba la familia generico (29-09).
        if repetidas or self.categorias_descartadas:
            self.duplicados_origen = (getattr(self, "duplicados_origen", 0) + repetidas
                                      + self.categorias_descartadas)

    def _candidatas(self, fuente: Fuente, plan: dict[str, Any]) -> Iterator[dict]:
        mapa = plan.get("operacion_por_ficha") or {}
        vistas: set[str] = set()
        listado = plan.get("listing_url")
        ruta_listado = (urllib.parse.urlparse(listado).path.rstrip("/").lower()
                        if listado else None)
        for item in self._fetch_listing(fuente, plan):
            c = item["source_url"].split("#")[0].rstrip("/")
            # El propio listado, con o sin filtro (`jorge martinez`:
            # /propiedades.php, ?operacion=venta, ?operacion=alquiler), llegaba
            # como candidata por forma, el guardian la rechazaba y contaba como
            # detalle fallido. Una candidata SIN forma de ficha cuya ruta es la
            # del listado no es una ficha.
            if (item.get("por_forma") and ruta_listado
                    and urllib.parse.urlparse(c).path.rstrip("/").lower() == ruta_listado):
                continue
            vistas.add(c)
            if c in mapa:
                item.setdefault("operacion_catalogo", mapa[c])
            yield item
        for u, operacion in plan.get("fichas_por_operacion") or []:
            c = u.split("#")[0].rstrip("/")
            if c in vistas:
                continue
            vistas.add(c)
            yield {"source_listing_id": self._id_de(u), "source_url": u, "pagina": 9000,
                   "por_forma": self._solo_por_forma(u, plan.get("patron_runtime")),
                   "catalogo_runtime_verificado": plan.get("catalogo_runtime_verificado", False),
                   "operacion_catalogo": operacion}
        # Las fichas de las paginas de resultados por categoria que enlaza la
        # portada (`lizio albarello`: /resultado/1/1/2/casas-en-venta/ lista 7
        # fichas que la portada no muestra).
        for u in plan.get("fichas_de_resultados") or []:
            c = u.split("#")[0].rstrip("/")
            if c in vistas:
                continue
            vistas.add(c)
            yield {"source_listing_id": self._id_de(u), "source_url": u, "pagina": 9500,
                   "por_forma": self._solo_por_forma(u, plan.get("patron_runtime")),
                   "catalogo_runtime_verificado": plan.get("catalogo_runtime_verificado", False)}

    def _fetch_listing(self, fuente: Fuente, plan: dict[str, Any]) -> Iterator[dict]:
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
        if plan["variante"] == "STRAPI_API":
            # Paginado de Strapi hasta `pageCount`; el corte por pagina vacia
            # cubre un `pageCount` que mienta.
            vistos: set[str] = set()
            for pagina in range(1, TOPE_PAGINAS_STRAPI + 1):
                try:
                    dato = json.loads(self.descargador.bajar(
                        f"{plan['strapi_api']}?populate=*&pagination[page]={pagina}"
                        f"&pagination[pageSize]={PAGINA_STRAPI}"))
                except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                    self.paginacion_interrumpida = True
                    return
                except (json.JSONDecodeError, TypeError):
                    self.paginacion_interrumpida = True
                    return
                filas = (dato or {}).get("data") or []
                for fila in filas:
                    identificador = str((fila or {}).get("id") or "").strip()
                    if not identificador or identificador in vistos:
                        continue
                    vistos.add(identificador)
                    yield {"source_listing_id": identificador,
                           "source_url": f"{plan['base']}/{plan['strapi_ruta']}/{identificador}",
                           "pagina": pagina,
                           "strapi_objeto": fila.get("attributes") or {}}
                cuantas = (((dato or {}).get("meta") or {}).get("pagination") or {}).get("pageCount")
                if not filas or (isinstance(cuantas, int) and pagina >= cuantas):
                    return
            return
        if plan["variante"] in ("SITEMAP", "CATEGORY_HTML_CATALOG", "BUSQUEDA_POR_TIPO"):
            if plan.get("paginacion_interrumpida_en_discover"):
                # Un POST de la busqueda por tipo que no respondio no es haber
                # llegado al final del catalogo.
                self.paginacion_interrumpida = True
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
        if plan["variante"] == "TIV_BUSQUEDA":
            # La primera tanda viene en el HTML del buscador; las siguientes,
            # de a 10, por el mismo POST que hace el scroll infinito. Termina
            # cuando una pagina no trae nada nuevo; un error corta y se dice.
            self.paginacion_interrumpida = False
            vistas_tiv: set[str] = set()
            nuevas = list(plan["tiv_primeras"])
            pagina = 1
            tope = (int(plan.get("total_declarado") or 0) // TIV_POR_PAGINA) + 3
            while nuevas:
                for url in nuevas:
                    vistas_tiv.add(url)
                    yield {"source_listing_id": self._id_de(url), "source_url": url,
                           "pagina": pagina, "catalogo_runtime_verificado": True}
                pagina += 1
                if pagina > min(tope, 300):
                    break
                try:
                    cuerpo = bajar_formulario(
                        self.descargador, f"{plan['tiv_base']}/Buscar/CargaMasInmueblesParam",
                        {**TIV_FORMULARIO, "Pagina": str(pagina)})
                except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                    self.paginacion_interrumpida = True
                    return
                nuevas = [u for u in dict.fromkeys(
                    urllib.parse.urljoin(plan["tiv_base"] + "/", h)
                    for h in RE_TIV_FICHA.findall(cuerpo or "")) if u not in vistas_tiv]
            return
        if plan["variante"] == "XINTEL_API":
            # La credencial publica de cliente de ESTA fuente, para el detalle
            # cuando la ficha no publica sus parametros (ver `_normalizar_xintel`).
            self._xintel_cliente = (plan["xintel_inm"], plan["xintel_key"])
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
        if plan["variante"] == "GVAMAX_API":
            for u in plan.get("fichas_gvamax") or []:
                c = u.rstrip("/")
                if c in vistas:
                    continue
                vistas.add(c)
                yield {"source_listing_id": self._id_de(u), "source_url": u, "pagina": 1,
                       "por_forma": False, "catalogo_runtime_verificado": True}
            return
        if plan["variante"] == "MAPAPROP_HTML":
            total = int(plan["total_declarado"])
            per_page = max(1, int(plan.get("per_page") or 1))
            # Las paginas pueden repetir fichas de la anterior: `bardi` sirve
            # 16 por pagina pero desde la segunda solo ~10 son nuevas, y el
            # tope ⌈105/16⌉+2 = 9 paginas cortaba en 90 de 105 (llegan en la
            # pagina 10). Se sigue mientras aparezcan fichas nuevas; el tope
            # queda solo como seguro contra un listado que no termina.
            max_pages = min(1000, 3 * ((total + per_page - 1) // per_page) + 2)
            duplicates = 0
            sin_novedades = 0
            for page in range(max_pages):
                if len(vistas) >= total or sin_novedades >= 2:
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
                antes = len(vistas)
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
                sin_novedades = 0 if len(vistas) > antes else sin_novedades + 1
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

        # La paginacion que el listado declara en sus enlaces va antes que las
        # convenciones: `ballarre` pagina con ?start=13, 25, 37… y, sin leerla,
        # la convencion `/?page=N` recorria 50 veces la portada, que muestra
        # destacadas AL AZAR: 235 fichas en una corrida y 259 en la otra, con 35
        # distintas, y la cola paro la familia.
        # Y TODOS los catalogos que la declaran, no solo el elegido: `zamorano`
        # (misma plataforma que `ballarre`) reparte venta, alquiler temporario
        # y permutas en tres listados paginados, y su portada muestra
        # destacadas al azar; elegir uno solo dejaba fuera a los otros y la
        # eleccion misma cambiaba de corrida a corrida (165 contra 162).
        catalogos = list(plan.get("catalogos_paginados") or [])
        declarada = plan.get("listing_url")
        if declarada and plan.get("html_home") and all(u != declarada for u, _ in catalogos):
            catalogos.insert(0, (declarada, plan["html_home"]))
        aporto = False
        for orden, (catalogo, primera) in enumerate(catalogos):
            if catalogo != declarada:
                for u in self._fichas_en(self._solo_el_listado(primera), base, propia):
                    c = u.rstrip("/")
                    if c in vistas:
                        continue
                    vistas.add(c)
                    aporto = True
                    yield {"source_listing_id": self._id_de(u), "source_url": u,
                           "pagina": 1, "por_forma": self._solo_por_forma(u, propia),
                           "catalogo_runtime_verificado": False}
            for item in self._paginacion_declarada(primera, catalogo, base, propia, vistas):
                aporto = True
                yield item
        if aporto:
            return

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
        # `/propiedades/pagina-N/` (`cuini`: 6 por pagina, 37 en siete paginas;
        # la portada solo enlaza 16).
        for patron in (patron_infinito, "{b}/propiedades/page/{n}/", "{b}/propiedades?page={n}",
                       "{b}/propiedades/pagina-{n}/", "{b}?page={n}"):
            inicio_patron = len(vistas)
            duplicados_patron = 0
            sin_nuevas = 0
            paginas_con_nuevas = 0
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
                    paginas_con_nuevas += 1
            if len(vistas) > inicio_patron:
                self.duplicados_origen = duplicados_patron
                self.paginacion_interrumpida = interrumpido
                # Una sola pagina con novedades puede ser el sitio IGNORANDO el
                # parametro y sirviendo la primera del listado: `cuini`
                # responde /propiedades/page/2/ con /propiedades/ y cortar ahi
                # tapaba su paginacion real, /propiedades/pagina-N/ (16 de 37).
                # Se sigue probando; lo ya visto no se repite.
                if paginas_con_nuevas >= 2:
                    break

    @staticmethod
    def _solo_el_listado(html: str) -> str:
        """La grilla del listado, sin los bloques que rotan en cada carga.

        `zamorano`: cada pagina de su listado trae la grilla (estable) y
        despues «Ventas Destacadas» y «Últimos Ingresos», elegidas al azar en
        cada pedido: sumarlas hacia que dos corridas enumeraran conjuntos
        distintos. Se corta en el primer encabezado de uno de esos bloques.
        """
        cuerpo = cuerpo_principal(html)
        return re.split(r"<h[1-6][^>]*>[^<]{0,40}(?:destacad|ingresos|relacionad|similares)",
                        cuerpo, maxsplit=1, flags=re.I)[0]

    @staticmethod
    def _declara_paginacion(html: str, listado: str) -> bool:
        """El listado enlaza su propia ruta con un parametro numerico de pagina."""
        ruta = urllib.parse.urlparse(listado).path
        for crudo in re.findall(r'href=["\']([^"\']+)["\']', html or ""):
            partes = urllib.parse.urlparse(urllib.parse.urljoin(listado, unescape(crudo)))
            if partes.path != ruta:
                continue
            pares = [(k, v) for k, v in urllib.parse.parse_qsl(partes.query) if v != ""]
            if [v for k, v in pares if k.lower() in PARAMS_DE_PAGINA and v.isdigit()]:
                return True
        return False

    def _paginacion_declarada(self, html: str, listado: str, base: str,
                              propia: "re.Pattern | None",
                              vistas: set[str]) -> Iterator[dict]:
        """Recorre las paginas que el listado enlaza por un parametro de pagina.

        Solo enlaces a la MISMA ruta del listado cuyo resto de la query ya esta
        en el listado (una variante de orden o de filtro no entra). Las paginas
        nuevas que aparecen al avanzar -la ventana 1..10 que se corre- se
        agregan a la cola. Corta sin mas paginas o en el tope.
        """
        destino_listado = urllib.parse.urlparse(listado)
        propios = {k: v for k, v in urllib.parse.parse_qsl(destino_listado.query)
                   if k.lower() not in PARAMS_DE_PAGINA}

        def paginas_en(cuerpo: str, desde: str) -> list[str]:
            salida = []
            for crudo in re.findall(r'href=["\']([^"\']+)["\']', cuerpo or ""):
                u = urllib.parse.urljoin(desde, unescape(crudo))
                partes = urllib.parse.urlparse(u)
                if partes.path != destino_listado.path or not self._mismo_sitio(u, base):
                    continue
                pares = [(k, v) for k, v in urllib.parse.parse_qsl(partes.query) if v != ""]
                pagina = [v for k, v in pares if k.lower() in PARAMS_DE_PAGINA]
                resto = {k: v for k, v in pares if k.lower() not in PARAMS_DE_PAGINA}
                if len(pagina) != 1 or not pagina[0].isdigit():
                    continue
                if any(propios.get(k) != v for k, v in resto.items()):
                    continue
                salida.append(u.split("#")[0])
            return salida

        pendientes = list(dict.fromkeys(paginas_en(html, listado)))
        pedidas: set[str] = set()
        n = 0
        while pendientes and n < TOPE_PAGINAS_DECLARADAS:
            pagina_url = pendientes.pop(0)
            if pagina_url in pedidas:
                continue
            pedidas.add(pagina_url)
            n += 1
            try:
                cuerpo = self.descargador.bajar(pagina_url)
            except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                self.paginacion_interrumpida = True
                return
            for u in self._fichas_en(self._solo_el_listado(cuerpo), base, propia):
                c = u.rstrip("/")
                if c in vistas:
                    continue
                vistas.add(c)
                yield {"source_listing_id": self._id_de(u), "source_url": u,
                       "pagina": n + 1, "por_forma": self._solo_por_forma(u, propia),
                       "catalogo_runtime_verificado": False}
            for nueva in paginas_en(cuerpo, pagina_url):
                if nueva not in pedidas and nueva not in pendientes:
                    pendientes.append(nueva)

    @staticmethod
    def _id_de(url: str) -> str:
        """Id de la plataforma si lo hay; si no, el slug. Nunca un hash propio:
        tiene que poder rastrearse hasta la ficha de origen."""
        parsed = urllib.parse.urlparse(url)
        amaira = ficha_amaira_en_query(url)
        if amaira:
            codigo = urllib.parse.parse_qs(urllib.parse.urlparse(amaira).query).get("ficha")
            if codigo and codigo[0].strip():
                return codigo[0].strip()
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
        if crudo.get("strapi_objeto"):
            # Igual que el proxy de Tokko: la ficha publica se arma en el
            # navegador con este mismo objeto.
            return self._normalizar_strapi(crudo, fuente)
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
            # «Propiedad inexistente.» con 200 (`d uva`: las 9 fichas de su
            # sitemap) es la baja de la ficha dicha por el sitio, no una
            # lectura fallida nuestra: se anota como el 404 para que el runner
            # la cuente como desaparecida.
            if RE_FICHA_INEXISTENTE.fullmatch(_texto(html or "").strip()):
                self.anotar_error(fuente, "detalle_permanente",
                                  ErrorPermanente("ficha inexistente"))
            return None
        html = con_cierres_normales(html)
        if ("/_next/static/" in html
                and re.search(r"/(?:inmueble|inmuebles|propiedad|propiedades)/[^/?#]+/?$",
                              urllib.parse.urlparse(url).path, re.I)
                and not re.search(r"application/ld\+json", html, re.I)
                # Solo un CASCARON: poco texto visible y ningun precio. Una
                # ficha Next.js con contenido (`fenix`) no paga la busqueda de
                # la API (hasta 12 chunks por host).
                and len(_texto(html)) < 2500
                and not re.search(r"(?:U\$S|USD|US\$|\$)\s*\d", _texto(html))):
            v3 = self._strapi_v3_por_slug(html, url)
            if v3 is not None:
                objeto, api_base = v3
                propiedad_v3 = self._normalizar_strapi(
                    {**crudo, "strapi_objeto": objeto, "strapi_v3_base": api_base}, fuente)
                if propiedad_v3 is not None:
                    return propiedad_v3
        # Y dicha en el ENCABEZADO de una pagina completa: `los cerros` (Next.js)
        # responde a veces con 200 y <h1>Propiedad no encontrada</h1> dentro de
        # la plantilla del sitio, y se guardaba una «propiedad» con ese titulo,
        # sin datos y con la og-image como foto (253 de 333 en una corrida).
        # Como el 404, el runner la reintenta una vez y la recupera si vuelve.
        primer_h1 = re.search(r"<h1\b[^>]*>(.*?)</h1>", html, re.I | re.S)
        if primer_h1 and RE_FICHA_INEXISTENTE.fullmatch(_texto(primer_h1.group(1)).strip()):
            self.anotar_error(fuente, "detalle_permanente",
                              ErrorPermanente("ficha inexistente"))
            return None
        # Una ficha Xintel que entro por el camino HTML tambien se lee de la
        # API. Sin JavaScript, la plantilla muestra el titulo «en», la
        # descripcion vacia (`<p class="txtobs"></p>`) y dos fotos:
        # `cannonepropiedades.com.ar` se guardaba asi en sus 16 fichas, y la
        # API trae titulo, descripcion, coordenadas y 20 a 28 fotos. La senal
        # es la que la propia plantilla usa para pedir el detalle.
        amaira = ficha_amaira_en_query(url)
        if amaira and not self._es_ficha_xintel(html):
            try:
                envuelta = self.descargador.bajar(amaira)
            except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                envuelta = ""
            if self._es_ficha_xintel(envuelta):
                html = envuelta
        if crudo.get("xintel") or self._es_ficha_xintel(html):
            return self._normalizar_xintel(crudo, fuente,
                                           self._ficha_xintel_embebida(html))

        principal = cuerpo_principal(html)
        texto = normalizar_texto_campos(_texto(sin_filtros_catalogo(principal)))
        # Un emprendimiento contiene fichas de unidades debajo de ``UNIDADES``.
        # Esos ambientes/precios/operaciones pertenecen a las unidades, no al
        # desarrollo padre. Mezclarlos inventa atributos para el proyecto.
        # `alagna` publica los suyos en /emprendimientos/ (plural): 21 edificios
        # salian tipo «casa» -del menu del sitio- con los dormitorios de una
        # unidad cualquiera.
        es_emprendimiento = bool(re.search(
            r"/emprendimientos?/", urllib.parse.urlparse(url).path.lower()))
        principal_campos = (re.split(
            r">\s*UNIDADES(?:\s+disponibles)?\s*<|id=[\"']property-sub-listings-wrap[\"']", principal, maxsplit=1, flags=re.I)[0]
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
        if not descripcion:
            # El contenedor de la plantilla, sin rotulo: `fios` publica
            # <div class="property-description …"><div class="show-more"><p>…
            # y 122 de sus 276 fichas quedaban sin descripcion. Se toma hasta el
            # proximo encabezado o comentario de seccion, como el rotulo.
            contenedor = re.search(
                r"<div\b[^>]*class=[\"'][^\"']*\bproperty-description\b[^\"']*[\"'][^>]*>",
                principal, re.I)
            if contenedor:
                resto = sin_bloques_no_textuales(principal[contenedor.end():])
                corte = re.search(r"<h[1-6]\b|<footer\b|<!--\s*(?!Details)", resto, re.I)
                visible = limpiar(_texto((resto[:corte.start()] if corte else resto)[:6000]))
                if not visible or len(visible) < 40:
                    # El contenedor abre con su propio encabezado «Descripción»
                    # y el texto trae subtitulos (tema ERE, `ingar`): cortar en
                    # el primer encabezado lo dejaba vacio. Se lee el contenedor
                    # entero, sin ese encabezado.
                    from bs4 import BeautifulSoup
                    sopa = BeautifulSoup(principal[contenedor.start():contenedor.start() + 60000],
                                         "html.parser")
                    caja = sopa.find(True)
                    if caja is not None:
                        for titulo_caja in caja.find_all(re.compile(r"^h[1-6]$")):
                            if re.fullmatch(r"descripci[oó]n", titulo_caja.get_text(strip=True), re.I):
                                titulo_caja.decompose()
                        # Una caja vacia da None y cortarlo reventaba la ficha
                        # entera (`manuel ponce`: TypeError en el certificador).
                        visible = (limpiar(re.sub(r"\s+", " ", caja.get_text(" "))) or "")[:6000]
                    sopa.decompose()
                descripcion = visible if visible and len(visible) >= 40 else None
        if not descripcion:
            # Elementor + JetEngine (`esnal`, 39 de 48 sin descripcion): el
            # campo bajo «Descripcion» puede venir VACIO y el texto aparecer
            # unos bloques mas abajo como otro campo dinamico. Se toma el primer
            # campo JetEngine que es PROSA (>=120): los de atributos son cortos
            # («Baños: 1», «Tipo de Propiedad: Departamento»).
            jet = RE_DESCRIPCION_JETENGINE.search(principal)
            if jet:
                visible = limpiar(_texto(jet.group(1)))
                descripcion = visible if visible and len(visible) >= 120 else None
        if not descripcion:
            # Terravirtual (`blangiforti`, 174 fichas): el encabezado es
            # «<strong>Información</strong> <small>de la Propiedad</small>» y el
            # texto va en el primer <p> que le sigue. Sin leerlo, la ficha caia
            # al meta -el eslogan del sitio, igual en todas- y el runner lo
            # descartaba por compartido: 164 de 164 sin descripcion.
            encabezado = re.search(
                r"<h[1-6]\b[^>]*>(?:\s|<[^>]+>)*Informaci(?:\u00f3|o|&oacute;)n"
                r"(?:\s|<[^>]+>)*de\s+la\s+propiedad(?:\s|<[^>]+>)*</h[1-6]>",
                principal, re.I)
            if encabezado:
                parrafo = re.search(r"<p\b[^>]*>(.*?)</p>",
                                    principal[encabezado.end():encabezado.end() + 3000],
                                    re.I | re.S)
                visible = limpiar(_texto(parrafo.group(1))) if parrafo else None
                descripcion = visible if visible and len(visible) >= 40 else None
        if descripcion and meta and self._es_su_comienzo(descripcion, meta):
            # El rotulo solo trajo el comienzo de lo que el meta dice entero:
            # `funesinmobiliaria` rotula «VENTA - Casa de 4 dormitorios -
            # Roldan.» y el meta sigue con la descripcion.
            descripcion = meta
        descripcion_de_meta = False
        if not descripcion:
            descripcion = meta
            descripcion_de_meta = bool(meta)

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
            # «$990,000 / DOLARES» (`ente`, tema Houzez): el signo es el
            # generico y la moneda viene DETRAS de la cifra.
            # «U$ 45.000» y «U$$ 75.000» tambien son dolares (`marcelo zanni`,
            # `kerlin`): sin la alternativa, el patron salteaba la U y leia
            # «$ 45.000» como pesos. Un dolar publicado como peso.
            m = re.search(r"(USD|U\$[SD]|U\$\$?|US\$|\$|ARS)\s*([\d][\d.,]{2,15})"
                          r"(\s*/?\s*(?:d[oó]lares|usd)\b)?",
                          texto, re.I)
            if m:
                visible = a_numero(m.group(2))
                # La moneda de otra cifra (expensas, otra unidad) no puede
                # completar un precio estructurado. Se exige concordancia.
                if precio is None or visible == a_numero(precio):
                    moneda = moneda or ("USD" if m.group(3) else _moneda_del_signo(m.group(1)))
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
            m = (RE_COORD_ES.search(html) or RE_COORD.search(html)
                 or RE_COORD_ARREGLO.search(html))
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
                               # El par rotulado «Tipo Propiedad | Venta Oficina /
                               # Local» (`gonzalez theyler`) manda sobre el arranque
                               # del texto, que ahi es el menu («Casa Departamento…»).
                               # Y el rotulo solo, «<p>Tipo</p> <span>Departamento
                               # </span>» (`piccardo`, 19 fichas sin tipo).
                               or detectar_tipo(self._par_rotulado(
                                   principal_campos,
                                   r"Tipo(?:(?:\s+de)?\s+(?:propiedad|inmueble))?") or "")
                               # Y «Categoría | PH» (Kiteprop, `linkasa`). Solo
                               # cuenta si el valor ES un tipo: «Categoría |
                               # Premium» no afirma nada.
                               or detectar_tipo(self._par_rotulado(
                                   principal_campos,
                                   r"Categor(?:\u00ed|i|&iacute;)a") or "")
                               # Houzez: <li><strong>Tipo de propiedad:</strong>
                               # Departamento</li> (`nexo`).
                               or detectar_tipo(self._rotulo_en_linea(
                                   principal_campos,
                                   r"Tipo(?:\s+de)?\s+(?:propiedad|inmueble)") or "")
                               # En un emprendimiento el arranque del texto es
                               # el menu y las tipologias de sus unidades.
                               or (None if es_emprendimiento else (
                                   detectar_tipo(texto_campos[:300])
                                   or self._tipo_en_la_ficha(principal)))),
            "dormitorios": None if es_emprendimiento else (
                self._cuenta_de_ficha(principal, texto_campos,
                                      ETIQUETAS_DE_CONTEO["dormitorios"],
                                      datos.get("dorm"))
                or self._dormitorios_del_titulo(titulo)),
            "banos": None if es_emprendimiento else self._cuenta_de_ficha(
                principal, texto_campos, ETIQUETAS_DE_CONTEO["banos"], datos.get("banos")),
            "ambientes": None if es_emprendimiento else (
                self._cuenta_de_ficha(principal, texto_campos,
                                      ETIQUETAS_DE_CONTEO["ambientes"],
                                      datos.get("ambientes"))
                or self._ambientes_del_titulo(titulo)),
            "superficie_total": (mapaprop.get("superficie_total")
                                 or datos.get("sup_total")
                                 or self._sup(texto_campos, ETIQUETA_SUP_TOTAL)),
            "superficie_cubierta": (mapaprop.get("superficie_cubierta")
                                    or datos.get("sup_cubierta")
                                    or self._sup(texto_campos, ETIQUETA_SUP_CUBIERTA)),
        }
        # La aritmetica de inmuebles vive en un modulo aparte: la comparten el
        # connector y la correccion de lo ya extraido, y asi no pueden divergir.
        fuera = revisar(campos)
        if (datos.get("geo_fuera_de_argentina") and campos.get("latitud") is None
                and "coordenada_fuera_de_argentina" not in fuera):
            fuera.append("coordenada_fuera_de_argentina")
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
            # «+5 Dormitorios» (`esnal`, un terreno con casa vieja) es una cota
            # inferior, no un valor: no se afirma, y se dice que se rechazo.
            elif (campos.get(nombre) is None
                    and re.search(rf"\+\s*\d{{1,2}}\s*(?:{etiqueta})\b",
                                  texto_campos or "", re.I)):
                fuera.append(f"{nombre}:cota_inferior")
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
        # Estatik (plugin de WordPress) nombra cada campo en la clase: <li
        # class="es-property-field--es_neighborhood"><span …label>Barrios<span
        # …sep>:</span></span><span …value><a rel="tag">Liniers</a></span></li>
        # (`bauer`: barrio en 0 de 9 fichas que lo publican). El rotulo en
        # plural y con el separador anidado no lo lee `_par_rotulado`; la clase
        # dice que campo es sin depender del idioma del rotulo.
        barrio_par = barrio_par or self._campo_estatik(principal, "es_neighborhood")
        ciudad_par = ciudad_par or self._campo_estatik(principal, "es_city|city")
        provincia_par = provincia_par or self._campo_estatik(
            principal, "es_state|es_province|province|state")
        # Houzez nombra la fila en la clase: <li class="detail-state"><strong>
        # Provincia/País</strong> <span>Buenos Aires</span></li> (`balsa`: 8 de
        # 58 fichas sin provincia). El rotulo compuesto «Provincia/País» no lo
        # lee `_par_rotulado`; la clase dice que campo es.
        ciudad_par = ciudad_par or self._campo_houzez(principal, "city")
        # «Estado» en Houzez es lo que la agencia cargo en ese campo, y
        # `inmobiliaria leal` carga ahi el departamento («Guaymallen»): solo
        # cuenta si ES una provincia.
        estado_houzez = self._campo_houzez(principal, "state")
        if estado_houzez and _es_provincia(estado_houzez):
            provincia_par = provincia_par or estado_houzez
        # Ciudad y provincia en su propio rotulo: «City/Town | Rosario»,
        # «Province/State | Santa Fe» (`ingar`, 21 de 26 sin barrio y 5 sin
        # ciudad). La geografia compartida los valida despues.
        ciudad_par = ciudad_par or self._par_rotulado(
            principal, r"city\s*/\s*town|ciudad|localidad")
        provincia_par = provincia_par or self._par_rotulado(
            principal, r"province\s*/\s*state|provincia")
        # Y el rotulo con su valor en el MISMO elemento: `cip` publica
        # <li class="prop-overview__item"> Localidad: Los Molles </li>
        # <li …> Provincia: San Luis </li> y las 163 fichas quedaban sin
        # provincia ni ciudad.
        ciudad_par = ciudad_par or self._rotulo_en_linea(principal, r"localidad|ciudad")
        provincia_par = provincia_par or self._rotulo_en_linea(principal, r"provincia")
        # La direccion completa que termina en «…, Oberá, Misiones» (`daniel`,
        # 12 fichas sin ciudad): si el ULTIMO tramo es una provincia, el
        # anterior es la ciudad que la ficha escribe. La geografia compartida
        # la valida despues; lo que no resuelve no se afirma.
        linea = None
        if not (ciudad_par and provincia_par) and not (datos.get("ciudad") or mapaprop.get("ciudad")):
            linea = self._linea_de_ubicacion(principal) or self._ubicacion_wix(html)
        if linea:
            # Fuera «Argentina» al final y el codigo postal delante de la
            # ciudad («B7602FKK Mar del Plata»): la cadena geocodificada de
            # Google repite «…, Mar Del Plata, Buenos Aires, Argentina.».
            tramos_l = [x.strip(" .") for x in re.split(r",|\s[-|]\s", linea) if x.strip(" .")]
            while tramos_l and re.fullmatch(r"(?i)rep(?:u|ú)blica\s+argentina|argentina", tramos_l[-1]):
                tramos_l.pop()
            tramos_l = [re.sub(r"^[A-Z]\d{4}[A-Z]{3}\s+|^\(?\d{4}\)?\s+", "", t) for t in tramos_l]
            # Houzez geocodifica «Pampa y Cabildo, La Pampa, Belgrano, Buenos
            # Aires, Comuna 13, Ciudad Autónoma de Buenos Aires, C1428CPD,
            # Argentina» (`de giorgio`): el codigo postal y la comuna sueltos no
            # son tramos de lugar, y con ellos al final la provincia no se veia.
            tramos_l = [t for t in tramos_l
                        if not re.fullmatch(r"(?i)[A-Z]\d{4}[A-Z]{3}|\(?\d{4}\)?|CP\s*\d{4}|comuna\s+\d{1,2}", t)]
            while tramos_l and re.fullmatch(r"(?i)rep(?:u|ú)blica\s+argentina|argentina", tramos_l[-1]):
                tramos_l.pop()
            if not direccion and tramos_l and re.search(r"\d", tramos_l[0]) and len(tramos_l[0]) <= 80:
                direccion = tramos_l[0]
            if len(tramos_l) >= 2 and _es_provincia(tramos_l[-1]):
                previo = tramos_l[-2]
                if not re.search(r"\d", previo) and len(previo) <= 40:
                    ciudad_par = ciudad_par or previo
                    provincia_par = provincia_par or tramos_l[-1]
            elif (len(tramos_l) >= 2 and re.search(r"\d", tramos_l[0])
                  and not re.search(r"\d", tramos_l[1]) and len(tramos_l[1]) <= 40):
                # «Santa Marina 538 - Monte Grande», «Av Int Zobboli 1604,
                # Rafaela - Luis Fasoli»: calle y altura, despues la ciudad. La
                # geografia compartida la valida; un barrio que no es localidad
                # no se afirma como ciudad.
                ciudad_par = ciudad_par or tramos_l[1]
        # El CRM TIV Tecnogestion (`caian` 44, `benitez ullo` 13…: 75 fichas
        # sin ciudad) no escribe la ubicacion en el cuerpo: la da su og:title
        # «Departamento en Venta. Almagro, Capital Federal, Buenos Aires» y la
        # calle su og:description «… ubicado sobre la calle Billinghurst 200
        # en Almagro, …». Solo con la firma del CRM y la forma exacta.
        if not (ciudad_par and provincia_par):
            tiv = self._ubicacion_tiv(html)
            if tiv:
                barrio_par = barrio_par or tiv[0]
                ciudad_par = ciudad_par or tiv[1]
                provincia_par = provincia_par or tiv[2]
                direccion = direccion or tiv[3]
        if direccion and not (ciudad_par and provincia_par):
            tramos = [x.strip(" .") for x in re.split(r",|\.\s", direccion) if x.strip(" .")]
            if (len(tramos) >= 3 and _es_provincia(tramos[-1])
                    and not re.search(r"\d", tramos[-2]) and len(tramos[-2]) <= 40):
                ciudad_par = ciudad_par or tramos[-2]
                provincia_par = provincia_par or tramos[-1]
        # Ultimo recurso: el titulo convencional «Departamento en Venta en
        # Centro, Mar del Plata - U$S 179.000» (Inmobiliatica: `lazzaro` 118,
        # `ballarre` 258 con «… :: Inmobiliaria Ballarre», `castro y compania`,
        # `insabella`...: 930 fichas sin ciudad el 28-09). Es la ubicacion que la
        # propia ficha escribe; la geografia compartida la valida despues y lo
        # que no resuelve no se afirma. Solo si ningun otro camino dio ciudad.
        ubicacion_titulo = _ubicacion_del_titulo(titulo)
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
        # Un GIF junto a fotos JPG/PNG/WEBP es un banner: `innoa` rota
        # /ac/b/4.gif, /ac/b/728-innoa.gif… en cada carga y la agencia quedaba
        # no idempotente. Medido 27-09 sobre todas las fichas certificadas: solo
        # innoa guardaba GIFs, y ninguna ficha tenia SOLO GIFs.
        if any(not RE_GIF.search(i) for i in imagenes):
            imagenes = [i for i in imagenes if not RE_GIF.search(i)]
        propiedad = PropiedadNormalizada(
            canonical_agency_id=fuente.canonical_agency_id,
            source_listing_id=str(crudo["source_listing_id"]),
            source_url=url,
            connector=self.nombre,
            titulo=titulo,
            # «627 Visitas al momento» al final de la descripcion (`ferrari`,
            # `bottega`, `diaz collins`: 173 fichas) es un contador que nuestra
            # propia visita incrementa: con el, la segunda corrida nunca es
            # igual a la primera. No describe a la propiedad.
            # Y una url con un token cifrado por pedido: `julian zaparart`
            # (Kiteprop) mete en la descripcion https://www.kiteprop.com/maps/
            # view/eyJpdiI6…, distinto en cada carga. `eyJ` es un JSON en
            # base64 (`{"iv":…`): firmado o cifrado para ESE pedido, no prosa.
            descripcion=(RE_URL_CON_TOKEN.sub("", re.sub(
                r"\s*\b\d[\d.,]*\s+visitas\s+al\s+momento\s*$", "",
                descripcion or "", flags=re.I)).strip()[:4000] or None),
            precio=precio,
            moneda=moneda,
            operacion=campos["operacion"],
            tipo_propiedad=campos["tipo_propiedad"],
            direccion=direccion,
            barrio=(mapaprop.get("barrio") or datos.get("barrio") or barrio_par
                    or (None if (mapaprop.get("ciudad") or datos.get("ciudad") or ciudad_par)
                        else ubicacion_titulo[0])),
            ciudad=(mapaprop.get("ciudad") or datos.get("ciudad") or ciudad_par
                    or ubicacion_titulo[1]),
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
        # El eslogan del meta no rescata un cascaron. `d amato` sirve con 200
        # la plantilla vacia de una ficha dada de baja -titulo «Propiedad |
        # D'Amato Propiedades», sin precio ni fotos- y el meta del sitio («Mas
        # de 35 años comprando, vendiendo…») era lo unico «publicado»: con eso
        # `ficha_sin_contenido` la dejaba pasar y se guardaba un departamento
        # adivinado del slug. Sin esa descripcion, el guardian decide como
        # siempre; una ficha real con titulo propio no cambia.
        if descripcion_de_meta:
            sin_meta = dataclasses.replace(propiedad, descripcion=None)
            if ficha_sin_contenido(sin_meta):
                return sin_meta
        return propiedad

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

    def _normalizar_strapi(self, crudo: dict,
                           fuente: Fuente) -> PropiedadNormalizada | None:
        """Arma la propiedad con el objeto Strapi que ya trajo el listado.

        Las claves son las del modelo del sitio (`Titulo`, `Tipo_de_operacion`,
        `valor_dolares`, `Ambientes: «c 3 ambientes»`...) y se buscan sin
        distinguir mayusculas. Nada se inventa: «c 5 o más dormitorios» es una
        cota y queda vacia; `Lote` («7.50 x 47») es una medida, no una
        superficie; la coordenada es el centro del mapa embebido de la ficha
        (el `!2d<lon>!3d<lat>` del iframe de Google Maps que publica el sitio).
        """
        objeto = crudo.get("strapi_objeto") or {}
        if not objeto:
            return None
        claves = {str(k).lower(): k for k in objeto}

        def valor(*nombres: str) -> Any:
            for nombre in nombres:
                clave = claves.get(nombre.lower())
                if clave is not None and objeto.get(clave) not in (None, ""):
                    return objeto.get(clave)
            return None

        def texto(*nombres: str) -> str | None:
            v = valor(*nombres)
            v = limpiar(str(v)) if v is not None else None
            return v or None

        def conteo(*nombres: str) -> int | None:
            v = texto(*nombres)
            if not v or re.search(r"\bo\s+m[aá]s\b|\+", v, re.I):
                return None
            m = re.search(r"\b(\d{1,2})\b", v)
            return _entero(m.group(1)) if m else None

        precio = moneda = None
        dolares, pesos = valor("valor_dolares", "precio_dolares"), valor("valor_pesos", "precio_pesos")
        ref = valor("precio_ref")
        if dolares not in (None, ""):
            precio, moneda = a_numero(str(dolares)), "USD"
        elif pesos not in (None, ""):
            precio, moneda = a_numero(str(pesos)), "ARS"
        elif isinstance(ref, dict) and ref.get("mostrar") and ref.get("valor") not in (None, ""):
            # Strapi v3 (`paladino`): {valor, moneda: {nombre: "USD" | "ARS Pesos"},
            # mostrar}. Con `mostrar` falso el sitio no publica el precio.
            divisa = ref.get("moneda") if isinstance(ref.get("moneda"), dict) else {}
            nombre = str(divisa.get("nombre") or "").upper()
            moneda = "USD" if ("USD" in nombre or "U$S" in nombre) else ("ARS" if "ARS" in nombre else None)
            precio = a_numero(str(ref.get("valor"))) if moneda else None
        if not precio:
            precio = moneda = None

        lat, lon = _coordenada(valor("latitud")), _coordenada(valor("longitud"))
        mapa = None if (lat is not None and lon is not None) else re.search(r"!2d(-?\d+\.\d+)!3d(-?\d+\.\d+)", str(valor("coordenadas", "mapa") or ""))
        if mapa:
            lon, lat = _coordenada(mapa.group(1)), _coordenada(mapa.group(2))

        imagenes = []
        for foto in ((valor("Imagen", "imagenes", "fotos") or {}).get("data") or []
                     if isinstance(valor("Imagen", "imagenes", "fotos"), dict) else []):
            url = ((foto or {}).get("attributes") or {}).get("url")
            if isinstance(url, str) and url.startswith("http"):
                imagenes.append(url)
        # v3: `imagen` y `galeria` con url relativa al host de la API.
        base_v3 = crudo.get("strapi_v3_base")
        if base_v3:
            portada = valor("imagen")
            for foto in ([portada] if isinstance(portada, dict) else []) + list(valor("galeria") or []):
                ruta = foto.get("url") if isinstance(foto, dict) else None
                if isinstance(ruta, str) and ruta:
                    completa = ruta if ruta.startswith("http") else base_v3 + ruta
                    if completa not in imagenes:
                        imagenes.append(completa)
        zona, estado = valor("catalogo_de_zona"), valor("estado")

        return PropiedadNormalizada(
            canonical_agency_id=fuente.canonical_agency_id,
            source_listing_id=str(crudo["source_listing_id"]),
            source_url=crudo["source_url"],
            connector="generico",
            inmobiliaria_id=fuente.inmobiliaria_id,
            titulo=texto("Titulo", "title", "nombre"),
            descripcion=texto("descripcion", "description"),
            operacion=detectar_operacion(texto("Tipo_de_operacion", "operacion") or ""),
            tipo_propiedad=detectar_tipo(texto("tipo_de_inmueble", "tipo", "tipo_inmueble", "tipos") or ""),
            precio=precio,
            moneda=moneda,
            direccion=texto("Direccion", "direccion"),
            ciudad=texto("Localidades", "localidad", "ciudad"),
            barrio=(limpiar(str(zona["nombre"])) or None) if isinstance(zona, dict) and zona.get("nombre") else None,
            latitud=lat,
            longitud=lon,
            ambientes=conteo("Ambientes"),
            dormitorios=conteo("Dormitorios", "habitaciones"),
            banos=conteo("Banos", "baños"),
            superficie_total=_decimal(valor("metros_totales2", "metros_totales", "superficie_total")),
            superficie_cubierta=_decimal(valor("m2_cubiertos", "superficie_cubierta")),
            imagenes=imagenes,
            extra={"strapi": True, **({"coordenada_de": "mapa embebido de la ficha"} if mapa else {}),
                   **({"strapi_version": 3} if base_v3 else {}),
                   **({"estado_fuente": str(estado["nombre"]).strip().lower()}
                      if isinstance(estado, dict) and estado.get("nombre") else {})},
        )

    def _ficha_xintel_embebida(self, html: str) -> str:
        """La ficha con los parametros del detalle, siguiendo el iframe Amaira.

        `battista` (480 propiedades) publica cada ficha como un marco vacio
        con `<iframe src="https://ficha.amaira.com.ar/nue/ficha.php?ficha=
        bat2953...">`: los parametros estan en el iframe y no en la pagina, y
        las 480 fallaban con «la ficha Xintel no trae los parametros del
        detalle». Si el iframe no los trae tampoco, sigue fallando igual.
        """
        if self._es_ficha_xintel(html):
            return html
        marco = RE_IFRAME_AMAIRA.search(html or "")
        if not marco:
            return html
        embebida = self.descargador.bajar(unescape(marco.group(1)))
        return embebida if self._es_ficha_xintel(embebida) else html

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
        cliente = getattr(self, "_xintel_cliente", None)
        if all(detail_params.values()):
            query = urllib.parse.urlencode({
                "json": "fichas.propiedades",
                "suc": detail_params["suc"],
                "global": detail_params["global"],
                "apiK": detail_params["apiK"],
                "id": detail_params["id"],
                "compartida": "false",
            })
        elif cliente and str(row.get("in_num") or "").strip():
            # La ficha la arma el JavaScript propio del sitio (`aloise`) y no
            # publica esos parametros: se hace la MISMA llamada que su frontend
            # (`fichas.propiedades` con su `inm`, su `apiK` y el numero de ficha).
            # Nunca con `global` ni con credenciales de otro sitio.
            query = urllib.parse.urlencode({
                "json": "fichas.propiedades", "inm": cliente[0], "apiK": cliente[1],
                "id": str(row.get("in_num")).strip()})
        else:
            raise ErrorTransitorio("la ficha Xintel no trae los parametros del detalle")
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
        # Y el fondo CSS, que el parrafo de arriba nombraba y nadie leia:
        # `guillermo rodriguez` publica su galeria solo como
        # <div class="item" style="background-image: url(resource2.php/…jpg)">
        # y sus 240 fichas se descartaban por forma con el logo y un sello
        # como unicas «fotos».
        crudos = [m.group(1) or m.group(2) for m in RE_ENLACE_A_FOTO.finditer(html or "")]
        crudos += [m.group(2) for m in RE_FONDO_CSS.finditer(html or "")]
        for crudo in crudos:
            u = _url_del_atributo(crudo or "")
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
    def _ubicacion_wix(html: str) -> str | None:
        """La direccion formateada que una pagina dinamica de Wix renderiza.

        Wix (CMS «Properties», `lucas liprandi`) no publica la ubicacion con
        rotulo ni icono: el campo `address` de la coleccion se renderiza como
        texto suelto, «Ascochinga, Córdoba, Argentina», en uno de los
        componentes de `wix-warmup-data` (ssrPropsUpdates). Se acepta solo esa
        forma -tramos sin cifras que terminan en «<provincia>, Argentina»- y
        solo si todos los componentes que la tienen dicen LO MISMO (la
        etiqueta del mapa repite la del encabezado). Dos ubicaciones distintas
        en la pagina: no se afirma ninguna.
        """
        m = re.search(r'<script[^>]*id="wix-warmup-data"[^>]*>(.*?)</script>', html or "", re.S)
        if not m:
            return None
        try:
            datos = json.loads(m.group(1))
        except ValueError:
            return None
        vistas = set()
        for tanda in ((datos.get("platform") or {}).get("ssrPropsUpdates") or []):
            for comp in (tanda or {}).values():
                bruto = (comp or {}).get("html") if isinstance(comp, dict) else None
                if not isinstance(bruto, str):
                    continue
                texto = limpiar(re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", bruto))))
                tramos = [t.strip() for t in (texto or "").split(",")]
                if (2 <= len(tramos) <= 4 and tramos[-1].casefold() == "argentina"
                        and _es_provincia(tramos[-2])
                        and not any(re.search(r"\d", t) for t in tramos)):
                    vistas.add(texto)
        return vistas.pop() if len(vistas) == 1 else None

    @staticmethod
    def _linea_de_ubicacion(html: str) -> str | None:
        """La ubicacion que la ficha escribe junto a un icono de mapa.

        Medido 2026-10-01 (LOCAL): 1.112 fichas de 48 agencias sin ciudad, y
        en muchas la ubicacion esta publicada asi: `martelliti` (Pixel
        Inmobiliario) <p><i class="fa fa-map-marker"></i> Laprida 1835,
        B7602FKK Mar del Plata, Provincia de Buenos Aires, Argentina, ...</p>,
        `alfa`/`franco` <span class="ficha__location-icon">, `abate`
        flaticon-pin, `b b` fa-map-marker-alt, `azara`, `zamorano`.

        La trampa es la OFICINA, que usa el mismo icono: en el pie
        (`martelliti`), en la cabecera (`agostina saracena`), en el bloque de
        contacto (`b b`: «Lavalle 388, Rafaela, Santa Fe»), o como «Sucursal
        Tigre» (`a campos`). Por eso: solo el cuerpo de la ficha, nada dentro
        de header/nav/footer, tarjetas de otras fichas, contacto o agente;
        nunca una linea que tambien este en el pie, ni una que diga sucursal u
        oficina. Se toma la PRIMERA que queda.
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:  # pragma: no cover
            return None
        cuerpo = html or ""
        pie = cuerpo[len(cuerpo_principal(cuerpo)):]
        sopa = BeautifulSoup(cuerpo_principal(cuerpo), "html.parser")
        for basura in sopa(["script", "style", "noscript", "header", "nav", "footer"]):
            basura.decompose()
        icono = re.compile(r"(?:^|[\s_-])(?:fa-map-marker(?:-alt)?|fa-location-dot|fa-map-marked(?:-alt)?|"
                           r"flaticon-pin|location-icon|icon-location|lucide-map-pin|map-pin|icon-pin)(?:$|[\s_-])", re.I)
        ajeno = re.compile(r"card|related|similar|relacionad|contact|agent|asesor|footer|header|"
                           r"navbar|menu|sucursal|oficina|office|widget|sidebar", re.I)
        plano_pie = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", pie)))
        for nodo in sopa.find_all(True, class_=icono):
            if any(ajeno.search(" ".join(a.get("class") or []) + " " + (a.get("id") or ""))
                   for a in nodo.parents if getattr(a, "attrs", None) is not None):
                continue
            # La oficina suele ser un ENLACE (a Google Maps, tel:, wa.me): en
            # `agostina saracena` la barra superior es <a href="maps.app.goo.gl/…">
            # con el mismo icono, y su plantilla no usa <header>. La ubicacion
            # de una ficha no se enlaza.
            if nodo.find_parent("a", href=True) is not None:
                continue
            contenedor = nodo.parent
            texto = re.sub(r"\s+", " ", contenedor.get_text(" ", strip=True) if contenedor else "")
            if len(texto) < 6 and contenedor is not None and contenedor.parent is not None:
                contenedor = contenedor.parent
                texto = re.sub(r"\s+", " ", contenedor.get_text(" ", strip=True))
            texto = texto.strip(" .|-")
            if not (4 <= len(texto) <= 160):
                continue
            if re.search(r"\b(?:sucursal|oficina|casa\s+central|ver\s+mapa|ubicaci[oó]n\s+aproximada)\b",
                         texto, re.I):
                continue
            if texto in plano_pie:
                continue
            return limpiar(texto)
        return None

    @staticmethod
    def _par_rotulado(html: str, etiqueta: str) -> str | None:
        """El valor de un par rotulo/valor: <p>Dirección</p><p>Av. Rosales 515</p>.

        Solo la estructura -rotulo solo en su elemento, valor en el siguiente
        y sin marcado adentro-: el texto aplanado no dice donde termina el
        valor. `bardi` publica asi direccion y barrio en sus 90 fichas.
        """
        m = re.search(
            # El rotulo en negrita DENTRO de su celda: Synapsis publica
            # <p><strong>Localidad:</strong></p><p>Don Torcuato</p> (`aranoa`:
            # localidad y provincia en 0 de 34 fichas).
            rf"<(p|span|dt|th|td|div|label|strong|h[1-6])\b[^>]*>\s*(?:<(?:strong|b)\b[^>]*>\s*)?(?:{etiqueta})\s*:?\s*"
            rf"(?:</(?:strong|b)>\s*)?"
            # El valor puede ser el enlace a su taxonomia: <span><a rel="tag">
            # Centro</a></span> (tema ERE de WordPress, `ingar`).
            # Con el mismo cierre intermedio que tolera `_cuenta_de_ficha`
            # (`daniel`: <strong>Dirección</strong></span><span …value>).
            rf"</\1>\s*(?:</(?:span|div)>\s*)?<(p|span|dd|td|div)\b[^>]*>\s*(?:<a\b[^>]*>\s*)?"
            rf"([^<>]{{2,150}}?)\s*(?:</a>\s*)?</\2>",
            html or "", re.I)
        return limpiar(unescape(m.group(3))) if m else None

    @staticmethod
    def _ubicacion_tiv(html: str) -> tuple[str | None, str | None, str | None, str | None] | None:
        """(barrio, ciudad, provincia, calle) del og:title de una ficha de TIV Tecnogestion."""
        if not re.search(r"cdn\.tecnogestion\.com\.ar|CRM Inmobiliario TIV", html or "", re.I):
            return None
        m = re.search(r'<meta[^>]+property="og:title"[^>]+content="[^".]{3,60} en '
                      r'(?:venta|alquiler|alquiler temporario)\.\s*([^".]{3,120})"', html or "", re.I)
        if not m:
            return None
        tramos = [t.strip() for t in unescape(m.group(1)).split(",") if t.strip()]
        if len(tramos) != 3 or not _es_provincia(tramos[2]) or any(re.search(r"\d", t) for t in tramos):
            return None
        calle = re.search(r'<meta[^>]+property="og:description"[^>]+content="[^"]*?'
                          r'ubicado sobre la calle ([^",]{3,80}?\d{1,5}) en ', html or "", re.I)
        barrio = None if tramos[0].casefold() == tramos[1].casefold() else tramos[0]
        return (barrio, tramos[1], tramos[2], limpiar(unescape(calle.group(1))) if calle else None)

    @staticmethod
    def _campo_houzez(html: str, campo: str) -> str | None:
        """El valor de una fila de detalle de Houzez: <li class="detail-<campo>">.

        Rotulo en <strong>, valor solo en el <span> siguiente, dentro del mismo
        <li> y sin marcado adentro.
        """
        m = re.search(
            rf"<li\b[^>]*class=[\"'](?:[^\"']*\s)?detail-(?:{campo})[\s\"'][^>]*>\s*"
            rf"<strong\b[^>]*>[^<]{{1,40}}</strong>\s*<span\b[^>]*>\s*([^<>]{{2,60}}?)\s*</span>\s*</li>",
            html or "", re.I)
        return limpiar(unescape(m.group(1))) if m else None

    @staticmethod
    def _campo_estatik(html: str, campo: str) -> str | None:
        """El valor visible de un campo de Estatik: <li class="es-property-field--<campo>">.

        Solo dentro del mismo <li> y con tope de largo: un valor largo no es un
        barrio ni una ciudad. La geografia compartida lo valida despues.
        """
        m = re.search(
            rf"<li\b[^>]*class=[\"'][^\"']*\bes-property-field--(?:{campo})[\s\"'][^>]*>"
            rf"(?:(?!</li>).){{0,400}}?"
            rf"<span\b[^>]*class=[\"'][^\"']*\bes-property-field__value\b[^\"']*[\"'][^>]*>"
            rf"((?:(?!</li>).){{0,300}}?)</span>\s*</li>", html or "", re.I | re.S)
        if not m:
            return None
        visible = limpiar(unescape(re.sub(r"<[^>]+>", " ", m.group(1))))
        return visible if visible and len(visible) <= 60 else None

    @staticmethod
    def _rotulo_en_linea(html: str, etiqueta: str) -> str | None:
        """«<li>Provincia: San Luis</li>»: rotulo, dos puntos y valor solos en su elemento.

        El elemento tiene que contener SOLO eso -sin marcado adentro del valor
        y con tope de largo-: una oracion de la descripcion que empiece con
        «Ciudad:» no es un par.
        """
        # Tambien con el rotulo en negrita, como lo escribe Houzez:
        # <li class="prop_type"><strong>Tipo de propiedad:</strong> Departamento</li>
        # (`nexo`: 33 de 40 fichas sin tipo).
        m = re.search(
            rf"<(li|p|span|div|td|dd)\b[^>]*>\s*(?:<(strong|b)\b[^>]*>\s*)?(?:{etiqueta})\s*:\s*"
            rf"(?:</(?:strong|b)>\s*)?([^<>:]{{2,60}}?)\s*</\1>",
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
        # Sin og:title ni h1, el titulo de la ficha puede ser su primer h2-h4:
        # `candoli` tiene <title> = «Candoli Propiedades» y el h2 «Complejo
        # turistico en venta a metros del mar, Camet Norte». Solo si el h2
        # nombra una operacion o un tipo y no es un encabezado de seccion.
        if not re.search(r'property="og:title"|<h1\b', html, re.I):
            # El cierre puede ser de OTRO nivel: la plantilla Oestesi/Argencasas
            # (`david rodriguez`) abre `<h2>` y cierra `</h1>`, y la ficha quedaba
            # titulada con el <title> del sitio.
            for m in re.finditer(r"<h([2-4])[^>]*>(.{3,2000}?)</h[1-6]>", html, re.S | re.I):
                visible = limpiar(unescape(re.sub(r"<[^>]+>", " ", m.group(2)))) or ""
                if (20 <= len(visible) <= 200
                        and not re.match(r"(?i)(?:propiedades|inmuebles|ultimas|[uú]ltimas|"
                                         r"destacad|similares|otras|busc)", visible)
                        and (detectar_operacion(visible) or detectar_tipo(visible))):
                    candidatos.insert(len(candidatos) - 1 if len(candidatos) > 1 else 1,
                                      visible)
                    break

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
        tramos = [plano(t) for t in re.split(r"\s*[|–—-]\s*", titulo or "") if t.strip()]
        if not nombre or not tramos:
            return False
        if tramos[0] == nombre:
            return True
        # El nombre repartido entre tramos: «Inmobiliaria | Guillermo
        # Rodriguez» es el sitio de «Guillermo Rodriguez Inmobiliaria», y sus
        # categorias (`propiedades.php?tipo=25`, 31 fichas enlazadas) se
        # guardaban como propiedades con el precio de la primera tarjeta.
        # Mismas palabras, ni una mas: un titulo que agrega algo es una ficha.
        return set(" ".join(tramos).split()) == set(nombre.split())

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
        # O en la query, como `?id=343`: `chambouleyron` pone de <h1> la seccion
        # -«DEPARTAMENTOS», «CASAS»- sobre cada ficha `product.php?id=N` con 5
        # vecinas debajo, y 7 de 16 fichas reales iban a revision. Una pagina
        # de listado con nombre de listado (`propiedades.php?id=2`) sigue siendo
        # categoria.
        if url and _id_de_ficha_en_la_query(url):
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
        # Y la categoria titulada con la OPERACION sola: `ana de napoli`
        # (Next.js) tiene /venta, /alquiler y /alquiler-temporario con <h1>
        # «Alquiler Temporario» y las tarjetas debajo; la de temporario se
        # guardaba como ficha con el precio y el tipo de su primera tarjeta
        # (2026-10-01). Mismo umbral: sin id en la ruta y 5 o mas fichas.
        operaciones = (r"(?:en\s+)?(?:ventas?|alquiler(?:es)?(?:\s+(?:temporari[oa]s?|temporal(?:es)?|"
                       r"anual(?:es)?|comercial(?:es)?))?|temporari[oa]s?)")
        if re.fullmatch(operaciones, plano):
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
        t = texto or ""
        # `og:type=article` SOLO (sin schema Article/BlogPosting) no veta una
        # pagina que publica un inmueble con todas las letras: `gandino
        # galetto` lo declara en sus 12 fichas -«Casa en venta Ambrosetti
        # 300», USD 130.000, 14 fotos- y quedaba en cero. Una nota de blog no
        # trae precio con moneda, operacion Y tres fotos a la vez.
        solo_og_article = bool(RE_EDITORIAL.search(html or "")) and not re.search(
            r'"@type"\s*:\s*"?(?:Article|NewsArticle|BlogPosting)', html or "", re.I)
        con_todo = (precio is not None and bool(RE_PRECIO_CON_MONEDA.search(t))
                    and bool(RE_OPERACION_TXT.search(t))
                    and len(imagenes) >= FOTOS_MINIMAS)
        if (RE_EDITORIAL.search(html or "") and not catalogo_verificado
                and not (solo_og_article and con_todo)):
            return False
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
        # Un schema.org con precio con moneda y operacion es una ficha aunque
        # la galeria la cargue un script: `benitez` publica una sola foto en
        # el HTML (la del JSON-LD `Product`) y perdia 7 de 8 fichas reales.
        if (not fotos_suficientes and tipo_ld and imagenes and precio is not None
                and RE_PRECIO_CON_MONEDA.search(t) and RE_OPERACION_TXT.search(t)):
            fotos_suficientes = True
        # Sin schema, dos fotos con precio con moneda y operacion tambien:
        # `martinez quiles` publica un galpon en alquiler, $ 5.200.000, con 2
        # fotos, y era la unica ficha descartada de la agencia (paro 08:3x).
        # Una pagina institucional no trae precio con moneda Y operacion.
        if (not fotos_suficientes and len(imagenes) >= 2 and precio is not None
                and RE_PRECIO_CON_MONEDA.search(t) and RE_OPERACION_TXT.search(t)):
            fotos_suficientes = True
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
        places_propios: list[tuple[int, str, dict]] = []
        for bloque in RE_LD.findall(html):
            dato = json_ld_tolerante(bloque)
            if dato is None:
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
                # Salvo que el Place SEA esta ficha: Houzez publica la ficha
                # como {"@type": "Place", "url": <esta pagina>, "geo": …,
                # "address": …} (`de giorgio`: coordenadas y localidad en
                # todas sus fichas, ninguna leida). La url propia es lo que
                # lo distingue del Place de la oficina.
                #
                # Y solo si la pagina no trae un nodo de inmueble concreto: la
                # plantilla de BuscadorProp (`cocciolo`, `partarrieu`) pone un
                # Place con la url propia DENTRO de su BreadcrumbList, al lado del
                # RealEstateListing de verdad, y sumarlo le cambiaba a una venta
                # de USD 350.000 el precio por el del alquiler, 1.800 dolares.
                if tipo == "Place" and not nodo.get("offers"):
                    if not (url and any(
                            isinstance(nodo.get(k), str)
                            and urllib.parse.urldefrag(urllib.parse.urljoin(url, nodo[k]))[0].rstrip("/")
                            == urllib.parse.urldefrag(url)[0].rstrip("/")
                            for k in ("url", "@id"))):
                        continue
                    places_propios.append((prioridad, tipo, nodo))
                    continue
                candidatos.append((prioridad, tipo, nodo))
        if places_propios and not any(c[0] == 0 for c in candidatos):
            candidatos.extend(places_propios)
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
                # Se anota: Houzez trae por defecto 25.68, -80.43 (Miami) en
                # las fichas sin mapa (`de giorgio`: 1 de 20), y sin rastro el
                # auditor lo contaba como coordenada no extraida en vez de
                # rechazada por la validacion.
                out["geo_fuera_de_argentina"] = True
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
            # como si fuera la cantidad de ambientes. Y la barra el «2» de
            # «1 1/2 AMB.» (`peirano`): el denominador no es una cantidad.
            hallazgo = re.search(
                rf"(?<![+/])\b([1-9]\d?)\s*(?:{etiqueta})", texto, re.I)
            if not hallazgo:
                return GenericoConnector._cuenta_en_letras(texto, etiqueta)
        if not hallazgo:
            return None
        valor = int(hallazgo.group(1))
        return valor if 1 <= valor <= 99 else None

    @staticmethod
    def _cuenta_en_letras(texto: str, etiqueta: str) -> int | None:
        """«cuatro dormitorios», «un baño»: la cantidad escrita con letras.

        Solo en prosa (la tabla de atributos no se escribe asi) y solo si NO
        hay ambiguedad, porque un conteo mal leido parece un dato real:
        - una UNICA mencion con letras de ese rotulo: «un baño en suite y un
          baño de servicio» son dos baños y no se afirma ninguno;
        - concordancia: «un» con el rotulo en singular, «dos» en plural. «Un
          ambientes» no es una cantidad;
        - sin cotas ni rangos delante: «mas de dos», «hasta tres», «dos y tres
          dormitorios» (un emprendimiento) no son la cantidad de ESTA ficha.
        """
        palabras = "|".join(NUMEROS_EN_LETRAS)
        texto = texto or ""
        # El rotulo tiene que aparecer UNA sola vez en toda la ficha. Medido
        # sobre el corpus (2026-10-01, 45 casos revisados a mano): «Dormitorio
        # principal en suite ... Dos dormitorios», «dos habitaciones
        # secundarias» o «P.B: dormitorio con baño ... P.A: dos dormitorios»
        # nombran una PARTE de los dormitorios, y la cuenta en letras quedaba
        # corta. Si el rotulo aparece en otro lado, no se afirma.
        if len(re.findall(rf"(?:{etiqueta})", texto, re.I)) != 1:
            return None
        validas = []
        for m in re.finditer(rf"(?<![\w+])({palabras})\s+((?:{etiqueta}))",
                             texto, re.I):
            valor = NUMEROS_EN_LETRAS[m.group(1).lower()]
            plural = m.group(2).lower().endswith("s")
            if (valor == 1) == plural:
                continue
            # «un ambiente acogedor», «generando un ambiente moderno»: en
            # singular «ambiente» es el clima del lugar, no un conteo (10 de 45
            # en la muestra). Un ambiente se publica como «monoambiente».
            if valor == 1 and re.match(r"ambiente", m.group(2), re.I):
                continue
            antes = texto[max(0, m.start() - 40):m.start()]
            despues = texto[m.end():m.end() + 30]
            if (re.search(r"(?:\bm[aá]s\s+de|\bhasta|\bentre|\bdesde)\s*$", antes, re.I)
                    or re.search(rf"(?:\b(?:{palabras})|\d)\s*(?:y|o|a|-|/)\s*(?:de\s+)?$", antes, re.I)
                    # Un piso o una unidad: «P.A: dos dormitorios», «semipisos de
                    # un dormitorio», «casitas de dos dormitorios cada una».
                    or re.search(r"(?:planta\s+(?:alta|baja)|\bp\.?\s?[ab]\b\.?|\bpiso\b|"
                                 r"semipisos?|unidades|departamentos|casitas|caba[nñ]as|"
                                 r"locales|monoambientes)[^.]{0,30}$", antes, re.I)
                    or re.search(r"^[^.]{0,20}\bcada\s+un[oa]\b", despues, re.I)
                    # «dos habitaciones secundarias»: hay otra (la principal).
                    or re.search(r"^\s*(?:secundari|adicional|extra|m[aá]s\b)", despues, re.I)):
                return None
            validas.append(valor)
        return validas[0] if len(validas) == 1 else None

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
        hallazgos = re.findall(r"(?<![\d+])\b([1-9])\s*amb(?:ientes?\b|\.|\b)",
                               titulo, re.I)
        if len(hallazgos) != 1 or re.search(
                r"\+|monoamb|\b(?:casas|deptos|departamentos|unidades|"
                r"locales|en\s+block)\b", titulo, re.I):
            return None
        return int(hallazgos[0])

    @staticmethod
    def _dormitorios_del_titulo(titulo: str | None) -> int | None:
        """Los dormitorios que la ficha solo dice en su titulo.

        «VENTA DEPARTAMENTO 3 DORMITORIOS CON COCHERA» (`metro`, `imperia`):
        la ficha no los rotula en otro lado. Mismas guardas que
        `_ambientes_del_titulo`: una sola unidad y un solo numero, sin rangos
        («2 y 3 dormitorios» es un emprendimiento, no esta ficha).
        """
        if not titulo:
            return None
        hallazgos = re.findall(
            r"(?<![\d+])\b([1-9])\s*(?:dormitorios?\b|dorm\b)", titulo, re.I)
        if len(hallazgos) != 1 or re.search(
                r"\+|\d\s*(?:y|a|o|-|/|,)\s*\d\s*dorm|\b(?:casas|deptos|"
                r"departamentos|unidades|locales|en\s+block)\b", titulo, re.I):
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
            # «Cocheras: 1» es un conteo con su rotulo, no el chip del tipo:
            # `candoli` guardaba dos complejos turisticos como cocheras.
            if re.search(r"[\d:]", texto):
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
        # Un icono VACIO dentro de la celda del rotulo no es parte del rotulo:
        # `bellomo` publica <dt><i class="bi bi-columns-gap"></i> Ambientes
        # </dt><dd>3</dd>, ninguna pareja de abajo la reconocia y el texto
        # plano «Ambientes 3 Baños 2» le daba banos=3 a una ficha con 2 (y
        # perdia los ambientes). Solo se quitan elementos sin texto: un icono
        # no puede ser rotulo ni valor.
        marcado = re.sub(r"<i\b[^>]*>\s*</i>", "", marcado, flags=re.I)
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
        # El rotulo puede ir en un <strong> dentro de su celda, que se cierra
        # antes del valor: <span class="…label"><span icono/><strong>Ambientes
        # </strong></span><span class="…value">5</span> (`daniel`, tema
        # estate: 10 fichas sin ambientes). Se tolera ese UNICO cierre, que
        # puede ser el del encabezado: el blurb de Divi es <h4><span>Ambientes
        # </span></h4><div class="et_pb_blurb_description">7</div> (`marcelo
        # zanni`: el texto plano leia «Ambientes 7 Baños 3» como 7 baños).
        for pareja in re.finditer(
                rf"<{celda}[^>]*>\s*(?:{etiqueta})\s*</{celda}>\s*(?:</(?:span|div|h[1-6])>\s*)?"
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
        # La pareja al reves: el NUMERO en su celda y el rotulo en la
        # siguiente, a veces con un <br> en el medio (fila de iconos):
        # <span class="p"> 1</span><br><span>Baños</span>. `b b administracion`
        # (Rafaela) la usa en sus 83 fichas y publica «Ambientes» como par
        # rotulo->valor, asi que la regla de abajo devolvia None y se perdian
        # 57 de 74 baños. Solo cuenta si el numero NO es el valor de un rotulo
        # anterior («<span>Ambientes</span><span>3</span><span>Baños</span>»
        # no dice 3 baños) y si todas las apariciones dicen lo mismo.
        inversos = set()
        for pareja in re.finditer(
                rf"<{celda}[^>]*>\s*(\d{{1,2}})\s*</{celda}>\s*(?:<br\s*/?>\s*)?"
                rf"<{celda}[^>]*>\s*(?:{etiqueta})\s*</{celda}>", marcado, re.I):
            previo = marcado[max(0, pareja.start() - 120):pareja.start()]
            if re.search(rf"<{celda}[^>]*>\s*(?:{ETIQUETAS_ATRIBUTO_COMPUESTO})\s*:?\s*</{celda}>\s*$",
                         previo, re.I):
                continue
            inversos.add(int(pareja.group(1)))
        if len(inversos) == 1:
            valor = inversos.pop()
            if 1 <= valor <= 99:
                return valor
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
        # O precedido de un icono vacio: <h2><i class="fas fa-info-circle"></i>
        # Descripción</h2> (`lo ponte`: 44 de 58 fichas sin descripcion).
        rotulo = r"(?:h[1-6]|div|span|strong|b|p|td)"
        # `.` cubre la vocal rota que sirven algunas fuentes legacy.
        acento = r"(?:[o\u00f3]|&oacute;|.)"
        m = re.search(
            rf"<{rotulo}[^>]*>\s*(?:<a\b[^>]*>\s*|<i\b[^>]*>\s*</i>\s*)?Descripci{acento}n"
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
            rf"<{rotulo}[^>]*>\s*(?:<a\b[^>]*>\s*|<i\b[^>]*>\s*</i>\s*)?Descripci{acento}n"
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
        # `properties` tambien: Kiteprop (`linkasa`, *.kitepropcrm.com) publica
        # el catalogo en /site/properties, paginado con ?page=N, y sin
        # reconocerlo se probaba /propiedades -que no existe- y solo se veian
        # las 4 destacadas de la portada de 19.
        patron = re.compile(
            r"(?:listado|propiedades|properties|inmuebles|emprendimientos|catalogo|"
            r"resultados|ventas|alquileres|buscar|comprar|alquilar)", re.I)
        def sin_www(u: str) -> str:
            return re.sub(r"^(https?://)www\.", r"\1", u, flags=re.I)

        for coincidencia in re.finditer(r'href="([^"]+)"', html or ""):
            destino = urllib.parse.urljoin(base, unescape(coincidencia.group(1)))
            # El padron puede traer el host sin `www.` y el sitio enlazar su
            # catalogo con `www.`: `blangiforti` (padron blangiforti.com.ar)
            # enlaza https://www.blangiforti.com.ar/ventas, que trae las 174
            # fichas en una pagina, y sin reconocerlo se caia a /propiedades,
            # paginado en orden aleatorio: 164 fichas en una corrida y 151 en
            # la otra. Solo esa variante del MISMO host, no subdominios.
            if not sin_www(destino).startswith(sin_www(base)):
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
                rf"<({celda})[^>]*>([^<>]{{1,60}})</{celda}>", marcado or "",
                re.I):
            contenido = bloque.group(2)
            if not re.search(etiqueta, contenido, re.I):
                continue
            # «3 DORMITORIOS CON COCHERA» en un TITULO dice un valor, no es un
            # rotulo que funde dos atributos: 83 fichas (`imperia`, `metro`,
            # `brunetti`...) perdian los dormitorios del <h1> como descartados.
            # Solo encabezados: en otras celdas la guarda sigue (`bottai` tiene
            # un buscador «1 dormitorio 2 dormitorios…» en la pagina).
            if (re.fullmatch(r"h[1-6]", bloque.group(1), re.I)
                    and re.search(rf"\d\s*(?:{etiqueta})", contenido, re.I)):
                continue
            rotulos = list(re.finditer(ETIQUETAS_ATRIBUTO_COMPUESTO, contenido, re.I))
            otros = {m.group(0).lower() for m in rotulos}
            # «4 dormitorios • 3 baños • 242» (`nexo`) es una LISTA de valores:
            # cada rotulo trae su numero delante. No funde dos atributos.
            if all(re.search(r"\d\s*[•·,|\-]?\s*$", contenido[:m.start()]) for m in rotulos):
                continue
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
        #
        # Y el numero que sigue al rotulo no es suyo si despues de su unidad
        # viene OTRO rotulo de superficie: «Son 110m2 totales, 94m2 cub» (`berardi`)
        # es valor-antes-de-rotulo, y «totales, 94» daba 94 de total. Ese 94 es
        # de «cub»; el total sale abajo, de «110m2 totales».
        otros = "|".join(raiz for raiz, muestra in SUPERFICIES_VECINAS
                         if not re.search(etiqueta, muestra, re.I))
        m = re.search(rf"(?:{etiqueta})[^\d]{{0,18}}([\d.,]{{2,9}})\s*m"
                      # «22m frente x 65m fondo», «14,36 mts de frente por
                      # 58,40»: tambien es una MEDIDA. Medido 2026-10-01: 11
                      # fichas de 10 agencias guardaban el frente (o el fondo)
                      # como superficie (`fenix` 4741529: 22 m² en un lote de
                      # 1.430).
                      rf"(?![a-z]*\.?\s*(?:de\s+)?(?:frente|fte|ancho)?\.?\s*(?:[x×]|por)\s*\d)"
                      # «95 m2 total: 200» o «45 m² Cubierta 40 m²» no: si el
                      # rotulo que sigue tiene SU numero, abre su propio par y
                      # el primero sigue siendo de quien lo precede.
                      rf"(?!\s*[²2]?\s*(?:{otros})[^\W\d_]*\b\.?(?!\s*:?\s*\d))",
                      texto, re.I) or \
            re.search(rf"([\d.,]{{2,9}})\s*m[²2]\s*(?:{etiqueta})", texto, re.I)
        if not m:
            return None
        v = a_numero(m.group(1))
        return v if v and 5 <= v <= 100_000 else None
