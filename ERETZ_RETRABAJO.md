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
