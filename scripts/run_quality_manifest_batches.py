#!/usr/bin/env python3
"""Run manifest execute safely in supervised batches.

This wrapper does not write to the database itself. It writes batch CSVs and
calls scripts/run_manifest.py, which owns the Pipeline A write guardrails.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "_scratch" / "full_supabase_data_quality_audit" / "final_quality_run_batches"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def kill_tree(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        proc.kill()


def run_command(cmd: list[str], cwd: Path, timeout_s: int, stdout_path: Path, stderr_path: Path) -> tuple[int | None, bool]:
    with stdout_path.open("w", encoding="utf-8", errors="replace") as out, stderr_path.open("w", encoding="utf-8", errors="replace") as err:
        proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=out, stderr=err, text=True)
        try:
            proc.wait(timeout=timeout_s)
            return proc.returncode, False
        except subprocess.TimeoutExpired:
            kill_tree(proc)
            return None, True


def chunks(rows: list[dict[str, str]], size: int) -> list[list[dict[str, str]]]:
    return [rows[i : i + size] for i in range(0, len(rows), size)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--timeout-minutes", type=int, default=90)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    if args.workers < 1 or args.workers > 2:
        raise RuntimeError("MAX_ACTIVE_BROWSERS=2")
    if args.batch_size < 1:
        raise RuntimeError("--batch-size must be positive")

    manifest = read_csv(args.manifest)
    if args.limit:
        manifest = manifest[: args.limit]
    fields = list(manifest[0].keys()) if manifest else []
    args.out.mkdir(parents=True, exist_ok=True)
    checkpoint_path = args.out / "batch_checkpoint.json"
    results_path = args.out / "batch_results.csv"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8")) if checkpoint_path.exists() and args.resume else {
        "started_utc": utc_now(),
        "updated_utc": utc_now(),
        "manifest": str(args.manifest),
        "batch_size": args.batch_size,
        "workers": args.workers,
        "completed_batches": [],
        "failed_batches": [],
        "timed_out_batches": [],
    }
    done = set(checkpoint.get("completed_batches", [])) if args.resume else set()
    results: list[dict[str, Any]] = read_csv(results_path) if args.resume and results_path.exists() else []

    batch_rows = chunks(manifest, args.batch_size)
    for index, rows in enumerate(batch_rows, start=1):
        batch_id = f"batch_{index:04d}"
        if batch_id in done:
            continue
        batch_dir = args.out / batch_id
        batch_manifest = batch_dir / "manifest.csv"
        write_csv(batch_manifest, rows, fields)
        run_out = batch_dir / "run_manifest"
        cmd = [
            sys.executable,
            "scripts/run_manifest.py",
            "--manifest",
            str(batch_manifest),
            "--execute",
            "--limit",
            str(len(rows)),
            "--workers",
            str(args.workers),
            "--out",
            str(run_out),
        ]
        started = utc_now()
        rc, timed_out = run_command(
            cmd,
            ROOT,
            args.timeout_minutes * 60,
            batch_dir / "stdout.log",
            batch_dir / "stderr.log",
        )
        row = {
            "batch_id": batch_id,
            "started_utc": started,
            "finished_utc": utc_now(),
            "sources": len(rows),
            "returncode": rc,
            "timed_out": timed_out,
            "out_dir": str(run_out),
        }
        results.append(row)
        if timed_out:
            checkpoint.setdefault("timed_out_batches", []).append(batch_id)
        elif rc == 0:
            checkpoint.setdefault("completed_batches", []).append(batch_id)
        else:
            checkpoint.setdefault("failed_batches", []).append(batch_id)
        checkpoint["updated_utc"] = utc_now()
        checkpoint["processed_batches"] = len(checkpoint.get("completed_batches", [])) + len(checkpoint.get("failed_batches", [])) + len(checkpoint.get("timed_out_batches", []))
        checkpoint["total_batches"] = len(batch_rows)
        checkpoint["processed_sources_estimate"] = min(len(manifest), checkpoint["processed_batches"] * args.batch_size)
        write_json(checkpoint_path, checkpoint)
        write_csv(results_path, results, list(results[0].keys()))
        if timed_out:
            break

    return 0 if not checkpoint.get("failed_batches") and not checkpoint.get("timed_out_batches") else 2


if __name__ == "__main__":
    raise SystemExit(main())
