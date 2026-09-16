#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""¿El `<title>` del HTML sirve para recuperar la operación? §7.

No escribe en la base. `database_writes: 0`. No arregla nada: mide si el
arreglo propuesto funcionaría, ANTES de escribirlo.

La pregunta no es "¿recupera?" sino "¿recupera **bien**?". Entre venta y
alquiler no hay un error chico: una casa de USD 180.000 publicada como alquiler
es una ficha que nadie entiende. Por eso se miden dos cosas por separado:

    TRUE_RECOVERY        fichas sin operación que la señal nueva completa
    FALSE_OPERATION_RISK fichas donde la señal nueva CONTRADICE lo que ya
                         sabemos, o donde afirma una operación que el cuerpo
                         de la ficha desmiente

La segunda es la que puede vetar el arreglo. Se mira contra cuatro fuentes
independientes —`<title>`, migas de pan, URL canónica y datos estructurados—
para no confiar en una sola.

Uso:
    python scripts/validar_operacion_fenix.py --agencia fenix
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
      "Accept-Encoding": "gzip", "Accept-Language": "es-AR,es;q=0.9"}

VENTA = re.compile(r"(?i)\ben\s+venta\b|\bventa\b")
ALQUILER = re.compile(r"(?i)\ben\s+alquiler\b|\balquiler\b|\balquila\b")
# El alquiler temporario es alquiler, pero decirlo aparte importa: mezclarlo
# con el permanente cambia el precio de escala y la ficha queda ilegible.
TEMPORARIO = re.compile(r"(?i)\btemporari|\btemporad")


def bajar(url: str) -> str:
    r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30)
    c = r.read(500_000)
    if r.headers.get("Content-Encoding") == "gzip":
        try:
            c = gzip.decompress(c)
        except OSError:
            pass
    return c.decode("utf-8", "replace")


def operacion_de(texto: str | None) -> str | None:
    """Qué operación afirma un fragmento. `None` si no afirma ninguna, y
    `AMBIGUA` si afirma las dos: una señal que dice las dos cosas no sirve
    para decidir, y tratarla como venta sería inventar."""
    if not texto:
        return None
    v, a = bool(VENTA.search(texto)), bool(ALQUILER.search(texto))
    if v and a:
        return "AMBIGUA"
    if a:
        return "alquiler_temporario" if TEMPORARIO.search(texto) else "alquiler"
    return "venta" if v else None


def senales(html: str, url: str) -> dict:
    t = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    titulo_html = re.sub(r"\s+", " ", t.group(1)).strip() if t else None

    h1 = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", html)
    encabezado = (re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", h1.group(1))).strip()
                  if h1 else None)

    canon = re.search(r'(?i)<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)',
                      html)
    canonica = canon.group(1) if canon else None

    migas = None
    m = re.search(r"(?is)<[^>]+class=[\"'][^\"']*breadcrumb[^\"']*[\"'][^>]*>(.*?)</",
                  html)
    if m:
        migas = re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", m.group(1))).strip()

    estructurado = None
    for m in re.finditer(r'(?is)<script[^>]+application/ld\+json[^>]*>(.*?)</script>',
                         html):
        crudo = m.group(1)
        mm = re.search(r'(?i)"(businessFunction|transactionType|operation)"\s*:\s*"([^"]+)',
                       crudo)
        if mm:
            estructurado = mm.group(2)
            break

    return {"titulo_html": titulo_html, "encabezado": encabezado,
            "canonica": canonica, "migas": migas, "estructurado": estructurado,
            "url": url}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agencia", default="fenix")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--pausa", type=float, default=1.2)
    args = ap.parse_args()

    paquete = None
    for d in (CERT / "agencies").iterdir():
        c = d / "certification.json"
        if not c.exists():
            continue
        try:
            j = json.loads(c.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if args.agencia in (j.get("canonical_agency_id") or ""):
            paquete = d
            break
    if not paquete:
        print(f"no encontre paquete para {args.agencia}")
        return 1

    props = [json.loads(l) for l in (paquete / "properties_run1.jsonl").read_text(
        encoding="utf-8", errors="replace").splitlines() if l.strip()]
    FICHA = re.compile(r"/propiedades/\d+/?$")
    props = [p for p in props if FICHA.search(p.get("source_url") or "")]
    sin = [p for p in props if not p.get("operacion")][:args.n]
    con = [p for p in props if p.get("operacion")][:args.n]
    print(f"### {args.agencia}: {len(sin)} sin operacion + {len(con)} con\n")

    filas = []
    for etiqueta, grupo in (("SIN", sin), ("CON", con)):
        for p in grupo:
            try:
                s = senales(bajar(p["source_url"]), p["source_url"])
            except Exception as e:
                print(f"  {etiqueta} no se pudo bajar: {type(e).__name__}")
                time.sleep(args.pausa)
                continue
            fila = {
                "grupo": etiqueta,
                "url": p["source_url"],
                "operacion_actual": p.get("operacion"),
                "por_titulo_html": operacion_de(s["titulo_html"]),
                "por_encabezado": operacion_de(s["encabezado"]),
                "por_canonica": operacion_de(s["canonica"]),
                "por_migas": operacion_de(s["migas"]),
                "por_estructurado": operacion_de(s["estructurado"]),
                "titulo_html": s["titulo_html"],
            }
            filas.append(fila)
            time.sleep(args.pausa)

    def resumen(campo: str) -> None:
        sin_f = [f for f in filas if f["grupo"] == "SIN"]
        con_f = [f for f in filas if f["grupo"] == "CON"]
        recupera = sum(1 for f in sin_f if f[campo] and f[campo] != "AMBIGUA")
        ambiguas = sum(1 for f in sin_f if f[campo] == "AMBIGUA")
        contradice = sum(1 for f in con_f
                         if f[campo] and f[campo] != "AMBIGUA"
                         and f[campo].split("_")[0] != str(f["operacion_actual"]).split("_")[0])
        coincide = sum(1 for f in con_f
                       if f[campo] and f[campo] != "AMBIGUA"
                       and f[campo].split("_")[0] == str(f["operacion_actual"]).split("_")[0])
        print(f"{campo:20} TRUE_RECOVERY {recupera:3}/{len(sin_f):<3} "
              f"| ambiguas {ambiguas:3} "
              f"| sobre las que YA funcionan: coincide {coincide:3}, "
              f"CONTRADICE {contradice:3}")

    print("=" * 78)
    for campo in ("por_titulo_html", "por_encabezado", "por_canonica",
                  "por_migas", "por_estructurado"):
        resumen(campo)
    print("=" * 78)
    print("\nCONTRADICE es FALSE_OPERATION_RISK: la senal nueva afirma una")
    print("operacion distinta de la que hoy tenemos por una via que ya")
    print("funciona. Cualquier valor > 0 ahi veta usar esa senal sola.\n")

    print("reparto de lo que recuperaria el <title>:")
    print(Counter(f["por_titulo_html"] for f in filas
                  if f["grupo"] == "SIN").most_common())
    print("\nejemplos de lo que recupera:")
    for f in [x for x in filas if x["grupo"] == "SIN"][:6]:
        print(f"   {str(f['por_titulo_html']):22} <- {(f['titulo_html'] or '')[:62]}")

    salida = CERT / f"ERETZ_OPERACION_{args.agencia.upper()}.jsonl"
    salida.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n"
                              for f in filas), encoding="utf-8")
    print(f"\nartefacto: {salida}")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
