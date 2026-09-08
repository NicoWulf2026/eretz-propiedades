#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Lo que se autoriza a escribir tiene que ser lo que se va a escribir.

El plan contaba 58.427 propiedades publicables sin mirar de quien es la web de
la que salieron. Adentro habia 729 de `Barreira Bienes Raices` -cuya web
cargada es `comunidadinmobiliaria.com.ar/web/miembros/`, la pagina de socios de
una asociacion que comparten tres inmobiliarias- y 73 de `arte propiedades`,
que es un perfil en el portal `lujanprop.com.ar`. Escribirlas le habria
atribuido a una el inventario de las otras.

La retencion vive tambien en la preingestion; aca se cuenta aparte porque este
es el artefacto que se lee ANTES de autorizar.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.plan_de_escritura import agencias_con_web_ajena, construir  # noqa: E402


def _escribir(ruta: Path, filas: list[dict]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("\n".join(json.dumps(f, ensure_ascii=False) for f in filas),
                    encoding="utf-8")


def test_la_web_de_un_tercero_no_hace_propietaria_a_nadie(tmp_path):
    directorio = tmp_path / "directorio.jsonl"
    _escribir(directorio, [
        {"canonical_agency_id": "roomix:propia", "web_kind": "OFFICIAL_WEB"},
        {"canonical_agency_id": "roomix:portal",
         "web_kind": "EXTERNAL_PORTAL_PROFILE"},
        {"canonical_agency_id": "roomix:ambigua",
         "web_kind": "AMBIGUOUS_WEB_ATTRIBUTION"},
        # La pagina de la oficina DENTRO de su propia red sí es suya.
        {"canonical_agency_id": "roomix:franquicia",
         "web_kind": "OFFICIAL_OFFICE_PAGE"},
    ])
    ajenas = agencias_con_web_ajena(directorio)
    assert ajenas == {"roomix:portal", "roomix:ambigua"}


def test_las_propiedades_de_una_web_ajena_no_entran_al_plan(tmp_path):
    directorio = tmp_path / "directorio.jsonl"
    _escribir(directorio, [
        {"canonical_agency_id": "roomix:propia", "web_kind": "OFFICIAL_WEB"},
        {"canonical_agency_id": "roomix:portal",
         "web_kind": "EXTERNAL_PORTAL_PROFILE"},
    ])
    pre = tmp_path / "preingestion"
    _escribir(pre / "PROPERTY_QUALITY_GATE.jsonl", [
        {"canonical_agency_id": "roomix:propia", "publicable": True},
        {"canonical_agency_id": "roomix:propia", "publicable": True},
        {"canonical_agency_id": "roomix:portal", "publicable": True},
        {"canonical_agency_id": "roomix:propia", "publicable": False},
    ])

    plan = construir(tmp_path / "cert", tmp_path / "geo", pre, directorio)
    ingesta = next(p for p in plan["pasos"] if p["orden"] == 4)
    assert ingesta["filas"] == 2
    assert ingesta["retenidas_por_web_ajena"] == 1
    assert "no es su inventario" in ingesta["por_que_se_retienen"]


def test_sin_directorio_no_se_inventa_una_retencion(tmp_path):
    """Un artefacto ausente no puede convertirse en permiso para escribir de
    más ni en una retención masiva: se cuenta lo que hay."""
    assert agencias_con_web_ajena(tmp_path / "no-existe.jsonl") == set()
