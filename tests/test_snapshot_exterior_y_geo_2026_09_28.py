"""Capa de publicacion (snapshot de la API), decisiones del 28-09.

- Politica publica ARGENTINA_ONLY: lo del exterior se conserva aguas arriba y
  la snapshot no lo sirve.
- La geografia de la snapshot (cobertura del 21-09) respeta lo que decidio la
  extraccion fresca: un conflicto nuevo manda tambien en cierres parciales, y
  CABA confirmada por el poligono oficial levanta el conflicto de texto.
"""
from __future__ import annotations

from connectors.exterior import (PRESERVED_NOT_PUBLISHED, PRODUCT_DECISION_PENDING,
                                 publicable)
from scripts.api_snapshot import CABA, _geo_de_la_extraccion, _publicable_en_argentina


def test_publicable_solo_sin_marca_de_exterior() -> None:
    assert publicable({}) and publicable(None)
    assert not publicable({"publicacion_exterior": PRESERVED_NOT_PUBLISHED})
    assert not publicable({"publicacion_exterior": PRODUCT_DECISION_PENDING})


def test_la_snapshot_no_sirve_lo_marcado_del_exterior() -> None:
    fila = {"titulo": "Depto 3 amb", "ciudad": None, "barrio": None}
    fresca = {"extra": {"publicacion_exterior": PRESERVED_NOT_PUBLISHED, "pais_publicado": "US"}}
    assert not _publicable_en_argentina(fila, fresca)


def test_la_snapshot_no_sirve_una_fila_vieja_con_evidencia_de_exterior() -> None:
    """Filas todavia no recertificadas: la misma evidencia conservadora."""
    fila = {"titulo": "Alquiler Temporal en Sorrento Italia Costa Amalfitana"}
    assert not _publicable_en_argentina(fila, None)


def test_la_snapshot_sirve_lo_argentino() -> None:
    for fila in ({"titulo": "Casa en venta en Italia al 2700", "ciudad": "Rosario"},
                 {"titulo": "Depto en Florida", "ciudad": "Florida"},
                 {"titulo": "Casa", "ciudad": None}):
        assert _publicable_en_argentina(fila, {"extra": {}}), fila


COBERTURA_BA = {"provincia_canonica": "Buenos Aires", "estado_geografico": None,
                "area_busqueda": {"nivel": "PROVINCIA", "nombre": "Buenos Aires"}}
CONFLICTO = {"publicado": {"provincia": "Buenos Aires", "localidad": "CABA",
                           "latitud": None, "longitud": None}}


def test_un_conflicto_fresco_manda_sobre_la_cobertura_vieja() -> None:
    g, motivo = _geo_de_la_extraccion(COBERTURA_BA, {"extra": {"geo_conflicto": CONFLICTO}})
    assert motivo == "conflicto_fresco"
    assert g["estado_geografico"] == "GEO_CONFLICT"
    assert g["conflicto"] == CONFLICTO


def test_sin_novedades_la_cobertura_no_cambia() -> None:
    assert _geo_de_la_extraccion(COBERTURA_BA, None) == (COBERTURA_BA, None)
    assert _geo_de_la_extraccion(COBERTURA_BA, {"extra": {}}) == (COBERTURA_BA, None)


def test_caba_por_poligono_levanta_el_conflicto_solo_a_nivel_provincia() -> None:
    vieja = {"estado_geografico": "GEO_CONFLICT", "conflicto": CONFLICTO,
             "provincia_canonica": None, "barrio_fuente": "Palermo"}
    fresca = {"extra": {"provincia_por_poligono": {
        "provincia": CABA, "geometria": {"fuente": "Instituto Geografico Nacional (IGN)"}}}}
    g, motivo = _geo_de_la_extraccion(vieja, fresca)
    assert motivo == "caba_por_poligono"
    assert g["estado_geografico"] is None and g["conflicto"] is None
    assert g["provincia_canonica"] == CABA
    assert g["municipio_canonico"] is None and g["departamento_canonico"] is None
    assert g["area_busqueda"]["nivel"] == "PROVINCIA"
    assert g["barrio_fuente"] == "Palermo"


def test_el_poligono_no_toca_una_cobertura_sin_conflicto() -> None:
    fresca = {"extra": {"provincia_por_poligono": {"provincia": CABA}}}
    assert _geo_de_la_extraccion(COBERTURA_BA, fresca) == (COBERTURA_BA, None)
