# Dry-Run: Enriquecimiento post Fix G + Fix E en registros existentes

- Fecha: 2026-06-07
- Tipo: **DRY-RUN** — solo análisis, cero cambios ejecutados
- Objetivo: enriquecer registros ya existentes en raw/staging sin crear duplicados
- Commit activo: `fe4ecd04` (Fix G aplicado)
- Tablas auditadas: `propiedades_raw`, `propiedades_staging`

---

## Resumen ejecutivo

| Agencia | Tabla | Registros candidatos | Registros que mejoran | Excluidos | Estado |
|---|---|---|---|---|---|
| Watson (inmob=6162) | propiedades_staging | 3 | **2** | 1 (precio genuinamente None) | SAFE ✅ |
| Watson (inmob=6162) | propiedades_raw | 3 | **2** | 1 | SAFE ✅ |
| Campos del Amapa (inmob=1443) | propiedades_staging | 4 | **4** | 0 | SAFE ✅ |
| Campos del Amapa (inmob=1443) | propiedades_raw | 4 | **4** | 0 | SAFE ✅ |

**Total updates propuestos: 12 filas (6 staging + 6 raw)**  
**Riesgo general: BAJO**

---

## FASE 2 — Watson precio (Fix G)

### Fuente del nuevo precio

Batch: `data/scraping_batches/rescrape_watson_fixG_20260606/captured/0001_www_watsonpropiedades_com_explora_propiedades.json`  
Fix G activo: cuando JSON-LD `@type=Product` no tiene `offers/price`, se enriquece desde `<h3 class="price">` vía `_html_extract_detail`.

### Mapeo staging → raw

| staging_id | raw_id | inmobiliaria_id | URL |
|---|---|---|---|
| 81057 | 82078 | 6162 | `watsonpropiedades.com/casa-en-zona-centro-excelente-ubicacion` |
| 81058 | 82079 | 6162 | `watsonpropiedades.com/casa-de-categoria-en-quintas-de-betbeder-apta-credito-hipotecario-4` |
| 81059 | 82080 | 6162 | `watsonpropiedades.com/casa-en-esquina-en-zona-centro` |

### Análisis prop a prop

#### Prop 1 — staging=81057 / raw=82078
| Campo | Antes | Después | Fuente |
|---|---|---|---|
| titulo | "Casa en zona Centro. Excelente ubicación." | sin cambio | — |
| precio | **None** | **88,000** | `<h3 class="price">US$\xa088.000,00</h3>` → Fix G |
| moneda | ARS | **USD** | normalización |
| precio_usd | — | 88,000 | calculado |
| precio_ars | — | 126,280,000 | tipo cambio al momento del scrape |

- URL match: ✅ exacto
- precio actual NULL: ✅ condición cumplida
- precio nuevo válido (float > 0, moneda conocida): ✅
- Conflicto: ninguno
- **Acción: UPDATE ✅ | Riesgo: BAJO**

#### Prop 2 — staging=81058 / raw=82079
| Campo | Antes | Después | Fuente |
|---|---|---|---|
| precio | None | **sin cambio** | precio genuinamente None en HTML |

- El HTML de `casa-de-categoria-en-quintas-de-betbeder` no tiene `<h3 class="price">` — verificado en 3 fetches independientes (FASE 3).
- **Acción: EXCLUIDO — no hay precio nuevo para aplicar**

#### Prop 3 — staging=81059 / raw=82080
| Campo | Antes | Después | Fuente |
|---|---|---|---|
| titulo | "Casa en esquina en zona Centro" | sin cambio | — |
| precio | **None** | **125,000** | `<h3 class="price">US$\xa0125.000,00</h3>` → Fix G |
| moneda | ARS | **USD** | normalización |
| precio_usd | — | 125,000 | calculado |
| precio_ars | — | 179,375,000 | tipo cambio al momento del scrape |

- URL match: ✅ exacto
- precio actual NULL: ✅
- precio nuevo válido: ✅
- **Acción: UPDATE ✅ | Riesgo: BAJO**

### SQL propuesto — Watson precio

> **NO EJECUTADO.** Solo para revisión.

