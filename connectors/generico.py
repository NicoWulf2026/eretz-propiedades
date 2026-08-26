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
import urllib.parse
from html import unescape
from typing import Any, Iterator

from .base import (Bloqueado, Connector, ErrorPermanente, ErrorTransitorio,
                   Fuente, PropiedadNormalizada, a_numero, detectar_moneda,
                   detectar_operacion, detectar_tipo, limpiar)

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
RE_COORD = re.compile(r'"?(?:latitude|lat)"?\s*[:=]\s*"?(-?[23456]\d\.\d{3,})"?'
                      r'.{0,80}?"?(?:longitude|lng|lon)"?\s*[:=]\s*"?(-?[567]\d\.\d{3,})"?',
                      re.S | re.I)

# Evidencia de que una pagina publica UNA propiedad. Se usa solo sobre las urls
# que entraron por la forma verificada de su fuente: la forma dice donde mirar,
# la pagina dice si hay una propiedad. Una nota del blog habla de venta y de
# dormitorios, pero no suele traer un precio con moneda al lado.
RE_OPERACION_TXT = re.compile(r"\b(en venta|en alquiler|venta|alquiler|se vende|"
                              r"se alquila)\b", re.I)
RE_EDITORIAL = re.compile(r'"@type"\s*:\s*"?(Article|NewsArticle|BlogPosting)|'
                          r'property="og:type"\s+content="article"', re.I)
FOTOS_MINIMAS = 3


MAX_SITEMAPS = 25
MAX_FICHAS = 4000


