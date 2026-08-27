#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Que la etiqueta esté no significa que adentro haya inventario.

El clasificador agrupa las fuentes que ningún connector pudo leer por MECANISMO
de publicación, y de ahí sale a qué connector mandarlas. Dos señales prometían
un mecanismo que no existía:

  `application/ld+json`   lo trae casi todo sitio moderno para el marcado de la
                          organización -RealEstateAgent, WebSite- sin una sola
                          propiedad adentro. 46 fuentes quedaron JSON_EMBEBIDO
                          por eso, se les corrió el connector genérico, y 49 de
                          56 no encontraron nada.

  inventario declarado    salía de buscar un número pegado a "propiedades".
                          En Quilquihue dio 7.556, que son los últimos cuatro
                          dígitos de `+54 9 294 469 7556`. En Mastres dio 500,
                          de "+500 Propiedades gestionadas", que es una frase de
                          marketing y no un contador de listado.

Las dos inflaban el inventario aparentemente recuperable y mandaban corridas a
fallar. Un número inventado es peor que ninguno: se usa para priorizar.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.classify_residual import (_inventario_declarado,  # noqa: E402
                                       _json_con_fichas)


def ld(cuerpo: str) -> str:
    return '<script type="application/ld+json">%s</script>' % cuerpo


# --- inventario declarado ----------------------------------------------------

def test_un_telefono_partido_no_es_inventario():
    """El caso Quilquihue: 7.556 propiedades que eran el final de un numero."""
    assert _inventario_declarado(
        "contacto@inmobiliaria.com  +54 9 294 469 7556 propiedades") is None


def test_una_frase_de_marketing_no_es_un_contador():
    """El caso Mastres: "+500 Propiedades gestionadas" habla de la historia de
    la empresa, no de lo que hay publicado hoy."""
    assert _inventario_declarado(
        "20 anios de experiencia  +500  Propiedades gestionadas") is None


def test_lo_que_precede_a_un_telefono_lo_descarta():
    for antes in ("Tel:", "WhatsApp", "Cel.", "Fax", "CUIT", "Matricula"):
        assert _inventario_declarado("%s 4469 7556 propiedades" % antes) is None


def test_un_contador_de_listado_si_cuenta():
    assert _inventario_declarado("Se encontraron 128 propiedades") == 128
    assert _inventario_declarado("Mostrando 42 Resultados") == 42
    assert _inventario_declarado("1.250 inmuebles publicados") == 1250


def test_un_numero_absurdo_se_descarta():
    """Sin tope, "54 11 6953 7580" daba 541.169.537.580 propiedades y catorce
    fuentes sumaban mas inventario que todo el pais."""
    assert _inventario_declarado("541169537580 propiedades") is None


def test_sin_numero_no_se_inventa_uno():
    assert _inventario_declarado("bienvenidos a nuestra inmobiliaria") is None
    assert _inventario_declarado("") is None


# --- json embebido -----------------------------------------------------------

def test_el_marcado_de_la_inmobiliaria_no_es_un_listado():
    """Es lo que tienen Quilquihue, Mastres y Ovejero: se describen a si
    mismas."""
    assert not _json_con_fichas(ld('{"@type":"RealEstateAgent","name":"Alfa"}'))
    assert not _json_con_fichas(ld('{"@type":"WebSite","url":"https://a.com"}'))
    assert not _json_con_fichas(ld('{"@context":"x","@graph":['
                                   '{"@type":"Organization"},{"@type":"WebPage"}]}'))


def test_dos_fichas_o_mas_si_son_un_listado():
    assert _json_con_fichas(ld('[{"@type":"RealEstateListing","name":"a"},'
                               '{"@type":"RealEstateListing","name":"b"}]'))


def test_una_sola_ficha_puede_ser_la_destacada_de_la_portada():
    """Una no alcanza: casi toda portada muestra una propiedad destacada."""
    assert not _json_con_fichas(ld('{"@type":"RealEstateListing","name":"a"}'))


def test_las_fichas_anidadas_tambien_cuentan():
    assert _json_con_fichas(ld('{"@type":"ItemList","itemListElement":['
                               '{"@type":"Apartment"},{"@type":"House"}]}'))


def test_un_json_roto_no_rompe_la_clasificacion():
    assert not _json_con_fichas(ld("{esto no es json"))
    assert not _json_con_fichas("")
    assert not _json_con_fichas("<html>sin script</html>")
