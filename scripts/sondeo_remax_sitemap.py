#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""¿Cuántas de nuestras 190 oficinas de RE/MAX cubre el sitemap de la red?

No escribe en la base. `database_writes: 0`. No implementa nada: mide.

El hallazgo del 2026-09-15 dice que RE/MAX Argentina publica ~80.000 fichas en
`sitemap1..4.xml`, que cada ficha sirve HTML legible, y que cada una trae
embebido el objeto de su oficina con id estable. Si eso cubre a nuestras 190
agencias, son 62.521 avisos —el 40 % del inventario del país— por una sola
estrategia nueva.

Pero "cubre" hay que medirlo antes de prometerlo. Este script recorre una
muestra del sitemap, extrae la oficina de cada ficha, y la compara contra el
padrón. Lo que devuelve es una **estimación con su tamaño de muestra**, no una
promesa.

Uso:
    python scripts/sondeo_remax_sitemap.py --muestra 200
"""
from __future__ import annotations

import argparse
import gzip
import json
import random
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

import verificador_identidad_v2 as v2  # noqa: E402

DATOS = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
SALIDA = CERT / "ERETZ_REMAX_SITEMAP_SONDEO.jsonl"

RAIZ_SITEMAP = "https://www.remax.com.ar/sitemap.xml"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept-Encoding": "gzip", "Accept-Language": "es-AR,es;q=0.9"}


def traer(url: str, tope: int = 8_000_000, timeout: float = 35) -> str:
    r = urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                               timeout=timeout)
    crudo = r.read(tope)
    if r.headers.get("Content-Encoding") == "gzip":
        try:
            crudo = gzip.decompress(crudo)
        except OSError:
            pass
    return crudo.decode("utf-8", "replace")


def objeto_json(html: str, clave: str = '"office":') -> dict | None:
    """El objeto que sigue a la clave, contando llaves.

    Una expresion regular no sirve: el objeto tiene anidados y `.*?}` corta en
    el primero. Con ocho fichas de prueba eso daba cero oficinas.
    """
    i = html.find(clave)
    while i >= 0:
        j = html.find("{", i)
        if j < 0:
            return None
        prof = 0
        for k in range(j, min(len(html), j + 6000)):
            if html[k] == "{":
                prof += 1
            elif html[k] == "}":
                prof -= 1
                if prof == 0:
                    try:
                        d = json.loads(html[j:k + 1])
                    except ValueError:
                        break
                    if d.get("name"):
                        return d
                    break
        i = html.find(clave, i + 1)
    return None


def nuestras_remax() -> dict[str, dict]:
    """Las oficinas de RE/MAX del padron, por nombre normalizado."""
    fuera: dict[str, dict] = {}
    ruta = DATOS / "roomix_agency_directory.jsonl"
    for linea in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
        if not linea.strip():
            continue
        f = json.loads(linea)
        nombre = f.get("nombre_original") or ""
        if not re.search(r"(?i)re/?\s?max", nombre):
            continue
        fuera[v2._normalizar(nombre).replace("re max", "remax")] = f
    return fuera


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--muestra", type=int, default=150)
    ap.add_argument("--pausa", type=float, default=1.0)
    args = ap.parse_args()

    indice = traer(RAIZ_SITEMAP, 2_000_000)
    sitemaps = [u for u in re.findall(r"<loc>([^<]+)</loc>", indice)
                if re.search(r"sitemap[1-9]\d*\.xml$", u)]
    print("### SONDEO DEL SITEMAP DE RE/MAX ###")
    print(f"  sub-sitemaps de listings: {len(sitemaps)}")

    urls: list[str] = []
    for s in sitemaps:
        try:
            urls += re.findall(r"<loc>([^<]+)</loc>", traer(s))
        except Exception as e:
            print(f"  {s.split('/')[-1]}: {type(e).__name__}")
        time.sleep(args.pausa)
    print(f"  fichas publicadas:        {len(urls):,}")

    nuestras = nuestras_remax()
    print(f"  oficinas RE/MAX nuestras: {len(nuestras)}\n")

    random.seed(11)
    muestra = random.sample(urls, min(args.muestra, len(urls)))
    oficinas: Counter = Counter()
    detalle: dict[str, dict] = {}
    sin_oficina = ilegibles = 0

    for i, u in enumerate(muestra, 1):
        try:
            html = traer(u, 600_000, 30)
        except Exception:
            ilegibles += 1
            time.sleep(args.pausa)
            continue
        d = objeto_json(html)
        if not d:
            sin_oficina += 1
        else:
            clave = v2._normalizar(d.get("name") or "").replace("re max", "remax")
            oficinas[clave] += 1
            detalle.setdefault(clave, {
                "name": d.get("name"), "slug": d.get("slug"),
                "web": (d.get("description") or "").strip()[:80],
                "id": d.get("id")})
        time.sleep(args.pausa)
        if i % 25 == 0:
            print(f"  {i}/{len(muestra)}  oficinas distintas: {len(oficinas)}",
                  flush=True)

    leidas = len(muestra) - ilegibles
    coinciden = {k for k in oficinas if k in nuestras}
    con_web = sum(1 for k in coinciden if detalle[k]["web"])

    with SALIDA.open("w", encoding="utf-8") as fh:
        for k, n in oficinas.most_common():
            fh.write(json.dumps({
                "oficina_normalizada": k, **detalle[k], "fichas_en_la_muestra": n,
                "esta_en_nuestro_padron": k in nuestras,
            }, ensure_ascii=False) + "\n")

    print("\n=== RESULTADO ===")
    print(f"  fichas de la muestra:        {len(muestra)}")
    print(f"  ilegibles:                   {ilegibles}")
    print(f"  sin objeto de oficina:       {sin_oficina}")
    print(f"  con oficina identificada:    {leidas - sin_oficina}"
          f"  ({(leidas - sin_oficina) / max(leidas, 1):.0%} de las leidas)")
    print(f"  oficinas DISTINTAS vistas:   {len(oficinas)}")
    print(f"  de esas, en nuestro padron:  {len(coinciden)}")
    print(f"  con dominio propio en el payload: {con_web}")
    if oficinas:
        print("\n  las mas frecuentes en la muestra:")
        for k, n in oficinas.most_common(8):
            marca = "SI" if k in nuestras else "no"
            print(f"     {detalle[k]['name'][:26]:28} {n:4} fichas  padron={marca}"
                  f"  {detalle[k]['web'][:28]}")
    print(f"\n  NOTA: con {len(muestra)} fichas sobre {len(urls):,} publicadas, "
          f"esto estima cobertura, no la demuestra.")
    print(f"  artefacto: {SALIDA}")
    print("database_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
