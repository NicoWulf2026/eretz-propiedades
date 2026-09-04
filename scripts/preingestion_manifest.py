#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Cual base de preingestion es la vigente. Una sola respuesta, en un solo lugar.

El certificador venia apuntando por default a la base del 27 de agosto, anterior
al fix D-014, mientras la vigente era la del 3 de septiembre con 13.023
candidatas mas. Nadie lo habia notado porque la ruta estaba escrita a mano en
dos `argparse` distintos, y una ruta escrita a mano envejece en silencio.

Aca la vigente se declara en `ERETZ_DATA_MANIFEST.json`, que es un dato y no
codigo. Eso importa por dos razones:

  - cambiarla no toca ningun componente de huella, asi que corregir a que base
    se apunta no cuesta una recertificacion masiva;
  - las snapshots historicas siguen existiendo como evidencia, pero quedan
    marcadas `HISTORICA` y el preflight se niega a arrancar apuntando a una.

**Sobre el caso concreto que motivo esto:** se midio y las dos bases dan el
MISMO baseline. 189.159 filas en las dos, 1.724 `canonical_id` en las dos, y
cero agencias con conteo distinto: `baseline_inventory` cuenta filas por
`canonical_id` sin mirar el estado, y el rebuild reclasifico estados sobre el
mismo universo. O sea que el default viejo no corrompio ningun veredicto. Se
corrige igual, porque una ruta que apunta a una snapshot vencida es una trampa
esperando a que alguien cambie algo que si dependa del estado.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

MANIFIESTO = Path(r"D:\INMO CAPITAL\ERETZ_DATA_MANIFEST.json")

# Si el manifiesto no esta, se usa esto. No es la base vieja a proposito: ante
# la ausencia del manifiesto conviene fallar apuntando a lo vigente y no
# revivir en silencio una snapshot vencida.
RESPALDO = Path(r"D:\INMO CAPITAL\ERETZ_PREINGESTION_REBUILD_20260903\PREINGESTION_REBUILD.sqlite3")


@lru_cache(maxsize=1)
def _manifiesto() -> dict:
    if not MANIFIESTO.exists():
        return {}
    try:
        return json.loads(MANIFIESTO.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def base_canonica() -> Path:
    """La base de preingestion vigente, segun el manifiesto."""
    dato = ((_manifiesto().get("preingestion") or {}).get("canonica") or {})
    ruta = dato.get("ruta")
    return Path(ruta) if ruta else RESPALDO


def historicas() -> list[Path]:
    dato = (_manifiesto().get("preingestion") or {}).get("historicas") or []
    return [Path(x["ruta"]) for x in dato if x.get("ruta")]


def es_historica(ruta: str | Path) -> bool:
    """Si esa ruta esta declarada como snapshot vencida."""
    objetivo = Path(ruta).resolve()
    return any(h.resolve() == objetivo for h in historicas()
               if h.exists() or True)


def describir(ruta: str | Path) -> dict:
    """Fecha, generacion y estado de la base que se esta por usar."""
    objetivo = str(Path(ruta))
    for bloque in ("canonica",):
        dato = (_manifiesto().get("preingestion") or {}).get(bloque) or {}
        if dato.get("ruta") and Path(dato["ruta"]) == Path(objetivo):
            return dato
    for dato in (_manifiesto().get("preingestion") or {}).get("historicas") or []:
        if Path(dato.get("ruta", "")) == Path(objetivo):
            return dato
    return {"ruta": objetivo, "estado": "NO_DECLARADA"}
