# Import captured props to Neon

Fecha: 2026-06-08 20:15
Modo: commit
Destino: public.propiedades_raw

## Resumen

- archivos_leidos: 8
- propiedades_detectadas: 41
- offset: 10
- propiedades_procesadas: 31
- importables: 30
- importadas: 30
- con_warnings: 31
- rechazadas: 0
- accion_final: commit

## Duplicados — detalle por categoría

Nota de negocio: solo se bloquean duplicados exactos de la misma fuente
(mismo inmobiliaria_id + misma URL). Las demás categorías son marcadores
informativos; no bloquean el import.

### Bloqueados (misma publicación exacta)
- duplicate_exact_same_source (dentro del batch): 0
- skipped_duplicate_in_propiedades_raw: 1
- skipped_duplicate_in_propiedades_staging: 0

### Marcados — NO bloqueados (publicaciones legítimas)
- possible_cross_agency_duplicate_within_batch: 0
- possible_cross_agency_duplicate_in_neon: 0
- possible_same_address_within_batch: 14

### Totales en Neon (antes de este import)
- duplicate_in_propiedades_raw: 1
- duplicate_in_propiedades_staging: 0

## Campos faltantes principales

- missing_location: 3

## Issues por tipo

- duplicate_in_propiedades_raw: 1
- missing_location: 3
- office_address_suspected: 17
- possible_same_address_within_batch: 14
- source_test_mode_id_rewritten: 31

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
