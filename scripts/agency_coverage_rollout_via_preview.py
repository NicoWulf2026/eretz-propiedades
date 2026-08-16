#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Rollout de Agency Coverage a través del puente temporal de Preview.

No hace falta credencial de base en esta máquina: la conexión vive server-side
en Vercel Preview, detrás de Deployment Protection. Este cliente sólo manda
lotes de candidatas y verifica lo que la base responde.

El dedupe NO se hace acá. Lo hace `eretz_agency_coverage_stage_v1` contra el
estado real, bajo advisory lock por candidate key. Duplicar esa lógica del lado
del cliente daría una segunda respuesta que puede discrepar de la primera, y la
que manda es la de la función.

Secuencia: preflight -> snapshot -> canary 12 -> el mismo canary otra vez para
probar idempotencia -> lotes -> verificación después de cada lote -> snapshot
final -> reconciliación contra el crosswalk.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

FRONTEND = Path(r"D:\INMO CAPITAL\eretz-agency\frontend")
# El CLI de Vercel destroza los argumentos que llevan espacios, así que el
# cuerpo viaja por archivo y en una ruta que no tenga ninguno.
BODY = Path(r"D:\acvtmp\body.json")

BATCH = 200
CANARY = 12
# El endpoint corre con maxDuration 60: cada item es un round-trip y además
# cada request cierra con un snapshot completo. 50 entra con margen.
HTTP_CHUNK = 50


def log(msg: str = "") -> None:
    print(msg, flush=True)


