# ERETZ PROPIEDADES — ACCOUNT HANDOFF

## CURRENT OWNER
B

## PREVIOUS OWNER
A

## CANONICAL BRANCH
integration/eretz

## CURRENT HEAD
El commit que agrega este archivo (ver `git rev-parse origin/integration/eretz`).
Estado de código que entrega A: `19dc3da` (punta de `claude/sweet-curie-doa2mn`); encima de él
solo hay commits de documentación de relevo. Verificar siempre contra el remoto, no contra este
texto: un archivo no puede contener el sha del commit que lo crea.

## LAST UPDATE
2026-10-01 (UTC), relevo A → B preparado desde la sesión CLOUD de la cuenta A.

## REPOSITORY
https://github.com/NicoWulf2026/eretz-propiedades.git

## LOCAL DATA ROOT
ERETZ_DATA_ROOT

Ruta actual conocida:
D:\INMO CAPITAL

La raíz se configura con la variable `ERETZ_DATA_ROOT` (`scripts/rutas_de_datos.py`); sin ella,
los scripts usan `D:\INMO CAPITAL`. Ahí viven el ledger, los paquetes, las snapshots, GeoRef
(`ERETZ_GEO`), la preingestión y los logs de la cola. Nada de eso está en el repo (es público).

## CURRENT OPERATIONAL STATE
LAST_KNOWN = checkpoint del 2026-09-29 17:15 (-03) (`docs/CLOUD_CONTINUATION_HANDOFF.md`).
Desde entonces nadie con acceso a la PC actualizó estas cifras: B las verifica antes de usarlas.

