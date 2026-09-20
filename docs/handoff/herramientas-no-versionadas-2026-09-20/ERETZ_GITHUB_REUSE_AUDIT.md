# ERETZ Propiedades - Auditoria de reutilizacion historica de GitHub

Fecha de auditoria: 2026-09-14  
Repositorio auditado: `NicoWulf2026/eretz-propiedades`  
Workspace local: `D:\INMO CAPITAL\Inmo-Capital-main`  
HEAD local al iniciar: `9461fab0195b84eb4fee99ca0a9195225c0081fe` (`release/eretz-private-preview`)  
Ultimo commit local visible: `9461fab019 docs(retrabajo): no comprar maquinas, eliminar la repeticion`  
Deadline operativo informado: 2026-10-12

## 1. Alcance y reglas respetadas

Esta auditoria fue realizada en modo lectura sobre Git/GitHub y archivos del repositorio. La unica escritura realizada fue este documento `ERETZ_GITHUB_REUSE_AUDIT.md`.

No se ejecuto:

- merge;
- cherry-pick;
- rebase;
- push;
- cambio de branch;
- fix de codigo;
- workers;
- deploy;
- escritura en base de datos;
- cambio de fingerprints;
- corrida de scraping productivo.

Advertencia importante: el working tree local ya estaba sucio antes de crear este informe. Hay modificaciones y muchos archivos no versionados preexistentes. No fueron revertidos ni tocados.

## 2. Estado inicial de Git

Comandos de auditoria usados:

- `git status --short`
- `git log --oneline -10`
- `git branch -r`
- `git for-each-ref refs/remotes/origin`
- `git ls-remote --heads origin`
- `git ls-remote origin refs/pull/*/head`
- `git show --stat`
- `git show`
- `git diff --name-status HEAD..origin/...`
- `git grep` / `rg` sobre areas tecnicas

Refs remotas auditadas:

| Rama remota | SHA | Fecha | Asunto |
|---|---:|---:|---|
| `origin/main` | `15e81991c0` | 2026-07-01 | `fix: handle manifest duplicate hash conflicts after pilot (#8)` |
| `origin/pr-be-prod-manifest-b-post-pilot-fixes` | `addaeff425` | 2026-07-01 | `fix: handle manifest duplicate hash conflicts after pilot` |
| `origin/pr-be-prod-09e-manifest-runner-hardening` | `3cf89adb3a` | 2026-07-01 | `feat: harden manifest runner for ERETZ production loads` |
| `origin/feat/parser-detail-url-detection` | `2b7632600c` | 2026-06-28 | `fix: improve parser detail URL detection` |
| `origin/feat/scraper-timeout-configurable-env` | `8df9c21ddc` | 2026-06-23 | `Scraper: timeouts de item/estrategia configurables por env` |
| `origin/feat/retry-run-from-error-items` | `d812792120` | 2026-06-23 | `Nuevo script: crear run de reintento desde scraping_run_items con error` |
| `origin/feat/fase-b1-publish-robustez` | `e57d4020c7` | 2026-06-19 | `chore(repo): remove generated reports from tracking` |
| `origin/feat/monorepo-frontend-integration` | `ebf29037a5` | 2026-06-24 | `feat: rebrand public frontend to ERETZ and remove debug route` |
| `origin/feat/fe-b-beta-safety-foundation` | `eb2d249473` | 2026-06-25 | `feat: show property update date when available` |
| `origin/feat/eretz-frontend-phase-a` | `04e63a289` | 2026-08-28 | `docs(publicacion): arquitectura, frontera y estado de cada pieza` |
| `origin/release/eretz-private-preview` | `7e21832676` | 2026-08-03 | `ci: make backend tests reproducible without secrets` |
| `origin/claude/roomix-agency-universe-ndvrfu` | `5e51042541` | 2026-08-18 | `feat(roomix-agency): heartbeat remoto de telemetria del crawler` |

PR heads encontrados:

- PR 1 -> `e57d4020c7`
- PR 2 -> `d812792120`
- PR 3 -> `8df9c21ddc`
- PR 4 -> `ebf29037a5`
- PR 5 -> `eb2d249473`
- PR 6 -> `2b7632600c`
- PR 7 -> `3cf89adb3a`
- PR 8 -> `addaeff425`
- PR 9 -> `7e21832676`

