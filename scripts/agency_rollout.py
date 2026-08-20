#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Crosswalk contra ERETZ, canary y rollout del padron Roomix a staging.

Entra por el puente de Preview: `eretz_preview_ro` eleva a
`eretz_agency_coverage_writer` dentro de cada transaccion. El dedupe definitivo
NO se decide aca sino en el servidor, bajo la misma transaccion que el insert:
entre que este script calcula su lista y la base escribe, el estado puede
cambiar, y la unica comprobacion que vale es la que ocurre adentro.

Lo que si se decide aca es la CLASIFICACION, que es otra cosa: si una entidad es
nueva, si ya existe, o si se parece demasiado a algo existente como para
decidirlo solo. Una entidad con un vecino significativo sin resolver no se
declara nueva por mas que su nombre no coincida exacto.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
BODY = Path(r"D:\acvtmp\rollout_body.json")


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


d = _load("eretz_dedupe")
cwin = _load("coverage_windows")

EXACT = "EXACT_MATCH"
EXISTING = "HIGH_CONFIDENCE_EXISTING"
NEW = "HIGH_CONFIDENCE_NEW"
AMBIG = "AMBIGUOUS"
INSUF = "INSUFFICIENT_DATA"
GARBAGE = "REJECTED_GARBAGE"

CANARY = 12
BATCH = 200


def api(base: str, query: str = "", payload: dict | None = None, timeout: int = 900) -> dict:
    args = ["vercel.cmd", "curl", base + "/api/agency-bridge" + query, "-s"]
    if payload is not None:
        BODY.parent.mkdir(parents=True, exist_ok=True)
        BODY.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        args += ["-X", "POST", "-H", "Content-Type:application/json", "-d", "@" + BODY.as_posix()]
    p = subprocess.run(args, cwd=FRONTEND, capture_output=True, text=True,
                       encoding="utf-8", errors="ignore", timeout=timeout)
    for linea in reversed((p.stdout or "").splitlines()):
        linea = linea.strip()
        if linea.startswith("{"):
            try:
                return json.loads(linea)
            except json.JSONDecodeError:
                continue
    return {"_error": (p.stdout or p.stderr or "")[-300:]}


def entidades_eretz(base: str) -> tuple[dict[str, dict], list]:
    """Estado ACTUAL de main y staging. No se usa un snapshot viejo."""
    porclave: dict[str, dict] = {}
    ents = []
    for tabla in ("main", "staging"):
        r = api(base, f"?op={tabla}")
        for fila in r.get("filas", []):
            nombre = (fila.get("nombre") or "").strip()
            if not nombre:
                continue
            k = d.norm_name(nombre)
            if not k:
                continue
            # main manda sobre staging si la clave esta en las dos.
            if k not in porclave or tabla == "main":
                porclave[k] = {"tabla": tabla, "id": fila.get("id"), "nombre": nombre}
            ents.append(d.Entidad(ident=f"{tabla}:{fila.get('id')}", nombre=nombre,
                                  web=fila.get("web"), fuente=tabla))
    return porclave, ents


def clasificar(padron: list[dict], porclave: dict[str, dict], ents_eretz: list) -> list[dict]:
    """Clasifica cada entidad del padron contra ERETZ."""
    # Solo interesa el universo inmobiliario.
    candidatas = [e for e in padron if e.get("tipo") in cwin.CUENTA_COMO_AGENCIA]
    izq = [d.Entidad(ident=e["stable_id"], nombre=e["nombre_original"]) for e in candidatas]
    vecinos: dict[str, list] = {}
    for par in d.cruzar(izq, ents_eretz):
        vecinos.setdefault(par.izquierda.ident, []).append(par)

    out = []
    for e in candidatas:
        k = e["nombre_normalizado"]
        prev = porclave.get(k)
        vs = vecinos.get(e["stable_id"], [])
        estado, razon, cand = None, "", None

        if prev and prev["tabla"] == "main":
            estado, razon, cand = EXACT, "clave presente en main", prev
        elif prev:
            estado, razon, cand = EXISTING, "clave presente en staging", prev
        elif len(k) < 4:
            estado, razon = INSUF, "nombre demasiado corto para decidir"
        else:
            # Regla anti-duplicados: un vecino significativo sin resolver impide
            # declarar NEW. Que el string no coincida exacto no alcanza.
            fuertes = [v for v in vs if v.veredicto.estado in (d.EXACT, d.HIGH_CONFIDENCE)]
            dudosos = [v for v in vs if v.veredicto.estado == d.AMBIGUOUS]
            if fuertes:
                mejor = fuertes[0]
                estado = EXISTING
                razon = f"coincide con {mejor.derecha.ident}: {mejor.veredicto.explicacion}"
                cand = {"tabla": mejor.derecha.fuente, "id": mejor.derecha.ident,
                        "nombre": mejor.derecha.nombre}
            elif dudosos:
                mejor = dudosos[0]
                estado = AMBIG
                razon = f"vecino sin resolver {mejor.derecha.ident}: {mejor.veredicto.explicacion}"
                cand = {"tabla": mejor.derecha.fuente, "id": mejor.derecha.ident,
                        "nombre": mejor.derecha.nombre}
            else:
                estado, razon = NEW, "sin coincidencia ni vecino significativo"

        out.append({**e, "crosswalk": estado, "crosswalk_razon": razon,
                    "crosswalk_candidato": cand})
    return out


