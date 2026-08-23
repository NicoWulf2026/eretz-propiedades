#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Connector Wasi — plataforma white-label.

Wasi sirve el mismo software bajo el dominio, el logo y los colores de cada
inmobiliaria. El fingerprint que lo reconoce vive en `scripts/wasi_fingerprint`
y no mira el hostname: se apoya en lo que sirve la plataforma, incluido un juego
de scripts que no menciona la marca en ninguna parte.

Lo medido sobre las 39 fuentes del universo:

  - `/sitemap.xml` enumera las fichas. En 34 de 39 alcanza solo, y donde se
    pudo contrastar coincide con recorrer la paginacion entera.
  - Donde no hay sitemap, `/search?...&page=N` pagina de a 12 y termina cuando
    deja de traer ids nuevos.
  - La ficha es `/<slug>/<id>` y ese id es el "Codigo" que la propia ficha
    muestra: sirve de source_listing_id sin fabricar nada.
  - La ficha trae una tabla etiquetada -Area Construida, Dormitorios, Tipo de
    negocio- que se lee del HTML servido. No hace falta navegador.

Dos trampas que costaron encontrar y que este connector evita:

  - La MISMA propiedad se sirve bajo dos slugs con el mismo id
    (/apartamento-venta-moron/5444177 y /departamento-venta-moron/5444177):
    184 casos en 3 fuentes. Como `hash_dedup` lleva la url adentro, entrar por
    un camino en una corrida y por el otro en la siguiente crearia filas
    duplicadas que el indice unico no puede ver. La identidad se toma de la url
    que declara el JSON-LD, que es la misma se entre por donde se entre.
  - El `floorSize` del JSON-LD es la cantidad de PLANTAS, no la superficie. Las
    medidas se leen de la tabla, nunca de ahi.

