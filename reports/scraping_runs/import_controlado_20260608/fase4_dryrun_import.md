# Import captured props to Neon

Fecha: 2026-06-08 20:07
Modo: dry-run
Destino: public.propiedades_raw

## Resumen

- archivos_leidos: 7
- propiedades_detectadas: 195
- offset: 0
- propiedades_procesadas: 195
- importables: 169
- importadas: 0
- con_warnings: 195
- rechazadas: 0
- accion_final: dry-run/no-writes

## Duplicados — detalle por categoría

Nota de negocio: solo se bloquean duplicados exactos de la misma fuente
(mismo inmobiliaria_id + misma URL). Las demás categorías son marcadores
informativos; no bloquean el import.

### Bloqueados (misma publicación exacta)
- duplicate_exact_same_source (dentro del batch): 0
- skipped_duplicate_in_propiedades_raw: 26
- skipped_duplicate_in_propiedades_staging: 0

### Marcados — NO bloqueados (publicaciones legítimas)
- possible_cross_agency_duplicate_within_batch: 0
- possible_cross_agency_duplicate_in_neon: 0
- possible_same_address_within_batch: 51

### Totales en Neon (antes de este import)
- duplicate_in_propiedades_raw: 26
- duplicate_in_propiedades_staging: 0

## Campos faltantes principales

- missing_images: 89
- missing_location: 164
- missing_type: 32

## Issues por tipo

- duplicate_in_propiedades_raw: 26
- invalid_address: 35
- low_quality_score: 55
- missing_images: 89
- missing_location: 164
- missing_type: 32
- office_address_suspected: 10
- possible_same_address_within_batch: 51
- source_test_mode_id_rewritten: 195

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
