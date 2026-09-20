# -*- coding: utf-8 -*-
"""Dos agencias con la misma url de fuente enumerarían el mismo catálogo.

De 3.113 agencias con fuente resoluble, **25 urls están compartidas por 61
agencias**. Compartir HOST no es el problema —`buscainmueble.com` aparece en 70
agencias y cada una tiene su url propia dentro del host, que es como funciona
un SaaS—. El problema es la url idéntica.

`https://cir.org.ar/socios` la comparten **diez** agencias: es la lista de
socios de un colegio inmobiliario, no la web de ninguna de ellas.

Y el número que ordena la urgencia: **24 de las 25 no tienen ni una
certificación ni una propiedad**, porque la cola no llegó. Es una mina, no un
incendio, y desactivarla antes de pisarla cuesta mucho menos que separar
inventario mezclado después.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from fuentes_compartidas import clasificar, normalizar  # noqa: E402


@pytest.mark.parametrize("url,agencias,clase", [
    ("https://cir.org.ar/socios",
     ["roomix:adrian giaganti", "roomix:baclini propiedades"],
     "DIRECTORIO_INSTITUCIONAL"),
    ("https://www.cpmclz.com.ar/colegiados",
     ["roomix:mariana aguirre", "roomix:martin castro"],
     "DIRECTORIO_INSTITUCIONAL"),
    ("https://ciali.org/socios-socias",
     ["roomix:una", "roomix:otra"], "DIRECTORIO_INSTITUCIONAL"),
    ("http://colegioinmobiliarioold.com.ar/infractores.asp?id=1",
     ["roomix:una", "roomix:otra"], "DIRECTORIO_INSTITUCIONAL"),
    ("https://indice-inmobiliario.com/buscar",
     ["roomix:daniel feder", "roomix:vanesa propiedades"],
     "BUSCADOR_DE_PORTAL"),
    ("https://www.remax-urbana.com.ar",
     ["roomix:re max actitud", "roomix:re max time"], "OFICINAS_DE_RED"),
    ("https://www.cosapropiedades.com",
     ["roomix:cosa propiedades", "roomix:cas as propiedades"],
     "POSIBLE_DUPLICADO"),
    ("https://rodriguezjurado.com.ar",
     ["roomix:maqueira rodriguez propiedades",
      "roomix:rodriguez jurado propiedades"], "SIN_CLASIFICAR"),
])
def test_cada_coincidencia_se_clasifica(url, agencias, clase):
    assert clasificar(url, agencias) == clase


def test_MUERDE_un_directorio_gana_sobre_cualquier_parecido_de_nombre():
    """El orden de las reglas importa y es fácil de romper.

    Si dos agencias de nombre parecido comparten la página de socios de un
    colegio, lo que decide **no** es que se parezcan: es que esa url no es la
    web de ninguna de las dos. Clasificarlo como duplicado mandaría a revisar
    la identidad cuando lo que hay que sacar es la fuente.
    """
    clase = clasificar("https://cir.org.ar/socios",
                       ["roomix:lopez propiedades", "roomix:lopez propiedad"])
    assert clase == "DIRECTORIO_INSTITUCIONAL"


def test_MUERDE_compartir_host_no_es_compartir_fuente():
    """`buscainmueble.com` lo usan 70 agencias y no hay ningún problema.

    Cada una tiene su propia url dentro del host. Este módulo agrupa por url
    normalizada justamente para no confundir las dos cosas: si agrupara por
    host, reportaría 70 agencias en conflicto donde no hay ninguno.
    """
    a = normalizar("https://buscainmueble.com/inmobiliaria/lopez/")
    b = normalizar("https://buscainmueble.com/inmobiliaria/perez")
    assert a != b


def test_la_barra_final_y_las_mayusculas_no_hacen_dos_urls():
    """Y al revés: si normalizara mal, dejaría pasar colisiones reales."""
    assert (normalizar("https://Cir.org.ar/Socios/")
            == normalizar("https://cir.org.ar/socios"))


def test_una_red_completa_se_reconoce_aunque_escriban_distinto():
    """`re max`, `remax` y `RE/MAX` son la misma red."""
    for nombres in (["roomix:re max noa", "roomix:remax noa ii"],
                    ["roomix:century 21 uno", "roomix:century21 dos"]):
        assert clasificar("https://x.com.ar", nombres) == "OFICINAS_DE_RED"


def test_una_sola_agencia_de_red_con_otra_cualquiera_no_es_red():
    """Basta con que una no sea de la red para que la explicación no aplique."""
    assert clasificar("https://x.com.ar",
                      ["roomix:re max noa", "roomix:lopez propiedades"]) != \
        "OFICINAS_DE_RED"
