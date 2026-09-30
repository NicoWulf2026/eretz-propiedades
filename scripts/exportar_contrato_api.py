#!/usr/bin/env python
"""Respuestas REALES de la API v2 para el test de contrato del frontend.

Los esquemas del frontend (`frontend/src/lib/api-v2/schemas.ts`) se probaban con
fixtures escritos a mano: si la API cambiaba la forma de una respuesta, ningun
test lo veia hasta el navegador. Esto levanta la API en proceso sobre la
snapshot SINTETICA (`snapshot_sintetica.py`), pide cada endpoint que el frontend
consume y guarda las respuestas tal cual en
`frontend/src/test/api-v2-contrato-real.json`.

- `tests/test_contrato_api_frontend.py` regenera y compara: si la API cambio y
  el archivo no, falla (correr este script y revisar el diff).
- `frontend/src/lib/api-v2/contrato-real.test.ts` pasa cada respuesta por el
  parser real del frontend.

    python scripts/exportar_contrato_api.py            # escribe el archivo
    python scripts/exportar_contrato_api.py --check    # solo compara (exit 1 si difiere)
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

SALIDA = RAIZ / "frontend" / "src" / "test" / "api-v2-contrato-real.json"

# (nombre, metodo, ruta, params, cuerpo, parser del frontend que la consume)
CASOS: list[tuple[str, str, str, dict[str, Any], Any, str]] = [
    ("buscar_texto", "GET", "/v2/buscar", {"q": "casa", "limit": 5}, None, "search_page"),
    ("buscar_combinado", "GET", "/v2/buscar",
     {"q": "casa", "operacion": "venta", "tipo": "casa", "moneda": "USD", "precio_min": 1,
      "dormitorios": 1, "limit": 5}, None, "search_page"),
    ("buscar_precio_asc", "GET", "/v2/buscar", {"sort": "price_asc", "moneda": "USD", "limit": 5},
     None, "search_page"),
    ("buscar_area", "GET", "/v2/buscar",
     {"nivel": "LOCALIDAD", "area": "Rosario", "limit": 5}, None, "search_page"),
    ("buscar_vacio", "GET", "/v2/buscar", {"q": "zzznadacoincide"}, None, "search_page"),
    ("propiedades_pagina", "GET", "/v2/propiedades", {"limit": 5}, None, "page"),
    ("mapa", "GET", "/v2/propiedades/mapa",
     {"north": -30, "south": -40, "east": -55, "west": -70, "limit": 50}, None, "map"),
    ("areas", "GET", "/v2/areas", {"q": "Córdoba"}, None, "areas"),
    ("barrios", "GET", "/v2/barrios", {}, None, "neighborhoods"),
    ("sugerencias", "GET", "/v2/sugerencias", {"q": "cor"}, None, "suggestions"),
    ("filtros", "GET", "/v2/filtros", {}, None, "filters"),
]
# Detalle, agencia y lote: sobre los casos borde con nombre de la sintetica.
DETALLES = ("sin_titulo", "sin_titulo_ni_datos", "sin_precio", "sin_moneda",
            "sin_coordenadas", "conflicto", "solo_provincia", "municipio", "combinado")


def capturar() -> dict[str, Any]:
    from fastapi.testclient import TestClient

    from api import v2
    from api.main import app
    from scripts.snapshot_sintetica import CASOS as CASOS_SINTETICOS
    from scripts.snapshot_sintetica import construir

    anterior = v2.SNAPSHOT
    with tempfile.TemporaryDirectory() as tmp:
        ruta = Path(tmp) / "ERETZ_API_SNAPSHOT.sqlite3"
        construir(ruta)
        v2.SNAPSHOT = ruta
        try:
            cliente = TestClient(app)
            salida: dict[str, Any] = {}

            def pedir(nombre, metodo, url, params, cuerpo, parser):
                r = cliente.request(metodo, url, params=params,
                                    **({"json": cuerpo} if cuerpo is not None else {}))
                if r.status_code != 200:
                    raise SystemExit(f"{nombre}: {url} respondio {r.status_code}: {r.text[:200]}")
                salida[nombre] = {"parser": parser, "metodo": metodo, "ruta": url,
                                  "params": params, "respuesta": r.json()}

            for caso in CASOS:
                pedir(*caso)
            for nombre in DETALLES:
                pedir(f"detalle_{nombre}", "GET", f"/v2/propiedades/{CASOS_SINTETICOS[nombre]}",
                      {}, None, "property")
            agencia = salida["detalle_combinado"]["respuesta"]["agency_id"]
            pedir("agencia", "GET", f"/v2/agencias/{agencia}", {}, None, "agency")
            ids = [CASOS_SINTETICOS[n] for n in DETALLES]
            pedir("lote", "POST", "/v2/propiedades/batch", {}, {"ids": ids + ["no-existe"]}, "batch")
        finally:
            v2.SNAPSHOT = anterior
    return salida


def serializar(datos: dict[str, Any]) -> str:
    return json.dumps(datos, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    texto = serializar(capturar())
    if args.check:
        actual = SALIDA.read_text(encoding="utf-8") if SALIDA.exists() else ""
        if actual != texto:
            print(f"{SALIDA} no coincide con la API: correr scripts/exportar_contrato_api.py")
            return 1
        print("contrato al dia")
        return 0
    SALIDA.write_text(texto, encoding="utf-8")
    print(f"{SALIDA}: {len(json.loads(texto))} respuestas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
