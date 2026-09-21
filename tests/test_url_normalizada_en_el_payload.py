# -*- coding: utf-8 -*-
"""`to_payload()` no producia `url_normalizada` y el RPC la exige.

Sin ella `insert_property_safe` levanta «safe insert requires complete
identity and audit envelope», asi que migrar del REST al RPC no era cambiar
la llamada: faltaba el dato. Y produccion ya trataba su ausencia como defecto
—la bandera `missing_normalized_url` es literalmente «url exists and
url_normalizada is blank»—.

Lo que estos tests protegen no es que el campo exista, sino **con que forma
se calcula**. Hay dos normalizaciones de url en el proyecto y no son la
misma:

    _normalize_url_for_hash   ...ficha.php?id=7838&op=v     (conserva query)
    la del volcado de prod    ...ficha.php                  (la tira)

Medido sobre las 22.097 propiedades certificadas: la segunda colapsa 492 en
otra fila. `agostinelli` funde 397 en una sola clave. Elegir la equivocada
aca no rompe ningun test obvio y arruina la identidad de los sitios que
identifican la propiedad por query.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from scraper.models import Propiedad, _compute_hash_dedup  # noqa: E402


def propiedad(url: str) -> Propiedad:
    return Propiedad(url=url, titulo="Casa en venta", inmobiliaria_id=7)


def test_el_payload_ahora_trae_url_normalizada():
    assert propiedad("https://www.x.com.ar/p/1/").to_payload()["url_normalizada"] \
        == "x.com.ar/p/1"


def test_MUERDE_la_query_se_conserva_porque_ahi_vive_la_identidad():
    """El caso `agostinelli`, exacto: 397 propiedades en una sola clave.

    Si se usara la forma del volcado de produccion, estas dos fichas —que son
    propiedades distintas— tendrian la misma `url_normalizada`.
    """
    una = propiedad("https://agostinelli.com.ar/ficha.php?id=7838&op=V")
    otra = propiedad("https://agostinelli.com.ar/ficha.php?id=8200&op=V")
    assert (una.to_payload()["url_normalizada"]
            != otra.to_payload()["url_normalizada"])
    assert "7838" in una.to_payload()["url_normalizada"]


def test_MUERDE_es_la_misma_forma_sobre_la_que_esta_definido_hash_dedup():
    """Dos identidades de la misma fila calculadas distinto es peor que una.

    `hash_dedup` ya estaba definido como sha256 de
    `{inmobiliaria_id}|url|{url_normalizada}`. Si el campo no coincidiera con
    lo que el hash hashea, la fila diria dos cosas sobre si misma.
    """
    p = propiedad("https://WWW.Ejemplo.com.ar//Casa//Linda/?a=1")
    payload = p.to_payload()
    import hashlib
    esperado = hashlib.sha256(
        f"7|url|{payload['url_normalizada']}".encode()).hexdigest()[:32]
    assert payload["hash_dedup"] == esperado
    assert payload["hash_dedup"] == _compute_hash_dedup(7, p.url)


def test_una_url_vacia_no_mete_un_campo_vacio():
    """El RPC rechaza `url_normalizada` en blanco con el mismo error que si
    faltara. Mandar la cadena vacia no gana nada y esconde el caso."""
    payload = Propiedad(url="", titulo="Casa").to_payload()
    assert "url_normalizada" not in payload


def test_el_resto_del_payload_no_cambio():
    """Este payload lo consume el INSERT por REST que si tiene consumidores.

    Agregar una clave que la tabla no acepte seria un 400 en produccion.
    """
    payload = propiedad("https://x.com.ar/p/1").to_payload()
    esperadas = {
        "url", "titulo", "precio", "moneda", "direccion", "barrio",
        "tipo_propiedad", "descripcion", "dormitorios", "banos", "ambientes",
        "superficie_total", "imagenes", "ciudad", "operacion", "latitud",
        "longitud", "fuente_extraccion", "estado", "inmobiliaria_id",
        "hash_dedup", "url_normalizada"}
    assert set(payload) == esperadas


def test_los_cuatro_campos_que_el_rpc_soporta_y_el_modelo_no_tiene():
    """`superficie_cubierta`, `id_externo`, `provincia` y `pais`.

    El documento de equivalencia los dejaba como decision pendiente. La
    decision se toma sola: `Propiedad` no los tiene, asi que no hay de donde
    sacarlos. Completarlos exigiria que alguien los produzca primero;
    inventarlos seria peor que su ausencia.
    """
    campos = set(Propiedad.__dataclass_fields__)
    for ausente in ("superficie_cubierta", "id_externo", "provincia", "pais"):
        assert ausente not in campos
