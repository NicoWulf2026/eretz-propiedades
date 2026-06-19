# Neon readiness de propiedades - 2026-06-04

## Resumen

Auditoria interna de propiedades en Neon antes de publicar.

No se publico nada a Supabase. No se escribio `publish_queue` con commit. La auditoria confirma que hay volumen util, pero tambien muchos datos retenidos por calidad, geocoding o deduplicacion.

## Totales internos

- Total `propiedades_raw`: 76.106.
- Total `propiedades_staging`: 76.048.
- Unicas estimadas staging por `hash_dedup`: 76.048.

## Estados raw

- `validated`: 76.048.
- `raw`: 58.

## Estados staging

- `staging`: 76.008.
- `queued`: 30.
- `published`: 10.

## Geocoding status

- `pending`: 42.905.
- `done`: 18.497.
- `skipped`: 12.770.
- `failed`: 1.876.

## Publish queue actual

- `pending`: 30.
- `done`: 10.

## Readiness

- Publicables ahora, criterio estricto: 21.129.
- Publicables con warning: 8.065.
- Potencialmente encolables segun reglas actuales: 31.189.
- Retenidas/no publicables ahora: 46.854.
- Requieren geocoding: 42.351.
- Duplicadas o requieren deduplicacion: 4.406.

## Calidad staging

- Score promedio: 92,35.
- Mediana: 100.
- Score 90-100: 46.877.
- Score 70-89: 24.485.
- Score 60-69: 4.387.
- Score 40-59: 299.

## Cobertura staging

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

## Problemas principales

- `geocoding_pending`: 40.521.
- `missing_location`: 22.853.
- `missing_price`: 8.494.
- `duplicate`: 4.406.
- `geocoding_failed`: 1.830.
- `missing_real_image`: 1.718.
- `score_bajo`: 58.

## Decision

No publicar masivamente todavia.

Primero se debe mejorar el pipeline para resolver causas raiz de datos faltantes y medir before/after. La publicacion futura debe ser controlada por tandas chicas.

## Politicas pendientes

- Duplicado exacto.
- Misma propiedad publicada por varias inmobiliarias.
- Posible duplicado dudoso.
- Propiedades sin precio.
- Ubicacion exacta, aproximada o no confiable.
- Imagen real vs placeholder prohibido.
