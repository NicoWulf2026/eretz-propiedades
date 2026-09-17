#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Discovery de variantes Tokko.

920 fuentes comparten plataforma, no necesariamente el mismo frontend. Antes de
escribir un conector conviene saber cuantas variantes hay realmente: un conector
que asume una sola y encuentra tres falla en silencio, devolviendo cero
propiedades sin error.

Baja la home y, si hace falta, la pagina de listado. No baja fichas.
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

UA = "Mozilla/5.0 (compatible; ERETZ-Discovery/1.0; +contacto@eretz)"

# Rutas de listado que usa el sitio hospedado de Tokko (Tokko Front Web).
RUTAS_TFW = ("/Propiedades", "/propiedades", "/Venta", "/venta", "/Buscar")


def bajar(url: str, timeout: int = 20, limite: int = 400_000) -> tuple[int | None, str]:
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Encoding": "gzip",
        "Accept": "text/html,application/xhtml+xml"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            raw = r.read(limite)
            if r.headers.get("Content-Encoding") == "gzip":
                try:
                    raw = gzip.decompress(raw)
                except OSError:
                    pass
            juego = "utf-8"
            tipo = r.headers.get("Content-Type") or ""
            m = re.search(r"charset=([\w-]+)", tipo, re.I)
            if m:
                juego = m.group(1)
            return r.getcode(), raw.decode(juego, "ignore")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return None, ""


def analizar(fuente: dict) -> dict:
    url = fuente["official_url"]
    base = f"{urllib.parse.urlparse(url).scheme}://{urllib.parse.urlparse(url).netloc}"
    out = {"canonical_agency_id": fuente["canonical_agency_id"],
           "agency_name": fuente.get("agency_name"), "official_url": url,
           "base": base, "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S")}

    codigo, html = bajar(url)
    out["http"] = codigo
    if not html:
        out["variante"] = "SIN_RESPUESTA"
        return out

    # El id de cliente Tokko aparece en la ruta del logo servido por su CDN.
    m = re.search(r"static\.tokkobroker\.com/logos/(\d+)/", html)
    out["tokko_client_id"] = m.group(1) if m else None
    out["usa_tfw"] = "static.tokkobroker.com/tfw/" in html

    # Buscar la pagina de listado: primero la que ya trae la home.
    ruta = None
    for r in RUTAS_TFW:
        if f'href="{r}"' in html:
            ruta = r
            break
    if ruta is None and re.search(r"/p/\d{4,}-", html):
        ruta = urllib.parse.urlparse(url).path or "/"

    listado_html = html
    if ruta and ruta != (urllib.parse.urlparse(url).path or "/"):
        time.sleep(0.4)
        c2, listado_html = bajar(base + ruta)
        out["http_listado"] = c2
        if not listado_html:
            listado_html = html
    out["ruta_listado"] = ruta

    ids = sorted(set(re.findall(r"/p/(\d+)-", listado_html)))
    out["ids_en_listado"] = len(ids)
    out["ejemplo_id"] = ids[0] if ids else None

    a = re.search(r"\$\.ajax\('([^']{20,800})'", listado_html)
    out["tiene_ajax_paginacion"] = bool(a)
    if a:
        q = a.group(1)
        out["param_pagina"] = "p" if q.rstrip().endswith("&p=") else (
            "page" if "page=" in q else "desconocido")
        out["query_paginacion"] = q[:400]
    m = re.search(r"(\d[\d.]*)\s*Resultados", listado_html, re.I)
    crudo = m.group(1).replace(".", "") if m else ""
    out["total_declarado"] = int(crudo) if crudo.isdigit() else None

    if out["usa_tfw"] and ids and out.get("tiene_ajax_paginacion"):
        out["variante"] = "TFW_ESTANDAR"
    elif out["usa_tfw"] and ids:
        out["variante"] = "TFW_SIN_AJAX"
    elif ids:
        out["variante"] = "FRONTEND_PROPIO_RUTA_P"
    elif out["tokko_client_id"] or "tokkobroker" in html:
        out["variante"] = "TOKKO_FRONTEND_PROPIO"
    else:
        out["variante"] = "SIN_MARCADOR"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--muestra", type=int, default=60)
    ap.add_argument("--hilos", type=int, default=4)
    a = ap.parse_args()
    dd = Path(a.data_dir)

    mapa = [json.loads(l) for l in
            (dd / "scrape_source_technology_map.jsonl").open(encoding="utf-8") if l.strip()]
    tokko = [x for x in mapa if x["detected_platform"] == "TOKKO"]

    # Muestra repartida a lo largo de la lista, no los primeros N: los primeros
    # estan ordenados por nombre y serian todos de la misma zona.
    paso = max(1, len(tokko) // a.muestra)
    muestra = tokko[::paso][:a.muestra]

    print(f"### DISCOVERY TOKKO ###")
    print(f"  fuentes TOKKO: {len(tokko):,}   muestra: {len(muestra)}\n", flush=True)

    filas = []
    salida = dd / "tokko_discovery.jsonl"
    with salida.open("w", encoding="utf-8") as fh:
        for i in range(0, len(muestra), 10):
            with ThreadPoolExecutor(max_workers=a.hilos) as ex:
                for r in ex.map(analizar, muestra[i:i + 10]):
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                    filas.append(r)
            fh.flush()
            time.sleep(0.5)

    print("  variantes:")
    for k, v in Counter(r["variante"] for r in filas).most_common():
        print(f"    {k:26} {v:4}  ({v/len(filas)*100:5.1f}%)")
    con = [r for r in filas if r.get("ids_en_listado")]
    print(f"\n  con inventario visible:   {len(con)}/{len(filas)}")
    print(f"  con ajax de paginacion:   {sum(1 for r in filas if r.get('tiene_ajax_paginacion'))}")
    print(f"  con tokko_client_id:      {sum(1 for r in filas if r.get('tokko_client_id'))}")
    print(f"  parametro de pagina:      {dict(Counter(r.get('param_pagina') for r in filas if r.get('param_pagina')))}")
    print(f"  rutas de listado:         {dict(Counter(r.get('ruta_listado') for r in filas).most_common(5))}")
    tot = [r['total_declarado'] for r in filas if r.get('total_declarado')]
    if tot:
        tot.sort()
        print(f"\n  inventario declarado: min={tot[0]} mediana={tot[len(tot)//2]} max={tot[-1]} suma={sum(tot):,}")
    print(f"\n  artefacto -> tokko_discovery.jsonl")
    return 0


if __name__ == "__main__":
    sys.exit(main())
