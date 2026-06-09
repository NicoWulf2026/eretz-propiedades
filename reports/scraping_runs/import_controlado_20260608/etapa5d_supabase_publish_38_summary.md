# ETAPA 5D - Supabase publish piloto 38 propiedades limpias

Fecha: 2026-06-09
Branch: `fix/scraping-diagnostics-batch`
HEAD inicial: `aa51ba029 docs(scraping): audit publish queue dry-run before Supabase pilot`
Objetivo: publicar realmente en Supabase solo las 38 propiedades limpias del ids-file exacto y frenar.

## Guardrails

- No git push.
- No frontend modificado ni ejecutado.
- No `.env` modificado.
- No schema changes.
- No import.
- No geocoding.
- No publish_queue adicional.
- No cleanup/borrado.
- No filas fuera del ids-file.
- No soft-warning ni warning fuerte.
- No reintentos masivos.

## Preflight

- Branch confirmada: `fix/scraping-diagnostics-batch`.
- HEAD pre-publicacion: `aa51ba029` o posterior.
- Procesos Python activos: ninguno detectado antes de empezar.
- Ids-file obligatorio existe y tiene 38 IDs unicos.
- `publish_queue` antes del commit real: `pending:38`, IDs exactos, staging `queued:38`, geocoding `done:38`.
- Supabase antes del commit real: `propiedades=91242`, hashes existentes para las 38 = 0, URLs existentes = 0.

## IDs publicados

Ids-file usado: `reports/scraping_runs/import_controlado_20260608/staging_ids_publishqueue_clean_38_etapa5b.csv`

```text
81645,81646,81647,81648,81649,81650,81651,81652,81653,81654,81781,81782,81814,81815,81816,81817,81818,81819,81821,81823,81824,81825,81826,81827,81828,81829,81830,81831,81832,81833,81834,81835,81836,81837,81838,81839,81840,81841
```

## Dry-run inmediato

Comando:

```powershell
$env:USE_INTERNAL_DB='true'; python -B scripts/publish_to_supabase.py --dry-run --staging-ids-file reports/scraping_runs/import_controlado_20260608/staging_ids_publishqueue_clean_38_etapa5b.csv --limit 38 --max-supabase-writes 38 --min-score 60 --sleep 0
```

| metrica | count |
| --- | ---: |
| filas_queue_leidas | 38 |
| props_validas | 38 |
| failed | 0 |
| omitidas_por_validacion | 0 |
| writes_supabase_usados | 0 |
| accion_final | rollback |

## Publicacion real

Comando:

```powershell
$env:USE_INTERNAL_DB='true'; python -B scripts/publish_to_supabase.py --commit --staging-ids-file reports/scraping_runs/import_controlado_20260608/staging_ids_publishqueue_clean_38_etapa5b.csv --limit 38 --max-supabase-writes 38 --min-score 60 --sleep 0
```

| metrica | count |
| --- | ---: |
| filas_queue_leidas | 38 |
| props_validas | 38 |
| publicadas_ok | 38 |
| failed | 0 |
| omitidas_por_validacion | 0 |
| writes_supabase_usados | 38 |
| accion_final | commit |

## Verificacion Supabase

| check | resultado |
| --- | --- |
| count antes | 91242 |
| count despues | 91280 |
| delta count | 38 |
| propiedades encontradas por hash_dedup | 38 |
| IDs Supabase unicos | 38 |
| inserts reales estimados | 38 |
| updates reales estimados | 0 |
| duplicados por hash_dedup | 0 |
| duplicados por url_normalizada | 0 |
| campos criticos faltantes | none |
| imagenes faltantes | 0 |
| imagenes min/max/total | 3 / 10 / 272 |

### Dominios

| dominio | count |
| --- | ---: |
| `inmobiliariamendocasa.com.ar` | 2 |
| `pagliaropropiedades.com.ar` | 26 |
| `svestudioinmobiliario.com.ar` | 10 |

### Inmobiliarias

| inmobiliaria_id | count |
| ---: | ---: |
| 3532 | 2 |
| 4418 | 26 |
| 6335 | 10 |

## Verificacion Internal DB

| check | resultado |
| --- | --- |
| queue IDs exactos | True |
| publish_queue status | {'done': 38} |
| publish_queue priority | {1: 36, 2: 2} |
| publish_queue errores | 0 |
| staging status | {'published': 38} |
| geocoding status | {'done': 38} |

## Vista frontend/mapa

No se ejecuto ni modifico frontend. Validacion read-only contra la vista usada por el frontend, `v_propiedades_frontend_mapa`:

| check | resultado |
| --- | --- |
| propiedades de la publicacion encontradas en la vista | 38 / 38 |
| faltantes en vista | 0 |
| estado activo | 38 / 38 |
| tiene_imagen_real | 38 / 38 |
| error vista | None |

## Riesgos restantes

- La publicacion fue exitosa para las 38 limpias; no se incluyeron soft-warning ni warning fuerte.
- Quedan fuera del piloto las 3 soft-warning y las 43 con warning fuerte; deben revisarse en etapa separada.
- El working tree sigue sucio con cambios no relacionados ya inventariados; no mezclar en commits futuros.

## Proximo paso recomendado

Frenar y validar visualmente en una etapa posterior si se autoriza frontend. Luego decidir si publicar las 3 soft-warning tras normalizar ciudad/provincia o atacar el bloque de 43 con problemas de imagen/titulo. No iniciar otro batch ni limpiar archivos en esta etapa.

Freno operativo cumplido: no push, no batch adicional, no cleanup, no frontend.