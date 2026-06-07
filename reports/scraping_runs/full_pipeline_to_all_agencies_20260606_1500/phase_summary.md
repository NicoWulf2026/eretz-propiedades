# Phase Summary — FASE 0-3

- Sesión: 2026-06-06
- Rama: `fix/scraping-diagnostics-batch`
- Commits: `69cac0db` (checkpoint anterior) + nuevo commit pendiente (Fix G)

---

## FASE 0 — Preflight ✅

**Estado**: COMPLETADO

- git status: rama correcta, sin cambios unstaged
- Commit anterior: `69cac0db` — 26 archivos, 5 scripts Python + 21 reportes
- No hay procesos Python activos
- `.env` no fue modificado
- Frontend no fue tocado
- publish_queue sin commit
- Neon: propiedades_raw=76.545, staging=76.447, geocoding=7.218, publish_queue=40

**Veredicto**: Todo consistente. Sin bloqueos.

---

## FASE 1 — Auditoría post-checkpoint ✅

**Estado**: COMPLETADO

**Fixes ya activos**: Fix A (hostname location), Fix B (ASP URL op), Fix E (short-ID titles), --ids-file en geocode y publish

**Errores pendientes identificados**:
- Watson sin precio → investigado en FASE 3 → RESUELTO
- Geocoding Cafayate: 7 pending + 2 failed → Nominatim sin cobertura
- Publish queue: 14 encolables sin commit → pendiente autorización

**Ver**: `post_checkpoint_audit.md`

---

## FASE 2 — Re-scrape controlado ✅

**Estado**: COMPLETADO

**Condiciones**: workers=1, timeout=220s, sin Playwright, solo captura local, NO DB

**Resultados**:

| Agencia | Props | Fix validado |
|---|---|---|
| Innoacafayate | 17 | Fix A ✅ Fix B ✅ |
| CamposDelAmapa | 4 | Fix E ✅ (títulos ricos) |
| Watson | 3 | No (pre-Fix G) |
| **Total** | **24** | |

**Validaciones**:
- Fix A: 17/17 Innoacafayate props con Cafayate/Salta ✅
- Fix B: 100% operaciones correctas (venta/alquiler desde URL) ✅
- Fix E: 0 títulos filename en re-scrape ✅ (antes: 4 props afectadas)
- CamposDelAmapa títulos ricos: Departamento Loventué, Limay Mahuida, Chalileo, Toay ✅

**Sin regresiones detectadas.**

**Ver**: `rescrape_controlled_report.md`

---

## FASE 3 — Fix G: Watson sin precio ✅

**Estado**: COMPLETADO

**Root cause**: Watson CMS (esmsv.com) genera JSON-LD `@type=Product` con solo `name` + `image` pero sin `offers`/`price`. El scraper aceptaba este JSON-LD y retornaba SIN llamar a `_html_extract_detail`, donde el selector `.price` habría encontrado el precio.

**Investigación**: 6 pasos diagnósticos
1. Confirmed HTML has price: `<h3 class="price">US$\xa088.000,00</h3>` at byte ~211K (77% of page)
2. `.price` CSS selector already in scraper — not the issue
3. `_normalizar_precio_detalle("US$ 88.000,00")` returns `(88000.0, 'USD')` correctly
4. `_fix_mojibake_text` doesn't corrupt Watson HTML (no mojibake triggers)
5. Watson JSON-LD scan: `@type=Product` matches `_JSONLD_TYPES` — intercepts before HTML extraction
6. `_parse_jsonld_item(Product{name,image})` returns non-None → `_html_extract_detail` never called

**Fix G implementado** (global, no hardcodeado para Watson):
- Si JSON-LD matchea pero `precio=None` → llamar `_html_extract_detail` para enriquecer precio
- Solo modifica precio/moneda; preserva titulo/imagenes del JSON-LD
- `try/except` protege contra errores de la llamada extra

**Validación before/after**:

| Prop | Before | After |
|---|---|---|
| casa-en-zona-centro | precio=None | **precio=88,000 USD** ✅ |
| casa-de-categoria-quintas | precio=None | precio=None (genuino) ✅ |
| casa-en-esquina | precio=None | **precio=125,000 USD** ✅ |

Watson `valid_price_ratio: 0.0 → 0.667` · score: 61 → 71

**Ver**: `watson_price_fix_report.md`

---

## Resumen de cambios de código esta sesión

| Fix | Archivo | Líneas | Tipo | Validado |
|---|---|---|---|---|
| Fix G — JSON-LD enrich from HTML | `scraper/scraper_propiedades.py` | +14 líneas en `_extract_detail_page` | Global | ✅ py_compile + re-scrape Watson |

---

## Qué NO se tocó

| Ítem | Estado |
|---|---|
| `.env` | NO MODIFICADO |
| Frontend | NO TOCADO |
| Neon DB (histórico) | NO MODIFICADO |
| publish_queue | SIN COMMIT |
| Supabase | NO TOCADO |
| publish_to_supabase.py | NO EJECUTADO |
| run_daily_pipeline.py --commit | NO EJECUTADO |
| git push | NO EJECUTADO |
| Zonaprop / Argenprop | 0 intentos de scraping |
| Geocoding masivo | NO — solo análisis |

---

## Métricas de la sesión

| Métrica | Valor |
|---|---|
| Fases completadas | 4/4 (FASE 0-3) |
| Fixes implementados | 1 (Fix G — global) |
| Fixes validados | 4 (A, B, E ya activos + G nuevo) |
| Batches de re-scrape | 2 (pre-fix y post-fix Watson) |
| Props scrapeadas (local, no DB) | 27 (24 + 3 Watson post-fix) |
| Errores de scraping | 0 |
| Regresiones detectadas | 0 |
| py_compile checks | PASS en todos los archivos modificados |
| Reportes generados | 4 (post_checkpoint, rescrape, watson_fix, phase_summary) |

---

## Próximo paso recomendado

**FASE 4 — Cerrar familia `extractor_missing_selector`** (requiere autorización)

- 27+ dominios identificados con este error en sesiones anteriores
- Muchos son sitios PHP/ASP/WordPress con selectores CSS diferentes
- Fix global por familia: detectar variantes de precio/título/tipo por CMS family
- Potencial: 200-500 props nuevas capturables

**Antes de FASE 4, también pendiente decisión sobre**:
- Commit Fix G (sin push)
- Publish queue commit para las 14 encolables actuales
- Geocoding Google Maps API para Cafayate (7 pending + 2 failed)
- Re-import CamposDelAmapa con títulos ricos (4 props en staging con título genérico)
- Re-import Watson con Fix G activo (3 props con precio ahora disponible)

---

*Sesión 2026-06-06 · FASE 0-3 completadas · rama fix/scraping-diagnostics-batch*
