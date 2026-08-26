#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""El censo por forma verificada, y lo que NO deja entrar.

Dos errores que este censo tiene que impedir, porque los dos publican
propiedades a nombre de quien no es su dueno:

  1. tomar por web propia un portal que el padron le atribuyo a varias
     inmobiliarias -bienesrosario.com figura como web oficial de cinco, entre
     ellas una Century 21 y una RE/MAX-;
  2. habilitar una forma que no se pudo traducir a un patron acotado.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_shape_census import (host_de, hosts_compartidos,  # noqa: E402
                                        raiz_de)


def test_un_host_de_varias_agencias_no_es_web_propia():
    padron = {
        "a": {"selected_domain": "https://bienesrosario.com"},
        "b": {"selected_domain": "https://www.bienesrosario.com/venta"},
        "c": {"selected_domain": "https://gargarella.com.ar"},
    }
    comp = hosts_compartidos(padron)
    assert comp == {"bienesrosario.com": 2}
    assert "gargarella.com.ar" not in comp


def test_un_saas_marca_blanca_no_cae_en_el_filtro():
    """Cada inmobiliaria tiene su propio host: es web propia alojada en una
    plataforma, no un perfil dentro de un portal."""
    padron = {
        "a": {"selected_domain": "https://aguilarbugeau87.kitepropcrm.com"},
        "b": {"selected_domain": "https://otra33.kitepropcrm.com"},
    }
    assert hosts_compartidos(padron) == {}


def test_el_origen_se_queda_sin_la_busqueda_con_la_que_se_descubrio():
    assert raiz_de("https://www.adrianadato.com/inmuebles?en=venta&tipo=local") \
        == "https://www.adrianadato.com"
    assert raiz_de("adrianadato.com") is None       # sin esquema no hay origen


def test_host_sin_www():
    assert host_de("https://WWW.Alfa.com.ar/x") == "alfa.com.ar"
    assert host_de("") == ""
