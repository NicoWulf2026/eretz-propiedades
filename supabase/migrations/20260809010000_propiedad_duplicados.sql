-- Agrupación de "misma propiedad física" publicada varias veces.
--
-- Metadato REVERSIBLE y AUDITABLE: nunca borra ni fusiona publicaciones; sólo
-- registra a qué grupo pertenece cada una y con qué confianza. La lógica de
-- scoring/bloqueo vive en la app (src/lib/duplicates.ts). Idempotente.

CREATE TABLE IF NOT EXISTS public.propiedad_duplicados (
  grupo_id     text NOT NULL,
  propiedad_id bigint NOT NULL,
  confianza    text NOT NULL DEFAULT 'HIGH_CONFIDENCE'
                 CHECK (confianza IN ('HIGH_CONFIDENCE', 'POSSIBLE_MATCH')),
  score        numeric,
  creado_en    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (grupo_id, propiedad_id)
);

CREATE INDEX IF NOT EXISTS propiedad_duplicados_propiedad_idx
  ON public.propiedad_duplicados (propiedad_id);

COMMENT ON TABLE public.propiedad_duplicados IS
  'Grupos de duplicados (metadato reversible). No fusiona ni borra publicaciones.';