```sql
-- Watson precio UPDATE · 2026-06-07 · DRY-RUN
-- Condición doble: primary key + precio IS NULL (previene sobreescribir precio válido)

-- [1/4] staging 81057: casa-en-zona-centro → 88,000 USD
UPDATE propiedades_staging
SET precio  = 88000.0,
    moneda  = 'USD'
WHERE id              = 81057
  AND inmobiliaria_id = 6162
  AND precio IS NULL;
-- Expected: 1 row updated

-- [2/4] staging 81059: casa-en-esquina → 125,000 USD
UPDATE propiedades_staging
SET precio  = 125000.0,
    moneda  = 'USD'
WHERE id              = 81059
  AND inmobiliaria_id = 6162
  AND precio IS NULL;
-- Expected: 1 row updated

-- [3/4] raw 82078: casa-en-zona-centro → 88,000 USD
UPDATE propiedades_raw
SET precio  = 88000.0,
    moneda  = 'USD',
    datos_extra = datos_extra || '{"precio_enriquecido_desde_html": true, "precio_usd": 88000.0, "precio_ars": 126280000.0}'::jsonb
WHERE id              = 82078
  AND inmobiliaria_id = 6162
  AND precio IS NULL;
-- Expected: 1 row updated

-- [4/4] raw 82080: casa-en-esquina → 125,000 USD
UPDATE propiedades_raw
SET precio  = 125000.0,
    moneda  = 'USD',
    datos_extra = datos_extra || '{"precio_enriquecido_desde_html": true, "precio_usd": 125000.0, "precio_ars": 179375000.0}'::jsonb
WHERE id              = 82080
  AND inmobiliaria_id = 6162
  AND precio IS NULL;
-- Expected: 1 row updated
```

**Notas sobre el SQL:**
- El operador `||` en JSONB hace merge (no reemplaza todo datos_extra).
- La condición `AND precio IS NULL` es idempotente: si se ejecuta dos veces, la segunda no modifica nada.
- No se toca `hash_dedup` (queda el hash del scrape original, que es correcto).
- No se toca `geocoding_status` (queda `pending`; Watson sin ciudad/provincia → skippeable).
- No se actualiza `staged_at` ni `validation_score` en staging.
- El `datos_extra` de staging no existe como columna → solo se actualiza en raw.

---

## FASE 3 — Campos del Amapa títulos ricos (Fix E)

### Fuente del nuevo título

Batch: `data/scraping_batches/rescrape_controlled_20260606_fase2/captured/0002_www_camposdelapampa_com_ar_ofertadecampos_camposenventa_html.json`  
Fix E activo: rechaza títulos filename (`_FILENAME_TITLE_RE`) y extrae título desde `section.famie-benefits-area`.

### Mapeo staging → raw

| staging_id | raw_id | inmobiliaria_id | URL |
|---|---|---|---|
| 81053 | 82074 | 1443 | `camposdelapampa.com.ar/ca266.html` |
| 81054 | 82075 | 1443 | `camposdelapampa.com.ar/mo342.html` |
| 81055 | 82076 | 1443 | `camposdelapampa.com.ar/mo340.html` |
| 81056 | 82077 | 1443 | `camposdelapampa.com.ar/mi319.html` |

### Estado actual

| staging_id | titulo_staging_actual | titulo_raw_actual |
|---|---|---|
| 81053 | "Campo en venta en La Pampa" | "Ca266.Html" |
| 81054 | "Campo en venta en La Pampa" | "Mo342.Html" |
| 81055 | "Campo en venta en La Pampa" | "Mo340.Html" |
| 81056 | "Campo en venta en La Pampa" | "Mi319.Html" |

Nota: `staging.titulo` fue actualizado a "Campo en venta en La Pampa" en una sesión anterior (UPDATE controlado para eliminar filename titles). `raw.titulo` conserva el filename original.

### Análisis prop a prop

| staging_id | raw_id | URL | Título actual (staging) | Título nuevo (Fix E) | Mejor? | Update? |
|---|---|---|---|---|---|---|
| 81053 | 82074 | ca266.html | "Campo en venta en La Pampa" | "Departamento Loventué Muy buen acceso 6.000 ha Cria" | **Sí** — aporta depto, ha, tipo | ✅ |
| 81054 | 82075 | mo342.html | "Campo en venta en La Pampa" | "Limay Mahuida Oportunidad 15.000 ha Cria" | **Sí** — aporta nombre propio, ha, tipo | ✅ |
| 81055 | 82076 | mo340.html | "Campo en venta en La Pampa" | "Departamento Chalileo Oportunidad 30.000 ha Cria" | **Sí** — aporta depto, ha, tipo | ✅ |
| 81056 | 82077 | mi319.html | "Campo en venta en La Pampa" | "Departamento Toay Bosque abierto 600 ha Ganaderia y Agricultura" | **Sí** — aporta depto, ha, uso | ✅ |

