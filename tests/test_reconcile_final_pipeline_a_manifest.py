from scripts.reconcile_final_pipeline_a_manifest import reconcile


FIELDS = {
    "source_name": "Agency",
    "needs_playwright": "False",
    "scraping_strategy": "html",
}


def row(source_id: int, url: str, **changes: str) -> dict[str, str]:
    return {
        **FIELDS,
        "source_id": str(source_id),
        "inmobiliaria_id": str(source_id),
        "new_url_listado": url,
        **changes,
    }


def test_reconcile_removes_unsafe_sources_and_preserves_canonical() -> None:
    prior = [
        row(1, "https://agency.test/properties"),
        row(2, "https://agency.test/properties"),
        row(3, "https://remax.com.ar/office"),
    ]
    audits = [
        {"source_id": "1", "decision": "canonical_source"},
        {"source_id": "2", "decision": "duplicate_source_record"},
    ]

    final, delta, removed, summary = reconcile(
        prior,
        prior,
        audits,
        {1, 2, 3},
    )

    assert [item["source_id"] for item in final] == ["1"]
    assert delta == []
    assert {item["removal_reason"] for item in removed} == {
        "DUPLICATE_SOURCE_RECORD",
        "PROHIBITED_DOMAIN:remax.com.ar",
    }
    assert summary["final_sources"] == 1
    assert summary["execution_delta_sources"] == 0


def test_reconcile_delta_contains_only_new_or_execution_changed_sources() -> None:
    prior = [row(1, "https://one.test/properties")]
    candidates = [
        row(1, "https://one.test/venta"),
        row(2, "https://two.test/properties"),
    ]

    final, delta, removed, summary = reconcile(
        prior,
        candidates,
        [],
        {1, 2},
    )

    assert len(final) == 2
    assert removed == []
    assert {item["source_id"] for item in delta} == {"1", "2"}
    assert summary["new_sources"] == 1
    assert summary["changed_sources"] == 1


def test_reconcile_removes_both_sides_of_ambiguous_shared_url() -> None:
    candidates = [
        row(1, "https://shared.test/one"),
        row(2, "https://shared.test/two"),
    ]
    audits = [
        {"source_id": "1", "decision": "manual_shared_url"},
        {"source_id": "2", "decision": "manual_shared_url"},
    ]

    final, delta, removed, summary = reconcile(
        candidates,
        candidates,
        audits,
        {1, 2},
    )

    assert final == []
    assert delta == []
    assert len(removed) == 2
    assert summary["ambiguous_shared_url_removed"] == 2
