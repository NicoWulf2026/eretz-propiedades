BEGIN;

DO $migration$
DECLARE
  matching_functions integer;
BEGIN
  SELECT count(*)
    INTO matching_functions
    FROM pg_proc AS procedure
    JOIN pg_namespace AS namespace ON namespace.oid = procedure.pronamespace
   WHERE namespace.nspname = 'public'
     AND procedure.proname = 'st_estimatedextent'
     AND procedure.prosecdef
     AND pg_get_function_identity_arguments(procedure.oid) IN (
       'text, text',
       'text, text, text',
       'text, text, text, boolean'
     );

  IF matching_functions <> 3 THEN
    RAISE EXCEPTION
      'Expected exactly three SECURITY DEFINER public.st_estimatedextent overloads; found %',
      matching_functions;
  END IF;
END
$migration$;

ALTER FUNCTION public.st_estimatedextent(text, text)
  SET search_path = pg_catalog, public;
ALTER FUNCTION public.st_estimatedextent(text, text, text)
  SET search_path = pg_catalog, public;
ALTER FUNCTION public.st_estimatedextent(text, text, text, boolean)
  SET search_path = pg_catalog, public;

DO $validation$
DECLARE
  hardened_functions integer;
BEGIN
  SELECT count(*)
    INTO hardened_functions
    FROM pg_proc AS procedure
    JOIN pg_namespace AS namespace ON namespace.oid = procedure.pronamespace
   WHERE namespace.nspname = 'public'
     AND procedure.proname = 'st_estimatedextent'
     AND procedure.prosecdef
     AND pg_get_function_identity_arguments(procedure.oid) IN (
       'text, text',
       'text, text, text',
       'text, text, text, boolean'
     )
     AND procedure.proconfig @> ARRAY['search_path=pg_catalog, public']::text[];

  IF hardened_functions <> 3 THEN
    RAISE EXCEPTION
      'SECURITY DEFINER search_path validation failed; hardened % of 3 functions',
      hardened_functions;
  END IF;
END
$validation$;

COMMIT;
