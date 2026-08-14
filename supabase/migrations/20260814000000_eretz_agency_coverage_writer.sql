-- ERETZ Agency Coverage: escritor dedicado de privilegio mínimo.
--
-- Crea `eretz_agency_coverage_writer`, cuyo único trabajo es insertar en la
-- tabla de staging de inmobiliarias las candidatas descubiertas por la campaña
-- de cobertura, y leer para deduplicar. No toca ninguna otra tabla.
--
-- La contraseña NO viaja en este archivo. Se asigna en el paso 2 de las
-- instrucciones, dentro del SQL Editor, y no se persiste en el repo.
--
-- Sobre Supabase Hosted: el rol se crea YA con sus atributos definitivos. No se
-- usa `alter role ... nosuperuser`, que falló antes por falta de permisos: un
-- rol creado sin esos atributos nunca los tiene, así que no hay nada que quitar.
--
-- Dónde vive la tabla de staging no se asume: el bloque la busca en `public` y
-- en `internal_scraping` y concede sólo sobre la que exista de verdad.

begin;

-- ---------------------------------------------------------------- 1. Rol
do $role$
begin
  if not exists (select 1 from pg_roles where rolname = 'eretz_agency_coverage_writer') then
    create role eretz_agency_coverage_writer
      login
      nosuperuser
      nocreatedb
      nocreaterole
      noreplication
      nobypassrls
      noinherit
      connection limit 4;
  end if;
end
$role$;

-- Límites de sesión: no son privilegios, así que no requieren superusuario.
alter role eretz_agency_coverage_writer in database postgres set statement_timeout = '60s';
alter role eretz_agency_coverage_writer in database postgres set idle_in_transaction_session_timeout = '30s';
alter role eretz_agency_coverage_writer in database postgres set lock_timeout = '10s';
alter role eretz_agency_coverage_writer in database postgres set search_path = pg_catalog, public;

-- ------------------------------------------------- 2. Superficie mínima
grant connect on database postgres to eretz_agency_coverage_writer;
revoke temporary, create on database postgres from eretz_agency_coverage_writer;

-- Se parte de cero: cualquier privilegio heredado de un estado anterior se
-- retira antes de conceder lo estrictamente necesario.
revoke all on all tables in schema public from eretz_agency_coverage_writer;
revoke all on all sequences in schema public from eretz_agency_coverage_writer;
revoke all on all functions in schema public from eretz_agency_coverage_writer;
revoke create on schema public from eretz_agency_coverage_writer;
grant usage on schema public to eretz_agency_coverage_writer;

-- Lectura para deduplicar contra el padrón canónico. Sólo SELECT.
grant select on table public.inmobiliarias_main to eretz_agency_coverage_writer;

-- --------------------------------- 3. Staging: donde exista realmente
do $staging$
declare
  t regclass;
  seq regclass;
  sch text;
  tbl text;
begin
  -- El esquema del proyecto define la tabla en `internal_scraping`, pero los
  -- importers histórricos la usan vía PostgREST sobre `public`. Se resuelve por
  -- introspección en vez de asumir.
  foreach sch in array array['public', 'internal_scraping'] loop
    t := to_regclass(sch || '.inmobiliarias_staging');
    if t is not null then
      tbl := sch || '.inmobiliarias_staging';

      if sch <> 'public' then
        execute format('grant usage on schema %I to eretz_agency_coverage_writer', sch);
        execute format('revoke create on schema %I from eretz_agency_coverage_writer', sch);
      end if;

      execute format('revoke all on table %s from eretz_agency_coverage_writer', tbl);
      execute format('grant select, insert on table %s to eretz_agency_coverage_writer', tbl);

      -- USAGE sobre la secuencia sólo si la PK realmente la usa. Con IDENTITY o
      -- con un default distinto, no hace falta y no se concede.
      select pg_get_serial_sequence(tbl, a.attname)::regclass into seq
        from pg_attribute a
       where a.attrelid = t
         and a.attnum > 0
         and not a.attisdropped
         and pg_get_serial_sequence(tbl, a.attname) is not null
       limit 1;

      if seq is not null then
        execute format('grant usage on sequence %s to eretz_agency_coverage_writer', seq);
        raise notice 'staging: % (secuencia %)', tbl, seq;
      else
        raise notice 'staging: % (sin secuencia serial; identity o default propio)', tbl;
      end if;

      -- RLS: si está habilitada, el rol necesita policies propias o no ve ni
      -- escribe nada. Se crean sólo para este rol y sólo para lo que necesita.
      if exists (select 1 from pg_class c where c.oid = t and c.relrowsecurity) then
        execute format(
          'drop policy if exists "eretz_agency_coverage_writer_select" on %s', tbl);
        execute format(
          'create policy "eretz_agency_coverage_writer_select" on %s for select to eretz_agency_coverage_writer using (true)', tbl);
        execute format(
          'drop policy if exists "eretz_agency_coverage_writer_insert" on %s', tbl);
        -- Sólo puede insertar filas marcadas con SU fuente: no puede escribir
        -- en nombre de otro import.
        execute format(
          'create policy "eretz_agency_coverage_writer_insert" on %s for insert to eretz_agency_coverage_writer with check (fuente = ''roomix_coverage_v1'')', tbl);
        raise notice 'RLS activa en %: policies creadas para el rol', tbl;
      end if;
    end if;
  end loop;

  if to_regclass('public.inmobiliarias_staging') is null
     and to_regclass('internal_scraping.inmobiliarias_staging') is null then
    raise exception 'No existe inmobiliarias_staging ni en public ni en internal_scraping';
  end if;
