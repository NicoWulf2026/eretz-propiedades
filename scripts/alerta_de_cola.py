#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Que un paro de la cola llegue a una persona, no a un archivo.

No escribe en la base. `database_writes: 0`. No toca la cola, no toca cerrojos,
no mata ni relanza nada: muestra una notificación y hace un ruido.

Existe por una medición: en las 23 h que el vigilante cubrió entre el
2026-09-15 y el 2026-09-16, la cola estuvo parada **20,5 h — el 89 %**. El
vigilante las detectó todas y las escribió puntualmente. Nadie miró el archivo.
Un aviso que hay que acordarse de ir a leer no es un aviso.

Usa sólo lo que Windows ya tiene. En orden, y cae al siguiente si uno falla:

  1. un toast de Windows -WinRT, sin instalar nada-;
  2. `msg.exe`, que existe en las ediciones Pro;
  3. el log, que siempre queda.

El sonido va aparte del toast a propósito: si el toast falla, el ruido igual
suena, y el ruido es lo que hace que alguien mire.
"""
from __future__ import annotations

import subprocess

TITULO = "ERETZ — COLA DETENIDA"


def _texto(estado: dict) -> str:
    """Corto y con lo único que hace falta para decidir si levantarse."""
    agencia = (estado.get("agency") or "(sin agencia)").split(":")[-1]
    return (f"Estado: {estado.get('stop_state')}\n"
            f"Agencia: {agencia}\n"
            f"Firma: {estado.get('stop_signature') or '(sin firma)'}\n"
            f"Detenida desde: {estado.get('paused_since') or '(sin hora)'}\n"
            f"Minutos: {estado.get('minutes_paused') or '?'}  |  "
            f"Workers vivos: {estado.get('workers_alive')}")


def _ps(script: str, timeout: float = 25) -> bool:
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0 and "ERROR_ALERTA" not in (r.stdout or "")
    except Exception:
        return False


def _toast(titulo: str, cuerpo: str) -> bool:
    """El toast nativo. `AppId` tiene que ser uno REGISTRADO en el sistema; el
    de PowerShell lo está siempre, y por eso se usa ése y no uno inventado."""
    t = titulo.replace("'", "''")
    c = cuerpo.replace("'", "''")
    script = f"""
try {{
  [void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime]
  [void][Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType=WindowsRuntime]
  $app = '{{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}}\\WindowsPowerShell\\v1.0\\powershell.exe'
  $tpl = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(
           [Windows.UI.Notifications.ToastTemplateType]::ToastText02)
  $n = $tpl.GetElementsByTagName('text')
  $n.Item(0).AppendChild($tpl.CreateTextNode('{t}')) | Out-Null
  $n.Item(1).AppendChild($tpl.CreateTextNode('{c}')) | Out-Null
  $toast = [Windows.UI.Notifications.ToastNotification]::new($tpl)
  [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show($toast)
}} catch {{ Write-Output 'ERROR_ALERTA'; exit 1 }}
"""
    return _ps(script)


def _msg(titulo: str, cuerpo: str) -> bool:
    """`msg.exe` manda un cuadro a la sesión del usuario. No bloquea al que lo
    manda, que importa: esto corre desde una tarea programada."""
    texto = (titulo + "  ||  " + cuerpo.replace("\n", "  |  ")).replace('"', "'")
    try:
        r = subprocess.run(["msg", "*", "/TIME:600", texto],
                           capture_output=True, text=True, timeout=20)
        return r.returncode == 0
    except Exception:
        return False


def _sonido() -> None:
    """Tres pitidos. Va aparte del toast: si el toast falla, el ruido suena
    igual, y el ruido es lo que hace que alguien mire la pantalla."""
    _ps("[console]::beep(880,220); [console]::beep(660,220); "
        "[console]::beep(880,420)", timeout=15)


def avisar(estado: dict, con_sonido: bool = True) -> dict:
    """Devuelve por qué vías salió el aviso. No levanta excepciones: un fallo
    al notificar no puede tumbar al vigilante que lo llama."""
    cuerpo = _texto(estado)
    vias = {"toast": False, "msg": False, "sonido": False}
    try:
        vias["toast"] = _toast(TITULO, cuerpo)
        if not vias["toast"]:
            vias["msg"] = _msg(TITULO, cuerpo)
        if con_sonido:
            _sonido()
            vias["sonido"] = True
    except Exception:
        pass
    return vias


if __name__ == "__main__":
    # Prueba manual: `python scripts/alerta_de_cola.py`
    demo = {"stop_state": "PARO_DESATENDIDO",
            "agency": "roomix:ejemplo de prueba",
            "stop_signature": "prueba / FAMILIA",
            "paused_since": "2026-09-16T00:00:00",
            "minutes_paused": 45, "workers_alive": 0}
    print("PRUEBA — esto es un aviso de mentira, la cola no esta parada")
    print(avisar(demo))
