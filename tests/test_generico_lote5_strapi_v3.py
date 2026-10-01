"""Lote 5 (LOCAL, 2026-10-01): Strapi v3 propio en `api.` (`paladino`).

Las 43 fichas del sitemap (/inmueble/<slug>) eran cascarones Next.js: 43 de 43
«ficha sin contenido». El sitio las llena desde su API publica sin clave.
Fixture: tests/fixtures/cloud_bridge/paladino/ (respuesta real recortada).
"""
from __future__ import annotations

import json
from pathlib import Path

from connectors.base import Fuente
from connectors.generico import GenericoConnector as G

OBJETOS = json.loads((Path(__file__).parent / "fixtures" / "cloud_bridge" / "paladino"
                      / "inmuebles_strapi_v3.json").read_text(encoding="utf-8"))
CASCARON = ('<html><head><script src="/_next/static/chunks/app/page-9d5f.js"></script></head>'
            "<body><nav>Inicio Inmuebles Emprendimientos Novedades Contacto</nav>"
            "<div id='__next'>" + "<div class='skeleton'></div>" * 30 + "Paladino Propiedades</div>"
            "<footer>Paladino Propiedades - Villa Carlos Paz - Cordoba</footer></body></html>")


class Sitio:
    def __init__(self, objetos, mostrar_api=True):
        self.objetos, self.mostrar_api, self.pedidos = objetos, mostrar_api, []

    def bajar(self, url, *a, **k):
        self.pedidos.append(url)
        if url.endswith(".js"):
            return 'fetch("https://api.paladinopropiedades.com.ar/inmuebles")' if self.mostrar_api else "x"
        if url.endswith("/inmuebles/count"):
            return str(len(self.objetos))
        if "/inmuebles?slug=" in url:
            slug = url.split("slug=")[1].split("&")[0]
            return json.dumps([o for o in self.objetos if o.get("slug") == slug])
        return CASCARON

    def __getattr__(self, nombre):
        return lambda *a, **k: None


def _normalizar(sitio, slug):
    return G(descargador=sitio).normalize(
        {"source_url": f"https://paladinopropiedades.com.ar/inmueble/{slug}", "source_listing_id": slug},
        Fuente(canonical_agency_id="roomix:paladino propiedades", agency_name="Paladino",
               official_url="https://paladinopropiedades.com.ar"))


def test_la_ficha_cascaron_se_arma_con_el_objeto_de_la_api():
    objeto = OBJETOS[0]
    p = _normalizar(Sitio(OBJETOS), objeto["slug"])
    assert p is not None and p.titulo == objeto["nombre"]
    assert (p.precio, p.moneda) == (float(objeto["precio_ref"]["valor"]), "USD")
    assert p.dormitorios == objeto["habitaciones"] and p.banos == objeto["banos"]
    assert p.imagenes and all(u.startswith("https://api.paladinopropiedades.com.ar/uploads/")
                              for u in p.imagenes)
    assert p.extra.get("strapi_version") == 3


def test_precio_oculto_no_se_publica():
    objeto = json.loads(json.dumps(OBJETOS[0]))
    objeto["precio_ref"]["mostrar"] = False
    p = _normalizar(Sitio([objeto]), objeto["slug"])
    assert p is not None and p.precio is None and p.moneda is None


def test_sin_api_en_el_javascript_propio_no_se_inventa_nada():
    p = _normalizar(Sitio(OBJETOS, mostrar_api=False), OBJETOS[0]["slug"])
    assert p is None or p.titulo != OBJETOS[0]["nombre"]


def test_la_api_se_descubre_una_vez_por_host():
    sitio = Sitio(OBJETOS)
    g = G(descargador=sitio)
    fuente = Fuente(canonical_agency_id="roomix:paladino propiedades", agency_name="Paladino",
                    official_url="https://paladinopropiedades.com.ar")
    for o in OBJETOS:
        g.normalize({"source_url": f"https://paladinopropiedades.com.ar/inmueble/{o['slug']}",
                     "source_listing_id": o["slug"]}, fuente)
    assert sum(1 for u in sitio.pedidos if u.endswith("/count")) == 1