**Condiciones verificadas para cada prop:**
- mismo inmobiliaria_id (1443): ✅
- misma URL/hash: ✅ (hash_dedup coincide)
- título actual es genérico (staging) / filename (raw): ✅
- título nuevo no es filename (`_FILENAME_TITLE_RE` lo rechazaría): ✅
- título nuevo es más informativo: ✅ (incluye departamento, ha, tipo de actividad)
- no hay título mejor en staging: ✅ (el actual es genérico)

### SQL propuesto — Campos del Amapa títulos

> **NO EJECUTADO.** Solo para revisión.

```sql
-- Campos del Amapa título UPDATE · 2026-06-07 · DRY-RUN
-- staging: reemplazar genérico por título rico
-- raw: reemplazar filename por título rico

-- staging 81053 (ca266.html)
UPDATE propiedades_staging
SET titulo = 'Departamento Loventué Muy buen acceso 6.000 ha Cria'
WHERE id              = 81053
  AND inmobiliaria_id = 1443
  AND titulo          = 'Campo en venta en La Pampa';
-- Expected: 1 row updated

-- staging 81054 (mo342.html)
UPDATE propiedades_staging
SET titulo = 'Limay Mahuida Oportunidad 15.000 ha Cria'
WHERE id              = 81054
  AND inmobiliaria_id = 1443
  AND titulo          = 'Campo en venta en La Pampa';
-- Expected: 1 row updated

-- staging 81055 (mo340.html)
UPDATE propiedades_staging
SET titulo = 'Departamento Chalileo Oportunidad 30.000 ha Cria'
WHERE id              = 81055
  AND inmobiliaria_id = 1443
  AND titulo          = 'Campo en venta en La Pampa';
-- Expected: 1 row updated

-- staging 81056 (mi319.html)
UPDATE propiedades_staging
SET titulo = 'Departamento Toay Bosque abierto 600 ha Ganaderia y Agricultura'
WHERE id              = 81056
  AND inmobiliaria_id = 1443
  AND titulo          = 'Campo en venta en La Pampa';
-- Expected: 1 row updated

-- raw 82074 (ca266.html)
UPDATE propiedades_raw
SET titulo = 'Departamento Loventué Muy buen acceso 6.000 ha Cria'
WHERE id              = 82074
  AND inmobiliaria_id = 1443
  AND titulo          = 'Ca266.Html';
-- Expected: 1 row updated

-- raw 82075 (mo342.html)
UPDATE propiedades_raw
SET titulo = 'Limay Mahuida Oportunidad 15.000 ha Cria'
WHERE id              = 82075
  AND inmobiliaria_id = 1443
  AND titulo          = 'Mo342.Html';
-- Expected: 1 row updated

-- raw 82076 (mo340.html)
UPDATE propiedades_raw
SET titulo = 'Departamento Chalileo Oportunidad 30.000 ha Cria'
WHERE id              = 82076
  AND inmobiliaria_id = 1443
  AND titulo          = 'Mo340.Html';
-- Expected: 1 row updated

-- raw 82077 (mi319.html)
UPDATE propiedades_raw
SET titulo = 'Departamento Toay Bosque abierto 600 ha Ganaderia y Agricultura'
WHERE id              = 82077
  AND inmobiliaria_id = 1443
  AND titulo          = 'Mi319.Html';
-- Expected: 1 row updated
```

**Notas sobre el SQL:**
- El WHERE incluye `titulo = '<valor_actual>'` para idempotencia: si ya fue actualizado, no modifica nada.
- No se toca `hash_dedup`, `precio`, `geocoding_status`, `staged_at`.
- No hay riesgo de pisar título mejor: el actual es genérico (staging) o filename (raw).

---

## FASE 4 — Reporte completo

### Resumen de cambios propuestos

