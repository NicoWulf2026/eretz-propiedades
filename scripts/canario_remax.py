#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Canario del sitemap de RE/MAX. §16–§20.

No escribe en la base. `database_writes: 0`. No implementa la estrategia: mide
si vale la pena escribirla.

El sondeo previo contó oficinas. Esto cuenta lo que el §17 pide por nombre, que
es otra cosa: no cuántas oficinas aparecen, sino **cuántas fichas servirían
para publicar**. Una ficha puede ser legible y no tener precio; puede tener
precio y pertenecer a una oficina de Uruguay; puede estar atribuida a una
oficina que no está en nuestro padrón, y entonces no es inventario nuestro.

Las ocho métricas se cuentan sobre la MISMA muestra, así que se pueden
componer: `LISTING_VALID` ∧ `OFFICE_ATTRIBUTION_MATCH_PADRON` ∧
`PROPERTY_FIELDS_AVAILABLE` es la fracción realmente aprovechable, y es la
única que autoriza a escribir una estrategia.

Se separa `FOREIGN_COUNTRY` porque RE/MAX publica Uruguay y Paraguay en el
mismo dominio. Contarlas como inventario argentino inflaría el número que
decide si esto se construye.

Uso:
    python scripts/canario_remax.py --muestra 300
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

import verificador_identidad_v2 as v2  # noqa: E402
from sondeo_remax_sitemap import (RAIZ_SITEMAP, UA, nuestras_remax,  # noqa: E402
                                  objeto_json, traer)

