# -*- coding: utf-8 -*-
"""Senales del auditor, lote de la tarde del 2026-09-28 (medido en la fuente)."""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from agency_certifier import SOURCE_SIGNALS  # noqa: E402


def test_MUERDE_valor_antes_del_rotulo_no_se_lee_con_el_numero_del_vecino():
    """`medina` (620315): «+4 Ambientes 12 baños 12 Dormitorios». El 12 es de
    los baños; «+4» es una cota. La ficha no publica una cantidad de
    ambientes y el extractor, con razon, no la afirma."""
    texto = "Para inversionistas +4 Ambientes 12 baños 12 Dormitorios Disposicion Frente"
    assert not SOURCE_SIGNALS["ambientes"].search(texto)
    assert SOURCE_SIGNALS["banos"].search(texto)
    assert SOURCE_SIGNALS["dormitorios"].search(texto)


def test_rotulo_antes_del_valor_sigue_contando():
    for texto in ("Ambientes: 3 Baños: 1", "Ambientes 3 Dormitorios 2",
                  "Detalles Dormitorios 2 Baños 1", "4 ambientes con cochera"):
        assert SOURCE_SIGNALS["ambientes"].search(texto) or "ambientes" not in texto.lower()
    assert SOURCE_SIGNALS["ambientes"].search("Ambientes 3 Dormitorios 2")
    assert SOURCE_SIGNALS["dormitorios"].search("Detalles Dormitorios 2 Baños 1")
    assert SOURCE_SIGNALS["banos"].search("Detalles Dormitorios 2 Baños 1")


def test_MUERDE_numero_en_letras_antes_del_rotulo():
    """`masar` (660513): «con 3 dormitorios un baño 3 patios 2 descubiertos».
    El 3 es de los patios; la ficha dice «un baño» en letras."""
    texto = "con 3 dormitorios un baño 3 patios 2 descubiertos y uno cubierto"
    assert not SOURCE_SIGNALS["banos"].search(texto)
    assert SOURCE_SIGNALS["dormitorios"].search(texto)


def test_una_medida_antes_del_rotulo_no_lo_invalida():
    """`building` (209): «Superficie cubierta: 315 Dormitorios: 4 Baños: 3».
    El 315 es una medida, no un conteo: la ficha publica 4 dormitorios."""
    texto = "Superficie total: 400 Superficie cubierta: 315 Dormitorios: 4 Baños: 3"
    assert SOURCE_SIGNALS["dormitorios"].search(texto)
    assert SOURCE_SIGNALS["banos"].search(texto)
