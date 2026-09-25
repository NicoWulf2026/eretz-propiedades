"""La snapshot declara como guardo sus filas; la API usa SOLO lo declarado.

Dos atajos medidos sobre las 57.665 de la snapshot v4, con las mismas
respuestas en nueve consultas:
- la ventana de candidatos de la busqueda rankeada se elige «por id»; si las
  filas se insertaron en orden de id, el `rowid` del indice de texto ya es
  ese orden (explorer 304 -> 75 ms);
- si cada fila de texto lleva el `rowid` de su propiedad, se unen por `rowid`
  y no por un `id` de texto (combinada 908 -> 251 ms).

Un atajo que la snapshot no declara no se toma: una snapshot vieja, o una
armada a mano, sigue con el camino lento y correcto.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


# ---------------------------------------------------------------- el builder

def _construir(tmp_path, monkeypatch, hashes):
    origen = tmp_path / "pre.sqlite3"
    con = sqlite3.connect(origen)
    con.execute("create table rows (row_json text, canonical_id text, "
                "hash_dedup text, status text)")
    for i, h in enumerate(hashes):
        fila = {"hash_dedup": h, "canonical_agency_id": "roomix:alfa",
                "source_url": f"https://a.com/{i}", "titulo": f"Casa {i}"}
        con.execute("insert into rows values (?,?,?,?)",
                    (json.dumps(fila), "roomix:alfa", h, "CANDIDATE"))
    con.commit()
    con.close()
    salida = tmp_path / "out"
    salida.mkdir()
    vacio = tmp_path / "vacio.jsonl"
    vacio.write_text("", encoding="utf-8")

    from scripts import api_snapshot
    monkeypatch.setattr(sys, "argv", [
        "snap", "--db", str(origen), "--gate", str(vacio),
        "--cobertura", str(vacio), "--salida", str(salida)])
    monkeypatch.setattr(api_snapshot, "exigir_base_vigente", lambda r: Path(r))
    monkeypatch.setattr(api_snapshot, "mas_frescas", lambda root, **_: {})
    monkeypatch.setattr(api_snapshot, "agencias_con_web_ajena", lambda root, **_: set())
    assert api_snapshot.main() == 0
    return sqlite3.connect(salida / "ERETZ_API_SNAPSHOT.sqlite3")


def test_el_builder_inserta_en_orden_de_id_y_alinea_los_rowid(tmp_path, monkeypatch):
    con = _construir(tmp_path, monkeypatch, ["hc", "ha", "hd", "hb"])
    propiedades = con.execute("select rowid, id from propiedades order by rowid").fetchall()
    busqueda = con.execute("select rowid, id from busqueda order by rowid").fetchall()
    assert [i for _, i in propiedades] == ["ha", "hb", "hc", "hd"]
    assert busqueda == propiedades
    meta = dict(con.execute("select clave, valor from snapshot_meta"))
    assert meta == {"orden_de_filas": "id", "busqueda_rowid": "propiedades"}


def test_un_id_repetido_deja_una_sola_fila_de_texto_y_sigue_alineado(tmp_path, monkeypatch):
    con = _construir(tmp_path, monkeypatch, ["hb", "ha", "hb", "hc"])
    propiedades = con.execute("select rowid, id from propiedades order by rowid").fetchall()
    busqueda = con.execute("select rowid, id from busqueda order by rowid").fetchall()
    assert [i for _, i in busqueda] == ["ha", "hb", "hc"]
    assert busqueda == propiedades


# ------------------------------------------------------------------- la API

def _snapshot(ruta: Path, *, alineada: bool, declarar: dict[str, str] | None):
    """Tres propiedades. Si no esta alineada, el indice de texto se carga al
    reves: el rowid de «h1» en `busqueda` es el de «h3» en `propiedades`."""
    con = sqlite3.connect(ruta)
    con.executescript("""
        create table propiedades (id text primary key, agency_id text not null,
            source_url text not null, titulo text, descripcion text,
            operacion text, tipo_propiedad text, precio real, moneda text,
            ambientes integer, dormitorios integer, banos integer,
            superficie_total real, superficie_cubierta real,
            imagenes_n integer not null default 0, latitud real, longitud real,
            localidad text, localidad_id text, municipio text,
            departamento text, provincia text, barrio text,
            area_nivel text not null, area_nombre text, geo_estado text,
            alcances text not null, documento text not null);
        create virtual table busqueda using fts5(
            id unindexed, titulo, descripcion, barrio, area_nombre,
            tokenize = "unicode61 remove_diacritics 2");
    """)
    filas = [("h1", "Casa con pileta", "venta"), ("h2", "Depto luminoso", "venta"),
             ("h3", "Casa quinta", "alquiler")]
    for i, titulo, operacion in filas:
        doc = {"id": i, "agency_id": "roomix:alfa", "source_url": f"https://a/{i}",
               "titulo": titulo, "operacion": operacion, "imagenes": [],
               "geo": {"area_busqueda": {"nivel": "SIN_AREA", "nombre": None}}}
        con.execute(
            "insert into propiedades (id, agency_id, source_url, titulo, operacion, "
            "area_nivel, alcances, documento) values (?,?,?,?,?,?,?,?)",
            (i, "roomix:alfa", f"https://a/{i}", titulo, operacion, "SIN_AREA",
             json.dumps(["FICHA"]), json.dumps(doc)))
    for i, titulo, _ in (filas if alineada else list(reversed(filas))):
        con.execute("insert into busqueda (id, titulo, descripcion, barrio, area_nombre) "
                    "values (?,?,'','','')", (i, titulo))
    if declarar is not None:
        con.execute("create table snapshot_meta (clave text primary key, valor text)")
        con.executemany("insert into snapshot_meta values (?,?)", declarar.items())
    con.commit()
    con.close()


@pytest.fixture()
def api(monkeypatch):
    from api import v2
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(v2.router)
    cliente = TestClient(app)

    def usar(ruta):
        monkeypatch.setattr(v2, "SNAPSHOT", ruta)
        return cliente
    return usar


def _ids(cliente, **params):
    r = cliente.get("/v2/buscar", params=params)
    assert r.status_code == 200, r.text
    return r.json()["total"], sorted(d["id"] for d in r.json()["data"])


def test_sin_declaracion_no_se_une_por_rowid_aunque_parezca(tmp_path, api):
    """El indice de texto al reves: unir por rowid devolveria «h3» para
    «casa venta». Sin declaracion se une por id y la respuesta es la real."""
    ruta = tmp_path / "vieja.sqlite3"
    _snapshot(ruta, alineada=False, declarar=None)
    assert _ids(api(ruta), q="casa", operacion="venta") == (1, ["h1"])


def test_una_declaracion_de_otra_cosa_tampoco_habilita_el_atajo(tmp_path, api):
    ruta = tmp_path / "otra.sqlite3"
    _snapshot(ruta, alineada=False, declarar={"busqueda_rowid": "otra_tabla",
                                              "orden_de_filas": "insercion"})
    assert _ids(api(ruta), q="casa", operacion="venta") == (1, ["h1"])


def test_declarada_y_alineada_da_lo_mismo_que_el_camino_lento(tmp_path, api):
    lenta, rapida = tmp_path / "lenta.sqlite3", tmp_path / "rapida.sqlite3"
    _snapshot(lenta, alineada=False, declarar=None)
    _snapshot(rapida, alineada=True, declarar={"busqueda_rowid": "propiedades",
                                               "orden_de_filas": "id"})
    for params in (dict(q="casa"), dict(q="casa", operacion="venta"),
                   dict(q="casa", operacion="alquiler"), dict(q="depto"),
                   dict(operacion="venta")):
        assert _ids(api(lenta), **params) == _ids(api(rapida), **params), params


def test_la_ventana_usa_el_rowid_solo_con_texto_y_declaracion(tmp_path):
    from api import v2

    ruta = tmp_path / "s.sqlite3"
    _snapshot(ruta, alineada=True, declarar={"orden_de_filas": "id"})
    con = sqlite3.connect(ruta)
    assert v2._orden_de_candidatos(con, True) == "busqueda.rowid"
    assert v2._orden_de_candidatos(con, False) == "propiedades.id"
    con.execute("delete from snapshot_meta")
    assert v2._orden_de_candidatos(con, True) == "propiedades.id"
    con.execute("drop table snapshot_meta")
    assert v2._orden_de_candidatos(con, True) == "propiedades.id"
    con.close()
