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

### Y hay una segunda mitad, que encontré después y es peor

Cada vez que cambié código compartido, **reinicié los workers** para que
tomaran el código nuevo. Parecía obviamente correcto —un worker con el módulo
viejo cargado escribiría certificaciones con la huella nueva y la conducta
anterior—. Lo que no miré es qué le hace el reinicio a la posición:

```
w0   global_cursor 4    queue_size 413    started_at 2026-09-20T22:52
w1   global_cursor 5    queue_size 378    started_at 2026-09-21T01:42
```

**w0 lleva seis horas corriendo y avanzó cuatro posiciones. w1, tres horas y
cinco.** Los `started_at` son exactamente mis reinicios, y el cursor arranca
de cero en cada uno.

Así que no es sólo que las certificaciones queden caducas: es que cada
reinicio vuelve a empezar por el principio del abecedario, vuelve a encontrar
las mismas agencias caducas, y las vuelve a hacer. Reinicié cinco veces hoy.
Las dos cosas se multiplican.

**Dejar drenar la cola significa también no reiniciarla.** Eso no estaba en mi
decisión de hace un rato y es la mitad que importa: sin esto, congelar el
código no alcanza.

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
4. **Formas de ficha que el patrón no reconoce: 12 agencias, 10 formas.**
   Medido con `que_forma_tienen_sus_fichas.py` sobre las 47 agencias
   `NEEDS_FIX` con cero enumeradas: 44 respondieron y 12 publican enlaces de
   ficha que no vemos. La forma más grande es `/<slug-con-tipo>` —48 urls en
   3 agencias, `urbanorosario.com.ar/pte-roca-1438-a`—, que es también la más
   difícil: un slug suelto en la raíz se parece a cualquier página.

   El arreglo no es aflojar el patrón global —arrastraría páginas
   institucionales— sino extender la forma verificada por fuente, que ya
   existe. Y ese camino ahora es más seguro que antes: el guardián que valida
   ficha por ficha es lo que lo hace viable, y acaba de quedar calibrado con
   las dos concesiones de `alma di matteo`.

5. **La plataforma SOM (`apmovil.som.com.ar`): 2 agencias medidas.**
   `amud` y `chenlo`. Tiene API propia y paginada, pero su parámetro
   `codigoInmobiliaria` **no filtra**: devuelve las 16.822 propiedades de toda
   la red. El conector no se puede escribir hasta resolver la atribución, o
   le adjudicaríamos propiedades ajenas a cada agencia.

6. lo que aparezca de los paros que la cola encuentre de acá en adelante.

### Lo que el sondeo descartó

Sondeadas las 51 agencias genéricas con 0–2 fichas enumeradas, buscando
familias nuevas: 4 inaccesibles, 3 wordpress, 2 tokko, 2 SOM, y el resto sin
plataforma reconocible. **No hay una familia grande escondida ahí.** Los casos
se reparten entre formas no reconocidas (la mayoría), sitios mínimos de pocos
kilobytes y páginas grandes sin fichas. Vale anotarlo porque el valor de un
sondeo que no encuentra nada es justamente ése: deja de ser una sospecha
abierta.

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
