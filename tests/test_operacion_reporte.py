"""El estado en una pantalla: alertas que piden acción, no ruido."""
from __future__ import annotations

import json
import time

from scripts.operacion_reporte import (LATIDO_VENCIDO, alertas,
                                       estado_de_la_cola)


def _resultado(cid, status):
    return {"canonical_agency_id": cid, "status": status}


def _cerrojo(carpeta, nombre, edad_s, agencia="roomix:x", pid=1):
    (carpeta / nombre).write_text(json.dumps({
        "pid": pid, "heartbeat_epoch": time.time() - edad_s,
        "current_agency": agencia}), encoding="utf-8")


def test_un_progreso_viejo_no_es_un_runner_vivo(tmp_path):
    """Un archivo de progreso que quedó de una corrida muerta sigue nombrando
    una agencia. Contarlo como runner activo hace ver dos procesos donde no hay
    ninguno."""
    (tmp_path / "AGENCY_CERTIFICATION_PROGRESS.json").write_text(
        json.dumps({"current_agency": "roomix:fantasma",
                    "current_phase": "CERTIFY"}), encoding="utf-8")
    cola = estado_de_la_cola(tmp_path)
    assert cola["en_curso"] == []


def test_el_latido_decide_cuando_no_se_puede_ver_el_proceso(tmp_path, monkeypatch):
    """El latido sigue siendo el criterio de respaldo: cuando no se puede
    comprobar el pid, decide la edad."""
    from scripts import operacion_reporte as reporte

    monkeypatch.setattr(reporte, "_proceso_existe", lambda pid: None)
    _cerrojo(tmp_path, "AGENCY_CERTIFICATION_RUNNER.w0.lock", 10)
    _cerrojo(tmp_path, "AGENCY_CERTIFICATION_RUNNER.w1.lock", LATIDO_VENCIDO + 60)

    cola = estado_de_la_cola(tmp_path)
    assert len(cola["en_curso"]) == 1
    assert cola["cerrojos_huerfanos"] == ["AGENCY_CERTIFICATION_RUNNER.w1.lock"]


def test_needs_fix_no_cuenta_como_terminal(tmp_path):
    """`NEEDS_FIX` nunca es un cierre, y el reporte no puede sugerir que sí."""
    (tmp_path / "AGENCY_CERTIFICATION_RESULTS.jsonl").write_text(
        "\n".join(json.dumps(r) for r in (
            _resultado("a", "CERTIFIED_COMPLETE"),
            _resultado("b", "NEEDS_FIX"),
            _resultado("c", "BLOCKED_EXTERNAL"))) + "\n", encoding="utf-8")
    cola = estado_de_la_cola(tmp_path)
    assert cola["terminales"] == 2
    assert cola["needs_fix_abiertos"] == 1


def test_una_linea_rota_se_cuenta_y_no_tapa_el_reporte(tmp_path):
    """Ignorarla en silencio escondería justo la señal de que dos procesos
    escribieron el mismo artefacto."""
    (tmp_path / "AGENCY_CERTIFICATION_RESULTS.jsonl").write_text(
        json.dumps(_resultado("a", "CERTIFIED_COMPLETE")) + "\n{rota\n",
        encoding="utf-8")
    cola = estado_de_la_cola(tmp_path)
    assert cola["lineas_ilegibles"] == 1
    assert cola["agencias_con_resultado"] == 1


def test_una_inmobiliaria_bloqueada_no_es_una_alerta():
    """Es un hecho conocido del mundo, no algo que alguien tenga que hacer."""
    cola = {"en_curso": [{"cerrojo": "x"}], "por_estado": {"BLOCKED_EXTERNAL": 15}}
    datos = {"propiedades": 100, "publicables": 100,
             "perdidas_por_incompletitud": 0}
    assert alertas(cola, datos) == []


def test_perder_una_propiedad_real_es_alerta_alta():
    """La regla que no se negocia."""
    cola = {"en_curso": [{"cerrojo": "x"}]}
    datos = {"perdidas_por_incompletitud": 3}
    niveles = [a["nivel"] for a in alertas(cola, datos)]
    assert "ALTA" in niveles


def test_la_cola_parada_es_alerta_alta():
    """Nadie más la va a reabrir."""
    cola = {"paro_pedido": {"canonical_agency_id": "roomix:ami"}, "en_curso": []}
    a = alertas(cola, {"perdidas_por_incompletitud": 0})
    assert a and a[0]["nivel"] == "ALTA"
    assert "transversal" in a[0]["que"]


def test_el_pid_manda_sobre_el_latido(tmp_path, monkeypatch):
    """Un latido viejo con el proceso VIVO es un worker atascado en una
    inmobiliaria lenta, no un huérfano. La distinción importa porque la acción
    que sigue —liberar el cerrojo— pone un segundo runner sobre su partición.

    Pasó de verdad: `abriola propiedades` llevaba una hora y catorce minutos
    con el proceso corriendo y ya figuraba vencido.
    """
    from scripts import operacion_reporte as reporte

    _cerrojo(tmp_path, "AGENCY_CERTIFICATION_RUNNER.w0.lock",
             LATIDO_VENCIDO + 400, pid=4242)
    monkeypatch.setattr(reporte, "_proceso_existe", lambda pid: True)

    cola = estado_de_la_cola(tmp_path)
    assert cola["cerrojos_huerfanos"] == []
    assert len(cola["en_curso"]) == 1


def test_un_pid_muerto_con_latido_fresco_igual_es_huerfano(tmp_path, monkeypatch):
    """Un proceso que murió recién dejó un latido nuevo. El latido no puede
    ganarle al hecho de que el proceso no está."""
    from scripts import operacion_reporte as reporte

    _cerrojo(tmp_path, "AGENCY_CERTIFICATION_RUNNER.w0.lock", 5, pid=4242)
    monkeypatch.setattr(reporte, "_proceso_existe", lambda pid: False)

    cola = estado_de_la_cola(tmp_path)
    assert cola["cerrojos_huerfanos"] == ["AGENCY_CERTIFICATION_RUNNER.w0.lock"]


def test_sin_poder_comprobar_el_pid_decide_el_latido(tmp_path, monkeypatch):
    """No saber no autoriza a inventar: se vuelve al criterio anterior."""
    from scripts import operacion_reporte as reporte

    _cerrojo(tmp_path, "AGENCY_CERTIFICATION_RUNNER.w0.lock", 5, pid=4242)
    monkeypatch.setattr(reporte, "_proceso_existe", lambda pid: None)
    assert estado_de_la_cola(tmp_path)["cerrojos_huerfanos"] == []

    _cerrojo(tmp_path, "AGENCY_CERTIFICATION_RUNNER.w1.lock",
             LATIDO_VENCIDO + 100, pid=4243)
    assert "AGENCY_CERTIFICATION_RUNNER.w1.lock" in \
        estado_de_la_cola(tmp_path)["cerrojos_huerfanos"]
