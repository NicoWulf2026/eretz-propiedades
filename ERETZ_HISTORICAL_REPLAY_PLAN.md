# Banco de replay histórico

**2026-09-16 · `database_writes: 0`**

El §22 pide convertir los hallazgos útiles en replay permanente, y el §102 dice
para qué: que una clase de error se investigue **una vez**. Este documento define
qué casos quedan fijados y por qué cada uno merece un lugar permanente.

Un caso entra al banco sólo si cumple las tres: hay evidencia reproducible, la
expectativa es una invariante durable (no la compuerta de una corrida), y su
regresión costaría algo concreto.

---

## Nivel de comparabilidad de los benchmarks históricos

El §6 pide no inventar equivalencia. De los benchmarks que el mandato nombra:

| benchmark | nivel | por qué |
|---|---|---|
| detail URL detection, 16 tests | **REPLAY_EXACT** | los 16 tests están en HEAD **verbatim** y los 47 de hoy pasan. Se reejecutaron. |
| manifest runner, 64 tests | **REPLAY_EXACT** menos 2 | 62 sobreviven; las 2 borradas se reejecutaron a mano contra el código actual. |
| las 413 fuentes de `9aa299b` | **NO RECONSTRUIBLE** | los scripts `validate_parser_fix_07b.py` y `validate_detail_quality_07d.py` están en HEAD, pero la lista de 413 fuentes con su snapshot no. Sin ese dataset, cualquier número que produzca hoy mide **otra población**. No se reporta equivalencia. |
| `ambientes` legacy vs actual | **REPLAY_RECONSTRUCTED** | se armó hoy con 5 fichas reales bajadas por HTTP. No es el dataset histórico; es una muestra nueva, chica y verificada una por una. |

La afirmación histórica de *3.588 → 4.628 links sobre 413 fuentes* **no se pudo
reproducir ni refutar**. No se convierte en "sigue valiendo" ni en "ya no vale":
queda como no verificable con lo que hay en el repositorio.

---

## Casos que entran al banco

### REPLAY-H01 · `ambientes` sale de la etiqueta y no del menú

| | |
|---|---|
| **REPLAY_ID** | `REPLAY-H01` |
| **ORIGIN_COMMIT** | `9aa299bde9` (regla legacy) + `xfail` abierto en `shared/certifier` |
| **SOURCE/fixture** | fichas reales de `bottegapropiedades.com.ar/site/properties/*` |
| **HISTORICAL_EXPECTATION** | de `"En alquiler Ambientes 5 Dormitorios 3"` sale `ambientes = 5` |
| **CURRENT_EXPECTATION** | hoy el certificador cierra `EXTRACTION_FAILED` con cobertura 0,41 |
| **FORBIDDEN_REGRESSION** | de `"Departamentos Monoambiente 1 dormitorio"` **no** puede salir `ambientes = 1` |
| **METRIC** | cobertura de `ambientes` en la familia, y cero falsos desde menús |

Lo que hace a este caso valioso es que las dos reglas fallan del mismo lado: el
legacy recupera 5 de 5 valores reales **y** fabrica un `1` desde un menú de
navegación; la señal actual hace exactamente lo mismo. El replay tiene que fijar
las dos mitades a la vez, porque arreglar una sola reintroduce la otra.

Ya existe test rojo documentando la mitad peligrosa
(`tests/test_senal_de_fuente_ambientes.py`, 3 `xfail`). Falta la mitad de
recuperación: un fixture con la etiqueta limpia que hoy se pierde.

### REPLAY-H02 · el preflight de deduplicación no puede degradar a duplicación

| | |
|---|---|
| **REPLAY_ID** | `REPLAY-H02` |
| **ORIGIN_COMMIT** | `fc896b1360` (donde estaba la tolerancia peligrosa) |
| **SOURCE/fixture** | `requests.get` simulado devolviendo 500 |
| **HISTORICAL_EXPECTATION** | **se invierte a propósito**: el histórico devolvía un set incompleto y seguía |
| **CURRENT_EXPECTATION** | `RuntimeError`, la corrida no arranca |
| **FORBIDDEN_REGRESSION** | que un error de PostgREST vuelva a producir un conjunto de deduplicación **silenciosamente incompleto** |
| **METRIC** | filas duplicadas insertadas tras un error de preflight: debe ser 0 |

