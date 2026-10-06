"""Recertificar una vez lo que fallo por el ENTORNO (corte de DNS del 2026-10-05 04:15-05:10).

Un NEEDS_FIX que el triaje dejo seguir cuenta como vigente hasta que cambia la huella:
bilas, book y pelay no se iban a rehacer nunca con v7. El archivo de prioridad puede
pedir una recertificacion con `recertificar: {desde, agencias}`.
"""
from __future__ import annotations

import json

from scripts import run_agency_certification_queue as q


def _prioridad(tmp_path, **extra):
    datos = {"motivo": "prueba", "hasta": "2099-01-01T00:00:00", "agencias": []}
    datos.update(extra)
    (tmp_path / q.PRIORIDAD_DE_COLA).write_text(json.dumps(datos), encoding="utf-8")


def test_MUERDE_la_agencia_pedida_se_vuelve_a_correr(tmp_path):
    _prioridad(tmp_path, recertificar={"desde": "2026-10-05T09:55:00",
                                       "agencias": ["roomix:pelay propiedades"]})
    assert q.recertificacion_pedida(tmp_path) == {"roomix:pelay propiedades": "2026-10-05T09:55:00"}


def test_sin_pedido_o_vencido_no_se_pide_nada(tmp_path):
    _prioridad(tmp_path)
    assert q.recertificacion_pedida(tmp_path) == {}
    _prioridad(tmp_path, hasta="2000-01-01T00:00:00",
               recertificar={"desde": "2026-10-05T09:55:00", "agencias": ["x"]})
    assert q.recertificacion_pedida(tmp_path) == {}
    _prioridad(tmp_path, motivo="", recertificar={"desde": "2026-10-05T09:55:00", "agencias": ["x"]})
    assert q.recertificacion_pedida(tmp_path) == {}
    assert q.recertificacion_pedida(tmp_path / "no_existe") == {}


def test_el_pedido_sin_desde_no_vale(tmp_path):
    _prioridad(tmp_path, recertificar={"agencias": ["x"]})
    assert q.recertificacion_pedida(tmp_path) == {}


def test_main_usa_el_pedido_solo_para_resultados_anteriores_a_desde():
    """El corte en `current`: una corrida posterior a `desde` vuelve a contar como vigente."""
    fuente = open(q.__file__, encoding="utf-8").read()
    assert "pedidas = recertificacion_pedida(output)" in fuente
    assert 'get("checked_at") or "") < desde' in fuente
