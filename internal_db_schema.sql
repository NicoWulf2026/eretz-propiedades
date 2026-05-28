-- =============================================================================
-- InmoCapital - Internal DB Schema (Neon u otro Postgres dedicado al scraper)
-- =============================================================================
-- Proposito
-- ---------
-- Tablas y funciones de cola/staging que actualmente viven en Supabase y se
-- pueden migrar a una base interna dedicada para aislar el ruido de scraping
-- del servicio publico (frontend) que sigue leyendo `propiedades` desde
-- Supabase. El cliente Python `InternalDBClient` (scraper/scraper_propiedades.py)
-- solo se activa cuando `USE_INTERNAL_DB=true` e `INTERNAL_DB_URL` esta seteado.
--
-- Que NO esta aqui
-- ----------------
-- - tabla `propiedades`           -> sigue en Supabase (la lee el frontend)
-- - tabla `inmobiliarias_main`    -> sigue en Supabase
-- - vistas v_propiedades_frontend_mapa, v_next_scraping_batch,
--   v_next_geocoding_batch       -> dependen de tablas de Supabase
--
-- Seguridad
-- ---------
-- - Solo CREATE TABLE IF NOT EXISTS / CREATE OR REPLACE FUNCTION / CREATE INDEX
--   IF NOT EXISTS.
-- - Sin DROP, sin TRUNCATE, sin DELETE.
-- - Idempotente: se puede aplicar varias veces sin perdida.
--
-- Compatibilidad con el codigo actual
-- -----------------------------------
-- Columnas y nombres de funciones replican EXACTAMENTE lo que el codigo Python
-- inserta / actualiza / consulta:
--   * scripts/create_scraping_run_from_next_batch.py::build_run_payload
--   * scripts/create_scraping_run_from_next_batch.py::build_item_payloads
--   * scraper/scraper_propiedades.py::InternalDBClient._RPC_ARGUMENTS
--   * scraper/geocoder.py (payload de geocoding_results)
--   * scripts/import_zonaprop_to_staging.py / import_excel_cordoba_to_staging.py
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Tabla: scraping_runs
-- Una fila por tanda (run). Acumula totales que el scraper incrementa en cada
-- finish_scraping_item_success/error.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.scraping_runs (
    id                                BIGSERIAL PRIMARY KEY,
    run_type                          TEXT,
    status                            TEXT NOT NULL DEFAULT 'running',
    started_at                        TIMESTAMPTZ,
    finished_at                       TIMESTAMPTZ,
    duration_seconds                  INTEGER,
    total_inmobiliarias_planificadas  INTEGER NOT NULL DEFAULT 0,
    total_inmobiliarias_procesadas    INTEGER NOT NULL DEFAULT 0,
    total_inmobiliarias_exitosas      INTEGER NOT NULL DEFAULT 0,
    total_inmobiliarias_error         INTEGER NOT NULL DEFAULT 0,
    total_propiedades_detectadas      INTEGER NOT NULL DEFAULT 0,
    total_propiedades_nuevas          INTEGER NOT NULL DEFAULT 0,
    total_propiedades_actualizadas    INTEGER NOT NULL DEFAULT 0,
    total_propiedades_sin_cambios     INTEGER NOT NULL DEFAULT 0,
    total_propiedades_error           INTEGER NOT NULL DEFAULT 0,
    source_view                       TEXT,
    notes                             TEXT,
    created_at                        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT scraping_runs_status_chk
        CHECK (status IN ('running','finished','error','cancelled'))
);

CREATE INDEX IF NOT EXISTS idx_scraping_runs_status
    ON public.scraping_runs(status);
CREATE INDEX IF NOT EXISTS idx_scraping_runs_started_at
    ON public.scraping_runs(started_at DESC);


