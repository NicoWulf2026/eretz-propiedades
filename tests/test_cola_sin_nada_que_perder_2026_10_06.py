"""Una agencia sin filas en la base y nunca certificada no detiene a su familia (06-10).

geraci, gle y guzzi -primeras corridas, base 0, nada servido- frenaron la cola de noche
con radio FAMILIA. Su paro no protegia ningun inventario. El defecto se anota igual.
"""
from __future__ import annotations

import inspect

from scripts import run_agency_certification_queue as q


def _r(base):
    return {"baseline_inventory": {"preingestion_rows": base}}


def test_MUERDE_primera_corrida_sin_base_no_tiene_nada_que_perder():
    assert q.sin_nada_que_perder(_r(0), None)
    assert q.sin_nada_que_perder(_r(0), {"status": "NEEDS_FIX"})


def test_con_base_o_ya_certificada_el_paro_se_mantiene():
    assert not q.sin_nada_que_perder(_r(142), None)              # rodriguez bled: 142 servidas
    assert not q.sin_nada_que_perder(_r(0), {"status": "CERTIFIED_COMPLETE"})
    assert not q.sin_nada_que_perder(_r(None), None)             # sin dato: no se asume nada
    assert not q.sin_nada_que_perder({}, None)


def test_main_degrada_el_paro_a_continue_y_lo_anota():
    fuente = inspect.getsource(q.main)
    assert "sin_nada_que_perder(result, existing.get(canonical_id))" in fuente
    assert '"decision": CONTINUE' in fuente and "degradado_de" in fuente
