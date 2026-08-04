#!/usr/bin/env python3
"""Persist local autonomous-run checkpoints without touching any database."""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import psutil


LOCAL_TZ = ZoneInfo("America/Buenos_Aires")


def parse_progress(text: str) -> dict[str, int]:
    patterns = {
        "processed": r"Procesadas\s*\|\s*\*{0,2}(\d+)",
        "total": r"Con FK \(elegibles\)\s*\|\s*\*{0,2}(\d+)",
        "inserted": r"Insertadas\s*\|\s*\*{0,2}(\d+)",
    }
    result = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text, flags=re.IGNORECASE)
        result[key] = int(match.group(1)) if match else 0
    return result


def update_status(path: Path, pid: int, run_id: str, metrics: dict[str, int], state: str) -> None:
    text = path.read_text(encoding="utf-8")
    now = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M America/Buenos_Aires")
    replacements = {
        r"(?m)^- Updated:.*$": f"- Updated: {now}",
        r"(?m)^- State:.*$": f"- State: {state}",
        r"(?m)^- PID:.*$": f"- PID: {pid if state == 'IN_PROGRESS' else 'none'}",
        r"(?m)^- Run ID:.*$": f"- Run ID: {run_id}",
        r"(?m)^- Sources processed:.*$": (
            f"- Sources processed: {metrics['processed']}/{metrics['total']} in current run"
        ),
        r"(?m)^- New properties:.*$": f"- New properties: {metrics['inserted']} in current run",
        r"(?m)^- Last change:.*$": (
            f"- Last change: checkpoint {metrics['processed']}/{metrics['total']}; "
            f"{metrics['inserted']} inserts"
        ),
    }
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text)
    path.write_text(text, encoding="utf-8")


def append_event(
    path: Path,
    run_id: str,
    pid: int,
    metrics: dict[str, int],
    status: str,
    *,
    phase: str = "Fase 13",
    event_prefix: str = "run_a",
) -> None:
    event = {
        "ts": datetime.now(LOCAL_TZ).isoformat(timespec="seconds"),
        "phase": phase,
        "event": f"{event_prefix}_progress" if status == "running" else f"{event_prefix}_process_finished",
        "status": status,
        "details": {"run_id": run_id, "pid": pid, **metrics},
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--progress", type=Path, required=True)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--interval", type=int, default=900)
    parser.add_argument("--phase", default="Fase 13")
    parser.add_argument("--event-prefix", default="run_a")
    args = parser.parse_args()

    while True:
        running = psutil.pid_exists(args.pid)
        progress = args.progress.read_text(encoding="utf-8") if args.progress.exists() else ""
        metrics = parse_progress(progress)
        state = "IN_PROGRESS" if running else "AWAITING_AUDIT"
        update_status(args.status, args.pid, args.run_id, metrics, state)
        append_event(
            args.events,
            args.run_id,
            args.pid,
            metrics,
            "running" if running else "finished",
            phase=args.phase,
            event_prefix=args.event_prefix,
        )
        if not running:
            return 0
        time.sleep(max(60, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
