#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Donde vive el estado operativo de ERETZ, configurable (checkpoint cloud del 29-09).

Todo el estado que no va al repo -ledger, paquetes, preingestion, GeoRef, snapshot servida,
directorios de identidad- vive bajo UNA raiz. En la maquina original es `D:\\INMO CAPITAL`; en
cualquier otra se fija con la variable de entorno `ERETZ_DATA_ROOT` y se restaura ahi el
paquete de estado (`docs/agent/ESTADO_DURABLE.md`). Sin la variable, nada cambia.

Los scripts de un solo uso de otras epocas siguen con rutas por argumento; el nucleo (API,
geografia, cola, certificador, snapshot, despliegue, Regression Gate) pasa por aca.
"""
from __future__ import annotations

import os
from pathlib import Path

RAIZ_POR_DEFECTO = r"D:\INMO CAPITAL"


def raiz_de_datos() -> Path:
    """La raiz del estado operativo: `ERETZ_DATA_ROOT` o la de la maquina original."""
    return Path(os.environ.get("ERETZ_DATA_ROOT") or RAIZ_POR_DEFECTO)


def dato(*partes: str) -> Path:
    """Una ruta del estado operativo, relativa a la raiz."""
    return raiz_de_datos().joinpath(*partes)
