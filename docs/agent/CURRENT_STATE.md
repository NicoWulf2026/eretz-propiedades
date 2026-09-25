# ERETZ — estado actual

Documento vivo. Se actualiza al cerrar cada fase; lo más nuevo va arriba en
«Bitácora». `database_writes: 0` en todo lo que figura acá salvo que diga lo
contrario.

**Rama:** `handoff/codex-unificacion-2026-09-18` (push sólo a esta rama).
**Universo de la cola:** 791 agencias `ready` (w0 413, w1 378). 434 con algún
resultado: 143 `CERTIFIED_COMPLETE`, 15 `CERTIFIED_BEST_AVAILABLE`, 1
`NO_INVENTORY_CONFIRMED`, 100 `NEEDS_FIX`, 35 `BLOCKED_EXTERNAL`, 140
`IDENTITY_PENDING` (medido 2026-09-24 11:08).

## Cómo corre la cola sola

| pieza | qué hace | dónde |
|---|---|---|
| 2 workers | certifican; paran ante cualquier bandera al terminar la agencia | `scripts/run_agency_certification_queue.py` |
| `ERETZ_relanzador` (cada 10 min) | relanza si es seguro, acota paros a familias, libera familias | `scripts/relanzar_la_cola.py --lanzar --log …` vía **pythonw** |
| `ERETZ_vigilante_paros` (cada 5 min) | alerta paros desatendidos y familias detenidas > 12 h | `scripts/vigilante_de_paros.py` vía `_vigilante.bat` |

Política de paros (vigente desde 2026-09-24):

- `FAMILIA` con conector conocido → se detiene esa familia, el resto sigue.
- `COMPARTIDO` **con causa nombrada** (`shared/runner`) → se detiene todo.
- `COMPARTIDO/sin_determinar` → se detiene **su familia**; si aparece otro
  sin atribuir en una familia distinta con el primero abierto → todo.
- Una familia detenida se libera con diferida firmada posterior al paro, o
  si cambió la huella del código que el paro sospechaba (se vuelve a probar,
  no se certifica nada).
- Si una familia se libera con workers corriendo, el relanzador pone una
  bandera `OPERACION` y los relanza al terminar su agencia en curso.

Libro de familias detenidas: `ERETZ_FAMILIAS_DETENIDAS.jsonl`. Hoy: ninguna.

## Bitácora

### 2026-09-25

- **Paro de `generico` 01:44 (`arquitectura`)**: falso positivo de la señal de
  operación del auditor (estado consumado sin precio). Diferida 01:45, familia
  liberada; arreglo anotado en HANDOFF 5e.
- **Orden de la cola, segunda parte** (`f742f35255`). La rotación eliminó el
  retrabajo (desde 21:24: 38 resultados, 38 agencias, 0 h repetidas; antes
  13,3 de 16,6 h) pero no entró ninguna nueva: los ~51 canarios iban antes.
  Ahora nuevas y conocidas 1:1 desde el principio. Relanzamiento 01:17.
- **Paro de `generico` 00:34 (`fios`)**: plantilla propia (descripción sin
  rótulo, categorías en singular, foto ajena por ficha). Radio AGENCIA,
  diferida firmada 00:36, familia liberada; arreglos anotados en HANDOFF 5d.
- **Gate 00:29: 83 agencias, 0 pendientes.** Patrón de las revisiones: casi
  todas las «pérdidas» eran datos falsos de la línea base que el código de hoy
  ya no produce — dirección y ciudad de la OFICINA de la agencia tomadas del
  nodo `RealEstateAgent` (`ferrari` 156×2, `diaz collins` 8×2, `franco`),
  conteos de propiedades del lateral (`cip`), operaciones al revés
  (`alma di matteo`, `filippini`). Las reales se arreglaron (tokko ubicación,
  Xintel detalle).
- **Paro de `generico` 23:57 (`gianini`, sin_determinar)**: la fuente sirvió una
  página degradada en la corrida 1 (643 s contra 98 s): una ficha con título
  «en» y descripción del meta. Radio AGENCIA, diferida firmada 00:06,
  familia liberada. `conti` (151 descripciones con HTML crudo) es un
  resultado del 21-09: el código de hoy las lee limpias.

