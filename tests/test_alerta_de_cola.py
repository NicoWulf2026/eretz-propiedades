# -*- coding: utf-8 -*-
"""Que el aviso salga una vez, se repita con criterio, y no moleste de más.

**No se provoca un paro real.** Escribir `AGENCY_CERTIFICATION_STOP.json` en el
directorio de produccion haria parar a los dos workers en su proxima agencia, y
un test no puede detener la cola para comprobarse a si mismo. Todo corre sobre
un directorio temporal y con la notificacion desactivada: lo que se prueba es
**la decision** de avisar, no el ruido.

Los cinco casos que el §9 pide:

    A. PARO_DESATENDIDO                    -> avisa
    B. el mismo paro 5 minutos despues     -> NO avisa
    C. pasado el recordatorio              -> vuelve a avisar
    D. vuelve a OK                         -> se resetea
    E. un paro nuevo                       -> avisa de nuevo
"""
import json
import time

import pytest

from scripts import vigilante_de_paros as v


def cuando(minutos_atras: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S",
                         time.localtime(time.time() - minutos_atras * 60))


def estado(**campos) -> dict:
    base = {"stop_state": "PARO_DESATENDIDO",
            "stop_signature": "extraccion_transversal_de_atributos / FAMILIA",
            "paused_since": cuando(90), "agency": "roomix:la que sea",
            "minutes_paused": 90, "workers_alive": 0}
    base.update(campos)
    return base


# --- la clave de deduplicación ------------------------------------------

def test_la_clave_junta_firma_y_hora_de_pausa():
    """Ninguna de las dos alcanza sola: dos paros distintos pueden compartir
    firma, y el mismo paro conserva su hora."""
    c = v.clave_de_alerta(estado())
    assert "extraccion_transversal_de_atributos" in c
    assert estado()["paused_since"] in c


def test_los_estados_que_NO_alertan():
    """`PARO_RECIENTE` todavia esta dentro del umbral y puede resolverse solo.
    `PARO_DIAGNOSTICADO` ya tiene diferida escrita. `PARO_OPERACIONAL` lo
    pedimos nosotros. Ninguno saca a nadie de lo que esta haciendo."""
    for e in ("OK", "PARO_RECIENTE", "PARO_DIAGNOSTICADO", "PARO_OPERACIONAL"):
        assert v.clave_de_alerta(estado(stop_state=e)) is None


def test_cero_workers_alerta_aunque_no_haya_firma():
    """Nadie certificando y ninguna bandera que lo explique: el caso peor."""
    c = v.clave_de_alerta({"stop_state": "CERO_WORKERS_SIN_BANDERA"})
    assert c == "CERO_WORKERS"


# --- A, B, C, D, E ------------------------------------------------------

def test_A_un_paro_desatendido_avisa():
    hay, porque = v.decidir_alerta(estado(), {}, time.time(), 60)
    assert hay is True
    assert "nuevo" in porque


def test_B_el_mismo_paro_cinco_minutos_despues_NO_duplica():
    previo = {"alert_key": v.clave_de_alerta(estado()),
              "last_alert_at": cuando(5)}
    hay, porque = v.decidir_alerta(estado(), previo, time.time(), 60)
    assert hay is False
    assert "hace 5 min" in porque


def test_C_pasado_el_recordatorio_vuelve_a_avisar():
    previo = {"alert_key": v.clave_de_alerta(estado()),
              "last_alert_at": cuando(61)}
    hay, porque = v.decidir_alerta(estado(), previo, time.time(), 60)
    assert hay is True
    assert "recordatorio" in porque


def test_C_bis_justo_antes_del_recordatorio_todavia_no():
    previo = {"alert_key": v.clave_de_alerta(estado()),
              "last_alert_at": cuando(59)}
    hay, _ = v.decidir_alerta(estado(), previo, time.time(), 60)
    assert hay is False


def test_D_volver_a_OK_no_alerta():
    previo = {"alert_key": v.clave_de_alerta(estado()),
              "last_alert_at": cuando(5)}
    hay, _ = v.decidir_alerta(estado(stop_state="OK"), previo, time.time(), 60)
    assert hay is False


