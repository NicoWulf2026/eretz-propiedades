-- Blindaje contra duplicados por URL normalizada.
-- Ejecutar en pasos. No correr el indice unico hasta que la consulta de
-- duplicados devuelva cero filas.

-- 1) Preparar columna para backfill Python.
ALTER TABLE public.propiedades
ADD COLUMN IF NOT EXISTS url_normalizada text;

-- 2) Ejecutar el backfill con Python, usando la misma normalizacion del scraper:
--    python scripts\backfill_propiedades_url_normalizada.py --dry-run
--    python scripts\backfill_propiedades_url_normalizada.py --commit

-- 3) Verificar duplicados pendientes antes del indice unico.
SELECT
    inmobiliaria_id,
    url_normalizada,
    COUNT(*) AS cantidad,
    STRING_AGG(id::text, ', ' ORDER BY id) AS ids,
    STRING_AGG(url, ' | ' ORDER BY id) AS urls
FROM public.propiedades
WHERE url_normalizada IS NOT NULL
  AND url_normalizada <> ''
GROUP BY inmobiliaria_id, url_normalizada
HAVING COUNT(*) > 1
ORDER BY cantidad DESC, inmobiliaria_id
LIMIT 200;

-- 4) Crear solo cuando la consulta anterior no devuelva filas.
-- IMPORTANTE: CREATE INDEX CONCURRENTLY no puede correr dentro de una transaccion.
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_propiedades_unique_inmobiliaria_url_normalizada
ON public.propiedades (inmobiliaria_id, url_normalizada)
WHERE url_normalizada IS NOT NULL
  AND url_normalizada <> '';
