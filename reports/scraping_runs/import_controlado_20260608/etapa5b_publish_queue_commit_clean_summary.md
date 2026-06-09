# ETAPA 5B - publish_queue commit grupo limpio

Fecha: 2026-06-08
Branch: `fix/scraping-diagnostics-batch`
HEAD inicial: `ddcbde725 docs(scraping): add publish queue dry-run audit for recovered properties`
Objetivo: commit controlado de publish_queue solo para el grupo limpio de propiedades recuperadas.

## Guardrails

- No git push.
- No Supabase publish.
- No `publish_to_supabase.py --commit`.
- No frontend.
- No `.env` modificado.
- No schema changes.
- No import.
- No geocoding.
- No Playwright.
- No borrado de archivos ni datos.
- No se incluyeron las 84 masivamente.
- No se incluyeron las 43 con imagen/titulo debil.
- No se incluyeron failed/skipped/pending.

## Preflight

- Branch confirmada: `fix/scraping-diagnostics-batch`.
- HEAD pre-commit queue: `ddcbde725`.
- Staging area Git: sin cambios staged antes de generar artefactos 5B.
- Procesos Python activos: ninguno detectado por `Get-Process python,python3,py`.
- `publish_queue` para el scope antes de empezar: 0 filas.

## Scope

| estado geocoding | count |
| --- | ---: |
| done | 92 |
| pending | 101 |
| skipped | 4 |
| failed | 2 |

- Scope total: 199 staging.
- Done con coords antes de queue: 92.
- Candidatas tecnicas 5A: 84.
- Grupo limpio reconstruido desde DB: 38.
- Grupo soft-warning ciudad/provincia: 3, no incluido.
- Grupo con warning fuerte imagen/titulo u otros: 43, no incluido.

## IDs incluidos

Ids-file usado: `reports/scraping_runs/import_controlado_20260608/staging_ids_publishqueue_clean_38_etapa5b.csv`

```text
81645,81646,81647,81648,81649,81650,81651,81652,81653,81654,81781,81782,81814,81815,81816,81817,81818,81819,81821,81823,81824,81825,81826,81827,81828,81829,81830,81831,81832,81833,81834,81835,81836,81837,81838,81839,81840,81841
```

### Priority estimada del ids-file

| priority | count |
| ---: | ---: |
| 1 | 36 |
| 2 | 2 |
| 3 | 0 |

## Soft-warning revisadas y excluidas

Decision: dejarlas fuera por defecto. Son geograficamente razonables por coords, pero `ciudad/provincia` esta NULL en staging; conviene normalizarlas o aprobarlas explicitamente en una etapa separada.

| staging_id | inmobiliaria_id | titulo | lat | lon | ciudad | provincia | motivo | recomendacion |
| ---: | ---: | --- | ---: | ---: | --- | --- | --- | --- |
| 81822 | 4418 | Casas en Venta - Tucumán y Trabajadores Municipales | -37.290944 | -59.154507 | NULL | NULL | missing_city_or_province_but_coords_present | dejar para despues |
| 81842 | 4418 | Locales en Venta - Reynoso y La Pampa | -37.295587 | -59.157812 | NULL | NULL | missing_city_or_province_but_coords_present | dejar para despues |
| 81843 | 4418 | Departamentos en Venta - Reynoso y La Pampa | -37.295536 | -59.157833 | NULL | NULL | missing_city_or_province_but_coords_present | dejar para despues |

## Otros excluidos

- Con warning fuerte de imagen/titulo u otros: 43 IDs.
- Done con score bajo: 8 IDs.
- Skipped sin lat/lon: 4 IDs.
- Pending/failed restantes: 103 IDs.

### Warning fuerte breakdown

| warning | count |
| --- | ---: |
| `missing_city_or_province_but_coords_present` | 43 |
| `missing_images` | 43 |
| `weak_title` | 5 |

### IDs warning fuerte

```text
81700,81705,81706,81712,81719,81720,81721,81724,81727,81728,81733,81734,81735,81736,81737,81739,81740,81742,81743,81745,81746,81747,81749,81752,81753,81754,81755,81757,81758,81759,81760,81761,81762,81763,81765,81767,81769,81773,81774,81775,81776,81778,81780
```

### IDs done score bajo

```text
81726,81764,81766,81768,81770,81771,81772,81779
```

### IDs skipped sin lat/lon

```text
81665,81673,81683,81793
```

## Dry-run final

Comando:

```powershell
$env:USE_INTERNAL_DB='true'; python -B scripts/build_publish_queue.py --dry-run --ids-file reports/scraping_runs/import_controlado_20260608/staging_ids_publishqueue_clean_38_etapa5b.csv --limit 100 --min-score 60
```

Resultado: 38 leidas, 38 encoladas en dry-run, 0 skips, priority 1 = 36, priority 2 = 2, rollback.

## Commit publish_queue

Comando:

```powershell
$env:USE_INTERNAL_DB='true'; python -B scripts/build_publish_queue.py --commit --ids-file reports/scraping_runs/import_controlado_20260608/staging_ids_publishqueue_clean_38_etapa5b.csv --limit 100 --min-score 60
```

Resultado: 38 leidas, 38 encoladas, 0 skips, commit.

## Verificacion post-commit

| check | resultado |
| --- | --- |
| filas publish_queue scope | 38 |
| filas insertadas esperadas | 38 |
| IDs exactos en ids-file | True |
| missing desde ids-file | 0 |
| extras fuera del ids-file | 0 |
| queue status pending | 38 |
| staging status queued | 38 |
| priority 1 | 36 |
| priority 2 | 2 |
| priority 3 | 0 |

Verificacion Supabase: no se ejecuto `publish_to_supabase.py`; `scripts/build_publish_queue.py` solo usa `INTERNAL_DB_URL` y no contiene referencias a `SUPABASE` segun `rg`. Por lo tanto no hubo publicacion ni writes a `propiedades` en Supabase desde esta etapa.

## Publish_queue final por inmobiliaria

| inmobiliaria_id | count |
| ---: | ---: |
| 3532 | 2 |
| 4418 | 26 |
| 6335 | 10 |

## Proximo paso recomendado

No publicar Supabase todavia. Antes de `publish_to_supabase`, hacer una auditoria final de las 38 queued en `publish_queue` y decidir si se publica el grupo limpio completo o por sublotes. Mantener fuera las 3 soft-warning hasta aprobar ciudad/provincia, y revisar aparte las 43 con imagen/titulo debil.

Freno operativo: no se corrio Supabase publish, no geocoding, no import, no cleanup/borrado.
