# ETAPA 5A - publish_queue dry-run audit

Fecha: 2026-06-08
Branch: `fix/scraping-diagnostics-batch`
HEAD: `17465478f fix(geocoding): use agency location context for staging geocoding`
Scope: 199 staging de ETAPA 2/3 via `raw_ids_fase5.csv`.

## Guardrails

- No git push.
- No Supabase publish.
- No `publish_to_supabase.py --commit`.
- No `publish_queue` commit.
- No frontend.
- No `.env` modificado.
- No schema changes.
- No import.
- No geocoding.
- No borrado de archivos ni datos.
- No Playwright.

## Scope DB read-only

| estado | count |
| --- | ---: |
| done | 92 |
| pending | 101 |
| skipped | 4 |
| failed | 2 |

- Scope total: 199
- Done con lat/lon y `status=staging`: 92
- Filas existentes en publish_queue para scope: 0

## Candidatas

- Candidatas tecnicas segun `build_publish_queue.py` con `min_score=60`: 88
- De esas, `skipped` sin lat/lon: 4
- Candidatas finales ETAPA 5A (`done` + lat/lon + score >= 60 + datos criticos): 84
- Excluidas `done` por score bajo: 8
- Excluidas `done` por falta de datos criticos: 0
- Pending/skipped/failed fuera del ids-file final: 107

Nota: la expectativa inicial de 88 candidatas incluia 4 filas `skipped` que el builder aceptaria tecnicamente, pero no tienen lat/lon. Para esta etapa se excluyen del ids-file final.

## IDs files

- Done: `reports/scraping_runs/import_controlado_20260608/staging_ids_done_etapa5a.csv` (92 IDs)
- Candidatas finales: `reports/scraping_runs/import_controlado_20260608/staging_ids_publishqueue_candidates_etapa5a.csv` (84 IDs)

## Dry-run publish_queue

Comando ejecutado:

```powershell
$env:USE_INTERNAL_DB='true'; python -B scripts/build_publish_queue.py --dry-run --ids-file reports/scraping_runs/import_controlado_20260608/staging_ids_publishqueue_candidates_etapa5a.csv --limit 200 --min-score 60
```

Resultado:

| metrica | count |
| --- | ---: |
| filas_leidas | 84 |
| encoladas dry-run | 84 |
| ya_en_cola | 0 |
| skips | 0 |
| priority 1 | 36 |
| priority 2 | 48 |
| priority 3 | 0 |

Accion final del script: `rollback`. Verificacion posterior: `publish_queue_rows_for_scope=0`.

## Auditoria pre-publish_queue

| check | resultado |
| --- | --- |
| URL valida presente | OK en 84 / 84 |
| Zonaprop/Argenprop/portal prohibido | 0 detectadas |
| Lat/lon presente | OK en 84 / 84 |
| Precio presente y > 0 | OK en 84 / 84 |
| Moneda presente | OK en 84 / 84 |
| Titulo razonable | warnings en 5 |
| Ciudad/provincia presente | warnings en 46; coords existen |
| Imagenes presentes | warnings missing_images en 43 |
| Duplicado URL en candidatas | 0 |
| Duplicado hash en candidatas | 0 |

### Warnings en candidatas

| warning | count |
| --- | ---: |
| `missing_city_or_province_but_coords_present` | 46 |
| `missing_images` | 43 |
| `weak_title` | 5 |

### Candidatas por inmobiliaria

| inmobiliaria_id | nombre | total | p1 | p2 | missing_images | weak_title | missing_city_province |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3531 | Inmobiliaria Angelina Martinez | 43 | 0 | 43 | 43 | 5 | 43 |
| 3532 | Mendocasa Lavalle | 2 | 0 | 2 | 0 | 0 | 0 |
| 4418 | Juan I. Pagliaro Propiedades | 29 | 26 | 3 | 0 | 0 | 3 |
| 6335 | SV Inmobiliaria | 10 | 10 | 0 | 0 | 0 | 0 |

### Candidatas por dominio

| dominio | count |
| --- | ---: |
| `inmobiliariaangelinam.com.ar` | 43 |
| `inmobiliariamendocasa.com.ar` | 2 |
| `pagliaropropiedades.com.ar` | 29 |
| `svestudioinmobiliario.com.ar` | 10 |

## Excluidas

### Done excluidas por score bajo

| staging_id | raw_id | inmobiliaria_id | score | titulo | motivo |
| ---: | ---: | ---: | ---: | --- | --- |
| 81726 | 82216 | 3531 | 55 | Propiedad en | score < 60 |
| 81764 | 82254 | 3531 | 55 | Departamento en Alquiler | score < 60 |
| 81766 | 82256 | 3531 | 55 | Propiedad en | score < 60 |
| 81768 | 82258 | 3531 | 55 | Propiedad en | score < 60 |
| 81770 | 82260 | 3531 | 55 | Propiedad en | score < 60 |
| 81771 | 82261 | 3531 | 55 | Propiedad en | score < 60 |
| 81772 | 82262 | 3531 | 55 | Propiedad en Alquiler | score < 60 |
| 81779 | 82269 | 3531 | 55 | Propiedad en | score < 60 |

### Skipped tecnicamente elegibles pero fuera del ids-file final

| staging_id | raw_id | inmobiliaria_id | score | titulo | motivo |
| ---: | ---: | ---: | ---: | --- | --- |
| 81665 | 82155 | 945 | 95 | CASA EN VENTA | geocoding_status=skipped sin lat/lon |
| 81673 | 82163 | 945 | 95 | DEPARTAMENTO EN VENTA | geocoding_status=skipped sin lat/lon |
| 81683 | 82173 | 945 | 95 | PH EN VENTA | geocoding_status=skipped sin lat/lon |
| 81793 | 82283 | 6732 | 95 | Avellaneda 3300 | geocoding_status=skipped sin lat/lon |

## Segmentos de riesgo

- Clean sin warnings: 38
- Solo warning blando `missing_city_or_province_but_coords_present`: 3
- Requieren revision antes de publicar por imagen/titulo/otros warnings: 43
- Angelina concentra warnings de `missing_images` y algunos titulos debiles.
- Falta ciudad/provincia en staging para muchas Angelina, pero las coordenadas existen y fueron validadas por bbox en ETAPA 4.
- No se detectaron portales externos prohibidos ni duplicados tecnicos por URL/hash dentro de las candidatas finales.

## Recomendacion

No conviene hacer commit masivo de publish_queue para las 84 sin una decision explicita sobre calidad visual. El camino mas seguro es:

1. Commit futuro de publish_queue solo para el subgrupo limpio y/o con warning blando de ciudad/provincia faltante.
2. Revisar antes de encolar las candidatas con `missing_images` o `weak_title`, especialmente Angelina.
3. Mantener fuera a las 8 `done` con score 55 y a las 4 `skipped` sin lat/lon.

Freno operativo: no se ejecuto `build_publish_queue.py --commit`, no se escribio `publish_queue`, no se publico Supabase.
