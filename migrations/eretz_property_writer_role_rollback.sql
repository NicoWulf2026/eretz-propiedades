-- Rollback de migrations/eretz_property_writer_role.sql (P18).
--
-- Deja la base como estaba ANTES de aplicarla:
--   - se van el cargador `eretz_property_loader` y los EXECUTE sobre los RPC;
--   - el escritor vuelve a lo que ya tenia en produccion (SELECT, INSERT en raw);
--     solo se BORRA si lo creo la migracion (lo dice su COMMENT).
-- La membresia de eretz_preview_ro NO se restaura: era el defecto que la
-- migracion corrige. Si hiciera falta, es una decision aparte y explicita.
--
-- Idempotente: sobre una base sin la migracion no cambia nada.

begin;

do $rollback$
declare
  creado_aca text := 'created_by: migrations/eretz_property_writer_role.sql (P18)';
begin
  if exists (select 1 from pg_roles where rolname = 'eretz_property_loader') then
    if shobj_description((select oid from pg_roles where rolname = 'eretz_property_loader'), 'pg_authid')
       is distinct from creado_aca then
      raise exception 'eretz_property_loader no lo creo esta migracion: no se borra';
    end if;
    -- Sin sesiones abiertas: DROP ROLE falla si el rol tiene conexiones o duenos.
    drop role eretz_property_loader;
  end if;

  if exists (select 1 from pg_roles where rolname = 'eretz_direct_property_writer') then
    if to_regprocedure('public.insert_property_safe(jsonb,text,text,jsonb)') is not null then
      revoke execute on function public.insert_property_safe(jsonb, text, text, jsonb)
        from eretz_direct_property_writer;
    end if;
    if to_regprocedure('public.apply_property_safe_merge(bigint,bigint,text,text,text,jsonb,text,text,jsonb)') is not null then
      revoke execute on function public.apply_property_safe_merge(
        bigint, bigint, text, text, text, jsonb, text, text, jsonb) from eretz_direct_property_writer;
    end if;
    if shobj_description((select oid from pg_roles where rolname = 'eretz_direct_property_writer'), 'pg_authid')
       = creado_aca then
      if to_regclass('internal_scraping.propiedades_raw') is not null then
        revoke all on internal_scraping.propiedades_raw from eretz_direct_property_writer;
        revoke usage on sequence internal_scraping.propiedades_raw_id_seq from eretz_direct_property_writer;
      end if;
      revoke usage on schema internal_scraping from eretz_direct_property_writer;
      drop role eretz_direct_property_writer;
    end if;
  end if;
end
$rollback$;

commit;
