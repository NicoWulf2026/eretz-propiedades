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

El contrato de propiedad v5 conserva el conflicto entre localidad explícita y
provincia como evidencia por fila; anula las dimensiones disputadas sin eliminar
la propiedad. Una cobertura geográfica anterior y el padrón de la agencia no
pueden revivir esos datos. Un nombre de barrio homónimo no basta para declarar
ese conflicto. Esto no demuestra aún detección universal de contradicciones
entre JSON-LD y prosa. Snapshot v3 recalcula scopes tras la fusión comercial y
respeta las restricciones del gate: un precio/operación vuelto desconocido no
mantiene scopes antiguos de filtros.

La primera suite de este bloque dio 2.269 PASS y una expectativa obsoleta de
versión (v4 frente a v5); se actualizó la expectativa, no las reglas del contrato.
La repetición completa posterior dio 2.270 PASS en 162,57 s antes de los nuevos
controles de discovery e imágenes.

Revisión de imágenes: el detector histórico ya distinguía repetición sospechosa
de exclusión, pero rollout y snapshot contradecían esa política con umbrales
automáticos. Se concentra ese detector en image_quality y el scraper histórico
lo reexporta por compatibilidad. Frecuencia sin otra señal conserva la imagen
y produce evidencia de revisión; renders de doce unidades y fotografías
exportadas por WhatsApp tienen controles negativos. Assets conocidos siguen
excluidos y las propiedades sin foto sobreviven. Fingerprint esquema 4 incluye
esta dependencia semántica compartida; no se convalidan paquetes viejos.

Discovery: los canarios V1/V2 son controles A/B históricos, no dos pipelines
productivos. Se elimina su carga de secretos al importar y la búsqueda de `.env`
en otro worktree. El CLI carga únicamente entorno propio explícitamente y el
dry-run no necesita credencial. Tres entrypoints comparten límites de respuesta
y validación de destinos/redirects; proveedor interrumpido termina PARTIAL con
exit 2. Veintiún controles offline PASS; cero consultas pagas ejecutadas. El
consumidor brave_250 carga su entorno explícitamente al ejecutar, no al importar;
cuenta procesadas reales y devuelve PARTIAL si faltan seleccionadas.

El preflight ya no trata cualquier esquema anterior como esquema 1: el helper
histórico depende del inventario actual de componentes y no reconstruye cada
esquema anterior exactamente. Un cambio de esquema no vence por sí solo un
defecto abierto; exige revalidación controlada. Veintiocho controles de
fingerprint/preflight PASS. Los fallos externos de radio acotado mantienen el
triage independiente. Preparación de índices/alias atómica y sin reemplazo
implícito: dos controles PASS.

Suite backend completa antes del último ajuste de preflight: 2.294 PASS,
184,03 s; repetir después del ajuste. No son 2.294 pruebas reales de sitios.

La siguiente suite dio 2.302 PASS en 180,58 s, antes de las correcciones del
cliente de merge y su nuevo control de rendimiento. Lookup de identidad ahora
rechaza respuestas malformadas o cortadas en el límite, en vez de asumir que no
hay coincidencias y permitir insertar. Los errores de ese lookup/RPC no hacen
eco del body o excepción crudos; un booleano no cuenta como filas auditadas.
Su import interno funciona como paquete instalado, no depende de `models`
top-level. Noventa y dos controles offline del bloque de escritura PASS.

Microbenchmark local sobre una URL sintética, 10.000 llamadas a
`is_known_page_asset`: 9,211 s antes y 1,040 s después de precalcular los
marcadores constantes. No demuestra ese factor de mejora en API/pipeline.
Control que cuenta normalizaciones y 43 controles de imágenes PASS. El primer
build v4 arrancó antes de esa optimización; no usar su duración como build
optimizado ni convertir un ajuste de CPU en una certificación de datos.

Control vivo nuevo con fingerprint esquema 4: Benítez Ullo, 12 propiedades,
dos corridas idempotentes, 58 requests, 156,8 s, sin reintentos ni errores de red.
Dos propiedades sin imágenes y todas sin coordenadas permanecen en inventario.
Su geografía/fuentes de cada campo no se dan por verdaderas sólo por ese cierre.
La optimización posterior cambia la huella; está en marcha otro control vivo
en carpeta nueva, no se actualiza a mano el certificado anterior.

