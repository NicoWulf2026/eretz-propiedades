-- =============================================================================
-- Fase A-bis — Logging mínimo: tabla error_log + vistas de resumen
-- =============================================================================
-- Fecha: 2026-06-17 · Proyecto: ERETZ Propiedades
-- Idempotente (IF NOT EXISTS / CREATE OR REPLACE). No destructivo.
-- Solo crea objetos nuevos en internal_scraping. No toca tablas/datos existentes.
-- =============================================================================

CREATE TABLE IF NOT EXISTS internal_scraping.error_log (
    id                        BIGSERIAL PRIMARY KEY,
    run_id                    BIGINT,                     -- 1
    inmobiliaria_id           INTEGER,                    -- 2
    inmobiliaria_nombre       TEXT,                       -- 3
    source_url                TEXT,                       -- 4 (redactada)
    fase                      TEXT NOT NULL,              -- 5 scraping|validate|geocode|build_queue|publish|drain|orchestrator
    error_type                TEXT NOT NULL,              -- 6
    mensaje                   TEXT,                       -- 7 (resumido, redactado)
    detalle                   TEXT,                       -- 8 (traceback redactado/truncado)
    severidad                 TEXT NOT NULL DEFAULT 'warning',  -- critical|warning|soft|incomplete|prohibited_source
    recuperable               BOOLEAN,                    -- 9
    reintentos                INTEGER NOT NULL DEFAULT 0, -- 10
    accion_tomada             TEXT,                       -- 11
    estado_final              TEXT,                       -- 12
    ocurrido_en               TIMESTAMPTZ NOT NULL DEFAULT now(),  -- 13
    worker                    TEXT,                       -- 14
    afecto_publicacion        BOOLEAN,                    -- 15
    requiere_revision_manual  BOOLEAN NOT NULL DEFAULT false,      -- 16
    propiedad_id              BIGINT,                     -- granularidad extra
    raw_id                    BIGINT,
    CONSTRAINT error_log_severidad_chk
        CHECK (severidad IN ('critical','warning','soft','incomplete','prohibited_source'))
);

-- Índices mínimos recomendados
CREATE INDEX IF NOT EXISTS idx_error_log_run_id       ON internal_scraping.error_log(run_id);
CREATE INDEX IF NOT EXISTS idx_error_log_inmobiliaria ON internal_scraping.error_log(inmobiliaria_id);
CREATE INDEX IF NOT EXISTS idx_error_log_fase         ON internal_scraping.error_log(fase);
CREATE INDEX IF NOT EXISTS idx_error_log_error_type   ON internal_scraping.error_log(error_type);
CREATE INDEX IF NOT EXISTS idx_error_log_severidad    ON internal_scraping.error_log(severidad);
CREATE INDEX IF NOT EXISTS idx_error_log_ocurrido_en  ON internal_scraping.error_log(ocurrido_en DESC);

GRANT ALL ON internal_scraping.error_log TO service_role;
GRANT USAGE, SELECT ON SEQUENCE internal_scraping.error_log_id_seq TO service_role;

-- Resumen por corrida
CREATE OR REPLACE VIEW internal_scraping.v_error_summary_by_run AS
SELECT run_id, fase, severidad, error_type,
       COUNT(*) AS n,
       SUM((requiere_revision_manual)::int) AS requieren_revision,
       SUM((afecto_publicacion)::int)       AS afectaron_publicacion,
       MAX(ocurrido_en) AS ultimo
FROM internal_scraping.error_log
GROUP BY run_id, fase, severidad, error_type;

-- Resumen por inmobiliaria
CREATE OR REPLACE VIEW internal_scraping.v_error_summary_by_inmobiliaria AS
SELECT inmobiliaria_id, inmobiliaria_nombre, fase, severidad,
       COUNT(*) AS n,
       SUM((requiere_revision_manual)::int) AS requieren_revision,
       MAX(ocurrido_en) AS ultimo
FROM internal_scraping.error_log
GROUP BY inmobiliaria_id, inmobiliaria_nombre, fase, severidad;

GRANT SELECT ON internal_scraping.v_error_summary_by_run          TO service_role;
GRANT SELECT ON internal_scraping.v_error_summary_by_inmobiliaria TO service_role;
