# -*- coding: utf-8 -*-
"""`farina` (Houzez, 979 fichas): `property_city` = [centro, rosario].

El barrio y la ciudad viajan en la misma taxonomia; juntos daban «Centro
Rosario», que no resuelve como localidad, y 119 fichas quedaban sin ciudad.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from connectors.wordpress import _localidad_entre_terminos  # noqa: E402


def _crudo(*nombres: str) -> tuple[dict, dict]:
    terminos = {str(i): {"name": n} for i, n in enumerate(nombres, 1)}
    return ({"taxonomy_terms": {"property_city": terminos}},
            {"property_city": [int(k) for k in terminos]})


def test_MUERDE_de_barrio_y_ciudad_se_toma_la_ciudad():
    crudo, item = _crudo("Centro", "Rosario")
    assert _localidad_entre_terminos(crudo, item, "property_city", "Santa Fe") == "Rosario"


def test_un_termino_solo_no_se_toca():
    crudo, item = _crudo("Rosario")
    assert _localidad_entre_terminos(crudo, item, "property_city", "Santa Fe") is None


def test_si_ninguno_resuelve_no_se_elige():
    crudo, item = _crudo("Centro", "Nuestra Señora De Lourdes")
    assert _localidad_entre_terminos(crudo, item, "property_city", "Santa Fe") is None


def test_MUERDE_ficha_con_id_en_la_query_y_la_seccion_de_encabezado():
    """`chambouleyron`: <h1>DEPARTAMENTOS</h1> sobre la ficha
    `product.php?id=343`, con 5 vecinas debajo: 7 de 16 fichas a revision."""
    from connectors.generico import GenericoConnector, _id_de_ficha_en_la_query
    vecinas = "".join(f'<a href="/product.php?id={i}">Depto {i}</a>' for i in range(300, 306))
    html = f"<h1> DEPARTAMENTOS </h1><p>Depto 2 amb, USD 90.000</p>{vecinas}"
    assert not GenericoConnector._es_pagina_contenedora(
        html, "https://chambo.test/product.php?id=343")
    assert _id_de_ficha_en_la_query("https://chambo.test/product.php?id=343")
    assert not _id_de_ficha_en_la_query("https://chambo.test/propiedades.php?id=2")
    assert not _id_de_ficha_en_la_query("https://gr.test/propiedades.php?tipo=25&operacion=0")
