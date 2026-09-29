"""P10, parte geometrica: contencion en el poligono oficial de cada provincia.

Geometria SINTETICA (cuadrados en una grilla): prueba el calculo, no el IGN. El
archivo real lo genera LOCAL con `scripts/geo_poligonos_provincias.py`.
"""
from __future__ import annotations

import json

import pytest

from connectors import poligono_provincia as P
from scripts import geo_poligonos_provincias as G


def _cuadrado(x0, y0, lado):
    return [[x0, y0], [x0 + lado, y0], [x0 + lado, y0 + lado], [x0, y0 + lado], [x0, y0]]


def _wfs(extra_por_codigo=None):
    """24 jurisdicciones de 1 x 1 grado en una grilla de 6 x 4, lon -70..-64, lat -40..-36."""
    rasgos = []
    for i in range(24):
        codigo = f"{2 + 4 * i:02d}"
        x0, y0 = -70 + (i % 6), -40 + (i // 6)
        coords = [[_cuadrado(x0, y0, 1)]]
        coords += (extra_por_codigo or {}).get(codigo, [])
        rasgos.append({"type": "Feature",
                       "properties": {"in1": codigo, "nam": f"Provincia {codigo}",
                                      "fna": f"Provincia de Prueba {codigo}"},
                       "geometry": {"type": "MultiPolygon", "coordinates": coords}})
    return {"type": "FeatureCollection", "features": rasgos, "timeStamp": "2026-09-29T00:00:00Z"}


@pytest.fixture()
def geometria(tmp_path):
    # «06»: una isla chica aparte y un poligono entero al sur de -60 (se omite).
    datos = _wfs({"06": [[_cuadrado(-60.0, -38.0, 0.01)], [_cuadrado(-60.0, -70.0, 1)]]})
    salida = G.construir(datos, "https://wfs.invalid", json.dumps(datos).encode())
    ruta = tmp_path / "provincias_ign.json"
    ruta.write_text(json.dumps(salida), encoding="utf-8")
    P._cargar.cache_clear()
    yield ruta
    P._cargar.cache_clear()


def test_construir_valida_las_24_jurisdicciones():
    datos = _wfs()
    datos["features"] = datos["features"][:23]
    with pytest.raises(ValueError, match="24 jurisdicciones"):
        G.construir(datos, "u", b"")
    datos = _wfs()
    datos["features"][1]["properties"]["in1"] = datos["features"][0]["properties"]["in1"]
    with pytest.raises(ValueError, match="codigo in1 distinto"):
        G.construir(datos, "u", b"")


def test_construir_deja_procedencia_islas_y_omite_la_antartida(geometria):
    datos = json.loads(geometria.read_text(encoding="utf-8"))
    assert datos["procedencia"]["jurisdicciones"] == 24
    assert datos["procedencia"]["sha256_origen"]
    poligonos = datos["provincias"]["06"]["poligonos"]
    assert len(poligonos) == 2   # el continental y la isla; el antartico no
    assert all(y > -60 for p in poligonos for a in p for _, y in a)


def test_contencion_por_codigo_y_por_nombre(geometria):
    # «02» es el cuadrado lon -70..-69, lat -40..-39.
    assert P.contencion("02", -39.5, -69.5, ruta=geometria) == P.DENTRO
    assert P.contencion("Provincia 02", -39.5, -69.5, ruta=geometria) == P.DENTRO
    assert P.contencion("provincia de prueba 02", -39.5, -69.5, ruta=geometria) == P.DENTRO
    assert P.contencion("02", -39.5, -68.5, ruta=geometria) == P.FUERA


def test_cerca_del_limite_no_afirma(geometria):
    # 1 km adentro del borde oeste (-70): el margen es 2 km.
    lon = -70 + 1.0 / (111.32 * 0.77)
    assert P.contencion("02", -39.5, lon, ruta=geometria) == P.FRONTERA
    assert P.contencion("02", -39.5, -69.9, ruta=geometria) == P.DENTRO   # ~8,6 km


def test_sin_evidencia_no_hay_veredicto(geometria, tmp_path):
    assert P.contencion("02", None, -69.5, ruta=geometria) is None
    assert P.contencion("02", "x", -69.5, ruta=geometria) is None
    assert P.contencion("99", -39.5, -69.5, ruta=geometria) is None          # provincia desconocida
    assert P.contencion("02", -39.5, -69.5, ruta=tmp_path / "no.json") is None


def test_la_isla_cuenta_como_su_provincia(geometria):
    assert P.contencion("06", -37.995, -59.995, ruta=geometria, margen_km=0.1) == P.DENTRO


def test_provincia_que_contiene_es_unica_o_nada(geometria):
    assert P.provincia_que_contiene(-39.5, -69.5, ruta=geometria) == "02"
    assert P.provincia_que_contiene(-39.0, -69.0, ruta=geometria) is None   # vertice de 4
    assert P.provincia_que_contiene(-20.0, -60.0, ruta=geometria) is None   # fuera de todas


def test_sin_archivo_real_todavia_no_se_afirma_nada():
    """Hasta que LOCAL genere el archivo del IGN, el modulo no afirma (fail-closed)."""
    if P.GEOMETRIA.exists():
        pytest.skip("el archivo real ya existe")
    assert P.contencion("06", -34.9, -57.95) is None
    assert P.procedencia() is None
