# Bloque 1 — Cierre formal

- Fecha cierre: 2026-06-07
- Rama: `fix/scraping-diagnostics-batch`
- Commits locales: `69cac0db` → `fe4ecd04`
- git push: NO ejecutado

---

## 1. Fixes implementados y commiteados

| Fix | Archivo | Tipo | Commit | Estado |
|---|---|---|---|---|
| Fix A — Ubicación desde hostname | `validate_raw_properties.py` | Global | `69cac0db` | ✅ ACTIVO |
| Fix B — Operación desde URL path ASP CMS | `import_captured_props_to_neon.py` | Por familia | `69cac0db` | ✅ ACTIVO |
| Fix E — Rechazar títulos short-ID filename | `scraper_propiedades.py` | Global | `69cac0db` | ✅ ACTIVO |
| Fix E — Título desde `section.famie-benefits-area` | `scraper_propiedades.py` | Por familia (CamposDelAmapa CMS) | `69cac0db` | ✅ ACTIVO |
| Fix E — Safety net en importer | `import_captured_props_to_neon.py` | Global | `69cac0db` | ✅ ACTIVO |
| Fix detail_patterns — 3 patrones de URL argentina | `scraper_propiedades.py` `_looks_like_real_property_url()` | Global | `69cac0db` | ✅ ACTIVO |
| Fix detail_patterns — ASP subfolder `/alquiler/item.asp` | `scraper_propiedades.py` | Por familia | `69cac0db` | ✅ ACTIVO |
| Fix detail_patterns — filename slug `/ca266.html` | `scraper_propiedades.py` | Por familia | `69cac0db` | ✅ ACTIVO |
| Fix detail_patterns — Watson-style clean slug (30+ chars) | `scraper_propiedades.py` | Global | `69cac0db` | ✅ ACTIVO |
| Fix G — JSON-LD Product sin precio → enriquecer desde HTML | `scraper_propiedades.py` `_extract_detail_page()` | Global | `fe4ecd04` | ✅ ACTIVO |
| Feature — `--ids-file` en `geocode_staging.py` | `geocode_staging.py` | Feature | `69cac0db` | ✅ ACTIVO |
| Feature — `--ids-file` en `build_publish_queue.py` | `build_publish_queue.py` | Feature | `69cac0db` | ✅ ACTIVO |

---

## 2. Commits locales

| Hash | Mensaje | Archivos | Notas |
|---|---|---|---|
| `69cac0db` | fix(scraping): improve extractor pipeline and safe publish queue filtering | 26 archivos | Checkpoint anterior a esta sesión |
| `fe4ecd04` | fix(scraping): Fix G — enrich JSON-LD price from HTML when JSON-LD has no price | 8 archivos | Fix G + 7 reportes FASE 0-3 |

**git push: NO ejecutado.**

---

## 3. Datos actualizados en Neon (esta sesión)

### propiedades_raw — 6 filas actualizadas

| raw_id | inmobiliaria_id | Campo actualizado | Antes | Después |
|---|---|---|---|---|
| 82078 | 6162 (Watson) | precio / moneda / datos_extra | None / ARS | **88,000 / USD** + audit trail |
| 82080 | 6162 (Watson) | precio / moneda / datos_extra | None / ARS | **125,000 / USD** + audit trail |
| 82074 | 1443 (CamposDelAmapa) | titulo | "Ca266.Html" | "Departamento Loventué Muy buen acceso 6.000 ha Cria" |
| 82075 | 1443 (CamposDelAmapa) | titulo | "Mo342.Html" | "Limay Mahuida Oportunidad 15.000 ha Cria" |
| 82076 | 1443 (CamposDelAmapa) | titulo | "Mo340.Html" | "Departamento Chalileo Oportunidad 30.000 ha Cria" |
| 82077 | 1443 (CamposDelAmapa) | titulo | "Mi319.Html" | "Departamento Toay Bosque abierto 600 ha Ganaderia y Agricultura" |

### propiedades_staging — 6 filas actualizadas

