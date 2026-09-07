"""La entrada del usuario nunca llega a la sentencia SQL."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

# Cargas que rompen una consulta armada por concatenación.
INYECCIONES = (
    "' or '1'='1",
    "'; drop table propiedades; --",
    "\" union select documento from propiedades --",
    "%' --",
    "1); delete from propiedades; --",
    "\\",
)


@pytest.fixture()
def v2(tmp_path, monkeypatch):
    ruta = tmp_path / "snap.sqlite3"
    con = sqlite3.connect(ruta)
    con.executescript("""
        create table propiedades (
            id text primary key, agency_id text not null, source_url text not null,
            titulo text, descripcion text, operacion text, tipo_propiedad text,
            precio real, moneda text, ambientes integer, dormitorios integer,
            banos integer, superficie_total real, superficie_cubierta real,
            imagenes_n integer not null default 0, latitud real, longitud real,
            localidad text, localidad_id text, municipio text, departamento text,
            provincia text, barrio text, area_nivel text not null,
            area_nombre text, geo_estado text, alcances text not null,
            documento text not null);
        create virtual table busqueda using fts5(
            id unindexed, titulo, descripcion, barrio, area_nombre,
            tokenize = "unicode61 remove_diacritics 2");
    """)
    doc = {"id": "h1", "titulo": "Casa", "geo": {"area_busqueda": {"nivel": "LOCALIDAD"}}}
    con.execute(
        "insert into propiedades values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,"
        "?,?,?,?,?,?,?,?,?)",
        ("h1", "roomix:alfa", "https://a.com/1", "Casa", "linda", "venta",
         "casa", 1.0, "USD", 3, 2, 1, None, 100.0, 0, -31.4, -64.2,
         "Rosario", "1", None, None, "Santa Fe", "Centro", "LOCALIDAD",
         "Rosario", None, "[]", json.dumps(doc)))
    con.execute("insert into busqueda values (?,?,?,?,?)",
                ("h1", "Casa", "linda", "Centro", "Rosario"))
    con.commit()
    con.close()

    from api import v2 as modulo
    monkeypatch.setattr(modulo, "SNAPSHOT", ruta)
    return modulo


def _listar(v2, **cambios):
    argumentos = dict(operacion=None, tipo=None, moneda=None, precio_min=None,
                      precio_max=None, area=None, nivel=None, localidad=None,
                      barrio=None, agencia=None, ambientes=None,
                      dormitorios=None, limit=24, offset=0)
    argumentos.update(cambios)
    return v2.listar(**argumentos)


def test_ninguna_inyeccion_altera_la_consulta(v2):
    """Si la entrada llegara a la sentencia, alguna de estas la rompería o
    devolvería filas que el filtro excluye."""
    for carga in INYECCIONES:
        for campo in ("operacion", "tipo", "area", "localidad", "barrio",
                      "agencia", "moneda", "nivel"):
            r = _listar(v2, **{campo: carga})
            assert r["total"] == 0, f"{campo}={carga!r} devolvio filas"


def test_la_tabla_sigue_estando_despues_de_las_inyecciones(v2):
    """Un `drop table` que pasara dejaría la siguiente consulta sin tabla."""
    for carga in INYECCIONES:
        _listar(v2, localidad=carga)
    assert _listar(v2)["total"] == 1


def test_la_busqueda_no_falla_con_sintaxis_de_fts(v2):
    """FTS5 tiene su propia sintaxis: un `"` o un `*` sin escapar hacen fallar
    la consulta con un error de sintaxis en vez de no encontrar nada."""
    for carga in INYECCIONES + ("*", '"', "NEAR(", "col:valor"):
        r = v2.buscar(q=carga, operacion=None, tipo=None, limit=5, offset=0)
        assert r["total"] >= 0


def test_el_where_solo_contiene_placeholders(v2):
    """La comprobación estructural: el SQL que se arma no lleva NADA del texto
    del usuario, sólo nombres de columna fijos y `?`."""
    import re

    from api.v2 import _filtros

    donde, valores = _filtros("' or 1=1 --", "casa'; drop--", "USD", 1, 2,
                              "area'", "LOCALIDAD", "loc'", "bar'", "ag'",
                              3, 2)
    assert "or 1=1" not in donde and "drop" not in donde
    # Todo lo que no sea nombre de columna, operador o `?` es sospechoso.
    assert not re.search(r"['\"]", donde), donde
    assert donde.count("?") == len(valores)


def test_las_sugerencias_tampoco_interpolan(v2):
    for carga in INYECCIONES:
        r = v2.sugerencias(q=carga if len(carga) >= 2 else "ab", limit=5)
        assert isinstance(r["data"], list)


def test_la_paginacion_profunda_no_es_un_boton_de_denegacion(v2):
    """La ventana de ranking crecía con el offset: `limit=100&offset=5000`
    puntuaba 25.500 filas y tardaba diez segundos, lo que convierte la búsqueda
    en un botón de denegación de servicio para cualquiera que sepa escribir un
    número grande."""
    from fastapi import HTTPException

    from api.v2 import TOPE_DE_OFFSET_RANKEADO, TOPE_DE_VENTANA

    with pytest.raises(HTTPException) as e:
        v2.buscar(q="casa", operacion=None, tipo=None, limit=100,
                  offset=TOPE_DE_OFFSET_RANKEADO + 1)
    assert e.value.status_code == 400
    # Y el mensaje dice a dónde ir, no sólo que no.
    assert "/v2/propiedades" in e.value.detail

    # La ventana tiene tope absoluto, no relativo al offset.
    assert TOPE_DE_VENTANA < 10 * TOPE_DE_OFFSET_RANKEADO


def test_el_listado_si_pagina_profundo(v2):
    """La paginación profunda tiene su lugar: `/propiedades` ordena por índice
    y es estable, así que no necesita tope."""
    r = _listar(v2, offset=1000)
    assert r["total"] == 1
    assert r["data"] == []
