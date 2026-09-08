#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Connector WordPress — implementacion numero dos.

WordPress no es una plataforma inmobiliaria sino un CMS, asi que lo que define
la ingesta no es "usa WordPress" sino DONDE guarda el inventario. El discovery
sobre 50 fuentes reales encontro tres caminos, y el connector los prueba en
orden de costo:

  1. REST (32%): wp-json expone un post type inmobiliario -casi siempre
     "property"- y devuelve JSON estructurado con paginacion por cabeceras.
     Ahorra el parser entero y es la unica via que da campos ya tipados.
  2. SITEMAP (8%): el indice lista las fichas y evita recorrer el sitio a
     ciegas.
  3. HTML (14%): ultimo recurso, sobre las rutas que el propio sitio expone.

El 46% restante no publica inventario detectable: se reporta como tal, no se
fuerza. Un connector que devuelve cero en silencio hace creer que la
inmobiliaria no tiene propiedades cuando en realidad no la supimos leer.
"""
from __future__ import annotations

import json
import re
import urllib.parse
from html import unescape
from typing import Any, Iterator

from .base import (Bloqueado, Connector, ErrorPermanente, ErrorTransitorio,
                   sin_fichas_vecinas,
                   Fuente, PropiedadNormalizada, a_entero, a_numero,
                   detectar_moneda, detectar_operacion, detectar_tipo, limpiar,
                   recorte_estable_de_imagenes)

TIPOS_INMO = ("property", "properties", "propiedad", "propiedades", "inmueble",
              "inmuebles", "listing", "listings", "estate", "houzez_property",
              "rem_property", "wpl_property", "residence")

POR_PAGINA = 50
MAX_PAGINAS = 200
TAXONOMIAS_INMO = (
    "property_type", "property_status", "property_state", "property_city",
    "property_area",
)
REST_FIELDS = (
    "id,link,type,modified,date,title,content,property_meta,meta,"
    "property_type,property_status,property_state,property_city,property_area"
)

RE_IMG = re.compile(r'https?://[^\s"\'<>]+?\.(?:jpe?g|png|webp)', re.I)


# El bloque de direccion del tema Houzez, con una clase por campo:
#
#   <li class="detail-city"><strong>Ciudad</strong> <span>La Plata</span></li>
#
# La taxonomia de WordPress puede estar vacia mientras la ficha muestra el dato
# ahi: en `adrianghiopropiedades.com` lo esta en las 58 fichas, y las 58 quedaban
# sin ciudad teniendo "La Plata" a la vista. La localidad es el dato mas escaso
# del proyecto -se puede demostrar en el 16,5 % de las propiedades-, asi que
# perderla cuando la fuente la publica es de los defectos mas caros.
#
# Se leen SOLO `detail-address` y `detail-city`, que son rotulos inequivocos.
# `detail-state` dice "Bs.As. G.B.A. Sur" -una zona, no una provincia- y
# `detail-area` esta rotulado "Localidad o barrio" y trae la ciudad repetida.
# Guardar el primero como provincia o el segundo como barrio seria inventar
# geografia en el lugar mas dificil de corregir despues. Que esos dos rotulos
# sean ambiguos es de la fuente, no un defecto nuestro.
RE_DETALLE_HOUZEZ = (
    "<li[^>]*class=[\"'][^\"']*detail-{clase}[^\"']*[\"'][^>]*>"
    ".{{0,160}}?<span[^>]*>(.{{1,120}}?)</span>")


def _detalle_houzez(html: str, clase: str) -> str | None:
    m = re.search(RE_DETALLE_HOUZEZ.format(clase=clase), html or "", re.I | re.S)
    if not m:
        return None
    return limpiar(re.sub(r"<[^>]+>", " ", m.group(1))) or None


def _texto(html: str) -> str:
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html or "", flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", unescape(t).replace("\xa0", " "))


# La ruta de listado suele llamarse "buscar-propiedades" o "propiedades", asi
# que la propia pagina de busqueda entra por el mismo patron que las fichas.
# Distinguirlas necesita dos condiciones: sin query string -un filtro no es una
# propiedad- y con un ultimo segmento que identifique algo, sea un id o un slug
# de varias palabras.
RE_SLUG_FICHA = re.compile(
    r"/[^/?#]*(?:\d{3,}|[a-z0-9]+(?:-[a-z0-9]+){2,})[^/?#]*/?$", re.I)


def _es_ficha(url: str) -> bool:
    if "?" in url or "#" in url:
        return False
    return bool(RE_SLUG_FICHA.search(url))


def _id_de(url: str) -> str:
    """Id rastreable hasta la ficha. Nunca la query string entera: un
    source_listing_id de 200 caracteres con filtros de busqueda adentro no
    identifica nada y ensucia el artefacto."""
    ruta = url.split("?")[0].rstrip("/")
    ultimo = ruta.rsplit("/", 1)[-1]
    m = re.search(r"(\d{3,})", ultimo)
    return (m.group(1) if m else ultimo)[:120]


# WordPress genera una copia de cada foto por cada tamano que usa el tema:
# la misma imagen aparece como -120x72, -224x140, -768x1024 y sin sufijo.
RE_TAMANO = re.compile(r"-(\d{2,4})x(\d{2,4})(?=\.[a-z]{3,4}$)", re.I)


def _sin_variantes_de_tamano(urls: list[str]) -> list[str]:
    """Una foto es una foto, no cuatro.

    El 30% de las "fotos" de WordPress eran variantes de tamano de la misma
    imagen: 146.876 entradas de mas en 9.672 propiedades, mas de la mitad del
    catalogo. Una propiedad que figuraba con 40 fotos solia tener diez.

    Se queda la version mas grande de cada imagen, que es la que sirve para
    mostrar: la original sin sufijo si esta, y si no la de mayor superficie. El
    orden de aparicion se respeta, asi que la principal sigue siendo la primera.
    """
    mejor: dict[str, tuple[int, str]] = {}
    orden: list[str] = []
    for u in urls:
        base = RE_TAMANO.sub("", u)
        m = RE_TAMANO.search(u)
        # Sin sufijo es la original: gana siempre.
        area = 0 if m is None else int(m.group(1)) * int(m.group(2))
        prioridad = float("inf") if m is None else area
        if base not in mejor:
            orden.append(base)
            mejor[base] = (prioridad, u)
        elif prioridad > mejor[base][0]:
            mejor[base] = (prioridad, u)
    return [mejor[b][1] for b in orden]


def _rendered(valor: Any) -> str | None:
    """Los campos de WordPress vienen como {"rendered": "<p>...</p>"}."""
    if isinstance(valor, dict):
        valor = valor.get("rendered")
    return limpiar(_texto(str(valor))) if valor else None


def _primero(meta: dict[str, Any], clave: str) -> Any:
    valor = meta.get(clave)
    if isinstance(valor, list):
        return valor[0] if valor else None
    return valor


def _descripcion_estable(valor: Any) -> str | None:
    texto = _rendered(valor)
    if not texto:
        return None
    # Houzez agrega una marca de hora al contenido renderizado de algunas
    # fichas. Cambia en cada request sin que cambie la publicacion.
    texto = re.sub(
        r"\s*Actualizado el d(?:í|i|�)a:\s*"
        r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s*$",
        "", texto, flags=re.I)
    return limpiar(texto)


def _nombre_taxonomia(crudo: dict[str, Any], item: dict[str, Any],
                      taxonomia: str) -> str | None:
    mapa = (crudo.get("taxonomy_terms") or {}).get(taxonomia) or {}
    nombres = []
    for term_id in item.get(taxonomia) or []:
        termino = mapa.get(str(term_id)) or {}
        nombre = termino.get("name") or termino.get("slug")
        if nombre:
            nombres.append(str(nombre))
    return " ".join(nombres) or None


def _texto_taxonomia(crudo: dict[str, Any], item: dict[str, Any],
                     taxonomia: str) -> str:
    """Nombre + slug para clasificar sin depender del encoding del nombre.

    Varios WordPress argentinos publican ``Galp�n`` en ``name`` pero un slug
    limpio ``galpon``. El slug sirve para mapear al vocabulario canonico; el
    nombre sigue siendo el valor que se conserva para ciudad/provincia/barrio.
    """
    mapa = (crudo.get("taxonomy_terms") or {}).get(taxonomia) or {}
    partes: list[str] = []
    for term_id in item.get(taxonomia) or []:
        termino = mapa.get(str(term_id)) or {}
        partes.extend(str(v) for v in (termino.get("name"), termino.get("slug")) if v)
    return " ".join(partes)


def _meta_presente(meta: dict[str, Any], clave: str) -> bool:
    valor = _primero(meta, clave)
    return valor is not None and str(valor).strip() not in {"", "0", "None"}


def _coordenadas_meta(meta: dict[str, Any]) -> tuple[float | None, float | None]:
    lat = a_numero(_primero(meta, "houzez_geolocation_lat"))
    lon = a_numero(_primero(meta, "houzez_geolocation_long"))
    if lat is None or lon is None:
        ubicacion = str(_primero(meta, "fave_property_location") or "")
        m = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*", ubicacion)
        if m:
            lat, lon = float(m.group(1)), float(m.group(2))
    if lat is None or not -56 <= lat <= -21:
        lat = None
    if lon is None or not -74 <= lon <= -53:
        lon = None
    return lat, lon


class WordPressConnector(Connector):
    nombre = "wordpress"
    variantes_soportadas = ("WORDPRESS_REST", "WORDPRESS_POST_TAXONOMY",
                            "WORDPRESS_SITEMAP", "WORDPRESS_HTML")

    # ---------------------------------------------------------------- discover
    def discover(self, fuente: Fuente) -> dict[str, Any]:
        p = urllib.parse.urlparse(fuente.official_url)
        base = f"{p.scheme}://{p.netloc}"
        plan: dict[str, Any] = {"base": base, "variante": "SIN_INVENTARIO",
                                "soportada": False, "total_declarado": None}

        # --- 1. REST -------------------------------------------------------
        try:
            tipos = json.loads(self.descargador.bajar(base + "/wp-json/wp/v2/types"))
        except (ValueError, ErrorTransitorio, ErrorPermanente, Bloqueado):
            tipos = None
        if isinstance(tipos, dict):
            plan["wp_json"] = True
            candidatos = [t for t in sorted(tipos)
                          if any(k == t.lower() or k in t.lower() for k in TIPOS_INMO)]
            plan["post_types_inmo"] = candidatos
            for t in candidatos:
                meta = tipos.get(t) or {}
                ruta = meta.get("rest_base") or t
                try:
                    cuerpo = self.descargador.bajar(
                        f"{base}/wp-json/wp/v2/{ruta}?per_page=1")
                    muestra = json.loads(cuerpo)
                except (ValueError, ErrorTransitorio, ErrorPermanente, Bloqueado):
                    continue
                if isinstance(muestra, list) and muestra:
                    plan.update({"variante": "WORDPRESS_REST", "soportada": True,
                                 "rest_base": ruta, "post_type": t})
                    plan["taxonomy_terms"] = self._taxonomias(base, meta)
                    return plan
            # Algunos portales propios modelan cada ficha como un post normal,
            # pero lo separan inequívocamente de un blog mediante taxonomías
            # registradas: una operación obligatoria y categorías de inmueble.
            # No alcanza con que existan posts ni con que el título diga venta.
            post_meta = tipos.get("post") or {}
            post_taxonomies = set(post_meta.get("taxonomies") or [])
            if {"operacion", "category"}.issubset(post_taxonomies):
                post_catalog = self._catalogo_posts_inmobiliarios(base)
                if post_catalog is not None:
                    plan.update({
                        "variante": "WORDPRESS_POST_TAXONOMY",
                        "soportada": True,
                        "rest_base": post_meta.get("rest_base") or "posts",
                        "post_type": "post",
                        "taxonomy_terms": post_catalog["terms"],
                        "total_declarado": post_catalog["total"],
                        "rest_fields": (
                            "id,link,type,modified,date,title,content,"
                            "categories,localidad,operacion"),
                        "post_taxonomy_catalog": True,
                    })
                    return plan

        # --- 2. sitemap ----------------------------------------------------
        for ruta in ("/wp-sitemap.xml", "/sitemap_index.xml", "/sitemap.xml"):
            try:
                cuerpo = self.descargador.bajar(base + ruta)
            except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                continue
            if "<" not in cuerpo:
                continue
            sub = [u for u in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", cuerpo)
                   if any(f"/{t}" in u.lower() for t in TIPOS_INMO)]
            if sub:
                plan.update({"variante": "WORDPRESS_SITEMAP", "soportada": True,
                             "sitemaps": sub[:20]})
                return plan

        # --- 3. HTML -------------------------------------------------------
        # No se retorna al fallar: la guardia de abajo tiene que ver TODAS las
        # salidas sin soporte, y saltearla era dejar el agujero justo en el
        # camino por el que se llega cuando el sitio no responde.
        html = ""
        try:
            html = self.descargador.bajar(fuente.official_url)
        except (ErrorTransitorio, ErrorPermanente, Bloqueado):
            pass
        rutas = {m.group(1).lower() for m in
                 re.finditer(r'href="[^"]*?/([a-z\-]{4,20})/[^"]{3,}"', html)}
        inmo = sorted(r for r in rutas if any(k in r for k in TIPOS_INMO))
        if inmo:
            plan.update({"variante": "WORDPRESS_HTML", "soportada": True,
                         "ruta_html": inmo[0], "html_home": html})
        return plan

    def _taxonomias(self, base: str, post_type: dict[str, Any]) -> dict[str, Any]:
        """Carga una vez los vocabularios chicos asociados al post type.

        No usamos ``_embed``: en Houzez incrusta cientos de features en cada
        propiedad y una sola pagina REST supera varios megabytes. Cinco tablas
        de terminos compactas dan la misma semantica sin repetirla 359 veces.
        """
        declaradas = post_type.get("taxonomies")
        # Si el endpoint de tipos no declara taxonomias no adivinamos rutas:
        # varios post types empiezan por ``property`` y un servidor permisivo
        # podria responder otra coleccion a un prefijo parecido.
        nombres = ([t for t in TAXONOMIAS_INMO if t in declaradas]
                   if isinstance(declaradas, list) else [])
        resultado: dict[str, Any] = {}
        for taxonomia in nombres:
            terminos: dict[str, Any] = {}
            for pagina in range(1, 20):
                url = (f"{base}/wp-json/wp/v2/{taxonomia}?per_page=100&page={pagina}"
                       "&_fields=id,name,slug")
                try:
                    items = json.loads(self.descargador.bajar(url))
                except (ValueError, ErrorTransitorio, ErrorPermanente, Bloqueado):
                    break
                if not isinstance(items, list) or not items:
                    break
                for item in items:
                    if item.get("id") is not None:
                        terminos[str(item["id"])] = {
                            "name": item.get("name"), "slug": item.get("slug")}
                if len(items) < 100:
                    break
            if terminos:
                resultado[taxonomia] = terminos
        return resultado

    def _catalogo_posts_inmobiliarios(self,
                                      base: str) -> dict[str, Any] | None:
        """Valida posts inmobiliarios por contratos taxonómicos públicos."""
        endpoints = {
            "operacion": "operacion",
            "categories": "categories",
            "localidad": "localidad",
        }
        terms: dict[str, dict[str, Any]] = {}
        for item_field, endpoint in endpoints.items():
            try:
                rows = json.loads(self.descargador.bajar(
                    f"{base}/wp-json/wp/v2/{endpoint}?per_page=100"
                    "&_fields=id,name,slug,count"))
            except (ValueError, ErrorTransitorio, ErrorPermanente, Bloqueado):
                return None
            if not isinstance(rows, list):
                return None
            terms[item_field] = {
                str(row["id"]): {"name": row.get("name"),
                                 "slug": row.get("slug"),
                                 "count": row.get("count")}
                for row in rows if isinstance(row, dict) and row.get("id") is not None
            }
        operations = terms.get("operacion") or {}
        valid_operations = {
            term_id: term for term_id, term in operations.items()
            if detectar_operacion(f"{term.get('name') or ''} {term.get('slug') or ''}")
        }
        declared = sum(int(term.get("count") or 0)
                       for term in valid_operations.values())
        category_text = " ".join(
            f"{term.get('name') or ''} {term.get('slug') or ''}"
            for term in (terms.get("categories") or {}).values())
        category_types = {
            detected for token in re.split(r"\s+", category_text)
            for detected in [detectar_tipo(token)] if detected
        }
        if not valid_operations or declared < 3 or not category_types:
            return None
        try:
            first_page = json.loads(self.descargador.bajar(
                f"{base}/wp-json/wp/v2/posts?per_page=1"
                "&_fields=id,link,categories,localidad,operacion"))
        except (ValueError, ErrorTransitorio, ErrorPermanente, Bloqueado):
            return None
        if (not isinstance(first_page, list) or not first_page
                or len(first_page[0].get("operacion") or []) != 1
                or not first_page[0].get("categories")):
            return None
        return {"terms": terms, "total": declared}

    # ----------------------------------------------------------- fetch_listing
    def fetch_listing(self, fuente: Fuente, plan: dict[str, Any]) -> Iterator[dict]:
        if not plan.get("soportada"):
            return
        if plan["variante"] in {"WORDPRESS_REST", "WORDPRESS_POST_TAXONOMY"}:
            yield from self._rest(plan)
        elif plan["variante"] == "WORDPRESS_SITEMAP":
            yield from self._sitemap(plan)
        else:
            yield from self._html(fuente, plan)

    def _rest(self, plan: dict[str, Any]) -> Iterator[dict]:
        base, ruta = plan["base"], plan["rest_base"]
        fields = plan.get("rest_fields") or REST_FIELDS
        vistos: set[str] = set()
        for pagina in range(1, MAX_PAGINAS + 1):
            url = (f"{base}/wp-json/wp/v2/{ruta}?per_page={POR_PAGINA}&page={pagina}"
                   f"&_fields={fields}")
            try:
                items = json.loads(self.descargador.bajar(url))
            except (ValueError, ErrorPermanente):
                # WordPress devuelve 400 cuando se pide una pagina inexistente:
                # es el final del listado, no un fallo.
                break
            except (ErrorTransitorio, Bloqueado):
                break
            if not isinstance(items, list) or not items:
                break
            nuevos = 0
            for it in items:
                lid = str(it.get("id") or "")
                if not lid or lid in vistos:
                    continue
                vistos.add(lid)
                nuevos += 1
                yield {"source_listing_id": lid,
                       "source_url": it.get("link") or f"{base}/?p={lid}",
                       "pagina": pagina, "rest": it,
                       "taxonomy_terms": plan.get("taxonomy_terms") or {},
                       "post_taxonomy_catalog": bool(
                           plan.get("post_taxonomy_catalog"))}
            if nuevos == 0 or len(items) < POR_PAGINA:
                break

    def _sitemap(self, plan: dict[str, Any]) -> Iterator[dict]:
        vistos: set[str] = set()
        pagina = 0
        for sm in plan["sitemaps"][:20]:
            pagina += 1
            try:
                cuerpo = self.descargador.bajar(sm)
            except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                continue
            for u in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", cuerpo):
                if u in vistos or not any(f"/{t}" in u.lower() for t in TIPOS_INMO):
                    continue
                if not _es_ficha(u):
                    continue
                vistos.add(u)
                yield {"source_listing_id": _id_de(u), "source_url": u,
                       "pagina": pagina}

    def _html(self, fuente: Fuente, plan: dict[str, Any]) -> Iterator[dict]:
        base, ruta = plan["base"], plan["ruta_html"]
        vistos: set[str] = set()
        for pagina in range(1, 41):
            url = f"{base}/{ruta}/" if pagina == 1 else f"{base}/{ruta}/page/{pagina}/"
            try:
                html = self.descargador.bajar(url)
            except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                break
            nuevos = 0
            for m in re.finditer(rf'href="({re.escape(base)}/{re.escape(ruta)}/[^"/]+/?)"', html):
                u = m.group(1)
                if u.rstrip("/").endswith(ruta) or u in vistos:
                    continue
                if not _es_ficha(u):
                    continue
                vistos.add(u)
                nuevos += 1
                yield {"source_listing_id": u.rstrip("/").rsplit("/", 1)[-1],
                       "source_url": u, "pagina": pagina}
            if nuevos == 0:
                break

    # --------------------------------------------------------------- normalize
    def normalize(self, crudo: dict, fuente: Fuente) -> PropiedadNormalizada | None:
        url = crudo["source_url"]
        item = crudo.get("rest")
        html = ""
        if item is None:
            try:
                html = self.descargador.bajar(url)
            except ErrorPermanente:
                return None
            except (ErrorTransitorio, Bloqueado) as e:
                self.anotar_error(fuente, "detalle", e)
                return None

        if item is not None:
            titulo = _rendered(item.get("title"))
            descripcion = _descripcion_estable(item.get("content"))
            texto = f"{titulo or ''} {descripcion or ''}"
            # Corrige solamente etiquetas conocidas para que el mojibake de la
            # fuente no convierta un dato visible en ausente.
            texto = (texto.replace("Ba�o", "Baño").replace("ba�o", "baño")
                     .replace("m�", "m²"))
            meta_cruda = item.get("property_meta") or item.get("meta") or {}
            meta = meta_cruda if isinstance(meta_cruda, dict) else {}
            imagenes = []
            for clave in ("_thumbnail_url", "featured_image", "image"):
                v = (meta or {}).get(clave)
                if isinstance(v, str) and v.startswith("http"):
                    imagenes.append(v)
            imagenes += RE_IMG.findall(str(item.get("content") or ""))
            fecha = item.get("modified") or item.get("date")

            # La ficha HTML se usa como respaldo de fotos/precio, pero NUNCA se
            # mezcla con ``texto``. Houzez agrega marcas horarias y a veces
            # bloques diferentes entre requests; mezclarlos volvia no
            # idempotentes ambientes, dormitorios y descripcion.
            if not imagenes or not re.search(r"(USD|U\$S|US\$|ARS)", texto, re.I):
                try:
                    html = self.descargador.bajar(url)
                except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                    html = ""
                if html:
                    imagenes += RE_IMG.findall(
                        sin_fichas_vecinas(html, url))
                    if not descripcion:
                        m = re.search(
                            r'<meta[^>]+name="description"[^>]+content="([^"]{1,400})"',
                            html)
                        if m:
                            descripcion = limpiar(m.group(1))
        else:
            texto_plano = _texto(html)
            m = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]{1,200})"', html)
            titulo = limpiar(m.group(1)) if m else None
            if not titulo:
                m = re.search(r"<title[^>]*>(.{1,200}?)</title>", html, re.S | re.I)
                titulo = limpiar(m.group(1)) if m else None
            descripcion = None
            m = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]{1,400})"', html)
            if m:
                descripcion = limpiar(m.group(1))
            texto = texto_plano[:6000]
            # El carrusel de propiedades relacionadas trae la foto de cada
            # vecina. Sin sacarlo, cada aviso terminaba con fotos de otros.
            imagenes = RE_IMG.findall(sin_fichas_vecinas(html, url))
            fecha = None

        # Precio y moneda. La convencion de "$" la decide el pipeline, no este
        # connector: normalize_currency de import_captured_props_to_neon mapea
        # "$" a ARS, y detectar_moneda en base.py hace lo mismo. Poner aca una
        # regla propia mas estricta dejaba precios sin moneda y creaba una
        # segunda verdad sobre el mismo dato.
        precio = moneda = None
        if item is not None:
            precio = a_numero(_primero(meta, "fave_property_price"))
            moneda = detectar_moneda(_primero(meta, "fave_currency"))
            # Houzez usa cero como placeholder de "consultar". No es un
            # precio publicado y PropiedadNormalizada lo considera invalido.
            if precio is not None and precio <= 0:
                precio = None
        mp = re.search(r"(USD|U\$S|US\$|\$|ARS)\s*([\d][\d.,]{2,15})", texto, re.I)
        if mp and precio is None:
            precio = a_numero(mp.group(2))
        if mp and moneda is None:
            moneda = detectar_moneda(mp.group(1))
        if item is not None and html and (precio is None or moneda is None):
            mp_html = re.search(r"(USD|U\$S|US\$|\$|ARS)\s*([\d][\d.,]{2,15})",
                                _texto(html)[:6000], re.I)
            if mp_html and precio is None:
                precio = a_numero(mp_html.group(2))
            if mp_html and moneda is None:
                moneda = detectar_moneda(mp_html.group(1))
        if precio is not None and precio <= 0:
            precio = None

        limpias, vistas = [], set()
        for u in imagenes:
            u = u.split("?")[0]
            if u in vistas or re.search(r"(logo|placeholder|avatar|icon|sprite)", u, re.I):
                continue
            vistas.add(u)
            limpias.append(u)

        # El signo NO es opcional. Argentina esta entera en el hemisferio sur y
        # oeste, asi que todas sus coordenadas son negativas; con el menos
        # opcional el patron tomaba pares como "50.774, 50.7708" -que no son
        # coordenadas de nada- y ubicaba 752 propiedades fuera del pais.
        lat, lon = _coordenadas_meta(meta) if item is not None else (None, None)
        if lat is None or lon is None:
            mc = re.search(r'(-[23456]\d\.\d{3,})[",\s]+(-[567]\d\.\d{3,})',
                           str(item or html))
            if mc:
                lat, lon = float(mc.group(1)), float(mc.group(2))

        is_post_catalog = bool(crudo.get("post_taxonomy_catalog"))
        operacion_fuente = (
            _texto_taxonomia(crudo, item, "operacion")
            if item is not None and is_post_catalog
            else _texto_taxonomia(crudo, item, "property_status")
            if item is not None else "")
        tipo_fuente = (
            _texto_taxonomia(crudo, item, "categories")
            if item is not None and is_post_catalog
            else _texto_taxonomia(crudo, item, "property_type")
            if item is not None else "")
        operacion = detectar_operacion(operacion_fuente) or detectar_operacion(
            f"{titulo or ''} {url}")
        tipo = detectar_tipo(tipo_fuente) or detectar_tipo(f"{titulo or ''} {url}")
        direccion = (limpiar(_primero(meta, "fave_property_address"))
                     if item is not None else None)
        barrio = _nombre_taxonomia(crudo, item, "property_area") if item is not None else None
        ciudad = (_nombre_taxonomia(crudo, item, "localidad")
                  if item is not None and is_post_catalog
                  else _nombre_taxonomia(crudo, item, "property_city")
                  if item is not None else None)
        provincia = _nombre_taxonomia(crudo, item, "property_state") if item is not None else None
        # Cuando la taxonomia no trae nada, la ficha suele traerlo igual.
        ciudad = ciudad or _detalle_houzez(html, "city")
        direccion = direccion or _detalle_houzez(html, "address")

        dormitorios = self._ambientes(texto, r"dormitorios?|habitaciones?")
        banos = self._ambientes(texto, r"ba[nñ]os?")
        ambientes = self._ambientes(texto, r"ambientes?")
        superficie_total = a_numero(self._superficie(
            texto, r"superficie total|sup\.?\s*total|[aá]rea del terreno|terreno"))
        superficie_cubierta = a_numero(self._superficie(
            texto, r"superficie cubierta|sup\.?\s*cubierta|cubierta|construidos?"))
        if item is not None:
            dormitorios = dormitorios or a_entero(_primero(meta, "fave_property_bedrooms"))
            banos = banos or a_entero(_primero(meta, "fave_property_bathrooms"))
            ambientes = ambientes or a_entero(_primero(meta, "fave_property_rooms"))
            superficie_total = superficie_total or a_numero(
                _primero(meta, "fave_property_land"))
            superficie_cubierta = superficie_cubierta or a_numero(
                _primero(meta, "fave_property_size"))

        source_fields = {}
        descartados: list[str] = []
        if item is not None:
            source_fields = {
                "titulo": bool(titulo), "descripcion": bool(descripcion),
                "precio": bool(precio), "moneda": bool(moneda),
                "operacion": bool(operacion_fuente), "tipo_propiedad": bool(tipo_fuente),
                "direccion": _meta_presente(meta, "fave_property_address"),
                "barrio": bool(barrio), "ciudad": bool(ciudad),
                "provincia": bool(provincia),
                "ambientes": bool(self._ambientes(texto, r"ambientes?") or
                                  _meta_presente(meta, "fave_property_rooms")),
                "dormitorios": bool(self._ambientes(texto, r"dormitorios?|habitaciones?") or
                                    _meta_presente(meta, "fave_property_bedrooms")),
                "banos": bool(self._ambientes(texto, r"ba[nñ]os?") or
                              _meta_presente(meta, "fave_property_bathrooms")),
                "superficie_total": bool(self._superficie(
                    texto, r"superficie total|sup\.?\s*total|[aá]rea del terreno|terreno") or
                    _meta_presente(meta, "fave_property_land")),
                "superficie_cubierta": bool(self._superficie(
                    texto, r"superficie cubierta|sup\.?\s*cubierta|cubierta|construidos?") or
                    _meta_presente(meta, "fave_property_size")),
                "latitud": _meta_presente(meta, "houzez_geolocation_lat") or
                            _meta_presente(meta, "fave_property_location"),
                "longitud": _meta_presente(meta, "houzez_geolocation_long") or
                             _meta_presente(meta, "fave_property_location"),
                "imagenes": bool(limpias),
            }
            if tipo_fuente and not tipo:
                descartados.append("tipo_propiedad:taxonomia_no_mapeada")
            if source_fields["latitud"] and lat is None:
                descartados.append("latitud:fuera_argentina")
            if source_fields["longitud"] and lon is None:
                descartados.append("longitud:fuera_argentina")
            if source_fields["superficie_total"] and superficie_total is None:
                descartados.append("superficie_total:formato_no_confiable")
            if source_fields["superficie_cubierta"] and superficie_cubierta is None:
                descartados.append("superficie_cubierta:formato_no_confiable")

        return PropiedadNormalizada(
            canonical_agency_id=fuente.canonical_agency_id,
            source_listing_id=str(crudo["source_listing_id"]),
            source_url=url,
            connector=self.nombre,
            titulo=titulo,
            descripcion=(descripcion or "")[:4000] or None,
            precio=precio,
            moneda=moneda,
            operacion=operacion,
            tipo_propiedad=tipo,
            direccion=direccion,
            barrio=barrio,
            ciudad=ciudad,
            provincia=provincia,
            latitud=lat,
            longitud=lon,
            dormitorios=dormitorios,
            banos=banos,
            ambientes=ambientes,
            superficie_total=superficie_total,
            superficie_cubierta=superficie_cubierta,
            imagenes=recorte_estable_de_imagenes(_sin_variantes_de_tamano(limpias), 40),
            extra={k: v for k, v in {
                "post_type": crudo.get("rest", {}).get("type") if crudo.get("rest") else None,
                "modificado_en_fuente": fecha,
                "via": "rest" if item is not None else "html",
                "source_fields_provided": source_fields or None,
                "atributos_descartados": ",".join(descartados) or None,
            }.items() if v},
            inmobiliaria_id=fuente.inmobiliaria_id,
            provenance={"connector": self.nombre,
                        "official_domain": f"{urllib.parse.urlparse(url).scheme}://"
                                           f"{urllib.parse.urlparse(url).netloc}",
                        "agency_name": fuente.agency_name,
                        "canonical_agency_id": fuente.canonical_agency_id,
                        "source_platform": "WORDPRESS",
                        "pagina_listado": crudo.get("pagina")},
        )

    @staticmethod
    def _campo(texto: str, etiqueta: str) -> str | None:
        m = re.search(rf"(\d[\d.,]{{0,6}})\s*(?:{etiqueta})", texto, re.I)
        if not m:
            m = re.search(rf"(?:{etiqueta})\s*:?\s*(\d[\d.,]{{0,6}})", texto, re.I)
        return m.group(1) if m else None

    @staticmethod
    def _superficie(texto: str, etiqueta: str) -> str | None:
        """Superficie explicita en las dos redacciones habituales.

        WordPress/Houzez usa tanto ``superficie total de 108 m2`` como
        ``48 m2 de superficie total``. No multiplicamos medidas de lote ni
        intentamos separar metadatos concatenados: ambos requieren inferencia.
        """
        numero = r"(\d[\d.,]{0,9})"
        unidad = r"(?:m(?:2|²))"
        patrones = (
            rf"(?:{etiqueta})\s*:?(?:\s+de)?\s*{numero}(?:\s*{unidad})?",
            rf"{numero}\s*{unidad}(?:\s+de)?\s*(?:{etiqueta})",
            rf"{numero}\s*(?:{etiqueta})",
        )
        for patron in patrones:
            m = re.search(patron, texto, re.I)
            if m:
                return m.group(1)
        return None

    @staticmethod
    def _ambientes(texto: str, etiqueta: str) -> int | None:
        """Cantidad de ambientes/dormitorios/banos.

        Un cero casi nunca es un dato: es un "0" suelto del texto que cayo
        junto a la etiqueta. Publicar "0 ambientes" es peor que no publicar
        nada, porque parece un dato verificado.
        """
        crudo = WordPressConnector._campo(texto, etiqueta)
        v = a_entero(crudo)
        return v if v and 1 <= v <= 99 else None
