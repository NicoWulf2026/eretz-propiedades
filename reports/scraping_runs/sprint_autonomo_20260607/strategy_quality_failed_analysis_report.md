# strategy_quality_failed — Analisis Familia Sprint Autonomo

**Fecha:** 2026-06-07  
**Fuente:** overnight run 2026-06-04 (37 dominios) + retest 2026-06-07 post-Fixes M/N/O/P  
**Retest:** 19 sitios ejecutados con `--test-url --allow-static-detail`, raw logs leidos para ground truth

---

## Resumen: 37 dominios originales

| Categoria | Sitios | Estado |
|-----------|--------|--------|
| Corregidos (Fixes M, N, O, P) | **14** | Resolved |
| Playwright requerido | 4 | Out of scope |
| strategy_quality_failed — sin fix de codigo | 10 | No fix code |
| 0 property links (structural) | 2 | No fix code |
| url_listado incorrecto en DB | 7 | DB fix needed |

**Total: 14 + 4 + 10 + 2 + 7 = 37** ✓

---

## Sitios corregidos por Fixes M, N, O, P (14 total)

### 7 confirmados en sesion previa (Fixes M y N)

| Sitio | ID | Issue original | Fix | Resultado |
|-------|----|----------------|-----|-----------|
| `cimientosbahiablanca.com` | 6309 | urls_invalidas (compound type) | Fix M | score 77→89 |
| `inmobiliariamt.com.ar` | 2340 | urls_invalidas (listing-preview/) | Fix M | score 83→100 |
| `inmobiliariaovejero.com.ar` | 6306 | urls_invalidas (compound type) | Fix M | url_ratio 0.67→1.00 |
| `ibb.com.ar` | 5147 | urls_invalidas (compound type) | Fix M | url_ratio 0.83→1.00 |
| `marramoscardipropiedades.com` | 5490 | urls_invalidas | Fix M | url_ratio 1.00 |
| `pabloemilio.com.ar` | 5846 | urls_invalidas (/propiedad/?id=) | Fix N | score 81→84 |
| `propiedadesgp.com` | 3554 | urls_invalidas (/listing/SLUG) | Fix O | score →100 |

### 7 nuevos descubiertos en retest 2026-06-07

| Sitio | ID | Fix | Resultado retest |
|-------|----|-----|-----------------|
| `kamilpropiedades.com` | 3446 | Fix P (240s budget) | **score=92 props=6** |
| `inmobiliariacasabaron.com.ar` | 2086 | Fix P (240s budget) | **score=84 props=2** |
| `maureinmobiliaria.com` | 1451 | Fix P (240s budget) | **score=67 props=1** |
| `mattiolivende.com.ar` | 4036 | Fix P (240s budget) | **score=90 props=26** |
| `inmobertetti.com.ar` | 2615 | Fix O (/listing/SLUG via sitemap) | **score=87 props=19** |
| `inmobiliariabrown.com.ar` | 699 | Fix O (wordpress_sitemap_detail) | **score=98 props=20** |
| `connectainmobiliaria.com.ar` | 5946 | Fix O (/listing/SLUG) | **score=89 props=6** |

**Nota Fix P:** Los sitios kamilpropiedades, inmobiliariacasabaron, maureinmobiliaria y mattiolivende
fallaban con el budget de 180s. Con 240s (Fix P) completan normalmente. No eran timeouts de red
sino de budget insuficiente relativo al tiempo de diagnostico previo.

**Nota Fix O — efecto sitemap:** inmobertetti y inmobiliariabrown usan `wordpress_sitemap_detail`.
Sus URLs de sitemap son `/listings/SLUG/` que Fix O hizo reconocibles como property URLs validas.
connectainmobiliaria usa `/listing/SLUG/` directamente en el HTML.

---

## Sitios sin fix de codigo disponible (23 total)

### Categoria A: requires_playwright (4 sitios)
Sites Next.js/React donde el contenido se carga por JS.

