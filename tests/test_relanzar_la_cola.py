# -*- coding: utf-8 -*-
"""Relanzar la cola vale más que cualquier arreglo, y por eso hay que acotarlo.

El 75 % del tiempo la cola está parada: 366,0 h de 487,6 h, en 167 episodios.
Y **117 de esos 167 huecos no coinciden con ningún paro registrado** —suman
190,6 h, el 52 % de las horas paradas—. No son defectos: es la cola no
corriendo porque nadie la relanzó.

Pero un relanzador sin freno es peor que ninguno: relanzar sobre un paro
transversal sin diagnosticar produce certificaciones con código sospechado que
después hay que rehacer. Estos tests fijan las dos mitades.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from relanzar_la_cola import (decidir, paro_atendido,  # noqa: E402
                              paro_vigente, workers_vivos)


def ahora(desplazamiento: float = 0.0) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S",
                         time.localtime(time.time() + desplazamiento))


def poner_paro(salida: Path, agencia="roomix:fios", cuando=None) -> None:
    (salida / "AGENCY_CERTIFICATION_STOP.json").write_text(json.dumps({
        "canonical_agency_id": agencia, "componente": "perdida_de_inventario",
        "radio": "FAMILIA", "cuando": cuando or ahora(-3600)}),
        encoding="utf-8")


def poner_diferida(salida: Path, agencia="roomix:fios", cuando=None) -> None:
    with (salida / "AGENCY_DEFECTS_DIFERIDOS.jsonl").open(
            "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"canonical_agency_id": agencia,
                             "componente": "perdida_de_inventario",
                             "radio": "FAMILIA",
                             "cuando": cuando or ahora()}) + "\n")


def test_sin_paro_y_sin_workers_se_lanzan_los_dos(tmp_path):
    faltan, motivo = decidir(tmp_path)
    assert faltan == [0, 1], motivo


def test_MUERDE_un_paro_sin_diagnosticar_NO_relanza(tmp_path):
    """La regla que no se relaja.

    Un paro transversal significa que sospechamos del código. Volver a correrlo
    produce certificaciones que habría que rehacer, y encima esconde el paro
    detrás de trabajo nuevo.
    """
    poner_paro(tmp_path)
    faltan, motivo = decidir(tmp_path)
    assert faltan == []
    assert "sin diagnosticar" in motivo


def test_un_paro_con_diferida_posterior_si_relanza(tmp_path):
    """La otra mitad: diagnosticado y firmado, la cola tiene que seguir.

    Sin esto el relanzador sería un freno permanente y volveríamos a las
    190,6 h de cola parada, que es el problema que vino a resolver.
    """
    poner_paro(tmp_path, cuando=ahora(-3600))
    poner_diferida(tmp_path, cuando=ahora(-60))
    faltan, _ = decidir(tmp_path)
    assert faltan == [0, 1]


def test_MUERDE_una_diferida_ANTERIOR_al_paro_no_alcanza(tmp_path):
    """El orden importa y es la parte fácil de equivocar.

    Si el paro es posterior a la diferida, trae información que esa diferida no
    pudo haber tenido en cuenta. Aceptarla convertiría «esta agencia ya se
    miró alguna vez» en «este paro está atendido», que no es lo mismo.
    """
    poner_diferida(tmp_path, cuando=ahora(-7200))
    poner_paro(tmp_path, cuando=ahora(-60))
    faltan, motivo = decidir(tmp_path)
    assert faltan == [], motivo


def test_una_diferida_de_OTRA_agencia_no_atiende_este_paro(tmp_path):
    poner_paro(tmp_path, agencia="roomix:fios", cuando=ahora(-3600))
    poner_diferida(tmp_path, agencia="roomix:otra", cuando=ahora())
    assert decidir(tmp_path)[0] == []


def test_un_paro_ilegible_no_relanza(tmp_path):
    """Ilegible es peor que ausente: no se relanza a ciegas."""
    (tmp_path / "AGENCY_CERTIFICATION_STOP.json").write_text(
        "{roto", encoding="utf-8")
    assert paro_vigente(tmp_path) is not None
    assert decidir(tmp_path)[0] == []


def test_MUERDE_nunca_mas_de_dos_workers(tmp_path, monkeypatch):
    """El límite duro del proyecto, comprobado acá además del cerrojo."""
    import relanzar_la_cola as modulo
    monkeypatch.setattr(modulo, "workers_vivos", lambda s: {0: 111})
    faltan, _ = modulo.decidir(tmp_path)
    assert faltan == [1]
    monkeypatch.setattr(modulo, "workers_vivos", lambda s: {0: 111, 1: 222})
    assert modulo.decidir(tmp_path)[0] == []


def test_un_cerrojo_ilegible_cuenta_como_ocupado(tmp_path):
    """Misma política que el runner, y por la misma razón.

    Borrar un cerrojo ilegible a ciegas es como se terminan pisando dos
    procesos el mismo checkpoint.
    """
    (tmp_path / "AGENCY_CERTIFICATION_RUNNER.w0.lock").write_text(
        "no es json", encoding="utf-8")
    assert 0 in workers_vivos(tmp_path)
    assert decidir(tmp_path)[0] == [1]


def test_un_cerrojo_de_un_pid_muerto_no_bloquea(tmp_path):
    """Un proceso muerto no es un worker vivo.

    Es justamente el caso de los 117 huecos sin paro: el proceso se murió y el
    cerrojo quedó. Tratarlo como ocupado dejaría la cola detenida para siempre,
    que es exactamente lo que venía pasando.
    """
    (tmp_path / "AGENCY_CERTIFICATION_RUNNER.w0.lock").write_text(
        json.dumps({"pid": 999999999, "heartbeat_epoch": time.time()}),
        encoding="utf-8")
    assert workers_vivos(tmp_path) == {}
    assert decidir(tmp_path)[0] == [0, 1]


def test_paro_atendido_no_se_confunde_con_fecha_invalida(tmp_path):
    poner_paro(tmp_path, cuando="no es una fecha")
    paro = paro_vigente(tmp_path)
    assert paro_atendido(tmp_path, paro) is False
