#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""QA semantica de la API v2 sobre una snapshot REAL (candidata o servida). Solo lectura.

Pedido del sprint de beta (06-10, item 14): contratos, NULL, cero, limites de paginado,
orden, consistencia lista/mapa, exclusiones, no encontrado, sugerencias y rendimiento local,
sobre la snapshot que se va a servir -no sobre la sintetica del contrato del frontend-.
Levanta la API en proceso (TestClient) apuntando a `--snapshot`. Una latencia local no es
un SLA de produccion: se informa como referencia. `database_writes: 0`.

    python scripts/qa_api_real.py --snapshot <ruta.sqlite3> [--json salida.json]
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import statistics
import sys
import time
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
ARGENTINA = {"north": -21.7, "south": -55.1, "east": -53.5, "west": -73.6}


def correr(snapshot: Path) -> dict[str, Any]:
    os.environ["ERETZ_API_SNAPSHOT"] = str(snapshot)
    sys.path[:0] = [str(RAIZ)]
    from fastapi.testclient import TestClient
    from api.main import app
    c = TestClient(app)
    db = sqlite3.connect(f"file:{snapshot.as_posix()}?mode=ro", uri=True)
    uno = lambda q, *a: db.execute(q, a).fetchone()  # noqa: E731
    casos: list[dict[str, Any]] = []
    tiempos: dict[str, list[float]] = {}

    def get(nombre: str, url: str, **params):
        t = time.perf_counter()
        r = c.get(url, params=params)
        tiempos.setdefault(nombre, []).append((time.perf_counter() - t) * 1000)
        return r

    def caso(nombre: str, ok: bool, detalle: Any = None):
        casos.append({"caso": nombre, "ok": bool(ok), "detalle": detalle})

    filas = uno("select count(*) from propiedades")[0]
    r = get("healthz", "/healthz")
    caso("healthz_200", r.status_code == 200)
    r = get("readyz", "/readyz").json()
    caso("readyz_cuenta_la_snapshot", r.get("status") == "ok" and r.get("propiedades") == filas
         and r.get("sintetica") is False and r.get("database_writes") == 0, r)

    lista = get("lista", "/v2/propiedades", limit=100).json()
    caso("lista_total_igual_a_filas", lista["total"] == filas, {"total": lista["total"], "filas": filas})
    precios = [d.get("precio") for d in lista["data"]]
    con = [p for p in precios if p is not None]
    caso("orden_precio_desc_nulos_al_final",
         con == sorted(con, reverse=True) and precios[:len(con)] == con, precios[:5])
    caso("limite_101_rechazado", get("lim", "/v2/propiedades", limit=101).status_code == 422)
    caso("offset_negativo_rechazado", get("lim", "/v2/propiedades", offset=-1).status_code == 422)
    fuera = get("lim", "/v2/propiedades", limit=5, offset=filas + 10)
    caso("offset_mas_alla_del_total_vacio", fuera.status_code == 200 and fuera.json()["data"] == [])

    venta = get("lista_venta", "/v2/propiedades", operacion="venta", limit=100).json()
    caso("filtro_operacion_venta", all(d.get("operacion") == "venta" for d in venta["data"])
         and venta["total"] == uno("select count(*) from propiedades where operacion='venta'")[0],
         venta["total"])

    sin_precio = uno("select id from propiedades where precio is null limit 1")
    if sin_precio:
        d = get("detalle", f"/v2/propiedades/{sin_precio[0]}").json()
        caso("NULL_precio_sigue_null_en_el_detalle", d.get("precio") is None, d.get("precio"))
    cero = uno("select id from propiedades where dormitorios=0 limit 1")
    if cero:
        d = get("detalle", f"/v2/propiedades/{cero[0]}").json()
        caso("cero_dormitorios_sigue_cero", d.get("dormitorios") == 0, d.get("dormitorios"))
    caso("precio_cero_no_servido", uno("select count(*) from propiedades where precio=0")[0] == 0)
    caso("no_encontrado_404", get("detalle", "/v2/propiedades/no-existe-0000").status_code == 404)

    m = get("mapa", "/v2/propiedades/mapa", operacion="venta", **ARGENTINA).json()
    # `total_matches` = lo que cumple los filtros (lo mismo que la lista);
    # `viewport_matches` = lo que tiene punto en la caja y no esta en GEO_CONFLICT.
    con_coord = uno("select count(*) from propiedades where operacion='venta' and latitud is not null "
                    "and coalesce(geo_estado,'') != 'GEO_CONFLICT' and latitud between -55.1 and -21.7 "
                    "and longitud between -73.6 and -53.5")[0]
    caso("mapa_total_igual_a_la_lista_con_los_mismos_filtros", m.get("total_matches") == venta["total"],
         {"mapa": m.get("total_matches"), "lista": venta["total"]})
    caso("mapa_viewport_igual_a_la_base_con_punto_sin_conflicto", m.get("viewport_matches") == con_coord,
         {"viewport": m.get("viewport_matches"), "base": con_coord})
    caso("mapa_truncado_declarado", m.get("truncated") == (m.get("viewport_matches", 0) > m.get("returned_points", 0)))
    marcadores = m.get("data") or m.get("items") or m.get("propiedades") or []
    if marcadores:
        mid = marcadores[0].get("id")
        caso("marcador_del_mapa_existe_en_el_detalle",
             get("detalle", f"/v2/propiedades/{mid}").status_code == 200, mid)

    for nombre, url, params in (("areas", "/v2/areas", {"q": "pal"}), ("barrios", "/v2/barrios", {}),
                                ("filtros", "/v2/filtros", {}), ("sugerencias", "/v2/sugerencias", {"q": "pal"})):
        r = get(nombre, url, **params)
        cuerpo = r.json() if r.status_code == 200 else None
        caso(f"{nombre}_200_no_vacio", r.status_code == 200 and bool(cuerpo), str(cuerpo)[:120])
    caso("sugerencias_q_corta_rechazada", get("sugerencias", "/v2/sugerencias", q="a").status_code == 422)

    exterior = uno("select count(*) from propiedades where documento like '%PRESERVED_NOT_PUBLISHED%'")[0]
    caso("exterior_no_publicado", exterior == 0, exterior)

    for _ in range(3):
        get("lista", "/v2/propiedades", limit=24)
        get("mapa", "/v2/propiedades/mapa", **ARGENTINA)
    medianas = {k: round(statistics.median(v), 1) for k, v in tiempos.items()}
    db.close()
    return {"snapshot": str(snapshot), "filas": filas, "casos": casos,
            "ok": sum(x["ok"] for x in casos), "total": len(casos),
            "medianas_ms_locales": medianas, "database_writes": 0}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", type=Path, required=True)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    res = correr(a.snapshot)
    if a.json:
        a.json.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    for x in res["casos"]:
        print(("OK  " if x["ok"] else "FALLA ") + x["caso"] + ("" if x["ok"] else f"  {x['detalle']}"))
    print(f"{res['ok']}/{res['total']}  medianas locales ms: {res['medianas_ms_locales']}")
    return 0 if res["ok"] == res["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
