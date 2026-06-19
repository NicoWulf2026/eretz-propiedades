# Roadmap actual - 2026-06-04

## Decision de foco

El scraping/autofix queda cerrado por ahora.

El foco pasa a calidad de datos desde el pipeline y frontend mobile, antes de cualquier publicacion masiva.

## Prioridad 1 - Pipeline quality root fix

Auditar causas raiz de:

- `missing_location`.
- `geocoding_pending`.
- `missing_price`.
- `missing_images`.
- Duplicados.

Determinar si el problema viene de:

1. El sitio original realmente no tiene el dato.
2. El scraper no lo extrajo.
3. El mapper no lo normalizo.
4. El validador lo descarto.
5. El geocoder lo salto correctamente.
6. El dato esta en raw/datos_extra pero no pasa a staging.
7. El dato esta en URL/titulo/descripcion pero no se usa.
8. Hay duplicados que deben agruparse, no eliminarse.

## Prioridad 2 - Mejorar pipeline

Mejorar durante scraping/normalizacion/validacion:

- Ubicacion desde breadcrumbs, URL, titulo, descripcion y JSON-LD.
- Precio/moneda desde HTML, JSON embebido y APIs.
- Imagenes reales desde galleries, JSON-LD, `og:image`, APIs y sliders.
- Normalizacion de ciudad/provincia/barrio/direccion.
- Geocoding con input mas confiable.
- Deduplicacion y agrupacion de publicaciones de la misma propiedad.
- Inmobiliaria/desarrolladora/contacto.

## Prioridad 3 - Retest controlado

Tomar muestra de:

- Propiedades con ubicacion faltante.
- Geocoding pending.
- Sin precio.
- Sin imagen.
- Posibles duplicadas.

Retestear sin publicar Supabase.

## Prioridad 4 - Medir before/after

Medir:

- Cuantas recuperan ubicacion.
- Cuantas recuperan precio.
- Cuantas recuperan imagen real.
- Cuantas suben quality_score.
- Cuantas pasan a publicables.
- Cuantas siguen igual porque el origen no trae el dato.

## Prioridad 5 - Publicacion controlada futura

Solo despues de mejorar calidad y repetir readiness:

1. Publicar 500 propiedades de maxima calidad.
2. Revisar frontend y mapa.
3. Publicar 1.000.
4. Publicar 5.000.
5. Ampliar solo si datos y UX se ven bien.

## Frontend

- Completar R6 mobile.
- Revisar visual general.
- Incorporar logo real.
- Validar performance con datos reales publicados.

## Politicas a definir

- Duplicado exacto.
- Misma propiedad por varias inmobiliarias.
- Posible duplicado dudoso.
- Propiedad sin precio.
- Ubicacion exacta, aproximada, no confiable o no publicable en mapa.
- Imagen real, sin imagen real, placeholder prohibido.

## Restricciones vigentes

- No publicar Supabase.
- No tocar `.env`.
- No borrar datos.
- No tocar `publish_queue` con commit.
- No correr `publish_to_supabase.py`.
- No correr `run_daily_pipeline.py --commit`.
- No hacer commit sin autorizacion.
- No hacer push sin autorizacion.
