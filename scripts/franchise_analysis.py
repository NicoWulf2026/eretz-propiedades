#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Estructura de franquicias en los publicadores observados.

Pregunta que responde: cuando una red aparece en Roomix, aparece como marca
unica o como oficinas separadas. De eso depende que ERETZ deba guardar una
entidad o muchas, y colapsarlas seria destruir informacion real.

No hay hardcodes por oficina: se detecta la MARCA y se deriva el SUFIJO que la
distingue, sea cual sea la red.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm(s: str) -> str:
    s = strip_accents((s or "").lower())
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", s)).strip()


# Marcas de red. Se listan las FORMAS de escribir la marca, no las oficinas:
# lo que se quiere detectar es el prefijo de red para separar marca de sucursal.
BRANDS = {
    "RE/MAX": ["re max", "remax"],
    "Century 21": ["century 21", "century21", "c21"],
    "Keller Williams": ["keller williams", "kw "],
    "Coldwell Banker": ["coldwell banker"],
    "Engel & Volkers": ["engel volkers", "engel y volkers"],
    "Tsg": ["tsg "],
    "Interwin": ["interwin"],
    "Toribio Achaval": ["toribio achaval"],
}


def brand_of(name: str) -> tuple[str | None, str]:
    """Devuelve (marca, sufijo de oficina). El sufijo es lo que queda al sacar
    la marca: si es no vacio y distinto entre registros, son oficinas reales."""
    n = norm(name)
    for brand, forms in BRANDS.items():
        for f in forms:
            fn = norm(f)
            if not fn:
                continue
            if n.startswith(fn + " ") or n == fn or (" " + fn + " ") in (" " + n + " "):
                suffix = re.sub(r"\s+", " ", (" " + n + " ").replace(" " + fn + " ", " ")).strip()
                return brand, suffix
    return None, ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    a = ap.parse_args()
    d = Path(a.data_dir)

    pubs = [json.loads(l) for l in (d / "publishers.jsonl").open(encoding="utf-8") if l.strip()]
    eretz = [json.loads(l) for l in (d / "eretz_agencies.jsonl").open(encoding="utf-8") if l.strip()]

    # --- Roomix: como modela cada red
    by_brand: dict[str, list[dict]] = defaultdict(list)
    for p in pubs:
        b, suf = brand_of(p["raw_name"])
        if b:
            p["_brand"], p["_suffix"] = b, suf
            by_brand[b].append(p)

    # --- ERETZ: que tiene de cada red
    eretz_brand: dict[str, list[dict]] = defaultdict(list)
    for e in eretz:
        b, suf = brand_of(e.get("name") or "")
        if b:
            e["_suffix"] = suf
            eretz_brand[b].append(e)

    print("### ESTRUCTURA DE RED EN ROOMIX vs ERETZ ###", flush=True)
    print("  %-18s %8s %8s %9s %8s %8s" %
          ("marca", "roomix", "sufijos", "avisos", "eretz", "gap"), flush=True)
    out = {}
    for brand in sorted(by_brand, key=lambda b: -len(by_brand[b])):
        rows = by_brand[brand]
        suffixes = {r["_suffix"] for r in rows if r["_suffix"]}
        listings = sum(r["listings_observed"] for r in rows)
        er = eretz_brand.get(brand, [])
        e_suf = {e["_suffix"] for e in er if e["_suffix"]}
        gap = len(suffixes - e_suf)
        print("  %-18s %8d %8d %9d %8d %8d" %
              (brand, len(rows), len(suffixes), listings, len(er), gap), flush=True)
        out[brand] = {
            "roomix_publicadores": len(rows),
            "roomix_oficinas_distintas": len(suffixes),
            "avisos_observados": listings,
            "eretz_registros": len(er),
            "oficinas_no_cubiertas": sorted(suffixes - e_suf)[:40],
            "modelado": ("POR_OFICINA" if len(suffixes) > 1 else
                         "MARCA_UNICA" if len(rows) else "SIN_DATOS"),
        }

    print("\n### DETALLE: oficinas que Roomix individualiza y ERETZ no ###", flush=True)
    for brand, info in sorted(out.items(), key=lambda kv: -len(kv[1]["oficinas_no_cubiertas"])):
        miss = info["oficinas_no_cubiertas"]
        if not miss:
            continue
        print("  %s -> %d oficinas sin cubrir" % (brand, len(miss)), flush=True)
        for s in miss[:10]:
            print("      %s" % s[:64], flush=True)

    # Un publicador sin sufijo con la marca sola indica que la red tambien
    # publica bajo la marca madre: no se debe colapsar con sus oficinas.
    print("\n### MARCA MADRE PUBLICANDO POR SI MISMA ###", flush=True)
    for brand, rows in by_brand.items():
        bare = [r for r in rows if not r["_suffix"]]
        if bare:
            print("  %-18s %d registro(s) con la marca sola, %d avisos"
                  % (brand, len(bare), sum(r["listings_observed"] for r in bare)), flush=True)

    (d / "franchises.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print("\n  -> %s" % (d / "franchises.json"), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
