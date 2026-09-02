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


def _campos_wasi(html: str) -> dict[str, Any]:
    """Compatibilidad con etiquetas singulares y mojibake del HTML Wasi."""
    compatible = (html or "").replace("Ba�o:", "Banos:")
    compatible = compatible.replace("Baño:", "Banos:")
    compatible = compatible.replace("N�mero de planta:", "Numero de plantas:")
    compatible = compatible.replace("Número de planta:", "Numero de plantas:")
    return campos_de_ficha(compatible)


def _descripcion_wasi(html: str) -> str | None:
    match = re.search(r'"description"\s*:\s*"(.*?)"\s*,\s*"address"',
                      html or "", re.S)
    if not match:
        return None
    texto = match.group(1).encode().decode("unicode_escape", "ignore")
    return limpiar(unescape(re.sub(r"<[^>]+>", " ", texto)))


def _numeros_descriptivos(texto: str, etiqueta: str) -> list[float]:
    hallados: dict[tuple[int, int], float] = {}
    for patron in (rf"\b(\d{{1,2}})\s*(?:{etiqueta})\b",
                   rf"\b(?:{etiqueta})\s*:?\s*(\d{{1,2}})\b"):
        for match in re.finditer(patron, texto or "", re.I):
            valor = a_numero(match.group(1))
            if valor and 1 <= valor <= 99:
                hallados[match.span()] = valor
    return list(hallados.values())


def _medidas_descriptivas(texto: str, patrones: tuple[str, ...]) -> list[float]:
    valores: list[float] = []
    for patron in patrones:
        for match in re.finditer(patron, texto or "", re.I):
            valor = a_numero(match.group(1))
            if valor and 5 <= valor <= 100_000:
                valores.append(valor)
    return valores


