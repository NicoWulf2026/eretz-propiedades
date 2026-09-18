# ERETZ — CODEX → CLAUDE CODE HANDOFF

Fecha: 2026-09-18. **Interrupción de emergencia por límite de uso, no misión terminada.**
No iniciar nuevamente la auditoría ni declarar beta/producción listas.

## Misión y entrega

Comparar toda la evolución GitHub/local por comportamiento, conservar seguridad
moderna y capacidades históricas mejores, corregir regresiones por familia,
unificar reversiblemente y producir veredicto/plan de backend beta, producción y
cobertura nacional. No es una reescritura ni una fusión ciega.

- Remoto principal: https://github.com/NicoWulf2026/eretz-propiedades.git
- Worktree editable único: `D:\INMO CAPITAL\eretz-unified`.
- Branch: `codex/eretz-unified-audit`.
- Base local: `d9238e64be53d27f0ca46deae74ad16eb01bb6b5`.
- HEAD funcional al interrumpir: `7dd838fa63c90952b3c744ecf8f326f7741761b1`.
- Git status antes del handoff: CLEAN; ningún cambio funcional sin commit.
- Este documento se entrega en un commit posterior de documentación: obtener su
  hash con `git log -1`; no confundirlo con el HEAD funcional validado arriba.
- No hay suites/procesos de esta sesión pendientes conocidos. Última suite terminó.
- Artefactos `_scratch` son locales/ignorados, no están incluidos en Git/wheel.
  No borrarlos: contienen replays, XML, snapshots y mediciones útiles.

PowerShell/Git: usar `git -c 'safe.directory=D:/INMO CAPITAL/eretz-unified' ...`
en el candidato. Python disponible en
`C:\Users\Nicolas Wulfsohn\AppData\Local\Programs\Python\Python314\python.exe`;
no se usa un venv candidato. Node: instalación de Program Files.

## Originales preservados — NO EDITAR

Último inventario comprobado: ocho originales más candidato. No se eliminaron
branches/worktrees ni se sobrescribieron cambios ajenos.

| Worktree bajo `D:\INMO CAPITAL` | HEAD observado | Observación |
|---|---|---|
| Inmo-Capital-main | 56f220c2b7fb5a1f6770c36b75410f0a3ab7a84d | release/eretz-private-preview; cambios ajenos, último inventario 5 dirty + 85 Python untracked |
| eretz-agency | d9238e64be53d27f0ca46deae74ad16eb01bb6b5 | Base moderna; limpio observado |
| eretz-audit | 8521d47008e2408ef3353defd5a75f4e699c6c86 | Detached |
| eretz-integration | bd3f37c3336f707675bd684ef5a62284427eb36c | integrate/eretz-pre-main |
| eretz-main | e9630f5f7060ad2b78b5d74960b208db0b0599cf | main |
| eretz-rescue | b6c326b0cecb2242e7697968f673e5fcc57f4ce7 | Cambios ajenos observados |
| Inmo-Capital-api-v2-cutovers | 806d5a5928ba4f36cf094138d68ee36615e1d006 | API integrada al candidato |
| Inmo-Capital-frontend-phase-a | ea7708f79fdc1a535d10f8f68322b5c2ce386668 | F7 preservado e integrado |

El cwd de la app puede seguir siendo Inmo-Capital-main: **establecer workdir
explícito al candidato en cada comando**. Históricamente hubo workers backend
activos. No tocar sus archivos/runner/manifiestos/cobertura.

## Veredicto provisional y arquitectura que quedó

Inventario realizado de 39 refs, 9 worktrees y ~3040 archivos de código; 12 heads
remotos obtenidos sin prune. Remote main observado:
`15e81991c0511653bbe9efb70a92d13c1835b310`, ancestro moderno (~534 commits detrás
de la evolución local), no una alternativa completamente independiente.

No está demostrado que GitHub sea globalmente superior. Sí hubo capacidad
histórica de detectar URLs de detalle perdida/reducida en ciertas familias.
El commit de control `9aa299bde9f7bc410b010be1387566269f551145` se inspeccionó y
ejecutó en replay acotado. Su benchmark histórico de 413 fuentes/+1040 links
**no fue reproducido**: no se encontró el artefacto completo. No extrapolar.

