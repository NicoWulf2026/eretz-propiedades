# Reporte comparativo final — 4 rondas de dry-run

- Fecha: 2026-06-06
- Batch: 24 propiedades de internal_batch_20260606_1129
- Fixes aplicados en orden: G → D → B → C → E
- Archivos modificados: `scripts/import_captured_props_to_neon.py`, `scraper/scraper_propiedades.py`
- Commit: **NO ejecutado** — pendiente de autorización

---

## Tabla comparativa

| Métrica | DR-1 (sin fixes) | DR-2 (G+D+B) | DR-3 (+C) | DR-4 (+E) |
|---|---|---|---|---|
| archivos_leidos | 14 | **3** | 3 | 3 |
| propiedades_detectadas | 24 | 24 | 24 | 24 |
| importables | 24 | 24 | 24 | 24 |
| rechazadas | 0 | 0 | 0 | 0 |
| duplicate_in_raw | 0 | 0 | 0 | 0 |
| duplicate_in_staging | 0 | 0 | 0 | 0 |
| invalid_file_structure | 11 | **0** | 0 | 0 |
| operation_inferred_from_url_path | 0 | **6** | 6 | 6 |
| invalid_address | 0 | **4** | 4 | 4 |
| office_address_suspected | 0 | 0 | **10** | 10 |
| possible_same_address_within_batch | 12 | 9 | **0** | 0 |
| tipo_inferred_from_rural_domain | 0 | 0 | 0 | **3** |
| missing_type | — | — | — | **0** |
| missing_location | 24 | 24 | 24 | 24 |
| low_quality_score | 3 | 3 | 3 | 3 |
| source_test_mode_id_rewritten | 24 | 24 | 24 | 24 |

---

## Fix G — `load_captured_files()`: ignorar `.metadata.json`

**Clasificación**: Fix global.

**Antes** (DR-1): `archivos_leidos=14` — 11 archivos `.metadata.json` producían `invalid_file_structure: 11`.

**Después** (DR-2+): `archivos_leidos=3`. `invalid_file_structure` eliminado del reporte.

---

## Fix D — `invalid_address_reason()`: dominio como dirección

**Clasificación**: Fix global.

**Antes** (DR-1): `camposdelapampa.com.ar 54` pasaba como dirección válida.

**Después** (DR-2+): `invalid_address: 4` — 4 props con `direccion_raw=NULL`. Motivo `contaminated_address_domain` en `datos_extra`.

**Efecto cascada**: `possible_same_address_within_batch` bajó 12→9 porque las 4 props de camposdelapampa ya no contribuyen al tracking.

---

## Fix B — Operación desde URL path (familia ASP CMS)

**Clasificación**: Fix por familia — ASP CMS con subfolder de operación.

**Antes** (DR-1): 6 props de `innoacafayate.com/alquiler/item.asp` tenían `operacion=venta`.

**Después** (DR-2+): `operation_inferred_from_url_path: 6` — operación corregida a `alquiler`. También aplicado en scraper para futuras capturas.

---

## Fix C — `detect_office_addresses()`: dirección de oficina repetida

**Clasificación**: Fix global con umbral por dominio/batch.

**Antes** (DR-2): `possible_same_address_within_batch: 9` — 10 props de innoacafayate con `direccion_raw = "San Martin Nº 191"` (oficina de la inmobiliaria).

**Después** (DR-3+): `office_address_suspected: 10` — 10 props con `direccion_raw=NULL`. Dirección original + ratio en `datos_extra`. `possible_same_address_within_batch: 0`.

**Umbral**: >50% del mismo host, mínimo 5 props. 10/17 = 58.8% → actúa.

---

## Fix E — `infer_tipo_from_rural_domain()`: tipo_propiedad en short-ID rural CMS

**Clasificación**: Fix por familia — CMS con short-ID URLs (`/ca266.html`, `/mo340.html`, `/mi319.html`).

**Causa raíz**: `_html_extract_detail()` usa `page_text[:300]` como fallback para inferir tipo. En camposdelapampa, el HTML contiene "departamento" en la navegación antes de cualquier señal rural → TIPO_MAP encuentra "departamento" antes que "campo" (orden de inserción del dict). Solo `mo342.html` fue correcto porque ese HTML particular tenía "campo" en una posición más temprana del page_text.

**Antes** (DR-3): 3 props con `tipo_propiedad=departamento` (ca266, mo340, mi319). 1 prop correcta con `tipo_propiedad=campo` (mo342).

**Después** (DR-4): `tipo_inferred_from_rural_domain: 3` — 3 props corregidas a `campo`. `mo342` (ya `campo`) no fue tocada.

**Condiciones del fix**:
- URL matchea `/[a-z]{2,3}\d{3,6}\.html` (short-ID: ca266, mo340, mi319)
- Hostname contiene señal rural: `campo`, `campos`, `rural`, `agro`, `pampa`, `hectarea`, `haras`, `estancia`, `chacra`
- `tipo_actual` NO está en `_RURAL_TIPO_VALUES` = {campo, chacra, estancia, finca, quinta}

**Tests validados** (10/10):
- `camposdelapampa.com.ar/ca266.html` tipo=departamento → corrección a campo ✓
- `camposdelapampa.com.ar/mo342.html` tipo=campo → NO toca ✓
- URL urbana `/departamento-en-venta-123` → NO toca ✓
- Hostname sin señales rurales + short-ID → NO toca ✓
- `estancialaverde.com/es001.html` tipo=departamento → corrección a campo ✓

