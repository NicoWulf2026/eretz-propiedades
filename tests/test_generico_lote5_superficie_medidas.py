"""Lote 5: una medida lineal (frente x fondo) no es una superficie.

Medido en LOCAL el 2026-10-01 sobre los paquetes certificados: 11 fichas de 10
agencias guardaban el frente o el fondo como superficie_total/cubierta.
`fenix` 4741529 ('Medidas del terreno: 22m frente x 65m fondo') tenia
superficie_total=22 en un lote que la propia pagina resume como 1.430 m2.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from connectors.generico import ETIQUETA_SUP_CUBIERTA, ETIQUETA_SUP_TOTAL, GenericoConnector as G

FIXTURES = Path(__file__).parent / "fixtures" / "cloud_bridge" / "fenix"


@pytest.mark.parametrize("texto", [
    "Medidas del terreno: 22m frente x 65m fondo aprox.",
    "Terreno de 14,36 mts de frente por 58,40 de fondo",
    "Lote 12 m de frente por 31 de fondo",
    "Terreno 40 mts de frente x 60 mts",
    "terreno de 8.66 metros de frente por 25",
    "Terreno 127 m x 50 m",
])
def test_frente_por_fondo_no_es_superficie(texto):
    assert G._sup(texto, ETIQUETA_SUP_TOTAL) is None


@pytest.mark.parametrize("texto,etiqueta,valor", [
    ("Superficie total 300 metros cuadrados", ETIQUETA_SUP_TOTAL, 300),
    ("Terreno: 450 m2", ETIQUETA_SUP_TOTAL, 450),
    ("Sup. total 1.430 m² - cubierta 280 m²", ETIQUETA_SUP_CUBIERTA, 280),
    ("Son 110m2 totales, 94m2 cub", ETIQUETA_SUP_TOTAL, 110),
])
def test_las_superficies_de_siempre_se_siguen_leyendo(texto, etiqueta, valor):
    assert G._sup(texto, etiqueta) == valor


def test_fixture_real_de_fenix_no_guarda_el_frente_como_superficie():
    from connectors.base import Fuente
    html = (FIXTURES / "ficha_frente_por_fondo.html").read_text(encoding="utf-8")

    class Fijo:
        def bajar(self, *a, **k):
            return html

        def __getattr__(self, nombre):
            return lambda *a, **k: None

    url = "https://www.fenixxweb.com/propiedades/4741529/"
    p = G(descargador=Fijo()).normalize(
        {"source_url": url, "source_listing_id": "4741529"},
        Fuente(canonical_agency_id="roomix:fenix inmobiliaria", agency_name="Fenix",
               official_url="https://www.fenixxweb.com/"))
    assert p is None or p.superficie_total != 22
