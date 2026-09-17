from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_full_coverage_manifests as manifests  # noqa: E402
import audit_duplicate_source_records as duplicate_sources  # noqa: E402
import build_playwright_recovery_manifest as pw_manifest  # noqa: E402
import audit_missing_website_identity as missing_identity  # noqa: E402
import audit_historical_url_recovery as historical_urls  # noqa: E402
import run_production_parser_playwright_recheck as production_pw_recheck  # noqa: E402
import build_safe_url_candidate_recheck as safe_urls  # noqa: E402
import repair_historical_fk_deterministic as fk_repair  # noqa: E402
import run_targeted_coverage_diagnostic as targeted  # noqa: E402
import run_targeted_playwright_diagnostic as targeted_playwright  # noqa: E402
import finalize_playwright_gap_results as finalize_pw_gaps  # noqa: E402


def test_fk_classification_keeps_only_deterministic_non_conflicting_row():
    groups = [{
        "manifest_slug": "agency_one",
        "source_name": "Agency One",
        "expected_inmobiliaria_id": "10",
        "actual_inmobiliaria_id": "20",
    }]
    agencies = {
        10: {"id": 10, "nombre": "Agency One", "web": "https://agency.test", "url_listado": ""},
        20: {"id": 20, "nombre": "Other Agency", "web": "https://other.test", "url_listado": ""},
    }
    base = {
        "fuente_extraccion": "agency_one",
        "current_inmobiliaria_id": 20,
        "expected_inmobiliaria_id": 10,
        "url_normalizada": "",
        "hash_dedup": "hash",
        "normalized_url_conflict": False,
        "hash_conflict": False,
    }
    raw = [
        {**base, "property_id": 1, "url": "https://agency.test/p/1", "exact_url_conflict": False},
        {**base, "property_id": 2, "url": "https://agency.test/p/2", "exact_url_conflict": True},
    ]

    candidates, safe, ambiguous = fk_repair._classify(raw, groups, agencies)

    assert len(candidates) == 2
    assert [row["property_id"] for row in safe] == [1]
    assert ambiguous[0]["classification"] == "blocked_duplicate_at_target"


def test_fk_classification_blocks_duplicate_inside_target_set():
    groups = [{
        "manifest_slug": "agency_one",
        "source_name": "Agency One",
        "expected_inmobiliaria_id": "10",
        "actual_inmobiliaria_id": "20",
    }]
    agencies = {
        10: {"id": 10, "nombre": "Agency One", "web": "https://agency.test", "url_listado": ""},
        20: {"id": 20, "nombre": "Other Agency", "web": "https://other.test", "url_listado": ""},
    }
    row = {
        "fuente_extraccion": "agency_one",
        "current_inmobiliaria_id": 20,
        "expected_inmobiliaria_id": 10,
        "url": "https://agency.test/p/same",
        "url_normalizada": "",
        "hash_dedup": "",
        "exact_url_conflict": False,
        "normalized_url_conflict": False,
        "hash_conflict": False,
    }

    _, safe, ambiguous = fk_repair._classify(
        [{**row, "property_id": 1}, {**row, "property_id": 2}], groups, agencies
    )

    assert safe == []
    assert all(item["target_set_duplicate"] for item in ambiguous)


def test_target_selection_separates_internal_and_external_retryable():
    rows = [
        {
            "source_id": "1",
            "internally_fixable": "True",
            "exclude_from_scraping": "False",
            "current_category": "INTERNAL_ERROR",
        },
        {
            "source_id": "2",
            "internally_fixable": "False",
            "exclude_from_scraping": "False",
            "current_category": "REMOTE_HTTP_ERROR",
        },
        {
            "source_id": "3",
            "internally_fixable": "True",
            "exclude_from_scraping": "True",
            "current_category": "INTERNAL_ERROR",
        },
    ]

    assert targeted._selection(rows, "internal", 0) == [1]
    assert targeted._selection(rows, "external_retryable", 0) == [2]


def test_target_diagnostic_contains_malformed_markup_errors(monkeypatch):
    def fail(_html, _base_url, _max_links):
        raise ValueError("malformed remote markup")

    monkeypatch.setattr(targeted, "_ORIGINAL_DISCOVER_LINKS", fail)
    assert targeted._safe_discover_links("\x00", "https://example.test", 10) == ([], [])


