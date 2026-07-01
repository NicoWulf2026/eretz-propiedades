# Pendientes de ERETZ Propiedades

Ultima actualizacion: 2026-07-01 (Cierre backend técnico en curso — PR-BE-PROD-09e auditado como parcial. Fix anti-MemoryError implementado (context recycling cada 50 fuentes). Tests 64/64 verdes. PR técnico preparado. Próximo paso: autorizar PR técnico → corrida pendientes 29 fuentes → frontend.)

Ver también: [[Auditoria completa y rebranding ERETZ 2026-06-17]]

---

## 🟢 PR-BE-PROD-09d — Corrida controlada 50 fuentes manifest (COMPLETADO, 2026-06-28)

Pipeline nuevo: `run_manifest.py` + `propiedades` directa, sin raw/staging/publish_queue.

### Resumen ejecutivo

| Fase | Fuentes | Inserts | Errores DB |
|---|---|---|---|
| 09d original | 50 | 0 | 23514 (propiedades_estado_chk) |
| 09d-ESTADO (fix) | — | — | Fix: `estado='activa'` en `to_payload()` |
| 09d-ESTADO canary | 15 | +385 | 0 |
| 09d-REMAINDER | 35 | +654 | 0 |
| **Total 09d** | **50** | **+1.039** | **0** |

- propiedades antes: 114.520 → propiedades después: **115.559**
- FK match total: 38/50 (76%)
- Sin FK omitidas: 12/50 (24%)
- Duración total: ~71 min (2 workers)

### Constraints PostgreSQL resueltos históricamente en PR-BE-PROD-09d

| # | Error PG | Descripción | Fix |
|---|---|---|---|
| 1 | 23502 | inmobiliaria_id NOT NULL | FK preflight en run_manifest.py |
| 2 | 42P10 | on_conflict=url sin unique constraint | INSERT plain sin on_conflict |
| 3 | 23502 | columnas inexistentes en payload | Limpieza to_payload() |
| 4 | 23502 | hash_dedup NOT NULL | _compute_hash_dedup() en to_payload() |
| 5 | 22003 | integer overflow (teléfonos como int) | _safe_int() guard |
| 6 | 23514 | propiedades_estado_chk | `"estado": "activa"` hardcoded en to_payload() |

### Tablas escritas / no escritas

- SÍ escrito: `propiedades` (INSERT plain, sin on_conflict)
- NO tocado: inmobiliarias_main (solo SELECT FK lookup) · publish_queue · raw/staging · url_listado · frontend

### Archivos outputs

- `_scratch/run_manifest_09d/` — ejecución original fallida
- `_scratch/run_manifest_09d_estado/` — fix + tests (7 tests nuevos)
- `_scratch/run_manifest_09d_estado_canary/` — canary 15 fuentes
- `_scratch/run_manifest_09d_remainder/` — remanente 35 fuentes + informe 20 puntos
- `tests/test_run_manifest.py` — 55 tests (incluyendo 7 de estado)

---

## 🟠 PR-BE-PROD-09e — Corrida completa 892 fuentes (PARCIALMENTE COMPLETADA — 2026-07-01)

**Decisión operativa (2026-07-01):** 09e aceptada como corrida parcial acumulada. No se lanzará rerun_04 por ahora. Las 29 fuentes pendientes quedan para la próxima corrida autorizada. Pasar a auditoría backend y frontend.

### Resumen acumulado 09e

| Intento | Fuentes procesadas | Props insertadas | Causa corte |
|---|---|---|---|
| Intento 1 | 99/615 (16%) | +3.082 | Sesión desconectada |
| rerun_01 | 123/615 (20%) | +841 | Sesión desconectada |
| rerun_02 | 586/615 (95%) | +12.610 | MemoryError Playwright (>3GB RAM, 2 workers, 20h+) |
| rerun_03 | 250/615 (41%) | +2.752 | Apagado accidental del equipo |
| **Total 09e** | **~586 fuentes completas** | **+19.285** | — |

- **propiedades antes de 09e:** 115.559
- **propiedades actuales:** 134.844
- **Delta total 09e: +19.285**
- FK match: 615/891 (69%) · Sin FK omitidas: 276/891 (31%)
- D'Aragona (id=4855): rechazado por validación (error http_error) — no en manifest_excluded

### Integridad confirmada
- hash_dedup NULL: 0 ✅ · inmobiliaria_id NULL: 0 ✅ · url NULL: 0 ✅ · precio <0: 0 ✅
- 3 errores 409 hash_dedup (no críticos — secondary safety net) · Sin constraint violations críticos
- No se tocó: publish_queue · raw/staging · schema · frontend · inmobiliarias_main (solo SELECT)

### Fix de dedup implementado (2026-06-28, PR-BE-PROD-09e-DEDUP-FIX)
- `_load_existing_urls_by_inmobiliaria()` en `scripts/run_manifest.py` — una query por `inmobiliaria_id`
- `MAX_EXECUTE_LIMIT` = 892 · `_ProgressTracker` (progress_live.md cada 250 fuentes o 15 min)
- 64/64 tests verdes

### Fix anti-MemoryError implementado (2026-07-01)
- `CONTEXT_RECYCLE_EVERY = 50` en `scraper/run.py` — recicla el BrowserContext cada 50 fuentes
- Libera memoria acumulada de Chromium sin reiniciar el browser process
- Compatible con workers=1 y workers=2
- Tests 64/64 sigue verde después del cambio
- Próxima corrida (29 pendientes): riesgo de MemoryError reducido significativamente

### Pendientes para próxima corrida
- 29 fuentes nunca procesadas → `_scratch/run_manifest_09e_audit/manifest_pendientes_09e.csv`
- Manifest a usar: mismo `manifest_success_only.csv` con `--limit 892`
- El dedup protege las 134.844 URLs ya en DB
- Producción neta esperada: propiedades de las 29 fuentes (~500–3.000 props)

### Outputs
- `_scratch/run_manifest_09e/` · `_scratch/run_manifest_09e_rerun_01/` · `_scratch/run_manifest_09e_rerun_02/` · `_scratch/run_manifest_09e_rerun_03/`
- `_scratch/run_manifest_09e_audit/auditoria_09e.md` — reporte consolidado
- `_scratch/run_manifest_09e_audit/manifest_pendientes_09e.csv` — 29 fuentes pendientes

---

## 🟢 Cierre técnico — Herramientas Grupo B timeout (2026-06-23)

Se completaron y **mergearon a `main`** los dos PRs técnicos necesarios para habilitar un futuro reintento controlado del Grupo B timeout. (La decisión de fondo y el diseño están en la sección 🔵 más abajo.)

### PR #2 — Acceso a errores
- **Estado:** merged · **Merge:** Squash and merge · **SHA en main:** `a99f172739`
- **Archivos incorporados:** `scripts/create_retry_run_from_error_items.py` · `tests/test_create_retry_run_from_error_items.py`
- **Función:** crear runs de reintento desde `scraping_run_items` con `status='error'`, sin depender de `v_next_scraping_batch`.
- **Características:** dry-run por default · `--commit` explícito · `--ids-file` · allowlist solo `timeout`/`item_timeout`/`static_timeout` · no Playwright · no backfill · no vistas · no DB productiva salvo futuro `--commit` autorizado · metadata de trazabilidad (`retry_of_run_id`, `original_run_item_id`, `original_error_type`).

### PR #3 — Timeout configurable
- **Estado:** merged · **Merge:** Squash and merge · **SHA en main:** `106fc447fc`
- **Archivos incorporados:** `scraper/scraper_propiedades.py` · `tests/test_timeout_env_config.py` · `.env.example`
- **Función:** ajustar timeouts del scraper mediante `SCRAPER_TIMEOUT_MULTIPLIER` (default `1.0` → comportamiento idéntico al histórico).
- **Validado:** default histórico `240/90/240/300` · multiplier `1.5` → `360/135/360/450` · suite completa verde (65) · sin cambios en lógica de scraping · sin activar Playwright.

**Historia en main:** `106fc447 (#3)` → `a99f1727 (#2)` → `3e957898 (base)`.

### Estado productivo
No se ejecutó scraping. No se tocó DB. No se creó ningún run productivo (último run_id sigue en 63). No se usó `--commit` real. No se usó `SCRAPER_TIMEOUT_MULTIPLIER` en corrida real. No se ejecutó validate_raw / build_queue / publish.

### Próximo paso pendiente — Mini-lote real Grupo B timeout (requiere autorización explícita)
**Orden futuro:**
1. Preflight: `scraping_run_items pending = 0` · `publish_queue pending = 0` · `failed = 0` · `publishing = 0` · `critical = 0` · queries largas = 0.
2. Crear ids-file con 5 timeout sub-tope: **696, 1288, 5724, 495, 1485**.
3. Crear run de reintento con `--commit` (`scripts/create_retry_run_from_error_items.py`).
4. Ejecutar scraper: `SCRAPER_TIMEOUT_MULTIPLIER=1.5 python scraper/scraper_propiedades.py --max-items 5 --workers 1`.
5. Aplicar gates.
6. Solo si gates pasan: validate_raw scoped → build_queue por run_id → publish exacto → verificar pending/failed/publishing = 0.

