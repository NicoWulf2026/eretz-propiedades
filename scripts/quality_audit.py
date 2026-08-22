#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Auditoria de calidad sobre las propiedades ya ingeridas.

Solo lee artefactos. No pide nada a la red y no toca la base.

Se separan dos cosas que suelen confundirse:

  - COBERTURA: cuantas propiedades traen cada campo. Un campo vacio no es un
    error si la fuente no lo publica; es informacion sobre la fuente.
  - COHERENCIA: combinaciones que no pueden ser ciertas al mismo tiempo. Ahi si
    hay un problema, y es del parser o del dato de origen.

Los chequeos de coherencia son deliberadamente conservadores. Un caso raro pero
posible -un monoambiente con dos banos, un terreno sin superficie cubierta- no
se marca: preferimos no ensuciar el informe con ruido que nadie va a mirar dos
veces.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

CAMPOS = ("titulo", "descripcion", "precio", "moneda", "operacion",
          "tipo_propiedad", "direccion", "barrio", "ciudad", "provincia",
          "latitud", "longitud", "dormitorios", "banos", "ambientes",
          "superficie_total", "superficie_cubierta", "imagenes")


def leer(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    out = []
    for l in ruta.open(encoding="utf-8"):
        l = l.strip()
        if not l:
            continue
        try:
            out.append(json.loads(l))
        except ValueError:
            continue
    return out


def incoherencias(p: dict) -> list[str]:
    """Combinaciones imposibles. Cada una explica por que lo es."""
    r = []
    precio, moneda = p.get("precio"), p.get("moneda")
    if precio is not None and precio <= 0:
        r.append("precio_no_positivo")
    if precio is not None and not moneda:
        r.append("precio_sin_moneda")
    if moneda and moneda not in ("ARS", "USD"):
        r.append("moneda_fuera_de_vocabulario")

    st, sc = p.get("superficie_total"), p.get("superficie_cubierta")
    for nombre, v in (("superficie_total", st), ("superficie_cubierta", sc)):
        if v is not None and v <= 0:
            r.append(f"{nombre}_no_positiva")
    if st and sc and sc > st * 1.05:
        # Se tolera un 5%: hay fichas que cuentan balcones en la cubierta y no
        # en la total. Mas que eso ya no es criterio, es error.
        r.append("cubierta_mayor_que_total")

    dor, amb = p.get("dormitorios"), p.get("ambientes")
    if dor and amb and dor > amb:
        # Un ambiente incluye a los dormitorios: mas dormitorios que ambientes
        # es imposible en el modelo argentino.
        r.append("dormitorios_mayor_que_ambientes")

    lat, lon = p.get("latitud"), p.get("longitud")
    if lat is not None and not (-56 <= lat <= -21):
        r.append("latitud_fuera_de_argentina")
    if lon is not None and not (-74 <= lon <= -53):
        r.append("longitud_fuera_de_argentina")
    if (lat is None) != (lon is None):
        r.append("coordenada_incompleta")

    if p.get("operacion") not in (None, "venta", "alquiler", "alquiler_temporario",
                                  "consultar", "venta_y_alquiler"):
        r.append("operacion_fuera_de_vocabulario")

    url = p.get("source_url") or ""
    if not url.startswith("http"):
        r.append("source_url_invalida")
    if not p.get("source_listing_id"):
        r.append("sin_source_listing_id")

    imgs = p.get("imagenes") or []
    if len(imgs) != len(set(imgs)):
        r.append("imagenes_duplicadas")
    if any(re.search(r"(logo|placeholder|sin-?imagen|no-?photo)", u, re.I) for u in imgs):
        r.append("imagen_sospechosa_de_placeholder")
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entradas", nargs="+", required=True)
    a = ap.parse_args()

    props: list[dict] = []
    for e in a.entradas:
        props.extend(leer(Path(e)))
    if not props:
        print("sin propiedades")
        return 1
    n = len(props)

    print("### AUDITORIA DE CALIDAD ###")
    print(f"  propiedades: {n:,}")
    print(f"  connectors:  {dict(Counter(p.get('connector') for p in props))}")

    print("\n  COBERTURA por campo (un vacio no es un error si la fuente no lo publica):")
    for c in CAMPOS:
        lleno = sum(1 for p in props if p.get(c) not in (None, "", []))
        print(f"    {c:22} {lleno/n*100:5.1f}%  ({lleno:,})")

    print("\n  COHERENCIA (combinaciones que no pueden ser ciertas):")
    fallas = Counter()
    afectadas = 0
    for p in props:
        r = incoherencias(p)
        if r:
            afectadas += 1
        for x in r:
            fallas[x] += 1
    if not fallas:
        print("    ninguna")
    for k, v in fallas.most_common():
        print(f"    {k:36} {v:6,}  ({v/n*100:5.2f}%)")
    print(f"    -> propiedades con al menos una: {afectadas:,} ({afectadas/n*100:.2f}%)")

    print("\n  DUPLICADOS:")
    hashes = Counter(p.get("hash_dedup") for p in props)
    rep = {h: c for h, c in hashes.items() if c > 1}
    print(f"    hash repetido en el dataset: {len(rep):,}")
    por_hash = defaultdict(set)
    for p in props:
        por_hash[p.get("hash_dedup")].add(p.get("canonical_agency_id"))
    cruzados = [h for h, ag in por_hash.items() if len(ag) > 1]
    print(f"    hash compartido entre agencias: {len(cruzados):,}")
    urls = Counter(p.get("source_url") for p in props)
    print(f"    url repetida: {sum(1 for u, c in urls.items() if c > 1):,}")

    # Mismo inmueble ofrecido por dos inmobiliarias distintas. No es un error de
    # la ingesta sino un hecho del mercado: se marca como candidato, nunca se
    # fusiona automaticamente.
    pistas = defaultdict(set)
    for p in props:
        if p.get("latitud") and p.get("precio") and p.get("moneda"):
            clave = (round(p["latitud"], 5), round(p.get("longitud") or 0, 5),
                     p["precio"], p["moneda"])
            pistas[clave].add(p.get("canonical_agency_id"))
    cross = {k: v for k, v in pistas.items() if len(v) > 1}
    print(f"    candidatos cross-agency (mismo punto y precio): {len(cross):,}")

    print("\n  PRECIOS:")
    con = [p for p in props if p.get("precio") and p.get("moneda")]
    for mon in ("USD", "ARS"):
        v = sorted(p["precio"] for p in con if p["moneda"] == mon)
        if v:
            print(f"    {mon}: n={len(v):,} min={v[0]:,.0f} "
                  f"mediana={v[len(v)//2]:,.0f} max={v[-1]:,.0f}")

    print("\n  OPERACION / TIPO:")
    print(f"    operacion: {dict(Counter(p.get('operacion') for p in props).most_common(6))}")
    print(f"    tipo:      {dict(Counter(p.get('tipo_propiedad') for p in props).most_common(8))}")

    fotos = [len(p.get("imagenes") or []) for p in props]
    print(f"\n  FOTOS: sin fotos {sum(1 for f in fotos if f == 0):,}  "
          f"media {sum(fotos)/n:.1f}  max {max(fotos)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
