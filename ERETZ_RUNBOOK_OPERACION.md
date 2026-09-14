# ERETZ — Runbook de operación

Para operar el sistema sin auditarlo entero cada mañana. Todo lo de acá es
local y de sólo lectura salvo donde diga lo contrario.

---

## 1. ¿Cómo está todo? (30 segundos)

```bash
python scripts/operacion_reporte.py
```

Devuelve el estado de la cola, el de los datos, y **alertas**. Sólo se enciende
lo que pide una acción humana: que una inmobiliaria esté bloqueada no es una
alerta, es un hecho conocido del mundo.

| Alerta | Qué hacer |
|---|---|
| la cola está parada por un defecto transversal | §3 |
| N líneas ilegibles en los resultados | §6 — dos procesos escribieron el mismo artefacto |
| N propiedades reales quedaron fuera por incompletitud | es la regla que no se negocia: revisar el quality gate |
| cerrojo sin proceso vivo | §5 |
| no hay ningún runner en curso | §2 |
| `<campo>` falla en N propiedades que la fuente sí publica | §7 |

---

## 2. Abrir la cola

**Siempre** preflight primero. Si no da 7/7, no se abre: cada chequeo existe
porque su ausencia ya costó algo.

```bash
python scripts/agency_rollout_preflight.py
```

Con un worker:

```bash
schtasks /run /tn ERETZ_cola_certificacion
```

Con dos (reparto por host, ver §4):

```bash
schtasks /run /tn ERETZ_cola_w0
```

```bash
schtasks /run /tn ERETZ_cola_w1
```

Task Scheduler y no una consola: una consola compartida con otro proceso muere
cuando ese proceso muere, y ya pasó tres veces.

---

## 3. La cola paró sola

Paró porque el triage encontró un defecto de radio transversal. **No se reabre
sin arreglarlo**: reabrir camina hacia la misma parada, y las agencias que
certifique en el camino habrá que rehacerlas igual.

1. Leer el último renglón de `cola_task.log` o `cola_w*.log`: dice qué
   inmobiliaria, qué componente se sospecha y con qué evidencia.
2. Diagnosticar **contra la fuente real**, no contra los tests. Un test que
   pasa no prueba nada sobre un sitio que cambió.
3. Arreglar, correr la suite, y recertificar esa inmobiliaria a mano:
   ```bash
   python scripts/agency_certifier.py --canonical-id "<id>"
   ```
4. Preflight y reabrir.

Si el defecto toca `connectors/base.py`, `geografia.py`, `texto.py`,
`coherencia.py` o `generico.py`, invalida **todas** las huellas: conviene
juntarlo con otros cambios pendientes del mismo radio y pagar una sola
recertificación. Ver §8.

---

## 3 bis. "Postgres no responde" (PGRST002)

**No es una caída.** Diagnosticado el 2026-09-08: PostgREST se conecta bien a la
base —los registros dicen `Successfully connected to PostgreSQL 17.6`— y falla
después, al construir el cache de esquemas:

```
Failed to load the schema cache using db-schemas=pg_pgrst_no_exposed_schemas
{"code":"3F000","message":"schema \"pg_pgrst_no_exposed_schemas\" does not exist"}
```

Ese nombre es el marcador que pone Supabase cuando la lista de **esquemas
expuestos** de la API quedó vacía. El proyecto figura `ACTIVE_HEALTHY`, la base
tiene sus datos —`public.propiedades` 257.073 filas -medido el 2026-09-09-, `public.inmobiliarias_main`
7.004— y PostgREST reintenta cada 32 segundos desde hace días.

Se arregla en **Settings → API → Exposed schemas**. Es un cambio de
configuración productiva: requiere autorización explícita (§8 del plan).

**Corrección del 2026-09-09.** Aquí decía que la tabla de backup quedaría
alcanzable con la anon key al reponer el esquema, y que había que cerrarla antes.
**Es falso.** Lo deduje del advisor de RLS sin mirar los permisos, y el advisor
habla de RLS, no de grants. Comprobado contra la base:

| rol | USAGE en `public` | lee `propiedades` | lee la tabla de backup |
|---|---|---|---|
| `anon` | sí | **no** | **no** |
| `authenticated` | sí | **no** | **no** |

