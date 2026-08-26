#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Decidir si una forma de url de RAIZ es una ficha o una pagina editorial.

95 fuentes publican en la raiz -/casa-en-venta-en-el-yacht-ficha-amn3894,
/p-1749_departamento-interno-de-2-dormitorios- y quedaron deliberadamente
afuera: aflojar el patron de raiz para que las tome haria entrar tambien
/propiedades-en-venta-2026, /2026-balance-anual y cualquier nota con un ano en
el slug. Un slug con palabra de inmueble y cuatro digitos describe las dos cosas.

La forma de la url no alcanza. Lo que decide es lo que hay ADENTRO de la pagina:
una ficha publica un precio con moneda, una operacion, fotos y casi siempre
datos estructurados; una nota no. Asi que se bajan tres urls de esa forma por
sitio y se cuenta cuantas traen esa evidencia.

La decision es POR FUENTE, no global: se habilita la forma de ese sitio, no se
afloja el patron para los otros 2.258.

Baja tres paginas por sitio. Solo lee.
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

VERSION = "root_shapes_v1"

RE_PRECIO = re.compile(r"(USD|U\$S|US\$|\$|ARS)\s*[\d][\d.,]{2,}", re.I)
RE_OPERACION = re.compile(r"\b(en venta|en alquiler|venta|alquiler|se vende|se alquila)\b", re.I)
RE_ATRIBUTOS = re.compile(r"\b(dormitorio|ambiente|ba[nñ]o|superficie|m2|m²|cubierta|"
                          r"cochera|antig[uü]edad)\b", re.I)
RE_LD_TIPO = re.compile(r'"@type"\s*:\s*"?(RealEstateListing|Residence|House|'
                        r'Apartment|SingleFamilyResidence|Product|Offer|Place)', re.I)
RE_EDITORIAL = re.compile(r'"@type"\s*:\s*"?(Article|NewsArticle|BlogPosting)|'
                          r'property="og:type"\s+content="article"', re.I)
RE_IMG = re.compile(r'<img[^>]+src="[^"]+\.(?:jpe?g|png|webp)', re.I)


def _bajar(d: Descargador, url: str) -> str | None:
    try:
        return d.bajar(url)
    except (Bloqueado, ErrorPermanente, ErrorTransitorio):
        return None


def evidencia_de_ficha(html: str) -> dict:
    """Que trae la pagina que solo trae una ficha."""
    texto = re.sub(r"<[^>]+>", " ", html or "")
    return {
        "precio": bool(RE_PRECIO.search(texto)),
        "operacion": bool(RE_OPERACION.search(texto)),
        "atributos": len(set(RE_ATRIBUTOS.findall(texto.lower()))) >= 2,
        "datos_estructurados": bool(RE_LD_TIPO.search(html or "")),
        "editorial": bool(RE_EDITORIAL.search(html or "")),
        "fotos": len(RE_IMG.findall(html or "")),
    }


def es_ficha(ev: dict) -> bool:
    """Una ficha publica precio Y (operacion o atributos), y no se declara nota.

    Se exige el precio porque es lo unico que una nota sobre el mercado
    inmobiliario no suele traer con moneda al lado, y las notas SI hablan de
    venta, alquiler y dormitorios.
    """
    if ev["editorial"]:
        return False
    return ev["precio"] and (ev["operacion"] or ev["atributos"]) and ev["fotos"] >= 3


def analizar(f: dict, lim: LimitadorDeRitmo) -> dict:
    d = Descargador(lim, limite_bytes=900_000)
    base = f.get("domain") or ""
    p = urllib.parse.urlparse(base)
    raiz = f"{p.scheme or 'https'}://{p.netloc}"
    out = {"canonical_agency_id": f.get("canonical_agency_id"),
           "agency_name": f.get("agency_name"), "domain": base, "host": f.get("host"),
           "forma": f.get("forma_dominante"), "urls_vistas": f.get("urls_en_la_forma"),
           "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "verifier_version": VERSION}

    muestras = (f.get("ejemplos") or [])[:3]
    if not muestras:
        return {**out, "veredicto": "SIN_MUESTRA", "motivo": "no quedaron ejemplos"}

    detalle, fichas = [], 0
    for ruta in muestras:
        html = _bajar(d, urllib.parse.urljoin(raiz, ruta))
        if html is None:
            detalle.append({"ruta": ruta, "estado": "no bajo"})
            continue
        ev = evidencia_de_ficha(html)
        ok = es_ficha(ev)
        fichas += ok
        detalle.append({"ruta": ruta, "es_ficha": ok, **ev})
    out["muestras"] = detalle
    out["muestras_que_son_ficha"] = fichas

    leidas = sum(1 for x in detalle if "es_ficha" in x)
    if not leidas:
        out["veredicto"], out["motivo"] = "INACCESIBLE", "ninguna muestra respondio"
    elif fichas >= 2 or (leidas == 1 and fichas == 1):
        out["veredicto"] = "FORMA_DE_FICHA"
        out["motivo"] = (f"{fichas} de {leidas} muestras traen precio con moneda, "
                         f"operacion o atributos, y fotos")
        out["connector_candidato"] = "generico"
    elif any(x.get("editorial") for x in detalle):
        out["veredicto"], out["motivo"] = "EDITORIAL", "la pagina se declara nota o articulo"
    else:
        out["veredicto"] = "SIN_EVIDENCIA_DE_FICHA"
        out["motivo"] = f"solo {fichas} de {leidas} muestras parecen una propiedad"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", default=r"D:\INMO CAPITAL\RESIDUAL_SHAPES_FINAL.jsonl")
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\ROOT_SHAPES_VERIFIED.jsonl")
    ap.add_argument("--solo-sin-cubrir",
                    default=r"D:\INMO CAPITAL\RESIDUAL_UNCOVERED.jsonl")
    ap.add_argument("--concurrencia", type=int, default=4)
    ap.add_argument("--intervalo", type=float, default=1.5)
    a = ap.parse_args()

    filas = [json.loads(l) for l in Path(a.entrada).open(encoding="utf-8") if l.strip()]
    filas = [f for f in filas if f.get("estado_final") == "INVENTARIO_RECUPERABLE"]
    if a.solo_sin_cubrir and Path(a.solo_sin_cubrir).exists():
        pendientes = {json.loads(l)["canonical_agency_id"]
                      for l in Path(a.solo_sin_cubrir).open(encoding="utf-8") if l.strip()}
        filas = [f for f in filas if f["canonical_agency_id"] in pendientes]

    print("### FORMAS DE RAIZ: FICHA O NOTA ###")
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

    print("\n  VEREDICTO")
    for k, v in Counter(r["veredicto"] for r in res).most_common():
        u = sum(r.get("urls_vistas") or 0 for r in res if r["veredicto"] == k)
        print(f"    {k:24} {v:4} fuentes  {u:6,} urls vistas")
    ok = [r for r in res if r["veredicto"] == "FORMA_DE_FICHA"]
    print(f"\n  habilitables: {len(ok)} fuentes, "
          f"{sum(r.get('urls_vistas') or 0 for r in ok):,} urls")
    print("  por forma:")
    for k, v in Counter(r["forma"] for r in ok).most_common(8):
        print(f"    {k:32} {v:4}")
    print(f"\n  artefacto -> {a.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
