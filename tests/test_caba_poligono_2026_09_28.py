"""CABA + provincia «Buenos Aires»: solo la contencion en el poligono oficial desempata.

Medido el 28-09 sobre los paquetes: 99 fichas (blanco 63 sin coordenadas,
cantale 34, agostinelli 2) nombran CABA con provincia «Buenos Aires». Con el
poligono del IGN se recuperan 32; las 4 de cantale con coordenadas en Parana,
La Matanza y Mendoza siguen en conflicto, y las 63 sin coordenadas tambien.
"""
from __future__ import annotations

import pytest

from connectors import poligono_caba
from connectors.geografia import (CABA_POR_POLIGONO_REASON, CONTRADICHA,
                                  DIRECTORIO_POR_DEFECTO, POR_COORDENADA,
                                  Geografia)
from connectors.poligono_caba import DENTRO, FRONTERA, FUERA, contencion

OBELISCO = (-34.6037, -58.3816)
LINIERS = (-34.6420, -58.5230)          # CABA, a ~600 m de la General Paz
AVELLANEDA = (-34.6625, -58.3650)       # GBA, a ~1 km del Riachuelo
CIUDADELA = (-34.6350, -58.5370)        # GBA, del otro lado de la General Paz
QUILMES = (-34.7206, -58.2546)
VICENTE_LOPEZ = (-34.5270, -58.4750)

requiere_georef = pytest.mark.skipif(
    not (DIRECTORIO_POR_DEFECTO / "localidades_censales.json").exists(),
    reason="falta el snapshot de GeoRef; se baja con scripts/geo_snapshot.py")


def test_la_geometria_es_la_oficial_y_trae_su_procedencia() -> None:
    procedencia = poligono_caba.procedencia()
    assert procedencia["fuente"].startswith("Instituto Geografico Nacional")
    assert "27.275" in procedencia["licencia"]
    assert procedencia["vertices"] == 1024
    assert len(procedencia["sha256_coordenadas"]) == 64


@pytest.mark.parametrize("punto", [OBELISCO, LINIERS])
def test_dentro_de_caba(punto) -> None:
    assert contencion(*punto) == DENTRO


@pytest.mark.parametrize("punto", [AVELLANEDA, CIUDADELA, QUILMES, VICENTE_LOPEZ])
def test_fuera_en_el_conurbano_cercano(punto) -> None:
    assert contencion(*punto) == FUERA


def test_sobre_el_limite_no_se_afirma_nada() -> None:
    anillos, _ = poligono_caba._cargar()
    lon, lat = anillos[0][100]
    assert contencion(lat, lon) == FRONTERA
    # 50 m al norte de un vertice sigue dentro del margen.
    assert contencion(lat + 50 / 111_320, lon) == FRONTERA


@pytest.mark.parametrize("lat,lon", [(None, None), ("", ""), (float("nan"), -58.4),
                                     ("x", -58.4)])
def test_sin_coordenadas_no_hay_veredicto(lat, lon) -> None:
    assert contencion(lat, lon) is None


def test_sin_geometria_no_hay_veredicto(tmp_path) -> None:
    assert contencion(*OBELISCO, ruta=tmp_path / "no_existe.geojson") is None


@pytest.fixture(scope="module")
def geo() -> Geografia:
    return Geografia()


@requiere_georef
@pytest.mark.parametrize("ciudad", ["CABA", "Capital Federal"])
def test_caba_con_buenos_aires_y_coordenada_adentro_se_resuelve(geo, ciudad) -> None:
    r = geo.resolver_localidad(ciudad, provincia="Buenos Aires",
                               lat=OBELISCO[0], lon=OBELISCO[1])
    assert r.entidad is not None
    assert r.entidad.official_name == "Ciudad Autónoma de Buenos Aires"
    assert r.certeza == POR_COORDENADA
    assert r.motivo == CABA_POR_POLIGONO_REASON


@requiere_georef
@pytest.mark.parametrize("punto", [AVELLANEDA, CIUDADELA, QUILMES, None])
def test_caba_con_buenos_aires_sin_contencion_sigue_contradicha(geo, punto) -> None:
    lat, lon = punto if punto else (None, None)
    r = geo.resolver_localidad("CABA", provincia="Buenos Aires", lat=lat, lon=lon)
    assert r.entidad is None
    assert r.certeza == CONTRADICHA


@requiere_georef
def test_caba_sobre_la_frontera_sigue_contradicha(geo) -> None:
    # Un vertice del limite TERRESTRE con Buenos Aires (General Paz /
    # Riachuelo), no de la costa: desde P10 (2026-10-01) la costa no hace dudar
    # entre provincias, el limite con otra provincia si.
    from connectors import poligono_provincia as P
    anillos, _ = poligono_caba._cargar()
    pc, _, _ = P._cargar(str(P.GEOMETRIA))
    terrestre = next((x, y) for x, y in anillos[0]
                     if P._distancia_al_borde_km(pc["06"]["anillos"], x, y) < 0.5)
    lon, lat = terrestre
    r = geo.resolver_localidad("CABA", provincia="Buenos Aires", lat=lat, lon=lon)
    assert r.certeza == CONTRADICHA


@requiere_georef
def test_otra_provincia_no_se_desempata_aunque_la_coordenada_este_en_caba(geo) -> None:
    # Lejos del Obelisco (Rosario): ni la regla CABA ni P10 afirman CABA.
    r = geo.resolver_localidad("CABA", provincia="Santa Fe", lat=-32.9442, lon=-60.6505)
    assert r.entidad is None and r.certeza == CONTRADICHA
    # En el Obelisco, P10 (localidad unica + coordenada en su poligono, lejos de
    # otra provincia) prevalece sobre la provincia publicada (2026-10-01).
    r = geo.resolver_localidad("CABA", provincia="Santa Fe", lat=OBELISCO[0], lon=OBELISCO[1])
    assert r.entidad is not None and r.entidad.official_id == "02"


def _propiedad(**campos):
    from connectors.base import PropiedadNormalizada

    base = {"canonical_agency_id": "roomix:x", "source_listing_id": "1",
            "source_url": "https://x.test/p/1", "connector": "generico"}
    return PropiedadNormalizada(**{**base, **campos})


@requiere_georef
def test_el_pipeline_afirma_caba_y_conserva_la_provincia_publicada() -> None:
    from connectors.base import Connector
    prop = _propiedad(ciudad="Capital Federal", provincia="Buenos Aires",
                      latitud=LINIERS[0], longitud=LINIERS[1])
    Connector._resolver_geografia(prop)
    assert prop.ciudad == "Ciudad Autónoma de Buenos Aires"
    assert prop.provincia == "Ciudad Autónoma de Buenos Aires"
    assert prop.extra["provincia_publicada"] == "Buenos Aires"
    assert prop.extra["provincia_por_poligono"]["geometria"]["vertices"] == 1024
    assert "geo_conflicto" not in prop.extra
    assert prop.geo.get("estado_geografico") != "GEO_CONFLICT"


@requiere_georef
def test_el_pipeline_mantiene_el_conflicto_en_quilmes() -> None:
    from connectors.base import Connector
    prop = _propiedad(ciudad="CABA", provincia="Buenos Aires",
                      latitud=QUILMES[0], longitud=QUILMES[1])
    Connector._resolver_geografia(prop)
    assert prop.ciudad is None and prop.provincia is None
    assert prop.latitud == QUILMES[0]
    assert prop.geo["estado_geografico"] == "GEO_CONFLICT"
