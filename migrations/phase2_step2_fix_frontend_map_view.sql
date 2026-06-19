-- =============================================================================
-- MIGRACIÓN Phase 2 — Step 2: Corregir v_propiedades_frontend_mapa (v2)
-- =============================================================================
-- Fecha: 2026-06-16
-- Riesgo: BAJO
--
-- PROBLEMAS ORIGINALES:
--
--   BUG 1 — Filtro de estado (causa 0 filas):
--     WHERE ... COALESCE(p.estado, 'activo') = 'activo'
--     → Solo pasarían filas con estado='activo', pero todas tienen 'activa'.
--     → Resultado: 0 filas permanentemente.
--
--   BUG 2 — JOIN lento (causa timeout HTTP 500):
--     JOIN v_propiedades_location_ready plr ON plr.id = p.id
--     → Vista lenta sobre 94,834 filas, timeout con ambos roles.
--
-- CORRECCIÓN APLICADA (Opción A — sin filtro de estado):
--
--   Regla de negocio vigente de InmoCapital:
--     "Todas las propiedades publicadas deben aparecer.
--      No se bloquea por estado, calidad incompleta, falta de imágenes,
--      falta de precio ni falta de coordenadas."
--
--   Por lo tanto:
--     - Se ELIMINA completamente el filtro de estado.
--     - Se MANTIENE el filtro latitud/longitud IS NOT NULL (requerido para mapa).
--     - Se MANTIENE la exclusión de URLs de entorno de test.
--     - Se ELIMINA el JOIN con v_propiedades_location_ready (fix del timeout).
--
-- DISTRIBUCIÓN DE ESTADOS ACTUAL (confirmado por auditoría 2026-06-16):
--   activa                          : 94,064  (99.2%)
--   desconocida                     :    763   (0.8%)
--   no_detectada_en_ultimo_scraping :      7  (<0.1%)
--   reservada / vendida / alquilada :      0
--   NULL                            :      0
--
-- CONTEO ESPERADO POST-FIX:
--   latitud IS NOT NULL (todos estados)   → 44,934
--   Desglose:
--     activa                              → 44,552
--     desconocida                         →    380
--     no_detectada_en_ultimo_scraping     →      2
--
-- CAMBIOS RESPECTO A VERSIÓN ANTERIOR:
--   1. WHERE estado: eliminado completamente.
--   2. JOIN v_propiedades_location_ready: eliminado (reemplazado por p.ciudad / p.provincia).
--   3. ciudad_final / provincia_final leen de p.ciudad / p.provincia directamente.
--   4. Todo lo demás: sin cambios (columnas, orden, lógica imagen_principal_real).
--
-- COLUMNAS PRESERVADAS (mismo orden y nombres):
--   id, inmobiliaria_id, url, titulo, descripcion, precio, moneda, precio_usd,
--   precio_ars, expensas, expensas_moneda, tipo_propiedad, operacion, ambientes,
--   dormitorios, banos, toilettes, cocheras, antiguedad, piso, superficie_total,
--   superficie_cubierta, superficie_terreno, direccion, barrio, ciudad_original,
--   provincia_original, ciudad_final, provincia_final, pais, latitud, longitud,
--   imagenes, video_url, plano_url, amenities, agente_nombre, agente_telefono,
--   fuente_extraccion, cms_origen, fecha_publicacion, estado, created_at,
--   updated_at, apto_credito, inmobiliaria_nombre, inmobiliaria_web,
--   inmobiliaria_telefono, inmobiliaria_email, imagen_principal_real, tiene_imagen_real
--
-- IDEMPOTENTE: CREATE OR REPLACE no elimina datos.
-- SIN DROP, DELETE, TRUNCATE.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Reemplazar la vista — Opción A: solo filtro de coordenadas, sin filtro estado
-- -----------------------------------------------------------------------------