def _campos_descriptivos(texto: str | None,
                         tipo_propiedad: str | None) -> tuple[dict[str, float], set[str]]:
    """Valores escalares inequivocos de la descripcion y rechazos explicitos."""
    texto = texto or ""
    encontrados: dict[str, float] = {}
    ambiguos: set[str] = set()
    etiquetas = {
        "ambientes": r"ambientes?",
        "dormitorios": r"dormitorios?|habitaciones?",
        "banos": r"ba(?:n|ñ|�)os?|toilettes?",
    }
    for campo, etiqueta in etiquetas.items():
        valores = _numeros_descriptivos(texto, etiqueta)
        if not valores:
            continue
        if tipo_propiedad == "terreno" or len(valores) != 1:
            ambiguos.add(campo)
        else:
            encontrados[campo] = valores[0]

    medidas = {
        "superficie_total": _medidas_descriptivas(texto, (
            r"superficie\s+(?:de\s+)?terreno\s*:?\s*([\d.,]+)\s*(?:m2|m²|mtrs?|metros?)",
            r"\bterreno\s+(?:de\s+)?([\d.,]+)\s*(?:m2|m²|mtrs?|metros?)",
            r"\blote\s+de\s+([\d.,]+)\s*(?:m2|m²|mtrs?|metros?)",
            r"([\d.,]+)\s*(?:m2|m²|mtrs?|metros?)\s+totales\b",
        )),
        "superficie_cubierta": _medidas_descriptivas(texto, (
            r"superficie(?:\s+total)?\s+cubierta\s*:?\s*([\d.,]+)\s*(?:m2|m²|mtrs?|metros?)",
            r"([\d.,]+)\s*(?:m2|m²|mtrs?|metros?)\s+cubiert[oa]s?\b",
            r"\bconstruidos?\s*:?\s*([\d.,]+)\s*(?:m2|m²|mtrs?|metros?)",
        )),
    }
    for campo, valores in medidas.items():
        unicos = set(valores)
        if len(unicos) == 1:
            encontrados[campo] = next(iter(unicos))
        elif unicos:
            ambiguos.add(campo)
    return encontrados, ambiguos


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
        # La suma del menu es una COTA SUPERIOR inalcanzable: cuenta una vez por
        # operacion, asi que una propiedad en venta y en permuta figura dos
        # veces. Verificado en jorgeorellano.com -venta 238 + alquiler 23 +
        # permuta 2 = 263, lo que declara el menu, mientras los ids unicos son
        # 261 porque las 2 de permuta estan tambien en venta-.
        #
        # Como objetivo de cobertura se usa la operacion mas grande, que si es
        # una cota INFERIOR real: dentro de una operacion cada propiedad aparece
        # una sola vez, asi que el total unico nunca puede ser menor. Con la
        # suma como objetivo, tres fuentes enteras quedaban marcadas
        # ENUMERACION_INCOMPLETA teniendo todo su inventario.
        plan["total_declarado"] = max(decl["por_operacion"].values(), default=0) or None
        plan["total_declarado_menu"] = decl["total"]
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

        # Para decidir SI PAGINAR se usa la cota SUPERIOR -la suma del menu-:
        # conviene ser exhaustivo aunque ese numero sea inalcanzable. La cota
        # inferior se usa despues, para juzgar la cobertura.
        declarado = plan.get("total_declarado_menu") or 0
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
        c = _campos_wasi(html)

        titulo = None
        m = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]{1,250})"', html)
        if m:
            titulo = limpiar(unescape(m.group(1)))
        if not titulo:
            m = re.search(r"<title[^>]*>(.{1,250}?)</title>", html, re.S | re.I)
            titulo = limpiar(unescape(m.group(1))) if m else None

        descripcion = _descripcion_wasi(html)
        tipo_propiedad = detectar_tipo(c.get("tipo_propiedad"))
        descriptivos, ambiguos = _campos_descriptivos(descripcion, tipo_propiedad)

        def campo_numerico(nombre: str) -> Any:
            return c.get(nombre) if c.get(nombre) is not None else descriptivos.get(nombre)

        lat = lon = None
        mg = re.search(r'"latitude"\s*:\s*"?(-?\d+\.\d+)"?\s*,\s*'
                       r'"longitude"\s*:\s*"?(-?\d+\.\d+)"?', html)
        if mg:
            lat, lon = a_numero(mg.group(1)), a_numero(mg.group(2))

        # Solo las fotos servidas por el CDN de la plataforma.
        imagenes, vistas = [], set()
        for u in RE_FOTO.findall(html):
            limpio = u.split("?")[0]
            # El CDN separa por carpeta lo que no es la propiedad: /empresas/
            # es el logo, /perfiles/ la foto del asesor y /publicidad/ un
            # banner. Aparecian hasta en 261 fichas de la misma inmobiliaria.
            if any(x in limpio for x in ("/empresas/", "/perfiles/", "/publicidad/")):
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
            tipo_propiedad=tipo_propiedad,
            direccion=None,
            barrio=limpiar(c.get("barrio")),
            ciudad=limpiar(c.get("ciudad")),
            provincia=limpiar(c.get("provincia")),
            latitud=lat,
            longitud=lon,
            # Las medidas salen de la tabla. El floorSize del JSON-LD es la
            # cantidad de plantas: leerlo como superficie registraria 2 m2 para
            # un duplex de 84.
            superficie_cubierta=campo_numerico("superficie_cubierta"),
            superficie_total=campo_numerico("superficie_total"),
            dormitorios=a_entero(campo_numerico("dormitorios")),
            banos=a_entero(campo_numerico("banos")),
            ambientes=a_entero(campo_numerico("ambientes")),
            imagenes=imagenes,
            extra={k: v for k, v in {
                "codigo_fuente": c.get("codigo"),
                "plantas": c.get("plantas"),
                "superficie_privada": c.get("superficie_privada"),
                "estado_inmueble": c.get("estado"),
                "cocheras": c.get("cocheras"),
                "pais": c.get("pais"),
                "url_enumerada": pedida if pedida != url else None,
                "atributos_descartados": ",".join(sorted(ambiguos)) or None,
            }.items() if v is not None},
            # La resolucion de conflictos entre inmobiliarias lee
            # `provenance.agency_name` para saber quien publica un aviso. Sin
            # esto, cualquier url reclamada por dos agencias quedaria
            # AMBIGUOUS teniendo la respuesta al lado.
            provenance={"connector": self.nombre,
                        "official_domain": self._base(fuente.official_url),
                        "agency_name": fuente.agency_name,
                        "canonical_agency_id": fuente.canonical_agency_id,
                        "source_platform": "WASI",
                        "pagina_listado": crudo.get("pagina")},
        )

    # ------------------------------------------------------------- ubicacion
    def foto_verificable(self) -> bool:
        """El CDN de Wasi no lleva el id de la propiedad en la ruta, asi que no
        se puede probar que una foto sea de ESTA ficha. Decir que si produciria
        miles de falsos positivos y taparia los casos reales."""
        return False
