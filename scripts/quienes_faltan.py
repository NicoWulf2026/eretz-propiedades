# -*- coding: utf-8 -*-
"""Que propiedades dejo de publicar la fuente, con nombre y antiguedad.

El item 8 de la tanda congelada dice que la cola registra CUANTAS propiedades
faltan y no CUALES, y que por eso la regla de bajas no puede acumular
evidencia. Es cierto a medias, y la mitad que falta cambia el problema: el
**resultado** guarda solo el conteo `ausentes`, pero el **checkpoint** de cada
paquete guarda las identidades.

    checkpoint.json
      fuentes[<agencia>].ausencias  {hash_dedup: corridas_seguidas_ausente}
      fuentes[<agencia>].ids        {hash_dedup: source_listing_id}

Medido el 2026-09-21 sobre los 236 checkpoints en disco: **89 agencias tienen
`ausencias`, con 918 propiedades ausentes en total, y ninguna sin id**. Estan
en los cuatro conectores -generico 41, tokko 33, wordpress 11, wasi 4-, asi
que no es una peculiaridad de una familia.

O sea que la evidencia que la regla de bajas necesitaba ya se venia
acumulando, callada, en el lugar donde nadie la miraba. Esto la lee.

    python scripts/quienes_faltan.py                # todas
    python scripts/quienes_faltan.py --agencia cocucci --minimo 3

Lo que esto NO hace, y conviene decirlo: no decide si una propiedad se dio de
baja o si la perdimos nosotros. Para eso hay que ir al catalogo de la fuente y
preguntar por ese id. Lo que aporta es el id para poder preguntarlo.

`database_writes: 0`.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterator

PAQUETES = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827\agencies")


def leer_checkpoint(ruta: Path) -> dict[str, Any]:
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def ausentes_de(checkpoint: dict[str, Any]) -> Iterator[tuple[str, list[dict]]]:
    """Por agencia, las propiedades ausentes ordenadas por antiguedad."""
    for agencia, estado in (checkpoint.get("fuentes") or {}).items():
        if not isinstance(estado, dict):
            continue
        ausencias = estado.get("ausencias") or {}
        ids = estado.get("ids") or {}
        if not ausencias:
            continue
        filas = [{"hash": h, "id": ids.get(h), "corridas_ausente": n}
                 for h, n in ausencias.items()]
        filas.sort(key=lambda f: -int(f["corridas_ausente"] or 0))
        yield agencia, filas


def recorrer(raiz: Path, aguja: str | None = None,
             minimo: int = 1) -> Iterator[tuple[str, Path, list[dict]]]:
    for ruta in sorted(raiz.glob("*/checkpoint.json")):
        for agencia, filas in ausentes_de(leer_checkpoint(ruta)):
            if aguja and aguja.lower() not in agencia.lower():
                continue
            filas = [f for f in filas if int(f["corridas_ausente"] or 0) >= minimo]
            if filas:
                yield agencia, ruta.parent, filas


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agencia", default=None, help="parte del canonical_agency_id")
    ap.add_argument("--minimo", type=int, default=1,
                    help="corridas seguidas ausente como minimo")
    ap.add_argument("--paquetes", default=str(PAQUETES))
    ap.add_argument("--detalle", action="store_true", help="listar cada propiedad")
    args = ap.parse_args(argv)

    agencias = 0
    propiedades = 0
    sin_id = 0
    for agencia, paquete, filas in recorrer(Path(args.paquetes), args.agencia,
                                            args.minimo):
        agencias += 1
        propiedades += len(filas)
        sin_id += sum(1 for f in filas if not f["id"])
        print(f"\n{agencia}  ({paquete.name})  {len(filas)} ausentes")
        for f in (filas if args.detalle else filas[:5]):
            print(f"   id={str(f['id'] or '(sin id)'):>12s}  "
                  f"ausente hace {f['corridas_ausente']} corridas")
        if not args.detalle and len(filas) > 5:
            print(f"   ... y {len(filas) - 5} mas (--detalle para verlas)")
    print(f"\nagencias con ausentes: {agencias}   propiedades: {propiedades}   "
          f"sin id: {sin_id}")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
