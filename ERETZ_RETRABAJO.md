# El 94,8 % del trabajo es repetido, y 329 de 330 repeticiones son evitables

**Medido el 2026-09-15 sobre las últimas 24 h. Nada aplicado. `database_writes: 0`.**

---

## 1. La medición

```
TOTAL_CERTIFICATION_RUNS        348
NEW_CERTIFICATIONS               18
RECERTIFICATIONS                330      94,8 %

PROPERTIES_NEWLY_CERTIFIED    2.609
PROPERTIES_REPROCESSED       20.681

NEW_WORK_RATIO                 11,6 %    tiempo nuevo / tiempo certificando
WORKER_PRODUCTIVE_UTILIZATION  10,1 %    tiempo nuevo / tiempo de pared

horas de trabajo nuevo           4,8
horas de trabajo repetido       36,8
```

### Causas, contadas y no estimadas

| causa | veces | clase |
|---|---:|---|
| `MANUAL_RESTART` | **316** | operacional |
| `STOP_RETRY` | 13 | operacional |
| `FINGERPRINT_INVALIDATION` | **1** | legítima |

**Una sola repetición en 24 horas fue legítima.**

`MANUAL_RESTART` significa acá algo preciso: la corrida anterior terminó
`NEEDS_FIX`, la nueva terminó `NEEDS_FIX`, y **enumeró exactamente lo mismo**.
Volver a ejecutarla no produjo información nueva.

---

## 2. Por qué pasa

`is_current_result()` devuelve `False` para cualquier estado que no sea
terminal. `NEEDS_FIX` no lo es, así que **las 62 agencias en ese estado vuelven
a la cola en cada arranque**, y el arranque ocurre después de cada paro.

De esas 62, **53 tienen una diferida firmada**: su defecto ya fue
diagnosticado contra la fuente, escrito y deliberadamente postergado a la
ventana semántica.

```
costo de repetir esas 53 una sola vez:  10,4 h de worker
```

Con dos workers parando y arrancando a lo largo del día, esas 10,4 horas se
pagan una y otra vez. Ahí están las 36,8.

El diseño era correcto cuando cada paro terminaba en un arreglo: reejecutar
comprobaba si el arreglo funcionó. **Bajo el freeze no se arregla nada**, así
que la reejecución comprueba que nada cambió — que es justo lo que ya sabíamos.

---

## 3. El cambio propuesto

No aplicado. `run_agency_certification_queue.py` no está fingerprintado, pero
cambiar qué se certifica en mitad de la pasada es una decisión que no tomo solo.

La regla que falta es la del §21: *resultado stale por un componente no
relacionado → no ejecutar*.

```python
def is_current_result(previous, record, diferidas):
    status = previous.get("status")
    if status in TERMINAL:
        ...                      # como hoy
    # NUEVO: un NEEDS_FIX ya diagnosticado y con la misma huella no cambia.
    if status == "NEEDS_FIX":
        firma = previous.get("strategy_fingerprint")
        actual = strategy_fingerprint(connector, strategy)
        if firma and firma == actual and tiene_diferida_firmada(previous, diferidas):
            return True          # vigente: reejecutarla no produce informacion
    return False
```

Las tres condiciones se exigen juntas y cada una cubre un riesgo distinto:

- **misma huella** — si el código que la certificó cambió, hay que rehacerla;
- **diferida firmada** — alguien miró el defecto contra la fuente y lo escribió;
- **estado `NEEDS_FIX`** — no toca nada de lo terminal.

### Lo que NO cubre, a propósito

Una fuente puede cambiar sola: `baron` pasó de enumerar 0 a enumerar 182 sin
que tocáramos nada, y `carlos castaño` cambió de plataforma entre agosto y
septiembre. Con esta regla, esos cambios tardarían más en verse.

