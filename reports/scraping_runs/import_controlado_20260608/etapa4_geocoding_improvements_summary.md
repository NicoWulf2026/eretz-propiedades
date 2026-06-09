# ETAPA 4 - Geocoding improvements sobre 199 staging

Fecha: 2026-06-08
Scope: 199 propiedades de ETAPA 2/3 desde `raw_ids_fase5.csv`
Branch: `fix/scraping-diagnostics-batch`
Base: `3ad593e48 fix(geocoding): normalize address prefixes and document etapa 3 audit`

## Resumen ejecutivo

Se mejoro el contexto de geocoding sin tocar schema, sin publicar Supabase, sin importar propiedades nuevas y sin tocar frontend. El trabajo se limito a los 199 staging del scope.

Resultado neto:

- 28 propiedades Angelina nuevas quedaron `done` con coordenadas dentro de General Alvear, Mendoza.
- El scope completo queda en: 92 `done`, 101 `pending`, 4 `skipped`, 2 `failed`.
- Los dos outliers previos siguen sin coordenadas malas: 81777 y 81820 quedaron `failed` con lat/lon NULL.
- Sauce fue diagnosticado pero no geocodificado porque falta contexto ciudad/provincia confiable.

## Fixes aplicados

### 1. Contexto por raw/inmobiliaria en `scripts/geocode_staging.py`

`fetch_staging_rows` ahora trae contexto adicional:

- `propiedades_raw.url`
- `propiedades_raw.ciudad`
- `propiedades_raw.provincia`
- `propiedades_raw.datos_extra`
- `inmobiliarias_staging.ciudad`
- `inmobiliarias_staging.provincia`
- `inmobiliarias_staging.pais`

El geocoder usa esos campos como fallback de contexto, sin sobrescribir `propiedades_staging.ciudad` ni `propiedades_staging.provincia`.

Nota operativa: en Neon, `public.inmobiliarias_staging` existe pero esta vacia para este scope. Por eso el contexto efectivo de Angelina salio de URL/metadatos raw, especialmente `General+Alvear%2C+Mendoza`.

### 2. Inferencia segura desde raw metadata

Se agrego inferencia conservadora desde URL/metadatos raw para casos claros:

- `General Alvear, Mendoza`
- `Las Heras, Mendoza`
- `Ciudad Mendoza`
- `Tandil, Buenos Aires`

Esto corrige queries ambiguas como `LINIERS 139, Argentina`, que ahora pasan a:

`LINIERS 139, General Alvear, Mendoza, Argentina`

### 3. CITY_BOUNDS en `scraper/geocoder.py`

Se ajustaron bounds:

- Tandil, Buenos Aires: bbox ampliado para cubrir periferia rural del batch controlado.
- General Alvear, Mendoza: bbox nuevo para bloquear falsos positivos de Godoy Cruz / Gran Mendoza.
- Mendoza, Mendoza: bbox nuevo para validar Mendocasa / area central.

No se agrego Sauce Viejo porque el contexto de Sauce no es claro todavia.

### 4. Anti-basura adicional

`scripts/geocode_staging.py` ahora considera basura geocodificable patrones como:

- `SALON COMERCIAL 776`
- `TALLER 55`

Esto evita que textos de tipo/titulo se traten como direccion.

## Tests y validaciones

Validaciones realizadas:

- Syntax compile in-memory de `scripts/geocode_staging.py`.
- Syntax compile in-memory de `scraper/geocoder.py`.
- Test de contexto Angelina: `LINIERS 139` genera query con `General Alvear, Mendoza, Argentina`.
- Test de Mendocasa: no se rompe el fix previo de prefijo `Address:`.
- Test de Tandil: mantiene `Tandil, Buenos Aires`.
- Test de bbox General Alvear: acepta coordenadas locales y rechaza Gran Mendoza.
- Verificacion read-only DB post-commit sobre los 199 IDs.

## IDs files usados

- Scope base: `reports/scraping_runs/import_controlado_20260608/raw_ids_fase5.csv` (199 raw IDs).
- Dry-run/probe Angelina: `reports/scraping_runs/import_controlado_20260608/staging_ids_etapa4_angelina_high_confidence.csv` (33 staging IDs).
- Commit Angelina: `reports/scraping_runs/import_controlado_20260608/staging_ids_etapa4_angelina_commit_success.csv` (28 staging IDs).
- Reporte de corrida: `reports/scraping_runs/import_controlado_20260608/fase5_geocoding_angelina_commit.md`.

## Angelina dry-run

Pendientes Angelina dentro del scope al inicio de ETAPA 4: 62.

Clasificacion previa:

- 33 candidatos high-confidence para probe.
- 26 quedaron en revision por direccion incompleta/ambigua.
- 2 quedaron como garbage address (`SALON COMERCIAL`, `TALLER`).
- 1 estaba lista por reglas generales pero no entro al grupo high-confidence.

Resultado probe:

- 28 exitos con coordenadas dentro de bbox General Alvear.
- 5 sin resultado Nominatim; no se commitearon:
  - 81725 - `BARTOLOME MITRE 776`
  - 81732 - `WASHINGTON OJEDA 946`
  - 81738 - `B SAN FRANCISCO 1030`
  - 81748 - `ALEM NORTE 970`
  - 81756 - `CHAPERROUGE 1057`

