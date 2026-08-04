from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "supabase" / "migrations"


def test_timestamped_migrations_are_unique_and_ordered():
    names = [path.name for path in MIGRATIONS.glob("*.sql")]
    timestamps = [name.split("_", 1)[0] for name in names]
    assert names
    assert all(timestamp.isdigit() and len(timestamp) == 14 for timestamp in timestamps)
    assert len(timestamps) == len(set(timestamps))
    assert names == sorted(names)


def test_active_state_migration_is_non_destructive_and_self_validating():
    sql = (
        MIGRATIONS / "20260730180000_align_active_state_contract.sql"
    ).read_text(encoding="utf-8").lower()
    assert "alter column estado set default 'activa'" in sql
    assert "using (estado = 'activa')" in sql
    assert "raise exception" in sql
    assert "update public.propiedades" not in sql
    assert "delete from" not in sql
    assert "drop table" not in sql
