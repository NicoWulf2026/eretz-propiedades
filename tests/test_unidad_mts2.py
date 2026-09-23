# -*- coding: utf-8 -*-
"""`mts2` es la misma unidad que `m2`, y se escribe tanto como aquella.

`alianza real estate` publica un terreno en Pujato con «Precio: Consulte»,
«Area: 382-mts2», «Dormitorios: 2», una lista de comodidades -Living Comedor,
Cochera, Patio, Toilette, Bano, Lavadero, Quincho- y 16 fotos. Es una
propiedad, y se descartaba.

Sin precio numerico la regla exige `ATRIBUTOS_SIN_PRECIO` atributos distintos.
La ficha tenia tres reconocidos -bano, cochera, dormitorio- y el cuarto era la
superficie, escrita con una unidad que la expresion no conocia.

Se agrega la UNIDAD y no la palabra `area`, a proposito: `area` aparece en
prosa y aflojaria el umbral por el mismo lado que el comentario del modulo ya
advertia para `superficie`.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from connectors.generico import (ATRIBUTOS_SIN_PRECIO,  # noqa: E402
                                 RE_ATRIBUTOS_TXT)


def atributos(texto: str) -> set[str]:
    return {m.group(0).lower() for m in RE_ATRIBUTOS_TXT.finditer(texto)}


def test_MUERDE_el_caso_alianza():
    """La ficha real, con sus cuatro atributos."""
    ficha = ("s/n Venta - Pujato Consulte Observaciones Lote con amplio "
             "proyecto Detalles ID Propiedad: 7 Tipo: Terrenos Estado: Venta "
             "Precio: Consulte Area: 382-mts2 Dormitorios: 2 Comodidades "
             "Living Comedor Cochera Patio Toilette Antebano Bano Lavadero")
    assert len(atributos(ficha)) >= ATRIBUTOS_SIN_PRECIO


def test_MUERDE_la_unidad_se_reconoce_escrita_de_las_cuatro_formas():
    assert atributos("Area: 382-mts2") == {"mts2"}
    assert atributos("90 mts²") == {"mts²"}
    assert atributos("120 m2") == {"m2"}
    assert atributos("3 m²") == {"m²"}


def test_MUERDE_la_palabra_area_NO_cuenta_como_atributo():
    """El otro lado, y es el que importa: `area` en prosa no puede sumar.

    Si alguien la agrega, una nota de mercado que hable del «area de
    influencia» empieza a parecerse a una ficha.
    """
    assert atributos("el area de influencia del corredor") == set()
    assert atributos("gran area verde y parque") == set()


def test_los_atributos_que_ya_andaban_siguen_andando():
    assert "dormitorio" in atributos("Dormitorios: 2")
    assert "cochera" in atributos("con cochera cubierta")
    assert "superficie" in atributos("Superficie total")
    assert "antiguedad" in atributos("Antiguedad: 6 anos")


def test_una_nota_de_mercado_sigue_sin_parecer_una_ficha():
    """El caso que el umbral existe para rechazar."""
    nota = "Analisis de la superficie construida en 2026 y su evolucion"
    assert len(atributos(nota)) < ATRIBUTOS_SIN_PRECIO