**Qué NO hacer sin autorización:** no batch grande · no Playwright · no `--retry-errors` · no `--include-backlog` · no mezclar con otros error_type · no tocar frontend · no tocar Neon · no publicar sin gates.

## 🔵 Decisión pendiente — Reintento Grupo B timeout (2026-06-23)

**Contexto:**
- Grupo B = **44 inmobiliarias** con errores `timeout` (27), `item_timeout` (16) o `static_timeout` (1).
- **No están en `v_next_scraping_batch`** (sin `url_listado`/`sitio_activo` en base) → el flujo `--inmobiliaria-id` NO sirve.
- `--retry-errors` alcanza los datos (lee de `scraping_run_items` status=error) pero **fuerza Playwright** (technical_mode → allow_playwright=True), **no filtra solo timeout** (toma todos los retryables, incl. requires_playwright) y **no resuelve la causa raíz** (Playwright es más lento, no da más presupuesto HTTP).
- Los timeouts están **hardcodeados** (constantes líneas 103-126 de `scraper_propiedades.py`), sin flag/env.
- Split por duración: ~26 agotaron el tope de 240s (estructural), ~18 fallaron sub-tope (transitorio, mejores candidatos).

**Conclusión:** para reintentar Grupo B de forma segura hacen falta **dos PRs separados**.

### PR 1 — Acceso a errores (implementar PRIMERO)
- **Branch:** `feat/retry-run-from-error-items`
- **Título:** `Nuevo script: crear run de reintento desde scraping_run_items con error (scoped, dry-run-first)`
- **Objetivo:** script nuevo `scripts/create_retry_run_from_error_items.py` que crea un `scraping_run` + `scraping_run_items` nuevos con `status=pending`, **copiando verbatim** datos desde `scraping_run_items` anteriores con `status=error` (inmobiliaria_id, nombre, ciudad, provincia, web, url_listado, cms_detectado). Copiar verbatim = sin mapeo de IDs (preserva el id-space correcto).
- **Características:** dry-run por default · `--commit` explícito · `--ids-file` · `--error-type` · allowlist solo `{timeout, item_timeout, static_timeout}` · NO Playwright · NO tocar vistas · NO backfill · NO modificar datos base · NO usar `v_next_scraping_batch` · metadata con `retry_of_run_id`, `original_run_item_id`, `original_error_type` · dedup (skip si ya hay pending para esa inmobiliaria) · skip cms prohibido (zonaprop/argenprop) · skip sin web/url_listado.
- **Archivos:** `scripts/create_retry_run_from_error_items.py` (nuevo) + `tests/test_create_retry_run_from_error_items.py` (nuevo). NO modifica `create_scraping_run_from_next_batch.py`.
- **Rollback:** run autocontenido; si no se scrapea, pending queda inerte. Suave: PATCH run+items a `cancelled` (sin borrar). Código: `git revert`.

### PR 2 — Timeout configurable (implementar DESPUÉS)
- **Branch:** `feat/scraper-timeout-configurable-env`
- **Título:** `Scraper: timeouts de item/estrategia configurables por env (default sin cambios)`
- **Objetivo:** hacer configurables los timeouts vía env, con default idéntico al actual.
- **Env principal:** `SCRAPER_TIMEOUT_MULTIPLIER` · default `1.0` · rango `[0.5, 5.0]` (clamp).
- **Aplica a:** `CONTROL_ITEM_TIMEOUT_SECONDS` (240) · `SIMPLE_ITEM_TIMEOUT_SECONDS` (90) · `CUSTOM_OR_SITEMAP_ITEM_TIMEOUT_SECONDS` (240) · `PLAYWRIGHT_ITEM_TIMEOUT_SECONDS` (300) · `STRATEGY_TIMEOUT_SECONDS` (dict 16 entradas).
- **Condición obligatoria:** sin env definida → comportamiento **exactamente igual** al actual.
- **Scope mínimo:** solo bloque de definición (líneas 103-126) + helper `_env_float` (junto al `_env_flag` línea 66) + tests. Cero cambios en consumidores (`_item_timeout_seconds` línea 14977, `STRATEGY_TIMEOUT_SECONDS.get` línea 958 leen el global en runtime).
- **Archivos:** `scraper/scraper_propiedades.py` + `tests/test_timeout_env_config.py` (nuevo) + `.env.example`.
- **Rollback:** instantáneo (`unset SCRAPER_TIMEOUT_MULTIPLIER`) o `git revert`.

### Orden recomendado
1. Implementar PR 1 (acceso) — desbloquea.
2. Implementar PR 2 (timeout).
3. Recién después, probar Grupo B con un mini-lote de 5.

### Uso futuro esperado (NO ejecutar ahora)
```bash
python scripts/create_retry_run_from_error_items.py --ids-file timeouts5.csv --error-type timeout --commit
SCRAPER_TIMEOUT_MULTIPLIER=1.5 python scraper/scraper_propiedades.py --max-items 5 --workers 1
```
Después: validate_raw scoped (ids-file) → build_queue por run_id → publish exacto → pending/failed/publishing final = 0.

### Gates futuros
mini-lote máximo 5 · solo `timeout` puro sub-tope al principio · `workers=1` · error_rate máximo 40% · critical=0 · queries largas=0 · sin mezcla · sin backlog · sin `--include-backlog` · NO Playwright · NO fuentes prohibidas.

### Qué NO hacer
- No usar `--retry-errors` para Grupo B.
- No usar Playwright para estos timeouts.
- No backfillear `inmobiliarias_scraping`.
- No meter las 44 en la vista artificialmente.
- No batch grande.
- No mezclar timeout con Playwright/no_property_links/sin_propiedades.
- No implementar ambos PRs sin revisión separada.

**Archivos de análisis (read-only):** `_grupo_b_detalle.py`, `_grupo_b_result.json`, `_grupo_b_en_vista.py`, `_grupo_b_estado_base.py`, `_consolidado_fallidas.py`, `_consolidado_fallidas_result.json`.

## 🟢 Track A — Cierre de pendientes internos runs 16–22 (COMPLETADO, 2026-06-22)

Rama: `feat/fase-b1-publish-robustez`. **Push: no realizado.** Alcance autorizado: solo runs 19/21/22; NO se tocó Grupo B (backlog viejo trazable) ni Grupo C (pre-tracking, raw.scraping_run_item_id=NULL).

**Auditoría previa (solo lectura):** raw sin validar = 2.957 (100% runs 21/22, cero backlog); staging sin encolar = 8.147 (3.809 runs 16-22 trazables + 1.437 backlog viejo + 2.901 pre-tracking sin run_id). De los trazables, solo ~14 inserts reales; resto updates por dedup `url_normalizada`.

**PASO 1 — validate_raw (runs 21 y 22) vía `--ids-file`** (el script no tiene `--run-id`; se generaron CSVs scoped con `WHERE id = ANY(...)`):

| batch | IDs | validadas | rechazadas |
|-------|-----|-----------|------------|
| 1-5 | 500 c/u | 500 c/u | 0 |
| 6 final | 457 | 457 | 0 |
| **Total** | **2.957** | **2.957** | **0** |

Solo warnings no-bloqueantes (geocoding_skipped_approx_location, missing_images, invalid_address, operacion_venta_y_alquiler). Raw pendientes runs 21/22 → **0**.

**PASO 2 — build_queue scoped por run** (`--run-id`, dry-run + commit, sin `--include-backlog`):

| run | encoladas | inserts reales | updates | ya_en_cola | omitidas |
|-----|-----------|----------------|---------|------------|----------|
| 19 | 514 | 6 | 508 | 0 | 0 |
| 21 | 2.968 | 5 | 2.963 | 0 | 0 |
| 22 | 3.284 | 77 | 3.207 | 0 | 0 |
| **Total** | **6.766** | **88** | **6.678** | 0 | 0 |

Cada dry-run confirmó `selection_mode=run`, `backlog=no_consultado`, `del_run_actual`=total. Staging sin encolar runs 19/21/22 → **0**.

**PASO 3 — Publish/drenaje robusto B.1 (tandas de 1.000):**

| tanda | items | nota |
|-------|-------|------|
| 1-4 | +1.000 c/u | limpias, exit 0 |
| 5 | +778 parcial | **murió ~37 min** (timeout sesión Supabase ~30 min). Sin pérdida: commits por fila protegieron las 778. Dejó 1 fila trabada en `publishing` (queue_id=127847). |
| 6 | +1.000 | `--reclaim-minutes 30` **reclamó y procesó** la fila #127847. Limpia. |
| final | +989 | exacto. pending → **0** |

**Métricas finales Track A:**

| Métrica | Inicial | Final |
|---------|---------|-------|
| raw pendientes runs 21/22 | 2.957 | **0** |
| staging sin encolar runs 19/21/22 | 3.809 (→6.766 tras validate) | **0** |
| publish_queue pending | 6.766 | **0** |
| publish_queue done | 86.259 | **93.025** (+6.766) |
| publish_queue failed | 0 | **0** |
| publish_queue publishing | 0 | **0** |
| public.propiedades | 114.016 | **114.104** (+88 inserts reales) |
| error_log critical | 0 | **0** |
| queries largas | 0 | **0** |

