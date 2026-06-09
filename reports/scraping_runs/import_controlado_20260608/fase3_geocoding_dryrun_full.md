# Geocode imported staging

Fecha: 2026-06-08 20:36
Modo: dry-run
Origen: all_staging
Proveedor: Nominatim

## Resumen

- pendientes_detectadas: 131
- candidatas_geocodificables: 39
- descartadas_por_direccion_ambigua: 92
- ya_geocodificadas_lote: 512
- done: 0
- failed: 0
- skipped: 92
- requests_usados: 0
- max_requests: 30
- accion_final: rollback

## Estados del lote

- done: 512
- failed: 1
- pending: 375
- skipped: 112

## Resultados de esta corrida

- probe: 39
- skipped: 92

## Readiness / errores esperados

- garbage_address: 64
- geocoding_not_ready: 8
- geocoding_ready_review: 20
- geocoding_ready_safe: 39

## Seguridad

- no_toca_supabase: true
- no_publica_supabase: true
- no_toca_publish_queue: true
- no_modifica_env: true
- no_borra_datos: true
- no_commit_git: true
- no_push_git: true
