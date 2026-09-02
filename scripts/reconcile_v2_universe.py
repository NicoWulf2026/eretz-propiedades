#!/usr/bin/env python
"""Explain the V1/V2 universe delta and the 6,791 eligibility gap.

All databases are opened read-only.  The report distinguishes the declared
source universe from the structurally eligible subset and the final Supabase
write plan; those are three different populations and must never be compared
as if they were the same gate.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any


def connect_readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def markdown_table(counter: Counter[str], label: str) -> list[str]:
    rows = [f"| {label} | Filas |", "| --- | ---: |"]
    rows.extend(f"| `{key or '(vacío)'}` | {value:,} |" for key, value in counter.most_common())
    return rows


def classify_delta(
    previous: sqlite3.Connection, current: sqlite3.Connection
) -> dict[str, Any]:
    previous_urls = Counter(
        row[0] for row in previous.execute("select source_url from inputs order by seq")
    )
    remaining = previous_urls.copy()
    source_totals: Counter[str] = Counter()
    added_sources: Counter[str] = Counter()
    added_statuses: Counter[str] = Counter()
    added_reasons: Counter[str] = Counter()
    added_connectors: Counter[str] = Counter()
    current_urls: Counter[str] = Counter()
    overlap = 0

    for row in current.execute(
        "select source_group,status,reason,connector,row_json from rows order by seq"
    ):
        record = json.loads(row["row_json"])
        source_url = str(record.get("source_url") or "")
        current_urls[source_url] += 1
        source_totals[row["source_group"]] += 1
        if remaining[source_url] > 0:
            remaining[source_url] -= 1
            overlap += 1
            continue
        added_sources[row["source_group"]] += 1
        added_statuses[row["status"]] += 1
        added_reasons[row["reason"] or "NO_HOLD_REASON"] += 1
        added_connectors[row["connector"] or "unknown"] += 1

    removed = Counter({key: value for key, value in remaining.items() if value})
    added_multiset = sum((current_urls - previous_urls).values())
    removed_multiset = sum((previous_urls - current_urls).values())
    previous_total = sum(previous_urls.values())
    current_total = sum(current_urls.values())
    return {
        "previous_total": previous_total,
        "current_total": current_total,
        "arithmetic_delta": current_total - previous_total,
        "overlap": overlap,
        "added_multiset": added_multiset,
        "removed_multiset": removed_multiset,
        "previous_unique_urls": len(previous_urls),
        "current_unique_urls": len(current_urls),
        "source_totals": source_totals,
        "added_sources": added_sources,
        "added_statuses": added_statuses,
        "added_reasons": added_reasons,
        "added_connectors": added_connectors,
        "removed_examples": list(removed.items())[:20],
    }


def classify_write_gap(
    current: sqlite3.Connection, reconciliation: sqlite3.Connection
) -> dict[str, Any]:
    classifications = Counter(
        dict(reconciliation.execute(
            "select classification,count(*) from results group by classification"
        ))
    )
    eligible = reconciliation.execute("select count(*) from inputs").fetchone()[0]
    conflict_rows = list(reconciliation.execute("""
        select i.hash_dedup,i.connector,r.match_relation,r.match_reason,
               r.conflict_agencies,r.notes
        from inputs i join results r using(seq)
        where r.classification='DUPLICATE_OR_CONFLICT'
    """))
    conflict_hashes = {row["hash_dedup"] for row in conflict_rows}
    by_connector: Counter[str] = Counter(row["connector"] or "unknown" for row in conflict_rows)
    by_match_relation: Counter[str] = Counter(
        row["match_relation"] or "NO_MATCH_RELATION" for row in conflict_rows
    )
    by_match_reason: Counter[str] = Counter(
        row["match_reason"] or "URL_OWNERSHIP_CONFLICT" for row in conflict_rows
    )
    conflict_cardinality: Counter[str] = Counter()
    note_counts: Counter[str] = Counter()
    for row in conflict_rows:
        agencies = json.loads(row["conflict_agencies"])
        conflict_cardinality[str(len(agencies))] += 1
        for note in json.loads(row["notes"]):
            note_counts[note] += 1
    by_source_group: Counter[str] = Counter()
    for row in current.execute(
        "select source_group,hash_dedup from rows where status='CANDIDATE'"
    ):
        if row["hash_dedup"] in conflict_hashes:
            by_source_group[row["source_group"]] += 1
    accounted = sum(classifications.values())
    return {
        "eligible": eligible,
        "classifications": classifications,
        "accounted": accounted,
        "gap": eligible
        - classifications.get("TRULY_NEW", 0)
        - classifications.get("EXISTS_CHANGED", 0)
        - classifications.get("EXISTS_UNCHANGED", 0),
        "by_connector": by_connector,
        "by_source_group": by_source_group,
        "by_match_relation": by_match_relation,
        "by_match_reason": by_match_reason,
        "conflict_cardinality": conflict_cardinality,
        "note_counts": note_counts,
    }


def render(delta: dict[str, Any], gap: dict[str, Any]) -> str:
    classifications = gap["classifications"]
    lines = [
        "# ERETZ — V2 UNIVERSE RECONCILIATION",
        "",
        "## 1. Qué poblaciones se estaban comparando",
        "",
        "`172.201` era el artefacto que había atravesado el write gate histórico. "
        "`189.159` es el universo fuente V2 declarado por las 20 entradas canónicas, "
        "antes de aplicar identidad, calidad, deduplicación y elegibilidad. No son el mismo gate.",
        "",
        "## 2. Reconciliación 172.201 → 189.159",
        "",
        f"- Universo histórico: **{delta['previous_total']:,}**",
        f"- Universo fuente V2: **{delta['current_total']:,}**",
        f"- Diferencia aritmética: **{delta['arithmetic_delta']:,}**",
        f"- Ocurrencias de URL compartidas entre ambos universos: **{delta['overlap']:,}**",
        f"- Ocurrencias incorporadas en V2: **{delta['added_multiset']:,}**",
        f"- Ocurrencias históricas ausentes en V2: **{delta['removed_multiset']:,}**",
        f"- URLs exactas únicas históricas / V2: **{delta['previous_unique_urls']:,} / "
        f"{delta['current_unique_urls']:,}**",
        "",
        "La diferencia no representa una liberación automática para insertar. V2 conserva "
        "el universo completo y manda cada fila agregada a su bucket explícito; el gate "
        "histórico omitía precisamente las filas descartadas o retenidas antes de reconciliar.",
        "",
        "### Entradas canónicas que aportan las ocurrencias incorporadas",
        "",
        *markdown_table(delta["added_sources"], "Entrada"),
        "",
        "### Estado V2 de esas ocurrencias",
        "",
        *markdown_table(delta["added_statuses"], "Estado"),
        "",
        "### Motivo exacto",
        "",
        *markdown_table(delta["added_reasons"], "Motivo"),
        "",
        "Interpretación: `CANDIDATE` identifica una ficha con contrato estructural; "
        "no equivale a `INSERT`. `AGENCY_ID_UNRESOLVED`, `INVALID_OR_REJECTED` y "
        "`DUPLICATE_OR_CONFLICT` permanecen en HOLD con evidencia y nunca son silent drops.",
        "",
        "## 3. Reconciliación de las 45.404 estructuralmente elegibles",
        "",
        f"- DB_WRITE_ELIGIBLE pre-reconciliación: **{gap['eligible']:,}**",
        f"- TRULY_NEW: **{classifications.get('TRULY_NEW', 0):,}**",
        f"- EXISTS_CHANGED: **{classifications.get('EXISTS_CHANGED', 0):,}**",
        f"- EXISTS_UNCHANGED: **{classifications.get('EXISTS_UNCHANGED', 0):,}**",
        f"- DUPLICATE_OR_CONFLICT: **{classifications.get('DUPLICATE_OR_CONFLICT', 0):,}**",
        f"- Suma: **{gap['accounted']:,}**",
        f"- Diferencia 45.404 − nuevas − cambiadas − sin cambios: **{gap['gap']:,}**",
        "",
        "Las **6.791** filas no faltaban: son `DUPLICATE_OR_CONFLICT`. Superaron el gate "
        "local (FK real, contrato, hash y URL únicos dentro del write set), pero al comparar "
        "contra Supabase la misma URL normalizada ya estaba asociada a otra inmobiliaria. "
        "Por política de ownership pasan a `HOLD`; no se elige dueño por similitud.",
        "",
        "### Conflictos por entrada",
        "",
        *markdown_table(gap["by_source_group"], "Entrada"),
        "",
        "### Conflictos por conector",
        "",
        *markdown_table(gap["by_connector"], "Conector"),
        "",
        "### Evidencia de reconciliación",
        "",
        *markdown_table(gap["note_counts"], "Nota"),
        "",
        "## 4. Veredicto",
        "",
        "**PASS CONTABLE — NO AUTORIZA CANARY.**",
        "",
        "Las dos diferencias cierran sin filas inexplicadas. La certificación individual "
        "de fuente e inventario sigue siendo obligatoria antes de promover cualquier "
        "`TRULY_NEW` a un canary.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--previous-database", required=True)
    parser.add_argument("--current-preingestion-database", required=True)
    parser.add_argument("--current-reconciliation-database", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    previous = connect_readonly(Path(args.previous_database))
    current = connect_readonly(Path(args.current_preingestion_database))
    reconciliation = connect_readonly(Path(args.current_reconciliation_database))
    try:
        delta = classify_delta(previous, current)
        gap = classify_write_gap(current, reconciliation)
    finally:
        previous.close()
        current.close()
        reconciliation.close()
    if delta["arithmetic_delta"] != 16_958:
        raise RuntimeError(f"unexpected universe delta: {delta['arithmetic_delta']}")
    if gap["gap"] != 6_791 or gap["accounted"] != gap["eligible"]:
        raise RuntimeError(f"write-set accounting does not close: {gap}")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(delta, gap), encoding="utf-8")
    print(json.dumps({
        "previous": delta["previous_total"],
        "current": delta["current_total"],
        "added": delta["added_multiset"],
        "removed": delta["removed_multiset"],
        "eligible": gap["eligible"],
        "gap": gap["gap"],
        "output": str(output),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
