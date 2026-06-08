# publish_to_supabase.py — Dry-run filtrado Pinamar 21 IDs

**Fecha:** 2026-06-08  
**Script modificado:** `scripts/publish_to_supabase.py` (+`--staging-ids-file`)  
**ids-file:** `publish_queue_ids_pinamar_21_done.csv`  
**Supabase:** NO tocada (dry-run + lectura de hashes)

---

## Cambios aplicados al script

4 ediciones mínimas a `scripts/publish_to_supabase.py`:

| # | Donde | Cambio |
|---|-------|--------|
| 1 | `fetch_queue_rows()` | Acepta `staging_ids_filter: Optional[List[int]]`; inyecta `AND staging_id = ANY(%s)` en el WHERE |
| 2 | `argparse` | Agrega `--staging-ids-file` (default=None) |
| 3 | `main()` | Carga el CSV si se pasa el flag; acepta columna `staging_id` o `id` |
| 4 | `main()` | Pasa `staging_ids_filter` a `fetch_queue_rows` |

**Sin `--staging-ids-file`: comportamiento idéntico al original** (no se altera el flujo).  
`py_compile`: OK. Tests de carga, SQL injection, `--help`: todos PASS.

---

## Resultado dry-run filtrado

```
filas_queue_leidas = 21
props_validas      = 21
publicadas_ok      =  0  (dry-run)
failed             =  0
omitidas           =  0
writes_supabase    =  0
accion_final       = rollback
```

El filtro funcionó: procesó exactamente los queue_ids 276–296, sin tocar los 22 pending anteriores.

---

## Queue IDs y payload completo

| queue_id | staging_id | hash_dedup | precio USD | moneda | lat | lon | imgs | URL (extracto) |
|---------|-----------|-----------|-----------|--------|-----|-----|------|----------------|
| 276 | 81392 | dbdbdac8... | 257,885 | USD | -37.1016 | -56.8440 | 10 | /p/6634883-Departamento-en-Venta-en-Norte-Playa |
| 277 | 81396 | dab55373... | 230,000 | USD | -37.0995 | -56.8478 | 10 | /p/7901432-Departamento-en-Venta-en-Norte-Playa |
| 278 | 81399 | b7324608... | 1,850,000 | USD | -37.0850 | -56.8696 | 10 | /p/6122156-Casa-en-Venta-en-La-Herradura |
| 279 | 81400 | 67bd1c3d... | 460,000 | USD | -37.0850 | -56.8696 | 10 | /p/6630592-Casa-en-Venta-en-La-Herradura |
| 280 | 81401 | 18fc3ae4... | 480,000 | USD | -37.0873 | -56.8598 | 10 | /p/7838218-Casa-en-Venta-en-Alamos |
| 281 | 81402 | 93353aa6... | 395,000 | USD | -37.0803 | -56.8562 | 10 | /p/3802835-Casa-en-Venta-en-La-Herradura |
| 282 | 81403 | 62d98965... | 465,000 | USD | -37.0803 | -56.8342 | 10 | /p/7840640-Casa-en-Venta-en-Pinamar-Norte |
| 283 | 81408 | 37504443... | 560,000 | USD | -37.0850 | -56.8696 | 10 | /p/3802850-Casa-en-Venta-en-La-Herradura |
| 284 | 81410 | c1f8809f... | 105,000 | USD | -37.1071 | -56.8755 | 10 | /p/3803052-Departamento-en-Venta-en-Centro |
| 285 | 81411 | ef12afeb... | 223,000 | USD | -37.0964 | -56.8740 | 10 | /p/6296673-Martín-Pescador-1485-FINANCIACIÓN-FLEXIBLE |
| 286 | 81412 | bb4cd2b0... | 230,000 | USD | -37.0964 | -56.8740 | 10 | /p/6294316-Martín-Pescador-1485-FINANCIACIÓN-FLEXIBLE |
| 287 | 81413 | b7a598bb... | 192,000 | USD | -37.0964 | -56.8740 | 10 | /p/6500838-Martín-Pescador-1485-FINANCIACIÓN-FLEXIBLE |
| 288 | 81414 | 77d01310... | 490,000 | USD | -37.0803 | -56.8562 | 10 | /p/7486167-Casa-en-Venta-en-La-Herradura |
| 289 | 81418 | 1ce067d6... | 280,000 | USD | -37.0793 | -56.8384 | 10 | /p/7664939-Casa-en-Venta-en-Pinamar-Norte |
| 290 | 81420 | 73322ac6... | 690,000 | USD | -37.0800 | -56.8577 | 10 | /p/3802983-Casa-en-Venta-en-La-Herradura |
| 291 | 81421 | 66d718aa... | 162,782 | USD | -37.1124 | -56.8669 | 10 | /p/7863554-Departamento-en-Venta-en-Centro |
| 292 | 81422 | 863a64a6... | 255,938 | USD | -37.1124 | -56.8669 | 10 | /p/7863539-Departamento-en-Venta-en-Centro |
| 293 | 81423 | d7c7895e... | 465,000 | USD | -37.1016 | -56.8440 | 10 | /p/3802736-Departamento-en-Venta-en-Norte-Playa |
| 294 | 81424 | 754d874b... | 161,137 | USD | -37.1124 | -56.8669 | 10 | /p/7863529-Departamento-en-Venta-en-Centro |
| 295 | 81443 | 10cdf479... | 200,000 | USD | -37.1124 | -56.8669 | 10 | /p/4962450-Departamento-en-Venta-en-Centro |
| 296 | 81445 | 9aaf2afe... | 120,000 | USD | -37.1046 | -56.8589 | 10 | /p/3803019-Departamento-en-Golf-Nuevo |