### 2026-09-24

- **Tokko perdía la ubicación** (`41eb162786`) cuando la seguía la lista de
  servicios («Victoria Agua Corriente No…»): patrón en 32 de 33 agencias tokko
  muestreadas con fichas sin geografía (hasta 294 fichas). 15 de 15 fichas
  reales la recuperan; 14 de 15 controles iguales, 1 mejora. Y la señal de
  fuente de operación del certificador ve la etiqueta (`896238f7ae`).
  Gate desde 11:39: 73 agencias, 0 pendientes (5 más firmadas 23:12).
- **Etiqueta «En Venta» de la plantilla `/ad/`** (`5977acb741`): 205 de 380
  fichas de 13 agencias sin operación, varias CERTIFIED_COMPLETE así. En 30
  fichas reales: 12 ganan, 0 cambian, 0 pierden.
- **Operación por rótulo** (`88f5a46c60`): «Tipo de operación En venta» (plantilla
  `/site/properties/`) y «alquiler temporario» que se cortaba en «alquiler». 6 de
  22 fichas reales ganan su operación, ninguna otra cambia. El gate de las
  21:49 marcó 322 pérdidas: 312 eran `ferrari` perdiendo la dirección y ciudad
  de la OFICINA de la inmobiliaria (nodo `RealEstateAgent`), firmadas como
  corrección; el resto, fichas con dos ofertas o conteos de emprendimiento.
- **La cola repetía trabajo** (`4f377ad210`, no toca huellas). Hoy: 125
  resultados sobre 58 agencias; 12,5 de 15,8 h de worker en agencias
  certificadas 2+ veces el mismo día; sólo 6 nuevas. Los canarios (3 por
  familia, ~51) eran siempre los primeros alfabéticos y cada cambio de huella
  los rehacía (~3 h). Ahora las conocidas van de la intentada hace más tiempo
  a la más reciente. Relanzamiento pedido con bandera OPERACION a las 21:15.
  **Lección**: cada cambio de huella cuesta ~3 h de canarios; agrupar cambios.
- **Páginas de categoría guardadas como fichas** (`cfd040385a`): van a
  revisión (detalle fallido), no se borran. Regla medida sobre 157 fichas
  reales: 0 falsos positivos. `cbdestino` había guardado una con el precio de
  un aviso de la grilla.
- **Xintel certificaba en falso** (`79fa5ae1dd`, `fa6eba6970`; excepción de
  ventana cerrada). `in_des` es una bandera: 256 fichas guardaban «True» como
  descripción y 1.014 la perdían; la real está en `in_obs`. 10 agencias, 6
  eran CERTIFIED_COMPLETE (sus certificados ya no tienen huella vigente).
  Además, si la API no aplicaba el detalle la ficha seguía con la fila del
  listado y marcaba coordenadas como «no provistas» (`bondar`, 4 fichas
  intermitentes); ahora es detalle fallido. Validado con fichas reales.
- **Regression Gate** (`686b134930`): lee también `atributos_descartados` y
  `provincia_supuesta_descartada`. Desde 11:39: 56 agencias, **0 pendientes**
  (6 pérdidas firmadas en `REVISADAS.jsonl`).
- **Regresión propia, detectada por la cola y arreglada** (`2bf6903d9f`). El
  cambio de descripciones de `0bd66ac5e5` activó un camino que truncaba antes
  de quitar `<script>`: `coldwell banker destino` guardó JavaScript como
  descripción en 19 de 22 fichas. Falló cerrada (el token CSRF cambia entre
  corridas → no idempotente) y detuvo `generico` 18:45–20:10. Radio: 1 agencia
  en 43 paquetes. Diferida firmada con las dos causas.
- **Paro de `wordpress` (19:25, `gustavo teruel`)**: la agencia carga los
  conteos como «1.», «2.» (y «Si.» en baños); verificado en 10 fichas. Radio
  real AGENCIA, falla cerrada, diferida firmada. Arreglo candidato para la
  próxima ventana de `wordpress`: aceptar punto final tras un conteo.
