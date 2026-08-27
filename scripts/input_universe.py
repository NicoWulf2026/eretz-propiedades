#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Las entradas que componen el universo de propiedades. Una sola lista.

Existe porque la lista estuvo escrita en tres lugares distintos -el comando
documentado, el mapa de mission_report y la invocacion real- y los tres decian
cosas distintas. El comando documentado omitia FORMAS3_ROLLOUT y
RESIDUAL_ROLLOUT: reanudar con el producia un write set 791 propiedades mas
chico y no fallaba, porque write_eligibility no tiene forma de saber que le
falta un archivo. Un universo incompleto no da error, da menos filas.

De aca en adelante la lista vive en un solo lugar y se comprueba sola:

  - cada entrada existe y se puede contar;
  - la suma de las entradas es el universo analizado;
  - cada `_run` que aparece en los artefactos de salida se explica por alguna
    de estas entradas, y no queda ninguna sin origen.

Si legitimamente cambia -un rollout nuevo, un archivo corregido- se cambia aca
y se documenta. Nunca se agrega una entrada "de paso" en una invocacion suelta.
"""
from __future__ import annotations

import json
from pathlib import Path

RAIZ = Path(r"D:\INMO CAPITAL")

# Version del universo. Subirla cuando la lista cambie a proposito, para que un
# artefacto viejo no se confunda con uno nuevo.
UNIVERSE_VERSION = "input_universe_v3"

# Se usa SIEMPRE el archivo corregido (.coherente / .limpio.coherente) cuando
# existe: es el que paso por las guardas de aritmetica de inmuebles.
ENTRADAS = (
    ("TOKKO_ROLLOUT_FULL",  "properties_run3.coherente.jsonl",        "tokko"),
    ("WP_ROLLOUT_FULL",     "properties_run6.coherente.jsonl",        "wordpress"),
    ("WASI_ROLLOUT_FULL",   "properties_run2.limpio.coherente.jsonl", "wasi"),
    ("C21_CANARY",          "properties_run2.coherente.jsonl",        "century21"),
    ("RESCATE2_generico",   "properties_run1.limpio.coherente.jsonl", "generico"),
    ("RESCATE2_tokko",      "properties_run1.coherente.jsonl",        "tokko"),
    ("RESCATE2_wordpress",  "properties_run1.coherente.jsonl",        "wordpress"),
    ("RESCATE3_shapes",     "properties_run1.coherente.jsonl",        "generico"),
    ("RESCATE_generico",    "properties_run1.coherente.jsonl",        "generico"),
    ("RESCATE_nextjs",      "properties_run1.coherente.jsonl",        "generico"),
    ("FORMAS_ROLLOUT",      "properties_run1.coherente.jsonl",        "generico"),
    ("FORMAS3_ROLLOUT",     "properties_run1.coherente.jsonl",        "generico"),
    ("RESIDUAL_ROLLOUT",    "properties_run1.coherente.jsonl",        "generico"),
    ("BACKLOG_generico",    "properties_run1.coherente.jsonl",        "generico"),
    ("RECUPERACION_tokko",     "properties_run1.coherente.jsonl",     "tokko"),
    ("RECUPERACION_wordpress", "properties_run1.coherente.jsonl",     "wordpress"),
    ("RECUPERACION_generico",  "properties_run1.coherente.jsonl",     "generico"),
    ("RECUPERACION_wasi",      "properties_run1.coherente.jsonl",     "wasi"),
)

# Las que no pueden faltar nunca mas, por nombre. No es decorativo: son
# exactamente las dos que el comando documentado se habia comido.
OBLIGATORIAS = {"FORMAS3_ROLLOUT", "RESIDUAL_ROLLOUT", "BACKLOG_generico",
                "RECUPERACION_tokko"}


def rutas(raiz: Path = RAIZ) -> list[Path]:
    return [raiz / d / f for d, f, _ in ENTRADAS]


def como_comando(raiz: Path = RAIZ) -> str:
    """La invocacion exacta de write_eligibility, generada, no escrita a mano."""
    args = "   ".join('"%s"' % (raiz / d / f).as_posix() for d, f, _ in ENTRADAS)
    return "python scripts/write_eligibility.py --entradas   " + args


def contar(raiz: Path = RAIZ) -> dict[str, int]:
    out = {}
    for d, f, _ in ENTRADAS:
        p = raiz / d / f
        n = 0
        if p.exists():
            with p.open(encoding="utf-8", errors="replace") as fh:
                for l in fh:
                    if l.strip():
                        n += 1
        out[d] = n
    return out


def corridas_por_entrada(raiz: Path = RAIZ) -> dict[str, set]:
    """Que `_run` aporta cada entrada. Es lo que permite despues comprobar que
    ningun artefacto de salida trae corridas de un origen no declarado."""
    out = {}
    for d, f, _ in ENTRADAS:
        p = raiz / d / f
        rs = set()
        if p.exists():
            with p.open(encoding="utf-8", errors="replace") as fh:
                for l in fh:
                    if l.strip():
                        try:
                            rs.add(json.loads(l).get("_run"))
                        except ValueError:
                            pass
        out[d] = rs
    return out


def faltantes(raiz: Path = RAIZ) -> list[str]:
    return [str(p) for p in rutas(raiz) if not p.exists()]
