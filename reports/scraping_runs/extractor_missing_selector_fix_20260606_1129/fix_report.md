# Fix Report — extractor_missing_selector FASE 2

- Fecha: 2026-06-06
- Sesión: fix/scraping-diagnostics-batch
- Operador: sistema asistido
- Estado: COMPLETADO (captura local)

---

## Objetivo

Diagnosticar y corregir el error `extractor_missing_selector` para los 27 dominios identificados en el batch `batch_20260605_2002`. Implementar fixes generales (no hardcodes por sitio). Validar antes/después. No importar a Neon.

---

## Dominios analizados (27 del batch_20260605_2002)

Clasificados por causa raíz:

### Amaira CMS — Vue.js / template literals (NO fixable sin Playwright)
Todos usan `${ficha.amigable}` en el HTML — las URLs son templates JS, no href estáticos.

| Dominio | Error original | Reclasificación |
|---|---|---|
| balmoral.com.ar | extractor_missing_selector | requires_playwright / amaira_cms |
| crescendo.com.ar | extractor_missing_selector | requires_playwright / amaira_cms |
| feijopropiedades.com.ar | extractor_missing_selector | requires_playwright / amaira_cms |
| leandrofaraonepropiedades.com | extractor_missing_selector | requires_playwright / amaira_cms |
| isninmobiliaria.net | extractor_missing_selector | requires_playwright / amaira_cms |

### GVAMax / Webflow / JS rendering (NO fixable sin Playwright)
JS-rendered property cards; anchors no están en el HTML estático.

| Dominio | Error original | Reclasificación |
|---|---|---|
| maerpropiedades.com | extractor_missing_selector | requires_playwright / gvamax |
| orion-inmobiliaria.com | extractor_missing_selector | requires_playwright / js_rendered |
| inmobiliariagiordanoconti.com.ar | extractor_missing_selector | requires_playwright / js_rendered |
| eduardobergo.com.ar | extractor_missing_selector | requires_playwright / js_rendered |
| burni.com.ar | extractor_missing_selector | requires_playwright / js_rendered |

### Site down o URL inválida

| Dominio | Estado |
|---|---|
| inmobiliariaescuza.com | site_down_confirmed |
| tonyzorrilla.com.ar | site_down (sesión anterior) |
| grupo-integra.com.ar | URL inválida (403 / no aplica) |

### Timeout / servidor muy lento

| Dominio | Estado |
|---|---|
| armestoinmobiliaria.com.ar | timeout (350s) — servidor no responde |
| luciafrolik.com.ar | item_timeout — listing OK, detail pages >120s |

### No es inmobiliaria / fuera de scope

| Dominio | Notas |
|---|---|
| krool.com.ar | Sin listing válido (sesión anterior) |
| heuguerot.com.ar | Sin clasificar (no incluida en batch) |
| chambopropiedades.com | Sin clasificar (no incluida en batch) |
| inmobellezze.com.ar | Sin clasificar (no incluida en batch) |
| solucionesinmobiliariasweb.com | Sin clasificar (no incluida en batch) |
| ramirezprop.com.ar | Sin clasificar (no incluida en batch) |
| acpneginmobiliarios.com.ar | Sin clasificar (no incluida en batch) |
| temporariosmadryn.com.ar | Sin clasificar (no incluida en batch) |
| rosanigo.com.ar | Sin clasificar (no incluida en batch) |

### FIXADOS — ahora funcionan

| Dominio | ID | Patrón nuevo | Props antes | Props después |
|---|---|---|---|---|
| innoacafayate.com | 5282 | ASP CMS `/venta/item.asp?t=...&id=N` | 0 | **17** |
| camposdelapampa.com.ar | 1443 | Short ID `/ca266.html` (2-3 letras + 3-6 dígitos) | 0 | **4** |
| watsonpropiedades.com | 6162 | Clean URL slug `/casa-en-zona-centro-...` (30+ chars) | 0 | **3** |

---

## Cambios implementados en scraper_propiedades.py

### Fix 1 — HTTP connect timeout (línea ~3142)

Antes: connect timeout hardcodeado a `min(t, 2.5)` — ignoraba el timeout del llamador.

Después: `connect = max(1.0, min(t*0.4, 8.0))` — escala con el timeout, máximo 8s.

Impacto: sitios lentos como luciafrolik ahora pasan la etapa de connect y llegan a detectar strategy (`wordpress_essential_real_estate_detail`), antes fallaban antes de eso.

### Fix 2 — Nuevos patrones en `_looks_like_real_property_url()` (línea ~9638)

Agregados 3 patrones al tuple `detail_patterns`:

```python
# ASP CMS argentino con subfolder de operacion
r"(^|/)(?:alquiler|venta|ventas|temporario)/(?:item|ver|ampliar|ficha|detalle)\.aspx?$"

# Short ID alphanumerico: /ca266.html /mo340.html
r"(^|/)[a-z]{2,3}\d{3,6}\.html?$"

# Slug limpio con tipo de propiedad al inicio (>=30 chars total)
r"^(?:casa|depto|departamento|terreno|local|oficina|lote|campo|chalet|galpon|cochera|duplex|ph|monoambiente)[a-z]?-[a-z0-9-]{22,}$"
```

