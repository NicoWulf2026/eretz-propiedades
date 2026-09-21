# -*- coding: utf-8 -*-
"""El marcador del mapa embebido como JSON, con las claves escritas.

`agustin zlotnik propiedades` paro la cola con radio FAMILIA: la senal dice
que la fuente publica latitud y longitud en las 84 fichas y la extraccion
fallo en 11. Comprobado contra la fuente, la senal tenia razon —las
coordenadas estan— y el extractor no las veia:

    {"address":"W. de Tata 4551","lat":"-34.6011211","lng":"-58.5607976"}

Ni el marcador ACF —que busca `data-lat=` y `data-lng=` como atributos— ni el
respaldo de «dos numeros pegados» lo encuentran, porque entre los dos valores
hay `","lng":"`. Las 73 que si funcionaban sacaban la coordenada del meta de
la API, no del HTML.

No es un detalle: la coordenada es lo que despues resuelve municipio y
departamento contra la geometria oficial de GeoRef, que acaba de pasar a ser
la fuente principal de las dos dimensiones.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from connectors.wordpress import _coordenada_en_json  # noqa: E402


def test_MUERDE_el_marcador_json_con_comillas_entre_los_valores():
    """El caso real de `azpropiedades`, tal cual viene en la pagina."""
    html = ('{"pricePin":"$410K","address":"W. de Tata 4551",'
            '"lat":"-34.6011211","lng":"-58.5607976","term_id":"5800"}')
    assert _coordenada_en_json(html) == (-34.6011211, -58.5607976)


def test_acepta_las_claves_largas_y_sin_comillas():
    """Los temas no se ponen de acuerdo en como llamarlas."""
    assert _coordenada_en_json('"latitude": -34.6011, "longitude": -58.5607') \
        == (-34.6011, -58.5607)
    assert _coordenada_en_json('"lat":-31.4201,"lon":-64.1888') \
        == (-31.4201, -64.1888)


def test_MUERDE_un_valor_fuera_de_argentina_no_entra_aunque_este_rotulado():
    """Un rotulo correcto con un valor imposible sigue siendo imposible.

    Es la trampa que ya costo 752 propiedades ubicadas fuera del pais con el
    respaldo por adyacencia. El rotulo evita confundir numeros sueltos; no
    evita que el numero este mal.
    """
    assert _coordenada_en_json('"lat":"40.7128","lng":"-74.0060"') is None
    assert _coordenada_en_json('"lat":"-34.60","lng":"2.3522"') is None


def test_MUERDE_un_par_de_numeros_sin_rotulo_no_se_toma():
    """Lo que distingue este patron del respaldo por adyacencia."""
    assert _coordenada_en_json('"precio":"50.774","expensas":"50.7708"') is None
    assert _coordenada_en_json("-34.6011211, -58.5607976") is None


def test_exige_decimales_de_verdad():
    """`-34.6` podria ser cualquier cosa; una coordenada de mapa trae mas."""
    assert _coordenada_en_json('"lat":"-34.6","lng":"-58.5"') is None


def test_html_vacio_o_nulo_no_explota():
    assert _coordenada_en_json("") is None
    assert _coordenada_en_json(None) is None


def test_se_queda_con_el_primer_marcador():
    """Una ficha con mapa de la propiedad y mapa de la oficina.

    El primero es el de la propiedad: los temas ponen el marcador principal
    antes que los accesorios.
    """
    html = ('"lat":"-34.6011211","lng":"-58.5607976" ... '
            '"lat":"-31.4201","lng":"-64.1888"')
    assert _coordenada_en_json(html) == (-34.6011211, -58.5607976)
