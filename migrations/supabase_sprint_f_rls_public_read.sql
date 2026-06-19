-- =============================================================================
-- MIGRACIÓN Sprint F — RLS: habilitar lectura pública para el frontend
-- =============================================================================
-- Fecha: 2026-06-10
-- Autor: Sprint F
--
-- PROBLEMA DETECTADO:
--   La tabla `propiedades` tiene RLS habilitado pero sin policy SELECT para
--   el rol `anon`. El frontend usa la anon key (NEXT_PUBLIC_SUPABASE_ANON_KEY),
--   que devuelve 0 filas (content-range: */0) aunque la tabla tiene datos.
--   El frontend cae al fallback de datos demo.
--
-- INSTRUCCIONES:
--   1. Abrir Supabase → SQL Editor (o Supabase Studio)
--   2. Copiar y pegar este archivo COMPLETO
--   3. Ejecutar
--   4. Verificar con las SELECT del final
--
-- Idempotente: se puede aplicar varias veces sin pérdida.
-- Sin DROP TABLE, sin DELETE, sin TRUNCATE.
-- Solo agrega permisos de LECTURA para la anon key (no escritura).
-- =============================================================================


-- -----------------------------------------------------------------------------
-- PASO 1: Policy SELECT pública en propiedades
-- Permite que la anon key (frontend público) lea todas las propiedades.
-- -----------------------------------------------------------------------------

DROP POLICY IF EXISTS "propiedades_public_read" ON public.propiedades;

CREATE POLICY "propiedades_public_read"
ON public.propiedades
FOR SELECT
TO anon
USING (true);


-- -----------------------------------------------------------------------------
-- PASO 2: Grants explícitos sobre la vista del frontend
-- La vista v_propiedades_frontend_mapa necesita grants explícitos además
-- de la policy en la tabla base.
-- -----------------------------------------------------------------------------

GRANT SELECT ON public.v_propiedades_frontend_mapa TO anon;
GRANT SELECT ON public.v_propiedades_frontend_mapa TO authenticated;

-- También asegurar que la tabla base tenga el grant (puede ya existir)
GRANT SELECT ON public.propiedades TO anon;
GRANT SELECT ON public.propiedades TO authenticated;


-- -----------------------------------------------------------------------------
-- PASO 3: Verificación post-migración
-- Ejecutar estas SELECT para confirmar que la policy funciona.
-- -----------------------------------------------------------------------------

-- Debe mostrar la policy recién creada
SELECT schemaname, tablename, policyname, roles, cmd, qual
FROM pg_policies
WHERE tablename = 'propiedades';

-- Debe retornar filas (no 0) — confirma que anon puede leer
SELECT COUNT(*) as total_propiedades FROM public.propiedades;

-- Debe retornar filas desde la vista
SELECT COUNT(*) as total_en_vista FROM public.v_propiedades_frontend_mapa;

-- =============================================================================
-- RESULTADO ESPERADO:
-- - total_propiedades > 0
-- - total_en_vista > 0
-- - policy "propiedades_public_read" listada para anon, cmd=SELECT
-- =============================================================================
