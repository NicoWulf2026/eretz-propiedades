"""Lote 5 (LOCAL, 2026-10-01): desempate por tercera corrida (F9)."""
from __future__ import annotations

import pytest

from scripts.agency_certifier import cambio_puntual_en_la_fuente as puntual


def _cmp(modificadas=1, nuevas=0, mismo=True, faltan=0, total=280):
    return {"same_url_set": mismo, "missing_in_run2": faltan, "new_in_run2": 0,
            "run2_identities": total,
            "run2_changes": {"SIN_CAMBIOS": total - modificadas, "MODIFICADA": modificadas,
                             **({"NUEVA": nuevas} if nuevas else {})}}


def test_una_ficha_editada_entre_corridas_pide_desempate():
    assert puntual(_cmp(1))          # `pennacchio`: 1 de 280
    assert puntual(_cmp(2, total=106))


@pytest.mark.parametrize("cmp", [
    _cmp(0),                         # ya es idempotente
    _cmp(4, total=280),              # 4 > max(2, 1 %): no es puntual
    _cmp(1, nuevas=1),               # cambio el inventario
    _cmp(1, mismo=False),
    _cmp(1, faltan=1),
])
def test_no_hay_desempate_si_no_es_un_cambio_puntual(cmp):
    assert not puntual(cmp)


def test_catalogos_grandes_toleran_el_uno_por_ciento():
    assert puntual(_cmp(10, total=1100)) and not puntual(_cmp(12, total=1100))
