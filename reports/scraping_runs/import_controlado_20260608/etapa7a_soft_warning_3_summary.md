# ETAPA 7A - Soft-warning 3 propiedades

Fecha: 2026-06-09

## Resultado general

Se auditaron y publicaron las 3 propiedades soft-warning que habían quedado excluidas en ETAPA 5B:

- 81822
- 81842
- 81843

Resultado final: 3/3 publicadas correctamente.

No se tocaron las 43 propiedades con warning fuerte, ni pending/skipped/failed, ni frontend, ni schema, ni imports, ni geocoding.

## Auditoría inicial

Warning original para las 3:

- `missing_city_or_province_but_coords_present`

Hallazgos antes de corregir:

| staging_id | Fuente | Título | Precio | Moneda | Latitud | Longitud | Ciudad | Provincia | Score | Estado |
|---:|---|---|---:|---|---:|---:|---|---|---:|---|
| 81822 | Pagliaro | Casas en Venta - Tucumán y Trabajadores Municipales | 110000 | USD | -37.290944 | -59.154507 | NULL | NULL | 85 | staging/done |
| 81842 | Pagliaro | Locales en Venta - Reynoso y La Pampa | 55000 | USD | -37.295587 | -59.157812 | NULL | NULL | 85 | staging/done |
| 81843 | Pagliaro | Departamentos en Venta - Reynoso y La Pampa | 62000 | USD | -37.295536 | -59.157833 | NULL | NULL | 85 | staging/done |

Validaciones previas:

- URLs fuente: HTTP 200 en las 3.
- Primeras imágenes reales: HTTP 200 en las 3.
- Imágenes reales detectadas: 81822 tiene 6; 81842 tiene 4; 81843 tiene 4.
- Duplicados internos por `url_normalizada`: 0.
- Duplicados internos por `hash_dedup`: 0.
- Existentes previos en Supabase por hash/url: 0.
- `publish_queue` previa para estos IDs: 0 filas.
- Coordenadas: dentro de zona esperada de Tandil.
- URL normalizada: contiene `en-tandil` en las 3.

## Corrección aplicada

Se aplicó una corrección mínima, reversible y acotada a los tres `staging_id`, con guardas estrictas por estado, geocoding, coordenadas y URL:

- `ciudad = 'Tandil'`
- `provincia = 'Buenos Aires'`

Filas actualizadas: 3/3.

## IDs file

Archivo usado:

`reports/scraping_runs/import_controlado_20260608/staging_ids_soft_warning_publishable_etapa7a.csv`

Contenido:

```csv
staging_id
81822
81842
81843
```

## publish_queue dry-run

Comando:

```powershell
$env:USE_INTERNAL_DB='true'; python -B scripts/build_publish_queue.py --ids-file reports/scraping_runs/import_controlado_20260608/staging_ids_soft_warning_publishable_etapa7a.csv --limit 3 --min-score 60
```

Resultado:

- filas_leidas: 3
- encoladas: 3
- ya_en_cola: 0
- omitidas: 0
- priorities: priority 2 = 3
- accion_final: rollback

## publish_queue commit

Comando:

```powershell
$env:USE_INTERNAL_DB='true'; python -B scripts/build_publish_queue.py --commit --ids-file reports/scraping_runs/import_controlado_20260608/staging_ids_soft_warning_publishable_etapa7a.csv --limit 3 --min-score 60
```

Resultado:

- filas_leidas: 3
- encoladas: 3
- ya_en_cola: 0
- omitidas: 0
- priorities: priority 2 = 3
- accion_final: commit

Verificación post-queue:

- 81822: staging `queued`, queue `pending`, priority 2.
- 81842: staging `queued`, queue `pending`, priority 2.
- 81843: staging `queued`, queue `pending`, priority 2.
- Extras dentro del rango 81822-81843: 0.

## Supabase dry-run

Comando:

```powershell
$env:USE_INTERNAL_DB='true'; python -B scripts/publish_to_supabase.py --dry-run --staging-ids-file reports/scraping_runs/import_controlado_20260608/staging_ids_soft_warning_publishable_etapa7a.csv --limit 3 --max-supabase-writes 3 --min-score 60 --sleep 0
```

Resultado:

- filas_queue_leidas: 3
- props_validas: 3
- failed: 0
- omitidas_por_validacion: 0
- writes_supabase_usados: 0
- accion_final: rollback
- hashes existentes antes: 0
- count Supabase antes: 91.280

## Supabase commit

Comando:

```powershell
$env:USE_INTERNAL_DB='true'; python -B scripts/publish_to_supabase.py --commit --staging-ids-file reports/scraping_runs/import_controlado_20260608/staging_ids_soft_warning_publishable_etapa7a.csv --limit 3 --max-supabase-writes 3 --min-score 60 --sleep 0
```

Resultado:

- filas_queue_leidas: 3
- props_validas: 3
- publicadas_ok: 3
- failed: 0
- omitidas_por_validacion: 0
- writes_supabase_usados: 3
- accion_final: commit

Supabase:

- count antes: 91.280
- count después: 91.283
- inserts reales: 3
- updates reales: 0
- hashes encontrados: 3/3
- duplicados por hash: 0, cada hash tiene count 1.

IDs Supabase insertados:

- 81822 -> propiedad 93575
- 81842 -> propiedad 93576
- 81843 -> propiedad 93577

## Verificación final

Internal DB:

| staging_id | staging_status | geocoding_status | queue_status | priority | error |
|---:|---|---|---|---:|---|
| 81822 | published | done | done | 2 | NULL |
| 81842 | published | done | done | 2 | NULL |
| 81843 | published | done | done | 2 | NULL |

Supabase `propiedades`:

| supabase_id | staging_id | Precio | Moneda | Ciudad | Provincia | Latitud | Longitud | Imágenes |
|---:|---:|---:|---|---|---|---:|---:|---:|
| 93575 | 81822 | 110000 | USD | Tandil | Buenos Aires | -37.290944 | -59.154507 | 10 |
| 93576 | 81842 | 55000 | USD | Tandil | Buenos Aires | -37.295587 | -59.157812 | 8 |
| 93577 | 81843 | 62000 | USD | Tandil | Buenos Aires | -37.295536 | -59.157833 | 8 |

Vista `v_propiedades_frontend_mapa`:

- Las 3 aparecen en la vista.
- La vista usa `ciudad_final` y `provincia_final`.
- `ciudad_final = Tandil` y `provincia_final = Buenos Aires` en las 3.
- `tiene_imagen_real = true` en las 3.

## Riesgos y notas

- La vista frontend muestra `inmobiliaria_nombre = Re/Max Jardin` para estas propiedades aunque el dominio fuente es Pagliaro. No se corrigió en esta etapa porque implicaría revisar mapeo de inmobiliaria/datos maestros fuera del alcance.
- La primera imagen seleccionada por la vista es logo de Pagliaro, aunque existen imágenes reales de propiedad en el array. Esto ya no bloqueó publicación porque `tiene_imagen_real = true`, pero conviene tratar la priorización de imagen principal en una etapa separada.
- No se detectaron duplicados por hash ni por URL normalizada en las verificaciones realizadas.

## Recomendación próxima

Dar por cerrada ETAPA 7A. Antes de avanzar sobre las 43 con warning fuerte, conviene abrir una etapa separada para:

- auditar mapeo de `inmobiliaria_id`/nombre visible en la vista;
- mejorar la selección de `imagen_principal_real` para evitar logos cuando hay fotos reales;
- luego recién revisar un subconjunto chico de las 43 con warning fuerte.
