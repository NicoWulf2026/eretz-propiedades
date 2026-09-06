"""Cobertura geográfica por dimensión, y el conflicto que no se resuelve."""
from __future__ import annotations

import json

from scripts.geo_coverage_audit import (NIVEL_DEPARTAMENTO, NIVEL_LOCALIDAD,
                                        NIVEL_MUNICIPIO, NIVEL_PROVINCIA,
                                        cargar_cache, clave_de)


def test_la_clave_de_cache_es_la_coordenada_redondeada():
    """Cinco decimales, ~1,1 m: la misma precisión que la firma de duplicados.
    Redondear más agruparía puntos de municipios distintos; menos haría la
    caché inútil."""
    assert clave_de(-31.362610001, -64.346130001) == "-31.36261,-64.34613"
    assert clave_de(None, -64.3) is None
    assert clave_de("no es un numero", 1) is None


def test_dos_avisos_del_mismo_edificio_comparten_entrada(tmp_path):
    """La caché se indexa por coordenada, no por propiedad: 36.552 puntos
    entraron en 26.965 entradas."""
    assert clave_de(-31.36261, -64.34613) == clave_de(-31.362610, -64.346130)


def test_una_cache_ausente_no_rompe_la_auditoria(tmp_path):
    """Sin geometría se mide igual, sólo que con menos evidencia."""
    assert cargar_cache(tmp_path / "no-existe.jsonl") == {}


def test_la_cache_se_lee_por_clave(tmp_path):
    ruta = tmp_path / "cache.jsonl"
    ruta.write_text(json.dumps({
        "clave": "-31.36261,-64.34613", "provincia": "Córdoba",
        "departamento": "Colón", "municipio": "La Calera"},
        ensure_ascii=False) + "\n", encoding="utf-8")
    cache = cargar_cache(ruta)
    assert cache["-31.36261,-64.34613"]["municipio"] == "La Calera"


def test_los_niveles_van_de_mas_preciso_a_menos():
    """El orden importa: si `PROVINCIA` ganara a `MUNICIPIO`, el área sería
    inútil para buscar."""
    assert [NIVEL_LOCALIDAD, NIVEL_MUNICIPIO, NIVEL_DEPARTAMENTO,
            NIVEL_PROVINCIA] == ["LOCALIDAD", "MUNICIPIO", "DEPARTAMENTO",
                                 "PROVINCIA"]
