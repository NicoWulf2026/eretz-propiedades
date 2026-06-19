# Estado actual para ChatGPT o Codex

Ultima actualizacion: 2026-06-04

Usar esta nota como contexto base al abrir un chat nuevo con ChatGPT, Codex o Claude. Para mas detalle, ver [[14 - Estado vigente 2026-06-04]], [[Scraping autofix cierre 2026-06-04]], [[Neon readiness 2026-06-04]], [[Frontend estado 2026-06-04]] y [[Roadmap actual 2026-06-04]].

## Proyecto

ERETZ Propiedades es una plataforma proptech que centraliza, organiza, normaliza y analiza informacion inmobiliaria de inmobiliarias y desarrolladoras.

La idea central no es crear otro portal de propiedades. El diferencial es transformar informacion dispersa en datos comparables, trazables y utiles para entender el mercado.

El mapa es el centro de la experiencia. ERETZ Propiedades no vende propiedades directamente: organiza datos y deriva a la publicacion original o a la inmobiliaria.

## Ruta local

```text
D:\INMO CAPITAL\Inmo-Capital-main
```

## Arquitectura actual

- Supabase: base publica/canonica que alimenta el frontend.
- Neon: base interna/operativa para scraping crudo, staging, geocoding, logs y cola de publicacion.

Flujo esperado:

```text
scraper
-> Neon propiedades_raw
-> scripts/validate_raw_properties.py
-> Neon propiedades_staging
-> scripts/geocode_staging.py
-> Neon propiedades_staging con lat/lon
-> scripts/build_publish_queue.py
-> Neon publish_queue
-> scripts/publish_to_supabase.py
-> Supabase propiedades
-> Frontend
```

## Estado scraping/autofix

Scraping/autofix esta cerrado por ahora.

Auditoria global final:

- Total inmobiliarias registradas: 7.004.
- Inmobiliarias con web/url: 5.245.
- Inmobiliarias sin web/url: 1.759.
- URLs procesadas localmente: 2.232.
- `v_next_scraping_batch` pendientes no procesadas localmente: 0.
- `latest errors` corregibles no procesados localmente: 0.
- Running/pending colgados: 0.
- Raw pendiente `captured_json`: 0.

Conclusion vigente: no quedan pendientes corregibles con el mecanismo actual. Los errores restantes no significan que el proceso este incompleto; estan clasificados como sitios caidos/bloqueados, fuente mala, higiene de URL/fuente, fix especifico por sitio o casos que requieren autorizacion.

## Ultima tanda procesada

- CSV: `global_audit_after_vnext_pending_correctable_20260603_1125.csv`.
- URLs procesadas: 453/453.
- OK: 365.
- Error: 88.
- Propiedades capturadas: 8.355.
- Importadas a Neon raw: 7.930.
- Validadas a staging: 7.930.
- Geocoding done/failed/skipped: 1.243 / 463 / 900.

## Estado Neon/readiness

- Total `propiedades_raw`: 76.106.
- Total `propiedades_staging`: 76.048.
- Unicas estimadas staging por `hash_dedup`: 76.048.
- Raw status: `validated` 76.048, `raw` 58.
- Staging status: `staging` 76.008, `queued` 30, `published` 10.
- Geocoding status: `pending` 42.905, `done` 18.497, `skipped` 12.770, `failed` 1.876.
- Publish queue: `pending` 30, `done` 10.

Readiness:

- Publicables ahora con criterio estricto: 21.129.
- Publicables con warning: 8.065.
- Potencialmente encolables segun reglas actuales: 31.189.
- Retenidas/no publicables ahora: 46.854.
- Requieren geocoding: 42.351.
- Duplicadas o requieren deduplicacion: 4.406.

Problemas principales:

- `geocoding_pending`: 40.521.
- `missing_location`: 22.853.
- `missing_price`: 8.494.
- `duplicate`: 4.406.
- `geocoding_failed`: 1.830.
- `missing_real_image`: 1.718.
- `score_bajo`: 58.

## Decision vigente sobre publicacion

No publicar masivamente todavia.

No se debe publicar el 100% de staging ni encolar todo solo porque el dry-run marque candidatas. Primero hay que mejorar calidad desde scraping, normalizacion, validacion, geocoding y deduplicacion.

La publicacion futura debe ser controlada:

1. 500 propiedades de maxima calidad.
2. 1.000 propiedades.
3. 5.000 propiedades.
4. Ampliar solo si frontend y datos se ven bien.

## Decision tecnica clave

No se haran correcciones manuales propiedad por propiedad.

Las correcciones deben incorporarse al pipeline para que cada nuevo scraping extraiga, normalice, valide, geocodifique y deduplique mejor automaticamente.

Ejemplos:

- Si ciudad/provincia aparece en URL, breadcrumb, titulo, descripcion o JSON-LD, debe recuperarse automaticamente cuando la senial sea clara.
- Si falta precio, distinguir si no existe en origen o si no fue extraido.
- Si faltan imagenes, revisar galleries, JSON-LD, `og:image`, APIs y sliders; descartar placeholders, logos, iconos, mapas y SVGs.
- Si hay duplicados, no siempre eliminarlos: puede ser la misma propiedad publicada por varias inmobiliarias.

## Frontend

Frontend esta en `frontend/`.

Rama frontend: `feature/frontend-home-map-ui`.

Avances completados:

- Loading/skeleton.
- Lazy loading de imagenes.
- Filtros client-side.
- Ordenamiento.
- Empty state.
- Performance client-side.
- Mapa limita marcadores.
- Timeout frontend Supabase con AbortController 4500ms.
- Marca corregida a `ERETZ Propiedades`.
- Navbar mejorado.
- Layout desktop con mapa a la izquierda y resultados a la derecha.
- Modos de vista: `map-large`, `balanced`, `list-large`, `map-only`, `list-only`.
- Filtros sectorizados.
- Cards premium con precio protagonista, specs, inmobiliaria/desarrolladora, link original y contacto si existe.
- Fix para no mostrar "Publicado por ERETZ Propiedades" si no hay inmobiliaria real.
- Seleccion mapa-listado.
- Markers seleccionados.
- Fullscreen mapa.
- R5 cerrado con build/lint OK.

Pendientes frontend:

- R6 mobile.
- Revision visual general.
- Incorporar logo real en `frontend/public/brand/`.
- Revisar performance cuando haya datos publicados reales.
- Revisar query Supabase cuando se publique en produccion.

## Reglas de seguridad

- No tocar `.env`.
- No borrar datos.
- No publicar a Supabase sin autorizacion.
- No tocar `publish_queue` con commit sin autorizacion.
- No correr `publish_to_supabase.py` sin autorizacion.
- No correr `run_daily_pipeline.py --commit` sin autorizacion.
- No hacer commit ni push sin autorizacion.
- No cambiar esquema de DB sin autorizacion.
- No inventar datos.
- No pisar datos buenos con datos peores.

## Proximo foco recomendado

1. Auditoria de causas raiz de `missing_location`, `geocoding_pending`, `missing_price`, `missing_images` y duplicados.
2. Mejorar pipeline para extraer ubicacion, precio, moneda, imagenes reales y fuente desde HTML, APIs, JSON-LD, breadcrumbs, titulo y URL.
3. Mejorar normalizacion de ciudad/provincia/barrio/direccion y geocoding con input confiable.
4. Retest controlado before/after.
5. Recien despues preparar publicacion controlada.

## Regla de marca

Usar siempre `ERETZ Propiedades`.

No usar `Inmocapital`, `INMOCAPITAL` ni `ERETZ Propiedades` como nombre de marca.
