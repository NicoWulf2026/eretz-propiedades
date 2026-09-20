# ERETZ - Codex Recovery Master Report

Fecha: 2026-09-15  
Repositorio: `D:\INMO CAPITAL\Inmo-Capital-main`  
Rama: `release/eretz-private-preview`  
HEAD inicial observado: `9461fab019 docs(retrabajo): no comprar maquinas, eliminar la repeticion`  
Modo: auditoria read-only con preparacion de artefactos locales.

## 1. Alcance ejecutado

Se avanzo sobre el plan de recuperacion sin activar ejecucion productiva:

- revision de estado Git;
- identificacion de fuente canonica de las 149 paginas office clasificadas como vacias/no oficiales;
- materializacion del manifest canonico local;
- preparacion de muestra canary 25 representativa;
- preparacion de runner Playwright read-only con checkpoint;
- contraste de la muestra Wave 0 anterior contra el universo canonico;
- lectura de evidencia RE/MAX ya existente;
- plan de ventana semantica separado.

No se ejecuto:

- push;
- deploy;
- merge;
- cherry-pick;
- rebase;
- reset;
- clean;
- DB writes;
- Supabase writes;
- migraciones productivas;
- workers nuevos;
- stop/restart de workers ajenos;
- navegador adicional bajo stop condition;
- cambios de parser;
- cambios de fingerprint.

## 2. Estado inicial de Git

El repositorio ya estaba sucio antes de esta etapa.

Cambios modificados preexistentes:

- `ERETZ_RETRABAJO.md`
- `scripts/build_full_coverage_manifests.py`
- `scripts/run_manifest.py`
- `scripts/run_production_parser_playwright_recheck.py`
- `tests/test_full_7004_coverage.py`
- `tests/test_run_manifest.py`

Tambien habia numerosos archivos no versionados de auditorias/scripts locales.
No se revirtio nada.

## 3. Capacidad actual reutilizable

Hallazgos confirmados desde `ERETZ_GITHUB_REUSE_AUDIT.md` y tests:

| capacidad | estado actual | recomendacion |
|---|---|---|
| `run_manifest.py` con guardrails | presente | mantener; no ejecutar productivo sin plan |
| retry desde errores | presente con dry-run/commit | usar solo para lotes acotados |
| tests de parser detail-url | presentes | ampliar con gaps medidos |
| Playwright | instalado y probado localmente en Wave 0 | usar como diagnostico con canary |
| timeout multiplier | presente, default conserva comportamiento | usar por preset, no globalmente |
| dedupe/fingerprint | estado reciente distinto al historico | portar invariantes/tests, no logica vieja |

Tests ya ejecutados en Wave 0:

```text
python -m pytest -q tests/test_run_manifest.py tests/test_parser_detail_url_candidates.py tests/test_timeout_env_config.py tests/test_create_retry_run_from_error_items.py
159 passed
```

Tests adicionales:

```text
python -m pytest -q tests/test_safe_merge.py tests/test_reconcile_final_pipeline_a_manifest.py tests/test_network_security.py
58 passed
```

## 4. Lista canonica 149/42.454

Fuente:

`D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827\ERETZ_OFFICE_PAGES_VALIDADAS.jsonl`

Filtro:

`clase = NO_OFFICIAL_WEB_FOUND`

Manifest generado:

`_scratch/office_202_empty_canonical.csv`

Resumen:

| metrica | valor |
|---|---:|
| agencias | 149 |
| URLs unicas | 147 |
| avisos esperados | 42.454 |
| REMAX | 137 |
| CENTURY21 | 8 |
| COLDWELL_BANKER | 2 |
| KELLER_WILLIAMS | 2 |

La fuente no trae status/bytes originales por fila. Se documento como
`UNKNOWN_NOT_RECORDED` para evitar inventar datos.

## 5. Correccion de la Wave 0 anterior

La canary previa de 10 office-like paginas tuvo:

- `RECOVERED_BY_RENDER`: 6
- `PARSER_GAP_AFTER_RENDER`: 1
- `NOT_LISTING_SOURCE`: 3

Pero el cruce exacto contra el universo 149 dio:

- overlap por `agency_id`: 0/10
- overlap por URL: 0/10

Conclusion: sirve como prueba de capacidad Playwright/parser, no como
estimacion de recuperacion para 149.

## 6. Canary 25 canonica preparada

Manifest:

`_scratch/office_202_empty_canary25_manifest.csv`

Cobertura:

- 25 agencias;
- 8.694 avisos esperados;
- todas las redes no-REMAX;
- muestra REMAX por peso y forma de URL.

