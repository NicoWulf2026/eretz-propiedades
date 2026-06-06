# Dry-run import — 24 propiedades capturadas (extractor_missing_selector fix)

- Fecha: 2026-06-06
- Modo: **dry-run** — sin escrituras reales en Neon
- Input dir: `data/scraping_batches/internal_batch_20260606_1129/captured/`
- Batch CSV: `data/batch_inputs/extractor_fix_fase2_targets.csv`
- Script: `scripts/import_captured_props_to_neon.py --dry-run`
- Report generado por: importer + análisis manual
- Commit autorizado: **NO**

---

## Resumen ejecutivo

| Métrica | Valor |
|---|---|
| Archivos leídos | 14 (3 capturas + 11 .metadata.json filtrados) |
| Propiedades detectadas | 24 |
| Propiedades procesadas | 24 |
| **Importables** | **24** |
| Importadas | 0 (dry-run) |
| Rechazadas (hard reject) | 0 |
| Con warnings | 24 |
| Duplicados en Neon raw | **0** |
| Duplicados en Neon staging | **0** |
| Cross-agency en Neon | 0 |

**Conclusión general**: Las 24 propiedades son nuevas, no existen en Neon. Técnicamente importables. Hay 4 issues de calidad de datos que deben resolverse a nivel de scraper antes del commit real.

---

## Duplicados (detalle)

### Bloqueantes — ninguno
- duplicate_exact_same_source (batch): 0
- skipped_duplicate_in_propiedades_raw: 0
- skipped_duplicate_in_propiedades_staging: 0

### Marcados (no bloqueantes)
- possible_cross_agency_within_batch: 0
- possible_cross_agency_in_neon: 0
- **possible_same_address_within_batch: 12** → ver Issue C + D

---

## Issues por dominio

### innoacafayate.com — 17 props

| Issue | Count | Importer lo detecta | Bloqueante |
|---|---|---|---|
| missing_location | 17 | Sí (logged) | No (warning) |
| operacion incorrecta (alquiler→venta) | 6 | **NO** | No (pasa como venta) |
| direccion = oficina ("San Martin Nº 191") | 10 | Parcial (same_address) | No (marcado) |
| source_test_mode_id_rewritten | 17 | Sí (logged) | No (resuelto) |

### camposdelapampa.com.ar — 4 props

| Issue | Count | Importer lo detecta | Bloqueante |
|---|---|---|---|
| missing_location | 4 | Sí (logged) | No |
| tipo_propiedad incorrecto ("departamento") | 3 | **NO** | No |
| titulo = filename ("Ca266.Html") | 4 | **NO** | No |
| direccion = dominio ("camposdelapampa.com.ar 54") | 4 | **NO** | No |
| possible_same_address_within_batch | 3 | Sí | No |
| source_test_mode_id_rewritten | 4 | Sí | No |

### watsonpropiedades.com — 3 props

| Issue | Count | Importer lo detecta | Bloqueante |
|---|---|---|---|
| missing_location | 3 | Sí (logged) | No |
| precio ausente | 3 | No (missing_price no existe) | No |
| low_quality_score (score=40) | 3 | Sí (logged) | No |
| source_test_mode_id_rewritten | 3 | Sí | No |

---

## Clasificación de cada issue

---

### Issue A — missing_location (24/24)

**Clasificación: Fix global**

**Causa raíz**: El scraper no extrae `ciudad`/`provincia` desde las páginas de detalle de ninguno de los 3 dominios nuevos. La función `normalize_location_fields()` tampoco infiere desde URL ni dominio (no hay `location_inferred_from_text` en los logs → la inferencia también falló para los 24 props).

**Evidencia**:
- `innoacafayate.com` → "cafayate" está en el dominio, claramente señala Cafayate, Salta
- `camposdelapampa.com.ar` → "pampa" en dominio → La Pampa (provincia)
- `watsonpropiedades.com` → sin señal en dominio, pero slugs como `/casa-en-zona-centro-...` contienen "zona Centro"

**Otros dominios beneficiados**: Cualquier dominio donde la ubicación está en el nombre del dominio (patrón común en inmobiliarias regionales argentinas): ej. `inmoviedma.com.ar`, `cordobapropiedades.com.ar`, `tucumanprop.com.ar`.

