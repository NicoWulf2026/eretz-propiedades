#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Delta y recuperacion sobre el snapshot ya agotado de Roomix.

El crawl inicial cerro con 168.563 fichas procesadas. Este script hace las dos
cosas que faltan antes de congelar el padron, y ninguna de las dos re-recorre lo
ya hecho:

  DELTA         Roomix pudo publicar avisos nuevos durante los casi tres dias
                que duro el crawl. Se reenumera el sitemap, se compara contra las
                URLs ya observadas y se procesan unicamente las que aparecieron.
                Se repite hasta que una pasada no traiga nada nuevo. El criterio
                de cierre es la enumeracion, no una convergencia estadistica.

  RECUPERACION  274 fichas quedaron con `method=not_found`: se leyeron, pero el
                bloque del publicador no se pudo extraer. Se reintentan una vez.
                Una ficha puede no tener publicador de verdad -las hay de dueno
                directo-, asi que un residual no es necesariamente un fallo.

Reutiliza el Fetcher del crawler, con su mismo rate y su misma regla ante 403:
si Roomix bloquea, se aborta sin evadirlo.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


rd = _load("roomix_agency_discovery")


def observadas(obs_p: Path) -> tuple[set[str], list[str]]:
    """URLs ya vistas, y las que quedaron sin publicador."""
    vistas: set[str] = set()
    sin_agente: list[str] = []
    for linea in obs_p.open(encoding="utf-8"):
        if not linea.strip():
            continue
        o = json.loads(linea)
        u = o.get("url")
        if not u:
            continue
        vistas.add(u)
        if not o.get("agent_id"):
            sin_agente.append(u)
    return vistas, sin_agente


def procesar(f, urls: list[str], obs_p: Path, etiqueta: str) -> Counter:
    """Baja cada ficha y anota solo al publicador. Nada del inmueble."""
    stats: Counter = Counter()
    with obs_p.open("a", encoding="utf-8") as fh:
        for i, u in enumerate(urls, 1):
            html = f.get(u)
            if not html:
                stats["fetch_error"] += 1
                continue
            aid, nombre, metodo = rd.parse_publisher(html)
            stats[metodo] += 1
            if aid:
                fh.write(json.dumps({"url": u, "agent_id": aid, "agent_name": nombre,
                                     "method": metodo, "ts": int(time.time())},
                                    ensure_ascii=False) + "\n")
                fh.flush()
            if i % 50 == 0:
                print(f"    {etiqueta}: {i}/{len(urls)}  {dict(stats)}", flush=True)
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--rate", type=float, default=3.0)
    ap.add_argument("--max-pasadas", type=int, default=5)
    ap.add_argument("--saltear-recuperacion", action="store_true")
    a = ap.parse_args()
    dd = Path(a.data_dir)
    obs_p = dd / "observations.jsonl"
    informe: dict = {"pasadas": [], "iniciado": time.strftime("%Y-%m-%dT%H:%M:%S")}

    f = rd.Fetcher(rate_per_s=a.rate)
    vistas, sin_agente = observadas(obs_p)
    informe["snapshot_inicial"] = len(vistas)
    informe["sin_publicador_inicial"] = len(sin_agente)
    print(f"### CIERRE DE UNIVERSO ###", flush=True)
    print(f"  URLs ya observadas:        {len(vistas):,}", flush=True)
    print(f"  fichas sin publicador:     {len(sin_agente):,}", flush=True)

    # ---------------------------------------------------------- recuperacion
    if not a.saltear_recuperacion and sin_agente:
        print(f"\n### RECUPERACION DE {len(sin_agente)} FICHAS SIN PUBLICADOR ###", flush=True)
        st = procesar(f, sin_agente, obs_p, "recuperacion")
        informe["recuperacion"] = dict(st)
        rec = st.get("agent_block", 0) + st.get("parse_fallback", 0)
        informe["recuperadas"] = rec
        informe["irrecuperables"] = len(sin_agente) - rec
        print(f"  recuperadas:   {rec}", flush=True)
        print(f"  sin publicador tras reintento: {len(sin_agente) - rec}", flush=True)
        vistas, _ = observadas(obs_p)

    # ---------------------------------------------------------------- delta
    for pasada in range(1, a.max_pasadas + 1):
        print(f"\n### DELTA — PASADA {pasada} ###", flush=True)
        shards = rd.property_urls(f)
        universo = [u for v in shards.values() for u in v]
        nuevas = [u for u in dict.fromkeys(universo) if u not in vistas]
        print(f"  universo actual:   {len(universo):,}", flush=True)
        print(f"  ya observadas:     {len(vistas):,}", flush=True)
        print(f"  NUEVAS:            {len(nuevas):,}", flush=True)
        informe["pasadas"].append({"pasada": pasada, "universo": len(universo),
                                   "nuevas": len(nuevas)})
        if not nuevas:
            print("  sin URLs nuevas: el universo quedo cerrado por enumeracion.", flush=True)
            informe["cerrado_en_pasada"] = pasada
            break
        st = procesar(f, nuevas, obs_p, f"delta{pasada}")
        informe["pasadas"][-1]["resultado"] = dict(st)
        vistas.update(nuevas)
    else:
        informe["cerrado_en_pasada"] = None
        print("  se agotaron las pasadas permitidas con delta todavia abierto.", flush=True)

    informe["universo_final"] = len(vistas)
    informe["terminado"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    informe["fetch_stats"] = dict(f.stats)
    out = dd / "delta_report.json"
    out.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  universo final: {len(vistas):,}", flush=True)
    print(f"  informe -> {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