La mitigación razonable es un **vencimiento**: una diferida firmada vale, por
ejemplo, 72 horas, y después la agencia vuelve a la cola una vez. Eso conserva
la detección de cambios de fuente y elimina igual la mayor parte de la
repetición, porque hoy se repiten decenas de veces por día y no una cada tres.

---

## 4. Lo que se recupera

```
hoy:      4,8 h utiles  +  36,8 h repetidas
posible:  ~40 h utiles de las mismas 48 h-worker disponibles
```

El número de horas recuperadas es un **techo**: supone que todas las
repeticiones evitables desaparecen, y la mitigación por vencimiento devuelve
algunas. Pero incluso con la mitad, el trabajo útil diario se multiplica por
cuatro o cinco **sin comprar nada**.

---

## 5. La decisión de infraestructura

El §17 pide decidir sobre trabajo nuevo real.

```
NEW_WORK_RATIO   11,6 %
```

**No comprar máquinas.** Una segunda máquina hoy agregaría 24 h-worker que se
gastarían, en su mayoría, repitiendo las mismas 53 agencias diagnosticadas.
Duplicar una máquina que repite trabajo duplica la repetición.

El orden correcto es: eliminar la repetición, volver a medir, y **recién ahí**
preguntar si falta capacidad. Con ~40 h útiles diarias la pregunta puede ni
llegar a plantearse.

---

# Addendum del 2026-09-14: el replay, y dos defectos que encontró

**`database_writes: 0`.** El cambio está aplicado en disco y los workers lo
cargan en el próximo relanzamiento. La suite completa pasa: **1794 tests**.

## El replay, sobre historial real

No es una estimación. Cada repetición de las últimas 24 h se volvió a juzgar
con el estado que el sistema tenía **en ese momento** —una diferida escrita
después de una corrida no podría haberla evitado, y no se cuenta a favor— y se
sumó su duración medida.

| | ANTES | DESPUÉS |
|---|---:|---:|
| `TOTAL_RUNS` | 350 | 121 |
| `NEW_RUNS` | 19 | 19 |
| `RECERTIFICATIONS` | 331 | 102 |
| `WORKER_HOURS` | 41,6 | 22,8 |
| `NEW_WORK_RATIO` | 5,4 % | 15,7 % |

229 recertificaciones evitadas sobre 48 agencias. **18,8 h de worker liberadas
por día, el 45 % del tiempo de certificación.**

## Los dos defectos que el replay encontró antes de activar nada

La primera versión del replay medía **4,0 h**, no 18,8. Ese hueco no era ruido:
eran dos defectos en el cambio que yo había escrito, y los tests no los veían.

### 1. `diferidos()` descartaba la fecha

La función proyectaba `diagnostico`, `componente` y `radio`, y tiraba `cuando`.
Entonces toda diferida llegaba a `diferida_vigente()` sin fecha, se la
rechazaba por no poder saber si había vencido, y **el cambio no habría ahorrado
una sola hora en producción** — mientras los quince tests pasaban, porque
construían el diccionario a mano con la fecha adentro.

Se coló porque el replay medía una **copia** de la lógica y la copia leía la
fecha del disco. Ahora el replay importa `diferida_vigente` de producción, y la
única forma de que difieran es que alguien las separe a propósito.

### 2. El TTL se medía contra la firma, no contra la última mirada

Anclado en la firma, una diferida de hace 200 h queda vencida para siempre, y
su agencia vuelve a correrse **en cada pasada de la cola**. Medido: 112
corridas en 24 h sobre 20 agencias, 14,6 h de worker.

De esas 112, **108 terminaron idénticas** — mismo estado, misma huella, mismo
enumerado. Las otras 4 movieron entre 1 y 4 avisos, que es rotación de catálogo
y no un hallazgo.

Anclado en la última observación real, el TTL hace lo que se le pidió: obliga a
volver a mirar cada 72 h —24 h si la firma es crítica—, **una vez por ventana
en lugar de una vez por pasada**. `previous` siempre es una corrida realmente
ejecutada, porque las salteadas no escriben resultado.

