"""¿La coordenada cae dentro de la Republica Argentina?

Contencion PUNTO-EN-POLIGONO contra la geometria oficial del IGN (`ign:pais`,
simplificada y versionada por `scripts/geo_poligono_pais.py`, con su
procedencia adentro). Reemplaza, para decidir EXTERIOR, a la caja
`CAJA_ARGENTINA` (-90..-21, -74..-53): esa caja cubre Uruguay entero y parte de
Chile, Paraguay y Brasil, y la snapshot servia departamentos de Montevideo y
Punta del Este (`enlaze`, `lopez baena`, `farina`...) como si fueran argentinos.

**Margen.** La simplificacion mueve el borde hasta ~550 m. A menos de
`MARGEN_KM` del borde la respuesta es `FRONTERA`, que no afirma nada: solo
`FUERA` (lejos del borde) es evidencia de exterior. El Delta, las islas y la
costa quedan protegidos por el mismo margen.

Rapido a proposito: los lados se indexan por franjas de latitud, asi que cada
consulta mira unas decenas de lados y no los 45.000.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

GEOMETRIA = Path(__file__).resolve().parent / "geometria" / "argentina_ign.json"

DENTRO = "DENTRO"
FUERA = "FUERA"
FRONTERA = "FRONTERA"

MARGEN_KM = 5.0
FRANJA = 0.05  # grados de latitud por franja (~5,5 km)
_KM_POR_GRADO = 111.32


@lru_cache(maxsize=2)
def _indice(ruta: str = str(GEOMETRIA)):
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    franjas: dict[int, list[tuple[float, float, float, float]]] = {}
    for poligono in datos["poligonos"]:
        for anillo in poligono:
            for (x1, y1), (x2, y2) in zip(anillo, anillo[1:] + anillo[:1]):
                lado = (x1, y1, x2, y2)
                for f in range(math.floor(min(y1, y2) / FRANJA), math.floor(max(y1, y2) / FRANJA) + 1):
                    franjas.setdefault(f, []).append(lado)
    return franjas, datos.get("procedencia", {})


def procedencia() -> dict[str, Any] | None:
    try:
        return _indice()[1]
    except (OSError, ValueError, KeyError):
        return None


def _dentro(franjas, lon: float, lat: float) -> bool:
    adentro = False
    for x1, y1, x2, y2 in franjas.get(math.floor(lat / FRANJA), ()):
        if (y1 > lat) != (y2 > lat):
            if lon < x1 + (lat - y1) * (x2 - x1) / (y2 - y1):
                adentro = not adentro
    return adentro


def _cerca_del_borde(franjas, lon: float, lat: float) -> bool:
    kx = _KM_POR_GRADO * math.cos(math.radians(lat))
    ky = _KM_POR_GRADO
    alcance = math.ceil((MARGEN_KM / _KM_POR_GRADO) / FRANJA)
    base = math.floor(lat / FRANJA)
    vistos = set()
    for f in range(base - alcance, base + alcance + 1):
        for lado in franjas.get(f, ()):
            if lado in vistos:
                continue
            vistos.add(lado)
            x1, y1, x2, y2 = lado
            ax, ay = (x1 - lon) * kx, (y1 - lat) * ky
            bx, by = (x2 - lon) * kx, (y2 - lat) * ky
            dx, dy = bx - ax, by - ay
            largo2 = dx * dx + dy * dy
            t = 0.0 if largo2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / largo2))
            if math.hypot(ax + t * dx, ay + t * dy) < MARGEN_KM:
                return True
    return False


def contencion(lat: Any, lon: Any, *, ruta: Path | None = None) -> str | None:
    """`DENTRO`, `FUERA`, `FRONTERA` o `None` (sin coordenada o sin geometria)."""
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lon)) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    try:
        franjas, _ = _indice(str(ruta or GEOMETRIA))
    except (OSError, ValueError, KeyError):
        return None
    if _cerca_del_borde(franjas, lon, lat):
        return FRONTERA
    return DENTRO if _dentro(franjas, lon, lat) else FUERA
