#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Retener no es resolver, pero inventar un dueno es peor que retener.

Dos fichas del padron con el mismo apellido sobre el mismo dominio pueden ser
tres cosas distintas: la misma empresa cargada dos veces, dos sucursales, o dos
inmobiliarias homonimas donde el sitio es de una sola. Las tres dan exactamente
la misma señal si uno mira nombres y dominio.

Lo que las separa es lo que el sitio dice de si mismo. Salerno lo dijo con todas
las letras: se titula "Salerno Inmobiliaria", su direccion es Cordoba Capital y
su telefono empieza con 351. La otra ficha trabaja en Mar del Plata, donde la
caracteristica es 223.

Estos tests cuidan el unico desenlace que no se puede permitir: adjudicar un
sitio sin evidencia, o concluir que la perdedora no tiene web cuando lo unico
demostrado es que esa no era la suya.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.resolve_padron_duplicates import (AMBIGUO, DEMOSTRADO,  # noqa: E402
                                               MISMA, decidir, es_404_blando,
                                               extraer_contacto, senas_de)

RESOLUCION = Path(r"D:\INMO CAPITAL\PADRON_DUPLICATE_RESOLUTION.json")


def ent(nombre, zs, ids):
    return {"nombre_original": nombre, "zonas_observadas": zs,
            "raw_agent_ids": ids}


MDQ = ent("Inmobiliaria Salerno", ["centro", "los pinares", "mar del plata"],
          ["id-mdq"])
CBA = ent("Salerno Inmobiliaria", ["comercial empalme", "den funes",
                                   "funes cordoba capital"], ["id-cba"])


def test_el_sitio_nombra_a_una_sola_y_esa_es_la_duena():
    v, dueno, ev = decidir(MDQ, CBA, "propiedades en cordoba capital empalme")
    assert v == DEMOSTRADO
    assert dueno is CBA
    assert any("ninguna" in x for x in ev)


def test_si_nombra_a_las_dos_no_se_adjudica():
    """O son sucursales de la misma empresa o el padron las separo mal. En los
    dos casos la decision es del padron, no de la ingesta."""
    v, dueno, _ = decidir(MDQ, CBA, "oficinas en pinares y en empalme cordoba")
    assert v == MISMA
    assert dueno is None


def test_si_no_nombra_a_ninguna_quedan_retenidas():
    v, dueno, _ = decidir(MDQ, CBA, "bienvenidos a nuestra inmobiliaria")
    assert v == AMBIGUO
    assert dueno is None


def test_sin_respuesta_del_sitio_no_se_inventa_un_dueno():
    v, dueno, ev = decidir(MDQ, CBA, "")
    assert v == AMBIGUO
    assert dueno is None
    assert any("no respondio" in x for x in ev)


def test_compartir_agent_id_gana_sobre_cualquier_lectura():
    """Un id de Roomix compartido no se comparte por casualidad, y no depende de
    que el sitio este arriba."""
    a = ent("A", ["pinares"], ["x", "y"])
    b = ent("B", ["empalme"], ["x"])
    assert decidir(a, b, "pinares y empalme")[0] == MISMA


def test_las_zonas_indistinguibles_no_deciden_nada():
    a = ent("A", ["centro"], ["a"])
    b = ent("B", ["centro"], ["b"])
    assert decidir(a, b, "centro")[0] == AMBIGUO


def test_las_palabras_de_relleno_no_cuentan_como_zona():
    """"comercial", "terrenos" y "capital" aparecen en cualquier sitio del
    rubro: si contaran, cualquier pagina "nombraria" a las dos fichas."""
    s = senas_de(ent("X", ["comercial empalme", "terrenos capital"], []))
    assert "empalme" in s
    assert "comercial" not in s and "terrenos" not in s and "capital" not in s


def test_un_404_con_http_200_no_es_contenido():
    assert es_404_blando("404")
    assert es_404_blando("  Error 404 - Not Found")
    assert es_404_blando("Pagina no encontrada")
    assert not es_404_blando("Salerno Inmobiliaria")


def test_el_contacto_se_extrae_para_que_quede_en_la_evidencia():
    """La caracteristica telefonica ubica la ciudad sin ambiguedad."""
    c = extraer_contacto("Contacto salernoinmobiliaria@gmail.com "
                         "Rayo Cortado 2167 - Cordoba Capital (351) 8555535")
    assert "@" in c
    assert "351" in c or "Cordoba" in c


# --- contra el artefacto real -----------------------------------------------

def test_los_dos_casos_quedaron_resueltos_con_evidencia():
    if not RESOLUCION.exists():
        pytest.skip("todavia no se genero la resolucion")
    d = json.loads(RESOLUCION.read_text(encoding="utf-8"))
    por_host = {c["host"]: c for c in d["casos"]}
    assert {"salernoinmobiliaria.com", "zaratepropiedades.com"} <= set(por_host)
    for host, caso in por_host.items():
        assert caso["veredicto"] == DEMOSTRADO, host
        assert caso["dueno"] and caso["dueno"]["eretz_id"], host
        assert caso["sin_derecho_sobre_el_sitio"], host
        assert caso["evidencia"], host
        # el dueno y el desplazado no pueden ser el mismo
        assert (caso["dueno"]["canonical_agency_id"]
                != caso["sin_derecho_sobre_el_sitio"]["canonical_agency_id"])


def test_salerno_quedo_para_la_de_cordoba():
    if not RESOLUCION.exists():
        pytest.skip("todavia no se genero la resolucion")
    d = json.loads(RESOLUCION.read_text(encoding="utf-8"))
    caso = [c for c in d["casos"] if c["host"] == "salernoinmobiliaria.com"][0]
    assert int(caso["dueno"]["eretz_id"]) == 6334
    assert int(caso["sin_derecho_sobre_el_sitio"]["eretz_id"]) == 3535


def test_zarate_quedo_para_la_de_zona_norte():
    if not RESOLUCION.exists():
        pytest.skip("todavia no se genero la resolucion")
    d = json.loads(RESOLUCION.read_text(encoding="utf-8"))
    caso = [c for c in d["casos"] if c["host"] == "zaratepropiedades.com"][0]
    assert int(caso["dueno"]["eretz_id"]) == 6849
    assert int(caso["sin_derecho_sobre_el_sitio"]["eretz_id"]) == 2587


def test_a_la_desplazada_no_se_le_concluye_ausencia_de_web():
    """Quitarle un sitio que no era suyo no demuestra que no tenga uno propio."""
    src = (Path(__file__).resolve().parents[1] / "scripts"
           / "resolve_padron_duplicates.py").read_text(encoding="utf-8")
    assert 'r["web_kind"] = "SEARCH_API_PENDING"' in src
    assert "OFFICIAL_WEB_NOT_FOUND" not in src
    assert "domain_mal_atribuido" in src