Conclusiones de estado:

- Los PR heads publicados no agregan refs adicionales fuera de las ramas remotas ya listadas.
- Muchas ramas antiguas divergen fuertemente del HEAD actual; traer ramas completas seria peligroso porque sus diffs muestran eliminaciones masivas de frontend/docs/infra que hoy existen.
- La reutilizacion recomendada es por piezas, tests, heuristicas y guardrails, no por merge directo.

## 3. Hallazgos ejecutivos

1. El mayor valor reutilizable ya esta parcialmente integrado en el estado actual: `create_retry_run_from_error_items.py`, tests de timeout, tests de parser de URLs de detalle y `run_manifest.py` existen hoy en el arbol.
2. La rama `pr-be-prod-09e-manifest-runner-hardening` sigue siendo una referencia fuerte para comparar guardrails del runner actual, especialmente bloqueos de `--commit`, `--include-backlog`, limites de workers, limites de ejecucion y reportes post-run.
3. La rama `feat/parser-detail-url-detection` aporta tests y heuristicas de alto valor para URLs de detalle en cards renderizadas: `href`, `data-*`, `onclick`, query params y rechazo de falsos positivos.
4. La rama `feat/retry-run-from-error-items` aporta un patron sano: script idempotente, dry-run por defecto, allowlist de errores y tests puros sin DB.
5. La rama `feat/scraper-timeout-configurable-env` aporta un patron de timeouts configurables por entorno y tests. El estado actual ya contiene señales de esa incorporacion.
6. `origin/main` / `pr-be-prod-manifest-b-post-pilot-fixes` contienen fix historico de conflictos por `hash_dedup` duplicado. Debe verificarse contra el codigo actual porque el repo reciente ya cambio el contrato de deduplicacion/fingerprint.
7. `origin/claude/roomix-agency-universe-ndvrfu` contiene migracion + heartbeat + tests para telemetria de crawling de agencias. Es valioso, pero no es Wave 0: toca DB/migraciones y observabilidad.
8. `feat/fase-b1-publish-robustez` no aporta mucho codigo operativo reutilizable: su commit visible es limpieza masiva de reportes generados.
9. Las ramas frontend antiguas tienen valor como documentacion/UX/arquitectura, pero menor prioridad para el objetivo actual de ingestion, parser, retry y cobertura antes del 2026-10-12.
10. Playwright no es una capacidad ausente: existe como dependencia formal y como estrategia en scraper/scripts. El problema pendiente no es "tener browser", sino usarlo con criterios medidos para diferenciar JS real, anti-bot, 202 vacio, parser gap y respuesta remota inservible.

## 4. Capacidad Playwright / browser

### Estado actual

El proyecto actual ya tiene Playwright formalmente:

- `pyproject.toml` incluye `playwright==1.58.0`.
- `README.md` indica `python -m playwright install chromium` cuando la tarea requiere navegador.
- `scraper/scraper_propiedades.py` incluye estrategias Playwright, network interception, timeouts, bloqueo de recursos pesados, diagnostico de `requires_playwright`, manejo de `202` y cierre seguro de contextos.
- Hay scripts locales actuales de diagnostico/recheck, entre ellos:
  - `scripts/run_production_parser_playwright_recheck.py`
  - `scripts/run_full_coverage_playwright_pass.py`
  - `scripts/diagnose_playwright_pass.py`
- El runbook limita concurrencia de browser a `MAX_ACTIVE_BROWSERS=2`.

### Sirve para las 149 paginas office con `202/0 bytes`?

Respuesta corta: si, pero solo como diagnostico y recuperacion condicional; no como garantia universal.

Playwright puede ayudar si:

- el HTML inicial por `requests` vuelve vacio, pero Chromium obtiene DOM util tras JS;
- hay fichas en iframes propios o recursos internos;
- el sitio necesita scroll/click/load-more;
- el parser HTTP no ve links, pero el DOM renderizado si los contiene;
- la respuesta `202` es una pantalla intermedia que luego resuelve.

Playwright probablemente no alcanza si:

