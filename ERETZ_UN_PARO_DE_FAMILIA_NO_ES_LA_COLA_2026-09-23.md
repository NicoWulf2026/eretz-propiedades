# Un paro de familia detuvo el 100 % de la cola durante 34 horas

**2026-09-23 · `database_writes: 0`**

El 2026-09-21 la cola paró esperando la firma de `d aria` y no volvió a
avanzar hasta 34 horas después. Nadie hizo nada mal: el paro estaba bien
puesto, el relanzador hizo exactamente lo que dice su regla —no relanzar sobre
un paro sin diagnosticar— y el fail-closed funcionó.

Lo que estaba mal era el **alcance**.

## Los números

| | |
|---|---:|
| paros STOP en todo el historial | **613** |
| de radio `FAMILIA` | **596** (97,2 %) |
| de radio `COMPARTIDO` | **17** (2,8 %) |

Y una familia no es la cola. Sobre las **791 agencias** de la cola `ready` de
hoy:

| conector | agencias | de la cola | sigue corriendo si esa familia para |
|---|---:|---:|---:|
| `generico` | 366 | 46,3 % | **53,7 %** |
| `tokko` | 299 | 37,8 % | **62,2 %** |
| `wordpress` | 114 | 14,4 % | **85,6 %** |
| `wasi` | 12 | 1,5 % | **98,5 %** |

Detener el 100 % de la cola por sospechar de una familia es desproporcionado
en el 97 % de los paros. En el caso de `wasi`, se paraliza el 98,5 % de la
cola por sospechar del 1,5 %.

## Qué cambia, y qué no cambia

**No cambia el fail-closed.** La familia sospechada no se toca hasta que su
paro tenga una diferida firmada, escrita después del paro. No se certifica
nada con el código sospechado, no se relaja ningún umbral, no se firma nada
automáticamente que no se firmara antes.

**Cambia el alcance.** Un paro `FAMILIA` con conector conocido ahora relanza
la cola con `--excluir-conector <familia>`. Las otras familias avanzan.

Tres casos siguen deteniendo todo, a propósito:

- **`COMPARTIDO`** — sospecha del código que todas las familias comparten.
  Excluir una sola no acotaría nada.
- **Un paro sin `conector` anotado** — sin saber *qué* familia, «acotar» sería
  adivinar. Las banderas viejas no traen el campo.
- **Una bandera ilegible** — ilegible es peor que ausente.

## Las tres piezas

**1. `pedir_paro` anota el conector.** Es lo que convierte un radio `FAMILIA`
—una categoría— en una familia concreta. Sin esto el relanzador sabe que hay
que sospechar de «una familia» y no de cuál.

**2. `run_agency_certification_queue.py --excluir-conector`** (repetible)
filtra la cola por familia antes de ordenarla. Si la exclusión deja la cola
vacía, el proceso corta con un mensaje en vez de arrancar en silencio sobre
nada.

**3. `relanzar_la_cola.py` decide con `plan()`** y escribe
`ERETZ_FAMILIAS_DETENIDAS.jsonl`.

Ese archivo es la parte que no se ve y sin la cual todo esto sería un
agujero. **La bandera de paro es efímera**: el runner la borra al arrancar
(«una bandera de una corrida anterior no puede frenar la siguiente»). Sin un
registro propio, el primer relanzamiento consumiría el paro y el siguiente
volvería a correr la familia sospechada como si nada hubiera pasado. Eso no
sería acotar el fail-closed: sería perderlo.

## La otra mitad: que no vuelva a pasar 34 horas sin que nadie se entere

Acotar el radio reduce el costo de un paro, pero no arregla la ceguera. Y el
propio acotamiento abre una ceguera nueva: como el relanzamiento consume la
bandera, el vigilante vería *workers vivos, ninguna bandera* y diría **OK**
mientras `generico` —el 46,3 % de la cola— lleva un día sin tocarse. Sería el
mismo incidente, más silencioso y más difícil de ver.

Por eso `vigilante_de_paros.py` gana un estado:

    FAMILIA_DETENIDA    una familia lleva más de 12 h sin diferida firmada

Alerta como los otros dos estados que alertan, se deduplica por el **conjunto**
de familias detenidas —si aparece una segunda, la clave cambia y vuelve a
avisar— y recuerda cada hora mientras siga sin resolverse. Por debajo del
umbral no interrumpe a nadie, pero la familia igual se imprime y queda en el
estado: dentro del umbral no es una urgencia, es información.

El umbral es 12 h y no los 30 min de un paro total, a propósito: con el resto
de la cola avanzando, una familia detenida es un problema de días, no de
minutos, y un aviso que llega demasiado seguido es un aviso que se aprende a
ignorar.

## Lo que queda abierto

Una familia puede quedarse detenida **para siempre** si nadie firma su
diagnóstico. Eso es deliberado —es el fail-closed— pero ahora es visible en
vez de manifestarse como una cola que no avanza. `diferir_por_precedente`
cubre el caso frecuente: tres de cada cuatro agencias en `NEEDS_FIX` sin
diferida comparten firma con una que sí la tiene.