## Angelina commit

Se hizo commit de geocoding solo para el ids-file exacto de 28 exitos high-confidence.

Comando usado, con `USE_INTERNAL_DB=true` solo a nivel proceso:

`python -B .\scripts\geocode_staging.py --ids-file .\reports\scraping_runs\import_controlado_20260608\staging_ids_etapa4_angelina_commit_success.csv --limit 28 --max-requests 40 --commit --report .\reports\scraping_runs\import_controlado_20260608\fase5_geocoding_angelina_commit.md`

Resultado:

- 28 `done`
- 0 `failed`
- 0 `skipped`
- 28 requests usados
- 0 propiedades del commit fuera de bbox General Alvear

## Retry outliers

### 81777 - Angelina

Estado actual:

- titulo: `Propiedad en`
- direccion_normalizada: texto de footer/contacto
- geocoding_status: `failed`
- lat/lon: NULL

Decision: no retry/commit. La direccion sigue contaminada y no hay calle+altura real.

### 81820 - Pagliaro

Estado actual:

- titulo: `Casas en Venta - Alameda 210 bis, No 633`
- direccion_normalizada: `Alameda 210`
- contexto: `Tandil, Buenos Aires`
- geocoding_status: `failed`
- lat/lon: NULL

Evaluacion sin write:

- `Alameda 210, Tandil, Buenos Aires, Argentina`
- `Alameda 210 bis, Tandil, Buenos Aires, Argentina`
- `Alameda al 633, Tandil, Buenos Aires, Argentina`
- `Alameda 633, Tandil, Buenos Aires, Argentina`

Resultado: sin resultado confiable. Decision: dejar `failed`, sin coordenadas.

## Sauce diagnostico

Sauce dentro del scope:

- 29 `pending`
- 1 `skipped`

Diagnostico de las 29 pending:

- 28 quedan como `garbage_address_no_query` porque `direccion_normalizada` esta vacia y el script no extrae todavia direccion desde titulos simples.
- 1 queda `geocoding_ready_safe`, pero sin ciudad/provincia confiable.

Ejemplos observados:

- `Irigoyen Freyre 2900`
- `San Lorenzo 2700`
- `Suipacha 2600`
- `Bv. Pellegrini 2900`
- `Austria 1100 - Sauce Viejo`

Decision: no commit Sauce. Hay ambiguedad Santa Fe / Sauce Viejo y falta contexto de inmobiliaria o raw confiable.

## Estado final del scope 199

| status | count | con coords | sin coords |
| --- | ---: | ---: | ---: |
| done | 92 | 92 | 0 |
| failed | 2 | 0 | 2 |
| pending | 101 | 0 | 101 |
| skipped | 4 | 0 | 4 |

## Estado por inmobiliaria

| inmobiliaria_id | nombre origen | done | pending | skipped | failed |
| ---: | --- | ---: | ---: | ---: | ---: |
| 945 | Ami Propiedades | 0 | 36 | 3 | 0 |
| 3531 | Inmobiliaria Angelina Martinez | 51 | 34 | 0 | 1 |
| 3532 | INMOBILIARIA & GESTORIA MENDOCASA LAVALL | 2 | 1 | 0 | 0 |
| 4418 | Juan I. Pagliaro Propiedades | 29 | 0 | 0 | 1 |
| 4709 | VivancoGroup Inmobiliaria - Patagonia | 0 | 1 | 0 | 0 |
| 6335 | SV Inmobiliaria | 10 | 0 | 0 | 0 |
| 6732 | Sauce Inmobiliaria | 0 | 29 | 1 | 0 |

## Candidatos para publish_queue dry-run futuro

Hay 92 propiedades del scope con `geocoding_status='done'` y coordenadas presentes.

No se ejecuto `build_publish_queue`.
No se ejecuto publish.
No se toco `publish_queue`.

## Riesgos restantes

- `inmobiliarias_staging` esta vacia, por lo que el JOIN aporta estructura futura pero no resuelve todos los casos actuales.
- Sauce necesita extraccion de direccion desde titulo y contexto localidad/provincia antes de geocodificar.
- Ami mantiene 36 pending y 3 skipped; requiere auditoria de direcciones/contexto aparte.
- Angelina aun tiene 34 pending y 1 failed; no todos tienen direccion suficiente.
- Pagliaro 81820 sigue failed por falta de match confiable en Nominatim.
- Subir volumen sin carril high-confidence puede reintroducir outliers.

## Confirmaciones operativas

- No Supabase publish.
- No `publish_to_supabase.py`.
- No `publish_queue` commit.
- No frontend.
- No `.env` modificado.
- No cambios de schema.
- No import de propiedades nuevas.
- No Playwright.
- No push.
- Geocoding commit limitado a 28 staging IDs dentro de los 199 del scope.

## Proximo paso recomendado

Antes de publish_queue, correr un dry-run de readiness/publish solo sobre los 92 `done` del scope y auditar imagen/direccion/precio. Para seguir mejorando geocoding, la proxima fase deberia atacar Sauce/Ami con extraccion de direccion desde titulo y contexto de localidad/provincia, sin commit hasta tener probes high-confidence.
