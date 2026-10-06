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

# La raiz por defecto es la carpeta que CONTIENE al repo: el estado vive al lado de
# los worktrees (`<raiz>/eretz-unified`, `<raiz>/ERETZ_AGENCY_CERTIFICATION_20260827`).
# Era `D:\INMO CAPITAL` fijo, y el 2026-10-04 la maquina movio todo de D: a E:: una
# ruta fija habria seguido leyendo y escribiendo el disco viejo sin avisar.
RAIZ_POR_DEFECTO = str(Path(__file__).resolve().parents[2])

# Donde se escribieron los manifiestos y paquetes viejos, que guardan rutas absolutas.
# No son la raiz vigente: solo sirven para reubicar esas rutas en la actual. Las dos
# llevan el nombre historico del proyecto: `D:\INMO CAPITAL` hasta el 03-10 y
# `E:\INMO CAPITAL` hasta la migracion definitiva del 04-10 a `E:\ERETZ Propiedades`.
RAICES_HISTORICAS = (r"D:\INMO CAPITAL", r"E:\INMO CAPITAL")
RAIZ_ORIGINAL = RAICES_HISTORICAS[0]  # alias de compatibilidad


def raiz_de_datos() -> Path:
    """La raiz del estado operativo: `ERETZ_DATA_ROOT` o la de la maquina original."""
    return Path(os.environ.get("ERETZ_DATA_ROOT") or RAIZ_POR_DEFECTO)


def dato(*partes: str) -> Path:
    """Una ruta del estado operativo, relativa a la raiz."""
    return raiz_de_datos().joinpath(*partes)
