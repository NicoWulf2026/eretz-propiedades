# -*- coding: utf-8 -*-
"""Una propiedad que dice «Precio Consulte» sigue siendo una propiedad.

`alma di matteo` perdio sus **6 fichas** y quedo en cero. Son propiedades
reales, hechas a mano en HTML estatico:

    Ranelagh Oeste - Calle 120    U$S 130.000, 8 fotos, 20x54 mts
    Bosco Building                U$S 118.000, 8 fotos
    Quilmes Oeste - A. Roca 3739  «Precio Consulte», 5 atributos, 8 fotos

Fallaban por dos clausulas distintas de `_confirma_ficha`:

  - las dos con precio, por `operacion o dos atributos`: el aviso dice «Se
    escuchan propuestas» en vez de «venta», y solo reconocia UN atributo;
  - las cuatro sin precio, por `precio o schema`: publican `Precio Consulte`
    y no tienen JSON-LD.

La segunda concesion ya estaba razonada en el propio docstring del guardian
—«'consultar precio' es una propiedad publicada, no una nota»— y estaba
implementada **solo** para schema.org.

Los dos umbrales salen de medir el corpus, no de elegir. De las 53 paginas
institucionales distintas que el guardian rechazo en toda la historia:

    45 tienen CERO atributos reconocidos
     4 tienen uno
     0 llegan a cuatro

Las unicas cuatro con cuatro o mas son las propiedades reales de esta
agencia. El hueco entre 1 y 4 es lo que hace seguro el corte. Verificado
bajando las 49 accesibles: **ninguna entra** con la regla nueva, y las 6 de
`alma di matteo` entran todas.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from connectors.generico import (ATRIBUTOS_SIN_PRECIO,  # noqa: E402
                                 FOTOS_MINIMAS, GenericoConnector)

FOTOS = ["f"] * (FOTOS_MINIMAS + 5)


def confirma(texto: str, precio=None, tipo_ld=None, fotos=None) -> bool:
    return GenericoConnector._confirma_ficha(
        "<html><body></body></html>", texto, precio,
        FOTOS if fotos is None else fotos, tipo_ld)


def test_MUERDE_precio_y_un_solo_atributo_alcanzan():
    """El caso `ranelagh`: U$S 130.000, `cochera`, sin la palabra «venta».

    Antes hacian falta dos atributos o la operacion, y el aviso dice «Se
    escuchan propuestas».
    """
    # El texto real de la ficha, con la moneda que la version abreviada de
    # este mismo test se habia comido.
    assert confirma("CARACTERISTICAS Precio U$S 130.000.- Lote 20 x 54 mts "
                    "Sup Total - Cochera - Se escuchan propuestas",
                    precio=130000.0)


def test_MUERDE_sin_precio_pero_describiendo_el_inmueble_en_detalle():
    """El caso `sarmiento`: «Precio Consulte» con cinco atributos.

    La concesion de «consultar precio» ya estaba razonada y solo funcionaba
    con schema.org.
    """
    assert confirma("Precio Consulte Expensas SI Piso 3 Sup Cubierta 96 mts2 "
                    "Cochera SI ambiente dormitorio baño")


def test_MUERDE_una_pagina_institucional_sin_precio_sigue_afuera():
    """`area_cliente.php?sec=sol` y `quienes-somos.php`: cero atributos.

    Si esto entrara, aflojar habria roto justamente lo que el guardian
    protege.
    """
    assert not confirma("Area de clientes solicitudes Nuestra historia "
                        "Quienes somos Contacto")


def test_MUERDE_un_solo_atributo_sin_precio_no_alcanza():
    """Cuatro paginas institucionales del corpus tienen exactamente uno.

    El corte esta del lado seguro del hueco medido: 1 no, 4 si.
    """
    assert not confirma("Nuestra historia. La cochera del edificio.")


def test_el_umbral_es_el_medido_y_no_se_baja_sin_querer():
    """Bajarlo a 2 o 3 acercaria el corte a las institucionales de 1 atributo
    sin ninguna evidencia que lo respalde."""
    assert ATRIBUTOS_SIN_PRECIO == 4
    tres = "ambiente dormitorio baño"
    cuatro = "ambiente dormitorio baño cochera"
    assert not confirma(tres)
    assert confirma(cuatro)


def test_las_fotos_se_siguen_exigiendo():
    """Aflojar el precio no puede aflojar las fotos: son clausulas distintas
    y una ficha sin fotos no es publicable."""
    assert not confirma("ambiente dormitorio baño cochera", fotos=["una"])


def test_una_pagina_editorial_sigue_bloqueada():
    """`og:type=article` manda por encima de todo lo demas."""
    assert not GenericoConnector._confirma_ficha(
        '<html><head><meta property="og:type" content="article"></head></html>',
        "ambiente dormitorio baño cochera Precio Consulte", None, FOTOS)


def test_lo_que_ya_entraba_sigue_entrando():
    """La regla se aflojo, no se cambio: nada de lo aceptado puede caerse."""
    assert confirma("Casa en venta 3 ambientes 2 baños", precio=95000.0)
    assert confirma("Departamento en alquiler dormitorio baño", precio=None,
                    tipo_ld="Product")


def test_MUERDE_un_numero_suelto_no_es_un_precio():
    """Un test que ya existia mordio mi primera version, y tenia razon.

    «Analisis de la superficie construida en 2026» trae un numero y una
    palabra de atributo. Es una nota de mercado, no una propiedad. La regla
    del censo decia «precio CON MONEDA» y el comentario de `RE_OPERACION_TXT`
    ya lo anticipaba; faltaba implementarlo.
    """
    assert not confirma("Analisis de la superficie construida en 2026",
                        precio=1000.0, fotos=["a", "b", "c"])


def test_el_precio_con_moneda_si_habilita_un_solo_atributo():
    """Las dos formas que usan los avisos argentinos."""
    assert confirma("Precio U$S 130.000.- Cochera -", precio=130000.0)
    assert confirma("Cochera. Valor 95.000 dolares", precio=95000.0)
