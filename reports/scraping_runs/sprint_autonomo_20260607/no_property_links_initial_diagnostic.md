# no_property_links — Diagnostico Inicial

**Fecha:** 2026-06-08
**Sprint:** sprint_autonomo_20260607
**Branch:** fix/scraping-diagnostics-batch

---

## Resumen ejecutivo

| Metrica | Valor |
|---------|-------|
| Candidatos analizados | 80 (del run expandido 2026-06-05) |
| Quick win encontrado | 1 (Pagliaro — Fix S aplicado) |
| Fix aplicado | **Fix S**: soporte de tipos plurales en URLs CMS argentino |
| Tests de regresion | 26/26 PASS |
| Props capturadas post-fix (Pagliaro) | **34** (score=100, antes: 1) |
| Otros candidatos desbloqueados por Fix S | 0 (en el set de 80) |
| Candidatos con requires_playwright | 16 (out of scope) |
| Candidatos flat_listing (sin paginas de detalle) | 27 (feature nueva requerida) |
| Candidatos sin solucion rapida | resto |

---

## Pagliaro Propiedades — Fix S aplicado ✅

### Site

| Campo | Valor |
|-------|-------|
| `id` | 4418 |
| `nombre` | Juan I. Pagliaro Propiedades |
| `dominio` | pagliaropropiedades.com.ar |
| `url_original` | `http://www.pagliaropropiedades.com.ar/propiedades.php` |
| CMS | CDH (CMS argentino propio) |
| Ciudad | Tandil, Buenos Aires |

### Diagnostico pre-Fix S

| Metrica | Valor |
|---------|-------|
| `generic_property_links_count` | 1 (solo una URL reconocida de 265+) |
| `listing_links_count` | 39 (filtros tipo `/propiedades.php?tipo_propiedad=Casas`) |
| `cards_posibles` | 30 |
| Props capturadas | 1 |
| Score | 82 |
| `motivos_descarte` | `cards_sin_links_detalle` |

### Causa raiz

Los hrefs en el HTML de Pagliaro son URLs RELATIVAS sin slash:
```
casas-en-venta-en-tandil-av.-balbin-y-machado---se-vende-con-renta-44315-161.html
departamentos-en-venta-en-tandil-la-amiga-44388-162.html
lotes-en-venta-en-tandil-parque-independencia-44267-162.html
```

El patron Fix M existente (linea 10112) reconocia solo SINGULARES (`casa`, `departamento`, `lote`).
Los URLs de Pagliaro usan PLURALES (`casas`, `departamentos`, `lotes`) — no reconocidos.

**Resultado**: `_looks_like_real_property_url` retornaba False para 265 URLs validas de propiedades.
Solo 1 URL (la primera que el scraper encontraba por otra via) pasaba el quality gate.

### Fix S aplicado — `(e?s)?` suffix en tipos

```python
# ANTES (Fix M, solo singular)
r"(^|/)(?:casa|depto|departamento|terreno|local|oficina|lote|campo|chalet|galpon|cochera|duplex|triplex|ph|monoambiente)(?:-[a-z]+)*-en-(?:venta|alquiler)-(?:en-)?[^/?#]{20,}(?:\.html?)?$"

# DESPUES (Fix S, singular + plural)
# (e?s)? cubre:
#   - sin sufijo:    casa, departamento, lote (singular, sin cambio)
#   - + s:           casas, departamentos, lotes, terrenos, cocheras
#   - + es:          locales, galpones (plurales irregulares)
r"(^|/)(?:casa|depto|departamento|terreno|local|oficina|lote|campo|chalet|galpon|cochera|duplex|triplex|ph|monoambiente)(e?s)?(?:-[a-z]+)*-en-(?:venta|alquiler)-(?:en-)?[^/?#]{20,}(?:\.html?)?$"
```

**Cambio minimo**: agrega `(e?s)?` entre el tipo y el separador `(?:-[a-z]+)*`.
**Riesgo**: muy bajo — el patron sigue requiriendo `-en-(venta|alquiler)-` y 20+ chars.

### Resultado post-Fix S

| Metrica | Pre-Fix S | Post-Fix S |
|---------|-----------|------------|
| `generic_property_links_count` | 1 | 29 |
| Props capturadas | 1 | **34** |
| Score | 82 | **100** |
| Props con fotos | 1/1 | 34/34 |
| Completitud | 3.3% (1/30) | **50%** (34/68) |
| Retry | `pagination_deep_scan` | `pagination_deep_scan` |
| Estrategia | `static_html_detail` | `static_html_detail` |
| Tiempo extraccion | 72.6s | 125.5s |

Propiedades capturadas (muestra de 5):
- Casas en Venta — Av. Balbin y Machado | USD 68.000
- Casas en Venta — San Martin al 200 | USD 85.000
- Casas en Venta — Muniz al 200 | USD 90.000
- Casas en Venta — Vulcano y Rivadavia | USD 95.000
- Casas en Venta — Alberdi al 400 | USD 100.000

**Importable**: ✅ — quality gate aprobada (score=100).
**Completitud**: 34/68 propiedades en primer run. Pipeline capturara el resto con `retry=pagination_deep_scan`.

### Tests de regresion Fix S — 26/26 PASS

