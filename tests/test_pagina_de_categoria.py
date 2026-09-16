# -*- coding: utf-8 -*-
"""Una vista filtrada del catálogo no es una propiedad.

**Rojo a propósito. El arreglo NO está aplicado.** Va aparte del arreglo de
`operacion` porque **no comparten causa**: uno es de dónde se lee un campo, el
otro es qué se admite como ficha. Unirlos ataría dos radios de dependencia
distintos a un solo despliegue.

EL DEFECTO, medido el 2026-09-15 sobre `fenix inmobiliaria`: el sitemap publica
502 urls y **3 no son fichas** sino vistas filtradas del catálogo:

    /propiedades/venta-casas-posadas/
    /propiedades/alquiler-departamentos-posadas/
    /propiedades/venta-terrenos-misiones/

Las tres entraron al inventario como si fueran propiedades. Y la segunda
—una url de ALQUILER— quedó clasificada como `venta`, que es un error que ve
el usuario final.

LA REGLA, y por qué son cuatro condiciones y no una. Se midió cada versión
contra las 378 agencias certificadas:

    titulo compartido + sin precio                   -> 396 paginas marcadas
    + url sin id numerico                            -> 395
    + el titulo es el INSTITUCIONAL del sitio        ->   8

Las primeras dos versiones marcaban fichas duplicadas legítimas: la misma
propiedad publicada dos veces tiene título repetido y a veces no trae precio.
Lo que separa a una vista filtrada es que su título es el del **sitio**
—"Fénix Inmobiliaria en Posadas | Ventas y Alquileres"— y no el de una
propiedad.

Las 8 que quedan se revisaron una por una contra la fuente: las 3 de fenix son
vistas filtradas; 3 de `baron` son emprendimientos —"Disponibilidad Unidades"—
y 2 de `brunetti` son barrios privados —"Últimos lotes disponibles"—. Las ocho
son páginas contenedoras y ninguna tiene precio propio. No se detectó ningún
falso positivo, pero la muestra es de ocho: la regla marca para revisión, no
descarta en silencio.
"""
import re
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
CATEGORIA = FIXTURES / "pagina_de_categoria.html"
FICHA = FIXTURES / "operacion_solo_en_title.html"

RE_PRECIO = re.compile(r"(?i)(?:USD|U\$S|US\$|ARS|\$)\s?[\d][\d.,]{2,}")
RE_ID = re.compile(r"/\d{3,}/?$")
RE_TIPO = re.compile(r"(?i)\b(casas?|departamentos?|terrenos?|lotes?|locales?|"
                     r"oficinas?|cocheras?|galp[oó]n|ph|quinta|campo|duplex|"
                     r"chalet|monoambiente)\b")


def titulo(html: str) -> str:
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def es_pagina_contenedora(html: str, url: str, nombre_agencia: str,
                          titulos_de_la_agencia: list[str]) -> bool:
    """Las cuatro condiciones, juntas. Ninguna alcanza sola."""
    t = titulo(html)
    if not t:
        return False
    compartido = titulos_de_la_agencia.count(t) >= 3
    institucional = (any(p in t.lower() for p in nombre_agencia.lower().split()
                         if len(p) >= 4)
                     and not RE_TIPO.search(t))
    sin_precio = not RE_PRECIO.search(re.sub(r"(?s)<[^>]+>", " ", html))
    sin_id = not RE_ID.search(url)
    return compartido and institucional and sin_precio and sin_id


@pytest.fixture
def categoria() -> str:
    return CATEGORIA.read_text(encoding="utf-8")


@pytest.fixture
def ficha() -> str:
    return FICHA.read_text(encoding="utf-8")


# --- que cada condición hace falta, una por una -------------------------

def test_el_titulo_de_la_categoria_es_el_del_sitio(categoria):
    assert titulo(categoria) == "Inmobiliaria Ejemplo en Ciudad | Ventas y Alquileres"
    assert not RE_TIPO.search(titulo(categoria))


def test_el_titulo_de_la_ficha_es_de_una_propiedad(ficha):
    assert RE_TIPO.search(titulo(ficha)), "dice 'Departamento'"


def test_la_categoria_no_tiene_precio_propio(categoria):
    assert not RE_PRECIO.search(re.sub(r"(?s)<[^>]+>", " ", categoria))


def test_la_ficha_si_tiene_precio(ficha):
    assert RE_PRECIO.search(re.sub(r"(?s)<[^>]+>", " ", ficha))


# --- la regla completa --------------------------------------------------

def test_la_regla_marca_la_categoria(categoria):
    compartidos = ["Inmobiliaria Ejemplo en Ciudad | Ventas y Alquileres"] * 3
    assert es_pagina_contenedora(
        categoria, "https://ejemplo.test/propiedades/venta-casas-ciudad/",
        "Inmobiliaria Ejemplo", compartidos) is True


def test_la_regla_NO_marca_una_ficha_de_verdad(ficha):
    assert es_pagina_contenedora(
        ficha, "https://ejemplo.test/propiedades/4750557/",
        "Inmobiliaria Ejemplo", [titulo(ficha)]) is False


def test_una_ficha_duplicada_no_se_marca_por_repetirse(ficha):
    """El caso que rompía las versiones anteriores de la regla.

    Una propiedad publicada tres veces tiene el título repetido, pero su
    título es el de una propiedad, no el del sitio. Con la regla de tres
    condiciones se marcaban 395 páginas casi todas así.
    """
    tres_veces = [titulo(ficha)] * 3
    assert es_pagina_contenedora(
        ficha, "https://ejemplo.test/propiedades/casa-en-venta-ejemplo",
        "Inmobiliaria Ejemplo", tres_veces) is False


# --- el rojo ------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason="defecto abierto: el enumerador admite "
                                       "vistas filtradas como si fueran fichas")
def test_ROJO_una_url_de_alquiler_no_puede_quedar_como_venta():
    """El desenlace concreto que se vio en producción.

    `/propiedades/alquiler-departamentos-posadas/` entró al inventario con
    `operacion = venta`. Hoy nada lo impide: la url no se examina antes de
    aceptarla como ficha.
    """
    url = "https://ejemplo.test/propiedades/alquiler-departamentos-ciudad/"
    operacion_asignada = "venta"          # lo que paso de verdad
    es_categoria = False                  # <-- hoy nadie lo pregunta
    assert es_categoria or "alquiler" not in url, (
        f"una url de alquiler entro como {operacion_asignada}")
