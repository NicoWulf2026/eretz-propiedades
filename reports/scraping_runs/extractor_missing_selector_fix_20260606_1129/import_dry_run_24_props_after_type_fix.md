# Import captured props to Neon

Fecha: 2026-06-06 17:09
Modo: dry-run
Destino: public.propiedades_raw

## Resumen

- archivos_leidos: 3
- propiedades_detectadas: 24
- offset: 0
- propiedades_procesadas: 24
- importables: 24
- importadas: 0
- con_warnings: 24
- rechazadas: 0
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
- possible_same_address_within_batch: 0

### Totales en Neon (antes de este import)
- duplicate_in_propiedades_raw: 0
- duplicate_in_propiedades_staging: 0

## Campos faltantes principales

- missing_location: 24

## Issues por tipo

- invalid_address: 4
- low_quality_score: 3
- missing_location: 24
- office_address_suspected: 10
- operation_inferred_from_url_path: 6
- source_test_mode_id_rewritten: 24
- tipo_inferred_from_rural_domain: 3

## Rechazos

- none: 0

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