**Rechazos validate_raw:** 0 (todos los 2.957 validados). **Inserts reales:** 88 (resto updates por dedup). **Incidentes:** 1 muerte de proceso por timeout de sesión (tanda 5), recuperada automáticamente vía reclaim en tanda 6 — sin pérdida de datos.

**Fuera de alcance (intacto):** Grupo B backlog viejo (1.437 staging) + Grupo C pre-tracking (2.901 staging) = 4.338 staging global sin encolar, no tocado. Candidatas problemáticas (746) no tocadas. Sin scraping, sin batch nuevo, sin frontend, sin Neon, sin push, sin `--include-backlog`.

## 🟡 Auditoría de estrategia — Grupo E vivo (solo lectura, 2026-06-23)

Auditoría HTTP read-only (sitemap.xml + listado) de las 18 vivas del Grupo E, con foco en sitemap (único bucket confiable).

**Resultado (18 auditadas):**
- **0 con `sitemap_usable`** · **0 con `sitemap_debil`**
- 0 `requires_playwright` detectadas por esta auditoría
- 2 con `url_listado_incorrecta`: **611** A Bonapace (listado 403) · **6470** De Fazio (`propiedades.php` 404)
- 1 `dominio_vivo_sin_propiedades`: **76** Rubén Bosco
- **15 en `revision_manual`** (tienen links HTML pero sin sitemap → criterio no confiable)

**Conclusión:** aunque 18 de las 30 del Grupo E están vivas, **ninguna tiene sitemap usable**. Por lo tanto **NO hay mini-lote automático recomendado**.

**Notas operativas:**
- No hacer scraping automático sobre estas 18.
- No usar conteo de links HTML como criterio de batch (refutado en mini-lotes 2 y 3).
- La recuperación por **sitemap fue el único método confiable** hasta ahora.
- Las 15 de revisión manual requieren análisis sitio por sitio.
- Existe una familia de template `propiedades.php?p=0&ope=...` (4551, 4841, 5049, 5180, 5530, 5925, 5942, 4872, 6470), pero **no se recomienda batch** hasta probar manualmente una por una.

**Cierre operativo:** **Grupo E queda auditado. No se recomienda scraping por lote. El próximo trabajo útil es Grupo B (timeout) o revisión manual/Playwright, pero no más recuperación automática por heurística de links.**

**Archivos (read-only):** `_estrategia_grupo_e_vivas.py`, `_estrategia_grupo_e_result.json`.

## 🟡 Liveness re-check Grupo E — caídos/bloqueados (solo lectura, 2026-06-23)

Re-verificación HTTP read-only de las 30 fallidas `site_down_confirmed`/`blocked` (runs 16-42). **No se cambió estado.**

**Resultado (30 chequeadas):**
- **18 vivas (HTTP 200)** → candidatas a auditoría de estrategia.
- 1 viva pero bloquea (403): **1689** Alicia Ciucci.
- 4 DNS caídas reales: **1817, 4625, 4815, 5839**.
- 4 redirects sospechosos: **146, 512, 998** (Century 21 → portal central century21.com.ar), **5150** (Hogg → hogg.ar, rebranding vivo).
- 2 errores 5xx (posible transitorio): **4541** (503), **4907** (500).
- 1 SSL error: **6482**.

**Conclusión:** `site_down_confirmed`/`dominio_caido` tiene **muchos falsos positivos** (23/30 responden). **No usar esa señal para descartar sin liveness previo.** Hallazgo extra: las 3 Century 21 migraron al portal central (explica retroactivamente el site_down de 512/998 en Grupo A).

**Archivos (read-only):** `_liveness_grupo_e.py`, `_liveness_grupo_e_result.json`.

## 🔴 Grupo C — Mini-lote 3 HTML alta evidencia (CERRADO + fin del experimento por bucket, 2026-06-23)

Tercer y último lote: 5 HTML de máxima evidencia (79-302 links). Flujo Opción A.

**Runs creados:** 59–63. pending previo = 0.

**Scraping (`--max-items 5 --workers 3`):** **2 OK / 3 error · error_rate 60%** (criterio ≥2 errores → frenado y reportado; usuario autorizó cerrar solo las 2 exitosas y terminar el experimento).

**Resultado:**
- ✅ 278 Reynares (8 det / +8) · ✅ 137 Del Centro (72 det / +2)
- ❌ 479 Urca — `no_property_links_confirmed` (tenía 159 links audit) · ❌ 78 Carpio — `requires_playwright` · ❌ 255 Cardozo — `no_property_links_confirmed`

**Hallazgo clave:** el conteo de links **NO predice éxito en HTML**. 479 (159 links) falló; las 2 OK detectaron solo 8 y 72 props pese a audit de 302/265. El heurístico sobre-cuenta (navegación/categorías/filtros), no listados reales.

**2 exitosas procesadas (runs 59, 60):**
- validate_raw (ids-file, 80 raw): **80 validadas, 0 rechazadas**.
- build_queue `--run-id` ×2: **80 encoladas** (8+72), sin backlog.
- publish (80 exacto): **80 publicadas, pending→0**.

**Métricas:** OK/err 2/3 · +10 nuevas · public.propiedades 114.510 → **114.520** · done 93.663 → **93.743** · pending/failed/publishing 0/0/0 · critical/queries 0/0.

### 🏁 Cierre del experimento de recuperación Grupo C (por bucket)

**Rendimiento final por estrategia:**
| Estrategia | OK / intentadas | Tasa | Veredicto |
|-----------|----------------:|-----:|-----------|
| **SITEMAP** | 4 / 5 | **80%** | ✅ único confiable |
| **WORDPRESS** | 5 / 11 | 45% | ❌ no confiable |
| **HTML** | 2 / 5 | 40% | ❌ no confiable (links no predicen) |
| **TOTAL** | **11 / 21** | 52% | |

**Recuperadas del Grupo C: 11 agencias · ~+138 propiedades nuevas** (de las 48 originalmente "dominio_caido").

**Conclusiones operativas:**
- **Sitemap.xml es el único predictor confiable** (lista canónica de URLs reales). Links-en-HTML = ruido.
- WordPress y HTML requieren **revisión manual sitio por sitio**, no batch por heurística.
- **No correr más mini-lotes por heurística de links. No hacer batches grandes.**
- El flag `dominio_caido` quedó refutado: de 48, solo 2 caídas reales (DNS); 11 recuperadas; resto requiere Playwright/revisión manual.

**Próximo paso recomendado (sin ejecutar scraping):** consolidar todas las fallidas (Grupo A + Grupo C, runs 16-63) y clasificarlas en Playwright / timeout / no_property_links / sin_propiedades / revisión manual, para decidir tratamiento por tipo.

## 🟠 Grupo C — Mini-lote 2 WordPress (COMPLETADO con gate fallido, 2026-06-23)

Segundo lote de recuperación Grupo C: 6 WordPress de evidencia media-baja (3-14 links). Flujo Opción A (`--inmobiliaria-id`).

**Runs creados:** 53–58. pending previo = 0.

**Scraping (`--max-items 6 --workers 3`):** **2 OK / 4 error · error_rate 66.7%** (gate 20% superado fuerte → frenado y reportado; usuario autorizó cerrar solo las 2 exitosas).

**Resultado:**
- ✅ 202 Moran Villa (54 det / +23) · ✅ 418 Mendez (11 det / 0)
- ❌ 437 Aguerre — `requires_playwright` · ❌ 6314 La Ribera — `sin_propiedades` · ❌ 134 Gutierrez — `no_property_links` · ❌ 181 Ascheri — `item_timeout`

**Patrón clave:** las 4 fallidas eran las de **menor evidencia** (3-7 links); las 2 OK tenían 8 y 14. El heurístico "N links HTML" para WordPress **no es confiable por debajo de ~8 links**.

**2 exitosas procesadas (runs 53, 54):**
- validate_raw (ids-file, 54 raw): **54 validadas, 0 rechazadas**.
- build_queue `--run-id` ×2: **56 encoladas**, ya_en_cola=0, sin backlog.
- publish (56 exacto): **56 publicadas, pending→0**.

**Métricas finales:**
| Métrica | Valor |
|---|---|
| OK / error | 2 / 4 (error_rate 66.7%) |
| propiedades nuevas | +23 |
| raw validadas | 54 (0 rechazadas) |
| staging encoladas | 56 |
| publicadas | 56 (todas updates) |
| public.propiedades | 114.487 → **114.510** (+23) |
| publish_queue done | 93.607 → **93.663** |
| pending / failed / publishing | 0 / 0 / 0 |
| error_log critical / queries largas | 0 / 0 |

**WordPress acumulado (lotes 1+2): 5/11 OK (45%).** SITEMAP acumulado: 4/5 OK (80%).

**Conclusión / regla nueva:** WordPress de baja evidencia NO es confiable. **Umbral sugerido: no reintentar WordPress con < 8 links sin revisión manual previa.** Tratamiento de las 4 fallidas: 437 → pool Playwright; 6314 → sin_propiedades/revisión manual; 134 → revisar patrón/listado; 181 → posible reintento futuro con más timeout.

