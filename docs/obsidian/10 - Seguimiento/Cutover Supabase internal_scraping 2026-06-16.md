# Cutover controlado → Supabase `internal_scraping` (2026-06-16)

Cutover de configuración: el pipeline interno pasa a usar Supabase
`internal_scraping` por defecto (vía `.env`). Validado end-to-end **sin scraping**
(por restricción explícita "No ejecutar scraping commit"). **Neon intacto como
backup.** Sin Batch 100, sin push, sin tocar frontend.

Ver también: [[Validacion final publish_to_supabase 2026-06-16]] ·
[[Migracion Neon a Supabase internal_scraping 2026-06-16]]

---

## Cambio de configuración (`.env`, gitignored)

| Variable | Antes | Después |
|---|---|---|
| `USE_INTERNAL_DB` | false | **true** |
| `INTERNAL_DB_URL` | Neon | **Supabase** (= `SUPABASE_DATABASE_URL`) |
| `INTERNAL_DB_SCHEMA` | (ausente → public) | **internal_scraping** |
| `NEON_DB_URL_BACKUP` | — | **Neon** (preservado, backup) |

Backup del `.env` previo: `.env.bak.precutover_20260616_161121`.
Cambios aplicados sin imprimir secrets.

---

## Decisión sobre el commit con scraping

El comando `run_daily_pipeline --commit --inmobiliarias 5` dispara **FASE 2
scraper real** (sitios web externos) + geocoding real + publicación, lo que
choca con la restricción "No ejecutar scraping commit". El pipeline no tiene flag
para saltear el scraping. Por decisión del usuario, se validó el cutover **sin
scraping**: solo `build_queue (commit)` → `publish (commit, máx 10)`, leyendo de
`.env` (sin override) para confirmar el cutover real.

---

## Verificación final

1. **¿Usó Supabase `internal_scraping`?** Sí. Logs: `target=internal_db
   (schema=internal_scraping)` y `[internal-db] enabled: using INTERNAL_DB_URL
   (schema=internal_scraping)`. Leído de `.env` sin override.
2. **run_id:** N/A — no se creó scraping_run (FASE 1/2 omitidas por no scraping).
3. **Inmobiliarias procesadas:** N/A (sin scraping).
4. **Propiedades detectadas:** N/A (sin scraping).
5. **Raw validadas:** N/A (validate_raw no aplica: raw ya `validated`; el dry-run
   previo dio `filas_leidas=0`).
6. **Geocoding:** N/A (sin scraping; dry-run previo OK).
7. **Queue encoladas:** **10** (`build_queue --limit 10 --commit`, omitidas=0).
8. **Publicadas:** **10** (`publish --limit 10 --commit`, 10 updates, 0 inserts).
9. **Failed:** **0**.
10. **Omitidas:** **0**.
11. **`public.propiedades` antes/después:** 94,834 → **94,834** (Δ0; 10 updates,
    `updated_at` refrescado 10/10).
12. **Performance por fase:**
    - build_queue commit: ~1.1s (10 filas).
    - publish commit: 28.4s (10 props, ~2.8s/prop; sin timeouts esta vez).
13. **¿Neon intacto?** Sí. Congelado: raw=80,054, staging=80,054
    (staging=68,367/published=11,687), publish_queue done=11,687, runs=11,
    items=73. El pipeline ya no le escribe.
14. **¿Listo para Batch 100 dry-run?** Sí del lado de infraestructura/cutover.

---

## Estado post-cutover (Supabase `internal_scraping`)

| Métrica | Valor |
|---|---|
| `publish_queue` | done=11,707 |
| `propiedades_staging` | published=11,707 · staging=68,347 |
| `public.propiedades` | 94,834 |

Progreso ocurre en Supabase; Neon quedó congelado (backup).

---

## Recomendación

- **Cutover efectivo y validado** del lado de datos (build_queue → publish →
  `public.propiedades`). El pipeline usa Supabase por defecto.
- **Pendiente de validar con scraping real** (FASE 1+2): requiere autorización
  explícita de scraping. Recién entonces tiene sentido un Batch 100 dry-run y
  luego controlado.
- **Performance de publicación** ~2.8–10s/prop (rate-limit + latencia): publicar
  el backlog (~57k staging) llevará horas; correr por tandas.
- **Reversión disponible:** restaurar `.env.bak.precutover_*` o apuntar
  `INTERNAL_DB_URL` a `NEON_DB_URL_BACKUP` vuelve a Neon.
- No borrar Neon hasta operar varios ciclos estables en Supabase.
