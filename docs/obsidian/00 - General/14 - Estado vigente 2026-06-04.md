# Estado vigente de ERETZ Propiedades - 2026-06-04

## Resumen ejecutivo

ERETZ Propiedades es una plataforma proptech para centralizar, organizar, normalizar y analizar informacion inmobiliaria proveniente de inmobiliarias y desarrolladoras.

La idea central no es crear otro portal de propiedades. El diferencial es ordenar informacion dispersa, mejorar su calidad, analizarla y ayudar a tomar mejores decisiones. El mapa es el centro de la experiencia.

ERETZ Propiedades no vende propiedades directamente. Organiza datos, muestra informacion clara y deriva a la publicacion original o a la inmobiliaria/desarrolladora correspondiente.

## Estado general

- Scraping/autofix: cerrado por ahora.
- Auditoria global final: no quedan pendientes corregibles con el mecanismo actual.
- Publicacion masiva a Supabase: no autorizada y no recomendada todavia.
- Proximo foco tecnico: mejorar calidad desde el pipeline, no hacer reparaciones manuales propiedad por propiedad.
- Frontend: avance fuerte en experiencia desktop/mapa/listado; queda R6 mobile y revision visual final.

## Arquitectura vigente

```text
scraper
  -> Neon propiedades_raw
  -> scripts/validate_raw_properties.py
  -> Neon propiedades_staging
  -> scripts/geocode_staging.py
  -> Neon propiedades_staging geocodificadas
  -> scripts/build_publish_queue.py
  -> Neon publish_queue
  -> scripts/publish_to_supabase.py
  -> Supabase propiedades
  -> Frontend
```

Neon es la base interna/operativa para raw, staging, geocoding, logs y cola de publicacion.

Supabase es la base publica/canonica que alimenta el frontend. No debe recibir cargas masivas sin control.

## Scraping/autofix

Auditoria global final:

- Total inmobiliarias registradas: 7.004.
- Inmobiliarias con web/url: 5.245.
- Inmobiliarias sin web/url: 1.759.
- URLs procesadas localmente: 2.232.
- `v_next_scraping_batch` pendientes no procesadas localmente: 0.
- `latest errors` corregibles no procesados localmente: 0.
- Running/pending colgados: 0.
- Raw pendiente `captured_json`: 0.

Conclusion: el proceso queda cerrado por ahora. No significa que todos los sitios funcionen; significa que no quedan pendientes corregibles con el mecanismo actual.

Errores restantes:

- Sitios caidos o bloqueados.
- Fuente mala.
- URL mala o requiere higiene de fuente.
- Fix especifico por sitio.
- Requiere autorizacion o cambio fuera del mecanismo actual.

Ultima tanda cerrada:

- CSV: `global_audit_after_vnext_pending_correctable_20260603_1125.csv`.
- URLs procesadas: 453/453.
- OK: 365.
- Error: 88.
- Propiedades capturadas: 8.355.
- Importadas a Neon raw: 7.930.
- Validadas a staging: 7.930.
- Geocoding done/failed/skipped: 1.243 / 463 / 900.

## Neon y readiness

- Total `propiedades_raw`: 76.106.
- Total `propiedades_staging`: 76.048.
- Unicas estimadas staging por `hash_dedup`: 76.048.

Raw status:

- `validated`: 76.048.
- `raw`: 58.

Staging status:

- `staging`: 76.008.
- `queued`: 30.
- `published`: 10.

Geocoding status:

- `pending`: 42.905.
- `done`: 18.497.
- `skipped`: 12.770.
- `failed`: 1.876.

Publish queue actual:

- `pending`: 30.
- `done`: 10.

## Readiness de propiedades

- Publicables ahora, criterio estricto: 21.129.
- Publicables con warning: 8.065.
- Potencialmente encolables segun reglas actuales: 31.189.
- Retenidas/no publicables ahora: 46.854.
- Requieren geocoding: 42.351.
- Duplicadas o requieren deduplicacion: 4.406.

Calidad staging:

