# -*- coding: utf-8 -*-
"""Una provincia que dedujimos nosotros no puede contradecir a la fuente.

El conector deduce la provincia del padron de la inmobiliaria cuando la ficha
no la publica, y lo marca `provincia_origen: padron_inmobiliaria`. Despues,
en la misma pasada, la usa como contexto para resolver la localidad. Si no
coinciden, declaraba GEO_CONFLICT.

Pero eso pone una suposicion nuestra a discutir contra un dato de la fuente, y
el que pierde es el dato. Medido sobre el catalogo entero: **3.439 de los
3.859 conflictos entre la geometria y la provincia -el 89,1 %- eran contra una
provincia inferida**, no contra una publicada. Una inmobiliaria de Cordoba que
vende en Neuquen no es una contradiccion: es una inmobiliaria que vende en
Neuquen.

El costo era el maximo posible. En la auditoria, la fila salia publicada sin
nada -sin provincia, sin departamento, sin municipio, sin localidad y con
`area_busqueda: SIN_AREA`-, incluida la geografia que la coordenada SI
demuestra: 3.888 propiedades, el 6,7 % del catalogo. Y en el conector, el
bloque de conflicto borra `ciudad`, `provincia`, `latitud` y `longitud` de una
sola vez.

Corregido: GEO_CONFLICT paso de 3.888 a 462, y la geografia publicable subio
—provincia 53.580 -> 57.007, departamento 42.124 -> 45.551, municipio 33.003
-> 36.281—. `localidad` quedo igual, como corresponde.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from connectors.base import Connector, PropiedadNormalizada  # noqa: E402


def propiedad(ciudad: str, provincia: str | None, inferida: bool,
              lat=None, lon=None) -> PropiedadNormalizada:
    prop = PropiedadNormalizada(
        canonical_agency_id="roomix:x", source_listing_id="1",
        source_url="https://x.test/p/1", connector="generico",
        ciudad=ciudad, provincia=provincia, latitud=lat, longitud=lon)
    if inferida:
        prop.extra["provincia_origen"] = "padron_inmobiliaria"
        prop.extra["provincia_confianza"] = "inferida"
    return prop


def test_MUERDE_una_ciudad_publicada_sobrevive_a_una_provincia_supuesta():
    """El caso real: agencia de Cordoba, propiedad en Neuquen.

    La ficha NOMBRA la ciudad. La provincia la pusimos nosotros. Antes se
    perdian las dos, mas las coordenadas.
    """
    prop = propiedad("Neuquén", "Córdoba", inferida=True)
    Connector._resolver_geografia(prop)
    assert prop.ciudad is not None, "se perdio la ciudad que publico la fuente"
    assert prop.extra["provincia_supuesta_descartada"] == "Córdoba"
    assert prop.geo.get("estado_geografico") != "GEO_CONFLICT"


def test_MUERDE_las_coordenadas_no_se_tiran_por_una_suposicion():
    """El bloque de conflicto borraba `latitud` y `longitud` tambien.

    Son el unico dato que despues permite resolver municipio y departamento
    por geometria oficial: tirarlas cuesta mucho mas que el campo en disputa.
    """
    prop = propiedad("Neuquén", "Córdoba", inferida=True,
                     lat=-38.9516, lon=-68.0591)
    Connector._resolver_geografia(prop)
    assert prop.latitud == -38.9516
    assert prop.longitud == -68.0591


def test_MUERDE_una_provincia_PUBLICADA_si_sigue_generando_conflicto():
    """La regla existe para esto y no se afloja.

    Si la ficha dice Cordoba y dice Neuquen, son dos evidencias de la misma
    fuente que se contradicen. Ahi no se elige.
    """
    prop = propiedad("Neuquén", "Córdoba", inferida=False)
    Connector._resolver_geografia(prop)
    assert prop.geo.get("estado_geografico") == "GEO_CONFLICT"
    assert prop.ciudad is None and prop.provincia is None


def test_una_provincia_supuesta_que_coincide_no_cambia_nada():
    """La mayoria de los casos: la inmobiliaria vende donde esta."""
    prop = propiedad("Rosario", "Santa Fe", inferida=True)
    Connector._resolver_geografia(prop)
    assert prop.ciudad == "Rosario"
    assert prop.provincia == "Santa Fe"
    assert "provincia_supuesta_descartada" not in prop.extra


def test_sin_provincia_no_hay_nada_que_descartar():
    prop = propiedad("Rosario", None, inferida=False)
    Connector._resolver_geografia(prop)
    assert prop.ciudad == "Rosario"
    assert "provincia_supuesta_descartada" not in prop.extra
