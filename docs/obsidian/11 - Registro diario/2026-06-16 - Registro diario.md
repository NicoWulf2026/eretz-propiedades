# 2026-06-16 — Registro diario

## Resumen
Día grande de infraestructura: **migración del pipeline interno de Neon a Supabase
`internal_scraping`**, optimización, cutover y reanudación de campaña con Batch 100.

## Hitos
1. **Migración Neon → Supabase `internal_scraping`**: 9 tablas, 252,433 filas,
   verificado 1:1, sequences sincronizadas. Neon intacto como backup.
   Ver [[Migracion Neon a Supabase internal_scraping 2026-06-16]].
2. **Optimización `build_publish_queue`**: bulk (limit 500: >300s → ~5s).
   Ver [[Optimizacion build_publish_queue 2026-06-16]].
3. **Cutover**: `.env` → `USE_INTERNAL_DB=true`, `INTERNAL_DB_URL`=Supabase,
   `INTERNAL_DB_SCHEMA=internal_scraping`; Neon = `NEON_DB_URL_BACKUP`.
   Ver [[Cutover Supabase internal_scraping 2026-06-16]].
4. **Corrida real chica** (run_id=12): 5 inmobiliarias, 5/5 OK, 50 publicadas.
   Ver [[Corrida real chica post-cutover 2026-06-16]].
5. **Drenaje backlog**: 950 pending → 0 (950 publicadas, 0 failed).
6. **Batch 100** (run_id=13): 89/100 OK, error_rate 11%, 10,527 detectadas,
   **1,758 nuevas** a `public.propiedades` (96,768). Ver [[Batch 100 post-cutover 2026-06-16]].

## Incidente
- **Batch 100: timeout del orquestador** a 7200s en FASE 2 scraper. El scraper
  completó las 100 (run finished) pero las fases internas 3-5 NO corrieron →
  **1,823 raw quedaron sin validar** (sus props ya están en producción vía scraper directo).
- Clasificación: timeout por batch demasiado grande (no bug, no infra caída).

## Estado final
- `public.propiedades`: 96,768 (desde 94,834 al inicio del día).
- `internal_scraping`: 433 MB; Supabase DB 798 MB.
- Neon: intacto/congelado (80,054 raw, 11 runs).
- Pipeline opera 100% sobre Supabase.

## Próximo paso (requiere autorización)
1. Recovery pipeline interno run 13 (validate→geocode→build-queue→publish de 1,823 raw).
2. Ajustar `--step-timeout` del scraper o reducir tamaño de batch.
3. No avanzar a Batch 250/500 sin autorización.
