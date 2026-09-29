-- ERETZ — rol escritor de propiedades de privilegio minimo (politica P18).
--
-- PREPARADO, NO APLICADO. Crear o modificar roles en produccion es una accion
-- productiva: la ejecuta el usuario (o una sesion con autorizacion explicita),
-- despues de backup + restore probados (P12/P19). Runbook:
-- docs/agent/RUNBOOK_ROL_ESCRITOR.md.
--
-- Requiere, en este orden: migrations/phase3_internal_scraping_schema.sql y
-- migrations/property_safe_merge_audit.sql (los RPC seguros). Sin ellos aborta.
--
-- DOS ROLES, A PROPOSITO:
--
--   eretz_direct_property_writer   NOLOGIN. Tiene los privilegios y nada mas:
--       SELECT, INSERT en internal_scraping.propiedades_raw (+ su secuencia) y
--       EXECUTE en los dos RPC seguros (insert_property_safe,
--       apply_property_safe_merge). Ningun privilegio directo sobre
--       public.propiedades: el unico camino a produccion es el RPC (lista
--       blanca, identidad verificada, auditoria en la misma transaccion).
--
--   eretz_property_loader          LOGIN, NOINHERIT. La credencial del cargador.
--       No tiene NINGUN privilegio propio: es miembro del escritor pero, por
--       NOINHERIT, solo lo ejerce despues de `SET LOCAL ROLE
--       eretz_direct_property_writer` dentro de una transaccion.
--
-- Por que no reusar `eretz_preview_ro`: el canario asumia el escritor desde la
-- credencial de SOLO LECTURA del Preview. Para eso ese usuario tiene que ser
-- miembro del escritor, y entonces cualquiera con la credencial del Preview
-- puede escribir. Esta migracion revoca esa membresia si existe.
--
-- La contrasena NO viaja en este archivo. Se fija despues, a mano, fuera del
-- repo (`\password eretz_property_loader`). Sin contrasena el rol no puede
-- entrar.
--
-- DISENO: falla cerrado. Un atributo inesperado, una membresia de mas o un
-- privilegio de escritura fuera de lo previsto abortan la transaccion entera
-- ANTES del commit. Idempotente: correrla dos veces deja lo mismo.

begin;

-- =============================================================================
-- 0. Precondiciones
-- =============================================================================
do $pre$
begin
  if to_regclass('internal_scraping.propiedades_raw') is null then
    raise exception 'falta internal_scraping.propiedades_raw (phase3_internal_scraping_schema.sql)';
  end if;
  if to_regprocedure('public.insert_property_safe(jsonb,text,text,jsonb)') is null
     or to_regprocedure('public.apply_property_safe_merge(bigint,bigint,text,text,text,jsonb,text,text,jsonb)') is null then
    raise exception 'faltan los RPC seguros (property_safe_merge_audit.sql)';
  end if;
end
$pre$;

-- =============================================================================
-- 1. Roles: se crean con sus atributos definitivos; si ya existen se AUDITAN.
-- =============================================================================
do $roles$
declare
  r record;
begin
  -- Escritor: NOLOGIN.
  select * into r from pg_roles where rolname = 'eretz_direct_property_writer';
  if not found then
    create role eretz_direct_property_writer
      nologin nosuperuser nocreatedb nocreaterole noreplication nobypassrls noinherit;
    comment on role eretz_direct_property_writer is
      'created_by: migrations/eretz_property_writer_role.sql (P18)';
  elsif r.rolsuper or r.rolcreatedb or r.rolcreaterole or r.rolreplication
        or r.rolbypassrls or r.rolcanlogin then
    raise exception 'eretz_direct_property_writer existe con atributos inesperados (super=% createdb=% createrole=% repl=% bypassrls=% login=%). Se aborta sin tocarlo.',
      r.rolsuper, r.rolcreatedb, r.rolcreaterole, r.rolreplication, r.rolbypassrls, r.rolcanlogin;
  end if;

  -- Cargador: LOGIN, NOINHERIT, sin contrasena (se fija aparte).
  select * into r from pg_roles where rolname = 'eretz_property_loader';
  if not found then
    create role eretz_property_loader
      login noinherit nosuperuser nocreatedb nocreaterole noreplication nobypassrls
      connection limit 2;
    comment on role eretz_property_loader is
      'created_by: migrations/eretz_property_writer_role.sql (P18)';
  elsif r.rolsuper or r.rolcreatedb or r.rolcreaterole or r.rolreplication
        or r.rolbypassrls or r.rolinherit or not r.rolcanlogin then
    raise exception 'eretz_property_loader existe con atributos inesperados (super=% createdb=% createrole=% repl=% bypassrls=% inherit=% login=%). Se aborta sin tocarlo.',
      r.rolsuper, r.rolcreatedb, r.rolcreaterole, r.rolreplication, r.rolbypassrls, r.rolinherit, r.rolcanlogin;
  end if;
end
$roles$;

-- =============================================================================
-- 2. Membresias: el cargador (y nadie mas) puede asumir el escritor.
-- =============================================================================
do $miembros$
declare
  m record;