| Sitio | ID | Sintoma |
|-------|----|---------|
| `narvaez.com.ar` | 5567 | Next.js, requires_playwright=True |
| `hito-arg.com` | 283 | React/Next.js |
| `remaxnoa.com.ar` | 5769 | remax.com.ar (portal externo) |
| `diegogmartin.com.ar` | 5880 | Next.js/React |

**Accion:** Out of scope para sprint sin Playwright masivo.

---

### Categoria B: 0 property links — extractor no ve contenido (2 sitios)

| Sitio | ID | Sintoma |
|-------|----|---------|
| `marinatortaroloinmobiliaria.com` | 5849 | urls_invalidas + sin_fotos_reales |
| `ipropietas.com.ar` | 5352 | requires_playwright |

---

### Categoria C: strategy_quality_failed — sin fix de codigo (10 sitios)
Resultados confirmados en retest 2026-06-07 (raw logs).

| Sitio | ID | Elapsed | Issues retest | Causa raiz |
|-------|----|---------|---------------|------------|
| `inmobiliariamarcon.com.ar` | 2656 | 28s | precios_insuficientes, sin_fotos_reales | Static HTML, contenido JS-rendered |
| `brixar.ar` | 5716 | 41s | precios_insuficientes, sin_fotos_reales | Static, 2 links pero sin precio/foto |
| `fernandescontreras.com` | 6493 | 89s | strategy_quality_failed | Vue.js, requires_playwright |
| `spazios.com.ar` | 3847 | 90s | urls_invalidas | Redirige a pagina de detalle en vez de listado |
| `inmobiliariagarciaherrera.com` | 3523 | 68s | urls_invalidas | Classic ASP, 57 listing links, 0 detail links reconocidos |
| `dinardoprop.com.ar` | 2002 | 51s | strategy_quality_failed | WP, redirige a /venta-y-alquiler/, no hay cards |
| `insiemmeprofesionales.com.ar` | 189 | 138s | urls_invalidas | links=0, like=5, URLs son pagination |
| `danielferraro.com.ar` | 4834 | 82s | strategy_quality_failed | WP sin precios detectables |
| `dimartinoprop.com.ar` | 4863 | 131s | strategy_quality_failed | Structural |
| `maure.com.ar` | 5495 | 103s | sin_propiedades | URL redirige a `maureinmobiliaria.com/departamentos-en-alquiler/` (dominio distinto, solo alquileres, sin links de detalle) |

**Nota maure.com.ar:** No es timeout de red. `http://www.maure.com.ar/alquileres` hace redirect
a `https://maureinmobiliaria.com/departamentos-en-alquiler/` (otro dominio). Esa pagina no tiene
links a fichas individuales. El url_listado en DB deberia apuntar a maureinmobiliaria.com
directamente — o mas precisamente a la pagina principal de propiedades.

---

### Categoria D: url_listado incorrecto en DB (7 sitios)
No retestados (diagnostico original del overnight run).

| Sitio | ID | URL en DB | Problema |
|-------|----|-----------|---------|
| `sauce.com.ar#` | 6732 | `https://sauce.com.ar#` | # anchor → homepage |
| `pcarbone.com#` | 704 | `https://pcarbone.com#` | # anchor → homepage |
| `marthabourre.com.ar#` | 294 | `https://www.marthabourre.com.ar#` | # anchor → homepage |
| `peconcip.com.ar#` | 700 | `http://peconcip.com.ar#` | # anchor → homepage |
| `ucodomos.com/ventajas/` | 332 | `https://ucodomos.com/ventajas/` | Pagina de "ventajas", no listings |
| `inmobiliariamendocasa.com.ar/calculadora-de-alquileres/` | 3532 | URL calculadora | Calculadora, no listings |
| `inmobiliaria-moreno.webnode.com/inmuebles/` | 628 | Webnode CMS | Webnode CMS no scrapeado |

---

## Conclusiones

