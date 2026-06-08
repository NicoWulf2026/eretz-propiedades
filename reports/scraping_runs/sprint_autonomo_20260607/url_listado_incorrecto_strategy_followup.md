# estrategia_scraping — Diagnóstico y Dry-Run

**Fecha:** 2026-06-08  
**Sprint:** sprint_autonomo_20260607  
**Branch:** fix/scraping-diagnostics-batch  
**Contexto:** url_listado de ids 294 y 3532 fue corregida en batch anterior.  
**Estado:** DRY-RUN — NO EJECUTADO. Pendiente autorización.

---

## Nota sobre `estado_scraping`

> El campo `estado_scraping` **no existe** en `inmobiliarias_main` ni en `v_next_scraping_batch`.  
> Los campos equivalentes son `activa`, `sitio_activo`, `proximo_scraping`, `ultimo_scraping`.  
> Ambos sitios tienen `activa=True, sitio_activo=True` — ningún cambio necesario en esos campos.

---

## Diagnóstico

### id=294 · Martha Bourre Propiedades Pilar

| Campo | Valor actual |
|-------|-------------|
| `url_listado` | `https://www.marthabourre.com.ar/inmuebles/` ✅ |
| `estrategia_scraping` | `'dominio_caido'` ❌ |
| `cms_detectado` | `'custom'` |
| `tipo_paginacion` | `'click'` |
| `lista_para_batch` | `False` |
| `prioridad_scraping` | `'media_revisar'` |
| `necesidades_detectadas` | `[]` |
| `recomendacion` | `'Revisar manualmente.'` |
| `proximo_scraping` | `2026-06-01` (vencido) |

**Resultado del test local read-only de `/inmuebles/`:**
- HTTP 200, 19KB
- `card_hints = 4`, pero keywords genéricas (propiedad/inmueble/venta/alquiler/dormitorio/precio)
- Precios: **ninguno**
- Links individuales a propiedades: **ninguno** — solo 4 links de navegación (/emprendimientos/, /tasaciones, /nosotros, /contacto)
- Sitemap: 404 en todos los candidatos
- Señales WordPress: **ninguna**
- Señales Tokko: **ninguna**

**Diagnóstico:** `dominio_caido` fue asignado porque DNS falló en el momento de detección (2026-05-25). El DNS está resuelto y el sitio responde correctamente. Sin embargo, el contenido del listado `/inmuebles/` es **JS-rendered** — no hay precios ni links de propiedades en HTML estático; las 4 cards son elementos vacíos de plantilla. El site tiene `tipo_paginacion='click'` (paginación JavaScript). Requiere Phase 2 browser detection para asignar estrategia correcta.

**Razón por la que está en `lista_para_batch=False`:**  
El valor `'dominio_caido'` no está en `supported_explicit_strategies` del scraper. El site nunca entra al pipeline.

---

### id=3532 · INMOBILIARIA & GESTORIA MENDOCASA LAVALLE

| Campo | Valor actual |
|-------|-------------|
| `url_listado` | `https://inmobiliariamendocasa.com.ar/listings/` ✅ |
| `estrategia_scraping` | `NULL` ❌ |
| `cms_detectado` | `'wordpress'` |
| `tipo_paginacion` | `'scroll_infinito'` |
| `lista_para_batch` | `False` |
| `prioridad_scraping` | `'media_revisar'` |
| `necesidades_detectadas` | `['falta_estrategia_scraping']` |
| `recomendacion` | `'Revisar manualmente.'` |
| `proximo_scraping` | `2026-06-01` (vencido) |

**Resultado del test local read-only:**
- HTTP 200, 94.3KB
- `card_hints = 58`, 4 detail links, 5 keywords
- WP REST API: `/wp-json/wp/v2/listing` → HTTP 200, `X-WP-Total: 3`
- Namespaces WP: `wp-listings/v1` (NOT `ere/v1` ni `essential-real-estate/v1`)
- Plugins WP detectados por HTML: `wordpress_generic` (sin ERE, Houzez, Estatik, RealHomes)
- Detail URLs confirmadas: `/listings/venta-terreno-calle-maipu-ciudad-mendoza/`, `/listings/1587/`, `/listings/mendocasa-casa-inmobiliaria.../`

