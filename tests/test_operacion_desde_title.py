# -*- coding: utf-8 -*-
"""La operación está en el `<title>` de la página, no sólo en el título editorial.

**Rojo a propósito. El arreglo NO está aplicado.** Marcado `xfail(strict=True)`:
el día que se aplique el parche, este test va a pasar y la suite se va a poner
en rojo, obligando a sacar el marcador. Un test rojo que nadie ve no existe.

EL DEFECTO, medido el 2026-09-15 sobre `fenix inmobiliaria` —499 fichas,
`generic/sitemap`—: `operacion` falla en **179 de 499**, y la fuente la publica
en las 499.

LA CAUSA: `_operacion_en_la_ficha()` lee el título editorial, que carga la
inmobiliaria a mano. Cuando ese título trae la palabra, funciona:

    "CASA EN VENTA Z/ AV. SANTA CRUZ Y AV. 115"   -> venta

y cuando no la trae, queda vacío:

    "z/ EL BRETE. EDIF. ARAI."                    -> None

pero la página publica la operación igual, en su propio `<title>`:

    "DF621 - Departamento en Venta en Posadas | Inmobiliaria Posadas"

LO QUE SE MIDIÓ ANTES DE PROPONERLO, y que es lo que autoriza el arreglo:

    TRUE_RECOVERY          20/20   fichas sin operación que el <title> completa
    FALSE_OPERATION_RISK       0   sobre 35 fichas que YA tienen operación
                                   —20 venta + 15 alquiler—, el <title> no
                                   contradijo ninguna

Las otras cuatro señales que se probaron —encabezado, URL canónica, migas de
pan y datos estructurados— recuperaron **0 de 20**. No sirven, y por eso el
arreglo usa una sola.

El caso caro se probó aparte: las 15 fichas que hoy dicen `alquiler` siguen
diciendo `alquiler` por `<title>`. Entre venta y alquiler no hay un error
chico, y sin esa comprobación el arreglo no se podía proponer.
"""
import re
from pathlib import Path

import pytest

from connectors.generico import GenericoConnector

FIXTURE = Path(__file__).parent / "fixtures" / "operacion_solo_en_title.html"


@pytest.fixture
def html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def titulo_html(h: str) -> str | None:
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", h)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else None


def encabezado(h: str) -> str | None:
    m = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", h)
    return re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", m.group(1))).strip() \
        if m else None


# --- el estado de hoy ---------------------------------------------------

def test_el_titulo_editorial_no_dice_la_operacion(html):
    """Así titula la inmobiliaria: sin la palabra."""
    h1 = encabezado(html)
    assert h1 == "z/ EL BRETE. EDIF. EJEMPLO."
    assert GenericoConnector._operacion_en_la_ficha(h1) is None


def test_el_title_del_html_SI_la_dice(html):
    """El dato existe en la página. No hay que inventarlo."""
    t = titulo_html(html)
    assert "en Venta" in t
    assert GenericoConnector._operacion_en_la_ficha(t) == "venta"


# --- el rojo ------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason="defecto abierto: la operacion sale del "
                                       "titulo editorial y no cae al <title>")
def test_ROJO_la_operacion_cae_al_title_cuando_el_editorial_no_la_trae(html):
    """El camino real de hoy, copiado sin arreglar.

    Poner el fallback adentro del test lo haría pasar, y entonces probaría la
    solución en vez del defecto.
    """
    operacion = GenericoConnector._operacion_en_la_ficha(encabezado(html))
    # <-- acá falta el `if operacion is None: mirar el <title>`
    assert operacion == "venta", ("quedo sin operacion teniendola en el "
                                  "<title> de la propia pagina")


# --- lo que el arreglo NO puede hacer -----------------------------------

def test_el_title_no_puede_pisar_una_operacion_ya_afirmada():
    """El fallback es fallback: sólo entra si no hay nada.

    Se midió que el `<title>` no contradice en 35 fichas, pero "no contradijo
    en la muestra" no es "no puede contradecir". Si algún día una ficha dijera
    alquiler en el cuerpo y venta en el `<title>`, gana el cuerpo: un alquiler
    publicado como venta es un error que ve el usuario final.
    """
    editorial = "CASA EN ALQUILER Z/ AV. EJEMPLO"
    del_title = "Casa en Venta en Ciudad | Inmobiliaria"
    operacion = GenericoConnector._operacion_en_la_ficha(editorial)
    if operacion is None:
        operacion = GenericoConnector._operacion_en_la_ficha(del_title)
    assert operacion == "alquiler"
