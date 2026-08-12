from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT
    / "supabase"
    / "migrations"
    / "20260803230000_harden_postgis_estimated_extent_search_path.sql"
)
ROLLBACK = (
    ROOT
    / "supabase"
    / "rollbacks"
    / "20260803230000_harden_postgis_estimated_extent_search_path.rollback.sql"
)
SIGNATURES = (
    "public.st_estimatedextent(text, text)",
    "public.st_estimatedextent(text, text, text)",
    "public.st_estimatedextent(text, text, text, boolean)",
)


def normalized(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").lower().split())


def test_migration_hardens_exactly_the_three_audited_signatures():
    sql = normalized(MIGRATION)

    assert sql.count("alter function public.st_estimatedextent") == 3
    for signature in SIGNATURES:
        assert f"alter function {signature} set search_path = pg_catalog, public" in sql


def test_migration_is_self_validating_and_does_not_change_acl():
    sql = normalized(MIGRATION)

    assert "expected exactly three security definer" in sql
    assert "search_path=pg_catalog, public" in sql
    assert " grant " not in f" {sql} "
    assert " revoke " not in f" {sql} "
    assert " drop " not in f" {sql} "


def test_rollback_restores_the_exact_absent_search_path_configuration():
    sql = normalized(ROLLBACK)

    assert sql.count("alter function public.st_estimatedextent") == 3
    for signature in SIGNATURES:
        assert f"alter function {signature} reset search_path" in sql
    assert "procedure.proconfig is null" in sql


def test_migration_and_rollback_are_transactional():
    for path in (MIGRATION, ROLLBACK):
        sql = normalized(path)
        assert sql.startswith("begin;")
        assert sql.endswith("commit;")
