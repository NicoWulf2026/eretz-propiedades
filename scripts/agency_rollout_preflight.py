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
from scripts.defect_triage import CONTINUE, clasificar
from scripts.preingestion_manifest import base_canonica, describir
from scripts.agency_fingerprints import (FINGERPRINT_SCHEMA_VERSION,
                                         strategy_fingerprint,
                                         strategy_fingerprint_v1, strategy_for)
from scripts.run_agency_certification_queue import (CERROJO, LATIDO_VENCIDO,
                                                    TERMINAL, choose_connector,
                                                    diferidos, full_queue,
                                                    is_current_result,
                                                    latest_results,
                                                    paro_ya_diagnosticado,
                                                    queue_fingerprint,
                                                    ready_queue)

RAIZ = Path(__file__).resolve().parents[1]


def sin_otro_runner(salida: Path) -> tuple[bool, str]:
    """Un segundo runner se pisa el cursor con el primero y le pide a las
    mismas fuentes el mismo inventario, al doble del ritmo acordado.

    Se miran TODOS los cerrojos, no solo el de un worker. Con dos workers los
    cerrojos se llaman `...RUNNER.w0.lock` y `...RUNNER.w1.lock`, y buscar
    unicamente el nombre de un worker respondia "no hay cerrojo tomado" con
    dos procesos corriendo: justo lo que este chequeo existe para impedir.
    """
    patron = Path(CERROJO).stem + "*" + Path(CERROJO).suffix
    cerrojos = sorted(salida.glob(patron))
    if not cerrojos:
        return True, "no hay cerrojo tomado"
    activos, vencidos = [], []
    for ruta in cerrojos:
        try:
            previo = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False, f"hay un cerrojo ilegible en {ruta}"
        edad = time.time() - float(previo.get("heartbeat_epoch") or 0)
        if edad < LATIDO_VENCIDO:
            activos.append(f"{ruta.name}: pid {previo.get('pid')} en "
                           f"{previo.get('current_agency')}, latido hace "
                           f"{edad:.0f}s")
        else:
            vencidos.append(f"{ruta.name} hace {edad:.0f}s")
    if activos:
        return False, "runner activo -- " + "; ".join(activos)
    return True, f"{len(vencidos)} cerrojo(s) vencido(s): {'; '.join(vencidos)}"


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


def huella_vigente(resultado: dict[str, Any],
                   registro: dict[str, dict[str, Any]]) -> bool:
    """Si el veredicto lo produjo el codigo que corre hoy.

    No se usa `is_current_result`: esa devuelve False de entrada para cualquier
    estado NO TERMINAL, y `NEEDS_FIX` no lo es. Preguntarle por un defecto daria
    siempre "vencido" y habria desactivado el guardian en silencio.
    """
    guardada = resultado.get("strategy_fingerprint")
    if not guardada:
        # Sin huella registrada no se puede demostrar que este vencido, y ante
        # la duda el defecto sigue abierto.
        return True
    conector = resultado.get("connector") or choose_connector(registro)
    estrategia = resultado.get("connector_strategy") or strategy_for(
        conector, resultado.get("publication_mechanism"))
    if resultado.get("fingerprint_schema_version") != FINGERPRINT_SCHEMA_VERSION:
        # El paquete se emitio con otra definicion de huella. Comparar contra
        # la actual no responde nada -todo difiere por construccion- y dejarlo
        # pasar convertiria el cambio de modelo en una amnistia silenciosa para
        # todos los defectos abiertos. Se recomputa con el algoritmo de SU
        # esquema, que es lo unico que contesta la pregunta real: cambio el
        # comportamiento desde que se emitio este veredicto.
        return guardada == strategy_fingerprint_v1(conector, estrategia)
    return guardada == strategy_fingerprint(conector, estrategia)


