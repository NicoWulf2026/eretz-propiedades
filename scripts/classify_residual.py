#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Clasificar lo que quedo sin cubrir, por MECANISMO de publicacion.

`RESIDUAL_UNCOVERED.jsonl` dice cuantas agencias faltan y con que etiqueta
tecnologica quedaron, pero esa etiqueta no sirve para decidir: 728 dicen
UNKNOWN, y "UNKNOWN" no es un mecanismo. Laravel tampoco: es el framework de
abajo, y ya se comprobo que 36 sitios Laravel no eran Wasi.

La pregunta util es como publica cada sitio su inventario, porque de eso
depende si un connector existente ya lo cubre:

  PLATAFORMA_CONOCIDA   tiene marcadores de una plataforma que ya sabemos leer
  SITEMAP_CON_FICHAS    el sitemap enumera fichas: el connector generico sirve
  LISTADO_SERVIDO       el HTML servido trae enlaces a fichas
  JSON_EMBEBIDO         estado serializado con propiedades
  RENDERIZA_EN_CLIENTE  hay que ejecutar JavaScript
  SIN_INVENTARIO        responde pero no publica propiedades
  INACCESIBLE           no respondio

Agrupar por mecanismo es lo que dice si faltan cuatro connectors o cuarenta.

Baja la home y, a lo sumo, el sitemap y una pagina de listado. No descarga
fichas. Solo lee.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from connectors.base import (Bloqueado, Descargador, ErrorPermanente,  # noqa: E402
                             ErrorTransitorio, LimitadorDeRitmo)
from connectors.generico import RE_FICHA, RE_FICHA_RAIZ  # noqa: E402
from scripts.wasi_fingerprint import fingerprint as fp_wasi  # noqa: E402

VERSION = "residual_classifier_v1"

# Plataformas para las que YA existe connector, o que agrupan muchas fuentes.
PLATAFORMAS = {
    "TOKKO": (r"tokkobroker|static\.tokkobroker\.com", "tokko"),
    "WORDPRESS": (r"wp-content|wp-json|wp-includes", "wordpress"),
    "INMOCLICK": (r"inmoclick\.(ai|com)", "generico"),
    "INMOUP": (r"inmoup\.com\.ar", None),
    "MEDIACORE": (r"mediacore|medialabs", None),
    "INMOVAR": (r"/templates/inmovar", None),
    "SIVAL": (r"sival\.com\.ar|sivalweb", None),
    "EASYBROKER": (r"easybroker\.com", None),
    "REDINMOBILIARIA": (r"redinmobiliaria\.com", None),
}

CLIENTE = re.compile(r"__NEXT_DATA__|/_next/|__NUXT__|/_nuxt/|data-reactroot|"
                     r"ng-version=|wixstatic", re.I)
JSON_EMBEBIDO = re.compile(r"application/ld\+json|window\.__INITIAL_STATE__|"
                           r"__NEXT_DATA__", re.I)

RUTAS = ("/propiedades", "/inmuebles", "/venta", "/propiedades-en-venta",
         "/emprendimientos", "/buscar")


def _bajar(d: Descargador, url: str) -> str | None:
    try:
        return d.bajar(url)
    except (Bloqueado, ErrorPermanente, ErrorTransitorio):
        return None


def _fichas(html: str, base: str) -> set[str]:
    out = set()
    for h in re.findall(r'href="([^"]{4,200})"', html):
        u = urllib.parse.urljoin(base, h)
        if urllib.parse.urlparse(u).netloc != urllib.parse.urlparse(base).netloc:
            continue
        if RE_FICHA.search(u) or RE_FICHA_RAIZ.search(urllib.parse.urlparse(u).path):
            out.add(u)
    return out


