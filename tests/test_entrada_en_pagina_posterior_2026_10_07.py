"""Una web oficial que apunta a la pagina 2+ de un listado se enumera desde la pagina 1.

Falso CERTIFIED_COMPLETE medido contra la fuente el 07-10: `barbara estanga` tiene como web
oficial `https://barbaraestangapropiedades.com.ar/?page=2`. La enumeracion arrancaba en la
pagina 2, seguia la paginacion hacia adelante y certificaba COMPLETE con 30 de 39 fichas: las
9 que faltaban son EXACTAMENTE las de la pagina 1. `nicolas de modena` (`...&pagina=22`)
enumeraba 9 de una busqueda filtrada.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RAIZ)]

from connectors.base import Fuente  # noqa: E402
from connectors.generico import GenericoConnector, entrada_sin_pagina_posterior  # noqa: E402


def test_MUERDE_page_2_vuelve_a_la_pagina_1() -> None:
    assert entrada_sin_pagina_posterior("https://barbaraestangapropiedades.com.ar/?page=2") \
        == "https://barbaraestangapropiedades.com.ar/"


def test_MUERDE_pagina_22_conserva_los_demas_parametros() -> None:
    u = ("https://www.nicolasdemodena.com/apartamentos/en-venta/?barrio=188&dormitorios=0"
         "&orden=Precio%20desc&pagina=22")
    assert entrada_sin_pagina_posterior(u) == (
        "https://www.nicolasdemodena.com/apartamentos/en-venta/?barrio=188&dormitorios=0"
        "&orden=Precio%20desc")


def test_wordpress_page_en_la_ruta() -> None:
    assert entrada_sin_pagina_posterior("https://agencia.test/propiedades/page/3/") \
        == "https://agencia.test/propiedades/"


def test_sin_paginacion_no_cambia_nada() -> None:
    for u in ("https://agencia.test/", "https://agencia.test/propiedades.php?ope=A&tipo=D",
              "https://agencia.test/?p=123",  # WordPress: ?p= es un post, no una pagina
              "https://agencia.test/propiedades?page=1"):
        assert entrada_sin_pagina_posterior(u) is None, u


def test_discover_arranca_de_la_pagina_1_y_lo_anota() -> None:
    pedidas = []

    class Descargador:
        def bajar(self, url, **_):
            pedidas.append(url)
            return "<html><body>sin catalogo</body></html>"

    c = GenericoConnector.__new__(GenericoConnector)
    c.descargador = Descargador()
    fuente = Fuente("roomix:x", "X", "https://agencia.test/?page=2")
    try:
        plan = c.discover(fuente)
    except Exception:
        plan = {}
    assert "https://agencia.test/" in pedidas
    assert not any("page=2" in u for u in pedidas), pedidas
    assert fuente.official_url == "https://agencia.test/?page=2"  # la fuente no se toca
    if plan:
        assert plan.get("entrada_declarada") == "https://agencia.test/?page=2"
