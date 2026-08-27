#!/usr/bin/env python
"""Clasifica SEARCH_API_PENDING usando sólo evidencia consolidada y gratuita."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def rows(path: Path):
    for line in path.open(encoding="utf-8"):
        if line.strip():
            yield json.loads(line)


def classify(item: dict) -> tuple[str, list[str]]:
    if item.get("perfil_en_portal_ajeno"):
        return "EXTERNAL_PORTAL_PROFILE", ["host compartido por múltiples inmobiliarias; no es web propia"]
    if item.get("identity_status") == "OFFICIAL_WEB_INACTIVE":
        return "INACTIVE", ["web oficial previamente demostrada, actualmente inactiva"]
    if item.get("official_office_page"):
        return "OFFICIAL_OFFICE_PAGE", ["página oficial dentro de franquicia/red; no es web independiente"]
    if item.get("candidato_no_confirmado") or item.get("dominio_refutado") or item.get("identity_status") == "OFFICIAL_WEB_AMBIGUOUS":
        return "AMBIGUOUS", ["hay evidencia contradictoria o candidata insuficiente"]
    return "SEARCH_PENDING", ["sin proveedor gratuito configurado; no equivale a NOT_FOUND"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--pending", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    pending_ids = {item["canonical_agency_id"] for item in rows(Path(args.pending))}
    manifest = {item["canonical_agency_id"]: item for item in rows(Path(args.manifest))}
    counts: Counter[str] = Counter()
    missing = 0
    destination = output / "SEARCH_API_RESOLUTION.jsonl"
    with destination.open("w", encoding="utf-8") as handle:
        for canonical_id in sorted(pending_ids):
            item = manifest.get(canonical_id)
            if item is None:
                missing += 1
                status, evidence = "SEARCH_PENDING", ["entidad ausente del manifest consolidado"]
                item = {"canonical_agency_id": canonical_id}
            else:
                status, evidence = classify(item)
            counts[status] += 1
            handle.write(json.dumps({
                "canonical_agency_id": canonical_id,
                "canonical_name": item.get("canonical_name"),
                "classification": status,
                "official_domain": item.get("official_domain") if status == "OFFICIAL_WEB" else None,
                "official_office_page": item.get("official_office_page") if status == "OFFICIAL_OFFICE_PAGE" else None,
                "evidence": evidence,
                "paid_external_search_used": False,
            }, ensure_ascii=False, sort_keys=True) + "\n")
    total = sum(counts.values())
    lines = [
        "# SEARCH API RESOLUTION SUMMARY", "",
        f"Universo inicial: **{total:,}**", "",
        "| Clasificación | Entidades |", "| --- | ---: |",
    ]
    for key in ("OFFICIAL_WEB", "OFFICIAL_OFFICE_PAGE", "EXTERNAL_PORTAL_PROFILE", "INACTIVE", "AMBIGUOUS", "NOT_FOUND", "SEARCH_PENDING"):
        lines.append(f"| {key} | {counts.get(key, 0):,} |")
    lines.extend([
        "", f"Suma: **{total:,}**", f"Ausentes del manifest: **{missing:,}**", "",
        "No se usó búsqueda paga ni se convirtió falta de API en `NOT_FOUND`.",
    ])
    (output / "SEARCH_API_RESOLUTION_SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"total": total, "counts": dict(counts), "missing": missing}, sort_keys=True))
    return 0 if total == len(pending_ids) and missing == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
