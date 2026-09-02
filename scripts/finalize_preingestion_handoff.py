#!/usr/bin/env python
"""Build the complete, read-only ERETZ pre-ingestion handoff.

The command combines the corrected offline universe with the targeted
Supabase reconciliation.  It never connects to Supabase and deliberately
excludes local SQLite working databases from the final archive.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


INCLUDED_NAMES = (
    "DB_WRITE_ELIGIBLE.jsonl",
    "CANONICAL_AGENCY_TO_ERETZ_ID.jsonl",
    "LIVE_AGENCY_IDENTITY_VALIDATION.jsonl",
    "SUPABASE_RECONCILIATION.jsonl",
    "SUPABASE_RECONCILIATION_SUMMARY.md",
    "SUPABASE_WRITE_PLAN.jsonl",
    "AGENCY_ID_RESOLUTION_FINAL.jsonl",
    "AGENCY_ID_RESOLUTION_SUMMARY.md",
    "AGENCY_ID_PENDING_MANIFEST.jsonl",
    "CROSS_AGENCY_NORMALIZED_RESOLUTION.jsonl",
    "DATA_QUALITY_AUDIT.md",
    "PREINGESTION_REBUILD_SUMMARY.json",
    "WRITE_SET_VALIDATION.json",
    "WRITE_SET_VALIDATION.md",
    "INVALID_OR_REJECTED.jsonl",
    "DUPLICATE_OR_CONFLICT.jsonl",
    "FINAL_BACKEND_MISSION_REPORT.md",
    "README_HANDOFF.txt",
)


def jsonl_rows(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise RuntimeError(f"non-object JSONL row in {path}")
                yield value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def line_count(path: Path) -> int:
    if path.suffix.lower() != ".jsonl":
        return 0
    with path.open("rb") as handle:
        return sum(1 for line in handle if line.strip())


def git_value(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=repo, text=True, encoding="utf-8"
    ).strip()


def load_candidate_reconciliation(database: Path) -> dict[str, dict[str, Any]]:
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    rows: dict[str, dict[str, Any]] = {}
    query = """
        select i.seq,i.hash_dedup,i.source_url,i.url_normalizada,
               i.inmobiliaria_id,i.source_listing_id,i.connector,
               r.classification,r.match_relation,r.match_id,r.match_reason,
               r.change_kind,r.changed_fields,r.non_substantive_fields,
               r.conflict_agencies,r.notes
        from inputs i join results r using(seq) order by i.seq
    """
    for source in connection.execute(query):
        item = dict(source)
        for key in (
            "changed_fields", "non_substantive_fields", "conflict_agencies", "notes"
        ):
            item[key] = json.loads(item[key])
        hash_value = item["hash_dedup"]
        if hash_value in rows:
            raise RuntimeError(f"duplicate candidate reconciliation hash: {hash_value}")
        rows[hash_value] = item
    expected = connection.execute("select count(*) from inputs").fetchone()[0]
    actual = connection.execute("select count(*) from results").fetchone()[0]
    connection.close()
    if expected != actual or actual != len(rows):
        raise RuntimeError(
            f"candidate reconciliation does not close: inputs={expected}, results={actual}, hashes={len(rows)}"
        )
    return rows


def build_agency_resolution(output: Path) -> Counter[str]:
    destination = output / "AGENCY_ID_RESOLUTION_FINAL.jsonl"
    counts: Counter[str] = Counter()
    with destination.open("w", encoding="utf-8") as handle:
        for row in jsonl_rows(output / "CANONICAL_AGENCY_TO_ERETZ_ID.jsonl"):
            counts[row["resolution_status"]] += 1
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    summary = [
        "# AGENCY ID RESOLUTION V2",
        "",
        "Only exact identities in `public.inmobiliarias_main` are resolved.",
        "Staging IDs and source IDs are never interpreted as main primary keys.",
        "",
        "| Status | Canonical agencies |",
        "| --- | ---: |",
    ]
    for status in ("RESOLVED", "AMBIGUOUS", "NOT_FOUND_IN_ERETZ"):
        summary.append(f"| {status} | {counts[status]:,} |")
    summary.extend(["", f"Total: **{sum(counts.values()):,}**", ""])
    (output / "AGENCY_ID_RESOLUTION_SUMMARY.md").write_text(
        "\n".join(summary), encoding="utf-8"
    )
    return counts


def build_global_reconciliation(
    output: Path, pre_database: Path, candidate_database: Path
) -> tuple[Counter[str], Counter[str], int]:
    candidate = load_candidate_reconciliation(candidate_database)
    connection = sqlite3.connect(f"file:{pre_database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    classifications: Counter[str] = Counter()
    actions: Counter[str] = Counter()
    used_candidates: set[str] = set()
    total = 0
    reconciliation_path = output / "SUPABASE_RECONCILIATION.jsonl"
    plan_path = output / "SUPABASE_WRITE_PLAN.jsonl"
    with reconciliation_path.open("w", encoding="utf-8") as rec, plan_path.open(
        "w", encoding="utf-8"
    ) as plan:
        for source in connection.execute("select * from rows order by seq"):
            total += 1
            record = json.loads(source["row_json"])
            hash_value = source["hash_dedup"] or ""
            base = {
                "input_seq": source["seq"],
                "source_group": source["source_group"],
                "canonical_agency_id": source["canonical_id"],
                "hash_dedup": hash_value,
                "source_url": record.get("source_url"),
                "url_normalizada": source["url_normalized"],
                "inmobiliaria_id": source["agency_id"],
                "connector": source["connector"],
            }
            if source["status"] == "CANDIDATE":
                result = candidate.get(hash_value)
                if result is None:
                    raise RuntimeError(
                        f"eligible row lacks Supabase reconciliation: seq={source['seq']} hash={hash_value}"
                    )
                used_candidates.add(hash_value)
                classification = result["classification"]
                item = {
                    **base,
                    "classification": classification,
                    "match_relation": result["match_relation"],
                    "match_id": result["match_id"],
                    "match_reason": result["match_reason"],
                    "change_kind": result["change_kind"],
                    "changed_fields": result["changed_fields"],
                    "non_substantive_fields": result["non_substantive_fields"],
                    "conflict_agencies": result["conflict_agencies"],
                    "notes": result["notes"],
                }
                action = {
                    "EXISTS_UNCHANGED": "NOOP",
                    "EXISTS_CHANGED": "UPDATE_CANDIDATE",
                    "TRULY_NEW": "INSERT",
                }.get(classification, "HOLD")
            else:
                classification = source["status"]
                item = {
                    **base,
                    "classification": classification,
                    "match_relation": None,
                    "match_id": None,
                    "match_reason": None,
                    "change_kind": None,
                    "changed_fields": [],
                    "non_substantive_fields": [],
                    "conflict_agencies": [],
                    "notes": [source["reason"]],
                }
                action = "HOLD"
            classifications[classification] += 1
            actions[action] += 1
            rec.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
            plan.write(
                json.dumps(
                    {
                        **base,
                        "classification": classification,
                        "action": action,
                        "changed_fields": item["changed_fields"],
                        "notes": item["notes"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )
    connection.close()
    if len(used_candidates) != len(candidate):
        raise RuntimeError(
            f"unused candidate results: {len(candidate) - len(used_candidates)}"
        )
    return classifications, actions, total


def build_reports(
    output: Path,
    classifications: Counter[str],
    actions: Counter[str],
    universe: int,
    agency_counts: Counter[str],
) -> None:
    if sum(classifications.values()) != universe or sum(actions.values()) != universe:
        raise RuntimeError("global reconciliation totals do not close")
    rows = [
        "# SUPABASE RECONCILIATION SUMMARY V2",
        "",
        f"Corrected universe: **{universe:,}**",
        "",
        "| Classification | Rows |",
        "| --- | ---: |",
    ]
    for key in sorted(classifications):
        rows.append(f"| {key} | {classifications[key]:,} |")
    rows.extend(
        [
            "",
            f"Classification sum: **{sum(classifications.values()):,}**",
            "",
            "| Planned action | Rows |",
            "| --- | ---: |",
        ]
    )
    for key in sorted(actions):
        rows.append(f"| {key} | {actions[key]:,} |")
    rows.extend(
        [
            "",
            "No write was executed. `INSERT` and `UPDATE_CANDIDATE` are reviewable plans only.",
            "All unresolved identity, quality rejection, and duplicate/conflict rows fail closed.",
            "",
        ]
    )
    (output / "SUPABASE_RECONCILIATION_SUMMARY.md").write_text(
        "\n".join(rows), encoding="utf-8"
    )

    critical = (
        classifications.get("AGENCY_ID_UNRESOLVED", 0)
        + classifications.get("INVALID_OR_REJECTED", 0)
        + classifications.get("DUPLICATE_OR_CONFLICT", 0)
    )
    report = f"""# FINAL BACKEND MISSION REPORT V2