- **Browser QA contra la v4 nueva: 65 de 65** (7 skipped: asistente de
  publicación apagado). Un defecto real del buscador arreglado (`c4051b4a21`:
  el cierre diferido del blur no se cancelaba al volver el foco) y el test de
  conteo literal ahora compara contra la API. Vitest 1.237, tsc y eslint
  limpios. Detalle en `ERETZ_QA_BROWSER_2026-09-20.md` § tercera corrida.
- **Mapa sin filtros** (`b84aba8b86`): índice cubriente por coordenadas, usado
  sólo para contar la caja cuando no hay otros filtros ni texto. Conteo 549→4
  ms; endpoint 520–550→90–165 ms con caché caliente; respuestas idénticas en 8
  casos. La v4 de `_scratch` ya tiene el índice.
- **`ab negocios` recertificada con el `generico` nuevo: CERTIFIED_COMPLETE**,
  24 descripciones propias (antes: el eslogan de la agencia en las 24).
- **Ventana corta de `generico`, 16:20–16:45** (`0bd66ac5e5`). Se reabrió con
  números: con las huellas invalidadas a las 15:17, había 6 resultados
  `generico` vigentes; cada hora que pasaba el cambio costaba más. Tres
  arreglos, todos validados con `normalize` completo sobre 16 fichas reales
  (HEAD vs nuevo: cambian sólo las esperadas):
  - descripción: el rótulo propio de la ficha gana sobre el `og:description`
    institucional. 28 agencias / 1.774 fichas guardaban el eslogan del sitio;
    sondeo de 193 fichas: 47 pasan a su descripción propia (24 agencias).
  - título: «Agencia | Título» ya no se descarta entero (`cortes`: 23 fichas
    CERTIFIED_COMPLETE tituladas con el nombre de la agencia).
  - conteos desde `additionalProperty` (`baron`).
  **Ventana cerrada de nuevo a las 16:45.**
- **API de búsqueda** (`09aba154c4`, no toca huellas): la snapshot se arma
  en orden de id, cada fila de `busqueda` lleva el rowid de su propiedad, y
  lo declara en `snapshot_meta`. La API sólo toma el atajo si está
  declarado. Mismas respuestas en 9 consultas sobre las 57.665: explorer
  304→75 ms, combinada 908→251, mapa con texto y filtros 1.618→604, precio
  selectivo 1.788→837. Se nota recién con una snapshot reconstruida.
- **Regression Gate con revisiones** (`6543624a97`): 36 agencias
  recertificadas desde las 11:39, 29 pérdidas sin explicar → 0 pendientes.
  24 eran la descripción institucional de `ab negocios` (el gate ahora lee
  `extra.descripcion_descartada`); 5 se bajaron de la fuente y se firmaron en
  `_regresion/REVISADAS.jsonl` (2 correcciones, 3 cambios en la fuente).
  Correrlo con `--desde 2026-09-24T11:39:00` cada tanto.
- **VENTANA SEMÁNTICA CERRADA a las 15:25.** Hoy se invalidaron todas las
  huellas dos veces (lote compartido 11:40, runner 15:17). A las 15:20 la
  cola `ready` tenía **784 agencias y 509 nunca certificadas**; de las 275
  con resultado, sólo 1 con huella vigente. Desde ahora no se tocan archivos
  de `archivos_de_la_huella()` salvo un defecto que certifique en falso; lo
  demás se acumula para la próxima ventana (ver «Pendiente anotado»). A ~8
  min por agencia y 2 workers, recorrer las 784 lleva ~52 h de máquina
  encendida.
- **Orden de la cola** (`082c805687`, no toca huellas): las nuevas iban al
  final del bulk y cada invalidación las volvía a postergar. Ahora canarios
  → nuevas y conocidas intercaladas 1:1 → cola larga.
- **Descripciones que son el pie del sitio** (`18c476dc29`, `shared/runner`):
  `coldwell banker de la vera cruz` estaba CERTIFIED_COMPLETE con la MISMA
  descripción —«© 2026 Coldwell Banker. Todos los derechos reservados…»— en
  sus 266 propiedades; `coldwell banker andes`, en 5 de 174. Regla nueva en
  el runner, junto a la de fotos compartidas: texto repetido en ≥ la mitad
  de las fichas (piso de 8) o que arranca con «©» → descripción vacía y
  `extra.descripcion_descartada`. Invalida las certificaciones desde las
  11:40. Suite: 3.154 en verde.
