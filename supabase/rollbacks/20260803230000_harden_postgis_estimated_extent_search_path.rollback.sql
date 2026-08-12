BEGIN;

ALTER FUNCTION public.st_estimatedextent(text, text)
  RESET search_path;
ALTER FUNCTION public.st_estimatedextent(text, text, text)
  RESET search_path;
ALTER FUNCTION public.st_estimatedextent(text, text, text, boolean)
  RESET search_path;

DO $validation$
DECLARE
  restored_functions integer;
BEGIN
  SELECT count(*)
    INTO restored_functions
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
     AND procedure.proconfig IS NULL;

  IF restored_functions <> 3 THEN
    RAISE EXCEPTION
      'SECURITY DEFINER rollback validation failed; restored % of 3 functions',
      restored_functions;
  END IF;
END
$validation$;

COMMIT;
