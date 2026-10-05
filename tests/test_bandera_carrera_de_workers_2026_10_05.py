"""Los dos workers borran la bandera de paro a la vez al arrancar (2026-10-05 09:48).

En Windows el segundo `unlink` sobre un archivo con borrado pendiente da
PermissionError: w0 murio al arrancar y la cola quedo con un worker.
"""
from __future__ import annotations

import pathlib

import pytest

from scripts import run_agency_certification_queue as q


def test_MUERDE_si_el_otro_worker_la_esta_borrando_no_muere(tmp_path, monkeypatch):
    ruta = tmp_path / q.BANDERA_DE_PARO
    ruta.write_text("{}", encoding="utf-8")
    original = pathlib.Path.unlink

    def carrera(self, missing_ok=False):
        if self == ruta and self.exists():
            original(self)  # el otro worker la borra...
            raise PermissionError(5, "Acceso denegado")  # ...y a este le toca el error
        return original(self, missing_ok=missing_ok)

    monkeypatch.setattr(pathlib.Path, "unlink", carrera)
    q.borrar_bandera_vieja(tmp_path)
    assert not ruta.exists()


def test_un_bloqueo_real_y_persistente_sigue_fallando(tmp_path, monkeypatch):
    ruta = tmp_path / q.BANDERA_DE_PARO
    ruta.write_text("{}", encoding="utf-8")

    def bloqueado(self, missing_ok=False):
        raise PermissionError(5, "Acceso denegado")

    monkeypatch.setattr(pathlib.Path, "unlink", bloqueado)
    monkeypatch.setattr(q.time, "sleep", lambda s: None)
    with pytest.raises(PermissionError):
        q.borrar_bandera_vieja(tmp_path, intentos=3)
    assert ruta.exists()


def test_sin_bandera_no_hace_nada(tmp_path):
    q.borrar_bandera_vieja(tmp_path)
