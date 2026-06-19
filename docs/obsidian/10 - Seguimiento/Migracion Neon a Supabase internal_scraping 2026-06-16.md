# Migración Neon → Supabase `internal_scraping` (2026-06-16)

Migración del pipeline interno de scraping desde Neon hacia Supabase Pro, bajo el
schema `internal_scraping`. **El frontend y `public.propiedades` no se tocaron.**
**Neon permanece intacto como respaldo.** No se ejecutó publicación, ni Batch 100,
ni limpieza/retención, ni push.

Ver también: [[Auditoria Supabase 2026-06-16]] · [[Phase2 Supabase fixes 2026-06-16]]

---

## Resumen ejecutivo

| Paso | Acción | Estado |
|------|--------|--------|
| 1 | Auditoría read-only de Neon | ✅ |
| 2 | Backup lógico de Neon a disco | ✅ (321 MB, 9 archivos) |
| 3 | DDL `internal_scraping` (9 tablas, 7 funciones, 40 índices) | ✅ aplicado |
| 4 | Migración de datos (COPY binario) | ✅ 252,433 filas |
| 5 | Verificación cruzada + sync de sequences | ✅ todo OK |
| 6 | Parametrización de schema en el código (8 archivos) | ✅ |
| 7 | Dry-runs contra Supabase | ✅ exit 0 ambos |
| 8 | Informe | ✅ este documento |

**Resultado:** el pipeline puede operar contra Supabase/`internal_scraping`
seteando `INTERNAL_DB_SCHEMA=internal_scraping` + `INTERNAL_DB_URL=<supabase>`.
El comportamiento por defecto (Neon, schema `public`) **no cambió**.

---

## Paso 1 — Auditoría Neon (PostgreSQL 17.10)

| Tabla | Filas | Tamaño total |
|-------|------:|-------------:|
| propiedades_raw | 80,054 | 189 MB |
| propiedades_staging | 80,054 | 172 MB |
| data_quality_issues | 72,012 | 22 MB |
| geocoding_results | 8,540 | 16 MB |
| publish_queue | 11,687 | 3.1 MB |
| scraping_run_items | 73 | 1.5 MB |
| scraping_runs | 11 | 64 kB |
| daily_update_summary | 2 | 48 kB |
| inmobiliarias_staging | 0 | 40 kB |

Distribuciones clave (Neon):
- staging.status: `staging`=68,367, `published`=11,687
- staging.geocoding_status: `pending`=42,650, `done`=20,400, `skipped`=14,665, `failed`=2,339
- publish_queue.status: `done`=11,687
- geocoding_results.status: `success`=6,201, `error`=2,339

FKs (respetadas en el orden de migración):
`scraping_run_items → scraping_runs (CASCADE)`,
`propiedades_raw → scraping_run_items (SET NULL)`,
`propiedades_staging → propiedades_raw (SET NULL)`,
`data_quality_issues → propiedades_raw (SET NULL)`,
`publish_queue → propiedades_staging (SET NULL)`.

---

## Paso 2 — Backup

`pg_dump` no está disponible en el entorno. Se hizo backup lógico vía
`COPY ... TO STDOUT (FORMAT BINARY)` por tabla:

```
backups/neon_internal_before_supabase_internal_scraping_migration/
  scraping_runs.bin, scraping_run_items.bin, propiedades_raw.bin,
  propiedades_staging.bin, data_quality_issues.bin, publish_queue.bin,
  geocoding_results.bin, daily_update_summary.bin, inmobiliarias_staging.bin
  MANIFEST.json
```

Total ~321 MB. **Redundante con Neon vivo** (Neon nunca se modificó; toda la
migración leyó de Neon en modo solo-lectura).

---

## Paso 3 — DDL en Supabase

Archivo: `migrations/phase3_internal_scraping_schema.sql`

- 9 tablas creadas en `internal_scraping` (estructura idéntica a Neon).
- 40 índices, incluido el crítico
  `idx_propiedades_staging_status_score_id (status, validation_score DESC, id ASC)`
  — sin él, `build_publish_queue` hace timeout sobre 78k+ filas.
- 7 funciones RPC (`claim_next_scraping_item`, `start_scraping_item`,
  `retry_scraping_item`, `finish_scraping_item_success`,
  `finish_scraping_item_error`, `close_scraping_run_if_finished`,
  `cleanup_old_data`) adaptadas con nombres calificados `internal_scraping.*`,
  `SECURITY DEFINER` y `search_path` fijo.
- `GRANT` a `service_role` en tablas, sequences y funciones.

---

## Paso 4 — Migración de datos

Método: `COPY ... TO STDOUT (FORMAT BINARY)` (Neon) → `COPY ... FROM STDIN (FORMAT BINARY)`
(Supabase), streaming sin cargar en memoria, en orden FK.

> Nota: Supabase impone `statement_timeout=2min`. Para las tablas grandes se
> usó `SET statement_timeout = 0` en la sesión de carga.

| Tabla | Filas migradas | Tiempo |
|-------|---------------:|-------:|
| scraping_runs | 11 | 0.4s |
| scraping_run_items | 73 | 15s |
| propiedades_raw | 80,054 | 607s |
| propiedades_staging | 80,054 | 309s |
| data_quality_issues | 72,012 | 45s |
| publish_queue | 11,687 | 9s |
| geocoding_results | 8,540 | 82s |
| daily_update_summary | 2 | 1s |
| **Total** | **252,433** | |

---

## Paso 5 — Verificación cruzada

Conteo y `MAX(id)` coinciden 1:1 en las 9 tablas (Neon vs Supabase). Todas las
distribuciones de status (staging, geocoding, publish_queue, geocoding_results)
coinciden exactamente.

