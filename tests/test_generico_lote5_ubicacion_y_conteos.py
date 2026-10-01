"""Lote 5 (LOCAL, 2026-10-01): ubicacion junto al icono, pareja numero->rotulo y «Cuartos de baño».

Medido sobre los paquetes: 1.112 fichas de 48 agencias generico/wordpress sin
ciudad; baños sin leer en 91 (57 de `b b administracion`). Cada caso sale de
una ficha real (fixtures en tests/fixtures/cloud_bridge/ o su estructura
minima copiada del sitio).
"""
from __future__ import annotations

from pathlib import Path

from connectors.base import Fuente
from connectors.generico import ETIQUETAS_DE_CONTEO, GenericoConnector as G

FIX = Path(__file__).parent / "fixtures" / "cloud_bridge"
BANOS, DORM = ETIQUETAS_DE_CONTEO["banos"], ETIQUETAS_DE_CONTEO["dormitorios"]


def _normalizar(html: str, url: str):
    class Fijo:
        def bajar(self, *a, **k):
            return html

        def __getattr__(self, nombre):
            return lambda *a, **k: None

    base = url.split("/")[0] + "//" + url.split("/")[2] + "/"
    return G(descargador=Fijo()).normalize(
        {"source_url": url, "source_listing_id": "1"},
        Fuente(canonical_agency_id="roomix:prueba", agency_name="prueba", official_url=base))


def test_martelliti_la_linea_del_icono_es_la_ubicacion_de_la_propiedad():
    html = (FIX / "martelliti" / "ficha_1.html").read_text(encoding="utf-8")
    assert G._linea_de_ubicacion(html).startswith("Laprida 1835")


def test_martelliti_el_pie_es_la_oficina_y_no_se_lee():
    html = (FIX / "martelliti" / "pie_oficina.html").read_text(encoding="utf-8")
    assert G._linea_de_ubicacion("<footer>" + html + "</footer>") is None


def test_la_oficina_enlazada_a_google_maps_no_es_la_ubicacion():
    # `agostina saracena` (Bricks): barra superior con la oficina enlazada y,
    # debajo del titulo, la ubicacion de la ficha con el mismo icono.
    html = """<div class="brxe-block"><a class="brxe-text-link" href="https://maps.app.goo.gl/x">
      <span class="icon"><i class="fas fa-location-dot"></i></span>
      <span class="text">18 de Diciembre 1816, San Martín - Provincia de Buenos Aires</span></a></div>
      <h2 class="brxe-heading">CONSCRIPTO BERNARDI AL 2425 | SAN ANDRES</h2>
      <span class="brxe-text-link"><span class="icon"><i class="fas fa-location-dot"></i></span>
      <span class="text">San Andrés, Provincia de Buenos Aires</span></span>"""
    assert G._linea_de_ubicacion(html) == "San Andrés, Provincia de Buenos Aires"


def test_tarjetas_de_otras_fichas_y_sucursales_no_cuentan():
    html = """<div class="card__location"><i class="card__location-icon fa fa-map-marker"></i>
      Don Orione 11, Claypole</div>
      <p><i class="fa fa-map-marker"></i> Sucursal Tigre</p>"""
    assert G._linea_de_ubicacion(html) is None


def test_martelliti_completa_ciudad_y_provincia():
    html = (FIX / "martelliti" / "ficha_1.html").read_text(encoding="utf-8")
    p = _normalizar(html, "https://www.adrianamartellitipropiedades.ar/ad/casa-de-2-ambientes")
    assert p is not None
    assert (p.direccion, p.ciudad) == ("Laprida 1835", "Mar Del Plata")
    assert p.provincia in ("Buenos Aires", "Provincia de Buenos Aires")


def test_pareja_numero_antes_del_rotulo_b_b():
    marcado = ('<div class="icodetalle"><i class="fa fa-bed-alt"></i><span class="p"> 1</span>'
               '<br><span>Dormitorios</span></div><div class="icodetalle"><i class="fa fa-shower"></i>'
               '<span class="p"> 1</span><br><span>Baños</span></div>'
               '<span class="strong">Ambientes</span> <span class="p"> 2</span>')
    texto = "1 Dormitorios 1 Baños Ambientes 2"
    assert G._cuenta_de_ficha(marcado, texto, BANOS, None) == 1


def test_el_numero_de_un_rotulo_anterior_no_es_del_siguiente():
    marcado = "<span>Ambientes</span><span>3</span><span>Baños</span><span>2</span>"
    assert G._cuenta_de_ficha(marcado, "Ambientes 3 Baños 2", BANOS, None) == 2


def test_cuartos_de_bano_realhomes():
    marcado = ('<div class="meta-inner-wrapper"><span class="meta-item-label">Cuartos de baño</span> '
               '<span class="meta-item-value">3</span></div>')
    assert G._cuenta_de_ficha(marcado, "Cuartos de baño 3", BANOS, None) == 3
