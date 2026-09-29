"""La cola no certifica sin catalogo geografico (`criscenti`, 28-09)."""
from __future__ import annotations

import sys

from scripts import run_agency_certification_queue as Q


def test_sin_georef_la_cola_no_arranca(tmp_path, monkeypatch, capsys):
    from connectors import base

    def sin_disco(*a, **k):
        raise FileNotFoundError("falta el snapshot D:/ERETZ_GEO/provincias.json")

    monkeypatch.setattr(base, "geografia", sin_disco)
    cargado = []
    monkeypatch.setattr(Q, "load_catalog", lambda *a, **k: cargado.append(1))
    monkeypatch.setattr(sys, "argv", ["cola", "--ready", "--output", str(tmp_path)])
    assert Q.main() == 3
    assert cargado == []                      # ni siquiera leyo el padron
    assert "sin catalogo geografico" in capsys.readouterr().out


def test_con_georef_el_preflight_no_objeta(monkeypatch):
    from connectors import base
    monkeypatch.setattr(base, "geografia", lambda *a, **k: object())
    assert Q.catalogo_geografico_cargado() is None
