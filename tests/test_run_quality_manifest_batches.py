from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from scripts import run_quality_manifest_batches as runner


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_resume_preserves_existing_batch_results(tmp_path: Path, monkeypatch) -> None:
    manifest = tmp_path / "manifest.csv"
    out_dir = tmp_path / "run"
    out_dir.mkdir()
    _write_csv(
        manifest,
        [
            {"source_id": "1", "new_url_listado": "https://one.example"},
            {"source_id": "2", "new_url_listado": "https://two.example"},
        ],
    )
    (out_dir / "batch_checkpoint.json").write_text(
        json.dumps(
            {
                "started_utc": "2026-01-01T00:00:00+00:00",
                "updated_utc": "2026-01-01T00:00:00+00:00",
                "manifest": str(manifest),
                "batch_size": 1,
                "workers": 1,
                "completed_batches": ["batch_0001"],
                "failed_batches": [],
                "timed_out_batches": [],
            }
        ),
        encoding="utf-8",
    )
    _write_csv(
        out_dir / "batch_results.csv",
        [
            {
                "batch_id": "batch_0001",
                "started_utc": "2026-01-01T00:00:00+00:00",
                "finished_utc": "2026-01-01T00:01:00+00:00",
                "sources": "1",
                "returncode": "0",
                "timed_out": "False",
                "out_dir": "batch_0001/run_manifest",
            }
        ],
    )

    monkeypatch.setattr(runner, "run_command", lambda *args, **kwargs: (0, False))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_quality_manifest_batches.py",
            "--manifest",
            str(manifest),
            "--out",
            str(out_dir),
            "--batch-size",
            "1",
            "--workers",
            "1",
            "--resume",
        ],
    )

    assert runner.main() == 0
    rows = runner.read_csv(out_dir / "batch_results.csv")
    assert [row["batch_id"] for row in rows] == ["batch_0001", "batch_0002"]
