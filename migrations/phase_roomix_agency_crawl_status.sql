-- =============================================================================
-- ROOMIX AGENCY COVERAGE — Heartbeat remoto del crawler (telemetría)
-- =============================================================================
-- Fecha: 2026-08-18 · Proyecto: ERETZ Propiedades
-- Idempotente (IF NOT EXISTS / CREATE OR REPLACE). No destructivo.
-- Solo crea objetos nuevos en internal_scraping. No toca tablas/datos existentes.
--
-- ALCANCE: esta tabla es un ESPEJO DE TELEMETRÍA del crawler Roomix.
--   - NO es fuente de verdad del crawl (esa sigue siendo el checkpoint local).
--   - NO almacena propiedades, precios, descripciones, fotos ni características.
--   - NO almacena secretos, DB URLs ni tokens.
--   - El rol de escritura NO tiene acceso alguno a inmobiliarias_main/staging.
-- =============================================================================

CREATE TABLE IF NOT EXISTS internal_scraping.roomix_agency_crawl_status (
    run_id                        TEXT PRIMARY KEY,
    status                        TEXT NOT NULL DEFAULT 'RUNNING',

    -- Progreso del universo enumerable
    processed_listings            BIGINT  NOT NULL DEFAULT 0,
    total_listings                BIGINT,
    completion_pct                NUMERIC(6,3)
        GENERATED ALWAYS AS (
            CASE
                WHEN total_listings IS NULL OR total_listings <= 0 THEN NULL
                ELSE ROUND(LEAST(processed_listings::numeric / total_listings::numeric, 1) * 100, 3)
            END
        ) STORED,

    -- RAW vs CANONICAL (métricas distintas; invariante raw >= canonical)
    raw_publisher_identities      BIGINT NOT NULL DEFAULT 0,
    canonical_publisher_entities  BIGINT NOT NULL DEFAULT 0,
    aliases_merged                BIGINT NOT NULL DEFAULT 0,

    -- Clasificación canónica
    inmobiliarias                 BIGINT NOT NULL DEFAULT 0,
    oficinas_franquicia           BIGINT NOT NULL DEFAULT 0,
    agentes                       BIGINT NOT NULL DEFAULT 0,
    developers                    BIGINT NOT NULL DEFAULT 0,
    unknown                       BIGINT NOT NULL DEFAULT 0,
    garbage                       BIGINT NOT NULL DEFAULT 0,

    -- Padrón objetivo = INMOBILIARIA + OFICINA_FRANQUICIA (invariante en la DB)
    real_estate_entities          BIGINT
        GENERATED ALWAYS AS (inmobiliarias + oficinas_franquicia) STORED,

    -- Salud del crawl
    errors_total                  BIGINT NOT NULL DEFAULT 0,
    inaccessible_total            BIGINT NOT NULL DEFAULT 0,

    -- Reanudación (referencia; la fuente de verdad es el checkpoint local)
    last_checkpoint               TEXT,
    last_listing_ref              TEXT,        -- sanitizado: sin querystring, redactado

    -- Tiempos
    started_at                    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_heartbeat_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    eta_seconds                   BIGINT,

    -- Versionado
    matcher_version               TEXT,
    crawler_version               TEXT,

    CONSTRAINT roomix_crawl_status_chk
        CHECK (status IN ('RUNNING','PAUSED','RETRYING','STALLED','COMPLETED','FAILED')),
    CONSTRAINT roomix_crawl_raw_ge_canonical_chk
        CHECK (raw_publisher_identities >= canonical_publisher_entities)
);

CREATE INDEX IF NOT EXISTS idx_roomix_crawl_status_status
    ON internal_scraping.roomix_agency_crawl_status(status);
CREATE INDEX IF NOT EXISTS idx_roomix_crawl_status_heartbeat
    ON internal_scraping.roomix_agency_crawl_status(last_heartbeat_at DESC);

COMMENT ON TABLE internal_scraping.roomix_agency_crawl_status IS
    'Espejo de telemetría del crawler Roomix Agency Coverage. No es fuente de verdad: '
    'el checkpoint local manda. Sin datos de propiedades ni secretos.';

-- -----------------------------------------------------------------------------
-- Rol de escritura de PRIVILEGIO MÍNIMO — sólo esta tabla, sólo telemetría.
-- No LOGIN (es un rol de privilegios, se usa vía SET LOCAL ROLE, igual que
-- eretz_agency_coverage_writer). No toca inmobiliarias_main ni _staging.
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eretz_roomix_heartbeat_writer') THEN
        CREATE ROLE eretz_roomix_heartbeat_writer
            NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
            NOINHERIT NOREPLICATION NOBYPASSRLS;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA internal_scraping TO eretz_roomix_heartbeat_writer;
GRANT SELECT, INSERT, UPDATE ON internal_scraping.roomix_agency_crawl_status
    TO eretz_roomix_heartbeat_writer;
-- Sin DELETE: la telemetría no se borra desde el crawler.
-- Sin permisos sobre ninguna otra tabla: el monitor no puede tocar
-- public.inmobiliarias_main ni public.inmobiliarias_staging.

GRANT ALL ON internal_scraping.roomix_agency_crawl_status TO service_role;

ALTER TABLE internal_scraping.roomix_agency_crawl_status ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS roomix_crawl_status_heartbeat_rw
    ON internal_scraping.roomix_agency_crawl_status;
CREATE POLICY roomix_crawl_status_heartbeat_rw
    ON internal_scraping.roomix_agency_crawl_status
    FOR ALL TO eretz_roomix_heartbeat_writer
    USING (true) WITH CHECK (true);

-- -----------------------------------------------------------------------------
-- Vista de monitoreo: agrega detección de STALL en el lado lectura.
-- Un crawler RUNNING sin heartbeat por más de 30 min se reporta STALLED,
-- sin que el crawler tenga que matarse ni relanzarse por eso.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW internal_scraping.v_roomix_agency_crawl_monitor AS
SELECT
    run_id,
    status,
    CASE
        WHEN status = 'RUNNING'
         AND last_heartbeat_at < now() - INTERVAL '30 minutes' THEN 'STALLED'
        ELSE status
    END                                             AS effective_status,
    processed_listings,
    total_listings,
    completion_pct,
    real_estate_entities,
    inmobiliarias,
    oficinas_franquicia,
    agentes,
    developers,
    unknown,
    garbage,
    raw_publisher_identities,
    canonical_publisher_entities,
    aliases_merged,
    errors_total,
    inaccessible_total,
    eta_seconds,
    last_heartbeat_at,
    now() - last_heartbeat_at                       AS heartbeat_age,
    started_at,
    last_checkpoint,
    crawler_version,
    matcher_version
FROM internal_scraping.roomix_agency_crawl_status;

GRANT SELECT ON internal_scraping.v_roomix_agency_crawl_monitor TO service_role;

-- -----------------------------------------------------------------------------
-- Lectura del monitor para la conexión Preview ya existente (eretz_preview_ro),
-- que es la que se usa para consultar el progreso desde cualquier dispositivo.
-- Estrictamente SELECT y estrictamente sobre la VISTA: no puede escribir
-- telemetría ni acceder a ninguna otra tabla del schema.
-- Condicional: si el rol no existe en este entorno, la migración no falla.
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eretz_preview_ro') THEN
        GRANT USAGE ON SCHEMA internal_scraping TO eretz_preview_ro;
        GRANT SELECT ON internal_scraping.v_roomix_agency_crawl_monitor TO eretz_preview_ro;
    END IF;
END
$$;