**Quick wins encontrados:** 14/37 sitios corregidos con Fixes M, N, O, P.

**Sitios sin fix de codigo disponible:** 23/37. Causas:
1. **Playwright requerido** (4): out of scope
2. **0 property links / structural** (2): requeriria feature nueva
3. **strategy_quality_failed sin solucion rapida** (10): Classic ASP, Vue.js, redirect, precios JS
4. **url_listado incorrecto en DB** (7): fix de DB, no de codigo

**Familias con potencial de fix futuro:**
- Classic ASP CMS (`inmobiliariagarciaherrera.com`) → agregar patron ASP `/propiedades.asp?id=N`
- maure.com.ar → DB fix: cambiar `url_listado` a `https://maureinmobiliaria.com/`
- sauce/pcarbone/marthabourre/peconcip → DB fix: quitar `#` del url_listado

---

## Fixes aplicados en este sprint (commits en branch fix/scraping-diagnostics-batch)

| Fix | Commit | Descripcion |
|-----|--------|-------------|
| Fix M | `76d1df572` | Compound property types + listing-preview/ + listing/ pattern |
| Fix N | `2130bd880` | /propiedad/?id=slug-digits |
| Fix O | `d40300a17` | /listing/SLUG |
| Fix P | `4830ae2d9` | CONTROL_ITEM_TIMEOUT 180→240s + static_html_detail 45→200s |

---

## Retest batch ground truth — 19 sitios (2026-06-07)

| # | Sitio | ID | Status real (raw log) | Score | Props |
|---|-------|----|-----------------------|-------|-------|
| 1 | inmobiliariamarcon.com.ar | 2656 | FAIL strategy_quality_failed | 47 | 0 |
| 2 | inmobiliariagarciaherrera.com | 3523 | FAIL strategy_quality_failed | - | 0 |
| 3 | kamilpropiedades.com | 3446 | **PASS** | 92 | 6 |
| 4 | inmobiliariacasabaron.com.ar | 2086 | **PASS** | 84 | 2 |
| 5 | maureinmobiliaria.com | 1451 | **PASS** | 67 | 1 |
| 6 | fernandescontreras.com | 6493 | FAIL strategy_quality_failed | - | 0 |
| 7 | brixar.ar | 5716 | FAIL strategy_quality_failed | 47 | 0 |
| 8 | maure.com.ar | 5495 | FAIL sin_propiedades (redirect domain) | - | 0 |
| 9 | mattiolivende.com.ar | 4036 | **PASS** | 90 | 26 |
| 10 | spazios.com.ar | 3847 | FAIL strategy_quality_failed | - | 0 |
| 11 | inmobertetti.com.ar | 2615 | **PASS** (Fix O via sitemap) | 87 | 19 |
| 12 | dinardoprop.com.ar | 2002 | FAIL strategy_quality_failed | - | 0 |
| 13 | insiemmeprofesionales.com.ar | 189 | FAIL strategy_quality_failed | - | 0 |
| 14 | danielferraro.com.ar | 4834 | FAIL strategy_quality_failed | - | 0 |
| 15 | dimartinoprop.com.ar | 4863 | FAIL strategy_quality_failed | - | 0 |
| 16 | inmobiliariabrown.com.ar | 699 | **PASS** (Fix O via sitemap) | 98 | 20 |
| 17 | inmobiliariamt.com.ar | 2340 | **PASS** (control — Fix M) | 100 | 24 |
| 18 | propiedadesgp.com | 3554 | **PASS** (control — Fix O) | 100 | 21 |
| 19 | connectainmobiliaria.com.ar | 5946 | **PASS** (Fix O: /listing/SLUG) | 89 | 6 |

**Nota:** El batch runner (`run_quality_retest.py`) reporto todos los PASS como "timeout" por un bug
en la deteccion de status (falso positivo cuando "timeout" aparece en log + props_json no leido).
Los resultados de esta tabla provienen de leer los raw logs directamente.
