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


def _snapshot_de_prueba(con: sqlite3.Connection, planas: bool = True) -> None:
    """Una snapshot minima con la forma real, para medir la consulta."""
    extra = ", area_nombre_plano text, barrio_plano text" if planas else ""
    con.execute(f"create table propiedades (id text, area_nivel text, "
                f"area_nombre text, barrio text{extra})")
    if planas:
        con.execute("create index ix_area_plano on propiedades"
                    "(area_nombre_plano, area_nivel, area_nombre)")
        con.execute("create index ix_barrio_plano on propiedades(barrio_plano, barrio)")
    filas = [("1", "MUNICIPIO", "Córdoba", "Alberdi"),
             ("2", "PROVINCIA", "Córdoba", "Centro"),
             ("3", "LOCALIDAD", "Mar del Plata", "Centro"),
             ("4", "LOCALIDAD", "Corrientes", "Sur")]
    for f in filas:
        if planas:
            con.execute("insert into propiedades values (?,?,?,?,?,?)",
                        f + (sin_acento(f[2]), sin_acento(f[3])))
        else:
            con.execute("insert into propiedades values (?,?,?,?)", f)
    con.commit()


def test_MUERDE_el_rango_devuelve_lo_mismo_que_el_like():
    """El cambio a rango es por velocidad -469 ms contra 2,8- y no puede
    cambiar ni una fila del resultado."""
    con = sqlite3.connect(":memory:")
    _snapshot_de_prueba(con)
    plano = sin_acento("cordo")
    rango = con.execute(
        "select area_nivel, area_nombre from propiedades "
        "where area_nombre_plano >= ? and area_nombre_plano < ? "
        "order by area_nivel", (plano, plano + "\uffff")).fetchall()
    like = con.execute(
        "select area_nivel, area_nombre from propiedades "
        "where area_nombre_plano like ? order by area_nivel",
        (plano + "%",)).fetchall()
    assert rango == like
    assert {n for _, n in rango} == {"Córdoba"}
    con.close()


def test_MUERDE_el_rango_no_se_lleva_de_mas_ni_de_menos():
    """`corri` no puede traer Cordoba, y `cordo` no puede traer Corrientes."""
    con = sqlite3.connect(":memory:")
    _snapshot_de_prueba(con)
    def buscar(q):
        p = sin_acento(q)
        return {r[0] for r in con.execute(
            "select distinct area_nombre from propiedades "
            "where area_nombre_plano >= ? and area_nombre_plano < ?",
            (p, p + "\uffff"))}
    assert buscar("cordo") == {"Córdoba"}
    assert buscar("corri") == {"Corrientes"}
    assert buscar("cor") == {"Córdoba", "Corrientes"}
    assert buscar("mar del") == {"Mar del Plata"}
    con.close()


def test_MUERDE_el_indice_cubre_el_filtro_y_la_agrupacion():
    """El indice de UNA sola columna no alcanzaba: el planificador prefiere
    el que cubre el `group by` y filtra escaneando. Medido, 469 ms contra
    2,8. Si alguien lo simplifica a una columna, esto muerde."""
    con = sqlite3.connect(":memory:")
    _snapshot_de_prueba(con)
    plan = " ".join(r[-1] for r in con.execute(
        "explain query plan select area_nivel, area_nombre, count(*) "
        "from propiedades where area_nombre_plano >= ? and area_nombre_plano < ? "
        "group by area_nivel, area_nombre", ("cordo", "cordo\uffff")))
    assert "ix_area_plano" in plan, plan
    con.close()