- **Pendiente anotado, sin tocar**: páginas de aterrizaje guardadas como
  propiedades en `fenix` (3) y `casablanca` (10), con operación y tipo
  adivinados de la URL de la categoría. Ninguna agencia está certificada.
  `ficha_sin_contenido` (en `shared/base`) cuenta esos campos como dato;
  arreglarlo invalida todo, para el próximo lote compartido.
- **`wordpress`/ERE** (`86c8cb1768`): «$990,000 / DOLARES» se guardaba como
  990.000 **pesos**; ahora una moneda explícita pegada detrás del número gana
  sobre el «$». Y el rótulo en elementos (`<strong>Property status</strong>
  <span>En Venta</span>`) se lee: `ente` pasa de operación vacía en 49 de 50 a
  `venta`. Verificado en 3 fichas reales. En `generico` el mismo patrón
  aparece una sola vez en las descripciones guardadas (`conti`): no se tocó.
- **Herramienta de heredoc, otra vez.** Un parche escrito por heredoc metió
  caracteres de control en un regex de `wordpress.py` (`\1` → `\x01`). Se
  reparó con un script escrito por Write y se revisaron todos los archivos
  tocados hoy: ningún otro tiene caracteres de control. Regla: los parches
  con regex, siempre por Write/Edit.
- **Utilización de la cola.** Desde el 17-09: 81,6 h de worker en 604
  resultados (≈8 min por agencia), ninguna con presupuesto agotado, sobre 336
  h disponibles: 24 %. Hoy, con la máquina encendida, 45–92 % por hora. El
  agujero de anoche no fue la cola: el registro del sistema muestra un
  reinicio pedido por el usuario a las 20:32 y un **apagado inesperado a las
  21:12:54** (evento 6008: corte de luz o apagado forzado); volvió a las
  08:29 y las tareas retomaron solas a las 08:34. Recomendación para el
  usuario (no la ejecuto: es configuración del equipo): UPS o mantener el
  equipo encendido; `WakeToRun` no sirve contra un apagado.
- **Tarde (14:50–15:00).** Paro `generico` por `alta inmobiliaria` a las
  14:28: la fuente declaró 18 y después 16, y enumeramos exactamente eso las
  dos veces. Triaje nuevo `catalogo_que_cambio_la_fuente` (`771666e47a`,
  replay: 3 cambios sobre 1.359, todos el patrón) y diagnóstico firmado.
- **Conteos de schema.org** (`af8be5820c`): `numberOfRooms/Bedrooms/
  BathroomsTotal` se leen y mandan; un «+4 Ambientes» ya no se guarda como 4.
- **Diagnóstico de `NEEDS_FIX` con el código de hoy** (livianos, 3 fichas
  por agencia, `scratchpad/diag_detalles.py`):
  - ya funcionan y van a certificar cuando la cola llegue: `cecilia sarro`,
    `corporacion`, `chambouleyron`, `a varela`, `beltramone`;
  - rechazo del guardián de forma en las 3 fichas: `cometto`, `cuini`,
    `aris` (2 de 3) — mirar qué rechaza;
  - sitios lentos (el presupuesto se va en enumerar): `casagrande`,
    `benitez`, `crestale`, `battista` (Xintel, 480);
  - descubrimiento sin plan: `eduardo fernandez`, `coviella`, `de ruyck`,
    `andrade`; WordPress sin inventario: `aguirre`, `estela d onofrio`.
- **La guarda de huella en vuelo, verificada en producción.** w0 (arrancado
  11:44) certificó `9010 inmobiliaria` mientras cambiaba
  `agency_web_discovery.py`: el resultado quedó `CERTIFIED_COMPLETE` con
  `strategy_fingerprint: None` y `codigo_cambio_en_vuelo` (se va a
  recertificar), y el worker paró con `para_por_codigo_cambiado`. Sin la
  guarda habría quedado vigente habiendo corrido el código viejo.
