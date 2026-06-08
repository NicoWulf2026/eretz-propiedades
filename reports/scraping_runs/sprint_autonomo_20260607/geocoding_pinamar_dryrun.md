# Geocode imported staging

Fecha: 2026-06-07 22:37
Modo: dry-run
Origen: all_staging
Proveedor: Nominatim

## Resumen

- pendientes_detectadas: 20
- candidatas_geocodificables: 20
- descartadas_por_direccion_ambigua: 0
- ya_geocodificadas_lote: 512
- done: 0
- failed: 0
- skipped: 0
- requests_usados: 0
- max_requests: 30
- accion_final: rollback

## Estados del lote

- done: 512
- failed: 1
- pending: 375
- skipped: 112

## Resultados de esta corrida

- probe: 20

## Readiness / errores esperados

- geocoding_ready_safe: 20

## Seguridad

- no_toca_supabase: true
- no_publica_supabase: true
- no_toca_publish_queue: true
- no_modifica_env: true
- no_borra_datos: true
- no_commit_git: true
- no_push_git: true
