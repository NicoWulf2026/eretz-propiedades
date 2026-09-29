"""Exterior por contencion en el poligono oficial del pais (IGN `ign:pais`).

La caja de coordenadas vieja (-74..-53) cubria Uruguay entero: la v4j servida
publicaba 116 fichas con coordenadas en Uruguay (115) y Paraguay (1) -`enlaze`
«Centro (Montevideo)», `lopez baena` y `farina` en Punta del Este-, ninguna en
el agua. Y sin coordenada, Miami por barrio o por titulo con «Florida».
"""
from __future__ import annotations

import pytest

from connectors import pais
from connectors.exterior import evidencia_de_exterior
from connectors.pais import DENTRO, FRONTERA, FUERA, contencion


def test_la_geometria_es_la_oficial_y_trae_su_procedencia() -> None:
    p = pais.procedencia()
    assert p["fuente"].startswith("Instituto Geografico Nacional")
    assert "27.275" in p["licencia"] and p["poligonos"] > 1000


@pytest.mark.parametrize("punto", [(-32.9468, -60.6393), (-41.1335, -71.3103),
                                   (-34.35, -58.55), (-34.20, -58.75)])
def test_argentina_y_el_delta_quedan_adentro(punto) -> None:
    assert contencion(*punto) == DENTRO


@pytest.mark.parametrize("punto", [(-34.6037, -58.3816), (-54.8019, -68.3030),
                                   (-27.3671, -55.8961), (-38.0055, -57.5426)])
def test_la_costa_y_las_fronteras_no_afirman_nada(punto) -> None:
    assert contencion(*punto) in (DENTRO, FRONTERA)


@pytest.mark.parametrize("punto", [(-34.9011, -56.1645), (-34.9620, -54.9431),
                                   (-25.2637, -57.5759), (-33.4489, -70.6693),
                                   (-26.9906, -48.6348), (25.7617, -80.1918)])
def test_los_paises_vecinos_quedan_afuera(punto) -> None:
    assert contencion(*punto) == FUERA


@pytest.mark.parametrize("lat,lon", [(None, None), ("", -58.4), ("x", "y"), (float("nan"), -58.4)])
def test_sin_coordenada_no_hay_veredicto(lat, lon) -> None:
    assert contencion(lat, lon) is None


def test_una_coordenada_en_uruguay_es_evidencia_de_exterior() -> None:
    e = evidencia_de_exterior(titulo="Departamento en Venta en Centro (Montevideo) - Gala Rock",
                              lat=-34.907442, lon=-56.1977419)
    assert e["pais"] == "UY" and "IGN" in e["evidencia"]
    sin_nombre = evidencia_de_exterior(titulo="Terreno con vista a la laguna",
                                       lat=-34.9200, lon=-54.9261)
    assert sin_nombre is not None and sin_nombre["pais"] is None


def test_la_calle_montevideo_de_rosario_no_es_exterior() -> None:
    assert evidencia_de_exterior(titulo="Departamento en Venta en Centro - Montevideo 961",
                                 lat=-32.9468, lon=-60.6393) is None


def test_miami_sin_coordenada_por_barrio_o_por_titulo_con_florida() -> None:
    no_es_argentina = lambda _t: False  # noqa: E731
    assert evidencia_de_exterior(barrio="Brickell", es_localidad_argentina=no_es_argentina)["pais"] == "US"
    assert evidencia_de_exterior(barrio="Miami-dade", es_localidad_argentina=no_es_argentina)["pais"] == "US"
    assert evidencia_de_exterior(titulo="Casa Dúplex en Venta. Miramar, Miami, Florida")["pais"] == "US"
    # «Florida» sola sigue siendo Vicente Lopez.
    assert evidencia_de_exterior(titulo="Casa en venta en Florida, Vicente Lopez") is None


def test_la_snapshot_no_sirve_una_fila_con_coordenada_en_uruguay() -> None:
    from scripts.api_snapshot import _publicable_en_argentina
    fila = {"titulo": "Departamento en Venta en Playa Brava", "latitud": -34.9445, "longitud": -54.9164}
    assert not _publicable_en_argentina(fila, None)
    assert _publicable_en_argentina({"titulo": "Depto", "latitud": -32.9468, "longitud": -60.6393}, None)
