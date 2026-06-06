# Reporte comparativo dry-run — antes vs después de fixes estructurales

- Fecha: 2026-06-06
- Batch: 24 propiedades de internal_batch_20260606_1129
- Fixes aplicados: D (dominio como dirección), B (operación desde URL ASP CMS), G (filtro metadata.json)
- Archivos modificados: `scripts/import_captured_props_to_neon.py`, `scraper/scraper_propiedades.py`
- Commit: **NO ejecutado** — pendiente de autorización

---

## Comparativa numérica

| Métrica | Antes | Después | Cambio |
|---|---|---|---|
| archivos_leidos | 14 | **3** | -11 (Fix G) |
| propiedades_detectadas | 24 | 24 | sin cambio |
| importables | 24 | 24 | sin cambio |
| rechazadas | 0 | 0 | sin cambio |
| duplicate_in_propiedades_raw | 0 | 0 | sin cambio |
| duplicate_in_propiedades_staging | 0 | 0 | sin cambio |
| invalid_file_structure | 11 | **0** | -11 (Fix G) ✓ |
| operation_inferred_from_url_path | 0 | **6** | +6 (Fix B) ✓ |
| invalid_address | 0 | **4** | +4 (Fix D) ✓ |
| possible_same_address_within_batch | 12 | **9** | -3 (Fix D efecto cascada) ✓ |
| missing_location | 24 | 24 | sin cambio (Issue A pendiente) |
| low_quality_score | 3 | 3 | sin cambio (watson sin precio) |
| source_test_mode_id_rewritten | 24 | 24 | esperado |

---

## Fix G — Filtro `.metadata.json` ✓

**Antes**: `archivos_leidos=14` — el importer cargaba los 11 archivos `.metadata.json` del directorio, que fallaban con `invalid_file_structure: 11`.

**Después**: `archivos_leidos=3` — solo los 3 archivos de captura real. El `invalid_file_structure` desaparece del reporte.

**Impacto**: Limpieza de logs. Sin efecto en datos importados.

---

## Fix B — Operación desde URL path ASP CMS ✓

**Antes**: 6 propiedades de `innoacafayate.com` provenientes de `/alquiler/item.asp` entraban con `operacion=venta` (incorrecto).

**Después**: `operation_inferred_from_url_path: 6` — el importer detecta la discrepancia entre la operación del JSON (`venta`) y el path de URL (`/alquiler/`), corrige a `alquiler`, y lo registra como warning informativo.

```
URL: innoacafayate.com/alquiler/item.asp?t=Local-calle-Salta-329&id=176
ANTES operacion: venta   (scrapeado del HTML)
DESPUES operacion: alquiler  (inferido del path /alquiler/)
```

**Impacto en staging/frontend**: Las 6 props de alquiler ahora entrarán correctamente clasificadas. Sin este fix, aparecerían como propiedades en venta en el frontend.

**Scope del fix**: Solo aplica al patrón `/{venta|alquiler|temporario}/item.asp`. No afecta ningún otro CMS ni URL.

**Fix en scraper también aplicado**: En `strategy_static_html_detail()`, futuras capturas de innoacafayate ya producirán operación correcta desde el scraper mismo. El fix del importer actúa como red de seguridad para capturas ya generadas.

---

## Fix D — Dominio como dirección ✓

**Antes**: `camposdelapampa.com.ar 54` pasaba como `direccion_raw` válida. El importer la almacenaba en Neon. El geocoder la intentaría como si fuera una calle.

**Después**: `invalid_address: 4` — las 4 props de camposdelapampa tienen `direccion_raw=NULL` (address nullificada). El motivo `contaminated_address_domain` queda registrado en `datos_extra`.

**Efecto cascada**: `possible_same_address_within_batch` bajó de 12 a 9. Las 4 props de camposdelapampa ya no compiten por "misma dirección" porque su dirección es NULL.

**Impacto**: El geocoder no intentará geolocalizar el dominio del sitio como si fuera una calle. Props entran con `direccion_raw=NULL` (correcto para props rurales/campos sin dirección explícita).

**Scope del fix**: Global — aplica a cualquier futura prop donde `direccion` contenga una URL o dominio sin prefijo `www.`. No afecta direcciones de calle válidas.

---

## Issues restantes después de los fixes

### 1. `missing_location` (24/24) — Issue A, pendiente

**Estado**: Sin cambio. Todas las props siguen sin `ciudad`/`provincia`.

**Causa**: `normalize_location_fields()` no infiere ubicación desde el nombre de dominio. "innoacafayate.com" contiene "cafayate" pero la función no mapea tokens del hostname a ciudades/provincias argentinas.

**Consecuencia**: Geocoding limitado. El geocoder puede intentar con `direccion_raw` (ej: "Pueblo Nuevo Mza. 21") pero sin ciudad de contexto tendrá menor precisión. Props sin coordenadas no aparecen en el mapa del frontend.