`anon` no tiene SELECT sobre ninguna tabla de producto: lo único que alcanza en
`public` son tres objetos de PostGIS (`geography_columns`, `geometry_columns`,
`spatial_ref_sys`). Y `internal_scraping` no es alcanzable en absoluto porque
`anon` **no tiene USAGE** sobre ese esquema.

O sea: **reponer el esquema expuesto no publica ni un dato.** Devuelve el
endpoint y nada más. No hay paso previo que dar.

Lo que sí conviene saber es qué es esa tabla de 129.572 filas, porque el nombre
engaña: **no es un backup de propiedades.** Tiene cuatro columnas
—`property_id, old_url_normalizada, new_url_normalizada, backup_created_at`— y
un solo timestamp. Es el registro para revertir **una columna** de la migración
del 2026-07-29. No sirve como respaldo de nada más.

### El paso, uno solo

**Reponer el esquema expuesto.** Settings → API → Exposed schemas: dejar
`public` (y `graphql_public` si estaba). **No agregar `internal_scraping`.**

PostgREST reintenta solo cada 32 segundos, así que la API vuelve sin reiniciar
nada. Para comprobarlo:

```bash
curl -s -o /dev/null -w "%{http_code}
" -H "apikey: $SUPABASE_ANON_KEY" "$SUPABASE_URL/rest/v1/"
```

`200` es que volvió; `503` con `PGRST002` es que sigue sin esquema.

**Qué NO hay que hacer**: no correr el `ALTER TABLE ... ENABLE ROW LEVEL
SECURITY` sobre las diez tablas de `internal_scraping`. Ahí escribe el pipeline
con la service role key —que se salta RLS— pero habilitarlo sin políticas es un
cambio productivo que no hace falta para esto, y el pipeline está en medio de
una recertificación.

---

## 3 ter. Fuentes que sirven el catálogo por JavaScript

Un sitio hecho con React o con un módulo de listado client-side devuelve un
cascarón: el HTML tiene el menú y el buscador, pero **ninguna URL propia**.
Diagnosticadas el 2026-09-09:

| agencia | qué devuelve |
|---|---|
| `armaninonegociosinmobiliarios.com.ar` | 657 bytes, "You need to enable JavaScript to run this app" |
| `attaguile.com` | 213 KB de Elementor, 1.310 caracteres de texto, y la única URL propia en todo el HTML es la home |

No son un defecto del parser ni una fuente sin inventario, y **no hay estado
terminal para ellas**: quedan en `NEEDS_FIX` esperando un arreglo que no es un
arreglo sino otra forma de leer. Hoy el triage las deja pasar —radio
`ESTRATEGIA`, no para la cola— así que no bloquean, pero tampoco cierran.

**Son cerca del 2 %: unas quince de las 764.** Medido sobre una muestra de 150
de la cola: 141 sirven HTML navegable, 5 no respondieron y 4 quedaron marcadas,
de las cuales una —`loscerrospropiedades.com`, con menú y 59 enlaces— es un
falso positivo de la señal `__NEXT_DATA__`. Las genuinas son constructores de
sitios que renderizan entero del lado del cliente: `arnoldipropiedades.com.ar`
devuelve 274 KB **sin un solo `href`**.

Con quince agencias, un camino con navegador no se paga hoy. Vuelve a mirarse
si el número sube.

La primera medición dio 31 y **estaba mal**: contaba sólo los enlaces que
empiezan con `/` y se perdía los relativos, así que metió en la bolsa a
`aconcaguaprop.com.ar`, que esa misma noche certificó COMPLETE con 78
propiedades. La lección es del método: un heurístico sobre HTML hay que
contrastarlo contra una fuente que ya sabemos leer.

---

## 3 quater. Cuándo NO arreglar algo durante la pasada

Hay una tensión que conviene tener escrita, porque no es obvia y se paga cara:
**la cola revela defectos, y arreglarlos invalida la cola**. Cualquier cambio en
un connector o en `shared/*` cambia la huella y obliga a rehacer todo lo
certificado desde que empezó la pasada.

Medido el 2026-09-09: ~5,5 minutos por inmobiliaria, o sea unas 36 horas por
worker para las 764. A las dos horas de pasada ya hay ~50 agencias hechas, y un
cambio de huella tira 4,5 horas de máquina. A las diez horas tira veinte.

**La regla, entonces:** durante una pasada sólo se aplican los cambios que

