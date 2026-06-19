-- =============================================================================
-- Fase B.1 — Agregar queue_id a error_log (rastreo de la fila exacta de publish_queue)
-- =============================================================================
-- Fecha: 2026-06-17 · Idempotente, no destructivo.
-- Motivo: para errores de publish es útil rastrear la fila exacta de publish_queue
-- sin sobrecargar el significado de propiedad_id (que es una propiedad real).
-- =============================================================================

ALTER TABLE internal_scraping.error_log
    ADD COLUMN IF NOT EXISTS queue_id BIGINT;

CREATE INDEX IF NOT EXISTS idx_error_log_queue_id
    ON internal_scraping.error_log(queue_id);
