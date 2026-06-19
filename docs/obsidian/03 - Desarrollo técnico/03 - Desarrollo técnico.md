# Desarrollo tecnico

Ultima actualizacion: 2026-06-04

Esta nota resume la arquitectura tecnica vigente de ERETZ Propiedades. Para el detalle del frontend actual, ver [[Frontend estado 2026-06-04]].

## Ruta local

```text
D:\INMO CAPITAL\Inmo-Capital-main
```

## Stack

Frontend:

- Next.js.
- Tailwind.
- Leaflet.
- Componentes propios.
- Datos desde Supabase.

Backend/datos:

- Python.
- Scraper propio.
- Playwright cuando corresponde.
- Supabase como base publica/canonica.
- Neon como base interna/operativa.
- Scripts de validacion, geocoding, queue y publicacion controlada.

Documentacion y seguimiento:

- Obsidian.
- Reportes locales en `reports/scraping_autofix/`.
- Git/GitHub para codigo.

## Arquitectura de datos

La arquitectura actual es dual:

- Supabase: datos publicos/canonicos para frontend.
- Neon: scraping crudo, staging, geocoding, logs y preparacion de publicacion.

La publicacion a Supabase no debe ser masiva todavia. Debe ocurrir solo despues de mejorar calidad y en tandas controladas.

## Estado scraping/autofix

Scraping/autofix cerrado por ahora.

No quedan pendientes corregibles con el mecanismo actual. Los errores restantes estan clasificados como no corregibles automaticamente, requieren higiene de fuente, fix especifico o autorizacion.

## Estado frontend

Rama frontend: `feature/frontend-home-map-ui`.

R5 cerrado con build/lint OK.

Avances:

- Loading/skeleton.
- Lazy loading de imagenes.
- Filtros client-side.
- Ordenamiento.
- Empty state.
- Performance client-side.
- Mapa limita marcadores.
- Timeout frontend Supabase con AbortController 4500ms.
- Marca `ERETZ Propiedades`.
- Navbar mejorado.
- Layout desktop con mapa protagonista.
- Modos de vista: `map-large`, `balanced`, `list-large`, `map-only`, `list-only`.
- Filtros sectorizados.
- Cards premium.
- Link original y contacto si existen.
- Seleccion mapa-listado, markers seleccionados y fullscreen mapa.

Pendientes:

- R6 mobile.
- Revision visual general.
- Logo real en `frontend/public/brand/`.
- Performance con datos reales publicados.
- Query Supabase en produccion.

## Prioridad tecnica vigente

1. Auditar causas raiz de datos faltantes o dudosos.
2. Mejorar scraping, normalizacion, validacion, geocoding y deduplicacion desde el pipeline.
3. Retest controlado before/after.
4. Preparar publicacion controlada solo con propiedades de maxima calidad.
5. Completar frontend R6 mobile y revision visual.

## Reglas tecnicas

- No tocar `.env`.
- No borrar datos.
- No publicar a Supabase sin autorizacion.
- No tocar `publish_queue` con commit sin autorizacion.
- No correr `publish_to_supabase.py` sin autorizacion.
- No correr `run_daily_pipeline.py --commit` sin autorizacion.
- No hacer commit ni push sin autorizacion.
- No cambiar esquema sin autorizacion.
- No inventar datos.
- No pisar datos buenos con datos peores.

## Como pedir ayuda tecnica

Usar [[13 - Estado actual para ChatGPT o Codex]] y agregar:

- Objetivo puntual.
- Restricciones.
- Archivos permitidos.
- Archivos prohibidos.
- Comandos de validacion esperados.
- Si se permite o no tocar Supabase, Neon, frontend, scraper o `.env`.

## Notas relacionadas

- [[Frontend estado 2026-06-04]]
- [[04 - Supabase y base de datos]]
- [[05 - Scraping]]
- [[Roadmap actual 2026-06-04]]
- [[10 - Decisiones importantes]]
