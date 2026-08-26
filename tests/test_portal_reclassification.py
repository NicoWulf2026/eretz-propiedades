#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Distinguir la web propia del perfil en un portal, sin depender de nombres.

La lista de portales por nombre siempre va a estar incompleta, y ademas se
equivoca: kitepropcrm estaba en ella y no es un portal, es un SaaS que le da a
cada inmobiliaria su propio host. Diez webs propias figuraban como perfiles
ajenos por el nombre del proveedor.

La senal que si se puede contar es cuantas inmobiliarias cuelgan del MISMO host.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.reclassify_portal_profiles import (AMBIGUA, OFICIAL,  # noqa: E402
                                                OFICINA_RED, PERFIL_PORTAL,
                                                agencias_por_host, clasificar,
                                                mismo_negocio)


def directorio(*pares):
    return [{"canonical_agency_id": f"ag-{i}", "agency_name": n, "domain": u}
            for i, (n, u) in enumerate(pares)]


def test_muchas_agencias_en_un_host_no_es_web_propia():
    # Un host que no esta en ninguna lista: lo delata la cuenta, no el nombre.
    filas = directorio(("A", "https://alquenia.com/a"), ("B", "https://alquenia.com/b"),
                       ("C", "https://alquenia.com/c"))
    por_host = agencias_por_host(filas)
    tipo, motivo = clasificar("https://alquenia.com/a", por_host, "A")
    assert tipo == PERFIL_PORTAL and "3 inmobiliarias" in motivo


def test_un_saas_con_un_host_por_agencia_sigue_siendo_web_propia():
    """La diferencia entre alojar tu web y publicar en un portal ajeno."""
    filas = directorio(("A", "https://a44.kitepropcrm.com/site/properties/1/x"),
                       ("B", "https://b33.kitepropcrm.com/site/properties/2/y"))
    por_host = agencias_por_host(filas)
    assert clasificar(filas[0]["domain"], por_host, "A")[0] == OFICIAL


def test_dos_veces_el_mismo_negocio_no_lo_convierte_en_portal():
    """El padron trae la misma inmobiliaria cargada dos veces. Declarar portal a
    su sitio le quitaria la web propia a quien si la tiene."""
    filas = directorio(("De Bernardis Propiedades", "https://debernardis.com.ar"),
                       ("FABIANA DE BERNARDIS GESTION INMOBILIARIA",
                        "https://debernardis.com.ar/property-city/adrogue"))
    por_host = agencias_por_host(filas)
    assert clasificar(filas[0]["domain"], por_host, filas[0]["agency_name"])[0] == OFICIAL


def test_dos_agencias_sin_relacion_en_un_host_queda_sin_decidir():
    """Una de las dos es la duena y desde afuera no se sabe cual. Se marca y no
    se ingiere: atribuirle a una el inventario de la otra es peor."""
    filas = directorio(("Arquitectura Inmobiliaria", "https://urbanorosario.com.ar/a"),
                       ("Urbano Rosario", "https://urbanorosario.com.ar/b"))
    por_host = agencias_por_host(filas)
    tipo, motivo = clasificar(filas[0]["domain"], por_host, filas[0]["agency_name"])
    assert tipo == AMBIGUA and "no se puede" in motivo


def test_la_pagina_de_la_oficina_dentro_de_su_red_no_es_un_portal_ajeno():
    filas = directorio(("C21 Uno", "https://century21.com.ar/oficina/uno"),
                       ("C21 Dos", "https://century21.com.ar/oficina/dos"),
                       ("C21 Tres", "https://century21.com.ar/oficina/tres"))
    por_host = agencias_por_host(filas)
    assert clasificar(filas[0]["domain"], por_host, "C21 Uno")[0] == OFICINA_RED


def test_los_nombres_se_comparan_por_lo_que_distinguen():
    assert mismo_negocio("Zarate Gestion Inmobiliaria", "Zarate Inmobiliaria")
    assert mismo_negocio("RE/MAX Platino 2", "REMAX Platino")
    # "Propiedades" e "Inmobiliaria" las comparte media Argentina: no acercan.
    assert not mismo_negocio("Barrera Propiedades", "CASAS Inmobiliaria")
    assert not mismo_negocio("Emir Elhelou Estudio", "LOGROS Servicios Inmobiliarios")
