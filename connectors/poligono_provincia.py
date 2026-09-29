"""¿La coordenada cae dentro de una provincia argentina? Contencion en el poligono oficial.

Para la politica P10 (provincia publicada contradictoria): cuando la localidad
resuelve sin ambiguedad, la coordenada cae en el poligono OFICIAL de la
provincia de esa localidad y las dos coinciden, prevalecen sobre la provincia
que escribio la fuente (que se conserva como evidencia). Este modulo solo
contesta la parte geometrica.

Geometria: `connectors/geometria/provincias_ign.json`, capa `ign:provincia` del
IGN simplificada y versionada por `scripts/geo_poligonos_provincias.py`, con su
procedencia adentro. Las provincias se identifican por el codigo INDEC de dos
cifras (`in1` en el IGN, `id` en GeoRef: son el mismo codigo), y tambien por
nombre.

**Margen.** La simplificacion mueve el borde hasta ~550 m y una coordenada
publicada no es un punto de agrimensura. A menos de `MARGEN_KM` del limite la
respuesta es `FRONTERA`, que NO afirma nada. Sin geometria, sin la provincia o
sin coordenada, la respuesta es `None`: sin evidencia no hay veredicto.

Nada de esto se usa todavia desde la huella: lo usa el lote P10
(`docs/agent/lotes/`), que decide LOCAL segun P4.
"""
from __future__ import annotations

import json
import math
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

GEOMETRIA = Path(__file__).resolve().parent / "geometria" / "provincias_ign.json"

DENTRO = "DENTRO"
FUERA = "FUERA"
FRONTERA = "FRONTERA"

MARGEN_KM = 2.0
_KM_POR_GRADO = 111.32


def _plano(texto: Any) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(t.replace(",", " ").split())


@lru_cache(maxsize=4)
def _cargar(ruta: str = str(GEOMETRIA)) -> tuple[dict[str, dict[str, Any]], dict[str, str], dict[str, Any]]:
    """(provincias por codigo, codigo por nombre plano, procedencia)."""
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    por_codigo: dict[str, dict[str, Any]] = {}
    por_nombre: dict[str, str] = {}
    for codigo, prov in (datos.get("provincias") or {}).items():
        anillos = [[(float(x), float(y)) for x, y in anillo]
                   for poligono in prov["poligonos"] for anillo in poligono]
        if not anillos:
            continue
        xs = [x for a in anillos for x, _ in a]
        ys = [y for a in anillos for _, y in a]
        por_codigo[str(codigo)] = {"nombre": prov.get("nombre"), "anillos": anillos,
                                   "caja": (min(xs), min(ys), max(xs), max(ys))}
        for nombre in (prov.get("nombre"), prov.get("fna")):
            if nombre:
                por_nombre[_plano(nombre)] = str(codigo)
    return por_codigo, por_nombre, dict(datos.get("procedencia") or {})


def procedencia(ruta: Path | None = None) -> dict[str, Any] | None:
    try:
        return _cargar(str(ruta or GEOMETRIA))[2]
    except (OSError, ValueError, KeyError):
        return None


def _dentro(anillos, lon: float, lat: float) -> bool:
    """Par-impar sobre todos los anillos: huecos y poligonos separados salen solos."""
    adentro = False
    for anillo in anillos:
        j = len(anillo) - 1
        for i in range(len(anillo)):
            xi, yi = anillo[i]
            xj, yj = anillo[j]
            if (yi > lat) != (yj > lat):
                if lon < xi + (lat - yi) * (xj - xi) / (yj - yi):
                    adentro = not adentro
            j = i
    return adentro


def _distancia_al_borde_km(anillos, lon: float, lat: float) -> float:
    kx = _KM_POR_GRADO * math.cos(math.radians(lat))
    ky = _KM_POR_GRADO
    mejor = math.inf
    for anillo in anillos:
        for (x1, y1), (x2, y2) in zip(anillo, anillo[1:] + anillo[:1]):
            ax, ay = (x1 - lon) * kx, (y1 - lat) * ky
            bx, by = (x2 - lon) * kx, (y2 - lat) * ky
            dx, dy = bx - ax, by - ay
            largo2 = dx * dx + dy * dy
            t = 0.0 if largo2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / largo2))
            mejor = min(mejor, math.hypot(ax + t * dx, ay + t * dy))
    return mejor


def _codigo(provincia: Any, por_nombre: dict[str, str], por_codigo: dict[str, Any]) -> str | None:
    texto = str(provincia or "").strip()
    if texto.isdigit():
        return texto.zfill(2) if texto.zfill(2) in por_codigo else None
    return por_nombre.get(_plano(texto))


def contencion(provincia: Any, lat: Any, lon: Any, *, ruta: Path | None = None,
               margen_km: float = MARGEN_KM) -> str | None:
    """`DENTRO`, `FUERA`, `FRONTERA` o `None` para la provincia (nombre o codigo INDEC)."""
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return None
    try:
        por_codigo, por_nombre, _ = _cargar(str(ruta or GEOMETRIA))
    except (OSError, ValueError, KeyError):
        return None
    codigo = _codigo(provincia, por_nombre, por_codigo)
    if codigo is None:
        return None
    prov = por_codigo[codigo]
    x0, y0, x1, y1 = prov["caja"]
    holgura = margen_km / _KM_POR_GRADO * 2
    if not (x0 - holgura <= lon <= x1 + holgura and y0 - holgura <= lat <= y1 + holgura):
        return FUERA
    if _distancia_al_borde_km(prov["anillos"], lon, lat) < margen_km:
        return FRONTERA
    return DENTRO if _dentro(prov["anillos"], lon, lat) else FUERA


def provincia_que_contiene(lat: Any, lon: Any, *, ruta: Path | None = None,
                           margen_km: float = MARGEN_KM) -> str | None:
    """El codigo INDEC de la UNICA provincia que contiene la coordenada, lejos del borde."""
    try:
        por_codigo, _, _ = _cargar(str(ruta or GEOMETRIA))
    except (OSError, ValueError, KeyError):
        return None
    dentro = [c for c in por_codigo
              if contencion(c, lat, lon, ruta=ruta, margen_km=margen_km) == DENTRO]
    return dentro[0] if len(dentro) == 1 else None
