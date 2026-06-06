# Validate dry-run — 24 propiedades raw → staging

- Fecha: 2026-06-06 17:19
- Modo: dry-run (rollback — sin cambios en Neon)
- Origen: `captured_json` + `scraped_at >= 2026-06-06T00:00:00` + `limit=30`
- Destino: `public.propiedades_staging`
- Props analizadas: las 24 de `internal_batch_20260606_1129` importadas hoy

---

## Resumen ejecutivo

| Métrica | Valor |
|---|---|
| raw_detectadas | 24 |
| candidatas_a_staging | **24** |
| rechazadas | **0** |
| duplicadas en staging | **0** |
| campos críticos faltantes | **0** |
| issues (solo soft) | missing_location × 24 |
| accion_final | rollback (dry-run) |

**Las 24 props pasarían a staging. Cero rechazos.**

---

## Filtros usados para aislar las 24 props

| Filtro | Valor | Propósito |
|---|---|---|
| `--source captured_json` | `datos_extra->>'imported_by' = 'scripts/import_captured_props_to_neon.py'` | Solo props de import capturado |
| `--created-after` | `2026-06-06T00:00:00` | Solo el import de hoy |
| `--limit` | `30` | Techo de seguridad (24 esperadas) |

Resultado: `filas_leidas=24`. Exactamente las 24 del batch. Sin histórico accidental.

---

## Issues por tipo

| Issue | Count | Tipo | Impacto en score |
|---|---|---|---|
| `missing_location` | 24 | Soft | -15 pts |

### Campos críticos (hard issues que bloquean staging)

```
none: 0
```

No hay ningún campo crítico faltante o inválido. Las 24 pasan.

---

## Análisis de validation_score por grupo

El validador calcula `validation_score` empezando en 100. Las penalizaciones aplicables:

| Penalización | Regla | innoacafayate | camposdelapampa | watson |
|---|---|---|---|---|
| -15 missing_location | `ciudad=NULL AND provincia=NULL` | ✓ todos | ✓ todos | ✓ todos |
| -15 missing_type | `tipo_propiedad=None` | ✗ tienen tipo | ✗ campo (Fix E) | ✗ tienen tipo |
| -10 missing_images | sin imágenes válidas | ✗ tienen imágenes | ✗ tienen imágenes | depende¹ |
| -20 missing_price | `precio=None` | 9 no (-20), 8 sí (0) | ✓ todos (-20) | ✓ todos (-20) |
| -5 invalid_address | dirección detectada inválida | ✗ ya nullificadas | ✗ ya nullificadas | ✗ NULL |
| -5 geocoding_skipped | sin dirección Y con ciudad | ✗ ciudad=NULL | ✗ ciudad=NULL | ✗ ciudad=NULL |

¹ Watson: las 3 props tienen imágenes del detalle pero pueden incluir iconos filtrados.

### Scores estimados por prop

| Grupo | Props | Escenario | Score estimado |
|---|---|---|---|
| innoacafayate | 9 | con precio + imágenes | **85** |
| innoacafayate | 8 | sin precio + imágenes | **65** |
| camposdelapampa | 4 | sin precio + imágenes | **65** |
| watson | 3 | sin precio + imágenes | **65** |
| watson | 3 | sin precio + sin imágenes | **55** |

Todos los scores ≥ 55. El validador **no tiene umbral mínimo de score** — solo rechaza por hard issues. El score se usa en etapas posteriores (`build_publish_queue.py`).

---

## geocoding_status de las 24 props en staging

El validador asigna `geocoding_status` según esta lógica:
```
"done"    ← si latitud/longitud ya válidas (ninguna tiene coords)
"skipped" ← si sin dirección normalizada Y tiene ciudad/provincia (ciudad=NULL → no aplica)
"pending" ← todo lo demás
```

**Resultado**: `geocoding_status = "pending"` para las 24.

| Grupo | Props | Situación geocoding |
|---|---|---|
| innoacafayate — 7 props | con `direccion_normalizada` real | pending → geocoder puede intentar con dirección + país=Argentina |
| innoacafayate — 10 props | `direccion_normalizada=NULL` (Fix C) | pending → geocoder no tendrá dirección; skip esperado |
| camposdelapampa — 4 props | `direccion_normalizada=NULL` (Fix D) | pending → skip esperado |
| watson — 3 props | `direccion_normalizada=NULL` | pending → skip esperado |

