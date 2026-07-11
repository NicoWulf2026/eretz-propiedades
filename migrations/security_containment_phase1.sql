-- ============================================================================
-- security_containment_phase1.sql
-- Fecha:     2026-07-11 (aplicado 13:43 UTC)
-- Proyecto:  ERETZ Propiedades (Supabase PostgreSQL 17.6)
-- Objetivo:  Contencion de exposiciones P0/P1 detectadas en la auditoria de
--            seguridad de DB: cerrar el acceso de anon/authenticated/PUBLIC a
--            datos de contacto e internos, y frenar la reexposicion automatica
--            de tablas/funciones nuevas via default privileges.
-- Alcance:   REVOKE de privilegios sobre 3 backups de inmobiliarias_main,
--            inmobiliarias_main/scraping/staging y 3 views sensibles;
--            ENABLE RLS en los 3 backups; cierre de EXECUTE publico de las
--            funciones set/check_inmolink_password y get_existing_hashes
--            (con GRANT directo preservado a service_role); correccion de los
--            default privileges de FOR ROLE postgres IN SCHEMA public
--            (tablas, secuencias y EXECUTE de funciones incl. PUBLIC).
-- Objetos afectados:
--   Tablas:    backup_inmobiliarias_main_before_diagnostic_backfill_20260626_1
--              backup_inmobiliarias_main_before_diagnostic_status_20260626_102
--              backup_inmobiliarias_main_url_listado_pr_be_url_06d_20260627_22
--              inmobiliarias_main, inmobiliarias_scraping, inmobiliarias_staging
--   Views:     v_propiedades_frontend_mapa, v_next_scraping_batch,
--              v_propiedades_location_ready
--   Funciones: set_inmolink_password(text,text), check_inmolink_password(text,text),
--              get_existing_hashes(text[])
--   Default privileges: FOR ROLE postgres IN SCHEMA public
-- NO contiene DML: no ejecuta INSERT/UPDATE/DELETE/UPSERT/TRUNCATE; no altera
--   filas. No toca public.propiedades. No usa FORCE RLS. No hace DROP.
-- Idempotente: REVOKE/GRANT/ENABLE RLS/ALTER DEFAULT PRIVILEGES son repetibles.
-- ============================================================================

BEGIN;
SET LOCAL statement_timeout = '30s';
SET LOCAL lock_timeout = '5s';

-- ========== PRECHECKS: roles, schema, objetos, owners, autoridad ==========
DO $$
DECLARE
  tbls text[] := ARRAY[
    'public.backup_inmobiliarias_main_before_diagnostic_backfill_20260626_1',
    'public.backup_inmobiliarias_main_before_diagnostic_status_20260626_102',
    'public.backup_inmobiliarias_main_url_listado_pr_be_url_06d_20260627_22',
    'public.inmobiliarias_main','public.inmobiliarias_scraping','public.inmobiliarias_staging'];
  vws  text[] := ARRAY[
    'public.v_propiedades_frontend_mapa','public.v_next_scraping_batch','public.v_propiedades_location_ready'];
  fns  text[] := ARRAY[
    'public.set_inmolink_password(text,text)',
    'public.check_inmolink_password(text,text)',
    'public.get_existing_hashes(text[])'];
  o text; f text; k "char"; own oid; foid oid;
