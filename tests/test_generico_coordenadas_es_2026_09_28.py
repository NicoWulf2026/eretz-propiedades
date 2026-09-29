"""Coordenada con claves en castellano, solo en las formas verificadas.

`ballarre` (247) y `zamorano` (143) publican `data-latitud`/`data-longitud` en
el mapa de la ficha; `bottai` declara `const latitud = ...` y un fallback de
Rosario que antes se tomaba como coordenada de la propiedad. Radio: 1 de 201
(bottai, corregido). Una `latitud:` suelta puede ser la de la CIUDAD.
"""
from __future__ import annotations

from connectors.generico import RE_COORD, RE_COORD_ES


def _par(html: str):
    m = RE_COORD_ES.search(html) or RE_COORD.search(html)
    return (float(m.group(1)), float(m.group(2))) if m else None


def test_el_mapa_de_la_ficha_con_data_latitud() -> None:
    html = ('<meta name="geo.position" content="-38.2703170;-57.8394500" />'
            '<div id="propertyMap" data-zoom="16" data-latitud="-38.267871930622746" '
            'data-longitud="-57.85335168932417"></div>')
    assert _par(html) == (-38.267871930622746, -57.85335168932417)


def test_la_variable_gana_al_fallback_de_rosario() -> None:
    html = ("const latitud = -31.65688832754; const longitud = -60.710149000372; "
            "const centro = (latitud !== null) ? [latitud, longitud] : [-32.9468, -60.6393];")
    assert _par(html) == (-31.65688832754, -60.710149000372)


def test_la_latitud_de_la_ciudad_no_es_la_de_la_propiedad() -> None:
    html = 'ciudad:{_id:e,nombre:"Arroyo Leyes",latitud:-31.585,longitud:-60.55000000000001,zoom:13}'
    assert RE_COORD_ES.search(html) is None


def test_coordenada_con_comillas_simples_del_plugin_estatik():
    """`portanko`: data-latitude='-38.84' data-longitude='-68.12' (35 de 42 sin coordenada)."""
    from connectors.generico import RE_COORD
    html = "<div class='es-property-map' data-latitude='-38.8411258' data-longitude='-68.1291336'></div>"
    assert RE_COORD.search(html).groups() == ("-38.8411258", "-68.1291336")