| staging_id | inmobiliaria_id | Campo actualizado | Antes | Después |
|---|---|---|---|---|
| 81057 | 6162 (Watson) | precio / moneda | None / ARS | **88,000 / USD** |
| 81059 | 6162 (Watson) | precio / moneda | None / ARS | **125,000 / USD** |
| 81053 | 1443 (CamposDelAmapa) | titulo | "Campo en venta en La Pampa" | "Departamento Loventué Muy buen acceso 6.000 ha Cria" |
| 81054 | 1443 (CamposDelAmapa) | titulo | "Campo en venta en La Pampa" | "Limay Mahuida Oportunidad 15.000 ha Cria" |
| 81055 | 1443 (CamposDelAmapa) | titulo | "Campo en venta en La Pampa" | "Departamento Chalileo Oportunidad 30.000 ha Cria" |
| 81056 | 1443 (CamposDelAmapa) | titulo | "Campo en venta en La Pampa" | "Departamento Toay Bosque abierto 600 ha Ganaderia y Agricultura" |

**No tocado: publish_queue, Supabase, frontend, .env, staging IDs < 81036**

---

## 4. Estado final de las 24 propiedades (staging 81036–81059)

### Por agencia

| Agencia | inmob_id | Props | Con precio | Geo done | Geo skipped | Geo pending | Geo failed |
|---|---|---|---|---|---|---|---|
| Innoacafayate | 5282 | 17 | 9 | 0 | 10 | 5 | 2 |
| CamposDelAmapa | 1443 | 4 | 0 | 0 | 4 | 0 | 0 |
| Watson | 6162 | 3 | 2 | 0 | 0 | 3 | 0 |
| **Total** | | **24** | **11** | **0** | **14** | **8** | **2** |

### Estado detallado por staging_id

| ID | Agencia | Título (final) | Precio | Geo | Publicable? |
|---|---|---|---|---|---|
| 81036 | Innoacafayate | Haras La Querencia 800 Hectareas | 1,450,000 USD | pending | NO — geo_pending |
| 81037 | Innoacafayate | Depto en Salta sobre avenida Chile | 65,000 USD | skipped | **SÍ** (priority=2) |
| 81038 | Innoacafayate | Casa Pueblo Nuevo Mza. 21 | 42,000 USD | pending | NO — geo_pending |
| 81039 | Innoacafayate | Propiedad en calle Ex Colon | 75,000 USD | skipped | **SÍ** (priority=2) |
| 81040 | Innoacafayate | Lote Barrio Ribera 1 | 50,000 USD | skipped | **SÍ** (priority=2) |
| 81041 | Innoacafayate | Pueblo Nuevo Mza. 69 dos lotes | None | pending | NO — geo_pending |
| 81042 | Innoacafayate | Pueblo Nuevo Mza. 46 | None | pending | NO — geo_pending |
| 81043 | Innoacafayate | Lote en calle Chacabuco. Cafayate | 57,000 USD | skipped | **SÍ** (priority=2) |
| 81044 | Innoacafayate | Pueblo Nuevo Mza. 127 | None | pending | NO — geo_pending |
| 81045 | Innoacafayate | Lotes en calle Los Andes | None | skipped | **SÍ** (priority=2) |
| 81046 | Innoacafayate | Hotel Texas | None | skipped | **SÍ** (priority=2) |
| 81047 | Innoacafayate | Local calle Salta 329 | 450,000 ARS | **failed** | NO — geo_failed |
| 81048 | Innoacafayate | Casa Vertientes 57, Cafayate | None | **failed** | NO — geo_failed |
| 81049 | Innoacafayate | Local Calchaqui esq. Arnaldo Echart | None | skipped | **SÍ** (priority=2) |
| 81050 | Innoacafayate | Depto Calchaqui esq. Arnaldo Echart | None | skipped | **SÍ** (priority=2) |
| 81051 | Innoacafayate | Deptos Guemes Sur | 600,000 ARS | skipped | **SÍ** (priority=2) |
| 81052 | Innoacafayate | Casa Lamadrid | 400,000 ARS | skipped | **SÍ** (priority=2) |
| 81053 | CamposDelAmapa | **Departamento Loventué Muy buen acceso 6.000 ha Cria** | None | skipped | **SÍ** (priority=2) |
| 81054 | CamposDelAmapa | **Limay Mahuida Oportunidad 15.000 ha Cria** | None | skipped | **SÍ** (priority=2) |
| 81055 | CamposDelAmapa | **Departamento Chalileo Oportunidad 30.000 ha Cria** | None | skipped | **SÍ** (priority=2) |
| 81056 | CamposDelAmapa | **Departamento Toay Bosque abierto 600 ha Ganaderia y Agricultura** | None | skipped | **SÍ** (priority=2) |
| 81057 | Watson | Casa en zona Centro. Excelente ubicación | **88,000 USD** | pending | NO — geo_pending |
| 81058 | Watson | Casa de categoría en Quintas de Betbeder | None | pending | NO — sin precio + geo_pending |
| 81059 | Watson | Casa en esquina en zona Centro | **125,000 USD** | pending | NO — geo_pending |

