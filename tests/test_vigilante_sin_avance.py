# -*- coding: utf-8 -*-
"""Workers vivos y ninguna bandera no es lo mismo que una cola que avanza."""
from __future__ import annotations

import json
import os
import sys
import time

import pytest

from scripts import vigilante_de_paros as v


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    monkeypatch.setattr(v, "CERT", tmp_path)
    monkeypatch.setattr(v, "BANDERA", tmp_path / "AGENCY_CERTIFICATION_STOP.json")
    monkeypatch.setattr(v, "DIFERIDOS", tmp_path / "AGENCY_DEFECTS_DIFERIDOS.jsonl")
    monkeypatch.setattr(v, "ESTADO", tmp_path / "ERETZ_QUEUE_WATCH_STATUS.json")
    monkeypatch.setattr(v, "BITACORA", tmp_path / "ERETZ_QUEUE_WATCH.log")
    return tmp_path


def _hace(minutos: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S",
                         time.localtime(time.time() - minutos * 60))


def _worker(d, i, latido_minutos):
    (d / v.CERROJO.format(i)).write_text(json.dumps(
        {"pid": os.getpid(), "heartbeat": _hace(latido_minutos),
         "current_agency": "roomix:la que sea"}), encoding="utf-8")


def _resultado(d, minutos):
    with (d / "AGENCY_CERTIFICATION_RESULTS.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"canonical_agency_id": "roomix:x",
                             "checked_at": _hace(minutos)}) + "\n")


def _correr(capsys):
    argv, sys.argv = sys.argv, ["vigilante", "--sin-alerta"]
    try:
        v.main()
    finally:
        sys.argv = argv
    capsys.readouterr()
    return json.loads(v.ESTADO.read_text(encoding="utf-8"))


def test_MUERDE_un_worker_vivo_con_el_latido_quieto_esta_colgado(entorno, capsys):
    _worker(entorno, 0, latido_minutos=40)
    _resultado(entorno, minutos=5)
    estado = _correr(capsys)
    assert estado["stop_state"] == "COLA_SIN_AVANCE"
    assert "sin latido" in estado["stop_signature"]


def test_MUERDE_horas_sin_un_solo_resultado_no_es_ok(entorno, capsys):
    _worker(entorno, 0, latido_minutos=1)
    _resultado(entorno, minutos=5 * 60)
    estado = _correr(capsys)
    assert estado["stop_state"] == "COLA_SIN_AVANCE"
    assert estado["stop_signature"] == "sin resultados"


def test_una_cola_que_avanza_sigue_ok(entorno, capsys):
    _worker(entorno, 0, latido_minutos=1)
    _resultado(entorno, minutos=20)
    assert _correr(capsys)["stop_state"] == "OK"


def test_sin_avance_alerta():
    assert "COLA_SIN_AVANCE" in v.ALERTAN
    assert v.clave_de_alerta({"stop_state": "COLA_SIN_AVANCE",
                              "stop_signature": "sin resultados",
                              "paused_since": "2026-09-24T10:00:00"})


def test_despues_de_un_apagado_los_workers_recien_lanzados_no_alarman(entorno, capsys):
    """La noche del 23 la maquina se apago a las 21:12 y volvio a las 08:29:
    el ultimo resultado tenia once horas y los workers acababan de arrancar."""
    _worker(entorno, 0, latido_minutos=1)
    _resultado(entorno, minutos=11 * 60)
    with (entorno / "ERETZ_RELANZAMIENTOS.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"cuando": _hace(5), "lanzados": {"0": 1}}) + "\n")
    assert _correr(capsys)["stop_state"] == "OK"
