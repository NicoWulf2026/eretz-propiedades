# ERETZ — evidencia de unificación

Estado: investigación e integración local en curso, 2026-09-18. Este documento
no certifica producción ni cobertura nacional. Worktree candidato:
`D:\INMO CAPITAL\eretz-unified`, rama `codex/eretz-unified-audit`.

## Decisión de base y preservación

La base elegida es el desarrollo local moderno `d9238e64be53d27f0ca46deae74ad16eb01bb6b5`.
El remoto main observado, `15e81991c0511653bbe9efb70a92d13c1835b310`, está en su
historial: volver a él como base perdería protecciones que luego habría que
reconstruir. Se integraron F7 `ea7708f79fdc1a535d10f8f68322b5c2ce386668` y API
`806d5a5928ba4f36cf094138d68ee36615e1d006` en el candidato aislado.
Los ocho worktrees originales se conservaron, incluidos sus cambios sin commit.
No hubo push, publicación, deploy ni escrituras productivas.

Se inventariaron 12 cabezas remotas y ramas locales/históricas. Inventariar
archivos, imports y commits no demuestra equivalencia de comportamiento.
`scripts/audit_project_lineage.py` reproduce el inventario sin abrir archivos
de entorno. Las pruebas comparativas se describen por su alcance real abajo.

## Comparación reproducible

| Capacidad / muestra | Histórico | Local previo | Candidato |
|---|---:|---:|---:|
| Campos explícitos en tablas HTML, 5 fichas Bottega, 15 valores | 0/15 | 8/15 | 15/15 |
| Detección y exclusión de URL, 9 casos offline | 8/9 | 6/9 | 9/9 |
| Búsqueda combinada, medición local aproximada | sin medición comparable | 964–1034 ms | 483 ms |
| Mapa combinado amplio, medición local aproximada | sin medición comparable | 1252 ms | 780 ms |

La primera fila compara el extractor HTML histórico del commit
`9aa299bde9f7bc410b010be1387566269f551145` con el genérico moderno sobre el mismo
HTML. No compara todas las estrategias del pipeline histórico: JSON-LD u otra
estrategia podrían recuperar otros campos. Las cinco fichas conservaron precio
y moneda. La segunda fila carga funciones históricas reales; no es una
reimplementación simulada del baseline. El histórico aceptaba un salto desde
un tenant al dominio raíz del proveedor; la recuperación actual mantiene la
restricción de identidad de fuente.

Los artefactos originales del experimento histórico de 413 fuentes, 93
recuperaciones y +1040 enlaces no se encontraron en la revisión realizada.
Esas cifras siguen siendo antecedentes reportados, no un benchmark repetido.
No se afirma superioridad nacional a partir de cinco fichas y nueve fixtures.

Reproductores: `scripts/replay_unification_sample.py`,
`scripts/benchmark_unified_api.py`, `scripts/audit_unification_incidents.py`.
Artefactos locales, ignorados por Git: `_scratch/unification/bottega/comparison.json`,
`_scratch/unification/api_benchmark_covering.json`,
`_scratch/unification/incidents.json`, `initial_inventory.json` en ese directorio.

## Capacidades recuperadas y protecciones conservadas

- Detección de fichas con comillas simples, atributos de datos y onclick;
  reglas compartidas en `scraper/detail_urls.py`, con exclusiones editoriales y
  control del hostname del tenant. El consumidor Playwright reutiliza el módulo.
- JSON-LD selecciona un inmueble asociado a la URL y no combina campos de
  inmuebles relacionados. Los nodos Place sin oferta no prueban inventario.
  Alias como CABA/Capital Federal y capitales contrastan la provincia antes
  de resolver; un alias ya no evita ese control.
- Extracción de etiquetas tabulares y protección contra páginas de categoría.
- Un único modelo compartido para hashing/identidad, sin cargas desde otro
  worktree ni copias silenciosas de algoritmos.
