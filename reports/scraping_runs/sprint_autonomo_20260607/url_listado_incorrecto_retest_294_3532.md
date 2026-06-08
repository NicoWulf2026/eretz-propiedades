# Re-test local ids 294 y 3532 — Post-estrategia-fix

**Fecha:** 2026-06-08  
**Sprint:** sprint_autonomo_20260607  
**Modo:** `--test-url --agency-id --dump-props-json` — sin DB writes  
**Playwright usado:** No (diagnostic `requires_js=False` en ambos)

---

## Resumen ejecutivo

| id | Nombre | Estrategia elegida | Props capturadas | Resultado | Importable |
|----|--------|-------------------|-----------------|-----------|------------|
| 294 | Martha Bourre | `static_html_detail` | 3 (calidad falló) | `strategy_quality_failed` | ❌ |
| 3532 | Mendocasa | `custom_listing_detail` → `static_html_detail` | 4 + 1 (calidad falló) | `strategy_quality_failed` | ❌ |

**Progreso real:** Ambos sitios pasaron de **completamente bloqueados** (`dominio_caido` / sin estrategia) a **scraping activo con propiedades detectadas**. El bloqueo es ahora la quality gate, no el DNS ni la ausencia de estrategia.

---

## id=3532 · Mendocasa

### Ejecución
- Inicio: 10:37:21 | Fin: 10:41:18 | **Duración: ~4 minutos**
- Presupuesto de item: 240s

### Diagnóstico del scraper
| Campo | Valor |
|-------|-------|
| Diagnóstico | `scrapeable_custom_listing` |
| `requires_js` | **False** |
| `load_more_signals` | `['wordpress_ajax']` |
| `generic_property_links_count` | 3 |
| `cards_posibles` | 46 |
| `extractores_detectados` | `['wordpress_generic_detail', 'static_html', 'custom_listing_detail']` |
| `motivos_descarte` | `['cards_sin_links_detalle']` |

**Nota:** El scraper ignoró el `estrategia_scraping='wordpress_generic_detail'` de la DB y ejecutó diagnóstico fresco — eligió `custom_listing_detail` (prioridad más alta en el strategy plan). Esto es comportamiento esperado: la DB strategy solo actúa como fallback explícito bajo condiciones específicas.

### Extractores ejecutados
| Extractor | Props | Score | Issues | Tiempo |
|-----------|-------|-------|--------|--------|
| `custom_listing_detail` | 4 | 63 | `urls_invalidas` | 67s |
| `static_html_detail` | 1 | 67 | `urls_invalidas` | 76s |

### Resultado final
`strategy_quality_failed` — `urls_invalidas`

### Análisis
El scraper encuentra 4 propiedades vía `custom_listing_detail` pero la quality gate las rechaza con `urls_invalidas`. La URL de cada propiedad sigue el patrón `/listings/SLUG/`. El validador de URLs del scraper puede estar clasificando `/listings/` como ruta de listado (no de detalle), rechazando toda URL bajo ese path.

**Las propiedades existen** — 4 capturadas, tipo de cambio cargado ($1435 ARS/USD). El problema es la validación de URLs, no el acceso al contenido.

---

## id=294 · Martha Bourre

### Ejecución
- Inicio: 10:40:47 | Fin: 10:42:57 | **Duración: ~2 minutos**
- Presupuesto de item: 240s

### Diagnóstico del scraper
| Campo | Valor |
|-------|-------|
| Diagnóstico | `scrapeable_static_html` |
| `requires_js` | **False** |
| `load_more_signals` | `['cargar_mas']` |
| `generic_property_links_count` | 3 |
| `cards_posibles` | 2 |
| `extractores_detectados` | `['static_html']` |
| `motivos_descarte` | `['cards_sin_links_detalle']` |

