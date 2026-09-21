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

Cada uno reinició el ciclo.

### CORRECCIÓN: la medición con la que justifiqué esto estaba mal

Escribí que «275 de 275 certificaciones comparables ya tenían la huella
caduca, cero vigentes», y usé ese número para justificar que tocar `shared/*`
no costaba recertificación adicional. **Estaba midiendo otra función.**

`code_fingerprint` no es la huella de componentes: es
`version_del_codigo(connector)`, el sha256 de los **bytes** de tres archivos
—`connectors/base.py`, `connectors/<connector>.py` y
`scripts/run_rollout.py`—. Yo estaba comparando contra
`fingerprint_from_components(...)`, que es el `strategy_fingerprint`, una
cantidad distinta. Nunca iba a coincidir.

Medido bien:

| | |
|---|---:|
| certificaciones **vigentes** | **42** |
| caducas | 233 |
| sin dato para comparar | 154 |

Y las huellas que los workers escriben coinciden exactamente con las que
calculo ahora —`4d72de75ed17` para tokko, `511258e31c3a` para wasi—, o sea
que están corriendo el código actual.

**Lo que se cae es el argumento, no los arreglos.** Cada cambio sobre
`shared/*` sí costó recertificación real. Los arreglos siguen siendo
correctos —están verificados contra las fuentes, uno por uno— pero la razón
que di para hacerlos todos seguidos no se sostenía.

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

6. **`source_listing_id` repetido en `generico`: 3.683 propiedades (24,5 %).**
   Apareció buscando si se podía construir el crosswalk de identidad pública.
   El conector genérico toma el primer número del slug, y en una url como
   `carusopropiedades.com/ad/lote-de-1200-m2-en-venta-la-reja-centro` ese
   número es la **superficie**. El id `1200` aparece en 31 urls de agencias
   distintas; el `500`, en 27.

   | conector | propiedades | ids con choque | afectadas |
   |---|---:|---:|---:|
   | tokko | 32.757 | **0** | **0** |
   | generico | 15.042 | 1.131 | **3.683 (24,5 %)** |
   | wordpress | 8.722 | 272 | 613 (7,0 %) |
   | wasi | 1.322 | 0 | 0 |
   | century21 | 584 | 0 | 0 |

   No compromete la identidad de la propiedad —`hash_dedup` se calcula sobre
   `inmobiliaria_id|url`, no sobre esto— pero es un campo publicado que dice
   algo falso, y el caso `eckert` muestra el mecanismo con claridad: la url es
   `/properties/446753/1200m2-…` y el id que guardamos es `1200`.

7. **Fotos con espacio en el nombre: se pierden enteras.**
   `connectors/generico.py:2745` hace `m.group(1).split()[0]`, que se queda
   con lo que hay antes del primer espacio —sirve para un `srcset`— y parte
   cualquier url cuyo archivo tenga uno:

   ```
   images/20260819104926_ChatGPT Image 19 ago 2026, 09_45_36.jpg
   -> images/20260819104926_ChatGPT   -> sin extensión -> descartada
   ```

   `RE_IMG`, el patrón de urls absolutas, tiene el mismo tope (`[^\s"'<>]+?`).

   Medido contra la fuente en `bottai`, y la correlación es perfecta: toda
   foto que falta tiene espacio, y toda foto con espacio falta. **71 de 232
   propiedades quedan sin ninguna foto, el 30,6 %.** Afecta a cualquier sitio
   que suba las fotos con su nombre original, y
   `WhatsApp Image 2026-07-28 at 15.31.50 (3).jpg` es un nombre muy común.

   El arreglo: quedarse con el token previo al espacio **sólo** cuando el
   valor es un `srcset` de verdad, y si el valor entero termina en extensión
   de imagen, usarlo entero.

8. **La cola no registra QUÉ propiedades faltan, sólo cuántas.**
   `run_rollout.py` escribe `absences_runN.jsonl` con el detalle; el camino
   del certificador guarda sólo el conteo `ausentes`. Resultado: **0 de 429
   paquetes** tienen el detalle, y sin identidades la regla de bajas no puede
   acumular evidencia nunca —ver `ERETZ_PROPERTY_LIFECYCLE.md`, sección 5
   bis—. No es una pieza que falte inventar: es una diferencia entre dos
   caminos.

9. lo que aparezca de los paros que la cola encuentre de acá en adelante.

### El crosswalk de identidad pública: no se puede construir acá

Era uno de los pendientes heredados —«el crosswalk URL numérica ↔ hash está
vacío; **no inventar aliases**»—. Comprobado: la tabla `property_aliases` no
existe en la snapshot y nada la construye; la API la consulta a la defensiva,
así que degrada a 404 en vez de romper.

**No se puede armar con datos locales, por dos razones y las dos medidas:**

1. El identificador público viejo es el `id` numérico de producción, y
   producción no se consulta. Localmente no existe en ningún artefacto: las
   filas de preingestión tienen `canonical_agency_id`, `inmobiliaria_id` y
   `source_listing_id`, ninguno de ellos ese id.
2. Aunque se intentara con `source_listing_id`, **no sirve**: 1.646 valores
   están compartidos por dos o más propiedades y afectan a 4.937 (8,4 %).
   Un alias construido así mandaría una url a la propiedad equivocada, que es
   exactamente lo que la consigna prohíbe.

Queda como bloqueado por acceso a producción, no como pendiente de trabajo.

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

## El congelamiento está funcionando

Medido con la función correcta, desde que dejé de tocar código compartido:

| hora | certificaciones vigentes escritas |
|---|---:|
| 04 | 13 |
| 05 | 14 |
| 06 | 15 |

**13 a 15 por hora, sostenido.** Con 767 en la cola, una pasada completa son
unas 55 horas —el número que ya había estimado, sólo que ahora es avance real
y no repetición—. Los dos workers están en la letra B, no en la A.

## Cómo saber si esto se repite

La señal es **cuántas certificaciones tienen la huella vigente**, y hay que
calcularla como la calcula el certificador:

```python
h = hashlib.sha256()
for r in (raiz/"connectors"/"base.py",
          raiz/"connectors"/f"{connector}.py",
          raiz/"scripts"/"run_rollout.py"):
    h.update(r.read_bytes())
vigente = (h.hexdigest()[:12] == resultado["code_fingerprint"])
```

La métrica que usé primero —agencias que cierran por primera vez— no sirve
para esto: mientras la cola recertifica, es cero por definición aunque el
trabajo avance.

```bash
python scripts/de_donde_falta_la_geografia.py
```

no responde esto. La consulta que sí lo responde está en esta bitácora y
convendría que fuera una herramienta, pero no la escribo ahora: sería
exactamente el tipo de trabajo que me llevó a no mirar el número correcto
durante doce horas.
