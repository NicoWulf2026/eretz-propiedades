# -*- coding: utf-8 -*-
"""Lote 5d de `generico` (2026-09-25), dos casos medidos en los paquetes:

- `forchino`: 19 fichas reales (precio, operacion, 20 fotos) rechazadas por
  forma: las fotos solo estan como enlace del visor
  (`<a href="fotos/imagen_…jpeg" class="popup-image">`) y como
  `background-image`; el `<img>` del carrusel esta comentado.
- `fernandez marull` y `crestale`: 59 enlaces señuelo de Cloudflare
  (`/cdn-cgi/content?id=…`, articulos inventados para bots) enumerados como
  fichas.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from connectors import base as B  # noqa: E402
from connectors.generico import GenericoConnector  # noqa: E402

URL = "https://alfa.test/propiedad.php?id=410"
RELLENO = "<p>" + "Contacto, horarios y redes de la inmobiliaria. " * 12 + "</p>"


class Falso(B.Descargador):
    def __init__(self, html: str):
        super().__init__(B.LimitadorDeRitmo(0.0))
        self.html = html

    def bajar(self, url: str) -> str:
        return self.html


def _normalizar(html: str):
    c = GenericoConnector(descargador=Falso(html))
    f = B.Fuente(canonical_agency_id="roomix:alfa propiedades", agency_name="Alfa Propiedades",
                 official_url="https://alfa.test/", inmobiliaria_id=1)
    return c.normalize({"source_url": URL, "source_listing_id": "410", "por_forma": True}, f)


def _ficha(fotos: str) -> str:
    return ("<html><body><main><h1>Departamento en venta en Rosario</h1>"
            "<p>Venta. 2 dormitorios, 1 baño, cochera. Precio USD 135.000</p>"
            f"{fotos}{RELLENO}</main></body></html>")


VISOR = "".join(f'<a href="fotos/imagen_2026_{i}.jpeg" class="gal-link popup-image"></a>'
                for i in range(1, 6))


def test_MUERDE_las_fotos_que_solo_estan_en_el_visor_confirman_la_ficha():
    p = _normalizar(_ficha('<img src="img/logo.png">' + VISOR))
    assert p is not None
    assert "https://alfa.test/fotos/imagen_2026_3.jpeg" in p.imagenes


def test_con_fotos_propias_el_visor_no_agrega_duplicados():
    propias = "".join(f'<img src="fotos/chica_{i}.jpg">' for i in range(1, 5))
    grandes = "".join(f'<a href="fotos/grande_{i}.jpg"></a>' for i in range(1, 5))
    p = _normalizar(_ficha(propias + grandes))
    assert p is not None
    assert not any("grande_" in u for u in p.imagenes)


def test_un_enlace_que_no_es_imagen_no_es_foto():
    enlaces = "".join(f'<a href="propiedad.php?id={i}">ver</a>' for i in range(5))
    assert _normalizar(_ficha(enlaces)) is None


def test_MUERDE_un_enlace_senuelo_de_cloudflare_no_es_ficha():
    """Entraban por las tarjetas recuperadas, que no preguntan la forma."""
    senuelo = "/cdn-cgi/content?id=C77_YNYOi.UtOHVmrAOlPwVNJgTtcrdBH3XLMAZG79o-1790342374.7814023"
    html = ('<html><body>'
            f'<div class="property-card"><a href="{senuelo}">Chronobiology: The Rhythms of Life</a></div>'
            '<div class="property-card"><a href="/propiedad/casa-en-venta-en-rosario-123">'
            'Casa en venta</a></div></body></html>')
    fichas = GenericoConnector._fichas_en(html, "https://alfa.test/propiedades")
    assert not any("/cdn-cgi/" in u for u in fichas)
    assert "https://alfa.test/propiedad/casa-en-venta-en-rosario-123" in fichas


def test_un_compartir_con_la_foto_en_la_query_no_es_foto():
    compartir = "".join(
        f'<a href="https://pinterest.com/pin/create/button/?media=https://alfa.test/f{i}.jpg">p</a>'
        for i in range(5))
    assert _normalizar(_ficha(compartir)) is None


# --- ambientes que la ficha solo dice en el titulo ---------------------------
# 156 fichas `generico` en 21 agencias (`bardi` 40, `blanco` 33): «Casa de 5
# Ambientes en Remedios de Escalada.» y el cuerpo rotula dormitorios y banos
# pero no ambientes. Las 46 que discrepan con el cuerpo son titulos de varias
# unidades («Casa de 3 amb. + depto. de 2 amb.»): ahi el cuerpo suma y manda.

def _ficha_titulo(titulo: str, cuerpo: str = "") -> str:
    # El titulo fuera del cuerpo principal, como en `bardi`.
    return (f"<html><body><header><h1>{titulo}</h1></header><main>"
            "<p>Venta. Precio USD 260.000</p>"
            '<div><p class="text-sm">Baños</p><p class="text-sm">3</p></div>'
            '<div><p class="text-sm">Dormitorios</p><p class="text-sm">3</p></div>'
            f"{cuerpo}"
            f"{VISOR}{RELLENO}</main></body></html>")


def test_MUERDE_los_ambientes_del_titulo_cuando_el_cuerpo_no_los_dice():
    p = _normalizar(_ficha_titulo("Casa de 5 Ambientes en Remedios de Escalada."))
    assert p.ambientes == 5


def test_el_cuerpo_manda_sobre_el_titulo():
    p = _normalizar(_ficha_titulo(
        "Casa de 5 Ambientes", '<div><p class="text-sm">Ambientes</p><p class="text-sm">4</p></div>'))
    assert p.ambientes == 4


def test_un_titulo_de_varias_unidades_no_dice_los_ambientes():
    for titulo in ("Casa de 3 amb. + depto. de 2 amb. en venta",
                   "Casa de 3 amb. con monoambiente en venta",
                   "2 casas de 4 y 5 amb. en venta",
                   "Edificio en block de 3 ambientes"):
        assert _normalizar(_ficha_titulo(titulo)).ambientes is None, titulo


def test_MUERDE_addressNeighborhood_llega_como_barrio_para_que_la_geografia_decida():
    """`fenix`: addressLocality «Capital» (departamento), addressNeighborhood
    «Posadas» (localidad). Sin leer el barrio, la geografia no tenia con que."""
    import json as _json
    ld = {"@context": "https://schema.org", "@type": "Residence", "name": "Casa en venta",
          "address": {"@type": "PostalAddress", "addressLocality": "Capital",
                      "addressRegion": "Misiones", "addressNeighborhood": "Posadas"}}
    html = ('<html><head><script type="application/ld+json">' + _json.dumps(ld) +
            '</script></head><body><main><h1>Casa en venta</h1>'
            '<p>Venta. 3 dormitorios, 2 baños. Precio USD 100.000</p>' + VISOR + RELLENO +
            '</main></body></html>')
    p = _normalizar(html)
    assert (p.ciudad, p.barrio, p.provincia) == ("Capital", "Posadas", "Misiones")


def test_un_barrio_que_repite_la_ciudad_no_se_afirma():
    import json as _json
    ld = {"@type": "Residence", "name": "Casa", "address": {
        "addressLocality": "Rosario", "addressRegion": "Santa Fe", "addressNeighborhood": "Rosario"}}
    html = ('<html><head><script type="application/ld+json">' + _json.dumps(ld) +
            '</script></head><body><main><h1>Casa en venta</h1>'
            '<p>Venta. 3 dormitorios. Precio USD 100.000</p>' + VISOR + RELLENO +
            '</main></body></html>')
    assert _normalizar(html).barrio is None