## 🟢 Grupo C — Mini-lote 1 recuperación (COMPLETADO, 2026-06-22)

Primer test de recuperación de las 46 vivas del Grupo C (flag `dominio_caido` desactualizado). Mini-lote de 10 con mejor evidencia (5 sitemap + 5 wordpress), flujo Opción A (`--inmobiliaria-id`, sin código nuevo, sin corregir DB — el scraper auto-detecta estrategia).

**Confirmación técnica:** `estrategia_scraping` es valor **derivado en la vista**, no almacenado (base = None); `scraping_run_items` no lleva esa columna; el scraper auto-detecta vía `run_best_strategy`. **No hizo falta corregir DB.**

**Runs creados:** 43–52 (1 inmobiliaria c/u). pending previo = 0.

**Scraping (`--max-items 10 --workers 3`):** 7 OK / 3 error · error_rate 30% (gate 15% superado → frenado y reportado; usuario autorizó seguir con las 7).

**Resultado por estrategia:**
- **SITEMAP 4/5 OK:** 195 Berasueta (36 det), 238 Barroso (45/+31), 232 Wilneder (45/+38), 313 N. Pereyra (6/+6). Falló 266 RE/MAX (sitemap débil 4 URLs → era SPA → requires_playwright).
- **WORDPRESS 3/5 OK:** 398 Casabonne (29/+28), 261 Los Andes (13/+2), 203 Del Rio (15). Fallaron 188 Arksa (timeout) y 285 Peirano (no_property_links).

**Las 3 fallidas (NO reprocesadas — registradas):**
| run | inmo | error_type | tratamiento futuro |
|-----|------|-----------|--------------------|
| 47 | 266 RE/MAX Andrés | requires_playwright | no reintentar con requests; pasa a pool Playwright |
| 49 | 188 Arksa | timeout | posible reintento futuro con más margen de timeout |
| 50 | 285 Peirano | no_property_links | revisar patrón/listado (heurística decía 69 links) |

**7 exitosas procesadas (runs 43,44,45,46,48,51,52):**
- validate_raw (ids-file, 120 raw): **120 validadas, 0 rechazadas**.
- build_queue `--run-id` ×7 (dry+commit, sin backlog): **148 encoladas**, ya_en_cola=0.
- publish (148 exacto): **148 publicadas, pending→0**.

**Métricas finales:**
| Métrica | Valor |
|---|---|
| OK / error | **7 / 3** (error_rate 30%) |
| propiedades detectadas | ~189 |
| **propiedades nuevas** | **+105** |
| raw validadas | 120 (0 rechazadas) |
| staging encoladas | 148 |
| publicadas | 148 (todas updates; las 105 nuevas ya entraron vía scraper) |
| public.propiedades | 114.382 → **114.487** (+105) |
| publish_queue done | 93.459 → **93.607** |
| pending / failed / publishing | **0 / 0 / 0** |
| error_log critical | **0** |
| queries largas | **0** |

**Conclusión:** El **sitemap funciona muy bien (4/5)**; wordpress decente (3/5). El flag `dominio_caido` confirmado como falso positivo: 7 de 10 agencias "caídas" produjeron datos reales. **Recomendación:** seguir con el resto de las recuperables en lotes chicos, priorizando sitemap; revisar caso a caso los no_property_links/timeout antes de reintentar.

## 🟡 Auditoría de estrategia — Grupo C vivo (solo lectura, 2026-06-22)

Auditoría HTTP read-only (sitemap.xml + links de propiedad en listado + marcadores SPA/JS) de las 46 vivas. **No se cambió estrategia ni estado.**

**Resultado (46 auditadas):**
- **33 recuperables fáciles futuras:** 17 `html` · 11 `wordpress_generic_detail` · 5 `sitemap`
- 9 `dominio_vivo_sin_propiedades` / revisión manual
- 3 `requires_playwright` (102, 193, 221; las 2 primeras tienen sitemap mínimo → probar sitemap antes)
- 1 `url_listado_incorrecta` (127 Iaco → listado 404)
- 0 sin estrategia clara

**Evidencia destacada (sitemap/html ricos):** 195 (sitemap 381 URLs), 278 (302 links), 137 (265), 398 (255), 479 (159), 188 (121), 238 (89), 232 (85).

**Conclusión:** el flag `dominio_caido` estaba desactualizado. De las 48 originales, solo **2 realmente caídas** (DNS) y **33 con estrategia probable de recuperación**. Confirma que liveness + auditoría de estrategia read-only es el paso correcto antes de descartar agencias.

**Caveat:** heurística HTTP — la estrategia es *probable*, no garantizada; requiere test de scraping controlado para confirmar.

**Archivos (read-only):** `_estrategia_grupo_c_vivas.py`, `_estrategia_grupo_c_result.json`.

## 🟡 Liveness check Grupo C — dominio_caido (solo lectura, 2026-06-22)

Chequeo HTTP read-only (HEAD/GET, timeout 8s, follow redirects) de las 48 inmobiliarias Grupo C marcadas `estrategia_scraping='dominio_caido'`. **No se cambió ningún estado.**

**Resultado:**
- 48 chequeadas · **46 vivas (HTTP 200)** · **2 caídas confirmadas (DNS)** · 0 bloqueadas · 0 redirects sospechosos/parking · 0 timeout · 0 SSL error · 0 404 · 0 5xx · 0 dudosas.

**Las 2 caídas confirmadas (DNS no resuelve) — candidatas a dominio caído, NO marcar sin autorización:**
- 183 — Belpasso Construcciones — belpasso.com.ar
- 259 — Inmobiliaria Galotto — galotto.com.ar

**Conclusión:** el flag `dominio_caido` está **mayormente desactualizado (46/48 = 96% falsos positivos)**. **No marcar inactiva ninguna inmobiliaria solo por ese flag sin liveness check previo.**

**Seguimiento:**
- Las **46 vivas** pasan conceptualmente a **auditoría de estrategia** (no van directo a Grupo A: "viva 200" = dominio responde, no que sea scrapeable).
- **7 requieren verificar URL de listado** por redirect/cambio de dominio: 261, 283, 313, 357, 398, 418, 6314.
- 2 DNS (183, 259) quedan como candidatas a dominio caído, pendientes de autorización para marcar.

**Archivos (read-only):** `_liveness_grupo_c.py`, `_liveness_grupo_c_result.json`.

## 🟢 Grupo A — Recuperables fáciles (COMPLETADO, 2026-06-22)

Rama: `feat/fase-b1-publish-robustez`. **Push: no realizado.** Primer ataque controlado al pool de 746 candidatas, solo Grupo A (20 con estrategia scrapeable). Opción A: 20 runs de 1 inmobiliaria c/u (`--inmobiliaria-id`, sin código nuevo, sin mezcla).

**Runs creados:** 23–42 (run_id por inmobiliaria). pending previo = 0 → sin mezcla.

**Scraping (`--max-items 20 --workers 3`):** 14 OK / 6 error · error_rate 30% · 20 runs `finished` · 489 raw. Gate error≤10% superado → se frenó y reportó; usuario autorizó continuar solo con las 14 exitosas.

**Las 6 fallidas (NO reprocesadas — registradas como errores Grupo A):**

| run | inmo | error_type | tratamiento futuro |
|-----|------|-----------|--------------------|
| 25 | 512 C21 El Yar | site_down_confirmed | candidato a dominio caído |
| 41 | 998 C21 Iribarren | site_down_confirmed | candidato a dominio caído |
| 28 | 611 A Bonapace | blocked | revisar luego |
| 29 | 628 Moreno | strategy_quality_failed | requiere ajuste de estrategia |
| 35 | 884 Prol | item_timeout | reintento futuro |
| 36 | 898 Ramirez | sin_propiedades | clasificar sin_propiedades si se confirma |

**14 exitosas procesadas (runs 23,24,26,27,30,31,32,33,34,37,38,39,40,42):**
- validate_raw (ids-file scoped, 331 raw): **331 validadas, 0 rechazadas, 0 duplicadas**. Solo warnings no-bloqueantes.
- build_queue `--run-id` ×14 (dry-run+commit, sin backlog): **434 encoladas**, ya_en_cola=0, omitidas=0.
- publish B.1 (434 exacto): **434 publicadas, pending→0, failed=0, publishing=0**.

**Métricas finales Grupo A:**

| Métrica | Valor |
|---|---|
| Inmobiliarias intentadas | 20 |
| OK / error | **14 / 6** (error_rate 30%) |
| Propiedades scrapeadas (detectadas) | 489 |
| Propiedades nuevas (scraper→public) | **+278** |
| raw validadas | 331 (0 rechazadas) |
| staging encoladas | 434 |
| publicadas | 434 |
| inserts en publish | 0 (las 278 nuevas ya entraron vía scraper) |
| updates en publish | 434 |
| public.propiedades | 114.104 → **114.382** (+278) |
| publish_queue done | 93.025 → **93.459** |
| pending / failed / publishing final | **0 / 0 / 0** |
| error_log critical | **0** |
| queries largas | **0** |

