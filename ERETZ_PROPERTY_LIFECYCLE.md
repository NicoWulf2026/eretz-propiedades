# ERETZ — Ciclo de vida de una propiedad

Cuándo una propiedad está activa, cuándo se retiene y cuándo —recién— se da de
baja.

Estado: **modo observación.** La regla está diseñada y **no encendida**, a
propósito. Sin escrituras productivas.

---

## 1. La regla que ordena todo

**Una propiedad que hoy no aparece NO es una baja.**

Puede ser un timeout, un listado paginado a la mitad, un sitio que cambió de
plantilla, o un aviso que pasó a otra página. Ya tenemos la prueba de que esto
no es teórico: anoche `alagnapropiedades.com.ar` devolvió 210 fichas en una
corrida y 209 en la siguiente, con media hora de diferencia. **La ficha que
"desapareció" responde HTTP 200 cuando se la pide de nuevo.**

Con la regla de bajas encendida y una sola ausencia como criterio, esa
propiedad se habría dado de baja esa noche.

En un agregador el error se ve enseguida: la inmobiliaria llama para preguntar
por qué no está su propiedad.

---

## 2. Estados

| Estado | Significa | Se muestra |
|---|---|---|
| `ACTIVE` | vista en la última corrida confiable | sí |
| `POTENTIAL_INACTIVE` | ausente en una corrida confiable | **sí** |
| `INACTIVE` | ausente en 3 corridas confiables seguidas | no |
| `REACTIVATED` | volvió a aparecer tras estar ausente | sí |
| `REMOVED` | la fuente devuelve 404/410 en su propia URL | no |

`POTENTIAL_INACTIVE` **sigue publicándose**. Es una anotación, no una baja: el
propósito del estado es acumular evidencia, no esconder inventario.

`REMOVED` es el único estado que no necesita esperar tres corridas, porque no es
una inferencia: la fuente contesta explícitamente que esa ficha ya no existe.

---

## 3. Qué corrida cuenta como evidencia

Una ausencia **sólo cuenta** si la corrida era confiable. No cuenta si:

- la fuente no respondió;
- la enumeración quedó incompleta o la paginación se interrumpió;
- el presupuesto se agotó antes de terminar;
- el connector cayó a una estrategia de respaldo.

El runner ya no emite ausencias cuando no puede confiar en lo que vio, y esa es
la mitad del trabajo. La otra mitad es no contar dos ausencias del mismo
episodio como si fueran dos observaciones independientes.

---

## 4. Antes de encender: dos números

`scripts/evaluate_deletions.py` existe para responderlos y **no desactiva
nada**:

1. **Cuántas propiedades desactivaría hoy la regla, y de qué fuentes.**
2. **Cuántas de esas reaparecieron después de "desaparecer".**

**La segunda es la que decide.** Una regla que da de baja algo que reaparece a
la corrida siguiente es una regla que borra inventario vivo.

Criterio propuesto para encenderla: la tasa de reaparición tras 3 ausencias
confiables tiene que ser **cercana a cero y medida**, no supuesta. Si una parte
apreciable reaparece, el umbral sube o la regla no se enciende.

---

## 5. Estado de implementación — honesto

| Pieza | Estado |
|---|---|
| `source_status` en la propiedad | existe, default `activa` |
| Detección de cambios (`SIN_CAMBIOS` / `NUEVA` / `MODIFICADA`) | **funciona** |
| `stable_signature` / `firma_de_columnas` | **funciona** |
| Anotación `POTENTIAL_INACTIVE` | existe en modo observación |
| Máquina de estados completa | **NO implementada** |
| `INACTIVE` / `REACTIVATED` / `REMOVED` | **NO implementados** |
| Regla de bajas encendida | **NO**, deliberadamente |

Es la brecha más grande del backend después del quality gate, y la única que
prefiero dejar abierta: encenderla mal borra inventario real, y el costo de
esperar es cero.

---

## 5 bis. Los dos números, medidos el 2026-09-21

Corrido `scripts/evaluate_deletions.py` sobre el histórico:

| | |
|---|---:|
| ausencias comparables | **1.565** |
| se desactivarían hoy | **0** |
| volvieron a aparecer | **0** |
| ausencia consecutiva más larga | **1** |

**El cero de la segunda columna no dice que la regla sea segura: dice que
nunca tuvo ocasión de dispararse.** Ninguna propiedad estuvo ausente tres
corridas seguidas, así que la tasa de reaparición tras tres ausencias —el
número que decide— está **indefinida, no en cero**. Leerlo al revés sería
exactamente el error que este documento existe para evitar.

Además hay **110.368 ausencias no comparables** (91.367 de
`TOKKO_ROLLOUT_FULL`, 19.001 de `WP_ROLLOUT_FULL`) anotadas con la clave
vieja del checkpoint: ninguna puede cruzarse con una propiedad de hoy.

### Y el reloj no está corriendo

Lo que importa más que los números: **el proceso que corre hoy no genera la
evidencia que hace falta.**

- Ningún paquete de la cola de certificación escribe `absences_runN.jsonl`:
  son **0 de 429**.
- El registro de corrida sí anota `ausentes`, en 219 paquetes, 60 de ellos
  con ausencias — pero es un **conteo**, no la lista de cuáles.

Sin las identidades no se puede acumular «la misma propiedad ausente tres
veces seguidas», que es la única forma de la evidencia. Esperar no alcanza:
por muchas pasadas que dé la cola, la racha nunca sube de cero.

El detalle sí se escribe en el camino de `run_rollout.py` —`esc_aus`—, y se
pierde en el camino del certificador. Es una diferencia entre dos caminos,
no una pieza que falte inventar.

---

## 6. Qué falta

1. ~~Correr `evaluate_deletions.py` y publicar los dos números.~~ **Hecho,
   sección 5 bis.** El resultado cambia el orden de lo que sigue: antes de
   implementar la máquina de estados hay que **empezar a registrar qué
   propiedades faltan**, porque hoy no se registra y sin eso no hay nada que
   evaluar.
2. Implementar la máquina de estados, con las ausencias contadas sólo sobre
   corridas confiables.
3. Detección de `REMOVED` por 404/410 en la ficha propia.
4. Recién entonces, decidir si se enciende.
