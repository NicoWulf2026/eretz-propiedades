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
                   Fuente, PropiedadNormalizada, a_entero, a_numero,
                   detectar_moneda, detectar_operacion, detectar_tipo, limpiar,
                   recorte_estable_de_imagenes)

TIPOS_INMO = ("property", "properties", "propiedad", "propiedades", "inmueble",
              "inmuebles", "listing", "listings", "estate", "houzez_property",
              "rem_property", "wpl_property", "residence")

POR_PAGINA = 50
MAX_PAGINAS = 200

RE_IMG = re.compile(r'https?://[^\s"\'<>]+?\.(?:jpe?g|png|webp)', re.I)


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


class WordPressConnector(Connector):
    nombre = "wordpress"
    variantes_soportadas = ("WORDPRESS_REST", "WORDPRESS_SITEMAP", "WORDPRESS_HTML")

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
        try:
            html = self.descargador.bajar(fuente.official_url)
        except (ErrorTransitorio, ErrorPermanente, Bloqueado):
            return plan
        rutas = {m.group(1).lower() for m in
                 re.finditer(r'href="[^"]*?/([a-z\-]{4,20})/[^"]{3,}"', html)}
        inmo = sorted(r for r in rutas if any(k in r for k in TIPOS_INMO))
        if inmo:
            plan.update({"variante": "WORDPRESS_HTML", "soportada": True,
                         "ruta_html": inmo[0], "html_home": html})
        return plan

    # ----------------------------------------------------------- fetch_listing
    def fetch_listing(self, fuente: Fuente, plan: dict[str, Any]) -> Iterator[dict]:
        if not plan.get("soportada"):
            return
        if plan["variante"] == "WORDPRESS_REST":
            yield from self._rest(plan)
        elif plan["variante"] == "WORDPRESS_SITEMAP":
            yield from self._sitemap(plan)
        else:
            yield from self._html(fuente, plan)

    def _rest(self, plan: dict[str, Any]) -> Iterator[dict]:
        base, ruta = plan["base"], plan["rest_base"]
        vistos: set[str] = set()
        for pagina in range(1, MAX_PAGINAS + 1):
            url = f"{base}/wp-json/wp/v2/{ruta}?per_page={POR_PAGINA}&page={pagina}"
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
                       "pagina": pagina, "rest": it}
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
            descripcion = _rendered(item.get("content"))
            texto = f"{titulo or ''} {descripcion or ''}"
            meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
            imagenes = []
            for clave in ("_thumbnail_url", "featured_image", "image"):
                v = (meta or {}).get(clave)
                if isinstance(v, str) and v.startswith("http"):
                    imagenes.append(v)
            imagenes += RE_IMG.findall(str(item.get("content") or ""))
            fecha = item.get("modified") or item.get("date")

            # La mayoria de los temas inmobiliarios guardan precio, moneda,
            # ambientes y fotos en campos ACF que la REST no expone: el JSON
            # trae titulo y poco mas. Cuando pasa eso, la ficha renderizada si
            # los muestra, y una peticion extra vale mas que publicar una
            # propiedad sin precio ni fotos.
            if not imagenes or not re.search(r"(USD|U\$S|US\$|ARS)", texto, re.I):
                try:
                    html = self.descargador.bajar(url)
                except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                    html = ""
                if html:
                    texto = f"{texto} {_texto(html)[:6000]}"
                    imagenes += RE_IMG.findall(html)
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
            imagenes = RE_IMG.findall(html)
            fecha = None

        # Precio y moneda. La convencion de "$" la decide el pipeline, no este
        # connector: normalize_currency de import_captured_props_to_neon mapea
        # "$" a ARS, y detectar_moneda en base.py hace lo mismo. Poner aca una
        # regla propia mas estricta dejaba precios sin moneda y creaba una
        # segunda verdad sobre el mismo dato.
        precio = moneda = None
        mp = re.search(r"(USD|U\$S|US\$|\$|ARS)\s*([\d][\d.,]{2,15})", texto, re.I)
        if mp:
            moneda = detectar_moneda(mp.group(1))
            precio = a_numero(mp.group(2))

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
        lat = lon = None
        mc = re.search(r'(-[23456]\d\.\d{3,})[",\s]+(-[567]\d\.\d{3,})',
                       str(item or html))
        if mc:
            lat, lon = float(mc.group(1)), float(mc.group(2))

        return PropiedadNormalizada(
            canonical_agency_id=fuente.canonical_agency_id,
            source_listing_id=str(crudo["source_listing_id"]),
            source_url=url,
            connector=self.nombre,
            titulo=titulo,
            descripcion=(descripcion or "")[:4000] or None,
            precio=precio,
            moneda=moneda,
            operacion=detectar_operacion(f"{titulo or ''} {url}"),
            tipo_propiedad=detectar_tipo(f"{titulo or ''} {url}"),
            direccion=None,
            barrio=None,
            ciudad=None,
            provincia=None,
            latitud=lat,
            longitud=lon,
            dormitorios=self._ambientes(texto, r"dormitorios?|habitaciones?"),
            banos=self._ambientes(texto, r"ba[nñ]os?"),
            ambientes=self._ambientes(texto, r"ambientes?"),
            superficie_total=a_numero(self._campo(texto, r"superficie total|terreno")),
            superficie_cubierta=a_numero(self._campo(texto, r"cubierta|construidos?")),
            imagenes=recorte_estable_de_imagenes(_sin_variantes_de_tamano(limpias), 40),
            extra={k: v for k, v in {
                "post_type": crudo.get("rest", {}).get("type") if crudo.get("rest") else None,
                "modificado_en_fuente": fecha,
                "via": "rest" if item is not None else "html",
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
    def _ambientes(texto: str, etiqueta: str) -> int | None:
        """Cantidad de ambientes/dormitorios/banos.

        Un cero casi nunca es un dato: es un "0" suelto del texto que cayo
        junto a la etiqueta. Publicar "0 ambientes" es peor que no publicar
        nada, porque parece un dato verificado.
        """
        crudo = WordPressConnector._campo(texto, etiqueta)
        v = a_entero(crudo)
        return v if v and 1 <= v <= 99 else None
