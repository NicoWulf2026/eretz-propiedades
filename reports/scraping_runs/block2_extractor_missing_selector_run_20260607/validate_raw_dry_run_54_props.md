# Validate raw → staging — Dry-run Bloque 2 (54 props)

- Fecha: 2026-06-07
- Modo: **DRY-RUN** — sin escritura a staging, rollback ejecutado
- Script: `scripts/validate_raw_properties.py`
- IDs: raw 82081–82134 (54 props)
- Fix activo en script: `--ids-file` (agregado en esta sesión — sin romper comportamiento anterior)
- Staging antes del dry-run: max_id=81,059 / total=76,487 — **INTACTO** ✅

---

## 1. Resultado del dry-run

```
filas_leidas  = 54
validadas     = 54   ← todas pasarían a staging si se hace --commit
rechazadas    =  0
duplicadas    =  0
accion_final  = rollback
```

**Conclusión: 54/54 pasan sin rechazo. 0 colisiones contra staging.**

---

## 2. Issues por tipo

| Issue | Count | Tipo | Impacto |
|---|---|---|---|
| `missing_location` | 40 | Warning | tonyzorrilla (29) + dilello (11) — sin ciudad/provincia en campo estructurado |
| Campos críticos faltantes | 0 | — | **ninguno** ✅ |
| Duplicados en staging | 0 | — | **ninguno** ✅ |
| `invalid_operation` | 0 | — | ✅ |
| `invalid_type` | 0 | — | ✅ |
| `bad_title` | 0 | — | ✅ |
| `missing_price` | — | Informativo | 35 sin precio (35/54 — normal para sitios "consultar") |
| `missing_images` | 0 | — | todas las 54 tienen imágenes ✅ |

---

## 3. Análisis por dominio

### inmobiliariaescuza.com — inmob_id=5848 | 2 props | IDs 82133–82134

| Campo | Estado |
|---|---|
| ciudad | ✅ Tandil (Buenos Aires) |
| precio | 1/2 USD, 1/2 sin precio |
| imágenes | 2/2 ✅ |
| operacion | 2/2 venta ✅ |
| tipo | 2/2 casa ✅ |
| missing_location | 0 ✅ |
| geocoding_status esperado | `pending` (ciudad OK, sin lat/lon) |

**2/2 pasan. Sin issues críticos.**

---

### luciafrolik.com.ar — inmob_id=5850 | 12 props | IDs 82081–82092

| Campo | Estado |
|---|---|
| ciudad | ✅ Tandil (Buenos Aires) — 12/12 |
| precio | 8/12 USD, 4/12 sin precio |
| imágenes | 12/12 ✅ |
| operacion | 12/12 venta ✅ |
| tipo | 12/12 casa ✅ |
| missing_location | 0 ✅ |
| geocoding_status esperado | `pending` (ciudad OK, sin lat/lon) |

**Nota:** 2 props tienen `direccion_raw` con overflow de descripción:
- ID 82082: `"compartimentado. Sobre un lote de 15"` — texto de descripción filtrado como dirección
- ID 82089: `"tanto en su estructura y detalles. 677"` — idem

Estos no son detectados por `GARBAGE_ADDRESS_PATTERNS` (no contienen los tokens contaminantes conocidos). Pasarán a staging como `direccion_normalizada` con texto basura. **No bloquean el validate** pero son ruido de calidad.

**12/12 pasan. 2 con direccion_raw de calidad baja (no bloquea).**

---

### tonyzorrilla.com.ar — inmob_id=5853 | 29 props | IDs 82093–82121

| Campo | Estado |
|---|---|
| ciudad | ❌ 29/29 sin ciudad (None/None) |
| precio | 1/29 USD, 28/29 consultar |
| imágenes | 29/29 ✅ |
| operacion | 24 venta / 5 alquiler ✅ |
| tipo | 23 casa / 5 departamento / 1 local ✅ |
| missing_location | ⚠️ 29/29 |
| geocoding_status esperado | `pending` (sin ciudad ni lat/lon) |

**Ciudad real**: Rawson y Playa Unión, Chubut — visible en títulos de las props ("Rawson", "Playa Unión"), pero no extraída al campo `ciudad` por el scraper.  
**Fix necesario antes de geocoding**: enrichment de ciudad desde título (Fix J pendiente).

**29/29 pasan. Sin ciudad estructurada → geocoding pending sin referencia de ciudad.**

---

### dilellopropiedades.com — inmob_id=5916 | 11 props | IDs 82122–82132

| Campo | Estado |
|---|---|
| ciudad | ❌ 11/11 sin ciudad (None/None) |
| precio | 9/11 USD, 2/11 sin precio |
| imágenes | 11/11 ✅ |
| operacion | 10 venta / 1 alquiler ✅ |
| tipo | 5 casa / 3 departamento / 3 terreno ✅ |
| missing_location | ⚠️ 11/11 |
| geocoding_status esperado | `pending` (sin ciudad ni lat/lon) |

