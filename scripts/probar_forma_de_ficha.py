#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""¿A cuántas agencias las destraba una FORMA declarada, sin tocar código? §3.

No escribe en la base ni en el padrón. `database_writes: 0`. No aplica nada.

`_es_ficha_url()` acepta una forma verificada por fuente —`patron_ficha`— que
viene del directorio de plataformas, o sea de **datos**. El vocabulario es
chico y está en `FORMA_A_REGEX`: `<num>`, `<slug>`, `<slug-con-id>`, `<otro>`.

Eso importa porque una agencia que hoy enumera 0 puede no necesitar un conector
nuevo: puede necesitar una línea de datos. Y una línea de datos **no cambia
ninguna huella**, así que no invalida una sola certificación.

Este script baja el catálogo de cada agencia que enumera 0, prueba cada forma
del vocabulario, y dice cuántas fichas entrarían con cada una. No elige: mide.

La comprobación incluye el contra-ejemplo: qué rutas institucionales
—`/contacto`, `/quienes-somos`— entrarían también. Una forma que arrastra la
página de contacto no sirve, por más fichas que recupere.

Uso:
    python scripts/probar_forma_de_ficha.py
    python scripts/probar_forma_de_ficha.py --agencia bottai
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from connectors.generico import (FORMA_A_REGEX, GenericoConnector,  # noqa: E402
                                 patron_de_forma)

CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
      "Accept-Encoding": "gzip", "Accept-Language": "es-AR,es;q=0.9"}

# Las formas que el vocabulario sabe traducir, de la más estricta a la más
# amplia. Se prueban en ese orden: si una estricta alcanza, no hay razón para
# habilitar una amplia.
FORMAS = ["/<slug-con-id>", "/<slug>", "/propiedades/<slug-con-id>",
          "/propiedad/<slug-con-id>", "/inmueble/<num>", "/propiedad/<num>",
          "/propiedades/<num>", "/ficha/<slug-con-id>"]

# Rutas que NINGUNA forma puede arrastrar. Si una forma las toma, se descarta.
INSTITUCIONALES = ("/contacto", "/quienes-somos", "/nosotros", "/empresa",
                   "/inicio", "/servicios", "/tasaciones", "/blog", "/novedades")

# Por dónde suele estar el catálogo, si la web registrada es la home.
CANDIDATAS = ("", "/inmuebles", "/propiedades", "/propiedades/", "/venta",
              "/ventas", "/listado", "/buscar")


def bajar(url: str, tope: int = 3_000_000) -> tuple[int, str]:
    r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=35)
    c = r.read(tope)
    if r.headers.get("Content-Encoding") == "gzip":
        try:
            c = gzip.decompress(c)
        except OSError:
            pass
    return r.status, c.decode("utf-8", "replace")


def catalogo_de(base: str, pausa: float) -> tuple[str, str] | None:
    """La página con más enlaces internos. No se adivina cuál es: se mide."""
    mejor, mejor_url, mejor_n = None, None, 0
    for sufijo in CANDIDATAS:
        url = base.rstrip("/") + sufijo
        try:
            st, h = bajar(url)
        except Exception:
            time.sleep(pausa)
            continue
        if st != 200 or len(h) < 2000:
            time.sleep(pausa)
            continue
        n = len(set(re.findall(r'href="([^"]{4,300})"', h)))
        if n > mejor_n:
            mejor, mejor_url, mejor_n = h, url, n
        time.sleep(pausa)
    return (mejor_url, mejor) if mejor else None


