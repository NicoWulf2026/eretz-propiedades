# -*- coding: utf-8 -*-
"""Las agencias que nunca se certificaron no esperan detrás de todas las demás.

El 2026-09-24 la cola `ready` tenía 784 agencias y 509 nunca habían tenido un
resultado, mientras los workers recertificaban otra vez las que empiezan con
«a»: cada cambio de código compartido invalida las conocidas, y las conocidas
iban primero.
"""
from __future__ import annotations

from scripts.run_agency_certification_queue import (CANARIOS_POR_FAMILIA,
                                                    ordenar_para_correr)


def _res(familia):
    return {"connector_strategy": familia, "status": "CERTIFIED_COMPLETE",
            "run1": {}, "run2": {}}


def test_MUERDE_una_nueva_no_queda_detras_de_todas_las_conocidas():
    conocidas = [f"k{i:03d}" for i in range(100)]
    nuevas = [f"n{i:03d}" for i in range(100)]
    resultados = {c: _res("tokko") for c in conocidas}
    orden = ordenar_para_correr(conocidas + nuevas, resultados)
    # despues de los canarios, la primera nueva aparece enseguida
    primera_nueva = next(i for i, c in enumerate(orden) if c.startswith("n"))
    assert primera_nueva <= CANARIOS_POR_FAMILIA
    # y en la primera mitad de la cola hay tantas nuevas como conocidas
    mitad = orden[:100]
    assert abs(sum(c.startswith("n") for c in mitad)
               - sum(c.startswith("k") for c in mitad)) <= CANARIOS_POR_FAMILIA + 1


def test_el_universo_sigue_sin_cambiar():
    conocidas = [f"k{i}" for i in range(7)]
    nuevas = [f"n{i}" for i in range(30)]
    orden = ordenar_para_correr(conocidas + nuevas,
                                {c: _res("wasi") for c in conocidas})
    assert sorted(orden) == sorted(conocidas + nuevas)
    assert len(orden) == len(set(orden))


def test_los_canarios_siguen_primero():
    conocidas = [f"t{i}" for i in range(10)]
    orden = ordenar_para_correr(conocidas + ["nueva"],
                                {c: _res("tokko") for c in conocidas})
    assert orden[:CANARIOS_POR_FAMILIA] == conocidas[:CANARIOS_POR_FAMILIA]
