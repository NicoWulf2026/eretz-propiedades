-- ERETZ Agency Coverage: escritor dedicado de privilegio mínimo.
--
-- Crea `eretz_agency_coverage_writer`, cuyo único trabajo es insertar en la
-- staging canónica de inmobiliarias las candidatas descubiertas por la campaña
-- de cobertura, y leer para deduplicar. No toca ninguna otra tabla.
--
-- La contraseña NO viaja en este archivo ni se genera acá.
--
-- DISEÑO: falla cerrado. Cualquier ambigüedad, atributo inesperado del rol o
-- superficie de escritura indirecta aborta la transacción ANTES del commit. Es
-- preferible no crear el rol a crear uno con más alcance del previsto.
--
-- Sobre Supabase Hosted: el rol se crea con sus atributos definitivos en el
-- CREATE. No se usa `alter role ... nosuperuser`, que falló antes por falta de
-- permisos; un rol que nunca recibió esos atributos no los tiene.

begin;

-- =============================================================================
-- 1. ROL — fail closed si ya existe con atributos inesperados
-- =============================================================================
do $role$
declare
  r record;
  n_mem int;
begin
  select * into r from pg_roles where rolname = 'eretz_agency_coverage_writer';

  if not found then
    create role eretz_agency_coverage_writer
      login
      nosuperuser
      nocreatedb
      nocreaterole
      noreplication
      nobypassrls
      noinherit
      connection limit 4;
    raise notice 'rol creado';
  else
    -- Ya existía: se AUDITA, no se corrige. Un ALTER ROLE sobre atributos
    -- privilegiados requiere permisos que el SQL Editor puede no tener, y
    -- "arreglarlo" en silencio ocultaría que alguien lo dejó distinto.
    if r.rolsuper or r.rolcreatedb or r.rolcreaterole
       or r.rolreplication or r.rolbypassrls or r.rolinherit
       or not r.rolcanlogin then
      raise exception
        'El rol ya existe con atributos inesperados (super=% createdb=% createrole=% repl=% bypassrls=% inherit=% canlogin=%). Se aborta sin tocarlo.',
        r.rolsuper, r.rolcreatedb, r.rolcreaterole,
        r.rolreplication, r.rolbypassrls, r.rolinherit, r.rolcanlogin;
    end if;

    select count(*) into n_mem
      from pg_auth_members m
      join pg_roles g on g.oid = m.member
     where g.rolname = 'eretz_agency_coverage_writer';
    if n_mem > 0 then
      raise exception 'El rol ya pertenece a % rol(es). Se aborta: una membresía puede aportar privilegios no previstos.', n_mem;
    end if;
    raise notice 'rol preexistente verificado';
  end if;
end
$role$;

-- Parámetros de sesión. No son privilegios y no requieren superusuario.
alter role eretz_agency_coverage_writer in database postgres set statement_timeout = '60s';
alter role eretz_agency_coverage_writer in database postgres set idle_in_transaction_session_timeout = '30s';
alter role eretz_agency_coverage_writer in database postgres set lock_timeout = '10s';
alter role eretz_agency_coverage_writer in database postgres set search_path = pg_catalog, public;


-- =============================================================================
-- 2. RESOLVER LA STAGING CANÓNICA — una sola, o se aborta
-- =============================================================================
-- Regla, derivada del código vigente y no de una preferencia:
-- todo lo que ESCRIBE o ENRIQUECE staging (import_zonaprop_to_staging.py,
-- import_excel_cordoba_to_staging.py, enrich_staging_pipeline.py) lo hace por
-- PostgREST sobre /rest/v1/inmobiliarias_staging, y PostgREST expone `public`.
-- `audit_pipeline_a_writes.py` mira las dos, pero sólo para comprobar que nadie
-- escribió: no es un escritor.
-- Por lo tanto la staging canónica para un IMPORT es public.inmobiliarias_staging.
-- Si no existe, se acepta internal_scraping como única alternativa. Nunca las dos.
do $target$
declare
  pub  oid := to_regclass('public.inmobiliarias_staging')::oid;
  intl oid := to_regclass('internal_scraping.inmobiliarias_staging')::oid;
  chosen oid;
  chosen_ns text;
  k "char";
