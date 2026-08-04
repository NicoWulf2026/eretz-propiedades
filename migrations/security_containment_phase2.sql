-- ERETZ backend final closure: least-privilege containment for public objects.
-- Additive/reversible privilege change. No data rows are modified.
-- Preflight evidence: _scratch/backend_final_closure/SUPABASE_AUDIT/grants.csv

BEGIN;

-- The public frontend model is read-only. RLS remains the row-level gate.
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
ON public.propiedades FROM anon, authenticated;
GRANT SELECT ON public.propiedades TO anon, authenticated;

-- The previous broad policy made the active-only policy ineffective.
-- ALTER is used instead of DROP to keep the migration non-destructive.
ALTER POLICY propiedades_public_read ON public.propiedades
TO anon, authenticated
USING (estado = 'activo');

-- No other public relation is part of the approved frontend contract yet.
-- service_role is intentionally untouched.
DO $containment$
DECLARE
  relation record;
BEGIN
  FOR relation IN
    SELECT n.nspname AS schema_name, c.relname AS relation_name
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
      AND c.relname <> 'propiedades'
  LOOP
    EXECUTE format(
      'REVOKE ALL PRIVILEGES ON %I.%I FROM anon, authenticated',
      relation.schema_name,
      relation.relation_name
    );
  END LOOP;
END
$containment$;

-- Backups remain available to service_role/postgres but are defense-in-depth
-- protected from API roles.
DO $backup_rls$
DECLARE
  relation record;
BEGIN
  FOR relation IN
    SELECT n.nspname AS schema_name, c.relname AS relation_name
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind IN ('r', 'p')
      AND (c.relname LIKE 'backup\_%' ESCAPE '\' OR c.relname LIKE '%\_backup\_%' ESCAPE '\')
  LOOP
    EXECUTE format(
      'ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY',
      relation.schema_name,
      relation.relation_name
    );
  END LOOP;
END
$backup_rls$;

-- Sensitive SECURITY DEFINER routines are callable only by service_role and
-- use an explicit, non-user-controlled search_path.
ALTER FUNCTION public.set_inmolink_password(text, text)
  SET search_path = public, pg_temp;
ALTER FUNCTION public.check_inmolink_password(text, text)
  SET search_path = public, pg_temp;
ALTER FUNCTION public.get_existing_hashes(text[])
  SET search_path = public, pg_temp;

REVOKE EXECUTE ON FUNCTION public.set_inmolink_password(text, text)
  FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.check_inmolink_password(text, text)
  FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.get_existing_hashes(text[])
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_existing_hashes(text[]) TO service_role;

-- Prevent recurrence for objects created by postgres.
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE ALL ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon, authenticated;

-- Transaction-local validation.
DO $validate$
BEGIN
  IF has_table_privilege('anon', 'public.propiedades', 'INSERT')
     OR has_table_privilege('anon', 'public.propiedades', 'UPDATE')
     OR has_table_privilege('anon', 'public.propiedades', 'DELETE')
     OR has_table_privilege('authenticated', 'public.propiedades', 'INSERT')
     OR has_table_privilege('authenticated', 'public.propiedades', 'UPDATE')
     OR has_table_privilege('authenticated', 'public.propiedades', 'DELETE')
  THEN
    RAISE EXCEPTION 'write privilege remains on public.propiedades';
  END IF;
  IF NOT has_table_privilege('anon', 'public.propiedades', 'SELECT')
     OR NOT has_table_privilege('authenticated', 'public.propiedades', 'SELECT')
  THEN
    RAISE EXCEPTION 'public read privilege missing on public.propiedades';
  END IF;
  IF has_function_privilege('anon', 'public.get_existing_hashes(text[])', 'EXECUTE')
     OR has_function_privilege('authenticated', 'public.get_existing_hashes(text[])', 'EXECUTE')
  THEN
    RAISE EXCEPTION 'sensitive RPC remains executable by API roles';
  END IF;
  IF NOT has_function_privilege('service_role', 'public.get_existing_hashes(text[])', 'EXECUTE')
  THEN
    RAISE EXCEPTION 'service_role lost scraper dedup RPC';
  END IF;
END
$validate$;

COMMIT;

