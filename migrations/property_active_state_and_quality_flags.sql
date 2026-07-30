-- ERETZ Propiedades: align the public active-state contract and expose
-- transparent, derived quality flags to service_role.
-- No property rows are modified.

BEGIN;

DO $policies$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'propiedades'
          AND policyname = 'Public read active properties'
    ) THEN
        ALTER POLICY "Public read active properties" ON public.propiedades
            TO anon
            USING (estado = 'activa');
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'propiedades'
          AND policyname = 'propiedades_public_read'
    ) THEN
        ALTER POLICY propiedades_public_read ON public.propiedades
            TO anon, authenticated
            USING (estado = 'activa');
    END IF;
END
$policies$;

-- Repair the legacy quality view without copying its long projection into a
-- second source of truth. CREATE OR REPLACE preserves dependencies.
DO $legacy_view$
DECLARE
    view_definition text;
BEGIN
    IF to_regclass('public.v_property_data_quality') IS NOT NULL THEN
        SELECT pg_get_viewdef('public.v_property_data_quality'::regclass, true)
        INTO view_definition;
        IF view_definition LIKE '%estado = ''activo''::text%' THEN
            view_definition := replace(
                view_definition,
                'estado = ''activo''::text',
                'estado = ''activa''::text'
            );
            EXECUTE 'CREATE OR REPLACE VIEW public.v_property_data_quality AS '
                || view_definition;
        END IF;
    END IF;
END
$legacy_view$;

CREATE TABLE IF NOT EXISTS public.property_quality_flag_definitions (
    flag        text PRIMARY KEY,
    severity    text NOT NULL CHECK (severity IN ('critical', 'high', 'medium', 'low')),
    category    text NOT NULL CHECK (
        category IN ('INTERNAL_CORRECTABLE', 'EXTERNAL_SOURCE_MISSING_DATA', 'AMBIGUOUS')
    ),
    description text NOT NULL,
    calculation text NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now()
);

INSERT INTO public.property_quality_flag_definitions(
    flag, severity, category, description, calculation, updated_at
) VALUES
('invalid_url', 'critical', 'INTERNAL_CORRECTABLE', 'URL missing or not HTTP(S).', 'url is blank or lacks an HTTP(S) host', now()),
('missing_normalized_url', 'medium', 'INTERNAL_CORRECTABLE', 'Canonical URL was not safely backfilled.', 'url exists and url_normalizada is blank', now()),
('fallback_title', 'high', 'INTERNAL_CORRECTABLE', 'Title is absent, generic or a page/file label.', 'title is blank, generic, HTML, or ends in a shell/file extension', now()),
('contaminated_description', 'high', 'INTERNAL_CORRECTABLE', 'Description contains HTML/navigation/institutional text.', 'description matches approved contamination patterns', now()),
('missing_description', 'medium', 'EXTERNAL_SOURCE_MISSING_DATA', 'No useful description is available.', 'description is blank or shorter than 30 characters', now()),
('invalid_price', 'high', 'INTERNAL_CORRECTABLE', 'Price is negative or above the accepted bound.', 'precio < 0 or precio > 1e15', now()),
('missing_price', 'medium', 'EXTERNAL_SOURCE_MISSING_DATA', 'Publication does not expose a positive price.', 'precio is null or zero', now()),
('invalid_currency', 'high', 'INTERNAL_CORRECTABLE', 'Positive price has no approved currency.', 'positive price and moneda not in ARS/USD/EUR/UYU', now()),
('missing_operation', 'high', 'INTERNAL_CORRECTABLE', 'Operation is absent or outside the database enum.', 'operation not in the approved enum', now()),
('missing_property_type', 'medium', 'INTERNAL_CORRECTABLE', 'Property type is absent.', 'tipo_propiedad is blank', now()),
('missing_location', 'medium', 'EXTERNAL_SOURCE_MISSING_DATA', 'No address, neighborhood, city or province is available.', 'all location fields are blank', now()),
('invalid_coordinates', 'high', 'AMBIGUOUS', 'Coordinates are partial or outside Argentina.', 'pair incomplete or outside the Argentina bounding box', now()),
('invalid_surface', 'high', 'INTERNAL_CORRECTABLE', 'Surface is non-positive or covered exceeds total.', 'invalid total/covered surface relationship', now()),
('invalid_feature_count', 'medium', 'AMBIGUOUS', 'Room/feature counts are negative or implausibly high.', 'approved feature bounds are exceeded', now()),
('missing_images', 'medium', 'EXTERNAL_SOURCE_MISSING_DATA', 'Publication has no image URLs.', 'imagenes is empty', now()),
('placeholder_images', 'high', 'INTERNAL_CORRECTABLE', 'Image array contains logo/icon/map/placeholder assets.', 'any image URL matches the approved placeholder patterns', now())
ON CONFLICT (flag) DO UPDATE SET
    severity = EXCLUDED.severity,
    category = EXCLUDED.category,
    description = EXCLUDED.description,
    calculation = EXCLUDED.calculation,
    updated_at = EXCLUDED.updated_at;