- Propiedades incompletas y ceros reales sobreviven raw → staging. Moneda y
  operación desconocidas no se convierten en datos comerciales falsos.
- Recuperación de ambientes/dormitorios/baños del raw asociado al publicar,
  mediante una consulta por lote y vínculo de agencia/hash. No se restaura la
  geografía cruda cuando staging la retuvo por conflicto.
- TLS obligatorio, comprobación de destinos y redirects, límites de
  descompresión; un fallo de descarga no cuenta como extracción completa.
- Certificación mantiene inventario y verdad del dato como dimensiones distintas.
  Recheck/triage/promoción requieren evidencia explícitamente vigente.
- Claim de worker protegido entre procesos; un lock vencido de un PID vivo no
  se roba. Heartbeat atómico. La prueba concurrente verifica un único ganador.
- Escritura directa sin rol retirada de `ingest_to_pipeline.py`. El canary
  valida usuario permitido y sesión real antes de asumir el rol de escritura.
- Publicador histórico aún consumido: identidad que converge en varias filas
  se retiene; 409 sin recuperación confirmada es fallo, no éxito sin cambios.
  Fallbacks históricos que copiaban ciudad/país/dirección a barrio retirados.
- Gate histórico de regresión recuperado por propósito, no por implementación:
  `python -m scripts.regression_gate` compara JSONL fila a fila, conserva IDs de
  query y no usa cobertura agregada para justificar pérdidas. Identidad ambigua,
  inventario no observado y mudanzas de dimensión requieren revisión. No autoriza
  publicación ni restauración automática. Diez controles offline cubren esa familia.
- Canary consume `CANONICAL_AGENCY_TO_ERETZ_ID.jsonl` con estado RESOLVED,
  corrobora ID/nombre contra main y rechaza duplicados. IDs de staging ya no
  pueden convertirse en FK de propiedades por coincidir numéricamente.
- Fusión de lecturas v3: ausencia comercial/editorial explícita gana al dato
  histórico; precio y moneda viajan juntos. Los faltantes estructurales sin
  rechazo siguen pudiendo recuperar evidencia anterior. Cuatro controles nuevos
  prueban que precio desconocido no revive una oferta ni toma moneda antigua.
- Reconstrucción del snapshot en archivo temporal: una falla no trunca el
  snapshot servido y no se permite usar la fuente como destino.
- Búsqueda técnica estable dentro de la ventana: offset máximo 200 conservado.
  El ranking ya no cambia su universo de candidatos al pasar de página.
- Dependencias frontend actualizadas y puente de operador desactivado por
  defecto, autenticado, local y limitado. Roomix y mobile conservados.

## Datos y contratos reales

El snapshot fuente revisado tiene 58.427 propiedades. El derivado local conserva
57.665 tras retener 762 registros asociados a webs ajenas. Se retiraron 48.594
referencias a imágenes repetidas según la regla existente; 433 propiedades
quedaron sin fotos y continuaron en el catálogo. La frecuencia de una imagen
es una heurística, no prueba individual de que sea un logo.

Se observaron 3.859 conflictos geográficos en la entrada; uno corresponde a
inventario retenido. No se convirtieron municipios en localidades. La cobertura
de localidad demostrada es mucho menor que la cobertura de un área de búsqueda:
9.612 localidades frente a 54.076 áreas en la muestra de entrada. No confundirlas.

El snapshot derivado inspeccionado no contiene URLs de inventario de Zonaprop
ni Argenprop. La política debe seguir operando también en nuevas ingestas.

API real local: búsqueda combinada, filtros, orden por precio, detalle por hash,
agencia, batch, mapa limitado por viewport y discovery pasaron nueve pruebas de
integración frontend. La tabla de alias legacy del snapshot está vacía: el
bridge de IDs numéricos públicos no está demostrado con datos históricos.
`recent` requiere datos temporales que el contrato actual no ofrece.