1. **detienen la cola** —un defecto de radio transversal no se puede esperar—, o
2. **corrompen datos** —una superficie de cincuenta kilómetros cuadrados que se
   iba a publicar—, o
3. **cierran una agencia que si no queda en `NEEDS_FIX` para siempre**.

Todo lo demás se **diagnostica contra la fuente, se escribe, y se aplica junto**
en la próxima ventana. Un campo que falta en 196 propiedades puede esperar; tirar
cinco horas de certificación para recuperarlo, no.

El corolario incómodo: la primera pasada produce datos **mejores que los
anteriores pero no óptimos**, y eso está bien. Lo que no está bien es reiniciarla
cada vez que el audit encuentra un rótulo más.

---

## 3 quinquies. Diferir un defecto ya diagnosticado

El corte por lote para la cola con cinco defectos sueltos, con dos que comparten
firma, con uno de radio compartido o de familia, o **a las 12 horas del primero
pendiente**. Los tres primeros son buenos. El cuarto se vuelve una molestia
cuando los pendientes son defectos que ya tuvieron su tanda de diagnóstico y no
se van a arreglar en esta pasada: la cola para, se mira lo mismo, se reabre, y
doce horas después vuelve a parar.

`AGENCY_DEFECTS_DIFERIDOS.jsonl`, en el directorio de certificación, es la
respuesta. Una fila por agencia:

```json
{"canonical_agency_id": "roomix:…", "diagnostico": "…", "por_que_se_difiere": "…"}
```

**Diferir no es ocultar.** El defecto se sigue anotando entero en
`AGENCY_DEFECT_QUEUE.jsonl`, la agencia sigue cerrando `NEEDS_FIX`, y la fila
**exige un `diagnostico` escrito** para valer —sin eso la lista se vuelve el
lugar donde van a parar los defectos incómodos—.

### Los dos grados

**Sin firma** —sólo `diagnostico`— difiere del **corte por lote** y de nada más.
Un radio transversal para igual. Es el caso de `armanino`, `attaguile`,
`gianfelice`, `amud`, `bergo` y `bottai`.

**Con firma** —además `componente` y `radio`— también atraviesa el **paro**,
pero sólo si el defecto que aparece es exactamente ése:

```json
{"canonical_agency_id": "roomix:bottega propiedades",
 "diagnostico": "publica 'Ambientes 5' en la ficha y la extraccion no lo toma…",
 "por_que_se_difiere": "quien lee ese bloque es codigo compartido…",
 "componente": "extraccion_transversal_de_atributos",
 "radio": "FAMILIA"}
```

La firma es lo que impide que esto sea un interruptor de apagado. Si esa misma
agencia vuelve con **otro componente**, o con el mismo y un **radio mayor**, el
paro se dispara igual: eso ya no es lo que alguien miró y decidió postergar.

**Antes de poner una firma hay que contrastar contra la fuente real.** El
diagnóstico de `bottega` se verificó abriendo `/site/properties/464060` y viendo
el rótulo `Ambientes 5` en el HTML servido, sin JavaScript. Firmar sin
comprobar es apagar el corte a ciegas.

**No usar `--continue-after-fix` para esto**: apaga *todos* los STOP, incluidos
los que atajaron `arte`, `alder` y `arbini`, y los que atajarían una corrupción.

El preflight lee la misma lista, así que una agencia con firma tampoco bloquea
la reapertura. Sin eso el deadlock volvía por la otra puerta.

---

## 3 sexies. Una señal más laxa que su extractor fabrica defectos

Pasó **tres veces** entre el 2026-09-09 y el 2026-09-10, y las tres pararon
las dos colas. Ya no es una anécdota: es la causa más frecuente de parada.

El audit de campos compara dos cosas: **la señal** —"¿la ficha publica este
campo?"— y **la extracción** —"¿lo sacamos?"—. Cuando la señal dice sí y la
extracción no, es un defecto nuestro, y si el campo lo lee código compartido el
triage lo escala a radio `FAMILIA` y detiene todo.

Eso está bien **siempre que las dos pregunten lo mismo**. Cuando la señal es más
laxa, no reporta un defecto: lo inventa.

