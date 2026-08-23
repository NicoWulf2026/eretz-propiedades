#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Censo de las fuentes que ningun connector supo leer.

La pregunta no es "que tiene este sitio" sino "cuantas formas distintas de
publicar hay aca". Cincuenta fuentes que no se pudieron leer pueden ser
cincuenta problemas o cuatro; solo agrupandolas por COMPORTAMIENTO se sabe, y
solo entonces tiene sentido escribir un connector.

Una fuente clasificada como Tokko que no muestra ninguna evidencia de Tokko no
se fuerza al connector de Tokko: se devuelve al mapa general. Forzarla produce
un cero silencioso, que es peor que un error.

Baja la home y, a lo sumo, una pagina de listado. No descarga fichas.
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

RUTAS = ("/propiedades", "/Propiedades", "/inmuebles", "/venta", "/Venta",
         "/propiedades-en-venta", "/buscar", "/emprendimientos")

# Cada senal se busca en el HTML servido. Todas son reproducibles: nadie tiene
# que confiar en el criterio de quien clasifico.
SENALES = {
    "tokko_tfw": r"static\.tokkobroker\.com/tfw/",
    "tokko_cdn": r"static\.tokkobroker\.com",
    "tokko_api": r"api\.tokkobroker\.com|tokkobroker\.com/api",
    "inmoclick": r"inmoclick\.(ai|com)",
    "wordpress": r"wp-content|wp-json|wp-includes",
    "wasi": r"wasi\.co|wasiapp",
    "inmoup": r"inmoup\.com\.ar",
    "mediacore": r"mediacore|medialabs",
    "inmovar": r"/templates/inmovar",
    "next": r"__NEXT_DATA__|/_next/",
    "nuxt": r"__NUXT__|/_nuxt/",
    "react": r"data-reactroot|react-dom",
    "jsonld": r"application/ld\+json",
    "sitemap_ref": r"sitemap[^\"'<>]{0,20}\.xml",
}


