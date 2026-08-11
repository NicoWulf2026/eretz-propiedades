-- QA READ-ONLY de las 4 migraciones + rol writer (NO es una migración: vive fuera
-- de supabase/migrations/, no se auto-ejecuta). Ejecutar en el SQL Editor DESPUÉS
-- de aplicar la instalación. No modifica datos (salvo el test SET ROLE, que crea y
-- borra sólo 2 fixtures sintéticos y NO altera memberships).
--
-- Correcciones de la auditoría:
--  * PUBLIC/anon/authenticated se comprueban con information_schema.table_privileges
--    (role_table_grants OMITE grants vía PUBLIC) + matriz has_table_privilege.
--  * membresías del writer (pg_auth_members) -> 0 filas.
--  * has_schema_privilege CREATE=false / USAGE=true.
--  * control global de secuencias (SELECT/UPDATE/USAGE).
--  * test SET ROLE sin GRANT/REVOKE temporal; auto-detecta si puede o se omite.

-- ==========================================================================
-- VERIFICACIÓN READ-ONLY
-- ==========================================================================

-- (1) Tablas + RLS habilitado (esperado: 4 filas, rls_habilitado = true)
SELECT c.relname AS tabla, c.relrowsecurity AS rls_habilitado
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname IN ('perfil_claims','propiedad_duplicados','reportes_publicacion','listing_price_history')
ORDER BY 1;

-- (2) Índices
SELECT tablename, indexname FROM pg_indexes
WHERE schemaname='public'
  AND tablename IN ('perfil_claims','propiedad_duplicados','reportes_publicacion','listing_price_history')
ORDER BY 1,2;

-- (3) Policies (rol + comando) — esperado 3: 2 INSERT writer + 1 SELECT RO
SELECT tablename, policyname, cmd, roles FROM pg_policies
WHERE schemaname='public'
  AND tablename IN ('perfil_claims','propiedad_duplicados','reportes_publicacion','listing_price_history')
ORDER BY 1,2;

-- (4) Grants de tabla por rol sobre las 4 tablas (via role_table_grants)
SELECT grantee, table_name, privilege_type
FROM information_schema.role_table_grants
WHERE table_schema='public'
  AND table_name IN ('perfil_claims','propiedad_duplicados','reportes_publicacion','listing_price_history')
ORDER BY 1,2,3;

-- (5a) CONTROL PUBLIC/anon/authenticated con table_privileges (SÍ incluye PUBLIC).
--      Esperado: 0 filas.
SELECT grantee, table_name, privilege_type
FROM information_schema.table_privileges
WHERE table_schema='public'
  AND table_name IN ('perfil_claims','propiedad_duplicados','reportes_publicacion','listing_price_history')
  AND grantee IN ('anon','authenticated','PUBLIC')
ORDER BY 1,2,3;

-- (5b) Refuerzo por ACL efectivo: anon/authenticated sin ningún privilegio
--      (has_table_privilege también reflejaría cualquier grant a PUBLIC).
--      Esperado: todas las columnas false.
SELECT r.rol, t.tabla,
       has_table_privilege(r.rol, t.tabla, 'SELECT') AS sel,
       has_table_privilege(r.rol, t.tabla, 'INSERT') AS ins,
       has_table_privilege(r.rol, t.tabla, 'UPDATE') AS upd,
       has_table_privilege(r.rol, t.tabla, 'DELETE') AS del
FROM (VALUES
  ('public.perfil_claims'),('public.propiedad_duplicados'),
  ('public.reportes_publicacion'),('public.listing_price_history')
) t(tabla)
CROSS JOIN (VALUES ('anon'),('authenticated')) r(rol)
ORDER BY 1,2;

-- (6) El writer NO tiene SELECT/UPDATE/DELETE/TRUNCATE en ningún lado. Esperado 0 filas.
SELECT grantee, table_name, privilege_type
FROM information_schema.role_table_grants
WHERE table_schema='public' AND grantee='eretz_app_writer'
  AND privilege_type IN ('SELECT','UPDATE','DELETE','TRUNCATE');

-- (A) Atributos del rol writer (esperado: todo false salvo rolcanlogin)
SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolcanlogin
FROM pg_roles WHERE rolname='eretz_app_writer';

-- (A2) MEMBRESÍAS del writer: NO debe ser miembro de ningún rol. Esperado 0 filas.
SELECT r.rolname AS writer, g.rolname AS miembro_de
FROM pg_auth_members m
JOIN pg_roles r ON r.oid = m.member
JOIN pg_roles g ON g.oid = m.roleid
WHERE r.rolname = 'eretz_app_writer'
ORDER BY 2;

-- (A3) Privilegios de schema public: CREATE=false (no crea objetos), USAGE=true.
SELECT has_schema_privilege('eretz_app_writer','public','CREATE') AS puede_crear,
       has_schema_privilege('eretz_app_writer','public','USAGE')  AS puede_usar;

-- (B) Secuencias identity: USAGE=true, SELECT=false, UPDATE=false (mínimo privilegio)
SELECT s AS secuencia,
       has_sequence_privilege('eretz_app_writer', s, 'USAGE')  AS usage,
       has_sequence_privilege('eretz_app_writer', s, 'SELECT') AS select_,
       has_sequence_privilege('eretz_app_writer', s, 'UPDATE') AS update_
