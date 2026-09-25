"""La descripcion de Wasi es un string JSON: se decodifica como JSON.

`_descripcion_wasi` usaba `.encode().decode("unicode_escape")`, que solo sirve
cuando la fuente escapa los acentos (`\\u00e1`). Con UTF-8 crudo los rompe:
«panorÃ¡micas», «195 mÂ²». 208 de 1.353 descripciones Wasi en 8 de 12
agencias, y `domus bienes raices` perdia la superficie cubierta porque
«mÂ²» no es «m²» (Regression Gate del 25-09).
"""
from __future__ import annotations

from connectors.wasi import _campos_descriptivos, _descripcion_wasi


def _html(descripcion_json: str) -> str:
    return ('<script type="application/ld+json">{"@type": "Product", "description": "'
            + descripcion_json + '", "address": {}}</script>')


def test_MUERDE_el_utf8_crudo_no_se_rompe():
    d = _descripcion_wasi(_html("Vistas panorámicas. Superficie cubierta: 195 m² aprox. 🏠"))
    assert d == "Vistas panorámicas. Superficie cubierta: 195 m² aprox. 🏠"
    medidas, _ = _campos_descriptivos(d, "casa")
    assert medidas.get("superficie_cubierta") == 195


def test_los_escapes_json_se_siguen_decodificando():
    d = _descripcion_wasi(_html("<p>Casa con jard\\u00edn</p>\\n<p>Cocina \\\"nueva\\\"</p>"))
    assert d == 'Casa con jardín Cocina "nueva"'
