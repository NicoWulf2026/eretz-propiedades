# Diagnóstico Sauce Inmobiliaria id=6732

**Fecha:** 2026-06-08  
**Sprint:** sprint_autonomo_20260607  
**Modo:** `--test-url --allow-static-detail` — sin DB writes

---

## Estado actual en Supabase (preflight)

| Campo | Valor |
|-------|-------|
| `id` | 6732 |
| `nombre` | Sauce Inmobiliaria |
| `web` | https://sauce.com.ar |
| `url_listado` | `https://sauce.com.ar#` ❌ (rota — `#` al final) |
| `estrategia_scraping` | `NULL` |
| `cms_detectado` | `wordpress` |
| `activa` | True |
| `sitio_activo` | True |
| `total_propiedades` | NULL (nunca scrapeado) |
| `proximo_scraping` | 2026-06-08 (vencido hoy) |

---

## Diagnóstico del sitio

El sitio `https://www.sauce.com.ar/properties/` responde HTTP 200 con 147KB de WordPress.

| Señal | Valor |
|-------|-------|
| HTTP | 200 |
| Tamaño HTML | 147KB |
| Respuesta por request | 4-5s (lento) |
| WP detectado | `wp-content` + `wp-json` en HTML |
| Plugin WP | `wordpress_generic` |
| Links `/properties/SLUG` en HTML | 84 |
| Precios en HTML | `$650.000`, `USD 90.000`, `$800.000` |
| Paginación | 6 páginas (`anchor_next`, `html_selector`) |
| Sitemap WP | `/wp-sitemap-posts-property-1.xml` → **149 URLs** |
| WP REST API | 404 en todos los endpoints (plugin no expone REST) |
| Requiere JS | `False` |

---

## Bug encontrado: Fix R — `properties/SLUG` no reconocido

### Root cause

`_looks_like_real_property_url` cubría `propiedades/` e `inmuebles/` (español) pero NO `properties/` (inglés plural). Sauce usa `/properties/SLUG/` — el formato estándar de temas WP (mismo problema de familia que Fix Q para `/listings/SLUG`).

**Efecto encadenado:**
1. `_looks_like_real_property_url("/properties/SLUG")` → FALSE → 0 links válidos detectados
2. Con 0 links válidos, el scraper prueba ~16 rutas alternativas × 4-5s = 80-100s
3. Timeout a los 90s (`SIMPLE_ITEM_TIMEOUT_SECONDS`) antes de llegar al sitemap

### Fix aplicado

```python
# ANTES (2 líneas separadas)
r"(^|/)propiedades/(?:\d{3,}|[^/]{8,})",
r"(^|/)inmuebles/(?:\d{3,}|[^/]{8,})",

# DESPUÉS (consolidado, +properties)
# Fix R: add properties/ — WP themes (Houzez, etc.) use /properties/SLUG as default post type.
r"(^|/)(?:propiedades|properties|inmuebles)/(?:\d{3,}|[^/]{8,})",
```

**10/10 tests de regresión PASS.** `py_compile` OK.

### Nota de timeout

Con Fix R, el scraper reconoce 25 property links en la primera ruta y determina la estrategia más rápido. Sin embargo, el servidor tarda 4-5s por request y el diagnóstico siempre prueba 16+ rutas — lo que todavía puede superar el límite de 90s en modo `--test-url` sin Playwright.

**En producción no es un problema**: el pipeline corre con Playwright permitido (`allow_playwright_fallback=True`), lo que sube el límite de diagnóstico a 120s. El diagnóstico de Sauce tarda ~85s → cabe dentro de 120s.

---

## Resultado del test local

**Comando:**  
```
--test-url https://www.sauce.com.ar/properties/ --agency-id 6732 --allow-static-detail --allow-playwright-fallback
```
(sin DB writes; `--allow-playwright-fallback` solo extiende el diagnosis timeout, no lanza Playwright)

