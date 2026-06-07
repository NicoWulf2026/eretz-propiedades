# Fix L — Corrección de Coordenadas Fuera de Bbox — Reporte

**Fecha:** 2026-06-07  
**Fix:** L — Geographic Bbox Validation  
**Operación:** UPDATE controlado — 3 propiedades con geocoding_status=done corregidos a failed  
**Archivos modificados:** `scraper/geocoder.py` (CITY_BOUNDS), DB (propiedades_staging + geocoding_results)

---

## Causa raíz

`CITY_BOUNDS` en `scraper/geocoder.py` no incluía las ciudades activas de InmoCapital:
**Rawson, Playa Unión, Pergamino, Tandil**.

La función `evaluate_city_bounds(lat, lon, ciudad, ...)` retorna `(within, checked)`.
Si la ciudad no está en `CITY_BOUNDS`, retorna `(None, False)` → `checked=False`.

La función `coords_are_valid()` en `geocode_staging.py` interpreta `checked=False` como
"sin restricción geográfica conocida" → acepta cualquier coordenada incondicionalmente.

Por eso, durante el geocoding commit del 2026-06-07, 3 propiedades de Rawson quedaron
geocodeadas con coordenadas en ciudades incorrectas (Trelew / Puerto Madryn) sin ser rechazadas.

---

## Corrección aplicada — `scraper/geocoder.py`

Se agregaron 4 entradas a `CITY_BOUNDS`:

```python
# Fix L — ciudades activas InmoCapital
"rawson":      (-43.40, -43.25, -65.20, -65.00),  # excluye Trelew (lon ~-65.31) y Puerto Madryn (lat ~-42.76)
"playa union": (-43.40, -43.28, -65.12, -64.98),  # barrio costero adyacente a Rawson
"pergamino":   (-33.96, -33.80, -60.68, -60.50),  # Pergamino, Buenos Aires
"tandil":      (-37.42, -37.25, -59.22, -59.00),  # Tandil, Buenos Aires
```

Post-Fix L: `evaluate_city_bounds` retorna `checked=True` para estas ciudades.
Coordenadas fuera de bbox → `within=False` → `coords_are_valid()` retorna `False` → geocoding rechazado.

---

## IDs corregidos

### Estado antes del UPDATE

| staging_id | ciudad | geocoding_status | latitud | longitud | gr.status | gr.precision | Problema |
|------------|--------|-----------------|---------|----------|-----------|--------------|---------|
| 81293 | Rawson | done | -43.2848056 | -65.2949381 | success | street | Lon -65.295 = Trelew (fuera bbox Rawson -65.20 a -65.00) |
| 81294 | Rawson | done | -42.7635438 | -65.0350863 | success | exact | Lat -42.763 = Puerto Madryn (fuera bbox Rawson -43.40 a -43.25) |
| 81306 | Rawson | done | -43.252961  | -65.3086085 | success | exact | Lon -65.309 = Trelew (fuera bbox Rawson -65.20 a -65.00) |

### Contexto de cada caso

| staging_id | Dirección geocodificada | Diagnóstico |
|------------|------------------------|-------------|
| 81293 | `Amancay N° 186, Rawson, Chubut, Argentina` | Calle "Amancay" existe en Trelew; Nominatim devolvió coordenadas trelenses |
| 81294 | `Rawson 14, Chubut, Argentina` | Dirección ambigua: "Rawson" como nombre de calle; Nominatim la resolvió en Puerto Madryn (calle homónima) |
| 81306 | `Rivadavia 360, Rawson, Chubut, Argentina` | "Rivadavia 360" existe en Trelew; Nominatim priorizó esa ciudad |

### Verificación bbox post-Fix L (pre-update)

```
81293: evaluate_city_bounds(-43.2848, -65.2949, "rawson") → within=False, checked=True ✅
81294: evaluate_city_bounds(-42.7635, -65.0351, "rawson") → within=False, checked=True ✅
81306: evaluate_city_bounds(-43.2530, -65.3086, "rawson") → within=False, checked=True ✅
```

---

## UPDATE ejecutado

**Transacción única — COMMIT OK (2026-06-07)**

### UPDATE 1 — propiedades_staging

```sql
UPDATE propiedades_staging
SET
    geocoding_status = 'failed',
    latitud          = NULL,
    longitud         = NULL
WHERE id = ANY(ARRAY[81293, 81294, 81306])
  AND ciudad = 'Rawson'
  AND geocoding_status = 'done'
  AND latitud IS NOT NULL;
-- Filas afectadas: 3 (exactamente) ✅
```

### UPDATE 2 — geocoding_results

```sql
UPDATE geocoding_results
SET
    status        = 'error',
    latitud       = NULL,
    longitud      = NULL,
    error_message = 'coordinate_out_of_city_bbox',
    updated_at    = NOW()
WHERE propiedad_id = ANY(ARRAY[81293, 81294, 81306])
  AND status = 'success';
-- Filas afectadas: 3 (exactamente) ✅
```

---

## Estado posterior al UPDATE

| staging_id | geocoding_status | latitud | longitud | gr.status | gr.error_message |
|------------|-----------------|---------|----------|-----------|-----------------|
| 81293 | **failed** | NULL | NULL | **error** | coordinate_out_of_city_bbox |
| 81294 | **failed** | NULL | NULL | **error** | coordinate_out_of_city_bbox |
| 81306 | **failed** | NULL | NULL | **error** | coordinate_out_of_city_bbox |

---

## Confirmación de no-colaterales

| Verificación | Resultado |
|---|---|
| Otros staging_ids del batch (81276-81327) — sin nuevos failed | ✅ Solo los 13 expected (10 previos + 3 Fix L) |
| geocoding_results — nuevos errors son exactamente 81293/81294/81306 | ✅ Solo 3 con `coordinate_out_of_city_bbox` |
| publish_queue — sin filas para 81293/81294/81306 | ✅ 0 filas |
| publish_queue — sin filas del batch 81276-81327 | ✅ Las 40 filas existentes son de batch anterior (IDs ~21-40) |
| .env — no modificado | ✅ |
| schema — no modificado | ✅ |
| Supabase — no tocado | ✅ |
| frontend — no tocado | ✅ |
| git push — no ejecutado | ✅ |

---

## Impacto en candidatos publish_queue

El recuento de confiables pasa de 34 → 31 efectivos:

| Categoría | Antes Fix L | Después Fix L |
|---|---|---|
| EXACTA/CALLE dentro bbox | 34 (incl. 3 erróneas) | **31 correctas** |
| FUERA BBOX (rechazadas) | 0 | 3 (→ failed) |
| Area-level (dudosas) | 3 | 3 |
| failed (Nominatim) | 10 | 13 |

**31 propiedades confiables** listas para dry-run de publish_queue (pendiente autorización).

---

## Próximos pasos (pendientes de autorización)

1. **`build_publish_queue.py --dry-run`** sobre los 31 IDs confiables.
2. Decidir qué hacer con las 6 dudosas (81280, 81292, 81293, 81294, 81304, 81306).
3. Para los 13 failed: 3 son Fix L (intentar con dirección corregida), 10 son Nominatim sin índice.
4. **NO ejecutar `--commit` de publish_queue** sin autorización explícita.
5. **NO hacer push** hasta nueva instrucción.