-- -----------------------------------------------------------------------------
-- Tabla: scraping_run_items
-- Una fila por inmobiliaria a procesar dentro de una run. `inmobiliaria_id`
-- es un ID logico que referencia `inmobiliarias_main.id` en Supabase (no hay
-- FK cross-DB; la integridad se valida en codigo al crear cada batch).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.scraping_run_items (
    id                          BIGSERIAL PRIMARY KEY,
    scraping_run_id             BIGINT NOT NULL
                                REFERENCES public.scraping_runs(id) ON DELETE CASCADE,
    inmobiliaria_id             INTEGER NOT NULL,  -- logico: inmobiliarias_main.id (Supabase)
    inmobiliaria_nombre         TEXT,
    ciudad                      TEXT,
    provincia                   TEXT,
    web                         TEXT,
    url_listado                 TEXT,
    cms_detectado               TEXT,
    status                      TEXT NOT NULL DEFAULT 'pending',
    started_at                  TIMESTAMPTZ,
    finished_at                 TIMESTAMPTZ,
    duration_seconds            INTEGER,
    propiedades_detectadas      INTEGER NOT NULL DEFAULT 0,
    propiedades_nuevas          INTEGER NOT NULL DEFAULT 0,
    propiedades_actualizadas    INTEGER NOT NULL DEFAULT 0,
    propiedades_sin_cambios     INTEGER NOT NULL DEFAULT 0,
    propiedades_error           INTEGER NOT NULL DEFAULT 0,
    error_message               TEXT,
    error_type                  TEXT,
    http_status                 INTEGER,
    final_url                   TEXT,
    metadata                    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT scraping_run_items_status_chk
        CHECK (status IN ('pending','running','success','error','cancelled'))
);

CREATE INDEX IF NOT EXISTS idx_items_run_id
    ON public.scraping_run_items(scraping_run_id);
CREATE INDEX IF NOT EXISTS idx_items_status
    ON public.scraping_run_items(status);
-- Para claim_next_scraping_item (toma el `pending` mas antiguo)
CREATE INDEX IF NOT EXISTS idx_items_status_created
    ON public.scraping_run_items(status, created_at);
-- Para retry-errors / retry-partial-extractions (filtran por error_type)
CREATE INDEX IF NOT EXISTS idx_items_error_type
    ON public.scraping_run_items(error_type) WHERE error_type IS NOT NULL;
-- Para evitar pending/running duplicados de la misma inmobiliaria
CREATE INDEX IF NOT EXISTS idx_items_inmo_status
    ON public.scraping_run_items(inmobiliaria_id, status);