| Métrica | Resultado |
|---------|-----------|
| Diagnóstico | `scrapeable_wordpress_sitemap` |
| Estrategia elegida | `wordpress_sitemap_detail` |
| Props capturadas | **30** |
| Score | **82** |
| Calidad | **ACEPTADA** |
| `url_real_ratio` | 1.0 |
| Props con fotos | 30/30 ✅ |
| `requires_js` | False |
| Duración extracción | 42.9s |
| Duración diagnóstico | ~85s |
| Completitud | `partial ratio=0.106` (30/284) → `retry=sitemap_batch` |
| Sitemap URLs detectadas | 149 |

### Propiedades (muestra de 5)

| Título | Precio | Fotos | URL |
|--------|--------|-------|-----|
| Country Ubajay | sin precio | 17 | `/properties/country-ubajay-prop79/` |
| Irigoyen Freyre 2900 | USD 90.000 | 9 | `/properties/irigoyen-freyre-2900-prop1777/` |
| Bv. Pellegrini 2900 | ARS 650.000 | 11 | `/properties/bv-pellegrini-2900-prop1786/` |
| Irigoyen Freyre 2600 | ARS 800.000 | 9 | `/properties/irigoyen-freyre-2600-prop245/` |
| Avellaneda 3300 | ARS 800.000 | 12 | `/properties/avellaneda-3300-prop370/` |

### Observaciones de calidad

| Issue | Estado |
|-------|--------|
| `urls_invalidas` | ✅ Ausente (Fix R resuelve) |
| Precios | Parcial — algunas props sin precio numérico (ej: "Country Ubajay") |
| Fotos reales | ✅ 30/30 tienen imágenes reales |
| `tipo_propiedad` | `"otro"` en todas — WP no expone el tipo vía REST; extractor no lo parsea del HTML |
| `direccion/ciudad/provincia` | Vacías en mayoría — el WP plugin no expone estos campos en HTML estático |
| `id_externo` | Vacío — podría extraerse del slug (ej: `prop79` → id 79) |

Los issues de tipo/dirección son **mejoras de enriquecimiento**, no bloqueantes. Quality gate pasada.

---

## Importable

**Sí** — quality gate aceptada (score=82). Los 30 propiedades capturadas pueden importarse.  
El sitemap tiene 149 URLs totales; la extracción completa requeriría `retry=sitemap_batch` en el pipeline.

---

## Acciones pendientes (requieren autorización)

### 1. UPDATE url_listado (DB — necesario antes de importar)

```sql
UPDATE public.inmobiliarias_main
SET url_listado = 'https://www.sauce.com.ar/properties/',
    updated_at  = NOW()
WHERE id = 6732
  AND url_listado = 'https://sauce.com.ar#';
```

**Riesgo:** BAJO. El nuevo URL devuelve HTTP 200 con 147KB de contenido real.  
Sin este UPDATE, el pipeline usa `https://sauce.com.ar#` como URL de listado y el scraper falla en preflight.

### 2. estrategia_scraping (opcional)

`wordpress_sitemap_detail` puede auto-detectarse. El fix R en el scraper permite al diagnóstico ver los 25+ property links y elegir `wordpress_sitemap_detail` automáticamente dentro del timeout de 120s.

No es necesario hacer UPDATE si el pipeline corre con Playwright permitido (120s timeout). Si se quiere evitar la lentitud del diagnóstico, podría setearse como hint, pero no es necesario.

---

## Archivos generados

| Archivo | Descripción |
|---------|-------------|
| `sauce_6732/props.json` | 30 props capturadas |
| `sauce_6732/meta.json` | Metadata completa del run |
| `sauce_6732/run.log` | Log (solo primera línea por bug de tee en background) |
| `sauce_6732_diagnostic.md` | Este reporte |

---

## FRENO

No se importó, validó, ni publicó nada.  
El `url_listado` en Supabase sigue siendo `https://sauce.com.ar#`.  
Esperando autorización para el UPDATE de `url_listado` y commit del Fix R.
