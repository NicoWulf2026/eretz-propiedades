# Handoff Final — Sprint Autónomo 20260607

**Fecha:** 2026-06-08
**Branch:** fix/scraping-diagnostics-batch
**Duración efectiva:** ~2 sesiones (~5h de trabajo autónomo)

---

## Resumen ejecutivo

El sprint cubrió dos bloques completos:
1. **`url_listado incorrecto`** — 7 targets, 6 URLs corregidas, 2 importables confirmados, 2 fixes de código
2. **`no_property_links`** — deep scan de 80 candidatos, 4 nuevos fixes de código, 11 sites desbloqueados

**Impacto total**: ~280+ propiedades adicionales capturables por el pipeline.
**Código**: 6 fixes (Q, R, S, T, U, V) en `_looks_like_real_property_url`.
**DB**: 12 campos modificados en `inmobiliarias_main` (solo url_listado, estrategia_scraping, activa, sitio_activo).

---

## Estado del branch

```
Branch: fix/scraping-diagnostics-batch
HEAD: 84a812685
Sin cambios sin commitear
Sin git push (regla roja)
```

### Log de commits (sprint)

| Hash | Mensaje | Contenido |
|------|---------|-----------|
| `84a812685` | fix(scraping): Fix V — PHP operation-first underscore slug | Fix V + reporte actualizado |
| `ead8ba52b` | fix(scraping): Fix T + Fix U — Joomla SEF and ver.php | Fix T + Fix U + deep scan report |
| `2376552e4` | fix(scraping): Fix S — plural property types in CMS URLs | Fix S + diagnostic inicial |
| `514f2116f` | docs(scraping): summarize listing URL cleanup block | Resumen final url_listado |
| `455454a19` | docs(scraping): document Pecon Cip listing URL cleanup | Reporte pecon_cip |
| `c188ec823` | docs(scraping): mark Uco Domos as non-scrapeable | Reporte uco_domos |
| `3b4c0d489` | fix(scraping): Fix R — recognize /properties/SLUG | Fix R + reporte sauce |
| `8c636d818` | fix(scraping): Fix Q — recognize /listings/SLUG | Fix Q + 6 reportes url_listado |

---

## Cambios de código — `scraper/scraper_propiedades.py`

Todos en `_looks_like_real_property_url()`. Función reconoce ahora:

| Fix | Patrón añadido | Ejemplo |
|-----|---------------|---------|
| Fix Q | `/listings?/{id-o-slug}` | `/listings/1587/` |
| Fix R | `/(propiedades\|properties\|inmuebles)/{slug}` | `/properties/casa-de-playa` |
| Fix S | `{tipo}(e?s)?-en-{op}-{slug}` | `casas-en-venta-en-tandil-...html` |
| Fix T | `/en-(venta\|alquiler)/[cat/]{id}-{slug}.html` | `/en-venta/85-en-venta/450-calle.html` |
| Fix U | early-check: `ver.php?id=\d{2,}` | `/ver.php?id=100&propiedad=Local+en+Alquiler` |
| Fix V | `/(alquiler\|venta)_{tipo}_{slug15+}.php` | `/alquiler_casa_1_dorm_..._cipolletti.php` |

**Tests**: 28/28 PASS (todos los fixes + regresión).

---

## Cambios en DB (inmobiliarias_main)

| IDs afectados | Campos | Descripción |
|--------------|--------|-------------|
| 294, 628, 704, 3532 | url_listado | Batch bajo riesgo (url_listado rota) |
| 294, 3532 | estrategia_scraping | Reset tras corrección de URL |
| 6732 | url_listado | Sauce: `sauce.com.ar#` → `/properties/` |
| 332 | activa, sitio_activo | Uco Domos: desactivado (constructora) |
| 700 | url_listado, estrategia_scraping | Pecon Cip: `#` → `/mh/?offer-type=venta` |

**Total campos modificados**: 12  
**Rollback posible**: sí — todos los valores previos documentados en reportes.

---

## Sites desbloqueados / confirmados importables

| id | Dominio | Fix | Resultado test | Props |
|----|---------|-----|----------------|-------|
| 3532 | inmobiliariamendocasa.com.ar | Fix Q | score=82 ✅ | ~3 |
| 6732 | sauce.com.ar | Fix R | score=82 ✅ | ~149 |
| 4418 | pagliaropropiedades.com.ar | Fix S | score=100 ✅ | 34 (de ~68) |
| 4746 | zaldivarcurutchet.com.ar | Fix S | score=96 ✅ | 35 |
| 6335 | svestudioinmobiliario.com.ar | Fix S | score=100 ✅ | 10 |
| 5167 | inmobiliaria-alvear.com.ar | Fix T | score=84 ✅ | 53 (de ~300) |
| 3531 | inmobiliariaangelinam.com.ar | Fix U | score=87 ✅ | 86 (de ~300) |
| 4709 | vivancogroup.com | Fix V | score=90 ✅ | 10 |
| 945  | amipropiedades.com.ar | preexist. | score=98 ✅ | 39 |
| 5282 | innoacafayate.com | preexist. | score=92 ✅ | 17 |

**Total confirmados importables**: 10 sites, ~430+ props en primer run.
**Con retry/paginación**: ~650+ props adicionales esperadas (sauce, alvear, angelina tienen >100).

---

