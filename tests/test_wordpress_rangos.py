"""Un emprendimiento publica rangos por unidad, no el valor de la propiedad.

`garcia andreu` (WordPress/Houzez): edificio-dot, firenze-xi, san-juan-2050
publican «Dormitorios: 2 - 3», «Baños: 2 - 3» y la meta `fave_property_bedrooms`
«2 - 3». El conector no afirma un valor unico -bien-, pero lo marcaba como
provisto y el auditor lo contaba como extraccion fallida: paro de familia el
25-09 15:57.
"""
from __future__ import annotations

import json

import test_connectors as TC


def _normalizar(meta: dict, contenido: str):
    tipos = json.dumps({"property": {"rest_base": "properties", "taxonomies": []}})
    item = [{"id": 88, "link": "https://wp.com.ar/property/edificio-88/", "type": "property",
             "modified": "2026-08-01T10:00:00", "title": {"rendered": "Edificio Dot"},
             "content": {"rendered": contenido},
             "property_meta": {"fave_property_price": ["109000"], "fave_currency": ["USD"], **meta}}]
    paginas = {"https://wp.com.ar/wp-json/wp/v2/types": tipos,
               "https://wp.com.ar/wp-json/wp/v2/properties?": json.dumps(item),
               "https://wp.com.ar/property/edificio-88/": "<p>Edificio</p>"}
    c = TC.wp_conector(paginas)
    f = TC.wp_fuente()
    return c.normalize(list(c.fetch_listing(f, c.discover(f)))[0], f)


def test_MUERDE_un_rango_de_unidades_es_un_descarte_y_no_una_falla():
    p = _normalizar({"fave_property_bedrooms": ["2 - 3"], "fave_property_bathrooms": ["2 - 3"]},
                    "<p>Dormitorios: 2 - 3 Baños: 2 - 3</p>")
    assert p.dormitorios is None and p.banos is None
    descartes = p.extra.get("atributos_descartados") or ""
    assert "dormitorios:rango_de_unidades" in descartes
    assert "banos:rango_de_unidades" in descartes


def test_un_valor_unico_se_lee_y_no_se_descarta():
    p = _normalizar({"fave_property_bedrooms": ["2"]}, "<p>Dormitorios: 2</p>")
    assert p.dormitorios == 2
    assert "rango" not in (p.extra.get("atributos_descartados") or "")


def test_una_lista_de_unidades_no_es_un_rango():
    """`eigen`: «Unidades Disponibles de 3 Dormitorios: 08 – 02 – U$S 246.000»."""
    p = _normalizar({"fave_property_bedrooms": ["3"]},
                    "<p>Unidades Disponibles de 3 Dormitorios: 08 – 02 – U$S 246.000</p>")
    assert p.dormitorios == 3
    assert "rango" not in (p.extra.get("atributos_descartados") or "")