| agencia | la señal veía | la ficha tenía |
|---|---|---|
| `arbinipropiedades.com.ar` | `Terreno 127 m` | `127 m x 50 m`, que es una **medida**, no un área |
| `inmobiliariacip.com.ar` | el atributo `data-lat` | `data-lat=""`, el contenedor del mapa **vacío** |
| `brunettipropiedades.com` | `bano 2`, o sea baños | `República del Líba**no 2**8,36 mts`: el **nombre de la calle y su altura**, en un **terreno** |

El tercero es el más claro de los tres, y el más incómodo: la señal encontró
`bano` dentro de `Líbano` y el número siguiente era la altura de la calle. La
misma ficha tampoco publica precio en ninguna forma —ni `USD`, ni `$`, ni la
palabra— y la señal decía que sí.

En los tres casos el extractor tenía razón en negarse, y en los tres el arreglo
fue **acercar la señal a la pregunta del extractor**, no relajar el extractor.

**Al escribir o tocar un extractor, mirar su señal en el mismo movimiento.** Si
el extractor gana una guarda —una unidad, un formato, un valor mínimo, un
límite de palabra— la señal necesita la misma, o el próximo sitio que caiga en
el hueco para la cola.

### Cómo distinguirlo en treinta segundos

Un `NEEDS_FIX` por `source fields not extracted` puede ser un hueco real del
extractor o un invento de la señal, y **cierran igual**. Los separa la escala:

```
extraction_failed / source_provided
```

- `bottega`: **11 de 23 (47,8 %)** en `ambientes` → hueco real. La fuente lo
  publica y no lo sacamos.
- `brunetti`: **2 de 145 (1,4 %)** en `banos` y `precio` → señal equivocada en
  dos fichas sueltas.

Medido el 2026-09-10 sobre 234 agencias con resultado, **sólo dos** tienen esa
razón. O sea que el problema es real pero todavía no contamina la pasada: no
alcanza para romper el congelamiento, sí para que la ventana semántica revise
**todas las señales de campo juntas** en vez de una por vez.

---

## 3 septies. Cuándo un defecto de campo NO para la cola

Desde el 2026-09-13 el triage mira **radio y magnitud**, no sólo radio.

Antes, cualquier campo que la fuente publicara y el extractor no leyera paraba
las dos colas, porque el lector es código compartido. Eso está bien cuando el
campo se pierde en serio —`blanco propiedades` pierde 1.207 precios de 1.211—
y cuesta un ciclo entero de diagnóstico cuando es una ficha:

| agencia | falla | de |
|---|---|---|
| `conti` | 1 | 275 |
| `civeira` | 1 | 163 |
| `cocucci` | 1 | 152 |
| `brunetti` | 1 | 76 |

**La regla.** Un defecto de campo es menor —y la cola sigue— sólo si **cada**
campo fallado cumple las dos condiciones:

```
fichas fallidas <= 4   Y   fichas fallidas / provistas <= 2 %
```

Las dos, porque cada una sola miente: el porcentaje solo dejaría pasar 40 de
2.000, y el tope solo dejaría pasar 4 de 4.

**Alcanza con que un campo exceda para que el conjunto pare.** `christian arce`
pierde una ficha de `ambientes` pero nueve de `operacion`: mandan las nueve.

**Diferir por magnitud no es esconder.** El defecto se anota entero en
`AGENCY_DEFECT_QUEUE.jsonl` con su detalle —`superficie_total 1 de 152`— y la
agencia sigue cerrando `NEEDS_FIX`.

### Lo que nunca es menor

El chequeo de magnitud **no devuelve** en el lugar donde estaba: deja caer al
resto de los controles. Eso arregló un problema que existía antes y que nadie
había mirado: el defecto de campo era el **primer** chequeo de la función, así
que una ficha con un campo ilegible devolvía **antes** de evaluar colisiones de
identidad, enumeración incompleta o inventario faltante. Un defecto chico podía
tapar uno grave del mismo resultado.

### Y un control nuevo, que va primero que todo

**Si la segunda corrida vio menos propiedades que la primera, se para.** Sin
excepciones, sin importar la magnitud.

`carames` lo destapó: run1 enumeró 207 urls y run2 177, con 30 faltantes, y el
triage lo dejaba pasar diciendo *"el catálogo enumeró igual en las dos
corridas"*. No enumeró igual.

La causa era leer **el relato en vez del dato**: la diferencia de inventario se
deducía buscando las frases `inventories differ` o `not idempotent` entre las
razones, y ese resultado traía otra razón —se quedó sin presupuesto de tiempo—,
así que la deducción dijo que no había diferencia mientras
`comparison.missing_in_run2` decía 30.

