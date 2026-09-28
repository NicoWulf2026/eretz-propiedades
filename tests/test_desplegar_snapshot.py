"""El despliegue de snapshot aborta sin tocar nada o vuelve atras solo."""
from __future__ import annotations

import json
import os
import sqlite3
import sys

import pytest

from scripts import desplegar_snapshot as D


def _snapshot(carpeta, ids, **resumen):
    carpeta.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(carpeta / D.NOMBRE)
    con.execute("create table propiedades (id text primary key, agency_id text)")
    con.executemany("insert into propiedades values (?, 'a')", [(i,) for i in ids])
    con.commit()
    con.close()
    (carpeta / D.RESUMEN).write_text(json.dumps({"propiedades": len(ids), **resumen}), encoding="utf-8")


def _correr(monkeypatch, *argumentos):
    monkeypatch.setattr(sys, "argv", ["desplegar_snapshot.py", *argumentos])
    return D.main()


def test_aborta_si_aparecen_ids_no_esperados(tmp_path, monkeypatch):
    _snapshot(tmp_path / "servida", ["a", "b"])
    _snapshot(tmp_path / "cand", ["a", "b", "c"])
    antes = D.sha(tmp_path / "servida" / D.NOMBRE)
    rc = _correr(monkeypatch, "--candidata", str(tmp_path / "cand"), "--etiqueta-respaldo", "v1",
                 "--servida-dir", str(tmp_path / "servida"))
    assert rc == 1
    assert D.sha(tmp_path / "servida" / D.NOMBRE) == antes
    assert (tmp_path / "servida" / "_anteriores" / "v1" / D.NOMBRE).exists()


def test_aborta_si_faltan_ids_que_la_candidata_no_declara(tmp_path, monkeypatch):
    _snapshot(tmp_path / "servida", ["a", "b"])
    _snapshot(tmp_path / "cand", ["a"], exterior_conservadas_no_publicadas=0)
    rc = _correr(monkeypatch, "--candidata", str(tmp_path / "cand"), "--etiqueta-respaldo", "v1",
                 "--servida-dir", str(tmp_path / "servida"),
                 "--exclusiones-declaradas", "exterior_conservadas_no_publicadas")
    assert rc == 1


def test_una_qa_que_falla_vuelve_atras_verificado(tmp_path, monkeypatch):
    """La QA de API no corre sobre esta base minima: tiene que volver a la servida."""
    _snapshot(tmp_path / "servida", ["a", "b"])
    _snapshot(tmp_path / "cand", ["a"], exterior_conservadas_no_publicadas=1)
    antes = D.sha(tmp_path / "servida" / D.NOMBRE)
    rc = _correr(monkeypatch, "--candidata", str(tmp_path / "cand"), "--etiqueta-respaldo", "v1",
                 "--servida-dir", str(tmp_path / "servida"),
                 "--exclusiones-declaradas", "exterior_conservadas_no_publicadas")
    assert rc == 2
    assert D.sha(tmp_path / "servida" / D.NOMBRE) == antes
    registro = next((tmp_path / "servida" / "_despliegues").glob("DEPLOY_*.json"))
    assert json.loads(registro.read_text(encoding="utf-8"))["resultado"] == "ROLLBACK"


@pytest.mark.skipif(os.name != "nt", reason="la apertura exclusiva es de Windows")
def test_detecta_un_archivo_abierto_por_otro(tmp_path):
    _snapshot(tmp_path / "s", ["a"])
    ruta = tmp_path / "s" / D.NOMBRE
    assert D.abiertos(ruta) == []
    with open(ruta, "rb"):
        assert D.abiertos(ruta)
