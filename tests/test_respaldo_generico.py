# -*- coding: utf-8 -*-
"""El respaldo a `generico` tiene que mejorar, no solo traer algo.

El respaldo existe para un caso real y sigue siendo bueno: una plataforma
declarada puede haber cambiado. Su docstring cuenta el ejemplo —
`requenapropiedades.com.ar` es una app Laravel a la que se le habia asignado
el connector de WordPress porque el HTML menciona `wp-content`—.

Lo que faltaba era comparar con algo. La condicion era «que haya obtenido
algo», y con eso alcanzaba para reemplazar una enumeracion de 196 por una de
17:

  - `austral inmobiliaria` certifico CERTIFIED_COMPLETE el 2026-09-10 con el
    connector de WordPress y 196 propiedades. El 2026-09-21 ese connector
    volvio vacio —su API responde: declara `X-WP-Total: 200` y su `discover`
    da `WORDPRESS_REST soportada=true`—, entro generico, trajo 17 recorriendo
    el menu, y se acepto contra un baseline de 191.
  - `forja propiedades`: de tokko a generico, 7 contra un baseline de 350.

La distincion: un connector que vuelve vacio puede estar equivocado —y ahi el
respaldo es la salida— o puede haber tenido un mal minuto —y ahi es un
downgrade—. El baseline los separa.

Aplicada a los 22 casos reales del corpus que usaron el respaldo, la regla lo
sigue usando en 19 y lo rechaza en 3: `austral`, `forja` y `carlos castano`
—cuyo sitio migro de WordPress a Laravel y hoy publica cero; su «1» era el
enlace del menu, no una propiedad—.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from scripts.agency_certifier import (PISO_DEL_RESPALDO,  # noqa: E402
                                      el_respaldo_mejora)


def corrida(enumeradas: int, estado: str = "OK") -> dict:
    return {"enumeradas": enumeradas, "estado": estado,
            "detalles_obtenidos": enumeradas}


def test_MUERDE_el_caso_austral():
    """196 propiedades reemplazadas por 17."""
    assert el_respaldo_mejora(corrida(17), 191) is False


def test_MUERDE_el_caso_forja():
    assert el_respaldo_mejora(corrida(7), 350) is False


def test_MUERDE_el_caso_que_el_respaldo_existe_para_resolver():
    """`requenapropiedades`: sin baseline, cualquier cosa es mejor que nada.

    Si esto se rompe, el respaldo deja de servir para lo unico que lo
    justifica.
    """
    assert el_respaldo_mejora(corrida(152), None) is True
    assert el_respaldo_mejora(corrida(152), 0) is True


def test_MUERDE_un_inventario_que_CRECIO_se_acepta():
    """`baron inmobiliaria` paso de 49 a 227 sin que tocaramos una linea."""
    assert el_respaldo_mejora(corrida(227), 49) is True


def test_una_diferencia_chica_se_acepta():
    """`alas` 206 contra 222, `d amato` 101 contra 102, `ciam` 46 contra 48.
    Un catalogo se mueve solo; el piso esta para los derrumbes."""
    assert el_respaldo_mejora(corrida(206), 222) is True
    assert el_respaldo_mejora(corrida(101), 102) is True
    assert el_respaldo_mejora(corrida(46), 48) is True


def test_el_piso_es_inclusivo_y_lo_que_sigue_no_pasa():
    """La frontera expresada contra la CONSTANTE y no contra un numero, que
    es el vicio que ya aparecio en otros tests de este repo."""
    base = 200
    justo = int(base * PISO_DEL_RESPALDO)
    assert el_respaldo_mejora(corrida(justo), base) is True
    assert el_respaldo_mejora(corrida(justo - 1), base) is False


def test_MUERDE_un_respaldo_vacio_nunca_se_usa():
    """La condicion vieja seguia valiendo y no puede perderse."""
    assert el_respaldo_mejora({"enumeradas": 0, "estado": "ERROR",
                               "detalles_obtenidos": 0}, 100) is False
    assert el_respaldo_mejora({"enumeradas": 0, "estado": "ERROR",
                               "detalles_obtenidos": 0}, None) is False


def test_un_respaldo_en_OK_sin_detalles_todavia_cuenta():
    """La condicion original aceptaba `estado OK` aunque no hubiera detalles
    -una agencia sin inventario es un cierre valido-. No se toca."""
    assert el_respaldo_mejora({"enumeradas": 0, "estado": "OK",
                               "detalles_obtenidos": 0}, None) is True