def test_E_un_paro_NUEVO_vuelve_a_avisar_aunque_comparta_firma():
    """Misma firma, otra hora de pausa: es otro episodio y hay que avisar.

    Este es el caso que una deduplicacion por firma sola se comeria: dos
    paradas distintas del mismo defecto transversal quedarian en silencio.
    """
    previo = {"alert_key": v.clave_de_alerta(estado(paused_since=cuando(300))),
              "last_alert_at": cuando(5)}
    hay, porque = v.decidir_alerta(estado(paused_since=cuando(90)), previo,
                                   time.time(), 60)
    assert hay is True
    assert "nuevo" in porque


def test_sin_registro_de_aviso_anterior_avisa():
    """Si el estado quedo a medias, se avisa. Callarse por un archivo roto es
    peor que un aviso de mas."""
    previo = {"alert_key": v.clave_de_alerta(estado()), "last_alert_at": None}
    hay, porque = v.decidir_alerta(estado(), previo, time.time(), 60)
    assert hay is True


# --- el ciclo completo, sobre disco y sin notificar ---------------------

@pytest.fixture
def entorno(tmp_path, monkeypatch):
    monkeypatch.setattr(v, "CERT", tmp_path)
    monkeypatch.setattr(v, "BANDERA", tmp_path / "AGENCY_CERTIFICATION_STOP.json")
    monkeypatch.setattr(v, "DIFERIDOS", tmp_path / "AGENCY_DEFECTS_DIFERIDOS.jsonl")
    monkeypatch.setattr(v, "ESTADO", tmp_path / "ERETZ_QUEUE_WATCH_STATUS.json")
    monkeypatch.setattr(v, "BITACORA", tmp_path / "ERETZ_QUEUE_WATCH.log")
    return tmp_path


def correr(entorno, **kw):
    import sys
    argv = sys.argv
    sys.argv = ["vigilante", "--sin-alerta"] + [
        f"--{k.replace('_', '-')}={x}" for k, x in kw.items()]
    try:
        v.main()
    finally:
        sys.argv = argv
    return json.loads((entorno / "ERETZ_QUEUE_WATCH_STATUS.json").read_text(
        encoding="utf-8"))


def poner_bandera(d, minutos):
    (d / "AGENCY_CERTIFICATION_STOP.json").write_text(json.dumps({
        "canonical_agency_id": "roomix:alguna", "componente": "x",
        "radio": "FAMILIA", "evidencia": "e",
        "cuando": cuando(minutos)}), encoding="utf-8")


def test_el_ciclo_entero_de_A_a_E(entorno, capsys):
    # A: paro desatendido -> avisa
    poner_bandera(entorno, 90)
    e1 = correr(entorno)
    assert e1["stop_state"] == "PARO_DESATENDIDO"
    assert e1["alert_key"] and e1["last_alert_at"]

    # B: el mismo paro otra vez -> no avisa, y `last_alert_at` no se mueve
    e2 = correr(entorno)
    assert e2["last_alert_at"] == e1["last_alert_at"]
    assert "sin aviso" in capsys.readouterr().out

    # D: vuelve a OK -> se limpia la clave
    (entorno / "AGENCY_CERTIFICATION_STOP.json").unlink()
    (entorno / v.CERROJO.format(0)).write_text(json.dumps({
        "pid": __import__("os").getpid(), "heartbeat": cuando(1),
        "current_agency": "roomix:otra"}), encoding="utf-8")
    e3 = correr(entorno)
    assert e3["stop_state"] == "OK"
    assert e3["alert_key"] is None and e3["last_alert_at"] is None

    # E: un paro nuevo -> vuelve a avisar
    poner_bandera(entorno, 45)
    e4 = correr(entorno)
    assert e4["stop_state"] == "PARO_DESATENDIDO"
    assert e4["last_alert_at"]

    # la bitacora tiene las transiciones y NINGUNA linea por chequeo normal
    lineas = (entorno / "ERETZ_QUEUE_WATCH.log").read_text(
        encoding="utf-8").strip().splitlines()
    transiciones = [l for l in lineas if "->" in l]
    assert any("PARO_DESATENDIDO" in l for l in transiciones)
    assert any("-> OK" in l for l in transiciones)
    # cuatro corridas, pero solo tres transiciones: la B no cambio nada
    assert len(transiciones) == 3, transiciones