ALTER TABLE public.property_quality_flag_definitions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.property_quality_flag_definitions FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.property_quality_flag_definitions TO service_role;

CREATE OR REPLACE VIEW public.v_property_quality_flags_v2
WITH (security_invoker = true)
AS
WITH flagged AS (
    SELECT
        p.id AS property_id,
        p.inmobiliaria_id,
        p.estado,
        array_remove(ARRAY[
            CASE WHEN p.url IS NULL OR btrim(p.url) = ''
                       OR p.url !~* '^https?://[^/]+'
                 THEN 'invalid_url' END,
            CASE WHEN p.url IS NOT NULL AND btrim(p.url) <> ''
                       AND (p.url_normalizada IS NULL OR btrim(p.url_normalizada) = '')
                 THEN 'missing_normalized_url' END,
            CASE WHEN p.titulo IS NULL OR btrim(p.titulo) = ''
                       OR lower(btrim(p.titulo)) IN (
                           'sin título', 'sin titulo', 'propiedad', 'propiedades',
                           'inmueble', 'detalle', 'venta', 'alquiler'
                       )
                       OR p.titulo ~ '<[^>]+>'
                       OR p.titulo ~* '\.(png|jpe?g|gif|svg|webp|php|html?|aspx?)\\?$'
                 THEN 'fallback_title' END,
            CASE WHEN p.descripcion ~* '<(script|style|html|body|div|span|nav|footer)[^>]*>'
                       OR lower(coalesce(p.descripcion, '')) ~
                          'política de cookies|aceptar cookies|todos los derechos reservados|copyright [12][0-9]{3}'
                 THEN 'contaminated_description' END,
            CASE WHEN p.descripcion IS NULL OR length(btrim(p.descripcion)) < 30
                 THEN 'missing_description' END,
            CASE WHEN p.precio < 0 OR p.precio > 1000000000000000
                 THEN 'invalid_price' END,
            CASE WHEN p.precio IS NULL OR p.precio = 0
                 THEN 'missing_price' END,
            CASE WHEN p.precio > 0 AND upper(btrim(coalesce(p.moneda, '')))
                       NOT IN ('ARS', 'USD', 'EUR', 'UYU')
                 THEN 'invalid_currency' END,
            CASE WHEN p.operacion IS NULL OR btrim(p.operacion) = ''
                       OR p.operacion NOT IN (
                           'venta', 'alquiler', 'alquiler_temporario',
                           'consultar', 'venta_y_alquiler'
                       )
                 THEN 'missing_operation' END,
            CASE WHEN p.tipo_propiedad IS NULL OR btrim(p.tipo_propiedad) = ''
                 THEN 'missing_property_type' END,
            CASE WHEN coalesce(
                           nullif(btrim(p.direccion), ''),
                           nullif(btrim(p.barrio), ''),
                           nullif(btrim(p.ciudad), ''),
                           nullif(btrim(p.provincia), '')
                       ) IS NULL
                 THEN 'missing_location' END,
            CASE WHEN (p.latitud IS NULL) <> (p.longitud IS NULL)
                       OR (
                           p.latitud IS NOT NULL AND p.longitud IS NOT NULL
                           AND (
                               p.latitud NOT BETWEEN -56.5 AND -20
                               OR p.longitud NOT BETWEEN -76.5 AND -52
                           )
                       )
                 THEN 'invalid_coordinates' END,
            CASE WHEN (p.superficie_total IS NOT NULL AND p.superficie_total <= 0)
                       OR (p.superficie_cubierta IS NOT NULL AND p.superficie_cubierta <= 0)
                       OR (
                           p.superficie_total > 0
                           AND p.superficie_cubierta > p.superficie_total
                       )
                 THEN 'invalid_surface' END,
            CASE WHEN least(
                           coalesce(p.ambientes, 0), coalesce(p.dormitorios, 0),
                           coalesce(p.banos, 0), coalesce(p.toilettes, 0),
                           coalesce(p.cocheras, 0), coalesce(p.antiguedad, 0)
                       ) < 0
                       OR coalesce(p.ambientes, 0) > 30
                       OR coalesce(p.dormitorios, 0) > 30
                       OR coalesce(p.banos, 0) > 20
                       OR coalesce(p.cocheras, 0) > 50
                       OR coalesce(p.antiguedad, 0) > 300
                 THEN 'invalid_feature_count' END,
            CASE WHEN coalesce(cardinality(p.imagenes), 0) = 0
                 THEN 'missing_images' END,
            CASE WHEN EXISTS (
                           SELECT 1
                           FROM unnest(coalesce(p.imagenes, ARRAY[]::text[])) AS image
                           WHERE lower(image) ~
                               'logo|placeholder|no[-_ ]?image|sin[-_ ]?imagen|google.*map|maps\.google|favicon|sprite|arrow[-_]|icon'
                       )
                 THEN 'placeholder_images' END
        ], NULL::text) AS quality_flags
    FROM public.propiedades p
    WHERE p.estado = 'activa'
)
SELECT
    property_id,
    inmobiliaria_id,
    estado,
    quality_flags,
    cardinality(quality_flags) AS quality_flag_count
