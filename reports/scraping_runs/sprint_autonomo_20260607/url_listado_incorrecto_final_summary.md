# url_listado incorrecto — Resumen Final del Bloque

**Fecha de cierre:** 2026-06-08
**Sprint:** sprint_autonomo_20260607
**Branch:** fix/scraping-diagnostics-batch

---

## Resumen ejecutivo

| Metrica | Valor |
|---------|-------|
| Targets iniciales | 7 |
| URLs corregidas en DB | 6 |
| Sitios desactivados | 1 |
| Sitios importables post-fix | 2 |
| Sitios quality_gate_blocked | 2 |
| Sitios sin propiedades publicadas | 1 |
| Sitios con senales fuertes (test parcial) | 2 |
| Fixes de codigo aplicados | 2 (Fix Q + Fix R) |
| Commits al branch | 4 |
| Updates a Supabase | 10 campos en total |

---

## Estado final por target

### id=294 — Martha Bourre Propiedades Pilar

| Campo | Antes | Despues |
|-------|-------|---------|
| `url_listado` | `https://www.marthabourre.com.ar#` | `https://www.marthabourre.com.ar/inmuebles/` |
| `estrategia_scraping` | `dominio_caido` | `NULL` |
| `activa` | True | True |

**DB changes:** 2 updates (url_listado + estrategia_scraping)
**Resultado test local:** `strategy_quality_failed`
**Issues:** `urls_invalidas` + `precios_insuficientes` + `sin_fotos_reales`
**Requires Playwright:** No (`requires_js=False` — contenido estatico parcial)
**Importable:** ❌
**Diagnostico:** El sitio tiene 3 propiedades detectables via `static_html_detail` pero la quality gate falla por 3 razones. Las URLs no pasan el validador, los precios no estan en el HTML estatico (probablemente "Consultar"), y las fotos no son accesibles sin JS. Problema de calidad de datos del sitio, no de acceso.
**Accion siguiente pendiente:** investigacion separada de quality gate (fuera del bloque url_listado).

---

### id=628 — Moreno, Negocios Inmobiliarios

| Campo | Antes | Despues |
|-------|-------|---------|
| `url_listado` | `http://inmobiliaria-moreno.webnode.com/inmuebles/` | `https://inmobiliaria-moreno.webnode.page/inmuebles/` |
| `estrategia_scraping` | `sitemap` | `sitemap` (sin cambio) |
| `activa` | True | True |

**DB changes:** 1 update (url_listado — migracion TLD .com → .page de Webnode)
**Resultado test superficial:** HTTP 200, 57.6KB, 5 card_hints, precio $350.000 visible, STRONG_SIGNALS
**No se corrio `--test-url` formal** (se incluyo en batch bajo riesgo con re-test superficial)
**Importable:** pendiente test formal — senales fuertes indican probable exito
**Nota:** campo `web` todavia apunta al dominio viejo `http://inmobiliaria-moreno.webnode.com`
**Accion siguiente pendiente:** test formal con `--test-url` para confirmar importabilidad.

---

### id=704 — PAPPACENA | CARBONE Propiedades

| Campo | Antes | Despues |
|-------|-------|---------|
| `url_listado` | `https://pcarbone.com#` | `https://pcarbone.com/inmuebles/venta` |
| `estrategia_scraping` | `sitemap` | `sitemap` (sin cambio) |
| `activa` | True | True |

**DB changes:** 1 update (url_listado)
**Resultado test superficial:** HTTP 200, 28.3KB, **48 card_hints**, **20 precios** ($290.000 / $1.300.000 / $650.000), STRONG_SIGNALS
**No se corrio `--test-url` formal** (re-test superficial del batch)
**Importable:** pendiente test formal — senales muy fuertes (48 card_hints + 20 precios)
**Accion siguiente pendiente:** test formal con `--test-url` para confirmar importabilidad.

---

