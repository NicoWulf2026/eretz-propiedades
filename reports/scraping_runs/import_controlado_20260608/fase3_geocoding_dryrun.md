# Geocode imported staging

Fecha: 2026-06-08 20:36
Modo: dry-run
Origen: all_staging
Proveedor: Nominatim

## Resumen

- pendientes_detectadas: 20
- candidatas_geocodificables: 0
- descartadas_por_direccion_ambigua: 20
- ya_geocodificadas_lote: 512
- done: 0
- failed: 0
- skipped: 20
- requests_usados: 0
- max_requests: 30
- accion_final: rollback

## Estados del lote

- done: 512
- failed: 1
- pending: 375
- skipped: 112

## Resultados de esta corrida

- skipped: 20

## Readiness / errores esperados

- garbage_address: 19
- geocoding_not_ready: 1

## Seguridad

- no_toca_supabase: true
- no_publica_supabase: true
- no_toca_publish_queue: true
- no_modifica_env: true
- no_borra_datos: true
- no_commit_git: true
- no_push_git: true