- **Lote compartido aplicado** (`d3afa4fd3e`): portales por nombre
  registrable, `compare_runs` por identidad, contador de rechazos con la
  regla del triaje. Cola `ready` 791 → 784. Recalculado sobre los 281
  paquetes: cambia sólo `eckert` (30 faltantes falsas → 0). Invalida las 60
  certificaciones vigentes.
- **`generico`**: id de la ficha sin números sueltos del slug (`feb5f5eca6`,
  ítem 6: choques dentro de una agencia 968 → 639) e ícono entre rótulo y
  número (`78349978a0`, ítem 11: `alas` 120 de 206 sin dormitorios).
- **Línea base para el Regression Gate**: 23.593 filas de 281 agencias en
  `ERETZ_AGENCY_CERTIFICATION_20260827/_regresion/ANTES_DEL_LOTE_2026-09-24.jsonl`
  (11:39, antes del lote compartido). Comparar contra la recertificación.
- **El vigilante corría un checkout del 17-09.** La tarea ejecutaba
  `D:\INMO CAPITAL\eretz-agency\_vigilante.bat` (worktree
  `feat/roomix-agency-coverage` @ `d9238e64be`): `FAMILIA_DETENIDA` y todo lo
  posterior no estaba corriendo. Ahora corre `eretz-unified` con `pythonw` y
  `--log`; sus subprocesos van con `CREATE_NO_WINDOW`. Se deshabilitaron
  `ERETZ_cola_w0/w1/certificacion` (sin horario, pero apuntaban al mismo
  worktree viejo). Copias de las definiciones anteriores:
  `ERETZ_relanzador.antes.xml` y `ERETZ_vigilante_paros.antes.xml` en el
  scratchpad de la sesión.
- **Los workers ahora corren con `pythonw.exe`** (el relanzador los lanza con
  `sys.executable`). Para buscarlos por proceso, filtrar por
  `run_agency_certification_queue` en la línea de comandos, no por
  `python.exe`.
- **Pedido de relanzar que no se borraba bien** (`c10a6e7309`): el primer
  worker nuevo borraba la bandera `OPERACION` y el otro, viejo, no se
  enteraba. Verificado: w1 nuevo a las 11:34 dejó la bandera en pie; w0 viejo
  para al terminar `alas propiedades`.
- **Huella en vuelo** (`f0556f8dc6`): `strategy_fingerprint` se leía de disco
  al terminar la agencia; un worker con código viejo en memoria estampaba la
  huella del código nuevo si alguien editaba con la cola corriendo. Ahora el
  worker para entre agencias si cambió un archivo de la huella, y un
  resultado producido durante un cambio queda sin huella (se recertifica).
  **Regla operativa desde ya:** no editar archivos de la huella con workers
  viejos (sin esta guarda) corriendo. Se pidió relanzamiento limpio con
  bandera `OPERACION` a las 11:25.
- **Pasadas con `pythonw` confirmadas**: 11:14 y 11:24, resultado 0, con
  «arranca pid» y «plan en 1,3–1,7 s» en el log.
- **Lote compartido en preparación** (tests escritos, código sin aplicar):
  lista de portales por etiqueta en la política de fuentes (`buscainmueble`,
  `todoprops.com`, `inmobusqueda.com`: 295 «propiedades» falsas en 4
  agencias, 9 agencias de la cola con la web oficial en un portal),
  `compare_runs` por identidad (ítem 19), contador de rechazos del runner con
  la regla de fotos del triaje (ítem 9). Invalida las 60 certificaciones
  vigentes (52 COMPLETE, 7 BEST_AVAILABLE, 1 NO_INVENTORY).
- **Relanzador sin consola.** Desde las 08:30 tres o cuatro pasadas por hora
  morían con `0xC000013A` sin dejar rastro (09:54, 10:24, 10:44; 10:54 dejó
  sólo «arranca pid»). El 23 no falló ninguna. La tarea pasó de
  `_relanzador.bat` a `pythonw.exe … --log`; la definición anterior está en
  el scratchpad de la sesión como `ERETZ_relanzador.antes.xml`. Con
  `faulthandler`, un cuelgue futuro deja la pila en el log a los 120 s.
  *Pendiente: confirmar la pasada de las 11:14.*
