#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Buscar duplicados sin volver a caer en lo que ya nos confundio tres veces.

Bustamante, Salerno y Zarate llegaron planteados como duplicados del padron.
Los tres compartian apellido, los tres compartian dominio, y los seis eran
inmobiliarias distintas en mercados que no se tocan.

La primera version de esta auditoria devolvia 949 candidatos. 948 tenian en
comun exactamente dos cosas: un host de portal y una ciudad. Ninguna de las dos
identifica a nadie -en Palermo trabajan cientos de inmobiliarias, y en choza.ai
figuran cuarenta y dos- asi que la lista era ruido con formato de evidencia, que
es peor que no tener lista: alguien la iba a mirar creyendo que decia algo.

Estos tests fijan que las senales que no identifican no puedan levantar un
candidato por si solas.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_agency_duplicates import (DEBIL, FUERTE,  # noqa: E402
                                             GENERICOS_MAIL, NO_IDENTIFICAN,
                                             claves_de, evaluar, tel)

CANDIDATOS = Path(r"D:\INMO CAPITAL\AGENCY_DUPLICATE_CANDIDATES.jsonl")


def ent(**kw):
    base = {"raw_agent_ids": [], "matricula": [], "telefono": None,
            "email": None, "nucleo": "", "zonas_observadas": []}
    base.update(kw)
    return base


def test_un_agent_id_compartido_alcanza_solo():
    a = claves_de(ent(raw_agent_ids=["x"], nucleo="alfa"), None)
    b = claves_de(ent(raw_agent_ids=["x"], nucleo="beta"), None)
    comunes, fuerza = evaluar(a, b)
    assert fuerza == FUERTE
    assert "agent_id_compartido" in comunes


def test_una_matricula_compartida_alcanza_sola():
    a = claves_de(ent(matricula=["CMCPSI 1234"]), None)
    b = claves_de(ent(matricula=["cmcpsi 1234"]), None)
    assert evaluar(a, b)[1] == FUERTE


def test_el_apellido_solo_no_levanta_nada():
    """Es exactamente lo que confundio los tres casos ya resueltos."""
    a = claves_de(ent(nucleo="bustamante"), None)
    b = claves_de(ent(nucleo="bustamante"), None)
    assert evaluar(a, b)[1] == ""


def test_compartir_zona_no_las_hace_la_misma():
    """En Palermo trabajan cientos de inmobiliarias."""
    a = claves_de(ent(zonas_observadas=["palermo", "recoleta"]), None)
    b = claves_de(ent(zonas_observadas=["palermo", "recoleta"]), None)
    assert evaluar(a, b)[1] == ""


def test_apellido_mas_zona_tampoco():
    """Las dos senales que no identifican, juntas, siguen sin identificar. Asi
    salian 948 candidatos que solo compartian un portal y una ciudad."""
    a = claves_de(ent(nucleo="lopez", zonas_observadas=["palermo"]), None)
    b = claves_de(ent(nucleo="lopez", zonas_observadas=["palermo"]), None)
    assert evaluar(a, b)[1] == ""


def test_las_dos_que_no_identifican_estan_declaradas():
    assert NO_IDENTIFICAN == {"nucleo_de_nombre_igual", "zonas_compartidas"}


def test_telefono_mas_dominio_si_levantan_un_candidato():
    a = claves_de(ent(telefono="+54 11 4567-8900"), "https://alfa.com.ar")
    b = claves_de(ent(telefono="(011) 4567 8900"), "https://www.alfa.com.ar/x")
    comunes, fuerza = evaluar(a, b)
    assert fuerza == DEBIL
    assert "telefono_compartido" in comunes and "dominio_compartido" in comunes


def test_el_telefono_se_compara_por_el_numero_no_por_el_prefijo():
    """Cada quien lo escribe distinto; el numero es el mismo."""
    assert tel("+54 9 11 4567-8900") == tel("(011) 4567 8900") == "45678900"
    assert tel("123") == ""


def test_una_casilla_generica_no_identifica():
    """info@ lo tiene medio rubro."""
    a = claves_de(ent(email="info@alfa.com"), None)
    assert not a["email_compartido"]
    for g in GENERICOS_MAIL:
        assert not claves_de(ent(email=g + "x.com"), None)["email_compartido"]


def test_un_mail_propio_si_cuenta():
    a = claves_de(ent(email="juan.perez@alfa.com"), None)
    assert a["email_compartido"] == {"juan.perez@alfa.com"}


def test_centro_no_cuenta_como_zona():
    a = claves_de(ent(zonas_observadas=["centro", "palermo"]), None)
    assert a["zonas_compartidas"] == {"palermo"}


# --- contra el artefacto real -----------------------------------------------

def test_la_lista_quedo_corta_y_con_evidencia():
    if not CANDIDATOS.exists():
        pytest.skip("todavia no se genero la auditoria")
    filas = [json.loads(l) for l in CANDIDATOS.open(encoding="utf-8") if l.strip()]
    # Si vuelve a dar cientos, es que alguna senal que no identifica se colo.
    assert len(filas) < 50, "demasiados candidatos: revisar las senales"
    for f in filas:
        assert f["fuerza"] in (FUERTE, DEBIL)
        assert f["senales"]
        utiles = [s for s in f["senales"] if s not in NO_IDENTIFICAN]
        assert utiles, "un candidato sostenido solo por senales que no identifican"
        assert len(f["entidades"]) == 2
        assert "no se fusiona" in f["accion"]


def test_la_auditoria_no_fusiona_nada():
    src = (Path(__file__).resolve().parents[1] / "scripts"
           / "audit_agency_duplicates.py").read_text(encoding="utf-8")
    for palabra in ("merge", "fusionar(", "unificar("):
        assert palabra not in src
    assert "no se fusiona" in src
