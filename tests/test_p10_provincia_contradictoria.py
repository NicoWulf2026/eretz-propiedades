"""P10: provincia publicada contradictoria, normalizada por localidad unica + poligono oficial.

Corre SIN el GeoRef privado: arma un catalogo GeoRef minimo SINTETICO (con su
manifiesto verificado, igual que el real) y una geometria SINTETICA de
provincias. Prueba la regla, no los datos: el radio real lo mide LOCAL.

El caso que la motiva: `analia requena` publica «Santa Clara del Mar» con
provincia «Ciudad Autonoma de Buenos Aires» (valor de plantilla) y coordenadas
correctas; 107 de 152 fichas quedaban sin geografia.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from connectors import poligono_provincia as P
from connectors.geografia import (PROVINCE_CONFLICT_REASON,
                                  PROVINCIA_POR_POLIGONO_REASON, Geografia)

SANTA_CLARA = (-37.8326665, -57.4969484)


def _manifiesto(directorio, recursos):
    registro = {}
    for recurso, filas in recursos.items():
        archivo = recurso.replace("-", "_") + ".json"
        crudo = json.dumps(filas, ensure_ascii=False).encode("utf-8")
        (directorio / archivo).write_bytes(crudo)
        registro[recurso] = {"archivo": archivo, "total_declarado": len(filas),
                             "filas_traidas": len(filas), "completo": True,
                             "sha256": hashlib.sha256(crudo).hexdigest()}
    (directorio / "MANIFEST.json").write_text(json.dumps(
        {"schema_version": 2, "sha256_scope": "file_bytes_utf8_lf", "recursos": registro}),
        encoding="utf-8")


def _loc(id_, nombre, prov_id, prov, depto, lat, lon):
    return {"id": id_, "nombre": nombre, "provincia": {"id": prov_id, "nombre": prov},
            "departamento": {"id": id_[:5], "nombre": depto}, "municipio": None,
            "centroide": {"lat": lat, "lon": lon}}


@pytest.fixture()
def geo(tmp_path, monkeypatch):
    d = tmp_path / "georef"
    d.mkdir()
    _manifiesto(d, {
        "provincias": [
            {"id": "02", "nombre": "Ciudad Autónoma de Buenos Aires", "centroide": {"lat": -34.61, "lon": -58.44}},
            {"id": "06", "nombre": "Buenos Aires", "centroide": {"lat": -36.68, "lon": -60.56}},
            {"id": "30", "nombre": "Entre Ríos", "centroide": {"lat": -32.06, "lon": -59.2}},
            {"id": "54", "nombre": "Misiones", "centroide": {"lat": -26.88, "lon": -54.65}},
        ],
        "localidades-censales": [
            _loc("06357080", "Santa Clara del Mar", "06", "Buenos Aires", "Mar Chiquita", *SANTA_CLARA),
            # «Colón» existe en dos provincias: nunca se infiere la provincia de un nombre ambiguo.
            _loc("06175010", "Colón", "06", "Buenos Aires", "Colón", -33.8953, -61.1045),
            _loc("30008010", "Colón", "30", "Entre Ríos", "Colón", -32.2233, -58.1428),
            _loc("54028010", "Posadas", "54", "Misiones", "Capital", -27.3671, -55.8961),
            # Sintetica: una localidad de Buenos Aires pegada a la caja de Entre Rios.
            _loc("06999010", "Villa Prueba Limite", "06", "Buenos Aires", "Prueba", -34.03, -60.0),
        ],
    })
    # Geometria SINTETICA: cajas que contienen a cada localidad, no el IGN.
    caja = lambda x0, y0, x1, y1: [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]  # noqa: E731
    ruta = tmp_path / "provincias_ign.json"
    ruta.write_text(json.dumps({"procedencia": {"fuente": "SINTETICA", "vertices": 20, "sha256_origen": "x"},
                                "provincias": {
                                    "02": {"nombre": "Ciudad Autónoma de Buenos Aires", "poligonos": [caja(-58.55, -34.72, -58.33, -34.52)]},
                                    "06": {"nombre": "Buenos Aires", "poligonos": [caja(-63.0, -41.0, -57.45, -33.2)]},
                                    "30": {"nombre": "Entre Ríos", "poligonos": [caja(-60.8, -34.0, -57.8, -30.1)]},
                                    "54": {"nombre": "Misiones", "poligonos": [caja(-56.1, -28.2, -53.6, -25.5)]},
                                }}), encoding="utf-8")
    monkeypatch.setattr(P, "GEOMETRIA", ruta)
    P._cargar.cache_clear()
    yield Geografia(d)
    P._cargar.cache_clear()


def test_localidad_unica_y_coordenada_en_su_provincia_prevalecen(geo):
    r = geo.resolver_localidad("Santa Clara del Mar", provincia="Ciudad Autónoma de Buenos Aires",
                               lat=SANTA_CLARA[0], lon=SANTA_CLARA[1])
    assert r.resuelta and r.entidad.provincia == "Buenos Aires"
    assert r.motivo == PROVINCIA_POR_POLIGONO_REASON


def test_sin_coordenada_sigue_el_conflicto(geo):
    r = geo.resolver_localidad("Santa Clara del Mar", provincia="Misiones")
    assert not r.resuelta and r.motivo == PROVINCE_CONFLICT_REASON


def test_coordenada_en_otra_provincia_sigue_el_conflicto(geo):
    r = geo.resolver_localidad("Santa Clara del Mar", provincia="Misiones", lat=-27.37, lon=-55.9)
    assert not r.resuelta and r.motivo == PROVINCE_CONFLICT_REASON


def test_coordenada_en_la_provincia_pero_lejos_de_la_localidad_sigue_el_conflicto(geo):
    # Dentro de la caja «Buenos Aires» pero a >100 km de Santa Clara del Mar.
    r = geo.resolver_localidad("Santa Clara del Mar", provincia="Misiones", lat=-34.0, lon=-61.0)
    assert not r.resuelta and r.motivo == PROVINCE_CONFLICT_REASON


def test_coordenada_sobre_el_limite_no_afirma(geo):
    # A ~1 km del limite con Entre Rios (la caja de ER empieza en lat -34.0): FRONTERA.
    r = geo.resolver_localidad("Villa Prueba Limite", provincia="Misiones",
                               lat=-34.0 - 1.0 / 111.32, lon=-60.0)
    assert not r.resuelta


def test_junto_a_la_costa_si_afirma(geo):
    # A ~1 km del borde este de la caja de Buenos Aires (el mar en la sintetica,
    # a ~4 km de Santa Clara como en la realidad):
    # la costa no hace dudar entre provincias (2026-10-01, `analia requena`).
    r = geo.resolver_localidad("Santa Clara del Mar", provincia="Misiones",
                               lat=-37.83, lon=-57.45 - 1.0 / (111.32 * 0.79))
    assert r.resuelta


def test_un_nombre_ambiguo_nunca_decide_la_provincia(geo):
    r = geo.resolver_localidad("Colón", provincia="Misiones", lat=-32.2233, lon=-58.1428)
    assert not r.resuelta and r.motivo == PROVINCE_CONFLICT_REASON


def test_sin_geometria_p10_no_actua(geo, monkeypatch, tmp_path):
    monkeypatch.setattr(P, "GEOMETRIA", tmp_path / "no_existe.json")
    P._cargar.cache_clear()
    r = geo.resolver_localidad("Santa Clara del Mar", provincia="Ciudad Autónoma de Buenos Aires",
                               lat=SANTA_CLARA[0], lon=SANTA_CLARA[1])
    assert not r.resuelta and r.motivo == PROVINCE_CONFLICT_REASON


def test_la_extraccion_conserva_la_provincia_publicada_como_evidencia(geo, monkeypatch):
    from connectors import base
    from connectors.base import Connector, PropiedadNormalizada
    monkeypatch.setattr(base, "geografia", lambda *a, **k: geo)
    p = PropiedadNormalizada(canonical_agency_id="roomix:alfa", source_listing_id="1",
                             source_url="https://alfa.com.ar/p/1", connector="generico",
                             ciudad="Santa Clara del Mar",
                             provincia="Ciudad Autónoma de Buenos Aires",
                             latitud=SANTA_CLARA[0], longitud=SANTA_CLARA[1])
    Connector._resolver_geografia(p)
    assert p.ciudad == "Santa Clara del Mar" and p.provincia == "Buenos Aires"
    assert p.latitud == SANTA_CLARA[0]
    assert "geo_conflicto" not in p.extra
    assert p.extra["provincia_publicada"] == "Ciudad Autónoma de Buenos Aires"
    evidencia = p.extra["provincia_por_poligono"]
    assert evidencia["politica"] == "P10" and evidencia["provincia"] == "Buenos Aires"
    assert evidencia["evidencia"]["localidad_id"] == "06357080"
    assert evidencia["geometria"]["fuente"] == "SINTETICA"


def test_la_snapshot_levanta_un_conflicto_viejo_que_hoy_es_p10(geo, monkeypatch):
    from scripts import api_snapshot as S
    monkeypatch.setattr(S, "geografia", lambda *a, **k: geo)
    conflicto = {"publicado": {"provincia": "Ciudad Autónoma de Buenos Aires",
                               "localidad": "Santa Clara del Mar",
                               "latitud": SANTA_CLARA[0], "longitud": SANTA_CLARA[1]}}
    g, motivo = S._geo_de_la_extraccion({"estado_geografico": "GEO_CONFLICT"},
                                        {"extra": {"geo_conflicto": conflicto}})
    assert motivo == "provincia_por_poligono"
    assert g["estado_geografico"] is None and g["provincia_canonica"] == "Buenos Aires"
    assert g["localidad_canonica"] == "Santa Clara del Mar"
    assert g["area_busqueda"]["nivel"] == "LOCALIDAD"
    assert g["provincia_publicada_en_conflicto"] == "Ciudad Autónoma de Buenos Aires"
    assert g["procedencia_de_dimensiones"]["provincia"] == "GEO_GEOMETRY"


def test_p10_no_afirma_una_localidad_lejana_aunque_la_provincia_sea_la_misma(geo):
    # `agostinelli` (2026-10-01): «Cordoba» era la provincia y la coordenada, de
    # Cruz del Eje, a ~95 km de la ciudad: con 100 km P10 afirmaba la ciudad.
    # Ahora la coordenada tiene que estar a <= 25 km de la localidad.
    lejos = geo.resolver_localidad("Santa Clara del Mar", provincia="Misiones",
                                   lat=-37.83 + 0.27, lon=-57.497)          # ~30 km
    cerca = geo.resolver_localidad("Santa Clara del Mar", provincia="Misiones",
                                   lat=-37.83 + 0.09, lon=-57.497)          # ~10 km
    assert not lejos.resuelta and cerca.resuelta
