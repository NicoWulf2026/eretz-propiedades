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

-- Seguridad: RLS habilitado. La app SÍ lee esta tabla vía el rol de sólo lectura
-- eretz_preview_ro (igual que public.propiedades). Se le da SELECT + policy USING
-- (true); anon/authenticated quedan deny-all. La escritura la hace un rol server
-- con BYPASSRLS/owner. Idempotente y guardado por existencia del rol.
ALTER TABLE public.listing_price_history ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eretz_preview_ro') THEN
    GRANT SELECT ON public.listing_price_history TO eretz_preview_ro;
    DROP POLICY IF EXISTS listing_price_history_ro_read ON public.listing_price_history;
    CREATE POLICY listing_price_history_ro_read
      ON public.listing_price_history FOR SELECT TO eretz_preview_ro USING (true);
  END IF;
END $$;

-- PUNTO DE INTEGRACIÓN: el read-model de la app (getPriceHistory) lee esta tabla
-- sólo cuando ERETZ_PRICE_HISTORY=1. Activar tras (a) ejecutar esta migración y
-- (b) conectar el pipeline de actualización para que inserte filas.