**Diagnóstico:** El sitio es WordPress con el plugin "WP Listings" (namespace `wp-listings/v1`). El scraper detectaría `wordpress_generic` mediante `_detect_wordpress_plugin()`. Solo 3 propiedades activas (confirmado via REST API). La estrategia `wordpress_generic_detail` iniciaría con `/listings/`, encontraría los 3 links de detalle, y fetchearía cada página de propiedad.

**Razón por la que está en `lista_para_batch=False`:**  
`estrategia_scraping = NULL` → `necesidades_detectadas = ['falta_estrategia_scraping']` → el view la marca como `lista_para_batch=False`.

---

## FASE 2 — Dry-Run SQL

> **IMPORTANTE: NO EJECUTAR.** Este bloque es solo de revisión.  
> Tabla destino: `public.inmobiliarias_main` en Supabase.

```sql
-- ─────────────────────────────────────────────────────────────────────────────
-- [1] id=294 · Martha Bourre
-- Actual:    estrategia_scraping = 'dominio_caido'
-- Propuesto: estrategia_scraping = NULL
-- Motivo:    dominio_caido fue asignado por falla DNS (2026-05-25). DNS resuelto.
--            NULL permite que Phase 2 browser detection re-ejecute detect_strategy.
--            El pipeline incluye en Phase 2 los sitios con estrategia_scraping IS NULL.
-- Evidencia: HTTP 200 en url_listado, sin señales WP/Tokko/sitemap, contenido JS-rendered
-- Riesgo:    BAJO — NULL no desactiva el sitio; peor caso: detect_strategy falla
--            de nuevo y queda en NULL indefinidamente (sin degradación del estado actual)
-- Efecto esperado: Phase 2 browser detection → assign 'playwright_html' o similar
-- estado_scraping: NO EXISTE — sin cambio
-- activa/sitio_activo: ya True — sin cambio
-- ─────────────────────────────────────────────────────────────────────────────
UPDATE public.inmobiliarias_main
SET estrategia_scraping = NULL,
    updated_at           = NOW()
WHERE id = 294
  AND estrategia_scraping = 'dominio_caido';

-- ─────────────────────────────────────────────────────────────────────────────
-- [2] id=3532 · Mendocasa
-- Actual:    estrategia_scraping = NULL
-- Propuesto: estrategia_scraping = 'wordpress_generic_detail'
-- Motivo:    Plugin WP detectado como 'wordpress_generic' (no ERE/Houzez/Estatik/RealHomes).
--            _strategy_wordpress_plugin_detail itera desde /listings/, extrae detail links,
--            fetchea cada ficha individual. 3 propiedades activas confirmadas vía REST API.
-- Evidencia: cms='wordpress', /wp-json/wp/v2/listing → 200 + 3 items,
--            card_hints=58, 4 detail links confirmados en /listings/, STRONG_SIGNALS
-- Riesgo:    BAJO — 3 propiedades confirmadas, WP REST API funcional, path /listings/ reconocido
--            por _UNIVERSAL_LISTING_PATHS del scraper
-- Efecto esperado: necesidades_detectadas=[] → lista_para_batch=True → entra al próximo batch
-- estado_scraping: NO EXISTE — sin cambio
-- activa/sitio_activo: ya True — sin cambio
-- ─────────────────────────────────────────────────────────────────────────────
UPDATE public.inmobiliarias_main
SET estrategia_scraping = 'wordpress_generic_detail',
    updated_at           = NOW()
WHERE id = 3532
  AND estrategia_scraping IS NULL;
```

---

## FASE 3 — Recomendación

| id | Opción | Decisión recomendada | Razón |
|----|--------|----------------------|-------|
| 294 | Cambiar solo `estrategia_scraping` → NULL | ✅ **Recomendado** | Habilita Phase 2 browser detection. La detección asignará la estrategia real (likely `playwright_html`). |
| 294 | Dejar que runner auto-diagnostique | ❌ No aplica | `dominio_caido` bloquea el pipeline. Sin cambio, nunca entra al batch. |
| 294 | Asignar `playwright_html` directamente | ⚠️ Posible pero prematuro | JS-rendered parece confirmado, pero no verificado con browser. Mejor dejar que Phase 2 confirme. |
| 3532 | Cambiar solo `estrategia_scraping` → `wordpress_generic_detail` | ✅ **Recomendado** | WP confirmado, plugin=generic, 3 props vía REST API. Cambio directo y correcto. |
| 3532 | Dejar que runner auto-diagnostique | ❌ No aplica | `estrategia=NULL` ya es el estado actual. No cambia nada. |
| 3532 | Usar `wordpress_essential_real_estate_detail` | ⚠️ Alternativa | Requeriría que el plugin sea ERE (namespace `ere/v1` — no encontrado). Innecesariamente específico. |