def fila_para_staging(e: dict) -> dict:
    """Lo minimo y solo lo del anunciante. Nada del inmueble."""
    prov = {
        "discovered_via": "roomix_public_property_page",
        "roomix_agent_ids": e.get("raw_agent_ids"),
        "roomix_logo": e.get("roomix_logo"),
        "listings_observed": e.get("avisos_observados"),
        "evidence_urls": (e.get("evidencia_urls") or [])[:3],
        "zonas_observadas": e.get("zonas_observadas"),
        "tipo": e.get("tipo"),
        "franquicia": e.get("red_franquicia"),
        "licences": e.get("matricula"),
        "matcher_version": e.get("matcher_version"),
        "directory_version": e.get("directory_version"),
        "crosswalk": e.get("crosswalk"),
    }
    return {
        "nombre": e["nombre_original"],
        "nombre_limpio": e["nombre_original"],
        "nombre_normalizado": e["nombre_normalizado"],
        "pais": "Argentina",
        "estado_scraping": "pendiente",
        "needs_manual_review": False,
        "revision_notas": f"[roomix_agency_coverage:{e['stable_id']}]",
        "metadata_zonaprop": prov,
    }


def enviar(base: str, filas: list[dict]) -> dict:
    return api(base, payload={"filas": filas})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    dd = Path(a.data_dir)

    padron = [json.loads(l) for l in
              (dd / "roomix_agency_directory.jsonl").open(encoding="utf-8") if l.strip()]
    print(f"### CROSSWALK ###\n  padron: {len(padron):,} entidades canonicas", flush=True)

    porclave, ents = entidades_eretz(a.base)
    print(f"  claves ERETZ (main+staging): {len(porclave):,}", flush=True)

    clasificado = clasificar(padron, porclave, ents)
    resumen = Counter(e["crosswalk"] for e in clasificado)
    print(f"  entidades inmobiliarias:     {len(clasificado):,}", flush=True)
    for k, v in resumen.most_common():
        print(f"    {k:26} {v:6,}", flush=True)

    out = dd / "crosswalk_final.jsonl"
    out.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in clasificado) + "\n",
                   encoding="utf-8")
    print(f"  crosswalk -> {out}", flush=True)

    nuevas = [e for e in clasificado if e["crosswalk"] == NEW]
    print(f"\n  elegibles para insert: {len(nuevas):,}", flush=True)
    if a.dry_run or not nuevas:
        print("  DRY-RUN o sin candidatas: no se escribe nada.", flush=True)
        return 0

    # ------------------------------------------------------------- canary
    print(f"\n### CANARY ({CANARY}) ###", flush=True)
    canary = nuevas[:CANARY]
    r1 = enviar(a.base, [fila_para_staging(e) for e in canary])
    print(f"  insertadas {r1.get('insertadas')} | saltadas {r1.get('saltadas')}", flush=True)
    if r1.get("error"):
        print(f"  ERROR: {r1['error']}", flush=True)
        return 3

    print("\n### IDEMPOTENCIA (mismo canary otra vez) ###", flush=True)
    r2 = enviar(a.base, [fila_para_staging(e) for e in canary])
    print(f"  insertadas {r2.get('insertadas')} | saltadas {r2.get('saltadas')}", flush=True)
    if r2.get("insertadas", 0) != 0:
        print(f"  FALLO: la segunda pasada inserto {r2['insertadas']}", flush=True)
        return 4
    print("  OK: la segunda pasada no inserto nada", flush=True)

    # ------------------------------------------------------------- lotes
    resto = nuevas[CANARY:]
    print(f"\n### ROLLOUT ({len(resto):,} restantes, lotes de {BATCH}) ###", flush=True)
    total = r1.get("insertadas", 0)
    saltadas: Counter = Counter(r1.get("saltadas") or {})
    for i in range(0, len(resto), BATCH):
        lote = resto[i:i + BATCH]
        r = enviar(a.base, [fila_para_staging(e) for e in lote])
        if r.get("error") or "_error" in r:
            print(f"  lote {i//BATCH+1:3d}: ERROR {r.get('error') or r.get('_error')}", flush=True)
            continue
        total += r.get("insertadas", 0)
        saltadas.update(r.get("saltadas") or {})
        st = (r.get("despues") or [{}])
        print(f"  lote {i//BATCH+1:3d}: +{r.get('insertadas'):4d} | acum {total:5,} | "
              f"saltadas {dict(r.get('saltadas') or {})}", flush=True)
        time.sleep(0.2)

    print(f"\n### RESULTADO ###", flush=True)
    print(f"  insertadas en total: {total:,}", flush=True)
    print(f"  saltadas por dedupe server-side: {dict(saltadas)}", flush=True)
    fin = api(a.base, "?op=stats")
    print(f"  stats finales: {json.dumps(fin.get('stats'), ensure_ascii=False)}", flush=True)
    print(f"  por fuente: {json.dumps(fin.get('fuentes'), ensure_ascii=False)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
