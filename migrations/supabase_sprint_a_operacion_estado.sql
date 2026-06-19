-- =============================================================================
-- MIGRACIÓN Sprint A — Ampliar operacion + estado en Supabase propiedades
-- =============================================================================
-- Fecha propuesta: 2026-06-09
-- Autor: FASE 1 Sprint A
--
-- INSTRUCCIONES:
--   1. Abrir Supabase → SQL Editor
--   2. Copiar y pegar este archivo COMPLETO
--   3. Verificar con las SELECT del final antes de guardar
--   4. SÓLO ejecutar con confirmación explícita del usuario
--
-- Idempotente: se puede aplicar varias veces sin pérdida.
-- Sin DROP TABLE, sin DELETE, sin TRUNCATE.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- PASO 0: Backup mental
-- Antes de ejecutar, verificar estado actual:
-- SELECT estado, COUNT(*) FROM propiedades GROUP BY estado;
-- SELECT operacion, COUNT(*) FROM propiedades GROUP BY operacion;
-- -----------------------------------------------------------------------------


-- -----------------------------------------------------------------------------
-- PASO 1: Migrar valores EXISTENTES antes de agregar constraints nuevas
-- (imprescindible: si se agrega el CHECK primero, los UPDATE fallan)
-- -----------------------------------------------------------------------------

-- activo → activa
UPDATE public.propiedades
SET estado = 'activa'
WHERE estado = 'activo';

-- inactivo → desconocida
-- (inactivo puede significar vendida, alquilada, o simplemente no detectada)
-- Si querés ser más específico, puede ser: no_detectada_en_ultimo_scraping
UPDATE public.propiedades
SET estado = 'desconocida'
WHERE estado = 'inactivo';


-- -----------------------------------------------------------------------------
-- PASO 2: Ampliar constraint de operacion
-- Elimina la constraint vieja (si existe) y la recrea con los nuevos valores.
-- Si no hay constraint, el ALTER ADD no la reemplaza (es ADD, no REPLACE).
-- -----------------------------------------------------------------------------

-- Eliminar constraint existente si existe
ALTER TABLE public.propiedades
    DROP CONSTRAINT IF EXISTS propiedades_operacion_chk;

-- Recrear con valores ampliados
ALTER TABLE public.propiedades
    ADD CONSTRAINT propiedades_operacion_chk
    CHECK (
        operacion IS NULL
        OR operacion IN (
            'venta',
            'alquiler',
            'alquiler_temporario',
            'consultar',
            'venta_y_alquiler'
        )
    );


-- -----------------------------------------------------------------------------
-- PASO 3: Ampliar constraint de estado
-- -----------------------------------------------------------------------------

-- Eliminar constraint existente si existe
ALTER TABLE public.propiedades
    DROP CONSTRAINT IF EXISTS propiedades_estado_chk;

-- Recrear con los 7 estados oficiales de InmoCapital
ALTER TABLE public.propiedades
    ADD CONSTRAINT propiedades_estado_chk
    CHECK (
        estado IS NULL
        OR estado IN (
            'activa',
            'reservada',
            'vendida',
            'alquilada',
            'no_detectada_en_ultimo_scraping',
            'consultar',
            'desconocida'
        )
    );


-- -----------------------------------------------------------------------------
-- PASO 4: Verificación post-migración
-- Ejecutar estas SELECT para confirmar que todo quedó bien.
-- -----------------------------------------------------------------------------

-- Ver distribución de estados (debe mostrar 'activa' y 'desconocida', no 'activo'/'inactivo')
SELECT estado, COUNT(*) as cantidad
FROM public.propiedades
GROUP BY estado
ORDER BY cantidad DESC;

-- Ver distribución de operaciones
SELECT operacion, COUNT(*) as cantidad
FROM public.propiedades
GROUP BY operacion
ORDER BY cantidad DESC;

-- Verificar que no quedaron valores prohibidos
SELECT COUNT(*) as valores_invalidos_estado
FROM public.propiedades
WHERE estado NOT IN (
    'activa', 'reservada', 'vendida', 'alquilada',
    'no_detectada_en_ultimo_scraping', 'consultar', 'desconocida'
) AND estado IS NOT NULL;

SELECT COUNT(*) as valores_invalidos_operacion
FROM public.propiedades
WHERE operacion NOT IN (
    'venta', 'alquiler', 'alquiler_temporario', 'consultar', 'venta_y_alquiler'
) AND operacion IS NOT NULL;

-- =============================================================================
-- FIN DE MIGRACIÓN
-- =============================================================================
-- Resultado esperado:
-- - valores_invalidos_estado = 0
-- - valores_invalidos_operacion = 0
-- - Estado 'activo' e 'inactivo' no aparecen en la distribución
-- =============================================================================
