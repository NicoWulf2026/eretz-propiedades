#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Un universo incompleto no da error, da menos propiedades.

El comando de reanudacion documentado omitia FORMAS3_ROLLOUT y RESIDUAL_ROLLOUT.
write_eligibility no tiene forma de saber que le falta un archivo que nadie le
paso: proceso lo que recibio, dijo que todo estaba bien y produjo un write set
791 propiedades mas chico. No hubo excepcion, ni advertencia, ni un numero raro
a la vista.

Por eso la lista vive en un solo lugar y estos tests la vigilan: son la
diferencia entre "se me traspapelo un rollout" y "el pipeline avisa".
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.input_universe import (ENTRADAS, OBLIGATORIAS,  # noqa: E402
                                    como_comando, contar,
                                    corridas_por_entrada, faltantes, rutas)

# El universo analizado que produjo el write gate. Si cambia a proposito -un
# rollout nuevo- se actualiza aca junto con la lista, y el cambio queda a la
# vista en el diff en vez de aparecer como un numero distinto en un informe.
UNIVERSO_ESPERADO = 181_492

# El conteo viejo, de cuando faltaban dos rollouts. Ningun artefacto puede
# volver a este numero sin que alguien lo note.
UNIVERSO_INCOMPLETO = 174_164

# El universo antes de reanudar el backlog. Tampoco puede volver a este.
UNIVERSO_SIN_BACKLOG = 174_955


def test_las_dos_que_se_habian_perdido_estan_declaradas():
    carpetas = {d for d, _, _ in ENTRADAS}
    assert "FORMAS3_ROLLOUT" in carpetas
    assert "RESIDUAL_ROLLOUT" in carpetas
    assert OBLIGATORIAS <= carpetas


def test_no_hay_entradas_repetidas():
    """Contar dos veces el mismo archivo infla el universo, que es el mismo
    problema al reves y tampoco avisa."""
    carpetas = [d for d, _, _ in ENTRADAS]
    assert len(carpetas) == len(set(carpetas))
    caminos = [str(p) for p in rutas()]
    assert len(caminos) == len(set(caminos))


def test_todas_las_entradas_existen_en_disco():
    assert faltantes() == []


def test_la_suma_de_las_entradas_es_el_universo_analizado():
    """La igualdad que el write gate tiene que reproducir. Si se rompe, o falta
    una entrada o sobra: en los dos casos hay que mirar antes de seguir."""
    total = sum(contar().values())
    assert total == UNIVERSO_ESPERADO, (
        "el universo cambio: %d, esperado %d. Si el cambio es legitimo, "
        "actualizar ENTRADAS y este numero juntos." % (total, UNIVERSO_ESPERADO))


def test_el_universo_no_volvio_a_ningun_conteo_viejo():
    total = sum(contar().values())
    assert total != UNIVERSO_INCOMPLETO, (
        "el universo volvio al conteo al que le faltaban FORMAS3_ROLLOUT y "
        "RESIDUAL_ROLLOUT")
    assert total != UNIVERSO_SIN_BACKLOG, (
        "el universo volvio al conteo previo a reanudar el backlog")


def test_las_dos_recuperadas_aportan_propiedades_reales():
    """No alcanza con que figuren en la lista: tienen que traer filas."""
    c = contar()
    assert c["FORMAS3_ROLLOUT"] > 0
    assert c["RESIDUAL_ROLLOUT"] > 0
    assert c["FORMAS3_ROLLOUT"] + c["RESIDUAL_ROLLOUT"] == 791
    # Y la que se sumo al reanudar el backlog.
    assert c["BACKLOG_generico"] == 6537


def test_cada_entrada_declara_sus_corridas():
    runs = corridas_por_entrada()
    assert set(runs) == {d for d, _, _ in ENTRADAS}
    for carpeta, rs in runs.items():
        assert rs, "la entrada %s no declara ninguna corrida" % carpeta


def test_el_comando_se_genera_y_lleva_las_trece():
    cmd = como_comando()
    assert cmd.startswith("python scripts/write_eligibility.py --entradas")
    assert cmd.count(".jsonl") == len(ENTRADAS)
    for obligatoria in OBLIGATORIAS:
        assert obligatoria in cmd
