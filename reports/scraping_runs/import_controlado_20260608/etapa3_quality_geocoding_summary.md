# ETAPA 3 — Auditoría de Calidad + Geocoding
## import_controlado_20260608

**Fecha:** 2026-06-08
**Branch:** fix/scraping-diagnostics-batch
**Scope:** 199 propiedades en propiedades_staging (staging_ids 81645–81843, raw_ids 82135–82333)

---

## Resumen ejecutivo

| Métrica | Valor |
|---------|-------|
| Props en staging (scope) | 199 |
| Geocodificadas ANTES de ETAPA 3 | 64 (validate_commit FASE 6 ETAPA 2) |
| Geocodificadas en ETAPA 3 | 2 (Mendocasa, Grupo A) |
| Outliers detectados y limpiados | 2 |
| Geocodificadas correctas (final) | **64** |
| Pendientes sin geocodificar | **129** |
| Skipped (dirección insuficiente) | 4 |
| Failed (outliers limpiados) | 2 |
| Fix aplicado en geocode_staging.py | Fix: strip prefijo "Address:" en normalize_address_for_geocoding |

---

## FASE 1 — Preflight

- Branch: `fix/scraping-diagnostics-batch` ✅
- DB target: Neon (INTERNAL_DB_URL) ✅
- Scope auditado por DB read-only usando `raw_ids_fase5.csv` (199 raw IDs; CSV local ignorado por `.gitignore`)
- Sin procesos activos en paralelo ✅
- REGLAS ROJAS activas ✅

---

## FASE 2 — Auditoría completa de los 199 staging props

### Clasificación por grupo

| Grupo | Descripción | Props |
|-------|-------------|-------|
| A | geocoding_ready_safe + ciudad unambigua en dirección → commit seguro | 2 |
| B | geocoding_ready_safe + ciudad AMBIGUA (no hay join a inmobiliarias en geocode_staging.py) | 36 |
| C | Dirección en título, no en campo `direccion` (dir="-", título = calle+número) | 28 |
| D | garbage_address sin dato recuperable | 36 |
| E | Basura de scraping en campo direccion (footer/copyright del sitio) | 15 |
| F | geocoding_not_ready (referencia de unidad, sin calle+altura) | 8 |
| — | Ya geocodificadas antes de ETAPA 3 (validate_commit) | 64 |
| **Total** | | **199** |

### Detalle por inmobiliaria

| Inmobiliaria | id | Props tot. | Geocod. previo | ETAPA 3 | Pendientes | Clasificación |
|---|---|---|---|---|---|---|
| Pagliaro | 4418 | 30 | 29* | 0 | 0 | done (1 outlier limpiado) |
| SV Estudio | 6335 | 10 | 10 | 0 | 0 | done ✅ |
| Angelina | 3531 | 86 | 23* | 0 | 62 | B=35, E=15, F=6, C=0, D=1 |
| Amipropiedades | 945 | 39 | 0 | 0 | 36+3 | D=33, F=2, skipped=3 |
| Vivanco | 4709 | 1 | 0 | 0 | 1 | D=1 |
| Mendocasa | 3532 | 3 | 0 | **2** | 1 | A=2 done, D=1 |
| Sauce | 6732 | 30 | 0 | 0 | 29+1 | C=28, B=1, skipped=1 |

*Pagliaro 30 - 1 outlier = 29 valid. Angelina 24 - 1 outlier = 23 valid.

### Grupo B — Angelina (35 props): por qué no se geocodificaron

`geocode_staging.py` no hace JOIN con tabla `inmobiliarias`. Para las 35 Angelina con
`geocoding_ready_safe`, `ciudad=None` y `provincia=None` en propiedades_staging. Sin contexto de ciudad,
`build_query_variants` genera queries como `"GODOY CRUZ 37, Argentina"` → Nominatim puede devolver
resultados en ciudades incorrectas (Godoy Cruz, Gran Mendoza ≠ General Alvear).

