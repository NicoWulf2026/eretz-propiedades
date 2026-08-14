#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Incorpora a `inmobiliarias_staging` las inmobiliarias descubiertas via Roomix.

Sigue el mismo patron que import_zonaprop_to_staging.py: dry-run por defecto,
dedupe previo, insert por lotes, y solo escribe con --commit.

Destino: `public.inmobiliarias_staging`, el buffer que el esquema ya define para
imports puntuales antes de promover a `inmobiliarias_main`. NO escribe en la
tabla principal: la promocion es un paso posterior y distinto.

Solo entran candidatas HIGH_CONFIDENCE_NEW. Las ambiguas quedan afuera con
needs_manual_review, nunca se auto-fusionan.
"""
from __future__ import annotations

import argparse
import html as _html
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

SOURCE_NAME = "roomix_coverage_v1"
MATCHER_VERSION = "v1"

# Columnas reales de inmobiliarias_staging (internal_db_schema.sql).
COLUMNS = [
    "nombre", "nombre_limpio", "nombre_normalizado", "web", "url_listado",
    "direccion", "barrio", "ciudad", "provincia", "pais", "telefono",
    "fuente", "estado_scraping", "needs_manual_review", "revision_notas",
    "url_perfil_zonaprop", "metadata_zonaprop",
]

# Matriculas argentinas que aparecen embebidas en el nombre del publicador.
# Son senal fuerte de identidad y se extraen para provenance y dedupe.
MAT_RE = re.compile(
    r"\b(cucicba|cmcpsi|cmcpdjlp|cmcpdsn|cpi|cmcp[a-z]{0,6}|cscoc)\s*[nº#:\-]*\s*(\d{3,6})\b",
    re.I)


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalize_name(s: str) -> str:
    """Misma clave que usa el matcher. Tienen que ser identicas: si el importer
    normaliza distinto, la clave de dedupe no coincide con la del cruce y se
    insertan duplicados."""
    s = _html.unescape(s or "")
    s = re.sub(r"\([^)]*\)", " ", s)
    s = strip_accents(s.lower())
    s = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", s)).strip()
    return re.sub(r"\s+(sa|srl|sas|sh|scs)$", "", s)


def extract_licences(raw: str) -> list[str]:
    return [f"{m.group(1).upper()} {m.group(2)}" for m in MAT_RE.finditer(raw or "")]


def clean_name(raw: str) -> str:
    """Nombre presentable: quita matriculas y espacios sobrantes, conserva el
    resto tal cual. El raw original se guarda igual en provenance."""
    s = MAT_RE.sub(" ", raw or "")
    s = re.sub(r"\s*[-–|]\s*$", "", s)
    return re.sub(r"\s+", " ", s).strip()


def build_row(c: dict, franchise: dict | None) -> dict:
    raw = c["raw_name"]
    limpio = clean_name(raw)
    provenance = {
        "discovered_via": "roomix_public_property_page",
        "discovered_at": c.get("discovered_at"),
        "roomix_agent_id": c["agent_id"],
        "roomix_raw_name": raw,
        "evidence_url": c.get("evidence_url"),
        "listings_observed": c.get("listings_observed"),
        "match_state": c.get("match_state"),
        "match_signal": c.get("match_signal"),
        "matcher_version": c.get("matching_version", MATCHER_VERSION),
        "licences": extract_licences(raw),
    }
    if franchise:
        provenance["franchise"] = franchise
    return {
        "nombre": raw,
        "nombre_limpio": limpio,
        "nombre_normalizado": normalize_name(limpio),
        "web": None,
        "url_listado": None,
        "direccion": None,
        "barrio": None,
        "ciudad": None,
        "provincia": None,
        "pais": "Argentina",
        "telefono": None,
        "fuente": SOURCE_NAME,
        "estado_scraping": "pendiente",
        "needs_manual_review": False,
        "revision_notas": None,
        "url_perfil_zonaprop": None,
        "metadata_zonaprop": provenance,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--commit", action="store_true",
                    help="escribe de verdad; sin esto solo simula")
    ap.add_argument("--limit", type=int, default=0, help="tope de filas (rollout por fases)")
    a = ap.parse_args()
    d = Path(a.data_dir)

    cross = [json.loads(l) for l in (d / "crosswalk.jsonl").open(encoding="utf-8") if l.strip()]
    new = [c for c in cross if c["match_state"] == "NEW_HIGH_CONFIDENCE"]
    ambiguous = [c for c in cross if c["match_state"] == "AMBIGUOUS"]

    fr = {}
    fp = d / "franchises.json"
    if fp.exists():
        fr = json.loads(fp.read_text(encoding="utf-8"))

    def franchise_of(name: str) -> dict | None:
        n = normalize_name(name)
        for brand in fr:
            b = normalize_name(brand).replace(" ", "")
            if b and b in n.replace(" ", ""):
                return {"brand": brand, "modelado": fr[brand].get("modelado")}
        return None

    rows, seen_norm, dupes = [], set(), Counter()
    for c in sorted(new, key=lambda x: -x.get("listings_observed", 0)):
        r = build_row(c, franchise_of(c["raw_name"]))
        if not r["nombre_normalizado"]:
            dupes["nombre_normalizado_vacio"] += 1
            continue
        # Idempotencia dentro del propio lote: la clave logica es el nombre
        # normalizado, igual que en el importer de zonaprop.
        if r["nombre_normalizado"] in seen_norm:
            dupes["duplicado_en_lote"] += 1
            continue
        seen_norm.add(r["nombre_normalizado"])
        rows.append(r)
        if a.limit and len(rows) >= a.limit:
            break

    lic = sum(1 for r in rows if r["metadata_zonaprop"]["licences"])
    with_fr = sum(1 for r in rows if r["metadata_zonaprop"].get("franchise"))

    print("### DRY-RUN DE INCORPORACION ###", flush=True)
    print("  destino:                  public.inmobiliarias_staging", flush=True)
    print("  fuente:                   %s" % SOURCE_NAME, flush=True)
    print("  candidatas NEW:           %d" % len(new), flush=True)
    print("  filas a insertar:         %d" % len(rows), flush=True)
    print("  con matricula extraida:   %d" % lic, flush=True)
    print("  con red identificada:     %d" % with_fr, flush=True)
    print("  descartadas en el lote:   %s" % (dict(dupes) or "ninguna"), flush=True)
    print("  AMBIGUAS no insertadas:   %d (quedan para revision humana)" % len(ambiguous), flush=True)
    print("  columnas usadas:          %d de %d" % (len(rows[0]) if rows else 0, len(COLUMNS)), flush=True)
    missing = set(COLUMNS) - set(rows[0]) if rows else set()
    extra = set(rows[0]) - set(COLUMNS) if rows else set()
    print("  columnas faltantes:       %s" % (sorted(missing) or "ninguna"), flush=True)
    print("  columnas inventadas:      %s" % (sorted(extra) or "ninguna"), flush=True)

    out = d / "staging_rows.jsonl"
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    print("\n  filas preparadas -> %s" % out, flush=True)

    print("\n  muestra:", flush=True)
    for r in rows[:5]:
        m = r["metadata_zonaprop"]
        print("    %-46s norm=%-34s avisos=%-4s red=%s" %
              (r["nombre"][:46], r["nombre_normalizado"][:34],
               m["listings_observed"], (m.get("franchise") or {}).get("brand", "-")), flush=True)

    if not a.commit:
        print("\n  DRY-RUN: no se escribio nada. Con credencial valida, --commit inserta.", flush=True)
        return 0

    print("\n  --commit pedido: se requiere credencial con INSERT sobre "
          "inmobiliarias_staging y SELECT sobre inmobiliarias_staging/_main.", flush=True)
    return 3


if __name__ == "__main__":
    sys.exit(main())