**Doble fix**: También aplicado en `strategy_static_html_detail()` del scraper → futuras capturas producirán `tipo_propiedad=campo` desde el scraper sin necesitar la corrección del importer.

---

## Estado final de las 24 propiedades (dry-run 4)

### innoacafayate.com — 17 props

| Campo | Estado |
|---|---|
| inmobiliaria_id | 5282 (resuelto desde batch CSV) |
| operacion | 11 × venta, 6 × alquiler ✓ (Fix B) |
| tipo_propiedad | asignado por scraper (no corregido por Fix E — hostname no es rural) |
| direccion_raw | 7 props con dirección real; 10 props NULL (Fix C office address) |
| ciudad / provincia | NULL (pendiente Fix A) |

### camposdelapampa.com.ar — 4 props

| Campo | Estado |
|---|---|
| inmobiliaria_id | 1443 (resuelto) |
| operacion | venta |
| tipo_propiedad | 4 × campo ✓ (1 ya correcto, 3 corregidos por Fix E) |
| direccion_raw | NULL (Fix D domain address) |
| ciudad / provincia | NULL (pendiente Fix A) |
| precio | NULL (no hay precio en HTML estático) |

### watsonpropiedades.com — 3 props

| Campo | Estado |
|---|---|
| inmobiliaria_id | 6162 (resuelto) |
| operacion | venta |
| tipo_propiedad | asignado por scraper |
| direccion_raw | NULL (sin dirección en página) |
| precio | NULL (pendiente Fix F) |
| score_calidad | 40 (low_quality_score) |

---

## Issues restantes (no bloquean commit)

### missing_location (24/24) — Issue A

**Estado**: Sin fix. Requiere diccionario de ciudades argentinas + extracción de tokens del hostname.

**Consecuencia**: Props entran con `ciudad=NULL`, `provincia=NULL`. Geocoding menos preciso.

**¿Bloquea commit?**: No.

---

### low_quality_score (3/3 watson) — Issue F

**Estado**: Sin fix. Precio de watson no está en HTML estático.

**Consecuencia**: 3 props con `precio=NULL`, `score=40`. Pueden no pasar staging si el umbral es >40.

**¿Bloquea commit?**: No.

---

## ¿Es seguro hacer commit real ahora?

**Respuesta: SÍ. Todos los errores de datos incorrectos están resueltos.**

| Issue original | Fix | Estado en DR-4 |
|---|---|---|
| 6 alquileres scrapeados como venta | Fix B | ✓ `operacion=alquiler` |
| Dominio como dirección (4 props) | Fix D | ✓ `direccion_raw=NULL` |
| `.metadata.json` en logs | Fix G | ✓ Filtrado |
| Dirección de oficina (10 props) | Fix C | ✓ `direccion_raw=NULL` |
| 3 props rurales como `departamento` | Fix E | ✓ `tipo_propiedad=campo` |

Los 2 issues restantes (`missing_location`, `watson sin precio`) son **datos incompletos**, no datos incorrectos. Las 24 props entrarían a Neon en estado estructuralmente limpio.

---

## Comando de commit (NO ejecutar sin autorización)

```
USE_INTERNAL_DB=true python scripts/import_captured_props_to_neon.py \
  --input-dir "data/scraping_batches/internal_batch_20260606_1129/captured" \
  --batch-csv "data/batch_inputs/extractor_fix_fase2_targets.csv" \
  --commit \
  --report "reports/scraping_autofix/import_captured_YYYYMMDD_HHMM.md"
```

**Resultado esperado en Neon**:
- 24 nuevas filas en `propiedades_raw` con `status=raw`
- 6 props innoacafayate con `operacion=alquiler`
- 4 props camposdelapampa con `tipo_propiedad=campo`
- 14 props con `direccion_raw=NULL` (10 office + 4 domain)
- 24 props con `ciudad=NULL`, `provincia=NULL`
- 0 colisiones de hash con props existentes

---

## Resumen de archivos modificados en toda la sesión

| Archivo | Fix | Descripción |
|---|---|---|
| `scripts/import_captured_props_to_neon.py` | G | `load_captured_files()` excluye `.metadata.json` |
| `scripts/import_captured_props_to_neon.py` | D | `invalid_address_reason()` detecta dominio sin `www.` |
| `scripts/import_captured_props_to_neon.py` | B | `infer_operation_from_url_path()` + `_ASP_CMS_OP_PATH_RE` |
| `scripts/import_captured_props_to_neon.py` | B | `build_raw_candidate()` safety net de operación |
| `scripts/import_captured_props_to_neon.py` | C | `detect_office_addresses()` + llamada en `main()` |
| `scripts/import_captured_props_to_neon.py` | E | `infer_tipo_from_rural_domain()` + constantes + llamada |
| `scraper/scraper_propiedades.py` | B | `_ASP_CMS_OP_PATH_RE` + `_infer_op_from_asp_url_path()` |
| `scraper/scraper_propiedades.py` | B | `strategy_static_html_detail()` — corrección de operación |
| `scraper/scraper_propiedades.py` | E | `_RURAL_SHORTID_URL_RE` + `_RURAL_DOMAIN_SIGNALS` + `_RURAL_TIPO_VALUES` |
| `scraper/scraper_propiedades.py` | E | `_infer_tipo_from_rural_shortid_url()` |
| `scraper/scraper_propiedades.py` | E | `strategy_static_html_detail()` — corrección de tipo |