**Sequences sincronizadas** (`setval` con el `last_value`/`is_called` de Neon):

| Sequence | last_value | próximo id | max(id) | OK |
|----------|-----------:|-----------:|--------:|:--:|
| scraping_runs_id_seq | 11 | 12 | 11 | ✅ |
| scraping_run_items_id_seq | 73 | 74 | 73 | ✅ |
| propiedades_raw_id_seq | 94,630 | 94,631 | 94,426 | ✅ |
| propiedades_staging_id_seq | 85,412 | 85,413 | 85,412 | ✅ |
| data_quality_issues_id_seq | 160,658 | 160,659 | 160,658 | ✅ |
| publish_queue_id_seq | 35,026 | 35,027 | 35,026 | ✅ |
| geocoding_results_id_seq | 8,755 | 8,756 | 8,755 | ✅ |
| daily_update_summary_id_seq | 4 | 5 | 2 | ✅ |
| inmobiliarias_staging_id_seq | 1 | 1 | 0 | ✅ |

Sin riesgo de colisión de PK en futuros inserts.

---

## Paso 6 — Parametrización del schema en el código

Mecanismo **aditivo y reversible**: nueva variable de entorno
`INTERNAL_DB_SCHEMA` con default `"public"`. El comportamiento histórico contra
Neon **no cambia** si la variable no se setea.

- `scraper/scraper_propiedades.py` (`InternalDBClient`): las queries calificadas
  pasaron de `public.<tabla>` a `<schema>.<tabla>` (schema validado en `__init__`).
- Los 7 scripts del pipeline diario: las queries usan nombres **sin calificar** y
  la conexión ejecuta `SET search_path TO <schema>` al abrirse. El schema se
  valida como identificador simple antes de interpolarse.

Archivos modificados (8):
`scraper/scraper_propiedades.py`, `scripts/build_publish_queue.py`,
`scripts/run_daily_pipeline.py`, `scripts/validate_raw_properties.py`,
`scripts/geocode_staging.py`, `scripts/publish_to_supabase.py`,
`scripts/create_scraping_run_from_next_batch.py`,
`scripts/enqueue_deactivations.py`.

`run_daily_pipeline.py` además propaga `INTERNAL_DB_SCHEMA` a los subprocesos.

**Pendiente menor (herramientas manuales, fuera del ciclo diario):** todavía
usan `public.` hardcodeado `scripts/import_captured_props_to_neon.py`,
`scripts/generate_scraping_run_audit_reports.py`,
`scripts/validate_pinamar_pilot.py`. No afectan el pipeline diario ni los
dry-runs; parametrizarlos antes de usarlos contra Supabase.

### Cómo apuntar el pipeline a Supabase

```
USE_INTERNAL_DB=true
INTERNAL_DB_URL=<connection string de Supabase>
INTERNAL_DB_SCHEMA=internal_scraping
```

Para volver a Neon: quitar `INTERNAL_DB_SCHEMA` (o `=public`) y apuntar
`INTERNAL_DB_URL` a Neon.

---

## Paso 7 — Dry-runs contra Supabase

Ejecutados con `INTERNAL_DB_URL=<supabase>` + `INTERNAL_DB_SCHEMA=internal_scraping`
(sin modificar `.env`).

**`build_publish_queue.py --dry-run --limit 50`** → exit 0:
- `target=internal_db (schema=internal_scraping)`
- filas_leidas=50, encoladas=50 (priority 1=30, 2=20), `accion_final=rollback`.

**`run_daily_pipeline.py --dry-run`** → exit 0:
- FASE 0 PRE-FLIGHT: `supabase_health=ok`, conexión interna OK contra
  `internal_scraping`, sin filas atascadas.
- Plan impreso correctamente, sin ejecutar subprocesos ni escrituras.

Confirmación post dry-runs (rollbacks sin residuos):
`internal_scraping.publish_queue.done=11,687` (sin filas nuevas),
`staging`=68,367 / `published`=11,687 (sin cambios),
`public.propiedades=94,834` (intacto).

> **Latencia:** `--limit 50` tardó ~48s y `--limit 500` superó 300s. El cuello
> de botella es la latencia de red (Argentina → Supabase) con muchos round-trips
> por fila (SAVEPOINT/UPDATE/INSERT), no el schema. A considerar antes de correr
> el pipeline real contra Supabase: lotes chicos o batching de statements.

---

## Estado final

| Métrica | Valor |
|---------|------:|
| DB Supabase (total) | 770 MB |
| `internal_scraping` | 406 MB |
| Filas migradas | 252,433 |
| `public.propiedades` | 94,834 (intacto) |
| Neon | intacto (respaldo) |

---

## Qué NO se hizo (respetando restricciones)

- No se ejecutó Batch 100.
- No se hizo commit de scraping ni publicación a `public.propiedades`.
- No se borró Neon ni datos de Supabase.
- No se tocó el frontend ni `public.propiedades`.
- No se ejecutó limpieza/retención (`cleanup_old_data`).
- No se hizo push ni se imprimieron secrets.
- No se modificó `.env` (la variable `SUPABASE_DATABASE_URL` la gestiona el usuario).

---

## Siguientes pasos sugeridos (requieren autorización)

1. Decidir cutover: cuándo apuntar `INTERNAL_DB_URL`/`INTERNAL_DB_SCHEMA` de
   producción a Supabase (idealmente fuera de horario, con una corrida controlada).
2. Parametrizar los 3 scripts manuales pendientes si se van a usar contra Supabase.
3. Evaluar el impacto de latencia para corridas reales (batching).
4. Solo tras validar el cutover: decidir retención en Neon y eventual baja.
