# -*- coding: utf-8 -*-
"""Que la evidencia de bajas se pueda nombrar, no solo contar.

El item 8 de la tanda daba por perdido este dato. No lo estaba: el resultado
guarda el conteo `ausentes` y el checkpoint de cada paquete guarda las
identidades. Estos tests fijan la lectura y, sobre todo, que no se invente un
id donde no lo hay.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from scripts.quienes_faltan import (ausentes_de, leer_checkpoint,  # noqa: E402
                                    recorrer)


def checkpoint(ausencias, ids, agencia="roomix:prueba"):
    return {"fuentes": {agencia: {"ausencias": ausencias, "ids": ids,
                                  "vistos": {}}}}


def test_nombra_las_ausentes_con_su_id():
    c = checkpoint({"h1": 20, "h2": 4}, {"h1": "7941974", "h2": "6943222"})
    (agencia, filas), = ausentes_de(c)
    assert agencia == "roomix:prueba"
    assert [f["id"] for f in filas] == ["7941974", "6943222"]


def test_MUERDE_se_ordenan_por_antiguedad():
    """La que lleva 20 corridas ausente importa mas que la de 2: si el orden
    se pierde, la lista de 918 no sirve para priorizar nada."""
    c = checkpoint({"a": 2, "b": 20, "c": 4}, {"a": "1", "b": "2", "c": "3"})
    (_, filas), = ausentes_de(c)
    assert [f["corridas_ausente"] for f in filas] == [20, 4, 2]


def test_MUERDE_una_ausente_sin_id_se_reporta_sin_id_y_no_se_inventa():
    """Medido: hoy no hay ninguna sin id, pero si apareciera, decir «(sin id)»
    es informacion y poner cualquier cosa es mentira."""
    c = checkpoint({"h1": 3}, {})
    (_, filas), = ausentes_de(c)
    assert filas[0]["id"] is None
    assert filas[0]["hash"] == "h1"


def test_una_agencia_sin_ausencias_no_aparece():
    assert list(ausentes_de(checkpoint({}, {"h": "1"}))) == []


def test_un_checkpoint_ilegible_no_corta_el_recorrido(tmp_path: Path):
    (tmp_path / "roto").mkdir()
    (tmp_path / "roto" / "checkpoint.json").write_text("{no es json", encoding="utf-8")
    (tmp_path / "sano").mkdir()
    (tmp_path / "sano" / "checkpoint.json").write_text(
        json.dumps(checkpoint({"h": 5}, {"h": "999"}, "roomix:sana")), encoding="utf-8")
    salida = list(recorrer(tmp_path))
    assert len(salida) == 1
    assert salida[0][0] == "roomix:sana"
    assert salida[0][2][0]["id"] == "999"


def test_el_minimo_filtra_por_antiguedad(tmp_path: Path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "checkpoint.json").write_text(
        json.dumps(checkpoint({"x": 1, "y": 9}, {"x": "1", "y": "9"})), encoding="utf-8")
    assert len(list(recorrer(tmp_path, minimo=1))[0][2]) == 2
    assert len(list(recorrer(tmp_path, minimo=5))[0][2]) == 1
    assert list(recorrer(tmp_path, minimo=20)) == []


def test_filtra_por_nombre_de_agencia(tmp_path: Path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "checkpoint.json").write_text(
        json.dumps(checkpoint({"x": 1}, {"x": "1"}, "roomix:cocucci inmobiliaria")),
        encoding="utf-8")
    assert list(recorrer(tmp_path, aguja="cocucci"))
    assert not list(recorrer(tmp_path, aguja="otra"))


def test_leer_un_checkpoint_que_no_existe_devuelve_vacio(tmp_path: Path):
    assert leer_checkpoint(tmp_path / "no-esta.json") == {}
