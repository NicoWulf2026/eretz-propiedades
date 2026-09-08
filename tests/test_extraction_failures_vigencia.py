#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""El ranking de defectos tiene que decir si esta midiendo fantasmas.

Las 58.427 propiedades de la snapshot se extrajeron en agosto y desde entonces
hubo 41 commits de connectors. Dos de los tres defectos mejor rankeados
-`tokko/superficie_total` y `generic/html_catalog operacion`- ya estaban
arreglados en el codigo: abrir una ficha real y correr el parser de hoy los
extraia sin tocar una linea. Perseguirlos costo medio dia.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.extraction_failures import vigencia  # noqa: E402


def _base(tmp_path: Path, cuando: str) -> Path:
    db = tmp_path / "snapshot.sqlite3"
    conexion = sqlite3.connect(db)
    conexion.execute("create table rows (status text, row_json text)")
    conexion.execute("insert into rows values ('CANDIDATE', ?)",
                     (json.dumps({"scraped_at": cuando}),))
    conexion.commit()
    conexion.close()
    return db


def test_avisa_cuando_los_datos_son_anteriores_al_codigo(tmp_path):
    v = vigencia(_base(tmp_path, "2020-01-01T00:00:00"))
    assert v["los_datos_son_anteriores_al_codigo"] is True
    assert v["advertencia"]
    assert v["commits_de_connectors_posteriores_a_los_datos"] > 0


def test_no_avisa_cuando_los_datos_son_mas_nuevos(tmp_path):
    v = vigencia(_base(tmp_path, "2099-01-01T00:00:00"))
    assert v["los_datos_son_anteriores_al_codigo"] is False
    assert v["advertencia"] is None


def test_sin_base_no_inventa_una_conclusion(tmp_path):
    v = vigencia(tmp_path / "no-existe.sqlite3")
    assert v["datos_extraidos_hasta"] is None
    assert v["los_datos_son_anteriores_al_codigo"] is False