**Riesgo global**: Bajo — lógica aditiva, no rompe extracción existente. Riesgo de falso positivo si el dominio contiene un topónimo ambiguo (ej. "pampa" también puede ser un barrio), mitigable con threshold de confianza.

**Fix propuesto**: En `normalize_location_fields()` (scraper) — agregar un tercer nivel de inferencia cuando `ciudad` y `provincia` siguen vacías después de los intentos existentes:
1. Extraer palabras del hostname (sin TLD, sin "www", sin "inmobiliaria/propiedades/bienes"): ej. `innoacafayate` → tokens ["ino", "cafayate"]
2. Comparar cada token contra un diccionario de ciudades y provincias argentinas comunes (~200 entradas)
3. Si hay match con confidence ≥ 0.8, asignar ciudad/provincia correspondiente

**No implementar como hardcode por dominio** — usar el diccionario general.

**Métrica de validación**: % de props con `missing_location` en batches de prueba. Antes: 100% (24/24). Después esperado: <30% (solo props de dominios sin señal de ubicación).

---

### Issue B — operacion incorrecta: `/alquiler/` → JSON dice `venta` (6/17 innoacafayate)

**Clasificación: Fix por familia** — ASP CMS argentino con subfolder de operación

**Causa raíz**: El scraper extrae `operacion` del HTML de la página de detalle, no del path de la URL. Cuando la página de listado es `/propiedades` (mixta: venta + alquiler), el scraper sigue todos los links incluyendo los de `/alquiler/item.asp`. Al scraping de ese detalle, extrae la operacion del HTML — pero si el HTML no tiene un marcador claro de "alquiler" (o el scraper no detecta el patrón), defaultea a "venta" o a lo que encontró.

**Evidencia**: 6 props con URL `innoacafayate.com/alquiler/item.asp?t=...` pero `operacion=venta` en el JSON.

**El importer NO detecta esto** — "venta" es una operación válida, pasa sin warning.

**Otros dominios beneficiados**: Cualquier ASP CMS con la estructura `/{venta|alquiler|temporario}/item.asp`. El mismo patrón de URL que ya se agregó a `_looks_like_real_property_url()` debería usarse también para inferir la operación.

**Riesgo global**: Bajo si se aplica solo a la familia ASP CMS con este patrón de URL. El regex ya existe — solo hay que extraer el subfolder.

**Fix propuesto** — Fix por familia en el scraper:
En `_extract_generic_property_links()`, cuando se detecta una URL que matchea el patrón ASP CMS (`/{operation}/item.asp`), inyectar la operación en los datos de la propiedad antes de scrapear el detalle. Específicamente, si el URL path contiene `/alquiler/` o `/temporario/`, sobreescribir `operacion` DESPUÉS de parsear el detalle HTML.

Implementación sugerida (pseudo-código):
```python
# En el punto donde se construye el dict de la propiedad para ASP CMS detail:
if re.search(r'/(alquiler|temporario)/', detail_url, re.I):
    prop['operacion'] = 'alquiler'  # o alquiler_temporario
elif re.search(r'/(venta|ventas)/', detail_url, re.I):
    prop['operacion'] = 'venta'
```

**Métrica de validación**: 0 props con `operacion=venta` cuando el URL path dice `/alquiler/`.

---

### Issue C — Dirección de oficina como dirección de propiedad (10/17 innoacafayate)

**Clasificación: Fix por familia** — ASP CMS argentino

**Causa raíz**: El template HTML de innoacafayate (y probablemente otros ASP CMS argentinos) embebe la dirección de contacto de la inmobiliaria en cada ficha de propiedad. El scraper extrae este campo como la dirección de la propiedad. Resultado: 10 de 17 fichas tienen exactamente "San Martin Nº 191" (la calle del negocio).

**Evidencia**: `possible_same_address_within_batch: 9` para "san martin nº 191" en batch de 17 props.

**El importer lo detecta PARCIALMENTE**: Marca como `possible_same_address_within_batch` pero NO bloquea ni filtra. La misma dirección queda en Neon.

**Otros dominios beneficiados**: Cualquier ASP CMS que repita la dirección de la inmobiliaria en cada ficha.

**Riesgo**: Medio — una detección post-hoc de "dirección repetida = dirección de oficina" podría nullificar direcciones válidas si muchas propiedades genuinamente están en el mismo edificio/cuadra. Mitigable con un umbral alto (>40% de props del dominio tienen la misma dirección).

**Fix propuesto — 2 opciones**:

