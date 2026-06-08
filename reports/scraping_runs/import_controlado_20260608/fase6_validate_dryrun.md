# Validate imported raw properties

Fecha: 2026-06-08 20:20
Modo: dry-run
Origen: all_raw
Destino: public.propiedades_staging

## Resumen

- raw_detectadas: 199
- candidatas_a_staging: 199
- pasaron_a_staging: 0
- rechazadas: 0
- warnings: 265
- duplicadas: 0
- accion_final: rollback

## Issues principales

- geocoding_skipped_approx_location: 18
- missing_images: 89
- missing_location: 158

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
