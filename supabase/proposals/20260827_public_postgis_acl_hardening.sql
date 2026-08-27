-- ERETZ Propiedades — PROPUESTA, NO EJECUTAR SIN AUTORIZACIÓN EXPLÍCITA.
-- Fecha de evidencia: 2026-08-27.
-- Objetivo P0: retirar exclusivamente privilegios de escritura directos que
-- PostGIS dejó otorgados a anon/authenticated sobre sus tres objetos públicos.
-- No modifica datos, RLS, ownership, extensiones ni permisos de otros roles.

BEGIN;

DO $preflight$
DECLARE
  missing_objects integer;
  missing_roles integer;
BEGIN
  SELECT 3 - count(*) INTO missing_objects
  FROM pg_class AS relation
  JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
  WHERE namespace.nspname = 'public'
    AND relation.relname IN ('spatial_ref_sys', 'geography_columns', 'geometry_columns');

  SELECT 2 - count(*) INTO missing_roles
  FROM pg_roles
  WHERE rolname IN ('anon', 'authenticated');

  IF missing_objects <> 0 OR missing_roles <> 0 THEN
    RAISE EXCEPTION 'ACL preflight failed: missing_objects=%, missing_roles=%',
      missing_objects, missing_roles;
  END IF;
END
$preflight$;

REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER, MAINTAIN
ON TABLE
  public.spatial_ref_sys,
  public.geography_columns,
  public.geometry_columns
FROM anon, authenticated;

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
        IF has_table_privilege(role_name, object_name, privilege_name) THEN
          RAISE EXCEPTION 'Unexpected effective privilege: role=%, object=%, privilege=%',
            role_name, object_name, privilege_name;
        END IF;
      END LOOP;
    END LOOP;
  END LOOP;
END
$validation$;

COMMIT;

-- Post-deploy canary (read-only):
-- 1. Ejecutar la validación anterior fuera de la transacción.
-- 2. Confirmar que eretz_preview_ro conserva sus SELECT de aplicación.
-- 3. Ejecutar Explorer, mapa y ficha con el Preview privado.
-- 4. Confirmar que Data API continúa OFF.
--
-- Fuera de este P0: PUBLIC conserva SELECT sobre los tres objetos y los tres
-- overloads SECURITY DEFINER de ST_EstimatedExtent conservan EXECUTE público.
-- Esos dos puntos requieren un canary PostGIS separado antes de revocarlos.