Ahora se mira el número. Que a una corrida le falte tiempo explica **por qué**
faltan; no vuelve seguro publicar lo que quedó.

### Cómo revalidar el umbral

```bash
python scripts/replay_triage.py --comparar
```

Reclasifica todo el historial con las dos políticas y muestra qué paradas se
evitarían. El veredicto falla si alguna de las que deben parar deja de parar.

```bash
python scripts/patrones_menores.py
```

Agrupa los defectos chicos por campo y plataforma. Un defecto de una ficha no
para la cola, pero cuatro agencias perdiendo el mismo campo son un patrón —y
así se ve. Fue lo que mostró que `superficie_total` se pierde en `berardi`
(12 de 14) y `constant` (11 de 13), dos WordPress con el mismo síntoma que se
habían diagnosticado por separado.

---

## 3 octies. El gate de regresión: ¿lo nuevo pierde algo que lo viejo tenía?

```bash
python scripts/regression_gate.py
```

Compara la preingestión del 2026-09-03 —que es el universo del dry-run— contra
la certificación de esta pasada, campo por campo, y clasifica cada pérdida:

| clase | qué significa |
|---|---|
| `SOURCE_CHANGED` | la fuente dejó de publicarlo |
| `EXPLICADA_VALIDACION` | el extractor lo rechazó a propósito |
| `MOVIDA_DE_DIMENSION` | el dato sigue, en otro campo |
| `RETENIDA_WEB_AJENA` | la agencia entera quedó afuera; el dato no era suyo |
| **`UNEXPLAINED_LOSS`** | **teníamos el dato, hoy no está, y no hay motivo escrito** |

**Ninguna `UNEXPLAINED_LOSS` puede escribirse destructivamente.** Ésa es la
barrera: no llevar el número a cero a la fuerza, sino que ninguna pérdida sin
explicar llegue a producción.

**Al 2026-09-13: 0 sobre 14.931 propiedades comparables.** Las 273 que el gate
marcaba al principio eran de `arte propiedades`, cuya "web" es su perfil en el
portal `lujanprop.com.ar`: no eran pérdidas, eran la retención correcta de
inventario ajeno.

**Dos límites que conviene tener presentes.** El lado fresco se compara con el
resumen por agencia, no fila por fila, así que una pérdida dentro de una agencia
cuya cobertura global sigue en pie no se ve. Y sólo se comparan las agencias ya
certificadas: 14.931 propiedades de 58.427 mientras la pasada avanza. Hay que
volver a correrlo al final.

---

## 4. Dos workers

El reparto es **por host**, no por posición: la cortesía se le debe al sitio y
el limitador vive dentro de cada proceso, así que dos workers sobre el mismo
host pedirían al doble del ritmo acordado sin que ninguno se entere.

- Cada worker tiene su cerrojo (`...RUNNER.w0.lock`) y su progreso.
- Un STOP transversal escribe `AGENCY_CERTIFICATION_STOP.json` y **corta a los
  dos**. Esa bandera se borra sola al abrir.
- Nunca más de dos. Más procesos contra sitios de inmobiliarias chicas deja de
  ser paralelismo y pasa a ser una molestia para ellas.

---

## 5. Cerrojo huérfano

Un cerrojo sin proceso vivo bloquea la apertura. El reporte **ya comprueba el
PID**, así que la alerta sólo enciende cuando el proceso realmente no está: si
dice huérfano, se puede borrar el `.lock`.

Si el reporte no pudo comprobar el PID —lo dice en `proceso_existe: null`—
hay que hacerlo a mano antes de borrar nada:

```bash
powershell -c "Get-Process -Id <pid> -ErrorAction SilentlyContinue"
```

**Un latido viejo no es un cerrojo huérfano.** El latido se refresca cada
minuto desde un hilo aparte, pero una inmobiliaria puede tardar hasta tres
horas y un worker atascado en una lenta sigue vivo. Borrar su cerrojo pone dos
runners sobre la misma partición: los dos le piden a los mismos sitios al doble
del ritmo acordado y se pisan el checkpoint.

---

## 6. Líneas ilegibles en un artefacto

