-- Reportes de problemas en una publicación (precio incorrecto, no disponible,
-- duplicada, datos erróneos, etc.).
--
-- Se guarda como SEÑAL: no modifica ni oculta la publicación automáticamente. La
-- revisión es humana. Sin cuenta; anti-abuso por unicidad blanda. Idempotente.

CREATE TABLE IF NOT EXISTS public.reportes_publicacion (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  propiedad_id bigint NOT NULL,
  motivo       text NOT NULL
                 CHECK (motivo IN ('no_disponible', 'precio_incorrecto', 'duplicada', 'datos_erroneos', 'otro')),
  detalle      text,
  email        text,
  estado       text NOT NULL DEFAULT 'nuevo'
                 CHECK (estado IN ('nuevo', 'en_revision', 'resuelto', 'descartado')),
  creado_en    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS reportes_publicacion_propiedad_idx
  ON public.reportes_publicacion (propiedad_id);

COMMENT ON TABLE public.reportes_publicacion IS
  'Reportes de publicaciones (señal). No auto-modifica ni oculta; revisión humana.';

-- Seguridad: RLS habilitado. anon/authenticated -> deny-all. La app inserta con
-- el rol writer dedicado eretz_app_writer (sólo INSERT + policy de INSERT), nunca
-- anon/authenticated ni BYPASSRLS global. La app NO lee esta tabla. Idempotente y
-- guardado por existencia del rol writer.
ALTER TABLE public.reportes_publicacion ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eretz_app_writer') THEN
    GRANT INSERT ON public.reportes_publicacion TO eretz_app_writer;
    DROP POLICY IF EXISTS reportes_publicacion_writer_insert ON public.reportes_publicacion;
    CREATE POLICY reportes_publicacion_writer_insert
      ON public.reportes_publicacion FOR INSERT TO eretz_app_writer WITH CHECK (true);
  END IF;
END $$;
