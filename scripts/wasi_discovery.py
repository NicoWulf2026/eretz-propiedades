#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Aplicar el fingerprint de Wasi al universo y medir si se puede extraer.

Detectar la plataforma no es lo mismo que poder leer el inventario. Ya paso
con WordPress: 57 fuentes se dieron por recuperables porque tenian marcadores
del CMS y las 57 devolvieron cero, porque sus paginas eran institucionales. Asi
que aca cada fuente que da positivo se mide ademas por lo que se le puede
enumerar, y solo se propone connector cuando hay fichas a la vista.

Para cada sitio se busca, en el orden de costo que manda el proyecto:

  1. API o JSON estructurado   Wasi la tiene (api.wasi.co) pero exige
                               id_company + wasi_token, que el sitio publico no
                               expone. No hay via gratuita: se descarta.
  2. endpoint interno          no hay: el front es Laravel server-side
  3. estado JSON embebido      hay JSON-LD por ficha, pero incompleto
  4. HTML estructurado         sitemap.xml enumera las fichas y la ficha trae
                               una tabla de atributos etiquetada  <-- esta
  5. navegador                 no hace falta

Solo lee: no escribe en la base ni toca ninguna corrida en curso.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from connectors.base import (Bloqueado, Descargador, ErrorPermanente,  # noqa: E402
                             ErrorTransitorio, LimitadorDeRitmo)
from scripts.wasi_fingerprint import (es_ficha, fingerprint,  # noqa: E402
                                      inventario_declarado)

VERSION = "wasi_discovery_v1"

# Plataformas cuya clasificacion no salio de adivinar marcadores sino de que un
# connector enumero inventario de verdad. Con confianza alta, ahi no se esconde
# un Wasi.
CONFIRMADAS_POR_CONNECTOR = {"TOKKO", "WORDPRESS", "CENTURY21", "SITIO_PROPIO"}


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


def _bajar(d: Descargador, url: str) -> str | None:
    try:
        return d.bajar(url)
    except (Bloqueado, ErrorPermanente, ErrorTransitorio):
        return None


