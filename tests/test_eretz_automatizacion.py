# -*- coding: utf-8 -*-
"""ERETZ AUTOMATION ON/OFF sin tocar el Task Scheduler real (schtasks falso)."""
from __future__ import annotations

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

import eretz_automatizacion as A  # noqa: E402
import interruptor_eretz as I  # noqa: E402

NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}


class SchtasksFalso:
    def __init__(self, existentes=()):
        self.tareas = {n: True for n in existentes}  # nombre -> habilitada
        self.llamadas: list[list[str]] = []

    def __call__(self, comando):
        comando = list(comando)
        self.llamadas.append(comando)
        verbo, nombre = comando[1], comando[3]
        ok = subprocess.CompletedProcess(comando, 0, "", "")
        no = subprocess.CompletedProcess(comando, 1, "", "no existe")
        if verbo == "/Create":
            self.tareas[nombre] = True
            return ok
        if nombre not in self.tareas:
            return no
        if verbo == "/Change" and "/DISABLE" in comando:
            self.tareas[nombre] = False
        return ok


def test_la_tarea_no_abre_ventanas_ni_se_superpone_ni_caduca(tmp_path):
    for nombre in A.TAREAS:
        xml = A.xml_de_tarea(nombre, tmp_path, r"PC\usuario", "2026-09-28T15:00:00",
                             pythonw=Path(r"C:\Python\pythonw.exe"))
        raiz = ET.fromstring(xml.split("\n", 1)[1])
        assert raiz.find(".//t:Command", NS).text.endswith("pythonw.exe")
        assert raiz.find(".//t:MultipleInstancesPolicy", NS).text == "IgnoreNew"
        assert raiz.find(".//t:Hidden", NS).text == "true"
        assert raiz.find(".//t:TimeTrigger/t:Repetition/t:Duration", NS) is None
        assert raiz.find(".//t:LogonTrigger", NS) is not None
        assert raiz.find(".//t:LogonType", NS).text == "InteractiveToken"
        argumentos = raiz.find(".//t:Arguments", NS).text
        assert "--log" in argumentos


def test_MUERDE_el_vigilante_programado_nunca_muestra_popups(tmp_path):
    """Sin `--sin-alerta` el vigilante muestra un toast y un cuadro de msg.exe."""
    xml = A.xml_de_tarea("ERETZ_vigilante_paros", tmp_path, "u", "2026-09-28T15:00:00")
    assert "--sin-alerta" in xml
    assert "--lanzar" in A.xml_de_tarea("ERETZ_relanzador", tmp_path, "u",
                                        "2026-09-28T15:00:00")


def test_on_crea_sin_duplicar_y_borra_solo_el_apagado_propio(tmp_path):
    falso = SchtasksFalso(existentes=["ERETZ_relanzador"])
    I.ruta(tmp_path).write_text("{}", encoding="utf-8")
    (tmp_path / I.BANDERA_DE_PARO).write_text(
        json.dumps({"radio": I.RADIO_APAGADO}), encoding="utf-8")
    informe = A.encender(tmp_path, falso, disparar=False)
    assert informe["ok"]
    assert not I.ruta(tmp_path).exists()
    assert not (tmp_path / I.BANDERA_DE_PARO).exists()
    creates = [c for c in falso.llamadas if c[1] == "/Create"]
    assert all("/F" in c for c in creates)  # reemplaza, nunca duplica
    assert sorted(c[3] for c in creates) == sorted(A.TAREAS)


def test_on_no_borra_la_bandera_de_un_defecto(tmp_path):
    bandera = tmp_path / I.BANDERA_DE_PARO
    bandera.write_text(json.dumps({"radio": "FAMILIA"}), encoding="utf-8")
    A.encender(tmp_path, SchtasksFalso(), disparar=False)
    assert bandera.exists()


def test_MUERDE_off_apaga_todo_lo_que_relanza(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "procesos_worker", lambda: {})
    falso = SchtasksFalso(existentes=[*A.TAREAS, "ERETZ_cola_w0"])
    informe = A.apagar(tmp_path, falso)
    assert I.apagada(tmp_path)
    assert all(not habilitada for habilitada in falso.tareas.values())
    assert set(informe["tareas"]) == {*A.TAREAS, "ERETZ_cola_w0"}
    bandera = json.loads((tmp_path / I.BANDERA_DE_PARO).read_text(encoding="utf-8"))
    assert bandera["radio"] == I.RADIO_APAGADO


def test_off_no_pisa_la_bandera_de_un_defecto(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "procesos_worker", lambda: {})
    bandera = tmp_path / I.BANDERA_DE_PARO
    bandera.write_text(json.dumps({"radio": "COMPARTIDO", "x": 1}), encoding="utf-8")
    A.apagar(tmp_path, SchtasksFalso())
    assert json.loads(bandera.read_text(encoding="utf-8"))["radio"] == "COMPARTIDO"


def test_interruptor_ilegible_cuenta_como_apagado(tmp_path):
    assert I.apagada(tmp_path) is None
    I.ruta(tmp_path).write_text("{no es json", encoding="utf-8")
    assert "ilegible" in I.apagada(tmp_path)


def test_MUERDE_con_el_interruptor_el_relanzador_no_lanza_nada(tmp_path):
    import relanzar_la_cola as R
    I.ruta(tmp_path).write_text(json.dumps({"cuando": "2026-09-28T15:00:00"}),
                                encoding="utf-8")
    faltan, motivo, excluir = R.plan(tmp_path)
    assert faltan == [] and "OFF" in motivo and excluir == []


def test_MUERDE_con_el_interruptor_el_runner_no_arranca(tmp_path):
    I.ruta(tmp_path).write_text(json.dumps({"cuando": "x"}), encoding="utf-8")
    r = subprocess.run([sys.executable, str(RAIZ / "scripts" / "run_agency_certification_queue.py"),
                        "--ready", "--output", str(tmp_path), "--limit", "1"],
                       capture_output=True, text=True, timeout=120, cwd=str(RAIZ))
    assert r.returncode == 0
    assert "no se arranca" in r.stdout