FROM (VALUES
  (pg_get_serial_sequence('public.perfil_claims','id')),
  (pg_get_serial_sequence('public.reportes_publicacion','id'))
) AS t(s);

-- (C) CONTROL GLOBAL de secuencias: TODA secuencia de public donde el writer tenga
--     USAGE/SELECT/UPDATE. Esperado: EXACTAMENTE las 2 identity, usage=true y
--     select_/update_=false; ninguna otra secuencia.
SELECT n.nspname AS schema, c.relname AS secuencia,
       has_sequence_privilege('eretz_app_writer', c.oid, 'USAGE')  AS usage,
       has_sequence_privilege('eretz_app_writer', c.oid, 'SELECT') AS select_,
       has_sequence_privilege('eretz_app_writer', c.oid, 'UPDATE') AS update_
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'S' AND n.nspname = 'public'
  AND (has_sequence_privilege('eretz_app_writer', c.oid, 'USAGE')
    OR has_sequence_privilege('eretz_app_writer', c.oid, 'SELECT')
    OR has_sequence_privilege('eretz_app_writer', c.oid, 'UPDATE'))
ORDER BY 2;

-- ==========================================================================
-- TEST DE PERMISOS CON SET ROLE (sin modificar memberships)
-- ==========================================================================

-- Mostrar la identidad administrativa (para saber si puede SET ROLE directo)
SELECT current_user, session_user, (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) AS es_superuser;

-- El bloque intenta SET LOCAL ROLE; si la sesión admin NO puede (sin tocar
-- memberships), OMITE el test y lo explica. Si puede, inserta 2 fixtures, verifica
-- que el writer puede INSERT pero NO SELECT/UPDATE/DELETE ni leer price_history, y
-- limpia SÓLO esos 2 fixtures.
DO $$
DECLARE
  ins_claims   int := 0;
  ins_reports  int := 0;
  can_select   boolean := true;
  can_update   boolean := true;
  can_delete   boolean := true;
  can_read_pph boolean := true;
  can_setrole  boolean := true;
BEGIN
  BEGIN
    SET LOCAL ROLE eretz_app_writer;
  EXCEPTION WHEN insufficient_privilege THEN
    can_setrole := false;
  END;

  IF NOT can_setrole THEN
    RAISE NOTICE 'SET ROLE a eretz_app_writer NO permitido sin modificar memberships.';
    RAISE NOTICE 'Test de permisos OMITIDO (no se altera ninguna membership).';
    RAISE NOTICE 'Los permisos ya quedan demostrados por las secciones (4)(5)(6)(A)(B)(C).';
    RETURN;
  END IF;

  -- Como writer: INSERT debe funcionar (RLS INSERT + USAGE de secuencia)
  INSERT INTO public.perfil_claims (tipo, entidad_id, nombre, email, estado)
    VALUES ('inmobiliaria', 999999999, 'QA FIXTURE', 'qa-fixture-claim@eretz.test', 'pending');
  GET DIAGNOSTICS ins_claims = ROW_COUNT;
  INSERT INTO public.reportes_publicacion (propiedad_id, motivo, email, estado)
    VALUES (999999999, 'otro', 'qa-fixture-report@eretz.test', 'nuevo');
  GET DIAGNOSTICS ins_reports = ROW_COUNT;

  -- SELECT / UPDATE / DELETE deben FALLAR (permiso insuficiente)
  BEGIN PERFORM 1 FROM public.perfil_claims LIMIT 1;              EXCEPTION WHEN insufficient_privilege THEN can_select := false; END;
  BEGIN UPDATE public.perfil_claims SET nombre = nombre WHERE false; EXCEPTION WHEN insufficient_privilege THEN can_update := false; END;
  BEGIN DELETE FROM public.perfil_claims WHERE false;            EXCEPTION WHEN insufficient_privilege THEN can_delete := false; END;
  BEGIN PERFORM 1 FROM public.listing_price_history LIMIT 1;     EXCEPTION WHEN insufficient_privilege THEN can_read_pph := false; END;

  RESET ROLE;

  RAISE NOTICE 'INSERT perfil_claims filas=% (esperado 1)', ins_claims;
  RAISE NOTICE 'INSERT reportes filas=%     (esperado 1)', ins_reports;
  RAISE NOTICE 'writer SELECT perfil_claims=%  (esperado false)', can_select;
  RAISE NOTICE 'writer UPDATE perfil_claims=%  (esperado false)', can_update;
  RAISE NOTICE 'writer DELETE perfil_claims=%  (esperado false)', can_delete;
  RAISE NOTICE 'writer SELECT price_history=%  (esperado false)', can_read_pph;

  -- Limpieza SÓLO de los 2 fixtures, como admin (rol ya reseteado)
  DELETE FROM public.perfil_claims        WHERE email = 'qa-fixture-claim@eretz.test';
  DELETE FROM public.reportes_publicacion WHERE email = 'qa-fixture-report@eretz.test';
END $$;