**Fix futuro recomendado:** JOIN a inmobiliarias en `fetch_staging_rows` para pre-popular
`ciudad/provincia` cuando el staging no los tiene. Angelina (id=3531) tiene
`localidad="General Alvear"` en la tabla de inmobiliarias.

### Grupo C — Sauce (28 props): dirección en título

WP Houzez scraper de sauce.com.ar capturó la dirección de calle como título
(ej: "Irigoyen Freyre 2900", "Francia 1200") pero el campo `direccion_normalizada = "-"`.
El geocoder no usa el título como fallback de dirección cuando dir="-".

**Fix futuro recomendado:** en `build_geocoder_row`, si `direccion` es garbage y
`pipeline_extract_address_from_titulo` está disponible, intentar extraer del título.
Ciudad probable: Santa Fe / Sauce Viejo.

### Grupo D — Amipropiedades (33 props)

Todos los títulos son genéricos ("CASA EN VENTA", "DEPARTAMENTO EN VENTA") y
`direccion="-"`. No hay dato recuperable para geocoding. Este CMS (amipropiedades.com.ar)
no expone direcciones en páginas de detalle sin JS.

### Grupo E — Angelina footer text (15 props)

`direccion_normalizada = "brevedad. Enviar Mensaje Copyright © 2026"` — texto del footer
del sitio scrapeado como dirección. El geocoder correctamente los marca `geocoding_ready_review`
y los skippea. Títulos son "Casa en Alquiler" / "Departamento en Alquiler" sin info de ubicación.

### Grupo F — parcial/solo unidad (8 props)

`direccion` = "DPTO 43", "CASA 216", "AV. ALVEAR OESTE DPTO 16", "DPTO 33", etc.
El geocoder marca `geocoding_not_ready`. Algunos tienen la calle (ej "AV. ALVEAR OESTE")
pero con sufijo de unidad que confunde el parser.

---

## FASE 3 — Dry-run completo (131 pending)

Ejecutado: `geocode_staging.py --ids-file staging_ids_pending.csv --limit 200 --dry-run`

| Resultado | Count |
|-----------|-------|
| probe (geocoding_ready_safe) | 39 |
| skipped (all other readiness) | 92 |
| Total leídas | 131 |
| Nominatim calls | 0 (dry-run) |

**Desglose de los 39 probe:**
- 2 Mendocasa (Grupo A, ciudad en dirección) → candidatos para commit
- 35 Angelina (Grupo B, sin ciudad context) → descartados por ambigüedad
- 1 Sauce 81805 (Grupo B, sin ciudad context) → descartado
- 1 Angelina "SALON COMERCIAL 776" / "TALLER 55" → referencia de unidad, no calle (marcados como safe por error del geocoder pero excluidos)

---

## FASE 4 — Geocoding commit (Grupo A: 2 Mendocasa)

### Fix aplicado: `geocode_staging.py` — normalize_address_for_geocoding

El campo `direccion_normalizada` de Mendocasa incluía el prefijo del label HTML:
```
"Address: Maipu 235 - Ciudad Mendoza Mendoza , Mendoza"
```

Sin el fix, la query enviada era `"Address: Maipu 235, Argentina"` → Nominatim
geocodificaba al primer "Maipu 235" encontrado en Argentina (Rosario, Santa Fe).
Coordenadas incorrectas: lat=-32.80, lon=-60.72.

**Fix en `normalize_address_for_geocoding`:**
```python
text = re.sub(r"^address:\s*", "", text, flags=re.IGNORECASE)
text = re.sub(r"^direcci[oó]n:\s*", "", text, flags=re.IGNORECASE)
```

También se pre-popularon `ciudad='Mendoza'` y `provincia='Mendoza'` para los 2 props
antes del commit (el detector automático `normalize_location_fields` no extrae ciudad
de "Ciudad Mendoza" — formato no reconocido).

### Resultados del commit

