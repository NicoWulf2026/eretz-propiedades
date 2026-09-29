"""Una URL de categoria no se enumera como ficha (calzetta, civeira, pagano, perla)."""
from __future__ import annotations

import pytest

from connectors.generico import es_url_de_categoria


@pytest.mark.parametrize("url", [
    "https://calzettapropiedades.com/propiedades/lotes_venta_lomas-de-zamora",
    "https://pfpropiedades.com.ar/propiedades/casas_venta_lomas-de-zamora",
    "https://civeirabienesraices.com.ar/propiedades/venta_destacadas",
    "https://www.paganopropiedades.com.ar/venta/casas",
    "https://www.paganopropiedades.com.ar/alquiler/departamentos/",
])
def test_categorias(url):
    assert es_url_de_categoria(url)


@pytest.mark.parametrize("url", [
    # Fichas reales que nombran tipo y operacion en el slug.
    "https://blancopropiedades.com/propiedades/venta-de-casa-en-la-peregrina",
    "https://baroneinmobiliaria.com.ar/propiedad/lotes-en-venta-navarro/",
    "https://nextinmobiliaria.com.ar/propiedades/alquiler-de-local-comercial-y-galpon-en-rosario/",
    # Categoria, pero fuera de la forma estricta: la cubre el detector de
    # paginas contenedoras (encabezado «Casas en venta» + grilla).
    "https://www.fenixxweb.com/propiedades/venta-casas-posadas/",
    # Con id: es una ficha aunque la ruta parezca categoria.
    "https://www.paganopropiedades.com.ar/venta/casas/1234",
    "https://calzettapropiedades.com/propiedades/casas_venta_lomas?id=55",
])
def test_fichas_no_son_categoria(url):
    assert not es_url_de_categoria(url)


@pytest.mark.parametrize("url", [
    "https://peiranopropiedades.com.ar/category/propiedades/3-amb-con-dep/",
    "https://peiranopropiedades.com.ar/tag/monoambientes-en-alquiler-en-barrio-norte/",
])
def test_archivos_de_taxonomia_de_wordpress(url):
    assert es_url_de_categoria(url)