begin
  if pub is null and intl is null then
    raise exception 'No existe inmobiliarias_staging ni en public ni en internal_scraping. Se aborta.';
  elsif pub is not null then
    chosen := pub; chosen_ns := 'public';
    if intl is not null then
      raise notice 'Existen ambas staging. Se elige public por el código: los importers y el enricher escriben por PostgREST, que expone public. internal_scraping NO recibe permisos.';
    end if;
  else
    chosen := intl; chosen_ns := 'internal_scraping';
  end if;

  -- Debe ser una tabla ordinaria o particionada: no se inserta en una vista.
  select relkind into k from pg_class where oid = chosen;
  if k not in ('r', 'p') then
    raise exception 'La staging elegida (%.inmobiliarias_staging) es relkind=%, no una tabla. Se aborta.', chosen_ns, k;
  end if;

  -- La policy de INSERT se apoya en `fuente`. Si no existe, no se inventa.
  if not exists (
    select 1 from pg_attribute
     where attrelid = chosen and attname = 'fuente'
       and attnum > 0 and not attisdropped
  ) then
    raise exception 'La staging elegida (%.inmobiliarias_staging) no tiene columna `fuente`; no se puede acotar el INSERT a esta campaña. Se aborta.', chosen_ns;
  end if;

  -- Se guarda en un parámetro de sesión, no en una tabla temporal: así no
  -- depende de que el editor mande todo el script en una sola transacción.
  perform set_config('eretz.acw_staging_ns', chosen_ns, false);
  raise notice 'staging canónica: %.inmobiliarias_staging', chosen_ns;
end
$target$;


-- =============================================================================
-- 3. LIMPIAR GRANTS DIRECTOS PREVIOS — re-ejecutable sin residuos
-- =============================================================================
-- Se revoca sólo lo concedido DIRECTAMENTE a este rol. No se toca PUBLIC ni
-- ningún otro rol: hacerlo podría romper otros servicios.
do $clean$
declare
  s text;
begin
  foreach s in array array['public', 'internal_scraping'] loop
    if exists (select 1 from pg_namespace where nspname = s) then
      execute format('revoke all on all tables in schema %I from eretz_agency_coverage_writer', s);
      execute format('revoke all on all sequences in schema %I from eretz_agency_coverage_writer', s);
      execute format('revoke all on all functions in schema %I from eretz_agency_coverage_writer', s);
      execute format('revoke all on all routines in schema %I from eretz_agency_coverage_writer', s);
      execute format('revoke all on schema %I from eretz_agency_coverage_writer', s);
    end if;
  end loop;
end
$clean$;

grant connect on database postgres to eretz_agency_coverage_writer;
-- Nota honesta: TEMPORARY sobre la base suele estar concedido a PUBLIC. Este
-- REVOKE quita el grant directo, pero NO garantiza TEMP efectivo = false. No se
-- altera PUBLIC porque afectaría a otros servicios. El aislamiento real de este
-- rol se apoya en no tener privilegios sobre tablas ajenas, no en TEMP.
revoke temporary, create on database postgres from eretz_agency_coverage_writer;


-- =============================================================================
-- 4. CONCEDER LO MÍNIMO
-- =============================================================================
grant usage on schema public to eretz_agency_coverage_writer;
grant select on table public.inmobiliarias_main to eretz_agency_coverage_writer;

do $grant$
declare
  t_ns  text;
  t_oid oid;
  seq   text;
  tbl   text;
