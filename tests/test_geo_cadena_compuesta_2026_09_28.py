"""Ubicacion publicada como cadena jerarquica: «Parte, Parte, Partido, Region».

Medido el 28-09 sobre los paquetes: 824 fichas sin ciudad con una cadena con
comas; 628 resuelven (ferrari 152 «Rosario, Santa Fe», blanco 133 «NORDELTA /
VILLANUEVA, TIGRE», d'aria 129 GBA Norte, lucero 76 «Morón, Bs.As. G.B.A.
Oeste»...). El catalogo del INDEC agrupa el GBA por partido.
"""
from __future__ import annotations

import pytest

from connectors.geografia import DIRECTORIO_POR_DEFECTO, geografia

pytestmark = pytest.mark.skipif(
    not (DIRECTORIO_POR_DEFECTO / "localidades_censales.json").exists(),
    reason="falta el snapshot de GeoRef; se baja con scripts/geo_snapshot.py")


@pytest.mark.parametrize("texto,provincia,localidad,barrio", [
    ("Rosario, Santa Fe", None, "Rosario", None),
    ("Córdoba, Córdoba", "Córdoba", "Córdoba", None),
    ("Morón, Bs.As. G.B.A. Oeste", "Buenos Aires", "Morón", None),
    ("Olivos, Vicente López, G.B.A. Zona Norte", "Buenos Aires", "Vicente López", "Olivos"),
    ("Libertador al Río, La Lucila, Vicente López, G.B.A. Zona Norte", "Buenos Aires",
     "Vicente López", "La Lucila"),
    ("NORDELTA, TIGRE", "Buenos Aires", "Tigre", "NORDELTA"),
    ("NORDELTA, TIGRE", None, "Tigre", "NORDELTA"),
    ("Vias a Libertador, San Isidro, San Isidro, G.B.A. Zona Norte", "Buenos Aires", "San Isidro", None),
    ("Bolla al 1400, Roque Perez", None, "Roque Pérez", None),
])
def test_la_localidad_que_la_cadena_nombra(texto, provincia, localidad, barrio) -> None:
    r, b = geografia().resolver_compuesta(texto, provincia=provincia)
    assert r.entidad.official_name == localidad
    assert b == barrio


def test_la_provincia_de_la_cadena_no_puede_contradecir_la_declarada() -> None:
    assert geografia().resolver_compuesta("Rosario, Santa Fe", provincia="Mendoza") is None


def test_un_departamento_no_se_toma_por_localidad() -> None:
    assert geografia().resolver_compuesta("Colón, Córdoba", provincia="Córdoba") is None


def test_caba_con_barrio_sin_coordenada_y_provincia_contradictoria_no_afirma() -> None:
    assert geografia().resolver_compuesta("Belgrano, CABA", provincia="Buenos Aires") is None
    r, b = geografia().resolver_compuesta("Belgrano, CABA")
    assert r.entidad.official_name == "Ciudad Autónoma de Buenos Aires" and b == "Belgrano"


def test_el_pipeline_escribe_ciudad_y_barrio() -> None:
    from connectors.base import Connector, PropiedadNormalizada
    prop = PropiedadNormalizada(canonical_agency_id="roomix:x", source_listing_id="1",
                                source_url="https://x.test/p/1", connector="generico",
                                barrio="Olivos, Vicente López, G.B.A. Zona Norte",
                                provincia="Buenos Aires")
    Connector._resolver_geografia(prop)
    assert prop.ciudad == "Vicente López" and prop.barrio == "Olivos"
    assert prop.provincia == "Buenos Aires"
    assert prop.extra["ciudad_de_cadena_compuesta"].startswith("Olivos")
