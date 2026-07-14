from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest
import requests


REPO_ROOT = Path(__file__).resolve().parents[1]
for path in (REPO_ROOT / "scripts", REPO_ROOT / "scraper"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from run_manifest import _InsertOnlySupabaseProxy, build_fuentes, write_execute_outputs  # noqa: E402
from audit_pipeline_a_writes import _audit_rows  # noqa: E402
from monitor_autonomous_run import parse_progress  # noqa: E402
from run_playwright_listing_dry_run import _normalize_input_row  # noqa: E402
from run_autonomous_manifest_dry_run import (  # noqa: E402
    _check,
    _parse_isolated,
    _sanitize as sanitize_dry_run_error,
)
from run import (  # noqa: E402
    _ACTIVE_BROWSER_SEM,
    _sanitize_source_error,
    calculate_source_hard_cap,
    classify_source_metrics,
)
from playwright_scraper import SAFE_LOAD_MORE_SELECTORS, _goto_safe  # noqa: E402
from clients import SessionFactory  # noqa: E402


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
        ({"pages": 1, "listings_seen": 2, "details_requested": 2, "valid_properties": 2, "db_writes": 1}, "SUCCESS_WITH_DEDUP"),
        ({"pages": 1, "listings_seen": 2, "details_requested": 2, "valid_properties": 2, "db_writes": 0}, "SUCCESS_WITH_DEDUP"),
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


def test_write_audit_resolves_duplicate_slugs_by_canonical_fk():
    manifest = [
        {"source_id": "10", "inmobiliaria_id": "10", "manifest_slug": "same_slug"},
        {"source_id": "20", "inmobiliaria_id": "20", "manifest_slug": "same_slug"},
    ]
    inserted = [{
        "id": 1,
        "inmobiliaria_id": 20,
        "fuente_extraccion": "same_slug",
        "url": "https://example.test/p/1",
        "url_normalizada": "https://example.test/p/1",
        "created_at": "2026-07-12T00:00:00Z",
        "duplicate_exact": False,
        "duplicate_normalized": False,
        "duplicate_hash": False,
    }]
    rows = _audit_rows(inserted, manifest, "test")
    assert rows[0]["source_id_expected"] == "20"
    assert rows[0]["fk_match"] is True


def test_autonomous_monitor_parses_progress_checkpoint():
    metrics = parse_progress(
        "| Con FK (elegibles) | 1252 |\n"
        "| Procesadas | 64 |\n"
        "| Insertadas | **1330** |\n"
    )
    assert metrics == {"processed": 64, "total": 1252, "inserted": 1330}


def test_manifest_timeout_overrides_are_explicitly_propagated():
    source = build_fuentes([{
        "source_id": "10",
        "source_name": "Example",
        "new_url_listado": "https://example.test/list",
        "detail_timeout_ms": "30000",
        "detail_retries": "1",
        "source_no_progress_s": "180",
    }])[0]
    assert source["detail_timeout_ms"] == "30000"
    assert source["detail_retries"] == "1"
    assert source["source_no_progress_s"] == "180"
    assert "listing_timeout_ms" not in source


def test_source_budget_scales_with_work_and_has_absolute_cap():
    assert calculate_source_hard_cap({}, 10) == 1800
    assert calculate_source_hard_cap({}, 250) == 2800
    assert calculate_source_hard_cap({}, 1000) == 5400
    assert calculate_source_hard_cap({"source_hard_cap_s": "3600"}, 1) == 3600


def test_navigation_callback_records_stage_timeout_and_attempt():
    class TimeoutPage:
        def goto(self, *_args, **_kwargs):
            raise RuntimeError("Timeout 20000ms exceeded")

    events = []
    assert not _goto_safe(
        TimeoutPage(),
        "https://example.test/p/1",
        20_000,
        navigation_callback=events.append,
        stage="detail",
        attempt=2,
    )
    assert events[0]["status"] == "timeout"
    assert events[0]["stage"] == "detail"
    assert events[0]["attempt"] == 2
    assert events[0]["timeout_ms"] == 20_000


def test_http_retry_policy_is_bounded_and_uses_short_backoff():
    retry = SessionFactory.make().get_adapter("https://").max_retries
    assert retry.total == 2
    assert retry.connect == 2
    assert retry.read == 1
    assert retry.backoff_factor <= 0.25


def test_playwright_diagnostic_accepts_manifest_schema():
    row = _normalize_input_row({
        "source_id": "10",
        "source_name": "Example",
        "new_url_listado": "https://example.test/list",
    })
    assert row["inmobiliaria_id"] == "10"
    assert row["nombre"] == "Example"
    assert row["url"] == "https://example.test/list"
    assert row["status"] == "PENDING_CONFIRMATION"


def test_scroll_load_more_never_clicks_navigable_text_links():
    joined = " ".join(SAFE_LOAD_MORE_SELECTORS)
    assert 'a:has-text("Ver más")' not in joined
    assert 'a:has-text("Cargar más")' not in joined
    assert all(
        'href="#"' in selector or 'href^="javascript:"' in selector
        for selector in SAFE_LOAD_MORE_SELECTORS
        if selector.startswith("a[")
    )


def test_diagnostic_dry_run_has_no_db_write_calls():
    source = (REPO_ROOT / "scripts" / "run_autonomous_manifest_dry_run.py").read_text(encoding="utf-8")
    assert "batch_save" not in source
    assert ".post(" not in source
    assert ".patch(" not in source
    assert ".delete(" not in source
    assert sanitize_dry_run_error("https://x.test/?token=fake-secret") == "https://x.test/?token=<redacted>"


def test_diagnostic_dry_run_caps_html_before_parsing():
    source = (REPO_ROOT / "scripts" / "run_autonomous_manifest_dry_run.py").read_text(encoding="utf-8")
    assert "MAX_HTML_BYTES = 500_000" in source
    assert "raw_body[:MAX_HTML_BYTES]" in source
    assert "PARSE_TIMEOUT_S = 45" in source
    assert "subprocess.run(" in source
    assert '"--parse-file"' in source
    assert "session.max_redirects = 5" in source


def test_isolated_parser_accepts_utf8_html_on_windows():
    html = '<a href="/propiedad/casa-123">Casa en venta - ❝ única</a>'
    cards, links = _parse_isolated(html, "https://example.test", "1")
    assert cards == 1
    assert links == 1


def test_dry_run_classifies_dns_failure_without_raising(monkeypatch):
    class FailingSession:
        def get(self, *_args, **_kwargs):
            raise requests.exceptions.ConnectionError("dns failed")

        def close(self):
            pass

    monkeypatch.setattr("run_autonomous_manifest_dry_run._session", lambda: FailingSession())
    row = {
        "source_id": "7",
        "inmobiliaria_id": "7",
        "source_name": "Offline",
        "new_url_listado": "https://offline.invalid/list",
    }
    result = _check(row, 1, "test")
    assert result["status"] == "NETWORK_TRANSIENT"
    assert result["error_type"] == "ConnectionError"
    assert result["db_writes"] == 0


def test_playwright_listing_dry_run_is_read_only_and_caps_workers():
    source = (REPO_ROOT / "scripts" / "run_playwright_listing_dry_run.py").read_text(encoding="utf-8")
    assert "batch_save" not in source
    assert ".post(" not in source
    assert ".patch(" not in source
    assert "args.workers <= 2" in source
    assert '"db_writes": 0' in source


@pytest.mark.parametrize(
    "script_name",
    ["analyze_rendered_parser_gaps.py", "build_final_autonomous_manifest.py"],
)
def test_autonomous_audit_helpers_do_not_write_db(script_name):
    source = (REPO_ROOT / "scripts" / script_name).read_text(encoding="utf-8")
    assert ".post(" not in source
    assert ".patch(" not in source
    assert ".delete(" not in source
    assert "UPDATE " not in source
    assert "DELETE FROM" not in source


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
