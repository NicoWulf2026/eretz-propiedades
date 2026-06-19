# Errores y soluciones

Ultima actualizacion: 2026-06-04

Esta nota sirve para registrar errores importantes y soluciones aplicadas.

## Regla principal

Los errores recurrentes no deben corregirse manualmente en Supabase, Neon o archivos sueltos si pueden resolverse desde el pipeline.

Si un error aparece durante scraping, normalizacion, validacion, geocoding o publicacion, la solucion ideal es mejorar esa etapa para que el problema no vuelva a repetirse.

## Formato recomendado

```text
## Error: nombre corto

Fecha:

Area:
Scraping / Neon / Supabase / Frontend / Datos / Geocoding / Otro

Que paso:

Donde aparecio:

Causa probable:

Solucion aplicada:

Validacion:

Estado:
Resuelto / pendiente / mitigado / requiere autorizacion

Notas:
```

## Errores/familias vigentes tras autofix

El scraping/autofix esta cerrado por ahora. Los errores restantes no indican que el proceso este incompleto.

Familias restantes:

- Sitios caidos.
- Sitios bloqueados.
- Fuente mala.
- URL mala o requiere higiene de fuente.
- Fix especifico por sitio.
- Requiere autorizacion o cambios fuera del mecanismo actual.

## Problemas de calidad detectados en readiness

- `geocoding_pending`: 40.521.
- `missing_location`: 22.853.
- `missing_price`: 8.494.
- `duplicate`: 4.406.
- `geocoding_failed`: 1.830.
- `missing_real_image`: 1.718.
- `score_bajo`: 58.

Estos problemas no deben repararse manualmente propiedad por propiedad. Deben convertirse en mejoras generales del pipeline.

## Solucion esperada por familia

### Ubicacion faltante

Mejorar extraccion desde breadcrumbs, URL, titulo, descripcion, JSON-LD y metadatos cuando la senial sea clara.

### Geocoding pending/failed

Mejorar input de geocoding y saltar direcciones ambiguas o contaminadas.

### Precio faltante

Distinguir si la fuente no publica precio o si el scraper no lo extrajo desde HTML, JSON embebido o API.

### Imagen faltante

Mejorar extraccion desde galleries, `og:image`, JSON-LD, APIs y sliders. Descartar placeholders, logos, iconos, mapas y SVGs.

### Duplicados

Clasificar entre duplicado exacto, misma propiedad por varias inmobiliarias y posible duplicado dudoso.

## Reglas de seguridad

- No tocar `.env`.
- No borrar datos.
- No publicar a Supabase sin autorizacion.
- No tocar `publish_queue` con commit sin autorizacion.
- No correr `publish_to_supabase.py` sin autorizacion.
- No correr `run_daily_pipeline.py --commit` sin autorizacion.
- No cambiar esquema sin autorizacion.
- No hacer commit ni push sin autorizacion.

## Notas relacionadas

- [[Scraping autofix cierre 2026-06-04]]
- [[Neon readiness 2026-06-04]]
- [[Roadmap actual 2026-06-04]]
- [[11 - Pendientes]]