def sin_defectos_abiertos(salida: Path,
                          catalogo: dict[str, dict[str, Any]]
                          ) -> tuple[bool, str]:
    """`NEEDS_FIX` nunca es un cierre: no se abre la cola con uno pendiente.

    Pendiente quiere decir que su huella SIGUE VIGENTE: el veredicto lo produjo
    el codigo que hoy corre, nadie lo corrigio, y reabrir seria caminar hacia la
    misma parada. Ese caso bloquea, que es el peligroso.

    Cuando la huella cambio, en cambio, ese veredicto lo emitio codigo que ya no
    existe. No es un defecto abierto sino evidencia vencida, y volver a
    evaluarla es exactamente para lo que esta la cola.

    Sin la distincion el protocolo queda en deadlock: el paquete solo se limpia
    recertificando y recertificar exige reabrir, asi que un solo `NEEDS_FIX`
    cerraba la cola para siempre.

    **Y bloquea el que la politica de triage habria parado, no cualquiera.** Un
    defecto de radio acotado -el sitio caido, el que nos bloquea, el que se
    quedo sin tiempo- es por definicion uno que la cola atraviesa sin detenerse:
    exigir que este resuelto para reabrir contradice la politica que dice
    seguir. `varelanegociosinmobiliarios.com` no respondia y dejaba la cola
    cerrada esperando que un servidor ajeno volviera.

    La clasificacion se RECALCULA sobre el resultado guardado en vez de leer el
    veredicto que quedo escrito: un veredicto lo produjo el triage de ese
    momento, y si el triage cambio -como cambio al dejar de leer un sitio
    inaccesible como perdida sistematica- el registro viejo ya no dice la
    verdad. Es el mismo criterio que las huellas.

    **Y tampoco bloquea el que ya se difirio con firma.** Si el runner va a
    atravesar ese paro -porque alguien escribio el diagnostico, el componente y
    el radio en la lista de diferidas-, exigir que este resuelto para reabrir
    reintroduce el mismo deadlock por otra puerta: el preflight cerraria la cola
    esperando un arreglo que la propia politica decidio postergar. Las dos
    puertas tienen que leer la misma lista.
    """
    resultados = latest_results(salida)
    pospuestos = diferidos(salida)
    abiertos, vencidos, acotados, postergados = [], [], [], []
    for clave, resultado in resultados.items():
        if resultado.get("status") != "NEEDS_FIX":
            continue
        triage = clasificar(resultado)
        if clave in catalogo and not huella_vigente(resultado, catalogo[clave]):
            vencidos.append(clave)
        elif triage.get("decision") == CONTINUE:
            acotados.append(clave)
        elif paro_ya_diagnosticado(pospuestos.get(clave), triage):
            postergados.append(clave)
        else:
            abiertos.append(clave)
    if abiertos:
        return False, f"{len(abiertos)} sin resolver: {abiertos[:5]}"
    detalle = "ninguno que detenga la cola"
    if postergados:
        detalle += (f"; {len(postergados)} con el paro diagnosticado y "
                    f"diferido: {postergados[:3]}")
    if vencidos:
        detalle += (f"; {len(vencidos)} con huella vencida que la cola vuelve "
                    f"a evaluar: {vencidos[:3]}")
    if acotados:
        detalle += (f"; {len(acotados)} de radio acotado que la cola atraviesa: "
                    f"{acotados[:3]}")
    return True, detalle


def base_de_datos_vigente(ruta: str) -> tuple[bool, str]:
    """Que el runner no arranque apuntando a una snapshot vencida.

    El certificador estuvo apuntando por default a la base del 27 de agosto,
    anterior al fix D-014, mientras la vigente era la del 3 de septiembre. No lo
    noto nadie porque la ruta estaba escrita a mano en dos `argparse` y una ruta
    a mano envejece en silencio. Esto lo vuelve imposible de repetir.
    """
    dato = describir(ruta)
    estado = dato.get("estado")
    if estado == "HISTORICA":
        return False, (f"apunta a una snapshot HISTORICA del {dato.get('fecha')} "
                       f"({dato.get('proposito')}); la vigente es "
                       f"{base_canonica()}")
    if estado == "NO_DECLARADA":
        return False, (f"la base {ruta} no esta declarada en "
                       f"ERETZ_DATA_MANIFEST.json; una base sin declarar no "
                       f"se puede auditar despues")
    if not Path(ruta).exists():
        return False, f"la base declarada vigente no existe en disco: {ruta}"
    return True, (f"base vigente del {dato.get('fecha')}, "
                  f"{dato.get('candidatas')} candidatas")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v2-dir", default=r"D:\INMO CAPITAL\ERETZ_SUPABASE_RECONCILIATION_V2_20260827")
    parser.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    parser.add_argument("--platform-directory", default=r"D:\INMO CAPITAL\agency_platform_directory.jsonl")
    parser.add_argument("--output", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
    parser.add_argument("--preingestion-db", default=str(base_canonica()))
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
        ("sin NEEDS_FIX abiertos", sin_defectos_abiertos(salida, catalogo)),
        ("base de preingestion vigente",
         base_de_datos_vigente(args.preingestion_db)),
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
