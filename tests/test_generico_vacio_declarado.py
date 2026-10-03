"""Un rotulo con guion es un dato vacio declarado, no un hueco a rellenar.

Canario de la ventana final (03-10): `eckert` (KiteProp) publica una oficina
como «Ambientes: 2 Dormitorios: - Baños: 4». La busqueda en prosa leia «2
Dormitorios» y guardaba los ambientes como dormitorios. Y la otra plantilla de
KiteProp pone las «Ultimas Propiedades» de las vecinas en
`div.widget.widget_recent_property`, dentro del cuerpo.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from connectors.generico import (ETIQUETAS_DE_CONTEO, GenericoConnector,  # noqa: E402
                                 cuerpo_principal)

DORM = ETIQUETAS_DE_CONTEO["dormitorios"]


def test_MUERDE_dormitorios_con_guion_no_toma_los_ambientes_de_al_lado():
    texto = "USD 340.000 En venta Ambientes: 2 Dormitorios: - Baños: 4 Estacionamientos: -"
    assert GenericoConnector._cuenta(texto, DORM, None) is None
    assert GenericoConnector._cuenta(texto, ETIQUETAS_DE_CONTEO["ambientes"], None) == 2
    assert GenericoConnector._cuenta(texto, ETIQUETAS_DE_CONTEO["banos"], None) == 4


def test_monoambiente_con_dormitorios_vacios_no_tiene_un_dormitorio():
    assert GenericoConnector._cuenta("Ambientes: 1 Dormitorios: - Baños: 1", DORM, None) is None


def test_los_demas_formatos_no_cambian():
    assert GenericoConnector._cuenta("Ambientes: 3 Dormitorios: 2 Baños: 1", DORM, None) == 2
    assert GenericoConnector._cuenta("Ambientes 3 Dormitorios 2 Baños 1", DORM, None) == 2
    assert GenericoConnector._cuenta("Hermoso depto de 3 dormitorios y 2 baños", DORM, None) == 3
    # El dato tipado (schema.org) sigue mandando.
    assert GenericoConnector._cuenta("Dormitorios: -", DORM, 3) == 3


def test_el_widget_de_la_otra_plantilla_kiteprop_no_es_la_ficha():
    html = ('<html><body><main><h1>Oficina</h1><p>Ambientes: 2 Dormitorios: -</p>'
            '<div class="widget widget_recent_property d-none d-sm-block">'
            '<h4>Últimas Propiedades</h4><p>Montevideo 2749 USD 254.000 Ambientes: 3 '
            '2 dormitorios</p></div></main></body></html>')
    principal = cuerpo_principal(html)
    assert "Montevideo 2749" not in principal
    assert "Ambientes: 2" in principal


def test_MUERDE_el_auditor_no_ve_dormitorios_publicados_en_un_rotulo_vacio():
    """Arreglado solo el extractor, el auditor seguia leyendo «2 Dormitorios» y
    daba la ficha por mal extraida: `eckert` paro la cola (03-10 15:30)."""
    from scripts.agency_certifier import source_signals
    html = ('<html><body><main><h1>Oficina a estrenar</h1>'
            '<p>USD 340.000 En venta Ambientes: 2 Dormitorios: - Baños: 4</p>'
            '</main></body></html>')
    senales = source_signals(html, "https://ejemplo.com/site/properties/1/oficina")
    assert senales["dormitorios"] is False
    assert senales["ambientes"] is True and senales["banos"] is True
