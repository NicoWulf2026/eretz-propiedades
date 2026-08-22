#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Reporte del universo de fuentes ya validado.

Solo lee artefactos y cuenta. No descarga nada, no decide nada: si un numero
sale distinto de lo esperado, el que esta mal es el artefacto, no este script.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ESTRATEGIAS_CONECTOR = ("TOKKO_CONNECTOR", "WORDPRESS_API", "API_DIRECT",
                        "JSON_EMBEDDED", "SITEMAP", "SSR_HTML",
                        "CUSTOM_CONNECTOR", "JS_BROWSER")


def leer(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    return [json.loads(l) for l in ruta.open(encoding="utf-8") if l.strip()]


def host_de(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", url or "").split("/")[0].lower()


def cobertura(mapa: list[dict], clave: str, excluir_unknown: bool) -> list[tuple]:
    """Cuantas fuentes cubren los primeros N conectores.

    UNKNOWN queda afuera cuando se cuenta por plataforma: son sitios propios,
    uno distinto por inmobiliaria, y contarlo como familia prometeria una
    cobertura que ningun conector entrega.
    """
    c = Counter(x[clave] for x in mapa)
    if excluir_unknown:
        c.pop("UNKNOWN", None)
        c.pop("MANUAL_REVIEW", None)
    return c.most_common()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    a = ap.parse_args()
    dd = Path(a.data_dir)

    mapa = leer(dd / "scrape_source_technology_map.jsonl")
    ident = leer(dd / "ready_identity_audit.jsonl")
    prof = leer(dd / "manual_review_deepened.jsonl")
    reaudit = leer(dd / "historical_scrapeability_reaudit.jsonl")
    total = len(mapa)

    print("=" * 66)
    print("A. IDENTIDAD")
    print("=" * 66)
    print(f"  fuentes auditadas en hosts compartidos: {len(ident):,}")
    for k, v in Counter(x["identity_status"] for x in ident).most_common():
        print(f"    {k:28} {v:5,}  ({v/max(len(ident),1)*100:5.1f}%)")
    fuera = [x for x in ident if x["identity_status"] in
             ("IDENTITY_WRONG_ENTITY", "IDENTITY_AMBIGUOUS")]
    print(f"  removidas de READY: {len(fuera):,}")
    print(f"  motivos de las ajenas:")
    for k, v in Counter(x["evidence"]["forma_de_ruta"] for x in ident
                        if x["identity_status"] == "IDENTITY_WRONG_ENTITY").most_common():
        print(f"    {k:28} {v:5,}")

    print()
    print("=" * 66)
    print("B. MANUAL_REVIEW PROFUNDIZADAS")
    print("=" * 66)
    if prof:
        print(f"  revisadas: {len(prof):,}")
        for k, v in Counter(x["new_status"] for x in prof).most_common():
            print(f"    {k:28} {v:5,}  ({v/len(prof)*100:5.1f}%)")
        rec = [x for x in prof if x["new_status"] == "SCRAPE_SOURCE_READY"]
        print(f"  recuperadas a READY: {len(rec):,}")
        con2 = sum(1 for x in prof if x.get("second_page"))
        print(f"  con segunda pagina efectiva: {con2:,}  "
              f"(sin candidato en la home: {len(prof)-con2:,})")
    else:
        print("  (sin artefacto)")

    print()
    print("=" * 66)
    print("C. READY FINAL")
    print("=" * 66)
    resc = sum(1 for x in reaudit if x.get("new_status") == "SCRAPE_SOURCE_READY")
    rec_mr = sum(1 for x in prof if x["new_status"] == "SCRAPE_SOURCE_READY")
    print(f"  READY originales:                  1,992")
    print(f"  + recuperadas historicas:         +{resc:,}")
    print(f"  - removidas por identidad:        -{len(fuera):,}")
    print(f"  = universo mapeado:                {total:,}")
    print(f"  de las cuales MANUAL_REVIEW:       "
          f"{sum(1 for x in mapa if x['strategy']=='MANUAL_REVIEW'):,}")
    # Las recuperadas desde MANUAL_REVIEW ya estan descontadas del recuento de
    # arriba: el overlay les asigno estrategia. Sumarlas otra vez las contaria dos veces.
    print(f"  recuperadas desde MANUAL_REVIEW:  +{rec_mr:,} (ya reflejadas arriba)")
    listas = sum(1 for x in mapa if x["strategy"] != "MANUAL_REVIEW")
    print(f"  TOTAL READY FINAL (con estrategia): {listas:,}")

    print()
    print("=" * 66)
    print("D. MAPA TECNOLOGICO FINAL")
    print("=" * 66)
    print("  por plataforma:")
    for k, v in Counter(x["detected_platform"] for x in mapa).most_common(16):
        print(f"    {k:22} {v:5,}  ({v/total*100:5.1f}%)")
    print("\n  por estrategia:")
    for k, v in Counter(x["strategy"] for x in mapa).most_common():
        print(f"    {k:22} {v:5,}  ({v/total*100:5.1f}%)")

    print("\n  hosts compartidos (tras el control de identidad):")
    porhost = defaultdict(list)
    for x in mapa:
        porhost[host_de(x["official_url"])].append(x)
    comp = sorted(((h, g) for h, g in porhost.items() if len(g) >= 3),
                  key=lambda t: -len(t[1]))
    for h, g in comp[:12]:
        plat = Counter(y["detected_platform"] for y in g).most_common(1)[0][0]
        est = Counter(y["strategy"] for y in g).most_common(1)[0][0]
        print(f"    {h:30} {len(g):4}  {plat:14} {est}")
    print(f"    -> {sum(len(g) for g in porhost.values() if len(g)>=3):,} fuentes "
          f"en {len(comp)} hosts compartidos")

    print()
    print("=" * 66)
    print("E. COBERTURA DE CONECTORES")
    print("=" * 66)
    for etiqueta, clave in (("PLATAFORMA", "detected_platform"),
                            ("ESTRATEGIA", "strategy")):
        print(f"\n  por {etiqueta} (UNKNOWN y MANUAL_REVIEW excluidos):")
        grupos = cobertura(mapa, clave, True)
        acum = 0
        for n, (k, v) in enumerate(grupos, 1):
            acum += v
            if n in (1, 3, 5, 10):
                print(f"    {n:2} conector(es): {acum:5,} fuentes "
                      f"({acum/total*100:5.1f}%)   ultimo: {k}")

    print()
    print("=" * 66)
    print("F. PRIORIDAD DE CONSTRUCCION")
    print("=" * 66)
    resumen = json.loads((dd / "scrape_platform_summary.json").read_text(encoding="utf-8"))
    filas = [(k, v) for k, v in resumen.items() if k != "UNKNOWN"]
    filas.sort(key=lambda t: -t[1]["count"])
    print(f"  {'#':>2} {'plataforma':20} {'fuentes':>7} {'%':>6}  {'estrategia':18} prio")
    for i, (k, v) in enumerate(filas[:10], 1):
        print(f"  {i:2} {k:20} {v['count']:7,} {v['percentage']:5.1f}%  "
              f"{v['strategy']:18} {v['priority']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
