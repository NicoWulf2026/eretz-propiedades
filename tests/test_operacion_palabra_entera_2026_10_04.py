"""La operacion se reconoce por PALABRA ENTERA, y el rotulo con icono vacio se lee.

P0 de la candidata final_v6 (04-10, READY #7b EN ESPERA):

  - `detectar_operacion` buscaba subcadenas: «rent» en «fRENTE», «sale» en
    «RoSALEs», «venta» en «VENTAnal». 516 filas de 110 agencias servian como
    ALQUILER ventas de USD 37.000 a 160.000. Replay offline de 57 fichas
    afectadas: 43 pasan a «venta» (la ficha dice Venta), 6 a NULL honesto.
  - `blanco` publica <li><i class="fa-light ..."></i> Tipo de propiedad:
    DEPARTAMENTOS</li>: el icono vacio impedia leer el rotulo y el tipo salia
    del menu del sitio -~200 de sus 573 «terrenos» no lo eran-.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from connectors.base import Checkpoint, Fuente, detectar_operacion
from connectors.generico import GenericoConnector as G


@pytest.mark.parametrize("texto", [
    "3 ambientes al frente", "Monoambiente al contrafrente", "Excelente renta, rentable",
    "Dormitorio con ventanal", "Av Rosales 624 - Remedios de Escalada", "Frente al mar",
])
def test_MUERDE_una_subcadena_no_es_operacion(texto: str) -> None:
    assert detectar_operacion(texto) is None


@pytest.mark.parametrize("texto,esperado", [
    ("Casa en venta", "venta"), ("PREVENTA en pozo", "venta"), ("Ventas y Alquileres", "venta"),
    ("House for sale", "venta"), ("Apartment for rent", "alquiler"), ("Alquileres", "alquiler"),
    ("/propiedades/casas_venta_9-de-abril", "venta"), ("/lotes_alquiler_centro", "alquiler"),
    ("PH al frente en venta", "venta"), ("Alquiler temporario frente al mar", "alquiler_temporario"),
])
def test_la_palabra_entera_sigue_detectandose(texto: str, esperado: str) -> None:
    assert detectar_operacion(texto) == esperado


def test_MUERDE_el_rotulo_con_icono_vacio_delante() -> None:
    html = ('<ul><li><i class="fa-light fa-house-turret"></i> Tipo de propiedad: DEPARTAMENTOS</li>'
            '<li><i class="fa-light fa-tag"></i> Operación: Venta</li></ul>')
    assert G._rotulo_en_linea(html, r"Tipo(?:\s+de)?\s+(?:propiedad|inmueble)") == "DEPARTAMENTOS"
    assert G._rotulo_en_linea(html, r"Operaci(?:ó|o|&oacute;)n") == "Venta"


class _Desc:
    html = ""

    def bajar(self, url: str) -> str:
        return self.html


FICHA_BLANCO = """<html><head><title>Muy luminoso dos ambientes frente a la plaza | Blanco</title></head>
<body><nav><a>Venta</a><a>Alquiler</a><a>Terrenos</a></nav>
<main><h1>Muy luminoso dos ambientes frente a la plaza</h1>
<p>USD 98.000</p>
<ul><li><i class="fa-light fa-house-turret"></i> Tipo de propiedad: DEPARTAMENTOS</li>
<li><i class="fa-light fa-tag"></i> Operación: Venta</li></ul>
<p>Departamento de dos ambientes al frente, muy luminoso, en Saavedra.</p></main></body></html>"""


def test_MUERDE_la_ficha_de_blanco_es_venta_de_departamento() -> None:
    d = _Desc(); d.html = FICHA_BLANCO
    g = G(d, Checkpoint(Path(tempfile.mkdtemp()) / "c.json"))
    url = "https://blancopropiedades.com/propiedades/muy-luminoso-dos-ambientes-frente-a-la-plaza"
    f = Fuente(canonical_agency_id="roomix:blanco propiedades", agency_name="Blanco",
               official_url="https://blancopropiedades.com/", inmobiliaria_id=1,
               detected_platform="UNKNOWN", extra={})
    p = g.normalize({"source_listing_id": "1", "source_url": url}, f)
    assert p.operacion == "venta"
    assert p.tipo_propiedad == "departamento"