- Score promedio: 92,35.
- Mediana: 100.
- Score 90-100: 46.877.
- Score 70-89: 24.485.
- Score 60-69: 4.387.
- Score 40-59: 299.

Cobertura staging:

- Con precio: 66.543 (87,5%).
- Sin precio: 9.505.
- Con moneda valida ARS/USD: 76.048 (100%).
- Con tipo: 76.048 (100%).
- Con operacion valida: 76.048 (100%).
- Con ciudad/provincia: 51.697 (68,0%).
- Con lat/lon: 18.497 (24,3%).
- Con imagen real: 73.389 (96,5%).
- Con URL/sourceUrl: 76.048 (100%).
- Con inmobiliaria/desarrolladora ID: 76.048 (100%).

Problemas principales:

- `geocoding_pending`: 40.521.
- `missing_location`: 22.853.
- `missing_price`: 8.494.
- `duplicate`: 4.406.
- `geocoding_failed`: 1.830.
- `missing_real_image`: 1.718.
- `score_bajo`: 58.

## Decision vigente sobre publicacion

No publicar el 100% y no publicar masivamente todavia.

Aunque el dry-run estima 31.189 candidatas, la decision vigente es mejorar antes el pipeline y publicar despues en tandas controladas:

1. 500 propiedades de maxima calidad.
2. 1.000 propiedades.
3. 5.000 propiedades.
4. Ampliar solo si los datos y el frontend se ven bien.

## Decision tecnica clave

No se haran correcciones manuales propiedad por propiedad.

Las correcciones deben incorporarse al pipeline para que cada nuevo scraping extraiga, normalice, valide, geocodifique y deduplique mejor automaticamente.

Ejemplos:

- Si falta ciudad/provincia pero aparece en URL, breadcrumb, titulo, descripcion o JSON-LD, debe recuperarse automaticamente.
- Si falta precio, hay que distinguir si no existe en origen o si no fue extraido.
- Si faltan imagenes, hay que revisar galleries, JSON-LD, `og:image`, APIs y sliders, descartando placeholders/logos.
- Si hay duplicados, no siempre se eliminan: puede ser la misma propiedad publicada por varias inmobiliarias.
- ERETZ Propiedades deberia poder mostrar "tambien publicada por otras inmobiliarias" cuando corresponda.

## Frontend

Repo frontend dentro de `frontend/`.

Rama frontend: `feature/frontend-home-map-ui`.

Avances cerrados:

- Loading/skeleton.
- Lazy loading de imagenes.
- Filtros client-side.
- Ordenamiento.
- Empty state.
- Performance client-side.
- Mapa limita marcadores.
- Timeout frontend Supabase con `AbortController` 4500ms.
- Marca corregida a `ERETZ Propiedades`.
- Navbar mejorado.
- Layout desktop con mapa protagonista a la izquierda y resultados a la derecha.
- Modos `map-large`, `balanced`, `list-large`, `map-only`, `list-only`.
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
- Revisar performance con datos publicados reales.
- Revisar query Supabase cuando se publique en produccion.

## Regla de marca

Usar siempre `ERETZ Propiedades`.

No usar:

- `Inmocapital`.
- `INMOCAPITAL`.
- `ERETZ Propiedades`.

## Proximos pasos

1. Pipeline quality root fix: auditar causas raiz de `missing_location`, `geocoding_pending`, `missing_price`, `missing_images` y duplicados.
2. Mejorar scraping/normalizacion/validacion/geocoding para corregir datos al scrapear.
3. Retest con muestra controlada y medir before/after.
4. Completar frontend R6 mobile.
5. Definir politicas de duplicados, sin precio, ubicacion e imagenes.
6. Repetir readiness audit.
7. Preparar publicacion controlada futura.

## Seguridad vigente

- No tocar `.env`.
- No borrar datos.
- No publicar Supabase.
- No tocar `publish_queue` con commit.
- No correr `publish_to_supabase.py`.
- No correr `run_daily_pipeline.py --commit`.
- No hacer commit sin autorizacion.
- No hacer push sin autorizacion.
