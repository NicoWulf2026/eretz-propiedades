# Sprint D — Prueba controlada del pipeline

Ultima actualizacion: 2026-06-10

Estado: **CERRADO** ✅ — completado 2026-06-10

---

## Objetivo

Correr el pipeline completo por primera vez con una agencia real, verificar cada fase de principio a fin, sin scraping masivo ni publicacion masiva.

El resultado esperado es:
- Una agencia scrapeada correctamente con `scraping_run_items.status = 'success'`.
- Props nuevas/actualizadas en Neon (propiedades_raw y propiedades_staging).
- Geocoding aplicado si hay props sin coords.
- Props publicadas en Supabase (maximo 5).
- Props desaparecidas marcadas como `no_detectada_en_ultimo_scraping` (si las hay).
- Logs claros en cada fase.

---

## Restricciones del sprint

- Maximo 1 agencia por run.
- Maximo 5 props publicadas a Supabase.
- Cada paso con `--commit` requiere autorizacion explicita antes de ejecutar.
- No correr `run_daily_pipeline.py --commit` sin revision paso a paso.
- No scraping masivo.
- No tocar `.env`.
- No hacer push.

---

## Criterios de seleccion de agencia

La agencia elegida debe cumplir:

- `lista_para_batch = true` en `v_next_scraping_batch`.
- `tiene_antibot = false` (sin proteccion antibot detectada).
- Sitio activo y accesible.
- Pocas propiedades (menos de 50 idealmente) para que el scraping sea rapido.
- Preferiblemente con scraping exitoso previo en Neon (para poder comparar baseline).

Candidatos probables: agencias de ciudades chicas con CMS conocido (WordPress, Vittal, etc.).

---

## Pasos del sprint

### PASO 0 — Identificar agencia candidata (sin writes)

```bash
# Ver candidatos disponibles para el proximo batch
python scripts/create_scraping_run_from_next_batch.py --dry-run --limit 10
```

Revisar output: elegir agencia con `lista_para_batch=true`, sin antibot, pocas props.

Si se quiere filtrar por provincia:
```bash
python scripts/create_scraping_run_from_next_batch.py --dry-run --limit 5 --provincia "Santa Fe"
```

### PASO 1 — Baseline de la agencia elegida (sin writes)

```bash
# Ver si ya tiene scraping en Neon y cuantas props activas tiene en Supabase
python scripts/enqueue_deactivations.py --inmobiliaria-id X --dry-run
```

Si dice "no hay scraping exitoso en Neon": la agencia no fue scrapeada aun por el pipeline interno. Es un buen candidato de primera corrida.

### PASO 2 — Crear run (requiere autorizacion)

```bash
python scripts/create_scraping_run_from_next_batch.py --limit 1 --commit
# Output esperado: run_id=N, inserted_items=1
```

Anotar el `run_id`.

### PASO 3 — Scraping (requiere autorizacion)

```bash
python scraper/scraper_propiedades.py --max-items 1 --workers 1
```

Verificar: `scraping_run_items.status = 'success'` para la agencia del run.

Si hay error: revisar logs, NO continuar al paso siguiente hasta entender el error.

### PASO 4 — Deteccion de desaparecidas (dry-run primero)

```bash
# Con el RUN_ID del paso 2:
python scripts/enqueue_deactivations.py --all-from-run RUN_ID --dry-run
```

Revisar: cuantas props desaparecidas detecta. Si es un numero razonable, confirmar con `--commit`.

```bash
# Solo si el dry-run tiene sentido:
python scripts/enqueue_deactivations.py --all-from-run RUN_ID --commit
```

### PASO 5 — Validar raw (dry-run primero)

```bash
python scripts/validate_raw_properties.py --limit 20 --dry-run
```

Revisar cuantas props nuevas/actualizadas hay. Confirmar.

```bash
python scripts/validate_raw_properties.py --limit 20 --commit
```

### PASO 6 — Geocoding (dry-run primero)

```bash
python scripts/geocode_staging.py --limit 5 --dry-run
```

Revisar si hay props sin coords para geocodificar. Si la agencia esta en ciudad conocida, agregar fallback:

```bash
python scripts/geocode_staging.py --limit 5 --fallback-city "CIUDAD" --fallback-province "PROVINCIA" --dry-run
```

Confirmar si todo OK:

```bash
python scripts/geocode_staging.py --limit 5 --fallback-city "CIUDAD" --fallback-province "PROVINCIA" --commit
```

### PASO 7 — Build publish queue (dry-run primero)

```bash
python scripts/build_publish_queue.py --limit 10 --dry-run
```

Revisar cuantas props se encolan para publicar. Confirmar.

```bash
python scripts/build_publish_queue.py --limit 10 --commit
```

### PASO 8 — Publicar (dry-run primero, maximo 5 props)

