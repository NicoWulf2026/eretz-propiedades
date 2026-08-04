# Migration strategy

The historical SQL files under `migrations/` predate a sequential migration
registry and must not be replayed blindly against production.

For a new environment, restore the sanitized schema baseline captured by the
definitive audit, then apply timestamped files in `supabase/migrations/` in
lexical order. For an existing environment, take a backup, compare the live
catalog with the baseline, and apply only migrations that are absent.

Rollback means restoring the pre-migration schema backup or applying a
reviewed forward migration. Destructive down migrations are intentionally not
automated.

The legacy dependency order established from the SQL is:

1. `supabase_sprint_a_operacion_estado.sql`
2. `phase2_step3_create_schemas.sql`
3. `phase3_internal_scraping_schema.sql`
4. phase A/B error-log migrations
5. `security_containment_phase1.sql`
6. `security_containment_phase2.sql`
7. `property_active_state_and_quality_flags.sql`
8. `property_safe_merge_audit.sql`

The timestamped registry starts after that deployed state. A clean local replay
remains blocked until Supabase CLI or PostgreSQL tooling is available.

