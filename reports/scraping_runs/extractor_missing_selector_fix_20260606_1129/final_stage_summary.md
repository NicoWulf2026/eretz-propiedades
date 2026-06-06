# Resumen final de etapa — batch extractor_missing_selector_fix_20260606_1129

- Fecha: 2026-06-06
- Rama: `fix/scraping-diagnostics-batch`
- Scope: importar, validar y corregir calidad estructural de 24 propiedades nuevas
- Estado: **CHECKPOINT LISTO — pendiente git commit y publish autorización**

---

## 1. Fixes aplicados al código

### Fix A — Inferir ubicación desde hostname (validate_raw_properties.py)

**Problema:** 24 props importadas sin ciudad/provincia porque los dominios no incluyen ubicación
en el HTML. Fix A agrega `_infer_location_from_hostname()` como safety net en el validador.

**Resultado:** `missing_location` bajó de 24 a 3 props (21 inferidas desde hostname).

| Archivo | Función | Tipo |
|---|---|---|
| `scripts/validate_raw_properties.py` | `_infer_location_from_hostname()` | Fix por familia |

---

### Fix B — Operación desde URL path ASP CMS (import_captured_props_to_neon.py)

**Problema:** Propiedades scrapeadas desde CMS ASP tenían `operacion=None` porque el HTML
no la exponía; la URL contenía `/venta/`, `/alquiler/`, etc.

**Resultado:** `infer_operation_from_url_path()` detecta el subfolder del URL.

| Archivo | Función | Tipo |
|---|---|---|
| `scripts/import_captured_props_to_neon.py` | `infer_operation_from_url_path()` | Fix por familia |

---

### Fix E — Títulos CMS short-ID rural (scraper + importer)

**Problema:** Dominios como `camposdelapampa.com.ar` usan URLs del tipo `/ca266.html`.
La función `_title_from_detail_url()` extraía "Ca266.Html" como título. La función
`_is_useful_scraped_title()` lo aceptaba incorrectamente. Resultado: 4 props con
títulos inaceptables para el frontend.

**Solución en 3 capas:**

| Capa | Archivo | Cambio | Tipo |
|---|---|---|---|
| Rechazo | `scraper/scraper_propiedades.py` | `_FILENAME_TITLE_RE` + check en `_is_useful_scraped_title()` | Fix global |
| Fuente alternativa | `scraper/scraper_propiedades.py` | `section.famie-benefits-area` en `title_candidates` | Fix por familia |
| Safety net importer | `scripts/import_captured_props_to_neon.py` | `_FILENAME_TITLE_RE` + `_fix_filename_titulo()` en `build_raw_candidate()` | Fix global |

**Resultado en staging DB:**

| staging_id | Título antes | Título ahora | Acción |
|---|---|---|---|
| 81053 | `Ca266.Html` | `Campo en venta en La Pampa` | UPDATE controlado |
| 81054 | `Mo342.Html` | `Campo en venta en La Pampa` | UPDATE controlado |
| 81055 | `Mo340.Html` | `Campo en venta en La Pampa` | UPDATE controlado |
| 81056 | `Mi319.Html` | `Campo en venta en La Pampa` | UPDATE controlado |

UPDATE ejecutado con 6 guardas: `id IN (...)`, `inmobiliaria_id=1443`, `tipo_propiedad='campo'`,
`provincia='La Pampa'`, `operacion='venta'`, `status='staging'`, `titulo ~* '^[a-zA-Z]{2,4}[0-9]{3,6}\.html?$'`.

---

### Feature — --ids-file en build_publish_queue.py

**Problema:** `build_publish_queue.py` no tenía forma de evaluar solo un subconjunto de
staging rows — con `--limit 30` procesaba los 30 de mayor score histórico, sin tocar el batch nuevo.

**Solución:** Agregar `--ids-file CSV` con la misma semántica que `geocode_staging.py`.

| Archivo | Función | Tipo |
|---|---|---|
| `scripts/build_publish_queue.py` | `fetch_staging_rows(ids=)` + `--ids-file` parser | Feature |

---

## 2. Pipeline ejecutado (paso a paso)

### Importar → propiedades_raw

| Paso | Script | Modo | Resultado |
|---|---|---|---|
| Dry-run import | `import_captured_props_to_neon.py` | dry-run | 24 candidatas |
| Commit import | `import_captured_props_to_neon.py` | **commit** | 24 insertadas en propiedades_raw |

Batch: `internal_batch_20260606_1129` · Fuente: `innoacafayate.com` (21) + `camposdelapampa.com.ar` (4) + `watson.com.ar` (3) ← aprox.

---

### Validar raw → staging

