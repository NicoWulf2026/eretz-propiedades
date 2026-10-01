"""Lote 4: conteos escritos con letras en la prosa de la ficha.

`pozzobon` «un baño» (Gate 28-09 21h, DEFECTO_PENDIENTE) y `ente` «cuatro
dormitorios»: la cantidad estaba publicada y quedaba sin leer. El auditor no
exige conteos en letras (SOURCE_SIGNALS pide cifras), asi que leerlos solo
agrega datos: no puede crear NEEDS_FIX. Lo que se cuida es no afirmar un
conteo ambiguo, porque un valor mal leido parece real.
"""
from __future__ import annotations

import pytest

from connectors.generico import ETIQUETAS_DE_CONTEO, GenericoConnector as G

DORM, BANOS, AMB = (ETIQUETAS_DE_CONTEO[k] for k in ("dormitorios", "banos", "ambientes"))


@pytest.mark.parametrize("texto,dorm,banos,amb", [
    ("Hermosa casa de cuatro dormitorios, living, cocina y un baño completo.", 4, 1, None),
    ("Departamento de dos ambientes con un dormitorio y un baño.", 1, 1, 2),
    ("Living, cocina y dos baños. Patio.", None, 2, None),
    ("CASA DE TRES DORMITORIOS Y DOS BAÑOS", 3, 2, None),
    # Las cifras mandan: el camino de siempre no cambia.
    ("Departamento de 3 dormitorios y un baño", 3, 1, None),
])
def test_lee_la_cantidad_escrita_con_letras(texto, dorm, banos, amb) -> None:
    assert G._cuenta(texto, DORM, None) == dorm
    assert G._cuenta(texto, BANOS, None) == banos
    assert G._cuenta(texto, AMB, None) == amb


@pytest.mark.parametrize("texto", [
    "Un baño en suite y un baño de servicio.",          # dos menciones: son 2, no 1
    "Departamentos de dos y tres dormitorios.",          # rango: un emprendimiento
    "Unidades de uno a dos dormitorios",
    "Casa con más de dos dormitorios",                   # cota, no cantidad
    "Hasta tres dormitorios segun la unidad",
    "Una de las habitaciones da al patio",               # no es un conteo
    "Un dormitorios",                                    # sin concordancia
    "Dos dormitorio",
])
def test_no_afirma_un_conteo_ambiguo(texto) -> None:
    assert G._cuenta(texto, DORM, None) is None
    assert G._cuenta(texto, BANOS, None) is None


def test_una_tabla_de_atributos_no_cae_a_las_letras() -> None:
    """En una tabla el numero va despues del rotulo; las letras son prosa."""
    texto = "Ambientes 3 Dormitorios 2 Baños 1 Descripcion: casa de cuatro dormitorios"
    assert G._cuenta(texto, DORM, None) == 2


def test_de_punta_a_punta_en_una_ficha_solo_en_prosa() -> None:
    html = ("<div class='descripcion'><p>Excelente casa de cuatro dormitorios, "
            "living comedor, cocina y un baño completo. Patio con parrilla.</p></div>")
    texto = "Excelente casa de cuatro dormitorios, living comedor, cocina y un baño completo."
    assert G._cuenta_de_ficha(html, texto, DORM, None) == 4
    assert G._cuenta_de_ficha(html, texto, BANOS, None) == 1


def test_la_estructura_sigue_mandando_sobre_la_prosa() -> None:
    html = ("<ul><li><span>Dormitorios</span><span>3</span></li></ul>"
            "<p>Casa de cuatro dormitorios originales, hoy tres.</p>")
    texto = "Dormitorios 3 Casa de cuatro dormitorios originales, hoy tres."
    assert G._cuenta_de_ficha(html, texto, DORM, None) == 3


# v2 (2026-10-01, LOCAL): falsos encontrados al medir el radio sobre el corpus
# real (20 de 45 en la muestra de la version original). Ninguno se afirma.
@pytest.mark.parametrize("texto,etiqueta", [
    ("Ofrece un ambiente seguro y tranquilo, con seguridad las 24 hs.", AMB),
    ("generando un ambiente moderno y de gran integracion", AMB),
    ("esta unidad dispone de un ambiente tipo comodin, adaptable", AMB),
    ("Dormitorio principal con calefactor. Segundo baño. Dos dormitorios en desnivel.", DORM),
    ("El sector privado: suite principal y dos habitaciones secundarias que comparten un baño.", DORM),
    ("P.B: dormitorio con baño y playroom. P.A: dos dormitorios en suite con vistas.", DORM),
    ("Dos casitas independientes de dos dormitorios cada una.", DORM),
    ("En planta baja oficina, del piso 1 al 3 cuenta con semipisos de un dormitorio.", DORM),
    ("11 pisos de departamentos semipisos, de uno y de dos dormitorios", DORM),
    ("Recepcion con dos baños, uno de los cuales es para discapacitados. Habitaciones con baño.", BANOS),
])
def test_v2_no_afirma_conteos_parciales_por_unidad_o_de_clima(texto, etiqueta):
    assert G._cuenta(texto, etiqueta, None) is None


@pytest.mark.parametrize("texto,etiqueta,valor", [
    ("Distribucion: Desarrollada en una planta. Dos dormitorios. Un baño completo.", DORM, 2),
    ("Distribucion: Desarrollada en una planta. Dos dormitorios. Un baño completo.", BANOS, 1),
    ("Departamento en venta de tres ambientes con balcon al frente.", AMB, 3),
    ("Cuenta con cinco ambientes: cocina, living y lavadero.", AMB, 5),
])
def test_v2_sigue_leyendo_la_prosa_inequivoca(texto, etiqueta, valor):
    assert G._cuenta(texto, etiqueta, None) == valor
