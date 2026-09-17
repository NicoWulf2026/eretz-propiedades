# -*- coding: utf-8 -*-
"""Un precio de JSON-LD sin moneda no puede tapar la moneda del texto.

Corregido en el candidato unificado. Las pruebas llaman normalize() real;
no replican el defecto dentro del test. La guarda de precio sin moneda sigue
activa y una moneda visible solo completa la cifra estructurada si coincide.
El diagnostico historico que sigue describe el estado PRE-unificacion.

EL DEFECTO, medido el 2026-09-15 sobre `blanco propiedades` -1.213 fichas,
`generic/sitemap`-:

    precio   se extrae en 4 de 1.213
    moneda   se extrae en 4 de 1.213

y la fuente publica el precio en 1.210 de ellas.

LA CAUSA, en cuatro pasos y todos verificados en el código:

  1. `_de_json_ld` lee `offers.price` -> 180000.0, y `offers.priceCurrency`,
     que esta fuente NO publica -> moneda queda None.
  2. `normalize` hace `precio = datos.get("precio")`, que ya no es None.
  3. por eso NO entra al `if precio is None` que baja al texto a buscar
     `U$S 180.000`, que es el único lugar donde está la moneda.
  4. más abajo, la guarda "un numero sin moneda no es un precio" encuentra
     precio sin moneda y **anula el precio**.

La guarda del paso 4 está bien y no se toca: entre pesos y dólares hay un
factor de mil, y publicar el número equivocado es peor que no publicarlo. El
defecto es del paso 3: la búsqueda de la MONEDA está atada a que falte el
PRECIO, y son dos cosas distintas.

Prediccion falsable, y por eso se puede confiar en el diagnóstico: "si la ficha
trae precio en JSON-LD y no trae priceCurrency, falla; si no trae precio en
JSON-LD, funciona". Se probó contra el sitio real en 12 fichas -4 que pasaban y
8 que fallaban- y acertó en 12 de 12.
"""
import re
from pathlib import Path

import pytest

from connectors.generico import (GenericoConnector, _texto, cuerpo_principal,
                                 normalizar_texto_campos, sin_filtros_catalogo)

FIXTURE = Path(__file__).parent / "fixtures" / "jsonld_price_sin_currency.html"

# La misma expresión que usa `normalize()` para bajar al texto.
RE_PRECIO = re.compile(r"(USD|U\$S|US\$|\$|ARS)\s*([\d][\d.,]{2,15})", re.I)


@pytest.fixture
def html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture
def texto(html) -> str:
    """El texto de la etapa 5, armado igual que en `normalize()`."""
    return normalizar_texto_campos(_texto(sin_filtros_catalogo(
        cuerpo_principal(html))))


# --- lo que YA funciona, y que el arreglo no puede romper ----------------

def test_el_json_ld_publica_el_precio(html):
    datos = GenericoConnector._de_json_ld(html)
    assert datos.get("precio") == 180000.0


def test_el_json_ld_NO_publica_la_moneda(html):
    """Esta es la condición que dispara todo. Si la fuente cambiara y
    empezara a publicar `priceCurrency`, el defecto desaparecería solo y este
    test avisaría que la fixture dejó de reproducirlo."""
    datos = GenericoConnector._de_json_ld(html)
    assert datos.get("moneda") is None


def test_la_moneda_esta_en_el_texto_visible(texto):
    """El dato existe. No hay que inventarlo: hay que ir a buscarlo."""
    m = RE_PRECIO.search(texto)
    assert m is not None
    assert m.group(1).upper() == "U$S"
    assert m.group(2) == "180.000"


# --- los dos rojos ------------------------------------------------------

def test_ROJO_la_moneda_se_completa_desde_el_texto(html, texto):
    """Cuando el JSON-LD trae precio y no trae moneda, la moneda tiene que
    salir del texto igual."""
    prop = _normalizar(html)
    assert prop is not None
    assert prop.moneda == 'USD'


def test_ROJO_el_precio_sobrevive_a_la_guarda_de_moneda(html, texto):
    """El desenlace que importa: hoy la guarda anula un precio correcto."""
    prop = _normalizar(html)
    assert prop is not None
    assert prop.precio == 180000.0


def _normalizar(html):
    from connectors.base import Fuente
    return GenericoConnector(type('Cached', (), {'bajar': lambda self, url: html})()).normalize(
        {'source_listing_id': '618', 'source_url': 'https://ejemplo.test/propiedades/618'},
        Fuente('audit:agency', 'Ejemplo', 'https://ejemplo.test'))


# --- ambientes NO va acá, y el motivo importa ---------------------------

def test_la_fuente_NO_publica_ambientes_y_por_eso_no_hay_nada_que_arreglar(texto):
    """`ambientes` figuraba como 1.089 fichas recuperables. No lo es.

    El certificador cuenta la fuente como proveedora de `ambientes` porque su
    patrón encuentra 'ambiente 1'... adentro de la palabra **Mono**ambiente,
    que es una opción del MENÚ DE FILTROS y está idéntica en las 1.213 fichas.
    La propiedad publica 'Cantidad de dormitorios: 2', que es otro campo.

    O sea: no hay un tercer arreglo. Hay un arreglo -precio y moneda, misma
    causa- y un error de medición. Sumar los tres campos habría prometido un
    ROI que no existe.
    """
    assert "monoambiente" in texto.lower()
    assert "cantidad de dormitorios: 2" in texto.lower()
    # Ni una sola aparición de "N ambientes" como atributo de la propiedad.
    assert not re.search(r"\b\d+\s*ambientes?\b", texto, re.I)