Local es superior en contratos API/domain, geografía con nivel/proveniencia,
resiliencia parcial, seguridad de red/fuentes, certificación granular, trazabilidad,
lifecycle observable, UI F7 y tests de fallos. También contenía regresiones
modernas reales: mayor sofisticación/tests no garantizaban correctitud.

Estrategia elegida: **candidato sobre la base local moderna**, incorporando F7 y
API de sus branches y recuperando capacidades históricas en fronteras compartidas.
La candidata todavía no es una versión final canónica aprobada.

- URL discovery compartido: `scraper/detail_urls.py`; no segundo scraper histórico.
- Red/fuentes: política compartida, TLS verificado, inventario oficial/office/perfil
  distinguidos; Zonaprop/Argenprop y otros portales no autorizan inventario.
- API DTO/schema/adapter/domain; frontend no consume JSON arbitrario en React.
- Snapshot SQLite local, API combinada, mapa viewport acotado y batch real; no
  inventar cursor, ranking frontend ni traducciones numéricas de identidad.
- Ranking técnico separado del sort del usuario; moneda explícita en price sort.
- Null/zero/incompletas retenidas por raw/staging/API/presentación.
- Certificación separa inventario/determinismo de verdad de campos/geografía.
- Se conservan entrypoints REST/RPC/rollout cuando hay consumidores legítimos.
  No hay equivalencia completa de escritores: no borrar el REST ni monolitos enteros.
- Roomix/UX V2 preservados. Mobile congelado. No nueva fidelity layer/rediseño.

## Commits locales de unificación, cronológicos

Los commits importados de F7/API no se enumeran como creados aquí; los dos merges
locales preservan su historia. Esta es la línea first-parent relevante de la misión:

| Commit | Contenido |
|---|---|
| e5d8346b0c | Integración local F7 canónico, preservando historia |
| 6240c8d0ce | Integración API v2 sin perder certificación moderna |
| e5f2c63dba | SQL de mapa combinado y diagnóstico de freshness/worktrees |
| edf7a37b34 | Selección única de fuentes y fronteras resilientes de datos |
| 910dcebea1 | Incertidumbre diagnóstica y métricas de comparación honestas |
| d534333847 | TLS de conectores; tests de campañas incluidos en CI |
| 303f443ea9 | Dependencias frontend y bridge de operador endurecidos |
| d39ebae0fa | Recuperación URL histórica, política outbound y packaging compartidos |
| 1234904ebf | Incompletas reales sobreviven staging/normalización |
| 598d288b19 | Ventana/ranking/páginas estables; geografía conflictiva retenida |
| 667050b92c | Claim atómico de checkpoints y promoción sólo verificada |
| 6d455c52f8 | Wheel runtime y archivos de entorno ignorados |
| c83d1fe583 | Smoke frontend contra API/snapshot real unificado |
| 707ecb981a | Counts, fuentes, credenciales y artefactos de ingesta protegidos |
| 1515b2493d | Replays históricos y evidencia de auditoría |
| c4800ef54f | SQL real en PostgreSQL desechable PGlite |
| 1080613ed0 | JSON-LD aislado, alias provincial, no barrio ficticio, legacy 409 |
| b597decd9f | Replay por fila, oferta actual incierta y namespace FK del canary |
| 420f7982f0 | Conflictos geográficos e imágenes repetidas legítimas; versiones de contratos |
| 7eff650100 | Discovery sin dotenv implícito y red compartida |
| 8d37c61323 | Snapshot preparado/indexado antes de publicación exclusiva |
| 3dd2a27df5 | Defectos de schemas de fingerprint viejos siguen abiertos |
| 8467265204 | Herramientas de imágenes no descartan renders compartidos; cleanup seguro |
| 6e4eaed883 | Cliente moderno falla cerrado ante lookup de identidad incompleto |
| 30f62fc19a | Cache de marcadores constantes de clasificación de imágenes |
| 9230bd400d | Ceros normalizados y superficies fraccionarias conservados |
| af7df0ebed | Publicación exclusiva Windows/exFAT sin requerir hard links |
| 7de49c48ec | JSONL corrupto de propiedades certificadas rechazado |
| 430ddb436f | Bound de superficie compatible con almacenamiento INT_MAX |
| 2b0a48f523 | Evidencia conductual y gates provisionales, no cierre ficticio |
| 40d7ca5a8a | Conflicto de lecturas de propiedad a igual instante rechazado |
| d938bbf4b6 | Reutiliza normalización existente de URL de imagen |
| b018b86398 | Imagen repetida no equivale a asset de página probado |
| 2b059b4010 | Documenta límites de hipótesis de imágenes/paginación |
| e1b6a886e6 | Regresión backend en proceso limpio documentada |
| 7476a69009 | Reemplazo de snapshot explícito ante builds concurrentes |
| 11c73c77a2 | Control vivo e incertidumbre de performance |
| 658ac32eaa | SOURCE_UNKNOWN distinto de ausencia; bool no es count cero |
| bed5e35a43 | Semántica de evidencia de fuente y replays |
| cc5654b714 | Operaciones desconocidas/proyecto almacenadas NULL según CHECK público |
| b9c6c49cb7 | Validación de storage y universos de catálogo diferenciados |
| 7d90ab039a | REST de identidad falla cerrado ante rango/página/total incompleto |
| 61da2abf18 | Superficie cubierta conservada en publicación atómica |
| 668655b477 | Build snapshot cierra conexiones y limpia sólo temporales propios |
| ad8215dcf8 | Fechas de archivos ordenadas con offsets explícitos, no zona inventada |
| a4840295d7 | Matriz de consumidores/tooling y publicación pendiente |
| 1fec505fec | Archivo declarado ausente/count inconsistente/run2 corrupto rechazados |
| e7e0c47e35 | Observaciones fiables y ausencia consecutiva completa; lifecycle no aprobado |
| 8d6949d270 | INSERT preserva id_externo/provincia/pais reales nullable; UPDATE no independiente |
| 5a2b2865a4 | GeoRef incompleto/error no produce referencia; descarga previa de seis recursos |
| 05c7dc7188 | Manifiestos GeoRef verificados; compatibilidad CRLF histórica explícita |
| caf0b05686 | Huella schema 5 observada; backfill no recertifica retrospectivamente |
| 59d27a31a7 | Diff detecta ID de parent/jerarquía/centroide/atributos, no sólo nombre |
| 5045726af5 | Intentos separados de primeros éxitos; ETA usa mismo criterio/lectura única |
| 7dd838fa63 | Cola revalida identidad actual, URL/FK observado y errores antes de reuse |

