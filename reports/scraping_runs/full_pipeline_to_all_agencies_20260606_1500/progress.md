# Pipeline Completo — Progreso

Inicio: 2026-06-06 15:00
Rama: fix/scraping-diagnostics-batch
Último commit: 69cac0db

---

## Fases autorizadas esta sesión

| Fase | Estado | Inicio | Fin | Resultado |
|---|---|---|---|---|
| FASE 0 — Preflight | ✅ COMPLETADO | 15:00 | 15:10 | Todo OK |
| FASE 1 — Auditoría post-checkpoint | ✅ COMPLETADO | 19:00 | 22:30 | post_checkpoint_audit.md |
| FASE 2 — Re-scrape controlado | ✅ COMPLETADO | 22:35 | 22:43 | 24 props, 0 errores, fixes validados |
| FASE 3 — Fix G: Watson sin precio | ✅ COMPLETADO | 20:00 | 22:50 | Root cause + fix implementado + validado |
| FASE 4+ | NO AUTORIZADO | — | — | — |

---

## Props en Neon (estado inicial)

| Tabla | Total | Notas |
|---|---|---|
| propiedades_raw | 76.545 | 76.487 validated |
| propiedades_staging | 76.447 | geo_done=18.843, geo_pending=42.499, geo_failed=1.989 |
| geocoding_results | 7.218 | success=5.229, error=1.989 |
| publish_queue | 40 | pending=30, done=10 |
| Batch actual (id>81035) | 24 staging | 0 en publish_queue |

---

## Actualizaciones

### Nuevos fixes aplicados esta sesión

| Fix | Archivo | Línea | Tipo | Estado |
|---|---|---|---|---|
| Fix G — JSON-LD sin precio → enriquecer desde HTML | `scraper/scraper_propiedades.py` | ~7863 | Global | ✅ VALIDADO |

### Nuevos batches

| Batch | Agencias | Props | Resultado |
|---|---|---|---|
| rescrape_controlled_20260606_fase2 | Inno + Campos + Watson (pre-FixG) | 24 | Fixes A/B/E validados |
| rescrape_watson_fixG_20260606 | Watson (post-FixG) | 3 | 2/3 precios extraídos ✅ |

### Reportes generados

- `post_checkpoint_audit.md` ✅
- `rescrape_controlled_report.md` ✅
- `watson_price_fix_report.md` ✅
- `phase_summary.md` ✅