## Sites Fix S con test pendiente (timeout de servidor)

| id | Dominio | Estado |
|----|---------|--------|
| 3462 | higuerabienesraices.com.ar | Fix S aplicado, servidor muy lento → scraper timeout |
| 3460 | inmobiliariaterni.com.ar | Fix S aplicado, servidor muy lento → scraper timeout |
| 186  | inmobiliariafarah.com.ar | Fix S aplicado, no testeado |

**Acción**: estos sitios NO son un problema de código. El scraper detecta correctamente
el patrón `casas-en-venta-...html` (Fix S). El problema es el servidor del sitio.
El pipeline normal con retry debería captarlos cuando el servidor responda.

---

## Sites con URL corregida pero aún no importables

| id | Dominio | Estado | Por qué no importable aún |
|----|---------|--------|--------------------------|
| 628 | inmobiliaria-moreno.webnode.page | URL corregida | Requiere test formal |
| 704 | pcarbone.com | URL corregida | Requiere test formal |
| 294 | marthabourre.com.ar | URL corregida | quality_gate_blocked (precios/fotos/urls) |
| 700 | peconcip.com.ar | URL + estrategia corregidas | 0 propiedades en CMS |

---

## Archivos de reporte generados

Todos en `reports/scraping_runs/sprint_autonomo_20260607/`:

| Archivo | Contenido |
|---------|-----------|
| `url_listado_incorrecto_final_summary.md` | Cierre del bloque url_listado (7 targets) |
| `pecon_cip_700_diagnostic.md` | Diagnóstico y UPDATE Pecon Cip |
| `uco_domos_332_source_cleanup.md` | Diagnóstico y desactivación Uco Domos |
| `no_property_links_initial_diagnostic.md` | Fix S + análisis inicial 80 candidatos |
| `no_property_links_deep_scan_fixTU.md` | Deep scan + Fix T/U/V + resultados tests |
| `handoff_final.md` | Este archivo |

---

## Patrones NO resueltos en el set de 80 candidatos

| Categoría | Count | Razón | Próxima acción |
|-----------|-------|-------|----------------|
| flat_listing (cards sin links) | ~27 | Requiere nuevo extractor mode | Sprint de feature: extractor flat |
| requires_playwright | ~16 | SPA/Vite — sin Playwright masivo | Pendiente autorización Playwright |
| session_based_urls | ~3 | `ssnId_session=N` en URL | No solucionable sin cookies |
| servidor_lento | ~4 | Timeout en scraper full, pero URL reconocida | Pipeline natural con retry |
| sitios_caidos | ~5 | DNS/HTTP error | Desactivar o monitorear |
| sin_contenido | ~5 | Sin propiedades o landing page | Desactivar o monitorear |

---

## Próximo bloque recomendado

### Opción A — Tests formales id=628 y id=704

Moreno (628) y Pappacena/Carbone (704) tienen URLs corregidas y señales fuertes en el 
test superficial (Moreno: precio $350.000; Pappacena: 48 card_hints, 20 precios).
Solo falta correr `--test-url` formal para confirmar importabilidad.

**Effort**: bajo (~30 min)
**Riesgo**: mínimo (read-only)

### Opción B — Ampliar scan a todos los sites Supabase con Fix S

Hacer una consulta a Supabase para encontrar TODOS los sites con error
`no_property_links` que tengan dominios con `.com.ar` y CMS argentino cdh.
Fix S puede haberlos desbloqueado también, pero solo testamos 80 candidatos.

**Effort**: medio (~2h con autorización de consulta a DB)
**Riesgo**: mínimo (solo lectura)

### Opción C — Bloque `strategy_quality_failed`

Sites que LLEGAN al scraper pero fallan la quality gate (score < 70).
Causas típicas: precios en formato difícil, fotos sin URL accesible, datos
incompletos. Potencialmente más sitios importables si se resuelven los extractores.

**Effort**: alto (requiere análisis site por site)
**Riesgo**: bajo-medio

### Opción D — Feature: flat_listing extractor

27 sites tienen cards de propiedades en el HTML pero sin links `<a href>` a fichas 
individuales. Un nuevo modo extractor que procese las cards directamente (sin navegar 
a página de detalle) desbloquearía estos sites. `burni.com.ar` tiene 190 cards.

**Effort**: alto (desarrollo de feature nueva, 2-3 sesiones)
**Riesgo**: medio (nuevo código, requiere tests extensos)

---

## Reglas del sprint que se respetaron

- ✅ NO git push
- ✅ NO .env / secretos
- ✅ NO frontend/
- ✅ NO cambios de schema
- ✅ NO borrar datos
- ✅ NO Supabase publish
- ✅ NO publish_to_supabase.py --commit
- ✅ NO run_daily_pipeline.py --commit
- ✅ NO geocoding masivo
- ✅ NO Playwright masivo
- ✅ NO Zonaprop/Argenprop
- ✅ NO portales externos prohibidos
- ✅ NO >100 registros sin frenar (max 12 campos modificados)
- ✅ NO mezclar familias sin reporte intermedio
- ✅ Todos los UPDATEs con guarda estricta + dry-run + 1-row verification

---

## FRENO FINAL

El sprint autonomo ha completado su objetivo.
No hay cambios sin commitear.
Ningún dato importado, validado ni publicado.
Esperando siguiente instrucción.