- el servidor entrega `202` con cuerpo vacio tambien a Chrome real;
- hay anti-bot duro, captcha, DataDome, Cloudflare challenge persistente o bloqueo por reputacion/IP;
- el sitio requiere sesion/login;
- el endpoint de office no es un listado real sino una ficha institucional sin inventario;
- el bloqueo depende de headers/rate limit/proxy y no de renderizado.

Recomendacion concreta:

1. No convertir las 149 en corrida productiva directa.
2. Ejecutar diagnostico read-only con browser sobre muestra 10 -> 25 -> 149.
3. Clasificar cada fuente en:
   - `RECOVERED_BY_RENDER`
   - `PARSER_GAP_AFTER_RENDER`
   - `EXTERNAL_ANTIBOT`
   - `EMPTY_IN_REAL_BROWSER`
   - `NOT_LISTING_SOURCE`
   - `NEEDS_CONNECTOR`
4. Solo pasar a scraping real las recuperadas con evidencia de links/fichas y sin anti-bot.

## 5. Matriz de candidatos de reutilizacion

### C1 - Retry run desde errores previos

| Campo | Detalle |
|---|---|
| Nombre | Crear run de reintento desde `scraping_run_items` con error |
| Rama | `origin/feat/retry-run-from-error-items` |
| Commit | `d81279212092aa5c12c84da0ee9967b8e06da4a6` |
| Fecha | 2026-06-23 |
| Archivos | `scripts/create_retry_run_from_error_items.py`, `tests/test_create_retry_run_from_error_items.py` |
| Problema que resuelve | Reintentar timeouts sin pasar por `v_next_scraping_batch`, copiando filas historicas de error como items `pending` nuevos. |
| Tests | 129 lineas de tests puros: allowlist, skips, dedup pending, limit, payload, ids-file. |
| Impacto esperado | Alto para recuperar errores transitorios sin mezclar backlog ni fuentes no elegibles. |
| Compatibilidad actual | `scripts/create_retry_run_from_error_items.py` y su test ya existen en el arbol actual; requiere diff fino contra version historica y esquema vigente. |
| Dependencias | `psycopg`, `INTERNAL_DB_URL`, schema `internal_scraping`. |
| Riesgo | Medio si se ejecuta sin revisar IDs/campos actuales; bajo si queda dry-run y tests. |
| Radio fingerprint | Bajo/medio; crea nuevos run items pero no deberia cambiar fingerprints de propiedades. |
| Trabajo requerido | Comparar version actual vs historica, validar schema, agregar sample dry-run y runbook. |
| Clasificacion | `ALREADY_PRESENT` + `ADAPT` |
| Recomendacion | Usar como patron Wave 0 para colas de retry medidas; no cherry-pick entero. |

### C2 - Timeouts configurables por entorno

| Campo | Detalle |
|---|---|
| Nombre | Multiplicador global de timeouts del scraper |
| Rama | `origin/feat/scraper-timeout-configurable-env` |
| Commit | `8df9c21ddcb2aa1d12532a3145de75b20a4bd928` |
| Fecha | 2026-06-23 |
| Archivos | `.env.example`, `scraper/scraper_propiedades.py`, `tests/test_timeout_env_config.py` |
| Problema que resuelve | Ajustar timeouts de item/estrategia sin tocar codigo para sitios lentos/WordPress/Playwright. |
| Tests | `tests/test_timeout_env_config.py`, 116 lineas. |
| Impacto esperado | Alto para canaries y lotes con sitios lentos; reduce falsos timeouts sin abrir corridas infinitas. |
| Compatibilidad actual | `scraper/scraper_propiedades.py` actual ya contiene `SCRAPER_TIMEOUT_MULTIPLIER`, timeouts por estrategia y test existe. |
| Dependencias | Ninguna nueva. |
| Riesgo | Bajo si se mantiene rango min/max y default 1.0. |
| Radio fingerprint | Nulo directo; solo afecta ejecucion/recuperacion. |
| Trabajo requerido | Verificar docs/runbook y que los tests actuales cubran limites min/max/default. |
| Clasificacion | `ALREADY_PRESENT` |
| Recomendacion | Mantener; documentar presets para canary, retry y Playwright. |

### C3 - Deteccion robusta de URLs de detalle en cards

