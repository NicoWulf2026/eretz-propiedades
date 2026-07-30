-- ERETZ: align future property writes with the already deployed `activa`
-- contract. This migration changes no property row.

BEGIN;

ALTER TABLE public.propiedades
    ALTER COLUMN estado SET DEFAULT 'activa';

DO $policies$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'propiedades'
          AND policyname = 'Public read active properties'
    ) THEN
        ALTER POLICY "Public read active properties" ON public.propiedades
            TO anon
            USING (estado = 'activa');
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'propiedades'
          AND policyname = 'propiedades_public_read'
    ) THEN
        ALTER POLICY propiedades_public_read ON public.propiedades
            TO anon, authenticated
            USING (estado = 'activa');
    END IF;
END
$policies$;

DO $validate$
DECLARE
    default_expression text;
BEGIN
    SELECT pg_get_expr(ad.adbin, ad.adrelid)
      INTO default_expression
      FROM pg_attrdef ad
      JOIN pg_attribute attribute
        ON attribute.attrelid = ad.adrelid
       AND attribute.attnum = ad.adnum
     WHERE ad.adrelid = 'public.propiedades'::regclass
       AND attribute.attname = 'estado';

    IF default_expression IS DISTINCT FROM '''activa''::text' THEN
        RAISE EXCEPTION 'propiedades.estado default is not activa: %',
            default_expression;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'propiedades'
          AND policyname IN (
              'Public read active properties',
              'propiedades_public_read'
          )
          AND qual NOT LIKE '%estado = ''activa''%'
    ) THEN
        RAISE EXCEPTION 'public property policy is not aligned to activa';
    END IF;
END
$validate$;

COMMIT;

