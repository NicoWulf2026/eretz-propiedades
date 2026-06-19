# Supabase, Neon y base de datos

Ultima actualizacion: 2026-06-04

Esta nota documenta el estado vigente de la base de datos de ERETZ Propiedades. La arquitectura actual es dual: Supabase es la base publica/canonica y Neon es la base interna/operativa.

## Arquitectura vigente

- Supabase: base publica/canonica que alimenta el frontend.
- Neon: base interna/operativa para scraping crudo, staging, geocoding, logs y preparacion de publicacion.

Flujo esperado:

```text
scraper
-> Neon propiedades_raw
-> validate_raw_properties.py
-> Neon propiedades_staging
-> geocode_staging.py
-> build_publish_queue.py
-> publish_to_supabase.py
-> Supabase propiedades
-> Frontend
```

## Supabase

Supabase debe mantenerse liviana, publica y controlada. Es la base canonica que consulta el frontend.

Estado vigente:

- No se publico masivamente.
- No se ejecuto `publish_to_supabase.py` para carga masiva.
- No se ejecuto `run_daily_pipeline.py --commit`.
- La publicacion futura debe hacerse en tandas chicas y auditadas.

Supabase contiene o puede contener:

- Propiedades canonicas publicables.
- Inmobiliarias/desarrolladoras visibles.
- Vistas para frontend.
- Eventos de producto.
- Datos necesarios para la experiencia publica.

## Neon

Neon es la base interna para operar el pipeline sin contaminar la base publica.

Tablas internas principales:

- `propiedades_raw`: copia cruda y trazable de propiedades capturadas.
- `propiedades_staging`: propiedades validadas y normalizadas antes de publicacion.
- `data_quality_issues`: problemas de calidad detectados.
- `geocoding_results`: resultados y trazabilidad de geocoding.
- `publish_queue`: cola controlada de publicacion hacia Supabase.
- `daily_update_summary`: resumen diario operativo.
- `scraping_runs` y `scraping_run_items`: corridas y items de scraping.

## Auditoria readiness 2026-06-04

Ver detalle en [[Neon readiness 2026-06-04]].

Resumen:

- Total `propiedades_raw`: 76.106.
- Total `propiedades_staging`: 76.048.
- Unicas estimadas staging por `hash_dedup`: 76.048.
- Raw status: `validated` 76.048, `raw` 58.
- Staging status: `staging` 76.008, `queued` 30, `published` 10.
- Geocoding status: `pending` 42.905, `done` 18.497, `skipped` 12.770, `failed` 1.876.
- Publish queue actual: `pending` 30, `done` 10.

## Readiness para publicacion

- Publicables ahora con criterio estricto: 21.129.
- Publicables con warning: 8.065.
- Potencialmente encolables segun reglas actuales: 31.189.
- Retenidas/no publicables ahora: 46.854.
- Requieren geocoding: 42.351.
- Duplicadas o requieren deduplicacion: 4.406.

Decision vigente:

No publicar masivamente todavia. Primero mejorar calidad desde el pipeline.

## Problemas principales de datos

- `geocoding_pending`: 40.521.
- `missing_location`: 22.853.
- `missing_price`: 8.494.
- `duplicate`: 4.406.
- `geocoding_failed`: 1.830.
- `missing_real_image`: 1.718.
- `score_bajo`: 58.

## Politica de calidad

No corregir propiedades manualmente una por una. Si el problema nace en scraping, mapping, normalizacion, validacion o geocoding, la solucion debe incorporarse al pipeline.

Reglas:

- No inventar datos faltantes.
- No pisar datos buenos con datos peores.
- No publicar propiedades con datos criticos dudosos.
- No guardar placeholders/logos como imagenes reales.
- No geocodificar direcciones ambiguas.
- No eliminar duplicados automaticamente si pueden representar la misma propiedad publicada por distintas inmobiliarias.

## Politica de duplicados

Clasificar antes de actuar:

- Duplicado exacto: misma URL, mismo hash o misma publicacion repetida.
- Misma propiedad por varias inmobiliarias: misma direccion/coordenada, precio y caracteristicas, con distinta inmobiliaria.
- Posible duplicado dudoso: evidencia insuficiente.

Objetivo de producto: poder mostrar "tambien publicada por otras inmobiliarias" cuando corresponda, sin perder trazabilidad.

## Reglas antes de tocar bases

- No tocar `.env`.
- No borrar datos.
- No ejecutar `DROP`, `TRUNCATE` o cambios destructivos sin autorizacion.
- No cambiar esquema sin autorizacion.
- No publicar masivamente a Supabase.
- No tocar `publish_queue` con commit sin autorizacion.
- No usar `count(*)` ni `count=exact` en auditorias livianas.
- Documentar decisiones relevantes en Obsidian.

## Notas relacionadas

- [[Neon readiness 2026-06-04]]
- [[Politicas de calidad y publicacion]]
- [[Scraping autofix cierre 2026-06-04]]
- [[10 - Decisiones importantes]]
- [[11 - Pendientes]]
