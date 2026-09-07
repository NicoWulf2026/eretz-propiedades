"""Qué estado terminal le corresponde a cada situación."""
from __future__ import annotations

from scripts.agency_certifier import certification_status


def _corrida(**cambios):
    base = {"estado": "OK", "enumeradas": 10, "detalles_fallidos": 0,
            "detalles_desaparecidos": 0, "fuera_de_servicio": None}
    base.update(cambios)
    return base


def _vacios():
    return ({"identity_collisions": 0, "same_url_set": True,
             "same_fingerprints": True, "idempotent": True},
            {"review_reasons": [], "enumeration_complete": True},
            {})


def test_un_dominio_suspendido_cierra_como_inactivo():
    """`ventasprop.com` devuelve "Account Suspended". Dejarlo en NEEDS_FIX lo
    condena a esperar para siempre un arreglo que no existe: no es una
    inmobiliaria sin propiedades ni un defecto nuestro, es una fuente que dejó
    de publicar."""
    comparacion, enumeracion, campos = _vacios()
    estado, razones = certification_status(
        _corrida(estado="VARIANTE_NO_SOPORTADA",
                 fuera_de_servicio="account suspended"),
        _corrida(estado="VARIANTE_NO_SOPORTADA",
                 fuera_de_servicio="account suspended"),
        comparacion, enumeracion, campos)

    assert estado == "INACTIVE"
    assert "account suspended" in razones[0]


def test_una_sola_lectura_de_baja_no_alcanza():
    """Una página de baja puede ser un error momentáneo del hosting, y dar de
    baja una inmobiliaria viva por una lectura es peor que revisarla mañana."""
    comparacion, enumeracion, campos = _vacios()
    estado, _ = certification_status(
        _corrida(estado="VARIANTE_NO_SOPORTADA",
                 fuera_de_servicio="account suspended"),
        _corrida(estado="VARIANTE_NO_SOPORTADA", fuera_de_servicio=None),
        comparacion, enumeracion, campos)

    assert estado != "INACTIVE"


def test_un_sitio_que_nos_rechaza_sigue_siendo_bloqueado():
    """La baja no puede tapar el rechazo: son cosas distintas y el rechazo se
    decide primero porque es una respuesta del sitio, no una ausencia."""
    comparacion, enumeracion, campos = _vacios()
    estado, _ = certification_status(
        _corrida(estado="BLOQUEADA"), _corrida(estado="BLOQUEADA"),
        comparacion, enumeracion, campos)
    assert estado == "BLOCKED_EXTERNAL"
