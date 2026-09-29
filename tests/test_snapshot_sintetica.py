"""La snapshot SINTETICA de QA: mismo contrato que la real, nunca servible como real."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys

import pytest
from fastapi.testclient import TestClient

from scripts import snapshot_sintetica as S


@pytest.fixture()
def snapshot(tmp_path):
    ruta = tmp_path / "ERETZ_API_SNAPSHOT.sqlite3"
    S.construir(ruta)
    return ruta


@pytest.fixture()
def cliente(snapshot, monkeypatch):
    from api import v2
    monkeypatch.setattr(v2, "SNAPSHOT", snapshot)
    from api.main import app
    return TestClient(app)


def _filas(ruta):
    con = sqlite3.connect(ruta)
    try:
        return con.execute("select id, documento from propiedades order by id").fetchall()
    finally:
        con.close()


def test_es_determinista(tmp_path):
    a, b = tmp_path / "a.sqlite3", tmp_path / "b.sqlite3"
    S.construir(a)
    S.construir(b)
    assert _filas(a) == _filas(b)
    digest = hashlib.sha256(json.dumps(_filas(a)).encode()).hexdigest()
    assert digest == hashlib.sha256(json.dumps(_filas(b)).encode()).hexdigest()


def test_se_declara_sintetica_y_no_parece_real(snapshot):
    assert S.es_sintetica(snapshot)
    for _, documento in _filas(snapshot):
        doc = json.loads(documento)
        assert doc["agency_id"].startswith(S.PREFIJO_AGENCIA)
        assert doc["source_url"].split("/")[2].endswith("." + S.DOMINIO)


def test_una_snapshot_real_no_se_declara_sintetica(tmp_path):
    ruta = tmp_path / "real.sqlite3"
    sqlite3.connect(ruta).execute("create table propiedades (id text)").connection.close()
    assert not S.es_sintetica(ruta)
    assert not S.es_sintetica(tmp_path / "no_existe.sqlite3")


def test_el_indice_de_texto_esta_alineado_por_rowid(snapshot):
    con = sqlite3.connect(snapshot)
    try:
        desalineadas = con.execute(
            "select count(*) from busqueda b join propiedades p on p.rowid = b.rowid "
            "where p.id != b.id").fetchone()[0]
        meta = dict(con.execute("select clave, valor from snapshot_meta"))
    finally:
        con.close()
    assert desalineadas == 0
    assert meta["orden_de_filas"] == "id" and meta["busqueda_rowid"] == "propiedades"


def test_pasa_los_catorce_casos_de_la_qa_de_api(snapshot, tmp_path, monkeypatch):
    from scripts import benchmark_unified_api as B
    salida = tmp_path / "API_BENCHMARK.json"
    monkeypatch.setattr(sys, "argv", ["benchmark", str(snapshot), "--output", str(salida)])
    B.main()
    casos = json.loads(salida.read_text(encoding="utf-8"))["cases"]
    assert len(casos) == 14
    por_nombre = {c["case"]: c for c in casos}
    # Los filtros combinados tienen que devolver algo, o la QA no prueba nada.
    assert por_nombre["combined"]["total"] >= 1
    assert por_nombre["map_small"]["returned"] >= 1


def test_trae_los_casos_borde_que_la_beta_necesita_ver(cliente):
    def doc(caso):
        r = cliente.get(f"/v2/propiedades/{S.CASOS[caso]}")
        assert r.status_code == 200, caso
        return r.json()

    assert doc("sin_titulo")["titulo"] is None and doc("sin_titulo")["tipo_propiedad"] == "casa"  # P9
    assert doc("sin_titulo_ni_datos")["titulo"] is None
    assert doc("sin_titulo_ni_datos")["operacion"] is None
    assert doc("sin_precio")["precio"] is None
    assert doc("sin_moneda")["precio"] is not None and doc("sin_moneda")["moneda"] is None
    assert doc("sin_coordenadas")["latitud"] is None
    conflicto = doc("conflicto")
    assert conflicto["geo"]["estado"] == "GEO_CONFLICT" and conflicto["latitud"] is None
    assert doc("solo_provincia")["geo"]["area_busqueda"]["nivel"] == "PROVINCIA"
    assert doc("municipio")["geo"]["area_busqueda"]["nivel"] == "MUNICIPIO"


def test_ids_con_la_forma_de_los_reales_y_paginas_completas(cliente, snapshot):
    import re
    assert all(re.fullmatch(r"[0-9a-f]{32}", i) for i, _ in _filas(snapshot))
    for filtro in ({"operacion": "venta"}, {"tipo": "departamento"}):
        assert cliente.get("/v2/buscar", params={**filtro, "limit": 24}).json()["total"] >= 24


def test_la_geografia_que_afirma_la_e2e_de_descubrimiento(cliente):
    # Sin acento, como escribe casi todo el mundo: lo mismo que pide el frontend.
    areas = cliente.get("/v2/sugerencias", params={"q": "cor", "limit": 20}).json()["data"]
    niveles = {a["nivel"] for a in areas if a["tipo"] == "area" and a["nombre"] == "Córdoba"}
    assert {"LOCALIDAD", "MUNICIPIO", "PROVINCIA"} <= niveles
    rosario = cliente.get("/v2/sugerencias", params={"q": "ros", "limit": 20}).json()["data"]
    assert {a["nivel"] for a in rosario if a["tipo"] == "area" and a["nombre"] == "Rosario"} == {
        "LOCALIDAD", "MUNICIPIO"}
    san = cliente.get("/v2/sugerencias", params={"q": "san", "limit": 20}).json()["data"]
    assert {"LOCALIDAD", "MUNICIPIO", "PROVINCIA"} <= {
        a["nivel"] for a in san if a["tipo"] == "area" and a["nombre"].startswith("San")}
    bue = cliente.get("/v2/sugerencias", params={"q": "bue", "limit": 20}).json()["data"]
    assert any(a["nivel"] == "PROVINCIA" and a["nombre"] == "Buenos Aires" for a in bue)


def test_readyz_rechaza_la_sintetica_salvo_permiso(cliente, monkeypatch):
    monkeypatch.delenv("ERETZ_ALLOW_SYNTHETIC_SNAPSHOT", raising=False)
    r = cliente.get("/readyz")
    assert r.status_code == 503 and r.json()["motivo"] == "snapshot SINTETICA de QA"
    monkeypatch.setenv("ERETZ_ALLOW_SYNTHETIC_SNAPSHOT", "1")
    r = cliente.get("/readyz")
    assert r.status_code == 200 and r.json()["sintetica"] is True
    assert r.json()["propiedades"] > 0 and r.json()["database_writes"] == 0


def test_healthz_no_depende_de_la_snapshot(tmp_path, monkeypatch):
    from api import v2
    monkeypatch.setattr(v2, "SNAPSHOT", tmp_path / "no_existe.sqlite3")
    from api.main import app
    cliente = TestClient(app)
    assert cliente.get("/healthz").json() == {"status": "ok"}
    r = cliente.get("/readyz")
    assert r.status_code == 503 and r.json()["motivo"] == "snapshot ausente"


def test_readyz_rechaza_una_snapshot_sin_indice_de_texto(tmp_path, monkeypatch):
    ruta = tmp_path / "vieja.sqlite3"
    con = sqlite3.connect(ruta)
    con.execute("create table propiedades (id text)")
    con.execute("insert into propiedades values ('a')")
    con.commit()
    con.close()
    from api import v2
    monkeypatch.setattr(v2, "SNAPSHOT", ruta)
    from api.main import app
    r = TestClient(app).get("/readyz")
    assert r.status_code == 503 and r.json()["motivo"] == "snapshot sin indice de texto"


def test_el_despliegue_se_niega_a_servir_la_sintetica(tmp_path, monkeypatch):
    from scripts import desplegar_snapshot as D
    servida = tmp_path / "servida"
    servida.mkdir()
    con = sqlite3.connect(servida / D.NOMBRE)
    con.execute("create table propiedades (id text primary key, agency_id text)")
    con.execute("insert into propiedades values ('a', 'x')")
    con.commit()
    con.close()
    (servida / D.RESUMEN).write_text(json.dumps({"propiedades": 1}), encoding="utf-8")
    cand = tmp_path / "cand"
    S.construir(cand / D.NOMBRE)
    (cand / D.RESUMEN).write_text(json.dumps({"propiedades": 56}), encoding="utf-8")
    antes = D.sha(servida / D.NOMBRE)
    monkeypatch.setattr(sys, "argv", ["desplegar_snapshot.py", "--candidata", str(cand),
                                      "--etiqueta-respaldo", "v1", "--servida-dir", str(servida)])
    assert D.main() == 1
    assert D.sha(servida / D.NOMBRE) == antes
    registro = next((servida / "_despliegues").glob("DEPLOY_*.json"))
    assert "SINTETICA" in registro.read_text(encoding="utf-8")