### id=3532 — INMOBILIARIA & GESTORIA MENDOCASA LAVALLE ✅

| Campo | Antes | Despues |
|-------|-------|---------|
| `url_listado` | `https://inmobiliariamendocasa.com.ar/calculadora-de-alquileres/` | `https://inmobiliariamendocasa.com.ar/listings/` |
| `estrategia_scraping` | `NULL` → `wordpress_generic_detail` | `wordpress_generic_detail` (en DB, el scraper usa `wordpress_sitemap_detail` por deteccion dinamica) |
| `activa` | True | True |

**DB changes:** 2 updates (url_listado + estrategia_scraping)
**Fix de codigo aplicado:** Fix Q — patron `/listings?/(?:\d{3,}|[^/?#]{8,})$` agregado a `_looks_like_real_property_url`
**Resultado `--test-url` post-fix:** score=82, ACEPTADA, `wordpress_sitemap_detail` (3.44s)
**Props capturadas:** 3-4 propiedades (sitio pequeno — 3 listados activos via WP REST API)
**Importable:** ✅ — quality gate aprobada

---

### id=6732 — Sauce Inmobiliaria ✅

| Campo | Antes | Despues |
|-------|-------|---------|
| `url_listado` | `https://sauce.com.ar#` | `https://www.sauce.com.ar/properties/` |
| `estrategia_scraping` | `NULL` | `NULL` (scraper auto-detecta en cada run) |
| `activa` | True | True |

**DB changes:** 1 update (url_listado)
**Fix de codigo aplicado:** Fix R — patron `(?:propiedades|properties|inmuebles)/(?:\d{3,}|[^/]{8,})` unificado en `_looks_like_real_property_url`
**Resultado `--test-url` post-fix:** score=82, ACEPTADA, `wordpress_sitemap_detail` (42.9s), **30 props capturadas**
**Sitemap total:** 149 URLs → pipeline necesitara `retry=sitemap_batch` para captura completa
**Importable:** ✅ — quality gate aprobada

---

### id=332 — Uco Domos — DESACTIVADO

| Campo | Antes | Despues |
|-------|-------|---------|
| `url_listado` | `https://ucodomos.com/ventajas/` | sin cambio |
| `activa` | True | **False** |
| `sitio_activo` | True | **False** |
| `estrategia_scraping` | `dominio_caido` | `dominio_caido` (irrelevante — desactivado) |

**DB changes:** 2 updates (activa + sitio_activo)
**Clasificacion:** `constructora_sin_listado`
**Evidencia:** empresa de domos geodesicos (glamping/turismo/vivienda), menu Tipos de Construccion/Portfolio/Opcionales, WP sitemap 0 post types de propiedades, WP REST API sin `property` type, 0 property links, theme Monolit (corporativo)
**Importable:** N/A — no es inmobiliaria
**Estado:** fuera del universo scrapeable permanentemente.

---

### id=700 — Inmobiliaria Pecon Cip

| Campo | Antes | Despues |
|-------|-------|---------|
| `url_listado` | `http://peconcip.com.ar#` | `http://peconcip.com.ar/mh/?offer-type=venta` |
| `estrategia_scraping` | `sitemap` (incorrecta) | `NULL` |
| `activa` | True | True |
| `sitio_activo` | True | True |

**DB changes:** 2 updates (url_listado + estrategia_scraping)
**Resultado `--test-url`:** `strategy_quality_failed` — todos los extractores fallaron
**Causa raiz:** 0 propiedades publicadas en el CMS (confirmado via `myhome/v1/estates` API + `wp/v2/estate` REST + HTML embebido)
**Requiere Playwright:** Si (`requires_playwright_signals: ["vite_bundle"]`) — pero sin efecto hasta que el operador publique fichas
**Importable:** ❌ — 0 propiedades actuales
**Estado:** URL e infraestructura correctas. Fallara hasta que el operador de Pecon Cip cargue propiedades al CMS.

