# -*- coding: utf-8 -*-
"""`cordo` no encontraba Cordoba.

`collate nocase` de SQLite pliega mayusculas **ASCII** y no toca los acentos,
asi que la comparacion por prefijo se rompia en la segunda letra. Medido
contra la snapshot antes del arreglo:

    q='cordo'   ->  0 areas
    q='córdo'   ->  3 areas  (municipio 2.050, provincia 937, localidad 208)

Quien escribe sin acento es casi todo el mundo.

El plegado tiene que **conservar los espacios**: `_plegar`, que ya existia en
el mismo modulo, convierte todo en slug con guiones, y entonces `mar del`
deja de ser prefijo de `mar del plata`.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from api.slugs import _plegar, sin_acento  # noqa: E402
from api.v2 import _tiene_columnas_planas  # noqa: E402


def test_MUERDE_el_caso_cordoba():
    assert sin_acento("Córdoba") == "cordoba"
    assert sin_acento("cordoba").startswith("cordo")
    assert sin_acento("Córdoba").startswith("cordo")


def test_MUERDE_los_espacios_se_conservan():
    """Si esto se rompe, `mar del` deja de encontrar `Mar del Plata`.

    Es la razon de no reusar `_plegar`, que esta en el mismo modulo y hace
    casi lo mismo.
    """
    assert sin_acento("Mar del Plata") == "mar del plata"
    assert sin_acento("Mar del Plata").startswith(sin_acento("mar del"))
    # La diferencia con el que ya existia, escrita:
    assert _plegar("Mar del Plata") == "mar-del-plata"


def test_las_provincias_con_acento_del_catalogo():
    assert sin_acento("Neuquén") == "neuquen"
    assert sin_acento("Tucumán") == "tucuman"
    assert sin_acento("Entre Ríos") == "entre rios"
    assert sin_acento("Ciudad Autónoma de Buenos Aires").startswith("ciudad auto")


def test_lo_que_no_es_texto_no_explota():
    assert sin_acento(None) == ""
    assert sin_acento(123) == ""
    assert sin_acento("") == ""


def test_MUERDE_una_snapshot_vieja_se_detecta_y_no_se_rompe():
    """El respaldo importa: la snapshot se regenera cada tanto y la API
    puede arrancar contra una anterior. Sin esto fallaria con `no such
    column` en vez de responder mas lento."""
    con = sqlite3.connect(":memory:")
    con.execute("create table propiedades (id text, area_nombre text, barrio text)")
    assert _tiene_columnas_planas(con) is False
    con.close()


def test_una_snapshot_nueva_se_detecta():
    con = sqlite3.connect(":memory:")
    con.execute("create table propiedades (id text, area_nombre text, "
                "barrio text, area_nombre_plano text, barrio_plano text)")
    assert _tiene_columnas_planas(con) is True
    con.close()


def test_MUERDE_con_una_sola_de_las_dos_columnas_no_alcanza():
    """Una snapshot a medio migrar no puede usar el camino rapido: la
    consulta de barrios fallaria."""
    con = sqlite3.connect(":memory:")
    con.execute("create table propiedades (id text, area_nombre text, "
                "barrio text, area_nombre_plano text)")
    assert _tiene_columnas_planas(con) is False
    con.close()