-- -----------------------------------------------------------------------------
-- Tabla: geocoding_results
-- Cache de geocoding generado por scraper/geocoder.py. `propiedad_id` es un ID
-- logico que referencia `propiedades.id` en Supabase. El campo `raw_response`
-- guarda la respuesta cruda del proveedor (Nominatim) para debugging.
-- Columnas y nombres replican exactamente lo que geocoder.py inserta/consulta.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.geocoding_results (
    id                    BIGSERIAL PRIMARY KEY,
    propiedad_id          BIGINT NOT NULL,  -- logico: propiedades.id (Supabase)
    direccion_geocoding   TEXT NOT NULL,    -- direccion final usada en la query
    latitud               DOUBLE PRECISION,
    longitud              DOUBLE PRECISION,
    precision_geocoding   TEXT,             -- ej: exact / area / interpolated
    proveedor             TEXT,             -- ej: nominatim
    raw_response          JSONB,            -- respuesta cruda del proveedor
    status                TEXT NOT NULL DEFAULT 'pending',  -- success / error / review / pending
    error_message         TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Lookup por propiedad para evitar duplicar geocoding por (propiedad, direccion)
CREATE INDEX IF NOT EXISTS idx_geocoding_propiedad_id
    ON public.geocoding_results(propiedad_id);
CREATE INDEX IF NOT EXISTS idx_geocoding_propiedad_direccion
    ON public.geocoding_results(propiedad_id, direccion_geocoding);
-- Para get_success_results_batch (apply-valid-results)
CREATE INDEX IF NOT EXISTS idx_geocoding_status_coords
    ON public.geocoding_results(status, latitud, longitud)
    WHERE latitud IS NOT NULL AND longitud IS NOT NULL;


-- -----------------------------------------------------------------------------
-- Tabla: inmobiliarias_staging
-- Buffer de imports puntuales (zonaprop, excel cordoba) antes de promoverlas a
-- `inmobiliarias_main` en Supabase. Columnas replican exactamente lo que
-- import_zonaprop_to_staging.py y import_excel_cordoba_to_staging.py insertan.
-- `metadata_zonaprop` se usa para ambos imports (heredado del nombre original).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.inmobiliarias_staging (
    id                       BIGSERIAL PRIMARY KEY,
    nombre                   TEXT,
    nombre_limpio            TEXT,
    nombre_normalizado       TEXT,
    web                      TEXT,
    url_listado              TEXT,
    direccion                TEXT,
    barrio                   TEXT,
    ciudad                   TEXT,
    provincia                TEXT,
    pais                     TEXT DEFAULT 'Argentina',
    telefono                 TEXT,
    fuente                   TEXT,
    estado_scraping          TEXT,
    needs_manual_review      BOOLEAN NOT NULL DEFAULT false,
    revision_notas           TEXT,
    url_perfil_zonaprop      TEXT,
    metadata_zonaprop        JSONB,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_staging_fuente
    ON public.inmobiliarias_staging(fuente);
CREATE INDEX IF NOT EXISTS idx_staging_needs_review
    ON public.inmobiliarias_staging(needs_manual_review)
    WHERE needs_manual_review = true;
CREATE INDEX IF NOT EXISTS idx_staging_nombre_normalizado
    ON public.inmobiliarias_staging(nombre_normalizado);


-- =============================================================================
-- FUNCIONES RPC
-- =============================================================================
-- Estas funciones implementan la API que espera InternalDBClient
-- (scraper/scraper_propiedades.py::_RPC_ARGUMENTS). El cliente Python las
-- invoca como `SELECT * FROM public.<funcion>(%s, %s, ...)` con argumentos
-- POSICIONALES en el orden documentado abajo.
--
-- Importante:
-- - Los nombres de columna se referencian con qualificacion para evitar
--   choques con nombres de parametros (ej: scraping_run_items.final_url).
-- - Todas son idempotentes en su efecto observable.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- claim_next_scraping_item()
-- Toma el siguiente item con status='pending' (FOR UPDATE SKIP LOCKED para
-- soportar 4+ workers en paralelo sin colisiones), lo marca 'running' y
-- devuelve la fila completa. Si no hay items pending, devuelve NULL.
-- Llamado desde: SupabasePropiedades.claim_next_scraping_item
--                (scraper_propiedades.py linea ~1907).
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.claim_next_scraping_item()
RETURNS public.scraping_run_items
LANGUAGE plpgsql AS $$
DECLARE
    claimed public.scraping_run_items;
BEGIN
    UPDATE public.scraping_run_items
       SET status      = 'running',
           started_at  = COALESCE(scraping_run_items.started_at, now()),
           updated_at  = now()
     WHERE id = (
            SELECT id
              FROM public.scraping_run_items
             WHERE status = 'pending'
             ORDER BY created_at ASC
             FOR UPDATE SKIP LOCKED
             LIMIT 1
         )
    RETURNING * INTO claimed;
    RETURN claimed;  -- NULL si no hay items pending
END;
$$;


-- -----------------------------------------------------------------------------
-- start_scraping_item(item_id BIGINT)
-- Idempotente: asegura status='running' y started_at. No falla si el item ya
-- estaba en running.
-- Llamado desde: SupabasePropiedades.start_scraping_item (linea ~2265).
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.start_scraping_item(item_id BIGINT)
RETURNS public.scraping_run_items
LANGUAGE plpgsql AS $$
DECLARE row_out public.scraping_run_items;
BEGIN
    UPDATE public.scraping_run_items
       SET status      = 'running',
           started_at  = COALESCE(scraping_run_items.started_at, now()),
           updated_at  = now()
     WHERE id = start_scraping_item.item_id
    RETURNING * INTO row_out;
    RETURN row_out;
END;
$$;


-- -----------------------------------------------------------------------------
-- retry_scraping_item(item_id BIGINT)
-- Resetea un item para reintento limpio: vuelve a 'pending', limpia timestamps
-- y error_*. No toca los conteos de propiedades (ya guardados pueden seguir).
-- Llamado desde: SupabasePropiedades.retry_scraping_item (linea ~2258).
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.retry_scraping_item(item_id BIGINT)
RETURNS public.scraping_run_items
LANGUAGE plpgsql AS $$
DECLARE row_out public.scraping_run_items;
BEGIN
    UPDATE public.scraping_run_items
       SET status            = 'pending',
           started_at        = NULL,
           finished_at       = NULL,
           duration_seconds  = NULL,
           error_message     = NULL,
           error_type        = NULL,
           http_status       = NULL,
           updated_at        = now()
     WHERE id = retry_scraping_item.item_id
    RETURNING * INTO row_out;
    RETURN row_out;
END;
$$;


-- -----------------------------------------------------------------------------
-- finish_scraping_item_success(item_id, propiedades_detectadas,
--      propiedades_nuevas, propiedades_actualizadas,
--      propiedades_sin_cambios, propiedades_error,
--      final_url, metadata_json)
--
-- Marca el item como 'success', calcula duration_seconds y propaga los
-- conteos a scraping_runs (incrementa totales acumulados).
-- Llamado desde: SupabasePropiedades.finish_scraping_item_success (~2272).
-- Orden de argumentos: ver InternalDBClient._RPC_ARGUMENTS.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.finish_scraping_item_success(
    item_id                  BIGINT,
    propiedades_detectadas   INTEGER,
    propiedades_nuevas       INTEGER,
    propiedades_actualizadas INTEGER,
    propiedades_sin_cambios  INTEGER,
    propiedades_error        INTEGER,
    final_url                TEXT,
    metadata_json            JSONB
) RETURNS public.scraping_run_items
LANGUAGE plpgsql AS $$
DECLARE
    row_out public.scraping_run_items;
BEGIN
    UPDATE public.scraping_run_items AS i
       SET status                   = 'success',
           finished_at              = now(),
           duration_seconds         = CASE
                WHEN i.started_at IS NOT NULL
                THEN EXTRACT(EPOCH FROM (now() - i.started_at))::INT
                ELSE NULL END,
           propiedades_detectadas   = COALESCE(finish_scraping_item_success.propiedades_detectadas, 0),
           propiedades_nuevas       = COALESCE(finish_scraping_item_success.propiedades_nuevas, 0),
           propiedades_actualizadas = COALESCE(finish_scraping_item_success.propiedades_actualizadas, 0),
           propiedades_sin_cambios  = COALESCE(finish_scraping_item_success.propiedades_sin_cambios, 0),
           propiedades_error        = COALESCE(finish_scraping_item_success.propiedades_error, 0),
           final_url                = finish_scraping_item_success.final_url,
           metadata                 = COALESCE(finish_scraping_item_success.metadata_json, '{}'::jsonb),
           updated_at               = now()
     WHERE i.id = finish_scraping_item_success.item_id
    RETURNING i.* INTO row_out;

    IF row_out.id IS NOT NULL THEN
        UPDATE public.scraping_runs AS r
           SET total_inmobiliarias_procesadas = r.total_inmobiliarias_procesadas + 1,
               total_inmobiliarias_exitosas   = r.total_inmobiliarias_exitosas   + 1,
               total_propiedades_detectadas   = r.total_propiedades_detectadas   + COALESCE(row_out.propiedades_detectadas, 0),
               total_propiedades_nuevas       = r.total_propiedades_nuevas       + COALESCE(row_out.propiedades_nuevas, 0),
               total_propiedades_actualizadas = r.total_propiedades_actualizadas + COALESCE(row_out.propiedades_actualizadas, 0),
               total_propiedades_sin_cambios  = r.total_propiedades_sin_cambios  + COALESCE(row_out.propiedades_sin_cambios, 0),
               total_propiedades_error        = r.total_propiedades_error        + COALESCE(row_out.propiedades_error, 0),
               updated_at                     = now()
         WHERE r.id = row_out.scraping_run_id;
    END IF;

    RETURN row_out;
END;
$$;


-- -----------------------------------------------------------------------------
-- finish_scraping_item_error(item_id, error_message, error_type,
--      http_status, final_url, metadata_json)
--
-- Marca el item como 'error', guarda diagnostico y propaga conteo a la run.
-- Llamado desde: SupabasePropiedades.finish_scraping_item_error (~2299).
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.finish_scraping_item_error(
    item_id        BIGINT,
    error_message  TEXT,
    error_type     TEXT,
    http_status    INTEGER,
    final_url      TEXT,
    metadata_json  JSONB
) RETURNS public.scraping_run_items
LANGUAGE plpgsql AS $$
DECLARE
    row_out public.scraping_run_items;
BEGIN
    UPDATE public.scraping_run_items AS i
       SET status            = 'error',
           finished_at       = now(),
           duration_seconds  = CASE
                WHEN i.started_at IS NOT NULL
                THEN EXTRACT(EPOCH FROM (now() - i.started_at))::INT
                ELSE NULL END,
           error_message     = finish_scraping_item_error.error_message,
           error_type        = finish_scraping_item_error.error_type,
           http_status       = finish_scraping_item_error.http_status,
           final_url         = finish_scraping_item_error.final_url,
           metadata          = COALESCE(finish_scraping_item_error.metadata_json, '{}'::jsonb),
           updated_at        = now()
     WHERE i.id = finish_scraping_item_error.item_id
    RETURNING i.* INTO row_out;

    IF row_out.id IS NOT NULL THEN
        UPDATE public.scraping_runs AS r
           SET total_inmobiliarias_procesadas = r.total_inmobiliarias_procesadas + 1,
               total_inmobiliarias_error      = r.total_inmobiliarias_error      + 1,
               updated_at                     = now()
         WHERE r.id = row_out.scraping_run_id;
    END IF;

    RETURN row_out;
END;
$$;


-- -----------------------------------------------------------------------------
-- close_scraping_run_if_finished(run_id BIGINT)
-- Verifica si el run todavia tiene items pending o running; si no, lo cierra
-- (status='finished', finished_at, duration_seconds). Si todavia hay
-- pending/running, devuelve la run sin tocar.
-- Llamado desde: SupabasePropiedades.close_scraping_run_if_finished (~2322).
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.close_scraping_run_if_finished(run_id BIGINT)
RETURNS public.scraping_runs
LANGUAGE plpgsql AS $$
DECLARE
    pending_count INTEGER;
    row_out       public.scraping_runs;
BEGIN
    SELECT COUNT(*) INTO pending_count
      FROM public.scraping_run_items
     WHERE scraping_run_id = close_scraping_run_if_finished.run_id
       AND status IN ('pending','running');

    IF pending_count = 0 THEN
        UPDATE public.scraping_runs AS r
           SET status            = 'finished',
               finished_at       = COALESCE(r.finished_at, now()),
               duration_seconds  = CASE
                    WHEN r.started_at IS NOT NULL
                    THEN EXTRACT(EPOCH FROM (COALESCE(r.finished_at, now()) - r.started_at))::INT
                    ELSE NULL END,
               updated_at        = now()
         WHERE r.id = close_scraping_run_if_finished.run_id
        RETURNING r.* INTO row_out;
    ELSE
        SELECT * INTO row_out
          FROM public.scraping_runs
         WHERE id = close_scraping_run_if_finished.run_id;
    END IF;

    RETURN row_out;
END;
$$;


-- =============================================================================
-- STAGING / PUBLICACION DIARIA
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Tabla: propiedades_raw
-- Captura cruda de propiedades detectadas por scraping antes de normalizar,
-- validar, geocodificar y publicar en Supabase.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.propiedades_raw (
    id                    BIGSERIAL PRIMARY KEY,
    scraping_run_item_id  BIGINT REFERENCES public.scraping_run_items(id)
                          ON DELETE SET NULL,
    inmobiliaria_id       BIGINT NOT NULL,
    hash_dedup            TEXT NOT NULL,
    titulo                TEXT,
    descripcion           TEXT,
    precio                NUMERIC,
    moneda                TEXT,
    superficie_total      NUMERIC,
    superficie_cubierta   NUMERIC,
    tipo_propiedad        TEXT,
    operacion             TEXT,
    url                   TEXT,
    url_normalizada       TEXT,
    direccion_raw         TEXT,
    barrio                TEXT,
    ciudad                TEXT,
    provincia             TEXT,
    pais                  TEXT DEFAULT 'Argentina',
    latitud               NUMERIC,
    longitud              NUMERIC,
    imagenes              JSONB DEFAULT '[]'::jsonb,
    datos_extra           JSONB DEFAULT '{}'::jsonb,
    scraped_at            TIMESTAMPTZ DEFAULT now(),
    status                TEXT NOT NULL DEFAULT 'raw',
    CONSTRAINT propiedades_raw_status_chk
        CHECK (status IN ('raw','validated','rejected','published'))
);

CREATE INDEX IF NOT EXISTS idx_propiedades_raw_status
    ON public.propiedades_raw(status);
CREATE INDEX IF NOT EXISTS idx_propiedades_raw_hash_dedup
    ON public.propiedades_raw(hash_dedup);
CREATE INDEX IF NOT EXISTS idx_propiedades_raw_inmobiliaria_status
    ON public.propiedades_raw(inmobiliaria_id, status);
CREATE INDEX IF NOT EXISTS idx_propiedades_raw_scraped_at
    ON public.propiedades_raw(scraped_at);
CREATE INDEX IF NOT EXISTS idx_propiedades_raw_url_normalizada
    ON public.propiedades_raw(url_normalizada);


-- -----------------------------------------------------------------------------
-- Tabla: propiedades_staging
-- Propiedades normalizadas y listas para validacion final / cola de publicacion.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.propiedades_staging (
    id                    BIGSERIAL PRIMARY KEY,
    raw_id                BIGINT REFERENCES public.propiedades_raw(id)
                          ON DELETE SET NULL,
    inmobiliaria_id       BIGINT NOT NULL,
    hash_dedup            TEXT NOT NULL,
    titulo                TEXT,
    descripcion           TEXT,
    precio                NUMERIC,
    moneda                TEXT,
    superficie_total      NUMERIC,
    superficie_cubierta   NUMERIC,
    tipo_propiedad        TEXT,
    operacion             TEXT,
    url                   TEXT,
    url_normalizada       TEXT,
    direccion_normalizada TEXT,
    barrio                TEXT,
    ciudad                TEXT,
    provincia             TEXT,
    pais                  TEXT DEFAULT 'Argentina',
    latitud               NUMERIC,
    longitud              NUMERIC,
    imagenes              JSONB DEFAULT '[]'::jsonb,
    geocoding_status      TEXT NOT NULL DEFAULT 'pending',
    validation_score      SMALLINT DEFAULT 0,
    staged_at             TIMESTAMPTZ DEFAULT now(),
    status                TEXT NOT NULL DEFAULT 'staging',
    CONSTRAINT propiedades_staging_geocoding_status_chk
        CHECK (geocoding_status IN ('pending','done','failed','skipped')),
    CONSTRAINT propiedades_staging_status_chk
        CHECK (status IN ('staging','queued','published','rejected'))
);

CREATE INDEX IF NOT EXISTS idx_propiedades_staging_status
    ON public.propiedades_staging(status);
CREATE INDEX IF NOT EXISTS idx_propiedades_staging_geocoding_status
    ON public.propiedades_staging(geocoding_status, status);
CREATE INDEX IF NOT EXISTS idx_propiedades_staging_hash_dedup
    ON public.propiedades_staging(hash_dedup);
CREATE INDEX IF NOT EXISTS idx_propiedades_staging_inmobiliaria_id
    ON public.propiedades_staging(inmobiliaria_id);
CREATE INDEX IF NOT EXISTS idx_propiedades_staging_url_normalizada
    ON public.propiedades_staging(url_normalizada);


-- -----------------------------------------------------------------------------
-- Tabla: publish_queue
-- Cola interna para publicar cambios diarios hacia Supabase.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.publish_queue (
    id                    BIGSERIAL PRIMARY KEY,
    staging_id            BIGINT REFERENCES public.propiedades_staging(id)
                          ON DELETE SET NULL,
    propiedad_supabase_id BIGINT,
    action                TEXT NOT NULL DEFAULT 'upsert',
    priority              SMALLINT DEFAULT 1,
    attempts              SMALLINT DEFAULT 0,
    last_attempt_at       TIMESTAMPTZ,
    error_message         TEXT,
    status                TEXT NOT NULL DEFAULT 'pending',
    queued_at             TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT publish_queue_action_chk
        CHECK (action IN ('upsert','deactivate')),
    CONSTRAINT publish_queue_status_chk
        CHECK (status IN ('pending','publishing','done','failed'))
);

CREATE INDEX IF NOT EXISTS idx_publish_queue_status_priority_queued
    ON public.publish_queue(status, priority, queued_at);
CREATE INDEX IF NOT EXISTS idx_publish_queue_staging_id
    ON public.publish_queue(staging_id);
CREATE INDEX IF NOT EXISTS idx_publish_queue_propiedad_supabase_id
    ON public.publish_queue(propiedad_supabase_id);


-- -----------------------------------------------------------------------------
-- Tabla: data_quality_issues
-- Observaciones de calidad detectadas durante validacion y staging.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.data_quality_issues (
    id            BIGSERIAL PRIMARY KEY,
    raw_id        BIGINT REFERENCES public.propiedades_raw(id)
                  ON DELETE SET NULL,
    issue_type    TEXT NOT NULL,
    issue_detail  TEXT,
    detected_at   TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_data_quality_issues_raw_id
    ON public.data_quality_issues(raw_id);
CREATE INDEX IF NOT EXISTS idx_data_quality_issues_issue_type
    ON public.data_quality_issues(issue_type);
CREATE INDEX IF NOT EXISTS idx_data_quality_issues_detected_at
    ON public.data_quality_issues(detected_at);


-- -----------------------------------------------------------------------------
-- Tabla: daily_update_summary
-- Resumen agregado de cada ciclo diario de scraping, staging y publicacion.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.daily_update_summary (
    id                           BIGSERIAL PRIMARY KEY,
    run_date                     DATE NOT NULL UNIQUE,
    inmobiliarias_intentadas     INT DEFAULT 0,
    inmobiliarias_ok             INT DEFAULT 0,
    inmobiliarias_error          INT DEFAULT 0,
    propiedades_scraped          INT DEFAULT 0,
    propiedades_nuevas           INT DEFAULT 0,
    propiedades_actualizadas     INT DEFAULT 0,
    propiedades_publicadas       INT DEFAULT 0,
    propiedades_rechazadas       INT DEFAULT 0,
    geocoding_ok                 INT DEFAULT 0,
    geocoding_failed             INT DEFAULT 0,
    duracion_segundos            INT DEFAULT 0,
    notas                        TEXT,
    created_at                   TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_daily_update_summary_run_date
    ON public.daily_update_summary(run_date);


-- -----------------------------------------------------------------------------
-- cleanup_old_neon_data()
-- Limpia datos internos historicos que ya no hacen falta para operacion diaria.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.cleanup_old_neon_data()
RETURNS VOID
LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM public.publish_queue
     WHERE status = 'done'
       AND queued_at < now() - INTERVAL '7 days';

    DELETE FROM public.propiedades_staging
     WHERE status = 'published'
       AND staged_at < now() - INTERVAL '14 days';

    DELETE FROM public.propiedades_raw
     WHERE status = 'published'
       AND scraped_at < now() - INTERVAL '30 days';

    DELETE FROM public.propiedades_raw
     WHERE status = 'rejected'
       AND scraped_at < now() - INTERVAL '7 days';

    DELETE FROM public.scraping_run_items
     WHERE created_at < now() - INTERVAL '90 days';

    DELETE FROM public.data_quality_issues
     WHERE detected_at < now() - INTERVAL '60 days';
END;
$$;


-- =============================================================================
-- FIN
-- =============================================================================
-- Para aplicar:
--   psql "$INTERNAL_DB_URL" -f internal_db_schema.sql
-- Para verificar:
--   psql "$INTERNAL_DB_URL" -c "\dt public.*"
--   psql "$INTERNAL_DB_URL" -c "\df public.*"
-- Documentacion completa: docs/INTERNAL_DB_SETUP.md
-- =============================================================================
