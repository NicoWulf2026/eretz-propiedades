# -*- coding: utf-8 -*-
"""Lo que la fuente escribe en `provincia` no siempre es una.

No es un fallo de extraccion, y eso importa para elegir el arreglo. La ficha
de `dardopropiedades` publica literalmente:

    Direccion Moreno 2568  Ciudad Mar del Plata  Provincia Bs.As. Costa Atlantica

El resto de su geografia esta bien. Es la taxonomia de otra plataforma debajo
de la misma etiqueta.

Medido: **612 propiedades** del padron tienen ahi algo que no es una
provincia, de las cuales **567 son etiquetas de zona** repartidas en 10
agencias —9 de ellas wordpress—.

La regla no adivina: se queda con la provincia **que el propio texto nombra**.
`Bs.As. Costa Atlantica` empieza diciendo Buenos Aires. Lo que sobra se
guarda como zona, porque es informacion real de la fuente. Lo que no nombra
ninguna provincia se vacia y se conserva crudo: `San Salvador` es una ciudad
de Jujuy escrita en el casillero equivocado, y no sabemos cual quiso decir.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from connectors.base import Connector, PropiedadNormalizada  # noqa: E402
from connectors.geografia import geografia  # noqa: E402


def canonizar(publicada):
    prop = PropiedadNormalizada(canonical_agency_id="x", source_listing_id="1",
                                source_url="u", connector="wordpress",
                                provincia=publicada)
    Connector._canonizar_la_provincia_publicada(prop)
    return prop


def test_MUERDE_las_etiquetas_de_zona_se_resuelven_a_su_provincia():
    """Las cuatro formas reales, con sus 567 propiedades."""
    for publicada, zona in (("Bs.As. Costa Atlántica", "costa atlantica"),
                            ("Bs.As. G.B.A. Oeste", "g b a oeste"),
                            ("Bs.As. G.B.A. Sur", "g b a sur"),
                            ("Buenos Aires Interior", "interior")):
        prop = canonizar(publicada)
        assert prop.provincia == "Buenos Aires", publicada
        assert prop.extra["zona_declarada"] == zona
        # Y el dato crudo no se pierde.
        assert prop.extra["provincia_publicada"] == publicada


def test_MUERDE_lo_que_no_nombra_una_provincia_se_vacia_y_se_conserva():
    """`San Salvador`, `Palpala`, `Ciudad Perico`: ciudades de Jujuy.

    Inventar que son provincias seria peor. Vaciar el campo permite que la
    inferencia del padron lo complete y quede marcada como inferida.
    """
    for publicada in ("San Salvador", "Palpala", "Ciudad Perico", "Itapúa"):
        prop = canonizar(publicada)
        assert prop.provincia is None, publicada
        assert prop.extra["provincia_declarada_sin_resolver"] == publicada
        assert "zona_declarada" not in prop.extra


def test_MUERDE_una_provincia_bien_escrita_no_se_toca():
    """La mayoria del padron. Si esto se rompiera, el arreglo costaria mas de
    lo que corrige."""
    for publicada in ("Santa Fe", "Córdoba", "Buenos Aires", "Mendoza"):
        prop = canonizar(publicada)
        assert prop.provincia == publicada, publicada
        assert "provincia_publicada" not in prop.extra
        assert "zona_declarada" not in prop.extra


def test_los_alias_de_caba_quedan_en_su_nombre_oficial():
    """`Capital Federal` y `CABA` son el lugar correcto sin canonizar."""
    for publicada in ("Capital Federal", "CABA"):
        prop = canonizar(publicada)
        assert prop.provincia == "Ciudad Autónoma de Buenos Aires"
        assert prop.extra["provincia_publicada"] == publicada
        assert "zona_declarada" not in prop.extra


def test_tierra_del_fuego_corta_se_resuelve_al_nombre_largo():
    """El catalogo la llama `Tierra del Fuego, Antártida e Islas del
    Atlántico Sur`, y 27 contradicciones del sondeo eran solo eso."""
    prop = canonizar("Tierra del Fuego")
    assert prop.provincia.startswith("Tierra del Fuego,")


def test_un_campo_vacio_no_hace_nada():
    for publicada in (None, ""):
        prop = canonizar(publicada)
        assert prop.provincia == publicada
        assert prop.extra == {}


def test_MUERDE_la_comparacion_es_por_palabras_enteras():
    """`\\b` mal puesto ya mordio cinco veces en este proyecto.

    Un prefijo de caracteres haria que `Cordobes` empiece por `Cordoba` y que
    `Santa Fenix` sea Santa Fe.
    """
    assert geografia().provincia_declarada("Cordobes") == (None, None)
    assert geografia().provincia_declarada("Sanjuanino") == (None, None)
    # Y la palabra entera si tiene que resolver.
    assert geografia().provincia_declarada("Cordoba")[0] == "Córdoba"


def test_gana_el_nombre_mas_largo_que_coincida():
    """`Tierra del Fuego` tiene que ganarle a cualquier prefijo mas corto."""
    provincia, zona = geografia().provincia_declarada("Tierra del Fuego Sur")
    assert provincia.startswith("Tierra del Fuego,")
    assert zona == "sur"