def probar(html: str, base_url: str) -> list[dict]:
    fuera = []
    for forma in FORMAS:
        p = patron_de_forma(forma)
        if p is None:
            continue
        urls = GenericoConnector._fichas_en(html, base_url, p)
        if not urls:
            continue
        rutas = [urllib.parse.urlparse(u).path for u in urls]
        arrastra = sorted({r for r in rutas
                           if any(r.rstrip("/").lower().endswith(i)
                                  for i in INSTITUCIONALES)})
        fuera.append({"forma": forma, "fichas": len(urls),
                      "arrastra_institucionales": arrastra,
                      "muestra": rutas[:3]})
    return sorted(fuera, key=lambda x: (-x["fichas"], len(x["forma"])))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agencia")
    ap.add_argument("--pausa", type=float, default=1.2)
    ap.add_argument("--tope", type=int, default=14)
    args = ap.parse_args()

    ult = {}
    for l in (CERT / "AGENCY_CERTIFICATION_RESULTS.jsonl").read_text(
            encoding="utf-8", errors="replace").splitlines():
        if not l.strip():
            continue
        try:
            r = json.loads(l)
        except ValueError:
            continue
        if r.get("canonical_agency_id"):
            ult[r["canonical_agency_id"]] = r

    # Las que enumeran CERO teniendo web propia: las candidatas a que les falte
    # una forma, no un conector.
    cero = []
    for a, r in ult.items():
        if args.agencia and not any(x.strip() and x.strip() in a
                                    for x in args.agencia.split(",")):
            continue
        ea = r.get("enumeration_audit") or {}
        if (ea.get("enumerated") or 0) > 0:
            continue
        url = r.get("official_url") or ""
        if not url.startswith("http"):
            continue
        cero.append((a, url, r.get("connector_strategy")))
    cero.sort()
    print(f"agencias que enumeran 0 con web propia: {len(cero)}"
          f"  (se prueban {min(args.tope, len(cero))})\n")

    resultados = []
    for a, url, est in cero[:args.tope]:
        nombre = a.split(":")[-1][:26]
        try:
            cat = catalogo_de(url, args.pausa)
        except Exception as e:
            print(f"{nombre:28} no se pudo: {type(e).__name__}")
            continue
        if not cat:
            print(f"{nombre:28} sin catalogo legible")
            resultados.append({"agencia": a, "resultado": "SIN_CATALOGO_LEGIBLE"})
            continue
        cat_url, html = cat
        opciones = probar(html, cat_url)
        limpias = [o for o in opciones if not o["arrastra_institucionales"]]
        if limpias:
            mejor = limpias[0]
            print(f"{nombre:28} {mejor['fichas']:4} fichas con {mejor['forma']:24} "
                  f"<- {cat_url[-40:]}")
            resultados.append({"agencia": a, "url_catalogo": cat_url,
                               "resultado": "FORMA_SIRVE", **mejor,
                               "estrategia_actual": est})
        else:
            sucio = opciones[0] if opciones else None
            print(f"{nombre:28} ninguna forma limpia"
                  + (f" (la mejor arrastra {sucio['arrastra_institucionales'][:2]})"
                     if sucio else ""))
            resultados.append({"agencia": a, "url_catalogo": cat_url,
                               "resultado": "NINGUNA_FORMA_LIMPIA",
                               "opciones": opciones})

    sirven = [r for r in resultados if r.get("resultado") == "FORMA_SIRVE"]
    total = sum(r["fichas"] for r in sirven)
    print(f"\n{'='*70}")
    print(f"agencias que una FORMA DECLARADA destraba: {len(sirven)}")
    print(f"fichas que entrarian en total:             {total:,}")
    print(f"{'='*70}")
    print("\n  Esto es un DATA_FIX: `patron_ficha` sale del directorio de")
    print("  plataformas, no del codigo. NO cambia ninguna huella y por eso")
    print("  no invalida una sola certificacion.")
    print("\n  Lo que NO prueba: que cada url enumerada sea una propiedad")
    print("  publicable. Entra con `por_forma=True` y el guardian de detalle")
    print("  la valida una por una. Hay que medirlo antes de prometer el total.")

    salida = CERT / "ERETZ_FORMAS_DE_FICHA.jsonl"
    salida.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                              for r in resultados), encoding="utf-8")
    print(f"\nartefacto: {salida}")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
