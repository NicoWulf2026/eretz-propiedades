#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Regression Gate entre dos snapshots de la API: la servida y la candidata.

Solo lectura (las dos se abren con mode=ro). `database_writes: 0`. Usa el MISMO
`regression_gate.compare` que el gate de la cola -misma identidad (agencia +
url normalizada), mismas clases: perdida sin explicar, recuperado, cambiado,
no observado-, pero sobre lo que el usuario VE: las filas servidas.

Existe para la beta del 12/10: el dia final tiene que ser correr, analizar y
decidir, no disenar. La snapshot no guarda `direccion` ni las urls de las fotos:
se compara `imagenes_n` (cantidad) y `localidad` como ciudad.

    python scripts/gate_de_snapshots.py --servida <sqlite> --candidata <sqlite> --salida <json>
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from scripts.regression_gate import compare  # noqa: E402

COLUMNAS = {"titulo": "titulo", "descripcion": "descripcion", "operacion": "operacion",
            "tipo_propiedad": "tipo_propiedad", "precio": "precio", "moneda": "moneda",
            "ciudad": "localidad", "barrio": "barrio", "provincia": "provincia",
            "superficie_total": "superficie_total", "superficie_cubierta": "superficie_cubierta",
            "ambientes": "ambientes", "dormitorios": "dormitorios", "banos": "banos",
            "latitud": "latitud", "longitud": "longitud"}


def filas(ruta: Path) -> list[dict]:
    con = sqlite3.connect(f"file:{ruta.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        salida = []
        sql = ("SELECT agency_id, source_url, imagenes_n, "
               + ", ".join(sorted(set(COLUMNAS.values()))) + " FROM propiedades")
        for r in con.execute(sql):
            fila = {"canonical_agency_id": r["agency_id"], "source_url": r["source_url"]}
            fila.update({campo: r[col] for campo, col in COLUMNAS.items()})
            # Cantidad de fotos como presencia: 0 o NULL es «sin fotos».
            fila["imagenes"] = ["x"] * int(r["imagenes_n"] or 0) or None
            salida.append(fila)
        return salida
    finally:
        con.close()


def resumen(resultado: dict, top: int = 15) -> dict:
    por_agencia: dict[str, Counter] = defaultdict(Counter)
    for c in resultado["changes"]:
        por_agencia[c["agency"]][c["kind"]] += 1
    graves = ("UNEXPLAINED_LOSS", "INVENTORY_NOT_OBSERVED", "DIMENSION_MOVE_REVIEW")
    peores = sorted(por_agencia.items(), key=lambda kv: -sum(kv[1][g] for g in graves))[:top]
    return {"status": resultado["status"], "old_rows": resultado["old_rows"],
            "fresh_rows": resultado["fresh_rows"], "matched_rows": resultado["matched_rows"],
            "counts": resultado["counts"],
            "agencias_con_cambios": len(por_agencia),
            "peores_agencias": [{"agencia": a, **dict(c)} for a, c in peores
                                if any(c[g] for g in graves)],
            "issues": {"old": len(resultado["old_issues"]), "fresh": len(resultado["fresh_issues"])},
            "database_writes": 0}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--servida", type=Path, required=True)
    ap.add_argument("--candidata", type=Path, required=True)
    ap.add_argument("--salida", type=Path, default=None)
    args = ap.parse_args(argv)
    resultado = compare(filas(args.servida), filas(args.candidata))
    r = resumen(resultado)
    if args.salida:
        args.salida.write_text(json.dumps({"resumen": r, "detalle": resultado}, ensure_ascii=False),
                               encoding="utf-8")
    print(json.dumps(r, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