**Volumen destacado:** Bahía Blanca +145 · Florencio Gonzalez +35 · Perata +32 · Areco Campos +24 · Bessa +18.

**Restricciones respetadas:** sin `--include-backlog` · sin tocar Grupo C/D/E · sin Playwright · sin reprocesar las 6 fallidas · sin frontend · sin Neon · sin push · sin modificar código · sin scripts auxiliares.

**Próximo paso sugerido (requiere autorización):** evaluar Grupo C (48 dominio caído) con liveness check read-only — los 2 site_down de este batch (512, 998) refuerzan que el flag dominio_caido puede estar mezclado con sitios vivos.

## 🟡 Informe candidatas problemáticas — solo lectura (2026-06-22)

Análisis read-only de las 746 candidatas `lista_para_batch=false`. **No se ejecutó ninguna acción.**

**Hallazgo estructural clave — dos pools casi disjuntos:**
- **Pool 1 — 746 candidatas** (`v_next_scraping_batch`): el pool del "próximo batch". **741 nunca fueron intentadas** en el loop; solo **5 solapan** con errores de runs 16-22 (todas `nav_error`).
- **Pool 2 — 1.250 intentadas en runs 16-22** (1.023 OK + 227 error). **Los 55 `requires_playwright` y los 25 `site_down_confirmed` están acá, NO en las 746** (0 solapamiento verificado).

**Clasificación de las 746 (suma validada = 746):**

| Grupo | Cant | Detalle |
|-------|------|---------|
| A — Recuperables fáciles | **20** | sitemap 12 + html 7 + wordpress_generic_detail 1. Todas con web+url_listado, **antibot 0**. Riesgo BAJO. |
| B — Requieren Playwright | **0** | (dentro de las 746; los 55 reales están en Pool 2) |
| C — Dominio caído | **48** | flag de análisis previo; **0 confirmados site_down en runs 16-22** (flag posiblemente obsoleto) |
| D — Sin estrategia | **668** | custom 527 + wordpress 135 + otros. El grueso (90%). Requiere auditoría por dominio. |
| E — Fuentes prohibidas | **10** | argenprop 6 + zonaprop 4. Omitir permanentemente. |
| F — Dudosas | **0** | todas clasificaron limpio |

**Datos generales 746:** todas con web (746/746) y url_listado (746/746); **antibot 0/746**. CMS: custom 574, wordpress 155, resto menor. Provincias top: Buenos Aires 292, Córdoba 78, Entre Ríos 42.

**Error pool runs 16-22 (227 errores):** por run 16=2/17=6/18=5/19=12/20=20/21=72/22=110. Por tipo: requires_playwright 55, sin_propiedades 39, timeout 26, site_down_confirmed 25, skipped_invalid_source 20, no_property_links(+confirmed) 26, item_timeout 14, strategy_quality_failed 8, nav_error 5, otros 8. Clasificación: ~47 reintentables, ~100 no-reintentar, ~80 cambio de scraper.

**Recomendación:** empezar por **Grupo A (20)** con flujo controlado tipo Track A (scraping→validate→build_queue --run-id→publish), gates error≤10%. **NO volver a Batch 300 general** (gate ROJO). Grupo C requiere liveness check antes de marcar inactivas; Playwright requiere piloto 5→10→25; Grupo D requiere auditoría por dominio. **Fuera de alcance hasta autorización: C, D, E, Playwright.**

**Archivos de análisis (read-only):** `_informe_candidatas.py`, `_cand_crossref.py`, `_cand_pw_location.py`, `_grupo_a_lista.py`.

## 🟢 Fase A — Higiene y drenaje (COMPLETADA, 2026-06-17)

Rama: `chore/fase-a-eretz-higiene` (sin push).

**Drenaje publish_queue:**
- `pending final = 0` · `done final = 22.707` · `failed = 0` · `omitted = 0` · `publishing = 0`.
- `public.propiedades`: 97.181 → 97.214 (33 inserts nuevos + 2.717 updates).
- Drenaje limpio (canary 250 + 3×1.000), sin errores transitorios.

**Higiene aplicada:**
- `.env.example` actualizado con placeholders (`INTERNAL_DB_SCHEMA`, `NEON_DB_URL_BACKUP`, `SUPABASE_DATABASE_URL`), sin secrets.
- Scripts Zonaprop/Argenprop **congelados** (guard que aborta): `scrape_zonaprop_agencias.py`, `scraper_zonaprop_inmobiliarias.py`, `import_zonaprop_to_staging.py`.
- 7 scripts sueltos `_*.py` movidos a `scripts/_scratch/`.
- Naming docs InmoCapital → ERETZ Propiedades (27 archivos, 88 reemplazos, links e identificadores técnicos preservados).

No se ejecutó scraping nacional · no se tocó frontend · no se tocó Neon · no se hizo push.

## 🟢 Fase A-bis — Logging mínimo obligatorio (COMPLETADA y validada, 2026-06-17)

- **DDL aplicado en Supabase:** `internal_scraping.error_log` + 2 vistas de resumen (`v_error_summary_by_run`, `v_error_summary_by_inmobiliaria`) + 7 índices.
- **Helper nuevo:** `scraper/error_logger.py`.
- **Integración mínima:** `scripts/publish_to_supabase.py` (errores `failed` → JSONL + tabla).
- **Tests:** `tests/test_error_logger_redaction.py` — **7/7 PASS**.
- JSONL se escribe **primero**; tabla **después como best-effort**.
- Logger usa **conexión efímera autocommit propia** (no la transacción del publish).
- Si la DB falla, el logger **no rompe** el proceso.
- **Redacción de secrets validada:** passwords falsos=0, JWT falsos=0, Bearer token=0, `<redacted>` presente.
- `publish --dry-run` sigue funcionando.
- **NO** se creó `drain_publish_queue.py`.
- **NO** se tocó: scraper monolítico, `validate_raw`, `geocode`, `build_queue`, `run_daily_pipeline`, frontend, Neon, `.env`.

### Decisión técnica
El logging mínimo queda activo **solo en `publish_to_supabase`** para errores `failed` (JSONL + tabla). La integración del logging en scraping/validate/geocode/build_queue/orchestrator queda para **Fase B o posteriores**.

### Estado actual antes de Fase B
- Cola de publicación vacía · producción estable · logging mínimo persistente disponible.
- Errores de publish ya **no quedan invisibles** · secretos protegidos por redacción.
- Neon sigue como backup congelado · frontend sin tocar · sin push.

### Próximo paso recomendado
**No avanzar todavía con campaña nacional.** Próxima decisión: elegir Fase B. Opciones:
1. Robustez de `publish_to_supabase`.
2. Optimización `validate_raw_properties.py` a bulk.
3. Presupuestos/checkpoints por inmobiliaria.
4. Incremental diario.

**Recomendación preliminar:** primero robustez de publish, después `validate_raw` bulk, antes de volver a scrapear a escala.

## 🟢 Fase B.1 — Robustez de `publish_to_supabase` (aplicada y validada en local, 2026-06-17)

Estado: **aplicada y validada en local.** Rama: `feat/fase-b1-publish-robustez`. **Push: no realizado.**

Ver: [[Plan Fase B1 robustez publish 2026-06-17]]

**Cambios principales:**
- Modelo B robusto aplicado: **claim atómico por fila** + **commit por fila**.
- **Retry seguro** para errores transitorios con **backoff exponencial + jitter**.
- **`reclaim_stale_publishing`** (preflight; incrementa `attempts`, respeta tope).
- Logging de retries, recuperaciones, failed y reclaim vía `error_logger.py`.
- **`queue_id`** agregado a `internal_scraping.error_log` (DDL idempotente).
- Mantiene dedup/upsert por `url_normalizada`.
- Dry-run sigue siendo **solo lectura**; **reclaim NO se ejecuta en dry-run**.
- Validación de staging fallida → `failed` (no deja filas trabadas en `publishing`).

**Archivos:** `scripts/publish_to_supabase.py`, `scraper/error_logger.py`,
`migrations/phase_b1_error_log_queue_id.sql`, `tests/test_publish_robustez.py`.

**Validaciones:**
- `test_publish_robustez.py`: **10/10 PASS** · `test_error_logger_redaction.py`: **7/7 PASS**.
- `py_compile`: OK · `publish --dry-run`: exit 0 · `retry_attempts=0` en resumen dry-run.
- `publishing` sin modificar en dry-run: 0 → 0 · **no** se ejecutó prueba real `--commit`.

**Restricciones respetadas:** no push · no frontend · no Neon · no scraper monolítico ·
no `validate_raw` · no geocode · no build_queue · no run_daily_pipeline · no scraping
nacional · sin cambiar reglas de negocio ni dedup por `url_normalizada` · incompletos
no se convierten en rechazo · sin imprimir secrets.

