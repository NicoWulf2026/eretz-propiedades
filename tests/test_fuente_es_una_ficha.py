# -*- coding: utf-8 -*-
"""Subir de una ficha a la raíz es seguro sólo si la raíz sigue siendo suya.

16 agencias tienen como fuente registrada **una propiedad** en vez del catálogo.
`fios consultoria` apunta a `fios.com.ar/emprendimiento-64427-...` y enumeró
cero; `danisa robledo` apuntaba a una ficha dentro de un marketplace y de ahí
entraron 6 propiedades ajenas.

La reparación obvia —subir a la raíz del mismo sitio— tiene una trampa que la
primera versión de este módulo pisó: para `danisa robledo` propuso
`https://www.mercado-unico.com/`, la raíz de un **marketplace entero**. Habría
cambiado una propiedad ajena por todas.

Los dos defectos que este archivo fija son los dos que aparecieron al correrlo.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from fuente_es_una_ficha import RE_FICHA_EN_RAIZ, es_una_ficha  # noqa: E402


@pytest.mark.parametrize("url", [
    "https://www.fios.com.ar/emprendimiento-64427-condominio-en-fisherton",
    "https://www.yacopino.com/propiedad-8519705-lascano-4320-departamento",
    "https://barnes-buenosaires.com/en/property/8509350/",
    "https://www.demarcooperacionesinmobiliarias.com.ar/front/propiedad/172",
    "https://www.mercado-unico.com/propiedades/69019270b5bada00113d470b",
    "https://century21.com.ar/en_us/propiedad/349966_inmueble-productivo",
])
def test_una_ficha_se_reconoce_como_ficha(url):
    assert es_una_ficha(url)


@pytest.mark.parametrize("url", [
    "https://www.fios.com.ar/",
    "https://www.fios.com.ar/propiedades",
    "https://inmob.com.ar/propiedades/venta",
    "https://inmob.com.ar/inmuebles",
])
def test_un_catalogo_no_se_confunde_con_una_ficha(url):
    """`/propiedades` es el catálogo; `/propiedad-8519705` es una ficha.

    Lo que las separa es el identificador. Sin exigirlo, esta herramienta
    marcaría como rota a cualquier agencia bien configurada.
    """
    assert not es_una_ficha(url)


def test_MUERDE_el_enlace_relativo_sin_barra_se_ve():
    """La tercera vez que este proyecto tropieza con lo mismo.

    `fios.com.ar` enlaza su catálogo como `href="propiedades"`, sin barra
    inicial, y por eso la primera versión no le encontró catálogo y no propuso
    nada. Antes fue `bottai inmobiliaria`, cuyo conteo dio 0 porque sus enlaces
    son `href="inmueble_6067"`.
    """
    html = '<a href="propiedades">Ver propiedades</a>'
    assert RE_FICHA_EN_RAIZ.findall(html) == ["propiedades"]


def test_tambien_se_ve_el_enlace_absoluto_de_siempre():
    """El arreglo no puede romper el caso que ya funcionaba."""
    html = '<a href="/propiedades/venta">Venta</a>'
    assert RE_FICHA_EN_RAIZ.findall(html) == ["/propiedades/venta"]


def test_MUERDE_la_raiz_de_un_marketplace_no_se_propone(monkeypatch):
    """El error que la primera versión sí cometió.

    Sin comprobar propiedad, subir de una ficha a la raíz cambia UNA propiedad
    ajena por TODAS. Y no alcanza con `es_portal_url()`: no conoce
    `mercado-unico.com`, que es justamente el caso.
    """
    import fuente_es_una_ficha as modulo

    html = ('<title>Mercado Unico - Portal inmobiliario</title>'
            '<a href="/propiedades/1">x</a><a href="/propiedades">todas</a>')
    monkeypatch.setattr(modulo, "bajar",
                        lambda u, limite=0: (200, "https://www.mercado-unico.com/", html))
    señal = modulo.verificar_raiz(
        "https://www.mercado-unico.com/propiedades/69019270b5bada00113d470b",
        "Danisa Robledo Servicios Inmobiliarios")
    assert señal["propuesta"] is None
    assert "no nombra a la agencia" in señal["porque"]


def test_si_hay_un_catalogo_que_declara_inventario_si_se_propone(monkeypatch):
    """El otro lado: la herramienta tiene que poder proponer algo.

    Una que nunca propone nada es tan inútil como una que propone cualquier
    cosa. Lo que se propone es el CATÁLOGO, no la raíz.
    """
    import fuente_es_una_ficha as modulo

    paginas = {
        "https://www.fios.com.ar/": ('<title>FIOS Inmobiliaria</title>'
                                     '<a href="propiedades">Propiedades</a>'),
        "https://www.fios.com.ar/propiedades": "<p>266 propiedades</p>",
    }
    monkeypatch.setattr(modulo, "bajar",
                        lambda u, limite=0: (200, u, paginas.get(u, "")))
    señal = modulo.verificar_raiz(
        "https://www.fios.com.ar/emprendimiento-64427-condominio-en-fisherton",
        "FIOS Consultoria Inmobiliaria")
    assert señal["propuesta"] == "https://www.fios.com.ar/propiedades"


def test_MUERDE_sin_catalogo_que_declare_nada_no_se_propone_la_raiz(monkeypatch):
    """La regresión que metí y que llegó a APLICARSE sobre `barnes`.

    Al aflojar el patrón de enlaces, sitios como `barnes` pasaron a tener rutas
    candidatas y dejaron de caer en la guarda de "no hay ninguna". La rama de
    respaldo proponía la raíz igual, y así `barnes` recibió su propia raíz como
    fuente —una página que no publica nada— y se dio el caso por corregido.

    Si ninguna candidata declara inventario, no sabemos dónde está el catálogo.
    """
    import fuente_es_una_ficha as modulo

    paginas = {
        "https://barnes-buenosaires.com/": (
            '<title>Barnes Buenos Aires</title>'
            '<a href="/en/properties">Properties</a>'
            '<a href="/es/propiedades">Propiedades</a>'),
        "https://barnes-buenosaires.com/en/properties": "<p>sin resultados</p>",
        "https://barnes-buenosaires.com/es/propiedades": "<p>sin resultados</p>",
    }
    monkeypatch.setattr(modulo, "bajar",
                        lambda u, limite=0: (200, u, paginas.get(u, "")))
    señal = modulo.verificar_raiz(
        "https://barnes-buenosaires.com/en/property/8509350/",
        "Barnes International Realty")
    assert señal["propuesta"] is None
    assert "NINGUNA declara inventario" in señal["porque"]


def test_una_raiz_sin_catalogo_no_se_propone(monkeypatch):
    """`barnes` y `demarco` caen acá, y está bien que caigan.

    Proponer una URL sin catálogo convertiría un error visible —enumera cero—
    en uno silencioso.
    """
    import fuente_es_una_ficha as modulo

    monkeypatch.setattr(modulo, "bajar",
                        lambda u, limite=0: (200, "https://barnes-buenosaires.com/",
                                             "<title>Barnes Buenos Aires</title>"))
    señal = modulo.verificar_raiz(
        "https://barnes-buenosaires.com/en/property/8509350/",
        "Barnes International Realty")
    assert señal["propuesta"] is None
    assert "no se le ve catalogo" in señal["porque"]


# --------------------------------------------------------------------------
# Lo que se aprendió al APLICAR las correcciones, que es donde se vio que no
# alcanzaba con sacar la fuente de la ficha: también hay que acertarle al
# catálogo.
#
# `fios` se recertificó contra la raíz que yo había propuesto y siguió
# enumerando CERO, porque `fios.com.ar/` declara literalmente "0 Propiedades"
# mientras `fios.com.ar/propiedades` declara 266. Enlazar a un catálogo no es
# ser uno.
# --------------------------------------------------------------------------

def test_MUERDE_la_palabra_puede_ir_en_cualquier_parte_de_la_url():
    """Tercera vez que la misma suposición muerde a este proyecto.

    `bottai` enlaza `inmueble_6067` sin barra, `fios` enlaza `propiedades`
    relativo, y `yacopino` enlaza `busqueda-de-propiedades-en-venta`, donde la
    palabra va precedida de un guion. Exigir que abra un segmento pierde
    candidatas que ni siquiera llegan a evaluarse.
    """
    html = ('<a href="busqueda-de-propiedades-en-venta">Venta</a>'
            '<a href="propiedades">Todas</a>'
            '<a href="/listado.php?tipo=1">Listado</a>')
    encontrados = RE_FICHA_EN_RAIZ.findall(html)
    assert "busqueda-de-propiedades-en-venta" in encontrados
    assert "propiedades" in encontrados


def test_se_elige_la_candidata_que_mas_declara_y_no_la_primera(monkeypatch):
    """`yacopino` enlaza `/emprendimientos` ANTES que su catálogo de venta.

    Cortar en la primera candidata aceptable es quedarse con el orden del menú:
    elegía la que declara CERO teniendo al lado una que declara 85.
    """
    import fuente_es_una_ficha as modulo

    paginas = {
        "https://yacopino.com.ar/": ('<title>Yacopino</title>'
                           '<a href="emprendimientos">Emprendimientos</a>'
                           '<a href="busqueda-de-propiedades-en-venta">Venta</a>'),
        "https://yacopino.com.ar/emprendimientos": "<p>0 propiedades</p>" + "<a href='/propiedad/1'>x</a>" * 17,
        "https://yacopino.com.ar/busqueda-de-propiedades-en-venta": "<p>85 propiedades</p>",
    }
    monkeypatch.setattr(modulo, "bajar",
                        lambda u, limite=0: (200, u, paginas.get(u, "")))
    señal = modulo.verificar_raiz("https://yacopino.com.ar/propiedad-123-casa", "Yacopino")
    assert señal["propuesta"].endswith("busqueda-de-propiedades-en-venta")
    assert "declara 85" in señal["porque"]


def test_una_raiz_que_declara_cero_no_se_propone_si_hay_algo_mejor(monkeypatch):
    """El caso `fios`, exacto.

    La raíz enlazaba al catálogo y por eso se propuso; pero declaraba cero y la
    agencia siguió enumerando cero después de "corregirla". Enlazar a un
    catálogo no es ser uno.
    """
    import fuente_es_una_ficha as modulo

    paginas = {
        "https://fios.com.ar/": '<title>FIOS</title><a href="propiedades">Propiedades</a>',
        "https://fios.com.ar/propiedades": "<p>266 propiedades</p>",
    }
    monkeypatch.setattr(modulo, "bajar",
                        lambda u, limite=0: (200, u, paginas.get(u, "")))
    señal = modulo.verificar_raiz("https://fios.com.ar/emprendimiento-64427-condominio",
                                  "FIOS Consultoria")
    assert señal["propuesta"] == "https://fios.com.ar/propiedades"