| Paso | Script | Modo | Resultado |
|---|---|---|---|
| Dry-run validate | `validate_raw_properties.py` | dry-run | 24 candidatas (21 location_inferred) |
| Commit validate | `validate_raw_properties.py` | **commit** | 24 movidas a propiedades_staging |

Scores resultantes: 100 (4 props), 95 (6), 80 (3), 75 (8), 65 (3).
`missing_location`: 3 (watson — sin datos de ubicación).

---

### Geocoding

| Paso | Script | Modo | Resultado |
|---|---|---|---|
| Dry-run geo (10 IDs) | `geocode_staging.py` | dry-run | 7 probe + 3 skip(watson) |
| Pilot commit (2 IDs) | `geocode_staging.py` | **commit** | 0 done, 2 failed (Nominatim no cubre Cafayate) |

**Conclusión:** Nominatim sin cobertura callejera para Cafayate (~15k hab). Las 2 props con
geocoding_status=failed tienen lat/lon=NULL (falla limpia, sin coordenadas falsas).

Pendiente: 8 props con geocoding_status=pending (5 Cafayate calles + 3 watson).

---

### Publish queue

| Paso | Script | Modo | Resultado |
|---|---|---|---|
| Dry-run (simulación manual) | — | simulación | 14 encolables / 10 saltadas |
| Dry-run real con --ids-file | `build_publish_queue.py` | dry-run | 14 encolables / 10 saltadas |
| Dry-run post-UPDATE títulos | `build_publish_queue.py` | dry-run | 14 encolables / 10 saltadas |

Las 14 encolables son priority=2 (ninguna llegó a p1 — requiere geo=done + precio + score>=90).
Los 10 saltados: 8 pending + 2 failed (geocoding).

---

## 3. Estado actual de las 24 propiedades en staging

| staging_id | Titulo | Tipo | Op | Precio | Ciudad | Prov | Geo | Score | Encolable |
|---|---|---|---|---|---|---|---|---|---|
| 81036 | Haras La Querencia 800 Hectareas | terreno | venta | 1.450.000 | Cafayate | Salta | pending | 100 | NO |
| 81037 | Depto en Salta sobre avenida Chile. | dpto | venta | 65.000 USD | Cafayate | Salta | skipped | 95 | SI (p2) |
| 81038 | Casa Pueblo Nuevo Mza. 21. | casa | venta | 42.000 USD | Cafayate | Salta | pending | 100 | NO |
| 81039 | Propiedad en calle Ex Colon. | terreno | venta | 75.000 USD | Cafayate | Salta | skipped | 95 | SI (p2) |
| 81040 | Lote Barrio Ribera 1. | terreno | venta | 50.000 USD | Cafayate | Salta | skipped | 95 | SI (p2) |
| 81041 | Pueblo Nuevo Mza. 69 dos lotes. | terreno | venta | NULL | Cafayate | Salta | pending | 80 | NO |
| 81042 | Pueblo Nuevo Mza. 46. | terreno | venta | NULL | Cafayate | Salta | pending | 80 | NO |
| 81043 | Lote en calle Chacabuco.- Cafayate. | terreno | venta | 57.000 USD | Cafayate | Salta | skipped | 95 | SI (p2) |
| 81044 | Pueblo Nuevo Mza. 127. | terreno | venta | NULL | Cafayate | Salta | pending | 80 | NO |
| 81045 | Lotes en calle Los Andes. | terreno | venta | NULL | Cafayate | Salta | skipped | 75 | SI (p2) |
| 81046 | Hotel Texas.- | hotel | venta | NULL | Cafayate | Salta | skipped | 75 | SI (p2) |
| 81047 | Local calle Salta 329 | local | alquiler | 450.000 ARS | Cafayate | Salta | **failed** | 100 | NO |
| 81048 | Casa Vertientes 57, Cafayate | casa | alquiler | NULL | Cafayate | Salta | **failed** | 80 | NO |
| 81049 | Local Calchaqui esq. Arnaldo Echart | local | alquiler | NULL | Cafayate | Salta | skipped | 75 | SI (p2) |
| 81050 | Depto Calchaqui esq. Arnaldo Echart | dpto | alquiler | NULL | Cafayate | Salta | skipped | 75 | SI (p2) |
| 81051 | Deptos Guemes Sur. | dpto | alquiler | 600.000 ARS | Cafayate | Salta | skipped | 95 | SI (p2) |
| 81052 | Casa Lamadrid | casa | alquiler | 400.000 ARS | Cafayate | Salta | skipped | 95 | SI (p2) |
| 81053 | ~~Ca266.Html~~ → **Campo en venta en La Pampa** | campo | venta | NULL | NULL | La Pampa | skipped | 75 | SI (p2) |
| 81054 | ~~Mo342.Html~~ → **Campo en venta en La Pampa** | campo | venta | NULL | NULL | La Pampa | skipped | 75 | SI (p2) |
| 81055 | ~~Mo340.Html~~ → **Campo en venta en La Pampa** | campo | venta | NULL | NULL | La Pampa | skipped | 75 | SI (p2) |
| 81056 | ~~Mi319.Html~~ → **Campo en venta en La Pampa** | campo | venta | NULL | NULL | La Pampa | skipped | 75 | SI (p2) |
| 81057 | Casa en zona Centro. Excelente ubicacion. | casa | venta | NULL | NULL | NULL | pending | 65 | NO |
| 81058 | Casa de categoria en Quintas de Betbeder... | casa | venta | NULL | NULL | NULL | pending | 65 | NO |
| 81059 | Casa en esquina en zona Centro | casa | venta | NULL | NULL | NULL | pending | 65 | NO |

