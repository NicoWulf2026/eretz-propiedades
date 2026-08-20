# -*- coding: utf-8 -*-
"""Tests del cierre determinista del delta.

El punto: un delta puede traer miles de avisos y cientos de agent_id y aun asi
contar como cero, porque lo que cierra el padron son las entidades
inmobiliarias, no la actividad.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


dl = _load("delta_loop")


def test_solo_cuentan_inmobiliaria_y_oficina():
    assert dl.OBJETIVO == ("INMOBILIARIA", "OFICINA_FRANQUICIA")


def test_un_delta_con_agentes_y_developers_cuenta_como_cero():
    """Actividad no es descubrimiento."""
    antes = {"alfa propiedades": "INMOBILIARIA"}
    despues = {**antes, "juan perez": "AGENTE",
               "grupo constructor sur desarrollos": "DESARROLLADORA"}
    a = dl.auditar(antes, despues, {})
    assert a["NEW_TARGET_ENTITIES"] == 0
    assert a["NEW_AGENTE"] == 1 and a["NEW_DESARROLLADORA"] == 1
    # pero no se ocultan: siguen reportandose
    assert a["canonical_nuevas"] == 2


def test_una_inmobiliaria_nueva_rompe_el_cierre():
    a = dl.auditar({}, {"beta propiedades": "INMOBILIARIA"}, {})
    assert a["NEW_INMOBILIARIA"] == 1 and a["NEW_TARGET_ENTITIES"] == 1


def test_una_oficina_de_franquicia_nueva_tambien_cuenta():
    a = dl.auditar({}, {"remax ultra": "OFICINA_FRANQUICIA"}, {})
    assert a["NEW_TARGET_ENTITIES"] == 1


def test_la_marca_generica_no_cuenta():
    a = dl.auditar({}, {"remax": "MARCA_GENERICA"}, {})
    assert a["NEW_TARGET_ENTITIES"] == 0 and a["NEW_MARCA_GENERICA"] == 1


def test_un_unknown_con_sustancia_bloquea_el_cierre():
    """Todavia podria resolverse como inmobiliaria con mas evidencia."""
    a = dl.auditar({}, {"torres y asociados": "UNKNOWN"},
                   {"torres y asociados": "Torres y Asociados"})
    assert a["NEW_UNKNOWN_POTENCIALMENTE_INMOBILIARIA"] == 1


def test_un_unknown_sin_sustancia_no_bloquea():
    """Ver mas avisos de `ab` no lo va a convertir en inmobiliaria."""
    a = dl.auditar({}, {"ab": "UNKNOWN"}, {"ab": "ab"})
    assert a["NEW_UNKNOWN_POTENCIALMENTE_INMOBILIARIA"] == 0


def test_la_basura_nunca_bloquea():
    assert not dl.puede_ser_inmobiliaria("Usuario")
    assert not dl.puede_ser_inmobiliaria("particular")


def test_ninguna_categoria_queda_sin_reportar():
    a = dl.auditar({}, {}, {})
    for k in ("NEW_INMOBILIARIA", "NEW_OFICINA_FRANQUICIA", "NEW_AGENTE",
              "NEW_DESARROLLADORA", "NEW_MARCA_GENERICA", "NEW_UNKNOWN",
              "NEW_UNKNOWN_POTENCIALMENTE_INMOBILIARIA", "canonical_nuevas",
              "NEW_TARGET_ENTITIES"):
        assert k in a, k