end
$staging$;

-- RLS de inmobiliarias_main: el lector necesita policy propia para deduplicar.
do $main$
begin
  if exists (select 1 from pg_class c
              join pg_namespace n on n.oid = c.relnamespace
             where n.nspname = 'public' and c.relname = 'inmobiliarias_main'
               and c.relrowsecurity) then
    drop policy if exists "eretz_agency_coverage_writer_read" on public.inmobiliarias_main;
    create policy "eretz_agency_coverage_writer_read"
      on public.inmobiliarias_main
      for select
      to eretz_agency_coverage_writer
      using (true);
  end if;
end
$main$;

commit;


-- =============================================================================
-- VERIFICACIONES (sólo lectura). Lo esperado está en cada comentario.
-- =============================================================================

-- Atributos del rol.
-- Esperado: canlogin=t y TODO lo demás en f.
select rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
       rolreplication, rolbypassrls, rolinherit, rolconnlimit
  from pg_roles
 where rolname = 'eretz_agency_coverage_writer';

-- Membresías. Esperado: 0 filas.
select r.rolname as miembro_de
  from pg_auth_members m
  join pg_roles r on r.oid = m.roleid
  join pg_roles g on g.oid = m.member
 where g.rolname = 'eretz_agency_coverage_writer';

-- Privilegios de schema. Esperado: usage=t, create=f.
select n.nspname,
       has_schema_privilege('eretz_agency_coverage_writer', n.nspname, 'USAGE')  as usage,
       has_schema_privilege('eretz_agency_coverage_writer', n.nspname, 'CREATE') as create_
  from pg_namespace n
 where n.nspname in ('public', 'internal_scraping');

-- Privilegios de tabla.
-- Esperado: inmobiliarias_main SELECT=t y el resto f;
--           inmobiliarias_staging SELECT=t INSERT=t, UPDATE/DELETE/TRUNCATE=f.
select c.relname,
       has_table_privilege('eretz_agency_coverage_writer', c.oid, 'SELECT')   as sel,
       has_table_privilege('eretz_agency_coverage_writer', c.oid, 'INSERT')   as ins,
       has_table_privilege('eretz_agency_coverage_writer', c.oid, 'UPDATE')   as upd,
       has_table_privilege('eretz_agency_coverage_writer', c.oid, 'DELETE')   as del,
       has_table_privilege('eretz_agency_coverage_writer', c.oid, 'TRUNCATE') as trunc
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
 where c.relname in ('inmobiliarias_main', 'inmobiliarias_staging')
   and c.relkind = 'r';

-- Que no tenga acceso a nada más. Esperado: 0 filas.
select n.nspname, c.relname
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
 where c.relkind = 'r'
   and n.nspname in ('public', 'internal_scraping')
   and c.relname not in ('inmobiliarias_main', 'inmobiliarias_staging')
   and has_table_privilege('eretz_agency_coverage_writer', c.oid, 'SELECT,INSERT,UPDATE,DELETE');

-- Secuencias accesibles. Esperado: sólo la de staging, y sólo si es serial.
select c.relname as secuencia,
       has_sequence_privilege('eretz_agency_coverage_writer', c.oid, 'USAGE') as usage
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
 where c.relkind = 'S'
   and has_sequence_privilege('eretz_agency_coverage_writer', c.oid, 'USAGE');

-- Policies del rol. Esperado: sólo las creadas arriba.
select schemaname, tablename, policyname, cmd
  from pg_policies
 where policyname like 'eretz_agency_coverage_writer%'
 order by tablename, policyname;

-- Forma real de staging: la necesita el loader para no inventar columnas.
select table_schema, column_name, data_type, is_nullable, column_default
  from information_schema.columns
 where table_name = 'inmobiliarias_staging'
 order by table_schema, ordinal_position;

-- Índices únicos de staging: definen la clave de conflicto para el upsert.
select n.nspname, c.relname as tabla, i.relname as indice, idx.indisunique,
       pg_get_indexdef(i.oid) as definicion
  from pg_index idx
  join pg_class c on c.oid = idx.indrelid
  join pg_class i on i.oid = idx.indexrelid
  join pg_namespace n on n.oid = c.relnamespace
 where c.relname = 'inmobiliarias_staging'
   and idx.indisunique;