Mediciones locales sobre snapshot derivado (cinco repeticiones por caso):
detalle ~9 ms, agencia ~9 ms, batch de 100 ~22 ms; mapa pequeño ~224 ms.
No son latencias de Internet, de staging ni un SLO productivo.

## Incidentes y capacidad operativa

Se localizaron 2.501 intentos sobre 429 agencias en 20,31 días de artefactos:
5,83 intentos por agencia y 21,12 agencias distintas/día. Esto incluye STOP,
reintentos y trabajo humano; no permite calcular una fecha nacional fiable.
Mediana de dos corridas: 215,4 segundos entre registros con esa medición.

Los 19 controles solicitados se mapearon en `incidents.json` a familias y
evidencia disponible. No todos fueron repetidos en vivo. Dos controles nuevos:
Benítez Ullo enumeró 12 propiedades consistentemente; Andrade falló discovery
con URLError y quedó NEEDS_FIX. Ninguno de esos resultados demuestra por sí
solo corrección de geografía o de todos los campos. Además son anteriores a
los últimos cambios de fingerprint: no constituyen certificación fresca para
publicación del HEAD final.

## Validación registrada y límites pendientes

- Suite backend tras JSON-LD/identidad/geografía y gate por fila:
  2.250 PASS, 157,19 s. La primera pasada detectó una oferta JSON-LD anidada
  compitiendo con su Product; se corrigió y se repitió la suite completa.
- Frontend: 1.235 PASS, 9 SKIPPED; typecheck PASS; lint 0 errores, 3 warnings.
- Integración frontend contra API local: 9 PASS.
- Canary de identidad/fusión comercial/snapshot/gate por fila: 71 PASS.
  Falta registrar la suite completa después de estas últimas modificaciones.
- Ruff de los módulos nuevos/tocados salvo scraper_propiedades: PASS. Ese
  archivo histórico tiene 16 hallazgos de lint fuera del bloque modificado;
  no se declara lint global limpio ni se reformatea por estética.
- Wheel construido e importado desde un entorno aislado fuera del checkout.
- Postgres local en memoria (PGlite): 10 comprobaciones PASS con las migraciones
  SQL reales. Incluyen aplicación repetida del schema interno y safe merge,
  join de staging por identidad, null/zero, rechazo entre agencias, rollback
  conjunto de actualización y auditoría, auditoría inválida, privilegios públicos
  y revocación sin borrar evidencia. `node scripts/verify_local_postgres.mjs`;
  instalar el runtime opcional únicamente en `_scratch/unification/postgres-check`.
  [Documentación del motor local](https://pglite.dev/docs/). Usa filas sintéticas
  y no demuestra comportamiento de Supabase alojado ni concurrencia productiva.
- Datos reales: 51 ceros en ambientes, 89 en dormitorios y 67 en baños. Se
  comprobaron ejemplos por endpoint de detalle, además de null en seis campos.
  No hay muestras reales de precio cero ni superficie cero en este derivado;
  esos casos permanecen cubiertos por fixtures. Coordenadas cero: ninguna.
- Production build repetido y confirmado: PASS, exit 0, 20 páginas generadas;
  compilación 22,6 s. La sesión anterior se perdió y no se usó como prueba.
- Browser QA del candidato pendiente: el control automático rechazó dos
  intentos de iniciar Next. No se evitó esa restricción mediante otra vía.

Pendientes de revisión/validación: caminos de publicación y gates de evidencia
de extremo a extremo, equivalencia de entrypoints históricos aún consumidos,
scripts operativos sin seguimiento en el principal, contradicciones entre la
geografía de JSON-LD y la prosa de la ficha, browser
QA y puente histórico de IDs. No declarar beta ni producción listas todavía.

La arquitectura candidata concentra conectores, identidad, detección de URLs,
contrato de propiedad y validación; conserva entrypoints históricos donde aún
hay consumidores. Su eliminación requiere una matriz de consumidores y
equivalencia verificada. Mantenerlos temporalmente no es el resultado final
de simplificación solicitado.
