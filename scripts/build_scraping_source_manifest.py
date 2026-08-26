#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""El manifest de fuentes que la mision de scraping va a consumir.

Una fila por entidad canonica, con la web que se le pudo demostrar, la evidencia
que lo sostiene y el diagnostico tecnico de si se puede leer. Nada mas: este
artefacto no scrapea ni una propiedad.

Dos reglas gobiernan lo que entra:

  - `ready_for_scraping` solo es verdadero cuando hay dominio demostrado Y el
    sondeo tecnico dijo que se puede leer. Una URL dudosa marcada como lista
    hace que la mision siguiente scrapee al competidor equivocado.

  - lo que no se pudo resolver queda SEARCH_API_PENDING con `needs_external_
    search`, nunca NOT_FOUND. Que falte proveedor de busqueda no es evidencia
    de que la inmobiliaria no tenga web, y confundir las dos cosas cierra la
    puerta a entidades que si la tienen.

Solo lee artefactos.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

MANIFEST_VERSION = "scraping_source_manifest_v1"

# Estados en los que la entidad tiene una web que le pertenece.
CON_WEB = {"OFFICIAL_WEB_VERIFIED", "OFFICIAL_WEB_HIGH_CONFIDENCE"}

# Estados que significan "falta buscar", no "no existe".
PENDIENTE_BUSQUEDA = {"SEARCH_API_PENDING", "SEARCH_SECOND_PASS_REQUIRED",
                      "NO_EXISTING_WEB_DATA", "OFFICIAL_WEB_AMBIGUOUS"}

LISTO = "SCRAPE_SOURCE_READY"


def leer(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    out = []
    for l in ruta.open(encoding="utf-8"):
        l = l.strip()
        if l:
            try:
                out.append(json.loads(l))
            except ValueError:
                pass
    return out


def fila(cid: str, base: dict, res: dict | None, ent: dict) -> dict:
    """Una fila del manifest. `res` es lo resuelto en esta mision, si lo hubo."""
    r = res or {}
    estado = r.get("official_web_status") or base.get("status")
    dominio = r.get("discovered_domain") or (
        base.get("selected_domain") if not res else None)
    oficina = r.get("official_office_page") or base.get("selected_office_page")

    return {
        "canonical_agency_id": cid,
        "canonical_name": base.get("canonical_name") or ent.get("nombre_original"),
        "city": base.get("city"),
        "province": base.get("province"),
        "franchise": base.get("franchise") or ent.get("red_franquicia"),
        "eretz_id": base.get("eretz_id"),
        "eretz_status": base.get("eretz_status"),
        "source_origin": "roomix",
        "previous_url": base.get("previous_url"),
        "previous_url_status": r.get("previous_url_status")
                               or base.get("previous_url_status"),
        "official_domain": dominio,
        "official_office_page": oficina,
        "identity_status": estado,
        "confidence": r.get("confidence") if res else None,
        "identity_score": r.get("identity_score"),
        "positive_evidence": r.get("positive_evidence") or [],
        "negative_evidence": r.get("negative_evidence") or [],
        "candidato_no_confirmado": r.get("candidato_no_confirmado"),
        "veto_del_scoring": r.get("veto_del_scoring"),
        "scrapeability_status": r.get("scrapeability_status")
                                or base.get("scrapeability_status"),
        "platform": r.get("plataforma"),
        "checked_at": r.get("checked_at") or base.get("checked_at"),
        "verifier_version": r.get("verifier_version") or base.get("verifier_version"),
        "scoring_version": r.get("scoring_version"),
        "runner_version": r.get("runner_version"),
        "search_provider": base.get("search_provider"),
        "search_queries_count": base.get("search_queries_count"),
        # Falta buscar no es lo mismo que no existe.
        "needs_external_search": bool(
            r.get("needs_external_search")
            if res else estado in PENDIENTE_BUSQUEDA),
        "ready_for_scraping": bool(
            estado in CON_WEB and dominio
            and (r.get("scrapeability_status") or base.get("scrapeability_status"))
            == LISTO),
        "manifest_version": MANIFEST_VERSION,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--salida",
                    default=r"D:\INMO CAPITAL\SCRAPING_SOURCE_MANIFEST.jsonl")
    a = ap.parse_args()

    dd = Path(a.data_dir)
    ents = {x["stable_id"]: x for x in leer(dd / "crosswalk_final.jsonl")}
    awd = {x["canonical_agency_id"]: x for x in leer(dd / "agency_web_directory.jsonl")}
    res = {x.get("canonical_agency_id"): x
           for x in leer(dd / "web_identity_resolved.jsonl")
           if x.get("canonical_agency_id")}

    filas = [fila(cid, base, res.get(cid), ents.get(cid) or {})
             for cid, base in sorted(awd.items())]

    salida = Path(a.salida)
    tmp = salida.with_suffix(salida.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for f in filas:
            fh.write(json.dumps(f, ensure_ascii=False) + "\n")
    tmp.replace(salida)

    print("### SCRAPING SOURCE MANIFEST ###")
    print(f"  entidades:            {len(filas):,}")
    print(f"  resueltas en esta mision: {len(res):,}\n")

    print("  IDENTIDAD")
    for k, v in Counter(f["identity_status"] for f in filas).most_common():
        print(f"    {str(k):34} {v:5}")

    con = [f for f in filas if f["official_domain"]]
    print(f"\n  con dominio demostrado: {len(con):,}")
    print("\n  SCRAPEABILIDAD (sobre las que tienen dominio)")
    for k, v in Counter(f["scrapeability_status"] for f in con).most_common():
        print(f"    {str(k):34} {v:5}")

    listos = [f for f in filas if f["ready_for_scraping"]]
    pend = [f for f in filas if f["needs_external_search"]]
    print(f"\n  listas para scraping:      {len(listos):,}")
    print(f"  pendientes de busqueda:    {len(pend):,}"
          f"  ({len(pend)/len(filas)*100:.1f}%)")
    print(f"\n  artefacto -> {salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