def test_la_bitacora_no_crece_cuando_no_pasa_nada(entorno):
    """Cinco chequeos con la cola andando no dejan NI UNA linea.

    Y si nunca hubo una transicion, el archivo ni siquiera se crea: un log
    vacio que hay que abrir para ver que esta vacio tambien cuesta atencion.
    """
    (entorno / v.CERROJO.format(0)).write_text(json.dumps({
        "pid": __import__("os").getpid(), "heartbeat": cuando(1),
        "current_agency": "roomix:otra"}), encoding="utf-8")
    bitacora = entorno / "ERETZ_QUEUE_WATCH.log"
    for _ in range(5):
        correr(entorno)
    assert not bitacora.exists(), bitacora.read_text(encoding="utf-8")


# --- lo que ninguno de los tests de arriba probaba -----------------------
#
# Todos los de arriba pasan `--sin-alerta`, y el import de `avisar` vive
# ADENTRO de esa rama. O sea: la linea que se rompio el 2026-09-16 nunca se
# ejecutaba en la suite. Doce tests en verde y el vigilante fallando en
# produccion durante dos horas con la cola parada.

def test_la_rama_que_avisa_se_ejecuta_de_verdad(entorno, monkeypatch, capsys):
    """Con la notificacion interceptada, pero recorriendo el camino entero.

    `avisar` se reemplaza por un espia: no suena nada, pero el import y la
    llamada ocurren. Sin esto, un error en ese import queda invisible.
    """
    import sys
    llamadas = []
    # Se parchea `v.avisar`, NO el modulo de origen: desde que el import
    # subio al tope, el vigilante tiene su propia referencia y parchear la
    # fuente no lo alcanza.
    monkeypatch.setattr(v, "avisar",
                        lambda e, **k: llamadas.append(e) or {"espia": True})

    poner_bandera(entorno, 90)
    argv = sys.argv
    sys.argv = ["vigilante"]          # SIN --sin-alerta, a proposito
    try:
        v.main()
    finally:
        sys.argv = argv

    assert len(llamadas) == 1, "no se llamo a avisar()"
    estado = json.loads((entorno / "ERETZ_QUEUE_WATCH_STATUS.json").read_text(
        encoding="utf-8"))
    assert estado["last_alert_at"], "aviso pero no lo dejo registrado"


def test_si_falla_el_aviso_el_estado_IGUAL_se_escribe(entorno, monkeypatch):
    """El defecto que dejo el archivo congelado dos horas.

    Avisar es lo deseable; dejar constancia es lo obligatorio. Y `last_alert_at`
    tiene que quedar VACIO, para que el proximo chequeo vuelva a intentarlo en
    vez de creer que ya aviso.
    """
    import sys

    def revienta(estado, **k):
        raise RuntimeError("la notificacion se rompio")

    monkeypatch.setattr(v, "avisar", revienta)

    poner_bandera(entorno, 90)
    argv = sys.argv
    sys.argv = ["vigilante"]
    try:
        v.main()
    finally:
        sys.argv = argv

    estado = json.loads((entorno / "ERETZ_QUEUE_WATCH_STATUS.json").read_text(
        encoding="utf-8"))
    assert estado["stop_state"] == "PARO_DESATENDIDO"
    assert estado["last_alert_at"] is None
    assert "RuntimeError" in estado["alert_error"]


def test_corre_como_lo_corre_el_bat(tmp_path):
    """Como SUBPROCESO, desde la raiz, igual que la tarea programada.

    Este es el test que habria atrapado el ModuleNotFoundError. Los otros
    importan el modulo desde pytest, que ya tiene la raiz del repo en
    `sys.path`; el `.bat` no. Probar la funcion no es probar el programa.
    """
    import subprocess
    import sys
    from pathlib import Path
    raiz = Path(__file__).resolve().parents[1]
    r = subprocess.run(
        [sys.executable, "-u", "scripts/vigilante_de_paros.py",
         "--sin-alerta", "--sin-estado"],
        cwd=str(raiz), capture_output=True, text=True, timeout=120)
    assert "Traceback" not in (r.stderr or ""), r.stderr
    assert "ModuleNotFoundError" not in (r.stderr or ""), r.stderr
    assert r.returncode == 0, f"salio {r.returncode}: {r.stderr[-400:]}"
    assert "STOP_DETECTED_AT" in r.stdout
