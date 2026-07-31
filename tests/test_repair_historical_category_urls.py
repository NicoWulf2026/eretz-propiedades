import pytest

from scripts import repair_historical_category_urls as repair


def test_cleanup_sql_uses_only_explicit_primary_keys():
    sql = repair.render_explicit_delete([10, 20, 30])

    assert "WHERE id IN (10, 20, 30)" in sql
    assert repair.URL_PREDICATE not in sql


def test_cleanup_sql_fails_closed_for_empty_set():
    sql = repair.render_explicit_delete([])

    assert "DELETE" in sql
    assert "no DELETE is permitted" in sql


def test_category_url_rule_is_closed_to_operation_routes():
    assert "/properties/operation/" in repair.URL_PREDICATE
    assert "forsale|forrent" in repair.URL_PREDICATE


def test_destructive_apply_requires_explicit_human_approval_token():
    with pytest.raises(RuntimeError, match="Destructive apply refused"):
        repair.validate_apply_authorization("apply", None)
    with pytest.raises(RuntimeError, match="Destructive apply refused"):
        repair.validate_apply_authorization("apply", "yes")

    repair.validate_apply_authorization("preflight", None)
    repair.validate_apply_authorization("apply", repair.APPLY_CONFIRMATION)