---

## 4. Qué NO se publicó y qué NO se tocó

| Item | Estado |
|---|---|
| publish_queue commit | **NO ejecutado** |
| Supabase | **NO tocado** |
| publish_to_supabase.py | **NO ejecutado** |
| Frontend | **NO tocado** |
| .env | **NO modificado** |
| Datos históricos (propiedades_staging previas) | **NO tocados** — ids-file garantizó aislamiento |
| run_daily_pipeline.py --commit | **NO ejecutado** |
| git push | **NO ejecutado** |
| Schema de Neon | **NO modificado** |
| geocoding masivo | **NO** — solo 2 IDs en pilot |

---

## 5. Issues pendientes

### Geocoding
| staging_id | Tipo | Geocoding | Problema | Acción recomendada |
|---|---|---|---|---|
| 81036, 81038, 81041, 81042, 81044 | terrenos/casa Cafayate | pending | Sin autorización | Autorizar geocoding commit con --ids-file |
| 81057, 81058, 81059 | watson | pending → skipped | Sin ubicación útil | Skippear (watson sin datos) |
| 81047, 81048 | local/casa Cafayate | **failed** | Nominatim sin cobertura callejera | Resetear a pending + probar Google Maps API |

### Publish queue
| Grupo | Encolables | Bloqueante actual |
|---|---|---|
| innoacafayate score=95 con precio (6) | SI | Sin coords (geo=skipped) — publicable como p2 |
| innoacafayate score=75 sin precio (4) | SI | Sin precio + sin coords — publicable como p2 |
| camposdelapampa (4) | SI | Sin ciudad/precio/coords — titulo corregido, publicable como p2 mínimo |
| pending/failed (10) | NO | Geocoding pendiente o fallado |

### Títulos de camposdelapampa (calidad futura)
Los 4 campos tienen título genérico "Campo en venta en La Pampa". Al re-scraper con el
Fix E activo, el scraper extraería de `section.famie-benefits-area`:
- ca266: "Departamento Loventué Muy buen acceso 6.000 ha Cria"
- mo342: "Limay Mahuida Oportunidad 15.000 ha Cria"
- mo340: "Departamento Chalileo Oportunidad 30.000 ha Cria"
- mi319: "Departamento Toay Bosque abierto 600 ha Ganaderia y Agricultura"

---

## 6. Próximos pasos recomendados

**Inmediato (sin riesgo):**
1. `git commit` del checkpoint de código (fixes A, B, E + --ids-file)
2. Revisar si las 10 innoacafayate son suficientemente buenas para publicar (geo=skipped pero titulo+precio ok)

**Cuando se autorice:**
3. `publish_queue --commit --ids-file` con subset: solo las 10 de innoacafayate (staging_ids 81037, 81039, 81040, 81043, 81045, 81046, 81049, 81050, 81051, 81052)
4. Evaluar Google Maps API para geocodificar Cafayate (las 7 props pending + 2 failed)
5. Re-scrape de camposdelapampa para obtener títulos ricos desde `section.famie-benefits-area`
6. Investigar precio en watson (Fix F pendiente)

---

## 7. Verificaciones finales de esta sesión

| Verificación | Resultado |
|---|---|
| py_compile scraper_propiedades.py | OK |
| py_compile import_captured_props_to_neon.py | OK |
| py_compile validate_raw_properties.py | OK |
| py_compile build_publish_queue.py | OK |
| py_compile geocode_staging.py | OK |
| Test suite fixes (5 grupos) | 5/5 PASS |
| UPDATE titulos: 4 filas afectadas | VERIFICADO |
| UPDATE titulos: 0 otras filas tocadas | VERIFICADO |
| publish_queue: 0 entradas para 81053-81056 | VERIFICADO |
| geocoding_results: sin cambios en 4 campos | VERIFICADO |
| Procesos Python activos | 0 |
| .env modificado | NO |
| Frontend tocado | NO |

---

*Sesion 2026-06-06 · rama fix/scraping-diagnostics-batch*
