#!/usr/bin/env python
"""Baja el poligono oficial de la Ciudad Autonoma de Buenos Aires y lo versiona.

Fuente: Instituto Geografico Nacional (IGN), servicio WFS publico, capa
`ign:provincia` («Division politico territorial de primer orden. Incluye la
Ciudad Autonoma de Buenos Aires»), entidad `in1 = 02`, EPSG:4326.

Licencia declarada por el servicio (ows:AccessConstraints): se permite acceder,
copiar, reprocesar, reutilizar y redistribuir libremente la informacion segun el
Articulo 2 de la Ley 27.275 de acceso a la informacion publica.

El archivo se guarda tal cual lo entrega el IGN -sin simplificar ni suavizar- y
con su procedencia adentro: url, fecha de descarga, cantidad de vertices y
sha256 de las coordenadas. Si una descarga futura cambia la geometria, el hash
lo muestra en el diff.

Uso: python scripts/geo_poligono_caba.py [--salida connectors/geometria/caba_ign.geojson]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

WFS = "https://wms.ign.gob.ar/geoserver/ows"
PARAMETROS = {
    "service": "WFS", "version": "2.0.0", "request": "GetFeature",
    "typeNames": "ign:provincia", "outputFormat": "application/json",
    "srsName": "EPSG:4326", "CQL_FILTER": "in1='02'",
}
AGENTE = "ERETZ-Propiedades/1.0 (geometria oficial)"
LICENCIA = ("IGN WFS ows:AccessConstraints: libre acceso, copia, reproceso, reutilizacion y "
            "redistribucion segun el Art. 2 de la Ley 27.275")
POR_DEFECTO = Path(__file__).resolve().parents[1] / "connectors" / "geometria" / "caba_ign.geojson"


def huella(geometria: dict) -> str:
    texto = json.dumps(geometria["coordinates"], separators=(",", ":"))
    return hashlib.sha256(texto.encode("ascii")).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", type=Path, default=POR_DEFECTO)
    args = ap.parse_args()
    url = f"{WFS}?{urllib.parse.urlencode(PARAMETROS)}"
    peticion = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(peticion, timeout=120) as respuesta:
        datos = json.loads(respuesta.read().decode("utf-8"))
    rasgos = [f for f in datos.get("features", []) if f["properties"].get("in1") == "02"]
    if len(rasgos) != 1:
        raise SystemExit(f"se esperaba exactamente un rasgo para CABA y llegaron {len(rasgos)}")
    rasgo = rasgos[0]
    if rasgo["properties"].get("fna") != "Ciudad Autónoma de Buenos Aires":
        raise SystemExit(f"el rasgo no es CABA: {rasgo['properties']}")
    geometria = rasgo["geometry"]
    vertices = sum(len(anillo) for poligono in geometria["coordinates"] for anillo in poligono)
    salida = {
        "type": "Feature",
        "properties": {
            **rasgo["properties"],
            "procedencia": {
                "fuente": "Instituto Geografico Nacional (IGN) - WFS ign:provincia",
                "url": url,
                "descargado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "sello_del_servicio": datos.get("timeStamp"),
                "crs": "EPSG:4326 (lon, lat)",
                "licencia": LICENCIA,
                "vertices": vertices,
                "sha256_coordenadas": huella(geometria),
                "reproducir": "python scripts/geo_poligono_caba.py",
            },
        },
        "geometry": geometria,
    }
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(json.dumps(salida, ensure_ascii=False), encoding="utf-8")
    print(f"{args.salida}: {vertices} vertices, sha256 {salida['properties']['procedencia']['sha256_coordenadas']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