Opción 1 (Fix por familia — scraper): En el parser de ASP CMS, identificar y excluir el bloque de contacto/footer cuando extrae `direccion`. Requiere análisis del HTML de innoacafayate para ubicar el selector CSS del bloque de contacto.

Opción 2 (Fix global — importer post-processing): En `build_raw_candidate()`, si la dirección raw ya aparece en más del 50% de las props del mismo dominio en el mismo batch, marcarla como `office_address_suspected` y nullificarla. Este fix es más robusto porque funciona independientemente del CMS.

**Recomendación**: Opción 2 es más segura y general. No requiere análisis de HTML por dominio.

**Métrica de validación**: `possible_same_address_within_batch` < 5% de props por dominio en batch de test.

---

### Issue D — Dominio como dirección de propiedad (4/4 camposdelapampa)

**Clasificación: Fix global** — gap en `GARBAGE_ADDRESS_PATTERNS`

**Causa raíz**: El scraper de camposdelapampa extrae el footer del sitio (que contiene el dominio y el código de área: "camposdelapampa.com.ar 54") como la `direccion` de la propiedad. El validador `invalid_address_reason()` del importer no detecta strings con extensiones de dominio sin prefijo "www.".

**Evidencia**: `direccion = "camposdelapampa.com.ar 54"` en 4/4 props. No flaggeado por el importer como `contaminated_address`.

**Gap estructural**: `GARBAGE_ADDRESS_PATTERNS` incluye `"www."`, `"http://"`, `"https://"` pero NO detecta dominios sin prefijo (`ejemplo.com.ar`).

**Otros dominios beneficiados**: Cualquier dominio que embebe su URL/dominio en el template de ficha. Mejora la calidad de dirección globalmente.

**Riesgo**: Bajo. Un address legítimo conteniendo `.com` es extremadamente raro en Argentina.

**Fix propuesto — Fix global en `invalid_address_reason()`**:

```python
# Agregar a GARBAGE_ADDRESS_PATTERNS o como check adicional:
if re.search(r'\b\w+\.(?:com\.ar|net\.ar|org\.ar|com|net|org)\b', lowered):
    return "contaminated_address_domain"
```

Aplicado en `import_captured_props_to_neon.py` → `invalid_address_reason()`. También debería agregarse al scraper si extrae y valida direcciones internamente.

**Métrica de validación**: "camposdelapampa.com.ar 54" debe retornar `contaminated_address_domain` en el validator.

---

### Issue E — Título y tipo_propiedad incorrectos (4/4 camposdelapampa)

**Clasificación: Fix por familia** — CMS con short-ID URLs (`/ca266.html`, `/mo342.html`)

**Causa raíz**: Las URLs tipo `/ca266.html` no proveen metadata. El scraper usa el filename como título fallback ("Ca266.Html") y defaultea `tipo_propiedad=departamento` cuando no encuentra señal en la URL.

**Evidencia**:
- `titulo = "Ca266.Html"` — claramente el filename, no el título real
- `tipo_propiedad = "departamento"` para una inmobiliaria llamada "Campos de la Pampa" que solo vende campos

**El importer NO detecta esto** — "Ca266.Html" no está en UI_TITLE_PATTERNS y "departamento" es un tipo válido.

**Fix propuesto — Fix por familia**:
1. **Título**: En el parser de short-ID pages, extraer el `<title>` o `<h1>` de la página de detalle en lugar de derivar desde el filename. El scraper ya fetchea el HTML del detalle — el `<title>` debería estar disponible.
2. **Tipo**: En `normalizar_tipo()`, si `tipo_propiedad` es "departamento" o "otro" pero el dominio pertenece a una inmobiliaria especializada (e.g., nombre contiene "campo", "campo", "rural", "agrícola"), hacer un segundo intento de inferencia desde el body HTML.
3. **Alternativa global**: Si `normalizar_tipo()` recibe un tipo "departamento" pero la descripción contiene palabras como "campo", "hectárea", "rural", "agrícola", "lote rural", sobrescribir con "campo".

**Riesgo**: Medio — el fix 3 podría reclasificar mal departamentos mencionados en descripciones rurales. Acotarlo a cuando `tipo_propiedad == "departamento" AND descripcion contains rural keywords AND inmobiliaria name contains "campo"`.

**Métrica de validación**: Títulos de camposdelapampa props deben ser descriptivos (no filenames). Tipos deben ser "campo" para esta inmobiliaria.

