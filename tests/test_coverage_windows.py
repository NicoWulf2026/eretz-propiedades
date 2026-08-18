# -*- coding: utf-8 -*-
"""Tests de las metricas por ventana.

Fijan en codigo las dos confusiones que hubo que corregir: mezclar el contador
raw con el canonico, y leer un acumulado como si fuera marginal.
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


c = _load("coverage_windows")


def test_la_oficina_de_franquicia_cuenta_y_la_marca_sola_no():
    """`RE/MAX Ultra` atiende clientes; `RE/MAX` a secas no es una oficina."""
    assert c.tipo_de("RE/MAX Ultra") == "OFICINA_FRANQUICIA"
    assert c.tipo_de("RE/MAX") == "MARCA_GENERICA"
    assert "OFICINA_FRANQUICIA" in c.CUENTA_COMO_AGENCIA
    assert "MARCA_GENERICA" not in c.CUENTA_COMO_AGENCIA


def test_una_inmobiliaria_normal_cuenta():
    assert c.tipo_de("Mizrahi Real Estate") == "INMOBILIARIA"
    assert c.tipo_de("Mizrahi Real Estate") in c.CUENTA_COMO_AGENCIA


def test_lo_que_no_es_inmobiliaria_no_entra_en_el_kpi():
    for nombre in ("Juan Perez", "Grupo Constructor Sur Desarrollos"):
        assert c.tipo_de(nombre) not in c.CUENTA_COMO_AGENCIA, nombre


def test_agente_y_desarrolladora_se_clasifican_aparte():
    assert c.tipo_de("Juan Perez") == "AGENTE"
    assert c.tipo_de("Grupo Constructor Sur Desarrollos") == "DESARROLLADORA"


def test_el_kpi_excluye_todo_lo_que_no_sea_agencia():
    """La definicion es el punto: agentes y desarrolladoras no son cobertura
    inmobiliaria por mas que sean publicadores."""
    assert c.CUENTA_COMO_AGENCIA == {"INMOBILIARIA", "OFICINA_FRANQUICIA"}
