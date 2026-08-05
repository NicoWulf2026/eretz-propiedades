begin;

drop policy if exists "eretz_preview_ro_read_active" on public.propiedades;
drop policy if exists "eretz_preview_ro_read_active_publishers" on public.inmobiliarias_main;

revoke all on table public.propiedades, public.inmobiliarias_main, public.spatial_ref_sys
  from eretz_preview_ro;
revoke all on all sequences in schema public from eretz_preview_ro;
revoke all on all functions in schema public from eretz_preview_ro;
revoke usage on schema public from eretz_preview_ro;
revoke connect on database postgres from eretz_preview_ro;
drop owned by eretz_preview_ro;
drop role if exists eretz_preview_ro;

commit;