def _texto(html: str) -> str:
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html or "", flags=re.S | re.I)
    t = unescape(t)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", unescape(t).replace("\xa0", " "))


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
    variantes_soportadas = ("SITEMAP", "LISTADO_HTML")

    @staticmethod
    def _patron_de(fuente: Fuente) -> "re.Pattern | None":
        return patron_de_forma((fuente.extra or {}).get("patron_ficha") or "")

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
            fichas += [u for u in locs if self._es_ficha_url(u, propia)]
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
                       if self._es_ficha_url(u, propia)]
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
        enlaces = self._fichas_en(html, base, propia)
        if enlaces:
            plan.update({"variante": "LISTADO_HTML", "soportada": True,
                         "fichas_home": enlaces, "html_home": html})
        return plan

    @staticmethod
    def _es_ficha_url(u: str, propia: "re.Pattern | None" = None) -> bool:
        ruta = urllib.parse.urlparse(u).path
        return bool(RE_FICHA.search(u) or RE_FICHA_RAIZ.search(ruta)
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
            if not (RE_FICHA.search(u) or RE_FICHA_RAIZ.search(ruta)
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
        propia = self._patron_de(fuente)
        if plan["variante"] == "SITEMAP":
            for i, u in enumerate(plan["fichas"], 1):
                yield {"source_listing_id": self._id_de(u), "source_url": u,
                       "pagina": 1 + i // 100,
                       "por_forma": self._solo_por_forma(u, propia)}
            return

        base = plan["base"]
        vistas: set[str] = set()
        pendientes = list(plan.get("fichas_home") or [])
        for u in pendientes:
            c = u.rstrip("/")
            if c in vistas:
                continue
            vistas.add(c)
            yield {"source_listing_id": self._id_de(u), "source_url": u, "pagina": 1,
                   "por_forma": self._solo_por_forma(u, propia)}

        # Paginacion por convencion: /page/N y ?page=N son las dos formas que
        # cubren casi todo. Se corta apenas una no aporta fichas nuevas.
        # La RAIZ tambien puede ser el listado. Una plataforma entera pagina
        # asi -abinmobiliaria.com.ar?page=2- y sin este patron el connector solo
        # veia las 18 fichas de la portada: la fuente tenia 46.
        for patron in ("{b}/propiedades/page/{n}/", "{b}/propiedades?page={n}",
                       "{b}?page={n}"):
            sin_nuevas = 0
            for n in range(2, 60):
                try:
                    html = self.descargador.bajar(patron.format(b=base, n=n))
                except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                    break
                nuevas = 0
                for u in self._fichas_en(html, base, propia):
                    c = u.rstrip("/")
                    if c in vistas:
                        continue
                    vistas.add(c)
                    nuevas += 1
                    yield {"source_listing_id": self._id_de(u), "source_url": u,
                           "pagina": n, "por_forma": self._solo_por_forma(u, propia)}
                if nuevas == 0:
                    sin_nuevas += 1
                    if sin_nuevas >= 2:
                        break
                else:
                    sin_nuevas = 0
            if len(vistas) > len(pendientes):
                break

    @staticmethod
    def _id_de(url: str) -> str:
        """Id de la plataforma si lo hay; si no, el slug. Nunca un hash propio:
        tiene que poder rastrearse hasta la ficha de origen."""
        ruta = urllib.parse.urlparse(url).path.rstrip("/")
        ultimo = ruta.rsplit("/", 1)[-1] if "/" in ruta else ruta
        m = re.search(r"(\d{3,})", ultimo)
        return m.group(1) if m else (ultimo or url)[:120]

    # --------------------------------------------------------------- normalize
    def normalize(self, crudo: dict, fuente: Fuente) -> PropiedadNormalizada | None:
        url = crudo["source_url"]
        try:
            html = self.descargador.bajar(url)
        except ErrorPermanente:
            return None
        except (ErrorTransitorio, Bloqueado) as e:
            self.anotar_error(fuente, "detalle", e)
            return None
        if not html or len(html) < 400:
            return None

        texto = _texto(html)
        datos = self._de_json_ld(html)

        titulo = datos.get("titulo")
        if not titulo:
            m = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]{1,200})"', html)
            titulo = limpiar(unescape(m.group(1))) if m else None
        if not titulo:
            m = re.search(r"<title[^>]*>(.{1,200}?)</title>", html, re.S | re.I)
            titulo = limpiar(unescape(m.group(1))) if m else None

        descripcion = datos.get("descripcion")
        if not descripcion:
            m = re.search(r'<meta[^>]+(?:name|property)="(?:og:)?description"'
                          r'[^>]+content="([^"]{20,600})"', html)
            descripcion = limpiar(unescape(m.group(1))) if m else None

        precio, moneda = datos.get("precio"), datos.get("moneda")
        if precio is None:
            # Solo con moneda explicita al lado. Un numero suelto en el texto
            # puede ser cualquier cosa, y un precio equivocado se publica sin
            # que nadie lo note.
            m = re.search(r"(USD|U\$S|US\$|\$|ARS)\s*([\d][\d.,]{2,15})", texto)
            if m:
                moneda = moneda or detectar_moneda(m.group(1))
                precio = a_numero(m.group(2))

        imagenes, vistas = [], set()
        for u in (datos.get("imagenes") or []) + RE_IMG.findall(html):
            u = u.split("?")[0]
            if u in vistas or re.search(r"(logo|placeholder|avatar|icon|sprite|banner)",
                                        u, re.I):
                continue
            vistas.add(u)
            imagenes.append(u)

        if crudo.get("por_forma") and not self._confirma_ficha(
                html, texto, precio, imagenes):
            self.descartadas_por_forma = getattr(self, "descartadas_por_forma", 0) + 1
            # Entro por la forma y la pagina no muestra una propiedad. Se
            # descarta en silencio: no es un error de la fuente ni del
            # connector, es la forma alcanzando una pagina que no era ficha.
            return None

        lat, lon = datos.get("lat"), datos.get("lon")
        if lat is None:
            m = RE_COORD.search(html)
            if m:
                lat, lon = float(m.group(1)), float(m.group(2))

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
            direccion=datos.get("direccion"),
            barrio=None,
            ciudad=datos.get("ciudad"),
            provincia=datos.get("provincia"),
            latitud=lat,
            longitud=lon,
            dormitorios=self._cuenta(texto, r"dormitorios?|habitaciones?", datos.get("dorm")),
            banos=self._cuenta(texto, r"ba[nñ]os?", datos.get("banos")),
            ambientes=self._cuenta(texto, r"ambientes?", None),
            superficie_total=datos.get("sup_total") or self._sup(texto, r"total|terreno"),
            superficie_cubierta=datos.get("sup_cubierta") or self._sup(texto, r"cubiert|construid"),
            imagenes=imagenes[:40],
            extra={k: v for k, v in {"via": datos.get("via") or "html",
                                     "tipo_ld": datos.get("tipo_ld")}.items() if v},
            inmobiliaria_id=fuente.inmobiliaria_id,
            provenance={"connector": self.nombre,
                        "official_domain": f"{urllib.parse.urlparse(url).scheme}://"
                                           f"{urllib.parse.urlparse(url).netloc}",
                        "agency_name": fuente.agency_name,
                        "canonical_agency_id": fuente.canonical_agency_id,
                        "source_platform": "SITIO_PROPIO",
                        "pagina_listado": crudo.get("pagina")},
        )

    @staticmethod
    def _confirma_ficha(html: str, texto: str, precio, imagenes: list) -> bool:
        """La pagina publica una propiedad: precio con moneda, operacion y fotos.

        Es el mismo criterio con el que se verificaron las formas antes de
        habilitarlas, aplicado ahora ficha por ficha.
        """
        if RE_EDITORIAL.search(html or ""):
            return False
        return (precio is not None
                and bool(RE_OPERACION_TXT.search(texto or ""))
                and len(imagenes) >= FOTOS_MINIMAS)

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
                dato = json.loads(bloque.strip())
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
        m = re.search(rf"(\d{{1,2}})\s*(?:{etiqueta})", texto, re.I) or \
            re.search(rf"(?:{etiqueta})\s*:?\s*(\d{{1,2}})", texto, re.I)
        if not m:
            return None
        n = int(m.group(1))
        return n if 1 <= n <= 99 else None

    @staticmethod
    def _sup(texto: str, etiqueta: str) -> float | None:
        m = re.search(rf"(?:{etiqueta})[^\d]{{0,18}}([\d.,]{{2,9}})\s*m", texto, re.I) or \
            re.search(rf"([\d.,]{{2,9}})\s*m[²2]\s*(?:{etiqueta})", texto, re.I)
        if not m:
            return None
        v = a_numero(m.group(1))
        return v if v and 5 <= v <= 100_000 else None
