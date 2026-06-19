-- =============================================================================
-- MIGRACIÓN Phase 3 — Schema internal_scraping en Supabase Pro
-- =============================================================================
-- Fecha: 2026-06-16
-- Origen: Neon (PostgreSQL 17.10) — tablas del pipeline de scraping
-- Destino: Supabase Pro — schema internal_scraping (PostgreSQL 17.6)
--
-- OBJETIVO:
--   Crear todas las tablas, índices, constraints y funciones RPC del pipeline
--   de scraping bajo el schema internal_scraping, reemplazando el acceso a Neon.
--
-- PREREQUISITO:
--   Schema internal_scraping debe existir y estar vacío.
--   Ejecutar migrations/phase2_step3_create_schemas.sql si no fue ejecutado.
--
-- ORDEN DE CREACIÓN (respeta dependencias FK):
--   1. scraping_runs            (sin dependencias)
--   2. scraping_run_items       (→ scraping_runs)
--   3. propiedades_raw          (→ scraping_run_items)
--   4. propiedades_staging      (→ propiedades_raw)
--   5. data_quality_issues      (→ propiedades_raw)
--   6. publish_queue            (→ propiedades_staging)
--   7. geocoding_results        (sin dependencias)
--   8. daily_update_summary     (sin dependencias)
--   9. inmobiliarias_staging    (sin dependencias)
--  10. Funciones RPC            (→ internal_scraping.scraping_runs/items)
--
-- IDEMPOTENTE: CREATE TABLE/INDEX IF NOT EXISTS — se puede ejecutar varias veces.
-- SIN DROP, DELETE, TRUNCATE.
-- SIN cambios a public.propiedades ni otras tablas de public.
--
-- Neon permanece INTACTO como respaldo hasta confirmación explícita de borrado.
-- =============================================================================


