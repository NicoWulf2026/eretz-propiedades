-- Historial de precios de una publicación.
--
-- Prepara la infraestructura para construir HISTORIA FUTURA de precios sin
-- inventar pasado. NO hace backfill ni genera precios ficticios. El proceso de
-- actualización/scraping (otro pipeline) debe insertar una fila cuando detecte un
-- cambio de precio: (propiedad_id, precio, moneda, observado_en, contexto).
--
-- Idempotente y aditiva. No modifica RLS ni tablas congeladas. Sin grants (sólo
-- el owner/rol de escritura accede). Punto de integración documentado abajo.

CREATE TABLE IF NOT EXISTS public.listing_price_history (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  propiedad_id bigint NOT NULL,
  precio       numeric NOT NULL,
  moneda       text,
  observado_en timestamptz NOT NULL DEFAULT now(),
  contexto     text
);

CREATE INDEX IF NOT EXISTS listing_price_history_propiedad_idx
  ON public.listing_price_history (propiedad_id, observado_en);

COMMENT ON TABLE public.listing_price_history IS
  'Historial de precios (sólo futuro; sin backfill). El pipeline de actualización inserta al detectar cambio de precio.';

-- PUNTO DE INTEGRACIÓN: el read-model de la app (getPriceHistory) lee esta tabla
-- sólo cuando ERETZ_PRICE_HISTORY=1. Activar tras (a) ejecutar esta migración y
-- (b) conectar el pipeline de actualización para que inserte filas.
