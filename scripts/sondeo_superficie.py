#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""¿Estamos enumerando el catalogo, o una vitrina que rota?

No escribe nada y no toca el conector. `database_writes: 0`.

Lo motiva `blangiforti`: su home y su /propiedades muestran una SELECCION
ROTATIVA de ~24 fichas -dos pedidos separados por segundos comparten 6- mientras
el catalogo real vive en /ventas, con 180 estables. Enumerabamos el 22 %, y un
22 % distinto cada vez.

Lo que hace peligroso al defecto es que se disfraza de exito. Si la rotacion
hubiera sido estable entre las dos corridas, el certificador habria dicho
CERTIFIED_COMPLETE sobre una quinta parte del inventario y nadie se habria
enterado. Por eso el chequeo no puede apoyarse en produccion como vara:
produccion se construyo con el mismo sesgo. Las 44 filas productivas de
blangiforti son la misma vitrina.

Dos preguntas por agencia, las dos contra la fuente:

    ROTA     pedir la misma pagina dos veces, ¿da el mismo conjunto de fichas?
    MAS      ¿algun listado por operacion ofrece bastante mas que la home?

Uso:
    python scripts/sondeo_superficie.py --estrategia generic/html_catalog
    python scripts/sondeo_superficie.py --web https://blangiforti.com.ar
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlsplit

RESULTADOS = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827"
                  r"\AGENCY_CERTIFICATION_RESULTS.jsonl")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept-Encoding": "gzip"}
LISTADOS = ("/ventas", "/venta", "/alquileres", "/alquiler", "/propiedades",
            "/inmuebles")
CORTESIA = 1.5
# Con menos de esto no hay muestra: dos fichas distintas no prueban rotacion.
MINIMO_PARA_OPINAR = 6


def traer(url: str, timeout: float = 30) -> str | None:
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                   timeout=timeout)
        crudo = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            crudo = gzip.decompress(crudo)
        return crudo.decode("utf-8", "replace")
    except Exception:
        return None


def fichas(html: str | None, base: str) -> set[str]:
    """Enlaces internos que parecen fichas: los que comparten el prefijo mas
    poblado. No se asume una forma de url; se deduce de la pagina."""
    if not html:
        return set()
    host = urlsplit(base).netloc.lower().removeprefix("www.")
    rutas = []
    for e in re.findall(r'href="([^"]+)"', html):
        u = urljoin(base, e).split("#")[0].split("?")[0]
        p = urlsplit(u)
        if p.netloc.lower().removeprefix("www.") != host:
            continue
        ruta = re.sub(r"/+", "/", p.path).rstrip("/")
        if not ruta or re.search(r"\.(css|js|png|jpe?g|svg|ico|webp|pdf)$", ruta):
            continue
        rutas.append(ruta)
    if not rutas:
        return set()
    conteo: dict[str, set[str]] = {}
    for ruta in rutas:
        partes = ruta.strip("/").split("/")
        prefijo = "/" + partes[0] if len(partes) > 1 else "/"
        conteo.setdefault(prefijo, set()).add(ruta)
    mejor = max(conteo.values(), key=len)
    return mejor if len(mejor) >= 3 else set()


def sondear(web: str) -> dict:
    base = web.rstrip("/")
    a = fichas(traer(base + "/"), base)
    time.sleep(CORTESIA)
    b = fichas(traer(base + "/"), base)

    rota = None
    if len(a) >= MINIMO_PARA_OPINAR and len(b) >= MINIMO_PARA_OPINAR:
        comunes = len(a & b)
        rota = round(1 - comunes / max(len(a), len(b)), 3)

    mejor_ruta, mejor_n = None, len(a)
    for ruta in LISTADOS:
        time.sleep(CORTESIA)
        n = len(fichas(traer(base + ruta), base))
        if n > mejor_n:
            mejor_ruta, mejor_n = ruta, n
    return {"web": base, "home": len(a), "rota": rota,
            "mejor_ruta": mejor_ruta, "mejor": mejor_n}


def agencias(estrategia: str) -> list[tuple[str, str, int, str]]:
    ultimo: dict[str, dict] = {}
    for linea in RESULTADOS.read_text(encoding="utf-8", errors="replace").splitlines():
        if not linea.strip():
            continue
        try:
            r = json.loads(linea)
        except ValueError:
            continue
        if r.get("canonical_agency_id"):
            ultimo[r["canonical_agency_id"]] = r
    fuera = []
    for a, r in ultimo.items():
        if r.get("connector_strategy") != estrategia or not r.get("official_url"):
            continue
        enumeradas = (r.get("enumeration_audit") or {}).get("enumerated") or 0
        fuera.append((a, r["official_url"], enumeradas, r.get("status") or ""))
    return sorted(fuera, key=lambda x: -x[2])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--estrategia", default="generic/html_catalog")
    ap.add_argument("--web")
    ap.add_argument("--solo-certificadas", action="store_true")
    args = ap.parse_args()

    if args.web:
        print(json.dumps(sondear(args.web), ensure_ascii=False, indent=1))
        return 0

    objetivos = agencias(args.estrategia)
    if args.solo_certificadas:
        objetivos = [o for o in objetivos if o[3].startswith("CERTIFIED")]
    print(f"{len(objetivos)} agencias en {args.estrategia}\n")
    print(f"{'agencia':34} {'enum':>5} {'home':>5} {'rota':>6} "
          f"{'mejor':>6} ruta")
    sospechosas = []
    for a, web, enumeradas, _ in objetivos:
        r = sondear(web)
        marca = ""
        # Rotar no basta: hace falta que lo enumerado se parezca a la vitrina.
        # Si enumeramos bastante mas que lo que la vitrina muestra, el conector
        # llego a un listado mas profundo y la rotacion no nos quita nada.
        rota = r["rota"] is not None and r["rota"] >= 0.3
        atrapados = enumeradas and r["home"] and enumeradas <= r["home"] * 2
        if rota and atrapados:
            marca = "  <-- VITRINA"
        elif enumeradas and r["mejor"] > enumeradas * 1.3:
            marca = "  <-- HAY MAS"
        elif rota:
            marca = "  (rota, pero enumeramos mas hondo)"
        if marca:
            sospechosas.append((a, r, enumeradas, marca.strip()))
        print(f"{a.split(':')[-1][:32]:34} {enumeradas:5} {r['home']:5} "
              f"{'-' if r['rota'] is None else format(r['rota'], '.2f'):>6} "
              f"{r['mejor']:6} {r['mejor_ruta'] or ''}{marca}")

    print(f"\nsospechosas: {len(sospechosas)}")
    for a, r, enumeradas, marca in sospechosas:
        print(f"   {a.split(':')[-1][:36]:38} {marca:10} "
              f"enum={enumeradas} mejor={r['mejor']} {r['mejor_ruta'] or ''}")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