## Tests

- `tests/test_relanzar_la_cola.py` — 10 tests nuevos: `FAMILIA` con conector
  relanza excluyendo esa familia; `COMPARTIDO` sigue deteniendo todo;
  `FAMILIA` sin conector también; la familia sigue excluida cuando la bandera
  ya no está; una diferida firmada después la reincorpora; el dry-run no
  escribe; la exclusión llega al comando del worker.
- `tests/test_orden_de_cola.py` — 3 tests: excluir una familia deja pasar a
  las demás, no distingue mayúsculas, y una familia que no existe no saca a
  nadie.
- `tests/test_vigilante_de_paros.py` — 4 tests: una familia detenida hace
  horas no puede leerse como OK; dentro del umbral no alarma; con diferida
  firmada deja de contar; la deduplicación es por conjunto.

## Lo que pasó en producción, la primera noche

**Funcionó para lo que fue hecho.** A las 12:29 del 2026-09-23 `alagna`
detuvo `generico`; a las 14:19 `austral` detuvo `wordpress`. Sin nadie
mirando, el relanzador siguió con las otras 311 agencias: `### worker 0 de 2:
151 de 311 inmobiliarias ###`. Con la regla anterior la cola habría quedado
entera parada desde las 12:29.

**Y mostró dos agujeros.**

### 1. Una familia esperaba una firma sobre un defecto que ya no existía

El paro de `alagna` tenía razón: la fuente publica `addressLocality: Rosario`
en el JSON-LD de las 229 fichas y extraíamos 0. La causa eran dos defectos
apilados en `_de_json_ld`:

- el sitemap publica `/local-comercial-...-centro` y la página declara
  `rel="canonical"` con el id al final, `...-centro-8408054`. El filtro de
  identidad comparaba sólo contra la url pedida, no encontraba ningún nodo y
  **descartaba el JSON-LD entero**;
- `RealEstateListing` describe el aviso, y la dirección está en su
  `mainEntity`, un `Place` que no se miraba.

Arreglado y verificado contra la fuente. Pero el paro seguía en pie: esperaba
una diferida firmada, y 366 agencias esperaban con él.

Ahora el relanzador compara la **huella del código** que el paro sospechaba
—`strategy_fingerprint`, anotada por el triaje— con la huella de hoy. Si
cambió, la familia se vuelve a **probar**: no se certifica nada, la cola la
corre con el código nuevo y el triaje decide de cero. Si el defecto sigue,
para otra vez con la huella nueva, y ese paro sí espera su firma. Lo que se
acorta es la espera sobre evidencia vieja, no la exigencia sobre la nueva.

Sólo para `FAMILIA`. Un paro `COMPARTIDO` sospecha del código común, y la
huella de una estrategia cambia también cuando cambia sólo su archivo propio.

### 2. `COMPARTIDO` por defecto detuvo todo

A las 18:25 `inmobiliaria varesse` (`wasi`) paró con `sin_determinar /
COMPARTIDO`: «second run is not idempotent». La cola entera quedó detenida
hasta las 10:04 del día siguiente.

**Corrección sobre la cifra.** Primero escribí «15 h 30 min detenida», que
es el tiempo de reloj entre el paro y el relanzamiento. El registro del
relanzador —corre cada diez minutos— tiene un hueco de 21:14 a 08:34: la
máquina estuvo apagada esas once horas y veinte. Con la máquina encendida
la cola estuvo bloqueada **4 h 19 min** (18:25–21:14 y 08:34–10:04). El
argumento no cambia —un campo de una ficha detuvo 791 agencias—, pero el
número que lo acompañaba estaba inflado casi cuatro veces.

Lo que había de verdad: **91 urls iguales, 90 fichas idénticas, y una ficha
con `dormitorios` en `None` en la primera corrida y `3` en la segunda.** La
fuente, bajada tres veces a la mañana, publica «Habitaciones: 3» siempre. Es
la firma de un aviso editado entre corridas o de una respuesta parcial, no de
un extractor que cambia de opinión.

El triaje no pudo atribuirlo y cayó en `COMPARTIDO` porque esa es su regla:
«no encontrar razones para parar no es tener razones para seguir». La regla
es correcta —sin atribución no hay forma de acotar— y no se toca. Se firmó el
diagnóstico, verificado contra la fuente.

Pero deja escrito **cuál es ahora el riesgo dominante**: no los paros
`FAMILIA` —acotados y, si el código cambia, reintentados— sino los
`COMPARTIDO` por defecto, donde un campo opcional de una sola ficha detiene
791 agencias. `maximiliano castanos`, veinte minutos antes, había parado igual
y se certificó sola en el reintento: 44 de 44, idéntica.

Queda como trabajo siguiente distinguir, dentro de «no idempotente», el caso
de **una sola ficha con un campo que pasa de ausente a presente** —que la
fuente puede producir sola— del caso de inventario o contenido inestable a
escala, que sí sospecha de nosotros.

