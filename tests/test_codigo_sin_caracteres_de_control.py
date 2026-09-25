"""Ningun archivo de codigo lleva caracteres de control.

El 25-09 un `\\b` de una regex llego al archivo como el caracter 0x08
(retroceso) al pasar por un heredoc de Bash: la regex seguia compilando, no
matcheaba nunca y el cambio parecia hecho. El diff no lo mostraba.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CONTROL = re.compile(rb"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def test_MUERDE_el_codigo_no_tiene_caracteres_de_control():
    malos = []
    for carpeta in ("connectors", "scraper", "scripts", "api", "tests"):
        for archivo in (RAIZ / carpeta).rglob("*.py"):
            datos = archivo.read_bytes()
            m = CONTROL.search(datos)
            if m:
                linea = datos[:m.start()].count(b"\n") + 1
                malos.append(f"{archivo.relative_to(RAIZ)}:{linea} byte {m.group(0)!r}")
    assert malos == []