**inmobiliaria_id:** 4019 × 21  
**operacion:** venta × 21  
**validation_score:** 100 × 21  
**geocoding:** street × 21  
**imagenes:** 10 URLs tokkobroker CDN × 21  

---

## Campos faltantes

| Campo | Estado | Impacto |
|-------|--------|---------|
| `superficie_total` | NULL × 21 | No bloquea. Queda vacío en Supabase. |
| `superficie_cubierta` | NULL × 21 | Ídem. |
| `barrio` | Presente (Norte Playa, La Herradura, etc.) | OK |
| `descripcion` | Presente (scraper) | OK |

---

## Verificación de duplicados en Supabase

**Resultado: 0 duplicados.** Ninguno de los 21 `hash_dedup` existe en la tabla `propiedades` de Supabase.  
La inserción sería completamente nueva para los 21.

Verificación: SELECT read-only vía `supabase-py` contra `propiedades.hash_dedup IN (...)`.  
No se escribió nada.

---

## Flags / riesgos

| Flag | Detalle | Bloquea |
|------|---------|---------|
| `superficie_total/cubierta = None` | El scraper (Tokko) no capturó superficies | No |
| URL con `FINANCIACIÓN FLEXIBLE` (81411–81413) | Es la URL del portal de origen — aceptable, no se limpia | No |
| Imágenes en CDN tokkobroker | URLs externas; podrían expirar | Riesgo futuro |
| Títulos con espacios dobles | Cosmético (`"en Venta   en"`) | No |
| Comportamiento INSERT vs UPSERT | `save_propiedades` usa upsert por `hash_dedup`; con 0 colisiones → INSERT en todos los casos | Verificado |

---

## Recomendación

**Las 21 propiedades son seguras para publicar.**

- 0 duplicados en Supabase
- 21/21 pasan validación del script
- Filtro `--staging-ids-file` funciona: procesa exactamente los 21, sin tocar los 22 pending anteriores
- Geocoding street-level, bbox Pinamar OK
- Precio USD, 10 imgs, score=100

**Comando listo para cuando autorices el commit real:**

```bash
USE_INTERNAL_DB=true python scripts/publish_to_supabase.py \
  --staging-ids-file "reports/scraping_runs/sprint_autonomo_20260607/publish_queue_ids_pinamar_21_done.csv" \
  --limit 30 \
  --commit
```

**FRENADO. No se publicó Supabase. Esperando confirmación.**
