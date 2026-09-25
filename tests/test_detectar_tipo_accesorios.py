# -*- coding: utf-8 -*-
"""El tipo es lo que la propiedad ES, no lo que trae.

Medido el 2026-09-25 sobre 26.993 titulos guardados: 44 fichas en 24 agencias
tenian tipo «cochera» siendo «Dúplex … con cochera», «Semipiso … y cochera» o
«3 ambientes con cochera»; y 266 «Galpón», 61 «Dúplex» y 7 «Fracción» quedaban
sin tipo porque la tilde no coincidia con la clave.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from connectors.base import detectar_tipo  # noqa: E402


@pytest.mark.parametrize("titulo, tipo", [
    ("Dúplex de 6 amb. con cochera y patio en venta | Berazategui", "casa"),
    ("DUPLEX AL FRENTE - C/COCHERA", "casa"),
    ("Semipiso 3 amb. con balcón al frente y cochera", "departamento"),
    ("4 AMBIENTES CON COCHERA Y TERRAZA PROPIA A ESTRENAR", None),
    ("Galpón a la venta", "galpon"),
    ("Venta de Fracción en Villa de Merlo", "terreno"),
    ("Depto. tipo dúplex de 2 ambientes con patio", "departamento"),
    ("PH en Venta en Arguello - APTO CREDITO DUPLEX", "departamento"),
    ("Lote de 500 mts apto Dúplex! Escritura.", "terreno"),
])
def test_MUERDE_accesorios_y_tildes(titulo, tipo):
    assert detectar_tipo(titulo) == tipo


@pytest.mark.parametrize("titulo, tipo", [
    ("Cochera cubierta en venta - Recoleta", "cochera"),
    ("Cochera en edificio con seguridad", "cochera"),
    ("Galpón y Cocheras", "galpon"),
    ("Local con depósito en el centro", "local"),
    ("Casa con pileta y cochera doble", "casa"),
])
def test_lo_que_ya_estaba_bien_no_cambia(titulo, tipo):
    assert detectar_tipo(titulo) == tipo


def test_semipiso_y_triplex_tienen_tipo():
    from connectors.base import detectar_tipo
    assert detectar_tipo("Amplio Semi piso en PB con cochera, baulera y patio") == "departamento"
    assert detectar_tipo("Amplio Triplex de 4 Amb con Escritorio y 2 Cocheras") == "casa"
    assert detectar_tipo("Oficina en 1er piso") == "oficina"


def test_una_oficina_en_semipiso_es_una_oficina():
    from connectors.base import detectar_tipo
    assert detectar_tipo("VENTA OFICINA EN SEMIPISO A ESTRENAR EN ZONA CENTRO") == "oficina"
    assert detectar_tipo("Muy luminoso semipiso de oficina A Estrenar") == "oficina"