### Pendiente — prueba real chica (requiere autorización)
Como `publish_queue.pending = 0`, NO se hizo prueba real. Cuando haya pending reales
por un enqueue controlado, ejecutar (pedir autorización antes):
```bash
python scripts/publish_to_supabase.py --limit 10 --max-supabase-writes 10 --commit
```
Validar después: `failed=0` · `publishing=0` · `pending` baja · `public.propiedades`
consistente · `error_log` sin entradas inesperadas · si hubo retry, que quede registrado.

### Próximo paso recomendado
No avanzar aún con campaña nacional. Siguiente decisión técnica posible:
1. prueba real chica de publish cuando haya pending;
2. luego **Fase B.2: `validate_raw_properties.py` bulk**;
3. después presupuestos/checkpoints por inmobiliaria.

## 🟢 Ajuste de `build_queue` — aplicado y validado localmente (2026-06-18)

Estado: **aplicado en local, sin tocar Supabase.** Rama: `feat/fase-b1-publish-robustez`. **Push: no realizado.**

- **Archivo modificado:** `scripts/build_publish_queue.py`
- **Test nuevo:** `tests/test_build_queue_run_scope.py`
- **Tests: 9/9 PASS** · `py_compile`: OK

**Cambios principales:**
- **Default nuevo seguro:** encola solo el último run `finished`.
- `--run-id N`: permite encolar un run específico.
- `--include-backlog`: necesario explícitamente para encolar backlog histórico (con advertencia fuerte).
- `--show-backlog-count`: opcional; evita el `COUNT` por defecto en dry-run.
- Dry-run no consulta backlog total salvo que se pida explícitamente (`backlog_total_staging=no_consultado`).
- `run_daily_pipeline` compatible: llama `build_queue` sin `--run-id` → ahora toma el último run `finished` (no se tocó run_daily_pipeline).
- **Reglas de negocio intactas:** incompletos siguen publicándose; no se rechaza por título/fotos/ciudad/provincia/coordenadas/precio; `classify_row`/`queue_skip_reason`/`compute_priority` sin cambios.

**Restricciones respetadas:** no se tocó Supabase · sin queries a DB · sin dry-run real · sin reset de pending · sin publish · sin otro batch · sin frontend · sin Neon · sin push · sin cambio de reglas de negocio.

**Problema que resuelve:** el Batch 100 run_id=14 encoló backlog completo (~49k pending). Con este ajuste, un batch futuro encola solo lo del run actual, salvo `--include-backlog`.

### Próximo orden acordado (post Disk I/O)
1. Esperar recuperación de Disk I/O en Supabase.
2. Verificar con consulta liviana si existe índice `public.propiedades(url_normalizada)`.
3. Crear índice `CONCURRENTLY` solo si falta y cuando el I/O esté recuperado.
4. Resetear pending redundantes en chunks chicos.
5. Probar `build_queue` corregido con `--dry-run --run-id`.
6. Recién después correr otro batch.

## 🟢 Reset de pending redundantes — COMPLETADO (2026-06-18)

Limpieza de la cola que el Batch 100 (run_id=14) había inflado con backlog. Hecho en
chunks chicos con verificación por chunk, sin saturar Disk I/O (índice
`public.propiedades(url_normalizada)` ya creado).

**Resultado final:**
- **pending final: 6.586** · **redundantes seguras restantes: 0** · **altas nuevas reales: 6.586**
- failed: **0** · publishing: **0**
- `public.propiedades`: **98.220, sin cambios**
- `error_log`: **11 registros** `drain/reset_redundant` (1 resumen por chunk, no por fila)
- queries largas activas: **0**
- **total reseteado: 42.653 redundantes seguras** (canary 500 + 2×2.000 + 8×5.000 + 1 parcial 3.153)

**Clasificación usada:** misma `inmobiliaria_id` + misma `url_normalizada` (NO solo url —
ERETZ preserva duplicados entre inmobiliarias). Acción: `publish_queue.status='done'` +
`error_message='skipped_redundant_url_in_public'` + `last_attempt_at=now()`; staging
`queued→published` solo si estaba `queued`.

**No se borró nada · no se tocó `public.propiedades` · no se corrió publish · no se corrió
scraping · no se hizo push.**

➡️ La cola quedó **limpia y lista para publicar solamente las 5.986 altas nuevas reales.**

## 🟢 Publicación de altas nuevas — COMPLETADA (2026-06-18)

Drenaje controlado de las 5.986 altas nuevas reales con `publish_to_supabase` robusto B.1.

**Métricas finales:**
| Métrica | Valor |
|---|---|
| pending inicial | 5.986 |
| pending final | **0** |
| done | 66.721 → **72.707** |
| failed | **0** |
| publishing al cerrar | **0** |
| public.propiedades | 98.793 → **104.706** |
| delta public.propiedades | **+5.913** |
| total procesadas/publicadas OK | **5.986** |
| diferencia (~73 ya existían) | updates por dedup normal (misma url_normalizada) |
| omitidas | **0** |
| retries en cierre | **0** |
| error_log critical | **0** |
| queries largas | **0** |
| saturación I/O | **no** |

**Tandas ejecutadas:**
1. Canary 100 → limpio
2. Tanda 500 → limpio
3. Tanda 1.000 × 4 → limpio
4. Cierre final 1.000 + 986 → limpio · pending=0

**Restricciones respetadas:** frontend no tocado · Neon no tocado · scraping no corrido ·
batch nuevo no corrido · push no realizado · sin critical en error_log · sin queries largas.

**Resultado:** La cola `publish_queue` quedó completamente drenada y las 5.986 altas nuevas
reales quedaron publicadas en `public.propiedades` (total: 104.706 propiedades).

## 🟡 Verificación post-drenaje + build_queue dry-run — OK con 183 staging legítimas pendientes (2026-06-18)

**Estado de la cola al verificar:**
| Métrica | Valor |
|---|---|
| publish_queue pending | **0** |
| publish_queue failed | **0** |
| publish_queue publishing | **0** |
| publish_queue done | **72.707** |
| public.propiedades | **104.706** |
| error_log critical (24h) | **0** |
| queries largas activas | **0** |
| DB / I/O | OK, sin saturación |

**build_queue dry-run — resultado:**
- Usó último run terminado: `run_id=14` (correcto).
- No consultó backlog viejo: `backlog_total_staging=no_consultado`.
- No usó `--include-backlog`.
- Detectó **183 filas de `run_id=14`** con `status='staging'` nunca encoladas.
  - `inmobiliaria_id=1155` (barrerapropiedades.com).
  - Score 65–80, operación venta, geocoding skipped.
  - No son backlog viejo. No son error del script.
  - Nunca pasaron por `publish_queue` (ya_en_cola=0).
  - 11.319 filas del mismo run ya están `published`. Solo estas 183 quedaron.
- **El fix de `build_queue` funciona correctamente.**

**Próximo paso:** mini-ciclo controlado — encolar las 183 con `--run-id 14 --commit`,
luego publicar con `publish_to_supabase --limit 183 --commit`.

## 🟢 Mini-ciclo 183 run_id=14 — COMPLETADO (2026-06-18)

**Origen:** `run_id=14` · `inmobiliaria_id=1155` (barrerapropiedades.com)

**Contexto:** `build_queue` dry-run detectó 183 staging con `status='staging'` que nunca
habían sido encoladas. No eran backlog viejo. No se usó `--include-backlog`.

**Encolado:**
```bash
python scripts/build_publish_queue.py --run-id 14 --limit 183 --commit
```
| Métrica | Valor |
|---|---|
| pending | 0 → 183 |
| done | 72.707 (sin cambio) |
| public.propiedades | 104.706 (sin cambio) |
| failed | 0 |
| publishing | 0 |

**Publicación:**
```bash
python scripts/publish_to_supabase.py --limit 183 --max-supabase-writes 183 --commit --reclaim-minutes 30
```
| Métrica | Valor |
|---|---|
| publicadas OK | **183** |
| failed | **0** |
| omitidas | **0** |
| retries | **0** |
| publishing al cerrar | **0** |
| error_log critical | **0** |
| queries largas | **0** |
| tiempo | ~10 min |

**Estado final:**
| Métrica | Valor |
|---|---|
| publish_queue pending | **0** |
| publish_queue done | **72.890** |
| publish_queue failed | **0** |
| publish_queue publishing | **0** |
| public.propiedades | **104.706** |

**Nota:** `public.propiedades` no subió porque las 183 filas ya existían en Supabase.
Fueron updates/upserts por `url_normalizada` (`Deduplicacion existente: url_normalizada=1`
en cada fila). Los datos de barrerapropiedades.com ya estaban publicados de antes.

**Validaciones:**
- `build_queue` corregido validado en producción (run_id=14, sin backlog).
- Cola completamente drenada.
- No queda ningún staging de `run_id=14` sin publicar.
- Sin push · sin frontend · sin Neon · sin scraping · sin nuevo batch.

## 🟢 Batch 25 controlado — commit 7 validado (2026-06-19)

**Rama:** `feat/fase-b1-publish-robustez` · **run_id=15** · **Push: no realizado.**

**Objetivo:** validar en producción los cambios del commit 7 (`scraper/models.py`, `scraper/scraper_propiedades.py`, `scraper/geocoder.py`) — normalización de `operacion` y `estado`, fallback `consultar`, detección `venta_y_alquiler`, valores `activa` / `no_detectada_en_ultimo_scraping`.

