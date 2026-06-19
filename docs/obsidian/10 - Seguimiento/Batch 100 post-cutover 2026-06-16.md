# Batch 100 post-cutover — drenaje + Batch 100 commit (2026-06-16)

Reanudación de campaña nacional contra Supabase `internal_scraping`. Drenaje del
backlog (950) + Batch 100 con scraping real. **Neon intacto.** Sin push, sin
limpieza, sin tocar frontend. Detención obligatoria tras este informe.

Ver también: [[Corrida real chica post-cutover 2026-06-16]] ·
[[Cutover Supabase internal_scraping 2026-06-16]] · [[11 - Pendientes]]

---

## FASE 0 — Baseline (OK)
Pipeline confirmado en Supabase `internal_scraping` (no Neon). public.propiedades=94,918,
publish_queue done=11,757/pending=950, Supabase 777 MB, 2,148 inmobiliarias elegibles
(de 7,004). Neon congelado.

## FASE 1 — Drenaje backlog (950) ✅
19 tandas de 50 (`publish --max-supabase-writes 50 --commit`):
- publicadas_ok=**950**, failed=**0**, omitidas=**0**, **pending final=0** (cola limpia).
- public.propiedades 94,918 → 95,010 (Δ+92: ~92 inserts + 858 updates).
- Tiempo: ~43 min.

## FASE 2 — Batch 100 dry-run ✅
100 candidatas (todas Santa Fe): CMS tokko=65/wordpress=17/custom=18.
**0 fuentes prohibidas, 0 antibot, 0 portales externos**, datos completos.
Estimación detectadas ~7,929. Sin bloqueantes → commit autorizado.

## FASE 3 — Batch 100 commit ⚠️ (timeout del orquestador, datos OK)

**run_id=13.** El scraper **completó las 100 inmobiliarias** (run_status=finished),
pero su subprocess excedió el `step-timeout` de 7200s → el orquestador lo marcó
"scraper timeout" y **NO ejecutó las fases 3-5** (validate/geocode/build-queue/publish).

### Resultado real (verificado en DB, no en el RESUMEN engañoso)
| Métrica | Valor |
|---|---|
| Inmobiliarias procesadas | **100** (89 success, 11 error) |
| **error_rate** | **11%** (gate 0.40 — OK) |
| Propiedades detectadas | **10,527** |
| Nuevas | **1,758** |
| Actualizadas | **8,769** |
| Raw insertadas | +1,823 (status `raw`, sin validar) |
| `public.propiedades` | 95,010 → **96,768** (+1,758, publicadas directo por el scraper en FASE 2) |
| Duración | ~172 min (scraper tope 120 min) |

### Errores (11) por tipo y CMS
- requires_playwright=4 (custom), timeout=2 (wordpress), sin_propiedades=2 (custom),
  item_timeout=1 (tokko), site_down_confirmed=1 (wordpress), skipped_invalid_source=1 (custom).
- **Desempeño por CMS:** tokko 2% error (43/1), wordpress 16% (16/3), custom 19% (30/7).
- Todos los errores son esperados/normales; ninguno crítico ni de corrupción.

## FASE 4 — Clasificación del incidente

**Tipo: timeout por batch demasiado grande** (no es bug, no es infra caída, no es CMS).
- Causa: 100 inmobiliarias con workers=2 tardaron >7200s; el scraper terminó igual
  (run finished) pero el orquestador abortó las fases internas 3-5.
- Archivo: `scripts/run_daily_pipeline.py` (`--step-timeout` del scraper, default 7200s).
- Cambio propuesto (NO aplicado, requiere autorización): subir `--step-timeout` del
  scraper o bajar tamaño de batch.
- Riesgo: bajo. Reversible. Sin migración SQL.
- **Datos íntegros:** las props scrapeadas ya están en producción; las 1,823 raw
  quedaron recuperables (status `raw`).

## FASE 5 — Informe final (25 puntos)
1. run_id=**13**  2. procesadas=**100**  3. **89 ok / 11 error**  4. error_rate=**11%**
5. detectadas=**10,527**  6. nuevas=**1,758**  7. actualizadas=**8,769**
8. raw validadas: pipeline interno NO corrió (1,823 raw pendientes) — validación del
   scraper sí (score≥85)  9. rejected/duplicates: N/A (validate_raw no corrió)
10. geocoding: **no corrió** (FASE 3.5 abortada)  11. queue encoladas: **0** (FASE 4 no corrió)
12. publicadas_ok vía pipeline: 0; **vía scraper directo: 1,758**  13. failed final=0
14. omitidas final=0  15. pending final=**0** (cola quedó limpia del drenaje)
16. errores por inmobiliaria: ver FASE 4  17. errores por CMS: tokko 1, wordpress 3, custom 7
18. desempeño no-tokko: wordpress 84% ok, custom 81% ok (aceptable sin Playwright)
19. duración total (drenaje+batch): ~43min + ~172min  20. public.propiedades 95,010 → **96,768**
21. internal_scraping: raw 80,351→82,174, staging sin cambios (pipeline interno no corrió),
    queue done=12,707/pending=0  22. **Neon intacto** (80,054 raw, 11 runs)
23. storage Supabase: **798 MB** (internal_scraping 433 MB)  24. Obsidian: este doc + Pendientes + Registro
25. **Recomendación: ver abajo**

## Recomendación (próximo paso)

**No pasar a Batch 250/500/1000.** Primero:

1. **Completar el pipeline interno del run 13** (recovery seguro, idempotente, no
   re-scrapea): `validate_raw` (1,823 raw → staging) → `geocode_staging` →
   `build_publish_queue` → `publish` por tandas. Esto agrega geocoding/coordenadas
   a las propiedades del batch. **Requiere autorización** (es completar el batch).
2. **Ajustar el timeout para futuros batches** (cambio de código, requiere
   autorización): subir `--step-timeout` del scraper, o limitar batches a ~50
   inmobiliarias para que las fases 3-5 corran dentro de la ventana.
3. Luego repetir Batch 100 (o Batch 50) ya con las fases internas completas.

**Gate de detención respetado:** no se avanza a batches mayores sin autorización.