- **Huellas cacheadas por archivo** (`edfcf4cd86`): 4,5 s → 2,7 s la primera
  pasada, 0,00 s las siguientes; valores idénticos en 5 estrategias.
- **`sin_determinar` degrada a su familia** (`142c2535ad`). Los 19 COMPARTIDO
  del historial son `sin_determinar`; simulado: 11 se acotan, 8 escalan.
- **Liberar una familia llega a los workers que corren** (`6f74d3e5b1`).
  Verificado: bandera 10:34, relanzamiento 10:52 con `conectores_excluidos: []`.
- **`wordpress`/`austral`** (`1c7a0b3a62`): página REST de 2,3 MB contra
  límite de 800 KB → páginas más chicas por `offset`. 0 → 205 = `X-WP-Total`.
- **Triaje: fichas que no bajaron** (`baec45b800`): 10 de 1.353 NEEDS_FIX
  pasan de STOP/FAMILIA a CONTINUE/AGENCIA.
- **Paro sobre código que cambió se reintenta** (`6de514d755`).
- **JSON-LD con URL canónica declarada** (`401252acfd`): `alagna` 0 → 229
  fichas con ciudad. w0 la está recertificando ahora (canario del arreglo).
- Diagnósticos firmados, verificados contra la fuente: `inmobiliaria
  varesse`, `brikel propiedades`, `di maria negocios inmobiliarios`.

### 2026-09-23

- Operación: 2.032 vacías, 64 al revés, 220 propiedades que eran fotos
  (`0693efa4fb`). Ver `ERETZ_LA_OPERACION_2026-09-23.md`.
- Paro de familia no es la cola (`8cef5a1550`). Ver
  `ERETZ_UN_PARO_DE_FAMILIA_NO_ES_LA_COLA_2026-09-23.md`.
- Coordenadas buenas ya no se borran en un conflicto de localidad
  (`a40d6cee6d`).

## Pendiente para producción — READY_FOR_PRODUCTION_ACTION

Nada de esto se ejecuta sin el usuario; se consolida acá.

- Escritura en Supabase (`internal_scraping`, `public.propiedades`): todo el
  trabajo es local; no hay write set nuevo preparado desde el 2026-08-27.
- Credencial de mínimo privilegio para `eretz_direct_property_writer`:
  `BLOCKED_EXTERNAL_CREDENTIAL` (ver `MASTER_PROGRESS.md`, checkpoint 08-27).
- Merge a `main` / deploy: no corresponde todavía.
- **Decisión de costo (no productiva, pero gasta dinero)**: 140 agencias en
  `IDENTITY_PENDING` desde el 31-08/01-09 (134 sin clave ERETZ resuelta, 111
  sin web oficial conocida). Resolverlas necesita la fase C de
  `scripts/run_web_discovery.py` (Brave, paga). Costo medido el 14-09: USD
  2,38 por 250 agencias → ~USD 1,35 para estas 140. No se corrió: además,
  `search_provider.py` carga `.env` por su cuenta y podría activar la fase paga
  sin que se note.
- **Snapshot servida de la API local** (`D:\INMO CAPITAL\ERETZ_API_CONTRACT\
  ERETZ_API_SNAPSHOT.sqlite3`): hoy es una `api_snapshot_v2` del 08-09. Hay
  una v4 del 24-09 construida y verificada (57.665 filas, `integrity_check`
  ok, 14 casos del benchmark con su status) en
  `_scratch/unification/snapshot_v4_2026-09-24/`. Con ella: explorer 307→83
  ms, combinada 900→249, mapa grande 1.236→674. Reemplazarla la hace servir;
  el clasificador de permisos lo trató como deploy, así que se revirtió y
  queda para el usuario (respaldo de la actual en `_anteriores/`).
  Diferencias de dato, v2 servida → v4 nueva: municipio 0 → 36.271,
  departamento 9.574 → 45.541, provincia 56.707 → 56.236, latitud 42.670 →
  42.414, SIN_AREA 492 → 963, precio 52.329 → 52.352. De las 481 filas que
  pierden coordenadas, 470 son `GEO_CONFLICT` que la v4 retiene (la v2
  servía, p. ej., provincia «Rosario» para `vanzini`); 225 filas ganan
  coordenadas.
