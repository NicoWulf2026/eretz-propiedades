from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
for path in (REPO_ROOT / "scripts", REPO_ROOT / "scraper"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from run_manifest import _InsertOnlySupabaseProxy, write_execute_outputs  # noqa: E402
from run_autonomous_manifest_dry_run import _sanitize as sanitize_dry_run_error  # noqa: E402
from run import (  # noqa: E402
    _ACTIVE_BROWSER_SEM,
    _sanitize_source_error,
    classify_source_metrics,
)


class _FakeClient:
    table = "propiedades"

    def __init__(self) -> None:
        self.inserted = []

    def batch_save_only_new(self, payloads):
        self.inserted.extend(payloads)
        return len(payloads)

    def batch_save_only_changed(self, payloads):  # pragma: no cover - must stay unreachable
        raise AssertionError("PATCH must not be reachable")


def test_active_browser_limit_never_exceeds_two():
    assert _ACTIVE_BROWSER_SEM._capacity <= 2


def test_insert_only_proxy_allows_plain_insert():
    client = _FakeClient()
    proxy = _InsertOnlySupabaseProxy(client)
    assert proxy.batch_save_only_new([{"url": "https://example.test/p/1"}]) == 1
    assert len(client.inserted) == 1


@pytest.mark.parametrize(
    "operation",
    ["batch_save_only_changed", "update_location", "delete", "patch", "deactivate"],
)
def test_insert_only_proxy_blocks_updates_deletes_and_deactivation(operation):
    proxy = _InsertOnlySupabaseProxy(_FakeClient())
    with pytest.raises(RuntimeError, match="Unauthorized Supabase operation"):
        getattr(proxy, operation)


def test_insert_only_proxy_rejects_wrong_table():
    client = _FakeClient()
    client.table = "inmobiliarias_main"
    with pytest.raises(RuntimeError, match="public.propiedades"):
        _InsertOnlySupabaseProxy(client)


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"pages": 1, "listings_seen": 2, "details_requested": 0, "valid_properties": 0, "db_writes": 0}, "SUCCESS_NO_NEW"),
        ({"pages": 1, "listings_seen": 0, "details_requested": 0, "valid_properties": 0, "db_writes": 0}, "PARSER_ERROR"),
        ({"pages": 0, "listings_seen": 0, "details_requested": 0, "valid_properties": 0, "db_writes": 0}, "REMOTE_HTTP_ERROR"),
        ({"pages": 1, "listings_seen": 2, "details_requested": 2, "valid_properties": 2, "db_writes": 2}, "SUCCESS_NEW"),
        ({"pages": 1, "listings_seen": 2, "details_requested": 2, "valid_properties": 0, "db_writes": 0}, "DATA_QUALITY_ERROR"),
    ],
)
def test_source_status_classification(kwargs, expected):
    status, _classification, _error_type, _retryable = classify_source_metrics(
        **kwargs, had_timeout=False, had_error=False, dry_run=False
    )
    assert status == expected


def test_source_status_prioritizes_timeout_and_internal_error():
    common = dict(
        pages=1,
        listings_seen=2,
        details_requested=2,
        valid_properties=2,
        db_writes=2,
        dry_run=False,
    )
    assert classify_source_metrics(**common, had_timeout=True, had_error=False)[0] == "TIMEOUT"
    assert classify_source_metrics(**common, had_timeout=False, had_error=True)[0] == "INTERNAL_ERROR"


def test_source_error_redacts_query_keys_and_bearer_tokens():
    raw = "https://api.test/p?key=fake-secret&x=1 Authorization: Bearer fake.token"
    sanitized = _sanitize_source_error(raw)
    assert "fake-secret" not in sanitized
    assert "fake.token" not in sanitized
    assert sanitized.count("<redacted>") == 2


def test_diagnostic_dry_run_has_no_db_write_calls():
    source = (REPO_ROOT / "scripts" / "run_autonomous_manifest_dry_run.py").read_text(encoding="utf-8")
    assert "batch_save" not in source
    assert ".post(" not in source
    assert ".patch(" not in source
    assert ".delete(" not in source
    assert sanitize_dry_run_error("https://x.test/?token=fake-secret") == "https://x.test/?token=<redacted>"


def test_write_execute_outputs_emits_structured_source_results(tmp_path):
    result = {
        "subset": [{
            "source_id": "10",
            "_manifest_name": "Example",
            "web": "https://example.test/list",
            "_url_source": "new_url_listado",
            "inmobiliaria_id": 10,
        }],
        "fuentes_sin_fk": [],
        "count_before": 0,
        "count_after": 1,
        "total_saved": 1,
        "net_new": 1,
        "new_props": [],
        "worker_results": {"h0": {"saved": 1, "status": "ok"}},
        "workers": 1,
        "limit": 1,
        "batches": 1,
        "source_metrics": [{
            "source_id": "10",
            "inmobiliaria_id": 10,
            "nombre": "Example",
            "started_at": "2026-07-11T10:00:00Z",
            "finished_at": "2026-07-11T10:00:01Z",
            "source_time_s": 1.0,
            "status": "SUCCESS_NEW",
            "classification": "SUCCESS",
            "pages": 1,
            "n_listado": 1,
            "n_nuevas": 1,
            "n_validas": 1,
            "props_saved": 1,
            "duplicates_skipped": 0,
            "had_timeout": False,
            "retryable": False,
        }],
    }
    write_execute_outputs(result, tmp_path, "2026-07-11T10:00:00Z", Path("manifest.csv"))
    with (tmp_path / "source_results.csv").open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1
    assert rows[0]["status"] == "SUCCESS_NEW"
    assert rows[0]["db_writes"] == "1"
    assert rows[0]["inmobiliaria_id"] == "10"
