# Fix: urls_invalidas en Mendocasa — patron /listings/SLUG/

**Fecha:** 2026-06-08  
**Sprint:** sprint_autonomo_20260607  
**Archivo modificado:** `scraper/scraper_propiedades.py`  
**Linea editada:** ~10097 (dentro de `_looks_like_real_property_url`)

---

## Diagnostico

### Root cause

El validador de URLs `_looks_like_real_property_url` contenia este patron en `detail_patterns`:

```python
r"(^|/)listing/[^/?#]{8,}$",
```

Cubre `/listing/SLUG` (singular) pero **no** `/listings/SLUG` (plural). Mendocasa usa el plugin WP Listings que genera URLs `/listings/SLUG/`:

- `/listings/venta-terreno-calle-maipu-ciudad-mendoza/`
- `/listings/1587/`
- `/listings/mendocasa-casa-inmobiliaria-alquiler-departamento.../`

Como ninguna URL de propiedad pasaba `_looks_like_real_property_url`, el `url_real_ratio` era `0/4 = 0.0 < 0.6` → `issues=['urls_invalidas']` → `strategy_quality_failed`.

El error NO era de extraccion ni de Playwright — las propiedades existian y se capturaban. Era un falso positivo del validador.

### Cascada del error

1. `/listings/SLUG/` rechazada por validador → `plugin_property_links_count = 0`
2. Con 0 links validos, el scraper no detecta sitemap WP → elige `custom_listing_detail`
3. `custom_listing_detail` extrae 4 props pero todas fallan quality gate por `urls_invalidas`
4. Quality score 63, resultado: `strategy_quality_failed`

---

## Fix aplicado

**Archivo:** `scraper/scraper_propiedades.py` — funcion `_looks_like_real_property_url`, bloque `detail_patterns`

```python
# ANTES
r"(^|/)listing/[^/?#]{8,}$",

# DESPUES
r"(^|/)listings?/(?:\d{3,}|[^/?#]{8,})$",
```

**Cambios:**
- `listing` → `listings?` — cubre singular (`/listing/`) Y plural (`/listings/`)
- `[^/?#]{8,}` → `(?:\d{3,}|[^/?#]{8,})` — acepta tambien IDs numericos puros de 3+ digitos (ej: `/listings/1587/`)
- Fix global: no hardcodea Mendocasa. Aplica a cualquier sitio WordPress con WP Listings plugin.

**Comentario actualizado en el codigo:**
```python
# CMS custom con prefijo listing[-preview|-detail|-view]/ o listing[s]/ aislado.
# Cubre singular (/listing/) y plural (/listings/) del WP Listings plugin.
# (?:\d{3,}|[^/?#]{8,}) acepta ID numerico puro (ej: /listings/1587/) y slugs largos.
# ej: inmobiliariamt.com.ar          /listing-preview/SLUG
#     propiedadesgp.com              /listing/calle-19-esquina-0-barrio-peteco-rodriguez
#     inmobiliariamendocasa.com.ar   /listings/venta-terreno-calle-maipu-ciudad-mendoza/
#     inmobiliariamendocasa.com.ar   /listings/1587/
# Nota: listing-category/ no matchea (tiene '-category' antes del '/').
#       /listings/ raiz no matchea (nada despues del '/').
#       /listings/page/2/ no matchea ('page' = 4 chars < 8 y no numerico).
```

---

## Tests de regresion (11/11 PASS)

| URL | Esperado | Resultado | Descripcion |
|-----|---------|-----------|-------------|
| `/listings/venta-terreno-calle-maipu-ciudad-mendoza/` | True | PASS | Mendocasa slug largo |
| `/listings/1587/` | True | PASS | Mendocasa ID numerico |
| `/listings/mendocasa-casa-inmobiliaria-alquiler-depto/` | True | PASS | Mendocasa slug largo #2 |
| `/listings/` | False | PASS | Raiz listado -- NO propiedad |
| `/listing-category/terrenos/` | False | PASS | WP taxonomy -- NO propiedad |
| `/listing/calle-19-esquina-0-barrio-peteco-rodriguez` | True | PASS | Singular existente -- no rompe |
| `/listing-preview/casa-3-dormitorios-cordoba` | True | PASS | listing-preview existente -- no rompe |
| `/listings/page/2/` | False | PASS | Paginacion WP -- NO propiedad |
| `/listings/12/` | False | PASS | ID 2 digitos -- no matchea |
| `/listings/999/` | True | PASS | ID 3 digitos -- matchea |
| `/listings/category/casas/` | False | PASS | Multi-segmento -- NO propiedad |

---

## Re-test local id=3532 Mendocasa

**Comando:** `--test-url https://inmobiliariamendocasa.com.ar/listings/ --agency-id 3532 --allow-static-detail`  
**Sin DB writes.**

### Resultado

| Metrica | Pre-fix | Post-fix |
|---------|---------|---------|
| Score | 63 | **82** |
| `accepted` | False | **True** |
| `issues` | `['urls_invalidas']` | **`[]`** |
| `url_real_ratio` | 0.0 | **1.0** |
| Estrategia elegida | `custom_listing_detail` | `wordpress_sitemap_detail` |
| Propiedades capturadas | 4 (rechazadas) | **3 (aceptadas)** |
| Duracion extraccion | ~4 min | **3.44 s** |

### Por que cambio la estrategia

Al reconocer `/listings/SLUG` como URL valida, `plugin_property_links_count` paso de 0 a 3. El diagnostico detecto el sitemap WP (`wp-sitemap-posts-listing-1.xml`, 3 URLs) y eligio `wordpress_sitemap_detail` — estrategia mas confiable y 70x mas rapida.

### Propiedades capturadas

| Titulo | Precio | Fotos | URL |
|--------|--------|-------|-----|
| Venta Deposito en calle Maipu 235 | USD 610000 | 4 | `/listings/1587/` |
| Venta Terreno calle Maipu | USD 60000 | 5 | `/listings/venta-terreno-calle-maipu-ciudad-mendoza/` |
| Alquiler Dpto Las Heras | ARS 300000 | 0 | `/listings/mendocasa-...-mendoza/` |

### Nota de completitud

`cards_posibles = 46` pero `sitemap_property_urls_count = 3`. El sitio tiene 46 slots en su template pero solo 3 propiedades publicadas activas. Extraccion parcial esperada — no indica un problema del scraper. El scraper anota `retry_strategy: playwright_or_ajax_load_more` por si en el futuro hay mas propiedades cargadas via AJAX.

---

## Importable

**Si** — quality gate superada, score=82, `url_real_ratio=1.0`, 2/3 props con imagenes, precios presentes en las 3.

---

## FRENO

Fix validado. Sin import, sin publicacion, sin push.  
Esperando confirmacion para el proximo paso (commit de este bloque).

---

## Archivos modificados

| Archivo | Cambio |
|---------|--------|
| `scraper/scraper_propiedades.py` | Patron `listing/` → `listings?/` en `_looks_like_real_property_url` |
| `reports/scraping_runs/sprint_autonomo_20260607/mendocasa_listings_url_fix.md` | Este reporte |
| `reports/scraping_runs/sprint_autonomo_20260607/retest_listings_fix/3532_mendocasa_postfix.json` | Props capturadas post-fix |
| `reports/scraping_runs/sprint_autonomo_20260607/retest_listings_fix/3532_mendocasa_postfix.meta.json` | Metadata completa |
| `reports/scraping_runs/sprint_autonomo_20260607/retest_listings_fix/3532_mendocasa_postfix.log` | Log de ejecucion |