| Campo | Detalle |
|---|---|
| Nombre | Parser de candidatos de URL de detalle desde cards |
| Rama | `origin/feat/parser-detail-url-detection` |
| Commit | `2b7632600cab2241287cd51d6cd0c470d2cf3509` |
| Fecha | 2026-06-28 |
| Archivos | `scraper/playwright_scraper.py`, `tests/test_parser_detail_url_candidates.py`, `scripts/validate_parser_fix_07b.py`, `scripts/validate_detail_quality_07d.py` |
| Problema que resuelve | Sitios que no exponen anchors obvios o usan `data-href`, `data-url`, `onclick`, query params tipo `idprop/ficha/codigo`. |
| Tests | `tests/test_parser_detail_url_candidates.py` con casos positivos y negativos. |
| Impacto esperado | Muy alto para parser gap y fuentes renderizadas sin links clasicos. |
| Compatibilidad actual | El test y `scraper/playwright_scraper.py` existen actualmente; ademas hay fixtures actuales `nuxt_click_only_property_card.html` y `onclick_relative_ficha_card.html`. |
| Dependencias | BeautifulSoup; Playwright solo para rutas renderizadas. |
| Riesgo | Medio si relaja demasiado falsos positivos; bajo si se incorpora como tests/heuristicas. |
| Radio fingerprint | Bajo; mejora discovery antes de crear propiedades. |
| Trabajo requerido | Comparar heuristicas historicas contra parser actual y convertir huecos en tests. |
| Clasificacion | `ALREADY_PRESENT` + `TESTS_HEURISTICS_ONLY` |
| Recomendacion | Wave 0: usar tests historicos como contrato de regresion, especialmente para 202/0 bytes renderizados. |

### C4 - Hardening del manifest runner PR-BE-PROD-09e

| Campo | Detalle |
|---|---|
| Nombre | Wrapper seguro de corrida por manifest |
| Rama | `origin/pr-be-prod-09e-manifest-runner-hardening` |
| Commit | `3cf89adb3ab02bfc412b8a4b10a92a19639c7333` |
| Fecha | 2026-07-01 |
| Archivos | `scripts/run_manifest.py`, `tests/test_run_manifest.py`, `scraper/clients.py`, `scraper/models.py`, `scraper/run.py`, docs Obsidian |
| Problema que resuelve | Guardrails de produccion: dry-run por defecto, bloqueo de `--commit`, bloqueo de backlog, limites, validacion de manifest, reportes, dedup y manejo de errores. |
| Tests | `tests/test_run_manifest.py` historico con 1063 lineas. |
| Impacto esperado | Muy alto para evitar writes accidentales y corridas fuera de alcance. |
| Compatibilidad actual | `scripts/run_manifest.py` y `tests/test_run_manifest.py` existen y estan modificados localmente. No reemplazar. |
| Dependencias | Requests/Supabase/scraper runner actual. |
| Riesgo | Alto si se copia entero porque el runner actual evoluciono. Bajo si se usa como checklist de guardrails. |
| Radio fingerprint | Medio/alto por ejecucion productiva, aunque el wrapper en si no cambia fingerprints. |
| Trabajo requerido | Checklist comparativo: flags prohibidos, limites, validacion de manifest, reportes, `verify=True`, dedup actual. |
| Clasificacion | `ADAPT` |
| Recomendacion | Wave 0: revisar que el runner actual mantenga todos los bloqueos historicos y tests equivalentes. |

### C5 - Fix de conflictos por `hash_dedup` duplicado post piloto

| Campo | Detalle |
|---|---|
| Nombre | Manejo de conflictos de hash duplicado en manifest/publish |
| Rama | `origin/main`, `origin/pr-be-prod-manifest-b-post-pilot-fixes` |
| Commit | `15e81991c0511653bbe9efb70a92d13c1835b310`, `addaeff4253662a2ed2a30c65482afe371a5dc41` |
| Fecha | 2026-07-01 |
| Archivos | `scraper/clients.py`, `tests/test_run_manifest.py`, docs |
| Problema que resuelve | Conflictos por hash duplicado luego de piloto, evitando marcar como fallo lo que ya existe o es dedup esperado. |
| Tests | 107 lineas agregadas en `tests/test_run_manifest.py`. |
| Impacto esperado | Alto para idempotencia y no duplicar propiedades. |
| Compatibilidad actual | El repo actual tiene commits posteriores sobre dedupe/fingerprint: revisar contra `safe_merge.py`, `models.py` y runner actual. |
| Dependencias | Contrato actual de `hash_dedup` / `url_normalizada`. |
| Riesgo | Alto si se aplica sin entender fingerprint actual; puede ocultar duplicados reales. |
| Radio fingerprint | Alto. |
| Trabajo requerido | Portar solo tests/invariantes, no logica literal, y verificar con dataset de duplicados. |
| Clasificacion | `TESTS_HEURISTICS_ONLY` + `ADAPT` |
| Recomendacion | Wave 1: convertir en regresiones sobre el contrato actual de dedupe. |

