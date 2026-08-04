from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MIGRATION = ROOT / "migrations/security_containment_phase2.sql"


def migration_sql() -> str:
    return MIGRATION.read_text(encoding="utf-8").lower()


def test_phase2_keeps_properties_read_only_for_public_roles():
    sql = migration_sql()

    assert "grant select on public.propiedades to anon, authenticated" in sql
    assert "revoke insert, update, delete" in sql


def test_phase2_preserves_service_role_scraper_rpc():
    sql = migration_sql()

    assert "grant execute on function public.get_existing_hashes(text[]) to service_role" in sql


def test_phase2_contains_backups_and_sensitive_functions():
    sql = migration_sql()

    assert "enable row level security" in sql
    assert "set search_path = public, pg_temp" in sql
    assert "from public, anon, authenticated" in sql


def test_phase2_avoids_destructive_schema_operations():
    sql = "\n".join(
        line for line in migration_sql().splitlines()
        if not line.lstrip().startswith("--")
    )

    assert "\ndrop " not in sql
    assert "\ntruncate " not in sql
