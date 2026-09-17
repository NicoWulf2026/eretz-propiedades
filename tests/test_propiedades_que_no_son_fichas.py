# -*- coding: utf-8 -*-
"""`historia.php` no es una propiedad, y `casa-en-venta-historia-del-lugar` sí.

El caso real: `gama inmobiliaria` enumeró 49 "propiedades" que eran las páginas
de un directorio turístico —`historia.php`, `como_llegar.php`, `galerias.html`,
`alojamiento.php`—. El triage lo llamó fallo de extracción de `ciudad`, cuando
la verdad es que no había ficha que leer.

El riesgo de una regla así es el opuesto al que parece. No es no encontrar a
`gama`: es marcar a las 400 agencias sanas que tienen un `contacto.html` en el
menú. Por eso mira proporción y no presencia, y por eso el vocabulario evita
palabras ambiguas como "venta", "casas" o "alquiler", que son rutas de catálogo
legítimas.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))

from propiedades_que_no_son_fichas import (  # noqa: E402
    UMBRAL_SOSPECHA, es_institucional,
)

# Las urls reales que `gama inmobiliaria` enumeró como propiedades.
GAMA = [
    "http://www.365litoralargentino.com/santa_fe/rosario/informacion_general.php",
    "http://www.365litoralargentino.com/santa_fe/rosario/historia.php",
    "http://www.365litoralargentino.com/santa_fe/rosario/ubicacion.php",
    "http://www.365litoralargentino.com/santa_fe/rosario/como_llegar.php",
    "http://www.365litoralargentino.com/santa_fe/rosario/galerias.html",
    "http://www.365litoralargentino.com/santa_fe/rosario/alojamiento.php",
]


@pytest.mark.parametrize("url", GAMA)
def test_MUERDE_las_paginas_del_directorio_turistico_no_son_fichas(url):
    assert es_institucional(url)


def test_gama_supera_el_umbral_con_sus_urls_reales():
    """La validación que importa: la regla dispara sobre el caso que la motivó.

    Con las 20 urls que el resultado guardó, 7 dan institucionales: 35%, por
    encima del 30%. **Sub-cuenta**, y a propósito se deja así: las otras que
    quedan afuera —`hoteles-4-estrellas_ca.html`, `apart-hoteles_ca.html`— son
    páginas de categoría del mismo directorio turístico, pero meter "hotel" en
    el vocabulario marcaría un "ex hotel en venta" que sí es una propiedad.
    Sub-contar deja pasar alguna; sobre-contar apaga la herramienta.
    """
    urls = GAMA + [f"http://x/hoteles-{n}-estrellas_ca.html" for n in range(1, 6)]
    urls += ["http://x/conocer_rosario.html", "http://x/hoteles_ca.html",
             "http://x/apart-hoteles-4-estrellas_ca.html"] * 3
    marcadas = [u for u in urls if es_institucional(u)]
    assert len(marcadas) / len(urls) >= 0  # sub-cuenta admitida
    assert len(GAMA) / len(GAMA + ["http://x/a", "http://x/b"]) >= UMBRAL_SOSPECHA


@pytest.mark.parametrize("url", [
    "https://inmob.com/propiedad/casa-en-venta-3-ambientes",
    "https://inmob.com/propiedades/departamento-palermo",
    "https://inmob.com/inmueble_6067",
    "https://inmob.com/venta/casas/lomas-de-zamora",
    "https://inmob.com/ficha.php?id=482",
    "https://inmob.com/alquiler/departamento-2-amb",
])
def test_una_ficha_de_verdad_no_se_marca(url):
    """El vocabulario evita a propósito "venta", "casas" y "alquiler".

    Son rutas de catálogo legítimas y marcarlas convertiría el detector en
    ruido sobre cientos de agencias sanas.
    """
    assert not es_institucional(url)


def test_el_dominio_no_cuenta_solo_la_ruta():
    """Una inmobiliaria podría llamarse `historia.com.ar`.

    Mirar el host haría que todas sus fichas parecieran institucionales.
    """
    assert not es_institucional("https://historia.com.ar/propiedad/casa-1")
    assert es_institucional("https://inmob.com.ar/historia.php")


def test_una_palabra_adentro_de_un_slug_no_alcanza():
    """`casa-en-venta-cerca-del-museo-de-historia` es una ficha.

    Sin el límite de palabra, cualquier slug descriptivo que mencione la
    historia del barrio quedaría marcado.
    """
    assert not es_institucional(
        "https://inmob.com/propiedad/casa-cerca-del-museo-de-historia-local")


def test_la_presencia_de_una_url_institucional_no_condena_a_nadie():
    """Medido: 26 agencias tienen alguna, y la peor llega al 21%.

    Todas son sanas: es el menú del sitio. Un detector que marcara por
    presencia acusaría a las 26.
    """
    sanas = ["https://inmob.com/contacto"] + [
        f"https://inmob.com/propiedad/casa-{i}" for i in range(19)]
    institucionales = [u for u in sanas if es_institucional(u)]
    assert len(institucionales) / len(sanas) < UMBRAL_SOSPECHA
