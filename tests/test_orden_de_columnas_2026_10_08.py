"""Las columnas anchas van al final y las inserciones nombran columnas (08-10, rendimiento del mapa)."""
from __future__ import annotations

import sqlite3

from scripts.api_snapshot import COLUMNAS_DE_FILA, ESQUEMA, INSERTAR_FILA


def _columnas(con):
    return [r[1] for r in con.execute("pragma table_info(propiedades)")]


def test_las_columnas_anchas_estan_al_final_y_la_insercion_las_cubre_todas():
    con = sqlite3.connect(":memory:")
    con.executescript(ESQUEMA)
    fisicas = _columnas(con)
    assert fisicas[-4:] == ["titulo", "descripcion", "alcances", "documento"]
    assert set(COLUMNAS_DE_FILA) == set(fisicas) and len(COLUMNAS_DE_FILA) == len(fisicas)


def test_una_fila_servida_con_el_orden_viejo_cae_en_sus_columnas():
    # La servida (rc5) tiene titulo/descripcion en la posicion 4-5; la fila se copia por NOMBRE.
    vieja = sqlite3.connect(":memory:")
    viejo_orden = ["id", "agency_id", "source_url", "titulo", "descripcion"] + [
        c for c in COLUMNAS_DE_FILA if c not in ("id", "agency_id", "source_url", "titulo", "descripcion")]
    vieja.execute(f"create table propiedades ({', '.join(viejo_orden)})")
    valores = {c: f"v_{c}" for c in viejo_orden}
    vieja.execute(f"insert into propiedades values ({','.join('?' * len(viejo_orden))})",
                  [valores[c] for c in viejo_orden])
    cur = vieja.execute("select * from propiedades")
    fila = dict(zip([d[0] for d in cur.description], cur.fetchone()))
    nueva = sqlite3.connect(":memory:")
    nueva.executescript(ESQUEMA)
    nueva.execute(f"insert or replace into propiedades ({', '.join(fila)}) values ({','.join('?' * len(fila))})",
                  tuple(fila.values()))
    cur = nueva.execute("select titulo, descripcion, latitud, documento from propiedades")
    assert cur.fetchone() == ("v_titulo", "v_descripcion", "v_latitud", "v_documento")
    # y la insercion del constructor usa el mismo mapa por nombre
    assert INSERTAR_FILA.startswith("insert or replace into propiedades (id, agency_id, source_url, titulo")