def api(base: str, payload: dict | None = None, query: str = "", timeout: int = 600) -> dict:
    """Una sola llamada. GET si no hay payload, POST si lo hay."""
    args = ["vercel.cmd", "curl", base + "/api/agency-coverage" + query, "-s"]
    if payload is not None:
        BODY.parent.mkdir(parents=True, exist_ok=True)
        BODY.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        args += ["-X", "POST", "-H", "Content-Type:application/json", "-d", "@" + BODY.as_posix()]
    p = subprocess.run(args, cwd=FRONTEND, capture_output=True, text=True,
                       encoding="utf-8", errors="ignore", timeout=timeout)
    for line in reversed((p.stdout or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return {"_error": (p.stdout or p.stderr or "")[-300:]}


def item_of(row: dict) -> dict:
    """La candidate key es el id de publicador de Roomix: estable entre corridas
    e independiente del nombre, así que sigue identificando a la misma candidata
    aunque el nombre se limpie distinto."""
    payload = {k: v for k, v in row.items() if k != "fuente"}
    return {"candidateKey": row["metadata_zonaprop"]["roomix_agent_id"], "payload": payload}


def status_field(rows: list[dict]) -> str | None:
    """La forma que devuelve `stage_v1` se descubre en la primera respuesta, no
    se asume."""
    if not rows:
        return None
    keys = list(rows[0].keys())
    for hint in ("status", "estado", "result", "resultado", "action", "accion",
                 "outcome", "reason", "motivo", "staged", "inserted"):
        for k in keys:
            if k.lower() == hint:
                return k
    for k in keys:
        if isinstance(rows[0][k], str):
            return k
    return None


def tally(results: list[dict], field: str | None) -> Counter:
    c: Counter = Counter()
    for r in results:
        if not r.get("ok"):
            c["ERROR_TRANSPORTE"] += 1
            continue
        rows = r.get("rows") or []
        if not rows:
            c["SIN_FILA"] += 1
            continue
        c[str(rows[0].get(field)) if field else json.dumps(rows[0], sort_keys=True)] += 1
    return c


def send(base: str, items: list[dict]) -> tuple[list[dict], dict, int]:
    """Parte el lote lógico en requests que entren en el tiempo de la función."""
    results: list[dict] = []
    snap: dict = {}
    errores = 0
    for i in range(0, len(items), HTTP_CHUNK):
        r = api(base, {"items": items[i:i + HTTP_CHUNK]})
        if "_error" in r or "error" in r:
            errores += len(items[i:i + HTTP_CHUNK])
            log(f"      request falló: {r.get('error') or r.get('_error')}")
            continue
        lote = r.get("results") or []
        results += lote
        errores += r.get("errores", 0)
        # Los errores se muestran, no sólo se cuentan: un recuento sin el motivo
        # obliga a otra corrida para averiguar qué pasó.
        for m in sorted({str(x.get("error")) for x in lote if not x.get("ok")})[:3]:
            log(f"      error: {m}")
        snap = r.get("snapshot") or snap
    return results, snap, errores


def show_snapshot(s: dict, indent: str = "  ") -> None:
    log(f"{indent}main={s.get('main')}  staging={s.get('staging')}  "
        f"mias={s.get('mias')}  distintas={s.get('miasDistintas')}  "
        f"duplicadas={s.get('duplicadas')}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--batch-size", type=int, default=BATCH)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    d = Path(a.data_dir)

    rows = [json.loads(l) for l in (d / "staging_rows.jsonl").open(encoding="utf-8") if l.strip()]
    cross = [json.loads(l) for l in (d / "crosswalk.jsonl").open(encoding="utf-8") if l.strip()]

    # -------------------------------------------------- 0. compuerta local
    log("### COMPUERTA DE ELEGIBILIDAD ###")
    by_agent = {c["agent_id"]: c for c in cross}
    malas = Counter()
    for r in rows:
        c = by_agent.get(r["metadata_zonaprop"]["roomix_agent_id"])
        if c is None:
            malas["sin_entrada_en_crosswalk"] += 1
        elif c.get("match_state") != "NEW_HIGH_CONFIDENCE":
            malas[c.get("match_state") or "sin_estado"] += 1
        elif c.get("type") != "INMOBILIARIA":
            malas[c.get("type") or "sin_tipo"] += 1
    log(f"  candidatas:              {len(rows)}")
    log(f"  no elegibles:            {dict(malas) or 'ninguna'}")
    if malas:
        log("  se detiene: sólo entran NEW_HIGH_CONFIDENCE de tipo INMOBILIARIA")
        return 2
    keys = [r["metadata_zonaprop"]["roomix_agent_id"] for r in rows]
    if len(set(keys)) != len(keys):
        log("  se detiene: candidate keys repetidas en el propio lote")
        return 2
    log("  todas NEW_HIGH_CONFIDENCE / INMOBILIARIA, candidate keys únicas")

    if a.limit:
        rows = rows[:a.limit]

    # -------------------------------------------------- 1. preflight
    log("\n### PREFLIGHT ###")
    pre = api(a.base)
    if "_error" in pre:
        log(f"  falló: {pre['_error']}")
        return 3
    log(f"  entorno:   {pre.get('environment')}")
    log(f"  preflight: {json.dumps((pre.get('preflight') or {}).get('rows'), ensure_ascii=False)}")
    log(f"  identidad: {json.dumps((pre.get('identity') or {}).get('rows'), ensure_ascii=False)}")
    if pre.get("environment") != "preview":
        log("  se detiene: esto no es Preview")
        return 3
    snap0 = pre.get("snapshot") or {}
    log("  snapshot inicial:")
    show_snapshot(snap0, "    ")

    # -------------------------------------------------- 2. canary
    log("\n### CANARY ###")
    canary = rows[:CANARY]
    t0 = time.time()
    res1, snap1, err1 = send(a.base, [item_of(r) for r in canary])
    field = status_field([x for r in res1 for x in (r.get("rows") or [])])
    log(f"  enviadas {len(canary)} en {time.time()-t0:.1f}s | errores {err1}")
    log(f"  forma de stage_v1: {json.dumps((res1[0].get('rows') or [{}])[0], ensure_ascii=False) if res1 else '-'}")
    log(f"  campo de estado:   {field}")
    log(f"  resultados:        {dict(tally(res1, field))}")
    show_snapshot(snap1)
    if snap1.get("duplicadas"):
        log("  se detiene: duplicados en staging")
        return 5

    # -------------------------------------------------- 3. idempotencia
    log("\n### IDEMPOTENCIA (el mismo canary otra vez) ###")
    res2, snap2, _ = send(a.base, [item_of(r) for r in canary])
    log(f"  resultados: {dict(tally(res2, field))}")
    show_snapshot(snap2)
    if snap2.get("mias") != snap1.get("mias"):
        log(f"  FALLO: la segunda pasada cambió mias {snap1.get('mias')} -> {snap2.get('mias')}")
        return 6
    if snap2.get("duplicadas"):
        log("  FALLO: aparecieron duplicados")
        return 6
    log("  OK: la segunda pasada no insertó nada")

    # -------------------------------------------------- 4. lotes
    rest = rows[CANARY:]
    log(f"\n### ROLLOUT ({len(rest)} restantes, lotes de {a.batch_size}) ###")
    total = Counter()
    snap = snap2
    for i in range(0, len(rest), a.batch_size):
        chunk = rest[i:i + a.batch_size]
        prev = snap.get("mias", 0)
        res, snap, err = send(a.base, [item_of(r) for r in chunk])
        t = tally(res, field)
        total.update(t)
        log(f"  lote {i//a.batch_size+1:2d}: {len(chunk):3d} enviadas | "
            f"mias {prev}->{snap.get('mias')} (+{snap.get('mias',0)-prev}) | "
            f"dup={snap.get('duplicadas')} | err={err} | {dict(t)}")
        if snap.get("duplicadas"):
            log("  se detiene: apareció un duplicado inesperado")
            return 7

    # -------------------------------------------------- 5. verificación final
    log("\n### SNAPSHOT FINAL ###")
    fin = api(a.base, query="?op=snapshot").get("snapshot") or {}
    show_snapshot(fin)
    log(f"  staging por fuente: {json.dumps(fin.get('stagingPorFuente'), ensure_ascii=False)}")

    # -------------------------------------------------- 6. reconciliación
    log("\n### RECONCILIACIÓN CONTRA EL CROSSWALK ###")
    kk = api(a.base, query="?op=keys").get("keys") or {}
    mias = set(kk.get("mias") or [])
    esperadas = {r["nombre_normalizado"] for r in rows}
    main_keys = set(kk.get("main") or [])
    log(f"  esperadas (candidatas):        {len(esperadas)}")
    log(f"  presentes en staging:          {len(mias)}")
    log(f"  esperadas y ausentes:          {len(esperadas - mias)}")
    log(f"  presentes y no esperadas:      {len(mias - esperadas)}")
    log(f"  colisiones con main:           {len(mias & main_keys)}")
    log(f"  crosswalk NEW_HIGH_CONFIDENCE: "
        f"{sum(1 for c in cross if c.get('match_state') == 'NEW_HIGH_CONFIDENCE')}")
    log(f"  crosswalk AMBIGUOUS (fuera):   "
        f"{sum(1 for c in cross if c.get('match_state') == 'AMBIGUOUS')}")
    log(f"  crosswalk INSUFFICIENT (fuera):"
        f"{sum(1 for c in cross if c.get('match_state') == 'INSUFFICIENT_DATA')}")
    log(f"\n  totales por resultado: {dict(total)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