# `traer` manda `Accept-Encoding` pero no `Accept`. Sin `Accept`, remax.com.ar
# devuelve HTTP 202 con CERO bytes; con `Accept` devuelve 202 con el desafio de
# AWS WAF. Ninguna de las dos es la ficha, pero la diferencia importa: sin esta
# cabecera el cuerpo vacio se lee como "la ficha no tiene datos", que es una
# afirmacion sobre RE/MAX cuando en realidad es una sobre nuestro cliente HTTP.
UA_NAVEGADOR = dict(UA, **{
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none", "Upgrade-Insecure-Requests": "1"})

# El desafio de AWS WAF. NO se resuelve: se cuenta y se informa.
DESAFIO = re.compile(r"(?i)awswaf|gokuProps|challenge\.js")

CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
SALIDA = CERT / "ERETZ_REMAX_CANARIO.jsonl"

# Los países que RE/MAX publica en el mismo dominio. No son inventario nuestro.
EXTRANJERO = re.compile(r"(?i)/(uruguay|paraguay|chile|bolivia|peru)[/-]"
                        r"|\b(montevideo|punta del este|asuncion|maldonado)\b")
PRECIO = re.compile(r"(?i)\"price\"\s*:\s*\"?(\d{3,})")
MONEDA = re.compile(r"(?i)\"currency\"\s*:\s*\"([A-Z]{3})\"")


def bajar(url: str, timeout: float = 30) -> str:
    """Como `traer`, pero con la cabecera `Accept` que el sitio exige."""
    import gzip
    import urllib.request
    r = urllib.request.urlopen(
        urllib.request.Request(url, headers=UA_NAVEGADOR), timeout=timeout)
    crudo = r.read(600_000)
    if r.headers.get("Content-Encoding") == "gzip":
        try:
            crudo = gzip.decompress(crudo)
        except OSError:
            pass
    return crudo.decode("utf-8", "replace")


def campos_de_propiedad(html: str) -> dict:
    """Los cuatro que hacen publicable a una ficha: precio, moneda, operación,
    superficie. Sin precio no se puede publicar; sin los otros tres se puede,
    pero mal."""
    precio = PRECIO.search(html)
    moneda = MONEDA.search(html)
    return {
        "precio": bool(precio),
        "moneda": moneda.group(1) if moneda else None,
        "operacion": bool(re.search(r"(?i)\"(operation|transactionType)\"\s*:", html)),
        "superficie": bool(re.search(r"(?i)\"(dimension|totalSurface|m2)\w*\"\s*:", html)),
        "ambientes": bool(re.search(r"(?i)\"(bedrooms|rooms)\"\s*:", html)),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--muestra", type=int, default=300)
    ap.add_argument("--pausa", type=float, default=1.0)
    ap.add_argument("--semilla", type=int, default=11)
    args = ap.parse_args()
    if not 200 <= args.muestra <= 500:
        print("el §16 pide entre 200 y 500 fichas")
        return 1

    indice = traer(RAIZ_SITEMAP, 2_000_000)
    sitemaps = [u for u in re.findall(r"<loc>([^<]+)</loc>", indice)
                if re.search(r"sitemap[1-9]\d*\.xml$", u)]
    urls: list[str] = []
    for s in sitemaps:
        try:
            urls += re.findall(r"<loc>([^<]+)</loc>", traer(s))
        except Exception as e:
            print(f"  {s.split('/')[-1]}: {type(e).__name__}")
        time.sleep(args.pausa)

    nuestras = nuestras_remax()
    print("### CANARIO RE/MAX ###")
    print(f"  sub-sitemaps:             {len(sitemaps)}")
    print(f"  fichas publicadas:        {len(urls):,}")
    print(f"  oficinas RE/MAX nuestras: {len(nuestras)}\n")

    random.seed(args.semilla)
    muestra = random.sample(urls, min(args.muestra, len(urls)))

    m: Counter = Counter()
    vistas: set[str] = set()
    monedas: Counter = Counter()
    oficinas: Counter = Counter()
    huerfanas: Counter = Counter()
    filas = []

    for i, u in enumerate(muestra, 1):
        fila = {"url": u}
        try:
            html = bajar(u)
        except Exception as e:
            fila["resultado"] = f"NO_HTTP_READABLE:{type(e).__name__}"
            m["ERROR_DE_RED"] += 1
            filas.append(fila)
            time.sleep(args.pausa)
            continue

        # HTTP_READABLE es "sirvio la ficha", no "no tiro excepcion". Sin esta
        # distincion, 300 cuerpos vacios se cuentan como 300 fichas legibles
        # sin un solo dato, y eso se lee como un defecto de RE/MAX cuando es
        # un bloqueo contra nosotros.
        fila["bytes"] = len(html)
        if not html.strip():
            m["ANTIBOT_CUERPO_VACIO"] += 1
            fila["resultado"] = "ANTIBOT_CUERPO_VACIO"
            filas.append(fila)
            time.sleep(args.pausa)
            continue
        if DESAFIO.search(html[:4000]):
            m["ANTIBOT_DESAFIO_WAF"] += 1
            fila["resultado"] = "ANTIBOT_DESAFIO_WAF"
            filas.append(fila)
            time.sleep(args.pausa)
            continue
        m["HTTP_READABLE"] += 1

        # LISTING_VALID: es una ficha de propiedad, no un indice ni un 404 con
        # codigo 200. Se exige el objeto de la ficha, no solo que cargue.
        valida = bool(re.search(r'(?i)"@type"\s*:\s*"(Residence|Product|Offer|'
                                r'RealEstateListing|Place)"', html)
                      or re.search(r'(?i)"listing(Id|Key)"\s*:', html)
                      or PRECIO.search(html))
        fila["listing_valid"] = valida
        if valida:
            m["LISTING_VALID"] += 1

        # DUPLICATE: la misma ficha publicada bajo dos urls del sitemap.
        clave = re.sub(r"(?i)[^a-z0-9]+", "", u.rsplit("/", 1)[-1])[-24:]
        if clave and clave in vistas:
            m["DUPLICATE"] += 1
            fila["duplicada"] = True
        vistas.add(clave)

        # FOREIGN_COUNTRY
        extranjera = bool(EXTRANJERO.search(u) or EXTRANJERO.search(html[:20000]))
        if extranjera:
            m["FOREIGN_COUNTRY"] += 1
        fila["extranjera"] = extranjera

        # OFFICE_ATTRIBUTION_*
        d = objeto_json(html)
        if d and (d.get("name") or "").strip():
            m["OFFICE_ATTRIBUTION_PRESENT"] += 1
            nombre = d["name"].strip()
            clave_of = v2._normalizar(nombre).replace("re max", "remax")
            oficinas[clave_of] += 1
            fila["oficina"] = nombre
            if clave_of in nuestras:
                m["OFFICE_ATTRIBUTION_MATCH_PADRON"] += 1
                fila["en_padron"] = True
            else:
                huerfanas[clave_of] += 1
                fila["en_padron"] = False
        else:
            m["UNATTRIBUTED"] += 1
            fila["oficina"] = None

        # PROPERTY_FIELDS_AVAILABLE: el precio es el que decide.
        campos = campos_de_propiedad(html)
        fila["campos"] = campos
        if campos["precio"]:
            m["PROPERTY_FIELDS_AVAILABLE"] += 1
            if campos["moneda"]:
                monedas[campos["moneda"]] += 1

        # La composicion, que es la unica que autoriza a construir.
        if (valida and fila.get("en_padron") and campos["precio"]
                and not extranjera and not fila.get("duplicada")):
            m["APROVECHABLE"] += 1
            fila["aprovechable"] = True

        filas.append(fila)
        time.sleep(args.pausa)
        if i % 25 == 0:
            print(f"  {i}/{len(muestra)}  aprovechables: {m['APROVECHABLE']}",
                  flush=True)

    n = len(muestra)
    SALIDA.write_text(
        "".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas),
        encoding="utf-8")

    print(f"\n=== RUBRICA §17 — muestra de {n} fichas ===")
    for k in ("ERROR_DE_RED", "ANTIBOT_CUERPO_VACIO", "ANTIBOT_DESAFIO_WAF",
              "HTTP_READABLE", "LISTING_VALID", "OFFICE_ATTRIBUTION_PRESENT",
              "OFFICE_ATTRIBUTION_MATCH_PADRON", "UNATTRIBUTED",
              "FOREIGN_COUNTRY", "DUPLICATE", "PROPERTY_FIELDS_AVAILABLE"):
        print(f"  {k:34} {m[k]:5}  {m[k]/n:6.1%}")
    print(f"\n  {'APROVECHABLE (las cinco juntas)':34} {m['APROVECHABLE']:5}"
          f"  {m['APROVECHABLE']/n:6.1%}")

    print(f"\n  oficinas distintas vistas:     {len(oficinas)}")
    print(f"  de esas, en nuestro padron:    {sum(1 for k in oficinas if k in nuestras)}")
    print(f"  oficinas fuera del padron:     {len(huerfanas)}")
    for k, c in huerfanas.most_common(8):
        print(f"     {k[:40]:42} {c} fichas")
    if monedas:
        print("\n  monedas:", dict(monedas.most_common()))

    proyectado = int(len(urls) * m["APROVECHABLE"] / n) if n else 0
    print(f"\n  PROYECCION sobre las {len(urls):,} fichas del sitemap:")
    print(f"     aprovechables ~{proyectado:,}")
    print(f"     el error de una muestra de {n} sobre {len(urls):,} es de unos")
    print(f"     ±{int(len(urls) * (0.98 / n ** 0.5)):,} fichas, asi que el numero")
    print("     sirve para decidir si se construye, no para prometer un total.")
    print(f"\nartefacto: {SALIDA}")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
