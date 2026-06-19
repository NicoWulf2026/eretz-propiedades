# Registro diario — 2026-06-10

## Sprint D — Cierre oficial ✅

Sprint D completado. Objetivo: prueba controlada del pipeline completo con 1 agencia real.

---

### Agencia utilizada

- **MOLL PROPIEDADES** — inmobiliaria_id=2718
- Ciudad: Rosario, Santa Fe
- CMS: tokko
- Props en sitio: ~80 esperadas; extraccion parcial en esta corrida (10 detectadas)

---

### Ejecucion completa paso a paso

| Paso | Comando clave | Resultado |
|---|---|---|
| PASO 2 — crear run | `create_scraping_run_from_next_batch.py --commit --inmobiliaria-id 2718` | run_id=6, item_id=6 (Neon) |
| PASO 3 — scraping | `scraper_propiedades.py --max-items 1 --workers 1` (USE_INTERNAL_DB=true) | 10 props actualizadas en propiedades_raw |
| PASO 4 — deactivations | `enqueue_deactivations.py --all-from-run 6 --dry-run` | skipped_partial=1; 0 falsas deactivations |
| PASO 5 — validate_raw | `validate_raw_properties.py --dry-run` | filas_leidas=0 (ya validadas desde sprint anterior) |
| PASO 6 — geocoding | diagnostico manual | 11/11 geocoding_status=done desde sprint anterior |
| PASO 7 — build_publish_queue | `build_publish_queue.py --ids-file tmp_moll_ids.csv --commit` | 11 filas encoladas pq_id 560-570 |
| PASO 8 — publish_to_supabase | `publish_to_supabase.py --staging-ids-file tmp_moll_ids.csv --limit 11 --max-supabase-writes 11 --commit` | 11/11 publicadas, failed=0 |
| PASO 9 — verificacion | query Supabase | id 70772-70782, todas estado=activa |

---

### Fixes aplicados durante Sprint D

#### 1. `create_scraping_run_from_next_batch.py`

- Nuevo argumento `--inmobiliaria-id`.
- Fallback a `inmobiliarias_main` cuando la agencia no aparece en `v_next_scraping_batch` (por `proximo_scraping` futuro o sin `lista_para_batch=true`).
- La funcion `fetch_single_candidate()` intenta la vista primero y, si no encuentra, busca directamente en la tabla base.

#### 2. `scraper/scraper_propiedades.py` — dos fixes

Fix 1 — `ON CONFLICT (hash_dedup)` en propiedades_raw:
```python
# Antes:
" ON CONFLICT (hash_dedup) DO NOTHING"
# Despues:
" ON CONFLICT (hash_dedup) DO UPDATE SET"
" scraping_run_item_id = EXCLUDED.scraping_run_item_id,"
" scraped_at = NOW()"
```
Sin este fix, las propiedades ya existentes no actualizaban su `scraping_run_item_id` y el pipeline perdia el contexto del run actual.

Fix 2 — `claim_next_scraping_item()`:
```python
# Antes:
data["scraping_run_item_id"] = data.get("id")
# Despues:
data["scraping_run_item_id"] = data.get("id") or data.get("scraping_run_item_id")
data["status"] = data.get("status") or data.get("item_status")
```
La RPC de Supabase devuelve `scraping_run_item_id` (no `id`) y `item_status` (no `status`). El codigo anterior pisaba el valor correcto con None.

#### 3. `scripts/enqueue_deactivations.py`

Agregada funcion `_is_partial_run()` que verifica tres condiciones:
1. `metadata.partial_extraction == True`
2. `metadata.completion_ratio < min_ratio`
3. `detectadas / expected_count < min_ratio` (fallback)

CLI: `--min-completion-ratio 0.5` (default).
Contador nuevo: `skipped_partial`.

Sin esta proteccion, una extraccion parcial (MOLL: ratio=0.125) generaria falsas deactivations masivas.

---

### Notas tecnicas

- **USE_INTERNAL_DB**: `.env` tiene `USE_INTERNAL_DB=false`. Todos los comandos del pipeline se corrieron con `$env:USE_INTERNAL_DB='true'` inline sin modificar `.env`.
- **tmp_moll_ids.csv**: archivo temporal generado para filtrar exactamente las 11 props de MOLL en PASO 7 y PASO 8. No es parte del repo; se puede regenerar con los staging_id 31844-31854.
- **max_supabase_writes**: el default es 10. Con 11 props se necesita `--max-supabase-writes 11` para no cortar la ultima.
- **Deduplicacion existente**: el log de PASO 8 mostro `url_normalizada=1` para cada prop. Correcto: las 11 existian en Supabase con la misma URL; el upsert actualizo los campos con datos frescos del run.
- **publish_queue status**: quedo `status=done` (no `published`) y `propiedad_supabase_id=None`. Comportamiento esperado del pipeline actual; el ID de Supabase no se registra de vuelta en Neon.

---

### Sprint E — Definido

Siguiente sprint: **Frontend labels y compatibilidad visual**.

Objetivos:
- Mostrar estado `activa` / `desconocida` / `no_detectada_en_ultimo_scraping` con label visible.
- Mostrar operacion `consultar` como "Consultar" y `venta_y_alquiler` como "Venta y alquiler".
- Mostrar "Consultar precio" si precio es null o 0.
- Mostrar placeholder si no hay imagenes reales.
- No ocultar propiedades incompletas del listado publico.

---

### Pendientes no bloqueantes (heredados)

