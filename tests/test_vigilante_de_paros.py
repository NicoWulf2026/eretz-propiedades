# -*- coding: utf-8 -*-
"""El vigilante mira y no toca. §18.

Los cinco estados se prueban con rutas desviadas a un directorio temporal. NO
se crea una bandera de paro de verdad: escribir
`AGENCY_CERTIFICATION_STOP.json` en el directorio real haría parar a los dos
workers en su próxima agencia, y un test no puede detener la cola de
producción para comprobarse a sí mismo.

Lo que estos tests fijan, además de los estados:

  - que el vigilante cuente workers por PROCESO VIVO y no por cerrojo
    presente. Un cerrojo huérfano diría "todo bien" con la cola parada, que es
    exactamente el error que el vigilante viene a evitar;
  - que NO escriba nada más que su archivo de estado. Si alguna vez toca el
    cerrojo, la bandera o los resultados, este test lo atrapa.
"""
import json
import time

import pytest

from scripts import vigilante_de_paros as v


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    """El vigilante, apuntando a un directorio de mentira."""
    monkeypatch.setattr(v, "CERT", tmp_path)
    monkeypatch.setattr(v, "BANDERA", tmp_path / "AGENCY_CERTIFICATION_STOP.json")
    monkeypatch.setattr(v, "DIFERIDOS", tmp_path / "AGENCY_DEFECTS_DIFERIDOS.jsonl")
    monkeypatch.setattr(v, "ESTADO", tmp_path / "ERETZ_QUEUE_WATCH_STATUS.json")
    # BITACORA tambien, y no es un detalle: sin desviarla estos tests
    # escribieron en el log de PRODUCCION el 2026-09-16, con nombres de
    # fixture -"alguna"- mezclados entre transiciones reales.
    monkeypatch.setattr(v, "BITACORA", tmp_path / "ERETZ_QUEUE_WATCH.log")
    return tmp_path


def cuando(minutos_atras: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S",
                         time.localtime(time.time() - minutos_atras * 60))


def poner_bandera(d, **campos):
    (d / "AGENCY_CERTIFICATION_STOP.json").write_text(
        json.dumps({"canonical_agency_id": "roomix:alguna",
                    "componente": "extraccion_transversal_de_atributos",
                    "radio": "FAMILIA", "evidencia": "algo",
                    **campos}, ensure_ascii=False), encoding="utf-8")


def poner_worker(d, i, vivo: bool):
    """Un cerrojo cuyo pid existe -el del propio test- o no."""
    import os
    pid = os.getpid() if vivo else 999_999
    (d / v.CERROJO.format(i)).write_text(
        json.dumps({"pid": pid, "heartbeat": cuando(1),
                    "current_agency": "roomix:la que sea"}), encoding="utf-8")


def correr(capsys, **kw) -> tuple[str, dict]:
    import sys
    # `--sin-alerta` NO es opcional aca. Sin el, estos tests mandaron avisos
    # de verdad -msg.exe a la sesion y pitidos- el 2026-09-16. Un test que
    # interrumpe a una persona no es un test, es una molestia.
    argv = (["vigilante", "--sin-alerta"]
            + [f"--{k.replace('_','-')}={x}" for k, x in kw.items()])
    monkey = sys.argv
    sys.argv = argv
    try:
        v.main()
    finally:
        sys.argv = monkey
    salida = capsys.readouterr().out
    estado = json.loads((v.ESTADO).read_text(encoding="utf-8"))
    return salida, estado


# --- los cinco estados --------------------------------------------------

def test_OK(entorno, capsys):
    poner_worker(entorno, 0, vivo=True)
    salida, estado = correr(capsys)
    assert "ESTADO: OK" in salida
    assert estado["stop_state"] == "OK"
    assert estado["workers_alive"] == 1


def test_CERO_WORKERS_SIN_BANDERA(entorno, capsys):
    """Nadie certificando y ningun paro que lo explique: el caso peor."""
    salida, estado = correr(capsys)
    assert "CERO_WORKERS_SIN_BANDERA" in salida
    assert estado["stop_state"] == "CERO_WORKERS_SIN_BANDERA"


def test_un_cerrojo_huerfano_no_cuenta_como_worker(entorno, capsys):
    """El pid 999.999 no existe. Si el vigilante lo contara, diria OK."""
    poner_worker(entorno, 0, vivo=False)
    salida, estado = correr(capsys)
    assert estado["workers_alive"] == 0
    assert estado["stop_state"] == "CERO_WORKERS_SIN_BANDERA"


def test_PARO_RECIENTE(entorno, capsys):
    poner_bandera(entorno, cuando=cuando(5))
    salida, estado = correr(capsys)
    assert "PARO_RECIENTE" in salida
    assert estado["stop_state"] == "PARO_RECIENTE"
    assert estado["minutes_paused"] == 5