### C6 - Heartbeat remoto de telemetria de crawling de agencias

| Campo | Detalle |
|---|---|
| Nombre | Roomix agency heartbeat |
| Rama | `origin/claude/roomix-agency-universe-ndvrfu` |
| Commit | `5e51042541b2df00187868d4f3ccf95f4ed0839b` |
| Fecha | 2026-08-18 |
| Archivos | `migrations/phase_roomix_agency_crawl_status.sql`, `scraper/roomix_agency_heartbeat.py`, `tests/test_roomix_agency_heartbeat.py` |
| Problema que resuelve | Estado/heartbeat de crawler por agencia para seguimiento operativo. |
| Tests | 395 lineas. |
| Impacto esperado | Medio/alto para observabilidad y seguimiento de campañas largas. |
| Compatibilidad actual | Archivos no existen en el estado actual. Requiere migracion nueva. |
| Dependencias | DB/migracion y contrato de crawler actual. |
| Riesgo | Medio/alto por schema y escritura de telemetria. |
| Radio fingerprint | Bajo para propiedades; medio para infra/DB. |
| Trabajo requerido | Revisar schema vigente y adaptar como migracion separada con rollback. |
| Clasificacion | `CHERRY_PICK_CANDIDATE` solo despues de adaptacion |
| Recomendacion | Wave 2, no bloquear el 12/10. |

### C7 - Documentacion de arquitectura/publicacion frontend Phase A

| Campo | Detalle |
|---|---|
| Nombre | Matriz de capacidades y arquitectura de publicacion |
| Rama | `origin/feat/eretz-frontend-phase-a` |
| Commit | `04e63a2895bfd3dc68725734eeb0567f78e91342` |
| Fecha | 2026-08-28 |
| Archivos | `docs/ERETZ_CAPABILITY_MATRIX.md`, `docs/ERETZ_PUBLICATION_ARCHITECTURE.md` |
| Problema que resuelve | Claridad de frontera entre piezas del producto/publicacion. |
| Tests | No aplica. |
| Impacto esperado | Medio para onboarding y release planning. |
| Compatibilidad actual | Docs pueden estar superadas por estado actual. |
| Dependencias | Ninguna critica. |
| Riesgo | Bajo. |
| Radio fingerprint | Nulo. |
| Trabajo requerido | Releer y reconciliar con docs actuales. |
| Clasificacion | `ADAPT` |
| Recomendacion | Wave 3 documental. |

### C8 - CI reproducible sin secretos

| Campo | Detalle |
|---|---|
| Nombre | Backend tests reproducibles sin secrets |
| Rama | `origin/release/eretz-private-preview` |
| Commit | `7e2183267643a8c2ca81ec76e5edd964e377b3c9` |
| Fecha | 2026-08-03 |
| Archivos | `.github/workflows/ci.yml` |
| Problema que resuelve | Evitar que CI dependa de secretos para tests de backend. |
| Tests | Indirecto: workflow ejecuta tests. |
| Impacto esperado | Medio. |
| Compatibilidad actual | `.github/workflows/ci.yml` actual existe y ya ignora `tests/test_full_7004_coverage.py`; revisar delta exacto. |
| Dependencias | GitHub Actions. |
| Riesgo | Bajo/medio. |
| Radio fingerprint | Nulo. |
| Trabajo requerido | Comparar workflow actual vs historico y conservar reproduccion sin secretos. |
| Clasificacion | `ADAPT` |
| Recomendacion | Wave 1. |