begin
  for m in
    select g.rolname as miembro
      from pg_auth_members am
      join pg_roles w on w.oid = am.roleid and w.rolname = 'eretz_direct_property_writer'
      join pg_roles g on g.oid = am.member
     where g.rolname <> 'eretz_property_loader'
  loop
    -- Incluye a eretz_preview_ro si el canario viejo lo habia cableado asi.
    execute format('revoke eretz_direct_property_writer from %I', m.miembro);
    raise notice 'membresia revocada: % ya no puede asumir el escritor', m.miembro;
  end loop;
  -- El escritor no hereda de nadie: una membresia le daria privilegios ajenos.
  if exists (select 1 from pg_auth_members am
               join pg_roles w on w.oid = am.member and w.rolname = 'eretz_direct_property_writer') then
    raise exception 'eretz_direct_property_writer es miembro de otro rol. Se aborta.';
  end if;
  if exists (select 1 from pg_auth_members am
               join pg_roles l on l.oid = am.member and l.rolname = 'eretz_property_loader'
               join pg_roles o on o.oid = am.roleid and o.rolname <> 'eretz_direct_property_writer') then
    raise exception 'eretz_property_loader es miembro de un rol distinto del escritor. Se aborta.';
  end if;
end
$miembros$;

grant eretz_direct_property_writer to eretz_property_loader;

-- =============================================================================
-- 3. Privilegios exactos del escritor (primero se limpia la tabla raw).
-- =============================================================================
revoke all on internal_scraping.propiedades_raw from eretz_direct_property_writer;
grant usage on schema internal_scraping to eretz_direct_property_writer;
grant select, insert on internal_scraping.propiedades_raw to eretz_direct_property_writer;
grant usage on sequence internal_scraping.propiedades_raw_id_seq to eretz_direct_property_writer;

grant execute on function public.insert_property_safe(jsonb, text, text, jsonb)
  to eretz_direct_property_writer;
grant execute on function public.apply_property_safe_merge(
  bigint, bigint, text, text, text, jsonb, text, text, jsonb
) to eretz_direct_property_writer;

-- =============================================================================
-- 4. Validacion: lo que el rol PUEDE y lo que NO. Cualquier desvio aborta.
-- =============================================================================
do $validar$
declare
  n int;
  detalle text;
begin
  -- Puede
  if not (has_table_privilege('eretz_direct_property_writer', 'internal_scraping.propiedades_raw', 'SELECT')
          and has_table_privilege('eretz_direct_property_writer', 'internal_scraping.propiedades_raw', 'INSERT')) then
    raise exception 'el escritor no quedo con SELECT, INSERT sobre raw';
  end if;
  if not has_function_privilege('eretz_direct_property_writer',
       'public.apply_property_safe_merge(bigint,bigint,text,text,text,jsonb,text,text,jsonb)', 'EXECUTE') then
    raise exception 'el escritor no puede ejecutar apply_property_safe_merge';
  end if;

  -- No puede: modificar ni borrar raw
  if has_table_privilege('eretz_direct_property_writer', 'internal_scraping.propiedades_raw', 'UPDATE')
     or has_table_privilege('eretz_direct_property_writer', 'internal_scraping.propiedades_raw', 'DELETE')
     or has_table_privilege('eretz_direct_property_writer', 'internal_scraping.propiedades_raw', 'TRUNCATE') then
    raise exception 'el escritor tiene UPDATE/DELETE/TRUNCATE sobre raw: no es minimo';
  end if;

  -- No puede: escribir ninguna otra tabla (produccion incluida) de forma directa
  select count(*), string_agg(table_schema || '.' || table_name || ':' || privilege_type, ', ')
    into n, detalle
    from information_schema.role_table_grants
   where grantee = 'eretz_direct_property_writer'
     and privilege_type in ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE')
     and not (table_schema = 'internal_scraping' and table_name = 'propiedades_raw');
  if n > 0 then
    raise exception 'el escritor puede escribir fuera de raw: %', detalle;
  end if;
  if to_regclass('public.propiedades') is not null
     and (has_table_privilege('eretz_direct_property_writer', 'public.propiedades', 'INSERT')
          or has_table_privilege('eretz_direct_property_writer', 'public.propiedades', 'UPDATE')
          or has_table_privilege('eretz_direct_property_writer', 'public.propiedades', 'DELETE')) then
    raise exception 'el escritor escribe public.propiedades sin pasar por el RPC';
  end if;

  -- No puede: la funcion interna de auditoria (la llaman los RPC, no el rol)
  if to_regprocedure('public.record_property_merge_audit(bigint,text,text,jsonb)') is not null
     and has_function_privilege('eretz_direct_property_writer',
           'public.record_property_merge_audit(bigint,text,text,jsonb)', 'EXECUTE') then
    raise exception 'el escritor puede escribir auditoria a mano';
  end if;

  -- El cargador no tiene privilegios propios: sin SET ROLE no escribe nada
  if has_table_privilege('eretz_property_loader', 'internal_scraping.propiedades_raw', 'INSERT')
     or has_function_privilege('eretz_property_loader',
          'public.apply_property_safe_merge(bigint,bigint,text,text,text,jsonb,text,text,jsonb)', 'EXECUTE') then
    raise exception 'el cargador escribe sin asumir el escritor (NOINHERIT roto)';
  end if;
  if not pg_has_role('eretz_property_loader', 'eretz_direct_property_writer', 'MEMBER') then
    raise exception 'el cargador no puede asumir el escritor';
  end if;

  -- Nadie publico ni la credencial del Preview puede asumirlo
  if exists (select 1 from pg_roles where rolname = 'eretz_preview_ro')
     and pg_has_role('eretz_preview_ro', 'eretz_direct_property_writer', 'MEMBER') then
    raise exception 'eretz_preview_ro todavia puede asumir el escritor';
  end if;
  if pg_has_role('anon', 'eretz_direct_property_writer', 'MEMBER')
     or pg_has_role('authenticated', 'eretz_direct_property_writer', 'MEMBER') then
    raise exception 'un rol publico puede asumir el escritor';
  end if;
end
$validar$;

commit;
