#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Una ficha no sirve como punto de partida para descubrir el listado.

La identidad de varias fuentes se demostro mirando una ficha concreta
-`acinpropiedades.com.ar/p/8093032-Departamento-en-Alquiler...`- y esa url quedo
guardada como su "web oficial". Para probar de quien es el sitio esta bien. Como
base de descubrimiento no sirve: el connector arranca desde esa ruta, busca el
listado y no encuentra nada, y la fuente termina marcada VARIANTE_NO_SOPORTADA
teniendo el inventario publicado a un nivel de distancia.

De las 623 fuentes que fallaron en la primera corrida del backlog, 68 tenian una
ficha por base.

La excepcion importante: la pagina de una oficina dentro de su propia red
-`century21.com.ar/oficina/33`- SI es su punto de partida. Recortarla a la raiz
la mandaria a leer el inventario de toda la franquicia.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_backlog_census import (base_de_descubrimiento,  # noqa: E402
                                          connector_de)


def test_una_ficha_se_recorta_a_la_raiz():
    assert (base_de_descubrimiento(
        "https://www.acinpropiedades.com.ar/p/8093032-Departamento-en-Alquiler")
        == "https://www.acinpropiedades.com.ar")


def test_un_deep_link_en_un_portal_tambien():
    assert (base_de_descubrimiento(
        "https://inmoclick.ai/263700-raiza/inmuebles/73/ficha/departamento")
        == "https://inmoclick.ai")


def test_la_oficina_dentro_de_su_red_no_se_toca():
    """Recortarla a la raiz la mandaria a leer el inventario de toda la
    franquicia y atribuirselo a una sola oficina."""
    for u in ("https://century21.com.ar/oficina/33",
              "https://www.remax.com.ar/oficina_133-franchi"):
        assert base_de_descubrimiento(u) == u


def test_la_raiz_queda_igual():
    for u in ("https://alfa.com.ar", "https://alfa.com.ar/",
              "http://www.beta.com.ar"):
        assert base_de_descubrimiento(u) == u


def test_una_seccion_de_un_solo_nivel_no_es_una_ficha():
    """`/venta` o `/inmuebles` son listados: son un punto de partida valido."""
    for u in ("https://alfa.com.ar/venta", "https://alfa.com.ar/inmuebles"):
        assert base_de_descubrimiento(u) == u


def test_lo_que_no_es_una_url_no_se_rompe():
    assert base_de_descubrimiento("") == ""
    assert base_de_descubrimiento(None) is None
    assert base_de_descubrimiento("no-es-una-url") == "no-es-una-url"


# --- eleccion de connector ---------------------------------------------------

def test_la_estrategia_manda_sobre_la_plataforma():
    """Un sitio hecho en WordPress puede publicar el inventario con Tokko
    adentro: lo que importa es como publica, no con que esta hecho."""
    c, _ = connector_de({"detected_platform": "WORDPRESS",
                         "strategy": "TOKKO_CONNECTOR"})
    assert c == "tokko"


def test_la_plataforma_decide_cuando_la_estrategia_no_dice_nada():
    assert connector_de({"detected_platform": "TOKKO", "strategy": ""})[0] == "tokko"
    assert connector_de({"detected_platform": "WASI", "strategy": ""})[0] == "wasi"


def test_sin_mapa_se_prueba_lo_barato():
    """Probar sitemap, JSON embebido y HTML cuesta un pedido; escribir un
    connector nuevo cuesta un dia."""
    c, porque = connector_de(None)
    assert c == "generico"
    assert "barato" in porque


def test_una_plataforma_sin_connector_propio_cae_en_generico():
    c, porque = connector_de({"detected_platform": "JOOMLA", "strategy": "SITEMAP"})
    assert c == "generico"
    assert "JOOMLA" in porque
