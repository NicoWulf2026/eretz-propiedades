#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Las fuentes que estan listas para leer y todavia no se leyeron.

El manifest dice cuales tienen web demostrada y responden. El write set dice
cuales ya aportaron inventario. La resta es el trabajo que queda, y es la unica
forma honesta de calcularlo: contar "fuentes pendientes" sobre un censo viejo
mide el universo de otro momento.

A cada fuente se le asigna el connector que corresponde segun lo que el mapa
tecnologico detecto. Las que el mapa no vio van a generico, no porque generico
sea mejor sino porque probar sitemap, JSON embebido y HTML cuesta un pedido y
escribir un connector nuevo cuesta un dia: primero se prueba lo barato.

Solo lee artefactos. No pide nada a la red.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

CENSUS_VERSION = "backlog_census_v1"

# Que connector sabe leer cada plataforma. Lo que no figura va a generico.
POR_PLATAFORMA = {
    "TOKKO": "tokko",
    "WORDPRESS": "wordpress",
    "WASI": "wasi",
    "CENTURY21": "century21",
}

# La estrategia manda sobre la plataforma cuando dice algo mas preciso: un sitio
# puede estar hecho en WordPress y publicar el inventario con Tokko adentro.
POR_ESTRATEGIA = {
    "TOKKO_CONNECTOR": "tokko",
    "WORDPRESS_API": "wordpress",
}


def leer(ruta: Path):
    if not ruta.exists():
        return
    with ruta.open(encoding="utf-8", errors="replace") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea:
                continue
            try:
                yield json.loads(linea)
            except ValueError:
                continue


def base_de_descubrimiento(url: str) -> str:
    """La raiz del sitio, no la ficha que quedo guardada como "web oficial".

    La identidad de varias fuentes se demostro mirando una ficha concreta
    -acinpropiedades.com.ar/p/8093032-Departamento-...- y esa url quedo como su
    dominio. Sirve para probar de quien es el sitio; no sirve como punto de
    partida para descubrir el listado, porque el connector arranca desde ahi y
    no encuentra nada. De 623 fuentes que fallaron, 68 tenian una ficha por
    base.

    Se normaliza solo cuando la ruta tiene profundidad de ficha. La pagina de
    una oficina dentro de su propia red -century21.com.ar/oficina/33- SI es su
    punto de partida y no se toca.
    """
    import re
    m = re.match(r"^(https?)://([^/]+)(/.*)?$", url or "")
    if not m:
        return url
    esquema, host, camino = m.group(1), m.group(2), m.group(3) or "/"
    if re.search(r"/oficina[_/-]", camino, re.I):
        return url
    partes = [x for x in camino.split("/") if x]
    if len(partes) < 2:
        return url
    return "%s://%s" % (esquema, host)


def connector_de(tec: dict) -> tuple:
    """(connector, por_que). Sin mapa, generico: probar es barato."""
    if not tec:
        return "generico", "el mapa tecnologico no la vio; se prueba lo barato"
    est = (tec.get("strategy") or "").upper()
    if est in POR_ESTRATEGIA:
        return POR_ESTRATEGIA[est], "estrategia detectada: %s" % est
    plat = (tec.get("detected_platform") or "").upper()
    for clave, conn in POR_PLATAFORMA.items():
        if plat.startswith(clave):
            return conn, "plataforma detectada: %s" % plat
    return "generico", "plataforma %s sin connector propio; se prueba generico" % (
        plat or "desconocida")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raiz", default=r"D:\INMO CAPITAL")
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\CENSO_BACKLOG.jsonl")
    ap.add_argument("--salida-generico",
                    default=r"D:\INMO CAPITAL\CENSO_BACKLOG_GENERICO.jsonl",
                    help="el mismo backlog, todo por generico: es la caida "
                         "cuando el connector de plataforma no reconocio el sitio")
    a = ap.parse_args()
    raiz, dd = Path(a.raiz), Path(a.data_dir)

    listas = {}
    for r in leer(raiz / "SCRAPING_SOURCE_MANIFEST.jsonl"):
        if r.get("ready_for_scraping") and r.get("official_domain"):
            listas[r["canonical_agency_id"]] = r

    con_inventario = set()
    for p in leer(raiz / "DB_WRITE_ELIGIBLE.jsonl"):
        con_inventario.add(p.get("canonical_agency_id"))

    tec = {}
    for t in leer(dd / "scrape_source_technology_map.jsonl"):
        cid = t.get("canonical_agency_id")
        if cid:
            tec[cid] = t

    filas = []
    for cid, r in sorted(listas.items()):
        if cid in con_inventario:
            continue
        conn, porque = connector_de(tec.get(cid))
        filas.append({
            "canonical_agency_id": cid,
            "agency_name": r.get("canonical_name"),
            "official_url": base_de_descubrimiento(r.get("official_domain")),
            "url_de_identidad": r.get("official_domain"),
            "connector_candidato": conn,
            "clasificacion_nueva": "BACKLOG_SIN_INVENTARIO",
            "eretz_id": r.get("eretz_id"),
            "detected_platform": (tec.get(cid) or {}).get("detected_platform"),
            "strategy": (tec.get(cid) or {}).get("strategy"),
            "requires_js": (tec.get(cid) or {}).get("requires_js"),
            "sitemap": (tec.get(cid) or {}).get("sitemap"),
            "en_mapa_tecnologico": cid in tec,
            "evidencia": porque,
            "identity_status": r.get("identity_status"),
            "census_version": CENSUS_VERSION,
        })

    salida = Path(a.salida)
    tmp = salida.with_suffix(salida.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for f in filas:
            fh.write(json.dumps(f, ensure_ascii=False) + "\n")
    tmp.replace(salida)

    # Caida a generico. Un connector de plataforma que no reconoce el sitio no
    # prueba que el sitio no tenga inventario: prueba que esa plataforma no era.
    # Probar sitemap, JSON embebido y HTML cuesta un pedido; escribir un
    # connector nuevo cuesta un dia.
    gen = Path(a.salida_generico)
    tmpg = gen.with_suffix(gen.suffix + ".tmp")
    with tmpg.open("w", encoding="utf-8") as fh:
        for f in filas:
            fh.write(json.dumps({**f, "connector_candidato": "generico",
                                 "connector_original": f["connector_candidato"]},
                                ensure_ascii=False) + chr(10))
    tmpg.replace(gen)

    print("### BACKLOG DE SCRAPING ###")
    print("  fuentes listas para leer:      %d" % len(listas))
    print("  ya aportaron inventario:       %d"
          % len(listas.keys() & con_inventario))
    print("  BACKLOG (listas sin leer):     %d" % len(filas))
    print()
    print("  por connector:")
    for k, v in Counter(f["connector_candidato"] for f in filas).most_common():
        print("    %-14s %5d" % (k, v))
    print("  vistas por el mapa tecnologico: %d de %d"
          % (sum(1 for f in filas if f["en_mapa_tecnologico"]), len(filas)))
    print("  por plataforma:")
    for k, v in Counter(f["detected_platform"] for f in filas).most_common(12):
        print("    %-28s %5d" % (k, v))
    print()
    print("  artefacto -> %s" % salida)
    print("  caida a generico -> %s" % gen)
    return 0


if __name__ == "__main__":
    sys.exit(main())
