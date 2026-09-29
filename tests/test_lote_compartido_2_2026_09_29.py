"""Lote compartido 2 (29-09): identidad canonica (P6), baja entre corridas, fincas."""
from __future__ import annotations

from connectors.base import PropiedadNormalizada, detectar_tipo
from scripts.agency_certifier import identidad_canonica_verificada, resolve_identity

WEB = "https://www.agostinalongo.com.ar"
VERIFICADA = {"estado": "AFIRMABLE", "estado_del_resolver": "OFFICIAL_WEB_HIGH_CONFIDENCE",
              "entidades_que_reclaman_el_host": 1, "verificacion": "VERIFICADA_ARGENTINA",
              "official_url": WEB}


def _registro(verificada=VERIFICADA, platform_id=2889):
    return {"resolution": {"resolution_status": "NOT_FOUND_IN_ERETZ", "eretz_id": None},
            "live": {}, "source": {}, "directory": {},
            "platform": {"domain": WEB, "web_kind": "OFFICIAL_WEB", "eretz_id": platform_id},
            "verificada": verificada}


def test_una_web_verificada_certifica_sin_main_y_sin_el_id_de_staging():
    ide = resolve_identity(_registro(), "roomix:agostina longo real estate")
    assert ide["identity_status"] == "READY"
    assert ide["identity_evidence"]["identity_basis"] == "CANONICAL_VERIFIED_WEB"
    # El id del directorio es de STAGING: nunca entra como clave.
    assert ide["eretz_id"] is None


def test_MUERDE_cualquier_duda_de_identidad_deja_la_agencia_pendiente():
    for cambio in ({"entidades_que_reclaman_el_host": 2},
                   {"estado_del_resolver": "OFFICIAL_WEB_MEDIUM_CONFIDENCE"},
                   {"verificacion": "NO_VERIFICADA"}, {"inventory_allowed": False},
                   {"url_retirada_como_fuente": True},
                   {"official_url": "https://otra-web.com.ar"}):
        ide = resolve_identity(_registro(dict(VERIFICADA, **cambio)), "roomix:x")
        assert ide["identity_status"] == "IDENTITY_PENDING", cambio
    assert not identidad_canonica_verificada({}, WEB)


def test_sin_fk_el_hash_usa_la_identidad_canonica():
    p = PropiedadNormalizada(canonical_agency_id="roomix:x", source_listing_id="1",
                             source_url=WEB + "/p/1", connector="generico", inmobiliaria_id=None)
    q = PropiedadNormalizada(canonical_agency_id="roomix:y", source_listing_id="1",
                             source_url=WEB + "/p/1", connector="generico", inmobiliaria_id=None)
    assert p.hash_dedup != q.hash_dedup


def test_finca_y_chacra_son_tierra_despues_de_los_tipos_edificados():
    assert detectar_tipo("Finca con Viñedo en San Rafael") == "terreno"
    assert detectar_tipo("Chacra en venta") == "terreno"
    assert detectar_tipo("Finca con casa y galpon") == "casa"
    assert detectar_tipo("Casa en Estancia El Terron") == "casa"


def _estado(run1, run2):
    from scripts.agency_certifier import certification_status
    base = {"estado": "OK", "detalles_fallidos": 0, "detalles_desaparecidos": 0}
    comparacion = {"same_url_set": True, "idempotent": True,
                   "same_contract_signature": True, "identity_collisions": 0}
    enumeracion = {"enumerated": 25, "pages_observed": 3,
                   "exhaustive_review_required": False, "review_reasons": []}
    return certification_status({**base, **run1}, {**base, **run2}, comparacion, enumeracion, {})


def test_una_baja_entre_corridas_no_es_una_lectura_fallida():
    """`emir elhelou`: 404 en la corrida 1 y fuera del listado en la 2, que leyo todo."""
    _, razones = _estado({"enumeradas": 26, "detalles_fallidos": 1, "detalles_desaparecidos": 1},
                         {"enumeradas": 25})
    assert "one or more listing details failed" not in razones


def test_MUERDE_si_la_segunda_corrida_sigue_enumerandola_es_un_fallo():
    _, razones = _estado({"enumeradas": 26, "detalles_fallidos": 1, "detalles_desaparecidos": 1},
                         {"enumeradas": 26})
    assert "one or more listing details failed" in razones
