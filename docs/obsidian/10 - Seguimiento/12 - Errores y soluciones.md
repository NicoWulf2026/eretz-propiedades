# Errores y soluciones

Ultima actualizacion: 2026-07-01 (fix anti-MemoryError implementado)

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

## Errores resueltos en PR-BE-PROD-09d (2026-06-28)

Pipeline: `scripts/run_manifest.py` → `propiedades` (INSERT directo, sin raw/staging).
Todos resueltos sin ALTER TABLE ni schema change.

### Error 1 — 23502 inmobiliaria_id NOT NULL

Fecha: 2026-06-28
Area: Supabase / pipeline run_manifest
Que paso: INSERT sin inmobiliaria_id violó constraint NOT NULL.
Causa: payload no incluía el campo.
Solucion: FK preflight en run_execute — lookup de inmobiliaria_id desde inmobiliarias_main antes de scraping. Solo fuentes con FK válido son scrapeadas.
Estado: Resuelto

### Error 2 — 42P10 on_conflict ambiguo

Fecha: 2026-06-28
Area: Supabase / clients.py
Que paso: `POST /propiedades?on_conflict=url` falló. propiedades.url no tiene unique constraint.
Causa: el código original usaba on_conflict=url por analogía con otros pipelines.
Solucion: INSERT plain sin on_conflict. Dedup por existing_urls en memoria.
Estado: Resuelto

### Error 3 — 23502 columnas inexistentes

Fecha: 2026-06-28
Area: scraper/models.py
Que paso: to_payload() enviaba columnas que no existen en propiedades (barrio_normalizado, calidad_score, scraped_at, fuente, metros).
Causa: payload heredado de schema anterior.
Solucion: limpiar to_payload() — mapear metros→superficie_total, fuente→fuente_extraccion, eliminar columnas inexistentes.
Estado: Resuelto

### Error 4 — 23502 hash_dedup NOT NULL

Fecha: 2026-06-28
Area: scraper/models.py
Que paso: INSERT sin hash_dedup violó constraint NOT NULL.
Causa: to_payload() no calculaba hash_dedup.
Solucion: _compute_hash_dedup() — SHA256[:32] de f"{inmobiliaria_id}|url|{normalize_url(url)}". Agregado al final de to_payload().
Estado: Resuelto

### Error 5 — 22003 integer overflow

Fecha: 2026-06-28
Area: scraper/models.py
Que paso: Teléfonos scrapeados como "dormitorios" (ej: 3413024001) excedían el rango int de PostgreSQL (max 2^31-1).
Causa: parse_cards extraía el primer número grande del texto como dormitorios.
Solucion: _safe_int() guard — valores fuera de [-2^31, 2^31-1] → None.
Estado: Resuelto

### Error 6 — 23514 propiedades_estado_chk

Fecha: 2026-06-28
Area: scraper/models.py / propiedades schema
Que paso: INSERT sin campo estado → PostgreSQL aplicó DEFAULT "activo" → constraint propiedades_estado_chk rechazó (solo acepta "activa").
Causa: OpenAPI reporta DEFAULT "activo" pero el CHECK constraint solo permite "activa".
Solucion: `"estado": "activa"` hardcodeado en to_payload(). Ningún cambio al schema.
Validacion: 1.039 filas insertadas, todas con estado='activa'. 0 filas con estado='activo'.
Estado: Resuelto

---

## Deuda técnica resuelta — dedup global (2026-06-28)

### Problema: existing_urls cargaba solo 1.000 filas

Area: scraper/clients.py / run_manifest.py
Que paso: get_all_existing_urls() pedía limit=100_000 pero PostgREST retornaba máximo 1.000 (límite de servidor por defecto).
Con 115.559 propiedades actuales, solo 0.9% de las URLs estaban cargadas.
Causa raiz: PostgREST impone db-max-rows=1000 por defecto en Supabase.
Fix implementado (2026-06-28, PR-BE-PROD-09e-DEDUP-FIX):
- `_load_existing_urls_by_inmobiliaria(supabase_url, key, inmobiliaria_ids)` en `scripts/run_manifest.py`
- Consulta `SELECT url FROM propiedades WHERE inmobiliaria_id = eq.{id}` para cada fuente con FK (≤10.000 por query)
- Reemplaza `supabase.get_all_existing_urls()` en `run_execute()`
- Sin schema change. Sin ALTER TABLE. Backward-compatible.
Estado: RESUELTO. 9 tests agregados, 64/64 verdes.

---

## Errores en PR-BE-PROD-09e (2026-06-28 a 2026-07-01)

### Error 09e-1 — MemoryError en Playwright (rerun_02)

Fecha: 2026-06-30
Area: Playwright / Python / scraper/run.py
Que paso: El proceso W0 lanzó MemoryError durante el scraping de `mudafy_one` (fuente con listado grande) tras 20+ horas de ejecución con 2 workers. RAM superó 3GB. El proceso quedó colgado.
Causa: Chromium acumula memoria en corridas muy largas. Con 2 workers simultáneos el consumo escala más rápido.
Solucion aplicada: rerun_03 lanzado con workers=1. No reprodujo el MemoryError.
Fix estructural (2026-07-01): `CONTEXT_RECYCLE_EVERY = 50` en `scraper/run.py`. El BrowserContext se cierra y se recrea cada 50 fuentes dentro de cada worker. Libera la memoria acumulada sin reiniciar el browser process. Compatible con workers=1 y workers=2.
Estado: RESUELTO. Fix implementado. Tests 64/64 verdes.

### Error 09e-2 — Procesos Python muertos por desconexión de sesión Claude Code (intentos 1 y rerun_01)

Fecha: 2026-06-28/29
Area: Bash tool / proceso hijo
Que paso: Los primeros dos intentos lanzaron el scraper como proceso hijo del shell de Claude Code. Al desconectarse la sesión MCP, el padre muere y el hijo con él.
Solucion aplicada: rerun_02 y rerun_03 lanzados con PowerShell `Start-Process` (proceso desacoplado, no hijo). Sobrevivieron a desconexiones de sesión.
Estado: Resuelto para futuras corridas.

### Error 09e-3 — Apagado accidental del equipo (rerun_03)

Fecha: 2026-07-01
Area: Hardware / SO
Que paso: El equipo se apagó accidentalmente. El proceso Python murió a mitad del scraping (250/615 fuentes, +2.752 props).
Solucion aplicada: Los datos insertados hasta el momento quedaron limpios en DB. El dedup protege contra re-inserción.
Estado: No reproducible por software. Requiere estabilidad del equipo en la próxima corrida.

### Errores 409 hash_dedup (3 casos, no críticos)

Fecha: 2026-06-30
Area: Supabase / propiedades
Que paso: 3 fuentes (cittadini_inmobiliaria, stiefel_propiedades, santa_fe_propiedades) intentaron insertar una URL que ya existía en DB bajo un inmobiliaria_id diferente. El constraint `propiedades_hash_dedup_key` rechazó el insert con error 409.
Causa: URLs de propiedades compartidas entre múltiples inmobiliarias (cross-listing). El dedup por inmobiliaria_id no las detecta como duplicados (busca por FK, no por hash). El constraint de DB actúa como segunda línea de defensa.
Solucion: No requiere fix — el comportamiento es correcto. El run continuó normalmente.
Estado: Esperado. No crítico.

---

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
