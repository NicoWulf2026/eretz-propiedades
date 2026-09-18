#!/usr/bin/env python
"""Baja un snapshot local de GeoRef Argentina y deja como reproducirlo.

La normalizacion geografica corre sobre cientos de miles de propiedades: pedirle
una consulta remota a cada una seria inaceptable para el pipeline y descortes
con un servicio publico. Se baja una vez, se guarda con su procedencia, y todo
lo demas trabaja contra el archivo.

Fuente: GeoRef Argentina, del Servicio de Normalizacion de Datos Geograficos de
la Secretaria de Innovacion Publica (datos.gob.ar). Es oficial, gratuita y no
pide credenciales.

Cada recurso queda con su url, fecha de descarga, total declarado por la API,
cantidad efectivamente traida y sha256 del archivo, para poder comparar
versiones despues: si cambian ids o nombres, se ve en el manifiesto.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

if __package__:
    from .geo_reference import entity_ids
else:
    from geo_reference import entity_ids

BASE = "https://apis.datos.gob.ar/georef/api"
VOLCADO = "https://infra.datos.gob.ar/georef"
AGENTE = "ERETZ-Propiedades/1.0 (snapshot geografico)"
PAGINA = 5000
PAUSA = 1.0

# El orden es de mayor a menor granularidad territorial.
RECURSOS = ("provincias", "departamentos", "municipios",
            "localidades-censales", "localidades", "asentamientos")


def bajar(url: str) -> dict[str, Any]:
    peticion = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(peticion, timeout=90) as respuesta:
        return json.loads(respuesta.read().decode("utf-8"))


def _pagina(datos: Any, recurso: str, inicio: int | None) -> tuple[list[dict[str, Any]], int]:
    """Never certify an arbitrary list, unknown total or repeated entity ID."""
    if not isinstance(datos, dict):
        raise ValueError('GeoRef response must be an object')
    keys = {recurso, recurso.replace('-', '_')}
    present = [key for key in keys if key in datos]
    if len(present) != 1:
        raise ValueError('GeoRef response must contain the requested resource')
    rows, total = datos[present[0]], datos.get('total')
    if not isinstance(rows, list) or type(total) is not int or not 0 < total <= 100_000:
        raise ValueError('GeoRef requires a bounded positive declared total and rows')
    if len(rows) > total:
        raise ValueError('GeoRef row count exceeds declared total')
    if 'cantidad' in datos and (type(datos['cantidad']) is not int or datos['cantidad'] != len(rows)):
        raise ValueError('GeoRef page count does not match its rows')
    if inicio is not None and (type(datos.get('inicio')) is not int or datos['inicio'] != inicio):
        raise ValueError('GeoRef page offset does not match request')
    entity_ids(rows)
    return rows, total


def traer(recurso: str) -> tuple[list[dict[str, Any]], int, str]:
    """Trae un recurso completo, preferentemente del volcado oficial.

    La API topea `max + inicio` en 10.000, asi que `asentamientos` (mas de
    14.000) no se puede paginar por ahi. El volcado de infra.datos.gob.ar si lo
    sirve entero. `municipios` es el caso inverso: no esta en el volcado pero
    entra holgado bajo el tope, asi que cae al paginado.
    """
    archivo = recurso.replace("-", "_")
    try:
        datos = bajar(f"{VOLCADO}/{archivo}.json")
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        # Some official resources have no dump; validate the API fallback too.
    else:
        rows, total = _pagina(datos, recurso, None)
        if len(rows) != total:
            raise ValueError('GeoRef dump is incomplete')
        return rows, total, 'volcado'

    filas: list[dict[str, Any]] = []
    total: int | None = None
    vistos: set[str] = set()
    while True:
        datos = bajar(f"{BASE}/{recurso}?max={PAGINA}&inicio={len(filas)}")
        pagina, declarado = _pagina(datos, recurso, len(filas))
        if total is not None and total != declarado:
            raise ValueError('GeoRef total changed during pagination')
        total = declarado
        if total > 10_000:
            raise ValueError('GeoRef API window cannot enumerate this resource; a complete dump is required')
        if not pagina:
            raise ValueError('GeoRef pagination ended before declared total')
        ids = {row['id'] for row in pagina}
        if vistos & ids or len(filas) + len(pagina) > total:
            raise ValueError('GeoRef pagination repeats entities or exceeds total')
        vistos.update(ids)
        filas.extend(pagina)
        if len(filas) >= total:
            break
        time.sleep(PAUSA)
    return filas, total, "api"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--destino", default=r"D:\INMO CAPITAL\ERETZ_GEO")
    args = parser.parse_args()

    destino = Path(args.destino)
    # Finish and validate every download before touching the existing reference.
    # File promotion is not a multi-file transaction; disk/kill failures remain
    # a separate generation-publication concern.
    preparados = [(recurso, traer(recurso)) for recurso in RECURSOS]
    destino.mkdir(parents=True, exist_ok=True)
    manifiesto: dict[str, Any] = {
        'schema_version': 2,
        'sha256_scope': 'file_bytes_utf8_lf',
        "fuente": "GeoRef Argentina - datos.gob.ar",
        "api": BASE,
        "licencia": "oficial, gratuita, sin credenciales",
        "descargado": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "recursos": {},
    }

    for recurso, (filas, total, via) in preparados:
        archivo = destino / f"{recurso.replace('-', '_')}.json"
        crudo = json.dumps(filas, ensure_ascii=False, indent=1)
        archivo.write_bytes(crudo.encode('utf-8'))
        manifiesto["recursos"][recurso] = {
            "archivo": archivo.name,
            "url": f"{BASE}/{recurso}",
            "total_declarado": total,
            "filas_traidas": len(filas),
            "completo": len(filas) == total,
            "via": via,
            "sha256": hashlib.sha256(crudo.encode("utf-8")).hexdigest(),
        }
        print(f"  {recurso:22} {len(filas):6}/{total:<6} via {via:8} "
              f"-> {archivo.name}")
        time.sleep(PAUSA)

    (destino / "MANIFEST.json").write_text(
        json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding="utf-8")
    incompletos = [r for r, m in manifiesto["recursos"].items()
                   if not m["completo"]]
    print()
    print(f"manifiesto en {destino / 'MANIFEST.json'}")
    if incompletos:
        print(f"INCOMPLETOS: {incompletos}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
