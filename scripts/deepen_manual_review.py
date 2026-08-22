#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Segunda pagina para las fuentes que quedaron en MANUAL_REVIEW.

Casi todas responden 200 y son sitios reales: lo unico que pasa es que la home
no muestra inventario, porque lo tiene una capa mas adentro. Mirar esa unica
pagina alcanza para decidir, y cuesta una peticion mas por sitio.

El limite es duro y deliberado: HOME + UNA pagina interna. No es un crawl. Los
candidatos salen de los links que la propia home muestra, no de rutas
adivinadas, asi que no se golpea nada que el sitio no haya ofrecido.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import time
import urllib.parse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


aud = _load("audit_existing_webs")
dp = _load("detect_platform")

DEEPEN_VERSION = "manual_review_deepen_v1"

# Lo que se busca en el texto o el href de un link de la home, de mas a menos
# especifico. El orden es el de preferencia: una ruta de listado explicita
# gana sobre un "ver mas" generico.
CANDIDATOS = [
    (re.compile(r"/(propiedades|inmuebles|properties|listings)/?$", re.I), 100),
    (re.compile(r"/(propiedades|inmuebles|properties|listings|listado[s]?|"
                r"emprendimientos|desarrollos)\b", re.I), 90),
    (re.compile(r"/(venta[s]?|alquiler(es)?|comprar|alquilar)\b", re.I), 70),
    (re.compile(r"/(buscar|busqueda|search|resultados|catalogo|oportunidades)\b", re.I), 60),
    (re.compile(r"(propiedades|inmuebles|listado|emprendimientos)", re.I), 40),
]

# Links que nunca son inventario.
DESCARTAR = re.compile(
    r"(mailto:|tel:|javascript:|\.(jpg|jpeg|png|gif|svg|pdf|zip|mp4|css|js)($|\?)|"
    r"/(contacto|contact|nosotros|about|quienes|blog|noticias|novedades|tasacion|"
    r"servicios|login|admin|wp-admin|privacidad|terminos|carrito|cart)\b|"
    r"facebook\.com|instagram\.com|wa\.me|whatsapp|linkedin\.com|youtube\.com)", re.I)


def links_de(html: str, base: str) -> list[tuple[int, str]]:
    """Links internos que la home ofrece, puntuados por cuanto prometen."""
    host = urllib.parse.urlparse(base).netloc.lower().replace("www.", "")
    vistos: set[str] = set()
    salida: list[tuple[int, str]] = []
    for m in re.finditer(r'<a\b[^>]*href=["\']([^"\']{1,300})["\']([^>]*)>(.{0,120}?)</a>',
                         html or "", re.I | re.S):
        href, _, texto = m.group(1), m.group(2), m.group(3)
        if DESCARTAR.search(href):
            continue
        absoluta = urllib.parse.urljoin(base, href)
        if not absoluta.startswith("http"):
            continue
        neto = urllib.parse.urlparse(absoluta).netloc.lower().replace("www.", "")
        if neto != host:
            continue
        clave = absoluta.split("#")[0].rstrip("/").lower()
        if clave in vistos or clave.rstrip("/") == base.rstrip("/").lower():
            continue
        vistos.add(clave)
        limpio = re.sub(r"<[^>]+>", " ", texto)
        for patron, peso in CANDIDATOS:
            if patron.search(absoluta) or patron.search(limpio):
                salida.append((peso, absoluta))
                break
    salida.sort(key=lambda x: -x[0])
    return salida