**Pipeline ejecutado:**

| Fase | Resultado |
|---|---|
| FASE 0 — Preflight | supabase=ok · neon=ok |
| FASE 1 — Create run | run_id=15 · 25 items insertados |
| FASE 2 — Scraping | **21/25 OK · 4 error** · 4.113 props scrapeadas |
| FASE 3 — Validate raw | 422 raw → 422 staged · **0 rechazadas** |
| FASE 3.5 — Geocode | 3 iteraciones · done=72 / failed=68 / skipped=159 |
| FASE 4 — Build queue | 2 iteraciones · **524 encoladas** (run_latest=15 solo) |
| FASE 5 — Publish inicial | 5 × 100 = **500 publicadas** · failed=0 · retries=0 |
| Cierre final (24 pending) | **24/24 publicadas** · failed=0 · retries=0 |

**Métricas finales:**

| Métrica | Valor |
|---|---|
| Inmobiliarias intentadas | 25 |
| Inmobiliarias OK / error | 21 / 4 |
| Props scrapeadas | 4.113 |
| Props nuevas en staging | 421 |
| Props publicadas total | **524** (500 + 24 cierre) |
| failed | **0** |
| pending final | **0** |
| publishing | **0** |
| publish_queue done | **73.414** |
| public.propiedades | **105.082** (antes: 104.706, delta+376) |
| error_log critical | **0** |
| queries largas | **0** |
| publishing stuck | **0** |
| 0 Zonaprop/Argenprop | ✅ |
| 0 backlog viejo reencolado | ✅ |

**Validación commit 7 — operacion:**

| operacion | staging run_id=15 | delta en public.propiedades |
|---|---|---|
| `venta` | 3.823 | +174 |
| `consultar` | 267 | **+159 ✅** |
| `alquiler` | 257 | +33 |
| `venta_y_alquiler` | 6 | **+10 ✅** |

**Validación commit 7 — estado:**

| estado | antes | después | delta |
|---|---|---|---|
| `activa` | 103.933 | 104.317 | **+384 ✅** |
| `no_detectada_en_ultimo_scraping` | 72 | 72 | 0 (correcto) |
| `desconocida` | 701 | 693 | -8 (reclasificadas a activa) |

**Gates verificados:**
- `build_queue` usó solo `run_latest run_id=15` (no backlog viejo). ✅
- Publish robusto B.1: claim atómico, retry_attempts=0, sin filas trabadas. ✅
- Incompletas no bloqueadas: 0 rechazadas con min_score=0. ✅
- Duplicados por inmobiliaria preservados (warnings, no errors). ✅
- `venta_y_alquiler` detectado como issue de validación (4 props) — no como rechazo. ✅

**Nota sobre error_rate 16% (4/25):** esperado para pool `lista_para_batch=false` (lower-priority agencies). Los 4 errors son HTTP/timeout en sitios de menor prioridad, no provienen del código nuevo.

**Restricciones respetadas:** sin push · sin Neon · sin frontend · sin Zonaprop/Argenprop · sin backlog · sin nuevo batch autorizado.

## 🔴→⭕ Loop autónomo nacional — cerrado por gate ROJO (2026-06-20)

Rama: `feat/fase-b1-publish-robustez`. **Push: no realizado.**

Deadline configurado: domingo 2026-06-22 09:00 ART (12:00 UTC).
Detenido automáticamente: 2026-06-20 ~16:00 UTC. Motivo: gate ROJO — run_id=22 con 36.7% error rate (umbral 30%).

**Batches ejecutados:**

| run_id | batch | exitosas | errores | err% | nuevas | gate |
|--------|-------|----------|---------|------|--------|------|
| 16 | 50 | 48 | 2 | 4% | 657 | 🟢 |
| 17 | 100 | 94 | 6 | 6% | 955 | 🟢 |
| 18 | 100 | 95 | 5 | 5% | 458 | 🟢 |
| 19 | 200 | 188 | 12 | 6% | 1.408 | 🟢 |
| 20 | 200 | 180 | 20 | 10% | 1.048 | 🟢 |
| 21 | 300 | 228 | 72 | 24% | 2.738 | 🟡 |
| 22 | 300 | 190 | 110 | 37% | 1.598 | 🔴 STOP |
| **Total** | **1.250** | **1.023** | **227** | **18%** | **+8.862** | |

**Métricas finales:**

| Métrica | Valor |
|---------|-------|
| `public.propiedades` antes | 105.082 |
| `public.propiedades` después | **113.944** |
| Delta | **+8.862** |
| `publish_queue done` | 73.414 → 76.238 |
| `publish_queue pending` al cerrar | ~10.021 |
| `critical errors` (todos los runs) | **0** |
| Candidatas restantes | **741** |

**Errores clasificados (227 total):**

| tipo | cant | % | observación |
|------|------|---|-------------|
| `requires_playwright` | 55 | 24% | necesitan browser JS — no funciona con requests |
| `sin_propiedades` | 39 | 17% | sitio vacío o cambió estructura |
| `timeout` + `item_timeout` | 40 | 18% | sitios lentos, timeout de scrapers |
| `site_down_confirmed` | 25 | 11% | dominio caído |
| `skipped_invalid_source` | 20 | 9% | filtrado como fuente inválida |
| `no_property_links` (ambas variantes) | 26 | 11% | no se encontraron links de props |
| `strategy_quality_failed` | 8 | 4% | estrategia no superó umbral de calidad |
| otros (`nav_error`, `mismatch`, etc.) | 14 | 6% | varios |

**Por qué escaló el error rate:**
- Runs 16-20: inmobiliarias con estrategia de scraping definida → 4-10% error.
- Run 21: primer batch con agencias problemáticas mezcladas → 24% (🟡 AMARILLO).
- Run 22: mayoría sin estrategia → 37% (🔴 ROJO). `requires_playwright` saltó de 17 a 36.

**Análisis de las 741 candidatas restantes:**
- `lista_para_batch=False` en **TODAS las 741**.
- `prioridad_scraping=media_revisar` en **TODAS**.
- `recomendacion="Revisar manualmente."` en **TODAS**.
- 638/741 (86%): `necesidades_detectadas=[falta_estrategia_scraping]`.
- 49: `estrategia_scraping=dominio_caido`.
- 34: `estrategia_scraping=sin_estrategia`.
- Solo 19 con estrategia válida (sitemap: 12, html: 7).
- CMS: custom 569, wordpress 155, argenprop 6 (skip), zonaprop 4 (skip).
- **Conclusión: NO conviene correr otro batch con este pool sin definir estrategias primero.**

**Drenaje publish_queue (10.021 pending al cerrar) — COMPLETADO 2026-06-21 ✅**

| Métrica | Valor |
|---------|-------|
| pending inicial | ~10.021 |
| pending final | **0** |
| publish_queue done final | **86.259** |
| failed | **0** |
| publishing al cerrar | **0** |
| error_log critical | **0** |
| queries largas | **0** |
| public.propiedades antes | 113.944 |
| public.propiedades después | **114.016** |
| delta (nuevos inserts reales) | **+72** |

Tandas ejecutadas (sesión autorizada):
- T1–T4 (sesión anterior): +5.730 items
- T5: +1.000 · exit 0 · gates OK
- T6: +1.000 · exit 0 · gates OK
- T7: +1.000 · exit 0 · gates OK
- T8: +1.000 · exit 0 · gates OK
- T_final: +291 exactos · exit 0 · gates OK · pending=0

Todas las propiedades procesadas mostraron `Deduplicacion existente: url_normalizada=1` (updates de existentes) salvo +72 inserts genuinamente nuevos.

**Archivos de auditoría:**
- `_loop_state.json` — estado completo del loop (runs 16-22, gates, candidatas).
- `_batch_error_log.md` — errores detallados de cada run con tablas y clasificación.
- `_capture_batch_errors.py` — script de captura (usado 7 veces, una por run).

**Restricciones respetadas:** sin push · sin Neon · sin frontend · sin Zonaprop/Argenprop scraped · sin `--include-backlog` · sin nuevo batch tras gate ROJO · sin secrets impresos · sin modificar código.

**Próximas decisiones (NO ejecutar sin autorización):**
- [x] Terminar de drenar `publish_queue` pending con tandas de 1.000 (`--limit 1000 --commit`). ✅ 2026-06-21 — pending=0, done=86.259.
- [ ] **NO** correr más batches con las 741 restantes sin definir estrategias.
- [ ] Opción A: Definir estrategia genérica para las ~155 WordPress (potencialmente scrapeable).
- [ ] Opción B: Marcar las 49 `dominio_caido` como inactivas en la tabla de inmobiliarias.
- [ ] Opción C: Evaluar si los 55 `requires_playwright` ameritan implementar Playwright.
- [ ] Opción D: Crear `estado_inmobiliaria` para clasificar: exitosa / vacía / timeout / parser_error / requires_playwright / antibot / dominio_caido.

---

## 🔴 Foco vigente 2026-06-16 — post Batch 100

