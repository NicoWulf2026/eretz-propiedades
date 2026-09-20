#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Nada relanzaba la cola, y eso costaba mas que todos los defectos juntos.

No escribe en produccion, no cambia extractores, no cambia huellas.
`database_writes: 0`. Lo unico que hace es lanzar procesos de la cola, y solo
cuando es seguro.

La medicion que lo justifica
----------------------------
Sobre las 2.501 corridas del historial completo, uniendo intervalos y contando
como parada cualquier hueco de mas de 20 minutos:

    span del historial      487,6 h
    tiempo ACTIVO           121,6 h
    tiempo PARADA           366,0 h   (75 %)
    episodios de parada     167

Y el reparto importa mas que el total: **117 de los 167 huecos no coinciden con
ningun paro registrado**, y suman **190,6 h -el 52 % de las horas paradas-**.
No son defectos: es la cola simplemente no corriendo. Proceso muerto, nadie
relanzo, maquina apagada.

Eliminar esa clase de hueco lleva el duty cycle del 25 % al **64 %** medido.
Ningun arreglo semantico del tablero se acerca a ese factor.

Y la infraestructura ya existia, apagada: `ERETZ_cola_w0` y `ERETZ_cola_w1`
estan en estado Ready con `NextRunTime` **vacio** y su ultima corrida es del
2026-09-09; `ERETZ_cola_certificacion` esta agendada para **2027-09-04**. Los
workers que corrieron el 17 los lanzo alguien a mano.

Que NO hace, y por que
----------------------
**No relanza sobre un paro sin diagnosticar.** Esa es la regla que no se
relaja: un paro transversal significa que sospechamos del codigo, y volver a
correrlo produce certificaciones que habria que rehacer. Relanzar tras un
**corte por lote** -salida limpia y planificada- o tras una **muerte del
proceso** si es legitimo, y son justamente los 117 huecos que cuestan las
190,6 h.

Un paro se considera atendido cuando hay una diferida firmada para esa agencia
escrita DESPUES del paro. No alcanza con que exista una diferida vieja: si el
paro es posterior, es informacion nueva.

**Nunca mas de 2 workers.** Se comprueba tres veces, y ninguna sobra: aca antes
de lanzar, el `MultipleInstancesPolicy: IgnoreNew` de la tarea, y el cerrojo
por worker del propio runner, que verifica PID vivo y latido.

Uso:
    python scripts/relanzar_la_cola.py            # dice que haria
    python scripts/relanzar_la_cola.py --lanzar
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

SALIDA = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
BITACORA = SALIDA / "ERETZ_RELANZAMIENTOS.jsonl"
WORKERS = 2


def _fecha(texto: str | None) -> float | None:
    if not texto:
        return None
    try:
        import datetime
        return datetime.datetime.fromisoformat(str(texto)[:19]).timestamp()
    except ValueError:
        return None


def paro_vigente(salida: Path) -> dict[str, Any] | None:
    """El paro escrito por un worker para el otro, si sigue en pie."""
    ruta = salida / "AGENCY_CERTIFICATION_STOP.json"
    if not ruta.exists():
        return None
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # Ilegible es peor que ausente: no se relanza a ciegas.
        return {"canonical_agency_id": "ilegible", "cuando": None}


def paro_atendido(salida: Path, paro: dict[str, Any]) -> bool:
    """Hay una diferida firmada para esa agencia, escrita DESPUES del paro.

    Una diferida vieja no alcanza. Si el paro es posterior, trae informacion
    que esa diferida no pudo haber tenido en cuenta.
    """
    agencia = paro.get("canonical_agency_id")
    cuando = _fecha(paro.get("cuando"))
    if not agencia or cuando is None:
        return False
    ruta = salida / "AGENCY_DEFECTS_DIFERIDOS.jsonl"
    if not ruta.exists():
        return False
    for linea in ruta.open(encoding="utf-8", errors="replace"):
        linea = linea.strip()
        if not linea:
            continue
        try:
            fila = json.loads(linea)
        except ValueError:
            continue
        if fila.get("canonical_agency_id") != agencia:
            continue
        firmada = _fecha(fila.get("cuando"))
        if firmada is not None and firmada >= cuando:
            return True
    return False


def workers_vivos(salida: Path) -> dict[int, int]:
    """Que workers tienen cerrojo con un PID que sigue existiendo."""
    import psutil
    vivos: dict[int, int] = {}
    for worker in range(WORKERS):
        ruta = salida / f"AGENCY_CERTIFICATION_RUNNER.w{worker}.lock"
        if not ruta.exists():
            continue
        try:
            previo = json.loads(ruta.read_text(encoding="utf-8"))
            pid = int(previo["pid"])
        except (OSError, ValueError, KeyError, TypeError):
            # Cerrojo ilegible: se trata como ocupado. El runner tiene la
            # misma politica y por una razon buena: borrarlo a ciegas es como
            # se terminan pisando dos procesos el mismo checkpoint.
            vivos[worker] = -1
            continue
        if pid > 0 and psutil.pid_exists(pid):
            vivos[worker] = pid
    return vivos


def decidir(salida: Path) -> tuple[list[int], str]:
    """Que workers lanzar, y por que no los otros."""
    paro = paro_vigente(salida)
    if paro is not None and not paro_atendido(salida, paro):
        return [], (f"paro sin diagnosticar en "
                    f"{paro.get('canonical_agency_id')} "
                    f"({paro.get('componente')}, radio {paro.get('radio')}): "
                    f"no se relanza hasta que haya una diferida firmada")
    vivos = workers_vivos(salida)
    faltan = [w for w in range(WORKERS) if w not in vivos]
    if not faltan:
        return [], f"los {WORKERS} workers ya estan vivos: {vivos}"
    return faltan, (f"faltan {len(faltan)} de {WORKERS}"
                    + (f"; vivos: {vivos}" if vivos else ""))


def lanzar(worker: int, salida: Path) -> int:
    """Un worker desprendido, con su log propio."""
    log = salida / f"cola_w{worker}.log"
    comando = [sys.executable, "-u",
               str(RAIZ / "scripts" / "run_agency_certification_queue.py"),
               "--ready", "--workers", str(WORKERS), "--worker", str(worker),
               "--limit", "0"]
    with log.open("a", encoding="utf-8", errors="replace") as fh:
        fh.write(f"\n=== relanzado por relanzar_la_cola.py "
                 f"{time.strftime('%Y-%m-%dT%H:%M:%S')} ===\n")
        fh.flush()
        proceso = subprocess.Popen(
            comando, cwd=str(RAIZ), stdout=fh, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    return proceso.pid


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lanzar", action="store_true")
    ap.add_argument("--salida", default=str(SALIDA))
    args = ap.parse_args()
    salida = Path(args.salida)

    faltan, motivo = decidir(salida)
    print(f"{time.strftime('%Y-%m-%dT%H:%M:%S')}  {motivo}")
    if not faltan:
        print("nada que lanzar")
        return 0
    print(f"a lanzar: workers {faltan}")
    if not args.lanzar:
        print("\n  DRY-RUN. Para lanzar de verdad: --lanzar")
        print("\ndatabase_writes: 0")
        return 0

    lanzados = {}
    for worker in faltan:
        try:
            lanzados[worker] = lanzar(worker, salida)
        except OSError as error:
            print(f"  worker {worker}: NO se pudo lanzar ({error})")
    with BITACORA.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "cuando": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "motivo": motivo, "lanzados": lanzados,
            "database_writes": 0}, ensure_ascii=False) + "\n")
    for worker, pid in lanzados.items():
        print(f"  worker {worker} -> pid {pid}")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
