# -*- coding: utf-8 -*-
"""Agrupar cuarenta urls por forma es lo que convierte un caso en una decisión.

Teníamos 39 agencias que cierran sin inventario y la costumbre era mirarlas de
a una. La pregunta que decide si hay un arreglo **compartido** no es «por qué
falla ésta» sino «qué forma tienen los enlaces que no reconocemos».

Medido sobre las 50 agencias `NEEDS_FIX` con cero enumeradas: **14 tienen al
menos una forma de enlace que ningún patrón nuestro ve**, repartidas en 10
formas. `/<palabra>-<id>-<slug>` —el caso `fios`— aporta 20 enlaces en una sola
agencia; `/<slug-con-tipo>` aparece en tres.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from que_forma_tienen_sus_fichas import forma_de, parece_ficha  # noqa: E402


@pytest.mark.parametrize("ruta,esperada", [
    ("/propiedad-9871962-venta-casa-en-funes", "/<palabra>-<id>-<slug>"),
    ("/inmueble_6076", "/<palabra>-<slug>"),
    ("/p/7525662", "/<palabra-suelta>/<id>"),
    ("/propiedades/12345", "/<palabra>/<id>"),
    ("/8471-venta-casa-3-ambientes", "/<id>-<slug>"),
    ("/pte-roca-1438-casa-en-venta", "/<slug-con-tipo>"),
    ("/quienes-somos", "/<palabra-suelta>"),
    ("/nosotros", "/<palabra-suelta>"),
])
def test_la_forma_resume_la_ruta(ruta, esperada):
    assert forma_de(ruta) == esperada


def test_MUERDE_la_forma_no_depende_del_id_ni_del_slug():
    """Dos fichas de la misma agencia tienen que caer en la misma forma.

    Si la forma dependiera del número o del texto, cada ficha sería su propia
    forma y la tabla tendría tantas filas como enlaces: exactamente el
    problema que esta herramienta viene a resolver.
    """
    a = forma_de("/propiedad-9871962-venta-casa-1-dormitorio-en-funes")
    b = forma_de("/propiedad-1234567-alquiler-departamento-en-rosario")
    assert a == b == "/<palabra>-<id>-<slug>"


def test_MUERDE_una_categoria_no_parece_ficha():
    """El caso que casi me hace inventar inventario.

    `fios` enlaza `/Terreno-en-venta` y `/Cochera-en-venta` desde el menú. Si
    la heurística de diagnóstico las contara como fichas, la tabla diría que
    esa agencia publica 27 propiedades y no publica ninguna ahí.

    Lo que las separa de una ficha real es el identificador: la categoría tiene
    la palabra y no el número.
    """
    for ruta in ("/Terreno-en-venta", "/Cochera-en-venta", "/Departamentos",
                 "/propiedades", "/venta"):
        assert not parece_ficha(ruta), ruta


def test_una_ficha_real_si_parece_ficha():
    """Las rutas son las que devolvio el escaneo real, no inventadas."""
    for ruta in ("/propiedad-9871962-venta-casa-1-dormitorio-en-funes",
                 "/p/7525662-Casa-en-Venta-en-Salvador-Maria",
                 "/8471-venta-casa-3-ambientes",
                 "/propiedad/452243"):
        assert parece_ficha(ruta), ruta


def test_MUERDE_un_id_sin_nada_que_lo_describa_no_alcanza():
    """`/p/7525662` a secas es ambiguo y la heuristica lo deja afuera.

    Y eso es un SUBCONTEO conocido, no un acierto: si una agencia publicara
    asi, este escaneo no la veria. Esta escrito para que el numero de
    "14 agencias con formas no reconocidas" se lea como un piso y no como un
    total.
    """
    assert not parece_ficha("/p/7525662")


def test_MUERDE_un_numero_solo_no_alcanza():
    """Un año o una paginación tienen número y no son propiedades.

    Pedir número **y** palabra juntas es mucho más difícil de cumplir por
    accidente que cualquiera de las dos sola.
    """
    for ruta in ("/2024/09/nota-del-blog", "/pagina/1234", "/noticias/5678"):
        assert not parece_ficha(ruta), ruta


def test_la_heuristica_de_diagnostico_no_reusa_la_del_conector():
    """Medir con la misma regla que se quiere evaluar no contesta nada.

    `_es_ficha_url` es justamente lo que se está auditando: si esta
    herramienta la reutilizara, reportaría que no se le escapa nada.
    """
    from connectors.generico import GenericoConnector
    ruta = "/propiedad-9871962-venta-casa-en-funes"
    assert parece_ficha(ruta)
    assert not GenericoConnector._es_ficha_url("https://x.com" + ruta)
