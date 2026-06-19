# 2026-06-17 — Registro diario

## Resumen
Recovery del pipeline interno del Batch 100 (run_id=13) sin re-scrapear, tras el
timeout del orquestador del día anterior. Incluye fix autorizado de `missing_title`.

Ver [[Recovery Batch 100 run13 2026-06-17]].

## Hitos
1. **Fix `missing_title` no-bloqueante** (autorizado) en `validate_raw_properties.py`:
   título faltante ya no rechaza; fallback `{Tipo} en {ciudad}` → `{Tipo} en {provincia}`
   → `Propiedad en {ciudad}` → `Propiedad sin título`. 4 props recuperadas.
2. **Recovery run 13 completo**:
   - validate_raw: 1,823 raw → staging, **0 rejected** (tras fix), 0 duplicates.
   - geocode: done+392, failed+108, skipped+655 (backlog 42,280 pending, no bloquea).
   - build-queue: 10,000 encoladas, 0 omitidas.
   - publish: 1,000 publicadas (tope recovery), 0 failed, 0 omitidas; pending 9,000.
3. **Diagnóstico timeout**: scraper de 100 inmob con 2 workers tardó 171.7 min
   (> step-timeout 120 min). tokko es el CMS más lento (avg 240s/inmob).

## Estado final
- `public.propiedades`: **96,837** (+69 en el publish del recovery).
- `internal_scraping`: raw 82,174 validated (0 pendientes); queue done=13,707/pending=9,000.
- Supabase DB: 828 MB (internal 469 MB).
- Neon: **intacto/congelado**.

## Próximo paso (requiere autorización)
1. Mejora de raíz: que el orquestador continúe fases 3-5 si la run quedó `finished`
   (evita recoveries). Alternativa sin código: Batch 50 o subir `--step-timeout`.
2. Drenar las 9,000 pending por tandas.
3. No avanzar a Batch 250/500 sin autorización.
