# 2026-06-04 - Registro diario

## Resumen del dia

Se actualizo el estado documental del proyecto despues del cierre del scraping/autofix, la auditoria global final, la auditoria readiness de propiedades, la decision de no publicar masivamente todavia y el cambio de enfoque hacia mejoras de calidad desde el pipeline.

## Cierre scraping/autofix

El scraping/autofix queda cerrado por ahora.

Datos principales:

- Total inmobiliarias registradas: 7.004.
- Inmobiliarias con web/url: 5.245.
- Inmobiliarias sin web/url: 1.759.
- URLs procesadas localmente: 2.232.
- Pendientes corregibles no procesados: 0.
- Running/pending colgados: 0.

Ultima tanda cerrada:

- CSV: `global_audit_after_vnext_pending_correctable_20260603_1125.csv`.
- URLs procesadas: 453/453.
- OK: 365.
- Error: 88.
- Propiedades capturadas: 8.355.
- Importadas raw: 7.930.
- Validadas staging: 7.930.
- Geocoding done/failed/skipped: 1.243 / 463 / 900.

## Readiness de propiedades

- Total raw: 76.106.
- Total staging: 76.048.
- Publicables ahora: 21.129.
- Publicables con warning: 8.065.
- Potencialmente encolables dry-run: 31.189.
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

## Decision sobre publicacion

No publicar masivamente a Supabase todavia.

Aunque hay 31.189 candidatas potenciales segun reglas actuales, se decide priorizar calidad y mejorar el pipeline antes de publicar.

La publicacion futura debe hacerse en tandas chicas y con validacion visual:

1. 500 propiedades de maxima calidad.
2. 1.000 propiedades.
3. 5.000 propiedades.
4. Ampliar solo si datos y frontend se ven bien.

## Decision sobre reparacion de datos

No se haran correcciones manuales propiedad por propiedad.

Los problemas deben resolverse desde:

- scraping;
- extraccion;
- normalizacion;
- validacion;
- geocoding;
- deduplicacion;
- importacion.

## Frontend

Estado:

- R5 cerrado con build/lint OK.
- Desktop avanzado.
- Mapa como protagonista.
- Cards premium.
- Seleccion mapa-listado.
- Fullscreen mapa.
- Marca corregida a `ERETZ Propiedades`.

Pendientes:

- R6 mobile.
- Revision visual general.
- Logo real en `frontend/public/brand/`.
- Revisar performance y query Supabase con datos reales publicados.

## Proximos pasos

1. Pipeline quality root fix.
2. Auditoria de causas raiz de datos faltantes.
3. Mejoras de scraping/normalizacion/validacion/geocoding.
4. Retest controlado y before/after.
5. Frontend R6 mobile.
6. Definir politicas de duplicados, precio, ubicacion e imagenes.
7. Repetir readiness audit.
8. Preparar publicacion controlada futura.

## Seguridad

- No se publico Supabase.
- No se ejecuto `publish_to_supabase.py`.
- No se ejecuto `run_daily_pipeline.py --commit`.
- No se toco `publish_queue` con commit.
- No se toco `.env`.
- No se borraron datos.
- No se hizo commit.
- No se hizo push.