Señal de que dos procesos escribieron el mismo archivo sin append atómico.
`append_jsonl` usa `O_APPEND` con un solo `os.write`, así que no debería pasar;
si pasa, hay un escritor que no lo usa. Buscarlo antes de seguir: ese archivo
es la fuente de verdad de las certificaciones.

---

## 7. Un campo que falla mucho

```bash
python scripts/extraction_failures.py
```

Agrupa por familia y campo, no por campo suelto: un campo que falla en ocho
lugares distintos no es un problema, y ocho campos que fallan en el mismo lugar
son uno solo. `familias_con_falla_ancha` marca las familias donde la lectura
estructurada directamente no está ocurriendo.

El arreglo se valida en cuatro pasos, no en uno: test, fuente real, RUN1/RUN2,
y before/after sobre las candidatas.

---

## 8. Ventana semántica

Cuando hay varios cambios pendientes que tocan componentes compartidos:

1. Esperar a que **no haya certificación en vuelo**. Editar un archivo
   fingerprintado con la cola corriendo hace que se estampen huellas de código
   que no es el que se ejecutó.
2. Calcular el radio antes de aplicar:
   ```bash
   python -c "from scripts.agency_fingerprints import fingerprint_components; print(sorted(fingerprint_components('generico','generic/html_catalog')))"
   ```
   `shared/*` está en toda estrategia: transversal. `connector/<x>` sólo en esa
   familia.
3. Si comparten radio, van juntos: se paga una recertificación en vez de tres.
4. Aplicar, suite completa, medir before/after, preflight, reabrir.

**Nunca** reducir artificialmente una invalidación. Un módulo semántico fuera
de la huella produce certificaciones falsamente vigentes, y ya pasó tres veces.

---

## 8 bis. La familia "slugs en la raíz", medida antes de escribir la regla

Es la que más diferidas acumula y la que más fácil se arregla mal. El síntoma
es siempre el mismo: WordPress sin plugin inmobiliario, el conector cierra
`VARIANTE_NO_SOPORTADA`, enumera 0, y el sitio **sí** publica catálogo. Las
fichas cuelgan de la raíz, al lado de `/contacto/` y `/nosotros/`.

Al abrir la ventana va a dar ganas de escribir una regla corta. Estas son las
tres que ya se midieron contra la fuente y **no** sirven:

| Regla tentadora | Dónde se rompe |
|---|---|
| "leer `/wp-json/wp/v2/posts`" | contesta en 1 de las 7. attaguile y d'onofrio 404, carlos castaño 403, pozzobon 401; cintia fonzo y csgestion contestan 0 |
| "leer el `post-sitemap`" | existe en 4 de 7 — y en csgestion sus 105 entradas son **el blog**, no el catálogo |
| "las entradas (`post`) son las fichas" | cierto en córdoba, falso en csgestion, misma plataforma y mismo síntoma |

Lo que queda es mirar la ficha, y por eso la familia es cara.

Hay una sub-variante que sí es barata y conviene hacer primero, separada: la de
los slugs **con marcador**. En `estela d onofrio` la ruta lleva `-ficha-` adentro
(`/casa-en-venta-en-colegiales-ficha-edp2409`), que se reconoce sin abrir nada.
Empezar por ésas paga varias agencias sin pedir criterio nuevo; los slugs
realmente pelados —`/san-luis-1038-venta/` de córdoba, `/montevideo-745-casa-3-dormitorios`
de urbanorosario— son los que obligan a decidir por contenido y van después.

Ninguna de las 7 tiene filas productivas hoy salvo `carlos castaño` (39), así
que la familia entera es inventario que todavía no está, no inventario en
riesgo de romperse.

---

## 9. Regenerar los artefactos de datos

En este orden, porque cada uno consume al anterior:

```bash
python scripts/geo_coverage_audit.py && python scripts/property_quality_gate.py && python scripts/api_contract.py && python scripts/api_snapshot.py
```

La snapshot de la API es **derivada y desechable**: se reconstruye entera y no
es fuente de verdad de nada.

---

## 10. Lo que NO se hace sin autorización

Escrituras productivas, migraciones, RLS, borrado de datos productivos, `git
push`, merge remoto, deploy, borrar repos o proyectos remotos, DNS, servicios
pagos, exponer o rotar secretos.

Ante cualquiera de esos: preparar diff, backup, rollback, números exactos y
riesgos, marcarlo `WAITING_USER_AUTHORIZATION`, y **seguir con otra cosa**.