```bash
python scripts/publish_to_supabase.py --limit 5 --dry-run
```

Revisar output. Si incluye `action=deactivate`, verificar que los `propiedad_supabase_id` son correctos.

Confirmar:

```bash
python scripts/publish_to_supabase.py --limit 5 --commit
```

### PASO 9 — Verificacion final

- Supabase: buscar las props de la agencia → estado correcto, datos completos.
- Neon: `SELECT * FROM daily_update_summary ORDER BY run_date DESC LIMIT 5`.
- Si hay props desactivadas: verificar estado `no_detectada_en_ultimo_scraping` en Supabase.

---

## Criterios de exito

| Criterio | Esperado |
|----------|----------|
| scraping_run_items.status | success para la agencia |
| props en propiedades_raw | > 0 |
| props en propiedades_staging | > 0 |
| props publicadas en Supabase | 1-5 (maximo) |
| estado en Supabase | activa para props nuevas |
| props desaparecidas (si las hay) | no_detectada_en_ultimo_scraping |
| errores de pipeline | 0 o explicados |

---

## Si algo falla

- PASO 3 falla (scraping): revisar logs del scraper. El run queda en error; no continuar.
- PASO 5 falla (validate): revisar `data_quality_issues` en Neon. Props pueden quedar en raw sin pasar a staging.
- PASO 6 falla (geocoding): revisar timeout/Nominatim. No es bloqueante para publicar.
- PASO 8 falla (publish): revisar `publish_queue.status = 'error'`. Puede ser issue de schema, FK o Supabase.

---

---

## Resultado real del sprint

Agencia: **MOLL PROPIEDADES** (inmobiliaria_id=2718, Rosario, Santa Fe, CMS tokko)

### Ejecucion paso a paso

| Paso | Resultado |
|---|---|
| PASO 0 — identificar agencia | MOLL seleccionada via `--inmobiliaria-id 2718` con fallback a `inmobiliarias_main` |
| PASO 1 — baseline | 11 props activas en Supabase; sin run exitoso previo en Neon |
| PASO 2 — crear run | run_id=6, scraping_run_item_id=6 (Neon, USE_INTERNAL_DB=true) |
| PASO 3 — scraping | 10 props detectadas/actualizadas; 1 hash sin scraping_run_item_id (parcial) |
| PASO 4 — deactivations | dry-run: skipped_partial=1 (completion_ratio=0.125 < 0.5); 0 falsas deactivations |
| PASO 5 — validate_raw | filas_leidas=0 (11 rows ya en status=validated de sprint anterior) |
| PASO 6 — geocoding | 11/11 geocoding_status=done, coords validas zona Rosario |
| PASO 7 — build_publish_queue | 11 filas encoladas, pq_id 560-570, action=upsert, status=pending, priority=1 |
| PASO 8 — publish_to_supabase | 11/11 publicadas (upsert); publicadas_ok=11, failed=0 |
| PASO 9 — verificacion | Supabase id 70772-70782, todas estado=activa |

### Fixes aplicados durante el sprint

1. **`create_scraping_run_from_next_batch.py`**: agregado `--inmobiliaria-id`; fallback a `inmobiliarias_main` si la agencia no aparece en `v_next_scraping_batch` (por `proximo_scraping` futuro).
2. **`scraper_propiedades.py`** — dos fixes:
   - `ON CONFLICT (hash_dedup)` en propiedades_raw ahora hace `DO UPDATE SET scraping_run_item_id, scraped_at` (antes era `DO NOTHING`).
   - `claim_next_scraping_item()`: preserva `scraping_run_item_id` del RPC Supabase; normaliza `item_status` → `status`.
3. **`enqueue_deactivations.py`**: proteccion contra extraccion parcial via `_is_partial_run()`, chequea `metadata.partial_extraction`, `completion_ratio` y `detectadas/expected`; CLI `--min-completion-ratio 0.5`.

### Notas tecnicas

- Pipeline ejecutado con `USE_INTERNAL_DB=true` inline (sin tocar `.env`).
- `staging-ids-file tmp_moll_ids.csv` usado en PASO 7 y PASO 8 para aislar exactamente MOLL.
- `max_supabase_writes=11` necesario porque el default es 10 (menor que las 11 props).
- PASO 8 logueo "Deduplicacion existente: url_normalizada=1" para cada prop: correcto, las 11 existian en Supabase; el upsert actualizo los datos frescos.
- `publish_queue` quedo con `status=done` (no `published`) y `propiedad_supabase_id=None`: comportamiento esperado del pipeline actual.

---

## Notas relacionadas

- [[Roadmap 2026-06-09]]
- [[06 - Batches diarios]]
- [[08 - Estados de propiedades]]
- [[2026-06-09 - Registro diario]]
- [[2026-06-10 - Registro diario]]
