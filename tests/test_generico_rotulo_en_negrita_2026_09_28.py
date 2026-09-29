"""Rotulo en negrita dentro del mismo elemento, y lista de valores != rotulo compuesto.

`nexo` (Houzez, paro de la familia wordpress 21:07): `<li><strong>Tipo de
propiedad:</strong> Departamento</li>` y 33 de 40 fichas sin tipo; ademas una
tarjeta «4 dormitorios • 3 baños • 242» activaba la guarda de rotulo compuesto
y apagaba «Habitaciones: 1». Radio: 5 de 201 (grosso, adriana nuti, y tres
Kiteprop con `<li><b>Ciudad:</b> Rosario</li>`), verificados.
"""
from __future__ import annotations

from connectors.generico import GenericoConnector as G

DORM = r"dormitorios?|habitaciones?"


def test_el_rotulo_en_negrita_con_el_valor_en_el_mismo_li() -> None:
    html = ('<ul><li><strong>Precio:</strong> $670,000</li><li><strong>Habitaciones:</strong> 1</li>'
            '<li class="prop_type"><strong>Tipo de propiedad:</strong> Departamento</li></ul>')
    assert G._rotulo_en_linea(html, r"Tipo(?:\s+de)?\s+(?:propiedad|inmueble)") == "Departamento"
    assert G._rotulo_en_linea("<li><b>Ciudad:</b> Rosario</li>", r"localidad|ciudad") == "Rosario"


def test_sigue_leyendo_el_rotulo_sin_negrita() -> None:
    assert G._rotulo_en_linea("<li class='x'> Localidad: Los Molles </li>", r"localidad|ciudad") == "Los Molles"


def test_una_lista_de_valores_no_es_un_rotulo_compuesto() -> None:
    assert not G._rotulo_compuesto("<p>4 dormitorios • 3 baños • 242</p>", DORM)


def test_un_rotulo_que_funde_atributos_sigue_bloqueando() -> None:
    assert G._rotulo_compuesto("<span>Dormitorios/Ambientes</span><span>2</span>", DORM)
    assert G._rotulo_compuesto("<p>1 dormitorio 2 dormitorios Cochera</p>", DORM)
