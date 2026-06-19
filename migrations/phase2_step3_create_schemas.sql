-- =============================================================================
-- MIGRACIÓN Phase 2 — Step 3: Crear schemas futuros
-- =============================================================================
-- Fecha: 2026-06-16
-- Riesgo: MUY BAJO (solo creación, nada se mueve todavía)
--
-- OBJETIVO:
--   Crear los schemas que recibirán las tablas en la migración Neon → Supabase Pro.
--   Este script SOLO crea los schemas y revoca acceso público.
--   NO mueve tablas. NO borra nada. NO cambia nada en public.
--
-- SCHEMAS A CREAR:
--   - internal_scraping: pipeline de scraping (propiedades_raw, propiedades_staging,
--     publish_queue, data_quality_issues, scraping_runs, scraping_run_items, etc.)
--   - archive: snapshots/backups históricos (tablas backup_propiedades_*)
--   - audit: auditoría futura (vacío por ahora)
--
-- IDEMPOTENTE: IF NOT EXISTS previene errores si se ejecuta dos veces.
-- SIN DROP, DELETE, TRUNCATE, ALTER TABLE.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- PASO 1: Crear schemas
-- -----------------------------------------------------------------------------

CREATE SCHEMA IF NOT EXISTS internal_scraping;
CREATE SCHEMA IF NOT EXISTS archive;
CREATE SCHEMA IF NOT EXISTS audit;


-- -----------------------------------------------------------------------------
-- PASO 2: Revocar acceso público a los schemas nuevos
-- Por defecto Supabase puede otorgar USAGE en public a anon/authenticated.
-- Estos schemas deben ser exclusivamente de uso interno (service_role).
-- -----------------------------------------------------------------------------

-- internal_scraping: solo service_role
REVOKE ALL ON SCHEMA internal_scraping FROM anon;
REVOKE ALL ON SCHEMA internal_scraping FROM authenticated;
REVOKE ALL ON SCHEMA internal_scraping FROM PUBLIC;

-- archive: solo service_role
REVOKE ALL ON SCHEMA archive FROM anon;
REVOKE ALL ON SCHEMA archive FROM authenticated;
REVOKE ALL ON SCHEMA archive FROM PUBLIC;

-- audit: solo service_role (puede ampliarse luego si se necesita lectura controlada)
REVOKE ALL ON SCHEMA audit FROM anon;
REVOKE ALL ON SCHEMA audit FROM authenticated;
REVOKE ALL ON SCHEMA audit FROM PUBLIC;

-- Otorgar USAGE explícito al service_role (para confirmar acceso)
GRANT USAGE ON SCHEMA internal_scraping TO service_role;
GRANT USAGE ON SCHEMA archive TO service_role;
GRANT USAGE ON SCHEMA audit TO service_role;


-- -----------------------------------------------------------------------------
-- PASO 3: Verificación
-- -----------------------------------------------------------------------------

-- Debe mostrar los 3 schemas creados
SELECT schema_name, schema_owner
FROM information_schema.schemata
WHERE schema_name IN ('internal_scraping', 'archive', 'audit')
ORDER BY schema_name;

-- Verificar que no hay tablas en los nuevos schemas (deben estar vacíos)
SELECT table_schema, COUNT(*) AS tablas
FROM information_schema.tables
WHERE table_schema IN ('internal_scraping', 'archive', 'audit')
GROUP BY table_schema;

-- =============================================================================
-- RESULTADO ESPERADO:
--   - 3 schemas listados: archive, audit, internal_scraping
--   - 0 tablas en cada schema (schemas vacíos, listos para recibir objetos)
-- =============================================================================


-- =============================================================================
-- NOTA: Siguientes pasos (NO ejecutar en este script)
-- =============================================================================
--
-- Una vez creados los schemas, los pasos siguientes son:
--
-- A) Mover tablas de backup a archive (requiere autorización explícita):
--    ALTER TABLE public.backup_propiedades_inmobiliaria_id_20260518 SET SCHEMA archive;
--    ALTER TABLE public.backup_propiedades_run32_ubicacion_20260519 SET SCHEMA archive;
--    ALTER TABLE public.backup_propiedades_run34_encoding_20260520 SET SCHEMA archive;
--    ALTER TABLE public.backup_propiedades_run36_ciudad_20260520 SET SCHEMA archive;
--    ALTER TABLE public.backup_propiedades_run32_ciudad_detectada_20260519 SET SCHEMA archive;
--    ALTER TABLE public.backup_propiedades_sin_provincia_20260520 SET SCHEMA archive;
--    ALTER TABLE public.backup_propiedades_duplicadas_url_20260518 SET SCHEMA archive;
--    ALTER TABLE public.backup_propiedades_duplicadas_url_normalizada_20260518 SET SCHEMA archive;
--    ALTER TABLE public.backup_propiedades_coordenadas_invalidas_20260519 SET SCHEMA archive;
--    ALTER TABLE public.propiedades_backup_pre_quality_fix SET SCHEMA archive;
--
-- B) Mover tablas operativas a internal_scraping (post-migración Neon):
--    ALTER TABLE public.scraping_runs SET SCHEMA internal_scraping;
--    ALTER TABLE public.scraping_run_items SET SCHEMA internal_scraping;
--    ALTER TABLE public.inmobiliarias_scraping SET SCHEMA internal_scraping;
--    -- (evaluar inmobiliarias_staging: mover o mantener en public)
--
-- ADVERTENCIA: mover tablas con ALTER TABLE SET SCHEMA puede romper:
--   - vistas que referencian la tabla por schema.tabla
--   - funciones que usan public.tabla explícitamente
--   - scripts que hardcodean "public."
-- Verificar dependencias antes de mover.
-- =============================================================================