def analizar(f: dict, lim: LimitadorDeRitmo) -> dict:
    url = f.get("domain") or ""
    p = urllib.parse.urlparse(url)
    base = f"{p.scheme or 'https'}://{p.netloc}"
    d = Descargador(lim, limite_bytes=1_200_000)
    out = {
        "canonical_agency_id": f.get("canonical_agency_id"),
        "eretz_id": f.get("eretz_id"),
        "agency_name": f.get("agency_name"),
        "domain": url,
        "base": base,
        "host": f.get("host"),
        "web_kind": f.get("web_kind"),
        "plataforma_previa": f.get("platform"),
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "discovery_version": VERSION,
    }

    html = _bajar(d, base) or _bajar(d, url)
    if html is None:
        return {**out, "es_wasi": False, "familia": "INACCESIBLE",
                "connector": None,
                "motivo": "el sitio no respondio; no se puede afirmar ni negar Wasi"}

    fp = fingerprint(html, base)
    out.update(fp)
    if not fp["es_wasi"]:
        return {**out, "familia": "NO_WASI", "connector": None}

    # --- se confirmo Wasi: ahora, se le puede leer el inventario? -----------
    decl = inventario_declarado(html)
    out["declarado_menu"] = decl["total"]
    out["declarado_por_operacion"] = decl["por_operacion"]

    sm = _bajar(d, base + "/sitemap.xml") or ""
    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sm) if "<loc>" in sm else []
    fichas_sm = [u for u in locs if es_ficha(u)]
    out["sitemap_locs"] = len(locs)
    out["sitemap_fichas"] = len(fichas_sm)
    out["sitemap_es_indice"] = "<sitemapindex" in sm

    # Fichas visibles en el HTML servido: respaldo si el sitemap falta o miente.
    fichas_html = {urllib.parse.urlparse(urllib.parse.urljoin(base, h)).path
                   for h in re.findall(r'href="([^"]{4,200})"', html)}
    fichas_html = {x for x in fichas_html if es_ficha(x)}
    out["fichas_en_home"] = len(fichas_html)

    enumerables = max(len(fichas_sm), len(fichas_html))
    out["enumerables"] = enumerables
    if decl["total"] and len(fichas_sm):
        out["cobertura_sitemap"] = round(len(fichas_sm) / decl["total"], 4)

    if fichas_sm:
        out["familia"], out["connector"] = "WASI_SITEMAP", "wasi"
        out["via_extraccion"] = "sitemap.xml enumera las fichas"
    elif fichas_html:
        # El sitemap no sirvio, pero el listado pagina con /search?page=N.
        out["familia"], out["connector"] = "WASI_LISTADO_HTML", "wasi"
        out["via_extraccion"] = "paginacion /search?page=N sobre HTML servido"
    else:
        out["familia"], out["connector"] = "WASI_SIN_INVENTARIO", None
        out["via_extraccion"] = None
        out["motivo_sin_inventario"] = (
            "es Wasi pero no se vio ninguna ficha: sitio nuevo, vacio o solo "
            "institucional")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--directorio",
                    default=r"D:\INMO CAPITAL\agency_platform_directory.jsonl")
    ap.add_argument("--plataforma", nargs="*", default=["WASI"],
                    help="plataformas del directorio a sondear; TODAS para el universo")
    ap.add_argument("--web-kind", default="OFFICIAL_WEB",
                    help="TODAS para no filtrar")
    ap.add_argument("--limite", type=int, default=0)
    ap.add_argument("--solo-no-confirmadas", action="store_true",
                    help="saltear las fuentes cuya plataforma ya la probo un "
                         "connector enumerando inventario: ahi no hay Wasi "
                         "escondido y volver a pedirles la home es ruido")
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\WASI_DISCOVERY.jsonl")
    ap.add_argument("--concurrencia", type=int, default=2)
    ap.add_argument("--intervalo", type=float, default=1.5)
    a = ap.parse_args()

    filas = leer(Path(a.directorio))
    objetivo = [f for f in filas if f.get("domain")]
    if a.web_kind != "TODAS":
        objetivo = [f for f in objetivo if f.get("web_kind") == a.web_kind]
    if "TODAS" not in a.plataforma:
        quiere = {p.upper() for p in a.plataforma}
        objetivo = [f for f in objetivo if (f.get("platform") or "").upper() in quiere]
    if a.solo_no_confirmadas:
        objetivo = [f for f in objetivo
                    if not ((f.get("platform") or "").upper() in CONFIRMADAS_POR_CONNECTOR
                            and f.get("confidence") == "alta")]
    if a.limite:
        objetivo = objetivo[:a.limite]

    print("### FINGERPRINT WASI ###")
    print(f"  plataformas: {', '.join(a.plataforma)}")
    print(f"  fuentes:     {len(objetivo)}\n", flush=True)
    if not objetivo:
        return 0

    lim = LimitadorDeRitmo(a.intervalo)
    res = []
    # Escritura incremental: una excepcion al final no puede llevarse el
    # trabajo ya hecho, que es exactamente como se perdieron 15 fuentes antes.
    with Path(a.salida).open("w", encoding="utf-8") as fh:
        for i in range(0, len(objetivo), 10):
            with ThreadPoolExecutor(max_workers=a.concurrencia) as ex:
                for r in ex.map(lambda f: analizar(f, lim), objetivo[i:i + 10]):
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                    res.append(r)
            fh.flush()
            print(f"    {min(i + 10, len(objetivo))}/{len(objetivo)}", flush=True)

    si = [r for r in res if r.get("es_wasi")]
    print(f"\n  WASI confirmados: {len(si)}/{len(res)}")
    print("  por confianza:")
    for k, v in Counter(r["confianza"] for r in si).most_common():
        print(f"    {k:14} {v:5}")
    print("\n  familias:")
    for k, v in Counter(r.get("familia") for r in res).most_common():
        con = {r.get("connector") for r in res if r.get("familia") == k} - {None}
        print(f"    {k:24} {v:5}  connector: {', '.join(sorted(con)) or '-'}")
    print("\n  senales fuertes (cuantos sitios las traen):")
    cf = Counter(s for r in si for s in r.get("senales_fuertes", []))
    for k, v in cf.most_common():
        print(f"    {k:24} {v:5}/{len(si)}")
    planes = Counter(r.get("plan") for r in si if r.get("plan"))
    print(f"\n  planes contratados: {dict(planes.most_common(8))}")
    print(f"  builds distintos:   {len({r.get('build') for r in si if r.get('build')})}")
    enum = sum(r.get("enumerables") or 0 for r in si)
    print(f"\n  propiedades enumerables: {enum:,}")
    print(f"  inventario declarado:    "
          f"{sum(r.get('declarado_menu') or 0 for r in si):,}")
    print(f"\n  artefacto -> {a.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
