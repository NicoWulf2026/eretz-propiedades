"""Capa de publicacion (snapshot de la API), decisiones del 28-09.

- Politica publica ARGENTINA_ONLY: lo del exterior se conserva aguas arriba y
  la snapshot no lo sirve.
- La geografia de la snapshot (cobertura del 21-09) respeta lo que decidio la
  extraccion fresca: un conflicto nuevo manda tambien en cierres parciales, y
  CABA confirmada por el poligono oficial levanta el conflicto de texto.
"""
from __future__ import annotations

import pytest

from connectors.exterior import (PRESERVED_NOT_PUBLISHED, PRODUCT_DECISION_PENDING,
                                 publicable)
from connectors.geografia import (AMBIGUA, DEPARTAMENTO_REASON, DIRECTORIO_POR_DEFECTO,
                                  geografia)
from scripts.api_snapshot import CABA, _geo_de_la_extraccion, _publicable_en_argentina

pytestmark = pytest.mark.skipif(
    not (DIRECTORIO_POR_DEFECTO / "localidades_censales.json").exists(),
    reason="falta el snapshot de GeoRef; se baja con scripts/geo_snapshot.py")


@pytest.mark.parametrize("localidad,provincia", [("San Jerónimo", "Santa Fe"),
                                                 ("Colón", "Córdoba"),
                                                 ("Junín", "San Luis")])
def test_un_departamento_de_la_provincia_declarada_no_la_contradice(localidad, provincia) -> None:
    r = geografia().resolver_localidad(localidad, provincia=provincia)
    assert r.entidad is None
    assert r.certeza == AMBIGUA and r.motivo == DEPARTAMENTO_REASON


def test_el_pipeline_conserva_la_provincia_ante_un_departamento() -> None:
    from connectors.base import Connector, PropiedadNormalizada
    prop = PropiedadNormalizada(canonical_agency_id="roomix:x", source_listing_id="1",
                                source_url="https://x.test/p/1", connector="generico",
                                ciudad="San Jerónimo", provincia="Santa Fe")
    Connector._resolver_geografia(prop)
    assert prop.provincia == "Santa Fe"
    assert prop.ciudad is None
    assert "geo_conflicto" not in prop.extra


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


def test_el_poligono_no_toca_una_cobertura_que_ya_dice_caba() -> None:
    cobertura = {"provincia_canonica": CABA, "estado_geografico": None,
                 "municipio_canonico": "Comuna 14"}
    fresca = {"extra": {"provincia_por_poligono": {"provincia": CABA}}}
    assert _geo_de_la_extraccion(cobertura, fresca) == (cobertura, None)


def test_un_conflicto_viejo_que_nombra_un_departamento_no_se_impone() -> None:
    """`metro`: «San Jeronimo, Santa Fe» son lotes en Monje, departamento San Jeronimo."""
    cobertura = {"provincia_canonica": "Santa Fe", "estado_geografico": None}
    conflicto = {"publicado": {"provincia": "Santa Fe", "localidad": "San Jerónimo",
                               "latitud": None, "longitud": None}}
    g, motivo = _geo_de_la_extraccion(cobertura, {"extra": {"geo_conflicto": conflicto}})
    assert motivo == "conflicto_obsoleto"
    assert g == cobertura


def test_un_conflicto_viejo_de_caba_dentro_del_poligono_afirma_caba() -> None:
    """Paquete certificado antes del poligono: se re-evalua sin esperar la cola."""
    vieja = {"estado_geografico": "GEO_CONFLICT", "provincia_canonica": None}
    conflicto = {"publicado": {"provincia": "Buenos Aires", "localidad": "CABA",
                               "latitud": -34.6037, "longitud": -58.3816}}
    g, motivo = _geo_de_la_extraccion(vieja, {"extra": {"geo_conflicto": conflicto}})
    assert motivo == "caba_por_poligono"
    assert g["provincia_canonica"] == CABA and g["estado_geografico"] is None


def test_un_conflicto_viejo_de_caba_en_quilmes_sigue() -> None:
    conflicto = {"publicado": {"provincia": "Buenos Aires", "localidad": "CABA",
                               "latitud": -34.7206, "longitud": -58.2546}}
    g, motivo = _geo_de_la_extraccion(COBERTURA_BA, {"extra": {"geo_conflicto": conflicto}})
    assert motivo == "conflicto_fresco" and g["estado_geografico"] == "GEO_CONFLICT"


def test_provincia_declarada_confirmada_por_su_coordenada_publica_provincia_y_punto() -> None:
    """cip (03-10): «Merlo» + San Luis, coordenada dentro de San Luis."""
    conflicto = {"publicado": {"provincia": "San Luis", "localidad": "Merlo",
                               "latitud": -32.3431, "longitud": -65.0136}}
    g, motivo = _geo_de_la_extraccion(COBERTURA_BA, {"extra": {"geo_conflicto": conflicto}})
    assert motivo == "provincia_declarada_por_poligono"
    assert g["provincia_canonica"] == "San Luis" and g["estado_geografico"] is None
    assert g["localidad_canonica"] is None


def test_provincia_inferida_del_padron_no_contradice_una_coordenada_en_caba() -> None:
    """d amato (03-10): Villa del Parque, padron «Buenos Aires», punto en CABA."""
    conflicto_viejo = dict(COBERTURA_BA, estado_geografico="GEO_CONFLICT")
    fresca = {"latitud": -34.6077, "longitud": -58.5004,
              "extra": {"provincia_confianza": "inferida", "provincia_supuesta_descartada": "Buenos Aires"}}
    g, motivo = _geo_de_la_extraccion(conflicto_viejo, fresca)
    assert motivo == "caba_por_poligono"
    assert g["provincia_canonica"] == CABA and g["estado_geografico"] is None


def test_provincia_publicada_no_se_toca_aunque_el_punto_este_en_caba() -> None:
    fresca = {"latitud": -34.6077, "longitud": -58.5004, "extra": {"provincia_confianza": "publicada"}}
    g, motivo = _geo_de_la_extraccion(dict(COBERTURA_BA, estado_geografico="GEO_CONFLICT"), fresca)
    assert motivo != "caba_por_poligono"
