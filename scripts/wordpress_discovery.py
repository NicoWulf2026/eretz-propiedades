#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Discovery de las fuentes WordPress.

WordPress no es una plataforma inmobiliaria: es un CMS sobre el que corren
plugins muy distintos (Houzez, WP Residence, Real Homes, Estatik, Realteo...).
Cada uno guarda las propiedades en su propio custom post type, asi que lo que
define el conector no es "WordPress" sino que post type publica el inventario.

La via barata existe y hay que buscarla primero: wp-json expone los post types
registrados y devuelve JSON estructurado, lo que ahorra el parser entero. Si
wp-json esta cerrado se cae a sitemap y recien despues a HTML.
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

# Post types que usan los plugins inmobiliarios mas comunes.
TIPOS_INMO = ("property", "properties", "propiedad", "propiedades", "inmueble",
              "inmuebles", "listing", "listings", "estate", "houzez_property",
              "rem_property", "wpl_property", "casa", "residence")


def analizar(fuente: dict, d: Descargador) -> dict:
    url = fuente["official_url"]
    p = urllib.parse.urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    out = {"canonical_agency_id": fuente["canonical_agency_id"],
           "agency_name": fuente.get("agency_name"), "official_url": url,
           "base": base, "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S")}

    # --- 1. wp-json: la via mas barata -------------------------------------
    try:
        cuerpo = d.bajar(base + "/wp-json/wp/v2/types")
        datos = json.loads(cuerpo)
        tipos = sorted(datos.keys()) if isinstance(datos, dict) else []
        out["wp_json"] = True
        out["post_types"] = tipos[:40]
        candidatos = [t for t in tipos
                      if any(k == t.lower() or k in t.lower() for k in TIPOS_INMO)]
        out["post_types_inmo"] = candidatos
        if candidatos:
            t = candidatos[0]
            ruta = (datos[t].get("rest_base") or t) if isinstance(datos.get(t), dict) else t
            out["rest_base"] = ruta
            try:
                m = d.bajar(f"{base}/wp-json/wp/v2/{ruta}?per_page=1")
                items = json.loads(m)
                out["rest_responde"] = isinstance(items, list)
                out["rest_muestra_campos"] = sorted(items[0].keys())[:25] if items else []
            except (ValueError, ErrorTransitorio, ErrorPermanente, Bloqueado) as e:
                out["rest_responde"] = False
                out["rest_error"] = type(e).__name__
    except ErrorPermanente:
        out["wp_json"] = False
    except (ValueError, ErrorTransitorio, Bloqueado) as e:
        out["wp_json"] = False
        out["wp_json_error"] = type(e).__name__

    # --- 2. sitemap --------------------------------------------------------
    if not out.get("rest_responde"):
        for ruta in ("/wp-sitemap.xml", "/sitemap_index.xml", "/sitemap.xml"):
            try:
                cuerpo = d.bajar(base + ruta)
            except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                continue
            if "<" not in cuerpo:
                continue
            out["sitemap"] = ruta
            hallados = [t for t in TIPOS_INMO if f"/{t}-" in cuerpo or f"/{t}/" in cuerpo]
            out["sitemap_tipos"] = hallados
            break

    # --- 3. HTML como ultimo recurso ---------------------------------------
    if not out.get("rest_responde") and not out.get("sitemap_tipos"):
        try:
            html = d.bajar(url)
            rutas = Counter(m.group(1).lower() for m in
                            re.finditer(r'href="[^"]*?/([a-z\-]{4,20})/[^"]{3,}"', html))
            out["rutas_frecuentes"] = [r for r, _ in rutas.most_common(8)]
            out["rutas_inmo"] = [r for r in out["rutas_frecuentes"]
                                 if any(k in r for k in TIPOS_INMO)]
        except (ErrorTransitorio, ErrorPermanente, Bloqueado) as e:
            out["html_error"] = type(e).__name__

    if out.get("rest_responde"):
        out["estrategia"] = "WORDPRESS_REST"
    elif out.get("sitemap_tipos"):
        out["estrategia"] = "WORDPRESS_SITEMAP"
    elif out.get("rutas_inmo"):
        out["estrategia"] = "WORDPRESS_HTML"
    else:
        out["estrategia"] = "SIN_INVENTARIO_DETECTADO"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--muestra", type=int, default=60)
    ap.add_argument("--concurrencia", type=int, default=6)
    a = ap.parse_args()
    dd = Path(a.data_dir)

    mapa = [json.loads(l) for l in
            (dd / "scrape_source_technology_map.jsonl").open(encoding="utf-8") if l.strip()]
    wp = [x for x in mapa if x["detected_platform"] == "WORDPRESS"]
    paso = max(1, len(wp) // a.muestra)
    muestra = wp[::paso][:a.muestra]

    print(f"### DISCOVERY WORDPRESS ###")
    print(f"  fuentes WORDPRESS: {len(wp):,}   muestra: {len(muestra)}\n", flush=True)

    lim = LimitadorDeRitmo(1.5)
    salida = dd / "wordpress_discovery.jsonl"
    filas = []
    with salida.open("w", encoding="utf-8") as fh:
        with ThreadPoolExecutor(max_workers=a.concurrencia) as ex:
            for r in ex.map(lambda f: analizar(f, Descargador(lim)), muestra):
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                fh.flush()
                filas.append(r)

    print("  estrategias:")
    for k, v in Counter(r["estrategia"] for r in filas).most_common():
        print(f"    {k:28} {v:4}  ({v/len(filas)*100:5.1f}%)")
    print(f"\n  wp-json abierto:      {sum(1 for r in filas if r.get('wp_json'))}")
    print(f"  REST de inventario:   {sum(1 for r in filas if r.get('rest_responde'))}")
    tipos = Counter(t for r in filas for t in (r.get("post_types_inmo") or []))
    print(f"  post types inmo:      {dict(tipos.most_common(8))}")
    print(f"\n  artefacto -> wordpress_discovery.jsonl")
    return 0


if __name__ == "__main__":
    sys.exit(main())
