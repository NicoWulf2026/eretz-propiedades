from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_active_state_migration_uses_database_enum_value():
    sql = (
        REPO_ROOT / "migrations" / "property_active_state_and_quality_flags.sql"
    ).read_text(encoding="utf-8")
    assert "USING (estado = 'activa')" in sql
    assert "WHERE p.estado = 'activa'" in sql
    assert "property_quality_flag_definitions" in sql
    assert "v_property_quality_flags_v2" in sql


def test_quality_flags_are_transparent_not_an_opaque_score():
    sql = (
        REPO_ROOT / "migrations" / "property_active_state_and_quality_flags.sql"
    ).read_text(encoding="utf-8").lower()
    assert "quality_flags" in sql
    assert "quality_flag_count" in sql
    assert "data_quality_score" not in sql
    assert "missing_operation" in sql
    assert "placeholder_images" in sql


def test_quality_flags_and_rollback_are_non_destructive():
    for name in (
        "property_active_state_and_quality_flags.sql",
        "property_active_state_and_quality_flags_rollback.sql",
    ):
        sql = (REPO_ROOT / "migrations" / name).read_text(encoding="utf-8").upper()
        assert "DROP " not in sql
        assert "TRUNCATE " not in sql
        assert "DELETE " not in sql