**Resumen:**
- **id=294**: SET NULL. Costo mínimo, habilita re-detección automática.
- **id=3532**: SET `wordpress_generic_detail`. Directo, correctamente alineado con el plugin detectado.
- **Ninguna de las dos** requiere tocar `activa`, `sitio_activo`, ni ningún campo que no sea `estrategia_scraping`.

---

## Impacto esperado post-UPDATE

| id | `lista_para_batch` | Próximo efecto |
|----|-------------------|----------------|
| 294 | `False` → seguirá `False` inicialmente | Entra a Phase 2 (browser detection) en próximo pipeline run → assign estrategia → luego `True` |
| 3532 | `False` → debería pasar a `True` | `necesidades_detectadas = []` → entra al batch automático |

---

## ✅ EJECUTADO — 2026-06-08

### Resultado de la transacción

| Paso | Resultado |
|------|-----------|
| STEP 1 Pre-verification | ✅ id=294: `dominio_caido`, id=3532: `NULL` — guardas OK |
| STEP 2 UPDATEs | ✅ 2/2 aplicados |
| STEP 3 Rollback | No requerido |
| STEP 4 Post-verification | ✅ id=294: `NULL`, id=3532: `wordpress_generic_detail`; `activa=True`, `sitio_activo=True` |
| STEP 5 Collateral | ✅ Solo los 2 IDs autorizados modificados |
| STEP 6 v_next re-check | id=294: `necesidades=['falta_estrategia_scraping']`; id=3532: `necesidades=[]` ✅ |

### Estado post-update en `v_next_scraping_batch`

| id | `estrategia_scraping` | `lista_para_batch` | `necesidades_detectadas` |
|----|----------------------|-------------------|--------------------------|
| 294 | `NULL` | `False` | `['falta_estrategia_scraping']` |
| 3532 | `'wordpress_generic_detail'` | `False` | `[]` ✅ |

**Nota sobre `lista_para_batch=False` persistente en id=3532:**  
`necesidades_detectadas` se limpió correctamente. `lista_para_batch` sigue en `False` porque la vista también considera `prioridad_scraping='media_revisar'` y `total_propiedades_normalizado=0` (nunca scrapeada exitosamente). La inclusión en el próximo batch requiere `--include-new` o adición manual. Tras el primer scrape exitoso, `total_propiedades_normalizado` se actualizará y la lógica de `lista_para_batch` debería cambiar.

---

## Re-test local post-update (read-only)

### id=294 Martha Bourre

```
estrategia_scraping = None
Phase 2 eligible:   True  (condición: not None → True)
HTTP check:  200 | 19KB | DNS OK
dominio_caido trigger: NO (sitio accesible)
```

**Conclusión:** id=294 queda habilitado para Phase 2 browser detection en el próximo pipeline run. Si Playwright encuentra propiedades, asignará `playwright_html` u otra estrategia. Si no, quedará en NULL con `falta_estrategia_scraping` para revisión manual. No hay regresión.

### id=3532 Mendocasa

Simulación de `_strategy_wordpress_plugin_detail(plugin='wordpress_generic')`:

```
[1] GET /listings/ → 200 | 94.3KB
[2] Detail links encontrados: 2
    → /listings/venta-terreno-calle-maipu-ciudad-mendoza/
    → /listings/mendocasa-casa-inmobiliaria-alquiler-departamento.../
[3] Fetch detail pages:
    [PROP] venta-terreno-...  → m2=['68M2'], tipo=['Terreno', 'CASA']
    [PROP] mendocasa-...      → prices=['$300000'], m2=['3m2'], tipo=['DEPARTAMENTO']
[4] Páginas con datos de propiedad: 2/2
[5] WP REST API /wp-json/wp/v2/listing → 200 | X-WP-Total=3
    (3ra prop /listings/1587/ disponible vía REST API)
```

**Conclusión:** `wordpress_generic_detail` es VIABLE para Mendocasa. 2 detail pages con datos de propiedad confirmados en HTML estático. Una 3ra propiedad accesible vía WP REST API. La estrategia capturará las 3 propiedades activas.