def analizar(fuente: dict, d: Descargador) -> dict:
    url = fuente["official_url"]
    p = urllib.parse.urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    out = {
        "canonical_agency_id": fuente["canonical_agency_id"],
        "eretz_id": fuente.get("eretz_id"),
        "agency_name": fuente.get("agency_name"),
        "dominio": base,
        "official_url": url,
        "clasificacion_anterior": fuente.get("variante") or fuente.get("estado"),
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "classifier_version": "unsupported_census_v1",
    }
    try:
        html = d.bajar(url)
    except Bloqueado as e:
        return {**out, "clasificacion_nueva": "BLOQUEADA", "evidencia": str(e)[:60]}
    except (ErrorTransitorio, ErrorPermanente) as e:
        return {**out, "clasificacion_nueva": "INACCESIBLE",
                "evidencia": type(e).__name__}

    senales = sorted(k for k, patron in SENALES.items()
                     if re.search(patron, html, re.I))
    out["evidencia"] = senales
    out["bytes_home"] = len(html)

    # Buscar el listado: primero el que la home enlaza, despues rutas conocidas.
    ruta = next((r for r in RUTAS if f'href="{r}"' in html), None)
    listado, ruta_usada = html, p.path or "/"
    if ruta and ruta != (p.path or "/"):
        try:
            listado = d.bajar(base + ruta)
            ruta_usada = ruta
        except (ErrorTransitorio, ErrorPermanente, Bloqueado):
            listado = html
    out["ruta_listado"] = ruta_usada

    fichas_seccion = {u for u in re.findall(r'href="([^"]{4,200})"', listado)
                      if RE_FICHA.search(urllib.parse.urljoin(base, u))}
    fichas_raiz = {u for u in re.findall(r'href="([^"]{4,200})"', listado)
                   if RE_FICHA_RAIZ.search(
                       urllib.parse.urlparse(urllib.parse.urljoin(base, u)).path)}
    fichas_tokko = set(re.findall(r"/p/(\d+)-", listado))
    out["fichas_seccion"] = len(fichas_seccion)
    out["fichas_raiz"] = len(fichas_raiz)
    out["fichas_tokko"] = len(fichas_tokko)

    m = re.search(r"(\d[\d.]*)\s*(?:Resultados|propiedades|inmuebles)",
                  re.sub(r"<[^>]+>", " ", listado), re.I)
    crudo = m.group(1).replace(".", "") if m else ""
    out["declared_inventory"] = int(crudo) if crudo.isdigit() else None
    out["enumerated_inventory"] = max(len(fichas_seccion), len(fichas_raiz),
                                      len(fichas_tokko))
    if out["declared_inventory"]:
        out["coverage_ratio"] = round(
            out["enumerated_inventory"] / out["declared_inventory"], 4)

    out["ajax_paginacion"] = bool(re.search(r"\$\.ajax\('[^']{20,}&p=", listado))
    out["endpoints"] = list(dict.fromkeys(re.findall(
        r"[\"'](/(?:api|ajax|json|wp-json|graphql)[^\"'\s]{0,60})", listado)))[:5]

    # --- taxonomia por comportamiento ---------------------------------------
    ev = set(senales)
    if out["fichas_tokko"] and out["ajax_paginacion"]:
        cat, conector = "TOKKO_TFW_ESTANDAR", "tokko"
    elif out["fichas_tokko"]:
        cat, conector = "TOKKO_TFW_SIN_AJAX", "tokko"
    elif "inmoclick" in ev:
        cat, conector = "TOKKO_INMOCLICK", "generico"
    elif out["fichas_raiz"]:
        cat, conector = "TOKKO_FRONTEND_PROPIO_ROOT", "generico"
    elif out["fichas_seccion"]:
        cat, conector = "FRONTEND_PROPIO_SSR", "generico"
    elif ev & {"wordpress"}:
        # Estaba anotada como Tokko y es WordPress: se devuelve al mapa general
        # en vez de forzarla, que produciria un cero silencioso.
        cat, conector = "RECLASIFICAR_WORDPRESS", "wordpress"
    elif ev & {"wasi", "inmoup", "mediacore", "inmovar"}:
        cat, conector = "RECLASIFICAR_OTRA_PLATAFORMA", None
    elif ev & {"next", "nuxt", "react"} and not out["enumerated_inventory"]:
        cat, conector = "RENDERIZA_EN_CLIENTE", None
    elif "sitemap_ref" in ev or "jsonld" in ev:
        cat, conector = "ESTRUCTURADO_SIN_LISTADO_VISIBLE", "generico"
    elif not (ev & {"tokko_cdn", "tokko_tfw", "tokko_api"}):
        cat, conector = "SIN_EVIDENCIA_TOKKO", None
    else:
        cat, conector = "TOKKO_CUSTOM_SIN_RESOLVER", None
    out["clasificacion_nueva"] = cat
    out["connector_candidato"] = conector
    out["status"] = "CON_CONECTOR" if conector else "SIN_CONECTOR"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventarios", nargs="+", required=True)
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\UNSUPPORTED_CENSUS.jsonl")
    ap.add_argument("--concurrencia", type=int, default=4)
    ap.add_argument("--intervalo", type=float, default=2.0)
    a = ap.parse_args()

    padron = {}
    for l in (Path(a.data_dir) / "agency_web_directory.jsonl").open(encoding="utf-8"):
        if l.strip():
            d = json.loads(l)
            eid = d.get("eretz_id")
            if str(eid).isdigit():
                padron[d["canonical_agency_id"]] = int(eid)

    fuentes, vistos = [], set()
    for ruta in a.inventarios:
        p = Path(ruta)
        if not p.exists():
            continue
        for l in p.open(encoding="utf-8"):
            if not l.strip():
                continue
            try:
                r = json.loads(l)
            except ValueError:
                continue
            if r.get("estado") not in ("VARIANTE_NO_SOPORTADA", "ERROR_DISCOVERY",
                                       "EXCEPCION"):
                continue
            cid = r.get("canonical_agency_id")
            if cid in vistos:
                continue
            vistos.add(cid)
            r["eretz_id"] = padron.get(cid)
            fuentes.append(r)

    print(f"### CENSO DE FUENTES NO SOPORTADAS ###")
    print(f"  fuentes a clasificar: {len(fuentes)}\n", flush=True)
    if not fuentes:
        return 0

    lim = LimitadorDeRitmo(a.intervalo)
    filas = []
    with Path(a.salida).open("w", encoding="utf-8") as fh:
        for i in range(0, len(fuentes), 10):
            with ThreadPoolExecutor(max_workers=a.concurrencia) as ex:
                for r in ex.map(lambda f: analizar(f, Descargador(lim)),
                                fuentes[i:i + 10]):
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                    filas.append(r)
            fh.flush()
            print(f"    {min(i + 10, len(fuentes))}/{len(fuentes)}", flush=True)

    print("\n  clasificacion nueva:")
    for k, v in Counter(r["clasificacion_nueva"] for r in filas).most_common():
        con = {x.get("connector_candidato") for x in filas
               if x["clasificacion_nueva"] == k} - {None}
        print(f"    {k:36} {v:4}  conector: {', '.join(sorted(con)) or '-'}")
    rec = [r for r in filas if r.get("status") == "CON_CONECTOR"]
    print(f"\n  recuperables con un conector existente: {len(rec)}/{len(filas)}")
    print(f"  inventario declarado en esas: "
          f"{sum(r.get('declared_inventory') or 0 for r in rec):,}")
    print(f"\n  artefacto -> {a.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
