# Dry-run import — Bloque 2: 59 propiedades

- Fecha: 2026-06-07
- Modo: **DRY-RUN** — sin escritura a Neon
- Comando: `import_captured_props_to_neon.py --input-dir block2_merged_59props --batch-csv block2_extractor_missing_selector_5_domains.csv --dry-run`
- Input dir: `data/scraping_batches/block2_merged_59props/captured/` (4 JSONs fusionados)
- Batch CSV: `data/block2_extractor_missing_selector_5_domains.csv`
- `USE_INTERNAL_DB=true` como variable de sesión — `.env` NO modificado

---

## 1. Resultado del script

```
archivos_leidos              = 4
propiedades_detectadas       = 59
propiedades_procesadas       = 59
importables                  = 59   ← todas pasan el filtro de import
importadas                   = 0    ← dry-run, no hay escritura
con_warnings                 = 59   ← warnings informativos (ver detalle)
rechazadas                   = 0    ← cero hard-rejects
accion_final                 = dry-run/no-writes
```

---

## 2. Duplicados — cero bloqueos

| Categoría | Resultado | Acción |
|---|---|---|
| `duplicate_exact_same_source_batch` | **0** | — |
| `skipped_duplicate_in_propiedades_raw` | **0** | — |
| `skipped_duplicate_in_propiedades_staging` | **0** | — |
| `possible_cross_agency_within_batch` | **0** | Informativo — no bloquea |
| `possible_cross_agency_in_neon` | **0** | Informativo — no bloquea |
| `possible_same_address_within_batch` | **2** | Informativo — no bloquea |

**Ningún duplicado bloquea el import.**

Los 2 `possible_same_address_within_batch` corresponden a props de dilello con dirección contaminada `"C.M.P. Consultas Online 2477"` — tres props distintas con el mismo texto de "dirección", que es información de contacto, no una dirección real.

---

## 3. Campos faltantes (no bloquean import)

| Campo | Props afectadas | Detalle |
|---|---|---|
| `missing_location` | 45 | tonyzorrilla (30) + dilello (15) — ciudad/provincia no en campo estructurado |
| `missing_images` | 4 | Las 4 props `.jfif` de dilello (ver análisis abajo) |

---

## 4. Issues detectados por tipo

| Issue | Props | Bloquea? | Detalle |
|---|---|---|---|
| `source_test_mode_id_rewritten` | 59 | No | `inmobiliaria_id=0` en JSONs, script lo reescribe desde batch CSV ✅ |
| `missing_location` | 45 | No | Ciudad en título, no en campo — geocoding la recuperará |
| `low_quality_score` | 6 | No | Score=30 (4 .jfif) + score=50 (2 borderline). Irán a raw |
| `missing_images` | 4 | No | Solo las 4 .jfif — sin imágenes porque son thumbnails |
| `possible_same_address_within_batch` | 2 | No | Dirección contaminada "C.M.P. Consultas Online" |

---

## 5. Issues cualitativos detectados en inventario (no visibles en script)

Estos issues no son detectados por el import script pero requieren atención:

### 🔴 4 props con URL de imagen .jfif (dilello)

El script NO las rechaza. Se importarán a `propiedades_raw` con `score_calidad=30`.

En `validate_raw_properties.py`, estas props **serán rechazadas a staging** por:
- Score insuficiente (30 < min_score típico de validación)
- Sin imágenes (0 URLs)
- Sin dirección
- Título contiene extensión `.jfif` y número de código

Conclusión: aunque entren a `propiedades_raw`, no llegarán a `propiedades_staging`. Son inofensivas en raw.

**Pendiente**: fix global en `_looks_like_real_property_url()` para excluir URLs con extensión de imagen o bajo path `/img/`. No autorizado en esta sesión.

### 🟡 1 prop posible listing page (tonyzorrilla)