def procesar(fuente: dict) -> dict:
    url = fuente["official_url"]
    base = {
        "canonical_agency_id": fuente["canonical_agency_id"],
        "agency_name": fuente.get("agency_name"),
        "official_url": url,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "deepen_version": DEEPEN_VERSION,
    }
    home = aud.bajar(url)
    http = home.get("http")
    if http != 200:
        estado = ("BLOCKED" if http in (401, 403, 429)
                  else "INACTIVE" if http in (404, 410)
                  else "ERROR")
        return {**base, "second_page": None, "new_status": estado,
                "strategy": None, "evidence": {"motivo": f"la home devolvio {http}"}}

    candidatos = links_de(home.get("html") or "", home.get("url") or url)
    if not candidatos:
        return {**base, "second_page": None, "new_status": "NO_LISTINGS",
                "strategy": None, "candidatos_vistos": 0,
                "evidence": {"motivo": "la home no ofrece ningun link que parezca inventario"}}

    peso, segunda = candidatos[0]
    pagina = aud.bajar(segunda)
    ev = {"motivo": "", "peso_del_link": peso, "http_segunda": pagina.get("http"),
          "titulo_segunda": (pagina.get("titulo") or "")[:120],
          "candidatos_vistos": len(candidatos),
          "otros_candidatos": [u for _, u in candidatos[1:4]]}

    if pagina.get("http") != 200:
        ev["motivo"] = f"la pagina interna devolvio {pagina.get('http')}"
        return {**base, "second_page": segunda, "new_status": "MANUAL_REVIEW",
                "strategy": None, "evidence": ev}

    # La decision se toma sobre home + segunda pagina juntas, con el MISMO
    # detector que se uso en las 1.992: no hay criterio paralelo.
    combinado = {
        "html": (home.get("html") or "") + " " + (pagina.get("html") or ""),
        "texto": (home.get("texto") or "") + " " + (pagina.get("texto") or ""),
        "titulo": pagina.get("titulo") or home.get("titulo") or "",
        "http": 200,
        "url": pagina.get("url") or segunda,
    }
    clasif = dp.clasificar(combinado, fuente.get("sitemap", False))

    if dp.requiere_js(combinado, clasif["detected_platform"]):
        estado = "REQUIRES_JS"
        ev["motivo"] = "la pagina interna tampoco trae inventario servido"
    elif clasif["has_listings"] or clasif["detected_api"] or clasif["json_embedded"]:
        estado = "SCRAPE_SOURCE_READY"
        ev["motivo"] = f"inventario visible en {segunda}"
    else:
        estado = "NO_LISTINGS"
        ev["motivo"] = "ni la home ni la pagina interna muestran inventario"

    return {**base, "second_page": segunda, "new_status": estado,
            "strategy": clasif["strategy"] if estado == "SCRAPE_SOURCE_READY" else None,
            "evidence": ev, **{k: clasif[k] for k in
                               ("detected_platform", "detected_framework", "detected_api",
                                "json_embedded", "requires_js", "has_listings",
                                "platform_confidence", "detector_version")}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--hilos", type=int, default=6)
    ap.add_argument("--limite", type=int, default=0)
    a = ap.parse_args()
    dd = Path(a.data_dir)

    mapa = [json.loads(l) for l in
            (dd / "scrape_source_technology_map.jsonl").open(encoding="utf-8") if l.strip()]
    pendientes = [x for x in mapa if x["strategy"] == "MANUAL_REVIEW"]
    if a.limite:
        pendientes = pendientes[:a.limite]

    print("### SEGUNDA PAGINA PARA MANUAL_REVIEW ###", flush=True)
    print(f"  fuentes en MANUAL_REVIEW: {len(pendientes):,}", flush=True)
    print(f"  profundidad maxima: home + 1 pagina interna\n", flush=True)

    salida = dd / "manual_review_deepened.jsonl"
    filas = []
    with salida.open("w", encoding="utf-8") as fh:
        for i in range(0, len(pendientes), 30):
            with ThreadPoolExecutor(max_workers=a.hilos) as ex:
                for r in ex.map(procesar, pendientes[i:i + 30]):
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                    filas.append(r)
            fh.flush()
            print(f"    {min(i + 30, len(pendientes))}/{len(pendientes)}", flush=True)
            time.sleep(0.2)

    print(f"\n### RESULTADO ###", flush=True)
    for k, v in Counter(r["new_status"] for r in filas).most_common():
        print(f"    {k:24} {v:5,}  ({v/max(len(filas),1)*100:5.1f}%)", flush=True)
    rec = [r for r in filas if r["new_status"] == "SCRAPE_SOURCE_READY"]
    print(f"\n  RECUPERADAS a READY: {len(rec):,} de {len(filas):,}", flush=True)
    if rec:
        print(f"  estrategia de las recuperadas:", flush=True)
        for k, v in Counter(r["strategy"] for r in rec).most_common():
            print(f"    {k:20} {v:5,}", flush=True)
    print(f"\n  artefacto -> manual_review_deepened.jsonl", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
