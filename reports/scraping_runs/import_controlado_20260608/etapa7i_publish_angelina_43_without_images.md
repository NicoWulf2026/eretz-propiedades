# ETAPA 7I - Publicacion Angelina 43 sin imagenes

Fecha: 2026-06-09

## Criterio de producto aplicado

Se cambio el criterio de publicacion: la falta de imagenes, ciudad/provincia, titulos poco detallados u otros datos blandos incompletos ya no bloquea la publicacion de propiedades reales. Esos puntos quedan documentados como pendientes de enriquecimiento posterior.

No se publicaron propiedades fuera del set de Angelina de ETAPA 7G. No se hizo `git push`, no se toco frontend, no se ejecuto SQL, no hubo import nuevo, no hubo geocoding y no se tocaron las 41 propiedades ya publicadas salvo lecturas de verificacion.

## IDs publicados

Fuente principal: `staging_ids_warning_fuerte_43_etapa7g.csv`.

Ids-file usado para esta etapa: `staging_ids_angelina_publish_all_43_etapa7i.csv`.

Staging IDs:

```text
81700, 81705, 81706, 81712, 81719, 81720, 81721, 81724, 81727, 81728,
81733, 81734, 81735, 81736, 81737, 81739, 81740, 81742, 81743, 81745,
81746, 81747, 81749, 81752, 81753, 81754, 81755, 81757, 81758, 81759,
81760, 81761, 81762, 81763, 81765, 81767, 81769, 81773, 81774, 81775,
81776, 81778, 81780
```

Supabase IDs insertados:

```text
93578, 93579, 93580, 93581, 93582, 93583, 93584, 93585, 93586, 93587,
93588, 93589, 93590, 93591, 93592, 93593, 93594, 93595, 93596, 93597,
93598, 93599, 93600, 93601, 93602, 93603, 93604, 93605, 93606, 93607,
93608, 93609, 93610, 93611, 93612, 93613, 93614, 93615, 93616, 93617,
93618, 93619, 93620
```

## Validacion previa

- Total exacto del ids-file: 43.
- Filas encontradas en `propiedades_staging`: 43.
- `propiedades_staging.status`: `staging=43`.
- `geocoding_status`: `done=43`.
- `inmobiliaria_id`: `3531=43`.
- `validation_score`: `75=43`.
- Filas previas en `publish_queue`: 0.
- Existentes previos en Supabase por `hash_dedup`: 0.
- Existentes previos en Supabase por `url_normalizada`: 0.
- Duplicados internos por hash/url: 0.
- Portales prohibidos: 0.
- Faltantes duros: precio 0, moneda 0, lat/lon 0, hash 0, URL 0, titulo 0.
- Supabase count previo: 91.283.

## Warnings aceptados

- `missing_images`: 43/43.
- `ciudad` NULL en staging: 43/43.
- `provincia` NULL en staging: 43/43.
- Titulos genericos tipo `Propiedad en`, `Casa en` o `Local en`: 6/43.
- `v_propiedades_frontend_mapa.tiene_imagen_real=false`: 43/43.

Estos warnings no fueron tratados como bloqueantes por el nuevo criterio de producto.

## Publish queue dry-run

Comando:

```powershell
$env:USE_INTERNAL_DB='true'; python -B scripts\build_publish_queue.py --dry-run --ids-file reports\scraping_runs\import_controlado_20260608\staging_ids_angelina_publish_all_43_etapa7i.csv --limit 43 --min-score 60
```

Resultado:

- `filas_leidas=43`.
- `encoladas=43`.
- `ya_en_cola=0`.
- `omitidas_por_motivo`: none.
- `priorities`: `2=43`.
- `accion_final=rollback`.

## Publish queue commit

Comando:

```powershell
$env:USE_INTERNAL_DB='true'; python -B scripts\build_publish_queue.py --commit --ids-file reports\scraping_runs\import_controlado_20260608\staging_ids_angelina_publish_all_43_etapa7i.csv --limit 43 --min-score 60
```

Resultado:

- `filas_leidas=43`.
- `encoladas=43`.
- `ya_en_cola=0`.
- `omitidas_por_motivo`: none.
- `priorities`: `2=43`.
- `accion_final=commit`.

Verificacion post-queue:

- `publish_queue`: `pending=43`.
- `priority`: `2=43`.
- `error_message`: 0 filas.
- `propiedades_staging.status`: `queued=43`.
- `geocoding_status`: `done=43`.

## Supabase dry-run

Comando:

```powershell
$env:USE_INTERNAL_DB='true'; python -B scripts\publish_to_supabase.py --dry-run --staging-ids-file reports\scraping_runs\import_controlado_20260608\staging_ids_angelina_publish_all_43_etapa7i.csv --limit 43 --max-supabase-writes 43 --min-score 60 --sleep 0
```

Resultado:

- `filas_queue_leidas=43`.
- `props_validas=43`.
- `publicadas_ok=0`.
- `failed=0`.
- `omitidas_por_validacion`: none.
- `writes_supabase_usados=0`.
- `accion_final=rollback`.

## Supabase commit

Comando:

```powershell
$env:USE_INTERNAL_DB='true'; python -B scripts\publish_to_supabase.py --commit --staging-ids-file reports\scraping_runs\import_controlado_20260608\staging_ids_angelina_publish_all_43_etapa7i.csv --limit 43 --max-supabase-writes 43 --min-score 60 --sleep 0
```

Resultado:

- `filas_queue_leidas=43`.
- `props_validas=43`.
- `publicadas_ok=43`.
- `failed=0`.
- `omitidas_por_validacion`: none.
- `writes_supabase_usados=43`.
- `accion_final=commit`.

## Verificacion final

Supabase:

- Count antes/despues: 91.283 -> 91.326.
- Propiedades encontradas por `hash_dedup`: 43/43.
- Inserts reales: 43.
- Updates esperados/reales: 0.
- `inmobiliaria_id`: `3531=43`.
- IDs insertados: 93578 a 93620.
- Duplicados por hash/url dentro del set publicado: 0.
- Faltantes criticos post-publicacion: titulo 0, precio 0, moneda 0, lat/lon 0.
- Imagenes: 43 quedaron sin imagen real, aceptado por criterio de producto.

Internal DB:

- `publish_queue.status`: `done=43`.
- `publish_queue.priority`: `2=43`.
- `publish_queue.error_message`: 0 filas.
- `propiedades_staging.status`: `published=43`.
- `geocoding_status`: `done=43`.

Vista frontend/mapa:

- `v_propiedades_frontend_mapa`: 43/43 visibles.
- `inmobiliaria_nombre`: `Inmobiliaria Angelina Martinez=43`.
- `tiene_imagen_real=false`: 43/43.
- Faltantes en vista por Supabase ID: 0.

## Pendientes de enriquecimiento

- Recuperar fotos reales si aparece una fuente publica confiable o se mejora el scraping de detalle.
- Enriquecer ciudad/provincia desde URL, coordenadas o datos canónicos de Angelina.
- Mejorar titulos genericos cuando haya evidencia suficiente.
- Revisar UX de cards sin imagen real en el frontend general.

## Riesgos

- Las 43 propiedades son reales y publicables, pero se veran sin imagen principal.
- La ubicacion visible depende de lat/lon porque `ciudad` y `provincia` quedaron incompletas en staging.
- Algunos titulos son poco descriptivos, aunque tienen precio, moneda, URL fuente y coordenadas.

## Recomendacion proxima

Hacer un chequeo visual/read-only del frontend para las 43 nuevas y luego abrir una etapa de enriquecimiento no bloqueante para imagenes, ciudad/provincia y titulos de Angelina.