Ver: [[Batch 100 post-cutover 2026-06-16]], [[Cutover Supabase internal_scraping 2026-06-16]]

- [x] Cutover a Supabase `internal_scraping` (pipeline ya NO usa Neon; Neon = backup congelado). ✅
- [x] Drenaje backlog 950 pending → 0, cola limpia, 950 publicadas. ✅
- [x] Batch 100 commit (run_id=13): 89/100 OK, error_rate 11%, 10,527 detectadas, 1,758 nuevas a public.propiedades (96,768). ✅ scraper
- [x] **Recovery pipeline interno run 13** ✅ 2026-06-17: 1,823 raw validadas (0 rejected tras fix missing_title), geocode +392 done, 10,000 encoladas, 1,000 publicadas (tope recovery). Ver [[Recovery Batch 100 run13 2026-06-17]].
- [x] **Fix `missing_title` no-bloqueante** ✅ en validate_raw_properties.py (fallback `{Tipo} en {ciudad}`...). 4 props recuperadas.
- [ ] **Drenar 9,000 pending** restantes en publish_queue por tandas (backlog publicable, no bloquea).
- [ ] **⚠️ Decidir mejora del orquestador (timeout)**: que run_daily_pipeline continúe fases 3-5 si la run quedó `finished` aunque el scraper reporte timeout tarde (solución de raíz). Alternativas: subir `--step-timeout` a ~4h o usar Batch 50 (entra en 120 min). Diagnóstico: scraper de 100 inmob con 2 workers tardó 171.7 min > step-timeout 120 min; tokko es el CMS más lento (avg 240s). **Cambio de código → requiere autorización.**
- [ ] No avanzar a Batch 250/500/1000/todas sin nueva autorización.
- Storage Supabase: 828 MB (internal_scraping 469 MB) — amplio margen (Pro). Neon ya no es restricción.

Esta nota ordena los pendientes vigentes. Los pendientes historicos previos quedan reemplazados por este roadmap salvo que esten citados en una nota historica.

## Foco inmediato — dos tracks paralelos

### Track A: Sprint G0 — Batches escalados

Ver: [[Registro 2026-06-11]], [[Roadmap 2026-06-09]]

- [x] Batch 5 cerrado: 5 inmobiliarias, 561 props publicadas a Supabase. ✅ 2026-06-11
- [x] Correcciones de reglas: min_score=0, allow_pending_geo=True (incluye failed). ✅
- [x] Batch 10 dry-run: plan OK, 10 inmobiliarias seleccionadas (tokko). ✅ 2026-06-11
- [x] **Batch 10 commit** — 1000 props publicadas, 0 failed. ✅ 2026-06-11
- [x] **Batch 50 commit** — run_id=11, 46/50 OK, 9496 detectadas, 10,000 publicadas, 0 failed. ✅ 2026-06-12
- [x] Índice compuesto `idx_propiedades_staging_status_score_id` creado en Neon. ✅ 2026-06-12
- [x] Limpieza 76,320 filas test data en data_quality_issues. ✅ 2026-06-12
- [ ] **⚠️ Neon storage: 411 MB / 540 MB (76%)** — quedan ~2 batches de margen. Evaluar upgrade plan Neon o estrategia de cleanup antes de Batch 100.
- [ ] Geocode backlog: ~42,538 staging rows pending geocoding. Correr geocode_staging standalone por sesiones.
- [ ] Autorizar Batch 100 dry-run (post-decisión sobre storage).
- [ ] Escalamiento progresivo: 50 → 100 → 500 → todas.

### Track B: Sprint G — QA interactivo + UX frontend

Ver: [[Roadmap 2026-06-09]]

Objetivos:
- Reconectar Chrome MCP (click en icono de extension en Chrome).
- Probar filtros reales interactivos.
- Buscar MOLL/Rosario en buscador — verificar que aparecen las 11 props.
- Revision mobile.
- Opacidad/estilo para propiedades no-activas.
- Indicador "No aparece en mapa" para props sin coordenadas.
- Filtro por estado en FilterBar.
- Mejorar marcador `venta_y_alquiler` en mapa.

Restricciones:
- No tocar backend ni scrapers.
- No publicar masivamente.
- No hacer push sin autorizacion.

---

## Sprint F — Cerrado parcial ⚡ 2026-06-10

QA real completado: frontend cargando datos reales desde Supabase. Fix RLS + query unica directa.
Ver: [[Sprint F - QA visual y UX frontend]]

## Sprint E — Cerrado ✅ 2026-06-10

Frontend labels y visualizacion de datos incompletos. 7 archivos modificados, ESLint + TypeScript limpios.
Ver: [[Sprint E - Frontend labels]]

## Sprint D — Cerrado ✅ 2026-06-10

Pipeline end-to-end verificado con MOLL PROPIEDADES (inmobiliaria_id=2718).
Ver: [[Sprint D - Prueba controlada pipeline]]

---

## Prioridad 1: Pipeline quality root fix

Auditar causas raiz de los principales problemas detectados en la auditoria readiness:

- `missing_location`.
- `geocoding_pending`.
- `missing_price`.
- `missing_images`.
- Duplicados.

Determinar para cada familia si el problema viene de:

- El sitio original no trae el dato.
- El scraper no lo extrajo.
- El mapper no lo normalizo.
- El validador lo descarto.
- El geocoder lo salto correctamente.
- El dato esta en raw/datos_extra pero no pasa a staging.
- El dato esta en URL, titulo o descripcion y no se usa.
- Es un duplicado que debe agruparse, no eliminarse.

## Prioridad 2: Mejorar pipeline al scrapear

Mejorar extraccion y normalizacion general, no propiedad por propiedad:

- Ubicacion desde breadcrumbs, URL, titulo, descripcion, metadatos y JSON-LD.
- Precio y moneda desde HTML visible, JSON embebido y APIs.
- Imagenes reales desde galleries, `og:image`, JSON-LD, APIs y sliders.
- Descarte de placeholders, logos, iconos, mapas y SVGs.
- Ciudad, provincia, barrio y direccion.
- Tipo de propiedad y operacion.
- Source URL original y URL normalizada.
- Inmobiliaria/desarrolladora/contacto si aparece.
- Quality score e issues/warnings.

## Prioridad 3: Mejorar geocoding

Preparar mejores inputs para geocoding:

- Usar direccion + ciudad + provincia.
- Inferir ciudad/provincia solo con senial clara.
- Saltar direcciones contaminadas por telefono, email, contacto, superficie o texto institucional.
- Si solo hay ciudad/provincia, marcar ubicacion aproximada cuando corresponda y dejar issue.
- No inventar coordenadas.

## Prioridad 4: Deduplicacion y agrupacion

Definir politica completa:

- Duplicado exacto.
- Misma propiedad publicada por varias inmobiliarias.
- Posible duplicado dudoso.

Objetivo:

- No perder informacion util.
- No pisar datos buenos con peores.
- Permitir mostrar "tambien publicada por otras inmobiliarias" si hay evidencia suficiente.

## Prioridad 5: Retest controlado

Tomar una muestra controlada de:

- Propiedades con ubicacion faltante.
- Propiedades con geocoding pending.
- Propiedades sin precio.
- Propiedades sin imagen real.
- Posibles duplicadas.

Medir before/after:

- Cuantas recuperan ubicacion.
- Cuantas recuperan precio.
- Cuantas recuperan imagen real.
- Cuantas suben quality score.
- Cuantas pasan de retenidas a publicables.
- Cuantas siguen igual porque el origen no trae el dato.

## Prioridad 6: Frontend

Pendientes frontend:

- R6 mobile.
- Revision visual general.
- Incorporar logo real en `frontend/public/brand/`.
- Revisar performance con datos reales publicados.
- Revisar query Supabase cuando se publique en produccion.

## Prioridad 7: Publicacion controlada futura

Solo despues de mejorar pipeline y revisar calidad:

1. Preparar auditoria previa a publicacion.
2. Publicar 500 propiedades de maxima calidad.
3. Revisar visualmente frontend y datos.
4. Publicar 1.000.
5. Publicar 5.000.
6. Ampliar solo si no aparecen problemas graves.

## Politicas pendientes de definicion

### Propiedades sin precio

- Mostrar "Consultar" si la fuente realmente no publica precio.
- Recuperar precio si existe en raw/HTML/API y no fue extraido.
- No inventar precio.

### Ubicacion

Clasificar como:

- Exacta.
- Aproximada.
- No confiable.
- No publicable en mapa.

### Imagenes

Clasificar como:

- Imagen real.
- Sin imagen real.
- Placeholder prohibido.

### Publicacion

- No publicar propiedades con datos criticos dudosos.
- No publicar solo por aumentar volumen.
- Priorizar confianza y trazabilidad.

## Seguridad vigente

- No tocar `.env`.
- No borrar datos.
- No publicar a Supabase sin autorizacion.
- No tocar `publish_queue` con commit sin autorizacion.
- No correr `publish_to_supabase.py` sin autorizacion.
- No correr `run_daily_pipeline.py --commit` sin autorizacion.
- No hacer commit ni push sin autorizacion.
- No cambiar esquema de DB sin autorizacion.