begin
  t_ns := current_setting('eretz.acw_staging_ns', true);
  if t_ns is null or t_ns = '' then
    raise exception 'No se resolvió la staging canónica. Ejecutar el script completo, no por partes.';
  end if;
  tbl   := format('%I.%I', t_ns, 'inmobiliarias_staging');
  t_oid := to_regclass(tbl)::oid;

  if t_ns <> 'public' then
    execute format('grant usage on schema %I to eretz_agency_coverage_writer', t_ns);
  end if;

  execute format('grant select, insert on table %s to eretz_agency_coverage_writer', tbl);

  -- Secuencia de la PK. pg_get_serial_sequence resuelve tanto columnas serial
  -- como columnas GENERATED ... AS IDENTITY. Para IDENTITY el motor no exige
  -- USAGE, pero concederlo sobre esa única secuencia no amplía nada relevante y
  -- evita que un INSERT falle si la columna resultara ser serial.
  select pg_get_serial_sequence(tbl, a.attname) into seq
    from pg_attribute a
   where a.attrelid = t_oid and a.attnum > 0 and not a.attisdropped
     and pg_get_serial_sequence(tbl, a.attname) is not null
   order by a.attnum
   limit 1;

  if seq is not null then
    -- Sólo USAGE: alcanza para nextval. Sin SELECT ni UPDATE.
    execute format('grant usage on sequence %s to eretz_agency_coverage_writer', seq);
    raise notice 'secuencia con USAGE: %', seq;
  else
    raise notice 'la PK de la staging no depende de una secuencia: no se concede ninguna';
  end if;

  -- RLS de la staging.
  if exists (select 1 from pg_class where oid = t_oid and relrowsecurity) then
    execute format('drop policy if exists "eretz_agency_coverage_writer_select" on %s', tbl);
    execute format('create policy "eretz_agency_coverage_writer_select" on %s for select to eretz_agency_coverage_writer using (true)', tbl);
    execute format('drop policy if exists "eretz_agency_coverage_writer_insert" on %s', tbl);
    -- Sólo puede insertar filas de SU campaña.
    execute format('create policy "eretz_agency_coverage_writer_insert" on %s for insert to eretz_agency_coverage_writer with check (fuente = ''roomix_coverage_v1'')', tbl);
    raise notice 'RLS activa en %: policies SELECT/INSERT creadas', tbl;
  else
    raise notice 'RLS no activa en %: no se crean policies', tbl;
  end if;
end
$grant$;

-- RLS de inmobiliarias_main: sin policy propia el rol no vería nada y el dedupe
-- daría falsos "nuevos".
do $main$
begin
  if exists (
    select 1 from pg_class c join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'public' and c.relname = 'inmobiliarias_main' and c.relrowsecurity
  ) then
    drop policy if exists "eretz_agency_coverage_writer_read" on public.inmobiliarias_main;
    create policy "eretz_agency_coverage_writer_read"
      on public.inmobiliarias_main
      for select
      to eretz_agency_coverage_writer
      using (true);
  end if;
end
$main$;


-- =============================================================================
-- 5. ASERCIONES DE SEGURIDAD — antes del commit; si algo falla, rollback
-- =============================================================================
do $assert$
declare
  r record;
  t_ns  text;
  t_rel text := 'inmobiliarias_staging';
  t_oid oid;
  n int;
  offenders text;
