# Recovery Batch 100 (run_id=13) sin re-scraping — 2026-06-17

Completar el pipeline interno del run 13, cuyas fases 3-5 no corrieron por el
timeout del orquestador. **Sin re-scrapear. Neon intacto.** Incluye fix autorizado
de `missing_title`. Detención obligatoria tras el informe.

Ver también: [[Batch 100 post-cutover 2026-06-16]] · [[11 - Pendientes]]

---

## Fix autorizado: `missing_title` no-bloqueante

- **Archivo:** `scripts/validate_raw_properties.py`.
- **Cambio:** `missing_title` deja de ser hard reject; pasa a soft issue (−5 score).
- **Fallback de título** (prioridad): `{Tipo} en {ciudad}` → `{Tipo} en {provincia}`
  → `Propiedad en {ciudad}` → `"Propiedad sin título"`.
- **py_compile:** OK.
- **Recuperadas:** 4/4 (inmobiliaria 5261, agserviciossrl.com) reseteadas
  rejected→raw y re-validadas → staging con títulos:
  `Casa en Capital Federal`, `Local en Capital Federal`, `Cochera en Lanús`,
  `Otro en Lanús`.
- Solo se modificó la regla de `missing_title`; el resto de reglas de publicación intacto.

## FASE 0 — Diagnóstico (OK)
Supabase `internal_scraping`, Neon no usado. 1,823 raw pendientes, run 13 finished
(89 ok/11 error), sin procesos activos, Neon intacto.

## FASE 1 — validate_raw ✅
- 1,823 raw → 1,819 validadas + 4 rechazadas (missing_title) → **tras fix: 4 recuperadas**.
- **rejected final=0**, duplicates=0.
- Issues (soft, no bloquean): geocoding_skipped_approx_location, missing_images,
  invalid_coordinates, invalid_address, operacion_venta_y_alquiler, missing_title (4).
- Performance: ~32 min (≈1s/fila por latencia; script no optimizado para bulk).

## FASE 2 — geocode_staging ✅
done=**392**, failed=**108**, skipped=**655**, requests usados=**500** (tope).
Backlog: **42,280 pending** (no bloquea — `allow_pending_geo=True`). ~30 min.

## FASE 3-4 — build_publish_queue ✅
Dry-run y commit: encoladas=**10,000**, omitidas=**0**, ya_en_cola=0
(prioridad 1=5,149, 2=4,851). Performance ~8-12s (bulk). pending=10,000.

## FASE 5 — publish limitado ✅
10 tandas de 100 (tope **1,000** de esta recovery): publicadas_ok=**1,000**,
failed=**0**, omitidas=**0**. pending_final=**9,000**.
public.propiedades 96,768 → **96,837** (+69 nuevas, 931 updates). ~41 min.

## FASE 6 — Diagnóstico del timeout del orquestador (sin modificar)

| # | Pregunta | Hallazgo |
|---|---|---|
| 1 | ¿Por qué excedió 7200s? | Trabajo total ~19,295s ÷ 2 workers ≈ 161 min ideal; real **171.7 min** > 120 min (step-timeout) |
| 2 | Duración real scraper | **10,303s = 171.7 min** (100 items, 89 ok/11 error) |
| 3 | Duración por CMS | **tokko avg 240s** (más props → más lento), custom 143s, wordpress 183s; item p90=267s, max=356s |
| 4 | ¿Subir `--step-timeout`? | Sí: Batch 100 con workers=2 necesita ~180-200 min → step-timeout ~14,400s (4h) con margen |
| 5 | ¿Dividir en Batch 50? | Sí: Batch 50 ≈ 85 min, entra en el 120 min actual (más granular/seguro) |
| 6 | ¿`--scrape-timeout` por item? | Poco valor: items individuales son razonables (max 356s); el problema es el agregado |
| 7 | ¿Orquestador continúe 3-5 si run finished? | **Sí — la mejor mejora.** El scraper terminó (run finished, 100 items) pero el orquestador abortó 3-5 por el timeout del subprocess. Detectar run finished antes de abortar evitaría perder el trabajo |

**Todas las opciones de FASE 6 requieren cambio de código → NO aplicadas (sin autorización).**

## Informe final (15 puntos)
1. Recovery: **completo** (validate/geocode/build-queue); publish **parcial por diseño**
   (1,000 de 10,000, tope de recovery).  2. raw procesadas=**1,823** (1,819 + 4 recuperadas)
3. rejected=**0** / duplicates=**0**  4. geocoding: done+392, failed+108, skipped+655, backlog 42,280 pending
5. queue encoladas=**10,000** / omitidas=**0**  6. publicadas_ok=**1,000**  7. failed final=**0**
8. omitidas final=**0**  9. pending final=**9,000**  10. public.propiedades 96,768 → **96,837**
11. internal_scraping: raw 1,823 `raw`→0 (todas validated); staging published 12,707→13,707,
    queued 0→9,000, staging 69,463→59,467; queue done 12,707→13,707, pending 0→9,000
12. **Neon intacto** (80,054 raw, 11 runs)  13. errores run 13: 4 requires_playwright, 2 timeout,
    2 sin_propiedades, 1 item_timeout, 1 site_down, 1 skipped_invalid_source (11 total)
14. storage Supabase **828 MB** (internal 469 MB)  15. recomendación ↓

## Recomendación

**No avanzar a Batch 250/500/1000.** Antes:
1. **Decidir la mejora del orquestador** (FASE 6 punto 7): que continúe fases 3-5 si
   la run quedó finished. Es la solución de raíz (evita re-trabajo y recoveries).
   Alternativa inmediata sin código: **usar Batch 50** (entra en la ventana de 120 min).
2. **Drenar las 9,000 pending** restantes por tandas (backlog publicable, no bloquea).
3. Recién después, repetir Batch 50/100 con el ciclo interno completo en una sola corrida.