def analizar(f: dict, lim: LimitadorDeRitmo) -> dict:
    url = f.get("domain") or ""
    p = urllib.parse.urlparse(url)
    base = f"{p.scheme or 'https'}://{p.netloc}"
    d = Descargador(lim, limite_bytes=900_000)
    out = {
        "canonical_agency_id": f.get("canonical_agency_id"),
        "eretz_id": f.get("eretz_id"), "agency_name": f.get("agency_name"),
        "domain": url, "host": f.get("host"), "province": f.get("province"),
        "plataforma_previa": f.get("platform"),
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "classifier_version": VERSION,
    }

    html = _bajar(d, base) or _bajar(d, url)
    if html is None:
        return {**out, "mecanismo": "INACCESIBLE", "connector": None,
                "motivo": "no respondio; no se puede afirmar nada del sitio"}
    out["bytes_home"] = len(html)

    # 1. Plataforma conocida.
    plataforma = conector = None
    for nombre, (patron, con) in PLATAFORMAS.items():
        if re.search(patron, html, re.I):
            plataforma, conector = nombre, con
            break
    if plataforma is None and fp_wasi(html, base)["es_wasi"]:
        plataforma, conector = "WASI", "wasi"
    out["plataforma_detectada"] = plataforma

    # 2. Sitemap con fichas: la enumeracion mas barata.
    sm = _bajar(d, base + "/sitemap.xml") or ""
    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sm) if "<loc>" in sm else []
    fichas_sm = {u for u in locs
                 if RE_FICHA.search(u)
                 or RE_FICHA_RAIZ.search(urllib.parse.urlparse(u).path)}
    out["sitemap_locs"] = len(locs)
    out["sitemap_fichas"] = len(fichas_sm)
    out["sitemap_es_indice"] = "<sitemapindex" in sm

    # 3. Fichas en el HTML servido, en la home o en un listado enlazado.
    fichas = _fichas(html, base)
    ruta = next((r for r in RUTAS if f'href="{r}"' in html), None)
    if not fichas and ruta:
        listado = _bajar(d, base + ruta)
        if listado:
            fichas = _fichas(listado, base)
            out["ruta_listado"] = ruta
    out["fichas_html"] = len(fichas)

    out["json_embebido"] = bool(JSON_EMBEBIDO.search(html))
    out["renderiza_cliente"] = bool(CLIENTE.search(html))
    texto = re.sub(r"<[^>]+>", " ", html)
    m = re.search(r"(\d[\d.]*)\s*(?:Resultados|propiedades|inmuebles)", texto, re.I)
    crudo = m.group(1).replace(".", "") if m else ""
    out["declared_inventory"] = int(crudo) if crudo.isdigit() else None

    # --- mecanismo, de mas barato a mas caro -------------------------------
    if plataforma and conector:
        out["mecanismo"], out["connector"] = "PLATAFORMA_CONOCIDA", conector
    elif plataforma:
        out["mecanismo"], out["connector"] = "PLATAFORMA_SIN_CONNECTOR", None
    elif fichas_sm:
        out["mecanismo"], out["connector"] = "SITEMAP_CON_FICHAS", "generico"
    elif fichas:
        out["mecanismo"], out["connector"] = "LISTADO_SERVIDO", "generico"
    elif out["json_embebido"] and not out["renderiza_cliente"]:
        out["mecanismo"], out["connector"] = "JSON_EMBEBIDO", "generico"
    elif out["renderiza_cliente"]:
        out["mecanismo"], out["connector"] = "RENDERIZA_EN_CLIENTE", None
    else:
        out["mecanismo"], out["connector"] = "SIN_INVENTARIO", None
        out["motivo"] = ("responde pero no se le vio ninguna ficha: puede ser "
                         "institucional, estar vacio o publicar de una forma "
                         "que este sondeo no reconoce")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada",
                    default=r"D:\INMO CAPITAL\RESIDUAL_UNCOVERED.jsonl")
    ap.add_argument("--salida",
                    default=r"D:\INMO CAPITAL\RESIDUAL_CLASSIFIED.jsonl")
    ap.add_argument("--plataforma", nargs="*", default=[],
                    help="acota a estas etiquetas previas; vacio = todas")
    ap.add_argument("--limite", type=int, default=0)
    ap.add_argument("--concurrencia", type=int, default=2)
    ap.add_argument("--intervalo", type=float, default=1.5)
    a = ap.parse_args()

    filas = [json.loads(l) for l in Path(a.entrada).open(encoding="utf-8") if l.strip()]
    if a.plataforma:
        quiere = {x.upper() for x in a.plataforma}
        filas = [f for f in filas if (f.get("platform") or "").upper() in quiere]
    if a.limite:
        filas = filas[:a.limite]

    print("### CLASIFICACION DEL RESIDUAL ###")
    print(f"  fuentes: {len(filas)}\n", flush=True)
    if not filas:
        return 0

    lim = LimitadorDeRitmo(a.intervalo)
    res = []
    # Escritura incremental: una excepcion al final no puede llevarse lo hecho.
    with Path(a.salida).open("w", encoding="utf-8") as fh:
        for i in range(0, len(filas), 10):
            with ThreadPoolExecutor(max_workers=a.concurrencia) as ex:
                for r in ex.map(lambda f: analizar(f, lim), filas[i:i + 10]):
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                    res.append(r)
            fh.flush()
            print(f"    {min(i + 10, len(filas))}/{len(filas)}", flush=True)

    print("\n  MECANISMO DE PUBLICACION")
    for k, v in Counter(r["mecanismo"] for r in res).most_common():
        con = {r.get("connector") for r in res if r["mecanismo"] == k} - {None}
        decl = sum(r.get("declared_inventory") or 0 for r in res
                   if r["mecanismo"] == k)
        print(f"    {k:26} {v:5}  connector: {', '.join(sorted(con)) or '-':10} "
              f"inventario declarado {decl:7,}")

    cubribles = [r for r in res if r.get("connector")]
    print(f"\n  RECUPERABLES CON UN CONNECTOR QUE YA EXISTE: {len(cubribles)}/{len(res)}")
    for k, v in Counter(r["connector"] for r in cubribles).most_common():
        print(f"    {k:14} {v:5}")

    print("\n  plataformas encontradas entre las que decian UNKNOWN:")
    porplat = Counter(r.get("plataforma_detectada") for r in res
                      if r.get("plataforma_detectada"))
    for k, v in porplat.most_common(12):
        print(f"    {k:20} {v:5}")

    print(f"\n  artefacto -> {a.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
