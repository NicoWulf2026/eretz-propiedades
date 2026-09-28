# -*- coding: utf-8 -*-
"""El interruptor general de la automatizacion de ERETZ.

`ERETZ_AUTOMATION_OFF.json` en la carpeta de salida de la cola apaga todo lo
que relanza: mientras exista, `relanzar_la_cola.py` no lanza workers y
`run_agency_certification_queue.py` no arranca. Lo escribe y lo borra
`eretz_automatizacion.py` (`ERETZ_AUTOMATION_OFF.cmd` / `..._ON.cmd`).

Fail-closed: si el archivo existe pero no se puede leer, cuenta como apagado.
Un interruptor que no se entiende no puede dejar la cola corriendo.
"""
from __future__ import annotations

import json
from pathlib import Path

SALIDA = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
ARCHIVO = "ERETZ_AUTOMATION_OFF.json"
BANDERA_DE_PARO = "AGENCY_CERTIFICATION_STOP.json"
# Radio de la bandera de paro que escribe el apagado: los workers la leen como
# cualquier paro y salen al terminar la agencia en curso.
RADIO_APAGADO = "APAGADO"


def ruta(salida: Path | None = None) -> Path:
    return Path(salida or SALIDA) / ARCHIVO


def apagada(salida: Path | None = None) -> str | None:
    """Por que la automatizacion esta apagada, o None si esta encendida."""
    archivo = ruta(salida)
    if not archivo.exists():
        return None
    try:
        dato = json.loads(archivo.read_text(encoding="utf-8"))
        return (f"ERETZ AUTOMATION OFF desde {dato.get('cuando', '?')}"
                f" ({dato.get('motivo') or 'sin motivo'})")
    except (OSError, ValueError):
        return f"ERETZ AUTOMATION OFF ({archivo.name} ilegible: cuenta como apagado)"