| # | Tabla | ID | inmob | Campo | Antes | Después | Riesgo |
|---|---|---|---|---|---|---|---|
| 1 | propiedades_staging | 81057 | 6162 | precio/moneda | None / ARS | 88,000 / USD | BAJO |
| 2 | propiedades_staging | 81059 | 6162 | precio/moneda | None / ARS | 125,000 / USD | BAJO |
| 3 | propiedades_raw | 82078 | 6162 | precio/moneda/datos_extra | None / ARS | 88,000 / USD + audit trail | BAJO |
| 4 | propiedades_raw | 82080 | 6162 | precio/moneda/datos_extra | None / ARS | 125,000 / USD + audit trail | BAJO |
| 5 | propiedades_staging | 81053 | 1443 | titulo | "Campo en venta en La Pampa" | "Departamento Loventué..." | BAJO |
| 6 | propiedades_staging | 81054 | 1443 | titulo | "Campo en venta en La Pampa" | "Limay Mahuida..." | BAJO |
| 7 | propiedades_staging | 81055 | 1443 | titulo | "Campo en venta en La Pampa" | "Departamento Chalileo..." | BAJO |
| 8 | propiedades_staging | 81056 | 1443 | titulo | "Campo en venta en La Pampa" | "Departamento Toay..." | BAJO |
| 9 | propiedades_raw | 82074 | 1443 | titulo | "Ca266.Html" | "Departamento Loventué..." | BAJO |
| 10 | propiedades_raw | 82075 | 1443 | titulo | "Mo342.Html" | "Limay Mahuida..." | BAJO |
| 11 | propiedades_raw | 82076 | 1443 | titulo | "Mo340.Html" | "Departamento Chalileo..." | BAJO |
| 12 | propiedades_raw | 82077 | 1443 | titulo | "Mi319.Html" | "Departamento Toay..." | BAJO |

### Registros que quedan igual

| staging_id | raw_id | Agencia | Por qué sin cambio |
|---|---|---|---|
| 81058 | 82079 | Watson | precio genuinamente None — verificado en HTML, no hay precio publicado |

### Registros excluidos y por qué

Ninguno excluido por conflicto o condición no cumplida. Solo el caso Watson prop 2 (sin precio real).

### Análisis de riesgo

| Riesgo | Nivel | Detalle |
|---|---|---|
| Sobreescribir precio válido existente | **CERO** | Condición `AND precio IS NULL` protege |
| Sobreescribir título mejor | **CERO** | Condición `AND titulo = '<valor_genérico>'` protege |
| Crear duplicados | **CERO** | Solo UPDATEs sobre IDs conocidos, no INSERT |
| Afectar propiedades de otras agencias | **CERO** | WHERE incluye `inmobiliaria_id` explícito |
| Afectar staging IDs anteriores al batch | **CERO** | WHERE incluye primary key exacto |
| Inconsistencia raw/staging | **MÍNIMO** | Ambas tablas se actualizan en el mismo bloque |
| Romper pipeline posterior | **MÍNIMO** | precio + moneda son campos simples; geocoding_status no cambia |
| Update falla silencioso (0 rows) | **BAJO** | Si precio ya fue actualizado = idempotente, no error |

### Recomendación

**Sí conviene hacer el UPDATE controlado.**

Razones:
1. **Watson precio**: 2 propiedades con precio verificado por 3+ fetches independientes, Fix G validado con py_compile. El precio en staging es definitivamente erróneo (None cuando debería ser 88k/125k USD). Riesgo cero de sobreescribir dato bueno.
2. **Campos títulos**: los títulos actuales son subóptimos (staging: genérico; raw: filename). Los títulos nuevos aportan información real (departamento, hectáreas, tipo de actividad). Fix E validado en FASE 2.
3. **Alternativa peor**: reimportar crearía registros nuevos con hashes distintos → posibles duplicados en staging si el dedup no los bloquea, ya que el precio cambió (hash diferente).
4. **Los WHERE son idempotentes**: ejecución doble = segura.

**Orden recomendado de ejecución si se autoriza:**
1. Watson staging (2 filas)
2. Watson raw (2 filas)
3. Campos staging (4 filas)
4. Campos raw (4 filas)
5. Verificación SELECT post-update

---

## FASE 5 — Freno

**STATUS: EN ESPERA DE AUTORIZACIÓN**

- Ningún UPDATE fue ejecutado.
- Ninguna reimportación.
- Ningún commit en publish_queue.
- Neon: sin cambios.
- Supabase: no tocado.
- Frontend: no tocado.
- git push: no ejecutado.

---

*Dry-run generado: 2026-06-07 · commit activo fe4ecd04 · rama fix/scraping-diagnostics-batch*