### C9 - Limpieza masiva de reportes generados

| Campo | Detalle |
|---|---|
| Nombre | Remocion de reportes generados del repo |
| Rama | `origin/feat/fase-b1-publish-robustez` |
| Commit | `e57d4020c7a1be99d5d96ea73c2ec9ebcf6fee98` |
| Fecha | 2026-06-19 |
| Archivos | 121 archivos eliminados, mayormente reportes generados |
| Problema que resuelve | Reduce ruido en Git. |
| Tests | No aplica. |
| Impacto esperado | Bajo operativo, medio en higiene. |
| Compatibilidad actual | El repo actual tiene muchos docs/reportes historicos deliberados; no borrar sin politica. |
| Dependencias | Ninguna. |
| Riesgo | Medio por perdida de evidencia historica. |
| Radio fingerprint | Nulo. |
| Trabajo requerido | Definir politica de `reports/`, `_scratch/`, logs y evidencia. |
| Clasificacion | `SUPERSEDED` / `OBSOLETE` como commit directo |
| Recomendacion | No aplicar; solo usar como recordatorio de hygiene. |

### C10 - Frontend/rebranding/propiedad update date

| Campo | Detalle |
|---|---|
| Nombre | Integracion frontend/rebrand/update date |
| Rama | `origin/feat/monorepo-frontend-integration`, `origin/feat/fe-b-beta-safety-foundation` |
| Commit | `ebf29037a5`, `eb2d249473` |
| Fecha | 2026-06-24 / 2026-06-25 |
| Archivos | Frontend Next.js y componentes |
| Problema que resuelve | Branding ERETZ y fecha de actualizacion visible. |
| Tests | Frontend parcial historico. |
| Impacto esperado | Bajo para scraping, medio para producto publico. |
| Compatibilidad actual | El frontend actual evoluciono mucho. |
| Dependencias | Next.js/frontend. |
| Riesgo | Alto si se copia; podria borrar componentes actuales. |
| Radio fingerprint | Nulo para scraper. |
| Trabajo requerido | Solo revisar ideas UX si hay backlog frontend. |
| Clasificacion | `SUPERSEDED` |
| Recomendacion | No usar antes del 12/10 salvo necesidad frontend puntual. |

## 6. Top 10 reutilizable, ordenado por impacto

1. `scripts/run_manifest.py` guardrails historicos (`3cf89adb3a`) - `ADAPT`.
2. Tests/heuristicas de detalle URL (`2b7632600c`) - `TESTS_HEURISTICS_ONLY`.
3. Retry desde error items (`d812792120`) - `ALREADY_PRESENT` + `ADAPT`.
4. Timeouts por entorno (`8df9c21ddc`) - `ALREADY_PRESENT`.
5. Fix de duplicate hash conflicts (`15e81991c0` / `addaeff425`) - `ADAPT` como tests de dedupe.
6. CI reproducible sin secretos (`7e21832676`) - `ADAPT`.
7. Playwright diagnostic scripts actuales del working tree - no son rama historica, pero son capacidad critica actual.
8. Roomix agency heartbeat (`5e51042541`) - `CHERRY_PICK_CANDIDATE` post Wave 1.
9. Docs de publicacion/capability matrix (`04e63a289`) - `ADAPT`.
10. Limpieza de artefactos generados (`e57d4020c7`) - `SUPERSEDED`, usar solo como politica de higiene.

## 7. Plan de incorporacion

### WAVE 0 - Antes de cualquier corrida amplia

Objetivo: cerrar riesgos de operacion antes de tocar DB o correr workers.

1. Comparar runner actual contra `3cf89adb3a`:
   - bloqueo de `--commit`;
   - bloqueo de `--include-backlog`;
   - dry-run obligatorio por defecto;
   - limites de `--limit` y `--workers`;
   - Playwright solo con limite;
   - reportes de excluded/failed/skipped;
   - TLS verification sin regresion.
2. Ejecutar tests actuales de:
   - `tests/test_run_manifest.py`;
   - `tests/test_parser_detail_url_candidates.py`;
   - `tests/test_timeout_env_config.py`;
   - `tests/test_create_retry_run_from_error_items.py`.
