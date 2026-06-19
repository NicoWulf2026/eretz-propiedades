-- =============================================================================
-- MIGRACIÓN Phase 2 — Step 1: Bloquear scraping_runs y scraping_run_items a anon
-- =============================================================================
-- Fecha: 2026-06-16
-- Riesgo: BAJO
--
-- PROBLEMA:
--   scraping_runs (53 filas) y scraping_run_items (2904 filas) son accesibles
--   al rol anon sin restricción. Cualquier visitante del frontend puede leer
--   el historial operativo completo de scraping.
--
-- SOLUCIÓN:
--   1. REVOKE SELECT para anon y authenticated.
--   2. ENABLE ROW LEVEL SECURITY (sin policies = deny all para no-superuser).
--   service_role bypassea RLS completamente — todos los scripts siguen funcionando.
--
-- VERIFICADO ANTES DE APLICAR:
--   - Frontend: no usa estas tablas (grep: 0 archivos en /frontend).
--   - Scripts: todos usan SUPABASE_SERVICE_ROLE_KEY (config.py línea 251:
--     SUPABASE_KEY = SUPABASE_SERVICE_ROLE_KEY). service_role bypassea RLS.
--   - Funciones RPC del scraper (claim_next_scraping_item, finish_scraping_item_*,
--     start_scraping_item, etc.) llamadas con service_role → sin impacto.
--
-- IDEMPOTENTE: se puede ejecutar varias veces sin pérdida.
-- SIN DROP, DELETE, TRUNCATE.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- PASO 1: Revocar permisos de lectura pública
-- -----------------------------------------------------------------------------

REVOKE SELECT ON public.scraping_runs FROM anon;
REVOKE SELECT ON public.scraping_run_items FROM anon;

REVOKE SELECT ON public.scraping_runs FROM authenticated;
REVOKE SELECT ON public.scraping_run_items FROM authenticated;

-- También revocar otros permisos por si fueron otorgados en bloque
REVOKE INSERT, UPDATE, DELETE ON public.scraping_runs FROM anon;
REVOKE INSERT, UPDATE, DELETE ON public.scraping_run_items FROM anon;
REVOKE INSERT, UPDATE, DELETE ON public.scraping_runs FROM authenticated;
REVOKE INSERT, UPDATE, DELETE ON public.scraping_run_items FROM authenticated;


-- -----------------------------------------------------------------------------
-- PASO 2: Habilitar Row Level Security
-- Sin policies = deny-all para anon/authenticated.
-- service_role bypassea RLS → scripts internos sin impacto.
-- -----------------------------------------------------------------------------

ALTER TABLE public.scraping_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.scraping_run_items ENABLE ROW LEVEL SECURITY;


-- -----------------------------------------------------------------------------
-- PASO 3: Verificación post-ejecución
-- Ejecutar estas SELECT para confirmar el resultado.
-- -----------------------------------------------------------------------------

-- Debe mostrar 0 filas (anon bloqueado correctamente)
-- Nota: ejecutar desde SQL Editor con rol anon o verificar via REST con ANON_KEY

-- Verificar que RLS está activo en ambas tablas
SELECT
    relname AS tabla,
    relrowsecurity AS rls_activo,
    relforcerowsecurity AS rls_forzado
FROM pg_class
WHERE relname IN ('scraping_runs', 'scraping_run_items')
  AND relkind = 'r';

-- Verificar que no quedan policies permisivas para anon/authenticated
SELECT tablename, policyname, roles, cmd, qual
FROM pg_policies
WHERE tablename IN ('scraping_runs', 'scraping_run_items');

-- Verificar que service_role puede seguir leyendo (no debe dar 0)
SELECT COUNT(*) AS total_scraping_runs FROM public.scraping_runs;
SELECT COUNT(*) AS total_scraping_run_items FROM public.scraping_run_items;

-- =============================================================================
-- RESULTADO ESPERADO:
--   - rls_activo = true para ambas tablas
--   - pg_policies: sin filas (o solo policies de service_role si existían)
--   - total_scraping_runs > 0  (service_role puede leer)
--   - total_scraping_run_items > 0  (service_role puede leer)
--   - Desde REST con ANON_KEY → 0 filas o HTTP 401/403
-- =============================================================================