La API de Wasi existe pero pide `id_company` y `wasi_token`, que el sitio
publico no expone: no hay via gratuita y no se intenta.
"""
from __future__ import annotations

import re
import sys
import urllib.parse
from html import unescape
from pathlib import Path
from typing import Any, Iterator

from .base import (Bloqueado, Connector, ErrorPermanente, ErrorTransitorio,
                   Fuente, PropiedadNormalizada, a_entero, a_numero,
                   detectar_operacion, detectar_tipo, limpiar)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.wasi_fingerprint import (campos_de_ficha, es_ficha,  # noqa: E402
                                      fingerprint, id_de_ficha,
                                      inventario_declarado, url_canonica)

MAX_PAGINAS = 120          # 1.440 avisos: el doble del maximo observado (303)
POR_PAGINA = 12

RE_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")
RE_FOTO = re.compile(r"https://images?\.wasi\.co/[^\"'\s)]+")


class WasiConnector(Connector):
    nombre = "wasi"

    def __init__(self, *a, variantes_soportadas: set[str] | None = None, **kw):
        super().__init__(*a, **kw)
        self.variantes_soportadas = variantes_soportadas or {
            "WASI_SITEMAP", "WASI_PAGINACION"}

    # ------------------------------------------------------------- discover
    @staticmethod
    def _base(url: str) -> str:
        p = urllib.parse.urlparse(url)
        return f"{p.scheme or 'https'}://{p.netloc}"

    def discover(self, fuente: Fuente) -> dict[str, Any]:
        base = self._base(fuente.official_url)
        html = self.descargador.bajar(base)

        fp = fingerprint(html, base)
        plan: dict[str, Any] = {
            "base": base,
            "es_wasi": fp["es_wasi"],
            "confianza": fp["confianza"],
            "senales": fp["senales_fuertes"] or fp["senales_medias"],
            "plan_wasi": fp.get("plan"),
            "build": fp.get("build"),
        }
        if not fp["es_wasi"]:
            # No se fuerza: una fuente que no es Wasi mandada a este connector
            # devuelve cero en silencio, que es la forma mas cara de fallar.
            plan["variante"] = "NO_ES_WASI"
            plan["soportada"] = False
            return plan

        decl = inventario_declarado(html)
        plan["total_declarado"] = decl["total"]
        plan["declarado_por_operacion"] = decl["por_operacion"]

        rutas = self._del_sitemap(base)
        plan["sitemap_fichas"] = len(rutas)
        plan["variante"] = "WASI_SITEMAP" if rutas else "WASI_PAGINACION"
        plan["rutas_sitemap"] = sorted(rutas)
        plan["soportada"] = plan["variante"] in self.variantes_soportadas
        return plan

    def _del_sitemap(self, base: str) -> set[str]:
        try:
            xml = self.descargador.bajar(base + "/sitemap.xml")
        except (ErrorTransitorio, ErrorPermanente, Bloqueado):
            return set()
        return {u for u in RE_LOC.findall(xml) if es_ficha(u)}

    # -------------------------------------------------------- fetch_listing
    def fetch_listing(self, fuente: Fuente, plan: dict[str, Any]) -> Iterator[dict]:
        """Enumera por sitemap y, si hace falta, completa paginando.

        Se rinde por ID, no por url: la misma propiedad aparece bajo dos slugs
        y emitirla dos veces la duplicaria aguas abajo.
        """
        base = plan["base"]
        vistos: set[str] = set()
        estado = self.resume(fuente)

        for u in plan.get("rutas_sitemap") or []:
            pid = id_de_ficha(u)
            if not pid or pid in vistos:
                continue
            vistos.add(pid)
            yield {"source_listing_id": pid, "source_url": u, "pagina": 0}

        declarado = plan.get("total_declarado") or 0
        # El total del menu es una COTA SUPERIOR: suma una vez por operacion,
        # asi que una propiedad publicada en venta y en permuta cuenta dos
        # veces. Se pagina cuando falta bastante, no por no llegar al numero
        # exacto, que a veces es inalcanzable por construccion.
        if vistos and declarado and len(vistos) >= declarado * 0.98:
            estado["completa"] = True
            return

        for pagina in range(1, MAX_PAGINAS + 1):
            url = (f"{base}/search?page={pagina}&for_sale=1&for_rent=1"
                   f"&for_temporary_rent=1&for_transfer=1&lax_business_type=1")
            try:
                html = self.descargador.bajar(url)
            except ErrorPermanente:
                break
            except (ErrorTransitorio, Bloqueado):
                break

            nuevos = 0
            for href in re.findall(r'href="([^"]{4,200})"', html):
                completa = urllib.parse.urljoin(base, unescape(href))
                if not es_ficha(completa):
                    continue
                pid = id_de_ficha(completa)
                if not pid or pid in vistos:
                    continue
                vistos.add(pid)
                nuevos += 1
                yield {"source_listing_id": pid, "source_url": completa,
                       "pagina": pagina}
            estado["ultima_pagina"] = pagina
            # Wasi vuelve a servir la ultima pagina cuando se pide una de mas:
            # cortar por "pagina vacia" daria vueltas hasta el tope.
            if nuevos == 0:
                break
        estado["completa"] = True

    # ------------------------------------------------------------ normalize
    def normalize(self, crudo: dict, fuente: Fuente) -> PropiedadNormalizada | None:
        pedida = crudo["source_url"]
        try:
            html = self.descargador.bajar(pedida)
        except ErrorPermanente:
            return None
        except (ErrorTransitorio, Bloqueado) as e:
            self.anotar_error(fuente, "detalle", e)
            return None

        # La identidad sale de la url que declara la ficha, no de la que se uso
        # para llegar: la misma propiedad se sirve bajo dos slugs.
        url = url_canonica(html, pedida)
        c = campos_de_ficha(html)

        titulo = None
        m = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]{1,250})"', html)
        if m:
            titulo = limpiar(unescape(m.group(1)))
        if not titulo:
            m = re.search(r"<title[^>]*>(.{1,250}?)</title>", html, re.S | re.I)
            titulo = limpiar(unescape(m.group(1))) if m else None

        descripcion = None
        md = re.search(r'"description"\s*:\s*"(.*?)"\s*,\s*"address"', html, re.S)
        if md:
            texto = md.group(1).encode().decode("unicode_escape", "ignore")
            descripcion = limpiar(unescape(re.sub(r"<[^>]+>", " ", texto)))

        lat = lon = None
        mg = re.search(r'"latitude"\s*:\s*"?(-?\d+\.\d+)"?\s*,\s*'
                       r'"longitude"\s*:\s*"?(-?\d+\.\d+)"?', html)
        if mg:
            lat, lon = a_numero(mg.group(1)), a_numero(mg.group(2))

        # Solo las fotos servidas por el CDN de la plataforma.
        imagenes, vistas = [], set()
        for u in RE_FOTO.findall(html):
            limpio = u.split("?")[0]
            if "/empresas/" in limpio:      # el logo de la inmobiliaria
                continue
            if limpio not in vistas:
                vistas.add(limpio)
                imagenes.append(limpio)

        return PropiedadNormalizada(
            canonical_agency_id=fuente.canonical_agency_id,
            source_listing_id=crudo["source_listing_id"],
            source_url=url,
            connector=self.nombre,
            inmobiliaria_id=fuente.inmobiliaria_id,
            titulo=titulo,
            descripcion=descripcion,
            precio=c.get("precio"),
            moneda=c.get("moneda"),
            operacion=detectar_operacion(c.get("operacion")),
            tipo_propiedad=detectar_tipo(c.get("tipo_propiedad")),
            direccion=None,
            barrio=limpiar(c.get("barrio")),
            ciudad=limpiar(c.get("ciudad")),
            provincia=limpiar(c.get("provincia")),
            latitud=lat,
            longitud=lon,
            # Las medidas salen de la tabla. El floorSize del JSON-LD es la
            # cantidad de plantas: leerlo como superficie registraria 2 m2 para
            # un duplex de 84.
            superficie_cubierta=c.get("superficie_cubierta"),
            superficie_total=c.get("superficie_total"),
            dormitorios=a_entero(c.get("dormitorios")),
            banos=a_entero(c.get("banos")),
            ambientes=None,
            imagenes=imagenes,
            extra={k: v for k, v in {
                "codigo_fuente": c.get("codigo"),
                "plantas": c.get("plantas"),
                "superficie_privada": c.get("superficie_privada"),
                "estado_inmueble": c.get("estado"),
                "cocheras": c.get("cocheras"),
                "pais": c.get("pais"),
                "url_enumerada": pedida if pedida != url else None,
                "plan_wasi": None,
            }.items() if v is not None},
        )

    # ------------------------------------------------------------- ubicacion
    def foto_verificable(self) -> bool:
        """El CDN de Wasi no lleva el id de la propiedad en la ruta, asi que no
        se puede probar que una foto sea de ESTA ficha. Decir que si produciria
        miles de falsos positivos y taparia los casos reales."""
        return False