3. Revisar que los scripts Playwright actuales escriban solo `_scratch` o salidas locales y no DB.
4. Definir protocolo 10 -> 25 -> 149 para paginas office 202/0 bytes.

### WAVE 1 - Recuperacion medida de parser/retry

Objetivo: maximizar cobertura sin cambiar fingerprint global.

1. Portar tests faltantes del parser historico si el parser actual no los cubre.
2. Validar `create_retry_run_from_error_items.py` contra schema actual.
3. Usar timeouts env solo por corrida, con default conservador.
4. Para `hash_dedup`, agregar regresiones de duplicate conflict sin copiar logica vieja literalmente.
5. Crear reporte de candidatos recuperados por Playwright: no DB, no publish.

### WAVE 2 - Observabilidad y telemetria

Objetivo: mejorar seguimiento de campañas largas.

1. Evaluar `roomix_agency_heartbeat.py`.
2. Adaptar migracion con rollback y prefijos actuales.
3. Integrar heartbeat solo si no aumenta fragilidad del camino critico.

### WAVE 3 - Documentacion/producto/frontend

Objetivo: limpiar deuda documental sin bloquear ingestion.

1. Reconciliar docs de arquitectura/publicacion.
2. Definir politica de reportes generados.
3. Revisar ramas frontend solo por ideas ya no implementadas.

## 8. Respuestas a las 14 preguntas finales

### 1. Que ramas/PRs tienen valor real?

Valor alto:

- `origin/pr-be-prod-09e-manifest-runner-hardening`
- `origin/feat/parser-detail-url-detection`
- `origin/feat/retry-run-from-error-items`
- `origin/feat/scraper-timeout-configurable-env`
- `origin/main` / `origin/pr-be-prod-manifest-b-post-pilot-fixes`

Valor medio:

- `origin/release/eretz-private-preview`
- `origin/claude/roomix-agency-universe-ndvrfu`
- `origin/feat/eretz-frontend-phase-a`

Valor bajo/superado:

- `origin/feat/fase-b1-publish-robustez`
- ramas frontend antiguas salvo consulta puntual.

### 2. Que se puede reutilizar tal cual?

Muy poco como archivo completo. Lo mas cercano a `REUSE_AS_IS` son tests puros, no modulos productivos. Aun asi, como varios archivos ya existen en el arbol actual, la categoria dominante es `ALREADY_PRESENT`.

### 3. Que conviene adaptar?

- Guardrails de `run_manifest.py`.
- Tests de parser de URLs de detalle.
- Retry desde errores, validado contra schema actual.
- Fixes de dedupe como invariantes/tests.
- CI reproducible sin secretos.

### 4. Que conviene cherry-pickear?

Nada sin revision. El unico candidato razonable para cherry-pick futuro seria `roomix-agency` como feature aislada, pero requiere migracion y adaptacion. Para el camino critico no recomiendo cherry-pick directo.

### 5. Que ya esta presente?

En el arbol actual existen:

- `scripts/run_manifest.py`
- `tests/test_run_manifest.py`
- `scripts/create_retry_run_from_error_items.py`
- `tests/test_create_retry_run_from_error_items.py`
- `tests/test_timeout_env_config.py`
- `tests/test_parser_detail_url_candidates.py`
- `scraper/playwright_scraper.py`
- Playwright en `pyproject.toml`
- scripts locales de diagnostico/recheck Playwright.

### 6. Que esta superado?

- Ramas frontend viejas como base completa.
- Limpieza masiva de reportes generados como commit directo.
- Cualquier runner historico que asuma limites/esquemas anteriores sin reconciliar con contratos actuales de dedupe/fingerprint.

### 7. Que es obsoleto o peligroso?

Peligroso:

- mergear ramas antiguas enteras;
- copiar `scraper/clients.py` o `scraper/run.py` historicos sobre el estado actual;
- aplicar fix de `hash_dedup` sin entender cambios posteriores;
- ejecutar retry scripts sin dry-run y sin validar schema;
- Playwright masivo sin limite de browsers.

Obsoleto:

- limpieza de reportes como sustituto de politica actual;
- frontend historico como reemplazo del frontend vigente.

### 8. Hay soporte Playwright/browser y sirve?