| Grupo | Tests | Resultado |
|-------|-------|-----------|
| Fix S nuevos (plurales): casas, departamentos, lotes, terrenos, cocheras, oficinas, galpones, locales | 9 | PASS |
| Fix M originales (singulares): casa, departamento, local-comercial, lote | 4 | PASS |
| Fix Q (listings/SLUG, /listings/ root guard, /listings/page/2/) | 3 | PASS |
| Fix R (properties/SLUG x2) | 2 | PASS |
| Fix O (listing-preview/SLUG) | 1 | PASS |
| Falsos positivos: filter query, bare plurals, too-short URLs | 7 | PASS |

---

## Re-scan familia no_property_links — resultados

Scan de 30 candidatos (php_listing N=15, clean_path+html_static N=16) para detectar URLs con patron plural `{tipo}s-en-{op}-en-...`:

| Familia | Candidatos scaneados | Fix S quick wins |
|---------|---------------------|-----------------|
| `php_listing` | 15 | 0 |
| `clean_path` | 12 | 0 (*) |
| `html_static` | 4 | 0 |

(*) 2 falsos positivos detectados en scan superficial:
- `mpatagonia.com` (id=3739): URL tipo blog (`/2010/07/casas-en-alquiler.html`) — no es ficha de propiedad
- `grupofons.com` (id=51): URL `/propiedades/departamentos-en-venta-...` — ya cubierto por patron `propiedades/SLUG` existente

**Conclusion**: Fix S beneficia a Pagliaro (id=4418) en este ciclo de candidatos. La familia CMS `cdh.com.ar` (sistema propietario argentino) tiene probablemente mas sitios en Supabase no incluidos en el set de 80 candidatos — Fix S los beneficiaria automaticamente cuando entren al pipeline.

---

## Clasificacion de los 80 candidatos

### Categoria 1: item_timeout con links detectados → QUICK WIN

| id | Site | Links detectados | Props estimadas | Fix |
|----|------|-----------------|-----------------|-----|
| 4418 | pagliaropropiedades.com.ar | 34 | ~68 | **Fix S — APLICADO** |

### Categoria 2: requires_playwright (16 sites) — OUT OF SCOPE

Causa: `req_js=True`, `req_playwright=True`, `motivo=html_responde_pero_contenido_cargado_por_js`
Ejemplos: `ferverinmobiliaria.com.ar`, `nucleoinmobiliaria.com.ar`, `ushuaiahome.com`
Fix: requiere Playwright masivo — NO en scope de este sprint.

### Categoria 3: flat_listing (27 sites) — FEATURE NUEVA

Causa: `cards_sin_links_detalle` — el HTML tiene cards de propiedades pero sin links `<a href>` individuales a fichas.
Toda la informacion de la propiedad esta inline en la card del listado, sin paginas de detalle.
Ejemplos: `burni.com.ar` (190 cards!), `feijopropiedades.com.ar`, `balmoral.com.ar`
Fix: nuevo modo extractor "flat listing" — extrae datos directamente de las cards sin navegar a detalle.
Scope: mayor desarrollo, no quick fix. Candidato para proximo sprint de features.

### Categoria 4: timeout/connection/DNS (4 sites)

- `saezfarez.com`: timeout persistente
- `inmoromanazzi.com.ar`: timeout persistente
- `grupoinver.com.ar`: connection_error
- `inmobiliariasoluciones.com`: DNS caido
Fix: no hay fix de codigo — sites inaccesibles.

### Categoria 5: no_listing_signals / possible_developer (4 sites)

- `valora.com.ar`, `sigmasa.com`: no_listing_signals — landing pages sin listado real
- `grdesarrollos.com`: possible_developer_without_listings
Fix: sin fix — no tienen propiedades en formato scrapeable.

### Categoria 6: site_down_confirmed (6 sites)

Sites caidos — sin fix posible.

---

## Impacto de Fix Q/R sobre esta familia

Ninguno de los 80 candidatos usa `/listings/SLUG` ni `/properties/SLUG` en sus URLs.
Fix Q y Fix R benefician sitios con esos patrones (Mendocasa, Sauce ya resueltos) pero no a
los candidatos actuales de `no_property_links`.

Fix Q/R tendra impacto futuro cuando sitios WP con esos plugins entren al pipeline por primera vez.

---

## Proximo paso recomendado

### Opcion A — Flat listing extractor (alto impacto, mayor scope)

27 sitios tienen HTML con cards pero sin links de detalle. Un extractor "flat" que procese
las cards del listado directamente capturaria ~100-200+ propiedades por ciclo.
Ejemplos: `burni.com.ar` (190 cards), `feijopropiedades.com.ar` (6 cards).

Scope: feature nueva — estimado 2-3 sesiones de desarrollo.

### Opcion B — Commit Fix S + siguiente familia de errores

Fix S esta listo y probado. Commitear y mover al siguiente bloque del sprint:
- `strategy_quality_failed` — sitios que llegan al scraper pero fallan la quality gate
- `requires_playwright` — si se autoriza Playwright para un subconjunto de sitios
- `item_timeout` — sitios que timeout durante extraccion (aunque no haya links faltantes)

### Opcion C — Ampliar el scan a todos los sitios Supabase

Consultar cuantos sitios en Supabase tienen `no_property_links` O `no_property_links_confirmed`
y tienen URLs con el patron `{tipo}s-en-{op}-en-` (CMS cdh). Fix S podria beneficiar mas sitios
que no aparecen en el set de 80 candidatos actual.

---

## FRENO

No se importo, valido, ni publico nada.
Fix S aplicado y probado localmente.
No se modifico DB.
Esperando autorizacion para commit de Fix S + reporte.
