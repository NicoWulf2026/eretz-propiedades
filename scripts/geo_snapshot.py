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
from pathlib import Path
from typing import Any

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
        clave = next(k for k in datos if isinstance(datos[k], list))
        return datos[clave], int(datos.get("total") or 0), "volcado"
    except Exception:  # noqa: BLE001 - se cae al paginado, que es equivalente
        pass

    filas: list[dict[str, Any]] = []
    total = 0
    while True:
        datos = bajar(f"{BASE}/{recurso}?max={PAGINA}&inicio={len(filas)}")
        clave = next(k for k in datos
                     if k not in ("cantidad", "inicio", "total", "parametros"))
        total = int(datos.get("total") or 0)
        pagina = datos.get(clave) or []
        if not pagina:
            break
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
    destino.mkdir(parents=True, exist_ok=True)
    manifiesto: dict[str, Any] = {
        "fuente": "GeoRef Argentina - datos.gob.ar",
        "api": BASE,
        "licencia": "oficial, gratuita, sin credenciales",
        "descargado": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "recursos": {},
    }

    for recurso in RECURSOS:
        filas, total, via = traer(recurso)
        archivo = destino / f"{recurso.replace('-', '_')}.json"
        crudo = json.dumps(filas, ensure_ascii=False, indent=1)
        archivo.write_text(crudo, encoding="utf-8")
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