| Staging ID | Título | Lat | Lon | Ciudad | Precision | Query |
|---|---|---|---|---|---|---|
| 81781 | Venta Deposito — Maipu 235, Mendoza | -32.9110 | -68.8483 | Mendoza | exact | Maipu 235, Mendoza, Mendoza, Argentina |
| 81782 | Venta Terreno — Maipu 243, Mendoza | -32.9110 | -68.8484 | Mendoza | exact | Maipu 243, Mendoza, Mendoza, Argentina |

Coordenadas en Mendoza ciudad ✅ (esperado: lat≈-32.89°S, lon≈-68.85°W)

---

## FASE 5 — Post-geocoding audit

### Estado final por inmobiliaria (props geocodificadas con coords válidas)

| Inmobiliaria | id | Ciudad | Props done | Lat range | Lon range | Outliers |
|---|---|---|---|---|---|---|
| Pagliaro | 4418 | Tandil, Buenos Aires | **29** | [-37.36,-37.28] | [-59.36,-58.80] | 1 limpiado |
| SV Estudio | 6335 | Tandil, Buenos Aires | **10** | [-37.35,-37.30] | [-59.19,-59.09] | 0 |
| Angelina | 3531 | (None/None) | **23** | [-35.00,-34.94] | [-67.80,-67.50] | 1 limpiado |
| Mendocasa | 3532 | Mendoza, Mendoza | **2** | [-32.911,-32.911] | [-68.848,-68.848] | 0 |
| **Total** | | | **64** | | | **2 limpiados** |

### Outliers detectados y limpiados

| Staging ID | Inmobiliaria | Coords incorrectas | Causa | Acción |
|---|---|---|---|---|
| 81820 | Pagliaro (4418) | lat=-37.24, lon=-56.97 (zona costera BA) | "Alameda 210 bis" geocodificado fuera de Tandil (no bbox definida para Tandil en CITY_BBOXES) | latitud/longitud=NULL, status=failed |
| 81777 | Angelina (3531) | lat=-34.62, lon=-68.28 (norte/oeste de General Alvear) | "Propiedad en" (título incompleto) geocodificado fuera del bbox de General Alvear | latitud/longitud=NULL, status=failed |

### Coordenadas repetidas (normal — edificios/mismo predio)

| Coords | Inmobiliaria | Props | Diagnóstico |
|--------|---|---|---|
| (-34.978, -67.689) | Angelina | 3 props | Departamentos mismo edificio ✅ |
| (-34.981, -67.699) | Angelina | 2 props | Departamentos mismo edificio ✅ |
| (-34.980, -67.681) | Angelina | 2 props | Departamentos mismo edificio ✅ |
| (-34.972, -67.699) | Angelina | 2 props | Departamentos mismo edificio ✅ |

### Issue abierto: Angelina ciudad=None, provincia=None

Las 23 props de Angelina con coordenadas tienen `ciudad=None`, `provincia=None` aunque
sus coords están correctamente en General Alvear, Mendoza (lat≈-34.97°S, lon≈-67.69°W).
El `validate_commit` geocoder no extrajo el nombre de la ciudad de los resultados de
Nominatim para General Alvear (posiblemente porque "General Alvear" no está en el
nivel administrativo capturado por el script).

**No es bloqueante**: las coordenadas son correctas y son suficientes para mapa.
Ciudad/provincia puede resolverse via reverse-geocoding en un pass futuro.

---

## Resumen final de geocoding status

| Status | Count | Notas |
|--------|-------|-------|
| done | **64** | Props con coords correctas |
| pending | **129** | Sin geocodificar (ver grupos B–F arriba) |
| skipped | **4** | Ami (3) + Sauce (1) — dirección insuficiente, skipped en validate_commit |
| failed | **2** | Outliers 81820 (Pagliaro) + 81777 (Angelina) — coords limpiadas |
| **Total** | **199** | |

---

## Pendiente: 129 props sin geocodificar

### Por qué no se geocodificaron

