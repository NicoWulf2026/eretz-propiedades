#!/usr/bin/env python3
"""Build a conservative URL proposal recheck set from prior evidence."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GAPS = ROOT / "_scratch/codex_full_7004_coverage/partition_identity_safe/manifest_internal_gaps.csv"
DEFAULT_PROPOSALS = ROOT / "_scratch/listing_url_detection_proposal/best_listing_url_proposals.csv"
DEFAULT_OUT = ROOT / "_scratch/codex_full_7004_coverage/url_candidate_recheck_overrides.csv"
PROHIBITED = ("zonaprop.", "argenprop.", "properati.", "remax.", "linktr.ee")
DETAIL_QUERY_KEYS = {"idprop", "id_propiedad", "property_id", "ficha", "codigo", "cod_propiedad"}
NEGATIVE_PATHS = ("ofrecer-mi-inmueble", "publicar-inmueble", "contacto", "tasacion", "blog", "noticia")


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _truth(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "si"}


def _canonical(value: str) -> tuple[str, str, str]:
    parsed = urlsplit(str(value or "").strip())
    return (
        parsed.netloc.lower().removeprefix("www."),
        (parsed.path or "/").rstrip("/") or "/",
        parsed.query.rstrip("&"),
    )


def unsafe_candidate(value: str) -> bool:
    parsed = urlsplit(str(value or "").strip())
    host = parsed.netloc.lower().removeprefix("www.")
    path = (parsed.path or "/").lower().strip("/")
    segments = [item for item in path.split("/") if item]
    query = {key.lower(): values for key, values in parse_qs(parsed.query).items()}
    if any(blocked in host for blocked in PROHIBITED):
        return True
    if any(token in path for token in NEGATIVE_PATHS):
        return True
    if DETAIL_QUERY_KEYS & set(query):
        return True
    basename = segments[-1] if segments else ""
    if basename in {"propiedad.php", "inmueble.php", "ficha.php", "detalle.php"} and query:
        return True
    if segments and segments[0] in {"propiedad", "inmueble", "emprendimiento"}:
        if len(segments) >= 2 and (any(char.isdigit() for char in segments[1]) or len(segments[1].split("-")) >= 3):
            return True
    if segments and segments[0].startswith("prop-") and len(segments) >= 2:
        return True
    return False


def build(gaps: list[dict[str, str]], proposals: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    output = []
    for gap in gaps:
        proposal = proposals.get(gap["source_id"])
        if not proposal:
            continue
        candidate = proposal.get("proposed_listing_url") or ""
        if (
            proposal.get("confidence") != "high"
            or float(proposal.get("score") or 0) < 90
            or int(float(proposal.get("property_links_count") or 0)) < 3
            or str(proposal.get("http_status") or "") != "200"
            or _truth(proposal.get("is_homepage"))
            or _truth(proposal.get("is_property_detail"))
            or _truth(proposal.get("is_prohibited"))
            or not candidate
            or unsafe_candidate(candidate)
            or _canonical(candidate) in {
                _canonical(gap.get("website_url") or ""),
                _canonical(gap.get("current_listing_url") or ""),
            }
        ):
            continue
        output.append({
            "source_id": gap["source_id"],
            "source_name": gap.get("nombre") or "",
            "website_url": gap.get("website_url") or "",
            "listing_url": candidate,
            "current_listing_url": gap.get("current_listing_url") or "",
            "gap_family": gap.get("gap_family") or "",
            "prior_score": proposal.get("score") or "",
            "prior_property_links": proposal.get("property_links_count") or "",
            "prior_evidence": proposal.get("evidence") or "",
        })
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gaps", type=Path, default=DEFAULT_GAPS)
    parser.add_argument("--proposals", type=Path, default=DEFAULT_PROPOSALS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    rows = build(_read(args.gaps), {row["source_id"]: row for row in _read(args.proposals)})
    if len(rows) != len({row["source_id"] for row in rows}):
        raise RuntimeError("Duplicate source_id in URL recheck set")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fields = tuple(rows[0].keys()) if rows else (
        "source_id", "source_name", "website_url", "listing_url", "current_listing_url",
        "gap_family", "prior_score", "prior_property_links", "prior_evidence",
    )
    with args.out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"safe_url_recheck_candidates={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