### Fix 3 — Nuevos CSS selectors en `_extract_generic_property_links()` (línea ~9733)

Agregados selectores para clean URL slugs con tipo de propiedad al inicio:

```python
"a[href^='/casa-']", "a[href^='/depto-']", "a[href^='/departamento-']",
"a[href^='/terreno-']", "a[href^='/lote-']", "a[href^='/local-']",
"a[href^='/oficina-']", "a[href^='/campo-']", "a[href^='/chalet-']",
"a[href^='/cochera-']", "a[href^='/galpon-']", "a[href^='/duplex-']",
"a[href^='/ph-']", "a[href^='/monoambiente-']",
```

### Fix 4 — Fix #2 (static pass) también usa `_looks_like_real_property_url()` (línea ~9776)

Antes: el segundo pase de links estáticos solo llamaba `_looks_like_static_php_detail_url()`.

Después: también evalúa `_looks_like_real_property_url()`, lo que permite capturar short IDs (camposdelapampa) y clean slugs (watson) en ese pase.

---

## Validación de código

- `py_compile.compile(scraper_propiedades.py)` → OK (sin errores de sintaxis)
- 15/15 tests unitarios de patrones → pasaron

---

## Resultados del batch principal (batch_20260606_1129)

- Input: `data/batch_inputs/extractor_fix_fase2_targets.csv` (11 dominios)
- Workers: 1 | Timeout: 220s | allow-static-detail: true | Supabase write: false
- Captura: `data/scraping_batches/internal_batch_20260606_1129/captured/`

| Resultado | N | Dominios |
|---|---|---|
| OK | 3 | innoacafayate, camposdelapampa, watson |
| extractor_missing_selector | 8 | giordanoconti, maer, orion, crescendo, balmoral, feijo, bergo, burni |

**Total props capturadas**: 24

---

## Resultados del batch de timeout (batch_20260606_1137)

- Input: `data/batch_inputs/timeout_fix_targets.csv` (3 dominios)
- Workers: 1 | Timeout: 350s | allow-static-detail: true

| Dominio | Resultado | Notas |
|---|---|---|
| armestoinmobiliaria.com.ar | timeout (test_url_start) | Servidor no responde en 350s |
| luciafrolik.com.ar | item_timeout (wordpress_essential_real_estate_detail) | Listing OK, detail >120s — mejora respecto a sesión anterior |
| inmobiliariaescuza.com | site_down_confirmed | Sitio caído |

**Total props capturadas**: 0

**Nota sobre luciafrolik**: La mejora es significativa — antes fallaba incluso antes de detectar strategy. Ahora llega a intentar `wordpress_essential_real_estate_detail`, lo que confirma que el listing carga. El cuello de botella son las páginas de detalle individuales (>120s cada una).

---

## Selectors / patrones corregidos

| Pattern | Familia CMS | Ejemplo |
|---|---|---|
| `/venta/item.asp?t=slug&id=N` | ASP CMS argentino | innoacafayate.com |
| `/alquiler/item.asp?t=slug&id=N` | ASP CMS argentino | innoacafayate.com |
| `/[a-z]{2,3}\d{3,6}\.html` | CMS propio argentino | camposdelapampa.com.ar |
| `/casa-[slug-30chars+]` | Clean URL CMS (watson) | watsonpropiedades.com |

---

## Dominios que requieren reclasificación en Neon

Los siguientes dominios tienen `extractor_missing_selector` en la tabla de errores de Neon pero la causa real es JS-rendering. No van a mejorar sin Playwright:

**Amaira CMS**: balmoral, crescendo, feijopropiedades, leandrofaraone, isninmobiliaria  
**JS rendering**: maer, orion, giordanoconti, bergo, burni

Acción recomendada: actualizar `familia_error` a `requires_playwright` en `scraping_run_items` (cuando se autorice el próximo ciclo de DB).

---

## Riesgos y limitaciones

1. **innoacafayate operacion**: 6 props del path `/alquiler/` tienen `operacion=venta` en raw. Requiere corrección antes de staging.
2. **camposdelapampa metadata**: Títulos y tipos incorrectos en raw (limitación del patrón short-ID). Requiere revisión manual o extracción adicional.
3. **watson precio**: 3/3 sin precio. El scraper no encuentra el campo en HTML estático.
4. **inmobiliaria_id=0**: El batch usó IDs temporales. Corregir a 5282/1443/6162 al importar.
5. **8 dominios JS sin fix**: Requieren Playwright (fase futura). No se incluyeron en capturas.

---

## Archivos generados

- `reports/scraping_runs/extractor_missing_selector_fix_20260606_1129/fix_report.md` (este archivo)
- `reports/scraping_runs/extractor_missing_selector_fix_20260606_1129/captured_manifest.csv`
- `reports/scraping_runs/extractor_missing_selector_fix_20260606_1129/captured_inventory.md`
- `reports/scraping_autofix/batch_20260606_1129/batch_report.md` (batch principal)
- `reports/scraping_autofix/batch_20260606_1137/batch_report.md` (batch timeout)
