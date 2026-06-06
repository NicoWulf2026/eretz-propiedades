# Validate imported raw properties

Fecha: 2026-06-06 17:43
Modo: commit
Origen: captured_json
Destino: public.propiedades_staging

## Resumen

- raw_detectadas: 24
- candidatas_a_staging: 24
- pasaron_a_staging: 24
- rechazadas: 0
- warnings: 38
- duplicadas: 0
- accion_final: commit

## Issues principales

- geocoding_skipped_approx_location: 14
- location_inferred_from_text: 21
- missing_location: 3

## Campos criticos faltantes o invalidos

- none: 0

## Seguridad

- no_toca_supabase: true
- no_publica_supabase: true
- no_toca_publish_queue: true
- no_modifica_env: true
- no_borra_datos: true
- no_commit_git: true
- no_push_git: true
