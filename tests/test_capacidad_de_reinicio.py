# -*- coding: utf-8 -*-
"""Tener disparador no es lo mismo que volver a correr.

`ERETZ_cola_w0` y `ERETZ_cola_w1` tienen un disparador cada una y su
`NextRunTime` está **vacío**: no vuelven a ejecutarse nunca.
`ERETZ_cola_certificacion` tiene próxima ejecución para septiembre de **2027**.

La primera versión de esta comprobación contaba disparadores y daba `OK` sobre
un sistema que no se reinicia solo. El campo que decide es la próxima
ejecución.

Y explica el mecanismo detrás del número que más duele: 9 de 58 paros se
llevaron el 80% de las horas perdidas, con máximos de 15, 17 y 18 horas, cuando
la mediana de diagnóstico es de 8 minutos. No tarda el diagnóstico: después de
resolverlo hay que estar para volver a encender la cola.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))

import operacion_reporte as reporte  # noqa: E402


class _Salida:
    def __init__(self, filas):
        self.stdout = json.dumps(filas)


def fingir(monkeypatch, filas):
    monkeypatch.setattr(reporte.subprocess, "run",
                        lambda *a, **k: _Salida(filas))
    return reporte.capacidad_de_reinicio()


def dentro_de(dias: int) -> str:
    return time.strftime("%m/%d/%Y %H:%M:%S",
                         time.localtime(time.time() + dias * 86400))


def test_MUERDE_disparador_con_proxima_vacia_no_es_reinicio(monkeypatch):
    """El caso real: las tres tareas tienen disparador y ninguna vuelve a correr."""
    salida = fingir(monkeypatch, [
        {"nombre": "ERETZ_cola_w0", "disparadores": 1, "proxima": "",
         "ultima": "09/09/2026 14:17:10", "resultado": 2},
        {"nombre": "ERETZ_cola_w1", "disparadores": 1, "proxima": "",
         "ultima": "09/09/2026 14:17:10", "resultado": 2},
        {"nombre": "ERETZ_cola_certificacion", "disparadores": 1,
         "proxima": "09/04/2027 08:30:02", "ultima": "09/06/2026 20:44:13",
         "resultado": 267014},
    ])
    assert salida["estado"] == "SIN_REINICIO_AUTOMATICO"
    assert len(salida["sin_proxima_ejecucion"]) == 3


def test_una_proxima_ejecucion_a_un_ano_no_cuenta(monkeypatch):
    """Un disparador para dentro de un año es un disparador olvidado."""
    salida = fingir(monkeypatch, [
        {"nombre": "a", "disparadores": 1, "proxima": dentro_de(400)},
        {"nombre": "b", "disparadores": 1, "proxima": dentro_de(400)},
    ])
    assert salida["estado"] == "SIN_REINICIO_AUTOMATICO"


def test_con_proximas_ejecuciones_reales_da_ok(monkeypatch):
    """La comprobación tiene que poder decir que sí: si nunca da OK, es ruido."""
    salida = fingir(monkeypatch, [
        {"nombre": "a", "disparadores": 1, "proxima": dentro_de(0)},
        {"nombre": "b", "disparadores": 1, "proxima": dentro_de(0)},
        {"nombre": "c", "disparadores": 1, "proxima": dentro_de(1)},
    ])
    assert salida["estado"] == "OK"
    assert salida["sin_proxima_ejecucion"] == []


def test_no_crea_ni_modifica_ninguna_tarea(monkeypatch):
    """La contención es el punto, no un detalle.

    Ponerle un disparador útil a estas tareas equivale a reiniciar la cola
    después de CUALQUIER parada, incluida una no diagnosticada, y eso está
    prohibido: un STOP nuevo se avisa, no se reinicia.
    """
    llamadas = []

    class _Espia(_Salida):
        def __init__(self, filas, cmd):
            super().__init__(filas)
            llamadas.append(cmd)

    monkeypatch.setattr(reporte.subprocess, "run",
                        lambda *a, **k: _Espia([], a[0] if a else []))
    reporte.capacidad_de_reinicio()
    texto = " ".join(" ".join(map(str, c)) for c in llamadas).lower()
    for prohibido in ("register-scheduledtask", "set-scheduledtask",
                      "start-scheduledtask", "enable-scheduledtask",
                      "new-scheduledtask"):
        assert prohibido not in texto


def test_si_powershell_falla_no_tumba_el_reporte(monkeypatch):
    """Saber esto nunca puede costar el resto del tablero."""
    def explota(*a, **k):
        raise OSError("no hay powershell")
    monkeypatch.setattr(reporte.subprocess, "run", explota)
    salida = reporte.capacidad_de_reinicio()
    assert salida["estado"] == "NO_SE_PUDO_COMPROBAR"


def test_una_tarea_ausente_se_informa_aparte(monkeypatch):
    """Que falte no es lo mismo que que exista y no corra."""
    salida = fingir(monkeypatch, [
        {"nombre": "a", "disparadores": -1},
        {"nombre": "b", "disparadores": 1, "proxima": dentro_de(0)},
    ])
    assert salida["ausentes"] == ["a"]
