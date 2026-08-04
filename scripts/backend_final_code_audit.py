#!/usr/bin/env python3
"""Static inventory and safety audit of the ERETZ backend source tree."""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "_scratch/backend_final_closure/BACKEND_AUDIT"
ROOTS = ("scraper", "scripts", "api", "tests", "migrations")
SECRET_ASSIGNMENT = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|service[_-]?role)\\s*=\\s*['\"][^'\"]+['\"]"
)


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def classify(path: Path) -> str:
    text = path.as_posix().casefold()
    if text.startswith("tests/"):
        return "TEST"
    if text.startswith("migrations/"):
        return "MIGRATION"
    if "run" in path.stem or path.stem in {"main", "__main__"}:
        return "ENTRYPOINT_OR_RUNNER"
    if "scrap" in path.stem or "extract" in path.stem or "parser" in path.stem:
        return "SCRAPER_OR_PARSER"
    if "audit" in path.stem or "validate" in path.stem or "diagnos" in path.stem:
        return "AUDIT_OR_VALIDATION"
    return "BACKEND_MODULE"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc).isoformat()
    inventory: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    counts = Counter()

    paths = []
    for root_name in ROOTS:
        root = ROOT / root_name
        if not root.exists():
            continue
        paths.extend(path for path in root.rglob("*") if path.is_file() and path.suffix in {".py", ".sql"})
    for path in sorted(paths):
        relative = path.relative_to(ROOT)
        raw = path.read_bytes()
        text = raw.decode("utf-8", errors="replace")
        category = classify(relative)
        inventory.append(
            {
                "path": relative.as_posix(),
                "category": category,
                "bytes": len(raw),
                "lines": text.count("\n") + 1,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "tracked": "yes",
            }
        )
        counts[category] += 1
        if path.suffix == ".py":
            try:
                tree = ast.parse(text, filename=str(relative))
            except SyntaxError as exc:
                findings.append(
                    {
                        "path": relative.as_posix(),
                        "line": exc.lineno or 0,
                        "finding": "SYNTAX_ERROR",
                        "severity": "critical",
                        "status": "ACTION_REQUIRED",
                        "detail": str(exc.msg),
                    }
                )
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler):
                    if node.type is None:
                        findings.append(
                            {
                                "path": relative.as_posix(),
                                "line": node.lineno,
                                "finding": "BARE_EXCEPT",
                                "severity": "medium",
                                "status": "REVIEW_REQUIRED",
                                "detail": "bare except may hide failures",
                            }
                        )
                    elif isinstance(node.type, ast.Name) and node.type.id in {"Exception", "BaseException"}:
                        findings.append(
                            {
                                "path": relative.as_posix(),
                                "line": node.lineno,
                                "finding": "BROAD_EXCEPTION",
                                "severity": "low",
                                "status": "REVIEW_REQUIRED",
                                "detail": "broad exception handler",
                            }
                        )
        for line_number, line in enumerate(text.splitlines(), 1):
            lower = line.casefold()
            if "neon_db_url" in lower or "neon.tech" in lower:
                findings.append(
                    {
                        "path": relative.as_posix(),
                        "line": line_number,
                        "finding": "NEON_REFERENCE",
                        "severity": "high",
                        "status": "BLOCKED_FROM_PIPELINE_A",
                        "detail": "legacy/backup Neon reference; must remain unreachable from Pipeline A",
                    }
                )
            if SECRET_ASSIGNMENT.search(line) and "os.getenv" not in line and "test" not in relative.parts:
                findings.append(
                    {
                        "path": relative.as_posix(),
                        "line": line_number,
                        "finding": "POSSIBLE_HARDCODED_SECRET",
                        "severity": "critical",
                        "status": "REVIEW_REQUIRED",
                        "detail": "potential literal credential (value intentionally omitted)",
                    }
                )
            if "max_active_browsers" in lower:
                counts["MAX_ACTIVE_BROWSERS_REFERENCES"] += 1
            if "pipeline b" in lower or "run_b" in lower:
                counts["PIPELINE_B_OR_HISTORICAL_REFERENCES"] += 1

    fields = ["path", "category", "bytes", "lines", "sha256", "tracked"]
    write_csv(out / "backend_file_inventory.csv", inventory, fields)
    finding_fields = ["path", "line", "finding", "severity", "status", "detail"]
    write_csv(out / "backend_findings.csv", findings, finding_fields)
    write_csv(
        out / "entrypoints.csv",
        [row for row in inventory if row["category"] == "ENTRYPOINT_OR_RUNNER"],
        fields,
    )
    write_csv(
        out / "migration_inventory.csv",
        [row for row in inventory if row["category"] == "MIGRATION"],
        fields,
    )
    summary = {
        "generated_utc": generated,
        "files": len(inventory),
        "findings": len(findings),
        "syntax_errors": sum(row["finding"] == "SYNTAX_ERROR" for row in findings),
        "possible_hardcoded_secrets": sum(row["finding"] == "POSSIBLE_HARDCODED_SECRET" for row in findings),
        "neon_references": sum(row["finding"] == "NEON_REFERENCE" for row in findings),
        "bare_excepts": sum(row["finding"] == "BARE_EXCEPT" for row in findings),
        "broad_exceptions": sum(row["finding"] == "BROAD_EXCEPTION" for row in findings),
        "categories": dict(counts),
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "BACKEND_CODE_AUDIT.md").write_text(
        "# Backend code audit\n\n"
        f"Generated UTC: {generated}\n\n"
        f"- Files inventoried: {summary['files']}\n"
        f"- Syntax errors: {summary['syntax_errors']}\n"
        f"- Possible hardcoded secrets: {summary['possible_hardcoded_secrets']}\n"
        f"- Neon references: {summary['neon_references']} (legacy/backup paths; Pipeline A must not reach them)\n"
        f"- Bare except handlers: {summary['bare_excepts']}\n"
        f"- Broad exception handlers: {summary['broad_exceptions']}\n"
        "- Findings are evidence for targeted hardening; mass deletion or broad rewrites were not performed.\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