begin
  t_ns := current_setting('eretz.acw_staging_ns', true);
  if t_ns is null or t_ns = '' then
    raise exception 'No se resolvió la staging canónica. Ejecutar el script completo, no por partes.';
  end if;
  t_oid := to_regclass(format('%I.%I', t_ns, t_rel))::oid;

  -- 5.1 Atributos del rol.
  select * into r from pg_roles where rolname = 'eretz_agency_coverage_writer';
  if r.rolsuper or r.rolcreatedb or r.rolcreaterole or r.rolreplication
     or r.rolbypassrls or r.rolinherit or not r.rolcanlogin then
    raise exception 'ASSERT atributos del rol: estado inesperado';
  end if;

  -- 5.2 Membresías.
  select count(*) into n from pg_auth_members m
    join pg_roles g on g.oid = m.member
   where g.rolname = 'eretz_agency_coverage_writer';
  if n <> 0 then
    raise exception 'ASSERT membresías: se esperaba 0, hay %', n;
  end if;

  -- 5.3 No puede crear objetos en ningún schema.
  select string_agg(nspname, ', ') into offenders
    from pg_namespace
   where nspname not like 'pg\_%'
     and nspname <> 'information_schema'
     and has_schema_privilege('eretz_agency_coverage_writer', nspname, 'CREATE');
  if offenders is not null then
    raise exception 'ASSERT CREATE en schema: el rol puede crear en %', offenders;
  end if;

  -- 5.4 inmobiliarias_main: sólo SELECT.
  if not has_table_privilege('eretz_agency_coverage_writer', 'public.inmobiliarias_main', 'SELECT') then
    raise exception 'ASSERT main: falta SELECT';
  end if;
  if has_table_privilege('eretz_agency_coverage_writer', 'public.inmobiliarias_main', 'INSERT')
     or has_table_privilege('eretz_agency_coverage_writer', 'public.inmobiliarias_main', 'UPDATE')
     or has_table_privilege('eretz_agency_coverage_writer', 'public.inmobiliarias_main', 'DELETE')
     or has_table_privilege('eretz_agency_coverage_writer', 'public.inmobiliarias_main', 'TRUNCATE') then
    raise exception 'ASSERT main: tiene privilegios de escritura';
  end if;

  -- 5.5 Staging: SELECT + INSERT y nada más.
  if not (has_table_privilege('eretz_agency_coverage_writer', t_oid, 'SELECT')
          and has_table_privilege('eretz_agency_coverage_writer', t_oid, 'INSERT')) then
    raise exception 'ASSERT staging: faltan SELECT/INSERT';
  end if;
  if has_table_privilege('eretz_agency_coverage_writer', t_oid, 'UPDATE')
     or has_table_privilege('eretz_agency_coverage_writer', t_oid, 'DELETE')
     or has_table_privilege('eretz_agency_coverage_writer', t_oid, 'TRUNCATE') then
    raise exception 'ASSERT staging: tiene UPDATE/DELETE/TRUNCATE';
  end if;

  -- 5.6 Ninguna otra superficie table-like accesible. Incluye vistas, vistas
  -- materializadas, foreign tables y particionadas, no sólo relkind='r'.
  select string_agg(format('%s.%s(%s)', n.nspname, c.relname, c.relkind), ', ')
    into offenders
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
   where c.relkind in ('r', 'v', 'm', 'f', 'p')
     and n.nspname not in ('pg_catalog', 'information_schema')
     and c.oid <> t_oid
     and c.relname <> 'inmobiliarias_main'
     and has_table_privilege('eretz_agency_coverage_writer', c.oid,
                             'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER');
  if offenders is not null then
    raise exception 'ASSERT otras relaciones: el rol accede a %', left(offenders, 400);
  end if;

  -- 5.7 Grants a nivel columna: pueden dar acceso efectivo mayor que el de tabla.
  select string_agg(format('%s.%s.%s:%s', table_schema, table_name, column_name, privilege_type), ', ')
    into offenders
    from information_schema.column_privileges
   where grantee = 'eretz_agency_coverage_writer'
     and not (table_schema = t_ns and table_name = t_rel)
     and not (table_schema = 'public' and table_name = 'inmobiliarias_main');
  if offenders is not null then
    raise exception 'ASSERT grants por columna inesperados: %', left(offenders, 400);
  end if;

  -- 5.8 Secuencias: sólo la de la staging elegida, si la hubo.
  select string_agg(format('%s.%s', n.nspname, c.relname), ', ') into offenders
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
   where c.relkind = 'S'
     and has_sequence_privilege('eretz_agency_coverage_writer', c.oid, 'USAGE,SELECT,UPDATE')
     and c.oid <> coalesce(
       (select pg_get_serial_sequence(format('%I.%I', t_ns, t_rel), a.attname)::regclass::oid
          from pg_attribute a
         where a.attrelid = t_oid and a.attnum > 0 and not a.attisdropped
           and pg_get_serial_sequence(format('%I.%I', t_ns, t_rel), a.attname) is not null
         order by a.attnum limit 1), 0::oid);
  if offenders is not null then
    raise exception 'ASSERT secuencias inesperadas: %', left(offenders, 300);
  end if;

  -- 5.9 Funciones ejecutables. has_function_privilege considera también lo que
  -- el rol hereda de PUBLIC, así que esto sí audita la superficie efectiva. No
  -- se modifica PUBLIC: se aborta y se informa cuál es la función.
  -- Peligrosas = SECURITY DEFINER (corren con permisos del dueño) o funciones
  -- cuya volatilidad permite escribir (VOLATILE) fuera de los schemas del motor.
  select string_agg(format('%s.%s(%s)', n.nspname, p.proname,
                           case when p.prosecdef then 'SECURITY DEFINER' else 'VOLATILE' end), ', ')
    into offenders
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
   where n.nspname in ('public', 'internal_scraping')
     and (p.prosecdef or p.provolatile = 'v')
     and has_function_privilege('eretz_agency_coverage_writer', p.oid, 'EXECUTE')
     -- Las de extensiones instaladas no son superficie propia del proyecto.
     and not exists (
       select 1 from pg_depend d
        where d.objid = p.oid and d.deptype = 'e'
     );
  if offenders is not null then
    raise exception
      'ASSERT funciones: el rol puede ejecutar funciones SECURITY DEFINER o mutantes (posible escritura indirecta): %. Revisar los grants a PUBLIC sobre esas funciones antes de continuar.',
      left(offenders, 600);
  end if;

  -- 5.10 Policies: sólo las de este rol.
  select count(*) into n from pg_policies
   where policyname like 'eretz_agency_coverage_writer%';
  if n > 3 then
    raise exception 'ASSERT policies: se esperaban hasta 3, hay %', n;
  end if;

  raise notice 'TODAS LAS ASERCIONES PASARON';
