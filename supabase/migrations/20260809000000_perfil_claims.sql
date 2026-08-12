-- Reclamos de perfiles públicos (inmobiliarias / agentes).
--
-- Almacena la SEÑAL de un reclamo, sin auto-aprobar ni modificar el perfil. La
-- verificación posterior es humana (estado pending -> needs_review -> approved/
-- rejected). Idempotente y seguro de ejecutar.
--
-- NOTA: esta migración crea infraestructura para el flujo de reclamo. El rol de
-- sólo lectura del preview (eretz_preview_ro) NO recibe permisos de escritura
-- aquí; la persistencia real de reclamos requiere un rol con INSERT y un endpoint
-- server con esa credencial (fuera del preview de sólo lectura).

CREATE TABLE IF NOT EXISTS public.perfil_claims (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tipo          text NOT NULL DEFAULT 'inmobiliaria' CHECK (tipo IN ('inmobiliaria', 'agente')),
  entidad_id    bigint NOT NULL,
  nombre        text NOT NULL,
  email         text NOT NULL,
  telefono      text,
  rol           text,
  mensaje       text,
  estado        text NOT NULL DEFAULT 'pending'
                  CHECK (estado IN ('pending', 'approved', 'rejected', 'needs_review')),
  creado_en     timestamptz NOT NULL DEFAULT now(),
  actualizado_en timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS perfil_claims_entidad_idx
  ON public.perfil_claims (tipo, entidad_id);

-- Un reclamo pendiente por (tipo, entidad, email) para mitigar spam/duplicados.
CREATE UNIQUE INDEX IF NOT EXISTS perfil_claims_dedupe_idx
  ON public.perfil_claims (tipo, entidad_id, lower(email))
  WHERE estado = 'pending';

COMMENT ON TABLE public.perfil_claims IS
  'Reclamos de perfiles públicos. Señal, no auto-aprueba. Verificación humana posterior.';

-- Seguridad: RLS habilitado. anon/authenticated -> deny-all (sin policies para
-- ellos). La app inserta con el rol writer dedicado eretz_app_writer (mínimo
-- privilegio: sólo INSERT + policy de INSERT), NUNCA con anon/authenticated ni
-- BYPASSRLS global. La app NO lee esta tabla (no se le da SELECT). Idempotente y
-- guardado por existencia del rol writer.
ALTER TABLE public.perfil_claims ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE seq text;
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eretz_app_writer') THEN
    GRANT INSERT ON public.perfil_claims TO eretz_app_writer;
    -- USAGE sólo sobre la secuencia identity concreta (nombre resuelto de forma
    -- segura, sin depender del nombre generado ni tocar otras secuencias).
    seq := pg_get_serial_sequence('public.perfil_claims', 'id');
    IF seq IS NOT NULL THEN
      EXECUTE format('GRANT USAGE ON SEQUENCE %s TO eretz_app_writer', seq);
    END IF;
    DROP POLICY IF EXISTS perfil_claims_writer_insert ON public.perfil_claims;
    CREATE POLICY perfil_claims_writer_insert
      ON public.perfil_claims FOR INSERT TO eretz_app_writer WITH CHECK (true);
  END IF;
END $$;