- **Scheduler/cron**: template para corrida diaria. Deployment-specific. No urgente.
- **Geocodificar Angelina (General Alvear)**: `geocode_staging.py --fallback-city "General Alvear" --fallback-province "Mendoza"`. No urgente.
- **Retry outliers geocoding**: props 81820 (Pagliaro) y 81777 (Angelina). No urgente.
- **enqueue_deactivations --commit para MOLL**: no ejecutado (run parcial; correcto no encolar).

---

---

## Sprint E — Cierre oficial ✅

Sprint E completado. Objetivo: ajustar el frontend para mostrar todos los estados, operaciones e indicadores de datos incompletos sin cambiar el diseño general.

### Problema critico resuelto

`property-supabase-service.ts` filtraba `.in("estado", ["activo","activa"])` en ambas queries, lo que excluia todas las propiedades con estado nuevo (incluidas las 11 de MOLL). Eliminado el filtro — Decision 13 aplicada en frontend.

### Archivos modificados

| Archivo | Cambio |
|---|---|
| `types/property.ts` | `PropertyOperation` += consultar, venta_y_alquiler; `PropertyStatus` += desconocida, no_detectada_en_ultimo_scraping |
| `property-mapper.ts` | normalizeOperation() y normalizeStatus() reconocen valores nuevos |
| `property-supabase-service.ts` | Eliminado filtro por estado — todas las props se muestran |
| `analysis-currency.ts` | "Consultar" → "Consultar precio" |
| `PropertyCard.tsx` | OPERATION_LABEL/CLS para ops nuevas; STATUS_LABEL/CLS con badges de estado |
| `FilterBar.tsx` | consultar y venta_y_alquiler en chips de filtro |
| `PropertyLeafletMap.tsx` | consultar y venta_y_alquiler en labels del mapa |

### Validacion

- ESLint: 0 errores, 0 warnings.
- TypeScript (`tsc --noEmit`): 0 errores.
- 21/21 patrones verificados en los archivos modificados.

### Sprint F — Definido

Proximo sprint: **QA visual y UX frontend**.

Objetivos: `npm run dev`, revision en browser, opacidad para props no-activas, indicador sin mapa, filtro por estado, mejora marcador venta_y_alquiler, revision mobile.

---

---

## Sprint F — Cierre oficial ⚡ CERRADO PARCIAL

Sprint F completado en su parte critica: el frontend ahora carga datos reales desde Supabase.

### Problemas criticos resueltos

#### 1. RLS sin policy SELECT para anon

`public.propiedades` tenia RLS habilitado sin policy SELECT para el rol `anon`.

El frontend usa `NEXT_PUBLIC_SUPABASE_ANON_KEY`. Sin policy, Supabase devolvía 0 filas → fallback a mock ("Datos demo", 4 propiedades).

Fix: migration `supabase_sprint_f_rls_public_read.sql` ejecutada manualmente en Supabase SQL Editor.

```sql
CREATE POLICY "propiedades_public_read"
  ON public.propiedades FOR SELECT TO anon USING (true);
GRANT SELECT ON public.propiedades TO anon;
```

Resultado: 91.326 propiedades accesibles.

#### 2. AbortController disparaba por arquitectura 3-queries

Incluso con RLS corregido, el frontend seguia cayendo a mock. Causa: la arquitectura de 2 fases generaba 3 queries en serie/paralelo desde la unidad de red D:, acumulando 19–38s de latencia → el `AbortController` de 25s disparaba → fallback.

Fix: reemplazar las 3 queries por 1 sola query directa:

```typescript
// property-supabase-service.ts
await client
  .from("propiedades")
  .select(FRONTEND_PROPERTY_COLUMNS)
  .order("id", { ascending: false })
  .limit(50)
  .abortSignal(signal);
```

Latencia resultante: 7–13s fresh load. Sin AbortErrors.

#### 3. v_propiedades_frontend_mapa — descartada para carga principal

La view tiene filtro `estado='activo'` incorrecto (valor pre-Sprint A) y JOINs lentos que generan timeout 57014.
Decision 31: el frontend usa `propiedades` directamente. La view queda para correccion futura.

### Resultado final

| Indicador | Estado |
|---|---|
| "Datos reales" en frontend | ✅ |
| 50 propiedades reales | ✅ |
| 50/50 con ubicacion | ✅ |
| Mapa con pins reales | ✅ (screenshot: USD 610k, ARS 280k, USD 200k) |
| Tarjetas reales | ✅ (Pagliaro, Tandil, USD 55k) |
| TypeScript + ESLint | ✅ 0 errores |
| Sin AbortErrors | ✅ |
| total_propiedades en Supabase | 91.326 |

### Archivos modificados en Sprint F

- `frontend/src/lib/property-supabase-service.ts` — query unica directa
- `frontend/src/lib/property-service.ts` — limit 50
- `frontend/src/types/property.ts` — campos directos + opcionales
- `frontend/src/lib/property-mapper.ts` — fallbacks ciudad/provincia y hasRealImage
- `migrations/supabase_sprint_f_rls_public_read.sql` — migration RLS (ejecutada manualmente)

### Pendiente (Chrome MCP desconectado)

- QA interactivo: filtros, scroll, busqueda, mobile.
- Verificar MOLL con buscador "Rosario".
- Mejoras UX: opacidad no-activas, indicador sin mapa, filtro por estado.

### Sprint G — Definido

Proximo sprint: **QA interactivo + UX frontend**.

Objetivos principales:
- Reconectar Chrome MCP.
- QA interactivo completo.
- Mejoras UX pendientes de Sprint F.

---

## Notas relacionadas

- [[Roadmap 2026-06-09]]
- [[Sprint D - Prueba controlada pipeline]]
- [[Sprint E - Frontend labels]]
- [[Sprint F - QA visual y UX frontend]]
- [[11 - Pendientes]]
- [[10 - Decisiones importantes]]