Distribucion:

| red | agencias |
|---|---:|
| REMAX | 13 |
| CENTURY21 | 8 |
| COLDWELL_BANKER | 2 |
| KELLER_WILLIAMS | 2 |

## 7. Runner Playwright preparado

Script:

`_scratch/office_browser_canary.py`

Salida esperada:

`_scratch/office_202_empty_canary25_results.csv`

Clasificaciones:

- `RECOVERED_BY_RENDER`
- `PARSER_GAP_AFTER_RENDER`
- `EMPTY_IN_REAL_BROWSER`
- `EXTERNAL_ANTIBOT`
- `NEEDS_CONNECTOR`
- `NOT_LISTING_SOURCE`

No se corrio por stop condition:

- RAM libre ~1,8 GB;
- worker `run_agency_certification_queue` activo;
- procesos Playwright/Chromium activos.

## 8. RE/MAX / redes

Lectura de `ERETZ_HALLAZGO_REDES.md`:

- 327 agencias de red concentran 68.140 avisos, 43,9 % del inventario observado.
- RE/MAX sitemap publica 74.529 fichas.
- Solo ~34 % de fichas sirve HTML legible en medicion previa; el resto responde 202/0 de forma deterministica por URL.
- Cuando una ficha se lee, la atribucion de oficina es practicamente total.
- La idea de que `office.description` siempre trae dominio propio fue descartada: era falsa generalizacion desde un caso puntual.

Artefactos medidos localmente:

- `ERETZ_REMAX_SITEMAP_SONDEO.jsonl`: 35 oficinas vistas, 31 en padron, 4 fuera de padron.
- `ERETZ_REMAX_CANARIO.jsonl`: 200/200 `ANTIBOT_DESAFIO_WAF`, bytes 1.971.

Decision: RE/MAX va a ventana semantica como conector/estrategia nueva; no
activar ahora ni mezclar con retry generico.

## 9. Riesgos principales

| riesgo | severidad | mitigacion |
|---|---|---|
| Ejecutar Playwright masivo con workers activos | alta | canary 25 solo en ventana limpia, `MAX_ACTIVE_BROWSERS=1` |
| Inferir 149 desde muestra no canonica | alta | usar solo manifest canonico |
| Portar codigo historico literal | alta | reusar tests/invariantes, no merges |
| Cambiar parser/fingerprint con cola activa | alta | ventana semantica separada |
| Duplicar inventario de redes y oficinas propias | alta | decidir fuente ganadora antes de DB writes |
| Clasificar paginas institucionales como inventario | media | buckets separados `NOT_LISTING_SOURCE`/`NEEDS_CONNECTOR` |
| Parser DOM con falsos positivos globales | media | medir `property_links_found` vs identidad de oficina |

## 10. Plan operativo seguro

### Paso A - Cerrar medicion Playwright office

Ejecutar cuando no haya Playwright/queue ajenos activos:

```powershell
$env:MAX_ACTIVE_BROWSERS='1'
python _scratch/office_browser_canary.py --input _scratch/office_202_empty_canary25_manifest.csv --output _scratch/office_202_empty_canary25_results.csv
```

Criterio de avance:

- si >= 8/25 son recuperables reales o parser gaps claros, escalar a 149;
- si predominan `NOT_LISTING_SOURCE`/`EXTERNAL_ANTIBOT`, derivar a conectores;
- si predominan parser gaps, crear tests antes de tocar parser.

### Paso B - No activar semantica todavia

Antes de cualquier extractor semantico:

- congelar fingerprint radius;
- definir fixtures y expected rows;
- ejecutar sobre copias/local artifacts;
- no tocar frontend;
- no tocar DB productiva.

### Paso C - Separar familias

No tratar todo como "office 202":

- RE/MAX sitemap/catalogo;
- RE/MAX office slug;
- RE/MAX global agent/office/listing;
- Century21;
- Coldwell;
- Keller Williams;
- parser gaps genericos.

## 11. Estado final de esta etapa

Archivos creados/actualizados por esta etapa:

- `ERETZ_PLAYWRIGHT_OFFICE_CANARY.md`
- `ERETZ_CODEX_RECOVERY_MASTER_REPORT.md`
- `ERETZ_SEMANTIC_WINDOW_PLAN.md`
- `_scratch/office_browser_canary.py`
- `_scratch/office_202_empty_canonical.csv`
- `_scratch/office_202_empty_canary25_manifest.csv`

No hubo migraciones, DB writes, deploy, push ni cambios de runtime productivo.
