# Pendientes de ERETZ Propiedades

Ultima actualizacion: 2026-06-19 (Batch 25 controlado completado — commit 7 validado, pending=0, done=73.414, public.propiedades=105.082)

Ver también: [[Auditoria completa y rebranding ERETZ 2026-06-17]]

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
