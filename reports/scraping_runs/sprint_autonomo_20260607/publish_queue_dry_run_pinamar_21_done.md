# publish_queue dry-run — Pinamar 21 IDs

**Fecha:** 2026-06-08  
**ids-file:** `publish_queue_ids_pinamar_21_done.csv`  
**Modo:** dry-run (rollback — sin escrituras)  
**Script:** `build_publish_queue.py`

---

## Resultado dry-run

| Metrica | Valor |
|---------|-------|
| filas_leidas | **21** |
| encoladas (dry-run) | **21** |
| ya_en_cola | 0 |
| skips | 0 |
| prioridad 1 | **21** |
| prioridad 2 | 0 |
| accion_final | rollback |

---

## Calidad de las 21 propiedades

| Metrica | Valor |
|---------|-------|
| Con precio | 21/21 (100%) |
| Con imagenes | 21/21 (100 %) — 10 imgs c/u |
| Validation score | min=100 max=100 avg=100 |
| Geocoding precision | street x21 |
| Moneda | USD x21 |
| Operacion | venta x21 |
| Dentro bbox Pinamar | 21/21 |

---

## Detalle por ID

| staging_id | Direccion (normalizada) | Tipo | Precio USD | Score | Imgs | Obs |
|-----------|------------------------|------|-----------|-------|------|-----|
| 81392 | Avenida Libertador C 1° 102 | departamento | 257,885 | 100 | 10 | |
| 81396 | Fragata 25 de Mayo 148 | departamento | 230,000 | 100 | 10 | |
| 81399 | De la Cincha 401 | casa | 1,850,000 | 100 | 10 | |
| 81400 | De la Cincha 336 | casa | 460,000 | 100 | 10 | |
| 81401 | De los Alamos 278 | casa | 480,000 | 100 | 10 | |
| 81402 | Del Lazo 245 | casa | 395,000 | 100 | 10 | |
| 81403 | Artemisa 4166 | casa | 465,000 | 100 | 10 | |
| 81408 | De la Cincha 635 | casa | 560,000 | 100 | 10 | |
| 81410 | Rivadavia 400 Unidad 2°19 | departamento | 105,000 | 100 | 10 | |
| 81411 | Martín Pescador 1485 PB 103 | departamento | 223,000 | 100 | 10 | ⚠ ver nota |
| 81412 | Martín Pescador 1485 1° 111 | departamento | 230,000 | 100 | 10 | ⚠ ver nota |
| 81413 | Martín Pescador 1485 1° 216 | departamento | 192,000 | 100 | 10 | ⚠ ver nota |
| 81414 | Del Lazo 119 | casa | 490,000 | 100 | 10 | |
| 81418 | Selene 1092 | casa | 280,000 | 100 | 10 | |
| 81420 | Del Rodeo 156 | casa | 690,000 | 100 | 10 | |
| 81421 | Avenida Bunge 1112 3°302 | departamento | 162,782 | 100 | 10 | |
| 81422 | Avenida Bunge 1112 2°206 | departamento | 255,938 | 100 | 10 | |
| 81423 | Avenida Libertador 4345 1° Piso Unidad 126 | departamento | 465,000 | 100 | 10 | |
| 81424 | Avenida Bunge 1112 2°205 | departamento | 161,137 | 100 | 10 | |
| 81443 | Avenida Bunge N° 1506 4° E | departamento | 200,000 | 100 | 10 | |
| 81445 | Del Dorado 1056 Unidad 3 | departamento | 120,000 | 100 | 10 | |

---

## Flags a resolver antes del commit

### ⚠ Ruido en direccion_normalizada (3 IDs)

IDs 81411, 81412, 81413 tienen `- Financiación Flexible` al final de la dirección
(texto de marketing del portal de origen, no parte de la dirección real).

El geocoding fue correcto (se geocodificaron bien por Nominatim ignorando el sufijo),
pero la `direccion_normalizada` que llegaría a Supabase si se publica ahora incluiría ese texto.

**Accion requerida:** limpiar los 3 campos antes del publish_queue commit:
```sql
UPDATE propiedades_staging
SET direccion_normalizada = 'Martín Pescador 1485 PB 103'   WHERE id = 81411;
UPDATE propiedades_staging
SET direccion_normalizada = 'Martín Pescador 1485 1° 111'   WHERE id = 81412;
UPDATE propiedades_staging
SET direccion_normalizada = 'Martín Pescador 1485 1° 216'   WHERE id = 81413;
```
(una sola transacción, guard: `geocoding_status='done' AND status='staging'`)

### ℹ Unidades en dirección (menor, sin bloquear)

Varios IDs tienen designaciones de unidad en `direccion_normalizada`
(`C 1° 102`, `2°206`, `3°302`, etc.). Son correctas para identificar la unidad
pero podrían verse poco prolijas en el frontend. Se puede limpiar más adelante
— no bloquea el publish_queue commit.

---

## Preflight de seguridad

| Check | Resultado |
|-------|-----------|
| publish_queue antes del dry-run | total=71, max_id=254 |
| Supabase | NO tocada |
| frontend | NO tocada |
| .env | sin cambio (modificado hace ~11 dias) |
| Procesos Python externos | ninguno |

---

## Recomendacion

**Las 21 propiedades son aptas para publish_queue commit** — score=100, precio USD,
10 imagenes, geocoding street-level, dentro del bbox de Pinamar.

**Pasos antes de autorizar commit:**
1. Limpiar `direccion_normalizada` para 81411/81412/81413 (quitar `- Financiación Flexible`)
2. Autorizar `build_publish_queue.py --ids-file ... --commit`

**Comando listo para cuando autorices:**
```bash
USE_INTERNAL_DB=true python scripts/build_publish_queue.py \
  --ids-file "reports/scraping_runs/sprint_autonomo_20260607/publish_queue_ids_pinamar_21_done.csv" \
  --limit 30 \
  --commit
```