## Regresiones/bugs demostrados y corregidos

- URLs de ficha/atributos estructurados de familias históricas parcialmente perdidos;
  recuperación compartida con controles positivos/negativos de portales/editoriales.
- Error de SQL al combinar q en mapa; ventanas inválidas no consultan red, total
  no se falsifica para coincidir con ventana alcanzable. Offset máximo sigue 200.
- Null convertido en cero/bools en counts; operaciones fuera del CHECK público.
- Campos como superficie cubierta/id_externo/provincia/pais perdidos por allowlist
  de INSERT RPC. No ampliar UPDATE geográfico sin acoplamiento probado.
- Lookup REST parcial podía confundirse con propiedad nueva; ahora falla cerrado.
- Imágenes frecuentes descartadas sin probar que eran assets; renders compartidos
  ahora sobreviven. Conflicto geográfico no elimina propiedad, evita afirmar coords.
- Temporales/snapshots podían publicar incompleto, sobreescribir concurrentemente o
  limpiar archivos ajenos; protección de ownership/publicación exclusiva/replace explícito.
- Archivos corruptos/faltantes/count mentiroso/run2 inválido podían esconderse detrás
  de run1 válido; now fail-closed. Igual timestamp conflictivo de propiedades rechazado.
- Lifecycle dejaba streak ausente en 1; ahora incrementa observaciones sucesivas.
  Métrica no activa bajas ni prueba completitud/fuente/intervalo de observación.
- GeoRef cortaba páginas cortas/silenciaba errores de dump: sólo 404 permite fallback;
  totales, duplicados, offsets y límites verificados antes de escribir recursos.
- Manifiestos antiguos calculaban hash LF antes de write_text Windows CRLF. Se
  comprobó la causa, no corrupción: lectura histórica explícita LF-normalizada;
  nuevo esquema 2/hash de bytes LF. Original no modificado.
- Backfill podía asignar huella actual a run viejo idempotente. Eliminado:
  current_code_evidence exige granular schema 5 actual y niega marcador retrospectivo;
  métricas refrescadas no cambian fecha/status/huella/payload.
