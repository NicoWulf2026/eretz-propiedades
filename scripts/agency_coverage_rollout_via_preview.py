#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Rollout de Agency Coverage a través del endpoint temporal de Preview.

No necesita credencial de base en esta máquina: la conexión vive server-side en
Vercel Preview, protegida por Deployment Protection. Este cliente sólo manda
lotes de candidatas y verifica lo que el servidor responde.

Secuencia: preflight -> dedupe (lo hace el servidor con el estado del momento)
-> canary -> canary otra vez para probar idempotencia -> lotes -> verificación
final -> reconciliación con el crosswalk.

Sólo viajan candidatas HIGH_CONFIDENCE_NEW. El servidor fija `fuente`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

BATCH = 200
CANARY = 12


def log(msg: str) -> None:
    print(msg, flush=True)


def bypass_cookie(base: str) -> str:
    """Cookie de Deployment Protection vía el CLI ya autenticado. No se imprime."""
    fd, tmp = tempfile.mkstemp(prefix="acv_", suffix=".hdr")
    os.close(fd)
    try:
        subprocess.run(
            ["vercel.cmd", "curl", base + "/api/properties/counts?x-vercel-set-bypass-cookie=true",
             "-i", "--yes"],
            stdout=open(tmp, "wb"), stderr=subprocess.DEVNULL, timeout=180)
        raw = Path(tmp).read_bytes().decode("utf-8", "ignore")
        m = re.search(r"(?i)set-cookie:\s*_vercel_jwt=([^;\r\n]+)", raw)
        if not m:
            raise RuntimeError("no se pudo obtener la cookie de Deployment Protection")
        return m.group(1)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def call(base: str, ck: str, method: str, payload: dict | None = None, timeout: int = 180) -> dict:
    url = base + "/api/agency-coverage"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Cookie": "_vercel_jwt=" + ck,
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "ignore"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        try:
            return {"_status": e.code, **json.loads(body)}
        except Exception:
            return {"_status": e.code, "error": body[:200]}


def pick_canary(rows: list[dict], n: int) -> list[dict]:
    """Representativo y determinista: varias franquicias, independientes grandes
    y cola. Mismo criterio que el rollout directo."""
    fr, indep, seen_brand = [], [], set()
    for r in rows:
        brand = ((r.get("metadata_zonaprop") or {}).get("franchise") or {}).get("brand")
        if brand and brand not in seen_brand:
            seen_brand.add(brand)
            fr.append(r)
        elif not brand:
            indep.append(r)
    out, seen = [], set()
    for r in fr[:4] + indep[:4] + indep[-4:]:
        k = r.get("nombre_normalizado")
        if k and k not in seen:
            seen.add(k)
            out.append(r)
    return out[:n]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="URL del Preview")
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--batch-size", type=int, default=BATCH)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    rows = [json.loads(l) for l in
            (Path(a.data_dir) / "staging_rows.jsonl").open(encoding="utf-8") if l.strip()]
    log(f"candidatas preparadas: {len(rows)}")

    ck = bypass_cookie(a.base)

    log("\n### PREFLIGHT ###")
    pre = call(a.base, ck, "GET")
    if pre.get("_status"):
        log(f"  HTTP {pre['_status']}: {pre.get('error')}")
        return 3
    p = pre.get("preflight", {})
    log(f"  entorno:            {pre.get('environment')}")
    log(f"  rol:                {p.get('role')}")
    log(f"  SELECT main:        {p.get('canSelectMain')}")
    log(f"  INSERT staging:     {p.get('canInsertStaging')}")
    log(f"  UPDATE staging:     {p.get('canUpdateStaging')} (esperado False)")
    log(f"  DELETE staging:     {p.get('canDeleteStaging')} (esperado False)")
    log(f"  staging actual:     {pre.get('staging')}")
    uq = p.get("uniqueIndexes") or []
    if uq:
        for d in uq:
            log(f"  índice único:       {d}")
    else:
        # Sin índice único no hay conflicto que `on conflict` pueda absorber: la
        # idempotencia queda apoyada sólo en el dedupe de aplicación y en el
        # detector de duplicados. Se sigue, pero conviene saberlo.
        log("  índice único:       NINGUNO (idempotencia sólo por dedupe de aplicación)")
    if not p.get("ok"):
        log(f"  preflight NO OK: {p.get('error')}")
        return 3
    if p.get("canUpdateStaging") or p.get("canDeleteStaging"):
        log("  el rol tiene más alcance del previsto; no se escribe")
        return 4

    if a.dry_run:
        r = call(a.base, ck, "POST", {"rows": rows[:a.batch_size], "dryRun": True})
        log(f"\n  DRY-RUN de un lote: {r}")
        return 0

    log("\n### CANARY ###")
    canary = pick_canary(rows, CANARY)
    r1 = call(a.base, ck, "POST", {"rows": canary})
    log(f"  enviadas {len(canary)} | insertadas {r1.get('insertadas')} | skipped {r1.get('skipped')}")
    log(f"  staging: {r1.get('staging', {}).get('after')}")
    if r1.get("duplicados"):
        log(f"  FALLO: {r1['duplicados']} duplicados")
        return 5

    log("\n### IDEMPOTENCIA (mismo canary otra vez) ###")
    r2 = call(a.base, ck, "POST", {"rows": canary})
    if r2.get("insertadas", 0) != 0:
        log(f"  FALLO: la segunda pasada insertó {r2['insertadas']}")
        return 6
    log(f"  OK: la segunda pasada insertó 0 (skipped {r2.get('skipped')})")

    done = {r["nombre_normalizado"] for r in canary}
    rest = [r for r in rows if r.get("nombre_normalizado") not in done]

    log(f"\n### ROLLOUT ({len(rest)} restantes, lotes de {a.batch_size}) ###")
    total, failed = r1.get("insertadas", 0), 0
    for i in range(0, len(rest), a.batch_size):
        chunk = rest[i:i + a.batch_size]
        res = call(a.base, ck, "POST", {"rows": chunk}, timeout=300)
        if res.get("_status") or res.get("error"):
            failed += 1
            log(f"  lote {i//a.batch_size+1:3d}: ERROR {res.get('error')}")
            continue
        total += res.get("insertadas", 0)
        st = res.get("staging", {}).get("after", {})
        dup = res.get("duplicados", 0)
        log(f"  lote {i//a.batch_size+1:3d}: +{res.get('insertadas'):4d} | "
            f"staging mios={st.get('mine')} distintos={st.get('distinct')} "
            f"{'OK' if not dup else 'DUPLICADOS'}")
        if dup:
            log("  se detiene: aparecieron duplicados")
            return 7
        time.sleep(0.3)

    final = call(a.base, ck, "GET")
    log("\n### RESULTADO ###")
    log(f"  insertadas en total: {total}")
    log(f"  lotes con error:     {failed}")
    log(f"  staging final:       {final.get('staging')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
