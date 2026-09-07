"""El preflight que decide si la cola se puede reabrir."""
from __future__ import annotations

import json

from scripts.agency_fingerprints import FINGERPRINT_SCHEMA_VERSION
from scripts.agency_rollout_preflight import (huella_vigente,
                                              sin_defectos_abiertos)


def _resultado(huella: str | None = "vieja", estado: str = "NEEDS_FIX",
               esquema: int | None = FINGERPRINT_SCHEMA_VERSION) -> dict:
    return {"canonical_agency_id": "roomix:alfa", "status": estado,
            "connector": "generico", "connector_strategy": "generico/portal",
            "strategy_fingerprint": huella,
            "fingerprint_schema_version": esquema}


def _salida(tmp_path, resultados: list[dict]):
    (tmp_path / "AGENCY_CERTIFICATION_RESULTS.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in resultados),
        encoding="utf-8")
    return tmp_path


def test_un_needs_fix_con_la_huella_vigente_cierra_la_cola(tmp_path, monkeypatch):
    """Es el caso peligroso: nadie corrigió nada y reabrir camina hacia la
    misma parada. `NEEDS_FIX` nunca es un cierre."""
    monkeypatch.setattr("scripts.agency_rollout_preflight.strategy_fingerprint",
                        lambda *_: "vieja")
    salida = _salida(tmp_path, [_resultado()])
    ok, detalle = sin_defectos_abiertos(salida, {"roomix:alfa": {}})
    assert ok is False
    assert "sin resolver" in detalle


def test_un_needs_fix_con_la_huella_vencida_no_cierra_la_cola(tmp_path, monkeypatch):
    """Ese veredicto lo emitió código que ya no existe: es evidencia vencida,
    no un defecto abierto, y volver a evaluarla es para lo que está la cola.

    Sin la distinción el protocolo queda en deadlock: el paquete sólo se limpia
    recertificando y recertificar exige reabrir, así que un solo `NEEDS_FIX`
    cerraba la cola para siempre.
    """
    monkeypatch.setattr("scripts.agency_rollout_preflight.strategy_fingerprint",
                        lambda *_: "nueva")
    salida = _salida(tmp_path, [_resultado(huella="vieja")])
    ok, detalle = sin_defectos_abiertos(salida, {"roomix:alfa": {}})
    assert ok is True
    assert "huella vencida" in detalle


def test_sin_huella_registrada_el_defecto_sigue_abierto(tmp_path, monkeypatch):
    """No poder demostrar que está vencido no es demostrar que se corrigió."""
    monkeypatch.setattr("scripts.agency_rollout_preflight.strategy_fingerprint",
                        lambda *_: "nueva")
    salida = _salida(tmp_path, [_resultado(huella=None)])
    assert sin_defectos_abiertos(salida, {"roomix:alfa": {}})[0] is False


def test_no_se_juzga_un_defecto_con_is_current_result(monkeypatch):
    """`is_current_result` devuelve False de entrada para todo estado NO
    TERMINAL, y `NEEDS_FIX` no lo es. Usarla habría dado siempre "vencido" y
    desactivado el guardián en silencio, que es lo contrario de lo que hace
    falta."""
    monkeypatch.setattr("scripts.agency_rollout_preflight.strategy_fingerprint",
                        lambda *_: "vieja")
    assert huella_vigente(_resultado(huella="vieja"), {}) is True
    monkeypatch.setattr("scripts.agency_rollout_preflight.strategy_fingerprint",
                        lambda *_: "nueva")
    assert huella_vigente(_resultado(huella="vieja"), {}) is False


def test_cambiar_la_definicion_de_la_huella_no_amnistia_los_defectos(tmp_path,
                                                                     monkeypatch):
    """Redefinir qué se hashea cambia todas las huellas y no corrige nada.

    Sin esta regla, subir `FINGERPRINT_SCHEMA_VERSION` habría dejado en cero la
    lista de `NEEDS_FIX` abiertos: todos pasarían por "evidencia vencida" de un
    plumazo. Un paquete de un esquema anterior se juzga con el algoritmo de SU
    esquema, que es lo único que contesta si cambió el comportamiento.
    """
    import scripts.agency_rollout_preflight as pre

    viejo = _resultado(huella="vieja", esquema=1)
    # El algoritmo del esquema 1 da lo mismo que lo guardado: nadie toco el
    # comportamiento, asi que el defecto sigue abierto.
    monkeypatch.setattr(pre, "strategy_fingerprint_v1", lambda *_: "vieja")
    monkeypatch.setattr(pre, "strategy_fingerprint", lambda *_: "nueva-por-el-modelo")
    salida = _salida(tmp_path, [viejo])
    assert sin_defectos_abiertos(salida, {"roomix:alfa": {}})[0] is False

    # Si ademas cambio el comportamiento, ahi si es evidencia vencida.
    monkeypatch.setattr(pre, "strategy_fingerprint_v1", lambda *_: "otra")
    assert sin_defectos_abiertos(salida, {"roomix:alfa": {}})[0] is True


