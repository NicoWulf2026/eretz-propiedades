# Scraping

Ultima actualizacion: 2026-06-04

Esta nota documenta el estado vigente del scraping de ERETZ Propiedades y como debe evolucionar. Para el cierre operativo del autofix, ver [[Scraping autofix cierre 2026-06-04]].

## Rol del scraping

El scraping es el motor de datos interno. Su objetivo no es solo capturar muchas propiedades, sino capturar propiedades trazables, limpias, validadas y utiles para analisis.

El flujo vigente no debe publicar directamente en Supabase de forma masiva:

```text
scraper
-> Neon propiedades_raw
-> validacion
-> Neon propiedades_staging
-> geocoding
-> publish_queue
-> publicacion controlada a Supabase
```

## Estado final del autofix

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

Conclusion: no quedan pendientes corregibles con el mecanismo actual.

## Ultima tanda procesada

- CSV: `global_audit_after_vnext_pending_correctable_20260603_1125.csv`.
- URLs procesadas: 453/453.
- OK: 365.
- Error: 88.
- Propiedades capturadas: 8.355.
- Importadas a Neon raw: 7.930.
- Validadas a staging: 7.930.
- Geocoding done/failed/skipped: 1.243 / 463 / 900.

## Errores restantes

Los errores restantes no significan que el proceso quedo incompleto.

Clasificacion general:

- Sitios caidos o bloqueados.
- Fuente mala.
- URL mala o requiere higiene de fuente.
- Requiere fix especifico por sitio.
- Requiere autorizacion o cambios fuera del mecanismo actual.

## Decision clave

No hacer correcciones manuales propiedad por propiedad.

Las mejoras deben incorporarse al pipeline para que nuevas corridas extraigan y normalicen mejor automaticamente.

## Proxima etapa del scraping

La proxima etapa no es correr mas tandas. Es mejorar calidad desde el origen:

- Extraer ubicacion desde breadcrumbs, URL, titulo, descripcion, metadatos y JSON-LD cuando la senial sea clara.
- Extraer precio y moneda desde HTML visible, JSON embebido y APIs.
- Extraer imagenes reales desde galleries, `og:image`, JSON-LD, APIs y sliders.
- Descartar placeholders, logos, iconos, mapas y SVGs.
- Conservar siempre URL original y URL normalizada.
- Mejorar normalizacion de ciudad, provincia, barrio, direccion, tipo, operacion, precio, moneda e imagenes.
- Mejorar input de geocoding para no geocodificar direcciones ambiguas.
- Clasificar duplicados sin perder publicaciones de distintas inmobiliarias.

## Calidad obligatoria

Cada propiedad debe intentar traer:

- URL original y normalizada.
- `inmobiliaria_id`.
- Titulo util.
- Descripcion si existe.
- Tipo de propiedad.
- Operacion.
- Precio y moneda si existen.
- Direccion, barrio, ciudad y provincia si existen.
- Latitud/longitud solo si son confiables.
- Superficies, dormitorios, ambientes, banos y cocheras si existen.
- Imagenes reales.
- Estrategia usada.
- Fecha de scraping.
- Quality score e issues/warnings.

Reglas:

- No inventar datos.
- No completar con valores falsos.
- No confundir telefono/email con direccion.
- No confundir nombre de inmobiliaria con titulo de propiedad.
- No guardar precios absurdos sin issue.
- No guardar coordenadas fuera de rango sin issue.
- No publicar datos criticos dudosos.

## Estrategias existentes

- HTML estatico.
- Playwright con flag controlado.
- Visible API con flag controlado.
- Static detail con flag controlado.
- Network interception con flag controlado.
- Deteccion por familias: WordPress/AJAX, SPA/API/XHR, cards no reconocidas, timeouts, URL mala, blocked/site_down.

## Reglas de seguridad

- No correr scraping masivo sin limites.
- No usar workers altos.
- No tocar `.env`.
- No publicar a Supabase durante diagnosticos.
- No correr `run_daily_pipeline.py --commit` sin autorizacion.
- No tocar `publish_queue` con commit sin autorizacion.
- No borrar datos.
- No cambiar esquema de DB sin autorizacion.

## Notas relacionadas

- [[Scraping autofix cierre 2026-06-04]]
- [[Neon readiness 2026-06-04]]
- [[Politicas de calidad y publicacion]]
- [[Roadmap actual 2026-06-04]]
- [[10 - Decisiones importantes]]