def test_target_diagnostic_reuses_production_detail_url_extractor(monkeypatch):
    monkeypatch.setattr(targeted, "_ORIGINAL_DISCOVER_LINKS", lambda *_args: ([], []))
    html = """
        <article class="property-card">
          <h2>Casa en venta</h2><span>USD 120000</span><span>3 dormitorios</span>
          <button data-href="/propiedad/casa-en-venta-123">Ver ficha</button>
        </article>
    """

    links, pages = targeted._safe_discover_links(html, "https://agency.test/listado", 10)

    assert links == ["https://agency.test/propiedad/casa-en-venta-123"]
    assert pages == []


def test_target_diagnostic_applies_explicit_url_overrides_only():
    sources = [
        {"id": 1, "web": "https://old.test", "url_listado": "https://old.test/list"},
        {"id": 2, "web": "https://two.test", "url_listado": ""},
    ]
    overrides = [{"source_id": "1", "website_url": "https://new.test", "listing_url": "https://new.test/props"}]

    updated = targeted._apply_source_overrides(sources, overrides)

    assert updated[0]["web"] == "https://new.test"
    assert updated[0]["url_listado"] == "https://new.test/props"
    assert updated[1] == sources[1]


def test_target_diagnostic_reclassifies_chunked_transport_error(monkeypatch):
    monkeypatch.setattr(targeted, "_ORIGINAL_PROCESS_HTTP", lambda *_args: {
        "final_status": "unexpected_error",
        "error_subcategory": "unexpected:ChunkedEncodingError",
    })
    result = targeted.process_http({}, {}, "test")
    assert result["final_status"] == "http_error"
    assert result["recommended_next_action"] == "retry_later"


