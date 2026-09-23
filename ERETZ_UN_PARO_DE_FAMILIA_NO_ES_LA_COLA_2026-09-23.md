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