BEGIN
  IF to_regnamespace('public') IS NULL THEN RAISE EXCEPTION 'PRECHECK: schema public ausente'; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role') THEN RAISE EXCEPTION 'PRECHECK: no existe service_role'; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='postgres')      THEN RAISE EXCEPTION 'PRECHECK: no existe rol postgres'; END IF;
  IF NOT pg_has_role(current_user, 'postgres', 'MEMBER')
     THEN RAISE EXCEPTION 'PRECHECK: current_user % no puede administrar default privileges de postgres', current_user; END IF;
  FOREACH o IN ARRAY tbls LOOP
    IF to_regclass(o) IS NULL THEN RAISE EXCEPTION 'PRECHECK: falta tabla %', o; END IF;
    SELECT relkind, relowner INTO k, own FROM pg_class WHERE oid = to_regclass(o);
    IF k <> 'r' THEN RAISE EXCEPTION 'PRECHECK: % no es tabla ordinaria (relkind=%)', o, k; END IF;
    IF NOT pg_has_role(current_user, own, 'MEMBER') THEN RAISE EXCEPTION 'PRECHECK: sin autoridad sobre %', o; END IF;
  END LOOP;
  FOREACH o IN ARRAY vws LOOP
    IF to_regclass(o) IS NULL THEN RAISE EXCEPTION 'PRECHECK: falta view %', o; END IF;
    SELECT relkind, relowner INTO k, own FROM pg_class WHERE oid = to_regclass(o);
    IF k <> 'v' THEN RAISE EXCEPTION 'PRECHECK: % no es view (relkind=%)', o, k; END IF;
    IF NOT pg_has_role(current_user, own, 'MEMBER') THEN RAISE EXCEPTION 'PRECHECK: sin autoridad sobre %', o; END IF;
  END LOOP;
  FOREACH f IN ARRAY fns LOOP
    foid := to_regprocedure(f);
    IF foid IS NULL THEN RAISE EXCEPTION 'PRECHECK: falta funcion %', f; END IF;
    SELECT proowner INTO own FROM pg_proc WHERE oid = foid;
    IF NOT pg_has_role(current_user, own, 'MEMBER') THEN RAISE EXCEPTION 'PRECHECK: sin autoridad sobre funcion %', f; END IF;
  END LOOP;
END $$;

-- ========== CAMBIOS (sin DML; idempotentes) ==========
REVOKE ALL ON public.backup_inmobiliarias_main_before_diagnostic_backfill_20260626_1  FROM anon, authenticated, PUBLIC;
REVOKE ALL ON public.backup_inmobiliarias_main_before_diagnostic_status_20260626_102  FROM anon, authenticated, PUBLIC;
REVOKE ALL ON public.backup_inmobiliarias_main_url_listado_pr_be_url_06d_20260627_22  FROM anon, authenticated, PUBLIC;
ALTER TABLE public.backup_inmobiliarias_main_before_diagnostic_backfill_20260626_1  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.backup_inmobiliarias_main_before_diagnostic_status_20260626_102  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.backup_inmobiliarias_main_url_listado_pr_be_url_06d_20260627_22  ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.inmobiliarias_main     FROM anon, authenticated, PUBLIC;
REVOKE ALL ON public.inmobiliarias_scraping FROM anon, authenticated, PUBLIC;
REVOKE ALL ON public.inmobiliarias_staging  FROM anon, authenticated, PUBLIC;

REVOKE ALL ON public.v_propiedades_frontend_mapa  FROM anon, authenticated, PUBLIC;
REVOKE ALL ON public.v_next_scraping_batch         FROM anon, authenticated, PUBLIC;
REVOKE ALL ON public.v_propiedades_location_ready  FROM anon, authenticated, PUBLIC;

REVOKE ALL ON FUNCTION public.set_inmolink_password(text,text)   FROM anon, authenticated, PUBLIC;
REVOKE ALL ON FUNCTION public.check_inmolink_password(text,text) FROM anon, authenticated, PUBLIC;

GRANT EXECUTE ON FUNCTION public.get_existing_hashes(text[]) TO service_role;
REVOKE EXECUTE ON FUNCTION public.get_existing_hashes(text[]) FROM PUBLIC, anon, authenticated;

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON TABLES       FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON SEQUENCES    FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM anon, authenticated, PUBLIC;

-- ========== VALIDACIONES (rollback automatico ante cualquier fallo) ==========
DO $$
DECLARE
  rels text[] := ARRAY[
    'public.backup_inmobiliarias_main_before_diagnostic_backfill_20260626_1',
    'public.backup_inmobiliarias_main_before_diagnostic_status_20260626_102',
    'public.backup_inmobiliarias_main_url_listado_pr_be_url_06d_20260627_22',
    'public.inmobiliarias_main','public.inmobiliarias_scraping','public.inmobiliarias_staging',
    'public.v_propiedades_frontend_mapa','public.v_next_scraping_batch','public.v_propiedades_location_ready'];
  bks text[] := ARRAY[
    'public.backup_inmobiliarias_main_before_diagnostic_backfill_20260626_1',
    'public.backup_inmobiliarias_main_before_diagnostic_status_20260626_102',
    'public.backup_inmobiliarias_main_url_listado_pr_be_url_06d_20260627_22'];
  fns text[] := ARRAY[
    'public.set_inmolink_password(text,text)',
    'public.check_inmolink_password(text,text)',
    'public.get_existing_hashes(text[])'];
  privs text[] := ARRAY['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER','MAINTAIN'];
  o text; r text; pv text;