def test_rest_fallback_fetches_only_requested_ids_in_bounded_batches(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.test")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "test-key")
    calls = []

    class Response:
        def __init__(self, rows):
            self._rows = rows

        def raise_for_status(self):
            return None

        def json(self):
            return self._rows

    def fake_get(_session, _url, *, params, headers, timeout):
        calls.append((params, headers, timeout))
        ids = [int(value) for value in params["id"][4:-1].split(",")]
        return Response([{"id": value, "sitio_activo": True} for value in ids])

    monkeypatch.setattr(targeted.requests.Session, "get", fake_get)
    ids = list(range(1, 206))

    rows, checksum = targeted._load_sources_rest(ids)

    assert [row["id"] for row in rows] == ids
    assert len(calls) == 3
    assert all(call[0]["id"].startswith("in.(") for call in calls)
    assert all(call[2] == (20, 45) for call in calls)
    assert len(checksum) == 32


def test_manifest_recovery_and_gap_families_are_explicit():
    assert manifests._recovery_family({"diagnostic_status": "needs_listing_url"}) == "recovered_url"
    assert manifests._recovery_family({"diagnostic_status": "needs_parser"}) == "recovered_parser"
    assert manifests._recovery_family({"diagnostic_status": "needs_cms_strategy"}) == "recovered_strategy"
    assert manifests._gap_family({"final_status": "no_property_links"}, {}) == "parser"
    assert manifests._gap_family({"final_status": "cms_unknown"}, {}) == "strategy"
    assert manifests._gap_family({"final_status": "requires_playwright"}, {}) == "playwright"
    assert manifests._gap_family({"final_status": "timeout"}, {}) == "transient_http"


def test_manifest_retry_merge_keeps_best_available_evidence():
    success = {"final_status": "partial_due_to_cap"}
    parser_gap = {"final_status": "no_property_links"}
    dns = {"final_status": "dns_error"}

    assert manifests._merge_result(parser_gap, success) is success
    assert manifests._merge_result(parser_gap, dns) is parser_gap
    assert manifests._merge_result(dns, parser_gap) is parser_gap


def test_manifest_normalizes_playwright_and_production_recheck_statuses():
    assert manifests._normalize_result({
        "playwright_final_status": "playwright_partial_due_to_cap"
    })["final_status"] == "partial_due_to_cap"
    assert manifests._normalize_result({"final_status": "recovered_parser"})["final_status"] == "success"
    assert manifests._normalize_result({
        "final_status": "external_transport_error"
    })["final_status"] == "dns_external"
    assert manifests._normalize_result({
        "final_status": "external_http_error"
    })["final_status"] == "remote_http_error"
    assert manifests._normalize_result({
        "final_status": "external_timeout"
    })["final_status"] == "remote_http_error"
    assert manifests._normalize_result({
        "final_status": "external_empty"
    })["final_status"] == "external_empty"
    assert manifests._normalize_result({
        "playwright_final_status": "playwright_login_required"
    })["final_status"] == "auth_required"


def test_manifest_final_external_result_overrides_old_internal_gap():
    parser_gap = {"final_status": "no_property_links"}
    transport = {"final_status": "dns_external"}

    assert manifests._merge_result(parser_gap, transport) is transport


def test_manifest_url_final_states_are_external_final():
    assert manifests.RESULT_EXTERNAL_FINAL["missing_listing_url_unrecoverable"] == "MISSING_LISTING_URL_UNRECOVERABLE"
    assert manifests.RESULT_EXTERNAL_FINAL["ssl_external"] == "SSL_EXTERNAL"


def test_manifest_plain_timeout_remains_retryable_until_finalized():
    assert manifests._normalize_result({"final_status": "timeout"})["final_status"] == "timeout"
    assert manifests._gap_family({"final_status": "timeout"}, {}) == "transient_http"


def test_manifest_quality_fix_is_not_automatic_success():
    assert "success_low_quality" not in manifests.SUCCESS_STATUSES


def test_manifest_prohibited_url_covers_regional_and_shared_portals():
    assert manifests._is_prohibited_url("https://www.zonaprop.com.ar/propiedades")
    assert manifests._is_prohibited_url("https://remax.com.ar/comprar-propiedades")
    assert manifests._is_prohibited_url("https://linktr.ee/example")
    assert not manifests._is_prohibited_url("https://agencia.example/propiedades")


def test_manifest_recovered_url_uses_validated_listing_override():
    source = {
        "source_id": "10",
        "nombre": "Agency",
        "website_url": "https://agency.test",
        "current_listing_url": "https://agency.test",
        "requires_playwright": "False",
    }

    row = manifests._manifest_row(
        source,
        "recovered_url",
        "validated",
        "https://agency.test/propiedades",
    )

    assert row["new_url_listado"] == "https://agency.test/propiedades"


def test_duplicate_source_audit_is_fail_closed_for_different_names():
    common = {
        "current_listing_url": "https://shared.test/propiedades/",
        "website_url": "https://shared.test",
        "properties_count": "0",
        "current_category": "INTERNAL_ERROR",
    }
    rows = [
        {**common, "source_id": "1", "nombre": "Alpha Inmobiliaria"},
        {**common, "source_id": "2", "nombre": "Beta Desarrollos"},
    ]

    classified = duplicate_sources.classify(rows)

    assert {row["decision"] for row in classified} == {"manual_shared_url"}
    assert not any(row["eligible"] for row in classified)


def test_duplicate_source_audit_selects_one_compatible_canonical():
    common = {
        "current_listing_url": "https://same.test/propiedades",
        "website_url": "https://same.test",
        "current_category": "SUCCESS_NO_NEW",
    }
    rows = [
        {**common, "source_id": "10", "nombre": "Acme Propiedades", "properties_count": "4"},
        {**common, "source_id": "11", "nombre": "Acme Inmobiliaria", "properties_count": "9"},
    ]

    classified = duplicate_sources.classify(rows)

    canonical = [row for row in classified if row["decision"] == "canonical_source"]
    assert [row["source_id"] for row in canonical] == ["11"]
    assert sum(bool(row["eligible"]) for row in classified) == 1


def test_playwright_checkpoint_filter_is_explicit_and_preserves_status(tmp_path):
    source = tmp_path / "source.jsonl"
    source.write_text(
        '{"source_id": 1, "final_status": "no_property_links"}\n'
        '{"source_id": 2, "final_status": "requires_playwright"}\n',
        encoding="utf-8",
    )
    ids = tmp_path / "ids.csv"
    ids.write_text("source_id\n2\n", encoding="utf-8")
    output = tmp_path / "selected.jsonl"

    count, statuses = targeted_playwright._filter_checkpoint(source, ids, output)

    assert count == 1
    assert statuses == "requires_playwright"
    assert json.loads(output.read_text(encoding="utf-8"))["source_id"] == 2


def test_playwright_manifest_requires_dynamic_evidence():
    gaps = [
        {"source_id": "1", "gap_family": "playwright", "nombre": "One"},
        {"source_id": "2", "gap_family": "parser", "cms_detectado": "wix", "nombre": "Two"},
        {"source_id": "3", "gap_family": "parser", "cms_detectado": "wordpress", "nombre": "Three"},
    ]

    selected = pw_manifest.select(gaps, {}, {})

    assert [row["source_id"] for row in selected] == ["1", "2"]


def test_missing_website_identity_requires_location_compatibility():
    universe = [
        {"source_id": "1", "nombre": "Acme Propiedades", "website_url": "", "current_listing_url": ""},
        {"source_id": "2", "nombre": "Acme Inmobiliaria", "website_url": "https://acme.test", "current_listing_url": ""},
    ]
    compatible = {
        1: {"ciudad": "Rosario", "provincia": "Santa Fe"},
        2: {"ciudad": "Rosario", "provincia": "Santa Fe"},
    }
    incompatible = {
        1: {"ciudad": "Rosario", "provincia": "Santa Fe"},
        2: {"ciudad": "Cordoba", "provincia": "Cordoba"},
    }

    assert missing_identity.classify(universe, compatible)[0]["decision"] == "duplicate_source_record"
    assert missing_identity.classify(universe, incompatible)[0]["decision"] == "manual_identity_review"


def test_historical_url_recovery_requires_same_id_name_and_unique_domain():
    universe = [
        {"source_id": "1", "nombre": "Acme Propiedades", "website_url": "", "current_listing_url": ""},
        {"source_id": "2", "nombre": "Other", "website_url": "", "current_listing_url": ""},
    ]
    history = [
        ("main.csv", {"id": "1", "nombre": "Acme Inmobiliaria", "web": "https://acme.test", "url_listado": "https://acme.test/propiedades"}),
        ("scraping.csv", {"id": "1", "nombre": "Acme Propiedades", "web": "https://www.acme.test", "url_listado": ""}),
        ("main.csv", {"id": "2", "nombre": "Different", "web": "https://wrong.test", "url_listado": ""}),
    ]

    results = historical_urls.classify(universe, history)

    assert results[0]["confidence"] == "HIGH"
    assert results[0]["proposed_url"] == "https://acme.test/propiedades"
    assert results[1]["confidence"] == "NO_MATCH"


def test_historical_url_recovery_rejects_prohibited_and_ambiguous_domains():
    universe = [{"source_id": "1", "nombre": "Acme", "website_url": "", "current_listing_url": ""}]
    prohibited = [("main.csv", {"id": "1", "nombre": "Acme", "web": "https://zonaprop.com.ar/acme", "url_listado": ""})]
    ambiguous = [
        ("main.csv", {"id": "1", "nombre": "Acme", "web": "https://one.test", "url_listado": ""}),
        ("scraping.csv", {"id": "1", "nombre": "Acme", "web": "https://two.test", "url_listado": ""}),
    ]

    assert historical_urls.classify(universe, prohibited)[0]["confidence"] == "NO_MATCH"
    assert historical_urls.classify(universe, ambiguous)[0]["status"] == "historical_domain_ambiguous"


def test_production_playwright_recheck_parses_rendered_data_url():
    html = """
      <article class="property-card">
        <h2>Departamento en venta</h2><span>USD 90000</span><span>2 ambientes</span>
        <div data-url="/propiedad/departamento-en-venta-321">Ver</div>
      </article>
    """

    links = production_pw_recheck.discover_rendered_property_links(
        html, "https://agency.test/listado"
    )

    assert "https://agency.test/propiedad/departamento-en-venta-321" in links


def test_production_playwright_recheck_classifies_remote_transport_errors():
    error = RuntimeError("Page.goto: net::ERR_NAME_NOT_RESOLVED")
    assert production_pw_recheck.classify_exception(error)[0] == "external_transport_error"
    disconnected = RuntimeError("Page.goto: net::ERR_INTERNET_DISCONNECTED")
    assert production_pw_recheck.classify_exception(disconnected)[0] == "external_transport_error"
    changed = RuntimeError("Page.goto: net::ERR_NETWORK_CHANGED")
    assert production_pw_recheck.classify_exception(changed)[0] == "external_transport_error"
    empty = RuntimeError("Page.goto: net::ERR_EMPTY_RESPONSE")
    assert production_pw_recheck.classify_exception(empty)[0] == "external_transport_error"
    reset = RuntimeError("Page.goto: net::ERR_CONNECTION_RESET")
    assert production_pw_recheck.classify_exception(reset)[0] == "external_transport_error"
    assert production_pw_recheck.classify_exception(TimeoutError("late"))[0] == "timeout"


def test_production_playwright_recheck_loads_gap_csv_with_exclusions(tmp_path):
    gaps = tmp_path / "gaps.csv"
    gaps.write_text(
        "source_id,nombre,website_url,current_listing_url,gap_family,current_http_status\n"
        "1,One,https://one.test,,strategy,cms_unknown\n"
        "2,Two,https://two.test,,url,bad_listing_url\n"
        "3,Three,https://three.test,,parser,no_property_links\n",
        encoding="utf-8",
    )

    rows = production_pw_recheck._load_input(gaps, {"strategy", "parser"}, {3})

    assert [row["source_id"] for row in rows] == [1]
    assert rows[0]["listing_url"] == "https://one.test"


def test_finalize_playwright_gap_results_prefers_retry_and_closes_externals():
    broad = {
        1: {"source_id": 1, "final_status": "internal_error", "error_type": "ERR_INTERNET_DISCONNECTED"},
        2: {"source_id": 2, "final_status": "still_no_property_links"},
        3: {"source_id": 3, "final_status": "timeout"},
    }
    retry = {
        1: {"source_id": 1, "final_status": "recovered_parser"},
    }

    rows = finalize_pw_gaps.choose_result(broad, retry)
    by_id = {row["source_id"]: row for row in rows}

    assert by_id[1]["final_status"] == "recovered_parser"
    # Zero observed links proves neither an empty source nor complete discovery.
    assert by_id[2]["final_status"] == "no_property_links"
    assert by_id[3]["final_status"] == "external_timeout"


def test_finalize_playwright_gap_results_maps_legacy_playwright_statuses():
    status, reason = finalize_pw_gaps.finalize_status({
        "source_id": 1,
        "playwright_final_status": "playwright_timeout",
    })
    assert status == "external_timeout"
    assert reason == "playwright_status_final"
    status, _reason = finalize_pw_gaps.finalize_status({
        "source_id": 2,
        "playwright_final_status": "playwright_zero_properties",
    })
    assert status == "no_property_links"


def test_finalize_does_not_bless_caps_low_quality_or_parser_errors():
    for raw, expected in (
        ('playwright_partial_due_to_cap', 'partial_due_to_cap'),
        ('playwright_success_low_quality', 'needs_quality_fix'),
        ('playwright_parser_error', 'internal_error'),
    ):
        assert finalize_pw_gaps.finalize_status({'playwright_final_status': raw})[0] == expected


def test_finalize_preserves_retry_only_sources_and_does_not_mutate_evidence():
    retry = {4: {'source_id': 4, 'playwright_final_status': 'playwright_zero_properties'}}
    rows = finalize_pw_gaps.choose_result({}, retry)
    assert rows[0]['source_id'] == 4
    assert rows[0]['final_status'] == 'no_property_links'
    assert 'final_status' not in retry[4]


def test_safe_url_recheck_rejects_details_forms_and_prohibited_portals():
    assert safe_urls.unsafe_candidate("https://agency.test/property.php?idprop=123")
    assert safe_urls.unsafe_candidate("https://agency.test/inmueble/24067")
    assert safe_urls.unsafe_candidate("https://agency.test/ofrecer-mi-inmueble.php")
    assert safe_urls.unsafe_candidate("https://www.zonaprop.com.ar/propiedades")
    assert not safe_urls.unsafe_candidate("https://agency.test/propiedades?operacion=venta")
