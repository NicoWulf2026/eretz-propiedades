#!/usr/bin/env python3
"""Build conservative, reviewable resolution manifests without changing Supabase."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit


CLEAR_URL_OWNERS = {
    "red-inmobiliaria.com.ar": {
        "owner": 4579,
        "name": "Red Inmobiliaria",
        "evidence": [
            "el dominio oficial coincide con public.inmobiliarias_main.id=4579",
            "el inventario público existente del dominio está asociado a 4579",
            "la contraparte 1082 corresponde a GKS Ingeniería y no posee inventario de ese dominio",
        ],
    },
    "cosapropiedades.com": {
        "owner": 1600,
        "name": "COSA PROPIEDADES",
        "evidence": [
            "el nombre canónico coincide con public.inmobiliarias_main.id=1600",
            "la contraparte 8618 no existe en public.inmobiliarias_main",
            "no se infiere identidad distinta a partir de variantes www/no-www",
        ],
    },
    "inmobiliariafotheringham.com.ar": {
        "owner": 6540,
        "name": "Inmobiliaria Fotheringham",
        "evidence": [
            "el dominio oficial coincide con public.inmobiliarias_main.id=6540",
            "el inventario público existente del dominio está asociado a 6540",
            "la contraparte 1420 corresponde a Bruzzo Propiedades y no posee inventario de ese dominio",
        ],
    },
}


AGENCY_CLEAR = {
    "roomix:brick propiedades": {
        "eretz_id": 2269,
        "evidence": [
            "nombre exacto y dominio oficial brick.com.ar coinciden",
            "el inventario público existente contiene URLs del mismo dominio bajo id 2269",
        ],
    },
    "roomix:guallini peifer propiedades": {
        "eretz_id": 2515,
        "evidence": [
            "nombre normalizado y dominio oficial guallinipeifer.com coinciden",
            "el inventario público existente contiene URLs del mismo dominio bajo id 2515",
        ],
    },
}


AGENCY_AMBIGUOUS = {
    "roomix:century 21 di girolamo": "el dominio compartido de la franquicia no identifica inequívocamente la oficina en el padrón actual",
    "roomix:century 21 tonat s a": "el dominio compartido de la franquicia no identifica inequívocamente la oficina en el padrón actual",
    "roomix:remax eleva": "inmoup.com.ar es un portal compartido y el candidato nominal encontrado pertenece a otra identidad",
}


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def build_url_resolutions(database: Path, output: Path) -> dict:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    rows = connection.execute("""
        select url_normalizada,
               min(source_url) as sample_url,
               group_concat(distinct inmobiliaria_id) as agencies,
               count(*) as row_count
        from inputs
        group by url_normalizada
        having count(distinct inmobiliaria_id) > 1
        order by url_normalizada
    """)
    counts: Counter[str] = Counter()
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            host = _host(row["sample_url"])
            rule = CLEAR_URL_OWNERS.get(host)
            if rule is None:
                raise RuntimeError(f"colisión sin regla conservadora: {host} {row['url_normalizada']}")
            agencies = sorted(int(value) for value in row["agencies"].split(","))
            if rule["owner"] not in agencies:
                raise RuntimeError(f"owner {rule['owner']} ausente en colisión {row['url_normalizada']}")
            item = {
                "url_normalizada": row["url_normalizada"],
                "owner_agency_id": rule["owner"],
                "owner_name": rule["name"],
                "category": "CLEAR_OWNER",
                "conflict_agency_ids": agencies,
                "input_rows": row["row_count"],
                "evidence": rule["evidence"],
            }
            handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
            counts[host] += 1
    connection.close()
    return {"total": sum(counts.values()), "by_host": dict(sorted(counts.items()))}


def build_agency_resolutions(source: Path, output: Path, report: Path) -> dict:
    counts: Counter[str] = Counter()
    properties: Counter[str] = Counter()
    with source.open(encoding="utf-8") as source_handle, output.open("w", encoding="utf-8") as output_handle:
        for line in source_handle:
            if not line.strip():
                continue
            row = json.loads(line)
            canonical_id = row["canonical_agency_id"]
            if canonical_id in AGENCY_CLEAR:
                resolution = AGENCY_CLEAR[canonical_id]
                status = "RESOLVED"
                eretz_id = resolution["eretz_id"]
                evidence = resolution["evidence"]
            elif canonical_id in AGENCY_AMBIGUOUS:
                status = "AMBIGUOUS"
                eretz_id = None
                evidence = [AGENCY_AMBIGUOUS[canonical_id]]
            else:
                status = "NOT_ENOUGH_EVIDENCE"
                eretz_id = None
                evidence = ["no existe coincidencia inequívoca simultánea de identidad y dominio en la evidencia auditada"]
            discovered = int(row.get("propiedades_descubiertas") or 0)
            output_handle.write(json.dumps({
                "canonical_agency_id": canonical_id,
                "agency_name": row.get("agency_name"),
                "official_domain": row.get("official_domain"),
                "resolution_status": status,
                "eretz_id": eretz_id,
                "properties_discovered": discovered,
                "evidence": evidence,
                "write_set_effect": "REGENERATE_THEN_RECONCILE" if status == "RESOLVED" else "HOLD",
            }, ensure_ascii=False, sort_keys=True) + "\n")
            counts[status] += 1
            properties[status] += discovered
    summary = {
        "agencies_total": sum(counts.values()),
        "properties_total": sum(properties.values()),
        "agencies_by_status": dict(counts),
        "properties_by_status": dict(properties),
    }
    lines = [
        "# AGENCY ID RESOLUTION SUMMARY", "",
        "No se modificó Supabase ni se anexaron filas al write set original.", "",
        "| Estado | Agencias | Propiedades descubiertas |", "| --- | ---: | ---: |",
    ]
    for status in ("RESOLVED", "AMBIGUOUS", "NOT_ENOUGH_EVIDENCE"):
        lines.append(f"| {status} | {counts[status]:,} | {properties[status]:,} |")
    lines.extend([
        f"| **Total** | **{sum(counts.values()):,}** | **{sum(properties.values()):,}** |", "",
        "Las 843 propiedades de las dos agencias resueltas deben regenerarse con su `eretz_id` y atravesar la conciliación completa; no se cargan por atajo.",
    ])
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--agency-pending", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    url_summary = build_url_resolutions(
        args.database, args.output_dir / "CROSS_AGENCY_NORMALIZED_RESOLUTION.jsonl")
    agency_summary = build_agency_resolutions(
        args.agency_pending,
        args.output_dir / "AGENCY_ID_RESOLUTION_FINAL.jsonl",
        args.output_dir / "AGENCY_ID_RESOLUTION_SUMMARY.md",
    )
    print(json.dumps({"url_resolutions": url_summary, "agency_resolutions": agency_summary}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
