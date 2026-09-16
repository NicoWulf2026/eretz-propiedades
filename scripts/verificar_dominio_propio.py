#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Agencias que apuntan a un portal teniendo sitio propio. §5, §55, §78.

No escribe en la base ni en el padrón. `database_writes: 0`. Verifica y deja el
artefacto; cambiar el destino de scrapeo es un paso aparte.

El hallazgo: 41 agencias tienen su dominio propio registrado como
`previous_url` y la fuente elegida es un perfil de portal. 35 de esas 41 tienen
su propio dominio marcado `OFFICIAL_WEB_AMBIGUOUS`, así que algo lo degradó y
el portal ganó por descarte.

Esto NO es lo mismo que apagar un portal. Apagar es seguro: se deja de mirar
una fuente que no era nuestra. **Cambiar** el destino significa empezar a
enumerar un sitio nuevo, y si el sitio es de otro, ingerimos inventario ajeno
—exactamente el daño que se acaba de reparar—. Por eso cada candidata se
comprueba una por una, y las que no pasan quedan afuera.

Las cuatro condiciones, todas contra la fuente:

  1. responde y sirve contenido;
  2. su propio título nombra a la agencia;
  3. no es un portal;
  4. publica algo que parece un catálogo —enlaces de ficha o precios—.

La cuarta importa porque un sitio institucional vivo, con el nombre correcto y
sin catálogo, no aporta inventario: cambiar a él no recupera nada y sí pierde
la única fuente que había.

Uso:
    python scripts/verificar_dominio_propio.py
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
from urllib.parse import urlparse

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

import verificador_identidad_v2 as v2  # noqa: E402

DATOS = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
DIRECTORIO = DATOS / "agency_web_directory.jsonl"
SALIDA = CERT / "ERETZ_DOMINIO_PROPIO_CANDIDATAS.jsonl"

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
      "Accept-Encoding": "gzip", "Accept-Language": "es-AR,es;q=0.9"}

RE_FICHA = re.compile(r'href="([^"]*/(?:propiedad|propiedades|inmueble|'
                      r'inmuebles|ad|ficha|listing)[^"]*)"', re.I)
RE_PRECIO = re.compile(r"(?i)(?:USD|U\$S|US\$|ARS|\$)\s?[\d][\d.,]{2,}")

GENERICAS = {"propiedades", "inmobiliaria", "inmobiliarias", "bienes", "raices",
             "negocios", "inmobiliarios", "servicios", "estudio", "real",
             "estate", "grupo", "realty", "inmuebles", "de", "y", "sa", "srl"}


def partes_del_nombre(nombre: str) -> list[str]:
    return [p for p in v2._normalizar(nombre).split()
            if len(p) >= 4 and p not in GENERICAS]


def bajar(url: str) -> tuple[int, str, str]:
    r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25)
    c = r.read(500_000)
    if r.headers.get("Content-Encoding") == "gzip":
        try:
            c = gzip.decompress(c)
        except OSError:
            pass
    return r.status, c.decode("utf-8", "replace"), r.url


def comprobar(nombre: str, propio: str) -> dict:
    if v2.es_portal_url(propio):
        return {"veredicto": "EL_PROPIO_TAMBIEN_ES_PORTAL",
                "porque": "el `previous_url` tampoco es un sitio propio"}
    try:
        http, html, final = bajar(propio)
    except Exception as e:
        return {"veredicto": "NO_RESPONDE",
                "porque": f"{type(e).__name__} {getattr(e, 'code', '')}".strip()}
    if not html.strip() or len(html) < 1500:
        return {"veredicto": "SIN_CONTENIDO",
                "porque": f"HTTP {http} con {len(html)} bytes"}
    if v2.es_portal_url(final):
        return {"veredicto": "REDIRIGE_A_PORTAL",
                "porque": f"termina en {urlparse(final).netloc}"}

    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    titulo = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    tit = re.sub(r"[^a-z0-9]", "", v2._normalizar(titulo))
    dom = re.sub(r"[^a-z0-9]", "", urlparse(final).netloc.lower())
    partes = partes_del_nombre(nombre)
    coincide = [p for p in partes if p in tit or p in dom]

    plano = re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", html))
    fichas = len({u for u in RE_FICHA.findall(html)})
    precios = len(set(RE_PRECIO.findall(plano)))

    if not coincide:
        return {"veredicto": "EL_NOMBRE_NO_APARECE", "titulo": titulo[:90],
                "porque": f"ninguna parte de {partes} esta en el titulo ni "
                          f"en el dominio"}
    if fichas < 3 and precios < 3:
        return {"veredicto": "SIN_CATALOGO_VISIBLE", "titulo": titulo[:90],
                "fichas": fichas, "precios": precios,
                "porque": "el sitio es suyo pero no se le ve catalogo: "
                          "cambiar a el no recupera inventario"}
    return {"veredicto": "CANDIDATA", "titulo": titulo[:90],
            "fichas": fichas, "precios": precios,
            "porque": f"'{coincide[0]}' en su titulo o dominio, "
                      f"{fichas} enlaces de ficha y {precios} precios"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pausa", type=float, default=1.2)
    ap.add_argument("--tope", type=int, default=50)
    args = ap.parse_args()

    objetivo = []
    for l in DIRECTORIO.read_text(encoding="utf-8", errors="replace").splitlines():
        if not l.strip():
            continue
        try:
            r = json.loads(l)
        except ValueError:
            continue
        prev = r.get("previous_url") or ""
        sel = r.get("selected_domain") or ""
        if not (prev.startswith("http") and sel.startswith("http")):
            continue
        if prev.rstrip("/") == sel.rstrip("/"):
            continue
        if v2.es_portal_url(sel) and not v2.es_portal_url(prev):
            objetivo.append(r)

    print(f"agencias que apuntan a un portal teniendo dominio propio: "
          f"{len(objetivo)}\n")

    filas = []
    for r in objetivo[:args.tope]:
        a = r.get("canonical_agency_id") or ""
        nombre = r.get("agency_name") or a.split(":")[-1]
        propio = r["previous_url"]
        c = comprobar(nombre, propio)
        filas.append({"agency_id": a, "agency_name": nombre,
                      "dominio_propio": propio,
                      "fuente_elegida_hoy": r["selected_domain"],
                      "estado_del_propio": r.get("previous_url_status"), **c})
        marca = "OK " if c["veredicto"] == "CANDIDATA" else "   "
        print(f"{marca}{nombre[:28]:30} {c['veredicto']:26} {c['porque'][:52]}")
        time.sleep(args.pausa)

    SALIDA.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n"
                              for f in filas), encoding="utf-8")

    print(f"\n{'='*74}")
    for k, n in Counter(f["veredicto"] for f in filas).most_common():
        print(f"   {k:30} {n}")
    cand = [f for f in filas if f["veredicto"] == "CANDIDATA"]
    print(f"\n  CANDIDATAS a cambiar de fuente: {len(cand)}")
    print("\n  NO se cambia nada acá. Apagar un portal es seguro; CAMBIAR el")
    print("  destino de scrapeo significa empezar a enumerar un sitio nuevo, y")
    print("  eso necesita autorizacion aparte.")
    print(f"\nartefacto: {SALIDA}")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