---

## 5. Resultado de geocoding

| Agencia | Estrategia geocoding | Resultado | Notas |
|---|---|---|---|
| Innoacafayate (10 props) | Nominatim → ciudad=Cafayate, Salta | geo=skipped (coordenadas ciudad) | Fix A activo: ciudad/prov asignados desde hostname |
| Innoacafayate (5 props) | Nominatim → calle específica | geo=pending | Nominatim sin cobertura callejera de Cafayate |
| Innoacafayate (2 props) | Nominatim → calle específica | geo=**failed** | Local calle Salta 329, Casa Vertientes 57 |
| CamposDelAmapa (4 props) | Sin ubicación exacta | geo=skipped | La Pampa, sin ciudad precisa |
| Watson (3 props) | Sin ciudad/provincia | geo=pending | Watson no expone ubicación en ninguna fuente |

---

## 6. Resultado publish_queue dry-run (post-enrichment)

- **14 de 24 props publicables** como priority=2
- **10 excluidas**: 5 geo_pending (Innoacafayate calles) + 2 geo_failed + 3 Watson geo_pending
- Campos del Amapa: 4 encolables con **títulos ricos** (enriquecimiento de esta sesión)
- Watson: 2 con precio correcto pero excluidas por geo_pending
- publish_queue total=40, pending=30 — **sin cambios**

---

## 7. Por qué no se publica todavía

1. **0 props con `geocoding_status=done`** en las 14 encolables — todas tienen `skipped` (ciudad-nivel, no coordenadas de calle).
2. No hay ninguna prop con coordenadas precisas para ser la primera muestra del producto.
3. Solución posible: Google Maps API para 7 props de Innoacafayate (5 pending + 2 failed) → requiere autorización + API key.
4. Watson: sin ubicación en la fuente, no resoluble sin datos adicionales.

---

## 8. Qué queda pendiente

| Pendiente | Requiere | Impacto |
|---|---|---|
| Publish_queue commit (14 props) | Autorización explícita | 14 props publicadas en Supabase |
| Google Maps API para Innoacafayate | Autorización + API key | Hasta 7 props con geocoding_done → publicables |
| Watson geocoding | Datos de ubicación en fuente (no disponibles) | 0-3 props (si se marca geo=skipped manualmente) |
| git push | Autorización explícita | Sincronizar con remote |
| Bloque 2 — extractor_missing_selector batch | Autorización | 60-80+ props nuevas recuperables |

---

## 9. Lo que no se tocó

| Ítem | Estado |
|---|---|
| .env | NO MODIFICADO |
| Frontend | NO TOCADO |
| Supabase | NO TOCADO |
| publish_to_supabase.py | NO EJECUTADO |
| publish_queue (commit) | SIN COMMIT |
| geocoding masivo | NO EJECUTADO |
| run_daily_pipeline.py --commit | NO EJECUTADO |
| git push | NO EJECUTADO |
| Zonaprop / Argenprop | 0 intentos de scraping |
| propiedades_staging ids < 81036 | INTACTOS |

---

*Cierre: 2026-06-07 · Bloque 1 completado · commit activo fe4ecd04 · rama fix/scraping-diagnostics-batch*