def test_PARO_DESATENDIDO(entorno, capsys):
    """Las ocho horas de `fenix`, que es para lo que existe esto."""
    poner_bandera(entorno, cuando=cuando(8 * 60))
    salida, estado = correr(capsys)
    assert "PARO_DESATENDIDO" in salida
    assert estado["stop_state"] == "PARO_DESATENDIDO"
    assert estado["minutes_paused"] == 480
    assert estado["diagnosis_state"] == "SIN_DIAGNOSTICO"


def test_PARO_DIAGNOSTICADO(entorno, capsys):
    """Con diferida escrita despues del paro, ya no es desatendido."""
    poner_bandera(entorno, cuando=cuando(8 * 60))
    (entorno / "AGENCY_DEFECTS_DIFERIDOS.jsonl").write_text(
        json.dumps({"canonical_agency_id": "roomix:alguna",
                    "componente": "x", "radio": "FAMILIA",
                    "cuando": cuando(30)}) + "\n", encoding="utf-8")
    salida, estado = correr(capsys)
    assert "PARO_DIAGNOSTICADO" in salida
    assert estado["stop_state"] == "PARO_DIAGNOSTICADO"


def test_una_diferida_ANTERIOR_al_paro_no_lo_da_por_atendido(entorno, capsys):
    """Si la diferida es vieja, no explica el paro de ahora."""
    poner_bandera(entorno, cuando=cuando(60))
    (entorno / "AGENCY_DEFECTS_DIFERIDOS.jsonl").write_text(
        json.dumps({"canonical_agency_id": "roomix:alguna",
                    "componente": "x", "radio": "FAMILIA",
                    "cuando": cuando(600)}) + "\n", encoding="utf-8")
    salida, estado = correr(capsys)
    assert estado["stop_state"] == "PARO_DESATENDIDO"


def test_PARO_OPERACIONAL_no_dispara_alarma(entorno, capsys):
    """La bandera que ponemos nosotros para relanzar no es un defecto."""
    poner_bandera(entorno, cuando=cuando(600), radio="OPERACION",
                  componente="operacion, no defecto")
    salida, estado = correr(capsys)
    assert "PARO_OPERACIONAL" in salida
    assert estado["stop_state"] == "PARO_OPERACIONAL"


# --- que no toque nada --------------------------------------------------

def test_solo_escribe_sus_dos_archivos(entorno, capsys):
    """Estado y bitacora. NADA mas.

    Se enumera a proposito en vez de comprobar "no creo archivos": el dia que
    alguien agregue una tercera escritura, este test lo dice por nombre en vez
    de aflojarse solo. Y lo que importa de verdad esta abajo: el cerrojo, la
    bandera y los resultados quedan byte por byte como estaban.
    """
    poner_worker(entorno, 0, vivo=True)
    poner_bandera(entorno, cuando=cuando(5))
    (entorno / "AGENCY_CERTIFICATION_RESULTS.jsonl").write_text(
        "intacto", encoding="utf-8")
    antes = {p.name: p.read_bytes() for p in entorno.iterdir()}
    correr(capsys)
    despues = {p.name: p.read_bytes() for p in entorno.iterdir()}
    nuevos = set(despues) - set(antes)
    assert nuevos <= {"ERETZ_QUEUE_WATCH_STATUS.json",
                      "ERETZ_QUEUE_WATCH.log"}, nuevos
    for nombre, contenido in antes.items():
        assert despues[nombre] == contenido, f"toco {nombre}"


def test_no_relanza_ni_mata_nada(entorno, capsys, monkeypatch):
    """El §6: un STOP nuevo se ALERTA, no se reinicia.

    `fenix`, `building` y `benjamin ferreyra` demostraron que el paro puede
    estar protegiendonos de un defecto real. Si el vigilante llegara a lanzar
    un proceso o a matar uno, este test lo atrapa.
    """
    import subprocess
    llamadas = []
    real = subprocess.run

    def espia(args, *a, **k):
        llamadas.append(args)
        return real(args, *a, **k)

    monkeypatch.setattr(subprocess, "run", espia)
    poner_worker(entorno, 0, vivo=True)
    poner_bandera(entorno, cuando=cuando(600))
    correr(capsys)
    for c in llamadas:
        texto = " ".join(str(x) for x in (c if isinstance(c, list) else [c]))
        assert "run_agency_certification_queue" not in texto, texto
        assert "taskkill" not in texto.lower(), texto
        # `tasklist` es lo UNICO que corre, y solo pregunta si un pid existe
        assert texto.split()[0].lower() in ("tasklist",), texto


def test_con_sin_estado_no_escribe_absolutamente_nada(entorno, capsys):
    import sys
    poner_worker(entorno, 0, vivo=True)
    antes = sorted(p.name for p in entorno.iterdir())
    argv = sys.argv
    sys.argv = ["vigilante", "--sin-estado", "--sin-alerta"]
    try:
        v.main()
    finally:
        sys.argv = argv
    assert sorted(p.name for p in entorno.iterdir()) == antes
