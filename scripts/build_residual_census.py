#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Censo de las fuentes con web propia que ningun connector intento todavia.

De las 861 que quedaban sin cubrir, 142 no son webs propias -perfiles en
portales y atribuciones ambiguas, que no se ingieren- y 342 simplemente nunca
pasaron por un connector. No hace falta escribir nada nuevo para esas: el
generico ya sabe leer sitemap, schema.org y listados en HTML. Faltaba correrlo.

Distinguir "no la supimos leer" de "nadie la miro" es la mitad del trabajo:
la primera necesita codigo, la segunda necesita una corrida.

Solo lee artefactos.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.build_shape_census import leer, raiz_de  # noqa: E402

WEB_PROPIA = "OFFICIAL_WEB"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--residual", default=r"D:\INMO CAPITAL\RESIDUAL_UNCOVERED.jsonl")
    ap.add_argument("--plataformas",
                    default=r"D:\INMO CAPITAL\agency_platform_directory.jsonl")
    ap.add_argument("--estados", default="NO_INTENTADA",
                    help="connector_status a incluir, separados por coma")
    ap.add_argument("--excluir", nargs="*", default=[],
                    help="censos ya armados: sus fuentes no se repiten aca")
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\CENSO_NO_INTENTADAS.jsonl")
    a = ap.parse_args()

    tipo = {x["canonical_agency_id"]: x.get("web_kind")
            for x in leer(Path(a.plataformas))}
    ya = set()
    for ruta in a.excluir:
        ya |= {x["canonical_agency_id"] for x in leer(Path(ruta))}

    estados = {e.strip() for e in a.estados.split(",") if e.strip()}
    filas, motivos = [], Counter()
    for r in leer(Path(a.residual)):
        cid = r["canonical_agency_id"]
        if r.get("connector_status") not in estados:
            motivos["OTRO_ESTADO"] += 1
            continue
        if tipo.get(cid) != WEB_PROPIA:
            # Un perfil en un portal no tiene inventario propio que ingerir.
            motivos[tipo.get(cid) or "SIN_CLASIFICAR"] += 1
            continue
        if cid in ya:
            motivos["YA_EN_OTRO_CENSO"] += 1
            continue
        base = raiz_de(r.get("domain") or "")
        if not base:
            motivos["SIN_DOMINIO"] += 1
            continue
        eid = r.get("eretz_id")
        filas.append({
            "canonical_agency_id": cid,
            "agency_name": r.get("agency_name"),
            "official_url": base,
            "connector_candidato": "generico",
            "clasificacion_nueva": r.get("platform") or "UNKNOWN",
            "eretz_id": int(eid) if str(eid).isdigit() else None,
            "evidencia": f"web propia, connector_status={r.get('connector_status')}",
        })
        motivos["INCLUIDA"] += 1

    salida = Path(a.salida)
    salida.write_text(
        "".join(json.dumps(f, ensure_ascii=False) + "\n"
                for f in sorted(filas, key=lambda x: x["canonical_agency_id"])),
        encoding="utf-8")

    print("### CENSO DE FUENTES NUNCA INTENTADAS ###")
    for k, v in motivos.most_common():
        print(f"  {k:28} {v:5}")
    print(f"\n  fuentes: {len(filas)}")
    print(f"  con eretz_id real: {sum(1 for f in filas if f['eretz_id'])}")
    print("  plataforma declarada:")
    for k, v in Counter(f["clasificacion_nueva"] for f in filas).most_common(10):
        print(f"    {k:24} {v:4}")
    print(f"\n  artefacto -> {salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
