#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Mapa tecnologico de las fuentes listas para scrapear.

Baja la home de cada inmobiliaria verificada y, cuando existe, su sitemap, para
clasificarla en una familia tecnica. La pregunta que responde no es "que usa
este sitio" sino "cuantos scrapers hacen falta": si doscientas corren sobre la
misma plataforma, un conector cubre las doscientas.

No descarga propiedades. Baja la home y a lo sumo el sitemap, con pausa, y se
detiene ahi.

Reanudable: lo ya clasificado no se vuelve a bajar.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


dp = _load("detect_platform")
aud = _load("audit_existing_webs")

UA = "Mozilla/5.0 (compatible; ERETZ-SourceMapper/1.0; +contacto@eretz)"


def bajar_texto(url: str, timeout: int = 12, limite: int = 120_000) -> str:
    """Descarga cruda para mirar sitemap o robots. Sin reintentos."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return r.read(limite).decode("utf-8", "ignore")
    except Exception:
        return ""


def sitemap_de_propiedades(dominio: str) -> bool:
    """Busca un sitemap que liste propiedades.

    Un sitemap ahorra recorrer el sitio a ciegas, asi que vale la pena una
    peticion extra por fuente para saber si existe.
    """
    for ruta in ("/sitemap.xml", "/sitemap_index.xml"):
        cuerpo = bajar_texto(dominio.rstrip("/") + ruta, timeout=8, limite=60_000)
        if not cuerpo or "<" not in cuerpo:
            continue
        if dp.RUTAS_LISTADO.search(cuerpo) or "sitemap" in cuerpo.lower():
            return True
    return False


def procesar(fila: dict, con_sitemap: bool = True) -> dict:
    url = fila.get("selected_domain") or ""
    sitio = aud.bajar(url) if url else {}
    tiene_sitemap = False
    if con_sitemap and sitio.get("http") == 200:
        tiene_sitemap = sitemap_de_propiedades(url)
    clasif = dp.clasificar(sitio, tiene_sitemap)
    return {
        "canonical_agency_id": fila["canonical_agency_id"],
        "agency_name": fila.get("canonical_name"),
        "official_url": url,
        "scrape_status": fila.get("scrapeability_status"),
        "http": sitio.get("http"),
        "evidence": {"titulo": (sitio.get("titulo") or "")[:120],
                     "final_url": sitio.get("url")},
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        **clasif,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--hilos", type=int, default=6)
    ap.add_argument("--limite", type=int, default=0)
    ap.add_argument("--sin-sitemap", action="store_true")
    a = ap.parse_args()
    dd = Path(a.data_dir)

    directorio = [json.loads(l) for l in
                  (dd / "agency_web_directory.jsonl").open(encoding="utf-8") if l.strip()]
    listas = [x for x in directorio
              if x.get("scrapeability_status") == "SCRAPE_SOURCE_READY"
              and x.get("selected_domain")]

    salida = dd / "scrape_source_technology_map.jsonl"
    hechas: set[str] = set()
    if salida.exists():
        for l in salida.open(encoding="utf-8"):
            if l.strip():
                hechas.add(json.loads(l)["canonical_agency_id"])
    pendientes = [x for x in listas if x["canonical_agency_id"] not in hechas]
    if a.limite:
        pendientes = pendientes[:a.limite]

    print("### MAPA TECNOLOGICO DE FUENTES ###", flush=True)
    print(f"  fuentes READY:      {len(listas):,}", flush=True)
    print(f"  ya clasificadas:    {len(hechas):,}", flush=True)
    print(f"  a clasificar ahora: {len(pendientes):,}", flush=True)

    hecho = 0
    with salida.open("a", encoding="utf-8") as fh:
        for i in range(0, len(pendientes), 30):
            trozo = pendientes[i:i + 30]
            with ThreadPoolExecutor(max_workers=a.hilos) as ex:
                for r in ex.map(lambda f: procesar(f, not a.sin_sitemap), trozo):
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            fh.flush()
            hecho += len(trozo)
            if hecho % 150 == 0 or hecho == len(pendientes):
                print(f"    {hecho}/{len(pendientes)}", flush=True)
            time.sleep(0.2)

    # ------------------------------------------------ resumen por plataforma
    filas = [json.loads(l) for l in salida.open(encoding="utf-8") if l.strip()]
    por_plataforma: dict[str, list] = defaultdict(list)
    for r in filas:
        por_plataforma[r["detected_platform"]].append(r)

    resumen = {}
    for plat, grupo in sorted(por_plataforma.items(), key=lambda x: -len(x[1])):
        estrategias = Counter(r["strategy"] for r in grupo)
        estrategia = estrategias.most_common(1)[0][0]
        resumen[plat] = {
            "count": len(grupo),
            "percentage": round(len(grupo) / max(len(filas), 1) * 100, 2),
            "strategy": estrategia,
            "strategies_breakdown": dict(estrategias),
            "priority": dp.prioridad(estrategia, len(grupo)),
            "requires_js": sum(1 for r in grupo if r["requires_js"]),
            "with_api": sum(1 for r in grupo if r["detected_api"]),
            "with_sitemap": sum(1 for r in grupo if r["sitemap"]),
            "representative_examples": [
                {"name": r["agency_name"], "url": r["official_url"]} for r in grupo[:3]],
        }
    (dd / "scrape_platform_summary.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n### RESULTADO ###", flush=True)
    print(f"  fuentes clasificadas: {len(filas):,}", flush=True)
    print(f"\n  por estrategia:", flush=True)
    for k, v in Counter(r["strategy"] for r in filas).most_common():
        print(f"    {k:20} {v:6,}", flush=True)
    print(f"\n  top plataformas:", flush=True)
    for plat, info in list(resumen.items())[:12]:
        print(f"    {plat:20} {info['count']:5,}  {info['percentage']:5.1f}%  "
              f"{info['strategy']:18} {info['priority']}", flush=True)

    # Impacto: cuantas fuentes cubren los primeros conectores.
    # UNKNOWN no es un conector: son sitios propios, cada uno con su HTML.
    # Contarlo como si fuera una familia inflaria la cobertura prometida.
    grupos = sorted(((k, v) for k, v in resumen.items() if k != "UNKNOWN"),
                    key=lambda x: -x[1]["count"])
    acum = 0
    print(f"\n  cobertura acumulada por conector:", flush=True)
    print(f"    (UNKNOWN = {resumen.get('UNKNOWN', {}).get('count', 0):,} sitios propios, "
          f"no es una familia reutilizable)", flush=True)
    for n, (plat, info) in enumerate(grupos[:5], 1):
        acum += info["count"]
        print(f"    primeros {n} conectores ({plat:18}): {acum:5,} fuentes "
              f"({acum/max(len(filas),1)*100:.1f}%)", flush=True)
    print(f"\n  artefactos -> scrape_source_technology_map.jsonl / "
          f"scrape_platform_summary.json", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
