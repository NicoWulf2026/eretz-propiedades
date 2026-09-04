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