-- =============================================================================
-- 1. scraping_runs
--    Una fila por tanda (run). Acumula totales que el scraper incrementa en cada
--    finish_scraping_item_success/error.
-- =============================================================================
CREATE TABLE IF NOT EXISTS internal_scraping.scraping_runs (
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
    ON internal_scraping.scraping_runs(status);
CREATE INDEX IF NOT EXISTS idx_scraping_runs_started_at
    ON internal_scraping.scraping_runs(started_at DESC);

-- Permiso de acceso para service_role (bypass RLS, pero GRANT necesario en Supabase)
GRANT ALL ON internal_scraping.scraping_runs TO service_role;
GRANT USAGE, SELECT ON SEQUENCE internal_scraping.scraping_runs_id_seq TO service_role;


-- =============================================================================
-- 2. scraping_run_items
--    Una fila por inmobiliaria a procesar dentro de una run.
-- =============================================================================
CREATE TABLE IF NOT EXISTS internal_scraping.scraping_run_items (
    id                          BIGSERIAL PRIMARY KEY,
    scraping_run_id             BIGINT NOT NULL
                                REFERENCES internal_scraping.scraping_runs(id) ON DELETE CASCADE,
    inmobiliaria_id             INTEGER NOT NULL,
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
    ON internal_scraping.scraping_run_items(scraping_run_id);
CREATE INDEX IF NOT EXISTS idx_items_status
    ON internal_scraping.scraping_run_items(status);
CREATE INDEX IF NOT EXISTS idx_items_status_created
    ON internal_scraping.scraping_run_items(status, created_at);
CREATE INDEX IF NOT EXISTS idx_items_error_type
    ON internal_scraping.scraping_run_items(error_type) WHERE error_type IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_items_inmo_status
    ON internal_scraping.scraping_run_items(inmobiliaria_id, status);

GRANT ALL ON internal_scraping.scraping_run_items TO service_role;
GRANT USAGE, SELECT ON SEQUENCE internal_scraping.scraping_run_items_id_seq TO service_role;


-- =============================================================================
-- 3. propiedades_raw
--    Captura cruda de propiedades detectadas por scraping.
-- =============================================================================
CREATE TABLE IF NOT EXISTS internal_scraping.propiedades_raw (
    id                    BIGSERIAL PRIMARY KEY,
    scraping_run_item_id  BIGINT REFERENCES internal_scraping.scraping_run_items(id)
                          ON DELETE SET NULL,
    inmobiliaria_id       INTEGER NOT NULL,
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
    ON internal_scraping.propiedades_raw(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_propiedades_raw_hash_dedup
    ON internal_scraping.propiedades_raw(hash_dedup);
CREATE INDEX IF NOT EXISTS idx_propiedades_raw_inmobiliaria_status
    ON internal_scraping.propiedades_raw(inmobiliaria_id, status);
CREATE INDEX IF NOT EXISTS idx_propiedades_raw_scraped_at
    ON internal_scraping.propiedades_raw(scraped_at);
CREATE INDEX IF NOT EXISTS idx_propiedades_raw_url_normalizada
    ON internal_scraping.propiedades_raw(url_normalizada);

GRANT ALL ON internal_scraping.propiedades_raw TO service_role;
GRANT USAGE, SELECT ON SEQUENCE internal_scraping.propiedades_raw_id_seq TO service_role;


-- =============================================================================
-- 4. propiedades_staging
--    Propiedades normalizadas y listas para validación / cola de publicación.
-- =============================================================================
CREATE TABLE IF NOT EXISTS internal_scraping.propiedades_staging (
    id                    BIGSERIAL PRIMARY KEY,
    raw_id                BIGINT REFERENCES internal_scraping.propiedades_raw(id)
                          ON DELETE SET NULL,
    inmobiliaria_id       INTEGER NOT NULL,
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
    ON internal_scraping.propiedades_staging(status);
CREATE INDEX IF NOT EXISTS idx_propiedades_staging_geocoding_status
    ON internal_scraping.propiedades_staging(geocoding_status, status);
CREATE INDEX IF NOT EXISTS idx_propiedades_staging_hash_dedup
    ON internal_scraping.propiedades_staging(hash_dedup);
CREATE INDEX IF NOT EXISTS idx_propiedades_staging_inmobiliaria_id
    ON internal_scraping.propiedades_staging(inmobiliaria_id);
CREATE INDEX IF NOT EXISTS idx_propiedades_staging_url_normalizada
    ON internal_scraping.propiedades_staging(url_normalizada);
-- CRÍTICO: sin este índice, build_publish_queue.py timeout en 78k+ filas
CREATE INDEX IF NOT EXISTS idx_propiedades_staging_status_score_id
    ON internal_scraping.propiedades_staging(status, validation_score DESC, id ASC);

GRANT ALL ON internal_scraping.propiedades_staging TO service_role;
GRANT USAGE, SELECT ON SEQUENCE internal_scraping.propiedades_staging_id_seq TO service_role;


-- =============================================================================
-- 5. data_quality_issues
--    Observaciones de calidad detectadas durante validación y staging.
-- =============================================================================
CREATE TABLE IF NOT EXISTS internal_scraping.data_quality_issues (
    id            BIGSERIAL PRIMARY KEY,
    raw_id        BIGINT REFERENCES internal_scraping.propiedades_raw(id)
                  ON DELETE SET NULL,
    issue_type    TEXT NOT NULL,
    issue_detail  TEXT,
    detected_at   TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_data_quality_issues_raw_id
    ON internal_scraping.data_quality_issues(raw_id);
CREATE INDEX IF NOT EXISTS idx_data_quality_issues_issue_type
    ON internal_scraping.data_quality_issues(issue_type);
CREATE INDEX IF NOT EXISTS idx_data_quality_issues_detected_at
    ON internal_scraping.data_quality_issues(detected_at);

GRANT ALL ON internal_scraping.data_quality_issues TO service_role;
GRANT USAGE, SELECT ON SEQUENCE internal_scraping.data_quality_issues_id_seq TO service_role;


-- =============================================================================
-- 6. publish_queue
--    Cola interna para publicar cambios diarios hacia Supabase public.propiedades.
-- =============================================================================
CREATE TABLE IF NOT EXISTS internal_scraping.publish_queue (
    id                    BIGSERIAL PRIMARY KEY,
    staging_id            BIGINT REFERENCES internal_scraping.propiedades_staging(id)
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
    ON internal_scraping.publish_queue(status, priority, queued_at);
CREATE INDEX IF NOT EXISTS idx_publish_queue_staging_id
    ON internal_scraping.publish_queue(staging_id);
CREATE INDEX IF NOT EXISTS idx_publish_queue_propiedad_supabase_id
    ON internal_scraping.publish_queue(propiedad_supabase_id);

GRANT ALL ON internal_scraping.publish_queue TO service_role;
GRANT USAGE, SELECT ON SEQUENCE internal_scraping.publish_queue_id_seq TO service_role;


-- =============================================================================
-- 7. geocoding_results
--    Cache de geocoding generado por scraper/geocoder.py.
--    propiedad_id referencia lógicamente propiedades.id en public (sin FK cross-schema).
-- =============================================================================
CREATE TABLE IF NOT EXISTS internal_scraping.geocoding_results (
    id                    BIGSERIAL PRIMARY KEY,
    propiedad_id          BIGINT NOT NULL,
    direccion_geocoding   TEXT NOT NULL,
    latitud               DOUBLE PRECISION,
    longitud              DOUBLE PRECISION,
    precision_geocoding   TEXT,
    proveedor             TEXT,
    raw_response          JSONB,
    status                TEXT NOT NULL DEFAULT 'pending',
    error_message         TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_geocoding_propiedad_id
    ON internal_scraping.geocoding_results(propiedad_id);
CREATE INDEX IF NOT EXISTS idx_geocoding_propiedad_direccion
    ON internal_scraping.geocoding_results(propiedad_id, direccion_geocoding);
CREATE INDEX IF NOT EXISTS idx_geocoding_status_coords
    ON internal_scraping.geocoding_results(status, latitud, longitud)
    WHERE latitud IS NOT NULL AND longitud IS NOT NULL;

GRANT ALL ON internal_scraping.geocoding_results TO service_role;
GRANT USAGE, SELECT ON SEQUENCE internal_scraping.geocoding_results_id_seq TO service_role;


-- =============================================================================
-- 8. daily_update_summary
--    Resumen agregado de cada ciclo diario de scraping, staging y publicación.
-- =============================================================================
CREATE TABLE IF NOT EXISTS internal_scraping.daily_update_summary (
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

GRANT ALL ON internal_scraping.daily_update_summary TO service_role;
GRANT USAGE, SELECT ON SEQUENCE internal_scraping.daily_update_summary_id_seq TO service_role;


-- =============================================================================
-- 9. inmobiliarias_staging
--    Buffer de imports puntuales antes de promover a inmobiliarias_main (public).
-- =============================================================================
CREATE TABLE IF NOT EXISTS internal_scraping.inmobiliarias_staging (
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
    ON internal_scraping.inmobiliarias_staging(fuente);
CREATE INDEX IF NOT EXISTS idx_staging_needs_review
    ON internal_scraping.inmobiliarias_staging(needs_manual_review)
    WHERE needs_manual_review = true;
CREATE INDEX IF NOT EXISTS idx_staging_nombre_normalizado
    ON internal_scraping.inmobiliarias_staging(nombre_normalizado);

GRANT ALL ON internal_scraping.inmobiliarias_staging TO service_role;
GRANT USAGE, SELECT ON SEQUENCE internal_scraping.inmobiliarias_staging_id_seq TO service_role;


-- =============================================================================
-- 10. FUNCIONES RPC — adaptadas para internal_scraping schema
--     Replican las funciones de public que usa InternalDBClient
--     (scraper/scraper_propiedades.py::_RPC_ARGUMENTS).
--     Nota: todas usan nombres completamente calificados (internal_scraping.tabla).
-- =============================================================================

-- claim_next_scraping_item()
-- Toma el siguiente item 'pending' con FOR UPDATE SKIP LOCKED.
CREATE OR REPLACE FUNCTION internal_scraping.claim_next_scraping_item()
RETURNS internal_scraping.scraping_run_items
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = internal_scraping, public
AS $$
DECLARE
    claimed internal_scraping.scraping_run_items;
BEGIN
    UPDATE internal_scraping.scraping_run_items
       SET status      = 'running',
           started_at  = COALESCE(scraping_run_items.started_at, now()),
           updated_at  = now()
     WHERE id = (
            SELECT id
              FROM internal_scraping.scraping_run_items
             WHERE status = 'pending'
             ORDER BY created_at ASC
             FOR UPDATE SKIP LOCKED
             LIMIT 1
         )
    RETURNING * INTO claimed;
    RETURN claimed;
END;
$$;

GRANT EXECUTE ON FUNCTION internal_scraping.claim_next_scraping_item() TO service_role;


-- start_scraping_item(item_id BIGINT)
CREATE OR REPLACE FUNCTION internal_scraping.start_scraping_item(item_id BIGINT)
RETURNS internal_scraping.scraping_run_items
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = internal_scraping, public
AS $$
DECLARE row_out internal_scraping.scraping_run_items;
BEGIN
    UPDATE internal_scraping.scraping_run_items
       SET status      = 'running',
           started_at  = COALESCE(scraping_run_items.started_at, now()),
           updated_at  = now()
     WHERE id = start_scraping_item.item_id
    RETURNING * INTO row_out;
    RETURN row_out;
END;
$$;

GRANT EXECUTE ON FUNCTION internal_scraping.start_scraping_item(BIGINT) TO service_role;


-- retry_scraping_item(item_id BIGINT)
CREATE OR REPLACE FUNCTION internal_scraping.retry_scraping_item(item_id BIGINT)
RETURNS internal_scraping.scraping_run_items
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = internal_scraping, public
AS $$
DECLARE row_out internal_scraping.scraping_run_items;
BEGIN
    UPDATE internal_scraping.scraping_run_items
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

GRANT EXECUTE ON FUNCTION internal_scraping.retry_scraping_item(BIGINT) TO service_role;


-- finish_scraping_item_success(...)
CREATE OR REPLACE FUNCTION internal_scraping.finish_scraping_item_success(
    item_id                  BIGINT,
    propiedades_detectadas   INTEGER,
    propiedades_nuevas       INTEGER,
    propiedades_actualizadas INTEGER,
    propiedades_sin_cambios  INTEGER,
    propiedades_error        INTEGER,
    final_url                TEXT,
    metadata_json            JSONB
) RETURNS internal_scraping.scraping_run_items
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = internal_scraping, public
AS $$
DECLARE
    row_out internal_scraping.scraping_run_items;
BEGIN
    UPDATE internal_scraping.scraping_run_items AS i
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
        UPDATE internal_scraping.scraping_runs AS r
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

GRANT EXECUTE ON FUNCTION internal_scraping.finish_scraping_item_success(BIGINT,INTEGER,INTEGER,INTEGER,INTEGER,INTEGER,TEXT,JSONB) TO service_role;


-- finish_scraping_item_error(...)
CREATE OR REPLACE FUNCTION internal_scraping.finish_scraping_item_error(
    item_id        BIGINT,
    error_message  TEXT,
    error_type     TEXT,
    http_status    INTEGER,
    final_url      TEXT,
    metadata_json  JSONB
) RETURNS internal_scraping.scraping_run_items
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = internal_scraping, public
AS $$
DECLARE
    row_out internal_scraping.scraping_run_items;
BEGIN
    UPDATE internal_scraping.scraping_run_items AS i
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
        UPDATE internal_scraping.scraping_runs AS r
           SET total_inmobiliarias_procesadas = r.total_inmobiliarias_procesadas + 1,
               total_inmobiliarias_error      = r.total_inmobiliarias_error      + 1,
               updated_at                     = now()
         WHERE r.id = row_out.scraping_run_id;
    END IF;

    RETURN row_out;
END;
$$;

GRANT EXECUTE ON FUNCTION internal_scraping.finish_scraping_item_error(BIGINT,TEXT,TEXT,INTEGER,TEXT,JSONB) TO service_role;


-- close_scraping_run_if_finished(run_id BIGINT)
CREATE OR REPLACE FUNCTION internal_scraping.close_scraping_run_if_finished(run_id BIGINT)
RETURNS internal_scraping.scraping_runs
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = internal_scraping, public
AS $$
DECLARE
    pending_count INTEGER;
    row_out       internal_scraping.scraping_runs;
BEGIN
    SELECT COUNT(*) INTO pending_count
      FROM internal_scraping.scraping_run_items
     WHERE scraping_run_id = close_scraping_run_if_finished.run_id
       AND status IN ('pending','running');

    IF pending_count = 0 THEN
        UPDATE internal_scraping.scraping_runs AS r
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
          FROM internal_scraping.scraping_runs
         WHERE id = close_scraping_run_if_finished.run_id;
    END IF;

    RETURN row_out;
END;
$$;

GRANT EXECUTE ON FUNCTION internal_scraping.close_scraping_run_if_finished(BIGINT) TO service_role;


-- cleanup_old_data()
-- Limpia datos históricos del pipeline que ya no hacen falta para operación diaria.
CREATE OR REPLACE FUNCTION internal_scraping.cleanup_old_data()
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = internal_scraping, public
AS $$
BEGIN
    DELETE FROM internal_scraping.publish_queue
     WHERE status = 'done'
       AND queued_at < now() - INTERVAL '7 days';

    DELETE FROM internal_scraping.propiedades_staging
     WHERE status = 'published'
       AND staged_at < now() - INTERVAL '14 days';

    DELETE FROM internal_scraping.propiedades_raw
     WHERE status = 'published'
       AND scraped_at < now() - INTERVAL '30 days';

    DELETE FROM internal_scraping.propiedades_raw
     WHERE status = 'rejected'
       AND scraped_at < now() - INTERVAL '7 days';

    DELETE FROM internal_scraping.scraping_run_items
     WHERE created_at < now() - INTERVAL '90 days';

    DELETE FROM internal_scraping.data_quality_issues
     WHERE detected_at < now() - INTERVAL '60 days';
END;
$$;

GRANT EXECUTE ON FUNCTION internal_scraping.cleanup_old_data() TO service_role;


-- =============================================================================
-- VERIFICACIÓN POST-EJECUCIÓN
-- =============================================================================

-- Debe listar todas las tablas creadas (9 tablas esperadas)
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'internal_scraping'
ORDER BY table_name;

-- Debe listar todas las funciones (7 funciones esperadas)
SELECT routine_name, routine_type
FROM information_schema.routines
WHERE routine_schema = 'internal_scraping'
ORDER BY routine_name;

-- =============================================================================
-- RESULTADO ESPERADO:
--   9 tablas: daily_update_summary, data_quality_issues, geocoding_results,
--             inmobiliarias_staging, propiedades_raw, propiedades_staging,
--             publish_queue, scraping_run_items, scraping_runs
--   7 funciones: claim_next_scraping_item, cleanup_old_data,
--                close_scraping_run_if_finished, finish_scraping_item_error,
--                finish_scraping_item_success, retry_scraping_item,
--                start_scraping_item
-- =============================================================================
