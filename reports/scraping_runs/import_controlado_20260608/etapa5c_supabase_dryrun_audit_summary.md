# ETAPA 5C - auditoria final publish_queue + Supabase dry-run

Fecha: 2026-06-08
Branch: `fix/scraping-diagnostics-batch`
HEAD inicial: `faeb06b49 docs(scraping): commit clean recovered properties to publish queue`
Objetivo: auditar las 38 filas `pending` en `publish_queue` y correr solo dry-run de publicacion Supabase.

## Guardrails

- No git push.
- No `publish_to_supabase.py --commit`.
- No Supabase real writes.
- No frontend.
- No `.env` modificado.
- No schema changes.
- No import.
- No geocoding.
- No publish_queue commit adicional.
- No cleanup/borrado.
- No cambios no relacionados.
- No soft-warning ni warning fuerte.

## Preflight

- Branch confirmada: `fix/scraping-diagnostics-batch`.
- HEAD confirmada: `faeb06b49` al inicio de la etapa.
- Procesos Python activos: ninguno detectado.
- Staging area Git: sin cambios staged antes de este reporte.
- `publish_queue` scope: 38 filas, exactamente las 38 del ids-file limpio: `True`.

## IDs auditados

Ids-file exacto: `reports/scraping_runs/import_controlado_20260608/staging_ids_publishqueue_clean_38_etapa5b.csv`

```text
81645,81646,81647,81648,81649,81650,81651,81652,81653,81654,81781,81782,81814,81815,81816,81817,81818,81819,81821,81823,81824,81825,81826,81827,81828,81829,81830,81831,81832,81833,81834,81835,81836,81837,81838,81839,81840,81841
```

## Auditoria read-only de las 38

| check | resultado |
| --- | --- |
| staging IDs exactos del ids-file | True |
| publish_queue.status pending | 38 / 38 |
| staging.status queued | 38 / 38 |
| geocoding_status done | 38 / 38 |
| lat/lon no NULL | 38 / 38 |
| precio y moneda OK | 38 / 38 |
| titulo razonable | 38 / 38 |
| URL y url_normalizada validas | 38 / 38 |
| portales prohibidos | 0 |
| duplicados URL/hash en las 38 | 0 |
| imagenes faltantes | 0 |
| ciudad/provincia warnings | 0 |
| score minimo/maximo | 85 / 100 |
| priority breakdown | {1: 36, 2: 2} |

### Imagenes

- Total imagenes referenciadas: 272.
- Minimo por propiedad: 3.
- Maximo por propiedad: 10.
- Faltantes: 0.

### Dominios

| dominio | count |
| --- | ---: |
| `inmobiliariamendocasa.com.ar` | 2 |
| `pagliaropropiedades.com.ar` | 26 |
| `svestudioinmobiliario.com.ar` | 10 |

### Inmobiliarias

| inmobiliaria_id | nombre | count |
| ---: | --- | ---: |
| 3532 | Mendocasa Lavalle | 2 |
| 4418 | Juan I. Pagliaro Propiedades | 26 |
| 6335 | SV Inmobiliaria | 10 |

## Estimacion Supabase read-only

- Conteo `propiedades` antes del dry-run: 91242.
- Hashes ya existentes en Supabase: 0.
- Inserts esperados por hash_dedup: 38.
- Updates esperados por hash_dedup: 0.
- `hash_dedup` se preservaria porque `staging_to_prop()` lo copia desde staging al payload.
- Error de lectura Supabase: `None`.

## Dry-run Supabase

Comando ejecutado:

```powershell
$env:USE_INTERNAL_DB='true'; python -B scripts/publish_to_supabase.py --dry-run --staging-ids-file reports/scraping_runs/import_controlado_20260608/staging_ids_publishqueue_clean_38_etapa5b.csv --limit 38 --max-supabase-writes 38 --min-score 60 --sleep 0
```

| metrica | count |
| --- | ---: |
| filas_queue_leidas | 38 |
| props_validas | 38 |
| publicadas_ok | 0 |
| failed | 0 |
| omitidas_por_validacion | 0 |
| writes_supabase_usados | 0 |
| accion_final | rollback |

Segun lectura previa de hashes, el dry-run representa 38 inserts esperados y 0 updates si se hiciera commit real.

## Validacion post dry-run

| check | resultado |
| --- | --- |
| Supabase `propiedades` count post dry-run | 91242 |
| Hashes de las 38 en Supabase post dry-run | 0 |
| publish_queue status post dry-run | pending:38 |
| staging status post dry-run | queued:38 |
| geocoding status post dry-run | done:38 |
| publish_queue errors | 0 |
| writes reales generados | 0 |
| frontend/.env tocados | no |

## Riesgos

- El dry-run no invoca `SupabasePropiedades.save_propiedades`, por diseno; por eso inserts/updates se estimaron con lectura read-only por `hash_dedup`.
- Las 38 son limpias, pero la publicacion real todavia puede fallar por constraints o reglas internas de `save_propiedades`.
- La cola ya esta `pending`; ejecutar una publicacion real futura debe usar el mismo ids-file exacto para evitar tomar otras filas pending historicas.

## Recomendacion

Conviene publicar las 38 como piloto controlado en la proxima etapa, usando el mismo `--staging-ids-file`, `--max-supabase-writes 38` y un reporte/validacion post-publicacion. No recomiendo partirlas mas: no hay warnings, duplicados ni updates esperados. Mantener fuera las 3 soft-warning y las 43 con warning fuerte.

Freno operativo: no se corrio `publish_to_supabase.py --commit`, no hubo writes Supabase, no se inicio ETAPA 5D.