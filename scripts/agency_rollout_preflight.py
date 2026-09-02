#!/usr/bin/env python
"""Comprueba que la cola se puede reabrir sin pisar nada.

Reabrir el rollout a ciegas es como se rompe la recuperabilidad: dos runners
sobre el mismo checkpoint, o un checkpoint que apunta a una cola que ya no
existe, o codigo sin commitear que no se corresponde con lo que quedo
registrado en los paquetes.

Cada chequeo dice que mira y por que. Si alguno falla, la salida es distinta de
cero y la cola NO deberia abrirse.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.agency_certifier import load_catalog
from scripts.run_agency_certification_queue import (CERROJO, LATIDO_VENCIDO,
                                                    TERMINAL, full_queue,
                                                    is_current_result,
                                                    latest_results,
                                                    queue_fingerprint,
                                                    ready_queue)

RAIZ = Path(__file__).resolve().parents[1]


def sin_otro_runner(salida: Path) -> tuple[bool, str]:
    """Un segundo runner se pisa el cursor con el primero y le pide a las
    mismas fuentes el mismo inventario, al doble del ritmo acordado."""
    ruta = salida / CERROJO
    if not ruta.exists():
        return True, "no hay cerrojo tomado"
    try:
        previo = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False, f"hay un cerrojo ilegible en {ruta}"
    edad = time.time() - float(previo.get("heartbeat_epoch") or 0)
    if edad < LATIDO_VENCIDO:
        return False, (f"runner activo pid {previo.get('pid')} en "
                       f"{previo.get('current_agency')}, latido hace {edad:.0f}s")
    return True, f"cerrojo vencido hace {edad:.0f}s, se puede tomar"


def checkpoint_coherente(salida: Path, cola: list[str],
                         modo: str) -> tuple[bool, str]:
    """El checkpoint tiene que describir la cola que se va a correr.

    Si describe otra, el cursor que guarda no significa nada sobre esta.
    """
    ruta = salida / "AGENCY_CERTIFICATION_PROGRESS.json"
    if not ruta.exists():
        return True, "sin checkpoint previo: arranca de cero"
    try:
        previo = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False, "el checkpoint no se puede leer"
    esperada = queue_fingerprint(cola, modo)
    if previo.get("queue_fingerprint") != esperada:
        return True, (f"la cola cambio ({previo.get('mode')} -> {modo}); el "
                      f"cursor se recalcula desde los resultados persistidos")
    return True, (f"coincide con la cola de {modo}, cursor "
                  f"{previo.get('global_cursor')}")


def huellas_al_dia(salida: Path,
                   catalogo: dict[str, dict[str, Any]]) -> tuple[bool, str]:
    """Cuantas certificaciones quedaron obsoletas por cambios de codigo.

    No es un fallo: es el trabajo que la cola va a rehacer antes de sumar
    cobertura nueva, y conviene saberlo antes de abrirla.
    """
    resultados = latest_results(salida)
    obsoletas = [k for k, r in resultados.items()
                 if r.get("status") in TERMINAL and k in catalogo
                 and not is_current_result(r, catalogo[k])]
    return True, f"{len(obsoletas)} certificaciones a rehacer por huella"


def git_coherente() -> tuple[bool, str]:
    """Codigo sin commitear significa que lo que corre no es lo que quedo
    registrado en los paquetes, y despues no se puede reconstruir que produjo
    cada certificacion."""
    try:
        salida = subprocess.run(
            ["git", "status", "--porcelain"], cwd=RAIZ, capture_output=True,
            text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as error:
        return False, f"no se pudo consultar git: {error}"
    sucio = [l for l in salida.stdout.splitlines() if l.strip()]
    if sucio:
        return False, f"{len(sucio)} archivos sin commitear"
    return True, "arbol limpio"


def hay_trabajo(salida: Path, cola: list[str],
                catalogo: dict[str, dict[str, Any]]) -> tuple[bool, str]:
    resultados = latest_results(salida)
    pendientes = [k for k in cola
                  if not is_current_result(resultados.get(k, {}), catalogo[k])]
    if not pendientes:
        return False, "no queda ninguna pendiente en esta cola"
    return True, f"{len(pendientes)} pendientes; la proxima es {pendientes[0]}"


def sin_defectos_abiertos(salida: Path) -> tuple[bool, str]:
    """`NEEDS_FIX` nunca es un cierre: no se abre la cola con uno pendiente."""
    resultados = latest_results(salida)
    abiertos = [k for k, r in resultados.items()
                if r.get("status") == "NEEDS_FIX"]
    if abiertos:
        return False, f"{len(abiertos)} sin resolver: {abiertos[:5]}"
    return True, "ninguno abierto"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v2-dir", default=r"D:\INMO CAPITAL\ERETZ_SUPABASE_RECONCILIATION_V2_20260827")
    parser.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    parser.add_argument("--platform-directory", default=r"D:\INMO CAPITAL\agency_platform_directory.jsonl")
    parser.add_argument("--output", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
    parser.add_argument("--full", action="store_true",
                        help="comprobar contra la cola completa, no --ready")
    args = parser.parse_args()

    salida = Path(args.output)
    catalogo = load_catalog(Path(args.v2_dir), Path(args.data_dir),
                            Path(args.platform_directory))
    cola = full_queue(catalogo) if args.full else ready_queue(catalogo)
    modo = "full" if args.full else "ready"

    chequeos = [
        ("no hay otro runner", sin_otro_runner(salida)),
        ("checkpoint coherente", checkpoint_coherente(salida, cola, modo)),
        ("huellas", huellas_al_dia(salida, catalogo)),
        ("git coherente", git_coherente()),
        ("hay trabajo pendiente", hay_trabajo(salida, cola, catalogo)),
        ("sin NEEDS_FIX abiertos", sin_defectos_abiertos(salida)),
    ]

    print(f"cola {modo}: {len(cola)} inmobiliarias")
    fallos = 0
    for nombre, (ok, detalle) in chequeos:
        marca = "OK  " if ok else "FALLA"
        fallos += 0 if ok else 1
        print(f"  [{marca}] {nombre}: {detalle}")
    print()
    print("LISTA PARA ABRIR" if not fallos
          else f"NO ABRIR: {fallos} chequeo(s) en falla")
    return 0 if not fallos else 1


if __name__ == "__main__":
    raise SystemExit(main())