`apply_page_image_filter` comparte ahora la política de assets y no excluye
renders sólo por repetir. Inputs/copia/informe deben ser distintos y nuevos;
JSON inválido o fingerprint que no puede recalcularse son fallos, no filas
omitidas ni certificados silenciosamente preservados. Cinco controles PASS.
Esta herramienta de copia no recertifica una agencia.

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

Validación adicional del 18 de septiembre (no certificación final):

- Suite backend anterior al cambio numérico: 2310 PASS, 186,431 s, sin skips
  ni errores, confirmada en el XML de pytest.
- Frontera numérica normalizada: 49 pruebas focalizadas PASS. No convertir
  booleanos o fracciones en cantidades enteras; preservar superficie decimal
  y cero válido. Safe merge no toma la moneda histórica para un importe nuevo.
  Esto no cambia las reglas de extractores que identifican cero como placeholder
  ni elimina la incertidumbre comercial de registros históricos.
- Snapshot v4 derivado: 57.665 propiedades, 762 omitidas por web ajena;
  25.417 referencias a assets compartidos descartadas y 44.891 referencias
  repetidas sin evidencia suficiente para descartarlas conservadas para revisión.
  231 fichas quedaron sin foto propia, sin eliminar la propiedad. El inventario
  coincide con el derivado anterior; la política de imágenes es menos destructiva.
- Segundo canario Benítez Ullo: 12 propiedades, 58 requests, 152,9 s, dos
  corridas idempotentes y sin errores de red. Ocurrió antes del cambio numérico;
  no demuestra certificación vigente del código final ni verdad de cada campo.
- La suite numérica completa encontró una regresión de rango de superficie
  (2323 PASS, 1 FAIL). Se corrigió preservando el límite de almacenamiento
  anterior junto con decimales, y 154 pruebas focalizadas posteriores pasan.
  No se usa esa corrida fallida como validación final verde.
