-- Rollback exacto de la propuesta 20260827_public_postgis_acl_hardening.sql.
-- NO EJECUTAR salvo rollback explícitamente autorizado.

BEGIN;

GRANT INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER, MAINTAIN
ON TABLE
  public.spatial_ref_sys,
  public.geography_columns,
  public.geometry_columns
TO anon, authenticated;

DO $validation$
DECLARE
  role_name text;
  object_name text;
  privilege_name text;
BEGIN
  FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated'] LOOP
    FOREACH object_name IN ARRAY ARRAY[
      'public.spatial_ref_sys',
      'public.geography_columns',
      'public.geometry_columns'
    ] LOOP
      FOREACH privilege_name IN ARRAY ARRAY[
        'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE',
        'REFERENCES', 'TRIGGER', 'MAINTAIN'
      ] LOOP
        IF NOT has_table_privilege(role_name, object_name, privilege_name) THEN
          RAISE EXCEPTION 'Rollback did not restore privilege: role=%, object=%, privilege=%',
            role_name, object_name, privilege_name;
        END IF;
      END LOOP;
    END LOOP;
  END LOOP;
END
$validation$;

COMMIT;