Si hay soporte Playwright/browser. Sirve para diagnosticar y recuperar una parte de las fuentes JS/renderizadas. Para 149 `office` con `202/0 bytes`, debe usarse como clasificador y canary, no como promesa de recuperacion total.

### 9. Que hacer con las 149 paginas `office`?

Plan recomendado:

1. Cargar muestra de 10 read-only.
2. Ejecutar Playwright diagnostic/recheck.
3. Clasificar evidencia:
   - DOM util con links;
   - parser gap;
   - anti-bot;
   - vacio real;
   - no listado;
   - necesita connector.
4. Expandir a 25 si la tasa de recuperacion es positiva y sin MemoryError.
5. Expandir a 149 solo con `MAX_ACTIVE_BROWSERS<=2`, checkpoint/resume y salidas locales.
6. No escribir propiedades ni colas hasta tener manifest seguro.

### 10. Que usar para REMAX / Century / redes?

Hay commits actuales recientes que mencionan Century21, RE/MAX, fingerprints y connectors. Para redes/franquicias conviene priorizar connectors especializados y reglas de identidad, no parser generico. El material historico de junio ayuda menos que commits actuales posteriores.

### 11. Que usar para Supabase/publish/rollback?

Usar:

- docs actuales `docs/RUNBOOK.md`, `docs/SUPABASE.md`, `docs/OPERATIONS.md`;
- migraciones/rollbacks actuales;
- tests de seguridad y rollback actuales;
- invariantes de `pr-be-prod-09e` solo como checklist.

No usar:

- scripts historicos de publish sin compararlos contra el contrato actual.

### 12. Que pruebas priorizar?

Prioridad:

1. `tests/test_run_manifest.py`
2. `tests/test_parser_detail_url_candidates.py`
3. `tests/test_timeout_env_config.py`
4. `tests/test_create_retry_run_from_error_items.py`
5. tests de dedupe/fingerprint actuales: `tests/test_safe_merge.py`, `tests/test_reconcile_final_pipeline_a_manifest.py`
6. tests de seguridad/migraciones: `tests/test_security_*`

### 13. Que no tocar antes del 12/10?

- Migraciones de heartbeat/observabilidad salvo necesidad clara.
- Frontend grande.
- Reescritura de fingerprint/dedupe.
- Limpieza masiva de docs/evidencia.
- Workers masivos Playwright.
- Pipeline B / Neon writes / publish sin autorizacion.

### 14. Cual es el camino critico?

Camino critico hasta 2026-10-12:

1. Confirmar guardrails del runner actual.
2. Reforzar tests de parser y dedupe.
3. Ejecutar diagnostico Playwright read-only sobre muestra de 202/0 bytes.
4. Separar recuperables reales de anti-bot/no-listing.
5. Crear manifest seguro solo de recuperables.
6. Corrida canary limitada.
7. Reconciliacion y reporte.
8. Repetir por oleadas chicas.

## 9. Conclusiones

La historia de GitHub si contiene piezas utiles, pero el repositorio actual ya absorbio varias. El mayor riesgo no es falta de codigo, sino aplicar codigo viejo por reflejo y romper contratos recientes de seguridad, fingerprints y dedupe.

Recomendacion central: no mergear ramas historicas. Usarlas como cantera de tests, invariantes y guardrails. Para el problema actual de cobertura, la prioridad es Playwright diagnostico medido, parser gap tests y retry controlado, no nueva arquitectura.

Estado de clasificacion global:

- `REUSE_AS_IS`: casi nada; solo snippets/tests muy acotados.
- `ADAPT`: runner guardrails, retry, dedupe conflicts, CI, docs.
- `CHERRY_PICK_CANDIDATE`: heartbeat Roomix, despues de adaptacion.
- `TESTS_HEURISTICS_ONLY`: parser detail URL, duplicate hash conflict.
- `ALREADY_PRESENT`: timeouts, retry script/test, parser tests, Playwright dependency/scripts.
- `SUPERSEDED`: frontend branches antiguas, limpieza masiva de reportes como commit directo.
- `OBSOLETE`: politicas operativas anteriores que contradigan runbook actual.
- `DANGEROUS`: merges enteros, runner/scraper clients historicos sobre estado actual, Playwright masivo sin limites, cambios de fingerprint sin gate.