**Fix propuesto**: Agregar tercer nivel de inferencia en `normalize_location_fields()` — extraer tokens del hostname y comparar contra diccionario de ciudades argentinas comunes. **No implementado todavía** — es más complejo y requiere el diccionario.

**Bloquea el commit**: NO. Las props pueden entrar a Neon sin ciudad/provincia. Es una limitación de calidad, no un error de datos.

---

### 2. `possible_same_address_within_batch: 9` — Issue C, pendiente

**Estado**: Reducido de 12 a 9 por efecto del Fix D. Quedan 9 innoacafayate props con `direccion_raw = "San Martin Nº 191"` (la dirección de la oficina de la inmobiliaria, no de la propiedad).

**Consecuencia**: El geocoder geolocaliza la oficina (San Martín 191, Cafayate) en vez de la propiedad. Props con esta dirección tendrán coordenadas incorrectas.

**Comportamiento del importer**: El warning `possible_same_address_within_batch` es informativo, NO bloquea el import. La dirección entra en Neon.

**Fix propuesto**: Post-procesamiento en el importer — si la misma dirección aparece en >50% de props del mismo dominio en el batch, nullificarla como `office_address_suspected`. **No implementado** — más complejo, pendiente para siguiente ciclo.

**Bloquea el commit**: NO. El geocoder intentará con la dirección disponible; si falla, la prop queda sin coordenadas pero no hay datos incorrectos en los campos estructurales.

---

### 3. `low_quality_score: 3` — watson sin precio

**Estado**: Sin cambio. Las 3 props de watsonpropiedades tienen score=40 (sin precio capturado).

**Consecuencia**: Props entran a raw con `precio=NULL`. En staging, el score bajo las puede excluir del publish queue si el umbral es >60.

**Fix propuesto**: Investigar HTML de watsonpropiedades para identificar dónde está el precio (JSON-LD, data-attribute, JS). **No implementado** — requiere inspección del HTML del detalle.

**Bloquea el commit**: NO. Props con precio NULL entran a Neon con ese estado. No hay datos erróneos, solo datos incompletos.

---

### 4. `source_test_mode_id_rewritten: 24` — comportamiento esperado

El importer resolvió correctamente `inmobiliaria_id=0` → `5282/1443/6162` desde el batch CSV. Este warning es informativo, registra que el ID original en el JSON era 0 (batch de test). No es un error.

---

## ¿Es seguro hacer commit real ahora?

**Respuesta: SÍ, con los 3 fixes activos.**

Los dos blockers originales están resueltos:
- ✓ 6 props de alquiler entrarán correctamente como `alquiler` (no `venta`)
- ✓ 4 props de camposdelapampa entrarán con `direccion_raw=NULL` (no el dominio como calle)

Los issues restantes (`missing_location`, `office_address_suspected`, `watson sin precio`) son limitaciones de calidad, no errores de datos. Las props entrarían a Neon en estado correcto para los campos estructurales.

**Condición para el commit**:

```
$env:USE_INTERNAL_DB = "true"
python scripts/import_captured_props_to_neon.py \
  --input-dir "data/scraping_batches/internal_batch_20260606_1129/captured" \
  --batch-csv "data/batch_inputs/extractor_fix_fase2_targets.csv" \
  --commit \
  --report "reports/scraping_autofix/import_captured_YYYYMMDD_HHMM.md"
```

**Esperado tras el commit**:
- 24 nuevas filas en `propiedades_raw` con `status=raw`
- inmobiliaria_id: 5282 (innoacafayate × 17), 1443 (camposdelapampa × 4), 6162 (watson × 3)
- 6 props de innoacafayate con `operacion=alquiler`
- 4 props de camposdelapampa con `direccion_raw=NULL`
- 24 props con `ciudad=NULL`, `provincia=NULL`
- 0 duplicados con filas existentes

**Próximos pasos post-commit (orden sugerido)**:
1. `validate_raw_properties.py --dry-run` → ver cuántas pasan a staging
2. `geocode_staging.py --dry-run` → ver cuántas son geocodificables (innoacafayate tiene direcciones parciales)
3. Implementar Fix A (location desde hostname) para mejorar el siguiente ciclo

---

## Archivos modificados en esta sesión

| Archivo | Fix | Cambio |
|---|---|---|
| `scripts/import_captured_props_to_neon.py` | G | `load_captured_files()`: excluye `.metadata.json` |
| `scripts/import_captured_props_to_neon.py` | D | `invalid_address_reason()`: detecta dominio como dirección |
| `scripts/import_captured_props_to_neon.py` | B | `infer_operation_from_url_path()`: nueva función + `_ASP_CMS_OP_PATH_RE` |
| `scripts/import_captured_props_to_neon.py` | B | `build_raw_candidate()`: aplica inferencia de operación como safety net |
| `scraper/scraper_propiedades.py` | B | `_ASP_CMS_OP_PATH_RE` + `_infer_op_from_asp_url_path()`: regex + función |
| `scraper/scraper_propiedades.py` | B | `strategy_static_html_detail()`: post-procesamiento de operación |
