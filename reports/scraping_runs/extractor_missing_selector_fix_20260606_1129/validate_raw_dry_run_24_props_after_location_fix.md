# Validate dry-run — post Fix A (location desde hostname)

Fecha: 2026-06-06 17:35
Modo: dry-run (rollback — sin cambios en Neon)
Filtro: --source captured_json --created-after 2026-06-06T00:00:00 --limit 30
Fix aplicado: A — _infer_location_from_hostname() en normalize_location_fields()

---

## Comparativa antes/despues de Fix A

| Metrica | Antes Fix A | Despues Fix A | Delta |
|---|---|---|---|
| raw_detectadas | 24 | 24 | — |
| validadas | 24 | 24 | — |
| rechazadas | 0 | 0 | — |
| missing_location | 24 | 3 | -21 CORREGIDO |
| location_inferred_from_text | 0 | 21 | +21 |
| geocoding_skipped_approx_location | 0 | 14 | +14 |

---

## Resumen original del script

- raw_detectadas: 24
- candidatas_a_staging: 24
- pasaron_a_staging: 0
- rechazadas: 0
- warnings: 38
- duplicadas: 0
- accion_final: rollback

## Issues principales

- geocoding_skipped_approx_location: 14
- location_inferred_from_text: 21
- missing_location: 3

## Campos criticos faltantes o invalidos

- none: 0

---

## Analisis de los 21 con location_inferred_from_hostname

### innoacafayate.com — 17 props
Token: "cafayate" en hostname "innoacafayate"
ciudad = Cafayate, provincia = Salta (inferidos)

### camposdelapampa.com.ar — 4 props
Token: "lapampa" en hostname "camposdelapampa"
ciudad = NULL, provincia = La Pampa (solo provincia inferida)

### watsonpropiedades.com — 3 props
Sin token coincidente. missing_location: 3 — correcto, no inventar.

---

## geocoding_status esperado en staging

| Grupo | Props | direccion_normalizada | ciudad/provincia | geocoding_status |
|---|---|---|---|---|
| innoacafayate | 7 | real | Cafayate / Salta | pending — geocodificable |
| innoacafayate | 10 | NULL (Fix C) | Cafayate / Salta | skipped — sin dir. precisa |
| camposdelapampa | 4 | NULL (Fix D) | NULL / La Pampa | skipped — sin dir. precisa |
| watson | 3 | NULL | NULL / NULL | pending (sin nada util) |

Las 7 innoacafayate con direccion real + ciudad=Cafayate, provincia=Salta
tendran geocoding de alta probabilidad de exito.

---

## Validation scores estimados

| Grupo | Escenario | Score antes | Score ahora |
|---|---|---|---|
| inno | con precio + direccion real | 85 | 100 |
| inno | con precio + NULL address | 85 | 95 |
| inno | sin precio + direccion real | 65 | 80 |
| inno | sin precio + NULL address | 65 | 75 |
| camposdelapampa | sin precio + NULL + solo prov | 65 | 75 |
| watson | sin precio + sin location | 65 | 65 |

---

## Conviene hacer validate con commit?

SI. No hay bloqueantes:
- rechazadas: 0
- missing_location: 3 (solo watson — esperado)
- campos criticos: 0
- 7 props de innoacafayate son ahora geocodificables con alta precision

---

## Comando para validate con commit (NO ejecutar sin autorizacion)

USE_INTERNAL_DB=true python scripts/validate_raw_properties.py \
  --source captured_json \
  --created-after "2026-06-06T00:00:00" \
  --limit 30 \
  --commit \
  --report "reports/scraping_runs/extractor_missing_selector_fix_20260606_1129/validate_raw_commit_24_props.md"

Esperando confirmacion antes de ejecutar.

---

## Seguridad

- no_toca_supabase: true
- no_publica_supabase: true
- no_toca_publish_queue: true
- no_modifica_env: true
- no_borra_datos: true
- no_commit_git: true
- no_push_git: true
