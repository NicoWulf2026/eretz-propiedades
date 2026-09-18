# -*- coding: utf-8 -*-
"""El reporte tiene que notar cuando el vigilante deja de vigilar. §33, §52, §53.

El 2026-09-16 el vigilante estuvo dos horas fallando en silencio: la tarea
programada figuraba corriendo, pero el script reventaba antes de escribir su
estado. Nadie lo notó hasta que alguien fue a mirar a mano.

Por eso la salud se mide contra el **archivo que el vigilante escribe**, no
contra la tarea: una tarea que arranca y revienta figura como "corrió".
"""
import json
import time

from scripts.operacion_reporte import (alertas, eta, rendimiento,
                                       salud_del_vigilante)


def cuando(minutos_atras: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S",
                         time.localtime(time.time() - minutos_atras * 60))


def escribir_estado(d, **campos):
    (d / "ERETZ_QUEUE_WATCH_STATUS.json").write_text(
        json.dumps({"checked_at": cuando(2), "stop_state": "OK", **campos}),
        encoding="utf-8")


# --- §33: salud del vigilante -------------------------------------------

def test_un_vigilante_fresco_esta_sano(tmp_path):
    escribir_estado(tmp_path)
    r = salud_del_vigilante(tmp_path)
    assert r["estado"] == "OK"
    assert r["edad_minutos"] < 5


def test_un_vigilante_que_no_escribe_hace_dos_horas_esta_enfermo(tmp_path):
    """El caso real: la tarea corría, el script reventaba."""
    escribir_estado(tmp_path, checked_at=cuando(120))
    r = salud_del_vigilante(tmp_path)
    assert r["estado"] == "WATCHDOG_UNHEALTHY"
    assert "120 min" in r["detalle"]


def test_sin_artefacto_tampoco_esta_sano(tmp_path):
    r = salud_del_vigilante(tmp_path)
    assert r["estado"] == "WATCHDOG_SIN_ARTEFACTO"


def test_una_fecha_ilegible_no_se_lee_como_sana(tmp_path):
    """Callarse por un archivo roto es peor que un aviso de más."""
    escribir_estado(tmp_path, checked_at="ayer a la tarde")
    assert salud_del_vigilante(tmp_path)["estado"] == "WATCHDOG_UNHEALTHY"


def test_el_vigilante_enfermo_dispara_alerta_ALTA(tmp_path):
    escribir_estado(tmp_path, checked_at=cuando(120))
    datos = {"_vigilante": salud_del_vigilante(tmp_path)}
    cola = {"en_curso": [{"x": 1}]}
    a = alertas(cola, datos)
    assert any(x["nivel"] == "ALTA" and "vigilante" in x["que"] for x in a)


def test_si_detecto_pero_no_pudo_avisar_tambien_se_reporta(tmp_path):
    """Persistir es obligatorio, notificar es best effort: si el aviso falló,
    el estado sobrevive Y alguien tiene que enterarse de que falló."""
    escribir_estado(tmp_path, alert_error="ModuleNotFoundError: scripts")
    datos = {"_vigilante": salud_del_vigilante(tmp_path)}
    a = alertas({"en_curso": [{"x": 1}]}, datos)
    assert any("NO pudo avisar" in x["que"] for x in a)


# --- §53: tres caudales, no uno -----------------------------------------

def test_los_tres_caudales_son_distintos(tmp_path):
    """Una agencia puede tardar tres horas y aportar 800 propiedades, y otra
    tardar diez minutos y aportar cero. `agencias/hora` sola premia a la
    segunda, y por eso hay tres números y no uno."""
    filas = [
        # la misma agencia tres veces: dos son repeticiones, no avance
        {"canonical_agency_id": "roomix:a", "checked_at": cuando(60),
         "status": "NEEDS_FIX", "enumeration_audit": {"enumerated": 800},
         "operational_metrics": {"duration_seconds": 3600}},
        {"canonical_agency_id": "roomix:a", "checked_at": cuando(40),
         "status": "NEEDS_FIX", "enumeration_audit": {"enumerated": 800}},
        {"canonical_agency_id": "roomix:a", "checked_at": cuando(20),
         "status": "NEEDS_FIX", "enumeration_audit": {"enumerated": 800}},
        # una agencia nueva que cierra terminal con 800 propiedades
        {"canonical_agency_id": "roomix:b", "checked_at": cuando(30),
         "status": "CERTIFIED_COMPLETE",
         "enumeration_audit": {"enumerated": 800}},
    ]
    (tmp_path / "AGENCY_CERTIFICATION_RESULTS.jsonl").write_text(
        "".join(json.dumps(f) + "\n" for f in filas), encoding="utf-8")
    r = rendimiento(tmp_path, horas=2.0)
    assert r["corridas"] == 4                 # raw incluye repeticiones
    assert r["agencias_nuevas"] == 2          # intentos nuevos: a y b
    assert r['agencias_con_primer_cierre_exitoso'] == 1
    assert r['certified_throughput_agencias_nuevas_por_hora'] == 0.5
    assert r["propiedades_nuevas"] == 800     # useful: solo la terminal


def test_una_agencia_que_no_cierra_no_aporta_propiedades(tmp_path):
    """`NEEDS_FIX` con 800 enumeradas no es catálogo: es trabajo en curso."""
    filas = [{"canonical_agency_id": "roomix:a", "checked_at": cuando(10),
              "status": "NEEDS_FIX",
              "enumeration_audit": {"enumerated": 800}}]
    (tmp_path / "AGENCY_CERTIFICATION_RESULTS.jsonl").write_text(
        "".join(json.dumps(f) + "\n" for f in filas), encoding="utf-8")
    assert rendimiento(tmp_path, horas=1.0)["propiedades_nuevas"] == 0


# --- §52: la ETA se mueve con el caudal ---------------------------------

def test_sin_avance_no_hay_fecha():
    """Con cero agencias nuevas por hora, cualquier fecha sería inventada."""
    r = eta({"terminales": 100},
            {"certified_throughput_agencias_nuevas_por_hora": 0})
    assert r["estado"] == "SIN_ETA"


def test_la_fecha_se_mueve_cuando_se_mueve_el_ritmo():
    lento = eta({"terminales": 185},
                {"certified_throughput_agencias_nuevas_por_hora": 0.5})
    rapido = eta({"terminales": 185},
                 {"certified_throughput_agencias_nuevas_por_hora": 5.0})
    assert lento["horas_estimadas"] == rapido["horas_estimadas"] * 10
    assert lento["fecha_estimada"] > rapido["fecha_estimada"]


def test_los_pendientes_son_el_universo_y_no_la_cola_de_hoy():
    """Usar la cola actual daría una fecha optimista que ignora las 6.000 que
    todavía no entraron a ninguna cola."""
    r = eta({"terminales": 185},
            {"certified_throughput_agencias_nuevas_por_hora": 1.0})
    assert r["pendientes"] == 6597 - 185