CREATE OR REPLACE VIEW public.v_propiedades_frontend_mapa AS
SELECT
    p.id,
    p.inmobiliaria_id,
    p.url,
    p.titulo,
    p.descripcion,
    p.precio,
    p.moneda,
    p.precio_usd,
    p.precio_ars,
    p.expensas,
    p.expensas_moneda,
    p.tipo_propiedad,
    p.operacion,
    p.ambientes,
    p.dormitorios,
    p.banos,
    p.toilettes,
    p.cocheras,
    p.antiguedad,
    p.piso,
    p.superficie_total,
    p.superficie_cubierta,
    p.superficie_terreno,
    p.direccion,
    p.barrio,
    p.ciudad         AS ciudad_original,
    p.provincia      AS provincia_original,
    p.ciudad         AS ciudad_final,       -- antes: plr.ciudad_final (JOIN eliminado)
    p.provincia      AS provincia_final,    -- antes: plr.provincia_final (JOIN eliminado)
    p.pais,
    p.latitud,
    p.longitud,
    p.imagenes,
    p.video_url,
    p.plano_url,
    p.amenities,
    p.agente_nombre,
    p.agente_telefono,
    p.fuente_extraccion,
    p.cms_origen,
    p.fecha_publicacion,
    p.estado,
    p.created_at,
    p.updated_at,
    p.apto_credito,
    i.nombre              AS inmobiliaria_nombre,
    i.web                 AS inmobiliaria_web,
    i.telefono_principal  AS inmobiliaria_telefono,
    i.email_principal     AS inmobiliaria_email,
    -- Lógica imagen_principal_real: sin cambios respecto a versión original
    CASE
        WHEN p.imagenes IS NOT NULL
         AND array_length(p.imagenes, 1) > 0
         AND p.imagenes[1] NOT LIKE     '%static.tokkobroker.com/tfw/img/prop-icons%'
         AND p.imagenes[1] NOT ILIKE    '%unsplash.com%'
         AND p.imagenes[1] NOT ILIKE    '%placeholder%'
         AND p.imagenes[1] NOT ILIKE    '%no-photo%'
         AND p.imagenes[1] NOT ILIKE    '%sin-imagen%'
         AND p.imagenes[1] NOT ILIKE    '%360%'
         AND p.imagenes[1] NOT ILIKE    '%tour%'
         AND p.imagenes[1] NOT ILIKE    '%virtual%'
        THEN p.imagenes[1]
        ELSE NULL
    END AS imagen_principal_real,
    CASE
        WHEN p.imagenes IS NOT NULL
         AND array_length(p.imagenes, 1) > 0
         AND p.imagenes[1] NOT LIKE     '%static.tokkobroker.com/tfw/img/prop-icons%'
         AND p.imagenes[1] NOT ILIKE    '%unsplash.com%'
         AND p.imagenes[1] NOT ILIKE    '%placeholder%'
         AND p.imagenes[1] NOT ILIKE    '%no-photo%'
         AND p.imagenes[1] NOT ILIKE    '%sin-imagen%'
         AND p.imagenes[1] NOT ILIKE    '%360%'
         AND p.imagenes[1] NOT ILIKE    '%tour%'
         AND p.imagenes[1] NOT ILIKE    '%virtual%'
        THEN true
        ELSE false
    END AS tiene_imagen_real

FROM public.propiedades p
LEFT JOIN public.inmobiliarias_main i ON i.id = p.inmobiliaria_id

-- FIX: sin filtro de estado (Opción A — regla de negocio: todas las props aparecen)
-- FIX: JOIN v_propiedades_location_ready eliminado (era la causa del timeout)
WHERE p.latitud  IS NOT NULL
  AND p.longitud IS NOT NULL
  AND p.url NOT ILIKE '%inmocapital.test%'
  AND p.url NOT ILIKE '%localhost%'
  AND p.url NOT ILIKE '%example.com%';


-- -----------------------------------------------------------------------------
-- Re-otorgar permisos de lectura pública
-- (CREATE OR REPLACE puede resetear GRANTs en algunas versiones de Supabase)
-- -----------------------------------------------------------------------------

GRANT SELECT ON public.v_propiedades_frontend_mapa TO anon;
GRANT SELECT ON public.v_propiedades_frontend_mapa TO authenticated;


-- -----------------------------------------------------------------------------
-- Verificación post-ejecución
-- -----------------------------------------------------------------------------

-- ESPERADO: 44,934 filas (todos los estados con latitud IS NOT NULL)
SELECT COUNT(*) AS total_en_vista FROM public.v_propiedades_frontend_mapa;

-- ESPERADO: activa=44552, desconocida=380, no_detectada_en_ultimo_scraping=2
SELECT estado, COUNT(*) AS cantidad
FROM public.v_propiedades_frontend_mapa
GROUP BY estado
ORDER BY cantidad DESC;

-- Muestra de 3 propiedades para verificar columnas
SELECT id, estado, ciudad_final, provincia_final,
       inmobiliaria_nombre, imagen_principal_real, tiene_imagen_real
FROM public.v_propiedades_frontend_mapa
ORDER BY id ASC
LIMIT 3;

-- =============================================================================
-- RESULTADO ESPERADO:
--   total_en_vista = 44,934
--   estado 'activo' no aparece (no hay ninguno en producción)
--   estado NULL no aparece (ninguna propiedad tiene estado NULL)
--   inmobiliaria_nombre poblado para la mayoría
--   Sin timeout
-- =============================================================================
