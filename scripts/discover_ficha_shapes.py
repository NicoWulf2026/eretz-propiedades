#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Descubrir QUE FORMA tienen las urls de ficha que no sabemos reconocer.

496 fuentes quedaron como "responde pero no publica inventario". Sólo 5 son
sitios vacíos: las otras 491 sirven una página real. Así que lo más probable no
es que no publiquen, sino que sus fichas tienen una forma de url que nuestros
patrones no contemplan.

Este sondeo NO clasifica. Agrupa las urls internas de cada sitio por su FORMA
-cuántos tramos tiene la ruta, si el último es numérico, si hay un slug largo- y
cuenta cuántas comparten cada forma. Una forma con muchas urls hermanas y un
identificador variable es un listado de fichas; una con dos o tres es el menú.

La diferencia con adivinar: si aparecen 200 urls con la forma
`/emprendimientos/<slug>/<id>`, eso es inventario, lo reconozca o no el patrón
que tenemos escrito hoy.

Baja la home, el sitemap y a lo sumo dos páginas más. Solo lee.
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

VERSION = "ficha_shapes_v1"

# Tramos que nunca son una ficha: son secciones, recursos o paginas del sitio.
RUIDO = re.compile(
    r"^(wp-|feed|rss|comments?|author|category|categoria|tag|etiqueta|page|"
    r"pagina|search|buscar|busqueda|contacto|contact|nosotros|about|blog|"
    r"noticias|novedades|servicios|tasacion|privacidad|terminos|login|admin|"
    r"cdn-cgi|assets|static|media|images?|css|js|fonts?)", re.I)

EXT = re.compile(r"\.(?:jpe?g|png|gif|webp|svg|css|js|pdf|xml|ico|woff2?|zip)$", re.I)


def forma_de(ruta: str) -> str:
    """La FORMA de una ruta, con los valores variables reemplazados.

    /propiedad/casa-en-venta-palermo/8471  ->  /<palabra>/<slug>/<num>

    Asi dos fichas distintas de la misma seccion caen en la misma forma y se
    pueden contar juntas.
    """
    tramos = [t for t in ruta.split("/") if t]
    if not tramos:
        return "/"
    salida = []
    for t in tramos:
        if t.isdigit():
            salida.append("<num>")
        elif re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+){2,}", t, re.I):
            salida.append("<slug>")
        elif re.search(r"\d{3,}", t):
            salida.append("<slug-con-id>")
        elif re.fullmatch(r"[a-z0-9-]{1,24}", t, re.I):
            salida.append(t.lower())
        else:
            salida.append("<otro>")
    return "/" + "/".join(salida)


def parece_ficha(forma: str) -> bool:
    """Una forma con un identificador variable al final es candidata a ficha."""
    return forma.rsplit("/", 1)[-1] in ("<num>", "<slug>", "<slug-con-id>")


def _bajar(d: Descargador, url: str) -> str | None:
    try:
        return d.bajar(url)
    except (Bloqueado, ErrorPermanente, ErrorTransitorio):
        return None


def internas(html: str, base: str) -> list[str]:
    host = urllib.parse.urlparse(base).netloc
    out = []
    for h in re.findall(r'href="([^"]{1,300})"', html or ""):
        u = urllib.parse.urljoin(base, h.replace("&amp;", "&"))
        p = urllib.parse.urlparse(u)
        if p.netloc != host or p.query or EXT.search(p.path or ""):
            continue
        tramos = [t for t in (p.path or "").split("/") if t]
        if tramos and RUIDO.match(tramos[0]):
            continue
        out.append(p.path or "/")
    return out


