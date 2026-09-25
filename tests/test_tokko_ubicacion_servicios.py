# -*- coding: utf-8 -*-
"""La ubicacion de Tokko termina donde empieza la lista de servicios.

Cocheras, lotes y locales publican «Ubicación Victoria Agua Corriente No Agua
Potable No Cable No Cloaca No (REF. FGA8052165)». Sin esas etiquetas como
frontera el valor no encontraba donde cortar dentro de los 70 caracteres y la
ubicacion quedaba vacia: 32 de 33 agencias tokko muestreadas con fichas sin
ciudad ni barrio tenian este patron (2026-09-24).
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from connectors.tokko import _campo  # noqa: E402


def test_MUERDE_la_ubicacion_corta_en_agua_corriente():
    texto = ("Dirección Constitucion al 3200 -1- Ubicación Victoria Agua Corriente No "
             "Agua Potable No Cable No Cloaca No (REF. FGA8052165) INFORMACIÓN BÁSICA")
    assert _campo(texto, "Ubicación") == "Victoria"
    assert _campo(texto, "Dirección") == "Constitucion al 3200 -1-"


def test_MUERDE_la_ubicacion_corta_en_cloaca_y_en_zonificacion():
    assert _campo("Ubicación Plottier Cloaca Si Gas Natural Si", "Ubicación") == "Plottier"
    texto = "Ubicación Las Acequias Zonificación Residencial Agua Potable Si"
    assert _campo(texto, "Ubicación") == "Las Acequias"


def test_un_nombre_con_gas_o_luz_no_se_corta():
    assert _campo("Ubicación Villa Luz Agua Corriente Si", "Ubicación") == "Villa Luz"
    assert _campo("Ubicación Barrio Gas Sur Cloaca Si", "Ubicación") == "Barrio Gas Sur"
