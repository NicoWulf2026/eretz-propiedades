"""El contrato que consume el frontend: nullability medida, no supuesta."""
from __future__ import annotations

import json

from scripts.api_contract import (ALCANCES, CONTRATO_API_VERSION, FORMA,
                                  FORMA_GEO, NUNCA_NULO, fila_de_api)


def _fila(**cambios):
    base = {"hash_dedup": "h1", "source_url": "https://alfa.com.ar/p/1",
            "canonical_agency_id": "roomix:alfa", "titulo": "Casa en Venta",
            "precio": 100000.0, "moneda": "USD"}
    base.update(cambios)
    return base


def test_la_identidad_nunca_viaja_vacia():
    """Sin esto no hay a qué volver ni cómo deduplicar."""
    api = fila_de_api(_fila(), None, ["FICHA", "LISTADO"])
    for campo in NUNCA_NULO:
        assert api[campo] not in (None, ""), campo


def test_una_propiedad_sin_nada_igual_tiene_forma_completa():
    """La regla del sistema es que una propiedad real incompleta sobrevive, así
    que el frontend tiene que poder renderizarla igual."""
    api = fila_de_api({"hash_dedup": "h", "source_url": "u",
                       "canonical_agency_id": "a"}, None, ["FICHA"])
    assert set(api) == set(FORMA)
    assert api["imagenes"] == []
    assert api["geo"]["area_busqueda"]["nivel"] == "SIN_AREA"


def test_la_localidad_no_se_rellena_con_el_area():
    """Una propiedad sin localidad demostrada NO se muestra con una ciudad
    inventada: se muestra con su área y su nivel."""
    geo = {"localidad_canonica": None, "municipio_canonico": "La Calera",
           "area_busqueda": {"nivel": "MUNICIPIO", "valor": "La Calera"}}
    api = fila_de_api(_fila(), geo, ["FICHA", "AREA_BUSQUEDA"])

    assert api["geo"]["localidad"]["nombre"] is None
    assert api["geo"]["localidad"]["procedencia"] == "UNKNOWN"
    assert api["geo"]["municipio"]["nombre"] == "La Calera"
    assert api["geo"]["area_busqueda"]["nivel"] == "MUNICIPIO"


def test_el_conflicto_geografico_viaja_al_frontend():
    """Si el frontend no sabe que hay conflicto, lo muestra como un dato
    normal."""
    geo = {"estado_geografico": "GEO_CONFLICT",
           "area_busqueda": {"nivel": "PROVINCIA", "valor": "Cordoba"}}
    api = fila_de_api(_fila(), geo, ["FICHA"])
    assert api["geo"]["estado"] == "GEO_CONFLICT"


def test_el_area_de_busqueda_siempre_declara_su_nivel():
    """Sin nivel, un municipio en la caja de búsqueda se lee como una ciudad."""
    assert FORMA_GEO["area_busqueda"]["nulo"] is False
    api = fila_de_api(_fila(), {}, [])
    assert "nivel" in api["geo"]["area_busqueda"]


def test_los_alcances_del_contrato_y_del_gate_son_los_mismos():
    """Si divergen, el frontend filtra por un alcance que nadie emite."""
    from scripts.property_contract import (AREA_BUSQUEDA, FICHA,
                                           FILTRO_LOCALIDAD, FILTRO_OPERACION,
                                           FILTRO_PRECIO, FILTRO_TIPO, LISTADO,
                                           MAPA)
    del_gate = {FICHA, LISTADO, MAPA, FILTRO_PRECIO, FILTRO_TIPO,
                FILTRO_OPERACION, FILTRO_LOCALIDAD, AREA_BUSQUEDA}
    assert set(ALCANCES) == del_gate


def test_el_contrato_declara_su_version():
    """Cambiar la forma tiene que verse; si no, Codex no sabe contra qué
    construyó."""
    assert CONTRATO_API_VERSION.startswith("eretz_api_property_v")