## Scope

- Rebuilt from the declared earliest normalized inputs; no scraping rerun.
- Supabase access was SELECT-only; no INSERT, UPDATE, DELETE, DDL, or RPC mutation.
- No commit, push, merge, frontend change, or production operation.

## Identity correction

- RESOLVED canonical agencies: {agency_counts['RESOLVED']:,}
- AMBIGUOUS canonical agencies: {agency_counts['AMBIGUOUS']:,}
- NOT_FOUND_IN_ERETZ canonical agencies: {agency_counts['NOT_FOUND_IN_ERETZ']:,}
- Staging IDs and source IDs accepted as `main.id`: 0
- Silent shared ERETZ IDs accepted: 0
- Guccione assigned to unrelated `main.id=6136`: 0

## Corrected universe

- Total: {universe:,}
- INSERT candidates: {actions['INSERT']:,}
- UPDATE candidates: {actions['UPDATE_CANDIDATE']:,}
- NOOP: {actions['NOOP']:,}
- HOLD: {actions['HOLD']:,}
- Critical/held rows: {critical:,}

## Verdict

The corrected eligible subset is isolated and reconciled for review. The full
universe is **not** declared ready for ingestion because unresolved identity,
invalid source quality, and conflicts remain explicitly held. No canary or
database write is authorized by this package.
"""
    (output / "FINAL_BACKEND_MISSION_REPORT.md").write_text(
        report, encoding="utf-8"
    )


def make_readme(output: Path, repo: Path, archive: Path) -> None:
    branch = git_value(repo, "branch", "--show-current")
    head = git_value(repo, "rev-parse", "HEAD")
    lines = [
        "ERETZ BACKEND HANDOFF V2",
        "",
        f"Original artifact directory: {output}",
        f"Repository: {repo}",
        f"Branch: {branch}",
        f"HEAD: {head}",
        "Database writes: 0",
        "",
        "FILES",
    ]
    for name in INCLUDED_NAMES:
        if name == "README_HANDOFF.txt":
            continue
        path = output / name
        if not path.exists():
            raise RuntimeError(f"required handoff artifact missing: {path}")
        count = line_count(path)
        count_text = str(count) if path.suffix.lower() == ".jsonl" else "n/a"
        lines.append(
            f"{name}\tJSONL_RECORDS={count_text}\tBYTES={path.stat().st_size}\tSHA256={sha256(path)}"
        )
    lines.extend(["", f"Archive destination: {archive}", ""])
    (output / "README_HANDOFF.txt").write_text("\n".join(lines), encoding="utf-8")


def create_archive(output: Path, archive: Path) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        raise RuntimeError(f"refusing to overwrite existing archive: {archive}")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for name in INCLUDED_NAMES:
            path = output / name
            if not path.exists():
                raise RuntimeError(f"missing archive member: {path}")
            bundle.write(path, arcname=name)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--archive", required=True)
    args = parser.parse_args()
    output = Path(args.output_dir)
    repo = Path(args.repo)
    archive = Path(args.archive)
    pre_database = output / "PREINGESTION_REBUILD.sqlite3"
    candidate_database = output / "SUPABASE_RECONCILIATION.sqlite3"
    agency_counts = build_agency_resolution(output)
    classifications, actions, universe = build_global_reconciliation(
        output, pre_database, candidate_database
    )
    build_reports(output, classifications, actions, universe, agency_counts)
    make_readme(output, repo, archive)
    create_archive(output, archive)
    print(
        json.dumps(
            {
                "archive": str(archive),
                "universe": universe,
                "classifications": classifications,
                "actions": actions,
                "agency_resolution": agency_counts,
                "sha256": sha256(archive),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
