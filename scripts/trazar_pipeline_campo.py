#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""¿En qué etapa se pierde el valor de un campo? §2.

No escribe en la base. `database_writes: 0`. No arregla nada: mira.

Corre **las funciones reales del conector**, no una reimplementación, sobre el
HTML real de cada ficha, y en cada etapa pregunta si el valor todavía está.
Devuelve las tres marcas que el §2 pide:

    FIRST_STAGE_WITH_VALUE     la primera etapa donde el valor aparece
    LAST_STAGE_WITH_VALUE      la última donde sobrevive
    FIRST_STAGE_WITHOUT_VALUE  la primera donde ya no está

La diferencia entre las dos últimas es el culpable. Si `LAST` es la etapa N y
`FIRST_WITHOUT` es la N+1, el defecto está en la N+1 y no hay que buscarlo en
otro lado.

Se compara siempre contra la ficha que SÍ funciona de la misma agencia, porque
una etapa que descarta el valor en las dos no puede ser la causa de que una
falle y la otra no.

Uso:
    python scripts/trazar_pipeline_campo.py --agencia blanco
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from connectors.generico import (GenericoConnector, _texto,  # noqa: E402
                                 cuerpo_principal, normalizar_texto_campos,
                                 sin_filtros_catalogo)

CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
      "Accept-Encoding": "gzip", "Accept-Language": "es-AR,es;q=0.9"}


def bajar(url: str) -> str:
    r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30)
    c = r.read(600_000)
    if r.headers.get("Content-Encoding") == "gzip":
        try:
            c = gzip.decompress(c)
        except OSError:
            pass
    return c.decode("utf-8", "replace")


def etapas(html: str) -> list[tuple[str, str]]:
    """Las etapas por las que pasa el HTML antes de que se lean los campos.

    Son las mismas llamadas, en el mismo orden, que hace `normalize()`.
    """
    principal = cuerpo_principal(html)
    sin_filtros = sin_filtros_catalogo(principal)
    plano = _texto(sin_filtros)
    normalizado = normalizar_texto_campos(plano)
    jsonld = json.dumps(GenericoConnector._de_json_ld(html), ensure_ascii=False)
    return [
        ("1_html_crudo", html),
        ("2_cuerpo_principal", principal),
        ("3_sin_filtros_catalogo", sin_filtros),
        ("4_texto_plano", plano),
        ("5_texto_normalizado", normalizado),
        ("6_json_ld_extraido", jsonld),
    ]


# Qué se considera "el valor está" en cada campo. Son señales de la FUENTE, no
# del parser: si la señal está y el campo sale vacío, el defecto es nuestro.
SENALES = {
    "precio": re.compile(r"(?i)(USD|U\$S|US\$|ARS|\$)\s?[\d][\d.,]{2,}"),
    "moneda": re.compile(r"(?i)\b(USD|U\$S|US\$|ARS|pesos|d[oó]lares)\b"),
    "ambientes": re.compile(r"(?i)\b(\d+)\s*(ambiente|dormitorio|habitacion)"),
    "operacion": re.compile(r"(?i)\b(en venta|en alquiler|venta|alquiler)\b"),
}


def trazar(url: str, campos: list[str]) -> dict:
    html = bajar(url)
    fuera: dict = {"url": url, "bytes": len(html), "etapas": {}}
    es = etapas(html)
    for campo in campos:
        patron = SENALES[campo]
        presencia = [(n, bool(patron.search(t))) for n, t in es]
        con = [n for n, ok in presencia if ok]
        sin_despues = None
        if con:
            ultimo = max(i for i, (n, ok) in enumerate(presencia) if ok)
            for n, ok in presencia[ultimo + 1:]:
                if not ok:
                    sin_despues = n
                    break
        fuera["etapas"][campo] = {
            "FIRST_STAGE_WITH_VALUE": con[0] if con else None,
            "LAST_STAGE_WITH_VALUE": con[-1] if con else None,
            "FIRST_STAGE_WITHOUT_VALUE": sin_despues,
            "presencia": {n: ok for n, ok in presencia},
        }
    return fuera


def paquete_de(agencia: str) -> Path | None:
    for d in (CERT / "agencies").iterdir():
        c = d / "certification.json"
        if not c.exists():
            continue
        try:
            j = json.loads(c.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if agencia in (j.get("canonical_agency_id") or ""):
            return d
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agencia", required=True)
    ap.add_argument("--campos", default="precio,moneda,ambientes")
    ap.add_argument("--fallan", type=int, default=5)
    ap.add_argument("--pausa", type=float, default=1.5)
    args = ap.parse_args()
    campos = [c.strip() for c in args.campos.split(",") if c.strip()]

    d = paquete_de(args.agencia)
    if not d:
        print(f"no encontre paquete para {args.agencia}")
        return 1
    props = [json.loads(l) for l in (d / "properties_run1.jsonl").read_text(
        encoding="utf-8", errors="replace").splitlines() if l.strip()]

    clave = campos[0]
    pasan = [p for p in props if p.get(clave)]
    fallan = [p for p in props if not p.get(clave)]
    print(f"### {args.agencia} — {len(props)} fichas, "
          f"{len(pasan)} con {clave}, {len(fallan)} sin\n")

    muestra = [("FALLA", p) for p in fallan[:args.fallan]]
    muestra += [("PASA", p) for p in pasan[:4]]

    resultados = []
    for etiqueta, p in muestra:
        url = p["source_url"]
        try:
            r = trazar(url, campos)
        except Exception as e:
            print(f"{etiqueta:6} {url[-50:]}  NO SE PUDO BAJAR: {type(e).__name__}")
            time.sleep(args.pausa)
            continue
        r["grupo"] = etiqueta
        resultados.append(r)
        print(f"{etiqueta:6} {url[-52:]}  ({r['bytes']:,} bytes)")
        for campo in campos:
            e = r["etapas"][campo]
            marcas = "".join("o" if v else "." for v in e["presencia"].values())
            print(f"        {campo:11} [{marcas}]  "
                  f"ultima={e['LAST_STAGE_WITH_VALUE'] or '(nunca aparece)'}"
                  + (f"  SE PIERDE EN={e['FIRST_STAGE_WITHOUT_VALUE']}"
                     if e["FIRST_STAGE_WITHOUT_VALUE"] else ""))
        time.sleep(args.pausa)

    print("\n  la fila [oooooo] se lee etapa por etapa:")
    for i, (n, _) in enumerate(etapas("<html></html>")):
        print(f"     {i+1}. {n}")

    print("\n=== DONDE SE PIERDE, POR GRUPO ===")
    for campo in campos:
        print(f"\n{campo}:")
        for grupo in ("FALLA", "PASA"):
            rs = [r for r in resultados if r["grupo"] == grupo]
            if not rs:
                continue
            pierde = [r["etapas"][campo]["FIRST_STAGE_WITHOUT_VALUE"] for r in rs]
            ultima = [r["etapas"][campo]["LAST_STAGE_WITH_VALUE"] for r in rs]
            print(f"   {grupo:6} ultima etapa con valor: "
                  f"{sorted({str(u) for u in ultima})}")
            print(f"          se pierde en:            "
                  f"{sorted({str(p) for p in pierde})}")

    salida = CERT / f"ERETZ_TRAZA_{args.agencia.upper()}.json"
    salida.write_text(json.dumps(resultados, ensure_ascii=False, indent=1),
                      encoding="utf-8")
    print(f"\nartefacto: {salida}")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
