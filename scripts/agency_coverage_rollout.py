#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Rollout de Agency Coverage a la tabla de staging de inmobiliarias.

Conecta con ERETZ_AGENCY_COVERAGE_DATABASE_URL, un rol de privilegio mínimo que
sólo puede leer inmobiliarias_main y leer/insertar en inmobiliarias_staging.

Flujo: preflight -> verificacion de privilegios -> dedupe -> canary -> batches,
verificando despues de cada paso. Nada se inserta fuera de staging.

No imprime nunca la credencial ni ninguna parte de ella.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover
    psycopg = None

ENV_VAR = "ERETZ_AGENCY_COVERAGE_DATABASE_URL"
SOURCE_NAME = "roomix_coverage_v1"


def log(msg: str) -> None:
    print(msg, flush=True)


# --------------------------------------------------------------- introspeccion
def discover(cur) -> dict:
    """Forma real de la tabla de staging. No se asume schema, columnas ni
    clave de conflicto: se leen del catálogo."""
    cur.execute("""
        select table_schema, column_name, is_nullable, column_default
          from information_schema.columns
         where table_name = 'inmobiliarias_staging'
         order by table_schema, ordinal_position
    """)
    rows = cur.fetchall()
    if not rows:
        raise RuntimeError("inmobiliarias_staging no es visible para este rol")
    schema = rows[0]["table_schema"]
    cols = {r["column_name"] for r in rows if r["table_schema"] == schema}

    cur.execute("""
        select i.relname as idx, pg_get_indexdef(i.oid) as def
          from pg_index x
          join pg_class c on c.oid = x.indrelid
          join pg_class i on i.oid = x.indexrelid
          join pg_namespace n on n.oid = c.relnamespace
         where c.relname = 'inmobiliarias_staging' and n.nspname = %s and x.indisunique
    """, (schema,))
    uniques = cur.fetchall()
    return {"schema": schema, "columns": cols, "uniques": uniques}


def check_privileges(cur) -> dict:
    cur.execute("""
        select current_user as usuario,
               has_table_privilege('public.inmobiliarias_main','SELECT') as main_select,
               has_table_privilege('public.inmobiliarias_main','INSERT') as main_insert,
               has_table_privilege('public.inmobiliarias_main','UPDATE') as main_update
    """)
    return cur.fetchone()


# ------------------------------------------------------------------- dedupe
def existing_keys(cur, schema: str) -> tuple[set, set]:
    """Nombres normalizados ya presentes. Se lee en el momento del rollout, no
    de un snapshot viejo: entre el crosswalk y ahora pudo cargarse algo."""
    cur.execute("select lower(coalesce(nombre_normalizado, nombre)) k from public.inmobiliarias_main")
    main = {r["k"] for r in cur.fetchall() if r["k"]}
    cur.execute(f"select lower(coalesce(nombre_normalizado, nombre)) k from {schema}.inmobiliarias_staging")
    stg = {r["k"] for r in cur.fetchall() if r["k"]}
    return main, stg


