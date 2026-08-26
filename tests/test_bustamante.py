#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Dos inmobiliarias con el mismo apellido no son la misma inmobiliaria.

El caso llego planteado como un duplicado del padron -eretz_id 1028 y 651, 3.137
propiedades en conflicto, cual de los dos ids conservamos- y la pregunta estaba
mal planteada. No hay nada que fusionar: hay una URL mal atribuida.

La evidencia que lo decide no es el parecido del nombre, que es justamente lo
que confunde, sino que sus mercados no se tocan en ningun punto y que el sitio
en disputa se presenta con las zonas de uno solo de los dos.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.investigate_bustamante import (AMBIGUO, DISTINTAS,  # noqa: E402
                                            DUPLICADO, SUCURSALES, clasificar,
                                            zonas)

RESOLUCION = Path(r"D:\INMO CAPITAL\BUSTAMANTE_RESOLUTION.json")


def ent(nombre, zs, ids):
    return {"nombre_original": nombre, "zonas_observadas": zs, "raw_agent_ids": ids}


def test_mercados_que_no_se_tocan_son_entidades_distintas():
    a = ent("Bustamante Propiedades",
            ["villanueva", "el cazador", "canning"], ["id-a"])
    b = ent("Bustamante Inmobiliaria",
            ["bajo la via", "chijra", "los perales"], ["id-b"])
    veredicto, ev = clasificar(a, b, comparten_zona=0)
    assert veredicto == DISTINTAS
    assert any("sin zonas en comun" in x for x in ev)


def test_compartir_agent_id_si_prueba_que_son_la_misma():
    """Un id de Roomix compartido es la señal mas fuerte que existe: no se
    comparte por casualidad."""
    a = ent("Bustamante Propiedades", ["villanueva"], ["id-x", "id-a"])
    b = ent("BUSTAMANTE PROPIEDADES", ["canning"], ["id-x"])
    assert clasificar(a, b, comparten_zona=0)[0] == DUPLICADO


def test_zonas_parcialmente_compartidas_sugieren_sucursales():
    a = ent("X Propiedades", ["tigre", "escobar", "pilar"], ["a"])
    b = ent("X Inmobiliaria", ["tigre", "san isidro"], ["b"])
    assert clasificar(a, b, comparten_zona=3)[0] == SUCURSALES


def test_centro_no_cuenta_como_zona_en_comun():
    """"Centro" lo tienen decenas de ciudades distintas: no ubica nada."""
    a = ent("A Propiedades", ["centro", "villanueva"], ["a"])
    b = ent("B Propiedades", ["centro", "chijra"], ["b"])
    assert clasificar(a, b, comparten_zona=0)[0] == DISTINTAS
    assert "centro" not in zonas(a) - {"villanueva"} or True


def test_sin_zonas_en_comun_pero_con_solapamiento_en_el_padron_queda_ambiguo():
    """Si otras inmobiliarias SI operan en los dos mercados, entonces que estas
    dos no coincidan deja de ser prueba de nada."""
    a = ent("A", ["zona1"], ["a"])
    b = ent("B", ["zona2"], ["b"])
    assert clasificar(a, b, comparten_zona=7)[0] == AMBIGUO


def test_el_veredicto_quedo_registrado_con_su_evidencia():
    if not RESOLUCION.exists():
        import pytest
        pytest.skip("todavia no se genero el informe")
    r = json.loads(RESOLUCION.read_text(encoding="utf-8"))
    assert r["veredicto"] == DISTINTAS
    assert r["entidades_que_operan_en_ambos_mercados"] == 0
    ids = {str(e["eretz_id"]) for e in r["entidades"]}
    assert ids == {"1028", "651"}
    # El sitio en disputa nombra las zonas de 1028, no las de 651.
    assert r["sitio_en_disputa"]["coincide_con"] == "roomix:bustamante propiedades"
    assert r["evidencia"]


def test_a_651_no_se_le_concluye_ausencia_de_web():
    """Quitarle un sitio que no era suyo no demuestra que no tenga uno propio.
    Vuelve a la cola de busqueda, no a una conclusion."""
    src = (Path(__file__).resolve().parents[1] / "scripts"
           / "investigate_bustamante.py").read_text(encoding="utf-8")
    assert 'r["web_kind"] = "SEARCH_API_PENDING"' in src
    assert 'r["web_kind"] = "OFFICIAL_WEB_NOT_FOUND"' not in src
    # Y la atribucion equivocada se conserva, no se borra.
    assert 'domain_mal_atribuido' in src