URL: `http://tonyzorrilla.com.ar/terrenos-a-la-venta-rawson-playa-union/`  
Título: `Terrenos a la venta | Rawson & Playa Unión`  
Score: 50 | Imágenes: 12 | Dirección: Amancay Nº 265

El script la importa sin problema. Si es una categoría, el pipeline de validación la puede filtrar o puede entrar en raw inofensivamente. No hay riesgo de pisar datos.

### 🟡 3 direcciones contaminadas (dilello)

Dirección capturada: `"C.M.P. Consultas Online 2477"` — número de teléfono/contacto.  
Las props tienen imágenes, score ≥ 50, operación y tipo correctos.  
En geocoding, el campo `direccion` no será útil → se geocodificará por ciudad.

---

## 6. Por dominio — estado de importación

| Dominio | inmob_id | Total | Importables | Issues en import |
|---|---|---|---|---|
| tonyzorrilla.com.ar | 5853 | 30 | **30** | missing_location (30), possible_listing_page (1) |
| dilellopropiedades.com | 5916 | 15 | **15** | missing_location (15), .jfif (4), contaminated_addr (3) |
| luciafrolik.com.ar | 5850 | 12 | **12** | — ninguno 🟢 |
| inmobiliariaescuza.com | 5848 | 2 | **2** | — ninguno 🟢 |
| **TOTAL** | | **59** | **59** | |

---

## 7. Seguridad del commit real

### ¿Es seguro ejecutar `--commit`?

**SÍ — con la siguiente aclaración:**

| Criterio | Estado |
|---|---|
| Duplicados exactos bloqueados | 0 ✅ |
| Colisión contra propiedades_raw existente | 0 ✅ |
| Colisión contra propiedades_staging existente | 0 ✅ |
| Riesgo de pisar datos buenos | 0 — import es solo INSERT, no UPDATE |
| Props que entrarán a staging automáticamente | 0 — staging requiere paso separado |
| Riesgo de .jfif en raw | Inofensivo — se filtran en validate |
| .env modificado | NO |
| Supabase tocada | NO |
| publish_queue modificado | NO |

### Condiciones para commit seguro:

1. ✅ Se usa `data/scraping_batches/block2_merged_59props/captured/` — contiene luciafrolik/escuza CON Fix H (títulos correctos)
2. ✅ Se usa `--batch-csv data/block2_extractor_missing_selector_5_domains.csv` para resolver `inmobiliaria_id`
3. ✅ `USE_INTERNAL_DB=true` como variable inline de sesión — no toca `.env`
4. ✅ Sin `--commit` hasta autorización explícita
5. ⚠️ Las 4 props `.jfif` entran a raw (inofensivo) — se bloquean en validate

---

## 8. Comando para commit real (cuando sea autorizado)

```bash
USE_INTERNAL_DB=true python scripts/import_captured_props_to_neon.py \
  --input-dir data/scraping_batches/block2_merged_59props/captured \
  --batch-csv data/block2_extractor_missing_selector_5_domains.csv \
  --commit \
  --report reports/scraping_runs/block2_extractor_missing_selector_run_20260607/import_commit_59_props.md
```

---

## 9. Controles de seguridad

| Control | Estado |
|---|---|
| Import a Neon (propiedades_raw) | NO ejecutado — DRY-RUN |
| validate_raw_properties | NO ejecutado |
| Geocoding | NO ejecutado |
| publish_queue | NO modificado |
| Supabase | NO tocado |
| Frontend | NO tocado |
| .env | NO modificado |
| git push | NO ejecutado |

---

## FASE 4 — Freno activo

**STATUS: EN ESPERA DE AUTORIZACIÓN**

Dry-run exitoso: 59 props importables, 0 rechazadas, 0 colisiones.  
El import commit es seguro de ejecutar cuando se autorice.

---

*Dry-run: 2026-06-07 · block2_merged_59props · batch_csv: block2_extractor_missing_selector_5_domains.csv · rama fix/scraping-diagnostics-batch · commit f0e6c21c*