# ------------------------------------------------------------------- insert
def insert_batch(cur, schema: str, cols: set, rows: list[dict]) -> int:
    """Inserta sólo columnas que existen de verdad. ON CONFLICT DO NOTHING sobre
    la clave única real cuando la hay: ejecutar dos veces no duplica."""
    if not rows:
        return 0
    usable = [c for c in rows[0] if c in cols]
    collist = ", ".join(f'"{c}"' for c in usable)
    placeholders = ", ".join(["%s"] * len(usable))
    sql = f'insert into {schema}.inmobiliarias_staging ({collist}) values ({placeholders})'
    sql += " on conflict do nothing"
    inserted = 0
    for r in rows:
        vals = []
        for c in usable:
            v = r[c]
            vals.append(json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
        cur.execute(sql, vals)
        inserted += cur.rowcount
    return inserted


def verify(cur, schema: str) -> dict:
    cur.execute(f"""
        select count(*) total,
               count(*) filter (where fuente = %s) mios,
               count(distinct lower(coalesce(nombre_normalizado, nombre)))
                 filter (where fuente = %s) distintos
          from {schema}.inmobiliarias_staging
    """, (SOURCE_NAME, SOURCE_NAME))
    return cur.fetchone()


# -------------------------------------------------------------------- canary
def pick_canary(rows: list[dict], n: int = 12) -> list[dict]:
    """Muestra representativa: franquicias distintas, independientes grandes y
    cola. Determinista para que el canary sea reproducible."""
    fr, indep = [], []
    seen_brand = set()
    for r in rows:
        b = (r["metadata_zonaprop"].get("franchise") or {}).get("brand")
        if b and b not in seen_brand:
            seen_brand.add(b); fr.append(r)
        elif not b:
            indep.append(r)
    out = fr[:4] + indep[:4] + indep[-4:]
    seen, uniq = set(), []
    for r in out:
        k = r["nombre_normalizado"]
        if k not in seen:
            seen.add(k); uniq.append(r)
    return uniq[:n]


# ---------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--batch-size", type=int, default=200)
    ap.add_argument("--canary", type=int, default=12)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    dsn = os.environ.get(ENV_VAR, "")
    if not dsn:
        log(f"FALTA {ENV_VAR}. El rollout no puede ejecutarse sin credencial.")
        return 2
    if psycopg is None:
        log("psycopg no instalado"); return 2

    rows = [json.loads(l) for l in (Path(a.data_dir) / "staging_rows.jsonl").open(encoding="utf-8") if l.strip()]
    log(f"candidatas preparadas: {len(rows)}")

    with psycopg.connect(dsn, connect_timeout=30, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            log("\n### PREFLIGHT ###")
            priv = check_privileges(cur)
            log(f"  rol conectado: {priv['usuario']}")
            log(f"  inmobiliarias_main  SELECT={priv['main_select']} "
                f"INSERT={priv['main_insert']} UPDATE={priv['main_update']}")
            if not priv["main_select"]:
                log("  FALTA SELECT sobre inmobiliarias_main"); return 3
            if priv["main_insert"] or priv["main_update"]:
                log("  ATENCION: el rol tiene mas privilegios de los necesarios sobre main")

            info = discover(cur)
            log(f"  staging en schema: {info['schema']}")
            log(f"  columnas visibles: {len(info['columns'])}")
            log(f"  indices unicos:    {[u['idx'] for u in info['uniques']] or 'ninguno'}")

            usable = [c for c in rows[0] if c in info["columns"]]
            dropped = [c for c in rows[0] if c not in info["columns"]]
            log(f"  columnas que se envian: {len(usable)}")
            if dropped:
                log(f"  columnas que la tabla NO tiene (se omiten, no se inventa esquema): {dropped}")

            log("\n### DEDUPE CONTRA EL ESTADO ACTUAL ###")
            main_keys, stg_keys = existing_keys(cur, info["schema"])
            log(f"  inmobiliarias_main:    {len(main_keys)}")
            log(f"  staging:               {len(stg_keys)}")
            pending, skipped = [], Counter()
            for r in rows:
                k = (r["nombre_normalizado"] or "").lower()
                if not k:
                    skipped["sin_clave"] += 1
                elif k in main_keys:
                    skipped["ya_en_main"] += 1
                elif k in stg_keys:
                    skipped["ya_en_staging"] += 1
                else:
                    pending.append(r); stg_keys.add(k)
            log(f"  a insertar: {len(pending)} | descartadas: {dict(skipped) or 'ninguna'}")

            if a.dry_run:
                log("\n  DRY-RUN: no se escribe. Preflight y dedupe OK.")
                return 0

            before = verify(cur, info["schema"])
            log(f"\n  staging antes: total={before['total']} mios={before['mios']}")

            log("\n### CANARY ###")
            canary = pick_canary(pending, a.canary)
            with conn.transaction():
                n = insert_batch(cur, info["schema"], info["columns"], canary)
            mid = verify(cur, info["schema"])
            log(f"  insertadas: {n} de {len(canary)}")
            log(f"  staging: total={mid['total']} mios={mid['mios']} distintos={mid['distintos']}")
            if mid["mios"] != mid["distintos"]:
                log("  FALLO: hay duplicados por nombre normalizado"); return 4
            if n != len(canary):
                log("  aviso: algunas filas del canary ya existian (on conflict)")
            # Idempotencia: reinsertar el canary no debe agregar nada.
            with conn.transaction():
                again = insert_batch(cur, info["schema"], info["columns"], canary)
            if again != 0:
                log(f"  FALLO de idempotencia: reinsertar agrego {again} filas"); return 5
            log("  idempotencia verificada: reinsertar el canary agrego 0 filas")

            done_keys = {r["nombre_normalizado"] for r in canary}
            rest = [r for r in pending if r["nombre_normalizado"] not in done_keys]

            log(f"\n### ROLLOUT ({len(rest)} restantes, lotes de {a.batch_size}) ###")
            total_ins, failures = n, 0
            for i in range(0, len(rest), a.batch_size):
                chunk = rest[i:i + a.batch_size]
                try:
                    with conn.transaction():
                        ins = insert_batch(cur, info["schema"], info["columns"], chunk)
                except Exception as e:
                    failures += 1
                    log(f"  lote {i//a.batch_size+1}: ERROR {str(e)[:90]} (transaccion revertida)")
                    continue
                total_ins += ins
                st = verify(cur, info["schema"])
                ok = st["mios"] == st["distintos"]
                log(f"  lote {i//a.batch_size+1:3d}: +{ins:4d} | staging mios={st['mios']:5d} "
                    f"distintos={st['distintos']:5d} {'OK' if ok else 'DUPLICADOS'}")
                if not ok:
                    log("  se detiene: aparecieron duplicados"); return 6
                time.sleep(0.2)

            after = verify(cur, info["schema"])
            log("\n### RESULTADO ###")
            log(f"  insertadas en total: {total_ins}")
            log(f"  lotes con error:     {failures}")
            log(f"  staging antes:       {before['total']} (mios {before['mios']})")
            log(f"  staging despues:     {after['total']} (mios {after['mios']})")
            log(f"  duplicados:          {after['mios'] - after['distintos']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