- Reporte llamaba certified a primeros intentos NEEDS_FIX y publicados a enumerados.
  Primeros éxitos registrados, intentos y recertificaciones ahora separados.
- Queue absorbía error de resolve_identity como fuente=None; pending viejo podía
  tapar nueva identidad READY. Nueva frontera del runner requiere clasificación
  actual, URL observada y FK entero positivo igual. No demuestra namespace público.

## Validaciones más recientes — NO VOLVER A CORRER AHORA

Última suite completa, HEAD funcional `7dd838fa63`:

- **2633 PASS; failures=0, errors=0, skipped=0**.
- CLI reportó 157,01 s; XML testsuite registra 156,764 s.
- `_scratch/unification/backend_current_identity_validation.xml` verificado al handoff.
- 166 controles focalizados de identidad/certificación/anti-recertificación/source
  change PASS; Ruff de archivos tocados PASS. No cambio funcional después de esta suite.

Otras suites completas congeladas: 2567 evidencia de código; 2582 diff GeoRef;
2602 caudal; 2607 ventanas; 2608 lectura única, todas PASS sin skips/fallos.
**17 checks PGlite PASS** en migración SQL real, con CHECK/FK/tipos observados,
NULL/zero/security/rollback; no ejecutados contra Supabase alojado.

Frontend candidato, última validación funcional previa (sin cambios frontend
en estos últimos bloques): 1235 PASS, 9 SKIP; typecheck/lint/build PASS
(lint 0 errores, 3 warnings); build Next 16.3.5, 20 páginas; 9 smoke de integración
con API/snapshot local PASS. No afirmar que es una validación de staging/browser.
Dos launches de devserver para browser QA fueron rechazados: no esquivar rechazo
mediante otra ruta. Browser QA/Preview siguen sin prueba.

Wheel offline previo al bloque de caudal/identidad:
`_scratch/unification/wheel_georef_code_evidence/eretz_propiedades-0.1.0-py3-none-any.whl`,
1493657 bytes, SHA256 `3819e37ac118b1b6b01f91c6a71910fd7d43da766c5da4840e4b65f078edd734`.
Instalación/imports aislados de GeoRef/Geografia/diff/fingerprints/current_code_evidence
PASS. No importar clients/config (dotenv de import). **Wheel ahora anterior al HEAD**;
no presentarlo como distribución final operacional ni empaquetar bases/secretos.

## Replays, catálogo y performance comprobados

- Replay Bottega congelado: cinco HTML cacheados iguales, sin requests externos.
  Campos: histórico 0/15, pre-local 8/15, candidato 15/15. URLs: 8/9, 6/9, 9/9.
  `_scratch/unification/bottega_frozen_b7476/comparison.json`.
  Es muestra pequeña de extractores, NO recuperación global/413 fuentes.
- Datos raw: 189159 filas/1724 agencias. Snapshot API original 58427; candidato
  derivado 57665 (762 de fuentes ajenas omitidas). No equiparar al universo alojado.
- Snapshot v4 real: `_scratch/unification/snapshot_image_v4/ERETZ_API_SNAPSHOT.sqlite3`;
  25417 referencias probadas compartidas descartadas, 44891 repeticiones sin prueba
  retenidas, 231 propiedades sin foto retenidas; 3858 conflictos geográficos
  retenidos y 0 map points de conflictos. Aliases públicos verificados: **tabla vacía**.
- API: 14 casos × 5 repeticiones PASS; limit/offset/sort/moneda/bounds/partial/batch.
  recent no soportado en esta snapshot sin timestamps; no inventar recent.
  Mapa viewport-limited points + Leaflet/frontend clustering: default 2000/max 5000;
  total/returned/truncated reales. Batch max 100, sin N+1.
- Latencia local combinada ~877–1209 ms mediana; mapa ~1100–1227 ms usual;
  detail ~10 ms, batch100 ~37–41 ms. Outlier ~12,86 s, host variable.
  Copia NTFS no mejoró consistentemente: no atribuir a exFAT/imagen sin prueba.
- NULL/zero reales API: price 5313 NULL/0 zeros; rooms 23741/51; beds 23344/89;
  baths 18723/67; total 39130/0; cubierta 28941/0; coords 18838/0.
  Nueve details reales PASS; precio/superficie cero **sólo fixtures**.
