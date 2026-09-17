# -*- coding: utf-8 -*-
"""Un `%20` en una url no es un contador de propiedades.

El 2026-09-16 la cola paró en `gabriela aloise propiedades` con la evidencia
"contador publicado: 20propiedades". No había 20 propiedades. El sitio tiene un
botón de WhatsApp cuyo texto dice *"...sobre las propiedades"*, y en la url ese
espacio viaja como `%20`. El patrón usaba `\\s*` —cero o más espacios— así que
leyó `20propiedades` adentro del enlace y lo reportó como total declarado.

La página de listado de ese mismo sitio dice **"0 propiedades"**.

Un contador falso no sólo miente en un informe: detiene a los dos workers hasta
que alguien va a mirar. Por eso esto es control plane y se arregla bajo el
congelamiento: `defect_triage.py` no está entre los componentes de la huella,
así que no invalida ninguna certificación ni cambia un solo campo extraído.

Los fixtures son el marcado real, recortado a lo que decide.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from scripts.defect_triage import RE_CONTADOR, senales_de_catalogo  # noqa: E402

WHATSAPP_REAL = (
    '<a href="https://wa.me/5491123490070?text=Hola!%20Quisiera%20m%C3%A1s'
    '%20informaci%C3%B3n%20sobre%20las%20propiedades" class="whatsapp-float">'
    "Consultar</a>"
)


def test_MUERDE_el_enlace_de_whatsapp_no_publica_un_contador():
    """El caso exacto que detuvo la cola."""
    assert RE_CONTADOR.search(WHATSAPP_REAL) is None


def test_ese_sitio_no_declara_inventario_por_el_boton_de_whatsapp():
    """La señal completa, no sólo el patrón: no debe aparecer ningún contador."""
    señales = senales_de_catalogo(WHATSAPP_REAL)
    assert not [s for s in señales if "contador" in s]


@pytest.mark.parametrize("texto,esperado", [
    ("16 propiedades encontradas", "16"),
    ("Mostrando 248 inmuebles", "248"),
    ("<span>20 propiedades</span>", "20"),
    ("Tenemos 7 avisos publicados", "7"),
])
def test_un_contador_de_verdad_se_sigue_leyendo(texto, esperado):
    """La reparación no puede volver ciego al detector.

    Si dejara de leer los contadores legítimos, agencias con catálogo declarado
    mayor que el enumerado pasarían como completas, que es el §28 al revés y
    mucho peor que un paro de más.
    """
    encontrado = RE_CONTADOR.search(texto)
    assert encontrado is not None and encontrado.group(1) == esperado


@pytest.mark.parametrize("texto", [
    "https://wa.me/54?text=sobre%20las%20propiedades",
    "?mensaje=ver%20120%20propiedades",   # el %20 pegado al numero
    "clase-casa20propiedades",
    "id=ficha30inmuebles",
])
def test_lo_que_esta_pegado_a_un_simbolo_o_a_una_letra_no_cuenta(texto):
    """Dos formas del mismo error: el `%` de una url y el pegoteo del marcado."""
    assert RE_CONTADOR.search(texto) is None


def test_un_contador_al_principio_del_texto_se_lee():
    """El lookbehind no puede romper el caso de borde más simple."""
    encontrado = RE_CONTADOR.search("35 propiedades")
    assert encontrado is not None and encontrado.group(1) == "35"


@pytest.mark.xfail(strict=True, reason=(
    "defecto abierto y PREEXISTENTE: con separador de miles el contador "
    "sub-cuenta. '1.234 resultados' se lee como 234, no como 1234. No lo "
    "introduce el lookbehind -el patron viejo hacia lo mismo- y no se arregla "
    "aca porque sub-contar es conservador: hace parar la cola de mas, nunca de "
    "menos, que es el lado seguro. Va a la ventana semantica"))
def test_ROJO_el_separador_de_miles_hace_subcontar_al_contador():
    """Se documenta en rojo en vez de bendecirse en verde.

    Un test que afirmara `== "234"` como resultado correcto convertiría un
    defecto en contrato, y el día que alguien lo arregle el test lo frenaría.
    """
    encontrado = RE_CONTADOR.search("1.234 resultados")
    assert encontrado is not None and encontrado.group(1) == "1234"