De las 24, **7 props de innoacafayate** tienen dirección real y podrían geocodificarse con dirección + "Argentina" como contexto.

---

## Detalle por inmobiliaria en staging (si se hace commit)

### innoacafayate.com — 17 props

| Campo en staging | Valor |
|---|---|
| inmobiliaria_id | 5282 |
| operacion | 11 × venta, 6 × alquiler |
| tipo_propiedad | como scrapeado |
| direccion_normalizada | 7 con dirección real, 10 NULL |
| ciudad / provincia | NULL |
| precio | 9 con precio, 8 NULL |
| geocoding_status | pending × 17 |
| validation_score | 85 (con precio) / 65 (sin precio) |

### camposdelapampa.com.ar — 4 props

| Campo en staging | Valor |
|---|---|
| inmobiliaria_id | 1443 |
| operacion | venta |
| tipo_propiedad | campo (4/4) ← Fix E |
| direccion_normalizada | NULL (Fix D) |
| ciudad / provincia | NULL |
| precio | NULL |
| geocoding_status | pending × 4 |
| validation_score | ~65 |

### watsonpropiedades.com — 3 props

| Campo en staging | Valor |
|---|---|
| inmobiliaria_id | 6162 |
| operacion | venta |
| tipo_propiedad | como scrapeado |
| direccion_normalizada | NULL |
| ciudad / provincia | NULL |
| precio | NULL |
| geocoding_status | pending × 3 |
| validation_score | ~55–65 |

---

## ¿Conviene hacer commit a staging?

**Sí — no hay bloqueantes.**

Las 24 pasan sin ningún hard issue. Los únicos issues son soft:
- `missing_location` (24/24) — ya esperado; no bloquea staging, reduce score en 15 pts

### ¿Qué fixes estructurales conviene hacer ANTES del commit?

| Fix | Issue | Impacto | ¿Bloquea staging? |
|---|---|---|---|
| Fix A — location desde hostname | missing_location (24/24) | Mejora score de 85→100 / 65→80 y habilita geocoding | No bloquea, pero mejoraría mucho el geocoding posterior |
| Fix F — watson precio | watson sin precio (3 props) | Mejora score de 55–65 a 65–85 | No bloquea |

Sin Fix A, las 24 entran a staging con `ciudad=NULL`, `provincia=NULL`. El geocoder en etapa posterior intentará con dirección sola (7 props con dirección) o se saltará las demás.

**Recomendación**: Si se quiere que el geocoding sea útil para innoacafayate (Cafayate, Salta), conviene implementar Fix A antes. Pero si el objetivo es avanzar el pipeline, las 24 pasan a staging en estado correcto ahora mismo.

---

## Issues pendientes para ciclos posteriores

| Issue | Fix | Impacto post-staging |
|---|---|---|
| `missing_location` (24) | Fix A — infer desde hostname | 7 innoacafayate geocodificables con ciudad; resto sin coord |
| watson sin precio (3) | Fix F — inspeccionar HTML | 3 props con score bajo en publish_queue |
| título corto (camposdelapampa) | Fix por familia | "Ca266.Html" como título — cosmético en frontend |

---

## Confirmación de seguridad

| Verificación | Estado |
|---|---|
| Supabase tocado | ✗ NO |
| geocoding ejecutado | ✗ NO |
| validate con commit | ✗ NO (solo dry-run) |
| publish_queue modificado | ✗ NO |
| frontend modificado | ✗ NO |
| `.env` modificado | ✗ NO |
| staging rows insertadas | **0** (rollback) |
| git commit | ✗ NO |

---

## Comando para commit a staging (NO ejecutar sin autorización)

```bash
USE_INTERNAL_DB=true python scripts/validate_raw_properties.py \
  --source captured_json \
  --created-after "2026-06-06T00:00:00" \
  --limit 30 \
  --commit \
  --report "reports/scraping_runs/extractor_missing_selector_fix_20260606_1129/validate_raw_commit_24_props.md"
```

**Esperando confirmación antes de ejecutar.**
