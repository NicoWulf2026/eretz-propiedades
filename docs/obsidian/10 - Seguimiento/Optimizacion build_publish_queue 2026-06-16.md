# Optimización `build_publish_queue` — batching pre-cutover (2026-06-16)

Optimización de performance del encolado contra Supabase `internal_scraping`,
detectada tras la migración. **Sin commit, sin publicación, sin push, sin tocar
`public.propiedades`, sin cambiar reglas de publicación.**

Ver también: [[Migracion Neon a Supabase internal_scraping 2026-06-16]]

---

## 1. Causa exacta de la lentitud

`build_publish_queue.py` procesaba **fila por fila** con un `SAVEPOINT` por cada
una. Por fila encolada ejecutaba 4 round-trips:

```
SAVEPOINT  →  INSERT publish_queue  →  UPDATE propiedades_staging  →  RELEASE
```

Con latencia Argentina → Supabase (~150 ms/round-trip), el costo crece lineal
con N. No era el índice ni el schema: era **exceso de round-trips de red**.

## 2. Cantidad de queries antes / después

| | Fórmula | N=50 | N=500 |
|---|---|---:|---:|
| **Antes** | `2 + ~4·N` | ~202 | ~2002 |
| **Después** | `2 SELECT + 1 INSERT bulk + 1 UPDATE bulk + 1 finalize` | ~5 | ~5 |

Independiente de N.

## 3. Archivos modificados

- **`scripts/build_publish_queue.py`** (único archivo con cambios de lógica de ejecución).
- `scripts/publish_to_supabase.py`: **auditado, no modificado** (ver punto 4).

## 4. Estrategia elegida — Opción A (bulk en una transacción)

Se preservó **intacta** la lógica de decisión (`queue_skip_reason`,
`compute_priority`, motivos de skip, prioridades). Solo cambió la **ejecución**:

1. `fetch_staging_rows` — 1 query (igual que antes, usa
   `idx_propiedades_staging_status_score_id`).
2. `fetch_existing_queue_staging_ids` — 1 query.
3. **Clasificación en memoria** (`classify_row`): 0 round-trips. Se eliminaron
   los `SAVEPOINT`/`RELEASE` por fila.
4. **`bulk_insert_publish_queue`**: un solo `INSERT ... VALUES (...),(...),...`.
5. **`bulk_mark_staging_queued`**: un solo `UPDATE ... WHERE id = ANY(%s)`
   (cubre las recién insertadas + las que ya estaban en cola).
6. `commit`/`rollback` único.

Se añadió **timing por bloque** (`fetch_staging`, `lookup_queue`,
`validate_memory`, `bulk_write`, `finalize`) para diagnóstico continuo.

> **`publish_to_supabase.py` no se optimizó a propósito.** Su fetch de staging ya
> es bulk (`WHERE id = ANY(%s)`). Su cuello de botella es **intencional**: escribe
> a `public.propiedades` por REST API **una propiedad a la vez** con `--sleep`
> entre escrituras y tope `--max-supabase-writes` (rate-limit + reintentos
> granulares). Hacer bulk ahí cambiaría las reglas de publicación — prohibido.

## 5. Tiempos comparativos (interno, sin arranque de Python)

| Escenario | Antes | Después |
|-----------|------:|--------:|
| Supabase `internal_scraping` — limit 50 | ~48 s | **1.5 s** |
| Supabase `internal_scraping` — limit 500 | >300 s (timeout) | **4.8 s** |
| Neon `public` (compat) — limit 50 | — | **1.3 s** |

Desglose limit 500 (Supabase): fetch 0.81s · lookup 0.77s · validación 0.01s ·
bulk_write 2.98s · finalize 0.18s.

Resultados de negocio idénticos a la versión anterior: encoladas=500
(priority 1=296, 2=204), sin filas omitidas.

## 6. Rollback sin residuos

Tras los dry-runs (todos `accion_final=rollback`):
- `internal_scraping.publish_queue`: `done`=11,687 (sin filas nuevas).
- `internal_scraping.propiedades_staging`: `staging`=68,367 / `published`=11,687 (sin cambios).
- `public.propiedades`: 94,834 (intacto).

## 7. Compatibilidad

- `INTERNAL_DB_SCHEMA=public` (default) contra Neon → exit 0, mismos resultados.
- `INTERNAL_DB_SCHEMA=internal_scraping` contra Supabase → exit 0.
- CLI sin cambios; `run_daily_pipeline.py` lo sigue invocando igual.
- `py_compile` OK en `build_publish_queue.py`, `publish_to_supabase.py`,
  `run_daily_pipeline.py`, `scraper/scraper_propiedades.py`.

## 8. ¿Listo para cutover controlado?

**El encolado sí** está listo en performance (limit 500 en ~5s). Antes del
cutover real conviene:
- Validar el resto del ciclo (`validate_raw`, `geocode_staging`) contra Supabase
  con lotes chicos para medir su latencia.
- `publish_to_supabase` seguirá siendo lento **por diseño** (rate-limit): dimensionar
  `--limit`/`--sleep` según cuántas props publicar por tanda.

## Recomendación del próximo paso

Correr un **dry-run del ciclo completo** (`run_daily_pipeline --dry-run` ya pasa)
y luego una **tanda controlada chica con `--commit`** contra `internal_scraping`
(p. ej. limit 20–50, sin publicar a Supabase) para validar el flujo real
escribiendo en la cola, antes de habilitar publicación. Esto requiere
autorización explícita (implica commit en `internal_scraping`).
