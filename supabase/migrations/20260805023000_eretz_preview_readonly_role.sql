-- ERETZ private Preview: least-privilege server-only reader.
--
-- The credential is deliberately absent. On a fresh database this migration
-- creates the role NOLOGIN; the controlled Preview setup activates LOGIN and
-- sends a generated password directly to Vercel without persisting it.

begin;

do $role$
begin
  if not exists (select 1 from pg_roles where rolname = 'eretz_preview_ro') then
    create role eretz_preview_ro
      nologin
      nosuperuser
      nocreatedb
      nocreaterole
      noreplication
      nobypassrls
      noinherit
      connection limit 8;
  end if;
end
$role$;

alter role eretz_preview_ro noinherit nocreatedb nocreaterole connection limit 8;
alter role eretz_preview_ro in database postgres set default_transaction_read_only = on;
alter role eretz_preview_ro in database postgres set statement_timeout = '30s';
alter role eretz_preview_ro in database postgres set idle_in_transaction_session_timeout = '15s';
alter role eretz_preview_ro in database postgres set lock_timeout = '5s';
alter role eretz_preview_ro in database postgres set search_path = pg_catalog, public;

grant connect on database postgres to eretz_preview_ro;
revoke temporary, create on database postgres from eretz_preview_ro;
revoke all on all tables in schema public from eretz_preview_ro;
revoke all on all sequences in schema public from eretz_preview_ro;
revoke all on all functions in schema public from eretz_preview_ro;
revoke create on schema public from eretz_preview_ro;
grant usage on schema public to eretz_preview_ro;
grant select on table public.propiedades, public.inmobiliarias_main to eretz_preview_ro;
revoke all on table public.spatial_ref_sys from eretz_preview_ro;

drop policy if exists "eretz_preview_ro_read_active" on public.propiedades;
create policy "eretz_preview_ro_read_active"
  on public.propiedades
  for select
  to eretz_preview_ro
  using (estado = 'activa'::text);

drop policy if exists "eretz_preview_ro_read_active_publishers" on public.inmobiliarias_main;
create policy "eretz_preview_ro_read_active_publishers"
  on public.inmobiliarias_main
  for select
  to eretz_preview_ro
  using (activa = true);

commit;
