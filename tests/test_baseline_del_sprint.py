"""Senales de falso COMPLETE del baseline del sprint (06-10)."""
from __future__ import annotations

import collections
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RAIZ), str(RAIZ / "scripts")]

from scripts.baseline_del_sprint import senales  # noqa: E402


def _fila(**corrida):
    base = {"host": "agencia.com.ar", "enumeradas": 50, "paginas": 3}
    return {"official_url": "https://agencia.com.ar", "run2": dict(base, **corrida)}


def test_sin_senal_una_enumeracion_paginada_y_completa():
    assert senales(_fila(total_declarado=50), collections.Counter({"agencia.com.ar": 1})) == []


def test_MUERDE_declarado_mucho_mayor_que_enumerado():
    s = senales(_fila(total_declarado=340, enumeradas=21), collections.Counter({"agencia.com.ar": 1}))
    assert any("declarado 340" in x for x in s)


def test_MUERDE_techo_redondo_en_una_pagina_sin_total():
    s = senales(_fila(enumeradas=12, paginas=1), collections.Counter({"agencia.com.ar": 1}))
    assert any("techo redondo 12" in x for x in s)


def test_MUERDE_portal_como_web_oficial_y_host_compartido():
    fila = _fila(host="redinmobiliaria.ar")
    fila["official_url"] = "https://redinmobiliaria.ar/site/properties/544003/x"
    s = senales(fila, collections.Counter({"redinmobiliaria.ar": 2}))
    assert "web oficial es portal" in s and any("host compartido" in x for x in s)
