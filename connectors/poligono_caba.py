"""¿La coordenada cae dentro de la Ciudad Autonoma de Buenos Aires?

Contencion PUNTO-EN-POLIGONO contra la geometria oficial del IGN
(`connectors/geometria/caba_ign.geojson`, bajada y versionada por
`scripts/geo_poligono_caba.py`, con su procedencia adentro). No es un radio ni
un centroide ni una caja: el conurbano rodea a la Ciudad, y una ficha de
Avellaneda o de Vicente Lopez esta a pocos cientos de metros del limite.

**Margen de frontera.** El poligono del IGN tiene 1.024 vertices para ~60 km de
perimetro, y una coordenada publicada no es un punto de agrimensura. A menos de
`MARGEN_M` del limite la respuesta es `FRONTERA`, que NO afirma nada: quien
pregunta la trata igual que a una coordenada que falta. Es el unico lugar donde
la geometria y el error de la fuente pueden confundirse, y ahi se prefiere no
afirmar.

Sin geometria disponible, o sin coordenada, la respuesta es `None`: sin
evidencia no hay veredicto.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

GEOMETRIA = Path(__file__).resolve().parent / "geometria" / "caba_ign.geojson"

DENTRO = "DENTRO"
FUERA = "FUERA"
FRONTERA = "FRONTERA"

# Metros al limite por debajo de los cuales no se afirma ni adentro ni afuera.
MARGEN_M = 100.0

_M_POR_GRADO = 111_320.0


@lru_cache(maxsize=1)
def _cargar(ruta: str = str(GEOMETRIA)) -> tuple[list[list[tuple[float, float]]], dict[str, Any]]:
    """Los anillos del poligono (lon, lat) y su procedencia."""
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    geometria = datos["geometry"]
    if geometria["type"] == "Polygon":
        poligonos = [geometria["coordinates"]]
    elif geometria["type"] == "MultiPolygon":
        poligonos = geometria["coordinates"]
    else:
        raise ValueError(f"geometria no poligonal: {geometria['type']}")
    anillos = [[(float(x), float(y)) for x, y, *_ in anillo]
               for poligono in poligonos for anillo in poligono]
    return anillos, dict(datos.get("properties", {}).get("procedencia", {}))


def procedencia() -> dict[str, Any] | None:
    try:
        return _cargar()[1]
    except (OSError, ValueError, KeyError):
        return None


def _dentro(anillos, lon: float, lat: float) -> bool:
    """Par-impar sobre todos los anillos: los huecos restan solos."""
    adentro = False
    for anillo in anillos:
        j = len(anillo) - 1
        for i in range(len(anillo)):
            xi, yi = anillo[i]
            xj, yj = anillo[j]
            if (yi > lat) != (yj > lat):
                x_corte = xi + (lat - yi) * (xj - xi) / (yj - yi)
                if lon < x_corte:
                    adentro = not adentro
            j = i
    return adentro


def _distancia_al_borde_m(anillos, lon: float, lat: float) -> float:
    """Distancia minima a los lados, en una proyeccion local (error << margen)."""
    kx = _M_POR_GRADO * math.cos(math.radians(lat))
    ky = _M_POR_GRADO
    mejor = math.inf
    for anillo in anillos:
        for (x1, y1), (x2, y2) in zip(anillo, anillo[1:] + anillo[:1]):
            ax, ay = (x1 - lon) * kx, (y1 - lat) * ky
            bx, by = (x2 - lon) * kx, (y2 - lat) * ky
            dx, dy = bx - ax, by - ay
            largo2 = dx * dx + dy * dy
            t = 0.0 if largo2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / largo2))
            px, py = ax + t * dx, ay + t * dy
            mejor = min(mejor, math.hypot(px, py))
    return mejor


def contencion(lat: Any, lon: Any, *, ruta: Path | None = None) -> str | None:
    """`DENTRO`, `FUERA`, `FRONTERA` o `None` (sin coordenada o sin geometria)."""
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return None
    try:
        anillos, _ = _cargar(str(ruta or GEOMETRIA))
    except (OSError, ValueError, KeyError):
        return None
    if _distancia_al_borde_m(anillos, lon, lat) < MARGEN_M:
        return FRONTERA
    return DENTRO if _dentro(anillos, lon, lat) else FUERA
