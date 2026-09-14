#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Abrir las candidatas que la búsqueda ya encontró y decidir.

No gasta una sola consulta paga. `database_writes: 0`.

La corrida anterior de discovery gastó 3.966 consultas en tres proveedores
—exa, serper, tavily— y dejó **1.634 inmobiliarias con candidatas encontradas y
sin decidir**: 1.414 en `OFFICIAL_WEB_AMBIGUOUS` y 220 en
`SEARCH_SECOND_PASS_REQUIRED`. La búsqueda está paga; lo que falta es abrir esas
páginas y ver si la inmobiliaria es la que dicen.

Antes de comprar más búsqueda conviene cobrar la que ya se compró.

El orden no es arbitrario. De las 1.177 con candidatas sin verificar:

    108   tienen la FK de `main` resuelta  -> verificarlas produce READY HOY
  1.069   están bloqueadas en staging      -> verificarlas deja el terreno listo

Por eso van primero las 108: son las únicas que se convierten en trabajo
certificable sin esperar la promoción de staging a main.

Uso:
    python scripts/verificar_candidatas_web.py --con-fk        # las 108
    python scripts/verificar_candidatas_web.py --limite 200
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import agency_web_discovery as wd  # noqa: E402

DATOS = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
V2 = Path(r"D:\INMO CAPITAL\ERETZ_SUPABASE_RECONCILIATION_V2_20260827")
DIRECTORIO = DATOS / "agency_web_directory.jsonl"
SALIDA = DATOS / "AGENCY_WEB_CANDIDATAS_VERIFICADAS.jsonl"

SIN_DECIDIR = ("OFFICIAL_WEB_AMBIGUOUS", "SEARCH_SECOND_PASS_REQUIRED")
UA = {"User-Agent": "Mozilla/5.0 (compatible; ERETZ/1.0)",
      "Accept-Encoding": "gzip"}


def bajar(url: str, timeout: float = 20) -> wd.Candidata:
    """Una candidata que no responde no es una candidata rechazada: es una que
    no se pudo mirar, y el veredicto lo trata distinto."""
    try:
        pedido = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(pedido, timeout=timeout) as r:
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
        return wd.Candidata(url=final, origen="verificacion", titulo=titulo,
                            texto=texto, http=200,
                            redirects=[url] if final != url else [])
    except urllib.error.HTTPError as e:
        return wd.Candidata(url=url, origen="verificacion", http=e.code)
    except Exception:
        return wd.Candidata(url=url, origen="verificacion", http=None)


def entidad_de(fila: dict) -> dict:
    """El contrato que `verificar` espera, armado desde el directorio web."""
    zonas = [z for z in (fila.get("city"), fila.get("province")) if z]
    return {"stable_id": fila.get("canonical_agency_id"),
            "nombre_original": fila.get("canonical_name") or "",
            "red_franquicia": fila.get("franchise"),
            "zonas_observadas": zonas,
            "matricula": []}


def con_fk_resuelta() -> set[str]:
    fuera = set()
    ruta = V2 / "AGENCY_ID_RESOLUTION_FINAL.jsonl"
    for linea in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
        if not linea.strip():
            continue
        try:
            fila = json.loads(linea)
        except ValueError:
            continue
        if (fila.get("resolution_status") == "RESOLVED"
                and fila.get("canonical_agency_id")):
            fuera.add(fila["canonical_agency_id"])
    return fuera


def hechas() -> set[str]:
    if not SALIDA.exists():
        return set()
    fuera = set()
    for linea in SALIDA.read_text(encoding="utf-8", errors="replace").splitlines():
        if not linea.strip():
            continue
        try:
            fuera.add(json.loads(linea)["canonical_agency_id"])
        except (ValueError, KeyError):
            continue
    return fuera


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--con-fk", action="store_true",
                    help="solo las que ya tienen FK de main: producen READY hoy")
    ap.add_argument("--limite", type=int, default=0)
    ap.add_argument("--pausa", type=float, default=0.4)
    args = ap.parse_args()

    resueltas = con_fk_resuelta()
    ya = hechas()
    pendientes = []
    for linea in DIRECTORIO.read_text(encoding="utf-8", errors="replace").splitlines():
        if not linea.strip():
            continue
        try:
            fila = json.loads(linea)
        except ValueError:
            continue
        if fila.get("status") not in SIN_DECIDIR:
            continue
        if not (fila.get("candidate_urls") or []):
            continue
        if fila.get("canonical_agency_id") in ya:
            continue
        if args.con_fk and fila.get("canonical_agency_id") not in resueltas:
            continue
        pendientes.append(fila)

    # Las que tienen FK primero: son las unicas que se vuelven certificables sin
    # esperar la promocion de staging a main.
    pendientes.sort(key=lambda f: 0 if f.get("canonical_agency_id") in resueltas else 1)
    if args.limite:
        pendientes = pendientes[:args.limite]

    print("### VERIFICAR CANDIDATAS YA ENCONTRADAS ###", flush=True)
    print(f"  a verificar:        {len(pendientes):,}", flush=True)
    print(f"  con FK de main:     "
          f"{sum(1 for f in pendientes if f['canonical_agency_id'] in resueltas):,}",
          flush=True)
    print("  consultas pagas:    0", flush=True)

    estados: Counter = Counter()
    resueltas_ahora = 0
    with SALIDA.open("a", encoding="utf-8") as fh:
        for i, fila in enumerate(pendientes, 1):
            candidatas = []
            for url in (fila.get("candidate_urls") or [])[:4]:
                if wd.es_portal(url):
                    continue
                c = bajar(url)
                if c.http is not None:
                    candidatas.append(c)
                time.sleep(args.pausa)
            veredicto = (wd.verificar(entidad_de(fila), candidatas) if candidatas
                         else None)
            estado = veredicto.estado if veredicto else "SIN_CANDIDATA_VIVA"
            estados[estado] += 1
            if estado in (wd.VERIFIED, wd.HIGH_CONFIDENCE):
                resueltas_ahora += 1
            fh.write(json.dumps({
                "canonical_agency_id": fila["canonical_agency_id"],
                "canonical_name": fila.get("canonical_name"),
                "estado_previo": fila.get("status"),
                "estado": estado,
                "official_web": veredicto.official_web if veredicto else None,
                "official_office_page": (veredicto.official_office_page
                                         if veredicto else None),
                "confianza": veredicto.confianza if veredicto else 0.0,
                "razon": veredicto.razon if veredicto else "ninguna candidata respondio",
                "tiene_fk_main": fila["canonical_agency_id"] in resueltas,
                "candidatas_probadas": [c.url for c in candidatas],
                "cuando": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }, ensure_ascii=False) + "\n")
            fh.flush()
            if i % 25 == 0:
                print(f"  {i}/{len(pendientes)}  resueltas {resueltas_ahora}",
                      flush=True)

    print("\nRESULTADO")
    for estado, n in estados.most_common():
        print(f"   {estado[:40]:42} {n:6}")
    print(f"\n   web oficial establecida: {resueltas_ahora}")
    print(f"   artefacto: {SALIDA}")
    print("   consultas pagas gastadas: 0")
    print("database_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
