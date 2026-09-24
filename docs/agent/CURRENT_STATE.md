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

### 2026-09-24

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
