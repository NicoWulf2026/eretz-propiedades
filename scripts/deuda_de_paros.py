# -*- coding: utf-8 -*-
"""Cuantos paros quedan de verdad, separando los que la realidad ya cerro.

`AGENCY_DEFECT_QUEUE.jsonl` escribe cada entrada con `pendiente_de_resolucion:
True` y `certificado: False`, y **nunca las actualiza**: los dos campos son
constantes puestas en el momento de crear la entrada -defect_triage.py, en el
diccionario del veredicto- y no hay ningun camino que las cierre.

La consecuencia se ve a simple vista en los datos del 2026-09-21: de 113
entradas STOP «abiertas», **18 son de agencias que ya certificaron despues**.
`altos servicios inmobiliarios` paro el 2026-09-05 y certifico
CERTIFIED_COMPLETE el 2026-09-21, dieciseis dias mas tarde, y su paro sigue
figurando como pendiente. `arbini propiedades` y `benitez ullo` certificaron
CINCO veces desde su paro.

Eso no es solo ruido en un numero: la lista de «paros sin diagnosticar» se usa
para decidir que falta hacer, y mezclaba trabajo pendiente con trabajo que la
propia cola ya habia resuelto.

## Por que una vista derivada y no un arreglo del archivo

Dos razones. La primera es operativa: los workers estan escribiendo ese
archivo, y reescribirlo en caliente es como se pierden datos. La segunda es de
fondo: la entrada es el registro de lo que se penso EN SU MOMENTO, y marcarla
resuelta reescribe esa historia. Lo que hace falta no es cambiar el pasado
sino saber leerlo.

La regla es la evidente: un paro esta cerrado si el ultimo resultado de esa
agencia es terminal y positivo -`CERTIFIED_*` o `NO_INVENTORY_CONFIRMED`- y es
POSTERIOR al paro. Lo de «posterior» importa: certificar antes y romperse
despues no cierra nada.

    python scripts/deuda_de_paros.py
    python scripts/deuda_de_paros.py --sin-firma

`database_writes: 0`.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterator

BASE = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
TERMINALES_BUENOS = ("CERTIFIED_COMPLETE", "CERTIFIED_BEST_AVAILABLE",
                     "NO_INVENTORY_CONFIRMED")


def leer_jsonl(ruta: Path) -> Iterator[dict[str, Any]]:
    if not ruta.exists():
        return
    with ruta.open(encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea:
                continue
            try:
                yield json.loads(linea)
            except ValueError:
                continue


def ultimos_resultados(ruta: Path) -> dict[str, dict[str, Any]]:
    ultimo: dict[str, dict[str, Any]] = {}
    for fila in leer_jsonl(ruta):
        if fila.get("canonical_agency_id"):
            ultimo[fila["canonical_agency_id"]] = fila
    return ultimo


def la_realidad_lo_cerro(paro: dict[str, Any],
                         resultado: dict[str, Any] | None) -> bool:
    """¿La agencia certificó DESPUÉS de este paro?"""
    if not resultado:
        return False
    if str(resultado.get("status")) not in TERMINALES_BUENOS:
        return False
    cuando_paro = str(paro.get("cuando") or "")
    cuando_res = str(resultado.get("checked_at") or "")
    if not cuando_paro or not cuando_res:
        return False
    return cuando_res >= cuando_paro


def paros_abiertos(base: Path = BASE) -> dict[tuple[str, str], dict[str, Any]]:
    """El último paro STOP por agencia y componente."""
    abiertos: dict[tuple[str, str], dict[str, Any]] = {}
    for fila in leer_jsonl(base / "AGENCY_DEFECT_QUEUE.jsonl"):
        if fila.get("decision") != "STOP" or not fila.get("pendiente_de_resolucion"):
            continue
        clave = (fila.get("canonical_agency_id"), fila.get("componente_sospechoso"))
        if clave[0]:
            abiertos[clave] = fila
    return abiertos


def firmados(base: Path = BASE) -> set[tuple[str, str]]:
    return {(f.get("canonical_agency_id"), f.get("componente"))
            for f in leer_jsonl(base / "AGENCY_DEFECTS_DIFERIDOS.jsonl")}


def deuda(base: Path = BASE) -> dict[str, Any]:
    resultados = ultimos_resultados(base / "AGENCY_CERTIFICATION_RESULTS.jsonl")
    con_firma = firmados(base)
    cerrados, vivos, sin_firma = [], [], []
    for clave, paro in paros_abiertos(base).items():
        if la_realidad_lo_cerro(paro, resultados.get(clave[0])):
            cerrados.append((clave, paro))
            continue
        vivos.append((clave, paro))
        if clave not in con_firma:
            sin_firma.append((clave, paro))
    return {"abiertos_en_el_archivo": len(cerrados) + len(vivos),
            "cerrados_por_la_realidad": cerrados,
            "vivos": vivos, "sin_firma": sin_firma}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=str(BASE))
    ap.add_argument("--sin-firma", action="store_true",
                    help="listar solo los vivos que ademas no tienen diferida")
    args = ap.parse_args(argv)
    d = deuda(Path(args.base))
    print(f"entradas STOP marcadas abiertas : {d['abiertos_en_el_archivo']}")
    print(f"  ya cerradas por la realidad   : {len(d['cerrados_por_la_realidad'])}")
    print(f"  deuda real                    : {len(d['vivos'])}")
    print(f"  de esas, sin diferida firmada : {len(d['sin_firma'])}")
    lista = d["sin_firma"] if args.sin_firma else d["vivos"]
    for (agencia, componente), paro in sorted(lista, key=lambda x: str(x[0])):
        print(f"   {str(agencia).split(':', 1)[-1][:32]:32s} {str(componente)[:36]:36s} "
              f"{str(paro.get('cuando'))[:10]}")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
