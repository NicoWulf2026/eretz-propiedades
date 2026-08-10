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

-- Seguridad: RLS habilitado SIN policies -> deny-all para anon/authenticated.
-- Escritura por rol server (service_role/owner). La app NO lee esta tabla.
ALTER TABLE public.reportes_publicacion ENABLE ROW LEVEL SECURITY;
