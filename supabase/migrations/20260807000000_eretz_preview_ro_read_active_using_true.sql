-- ERETZ private Preview: the read-only role must see every listing authorized by
-- the private Quality Gate, not only estado='activa'. The public catalog is defined
-- by the Quality Gate (applied in the application layer), so this row-level policy
-- must NOT filter by estado; otherwise gate-visible non-active listings (e.g.
-- 'desconocida' / 'no_detectada_en_ultimo_scraping') are hidden at the database
-- level, undercounting the catalog and 404-ing valid detail pages.
--
-- This change was ALREADY applied manually to the current database; this migration
-- only RECORDS it so the schema history stays reproducible. It is idempotent and
-- SAFE to run: re-running it (here or on a fresh database) is a no-op that leaves the
-- policy at USING (true). It is strictly scoped to this single policy:
--   * only public.propiedades / policy "eretz_preview_ro_read_active"
--   * does not touch any other policy (incl. the inmobiliarias_main publishers one)
--   * does not touch the anon or authenticated roles
--   * does not touch any data
--   * does not rename the policy

begin;

do $$
begin
  if exists (
    select 1
    from pg_policies
    where schemaname = 'public'
      and tablename  = 'propiedades'
      and policyname = 'eretz_preview_ro_read_active'
  ) then
    -- Preserve command (SELECT); explicitly pin the grantee and relax USING.
    alter policy "eretz_preview_ro_read_active" on public.propiedades
      to eretz_preview_ro
      using (true);
  else
    -- Fresh database that has not yet created the policy: create it already correct.
    create policy "eretz_preview_ro_read_active"
      on public.propiedades
      for select
      to eretz_preview_ro
      using (true);
  end if;
end
$$;

commit;
