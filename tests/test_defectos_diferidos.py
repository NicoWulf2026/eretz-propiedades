#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Un defecto ya diagnosticado no puede parar la cola cada doce horas.

El corte por lote existe para que cinco defectos sueltos obliguen a una tanda
de diagnostico. Pero cuenta tambien los que ya tuvieron su tanda: `armanino` y
`attaguile` sirven el catalogo por JavaScript y `andrea gianfelice` pierde una
ficha de 147 cuya url el propio sitio no sirve. Ninguno se arregla sin un
cambio que invalida la pasada entera, y los tres hacian saltar el umbral de las
doce horas una y otra vez sin que hubiera nada nuevo que mirar.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_agency_certification_queue import DIFERIDOS, diferidos  # noqa: E402


def test_sin_archivo_no_hay_nada_diferido(tmp_path):
    assert diferidos(tmp_path) == {}


def test_se_lee_el_diagnostico_de_cada_agencia(tmp_path):
    (tmp_path / DIFERIDOS).write_text("\n".join(json.dumps(f) for f in (
        {"canonical_agency_id": "roomix:armanino",
         "diagnostico": "sirve el catalogo por JavaScript"},
        {"canonical_agency_id": "roomix:attaguile",
         "diagnostico": "sin una sola url propia en el HTML"},
    )) + "\n", encoding="utf-8")

    fuera = diferidos(tmp_path)
    assert set(fuera) == {"roomix:armanino", "roomix:attaguile"}
    assert "JavaScript" in fuera["roomix:armanino"]


def test_sin_diagnostico_escrito_no_se_difiere(tmp_path):
    """La lista tiene que costar algo, o se vuelve el lugar donde van a parar
    los defectos incómodos."""
    (tmp_path / DIFERIDOS).write_text(
        json.dumps({"canonical_agency_id": "roomix:comoda"}) + "\n",
        encoding="utf-8")
    assert diferidos(tmp_path) == {}


def test_una_linea_rota_no_tira_la_cola(tmp_path):
    (tmp_path / DIFERIDOS).write_text(
        "{esto no es json\n"
        + json.dumps({"canonical_agency_id": "roomix:x", "diagnostico": "y"})
        + "\n", encoding="utf-8")
    assert diferidos(tmp_path) == {"roomix:x": "y"}