Este es el único caso del banco cuya expectativa histórica se guarda **como
prohibición**. Es la lección del §14 hecha test: el repositorio histórico tenía
un test verde que protegía un comportamiento que duplicaba datos.

Un segundo invariante conviene fijar junto: la **paginación**. El histórico
pedía `limit: 10000` sin paginar, así que una agencia con más de 10.000
propiedades entraba truncada al set de deduplicación, en silencio. El actual
pagina por `offset` con `order` estable.

### REPLAY-H03 · un catálogo alcanzable por HTTP no puede cerrarse `SIN_INVENTARIO`

| | |
|---|---|
| **REPLAY_ID** | `REPLAY-H03` |
| **ORIGIN_COMMIT** | ninguno: **hueco nuevo**, no regresión |
| **SOURCE/fixture** | `tests/test_firma_navegacion_javascript.py`, marcado real de `davidrodriguezprop.com` |
| **HISTORICAL_EXPECTATION** | el legacy también da 0 — se midió |
| **CURRENT_EXPECTATION** | `NAVEGACION_SOLO_JAVASCRIPT`, 4 de 35 agencias |
| **FORBIDDEN_REGRESSION** | un perfil de portal **nunca** puede contarse como inventario recuperable |
| **METRIC** | agencias recuperables por HTTP plano, hoy 4 |

La prohibición de este caso no es teórica: la primera medición dio 7
recuperables y **tres eran perfiles de `buscainmueble.com`** cuyo catálogo
también vive en un `location.href` —apuntando al `/List` del portal—. El test
`test_un_perfil_de_portal_NUNCA_es_inventario_recuperable` fija eso, y muerde:
con la regla rota, 3 tests fallan.

### REPLAY-H04 · el heartbeat no puede frenar al crawler

| | |
|---|---|
| **REPLAY_ID** | `REPLAY-H04` |
| **ORIGIN_COMMIT** | `5e51042541` (24 tests históricos, ausentes de HEAD) |
| **SOURCE/fixture** | inyección de fallo en el canal de telemetría |
| **HISTORICAL_EXPECTATION** | ningún método propaga excepciones; Supabase caído no frena el crawl |
| **CURRENT_EXPECTATION** | el vigilante ya cumple: estado escrito primero, aviso después, excepción tragada |
| **FORBIDDEN_REGRESSION** | que una falla de notificación impida escribir el estado |
| **METRIC** | estado persistido tras fallo del canal: siempre |

Vale la pena fijarlo aunque el heartbeat no se porte todavía, porque **este
error ya ocurrió acá**: el vigilante corrió dos horas fallando en silencio
porque el import del canal de aviso estaba dentro de la rama que avisa. Quince
tests verdes no lo detectaron, porque todos pasaban `--sin-alerta`.

---

## Tests históricos, clasificados (§23)

| test | clasificación | motivo |
|---|---|---|
| los 16 de `test_parser_detail_url_candidates.py` | **STILL_VALID** | están en HEAD verbatim y pasan |
| los 62 sobrevivientes de `test_run_manifest.py` | **STILL_VALID** | sin cambio de invariante |
| `test_load_existing_urls_tolerates_http_error` | **UNSAFE_NOW** | protegía una degradación a duplicación silenciosa |
| `test_max_execute_limit_is_892` | **SUPERSEDED** | compuerta de una corrida, no invariante |
| los 7 de `test_timeout_env_config.py` | **STILL_VALID** | presentes, sin cambios |
| los 11 de `test_create_retry_run_from_error_items.py` | **STILL_VALID** | presentes, sin cambios |
| los 24 de `test_roomix_agency_heartbeat.py` | **WORTH_PORTING** | ausentes; llegan con el port, no antes |

---

## Lo que este banco **no** hace

No se porta código todavía. El bulk sigue activo y el §39 manda backlog, no fix.
Los tres candidatos con su radio están en
[`ERETZ_GITHUB_HISTORICAL_AUDIT.md`](ERETZ_GITHUB_HISTORICAL_AUDIT.md), sección I,
y entran a la **misma** ventana semántica que el backlog existente: el §40 es
explícito en no abrir una segunda ventana sólo porque los hallazgos vinieron de
GitHub.