- Último control vivo Benitez: 12 propiedades, dos runs idempotentes, 58 requests,
  160,6 s; schema 4/fingerprint antiguo. **STALE respecto al HEAD/schema 5 actual**,
  no refrescar su metadata para hacerlo pasar. Falta cohorte multifamilia fresca.
- Archivo histórico: lectura sólo lectura de 168 paquetes produjo 15942 identidades
  disponibles; no significa certificadas actualmente.
- Observaciones mismo log: 207 agencias/88 medibles, 201 desapariciones,
  77 reapariciones; streak antiguo 1 → nuevo 32 observaciones. No prueba bajas reales.
- Caudal replay 48 h, reloj congelado: 125 corridas/26 primeros intentos vs
  8 primeros éxitos registrados; mal etiquetado 0,54/h → 0,17/h.
  Enumerados asociados 363 → 386 por primer éxito posterior; NO publicación.
- Ventanas 6/12/24/48/168h: 0/0/0/0,17/0,31 éxitos registrados/h.
  Cinco lecturas 4,52 s → log/reloj únicos 0,789 s, misma tasa; micro-medición local.
- 2501 intentos/429 agencias/20,31 días, 5,83 intentos/agencia. 21,12 distintas/día
  NO altas verificadas/día ni ETA nacional. Mediana dos runs 215,4 s no incluye espera.

## Supabase/producción y restricciones

Supabase inspeccionado únicamente por metadata/SELECT agregado: proyecto
`pggrvzyixyjkhfknpurg` (inmolink), PG17.6.1.084. No RPC llamado, SQL/migración
aplicada, INSERT/ROLLBACK ni escritura productiva. No credentials/keys/.env leídos.

- public.propiedades PK bigint; inmobiliaria_id FK a public.inmobiliarias_main(id).
- Tipos/CHECK/nullability verificados; RPCs existentes con EXECUTE sólo postgres/
  service_role. Cuerpos/versión efectiva de RPC alojado **no demostrados**.
- Público observado 257073 propiedades, 3187 agencias con propiedades; catálogo
  distinto de snapshot 57665, no inferir pérdida/ganancia por diferencia de tamaños.
- public.inmobiliarias_main: 7004, IDs 1..7004. **0 igualdad de PK con
  scraping_id_origen y 0 con staging_id_origen**. No sustituir namespaces por números.
- Inventario alojado contiene 2 URLs Zonaprop/24 Argenprop: agregado de control,
  no autorización, no se ingirió ni limpió ese inventario.

Restricciones siguen: NO producción/Supabase writes/publicación/deploy/DNS/push/
merge remoto/reset hard/clean/restore ajeno/borrar históricos. No CRM/auth/dominio/
servicio pago nuevo ni rediseño. No consultas Brave pagas/lote. No revelar secretos,
ni leer .env. SQL sólo local desechable; versionado/deployment real requiere workflow
autorizado. No abrir privilegios públicos. No subagentes salvo autorización explícita.

## Problemas abiertos (no convertir hipótesis en hallazgos)

1. **NEXT-001: ledger de certificación**; detalle abajo.
2. Writer equivalence: REST aún usado; UPDATE geográfico requiere acoplar ciudad/
   provincia/país/coords, enrichment extras y NULL de oferta actual con razón validada.
   No broaden allowlist ni retirar REST antes de equivalencia real.
3. Identidad pública: crosswalk URL numérica pública↔hash vacío, namespace agencia
   no resuelto por igualdad. Falta lineage/crosswalk verificable, no aliases ficticios.
4. Code fingerprint schema 5 no captura versión de INPUT GeoRef efectivamente usado.
   Geografia cachea y carga provincias/localidades_censales; cambios de referencia
   pueden dejar code hash igual. Capturar input realmente usado por ambos runs.
5. GeoRef downloader valida/prefetch seis recursos, pero **no promoción multiarchivo
   atómica contra kill/disk failure**. Hardcoded D/defaults y runtime/data packaging pendientes.
6. Lifecycle: falta continuidad fuente, completitud positiva, intervalos temporales y
   proveniencia; métricas no activan bajas. Docstring vieja aún dice «nada más se necesita»:
   corregir honestamente cuando se retome, no usarla como aprobación.
