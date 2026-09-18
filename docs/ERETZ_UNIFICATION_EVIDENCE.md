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
