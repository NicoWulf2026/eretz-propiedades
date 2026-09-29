#!/usr/bin/env python
"""Baja los poligonos oficiales de las 24 jurisdicciones (IGN) y los deja versionables.

Para la politica P10 (`connectors/poligono_provincia.py`). Mismo criterio que
`geo_poligono_pais.py`:

Fuente: Instituto Geografico Nacional, WFS publico, capa `ign:provincia`
(division politico-territorial de primer orden, incluye CABA). Licencia
declarada por el servicio: libre acceso, copia, reproceso, reutilizacion y
redistribucion segun el Art. 2 de la Ley 27.275.

Se SIMPLIFICA con Douglas-Peucker (`TOLERANCIA` grados, ~550 m) y se redondea a 5
decimales. Ningun poligono se descarta por chico (las islas son territorio de su
provincia); una isla que la simplificacion aplasta se conserva entera. Se omite
lo que queda entero al sur de -60 (sector antartico): no hay inventario ahi.
Quien consulta exige un margen mayor que el error de la simplificacion.

Las provincias quedan por codigo INDEC (`in1`), que es el mismo `id` de GeoRef.

    python scripts/geo_poligonos_provincias.py
    python scripts/geo_poligonos_provincias.py --desde-archivo provincias_wfs.json

Corre en LOCAL (el entorno CLOUD no tiene salida al IGN).
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
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from scripts.geo_poligono_pais import _dp  # noqa: E402

WFS = "https://wms.ign.gob.ar/geoserver/ows"
PARAMETROS = {"service": "WFS", "version": "2.0.0", "request": "GetFeature",
              "typeNames": "ign:provincia", "outputFormat": "application/json",
              "srsName": "EPSG:4326"}
AGENTE = "ERETZ-Propiedades/1.0 (geometria oficial)"
LICENCIA = ("IGN WFS ows:AccessConstraints: libre acceso, copia, reproceso, reutilizacion y "
            "redistribucion segun el Art. 2 de la Ley 27.275")
TOLERANCIA = 0.005
SUR_OMITIDO = -60.0
JURISDICCIONES = 24
POR_DEFECTO = RAIZ / "connectors" / "geometria" / "provincias_ign.json"


def _poligonos(geometria: dict[str, Any]) -> list:
    if geometria["type"] == "Polygon":
        return [geometria["coordinates"]]
    if geometria["type"] == "MultiPolygon":
        return geometria["coordinates"]
    raise ValueError(f"geometria no poligonal: {geometria['type']}")


def construir(datos: dict[str, Any], url: str, crudo: bytes) -> dict[str, Any]:
    """El archivo versionable, a partir de la respuesta del WFS. Falla cerrado."""
    rasgos = datos.get("features") or []
    codigos = [str((r.get("properties") or {}).get("in1") or "") for r in rasgos]
    if len(rasgos) != JURISDICCIONES or len(set(codigos)) != JURISDICCIONES or "" in codigos:
        raise ValueError(f"se esperaban {JURISDICCIONES} jurisdicciones con codigo in1 distinto; "
                         f"llegaron {len(rasgos)} ({len(set(codigos))} codigos)")
    provincias: dict[str, Any] = {}
    vertices_origen = vertices = 0
    for rasgo in rasgos:
        props = rasgo["properties"]
        salida = []
        for poligono in _poligonos(rasgo["geometry"]):
            vertices_origen += sum(len(anillo) for anillo in poligono)
            if max(y for x, y, *_ in poligono[0]) < SUR_OMITIDO:
                continue
            anillos = []
            for anillo in poligono:
                original = [(float(x), float(y)) for x, y, *_ in anillo]
                simple = [[round(x, 5), round(y, 5)] for x, y in _dp(original, TOLERANCIA)]
                if len(simple) < 4:
                    simple = [[round(x, 5), round(y, 5)] for x, y in original]
                if len(simple) >= 4:
                    anillos.append(simple)
            if anillos:
                salida.append(anillos)
        if not salida:
            raise ValueError(f"la jurisdiccion {props.get('in1')} quedo sin poligonos")
        vertices += sum(len(a) for p in salida for a in p)
        provincias[str(props["in1"])] = {"nombre": props.get("nam"), "fna": props.get("fna"),
                                         "poligonos": salida}
    return {
        "procedencia": {
            "fuente": "Instituto Geografico Nacional (IGN) - WFS ign:provincia",
            "url": url,
            "descargado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sello_del_servicio": datos.get("timeStamp"),
            "sha256_origen": hashlib.sha256(crudo).hexdigest(),
            "vertices_origen": vertices_origen,
            "simplificacion": f"Douglas-Peucker {TOLERANCIA} grados, 5 decimales; omitido lo "
                              f"que queda entero al sur de {SUR_OMITIDO}",
            "vertices": vertices, "jurisdicciones": len(provincias),
            "crs": "EPSG:4326 (lon, lat)", "licencia": LICENCIA,
            "reproducir": "python scripts/geo_poligonos_provincias.py",
        },
        "provincias": dict(sorted(provincias.items())),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", type=Path, default=POR_DEFECTO)
    ap.add_argument("--desde-archivo", type=Path, default=None,
                    help="GeoJSON ya bajado del mismo WFS")
    args = ap.parse_args()
    url = f"{WFS}?{urllib.parse.urlencode(PARAMETROS)}"
    if args.desde_archivo:
        crudo = args.desde_archivo.read_bytes()
    else:
        peticion = urllib.request.Request(url, headers={"User-Agent": AGENTE})
        with urllib.request.urlopen(peticion, timeout=600) as respuesta:
            crudo = respuesta.read()
    salida = construir(json.loads(crudo), url, crudo)
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(json.dumps(salida, ensure_ascii=False, separators=(",", ":")),
                           encoding="utf-8")
    p = salida["procedencia"]
    print(f"{args.salida}: {p['jurisdicciones']} jurisdicciones, {p['vertices']} vertices "
          f"(de {p['vertices_origen']}), {args.salida.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
