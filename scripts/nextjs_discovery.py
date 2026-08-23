#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Fingerprint de las fuentes Next.js antes de escribir un connector.

Next.js no dice nada sobre como se publica el inventario: dice como se
construyo el front. Las 87 fuentes pueden ser una familia o seis, y varias ni
siquiera son el sitio de la inmobiliaria sino su perfil en un portal.

Se buscan, en orden de utilidad:
  __NEXT_DATA__   el estado del servidor serializado en la pagina: cuando esta,
                  trae las propiedades ya tipadas y no hace falta parsear HTML
  buildId         permite armar la ruta /_next/data/<buildId>/<ruta>.json, que
                  es la API que el propio Next usa para navegar
  sitemap         enumeracion barata
  JSON-LD         schema.org
  rutas de ficha  ultimo recurso
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from connectors.base import (Bloqueado, Descargador, ErrorPermanente,  # noqa: E402
                             ErrorTransitorio, LimitadorDeRitmo)
from connectors.generico import RE_FICHA, RE_FICHA_RAIZ  # noqa: E402

# Hosts que son portales o directorios: el sitio no es de la inmobiliaria.
PORTALES = re.compile(
    r"(realestate\.com\.au|construex|todoprops|zonaprop|argenprop|properati|"
    r"mercadolibre|inmuebles24|remax\.com|century21\.com|inmoup|inmoclick|"
    r"mapaprop|proppies|near-place|miguiaargentina|inmobusqueda)", re.I)


def analizar(f: dict, d: Descargador) -> dict:
    url = f["domain"]
    p = urllib.parse.urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    out = {"canonical_agency_id": f["canonical_agency_id"], "eretz_id": f.get("eretz_id"),
           "agency_name": f.get("agency_name"), "domain": url, "base": base,
           "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if PORTALES.search(url):
        return {**out, "familia": "PERFIL_EN_PORTAL", "connector": None,
                "motivo": "el dominio es un portal o directorio, no el sitio propio"}
    try:
        html = d.bajar(url)
    except Bloqueado:
        return {**out, "familia": "BLOQUEADA", "connector": None}
    except (ErrorTransitorio, ErrorPermanente) as e:
        return {**out, "familia": "INACCESIBLE", "connector": None,
                "motivo": type(e).__name__}

    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    datos = None
    if m:
        try:
            datos = json.loads(m.group(1))
        except ValueError:
            datos = None
    out["tiene_next_data"] = bool(datos)
    out["build_id"] = (datos or {}).get("buildId")
    out["ruta_next"] = (datos or {}).get("page")

    # Cuantas propiedades hay dentro del estado serializado.
    props = 0
    if datos:
        crudo = json.dumps(datos, ensure_ascii=False)
        props = len(set(re.findall(r'"(?:slug|permalink|url)"\s*:\s*"([^"]{6,120})"', crudo)))
        out["claves_pageprops"] = sorted((datos.get("props") or {})
                                         .get("pageProps", {}).keys())[:12]
    out["items_en_next_data"] = props
    out["jsonld"] = "application/ld+json" in html
    out["fichas_en_html"] = len({u for u in re.findall(r'href="([^"]{4,200})"', html)
                                 if RE_FICHA.search(urllib.parse.urljoin(base, u))
                                 or RE_FICHA_RAIZ.search(
                                     urllib.parse.urlparse(
                                         urllib.parse.urljoin(base, u)).path)})
    sitemap = False
    for ruta in ("/sitemap.xml", "/sitemap_index.xml"):
        try:
            cuerpo = d.bajar(base + ruta)
        except (ErrorTransitorio, ErrorPermanente, Bloqueado):
            continue
        if "<loc>" in cuerpo:
            locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", cuerpo)
            sitemap = any(RE_FICHA.search(u) for u in locs) or len(locs) > 5
            out["sitemap_locs"] = len(locs)
            break
    out["sitemap"] = sitemap

    if props >= 5:
        out["familia"], out["connector"] = "NEXTJS_EMBEDDED_JSON", "generico"
    elif sitemap:
        out["familia"], out["connector"] = "NEXTJS_SITEMAP", "generico"
    elif out["fichas_en_html"]:
        out["familia"], out["connector"] = "NEXTJS_HTML", "generico"
    elif out["build_id"]:
        out["familia"], out["connector"] = "NEXTJS_DATA_API", None
    else:
        out["familia"], out["connector"] = "NEXTJS_SIN_INVENTARIO", None
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--directorio",
                    default=r"D:\INMO CAPITAL\agency_platform_directory.jsonl")
    ap.add_argument("--plataforma", default="NEXTJS")
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\NEXTJS_DISCOVERY.jsonl")
    ap.add_argument("--concurrencia", type=int, default=3)
    a = ap.parse_args()

    filas = [json.loads(l) for l in Path(a.directorio).open(encoding="utf-8") if l.strip()]
    objetivo = [f for f in filas if f["platform"] == a.plataforma and f.get("domain")]
    print(f"### FINGERPRINT {a.plataforma} ###")
    print(f"  fuentes: {len(objetivo)}\n", flush=True)

    lim = LimitadorDeRitmo(2.0)
    res = []
    with Path(a.salida).open("w", encoding="utf-8") as fh:
        for i in range(0, len(objetivo), 10):
            with ThreadPoolExecutor(max_workers=a.concurrencia) as ex:
                for r in ex.map(lambda f: analizar(f, Descargador(lim)),
                                objetivo[i:i + 10]):
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                    res.append(r)
            fh.flush()
            print(f"    {min(i + 10, len(objetivo))}/{len(objetivo)}", flush=True)

    print("\n  familias:")
    for k, v in Counter(r["familia"] for r in res).most_common():
        con = {r.get("connector") for r in res if r["familia"] == k} - {None}
        print(f"    {k:26} {v:4}  connector: {', '.join(sorted(con)) or '-'}")
    print(f"\n  con __NEXT_DATA__: {sum(1 for r in res if r.get('tiene_next_data'))}")
    print(f"  con buildId:       {sum(1 for r in res if r.get('build_id'))}")
    print(f"  con sitemap:       {sum(1 for r in res if r.get('sitemap'))}")
    print(f"  recuperables:      {sum(1 for r in res if r.get('connector'))}/{len(res)}")
    print(f"\n  artefacto -> {a.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