| pieza | LAST_KNOWN | cómo verificar en la PC |
|---|---|---|
| workers | 2 (régimen `ERETZ_WORKERS.json`); todo Tokko en el worker 0; prueba de 3 pendiente (P5) | `python scripts\eretz_automatizacion.py estado` |
| scheduler | tareas de Windows `ERETZ_relanzador` (10 min) y `ERETZ_vigilante_paros` (5 min) | mismo comando |
| cola `--ready` | 1.819 agencias con identidad lista; ritmo ~8 agencias/h con 2 workers | `python scripts\relanzar_la_cola.py` (dry-run) |
| ledger vigente | 766 agencias: 338 COMPLETE, 40 BEST_AVAILABLE, 204 NEEDS_FIX, 132 IDENTITY_PENDING, 51 BLOCKED_EXTERNAL, 1 NO_INVENTORY | ledger en `ERETZ_AGENCY_CERTIFICATION_20260827` |
| snapshot servida | v4l-c desde 2026-09-29 16:52: 65.028 propiedades, 603 agencias, QA de API 14/14 | `ERETZ_API_CONTRACT\_despliegues\` |
| huella compartida | `sha256_12 = 8bf7f9274ed4` (lotes 1–3 aplicados) | `scripts/agency_fingerprints.py` |
| Regression Gate | 578 agencias, 0 pendientes | `python scripts\comparar_con_linea_base.py --linea-base _regresion/ANTES_DEL_LOTE_2026-09-24.jsonl --desde 2026-09-24T11:39:00` |
| recertificación | en curso por los lotes 1–3 (cada lote compartido la reinicia) | logs `cola_w*.log` |
| suite LOCAL | 3.701 passed (HEAD `c4092f1238`, Windows, Python 3.14.4) | ver NEXT ACTIONS #1 |

**Integrar `integration/eretz` NO cambia la huella**: se verificó que ninguno de los 89 archivos
modificados desde `ce57824` está en `archivos_de_la_huella()`. Los cambios semánticos que sí la
tocan están como PARCHES sin aplicar (abajo).

## WHAT ACCOUNT A COMPLETED
Sobre `handoff/codex-unificacion-2026-09-18` (`ce57824`), 24 commits en
`claude/sweet-curie-doa2mn`, todos desde CLOUD (sin red a fuentes externas y sin datos locales):

| tema | commit(s) | resultado |
|---|---|---|
| P9 título derivado | `728ef67` | «{tipo} en {operación} · {localidad}» en la web; `hasValidTitle` intacto |
| Suite reproducible fuera de la PC | `bfa37a7` | marcador `georef` + `ERETZ_REQUIRE_LOCAL_DATA=1`; `httpx2` al lock; en Linux 3.610 passed, 170 skipped |
| Snapshot sintética de QA | `ab64c32` | `scripts/snapshot_sintetica.py` (86 fichas rotuladas); `desplegar_snapshot.py` y `/readyz` la rechazan |
| QA de API | `ab64c32` | 14/14 sobre la sintética |
| QA de navegador | `d1a874f`, `b246765` | `scripts/qa_navegador_sintetica.py`; 82 → 75 ok, 0 fallos, 7 salteados (flag del asistente) |
| P21 API beta | `f7d4b1c`, `8ae134e` | `deploy/api-beta/` (Dockerfile, fly.toml, runbook); docker verificado; NO desplegado |
| healthz / readyz | `ab64c32` | `/healthz` liveness, `/readyz` 503 si falta/vacía/sin FTS/sintética |
| Activación atómica / rollback | `f7d4b1c` | `deploy/api-beta/activar_snapshot.py` (sha256, integrity, enlace atómico, historial) |
| P18 rol escritor | `b74184b` | migración + rollback + verificador PGlite 14/14 + runbook; canario ya no usa `eretz_preview_ro`; NO creado |
| P7 USD 10/mes | `21ebbe0` | cobro dentro de cada proveedor pago; costo declarado o no se busca; libro `ERETZ_SEARCH_SPEND.jsonl` |
| Contrato backend↔frontend | `fcf4cee` | 22 respuestas reales de la API validadas por los parsers del frontend |
| Observabilidad de la API | `e8986ff` | un evento JSON por pedido, `x-request-id`, noindex/nosniff/no-referrer |
| Límites de entrada | `692be33` | topes de largo en textos; sin hallazgos de inyección |
| `/api/health` del frontend | `5e3a651` | estado de la API, snapshot sintética o no, SHA desplegado |
| undici (seguridad) | `1030149` | `npm audit --audit-level=high` = 0 |
| Preflight GeoRef de la cola | `b52a1cb` | sin GeoRef el worker sale con código 3 (caso `criscenti`) |
| P10 tooling | `36d9954` | `connectors/poligono_provincia.py` + `scripts/geo_poligonos_provincias.py` (sin uso en la huella) |
| Lote 4 | `e258442` | parche de conteos en letras |
| P10 parche | `6b0f047` | parche de provincia contradictoria |
| Accesibilidad | `b246765` | axe 0 violaciones serias; `<main>` anidado corregido |
| Workflow manual QA | `ed525a6` | `.github/workflows/qa-navegador-sintetica.yml` (solo `workflow_dispatch`) |
| Puente LOCAL→CLOUD | `19dc3da` | `scripts/cloud_bridge/` (capturador de fixtures, chequeo P18 READ-ONLY) |
| Casos bloqueados por red | `11e28e1`, `e258442` | martelliti, fenix, paladino, Wix, IGN: CLOUD nunca tuvo red; ver REQUIRES LOCAL |

Error conocido en un mensaje: `ab64c32` dice «58 fichas»; son 86 (corregido en CURRENT_STATE).

## PATCHES PREPARED BUT NOT APPLIED
Ambos tocan la huella COMPARTIDA: aplicarlos reinicia la recertificación entera (P4).

**Lote 4 — conteos escritos con letras**
- PATH: `docs/agent/lotes/LOTE_COMPARTIDO_4_2026-09-29.patch` (+ README del lote)
- PURPOSE: leer «cuatro dormitorios», «un baño» en la prosa (`pozzobon`, `ente`), sin rangos, cotas ni menciones ambiguas.
- TEST STATUS: 16 tests en el parche (6 fallan sin el cambio); suite CLOUD con el parche aplicado: 3.588 passed.
- WHY NOT APPLIED: `connectors/generico.py` está en la huella; sin corpus no hay radio.
- WHAT LOCAL MUST MEASURE: A/B de extracción sobre el HTML cacheado de las fichas generico con conteos vacíos, con y sin el parche: campos nuevos por agencia, una muestra revisada (buscar «un dormitorio en suite» en casas de varios). Decidir según P4.

**P10 — provincia publicada contradictoria**
- PATH: `docs/agent/lotes/LOTE_P10_PROVINCIA_POR_POLIGONO_2026-09-29.patch` (+ README)
- PURPOSE: localidad única + coordenada DENTRO del polígono oficial (IGN) de su provincia (≥ 2 km del límite) + a ≤ 100 km de la localidad → se afirma la provincia de la localidad; la publicada queda como evidencia.
- TEST STATUS: 9 tests con GeoRef y geometría SINTÉTICOS (corren sin datos locales); suite CLOUD con el parche: 3.589 passed.
- WHY NOT APPLIED: toca `geografia.py`, `base.py` y `agency_fingerprints.py`; falta la geometría real (`provincias_ign.json`) y el radio.
- WHAT LOCAL MUST MEASURE: generar la geometría, aplicar en `eretz-dev`, construir una snapshot candidata y leer `provincia_normalizada_por_poligono_p10` del resumen; revisar muestra y falsos positivos.

## REQUIRES LOCAL OPERATIONAL STATE
1. Suite completa con `ERETZ_REQUIRE_LOCAL_DATA=1` sobre `integration/eretz` (descubre lo que los 170 skips de CLOUD no ven).
2. QA de navegador sintética en Windows: `python scripts\qa_navegador_sintetica.py --salida _scratch\qa_sintetica`.
3. Radio del lote 4.
4. Radio de P10.
5. Generar y validar `connectors/geometria/provincias_ign.json` (`python scripts\geo_poligonos_provincias.py`): códigos, CABA, islas, fronteras, sha256.
6. Martelliti: ¿la línea «Laprida 1835, B7602FKK Mar del Plata…» junto al `fa-map-marker` es idéntica en las 44 fichas? Si sí es la OFICINA y no se extrae.
7. Fenix: fixture de la superficie sin rótulo («50 M² 50 M²»).
8. Paladino: fixture de la página y de la respuesta de su API (endpoint, paginación, total, detalle, si usa token, sin guardar valores).
9. Wix (lucas liprandi, dib kai): fixtures con `wix-warmup-data`.
10. P18 READ-ONLY: `python scripts\cloud_bridge\p18_chequeo_lectura.py` → YES / NO / UNABLE_TO_VERIFY.
11. Cola, workers y ledger reales.
12. Snapshots reales (reconstrucción y despliegue P2).

Herramientas para 5–10: `scripts/cloud_bridge/` y la tabla «EVIDENCE READY FOR CLOUD» de `docs/agent/HANDOFF.md`.

## NEXT ACTIONS FOR ACCOUNT B
1. **INTEGRAR Y VALIDAR LOCALMENTE EL ESTADO DE `integration/eretz`** antes de aplicar cambios semánticos: llevar el worktree operativo a esa rama (fast-forward desde `ce57824`), `pip install --require-hashes -r requirements.lock` (trae `httpx2`), suite con `ERETZ_REQUIRE_LOCAL_DATA=1`, y comprobar que la cola sigue corriendo (`eretz_automatizacion.py estado`). La huella no cambia.
2. P18 READ-ONLY (#10 arriba). Si da YES, la credencial del Preview puede escribir hoy: priorizar `migrations/eretz_property_writer_role.sql` (acción productiva: autorización + backup/restore).
3. Generar `provincias_ign.json` y medir el radio de P10 en `eretz-dev`.
4. Medir el radio del lote 4 en `eretz-dev`; decidir con P10 si van juntos (P4).
5. Martelliti: el conteo de la línea en las 44 fichas; cerrar B sin cambio si es la oficina.
6. Fixtures de fenix, paladino y Wix con `scripts/cloud_bridge/capturar_fixture.py`; después, parsers con tests (como parche si tocan la huella).
7. QA de navegador sintética en Windows y, cuando haya cuenta de hosting (P21), seguir `deploy/api-beta/RUNBOOK.md`.
8. Operación continua: cola sana, Regression Gate a 0 tras cada tanda, snapshot nueva con despliegue automático P2 cuando las certificaciones lo justifiquen; reprobar 3 workers (P5).

## DO NOT REDO
- Auditorías históricas del proyecto (están en Git y en `docs/agent/`).
- Lotes compartidos 1, 2 y 3 (aplicados el 29-09).
- Políticas P1–P24 (decididas; no volver a preguntar).
- Todo lo de WHAT ACCOUNT A COMPLETED: P9, suite reproducible, snapshot sintética, QA de API y de navegador, contenedor P21, healthz/readyz, activación/rollback, P18 (SQL/runbook/tests), P7, contrato API↔frontend, observabilidad, límites de entrada, `/api/health`, undici, preflight GeoRef, accesibilidad, revisión de encabezados de seguridad del frontend (sin hallazgos), análisis estático (sin hallazgos).
- Los parches del lote 4 y P10: no reescribirlos; medirlos.
- Martelliti: no implementar la extracción de esa línea sin el conteo de las 44 fichas.

## PERMANENT POLICIES
`docs/agent/POLITICAS_PERMANENTES.md`: **P1–P24 siguen vigentes** y mandan. Un caso cubierto por
una política se resuelve con ella, sin preguntar. Reglas del repo: `CLAUDE.md` y `.claude/rules/`.

## PRODUCTION SAFETY
Prohibido sin las condiciones documentadas (`CLAUDE.md` § Barreras, P12/P17/P19/P24,
`docs/agent/READY_FOR_PRODUCTION_ACTION.md`):
- writes a Supabase (INSERT/UPDATE/DELETE), migraciones, RLS/grants, crear o modificar roles (P18), restore;
- deploy público (Vercel producción, API remota), DNS, retirar `noindex`;
- merge a `main` que dispare CI/producción;
- rotar contraseñas; gasto de búsqueda paga por encima de USD 10/mes (P7);
- reemplazar la snapshot servida fuera de `desplegar_snapshot.py --automatico` con todas las compuertas P2;
- force push, `reset --hard`, `clean` destructivo, reescribir historia; subir datos privados o secretos.

## WHEN B RUNS OUT OF TOKENS
Protocolo inverso (detalle en `docs/ACCOUNT_RELAY_PROTOCOL.md`):
B → terminar la unidad atómica → tests relevantes → commit → push `integration/eretz` →
verificar que el HEAD remoto es el local → actualizar este archivo (CURRENT OWNER = A,
PREVIOUS OWNER = B, CURRENT HEAD, LAST UPDATE, NEXT ACTIONS) → commit + push → árbol limpio.