### Extractores ejecutados
| Extractor | Props | Score | Issues | Tiempo |
|-----------|-------|-------|--------|--------|
| `static_html_detail` | 3 | 46 | `urls_invalidas`, `precios_insuficientes`, `sin_fotos_reales` | 56s |
| `json_ld` | 0 | — | `sin_propiedades` | 4s |
| `sitemap` | 0 | — | `sin_propiedades` (404) | 3s |

### Resultado final
`strategy_quality_failed` — `urls_invalidas + precios_insuficientes + sin_fotos_reales`

### Análisis
El scraper detecta 3 propiedades vía `static_html_detail` pero la quality gate falla por 3 razones:
1. **`urls_invalidas`** — las URLs de las 3 propiedades no pasan el validador (posiblemente apuntan a la misma página listing o tienen patrón rechazado)
2. **`precios_insuficientes`** — las propiedades no tienen precios en el HTML estático (probablemente "Consultar" sin valor numérico)
3. **`sin_fotos_reales`** — el sitio no expone imágenes de propiedades en HTML estático

**No requiere Playwright**: `requires_js=False`. El sitio tiene contenido estático scrappeable pero con calidad insuficiente para pasar la quality gate.

---

## Clasificación de bloqueo post-retest

| id | Bloqueante anterior | Bloqueante actual | Bloqueante nuevo |
|----|--------------------|--------------------|-----------------|
| 294 | `dominio_caido` (DNS) | `strategy_quality_failed` | `urls_invalidas` + `precios_insuficientes` + `sin_fotos_reales` |
| 3532 | `falta_estrategia_scraping` (NULL) | `strategy_quality_failed` | `urls_invalidas` |

**Ambos sitios avanzaron**: de "completamente bloqueados" a "scraping activo, quality gate".

---

## Requiere Playwright

**NO** para ninguno de los dos. Diagnóstico explícito: `requires_js=False`.

- **id=294** no queda pendiente para bloque JS — queda pendiente para `strategy_quality_failed` investigation
- La clasificación correcta es: `quality_gate_blocker`, no `requires_playwright_candidate`

---

## Análisis de importabilidad

| id | Importable | Razón |
|----|-----------|-------|
| 294 | ❌ | quality gate falla; URLs inválidas, sin precios, sin fotos |
| 3532 | ❌ | quality gate falla; URLs inválidas |

Para ser importables necesitan resolver el `strategy_quality_failed`. El camino más probable:

**id=3532 Mendocasa:**  
Investigar si el patrón `/listings/SLUG/` está siendo rechazado por el validador de URLs del scraper como "listing page" en lugar de "detail page". Es un falso positivo — las 3 URLs confirmadas vía WP REST API son fichas reales.

**id=294 Martha Bourre:**  
- `urls_invalidas` → igual que Mendocasa, patrón de URL rechazado
- `precios_insuficientes` → el sitio puede no mostrar precios en HTML (solo "Consultar")
- `sin_fotos_reales` → imágenes no accesibles sin JS o no expuestas en HTML estático
- Estos 3 issues juntos indican un sitio con datos parciales que necesita ajuste fino del quality gate o extractor

---

## FRENO

> Re-test completado. Ningún import, validación, ni publicación ejecutada.  
> Logs en: `reports/scraping_runs/sprint_autonomo_20260607/retest_294_3532/`  
> Esperando confirmación para decidir próximos pasos.

---

## Opciones de próximo paso (requieren nueva autorización)

| Opción | Acción | Prerequisito |
|--------|--------|-------------|
| A | Investigar `urls_invalidas` en scraper (patrón `/listings/SLUG/`) | Autorizar análisis de código |
| B | Correr Mendocasa con `--allow-explicit-strategy-fallback` para forzar `wordpress_generic_detail` | Autorizar flag adicional en retest |
| C | Avanzar con otro bloque del sprint (Pecon Cip, Sauce, no_property_links, etc.) | Autorizar bloque |
| D | Commitear los reportes de este bloque y hacer limpieza | Autorizar commit |
