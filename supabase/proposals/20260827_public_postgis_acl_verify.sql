-- ERETZ Propiedades — verificación de SÓLO LECTURA del P0 de ACL PostGIS.
--
-- Este archivo no cambia nada. Existe para poder responder tres preguntas sin
-- tener que confiar en la memoria de nadie:
--
--   1. ¿la exposición sigue ahí?      (antes de aplicar)
--   2. ¿se cerró?                     (después de aplicar)
--   3. ¿volvió?                       (en cualquier momento posterior)
--
-- Se puede ejecutar con `eretz_preview_ro`: sólo lee catálogo.
--
-- Uso:
--   psql "$ERETZ_PREVIEW_RO_URL" -f 20260827_public_postgis_acl_verify.sql

\echo '== 1. Version del servidor =='
-- MAINTAIN existe desde PostgreSQL 17. La propuesta lo nombra, y un REVOKE que
-- nombra un privilegio inexistente falla al parsear, antes de cualquier
-- preflight. Si esto dice 16 o menos, hay que sacar MAINTAIN de la lista antes
-- de aplicar.
SELECT current_setting('server_version_num')::int AS server_version_num,
       version() AS version,
       (current_setting('server_version_num')::int >= 170000) AS soporta_maintain;

\echo ''
\echo '== 2. ACL actual de los tres objetos PostGIS =='
SELECT n.nspname AS schema,
       c.relname AS objeto,
       CASE c.relkind WHEN 'r' THEN 'tabla' WHEN 'v' THEN 'vista' ELSE c.relkind::text END AS tipo,
       pg_get_userbyid(c.relowner) AS owner,
       c.relrowsecurity AS rls,
       c.relacl::text AS acl
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname IN ('spatial_ref_sys', 'geography_columns', 'geometry_columns')
ORDER BY c.relname;

\echo ''
\echo '== 3. Privilegios EFECTIVOS de escritura (lo que importa) =='
-- Se pregunta por privilegio efectivo y no por la ACL literal: `anon` podría
-- recibir escritura por pertenecer a otro rol o por un grant a PUBLIC, y en la
-- ACL del objeto eso no se ve.
SELECT rol,
       objeto,
       privilegio,
       has_table_privilege(rol, objeto, privilegio) AS lo_tiene
FROM unnest(ARRAY['anon', 'authenticated']) AS rol,
     unnest(ARRAY['public.spatial_ref_sys',
                  'public.geography_columns',
                  'public.geometry_columns']) AS objeto,
     unnest(ARRAY['INSERT', 'UPDATE', 'DELETE', 'TRUNCATE',
                  'REFERENCES', 'TRIGGER']) AS privilegio
WHERE has_table_privilege(rol, objeto, privilegio)
ORDER BY rol, objeto, privilegio;

\echo ''
\echo '   (sin filas arriba = P0 cerrado)'

\echo ''
\echo '== 4. SELECT, que la propuesta NO toca =='
-- Debe seguir habiendo lectura: revocarla es otro cambio, con su propio canary,
-- porque puede romper funciones internas de PostGIS.
SELECT rol,
       objeto,
       has_table_privilege(rol, objeto, 'SELECT') AS puede_leer
FROM unnest(ARRAY['anon', 'authenticated', 'eretz_preview_ro']) AS rol,
     unnest(ARRAY['public.spatial_ref_sys']) AS objeto
WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = rol)
ORDER BY rol;

\echo ''
\echo '== 5. Origen del privilegio: grant directo o herencia =='
-- Si la exposición volviera, esto dice si alguien re-otorgó explícitamente o si
-- `anon` quedó como miembro de un rol que ya lo tenía. Son dos problemas
-- distintos y se arreglan distinto.
SELECT r.rolname AS rol,
       m.rolname AS es_miembro_de
FROM pg_roles r
JOIN pg_auth_members am ON am.member = r.oid
JOIN pg_roles m ON m.oid = am.roleid
WHERE r.rolname IN ('anon', 'authenticated')
ORDER BY r.rolname, m.rolname;

\echo ''
\echo '== 6. SECURITY DEFINER publico en public (fuera del P0) =='
-- No lo cierra esta propuesta. Se lista para que quede medido y no se olvide.
SELECT p.proname AS funcion,
       pg_get_function_identity_arguments(p.oid) AS argumentos,
       p.prosecdef AS security_definer,
       p.proconfig AS config,
       has_function_privilege('anon', p.oid, 'EXECUTE') AS anon_ejecuta
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'public'
  AND p.prosecdef
ORDER BY p.proname
LIMIT 50;
