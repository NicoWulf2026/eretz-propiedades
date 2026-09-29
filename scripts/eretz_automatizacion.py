# -*- coding: utf-8 -*-
"""ERETZ AUTOMATION ON / OFF: la cola de certificacion corriendo sola, o nada.

    python scripts/eretz_automatizacion.py on       (ERETZ_AUTOMATION_ON.cmd)
    python scripts/eretz_automatizacion.py off      (ERETZ_AUTOMATION_OFF.cmd)
    python scripts/eretz_automatizacion.py estado

ON
  - borra el interruptor `ERETZ_AUTOMATION_OFF.json` (ver `interruptor_eretz`)
    y la bandera de paro de radio APAGADO que dejo el OFF;
  - crea -o reemplaza, nunca duplica: `schtasks /Create /F` con el mismo
    nombre- dos tareas del usuario, con `pythonw.exe` (sin consola, sin
    ventanas) y `IgnoreNew` (una pasada a la vez):
      ERETZ_relanzador       cada 10 min + al iniciar sesion: relanza los
                             workers que falten, max 3 (segun ERETZ_WORKERS.json), respetando paros
      ERETZ_vigilante_paros  cada 5 min + al iniciar sesion: escribe
                             ERETZ_QUEUE_WATCH_STATUS.json. `--sin-alerta`: sin
                             toast, sin msg.exe, sin pitidos. Sin popups.
  - dispara el relanzador una vez para no esperar 10 minutos.

OFF
  - escribe el interruptor: desde ese momento ni el relanzador ni el runner
    arrancan workers, aunque alguien corra un .bat viejo;
  - deshabilita las tareas (las nuestras y las viejas ERETZ_cola_*) y termina
    las pasadas en curso. Deshabilitar y no borrar: el ON las rehace igual;
  - pide a los workers que paren con la bandera de paro (radio APAGADO): cada
    uno termina la agencia en curso y sale. Nunca pisa una bandera de un
    defecto, que ya los detiene. Con `--inmediato`, ademas, los termina.

Nada de esto toca produccion ni la huella: `database_writes: 0`.
Bitacora: ERETZ_AUTOMATION.log en la carpeta de salida.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Sequence
from xml.sax.saxutils import escape

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))

from interruptor_eretz import (BANDERA_DE_PARO, RADIO_APAGADO, SALIDA,  # noqa: E402
                               apagada, ruta as ruta_interruptor)

PYTHONW = Path(sys.executable).with_name("pythonw.exe")
BITACORA = "ERETZ_AUTOMATION.log"
WORKERS_MAXIMO = 3  # politica P5 (29-09); el regimen vigente lo fija ERETZ_WORKERS.json

# nombre -> (script, argumentos, minutos entre pasadas, log)
TAREAS: dict[str, tuple[str, list[str], int, str]] = {
    "ERETZ_relanzador": ("relanzar_la_cola.py", ["--lanzar"], 10, "relanzador.log"),
    "ERETZ_vigilante_paros": ("vigilante_de_paros.py", ["--sin-alerta"], 5, "vigilante.log"),
}
# Tareas de otras epocas que tambien relanzaban workers: el OFF las apaga si
# existen. El ON no las recrea (lanzaban workers sin mirar paros).
TAREAS_VIEJAS = ("ERETZ_cola_w0", "ERETZ_cola_w1", "ERETZ_cola_certificacion")

Ejecutar = Callable[[Sequence[str]], subprocess.CompletedProcess]


def _ejecutar(comando: Sequence[str]) -> subprocess.CompletedProcess:
    """schtasks sin ventana y sin colgarse."""
    return subprocess.run(list(comando), capture_output=True, text=True,
                          encoding="mbcs" if os.name == "nt" else "utf-8",
                          errors="replace", timeout=60,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _anotar(salida: Path, evento: dict) -> None:
    evento = {"cuando": time.strftime("%Y-%m-%dT%H:%M:%S"), **evento,
              "database_writes": 0}
    with (salida / BITACORA).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(evento, ensure_ascii=False) + "\n")


def _usuario() -> str:
    dominio = os.environ.get("USERDOMAIN")
    return f"{dominio}\\{getpass.getuser()}" if dominio else getpass.getuser()


def argumentos_de(nombre: str, salida: Path) -> str:
    script, extra, _, log = TAREAS[nombre]
    partes = [str(RAIZ / "scripts" / script), *extra, "--log", str(salida / log)]
    return " ".join(f'"{p}"' if " " in p else p for p in partes)


def xml_de_tarea(nombre: str, salida: Path, usuario: str, inicio: str,
                 pythonw: Path = PYTHONW) -> str:
    """La definicion completa. Sin `Duration` en la repeticion: indefinida."""
    _, _, minutos, _ = TAREAS[nombre]
    u = escape(usuario)
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>ERETZ AUTOMATION ({escape(nombre)}). Crear/apagar SOLO con ERETZ_AUTOMATION_ON.cmd / ERETZ_AUTOMATION_OFF.cmd.</Description>
  </RegistrationInfo>
  <Triggers>
    <TimeTrigger>
      <Repetition>
        <Interval>PT{minutos}M</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <StartBoundary>{inicio}</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>{u}</UserId>
      <Delay>PT2M</Delay>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{u}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>true</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT5M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(str(pythonw))}</Command>
      <Arguments>{escape(argumentos_de(nombre, salida))}</Arguments>
      <WorkingDirectory>{escape(str(RAIZ))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def existe(nombre: str, ejecutar: Ejecutar) -> bool:
    return ejecutar(["schtasks", "/Query", "/TN", nombre]).returncode == 0


def procesos_worker() -> dict[int, str]:
    """pid -> linea de comando de TODO proceso de la cola, registrado o no."""
    import psutil
    salida: dict[int, str] = {}
    for p in psutil.process_iter(["pid", "cmdline"]):
        try:
            linea = " ".join(p.info["cmdline"] or [])
        except (psutil.Error, TypeError):
            continue
        if "run_agency_certification_queue.py" in linea:
            salida[p.info["pid"]] = linea
    return salida


def encender(salida: Path = SALIDA, ejecutar: Ejecutar = _ejecutar,
             disparar: bool = True) -> dict:
    salida.mkdir(parents=True, exist_ok=True)
    informe: dict = {"accion": "ON", "tareas": {}}
    ruta_interruptor(salida).unlink(missing_ok=True)
    bandera = salida / BANDERA_DE_PARO
    try:
        if json.loads(bandera.read_text(encoding="utf-8")).get("radio") == RADIO_APAGADO:
            bandera.unlink()
            informe["bandera_apagado"] = "borrada"
    except (OSError, ValueError):
        pass  # sin bandera, o la de un defecto: esa no es nuestra y se queda
    inicio = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() + 60))
    usuario = _usuario()
    for nombre in TAREAS:
        xml = salida / f"{nombre}.xml"
        xml.write_text(xml_de_tarea(nombre, salida, usuario, inicio), encoding="utf-16")
        r = ejecutar(["schtasks", "/Create", "/TN", nombre, "/XML", str(xml), "/F"])
        informe["tareas"][nombre] = "creada" if r.returncode == 0 else (
            f"ERROR: {(r.stderr or r.stdout).strip()[:200]}")
    if disparar and informe["tareas"].get("ERETZ_relanzador") == "creada":
        r = ejecutar(["schtasks", "/Run", "/TN", "ERETZ_relanzador"])
        informe["relanzador_disparado"] = r.returncode == 0
    informe["ok"] = all(v == "creada" for v in informe["tareas"].values())
    _anotar(salida, informe)
    return informe


def apagar(salida: Path = SALIDA, ejecutar: Ejecutar = _ejecutar,
           inmediato: bool = False, esperar: int = 0, motivo: str = "") -> dict:
    salida.mkdir(parents=True, exist_ok=True)
    informe: dict = {"accion": "OFF", "tareas": {}}
    # 1. El interruptor primero: desde aca nadie relanza, ni la tarea que
    #    pudiera estar corriendo en este mismo segundo.
    tmp = ruta_interruptor(salida).with_suffix(".tmp")
    tmp.write_text(json.dumps({
        "cuando": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "motivo": motivo or "ERETZ_AUTOMATION_OFF", "database_writes": 0},
        ensure_ascii=False), encoding="utf-8")
    tmp.replace(ruta_interruptor(salida))
    # 2. Las tareas: deshabilitadas y sin pasada en curso.
    for nombre in (*TAREAS, *TAREAS_VIEJAS):
        if not existe(nombre, ejecutar):
            continue
        ejecutar(["schtasks", "/End", "/TN", nombre])
        r = ejecutar(["schtasks", "/Change", "/TN", nombre, "/DISABLE"])
        informe["tareas"][nombre] = "deshabilitada" if r.returncode == 0 else (
            f"ERROR: {(r.stderr or r.stdout).strip()[:200]}")
    # 3. Los workers: que paren al terminar la agencia en curso.
    bandera = salida / BANDERA_DE_PARO
    if bandera.exists():
        informe["bandera"] = "ya habia una bandera de paro: se respeta"
    else:
        bandera.write_text(json.dumps({
            "canonical_agency_id": "(apagado)", "componente": "automatizacion",
            "radio": RADIO_APAGADO, "evidencia": "ERETZ AUTOMATION OFF",
            "cuando": time.strftime("%Y-%m-%dT%H:%M:%S"), "database_writes": 0},
            ensure_ascii=False), encoding="utf-8")
        informe["bandera"] = "escrita (radio APAGADO)"
    limite = time.time() + max(0, esperar)
    vivos = procesos_worker()
    while vivos and time.time() < limite:
        time.sleep(5)
        vivos = procesos_worker()
    if vivos and inmediato:
        import psutil
        for pid in vivos:
            try:
                proceso = psutil.Process(pid)
                for hijo in proceso.children(recursive=True):
                    hijo.terminate()
                proceso.terminate()
            except psutil.Error:
                pass
        psutil.wait_procs([p for p in psutil.process_iter()
                           if p.pid in vivos], timeout=20)
        vivos = procesos_worker()
    informe["workers_vivos"] = sorted(vivos)
    informe["ok"] = all(not str(v).startswith("ERROR") for v in informe["tareas"].values())
    _anotar(salida, informe)
    return informe


def estado(salida: Path = SALIDA, ejecutar: Ejecutar = _ejecutar) -> dict:
    informe: dict = {"interruptor": apagada(salida) or "ON", "tareas": {}}
    for nombre in (*TAREAS, *TAREAS_VIEJAS):
        r = ejecutar(["schtasks", "/Query", "/TN", nombre, "/FO", "LIST", "/V"])
        if r.returncode != 0:
            if nombre in TAREAS:
                informe["tareas"][nombre] = "NO EXISTE"
            continue
        campos = {}
        for linea in r.stdout.splitlines():
            clave, _, valor = linea.partition(":")
            campos[clave.strip()] = valor.strip()
        informe["tareas"][nombre] = {
            k: v for k, v in campos.items()
            # Windows en castellano: «Hora próxima ejecución», con la tilde
            # a veces mal decodificada; se busca lo que no lleva acento.
            if any(x in k.lower() for x in ("status", "estado", "next run", "xima ejec",
                                            "last run", "tiempo de ejec", "result"))}
    informe["workers"] = procesos_worker()
    informe["workers_maximo"] = WORKERS_MAXIMO
    return informe


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = ap.add_subparsers(dest="accion", required=True)
    sub.add_parser("on")
    off = sub.add_parser("off")
    off.add_argument("--inmediato", action="store_true",
                     help="ademas de pedirles que paren, terminar los workers ya")
    off.add_argument("--esperar", type=int, default=0,
                     help="segundos a esperar que los workers salgan solos")
    off.add_argument("--motivo", default="")
    sub.add_parser("estado")
    args = ap.parse_args(argv)
    if args.accion == "on":
        informe = encender()
    elif args.accion == "off":
        informe = apagar(inmediato=args.inmediato, esperar=args.esperar,
                         motivo=args.motivo)
    else:
        informe = estado()
    print(json.dumps(informe, ensure_ascii=False, indent=2, default=str))
    if args.accion == "off" and informe.get("workers_vivos"):
        print("\nLos workers terminan la agencia en curso y salen solos. "
              "Para cortarlos ya: eretz_automatizacion.py off --inmediato")
    return 0 if informe.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
