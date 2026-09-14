#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Las 211 `OFFICIAL_OFFICE_PAGE`: ¿son la página de ESA oficina?

No escribe en la base. `database_writes: 0`.

El §10 las pone primero y tiene razón: 211 agencias concentran 45.661 avisos
—216 por agencia contra 5 de las 2.216 `NO_WEB`—. Ahí está el inventario.

Pero "tiene office page" no es lo mismo que "tiene office page verificada".
Por forma de URL, 27 de las 211 no lo son: listados de la red, blogs, índices
de directorio y una ficha de propiedad. Y entre los listados hay uno de
`global.remax.com/es/propiedades/**uruguay**/piso`, que además es de otro país.

Este paso abre cada una y aplica el verificador V2, que exige las dos cosas por
separado: que la página sea de una oficina (no de la red) y que sea de ESTA
oficina (no de otra, ni en otro país).

Uso:
    python scripts/validar_office_pages.py
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

import verificador_identidad_v2 as v2  # noqa: E402

DATOS = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
BREAKDOWN = CERT / "ERETZ_STAGING_BREAKDOWN.jsonl"
SALIDA = CERT / "ERETZ_OFFICE_PAGES_VALIDADAS.jsonl"

UA = {"User-Agent": "Mozilla/5.0 (compatible; ERETZ/1.0)", "Accept-Encoding": "gzip"}


def bajar(url: str, timeout: float = 20) -> v2.Sitio:
    try:
        with urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            crudo = r.read(400_000)
            if r.headers.get("Content-Encoding") == "gzip":
                try:
                    crudo = gzip.decompress(crudo)
                except OSError:
                    pass
            cuerpo = crudo.decode("utf-8", "replace")
            final = r.url
        titulo = ""
        m = re.search(r"(?is)<title[^>]*>(.*?)</title>", cuerpo)
        if m:
            titulo = re.sub(r"\s+", " ", m.group(1)).strip()
        texto = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", cuerpo)
        texto = re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", texto))[:8000]
        return v2.Sitio(url=final, titulo=titulo, texto=texto, http=200)
    except urllib.error.HTTPError as e:
        return v2.Sitio(url=url, http=e.code)
    except Exception:
        return v2.Sitio(url=url, http=None)


def leer(ruta: Path, clave: str) -> dict[str, dict]:
    fuera = {}
    if not ruta.exists():
        return fuera
    for linea in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
        if not linea.strip():
            continue
        try:
            fila = json.loads(linea)
        except ValueError:
            continue
        if fila.get(clave):
            fuera[fila[clave]] = fila
    return fuera


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pausa", type=float, default=0.5)
    ap.add_argument("--limite", type=int, default=0)
    args = ap.parse_args()

    web = leer(DATOS / "agency_web_directory.jsonl", "canonical_agency_id")
    padron = leer(DATOS / "roomix_agency_directory.jsonl", "stable_id")
    filas = [json.loads(l) for l in
             BREAKDOWN.read_text(encoding="utf-8", errors="replace").splitlines()
             if l.strip()]
    objetivo = [f for f in filas if f["block_reason"] == "OFFICIAL_OFFICE_PAGE"]
    objetivo.sort(key=lambda f: -(f.get("avisos_observados") or 0))
    if args.limite:
        objetivo = objetivo[:args.limite]

    print("### VALIDAR OFFICE PAGES ###")
    print(f"  a validar: {len(objetivo)}")
    print(f"  avisos:    {sum(f['avisos_observados'] for f in objetivo):,}\n")

    clases: Counter = Counter()
    avisos: Counter = Counter()
    salida = []
    for i, f in enumerate(objetivo, 1):
        url = (web.get(f["agency_id"]) or {}).get("selected_office_page") or ""
        p = padron.get(f["agency_id"]) or {}
        entidad = {"nombre_original": p.get("nombre_original") or f.get("nombre") or "",
                   "zonas_observadas": p.get("zonas_observadas") or [],
                   "matricula": p.get("matricula") or []}
        sitio = bajar(url) if url else v2.Sitio(url="", http=None)
        veredicto = v2.verificar(entidad, [sitio]) if url else v2.VeredictoV2(
            clase=v2.NO_OFFICIAL_WEB_FOUND, razon="sin url de oficina")
        clases[veredicto.clase] += 1
        avisos[veredicto.clase] += f.get("avisos_observados") or 0
        salida.append({
            "agency_id": f["agency_id"],
            "nombre": entidad["nombre_original"],
            "url_candidata": url,
            "clase": veredicto.clase,
            "confianza": veredicto.confianza,
            "site_type": veredicto.tipo_de_sitio,
            "razon": veredicto.razon[:300],
            "contras": "; ".join(veredicto.contras)[:200],
            "avisos_observados": f.get("avisos_observados") or 0,
            "cuando": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        time.sleep(args.pausa)
        if i % 25 == 0:
            print(f"  {i}/{len(objetivo)}", flush=True)

    with SALIDA.open("w", encoding="utf-8") as fh:
        for s in salida:
            fh.write(json.dumps(s, ensure_ascii=False) + "\n")

    print("\n=== RESULTADO ===")
    print(f"{'clase':28} {'agencias':>8} {'avisos':>9}")
    for clase, n in clases.most_common():
        print(f"{clase:28} {n:8} {avisos[clase]:9,}")
    ok = clases[v2.OFFICIAL_OFFICE_PAGE]
    print(f"\n  TERMINAL_IDENTITY confirmadas: {ok} "
          f"({avisos[v2.OFFICIAL_OFFICE_PAGE]:,} avisos)")
    print(f"  no lo son:                     {sum(clases.values()) - ok}")
    print(f"\n  artefacto: {SALIDA}")
    print("database_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
