# -*- coding: utf-8 -*-
"""Tests del backfill de nombre_normalizado.

Lo que importa no es cuantas filas llena, sino cuales se niega a llenar. Poblar
la columna con un valor que colisiona convierte un dato faltante en uno
ambiguo, y el ambiguo no se nota.
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


bf = _load("backfill_main_normalizado")
d = _load("eretz_dedupe")


def F(id_, nombre, norm=None, fuente="cocir"):
    return {"id": id_, "nombre": nombre, "nombre_normalizado": norm,
            "ciudad": None, "provincia": None, "web": None, "fuente": fuente}


def test_una_fila_sin_conflicto_se_puede_escribir():
    a = bf.analizar([F(1, "VANZINI PROPIEDADES")])
    assert len(a["seguros"]) == 1
    assert a["seguros"][0]["normalizado_propuesto"] == "vanzini propiedades"


def test_usa_el_normalizador_canonico():
    a = bf.analizar([F(1, "FIOS Consultoría Inmobiliaria")])
    assert a["seguros"][0]["normalizado_propuesto"] == d.norm_name("FIOS Consultoría Inmobiliaria")


def test_dos_nulas_que_normalizan_igual_no_se_escriben():
    """Serian dos entidades distintas con la misma clave."""
    a = bf.analizar([F(1, "Sur Propiedades"), F(2, "SUR PROPIEDADES")])
    assert a["seguros"] == []
    assert len(a["conflictos"]) == 2
    assert all("normalizan igual" in c["motivo"] for c in a["conflictos"])


def test_una_nula_que_choca_con_una_ya_normalizada_no_se_escribe():
    a = bf.analizar([F(1, "Sur Propiedades", norm="sur propiedades"),
                     F(2, "SUR PROPIEDADES")])
    assert a["seguros"] == []
    assert a["conflictos"][0]["ya_existentes_con_la_misma_clave"] == [1]


def test_nombre_que_no_produce_clave_util_queda_afuera():
    a = bf.analizar([F(1, "--"), F(2, "")])
    assert a["seguros"] == [] and len(a["sin_clave"]) == 2


def test_las_ya_normalizadas_no_se_tocan():
    a = bf.analizar([F(1, "Alfa Propiedades", norm="valor previo raro")])
    assert a["nulas"] == 0 and a["seguros"] == []


def test_el_conteo_por_fuente_permite_priorizar():
    a = bf.analizar([F(1, "Alfa Propiedades", fuente="cocir"),
                     F(2, "Beta Propiedades", fuente="excel_propio"),
                     F(3, "Gama Propiedades", fuente="cocir")])
    assert a["por_fuente_nulas"]["cocir"] == 2
    assert a["por_fuente_nulas"]["excel_propio"] == 1


def test_el_update_es_idempotente_por_construccion():
    """El WHERE repite `is null`, asi que reejecutar no pisa nada."""
    assert "nombre_normalizado is null" in bf.UPDATE_UNA.lower()


def test_el_analisis_no_escribe_nada():
    """analizar() es puro: no recibe conexion ni la puede abrir."""
    import inspect
    src = inspect.getsource(bf.analizar)
    for prohibido in ("connect", "execute", "commit", "update"):
        assert prohibido not in src.lower(), prohibido
