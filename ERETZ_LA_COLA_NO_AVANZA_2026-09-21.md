# La cola corrió 12 horas y no cerró ni una agencia nueva

**2026-09-21 · `database_writes: 0`**

Fui a reportar que el rendimiento había mejorado —14 a 19 certificaciones por
hora contra el 1,62/h medido antes— y al separar qué eran esas corridas el
número se dio vuelta.

| | |
|---|---:|
| corridas escritas en ~12 h | **129** |
| agencias distintas tocadas | **46** |
| agencias que cerraron por primera vez | **0** |
| veces que se certificó `adrian ghio` | **7** |

33 de esas 46 empiezan con **A**. La cola lleva medio día recertificando el
principio del abecedario.

## Por qué, y es consecuencia de mi propio trabajo

La regla que decide si un cierre sigue vigente lo dice sin vueltas
(`run_agency_certification_queue.py`):

> «La huella se comprueba igual, más abajo: si el código cambió, hay que
> rehacerla aunque el defecto esté diagnosticado.»

Es correcta: una certificación describe lo que ese código vio en esa fuente.
Si el código cambió, no dice nada sobre el código de hoy.

Pero **cada arreglo que toca código compartido invalida el padrón entero**, y
hoy hice varios, uno tras otro:

| cambio | componente de la huella |
|---|---|
| paginación de Tokko | `connector/tokko` |
| catálogos partidos de Tokko | `connector/tokko` |
| `url_normalizada` en `to_payload` | `shared/models` |
| provincia que no es una provincia | `shared/base`, `shared/geografia` |
| la provincia supuesta no veta la ciudad | `shared/base` |
| guardián de forma, dos concesiones | `generic/common` |
| coordenada en JSON | `connector/wordpress` |
| corte en «Fecha de entrega» | `connector/tokko` |

Cada uno reinició el ciclo. Medido antes de empezar la tanda: **275 de 275
certificaciones comparables ya tenían la huella caduca, cero vigentes**. Usé
ese dato para justificar que tocar `shared/*` «no costaba recertificación
adicional» —y era cierto para *ese* cambio—, pero lo que no medí es que
encadenar ocho cambios mantiene el padrón permanentemente caduco.

**La cola no está rota. Está haciendo exactamente lo que se le pidió.** Lo que
falla es la secuencia en la que trabajé.

## Lo que esto NO significa

No significa que los arreglos no valieran la pena. Lo que evitaron está
medido, y es mucho más que 12 horas de cola:

- la paginación de Tokko: **~6.445 propiedades**, el 24 % del catálogo, que se
  habrían certificado como completas con 20 fichas cada una;
- los catálogos partidos: **291 propiedades** invisibles en 10 agencias;
- la provincia supuesta: **3.888 propiedades** que salían publicadas sin
  ninguna geografía;
- el guardián: **6 propiedades reales** de una agencia que quedaba en cero;
- la geometría: **36.281 municipios** y **45.551 departamentos** que existían y
  no se publicaban.

Certificar rápido sobre código equivocado no es avanzar: es acumular
certificaciones que habría que rehacer igual, pero sin saberlo.

## La decisión, y la tomo

**Freno los cambios sobre código compartido y dejo drenar la cola.**

Con 766 pendientes y el ritmo bruto observado —14 a 19 corridas por hora con
dos workers—, una pasada completa sin interrupciones son unas **45 a 55 horas
de reloj**. Ese número sólo vale si nadie vuelve a tocar la huella mientras
corre.

Lo que sí se puede hacer sin frenarla, porque no entra en ninguna huella:

- artefactos y auditorías (`geo_coverage_audit`, `artefacto_por_propiedad`,
  `api_contract`, `api_snapshot`);
- el registro de fuentes y de identidad;
- triaje y relanzador (`defect_triage`, `relanzar_la_cola`);
- frontend, API y sus pruebas;
- documentación.

Y lo que hay que juntar en **una sola tanda** antes de volver a tocar código
compartido, en vez de ir de a uno:

1. **`Terreno NNN m²` pegado al barrio: 380 propiedades en 54 agencias.**
   Apareció mirando el autocompletado —`Cordoba Capital Terreno 33729 m²`
   compitiendo con `Córdoba` como sugerencia— y es la misma forma que
   «Fecha de entrega»: el barrio está bien y se le pegó el campo siguiente.
   `Banfield Oeste Terreno 358 m²`, `Centenario Terreno 10466 m²`,
   `Añelo Terreno 20000 m²`. Recuperables cortando ahí.
2. los 1.022 barrios que son prosa recortada —la familia que **no** se
   arregla cortando en una etiqueta—;
3. las 32 ciudades de Jujuy escritas en el campo `provincia`;
4. lo que aparezca de los paros que la cola encuentre de acá en adelante.

Para dimensionar la primera contra la que ya se arregló: «Fecha de entrega»
son 1.242 propiedades en 64 agencias, y ese corte ya está aplicado —sólo
falta que la cola vuelva a pasar—.

## Cómo saber si esto se repite

La señal es directa y no hace falta ninguna herramienta nueva: **agencias que
cierran por primera vez, por hora**. Si es cero durante horas mientras la cola
escribe resultados, la cola está recertificando y no avanzando.

```bash
python scripts/de_donde_falta_la_geografia.py
```

no responde esto. La consulta que sí lo responde está en esta bitácora y
convendría que fuera una herramienta, pero no la escribo ahora: sería
exactamente el tipo de trabajo que me llevó a no mirar el número correcto
durante doce horas.
