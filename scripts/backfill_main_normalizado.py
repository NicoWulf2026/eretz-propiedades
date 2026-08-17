#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Backfill de `nombre_normalizado` en `inmobiliarias_main`.

1.983 de 7.003 filas visibles de main tienen esa columna en NULL. No es un
detalle cosmetico: todo el dedupe contra main la usa como clave, asi que esas
filas son invisibles para cualquier cruce por mas que su nombre coincida
exactamente. Eso ya produjo 31 duplicados staged en la campana de Roomix.

Usa el MISMO normalizador que el cruce y que el motor de dedupe
(`eretz_dedupe.norm_name`). Un normalizador propio seria un tercer dialecto y
volveria a partir las claves.

Por defecto es dry-run: mide y no escribe. Escribir requiere una conexion con
UPDATE sobre main, que hoy no existe; el modo `--commit` esta implementado pero
falla temprano y a proposito si no se le pasa una conexion habilitada.

Regla que no se negocia: si al normalizar aparecen DOS filas distintas de main
con el mismo normalizado, ninguna de las dos se escribe. Poblar la columna con
un valor que colisiona convertiria un dato faltante en un dato ambiguo, que es
peor: el faltante se nota, el ambiguo no.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


d = _load("eretz_dedupe")

SELECT_MAIN = """
select id, nombre, nombre_normalizado, ciudad, provincia, web, fuente
  from public.inmobiliarias_main
 order by id
"""

UPDATE_UNA = """
update public.inmobiliarias_main
   set nombre_normalizado = %(norm)s
 where id = %(id)s
   and nombre_normalizado is null
"""


def analizar(filas: list[dict]) -> dict:
    """Separa lo que se puede escribir de lo que no. No toca nada."""
    ya = [f for f in filas if (f.get("nombre_normalizado") or "").strip()]
    nulos = [f for f in filas if not (f.get("nombre_normalizado") or "").strip()]

    # Lo que ya existe cuenta como ocupado: si un nulo normaliza a algo que ya
    # esta tomado, no es un hueco, es una colision.
    ocupado: dict[str, list[int]] = defaultdict(list)
    for f in ya:
        ocupado[(f["nombre_normalizado"] or "").strip().lower()].append(f["id"])

    generado: dict[str, list[dict]] = defaultdict(list)
    vacios, seguros, conflictos = [], [], []
    for f in nulos:
        n = d.norm_name(f["nombre"] or "")
        if not n or len(n) < 3:
            vacios.append({**f, "motivo": "el nombre no produce clave util"})
            continue
        generado[n].append(f)

    for n, grupo in generado.items():
        choca_con_existente = ocupado.get(n, [])
        if len(grupo) > 1 or choca_con_existente:
            for f in grupo:
                conflictos.append({
                    "id": f["id"], "nombre": f["nombre"], "normalizado_propuesto": n,
                    "otros_nulos_con_la_misma_clave": [g["id"] for g in grupo if g["id"] != f["id"]],
                    "ya_existentes_con_la_misma_clave": choca_con_existente,
                    "motivo": ("dos filas distintas normalizan igual"
                               if len(grupo) > 1 else "la clave ya esta ocupada en main"),
                })
        else:
            f = grupo[0]
            seguros.append({"id": f["id"], "nombre": f["nombre"], "normalizado_propuesto": n})

    return {
        "total": len(filas), "ya_normalizadas": len(ya), "nulas": len(nulos),
        "seguros": seguros, "conflictos": conflictos, "sin_clave": vacios,
        "por_fuente_nulas": Counter((f.get("fuente") or "(sin fuente)") for f in nulos),
    }


def informe(a: dict, salida: Path | None) -> None:
    print("### BACKFILL nombre_normalizado — DRY RUN ###", flush=True)
    print(f"  filas de main:            {a['total']}", flush=True)
    print(f"  ya normalizadas:          {a['ya_normalizadas']}", flush=True)
    print(f"  con NULL:                 {a['nulas']}", flush=True)
    print(f"  escribibles sin riesgo:   {len(a['seguros'])}", flush=True)
    print(f"  en conflicto (no tocar):  {len(a['conflictos'])}", flush=True)
    print(f"  sin clave util:           {len(a['sin_clave'])}", flush=True)
    print(f"  NULL por fuente:          {dict(a['por_fuente_nulas'])}", flush=True)
    restante = a["nulas"] - len(a["seguros"])
    print(f"\n  NULL despues del backfill: {restante} "
          f"({restante / a['nulas'] * 100:.1f}% de los actuales)" if a["nulas"] else "", flush=True)
    if a["conflictos"]:
        print("\n  ejemplos de conflicto:", flush=True)
        for c in a["conflictos"][:8]:
            print(f"    id={c['id']:>6} {c['nombre'][:44]:44} -> {c['normalizado_propuesto'][:30]:30} "
                  f"{c['motivo']}", flush=True)
    if salida:
        salida.write_text(json.dumps(
            {k: (v if k not in ("por_fuente_nulas",) else dict(v)) for k, v in a.items()},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  detalle -> {salida}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", help="JSON con las filas de main (modo offline)")
    ap.add_argument("--dsn-env", default="ERETZ_MAIN_WRITE_URL",
                    help="variable de entorno con la conexion; nunca se imprime")
    ap.add_argument("--out", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA\backfill_normalizado_dryrun.json")
    ap.add_argument("--commit", action="store_true",
                    help="escribe de verdad; sin esto solo mide")
    a = ap.parse_args()

    if a.input:
        filas = json.loads(Path(a.input).read_text(encoding="utf-8"))
        if isinstance(filas, dict):
            filas = filas.get("rows", [])
    else:
        import os
        dsn = (os.environ.get(a.dsn_env) or "").strip()
        if not dsn:
            print(f"  sin conexion: la variable {a.dsn_env} no esta definida.", flush=True)
            print("  este script mide con --input <json> o escribe con una conexion valida.",
                  flush=True)
            return 3
        import psycopg
        with psycopg.connect(dsn, connect_timeout=15) as conn, conn.cursor() as cur:
            cur.execute(SELECT_MAIN)
            cols = [c.name for c in cur.description]
            filas = [dict(zip(cols, r)) for r in cur.fetchall()]

    analisis = analizar(filas)
    informe(analisis, Path(a.out) if a.out else None)

    if not a.commit:
        print("\n  DRY-RUN: no se escribio nada.", flush=True)
        return 0

    import os
    dsn = (os.environ.get(a.dsn_env) or "").strip()
    if not dsn:
        print("\n  --commit pedido pero no hay conexion con UPDATE sobre main.", flush=True)
        return 3

    import psycopg
    escritas = 0
    with psycopg.connect(dsn, connect_timeout=15) as conn:
        with conn.cursor() as cur:
            # Solo los seguros, y el WHERE repite `is null` para que reejecutar
            # no pise un valor que alguien haya puesto entre medio.
            for s in analisis["seguros"]:
                cur.execute(UPDATE_UNA, {"norm": s["normalizado_propuesto"], "id": s["id"]})
                escritas += cur.rowcount
        conn.commit()
    print(f"\n  filas actualizadas: {escritas} de {len(analisis['seguros'])}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