- Preparar índices falló en el volumen exFAT por falta de hard links. La
  publicación exclusiva en Windows usa rename, manteniendo el rechazo de
  destinos existentes incluso si otro proceso los crea después del preflight;
  tres pruebas PASS y preparación del snapshot real repetida exitosamente.
  [Semántica de rename en Python](https://docs.python.org/3/library/os.html#os.rename).
- Lectura de propiedades certificadas: JSONL corrupto o filas no objeto
  producen error sin mostrar payload, en lugar de perder filas silenciosamente
  bajo un estado COMPLETE; 17 pruebas de frescura PASS. Vigencia de huellas y
  resolución de empates entre paquetes siguen pendientes de revisión.

Controles posteriores (validación global pendiente, HEAD funcional congelado):

- Empates con fecha idéntica y valores distintos ya producen error explícito,
  no elección dependiente del filesystem; 19 pruebas de frescura PASS.
  La comparación de zonas horarias y la vigencia de huellas siguen pendientes.
- Clasificador y scraper comparten también la normalización de URLs histórica;
  56 pruebas de imágenes PASS, incluyendo wrappers y enlaces protocol-relative.
- Diagnóstico entre agencias v2: repetición produce REVIEW_REQUIRED, no prueba
  de contaminación. Sólo un asset conocido tiene safe_to_exclude; siete pruebas
  PASS. Las métricas históricas de ese diagnóstico no validan un umbral de borrado.
- Catorce casos de API real PASS en dos mediciones locales de cinco requests por
  caso. Segunda mediana: Explorer 317,75 ms, combinado 877,35 ms, mapa amplio
  1150,39 ms, detalle 10,8 ms, batch de cien 37,41 ms. Había pruebas concurrentes;
  no equivalen a latencia remota, producción ni comparación aislada de rendimiento.
  3858 conflictos geográficos conservados, cero puntos conflictivos en el mapa.
- Una corrida global se invalidó por cambios de código durante su ejecución:
  imports mezclaron el helper nuevo con un módulo anterior ya cargado. Sus
  2318 PASS, ocho fallos y cuatro errores no acreditan validación global verde.
  Se repite desde un proceso nuevo con código funcional congelado.

Suite congelada posterior: **2336 PASS, cero fallos/errores/skips, 228,95 s**,
confirmada por pytest y XML `backend_frozen_validation.xml`. Los trece controles
de publicación histórica y configuración de timeout también pasan en proceso
nuevo. Esto acredita la suite backend actual, no la finalización de toda la
misión ni certificación del long tail. Código funcional `b018b86398` y documentación
posterior sin cambios semánticos.

Comprobación viva posterior a la normalización compartida: Benítez Ullo,
CERTIFIED_COMPLETE, 12 propiedades, dos corridas idempotentes, 58 requests,
160,6 s, cero retries/errores de red; estrategia generic/html_catalog,
huella `8a3057c78ab0`, schema 4. Alcance: una fuente oficial, no toda la cohorte
ni verdad de su geografía. Los builders del snapshot no forman parte de esa
huella de extracción.

Performance posterior: el mismo código sobre el derivado anterior también
presentó dispersión (combinado 921,36 ms de mediana, outlier del mapa pequeño
12,86 s). Una copia del mismo snapshot v4 en NTFS no mejoró consistentemente
las latencias; por tanto no se confirma una causa puramente exFAT ni una
regresión atribuible sólo a imágenes. Conservar estos resultados como límites
de la medición local; falta comparación controlada y diagnóstico del caso
combinado cercano a un segundo antes de declarar rendimiento launch-ready.

El builder principal también respeta publicación exclusiva si no se pide
--replace-derived: rechaza un destino creado durante la construcción. El modo
de reemplazo explícito permanece disponible; 14 controles de snapshot PASS.

Suite posterior al builder exclusivo: 2338 PASS, sin fallos/errores/skips,
388,19 s. Replay offline del HEAD funcional repetido con las cinco capturas:
0/15 histórico, 8/15 local previo, 15/15 candidato; URLs 8/9, 6/9, 9/9,
respectivamente. No hubo requests externos en ese replay ni escrituras de DB.

Familia de evidencia de campos (`658ac32eaa`): no detectar una señal no prueba
ausencia de fuente. El auditor conserva source_not_provided por compatibilidad,
pero no inventa pruebas negativas: registra source_unknown y SOURCE_UNKNOWN.
EXTRACTED continúa significando presencia normalizada, no corrección del dato.
Una galería normalizada vacía tampoco demuestra ausencia de fotos en la fuente.
Rechazos registrados sobreviven aunque falte señal del detector, y el mapper
por ficha no convierte presencia agregada de agencia en ausencia demostrada en
una fila. Cero permanece presente; booleanos no cuentan como campos numéricos.
134 controles focalizados PASS, lint de los archivos tocados PASS; suite global
posterior 2349 PASS, sin fallos/errores/skips, 235,52 s (XML
backend_source_evidence_validation.xml). Cambia la huella del certificador: el canario anterior
no se actualiza artificialmente ni acredita vigencia de este nuevo HEAD.

La arquitectura candidata concentra conectores, identidad, detección de URLs,
contrato de propiedad y validación; conserva entrypoints históricos donde aún
hay consumidores. Su eliminación requiere una matriz de consumidores y
equivalencia verificada. Mantenerlos temporalmente no es el resultado final
de simplificación solicitado.

Verificación de Supabase en esta continuación: sólo SELECT de metadatos sobre
columnas, constraints y ACLs; ninguna llamada al RPC, lectura de secretos,
INSERT, rollback productivo ni publicación. La FK de propiedades referencia
inmobiliarias_main. El CHECK real acepta operación NULL o venta, alquiler,
alquiler_temporario, consultar y venta_y_alquiler; no acepta desconocida ni
proyecto. Los RPC observados existen y tienen EXECUTE para postgres/service_role,
no PUBLIC/anon/authenticated. Esto no certifica sus cuerpos ni su deployment.

Regresión de frontera comprobada: el fallback local desconocida podía rechazar
una propiedad real incompleta al insertar en el contrato público. El modelo,
safe_merge, staging_to_prop y sanitizador REST ahora comparten un serializador:
desconocida/proyecto/no reconocido -> NULL público, conservando la evidencia
original en dominio/staging; nunca venta ni consultar inventadas. Un estado
desconocido tampoco se promueve como mejora de operación en una actualización.
El fixture PGlite incluye los CHECK observados y la FK main, antes ausentes:
rechaza desconocida y agencia inexistente; conserva INSERT con operación NULL,
precio/ambientes cero y auditoría atómica. Once comprobaciones SQL PASS; ninguna
conexión productiva. Falta cerrar la equivalencia de campos y semántica de
actualizaciones antes de retirar el publicador REST todavía consumido.

Suite congelada posterior al serializador de almacenamiento (`cc5654b714`):
2374 PASS, sin fallos/errores/skips, 248,94 s; XML
backend_storage_operation_validation.xml. Wheel construido sin descargar
dependencias e instalado en carpeta aislada: serializador, superficies
fraccionarias, safe_merge y normalización de URL de imagen PASS, sin importar
bootstrap/.env ni conectar a red/DB.

Metadatos y agregados productivos de sólo lectura: 7004 agencias main, 7004
orígenes scraping distintos y 138 orígenes staging distintos. La presencia
de una columna de origen no establece por sí sola una correspondencia con
canonical_agency_id del snapshot. Public.propiedades tiene 257073 filas,
256290 activas y 3187 agencias; todos los hashes observados son de 32 caracteres
hexadecimales. No es el universo de 57665 filas del derivado local y no se
presenta esa diferencia como mejora/regresión ni cobertura certificada.
El agregado de URLs publicadas encontró 2 URLs host Zonaprop y 24 Argenprop;
su existencia histórica no autoriza ingestión: no se consultaron esos sitios,
no se borró ni modificó ninguna fila. Requiere revisión de lineage/scope antes
de cualquier saneamiento productivo autorizado. La regla de fuentes prohibidas
se mantiene en la arquitectura candidata.

Consulta de identidad REST aún consumida: un HTTP fallido o excepción cortaba
el loop y devolvía un índice parcial, permitiendo tratar registros existentes
como nuevos. Ahora falla antes de POST/PATCH y contabiliza el fallo; no imprime
body ni texto de excepciones. Solicita count=exact, valida Content-Range,
acepta 206 y avanza por filas efectivamente recibidas: una página corta por
límite del servidor no implica fin. Total cambiante, rango incompleto, fila
malformada, agencia ajena y IDs repetidos/desordenados bloquean la escritura.
No equivale a lectura transaccional: cambios de contenido con igual total
todavía requieren el escritor atómico. 107 controles focalizados PASS, red
bloqueada y bootstrap/.env excluido por AST. El código AST se compila una vez
y se ejecuta en namespace nuevo por test; evita repetir el coste observado de
parsear el monolito sin compartir instancias/estado entre casos.
[Contrato de paginación PostgREST](https://docs.postgrest.org/en/stable/references/api/pagination_count.html).

Equivalencia de superficie cubierta: el escritor atómico candidato omitía la
columna real superficie_cubierta del SELECT de existentes, allowlist INSERT,
INSERT SQL, campos de merge y UPDATE SQL. La conserva ahora, nullable y numeric,
con la política conservadora existente: llenar ausencia válida, no sustituir
un valor estructural conocido sin evidencia suficiente. El sanitizador INSERT
comparte los límites numéricos del modelo para ambas superficies y rechaza
booleanos/fracciones de conteos sin descartar la propiedad. Trece controles
PGlite PASS, incluidos INSERT NULL/0/90,75, UPDATE desde NULL y rollback de
campo/auditoría; privilegios y rechazo de patch NULL permanecen intactos.
El SQL es una iteración local del script idempotente del candidato: no fue
aplicado en Supabase ni acredita vigencia del RPC alojado. Un futuro despliegue
requiere generar/verificar su migración versionada en el workflow real antes
de habilitar escrituras. Provincia/pais y la invalidación validada de datos
históricos siguen impidiendo retirar ciegamente el publicador REST.

Builder de snapshot: cierra ambas conexiones y retira sólo el temporal creado
exclusivamente por esta construcción ante excepciones, incluida la apertura
fallida del origen readonly. No elimina un temporal ajeno preexistente ni toca
el origen o snapshot servido; publicación sigue exigiendo reemplazo explícito.
17 controles de snapshot PASS. Un kill del proceso puede dejar su temporal:
no se usa limpieza global ni se supone que finally corre después de SIGKILL.
La cabecera ya no afirma indisponibilidad productiva ni una cantidad constante
de propiedades: el alcance se informa en el resumen real de cada derivación.

Cronología del refresco (`property_freshest_v4`): interpreta checked_at como
datetime, compara offsets explícitos en UTC y detecta conflictos de la misma
ficha en el mismo instante aunque el texto use otra zona. Mezclar fechas sin
zona con fechas zonificadas para la misma identidad es un error, no asignación
ficticia de UTC/Argentina. Certificado sin tiempo válido o JSON corrupto no
desaparece silenciosamente ni puede ganar como "más nuevo". La fecha no acredita
fingerprint actual ni verdad del dato: esa verificación sigue pendiente en la
frontera de consumo de paquetes archivados y no se declara este punto cerrado.
64 controles de refresco/snapshot/gate/diagnóstico de imágenes PASS; lint de
los archivos tocados PASS.

Suite congelada después de consulta REST, superficie cubierta, cleanup del
builder y cronología (`ad8215dcf8`): 2437 PASS, 0 fallos, 0 errores, 0 skipped,
233,444 s. Confirmado en backend_publication_snapshot_validation.xml, terminado
2026-09-18 10:12:48 local. Los ocho worktrees originales conservan los HEADs
previamente inventariados; candidato limpio antes de esta actualización documental.

Integridad de paquetes (`property_freshest_v5`, auditoría en curso): el consumidor
rechaza certificados sin ningún archivo de propiedades, corridas declaradas
ausentes, metadata de corrida malformada, conteos declarados distintos a las
filas, hashes vacíos/no textuales y duplicados dentro de una corrida. Valida
también run2 si existe aunque run1 tenga datos: un segundo archivo corrupto no
queda oculto por el fallback. Un archivo existente vacío sigue representando
cero observaciones; archivos ausentes no. Archivos históricos con una única
corrida no declarada se conservan como lecturas históricas, no como prueba de
dos corridas actuales ni verdad del dato. Preferencia histórica run1/run2 sin
cambios. 62 controles focalizados PASS; lint PASS.

Revisión agregada readonly del archivo original de certificaciones: 168 paquetes
con status CERTIFIED_COMPLETE/CERTIFIED_BEST_AVAILABLE, cero paquetes sin archivos,
cero corridas declaradas ausentes y cero diferencias de detalles_obtenidos contra
conteo de líneas no vacías. Este chequeo de conteo no valida semánticamente cada
fila ni acredita fingerprint vigente, identidad actual o calidad geográfica.
No se modificó el archivo original ni se imprimieron filas de propiedades.

Suite backend congelada con esta integridad de archivos: 2455 PASS, 0 fallos,
0 errores, 0 skipped, 181,58 s; backend_archive_integrity_validation.xml.

Ciclo de vida/registro (`property_observations_v2`, no activado): observación OK
con paginación interrumpida, presupuesto agotado o enumeración explícitamente
incompleta no registra ausencias. Reutiliza la validación de paquetes; archivos
corruptos/ausentes o conteos contradictorios fallan antes de append. Agencia y
fecha deben existir: no se fabrica una observación de "hoy". El lector del log
append-only rechaza corrupción y conteos/identidades inválidas; ordena instantes
con offsets explícitos sin inventar zona, deduplica la misma evidencia temporal
y rechaza conflictos en el mismo instante. Ausencia continuada incrementa el
contador en cada observación, no sólo al desaparecer; reaparecer lo reinicia.
88 controles focalizados PASS y lint PASS. CLI directa y de módulo preservadas.
La métrica de desapariciones ya no afirma autorización para activar lifecycle;
esa salida queda false, separada de datos_para_medir_reapariciones. No hubo bajas
ni escrituras en bases. OK histórico sin prueba positiva de completitud, cambios
de fuente y vigencia de fingerprint siguen requiriendo validación: este bloque
no demuestra por sí solo que toda ausencia archivada sea ausencia real.

Replay readonly del MISMO registro histórico, con funciones anteriores aisladas
por AST (`a4840295d7`) contra el consumidor candidato: ambos cuentan 207 agencias,
88 medibles, 201 desapariciones y 77 reapariciones (38,3%). El contador máximo al
final pasa de 1 a 32 observaciones: antes no incrementaba una ausencia continuada.
Esto corrige una métrica, NO prueba 32 ausencias reales independientes: vigencia,
completitud positiva, separación temporal y continuidad de fuente deben ser
verificadas antes de convertir el registro en bajas. No hubo mutación de log,
registro de nuevas observaciones ni escrituras en bases durante este replay.

Regresión completa congelada del registro/lifecycle: 2481 PASS, 0 fallos,
0 errores, 0 skipped, 156,20 s; backend_lifecycle_integrity_validation.xml.

Equivalencia de INSERT público, siguiente bloque local: metadatos readonly de
Supabase confirman id_externo/provincia/pais nullable text. El RPC candidato los
conserva si se entregan; omisión/NULL no fabrica localidad, país ni identificador.
INSERT rechaza JSON no textual en esos campos; la preparación normalizada mantiene
la propiedad y convierte evidencia opcional de tipo inválido en NULL. UPDATE no
permite modificar id_externo ni agregar provincia/pais de manera independiente:
falta la política geográfica acoplada, no se finge cerrada. Continúan prohibidas
claves arbitrarias, escrituras públicas de anon/authenticated y degradación NULL.
114 controles Python focalizados y 17 controles PGlite PASS, incluida reversión
de fila/auditoría y validación de campos nuevos. No conexión ni migración alojada.
La guía de Supabase/PostgreSQL se usó para mantener límites de privilegios y
transacciones; no para abrir permisos ni ejecutar publicaciones productivas.
Referencia de seguridad: [funciones de base](https://supabase.com/docs/guides/database/functions).

Este cambio es iteración del SQL local existente, no prueba del cuerpo del RPC
productivo ni migración desplegada. Antes de un despliegue autorizado se debe
generar/verificar la migración versionada en el workflow real. El escritor REST
todavía tiene consumidores: faltan equivalencia del payload enriquecido completo,
actualización geográfica coherente e invalidaciones justificadas de datos viejos.

Suite completa congelada de INSERT identidad/geografía: 2494 PASS, 0 fallos,
0 errores, 0 skipped, 155,87 s; backend_identity_geo_insert_validation.xml.
Wheel construido offline sin dependencias e instalado en directorio aislado:
fronteras puras fuera del checkout PASS (operación desconocida, superficie cero,
identidad/geografía nullable y ausencias continuadas). No prueba staging completo,
recursos GeoRef empaquetados, CLI operacional ni permisos del RPC alojado.

GeoRef, integridad de descarga (nuevo bloque en validación): sólo el 404 de un
volcado ausente permite fallback a API. Respuesta malformada/incompleta, total
desconocido/cambiante, offsets incompatibles, IDs inválidos/duplicados, paginación
interrumpida y ventana API insuficiente no se convierten en snapshot completo.
Se terminan/validan los seis recursos antes de escribir el destino: un fallo de
descarga tardío conserva la referencia anterior. 63 controles de descarga y
resolución geográfica PASS, lint PASS. No se ejecutó descarga real ni se alteró
el directorio GeoRef original. Referencia: [GeoRef oficial](https://datosgobar.github.io/georef-ar-api/).
El límite local de volumen es protección operativa, no afirmación de un límite
oficial del universo. Promoción multiarchivo frente a fallo de disco/kill sigue
pendiente: prefetched downloads no equivalen a una transacción de publicación.

Chequeo readonly de la referencia original (2026-09-02): 24 provincias, 529
departamentos, 2082 municipios, 4023 localidades censales, 4028 localidades y
14466 asentamientos; conteos iguales al manifiesto, cero IDs repetidos/no textuales.
Los seis hashes físicos difieren; los seis hashes con CRLF→LF coinciden. Causa
demostrada de formato: el generador hashea texto LF antes de write_text, que usa
conversión de newline en Windows. No se etiqueta esta discrepancia como corrupción
semántica ni se "repara" el original. Falta formalizar hash de bytes vs texto y
proveniencia de la referencia en certificados; un fingerprint de código solo no
demuestra que dos corridas usaron el mismo snapshot geográfico.

Suite completa congelada de integridad de descarga GeoRef: 2519 PASS, 0 fallos,
0 errores, 0 skipped, 152,65 s; backend_georef_download_integrity_validation.xml.
Consumidor de paquetes v5 sobre el archivo original readonly: 15942 identidades
con lectura histórica disponible, sin error de integridad, database_writes=0.
No se declara ese número inventario vigente/certificación actual; la misma
limitación de fingerprint/procedencia sigue abierta.

GeoRef diff/manifiesto, siguiente bloque en validación: geo_reference centraliza
IDs y verificación de recurso contra manifiesto. Archivos/manifiesto ausentes,
totales/conteos no exactos, flags de completitud no booleanos, checksum incorrecto,
IDs duplicados y esquema/scope desconocidos son errores, no diccionarios vacíos.
El escritor nuevo guarda bytes UTF-8 LF y declara schema_version=2,
sha256_scope=file_bytes_utf8_lf. El histórico sin schema explícito admite sólo
la semántica demostrada de hash de texto con newlines normalizados; no adivina
semánticas de versiones desconocidas. El diff no autoriza reemplazos: informe
replacement_authorized=false y mensaje diagnóstico aun cuando no hay cambios.
84 controles focalizados PASS, lint PASS; CLI directa y de módulo preservadas.
Autodiff readonly de los seis recursos originales pasa sus conteos/hashes y
reporta cero cambios; único artefacto nuevo es el informe local en _scratch.
Esta verificación prueba integridad de referencia, no exactitud de cada ubicación,
equivalencia de geometrías ni una promoción multiarchivo atómica.

Suite completa congelada de diff/manifiesto GeoRef: 2540 PASS, 0 fallos,
0 errores, 0 skipped, 148,81 s; backend_georef_manifest_integrity_validation.xml.

Namespaces de agencia, agregado alojado readonly: 7004 agencias, ID público
min=1/max=7004; cero filas con id=scraping_id_origen y cero con id=staging_id_origen;
scraping_id_origen está presente en todas. Esto no demuestra por sí mismo cuál
namespace usa cada artefacto local, pero descarta sustituir IDs de origen por PK
pública suponiendo igualdad numérica. Bridge de propiedad/agency FK requiere
crosswalk de procedencia verificable, sin IDs ficticios ni consultas a secretos.

Consumidor geográfico y promoción de evidencia, bloque en validación: Geografia
reutiliza verified_rows, por lo que JSON presente sin manifiesto/count/hash válido
no entra silenciosamente al normalizador. Fingerprint schema=5 incluye el helper
geo_reference; futuros cambios de esa frontera no quedan fuera de la huella.
Resultados schema 4 anteriores no se marcan retrospectivamente como schema 5.

Regresión moderna demostrada por control: backfill_strategy_fingerprints podía
asignar strategy_fingerprint del HEAD actual a cierres antiguos idempotentes y
--refresh-safe podía sustituir una huella vencida por la actual sin recertificar.
Esto probaba consistencia antigua, no código ejecutado ni verdad del dato.
Se elimina esa promoción: migrate_result exige evidencia de código granular ya
registrada/currente y conserva huella/schema/fecha/status/payload; sólo refresca
métricas. Los marcados fingerprint_backfilled_from_terminal_evidence no prueban
código actual, incluso si su huella coincide. Queue no da éxito vigente por hash
whole-connector antiguo, metadata de versión ausente/malformada, mecanismo/estrategia
contradictorios ni estrategia desconocida. current_code_evidence se comparte entre
queue y tooling; no es prueba de identidad ni proveniencia de datos GeoRef.
230 controles focalizados PASS y lint PASS, CLI backfill --help sin ejecutar
mutaciones. No se corrió el backfill sobre archivos originales. Defectos NEEDS_FIX
sin huella/esquema antiguo siguen abiertos según preflight: no amnistía por versión.
Paquetes históricos siguen legibles como lecturas, no certificaciones actuales.

Suite completa congelada de consumidor geográfico/promoción de evidencia:
2567 PASS, 0 fallos, 0 errores, 0 skipped, 149,28 s;
backend_certification_evidence_validation.xml. Mínimo de score de publicación
verificado en run_daily_pipeline/build_publish_queue/publish_to_supabase: default
0 (optativo). Penalizaciones de completitud no excluyen por ese umbral en default;
no se declara una regresión de publicación inferida de un supuesto default 70.

Diagnóstico semántico GeoRef: el comparador anterior sólo miraba el nombre de
provincia, por lo que un cambio de ID manteniendo ese nombre quedaba invisible.
Ahora compara contexto completo de provincia/departamento/municipio/localidades
y cualquier otro atributo cambiado, incluidos centroides/geometría. Conserva
los campos históricos del reporte, agrega detalles y devuelve revisión ante
renombres o cambios semánticos; contextos no objeto/null fallan explícitamente.
No reemplaza ni autoriza una referencia. 75 controles focalizados PASS/lint PASS;
suite completa congelada: 2582 PASS, 0 fallos/errores/skipped, 175,75 s,
backend_georef_semantic_diff_validation.xml. Autocomparación de la referencia
original ERETZ_GEO en seis recursos: sin cambios; ningún archivo original escrito.

Wheel reconstruido offline sin resolver dependencias: 1493657 bytes,
SHA256 3819e37ac118b1b6b01f91c6a71910fd7d43da766c5da4840e4b65f078edd734.
Instalación aislada e imports/lectura verificada GeoRef/normalizador/comparador
PASS. No se importaron clients/config ni se leyeron archivos .env. Esto prueba
distribución del helper y código, no una instalación operacional completa ni
proveniencia geográfica registrada por una certificación actual.

Caudal operativo, bloque en validación: rendimiento etiquetaba como certified
toda agencia vista por primera vez, incluso NEEDS_FIX, y llamaba publicados a
conteos enumerados. Se separan intentos nuevos/primeros cierres exitosos registrados,
sin contar BLOCKED_EXTERNAL como certificado. Un primer éxito tras un intento viejo
sí cuenta; recertificaciones no vuelven a sumar inventario. Orden temporal explícito
y offsets respetados; historial ilegible/fecha futura bloquea ETA. Contadores y
duraciones desconocidos se señalan, no se presentan como medición cero.

Replay local del mismo historial, reloj congelado para ambas implementaciones,
ventana móvil 48 h de esta ejecución: 125 corridas y 26 intentos de agencias nuevas
en ambas; caudal mal llamado certified anterior 0,54/h vs 8 primeros cierres
exitosos registrados/0,17/h candidato. Inventario enumerado asociado 363 vs 386
por recuperar el primer éxito posterior de agencias ya intentadas; NO son filas
publicadas ni prueba de mejor extracción. Cero requests/escrituras de DB o archivos
originales. No se transforma esta tasa histórica en throughput neto verificado
ni ETA nacional. Suite inicial 2602 PASS (157,71 s); alinear las ventanas múltiples
con la misma frontera agregó controles: 2607 PASS (158,84 s), sin fallos/errores/skips.
47 controles focalizados PASS/lint PASS de la optimización posterior. Cinco ventanas
repetían cinco lecturas del log de 19.891.396 bytes/2501 registros (4,52 s); una
captura de log/reloj conservó tasas 0/0/0/0,17/0,31 por hora y midió 0,789 s.
Es una medición local puntual, no un benchmark del pipeline ni throughput nacional.
Suite completa de lectura única: 2608 PASS, 0 fallos/errores/skipped, 168,63 s,
backend_throughput_single_read_validation.xml. Wheel aislado también
resolvió strategy_fingerprint/current_code_evidence sin importar config/clients.

Vigencia de identidad en la cola: el runner convertía excepciones de
resolve_identity en fuente=None y podía reutilizar éxito antiguo; IDENTITY_PENDING
sin URL previa seguía terminal por certifier_version aunque el catálogo ya fuera
READY. La frontera is_current_catalog_result reutiliza la política existente sin
requests: cierre de identidad sólo vigente si persiste su clasificación; cierres
de parser exigen identidad READY, URL observada no vacía y el mismo FK entero
positivo observado, además de huella actual. Cambios de FK/URL, metadata ausente,
catálogo malformado o fallo de resolución invalidan reutilización, no prueban una
agencia inactiva. Los llamadores históricos de is_current_result se conservan;
el runner real usa la nueva frontera. No traduce IDs ni prueba namespace público.
166 controles focalizados/lint PASS; suite congelada 2633 PASS, 0 fallos/errores/
skipped, 157,01 s, backend_current_identity_validation.xml. No se ejecutó cola
contra agencias/productivo ni se mutaron registros originales. Sigue pendiente
la continuidad temporal/proveniencia geográfica y vigencia de éxito por antigüedad.
