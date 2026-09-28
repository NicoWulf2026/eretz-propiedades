# -*- coding: utf-8 -*-
"""Lote `generico` del 2026-09-28, medido contra la fuente.

- `matias sosa` (plantilla Coding & Company): cierra todo con espacio
  -`</h1 >`, `</h6 >`- y cada regla escrita contra `</h1>` quedaba ciega:
  titulo del `<title>` del sitio, descripcion del meta («A custom site made by
  Coding & Company») y 14 fotos de «Otras propiedades» -tarjetas vecinas al
  azar- en la galeria (36 de 42 fichas no idempotentes).
- «13.00m² semicubiertos 71.00m² totales»: el numero que sigue a
  «semicubiertos» se leia como superficie cubierta.
- `guillermo rodriguez`: la galeria es solo `background-image` en un `style`
  (240 fichas descartadas por forma) y el titulo «Inmobiliaria | Guillermo
  Rodriguez» no se reconocia como el del sitio, asi que 9 categorias
  `propiedades.php?tipo=N` se guardaban como propiedades.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from connectors import base as B  # noqa: E402
from connectors.generico import (ETIQUETA_SUP_CUBIERTA, GenericoConnector,  # noqa: E402
                                 con_cierres_normales, cuerpo_principal)

URL = "https://alfa.test/propiedad/7623"
FOTO = "https://static.tokkobroker.com/dev_pictures/72197_propia.jpg"
VECINA = "https://static.tokkobroker.com/pictures/8700296_vecina.jpg"


class Falso(B.Descargador):
    def __init__(self, html: str):
        super().__init__(B.LimitadorDeRitmo(0.0))
        self.html = html

    def bajar(self, url: str) -> str:
        return self.html


def _ficha() -> str:
    return (
        "<html><head><title>Alfa - Venta y Alquiler de Propiedades - Home</title>"
        '<meta name="description" content="A custom site made by Coding &amp; Company">'
        "</head><body><main>"
        '<h1 class="text_white">\n    Departamento en venta en Plaza Mitre, Mar Del Plata\n</h1 >'
        '<h2 class="text_white">\n    USD 173.500\n</h2 >'
        f'<div class="property_carousel"><a href="{FOTO}"><img src="{FOTO}" /></a></div>'
        '<p class="text_light_silver">\n    Departamento\n</p >'
        '<h6 class="text_primarycolor">\n    Descripci&oacute;n\n</h6 ><hr />'
        '<div class="property_description"><p>Departamento 2 ambientes ubicado en La Rioja '
        "2813 dentro del edificio Linehouse. Living comedor con balcon y parrilla, cocina "
        "integrada, bano de servicio y habitacion en suite con placard.</p></div>"
        '<div class="featured_section_title"><h5 class="text_primarycolor">\n'
        "    Otras propiedades\n</h5 ></div>"
        f'<a class="card_link"><div class="card_image"><img src="{VECINA}" /></div>'
        "<h4>Bolivar 3342</h4><p>USD 99.000</p><p>3 ambientes</p></a>"
        "</main></body></html>")


def _normalizar(html: str):
    c = GenericoConnector(descargador=Falso(html))
    f = B.Fuente(canonical_agency_id="roomix:alfa propiedades", agency_name="Alfa Propiedades",
                 official_url="https://alfa.test/", inmobiliaria_id=1)
    return c.normalize({"source_url": URL, "source_listing_id": "7623"}, f)


def test_un_cierre_con_espacio_es_un_cierre():
    assert con_cierres_normales("<h1 >T</h1 ><p>x</p\t>") == "<h1 >T</h1><p>x</p>"
    # Solo cierres: una apertura con atributos no se toca.
    assert con_cierres_normales('<a href="/x" >y</a>') == '<a href="/x" >y</a>'


def test_MUERDE_otras_propiedades_como_encabezado_corta_la_ficha():
    principal = cuerpo_principal(_ficha())
    assert FOTO in principal
    assert VECINA not in principal and "Bolivar 3342" not in principal


def test_MUERDE_la_plantilla_con_cierres_con_espacio_se_lee_entera():
    p = _normalizar(_ficha())
    assert p is not None
    assert p.titulo == "Departamento en venta en Plaza Mitre, Mar Del Plata"
    assert p.descripcion and p.descripcion.startswith("Departamento 2 ambientes ubicado")
    assert FOTO in p.imagenes
    assert VECINA not in p.imagenes
    assert p.precio == 173500 and p.moneda == "USD"


def test_MUERDE_semicubierta_no_es_la_cubierta():
    texto = "Detalles 13.00m 2 semicubiertos 71.00m 2 totales 58m 2 cubiertos Entrega"
    assert GenericoConnector._sup(texto, ETIQUETA_SUP_CUBIERTA) != 71
    assert GenericoConnector._sup("Sup. cubierta: 80 m2", ETIQUETA_SUP_CUBIERTA) == 80
    assert GenericoConnector._sup("Superficie construida 95 m²", ETIQUETA_SUP_CUBIERTA) == 95
    assert GenericoConnector._sup("Sup. semicubierta: 20 m2", ETIQUETA_SUP_CUBIERTA) is None


# `guillermo rodriguez`: 240 fichas reales descartadas por forma (galeria solo
# como fondo CSS) y sus categorias guardadas como propiedades.

def _fuente_gr():
    return B.Fuente(canonical_agency_id="roomix:guillermo rodriguez inmobiliaria",
                    agency_name="Guillermo Rodriguez Inmobiliaria",
                    official_url="https://gr.test/", inmobiliaria_id=1)


def test_MUERDE_el_nombre_repartido_entre_tramos_es_el_titulo_del_sitio():
    f = _fuente_gr()
    assert GenericoConnector._es_titulo_del_sitio("Inmobiliaria | Guillermo Rodriguez", f)
    assert GenericoConnector._es_titulo_del_sitio("Guillermo Rodriguez Inmobiliaria - Inicio", f)
    assert not GenericoConnector._es_titulo_del_sitio("Nansen 432 | Guillermo Rodriguez", f)
    assert not GenericoConnector._es_titulo_del_sitio("Inmobiliaria", f)


def test_MUERDE_la_galeria_como_fondo_css_son_fotos():
    html = ('<div class="owl-carousel">'
            '<div class="item" style="background-image: url(resource2.php/crop/'
            'inmuebles_imagenes/whatsapp-image-2026-09-16-at-11-12-51-14.jpg);"></div>'
            "<div class=\"item\" style='background: url(&quot;fotos/b.webp&quot;) center'></div>"
            '<div class="item" style="background-image: url(/img/sin-extension)"></div></div>')
    fotos = GenericoConnector._fotos_de_enlaces(html, "https://gr.test/detalles.php?id=1451")
    assert fotos == [
        "https://gr.test/resource2.php/crop/inmuebles_imagenes/"
        "whatsapp-image-2026-09-16-at-11-12-51-14.jpg",
        "https://gr.test/fotos/b.webp"]


def test_el_fondo_de_una_hoja_de_estilos_no_es_foto():
    html = "<style>.banner{background-image:url(img/banner.jpg)}</style><p>x</p>"
    assert GenericoConnector._fotos_de_enlaces(html, "https://gr.test/x") == []


def _con_candidatas(urls):
    c = GenericoConnector(descargador=Falso(""))
    c._candidatas = lambda fuente, plan: iter(
        [{"source_listing_id": u.rsplit("=", 1)[-1], "source_url": u, "pagina": 1} for u in urls])
    return c


def test_MUERDE_la_misma_ficha_con_el_contexto_del_listado_entra_una_vez():
    base = "https://gr.test/detalles.php?id="
    c = _con_candidatas([base + "1449&tipo=25&operacion=0", base + "1449",
                         base + "1450&tipo=25&operacion=0", base + "939"])
    urls = [i["source_url"] for i in c.fetch_listing(_fuente_gr(), {})]
    # La larga de 1449 sobra (la corta esta); la de 1450 es la unica forma.
    assert urls == [base + "1449", base + "1450&tipo=25&operacion=0", base + "939"]
    assert c.duplicados_origen == 1


def test_parametros_que_identifican_no_son_contexto():
    c = _con_candidatas(["https://a.test/ficha.php?id=8323&op=V",
                         "https://a.test/ficha.php?id=8323&op=A"])
    assert len(list(c.fetch_listing(_fuente_gr(), {}))) == 2


def test_MUERDE_la_navegacion_entre_entradas_no_es_la_ficha():
    """`mattioli` (wpcasa): «← …DEPTO DOS AMBIENTES | OPORTUNIDAD!!! Depto 4
    Amb. →» son los titulos de las fichas vecinas, debajo de un lote."""
    html = ("<h1>VENTA DE LOTE</h1><p>Lote de 10 x 30.</p>"
            '<div class="post-navigation clearfix"><div class="previous">'
            '<a href="/listing/1292/">&larr; DEPTO DOS AMBIENTES</a></div>'
            '<div class="next"><a href="/listing/1222/">Depto 4 Amb. &rarr;</a></div></div>')
    principal = cuerpo_principal(html)
    assert "Lote de 10 x 30" in principal and "4 Amb" not in principal
