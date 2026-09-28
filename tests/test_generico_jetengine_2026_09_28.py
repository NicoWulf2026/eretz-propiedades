"""Elementor + JetEngine (`esnal`) y la cota inferior «+5 Dormitorios».

Medido el 28-09 sobre el HTML cacheado de las 48 fichas de `esnal`: +38
descripciones (47 de 48 la tienen), todas distintas; radio en una ficha por
agencia: 0 de 197.
"""
from __future__ import annotations

from connectors.generico import RE_DESCRIPCION_JETENGINE

PROSA = ("Departamento en venta en el Centro a pocas cuadras de Oroño y del rio Parana, "
         "ideal para vivienda. Cuenta con 2 ambientes bien distribuidos, 1 dormitorio y 1 baño.")


def _ficha(*campos: str) -> str:
    cuerpo = "".join(
        f'<div class="jet-listing-dynamic-field__content">{c}</div></div></div>'
        for c in campos)
    return ('<h2 class="elementor-heading-title">Descripcion</h2>'
            '<div class="elementor-divider"><span></span></div>' + cuerpo)


def test_el_campo_vacio_bajo_el_encabezado_no_corta_la_descripcion() -> None:
    m = RE_DESCRIPCION_JETENGINE.search(_ficha("", "Baños: 1", "Tipo de Propiedad: Departamento", PROSA))
    assert m and m.group(1).strip() == PROSA


def test_los_campos_de_atributos_no_son_descripcion() -> None:
    assert RE_DESCRIPCION_JETENGINE.search(_ficha("", "Baños: 1", "Metros Cuadrados: 50")) is None


def test_sin_el_encabezado_no_se_toma_nada() -> None:
    html = f'<div class="jet-listing-dynamic-field__content">{PROSA}</div>'
    assert RE_DESCRIPCION_JETENGINE.search(html) is None
