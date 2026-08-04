-- Non-destructive rollback. Retains flag definitions/view for evidence but
-- revokes service access and restores the previous active-state expression.

BEGIN;

REVOKE ALL ON public.v_property_quality_flags_v2
    FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON public.property_quality_flag_definitions
    FROM PUBLIC, anon, authenticated, service_role;

DO $policies$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'propiedades'
          AND policyname = 'Public read active properties'
    ) THEN
        ALTER POLICY "Public read active properties" ON public.propiedades
            TO anon
            USING (estado = 'activo');
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'propiedades'
          AND policyname = 'propiedades_public_read'
    ) THEN
        ALTER POLICY propiedades_public_read ON public.propiedades
            TO anon, authenticated
            USING (estado = 'activo');
    END IF;
END
$policies$;

DO $legacy_view$
DECLARE
    view_definition text;
BEGIN
    IF to_regclass('public.v_property_data_quality') IS NOT NULL THEN
        SELECT pg_get_viewdef('public.v_property_data_quality'::regclass, true)
        INTO view_definition;
        IF view_definition LIKE '%estado = ''activa''::text%' THEN
            view_definition := replace(
                view_definition,
                'estado = ''activa''::text',
                'estado = ''activo''::text'
            );
            EXECUTE 'CREATE OR REPLACE VIEW public.v_property_data_quality AS '
                || view_definition;
        END IF;
    END IF;
END
$legacy_view$;

COMMIT;