7. Éxitos de certificación: refresh por antigüedad sin code/source change pendiente.
   No afirmar que existe TTL de éxito: verificado sólo diferidas NEEDS_FIX 24/72h.
8. Backfill ahora no recertifica, pero métricas faltantes todavía pueden default a cero
   en operational_metrics/network; endurecer unknown vs measured0 sin falsificar fechas.
9. Source identity/corrección: Analia JSON-LD/prosa/oficina vs propiedad; benchmark
   históricamente consistente pero geografía incorrecta no es verdad certificada.
   19 incidentes/familias mapeados; no todos revalidados con cohorte actual.
10. Revisar restantes herramientas originales semánticamente: 85 Python untracked,
    AST parse hecho, no ejecutadas/portadas en bloque. Narrow write scan no prueba seguridad.
    run_faceted_scraping duplica discovery/worker unused/pagina inventada; no portarlo
    como segundo crawler. Coverage campaigns/targeted diagnostics siguen consumidos.
11. validate_live_agency_identity.py: revisión sólo lectura detectó name_exact como
    VALIDATED aunque domain_match sea false; IDs de manifest/live sobrescritos en dict,
    unexpected rows chequeados después de escribir output. **No corregido ni
    comportamiento completo revalidado**. No confundir evidencia de nombre con namespace/
    fuente de inventario; endurecer input/ownership antes de reemplazar artefactos.
12. Soak workers/faults, cohortes actuales, performance API ~1s, browser/staging/Preview,
    real-data QA de cero precio/superficie y comparación histórica mayor pendientes.

## NEXT-001 — punto exacto interrumpido

**PENDIENTE. No hay patch ni commit de solución del ledger.** La investigación
activa seguía siendo si corrupción/igual fecha puede reutilizar un cierre viejo.

Confirmado por implementación:

- `scripts/agency_certifier.py: read_jsonl` saltea ValueError de JSON inválido y acepta
  cualquier JSON, no sólo objetos. Es compartido por lectores generales.
- `scripts/run_agency_certification_queue.py: latest_results` lee ese helper y usa
  último append por canonical_agency_id, sin ordenar/comparar checked_at.
- `scripts/backfill_strategy_fingerprints.py: latest_results` repite esa lógica.
- Consecuencia candidata a reproducir: latest NEEDS_FIX roto queda salteado y
  closure antiguo permanece seleccionado; metadata refresh atrasado puede tapar
  resultado nuevo. No está aún demostrado con test/replay controlado de producción.
- Último SELECT de archivo local (sin writes/requests): 2501 rows;
  eretz_id types 2293 int/208 None; **35 grupos agencia+checked_at repetidos**.
  No se determinó todavía si son idénticos, métricas refresh o evidencia conflictiva.
- `scripts/property_freshest.py: _leer` ya es estricto JSONL/objetos;
  `_certification_time` ya trata offsets/naive y rechaza fechas inválidas.
  Guardas de igual timestamp allí son de **propiedades**, no del ledger de agencias.
- Último código funcional fue el wrapper de identidad del commit 7dd838fa63;
  no confundirlo con solución de ledger.

**Próximo paso exacto:** leer los tres lectores anteriores y tests relacionados;
crear primero replay offline con ledger válido → fila inválida reciente, igual
instante conflictivo, offsets equivalentes y append fuera de orden. Examinar los
35 grupos existentes sólo en lectura/por agregados, sin payloads ni secretos.
Definir selección temporal/ambigüedad explícita compartida entre queue y backfill,
manteniendo refresh de métricas legítimo (no inventar nueva corrida/fecha/huella).
No elegir arbitrariamente un COMPLETE entre dos evidencias distintas. Corrupción
no debe convertirse en {} o éxito viejo; conservar agencias válidas sólo cuando
la identidad del issue es trazable. No modificar todos los callers tolerantes de
read_jsonl sin matriz de consumidores/tests. Implementar, tests focalizados,
regresión proporcional en runtime congelado, documentar y commit local. Después
continuar demás pendientes, no empezar de cero la auditoría.

## Archivos/documentos importantes

- `docs/ERETZ_UNIFICATION_EVIDENCE.md`: evidencia, controles, números y limitaciones.
- `docs/ERETZ_UNIFICATION_PLAN.md`: plan provisional beta/producción/nacional,
  matriz consumidores y blockers; no es el reporte final de la misión.