---

## Cambios en DB (cronologia)

| Fecha | IDs | Campos modificados | Tipo |
|-------|-----|--------------------|------|
| 2026-06-08 | 294, 628, 704, 3532 | `url_listado` | Batch bajo riesgo |
| 2026-06-08 | 294, 3532 | `estrategia_scraping` | Strategy followup |
| 2026-06-08 | 6732 | `url_listado` | Sauce individual |
| 2026-06-08 | 332 | `activa`, `sitio_activo` | Desactivacion |
| 2026-06-08 | 700 | `url_listado`, `estrategia_scraping` | Pecon Cip individual |

**Total campos modificados:** 12 (10 en inmobiliarias_main + 0 en otras tablas)
**Rollback posible:** Si — todos los valores anteriores estan documentados en los reportes.

---

## Cambios en codigo

| Fix | Commit | Descripcion | Impacto |
|-----|--------|-------------|---------|
| Fix Q | `8c636d818` | `_looks_like_real_property_url`: patron `/listings?/SLUG` — WP Listings plugin | Desbloqueo Mendocasa id=3532 |
| Fix R | `3b4c0d489` | `_looks_like_real_property_url`: patron `/properties/SLUG` — WP/Houzez theme | Desbloqueo Sauce id=6732 |

Ambos fixes son globales — benefician a cualquier inmobiliaria futura con estos path patterns.

---

## Commits al branch (bloque url_listado)

| Hash | Mensaje | Contenido |
|------|---------|-----------|
| `8c636d818` | fix(scraping): Fix Q — recognize /listings/SLUG | Fix Q + 6 reportes (dry_run, low_risk, strategy_followup, retest_294_3532, mendocasa fix, retest) |
| `3b4c0d489` | fix(scraping): Fix R — recognize /properties/SLUG | Fix R + reporte sauce_6732_diagnostic |
| `c188ec823` | docs(scraping): mark Uco Domos as non-scrapeable | Reporte uco_domos_332_source_cleanup |
| `455454a19` | docs(scraping): document Pecon Cip listing URL cleanup | Reporte pecon_cip_700_diagnostic |

---

## Que NO se toco

- No se hizo `git push`
- No se importo, valido, ni publico ningun dato a Supabase
- No se cambio ningun schema de Neon/Supabase
- No se modifico nada en `frontend/`
- No se ejecuto `run_daily_pipeline.py`, `build_publish_queue.py`, ni `geocode_staging.py` con --commit
- No se toco `.env` ni `.env.local`
- id=628 `web` field: sigue apuntando al dominio .com viejo (fuera de scope de este bloque)
- id=704 estrategia_scraping `sitemap`: no revisada (puede ser incorrecto segun el sitio)

---

## Clasificacion final del bloque

| Clasificacion | IDs | Descripcion |
|---------------|-----|-------------|
| ✅ **importable** | 3532, 6732 | Quality gate aprobada post-fix; listos para pipeline |
| 🔶 **senales_fuertes_pendiente_test** | 628, 704 | URL corregida, re-test superficial positivo; test formal pendiente |
| ❌ **quality_gate_blocked** | 294 | URL corregida, scraping activo, pero quality gate falla por contenido |
| ❌ **sin_propiedades_actuales** | 700 | URL corregida, 0 props en CMS; requiere Playwright + carga de fichas |
| ⛔ **desactivado** | 332 | Constructora sin listado — fuera del universo |

---

## Proximo bloque recomendado — ver FASE 3

`no_property_links` — ver seccion siguiente.

---

---

# FASE 3 — Proximo bloque: `no_property_links`

## Por que conviene seguir con esta familia

El bloque `url_listado incorrecto` cerro los problemas de entrada (URL rota que impide al scraper llegar al sitio). El siguiente nivel natural es `no_property_links` — sitios a los que el scraper SI llega pero no puede encontrar URLs de propiedades individuales para extraer.

