# Scraping/autofix - cierre operativo 2026-06-04

## Estado final

El scraping/autofix queda cerrado por ahora.

La auditoria global final confirmo que no quedan pendientes corregibles con el mecanismo actual. Esto no significa que todas las inmobiliarias funcionen ni que todos los sitios sean scrapeables; significa que lo que queda ya esta clasificado como no corregible por el pipeline actual o requiere acciones fuera del mecanismo general.

## Universo auditado

- Total inmobiliarias registradas: 7.004.
- Inmobiliarias con web/url: 5.245.
- Inmobiliarias sin web/url: 1.759.
- URLs procesadas localmente: 2.232.
- `v_next_scraping_batch` pendientes no procesadas localmente: 0.
- `latest errors` corregibles no procesados localmente: 0.
- Running/pending colgados: 0.
- Raw pendiente `captured_json`: 0.

## Ultima tanda cerrada

- CSV: `global_audit_after_vnext_pending_correctable_20260603_1125.csv`.
- URLs procesadas: 453/453.
- OK: 365.
- Error: 88.
- Propiedades capturadas: 8.355.
- Importadas a Neon raw: 7.930.
- Validadas a staging: 7.930.
- Geocoding done/failed/skipped: 1.243 / 463 / 900.

## Errores restantes

Los errores restantes no indican proceso incompleto. Quedan clasificados como:

- Sitios caidos.
- Sitios bloqueados.
- Fuente mala.
- URL mala.
- Requiere higiene de fuente.
- Requiere fix especifico por sitio.
- Requiere autorizacion.
- Requiere cambio fuera del mecanismo actual.

## Mecanismo de continuidad

El proceso de autofix continuo dejo estado local reanudable:

- `reports/scraping_autofix/autofix_state.json`
- `reports/scraping_autofix/autofix_resume.md`
- reportes por batch y status en `reports/scraping_autofix/`

Si se reabre scraping en el futuro, debe partir desde esos reportes y no repetir offsets cerrados salvo error claro.

## Decision vigente

No seguir scrapeando ahora.

La prioridad ya no es capturar mas volumen sino mejorar la calidad del pipeline para que futuras corridas obtengan mejor:

- Ciudad.
- Provincia.
- Barrio.
- Direccion.
- Coordenadas.
- Precio.
- Moneda.
- Imagenes reales.
- Inmobiliaria/desarrolladora.
- Link original.
- Deduplicacion.
- Quality score.
- Issues/warnings.

## Seguridad

- No publicar Supabase.
- No correr `publish_to_supabase.py`.
- No correr `run_daily_pipeline.py --commit`.
- No tocar `publish_queue` con commit.
- No tocar `.env`.
- No borrar datos.
- No hacer commit.
- No hacer push.