**Ciudad real**: Pergamino, Buenos Aires — visible en títulos ("En Pergamino"), no extraída al campo `ciudad`.

**Direcciones contaminadas detectadas (no bloqueadas por validate):**
- ID 82122: `"C.M.P. Consultas Online 2477"` — dirección de oficina inmobiliaria, no de la propiedad
- ID 82123: `"C.M.P. Consultas Online 2477"` — idem
- ID 82128: `"C.M.P. Consultas Online 2477"` — idem

Estas 3 no son detectadas por `GARBAGE_ADDRESS_PATTERNS` actual (no contienen "consultar precio", "whatsapp", etc. exactos). El campo `direccion_normalizada` en staging tendrá texto basura.  
**Recomendación**: agregar "consultas online" a `GARBAGE_ADDRESS_PATTERNS` en una futura Fix J (global).

**11/11 pasan. 3 con direccion contaminada (no bloqueada — Fix J pendiente).**

---

## 4. Geocoding_status esperado en staging

| Dominio | Props | Ciudad | Lat/Lon | geocoding_status |
|---|---|---|---|---|
| luciafrolik | 12 | Tandil, BA | No | `pending` |
| escuza | 2 | Tandil, BA | No | `pending` |
| tonyzorrilla | 29 | **Sin ciudad** | No | `pending` — riesgo geocoding sin referencia |
| dilello | 11 | **Sin ciudad** | No | `pending` — riesgo geocoding sin referencia |
| **TOTAL** | **54** | 14 con ciudad | 0 | **54 × pending** |

---

## 5. ¿Es seguro hacer validate --commit?

**SÍ. Con observaciones.**

| Check | Estado |
|---|---|
| 54/54 pasan validate | ✅ |
| 0 rechazadas | ✅ |
| 0 duplicados en staging | ✅ |
| 0 campos críticos faltantes | ✅ |
| staging antes: 76,487 rows / max_id 81,059 | ✅ intacto |
| staging esperado después: 76,541 rows (+54) | — |
| missing_location (40) | ⚠️ warning, no bloquea |
| 3 direcciones C.M.P. contaminadas (dilello) | ⚠️ calidad baja, no bloquea |
| 2 direcciones con overflow de descripción (luciafrolik) | ⚠️ calidad baja, no bloquea |

---

## 6. Pendientes antes del validate --commit

| Pendiente | Prioridad | Scope |
|---|---|---|
| Fix J: añadir "consultas online" a `GARBAGE_ADDRESS_PATTERNS` | Opcional | dilello — 3 props |
| Fix J: enrichment ciudad desde título (tonyzorrilla→Rawson, dilello→Pergamino) | Recomendado antes de geocoding | 40 props sin ciudad |
| Decidir si address overflow de luciafrolik (82082, 82089) se corrige | Opcional | 2 props |

> **Nota crítica**: Si se hace validate --commit SIN Fix J, las 40 props de tonyzorrilla/dilello entran a staging sin ciudad. Cuando se geocodifique, el geocoder necesitará una referencia de ciudad para encontrar las direcciones. Sin ciudad, el geocoding de estas props es de muy baja calidad.
>
> **Recomendación**: implementar Fix J (ciudad desde título) ANTES de validate --commit, para que las 40 props entren a staging ya con `ciudad` rellenada.

---

## 7. Comando para validate --commit (cuando se autorice)

```bash
USE_INTERNAL_DB=true python scripts/validate_raw_properties.py \
  --ids-file "reports/scraping_runs/block2_extractor_missing_selector_run_20260607/raw_ids_54_props.csv" \
  --commit \
  --report "reports/scraping_runs/block2_extractor_missing_selector_run_20260607/validate_raw_commit_54_props.md"
```

---

## 8. Controles de seguridad del dry-run

| Control | Estado |
|---|---|
| staging | NO modificado ✅ |
| geocoding_results | NO tocada ✅ |
| publish_queue | NO modificada ✅ |
| Supabase | NO tocada ✅ |
| .env | NO modificado ✅ |
| git push | NO ejecutado ✅ |

---

## FASE 5 — Freno activo

**STATUS: EN ESPERA DE AUTORIZACIÓN PARA validate --commit**

Dry-run exitoso: 54/54 pasarían a staging.  
Antes de autorizar el commit, considerar si implementar Fix J (ciudad desde título para tonyzorrilla/dilello).

---

*Dry-run ejecutado: 2026-06-07 · raw 82081–82134 · 54 props · accion=rollback · rama fix/scraping-diagnostics-batch · commit 52395d74*
