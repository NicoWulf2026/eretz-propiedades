"""«3 DORMITORIOS CON COCHERA» en el titulo dice un valor, no funde dos rotulos.

Medido el 28-09 sobre los paquetes: 216 fichas `generico` con dormitorios
descartados; 119 con «N dormitorios» en el titulo, casi todas por la guarda de
rotulo compuesto leyendo el <h1>. A/B sobre el HTML cacheado de esas fichas: 104
dormitorios recuperados en 16 agencias (imperia, brunetti, vilches, fiano,
metro, fenix...), 0 perdidos; radio en una ficha por agencia: 2 de 197.
"""
from __future__ import annotations

import pytest

from connectors.generico import GenericoConnector as G

DORM = r"dormitorios?|habitaciones?"


def test_un_titulo_con_valor_no_es_un_rotulo_compuesto() -> None:
    for marcado in ("<h1>VENTA DEPARTAMENTO 3 DORMITORIOS CON COCHERA</h1>",
                    "<h2 class='t'>Casa en venta de 3 dormitorios c/ cochera en Maipu</h2>"):
        assert not G._rotulo_compuesto(marcado, DORM), marcado


def test_un_rotulo_que_funde_dos_atributos_sigue_bloqueando() -> None:
    assert G._rotulo_compuesto("<span>Dormitorios/Cocheras</span><span>2</span>", DORM)
    assert G._rotulo_compuesto("<dt>Dormitorios / Ambientes</dt><dd>2</dd>", DORM)


def test_fuera_de_un_encabezado_la_guarda_no_cambia() -> None:
    """`bottai`: un buscador «1 dormitorio 2 dormitorios … Cochera» en la pagina."""
    assert G._rotulo_compuesto("<p>1 dormitorio 2 dormitorios Cochera</p>", DORM)


@pytest.mark.parametrize("titulo,esperado", [
    ("VENTA DEPARTAMENTO 3 DORMITORIOS CON COCHERA", 3),
    ("Casa en venta de 4 dormitorios c/ cochera en Tunuyán | Brunetti Propiedades", 4),
    ("DUPLEX A ESTRENAR EN VENTA - 3 DORMITORIOS - B° IVYRA PYTA", 3),
    ("Departamento PB cochera 1 Dormitorio", 1),
    ("Depto 2 y 3 dormitorios", None),
    ("Departamentos de 1 y 2 dormitorios", None),
    ("Monoambientes y Departamentos de 1 Dormitorio", None),
    ("Casa de 3 dorm. + depto de 2 dorm.", None),
    ("Casa en venta en Distrito Sur", None),
    (None, None),
])
def test_dormitorios_del_titulo(titulo, esperado) -> None:
    assert G._dormitorios_del_titulo(titulo) == esperado
