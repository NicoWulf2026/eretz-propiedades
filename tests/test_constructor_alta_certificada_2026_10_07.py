"""Una fila de la preingestion que no se servia y llega con paquete CERTIFICADO es un alta (07-10).

sprint_rc1: P2 freno '4 altas sin motivo aprobado' (gonzalez e hijos, gualtieri, oyharzabal,
morero): filas CANDIDATE de la preingestion, nunca servidas, con su ficha en las dos corridas de
una certificacion COMPLETE. El constructor solo marcaba SUMADA_CERTIFICADA a las filas que no
estaban en la preingestion (`es_nueva`). Con frescura PARCIAL (de un NEEDS_FIX) no esta
certificada y no se suma.
"""
from __future__ import annotations

import inspect

from scripts import api_snapshot as a


def test_MUERDE_la_fila_no_servida_con_paquete_certificado_se_marca_como_alta():
    fuente = inspect.getsource(a._build_contents)
    assert "alta_certificada = True" in fuente
    i = fuente.index("if alta_certificada:")
    assert 'cambios[hash_dedup] = "SUMADA_CERTIFICADA"' in fuente[i:i + 120]


def test_MUERDE_la_frescura_parcial_no_alcanza_para_sumar():
    fuente = inspect.getsource(a._build_contents)
    i = fuente.index("alta_certificada = False")
    tramo = fuente[i:i + 500]
    assert '"_campos_confiables" in fresca' in tramo
    assert '"ALTA_SIN_CERTIFICAR"' in tramo and "continue" in tramo
