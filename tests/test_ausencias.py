#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Que no la hayamos visto no siempre significa que ya no esté.

La regla de bajas necesita tres corridas seguidas sin ver una propiedad. La
protección real es que el contador **no avance** cuando la ausencia no significa
nada, y eso ya funciona: BTS Propiedades entregó 13 fichas en una corrida y 3 en
la siguiente, el solapamiento dio 23%, la enumeración quedó marcada no
comparable, y sus 10 faltantes cerraron con el contador en cero.

Lo que estaba mal era el renglón. En modo observación se reescribían **todas**
las ausencias como `POTENTIAL_INACTIVE`, incluidas esas 10, así que el artefacto
mostraba 21 candidatas a baja cuando 10 no tenían ninguna evidencia detrás.
Nadie se iba a dar de baja por eso —el contador mandaba— pero cualquiera que
leyera el archivo se iba a llevar una idea equivocada de qué está pasando con
ese inventario.

Un artefacto que dice de más es un problema aunque el código haga lo correcto:
es la clase de dato que alguien mira una vez y usa para decidir.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from connectors.base import (AUSENCIAS_PARA_BAJA,  # noqa: E402
                             SOLAPAMIENTO_MINIMO, clasificar_ausencia)

FUENTE = (Path(__file__).resolve().parents[1] / "scripts"
          / "run_rollout.py").read_text(encoding="utf-8")


def test_una_fuente_caida_no_prueba_ninguna_baja():
    """Un 502 de diez minutos daría de baja el catálogo entero."""
    assert clasificar_ausencia({}, "h1", fuente_respondio=False) == \
        "SIN_EVIDENCIA_FUENTE_CAIDA"


def test_una_ausencia_sola_no_alcanza():
    est = {"ausencias": {"h1": 1}}
    assert clasificar_ausencia(est, "h1", True) == "AUSENTE_PROVISORIA"


def test_recien_a_las_tres_se_confirma():
    est = {"ausencias": {"h1": AUSENCIAS_PARA_BAJA}}
    assert clasificar_ausencia(est, "h1", True) == "BAJA_CONFIRMADA"
    est = {"ausencias": {"h1": AUSENCIAS_PARA_BAJA - 1}}
    assert clasificar_ausencia(est, "h1", True) == "AUSENTE_PROVISORIA"


def test_el_umbral_de_solapamiento_sigue_exigiendo_la_mitad():
    """Por debajo de esto no estamos viendo bajas: estamos viendo dos vistas
    distintas del mismo sitio."""
    assert SOLAPAMIENTO_MINIMO == 0.5


def test_observacion_no_llama_candidata_a_lo_que_no_es_comparable():
    """El caso BTS: 3 fichas de 13, y sus 10 faltantes salían como candidatas a
    baja con el contador en cero."""
    assert 'if x.get("enumeracion_comparable"):' in FUENTE
    assert "SIN_EVIDENCIA_ENUMERACION_NO_COMPARABLE" in FUENTE


def test_en_observacion_no_se_desactiva_nada():
    """Ninguna corrida escribe una baja: sólo se anota."""
    assert "POTENTIAL_INACTIVE" in FUENTE
    for prohibido in ("DELETE FROM", "estado = 'inactiva'", "desactivar("):
        assert prohibido not in FUENTE


def test_el_contador_solo_avanza_cuando_la_ausencia_significa_algo():
    base = (Path(__file__).resolve().parents[1] / "connectors"
            / "base.py").read_text(encoding="utf-8")
    assert "cuenta = fuente_respondio and comparable" in base
    # y el solapamiento se calcula contra lo que ya se habia visto
    assert "solapamiento = len(previos & vistos_ahora) / len(previos)" in base