def test_un_defecto_de_radio_acotado_no_cierra_la_cola(tmp_path, monkeypatch):
    """La cola atraviesa un defecto de radio acotado sin detenerse; exigir que
    esté resuelto para reabrir contradice la política que dice seguir.

    `varelanegociosinmobiliarios.com` no respondía y dejaba la cola cerrada
    esperando que un servidor ajeno volviera.
    """
    monkeypatch.setattr("scripts.agency_rollout_preflight.strategy_fingerprint",
                        lambda *_: "vieja")
    caido = dict(_resultado(),
                 reasons=["one or both runs did not finish with connector "
                          "state OK"],
                 run1={"estado": "ERROR_DISCOVERY", "detalle": "TimeoutError"},
                 run2={"estado": "ERROR_DISCOVERY", "detalle": "TimeoutError"},
                 comparison={"identity_collisions": 0}, field_coverage={},
                 enumeration_audit={"review_reasons": ["COLLAPSE_GT_80_PERCENT"]})
    salida = _salida(tmp_path, [caido])

    ok, detalle = sin_defectos_abiertos(salida, {"roomix:alfa": {}})
    assert ok is True
    assert "radio acotado" in detalle


def test_un_defecto_transversal_sigue_cerrando_la_cola(tmp_path, monkeypatch):
    """La puerta anterior no puede tapar el caso peligroso: un colapso con el
    sitio leído es nuestro y para la cola."""
    monkeypatch.setattr("scripts.agency_rollout_preflight.strategy_fingerprint",
                        lambda *_: "vieja")
    nuestro = dict(_resultado(),
                   reasons=["inventory collapsed by more than 80%"],
                   run1={"estado": "OK", "detalles_fallidos": 0},
                   run2={"estado": "OK", "detalles_fallidos": 0},
                   comparison={"identity_collisions": 0}, field_coverage={},
                   enumeration_audit={"review_reasons": ["COLLAPSE_GT_80_PERCENT"]})
    salida = _salida(tmp_path, [nuestro])

    assert sin_defectos_abiertos(salida, {"roomix:alfa": {}})[0] is False


def test_el_veredicto_se_recalcula_y_no_se_lee_del_registro(tmp_path, monkeypatch):
    """Un veredicto lo produjo el triage de ese momento. Si el triage cambió
    —como cambió al dejar de leer un sitio inaccesible como pérdida
    sistemática— el registro viejo ya no dice la verdad. Es el mismo criterio
    que las huellas."""
    monkeypatch.setattr("scripts.agency_rollout_preflight.strategy_fingerprint",
                        lambda *_: "vieja")
    # El registro dice STOP; el triage de hoy, sobre los mismos datos, dice
    # CONTINUE. Manda el de hoy.
    con_veredicto_viejo = dict(_resultado(),
                               decision="STOP", radio_estimado="FAMILIA",
                               reasons=["inventory collapsed"],
                               run1={"estado": "ERROR_DISCOVERY"},
                               run2={"estado": "ERROR_DISCOVERY"},
                               comparison={"identity_collisions": 0},
                               field_coverage={},
                               enumeration_audit={
                                   "review_reasons": ["COLLAPSE_GT_80_PERCENT"]})
    salida = _salida(tmp_path, [con_veredicto_viejo])

    assert sin_defectos_abiertos(salida, {"roomix:alfa": {}})[0] is True


def test_el_preflight_ve_los_cerrojos_de_los_dos_workers(tmp_path):
    """Con dos workers los cerrojos se llaman `...RUNNER.w0.lock` y
    `...RUNNER.w1.lock`. Buscar sólo el nombre de un worker respondía "no hay
    cerrojo tomado" con dos procesos corriendo: justo lo que este chequeo
    existe para impedir."""
    import time

    from scripts.agency_rollout_preflight import sin_otro_runner

    assert sin_otro_runner(tmp_path)[0] is True

    (tmp_path / "AGENCY_CERTIFICATION_RUNNER.w1.lock").write_text(
        json.dumps({"pid": 123, "heartbeat_epoch": time.time(),
                    "current_agency": "roomix:alfa"}), encoding="utf-8")

    ok, detalle = sin_otro_runner(tmp_path)
    assert ok is False
    assert "w1" in detalle and "123" in detalle


def test_un_cerrojo_vencido_no_bloquea(tmp_path):
    """Un proceso muerto no puede cerrar la cola para siempre."""
    import time

    from scripts.agency_rollout_preflight import (LATIDO_VENCIDO,
                                                  sin_otro_runner)

    (tmp_path / "AGENCY_CERTIFICATION_RUNNER.w0.lock").write_text(
        json.dumps({"pid": 1, "heartbeat_epoch": time.time() - LATIDO_VENCIDO - 60}),
        encoding="utf-8")
    ok, detalle = sin_otro_runner(tmp_path)
    assert ok is True
    assert "vencido" in detalle
