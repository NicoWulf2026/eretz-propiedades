# Corrida real chica post-cutover — pipeline completo con scraping (2026-06-16)

Primer ciclo end-to-end **con scraping real** corriendo contra Supabase
`internal_scraping` tras el cutover. 5 inmobiliarias, workers=1, publicación ≤50.
**Neon intacto.** Sin Batch 100, sin push, sin limpieza, sin tocar frontend.

Ver también: [[Cutover Supabase internal_scraping 2026-06-16]]

---

## Dry-run previo
Pre-flight OK contra `internal_scraping`, plan razonable (sin Playwright → HTTP),
exit 0. Sin fuentes prohibidas ni errores de schema.

## Resultado del commit real (run_id=12, ~38 min, exit 0)

| # | Métrica | Valor |
|---|---|---|
| 1 | run_id | **12** (`auto_batch_5_20260616_202259`, finished) |
| 2 | Inmobiliarias procesadas | **5** (Cecilia Inmuebles, Martiarena, DelCastillo, Russillo, Must Brokers — todas Tokko) |
| 3 | Exitosas / fallidas | **5 / 0** |
| 4 | **error_rate** | **0.00%** |
| 5 | Propiedades detectadas | **1,180** (scraped) |
| 6 | Raw nuevas / actualizadas | nuevas=**82**, actualizadas=**1,098** (a `public.propiedades`); raw insertadas en `internal_scraping`: **+297** |
| 7 | validate_raw | procesadas=**297**, rejected=**0**, duplicates=**0** (issues: geocoding_skipped_approx=58, invalid_address=1) |
| 8 | Geocoding | done=**93**, failed=**30**, skipped=**180**, requests=123 |
| 9 | Queue encoladas / omitidas | encoladas=**1,000** (5×200) / omitidas=**0** |
| 10 | publicadas_ok | **50** (5×10, tope respetado) |
| 11 | **failed final** | **0** |
| 12 | **omitidas final** | **0** |
| 13 | `public.propiedades` antes/después | 94,834 → **94,918** (Δ+84: 84 nuevas creadas + 1,230 updates en la última hora) |
| 14 | `internal_scraping` antes/después | ver tabla abajo |
| 15 | **Neon intacto** | **Sí** (raw=80,054, runs=11, publish_queue done=11,687 — congelado) |
| 16 | Performance por fase | ver abajo |
| 17 | Recomendación | **autorizar Batch 100 dry-run** |

### 14 — `internal_scraping` antes/después
| Tabla | Antes | Después | Δ |
|---|---:|---:|---:|
| propiedades_raw | 80,054 | 80,351 | +297 |
| staging.staging | 68,347 | 67,644 | −703 |
| staging.queued | 0 | 950 | +950 |
| staging.published | 11,707 | 11,757 | +50 |
| publish_queue.done | 11,707 | 11,757 | +50 |
| publish_queue.pending | 0 | 950 | +950 |

**Consistencia verificada:** staging.queued=950 ↔ publish_queue.pending=950;
staging.published=11,757 ↔ publish_queue.done=11,757. Conservación:
68,347 + 297 − 1,000 = 67,644 ✓.

### 16 — Performance por fase
| Fase | Detalle |
|---|---|
| FASE 1 create-queue | 5 items, run_id=12 (~s) |
| FASE 2 scraper | grueso del tiempo (~20 min, 5 Tokko; Cecilia 240 props ~4 min) |
| FASE 3 validate-raw | 3 iter (297 validadas), rápidas |
| FASE 3.5 geocoding | 3 iter, 123 requests Nominatim (~1/s + retries) |
| FASE 4 build-queue | 5 iter × ~1.5s = ~7s (bulk optimizado) |
| FASE 5 publish | 5 iter × ~30s = ~150s (50 props, ~3s/prop, rate-limit) |
| **Total** | **2,272 s (~38 min)** |

---

## Gates — todos OK
error_rate=0 · sin errores schema/permisos · failed=0 · omitidas=0 · sin timeouts
repetidos · publicación=50 (≤50) · sin uso de Neon (todo `internal_scraping`) ·
queue/staging consistentes · cambio en `public.propiedades` **esperado** (scraping
real autorizado) · sin fuentes prohibidas · dedup OK (sin duplicación).

## Notas
- **950 props quedaron en cola** (`pending`): el encolado (1,000) supera el tope de
  publicación por tanda (50). Es esperado; se publican en próximas corridas.
- **Geocoding fail/skip:** 30 failed + 180 skipped de direcciones argentinas
  parciales/garbage. Normal para Nominatim; no es problema del cutover.
- El scraper escribe a `public.propiedades` (flujo directo, FASE 2) **y** a
  `internal_scraping` (raw); la FASE 5 publica desde la cola. Por eso `public`
  sube +84 (scraping) además de los updates.

## Recomendación
**Listo para Batch 100 dry-run.** El ciclo completo funciona post-cutover con
scraping real: error_rate=0, failed=0, consistencia total, Neon intacto. Antes
del Batch 100 commit, considerar:
- La publicación es el cuello (~3–10s/prop): un Batch 100 generará una cola grande
  que tomará tiempo drenar a 50/tanda; planificar tandas de publicación.
- Monitorear geocoding (Nominatim rate-limit) en volúmenes mayores.