def analizar(f: dict, lim: LimitadorDeRitmo) -> dict:
    url = f.get("domain") or f.get("official_url") or ""
    p = urllib.parse.urlparse(url)
    base = f"{p.scheme or 'https'}://{p.netloc}"
    d = Descargador(lim, limite_bytes=900_000)
    out = {"canonical_agency_id": f.get("canonical_agency_id"),
           "agency_name": f.get("agency_name"), "domain": url, "host": f.get("host"),
           "mecanismo_previo": f.get("mecanismo"),
           "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "discovery_version": VERSION}

    html = _bajar(d, base)
    if html is None:
        return {**out, "estado": "INACCESIBLE"}

    rutas = internas(html, base)

    # El sitemap suele traer TODO el inventario aunque la home no lo enlace.
    sm = _bajar(d, base + "/sitemap.xml") or ""
    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sm) if "<loc>" in sm else []
    # Si es un indice, se sigue el primer sub-sitemap que no sea de paginas.
    if "<sitemapindex" in sm and locs:
        sub = next((u for u in locs
                    if not re.search(r"(page|categor|tag|author|post)", u, re.I)), None)
        if sub:
            cuerpo = _bajar(d, sub) or ""
            locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", cuerpo) or locs
    host = urllib.parse.urlparse(base).netloc
    for u in locs:
        q = urllib.parse.urlparse(u)
        if q.netloc == host and not EXT.search(q.path or ""):
            rutas.append(q.path or "/")
    out["urls_internas"] = len(rutas)
    out["sitemap_locs"] = len(locs)

    formas = Counter(forma_de(r) for r in rutas)
    candidatas = [(k, v) for k, v in formas.items() if parece_ficha(k) and v >= 3]
    candidatas.sort(key=lambda t: -t[1])
    out["formas"] = [{"forma": k, "urls": v} for k, v in candidatas[:6]]
    out["ejemplos"] = []
    if candidatas:
        mejor = candidatas[0][0]
        out["ejemplos"] = [r for r in dict.fromkeys(rutas)
                           if forma_de(r) == mejor][:3]
        out["forma_dominante"] = mejor
        out["urls_en_la_forma"] = candidatas[0][1]
        out["estado"] = "FORMA_ENCONTRADA"
    else:
        out["estado"] = "SIN_FORMA_REPETIDA"
        out["formas_todas"] = [{"forma": k, "urls": v}
                               for k, v in formas.most_common(5)]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", default=r"D:\INMO CAPITAL\RESIDUAL_CLASSIFIED.jsonl")
    ap.add_argument("--mecanismo", nargs="*", default=["SIN_INVENTARIO"])
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\FICHA_SHAPES.jsonl")
    ap.add_argument("--limite", type=int, default=0)
    ap.add_argument("--concurrencia", type=int, default=4)
    ap.add_argument("--intervalo", type=float, default=1.5)
    a = ap.parse_args()

    filas = [json.loads(l) for l in Path(a.entrada).open(encoding="utf-8") if l.strip()]
    if a.mecanismo and "TODAS" not in a.mecanismo:
        quiere = set(a.mecanismo)
        filas = [f for f in filas if f.get("mecanismo") in quiere]
    if a.limite:
        filas = filas[:a.limite]

    print("### FORMAS DE FICHA ###")
    print(f"  fuentes: {len(filas)}\n", flush=True)
    if not filas:
        return 0

    lim = LimitadorDeRitmo(a.intervalo)
    res = []
    with Path(a.salida).open("w", encoding="utf-8") as fh:
        for i in range(0, len(filas), 10):
            with ThreadPoolExecutor(max_workers=a.concurrencia) as ex:
                for r in ex.map(lambda f: analizar(f, lim), filas[i:i + 10]):
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                    res.append(r)
            fh.flush()
            print(f"    {min(i + 10, len(filas))}/{len(filas)}", flush=True)

    print("\n  ESTADO")
    for k, v in Counter(r["estado"] for r in res).most_common():
        print(f"    {k:24} {v:5}")

    con = [r for r in res if r.get("forma_dominante")]
    print(f"\n  fuentes con una forma repetida de ficha: {len(con)}/{len(res)}")
    print(f"  urls en esas formas: "
          f"{sum(r.get('urls_en_la_forma') or 0 for r in con):,}")

    print("\n  FORMAS MAS FRECUENTES EN EL CORPUS")
    corpus: Counter = Counter()
    urls_por_forma: Counter = Counter()
    for r in res:
        for x in r.get("formas") or []:
            corpus[x["forma"]] += 1
            urls_por_forma[x["forma"]] += x["urls"]
    for k, v in corpus.most_common(15):
        print(f"    {k:44} {v:4} sitios  {urls_por_forma[k]:7,} urls")

    print("\n  ejemplos de las tres formas mas comunes:")
    for forma, _ in corpus.most_common(3):
        ej = next((r["ejemplos"] for r in res
                   if r.get("forma_dominante") == forma and r.get("ejemplos")), [])
        print(f"    {forma}")
        for e in ej[:2]:
            print(f"       {e[:96]}")

    print(f"\n  artefacto -> {a.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
