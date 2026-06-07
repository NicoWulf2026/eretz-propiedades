# Dry-run import filtrado — Bloque 2: Fix I aplicado

- Fecha: 2026-06-07
- Modo: **DRY-RUN** — sin escritura a Neon
- Fix aplicado: **Fix I** (global) — excluir URLs de imagen + listing-page titles
- Total original: 59 · Rechazadas: **5** · Importables: **54**
- Input: `data/scraping_batches/block2_merged_59props/captured/` (4 JSONs)
- Batch CSV: `data/block2_extractor_missing_selector_5_domains.csv`

---

## Comparativa antes/después de Fix I

| Métrica | Sin Fix I | Con Fix I |
|---|---|---|
| Detectadas | 59 | 59 |
| **Rechazadas** | **0** | **5** |
| **Importables** | **59** | **54** |
| url_is_image_file | 0 | 4 |
| ui_contaminated_title | 0 | 1 |
| Duplicados bloqueados | 0 | 0 |

---

## Los 5 rechazados

### 4 × url_is_image_file (dilello — Fix I)
Thumbnails `.jfif` cuyo filename contenía slug de propiedad. Las propiedades reales existen en el batch con score=75.

### 1 × ui_contaminated_title (tonyzorrilla — Fix I)
URL: `terrenos-a-la-venta-rawson-playa-union/` · Título: `Terrenos a la venta | Rawson & Playa Unión`
Diagnóstico: página de categoría/listado WordPress — no es ficha individual.

---

## Por dominio

| Dominio | Total | Rechazadas | Importables |
|---|---|---|---|
| tonyzorrilla.com.ar | 30 | 1 (listing page) | **29** |
| dilellopropiedades.com | 15 | 4 (.jfif) | **11** |
| luciafrolik.com.ar | 12 | 0 | **12** ✅ |
| inmobiliariaescuza.com | 2 | 0 | **2** ✅ |
| **TOTAL** | **59** | **5** | **54** |

---

## Resumen script (output original)

- archivos_leidos: 4
- propiedades_detectadas: 59
- offset: 0
- propiedades_procesadas: 59
- importables: 54
- importadas: 0
- con_warnings: 54
- rechazadas: 5
- accion_final: dry-run/no-writes

## Duplicados — detalle por categoría

Nota de negocio: solo se bloquean duplicados exactos de la misma fuente
(mismo inmobiliaria_id + misma URL). Las demás categorías son marcadores
informativos; no bloquean el import.

### Bloqueados (misma publicación exacta)
- duplicate_exact_same_source (dentro del batch): 0
- skipped_duplicate_in_propiedades_raw: 0
- skipped_duplicate_in_propiedades_staging: 0

### Marcados — NO bloqueados (publicaciones legítimas)
- possible_cross_agency_duplicate_within_batch: 0
- possible_cross_agency_duplicate_in_neon: 0
- possible_same_address_within_batch: 2

### Totales en Neon (antes de este import)
- duplicate_in_propiedades_raw: 0
- duplicate_in_propiedades_staging: 0

## Campos faltantes principales

- missing_images: 4
- missing_location: 45

## Issues por tipo

- low_quality_score: 6
- missing_images: 4
- missing_location: 45
- possible_same_address_within_batch: 2
- source_test_mode_id_rewritten: 59
- ui_contaminated_title: 1
- url_is_image_file: 4

## Rechazos

- ui_contaminated_title: 1
- url_is_image_file: 4

## Seguridad

- no_toca_supabase: true
- no_publica_supabase: true
- no_toca_publish_queue: true
- no_modifica_env: true
- no_borra_datos: true
- no_commit_git: true
- no_push_git: true
- duplicados_cross_agency_NO_bloqueados: true
- duplicados_misma_direccion_NO_bloqueados: true

---

## Evaluación: ¿Es seguro el commit real?

**SÍ.** 54 props limpias, 5 rechazadas correctamente, 0 colisiones contra Neon, 0 falsos positivos confirmados.

### Comando cuando se autorice:

```bash
USE_INTERNAL_DB=true python scripts/import_captured_props_to_neon.py \
  --input-dir data/scraping_batches/block2_merged_59props/captured \
  --batch-csv data/block2_extractor_missing_selector_5_domains.csv \
  --commit \
  --report reports/scraping_runs/block2_extractor_missing_selector_run_20260607/import_commit_54_props.md
```

---

## FASE 5 — Freno activo

NO importado · NO validado · NO geocoding · NO publish_queue · NO Supabase · NO push
**Esperando autorización.**

---

*Dry-run filtrado: 2026-06-07 · Fix I — 54 importables · rama fix/scraping-diagnostics-batch · commit f0e6c21c*