| Grupo | Count | Causa raíz | Fix requerido |
|-------|-------|------------|---------------|
| B (Angelina) | 35 | geocode_staging.py sin JOIN a inmobiliarias | Agregar JOIN: `inmobiliarias.localidad` → city context |
| B (Sauce 1 prop) | 1 | Sin ciudad en dirección | Mismo fix |
| C (Sauce 28) | 28 | Dirección en título, no en campo `direccion` | Fallback título-como-dirección en `build_geocoder_row` |
| D (garbage, no data) | 36 | Ami 33 + Mendocasa 1 + Vivanco 1 + Sauce dudoso 1 | No resoluble sin JS scraping |
| E (footer text) | 15 | Angelina footer text en `direccion_normalizada` | Filtro adicional en `is_garbage_address` o skip de URLs de footer |
| F (partial) | 8 | Solo ref de unidad, sin calle+altura | No resoluble sin datos adicionales |
| Angelina pending | 62 | Combinación de B+E+F | Prioridad: fix JOIN inmobiliarias |

### Angelina (62 pending): estimación del impacto del fix

Si se añade JOIN a `inmobiliarias` y se pre-popula `ciudad='General Alvear'`:
- ~35 con `geocoding_ready_safe` → alta probabilidad de geocoding exitoso
- ~15 con footer text → seguirían skipped
- ~8 con partial → seguirían not_ready
- ~4 mixtos

**Ganancia potencial: ~35 props más geocodificadas** con un fix de 5 líneas de SQL.

---

## Fixes aplicados en ETAPA 3

### Fix en `scripts/geocode_staging.py` — normalize_address_for_geocoding

```python
# Fix: strip HTML-label prefixes scrapeados junto con la dirección
# ej. "Address: Maipu 235 - Ciudad Mendoza" → "Maipu 235 - Ciudad Mendoza"
text = re.sub(r"^address:\s*", "", text, flags=re.IGNORECASE)
text = re.sub(r"^direcci[oó]n:\s*", "", text, flags=re.IGNORECASE)
```

**Impacto:** Resuelve el caso Mendocasa donde el scraper captura el label "Address:"
junto con la dirección. Sin el fix, Nominatim recibía `"Address: Maipu 235, Argentina"`
→ no results o resultado en otra ciudad.

---

## Archivos generados en ETAPA 3

| Archivo | Contenido |
|---------|-----------|
| `raw_ids_fase5.csv` | 199 raw IDs usados para validar el scope ETAPA 2/3 (CSV local ignorado por `.gitignore`) |
| `fase3_geocoding_dryrun.md` | Dry-run inicial (20 props, limit=20) |
| `fase3_geocoding_dryrun_full.md` | Dry-run completo (131 props) |
| `fase4_geocoding_group_a_dryrun.md` | Dry-run pre-commit Grupo A |
| `fase4_geocoding_group_a_commit.md` | Commit Grupo A (2 props done) |
| `etapa3_quality_geocoding_summary.md` | Este reporte |

---

## REGLAS ROJAS — Estado ETAPA 3

- NO git push ✅
- NO Supabase publish ✅
- NO publish_to_supabase.py --commit ✅
- NO publish_queue commit ✅
- Geocoding commit solo para Grupo A (alta confianza) ✅
- NO frontend ✅
- NO tocar .env ✅
- NO cambios de schema ✅
- NO borrar datos ✅ (outliers limpiados = UPDATE lat/lon=NULL, no DELETE)
- NO importar más propiedades ✅
- NO Playwright masivo ✅
- NO Zonaprop ni Argenprop ✅
- NO tocar propiedades viejas fuera de los IDs de esta ETAPA ✅

---

## Próximos pasos recomendados (ETAPA 4)

1. **Fix JOIN inmobiliarias en geocode_staging.py** (5 líneas SQL) → desbloquea ~35 Angelina
2. **Agregar Tandil a CITY_BBOXES en geocoder.py** → previene futuros outliers de Pagliaro
3. **Retry 81820 (Pagliaro)** con query manual corregida — "Alameda al 633, Tandil, BA"
4. **Retry 81777 (Angelina)** una vez que city context esté disponible
5. **Investigar Sauce**: ¿puede extractarse dirección del título para 28 props?
6. **General Alvear bbox**: agregar a CITY_BBOXES para validación de Angelina coords
