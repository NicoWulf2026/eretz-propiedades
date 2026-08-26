#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""La cadencia de relectura sale de lo que cada fuente hace.

Entre la corrida 2 y la 3 de Tokko, el 99,83% del inventario estaba igual.
Recorrer todo todos los dias gasta casi todo el presupuesto en confirmar que
nada cambio; bajarlo parejo deja atrasada a la inmobiliaria que publica todas
las semanas.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.plan_recrawl import (MAXIMO_DIAS, MINIMO_DIAS,  # noqa: E402
                                  cadencia, tasa_de_cambio)


def inventario(**kw):
    base = {"canonical_agency_id": "ag-1", "estado": "OK",
            "detalles_obtenidos": 100, "cambios": {"SIN_CAMBIOS": 100},
            "ausentes": 0}
    return {**base, **kw}


def test_la_que_se_mueve_se_lee_seguido():
    fila = inventario(cambios={"SIN_CAMBIOS": 80, "NUEVA": 15, "MODIFICADA": 5})
    tasa, movidas, total = tasa_de_cambio([fila])
    assert movidas == 20 and total == 100 and tasa == 0.2
    assert cadencia(tasa, "OK", 2)[0] == MINIMO_DIAS


def test_la_que_no_cambio_nada_espera():
    tasa, movidas, _ = tasa_de_cambio([inventario()])
    assert movidas == 0 and tasa == 0.0
    assert cadencia(tasa, "OK", 3)[0] == MAXIMO_DIAS


def test_una_baja_cuenta_como_movimiento():
    """Una propiedad que desaparecio es un cambio del inventario tanto como una
    que aparecio."""
    tasa, movidas, _ = tasa_de_cambio([inventario(ausentes=12)])
    assert movidas == 12 and tasa == 0.12


def test_no_supimos_leerla_no_se_arregla_volviendo_manana():
    """334 fuentes pedian lectura diaria por esto. Volver 365 veces al ano da
    365 veces el mismo resultado: lo que falta es un connector."""
    dias, motivo = cadencia(0.0, "VARIANTE_NO_SOPORTADA", 3)
    assert dias == MAXIMO_DIAS and "connector" in motivo


def test_un_fallo_pasajero_si_se_reintenta_pronto():
    dias, motivo = cadencia(0.0, "BLOQUEADA", 3)
    assert dias == MINIMO_DIAS and "pasajero" in motivo


def test_con_una_sola_corrida_no_hay_con_que_comparar():
    """La primera corrida marca todo NUEVA: leer eso como "cambio el 100%"
    mandaria a lectura diaria a todas las fuentes recien incorporadas."""
    fila = inventario(cambios={"NUEVA": 100})
    tasa, _, _ = tasa_de_cambio([fila])
    assert tasa == 1.0
    assert cadencia(tasa, "OK", 1)[0] == 3


def test_la_cadencia_nunca_se_va_de_rango():
    for estado in ("OK", "BLOQUEADA", "VARIANTE_NO_SOPORTADA", "RARO"):
        for tasa in (0.0, 0.001, 0.05, 0.5, 1.0):
            for corridas in (1, 2, 9):
                dias, motivo = cadencia(tasa, estado, corridas)
                assert MINIMO_DIAS <= dias <= MAXIMO_DIAS
                assert motivo
