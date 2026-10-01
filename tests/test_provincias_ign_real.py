"""La geometria oficial del IGN (`connectors/geometria/provincias_ign.json`) que usa P10.

Generada en LOCAL con `scripts/geo_poligonos_provincias.py` (WFS `ign:provincia`,
Ley 27.275) el 2026-10-01. Estos tests validan el archivo versionado, no la red.
"""
from __future__ import annotations

import json

import pytest

from connectors import poligono_provincia as P

pytestmark = pytest.mark.skipif(not P.GEOMETRIA.exists(), reason="sin provincias_ign.json")

INDEC = ["02", "06", "10", "14", "18", "22", "26", "30", "34", "38", "42", "46",
         "50", "54", "58", "62", "66", "70", "74", "78", "82", "86", "90", "94"]

# (nombre, lat, lon, codigo INDEC esperado). Varios estan a menos de 2 km de la
# costa o de un rio limitrofe: por eso se consulta con un margen chico.
PUNTOS = [
    ("Obelisco, CABA", -34.6037, -58.3816, "02"),
    ("La Plata", -34.9214, -57.9545, "06"),
    ("Mar del Plata", -38.0055, -57.5426, "06"),
    ("Santa Clara del Mar", -37.8370, -57.5050, "06"),
    ("Isla Martin Garcia", -34.1833, -58.2500, "06"),
    ("Cordoba", -31.4201, -64.1888, "14"),
    ("Rosario", -32.9442, -60.6505, "82"),
    ("Parana", -31.7319, -60.5238, "30"),
    ("Mendoza", -32.8895, -68.8458, "50"),
    ("Neuquen", -38.9516, -68.0591, "58"),
    ("Cipolletti", -38.9339, -67.9903, "62"),
    ("Posadas", -27.3671, -55.8961, "54"),
    ("Puerto Madryn", -42.7692, -65.0385, "26"),
    ("Ushuaia", -54.8019, -68.3030, "94"),
    ("Puerto Argentino, Malvinas", -51.6977, -57.8517, "94"),
]


def test_las_24_jurisdicciones_por_codigo_indec():
    datos = json.loads(P.GEOMETRIA.read_text(encoding="utf-8"))
    assert sorted(datos["provincias"]) == INDEC
    procedencia = datos["procedencia"]
    assert "IGN" in procedencia["fuente"] and procedencia["jurisdicciones"] == 24
    assert procedencia["sha256_origen"]


def test_las_islas_son_de_su_provincia():
    datos = json.loads(P.GEOMETRIA.read_text(encoding="utf-8"))
    # Tierra del Fuego (Malvinas, Isla de los Estados), Chubut y Santa Cruz (islas
    # costeras), Buenos Aires (delta, Martin Garcia): ninguna se descarta por chica.
    for codigo, minimo in (("94", 100), ("06", 10), ("26", 10), ("78", 10)):
        assert len(datos["provincias"][codigo]["poligonos"]) >= minimo


@pytest.mark.parametrize("nombre,lat,lon,codigo", PUNTOS, ids=[p[0] for p in PUNTOS])
def test_cada_ciudad_cae_en_su_provincia(nombre, lat, lon, codigo):
    assert P.provincia_que_contiene(lat, lon, margen_km=0.1) == codigo


@pytest.mark.parametrize("lat,lon", [(-34.9011, -56.1645), (-33.4489, -70.6693), (-25.2637, -57.5759)],
                         ids=["Montevideo", "Santiago de Chile", "Asuncion"])
def test_lo_de_afuera_no_es_de_ninguna(lat, lon):
    assert P.provincia_que_contiene(lat, lon, margen_km=0.1) is None


def test_con_el_margen_de_p10_la_costa_cuenta_como_borde():
    """Medido 2026-10-01: el margen de 2 km se mide contra TODO borde, costa incluida.

    Mar del Plata (0,76 km de la costa en la geometria simplificada) queda en
    FRONTERA y P10 no afirma. Es fail-closed; ver el radio de P10 en el README de lotes.
    """
    assert P.contencion("06", -38.0055, -57.5426) == P.FRONTERA