## Lo que el cambio NO toca

- `run_agency_certification_queue.py` no es componente de ninguna huella. Los
  26 componentes que entran en alguna están listados y ninguno es este archivo.
- 156 certificaciones terminales comparadas contra la huella viva: **cero
  cambian por esta modificación**.
- Aparecen 5 huellas distintas, todas `BLOCKED_EXTERNAL` certificadas entre el
  2 y el 8 de septiembre. Son deriva previa, de antes de hoy, y ya se
  recertificaban igual. No se tocan acá: es otro trabajo.

## Activación

Se pidió el paro por bandera, que los workers leen al empezar cada agencia. No
se mató ninguno: terminan la que tienen entre manos, sueltan su cerrojo solos y
se relanzan iguales.

---

## Lo que quedó después del cambio, y una trampa que casi pisamos

Con el cambio activo la cola tomó **797 agencias en vez de 847**: 50 con
diferida vigente que ya no se repiten. El resto de la repetición se desglosa
así, contado:

| motivo | corridas | horas | agencias |
|---|---:|---:|---:|
| diferida vencida por TTL | 112 | 14,6 | 20 |
| diferida escrita después de la corrida | 56 | 2,1 | 19 |
| **`NEEDS_FIX` sin diferida** | **32** | **12,6** | **6** |
| diferida sin firma | 14 | 3,2 | 2 |

Las primeras dos las resuelve el TTL anclado. La tercera no: son seis agencias
con un defecto real y **nadie escribió su diagnóstico**. `brunetti propiedades`
llevaba 23 corridas de ~1,4 h —unas 32 h de worker en un día— siempre
`NEEDS_FIX`, siempre enumerando exactamente 430 de 430.

### El bloqueo era una sola ficha

`brunetti` está bloqueada por `source fields not extracted: banos`, con
`extraction_failed = 1`. **Una ficha de 430.** La enumeración está intacta:
cobertura 1.0, idempotente entre corridas, misma firma de contenido, cero
colisiones.

Medido sobre las 63 `NEEDS_FIX` vigentes: **19 están bloqueadas sólo por campos
no extraídos, y 6 de esas fallan en ≤2 % de sus fichas.**

### La trampa

La lectura cómoda era "una ficha donde el campo no aplica, difiero las seis y
recupero 12,6 h". Se descargaron las seis fichas que fallan, una por una, y
**no son la misma historia**:

| agencia | ficha que falla | qué se vio al descargarla |
|---|---|---|
| brunetti | `banos` | es un **terreno**: no tiene baños. El campo no aplica |
| civeira | `banos` | la ficha **dice "2 baños"**. Falla nuestro extractor |
| conti | `descripcion` | la ficha **trae descripción**. Falla nuestro extractor |
| fdc | `moneda` | dice `USD 111.111.111` y "Vendida": precio de relleno |
| cocucci | `superficie_total` | el valor sólo está en la prosa, como `1.367.26 m` — dos puntos, no parseable |
| crm | `tipo_propiedad` | **no se aisló por qué falla** |

Deferir las seis con el mismo texto habría sido falso en tres de ellas.

Se difirieron **cinco**, cada una con su diagnóstico propio y su url exacta
—dos dicen literalmente "es un defecto nuestro, el arreglo está bajo freeze"—.
**`crm propiedades` queda afuera**: sin diagnóstico no se difiere, y ésa todavía
no lo tiene.

La cola pasó de 50 a **54** agencias salteadas; **2,3 h de worker por pasada**
que dejan de gastarse.

### Lo que sigue abierto

- **16 diferidas no tienen firma** y por eso no cuentan para nada. Son de antes
  del mecanismo de firmas.
- **20 agencias, 14,6 h**, seguían cayendo por TTL vencido bajo el ancla vieja.
  Con el ancla nueva se revisan una vez por ventana, no una por pasada.
- `crm propiedades` necesita que alguien mire su ficha.