BEGIN
  FOREACH o IN ARRAY rels LOOP
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
      FOREACH pv IN ARRAY privs LOOP
        IF has_table_privilege(r, o, pv) THEN RAISE EXCEPTION 'VALIDACION: % conserva % en %', r, o, pv; END IF;
      END LOOP;
    END LOOP;
    IF EXISTS (SELECT 1 FROM pg_class c, aclexplode(c.relacl) a WHERE c.oid=to_regclass(o) AND a.grantee=0)
      THEN RAISE EXCEPTION 'VALIDACION: PUBLIC conserva privilegio en %', o; END IF;
    IF EXISTS (SELECT 1 FROM pg_attribute at, aclexplode(at.attacl) a
               WHERE at.attrelid=to_regclass(o) AND at.attnum>0 AND NOT at.attisdropped
                 AND (a.grantee=0 OR a.grantee='anon'::regrole OR a.grantee='authenticated'::regrole))
      THEN RAISE EXCEPTION 'VALIDACION: ACL de columna residual en %', o; END IF;
  END LOOP;
  FOREACH o IN ARRAY fns LOOP
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
      IF has_function_privilege(r, o, 'EXECUTE') THEN RAISE EXCEPTION 'VALIDACION: % ejecuta %', r, o; END IF;
    END LOOP;
    IF EXISTS (SELECT 1 FROM pg_proc p, aclexplode(p.proacl) a
               WHERE p.oid=to_regprocedure(o) AND a.grantee=0 AND a.privilege_type='EXECUTE')
      THEN RAISE EXCEPTION 'VALIDACION: PUBLIC ejecuta %', o; END IF;
  END LOOP;
  IF NOT has_function_privilege('service_role','public.get_existing_hashes(text[])','EXECUTE')
    THEN RAISE EXCEPTION 'VALIDACION: service_role perdio EXECUTE get_existing_hashes'; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_proc p, aclexplode(p.proacl) a
                 WHERE p.oid=to_regprocedure('public.get_existing_hashes(text[])')
                   AND a.grantee='service_role'::regrole AND a.privilege_type='EXECUTE')
    THEN RAISE EXCEPTION 'VALIDACION: falta grant DIRECTO EXECUTE a service_role'; END IF;
  IF NOT has_table_privilege('service_role','public.inmobiliarias_main','SELECT')
    THEN RAISE EXCEPTION 'VALIDACION: service_role perdio SELECT inmobiliarias_main'; END IF;
  FOREACH o IN ARRAY bks LOOP
    IF NOT has_table_privilege('service_role', o, 'SELECT') THEN RAISE EXCEPTION 'VALIDACION: service_role perdio SELECT en %', o; END IF;
    IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid=to_regclass(o)) THEN RAISE EXCEPTION 'VALIDACION: RLS no activo en %', o; END IF;
  END LOOP;
  IF NOT has_table_privilege('anon','public.propiedades','SELECT')
    THEN RAISE EXCEPTION 'VALIDACION: anon perdio SELECT en propiedades'; END IF;
  IF EXISTS (SELECT 1 FROM pg_default_acl d JOIN pg_namespace n ON n.oid=d.defaclnamespace
             CROSS JOIN LATERAL aclexplode(d.defaclacl) a
             WHERE n.nspname='public' AND pg_get_userbyid(d.defaclrole)='postgres'
               AND (a.grantee='anon'::regrole OR a.grantee='authenticated'::regrole))
    THEN RAISE EXCEPTION 'VALIDACION: default privileges residuales a anon/authenticated'; END IF;
  IF EXISTS (SELECT 1 FROM pg_default_acl d JOIN pg_namespace n ON n.oid=d.defaclnamespace
             CROSS JOIN LATERAL aclexplode(d.defaclacl) a
             WHERE n.nspname='public' AND pg_get_userbyid(d.defaclrole)='postgres'
               AND d.defaclobjtype='f' AND a.grantee=0 AND a.privilege_type='EXECUTE')
    THEN RAISE EXCEPTION 'VALIDACION: default EXECUTE a PUBLIC en funciones'; END IF;
END $$;

COMMIT;