**Vinculo con Fix Q y Fix R:** Los dos fixes de codigo aplicados en este bloque (`/listings/SLUG`, `/properties/SLUG`) se basan exactamente en el mismo mecanismo que genera `no_property_links`. Si hay sitios que usan otros path patterns no reconocidos por `_looks_like_real_property_url`, la misma clase de fix los desbloquea.

## Que dice el analisis existente

El reporte `no_property_links_analysis_report.md` (2026-06-07, 80 sitios testeados) categorizo los sitios asi:

| Categoria | Count | Accionable |
|-----------|-------|------------|
| `no_property_links_confirmed` (profundo) | 30 | Ver sub-categorias |
| `requires_playwright` | 16 | ❌ OUT OF SCOPE (sin Playwright masivo) |
| `extractor_missing_selector` (flat listing) | 27 | ❌ Feature nueva — no quick fix |
| `timeout/connection/dns` | 4 | ❌ Sites inaccesibles |
| `no_listing_signals` | 4 | ❌ No tienen propiedades reales |
| `item_timeout` con links encontrados | **1** | ✅ QUICK WIN POTENCIAL |

**Quick win identificado: `pagliaropropiedades.com.ar` (Tandil)**
- El scraper encontro 34 property links en el diagnostico
- Fallo por `item_timeout` antes de completar la extraccion
- `U$S 85000` visible en HTML de paginas de detalle
- Fix probable: ajuste de timeout o seleccion directa de las 34 URLs sin scraping del listing

## Impacto esperado

| Escenario | Sitios desbloqueados | Props estimadas |
|-----------|---------------------|-----------------|
| Fix patron URL faltante (como Fix Q/R) | 2-5 sitios | 10-100 props |
| Fix timeout para pagliaropropiedades | 1 sitio | 20-40 props |
| Flat listing extractor (feature nueva) | 27 sitios | potencialmente grande — pero scope mayor |

El impacto de quick wins de patron URL es modesto (2-5 sitios). El impacto de flat listing extractor seria mayor pero requiere mas desarrollo.

## Riesgos

| Riesgo | Nivel | Mitigacion |
|--------|-------|------------|
| Fix de patron URL afecta otros sitios negativamente | BAJO | Los patrones son additivos; no se remueve ningun patron existente |
| Flat listing extractor genera propiedades de calidad baja | MEDIO | La quality gate (score >= 70) actua como filtro |
| Aumentar timeout puede impactar performance del pipeline | BAJO-MEDIO | Aplicar solo a sitios especificos via --test-url primero |
| Sitios con `no_property_links` pueden ser SPAs (requires_playwright) | MEDIO | Analizar `requires_js` antes de invertir en fix estatico |

## Primer paso sugerido

**Antes de iniciar el bloque `no_property_links`:**

1. **Re-correr el diagnostico expandido** con Fix Q y Fix R aplicados — es posible que algunos sitios que antes fallaban ahora pasen gracias a los nuevos patrones de URL ya en el codigo.

2. **Evaluar `pagliaropropiedades.com.ar` primero** — es el quick win mas claro: 34 property links detectados, precio visible, solo falla por timeout.

3. **Clasificar los restantes** entre:
   - `url_pattern_missing` (fix en `_looks_like_real_property_url`) — 2-5 sitios esperados
   - `flat_listing` (feature nueva) — 27 sitios, mayor scope
   - `requires_playwright` — descartar para este sprint

**Comando sugerido de primer diagnostico (read-only, sin DB writes):**
```bash
python scraper/scraper_propiedades.py \
  --test-url http://www.pagliaropropiedades.com.ar/propiedades.php \
  --allow-static-detail \
  --allow-playwright-fallback
```

---

## FRENO

No se inicia el bloque `no_property_links` hasta recibir confirmacion.
Este documento es solo preparacion/analisis — ninguna accion ejecutada.
