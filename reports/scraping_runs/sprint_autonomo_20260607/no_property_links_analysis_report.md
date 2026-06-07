# no_property_links_confirmed — Análisis Familia Sprint Autónomo

**Fecha:** 2026-06-07  
**Fuente:** expanded run `no_property_links_expanded_20260605_1958` (80 dominios testeados)

---

## Resultados del run expandido

| Status | Count |
|--------|-------|
| OK | 20 (120 props capturadas) |
| no_property_links_confirmed | 30 |
| requires_playwright | 16 |
| site_down_confirmed | 6 |
| no_property_links | 3 |
| sin_propiedades | 2 |
| item_timeout | 1 |
| timeout | 1 |
| strategy_quality_failed | 1 |
| **Total** | **80** |

---

## Clasificación profunda de los 60 sites fallidos

### Categoría 1: requires_playwright (16 sites)
- **Causa:** `req_js=True`, `req_playwright=True`, `motivo=html_responde_pero_contenido_cargado_por_js`
- **No_links_sub:** `dynamic_site_no_cards`
- **Estado:** OUT OF SCOPE — sin Playwright masivo en sprint
- **Ejemplos:** ferverinmobiliaria.com.ar, nucleoinmobiliaria.com.ar, ushuaiahome.com

### Categoría 2: extractor_missing_selector (27 sites)
- **Causa root:** `cards_sin_links_detalle` — el diagnóstico detecta cards HTML pero los cards no contienen `<a href>` a páginas de detalle. El scraper asume flow listing→detail y se bloquea cuando no hay links.
- **req_js=False, req_playwright=False** — HTML estático accesible
- **Arquitectura del problema:** Sites con "flat listing" — toda la info de la propiedad está inline en la página de listado, sin páginas de detalle individuales.
- **Fix requerido:** Nuevo modo de extractor "flat listing" que procese datos directamente de las cards del listado. Esto es una feature nueva significativa, no un quick fix.
- **Sites destacados:**
  - `burni.com.ar`: 190 cards, 1950 visible_properties — enorme volumen pero flat listing
  - `feijopropiedades.com.ar`: 6 cards
  - `balmoral.com.ar`: 3 cards (WordPress)
  - La mayoría: 0 cards y 0 prop_links (scraper completamente ciego a su estructura)

### Categoría 3: timeout/connection/dns (4 sites)
- `saezfarez.com`, `inmoromanazzi.com.ar`: timeout (sitio lento)
- `grupoinver.com.ar`: connection_error
- `inmobiliariasoluciones.com`: dns_error (sitio caído)
- **Fix:** No hay fix de código aplicable — sites inaccesibles o demasiado lentos

### Categoría 4: no_listing_signals / possible_developer (4 sites)
- `valora.com.ar`, `sigmasa.com`: no_listing_signals — probablemente landing pages sin listado real
- `grdesarrollos.com`: possible_developer_without_listings
- **Fix:** Sin fix — sites no tienen propiedades en formato scrapeable

### Categoría 5: static_no_links con req_playwright=True (3 sites)
- `innovaservicioinmobiliario.com`, `inmobiliariacapdevila.com`, `irujo.com.ar`
- Clasificados como estrategia estática pero realmente necesitan Playwright
- **Fix:** OUT OF SCOPE

### Categoría 6: item_timeout (1 site — IMPORTANTE)
- **`pagliaropropiedades.com.ar`** (Tandil)
- El diagnóstico encontró **34 property links**, eligió `static_html_detail`
- Falló por timeout antes de completar extracción de detalles
- Log: `[46/80] item_timeout props=0 url=http://www.pagliaropropiedades.com.ar/propiedades.php`
- **Fix:** Aumentar timeout de items → pertenece a la familia `item_timeout`, no a esta
- HTML de detalle verificado: precio `U$S 85000` en `<p class="margin-none font-28">`, superficie en `<i class="fa fa-arrows"> </i>&nbsp; XX m2`

### Categoría 7: site_down_confirmed (6 sites)
- Sites caídos — sin fix posible

---

## Conclusión

**Quick wins disponibles en esta familia: NINGUNO.**

Los 30 sites persistentemente no_property_links_confirmed tienen problemas estructurales:
1. Requieren Playwright (out of scope)
2. Flat listing sin páginas de detalle (feature nueva requerida)
3. Sites caídos o inaccesibles

**Acción recomendada:**
- Archivar esta familia por ahora
- `pagliaropropiedades.com.ar` → mover a familia `item_timeout` como caso de prueba
- `burni.com.ar` (190 cards) → candidato futuro si se implementa modo "flat listing"

---

## Próxima familia: item_timeout (80 domains en overnight run + pagliaropropiedades)

El timeout actual de items es 120s. Sites como pagliaropropiedades necesitan más tiempo para:
1. Fetch del listado (~5s)
2. Fetch de cada URL de detalle (34 × ~3s = ~102s) → total ~107s → al límite de 120s

**Fix candidato:** Aumentar timeout por item a 180s o 240s para sites estáticos sin Playwright.