FROM flagged;

REVOKE ALL ON public.v_property_quality_flags_v2 FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.v_property_quality_flags_v2 TO service_role;

DO $validate$
DECLARE
    active_rows bigint;
    quality_rows bigint;
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'propiedades'
          AND policyname IN ('Public read active properties', 'propiedades_public_read')
          AND qual LIKE '%estado = ''activo''%'
    ) THEN
        RAISE EXCEPTION 'stale activo policy remains';
    END IF;
    SELECT count(*) INTO active_rows
    FROM public.propiedades WHERE estado = 'activa';
    SELECT count(*) INTO quality_rows
    FROM public.v_property_quality_flags_v2;
    -- A clean migration replay legitimately has zero property rows. The
    -- invariant is equality between the canonical active set and the view,
    -- not that production data must already exist.
    IF quality_rows <> active_rows THEN
        RAISE EXCEPTION 'quality flag view active-state mismatch';
    END IF;
    IF active_rows > 0
       AND to_regclass('public.v_property_data_quality') IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM public.v_property_data_quality LIMIT 1)
    THEN
        RAISE EXCEPTION 'legacy property quality view still empty';
    END IF;
    IF has_table_privilege('anon', 'public.v_property_quality_flags_v2', 'SELECT')
       OR has_table_privilege('authenticated', 'public.v_property_quality_flags_v2', 'SELECT')
    THEN
        RAISE EXCEPTION 'quality flags unexpectedly exposed to public roles';
    END IF;
END
$validate$;

COMMIT;