---

### Issue F — watson sin precio (3/3)

**Clasificación: Fix por familia** — clean-slug CMS

**Causa raíz**: El precio no está en el HTML estático de las páginas de detalle de watsonpropiedades.com, o está en un formato no reconocido por el scraper. El `infer_price_from_text()` del importer tampoco lo encuentra desde título/descripción/URL.

**A investigar antes de fijar**: Ver el HTML real del detalle de watson para confirmar:
- ¿Está el precio en JSON-LD (`<script type="application/ld+json">`)? → fix global (parsear JSON-LD)
- ¿Está en un data-attribute? → fix por familia
- ¿Solo en JS dinámico? → requiere Playwright (no fixable sin render)
- ¿En un iframe? → complejidad alta

**Métrica de validación**: % de props de watson con precio capturado.

---

### Issue G — invalid_file_structure: 11

**Clasificación: No es un issue real** — comportamiento esperado

Los 11 archivos `.metadata.json` son capturados por `*.json` glob y filtrados al verificar `payload.get("props")`. Reportado como `invalid_file_structure` pero no afecta la importación. El valor `files_read=14` es confuso pero no incorrecto.

**Fix opcional**: En `load_captured_files()`, filtrar explícitamente archivos que terminen en `.metadata.json`:
```python
files = sorted(f for f in input_dir.glob("*.json") if not f.name.endswith(".metadata.json"))
```
Clasificación: **Fix global** (limpieza del importer). Bajo riesgo, mínimo impacto.

---

## ¿Es seguro hacer commit real ahora?

**Respuesta: CONDICIONALMENTE.** El commit NO rompe nada en Neon, pero los datos que entrarían tienen issues de calidad estructurales.

### Lo que entraría en Neon sin correcciones previas:

| Issue | Consecuencia en Neon raw | Consecuencia downstream |
|---|---|---|
| missing_location (24/24) | ciudad=NULL, provincia=NULL | Geocoding fallará (sin dirección completa); filtros de ciudad en frontend vacíos |
| operacion=venta para 6 alquileres | operacion incorrecto en raw | Props de alquiler aparecerán como venta en staging + frontend |
| direccion = oficina (10 innoacafayate) | direccion_raw contaminada | Geocoding podría geolocalizar la inmobiliaria, no la propiedad |
| direccion = dominio (4 campos) | direccion_raw inválida | Geocoding fallará (no es una calle) |
| titulo = filename (4 campos) | titulo ilegible | Frontend mostraría "Ca266.Html" como título de propiedad |
| tipo = departamento (3 campos) | tipo incorrecto | Frontend clasificaría campos rurales como departamentos |
| precio ausente (15/24) | precio=NULL | 62% sin precio en frontend |

### Recomendación para el commit:

No hacer `--commit` hasta que se implementen al menos:
1. **Fix D (global, simple)**: Agregar detección de dominio-como-dirección en `invalid_address_reason()` → impide que "camposdelapampa.com.ar 54" entre en Neon.
2. **Fix B (familia, simple)**: Corrección de operación desde URL path en ASP CMS → impide que 6 props de alquiler entren como venta.

Los fixes A, C, E, F son importantes pero más complejos. Pueden hacerse en el ciclo siguiente antes del próximo scraping run.

---

## Orden de prioridad de los fixes

| # | Issue | Scope | Complejidad | Impacto | Prioridad |
|---|---|---|---|---|---|
| D | Dominio como dirección | Global (importer) | Baja | Medio | **1** |
| B | Operación desde URL path | Familia (ASP CMS) | Baja | Alto | **2** |
| G | Filtro .metadata.json | Global (importer) | Muy baja | Bajo | **3** |
| A | Location desde dominio | Global (scraper) | Media | Muy alto | **4** |
| C | Office address detection | Global (importer) | Media | Alto | **5** |
| E | Título/tipo short-ID | Familia (short-ID) | Media | Medio | **6** |
| F | Precio watson | Familia (clean-slug) | Alta (requiere inspección HTML) | Bajo | **7** |

---

## Seguridad del dry-run

- no_toca_supabase: true
- no_publica_supabase: true
- no_toca_publish_queue: true
- no_modifica_env: true
- no_borra_datos: true
- no_commit_git: true
- no_push_git: true
- neon_write: false (dry-run/no-writes confirmado)
