# Validación controlada `internal_scraping` (2026-06-16)

Prueba chica y controlada del ciclo de pipeline contra Supabase `internal_scraping`,
previa al cutover. **Sin publicar a `public.propiedades`, sin `publish_to_supabase`,
sin Batch 100, sin push, sin tocar frontend ni Neon.**

Ver también: [[Optimizacion build_publish_queue 2026-06-16]] ·
[[Migracion Neon a Supabase internal_scraping 2026-06-16]]

Variables usadas: `USE_INTERNAL_DB=true`, `INTERNAL_DB_URL=<supabase>`,
`INTERNAL_DB_SCHEMA=internal_scraping`.

---

## 1. Estado inicial (read-only)

| Métrica | Valor |
|---|---|
| `publish_queue` | done=11,687 |
| `propiedades_staging` | staging=68,367 · published=11,687 |
| `propiedades_raw` | 80,054 (todas `validated`) |
| `public.propiedades` | 94,834 |
| último `scraping_run` | id=11 `auto_batch_50` finished |
| último `scraping_run_item` | id=73 (run 11) success |

## 2. Dry-run `validate_raw_properties --limit 100`
exit 0 · `filas_leidas=0` (no hay raw en estado `raw`; todas `validated`) ·
`accion_final=rollback`. Conexión a `internal_scraping` OK, sin errores de
schema/permisos. ~5s.

## 3. Dry-run `geocode_staging --limit 100 --max-requests 10`
exit 0 · leyó 100 staging, clasificó readiness
(`geocoding_ready_safe`→probe, `garbage_address`→skipped) · dry-run sin
escritura. Sin errores de schema/permisos. ~8s.

## 4. `build_publish_queue --limit 100`

**Dry-run:** `filas_leidas=100`, `encoladas=100`, `omitidas=0`, `ya_en_cola=0`,
rollback, exit 0 (total interno 1.6s).

**Commit chico:** `encoladas=100` (priority 1=63, 2=37), `omitidas=0`,
`accion_final=commit`, exit 0 (total interno 1.4s).

## 5. Verificación post-commit (antes → después)

| Métrica | Antes | Después | Δ |
|---|---:|---:|---:|
| `publish_queue.pending` | 0 | 100 | +100 |
| `publish_queue.done` | 11,687 | 11,687 | 0 |
| `propiedades_staging.queued` | 0 | 100 | +100 |
| `propiedades_staging.staging` | 68,367 | 68,267 | −100 |
| `public.propiedades` | 94,834 | **94,834** | **0 (intacta)** |

Conservación correcta: 100 filas pasaron `staging → queued` y generaron 100
entradas `pending` en `publish_queue`.

## 6. Cambios reales en `internal_scraping`
- +100 filas `pending` en `publish_queue`.
- 100 filas `propiedades_staging` cambiadas de `staging` a `queued`.
- Nada más. `propiedades_raw`, `scraping_runs`, `scraping_run_items`, geocoding: sin cambios.

## 7. `public.propiedades`
**Intacta: 94,834** antes y después. No hubo publicación. Frontend no tocado.

## 8. Tiempos
| Paso | Tiempo interno |
|---|---|
| validate_raw dry-run | ~5s |
| geocode_staging dry-run | ~8s |
| build_queue dry-run | 1.6s |
| build_queue commit | 1.4s |

## 9. Errores
Ninguno. Todos los pasos exit 0, sin errores de schema ni de permisos.

## 10. Estado de la prueba — REVERTIDA (Opción B)

El usuario eligió **Opción B (revertir)**. Reversión ejecutada en una
transacción con sanity-check (exactamente 100/100 antes de tocar):
- `DELETE FROM internal_scraping.publish_queue WHERE status='pending'` → 100 filas.
- `UPDATE internal_scraping.propiedades_staging SET status='staging' WHERE status='queued'` → 100 filas.

**Estado final verificado — idéntico al post-migración:**
- `publish_queue`: done=11,687.
- `propiedades_staging`: staging=68,367 · published=11,687.
- `public.propiedades`: 94,834.

La prueba no dejó residuos. `internal_scraping` quedó en el estado conocido
post-migración, listo para un cutover controlado posterior.