- `docs/ARCHITECTURE.md`: arquitectura candidata, scope de entrypoints conservados.
- `docs/API_V2_CONVERGENCE.md`, docs/handoff API existentes: contratos/consumers.
- `scripts/agency_certifier.py`, `agency_fingerprints.py`,
  `run_agency_certification_queue.py`, `backfill_strategy_fingerprints.py`.
- `scripts/property_freshest.py`, `property_observations.py`,
  `geo_reference.py`, `geo_snapshot.py`, `geo_snapshot_diff.py`.
- `scraper/safe_merge.py`, `clients.py`, `models.py`, `detail_urls.py`;
  `scripts/publish_to_supabase.py`, `run_daily_pipeline.py`, `run_manifest.py`.
- `migrations/property_safe_merge_audit.sql` y rollback: **iteración local**, no applied.
- Tests: `test_current_catalog_identity.py`, `test_certification_code_evidence.py`,
  `test_operacion_throughput_truth.py`, `test_geo_reference_integrity.py`,
  `test_geo_snapshot_semantic_diff.py`, `test_safe_merge.py`; fixtures/PGlite existentes.
- `_scratch/unification/`: XML/replays/snapshots/wheels; preservar fuera de Git.

## DO NOT REDO

- No volver a descubrir repos/branches/8 originales ni comparar sólo HEAD contra HEAD.
  Inventario/historia/12 heads y las integraciones locales están documentados y en Git.
- No decidir automáticamente GitHub=new base: es ancestro, evidencia por familia.
- No reimplementar URL detector/red/fuentes ni un segundo autocomplete/fidelity layer.
- No repetir benchmark Bottega ni afirmar 413 fuentes a partir de sus cinco páginas.
- No volver a atribuir los hashes GeoRef distintos a corrupción: causa CRLF probada.
- No repetir suites completas 2633/2608/2582 mientras no cambie código funcional.
- No repetir Supabase CHECK/tipos/PK↔origen: ya agregados comprobados; no llamar RPC.
- No volver a inferir publicación default score=70: default real es 0, optativo.
- No investigar nuevamente null≠zero/bool≠0 desde cero: tests/fronteras ya implementados.
- No reabrir conservación de shared renders por frecuencia: prueba de asset requerida.
- No cambiar offset>200 sin nuevo contrato/medición backend formal.
- No recertificar con backfill/upgrade de metadata: antiguo run idempotente no prueba
  código actual; último Benitez es STALE, no «actualizar» su huella.
- No confundir ausencia streak 32 con bajas aprobadas, ni dos runs con verdad del dato.
- No borrar REST/monolito/campañas como dead code: matriz prueba consumidores reales.
- No volver a dar ETA nacional con 21,12 agencias distintas/día ni contar NEEDS_FIX
  como certified; el bug de caudal y las cinco lecturas ya están corregidos.
- No intentar esquivar rechazos de browser launch ni asumir Preview/beta lista.

## CLAUDE CODE — START HERE

1. Leer este handoff y luego evidence/plan sólo en las secciones relevantes.
2. Establecer workdir `D:\INMO CAPITAL\eretz-unified`; verificar branch/HEAD/status
   con safe.directory. Esperar HEAD de handoff posterior a 7dd838fa63, no retroceder.
3. No tocar originales ni sus cambios ajenos; preservar `_scratch` y toda historia.
4. Continuar **NEXT-001**, no repetir auditoría GitHub/local completa. Ledger aún abierto.
5. No production writes, no RPC/migrations alojadas, no deploy, no DNS, no publicar.
   No push/merge salvo autorización explícita. No secretos/.env/credentials en logs/Git.
6. Tests sólo después de cambios funcionales y con runtime congelado; no suite nueva
   para este handoff de documentación. Commit local coherente con diff revisado.
7. Seguir autónomamente con tareas técnicamente desbloqueadas hasta una barrera
   real/autorización irreversible; no parar por un solo contrato bloqueado.
8. Al finalizar de verdad: comparación histórico/pre-local/unificado con límites,
   veredicto ejecutivo y plan actualizado separado backend beta/producción/nacional.
   No declarar misión completada por entregar este handoff.