end
$assert$;

commit;


-- =============================================================================
-- INFORMATIVO (sólo lectura, después del commit)
-- =============================================================================

-- Atributos. Esperado: rolcanlogin=t; todo lo demás f.
select rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
       rolreplication, rolbypassrls, rolinherit, rolconnlimit
  from pg_roles where rolname = 'eretz_agency_coverage_writer';

-- Privilegios de tabla. Esperado: main sel=t resto f; staging sel=t ins=t resto f.
select n.nspname, c.relname,
       has_table_privilege('eretz_agency_coverage_writer', c.oid, 'SELECT')   as sel,
       has_table_privilege('eretz_agency_coverage_writer', c.oid, 'INSERT')   as ins,
       has_table_privilege('eretz_agency_coverage_writer', c.oid, 'UPDATE')   as upd,
       has_table_privilege('eretz_agency_coverage_writer', c.oid, 'DELETE')   as del,
       has_table_privilege('eretz_agency_coverage_writer', c.oid, 'TRUNCATE') as trunc
  from pg_class c join pg_namespace n on n.oid = c.relnamespace
 where c.relname in ('inmobiliarias_main', 'inmobiliarias_staging')
   and c.relkind in ('r', 'p');

-- Policies del rol.
select schemaname, tablename, policyname, cmd
  from pg_policies
 where policyname like 'eretz_agency_coverage_writer%'
 order by tablename, policyname;

-- Forma real de la staging: el loader la lee sola, no hace falta enviármela.
select table_schema, column_name, data_type, is_nullable, column_default
  from information_schema.columns
 where table_name = 'inmobiliarias_staging'
 order by table_schema, ordinal_position;

-- Índices únicos de la staging: definen la clave de conflicto del insert.
select n.nspname, i.relname as indice, pg_get_indexdef(i.oid) as definicion
  from pg_index idx
  join pg_class c on c.oid = idx.indrelid
  join pg_class i on i.oid = idx.indexrelid
  join pg_namespace n on n.oid = c.relnamespace
 where c.relname = 'inmobiliarias_staging' and idx.indisunique;
