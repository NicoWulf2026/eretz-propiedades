"""Presupuesto por corrida para catalogos grandes o lentos (LOCAL, 2026-10-01).

6 agencias / 8.291 propiedades quedaban NEEDS_FIX para siempre por agotar los
5.400 s de cada corrida. Se les da lo que su corrida anterior dice que
necesitan, con margen y con tope.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_agency_certification_queue as Q  # noqa: E402


def _previo(enum, obtenidas, segundos, agotada=True):
    corrida = {"enumeradas": enum, "detalles_obtenidos": obtenidas, "segundos": segundos,
               "estado": "PRESUPUESTO_AGOTADO" if agotada else "OK"}
    return {"run1": corrida, "run2": dict(corrida)}


def test_sin_presupuesto_agotado_no_cambia_nada():
    assert Q.presupuesto_para(_previo(100, 100, 600, agotada=False), 5400) == 5400
    assert Q.presupuesto_para(None, 5400) == 5400


def test_gianini_recibe_lo_que_su_ritmo_pide():
    # 1.033 fichas, 822 leidas en 5.406 s (6,6 s por ficha) -> ~2,5 h con margen.
    p = Q.presupuesto_para(_previo(1033, 822, 5406), 5400)
    assert 5400 < p <= Q.PRESUPUESTO_MAXIMO
    assert abs(p - 1033 * 5406 / 822 * Q.MARGEN_DE_PRESUPUESTO) < 1


def test_si_ni_con_el_tope_alcanza_no_se_retiene_el_worker():
    # `benjamin ferreyra`: 4.000 fichas a 6,4 s -> 9 h por corrida.
    assert Q.presupuesto_para(_previo(4000, 842, 5420), 5400) == 5400


def test_sin_muestra_suficiente_no_se_extrapola():
    assert Q.presupuesto_para(_previo(500, 10, 5400), 5400) == 5400
