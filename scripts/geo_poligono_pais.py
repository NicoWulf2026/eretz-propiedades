#!/usr/bin/env python
"""Baja el poligono oficial de la Republica Argentina (IGN) y lo deja versionable.

Fuente: Instituto Geografico Nacional, WFS publico, capa `ign:pais`
(«Republica Argentina», un MultiPolygon de ~4,1 millones de vertices, 113 MB).
Licencia declarada por el servicio: libre acceso, copia, reproceso,
reutilizacion y redistribucion segun el Art. 2 de la Ley 27.275.

Para versionarlo se SIMPLIFICA con Douglas-Peucker (tolerancia `TOLERANCIA`
grados, ~550 m) y se redondea a 5 decimales. No se descarta ningun poligono
por chico: las islas del Delta del Parana son Argentina y sacarlas mandaria sus
propiedades "afuera". Solo se omite lo que esta al sur de -60 (sector antartico),
donde no hay inventario inmobiliario.

Quien consulta (`connectors/pais.py`) exige un margen mayor que el error de la
simplificacion antes de afirmar que un punto esta FUERA.

Uso: python scripts/geo_poligono_pais.py [--salida connectors/geometria/argentina_ign.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

WFS = "https://wms.ign.gob.ar/geoserver/ows"
PARAMETROS = {"service": "WFS", "version": "2.0.0", "request": "GetFeature",
              "typeNames": "ign:pais", "outputFormat": "application/json",
              "srsName": "EPSG:4326"}
AGENTE = "ERETZ-Propiedades/1.0 (geometria oficial)"
LICENCIA = ("IGN WFS ows:AccessConstraints: libre acceso, copia, reproceso, reutilizacion y "
            "redistribucion segun el Art. 2 de la Ley 27.275")
TOLERANCIA = 0.005
SUR_OMITIDO = -60.0
POR_DEFECTO = Path(__file__).resolve().parents[1] / "connectors" / "geometria" / "argentina_ign.json"


def _dp(puntos: list, tol: float) -> list:
    """Douglas-Peucker iterativo (las costas tienen decenas de miles de vertices)."""
    if len(puntos) < 5:
        return puntos
    conservar = [False] * len(puntos)
    conservar[0] = conservar[-1] = True
    pila = [(0, len(puntos) - 1)]
    while pila:
        a, b = pila.pop()
        (x1, y1), (x2, y2) = puntos[a], puntos[b]
        dx, dy = x2 - x1, y2 - y1
        largo2 = dx * dx + dy * dy
        peor, indice = -1.0, None
        for i in range(a + 1, b):
            px, py = puntos[i]
            if largo2 == 0:
                d2 = (px - x1) ** 2 + (py - y1) ** 2
            else:
                t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / largo2))
                d2 = (px - x1 - t * dx) ** 2 + (py - y1 - t * dy) ** 2
            if d2 > peor:
                peor, indice = d2, i
        if indice is not None and peor > tol * tol:
            conservar[indice] = True
            pila.append((a, indice))
            pila.append((indice, b))
    return [p for p, k in zip(puntos, conservar) if k]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", type=Path, default=POR_DEFECTO)
    ap.add_argument("--desde-archivo", type=Path, default=None,
                    help="GeoJSON ya bajado del mismo WFS (evita 113 MB de nuevo)")
    args = ap.parse_args()
    url = f"{WFS}?{urllib.parse.urlencode(PARAMETROS)}"
    if args.desde_archivo:
        crudo = args.desde_archivo.read_bytes()
    else:
        peticion = urllib.request.Request(url, headers={"User-Agent": AGENTE})
        with urllib.request.urlopen(peticion, timeout=600) as respuesta:
            crudo = respuesta.read()
    datos = json.loads(crudo)
    rasgos = datos.get("features") or []
    if len(rasgos) != 1 or rasgos[0]["properties"].get("nam") != "Argentina":
        raise SystemExit("se esperaba un unico rasgo «Argentina»")
    poligonos, vertices_origen = [], 0
    for poligono in rasgos[0]["geometry"]["coordinates"]:
        vertices_origen += sum(len(anillo) for anillo in poligono)
        if max(y for x, y, *_ in poligono[0]) < SUR_OMITIDO:
            continue
        anillos = []
        for anillo in poligono:
            original = [(float(x), float(y)) for x, y, *_ in anillo]
            simple = [[round(x, 5), round(y, 5)] for x, y in _dp(original, TOLERANCIA)]
            if len(simple) < 4:
                # Una isla chica que la simplificacion aplasta se conserva
                # entera: sacarla dejaria afuera tierra argentina (el Delta).
                simple = [[round(x, 5), round(y, 5)] for x, y in original]
            if len(simple) >= 4:
                anillos.append(simple)
        if anillos:
            poligonos.append(anillos)
    vertices = sum(len(a) for p in poligonos for a in p)
    salida = {
        "procedencia": {
            "fuente": "Instituto Geografico Nacional (IGN) - WFS ign:pais",
            "url": url,
            "descargado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sello_del_servicio": datos.get("timeStamp"),
            "sha256_origen": hashlib.sha256(crudo).hexdigest(),
            "vertices_origen": vertices_origen,
            "simplificacion": f"Douglas-Peucker {TOLERANCIA} grados, 5 decimales; omitido lo "
                              f"que queda al sur de {SUR_OMITIDO}",
            "vertices": vertices, "poligonos": len(poligonos),
            "crs": "EPSG:4326 (lon, lat)", "licencia": LICENCIA,
            "reproducir": "python scripts/geo_poligono_pais.py",
        },
        "poligonos": poligonos,
    }
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(json.dumps(salida, separators=(",", ":")), encoding="utf-8")
    print(f"{args.salida}: {len(poligonos)} poligonos, {vertices} vertices (de {vertices_origen}), "
          f"{args.salida.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
