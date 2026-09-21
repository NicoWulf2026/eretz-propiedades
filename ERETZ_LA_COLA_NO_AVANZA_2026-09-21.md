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

9. **La condición de fotos del triaje quedó inerte en el camino que
   importa.** Hace unas horas agregué que un rechazo del guardián sólo es
   sospechoso si traía precio o schema **y además fotos suficientes**, y lo
   puse en `defect_triage.py`. Pero el contador que el triaje **prefiere**
   —`descartes_con_senal`, calculado en `run_rollout.py:605`— se quedó sin
   esa condición.

   Lo destapó `bunader`: sus 8 rechazos tienen **cero fotos**, el triaje
   actual da 0 sospechosos y veredicto `None`, y el paro salió igual del
   contador, que dice 2.

   Es la misma regla escrita en dos lugares y separada. El arreglo es una
   línea —agregar `and (d.get("fotos") or 0) >= FOTOS_MINIMAS`— pero
   `_procesar_con` **sí** está en la huella del certificador.

10. **El conflicto geográfico borra la coordenada y la reporta como fallo de
    extracción.** `connectors/base.py:934-937` borra cuatro campos y marca
    dos:

    ```python
    prop.provincia = prop.ciudad = None
    prop.latitud = prop.longitud = None
    _marcar_descartado(prop, 'ciudad')
    _marcar_descartado(prop, 'provincia')
    ```

    Latitud y longitud quedan en `None` sin rastro, así que la cobertura ve
    «la fuente lo publica, no lo tenemos, nadie lo descartó» y concluye
    `EXTRACTION_FAILED`. Son **dos** defectos: la etiqueta —debería ser
    `PROVIDED_REJECTED`, que existe para esto— y borrar la coordenada, que es
    el mismo exceso corregido esta mañana en la rama de
    `PROVINCE_CONFLICT_REASON`; ésta es la de `CONTRADICTED_BY_COORDINATES` y
    quedó afuera.

    Medido: de 372 propiedades sin latitud en las 7 agencias con ese estado,
    **58 son descartes y no fallos** —34 de `cantale` y 11 de `agostinelli`—.
    Las otras 314 sí son fallos reales. Chico en propiedades y caro en
    operación: dos paros FAMILIA de la misma agencia.

11. **Un icono entre el rótulo y el número rompe el conteo de atributos.**
    `alas propiedades` publica `Dormitorios 4` con el tema RealHomes:

    ```html
    <span class="rh_meta_titles"> Dormitorios </span>
    <div> <svg class="rh_svg" …> … 4 … </div>
    ```

    `_cuenta_de_ficha` exige que el elemento del valor contenga **sólo** el
    número, y acá empieza con un SVG. Cuesta **120 de 206 fichas** sin
    dormitorios.

    Cuidado con el respaldo por texto: aplanada, la ficha dice `ID de la
    propiedad: A222 Dormitorios 4`, y un patrón de «número antes de la
    palabra» saca **222**, que es el ID. La salida no es aflojar hacia el
    texto plano sino permitir contenido no numérico dentro del elemento del
    valor.

    **No es familia grande**: de las 6 agencias con 10+ fallos en un conteo,
    sólo ésta usa RealHomes.

12. **`SIN_INVENTARIO` significa dos cosas distintas y se escribe igual.**
    Salió del paro de `carlos castano` el 2026-09-21. La etiqueta
    `publication_mechanism` se pone en `SIN_INVENTARIO` tanto cuando la fuente
    no publica nada como cuando la corrida **no llegó a mirar**, y quien abre
    el archivo lee lo primero.

    De 34 agencias con conector `wordpress`, 8 enumeraron cero y las 8 están
    así etiquetadas. Bajé los 8 sitios: **3 publican de verdad**. `aguirre`
    sirve el tipo `property` por `wp-json/wp/v2/properties` —corrí el
    `discover` real y hoy devuelve `WORDPRESS_REST, soportada=true`—, `franchi`
    tiene 13 fichas en `/propiedad/`, y `cintia fonzo` publica como productos
    de WooCommerce en `/categoria-producto/venta`.

    **No es un cero certificado**, y conviene decirlo porque yo mismo lo
    escribí mal antes de verificarlo: las 8 están en `NEEDS_FIX` o
    `BLOCKED_EXTERNAL`, con la razón `one or both runs did not finish with
    connector state OK`. El sistema paró; no certificó nada. Es un defecto de
    **nombre**, no de decisión.

    `base.py:475` ya tiene `hubo_contacto()` escrito contra esta confusión —su
    docstring nombra a `aguirreinmobiliaria.com.ar`, «publica 38
    propiedades»—, pero separa los estados **terminales**, no esta etiqueta.
    La misma regla en dos lugares que no se hablan, otra vez.

13. lo que aparezca de los paros que la cola encuentre de acá en adelante.

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

## Lo que descubrí después: firmar una diferida también reinicia el cursor

El ritmo cayó de 13/h a 8/h entre las 07 y las 10, y la causa es mi propio
ciclo de diagnóstico.

El cursor se restaura **sólo si la cola no cambió** (`same_queue`). Y la cola
cambia cada vez que se firma una diferida: un `NEEDS_FIX` con diferida fresca
pasa a vigente y sale de la cola. **Hoy firmé 12.**

Medido en el momento de escribir esto:

```
w1  huella_cola 5e08142b…  cursor 39 de 378  desde 06:34   -> ~11/h
w0  huella_cola b8d14d46…  cursor  0 de 413  desde 09:04   -> reiniciado
```

w1 lleva tres horas y media con la misma cola y avanza parejo. w0 cambió de
cola y volvió a empezar. Los dos workers tienen turnos distintos, así que una
diferida reinicia sólo al que le toca.

**La mitigación no es de código, es de método: firmar las diferidas en tanda.**
Doce firmas espaciadas cambian la cola doce veces; las mismas doce juntas la
cambian una. Diagnosticar en el momento sigue siendo lo correcto —la evidencia
está fresca y el sitio está como estaba—, pero la firma puede esperar.

### Cómo se aplica, con lo que se aprendió aplicándolo

1. Llega el paro. **Se diagnostica en el momento**, contra la fuente.
2. El dictamen se guarda en
   `ERETZ_AGENCY_CERTIFICATION_20260827/DIFERIDAS_PENDIENTES_DE_FIRMA.jsonl`,
   **sin firmar**.
3. **La bandera de paro sí se levanta igual.** Mata al worker y persiste hasta
   que alguien la saca; levantarla **no** cambia la cola, sólo la firma lo
   hace. Esto no era obvio y costó un worker caído hasta notarlo.
4. Se relanza el worker que murió.
5. Las firmas se aplican todas juntas, una sola vez.

### CORRECCIÓN, después de aplicarlo: diferir la firma sale más caro

El método era media verdad y `cantale` la mostró: paró **tres veces** en dos
horas con la misma evidencia. **Una diferida sin firmar no evita que el paro
se repita** —justamente la firma es lo que marca el defecto como atendido—,
así que cada pasada vuelve a frenar los dos workers, a matarlos y a esperar
hasta diez minutos al relanzador.

La aritmética, medida:

| | |
|---|---|
| firmar | 1 cambio de cola, 1 reinicio de cursor **de un turno** |
| no firmar | el paro se repite en cada pasada, y cada uno mata **los dos** workers |

Tres paros valen más que un reinicio de cursor. **La regla correcta no es
diferir la firma, es agruparla:** si llegan varios paros seguidos se
diagnostican todos y se firman juntos —una sola vez—, pero no se deja ninguno
sin firmar esperando una tanda que no se sabe cuándo llega.

Lo que sigue valiendo del hallazgo original: doce firmas espaciadas cambian la
cola doce veces. Lo que estaba mal era la conclusión de que la solución fuera
esperar.

Un veredicto que conviene tener a mano: **`NO_REPRODUCIBLE`**. Si el paro
denuncia un fallo que no se puede reproducir contra la fuente por ningún
camino, eso es el resultado —no una causa inventada—, y la acción es
re-certificar, no tocar código. Cambiar un extractor por un fallo que no se
reproduce es como se rompen las cosas que andaban.

## El costo real de un paro no son los diez minutos de relanzador

Medido al final del día, y corrige dos hipótesis mías que eran falsas.

El ritmo cayó de 15 resultados/hora a 3. Probé dos explicaciones y las dos se
cayeron: **no** es que los workers re-recorran un prefijo creciente de
vigentes —los dos estaban haciendo trabajo nuevo cuando lo miré— y **no** es
que el termómetro subcuente agencias sin conector —los 145 resultados de hoy
tienen conector—.

Lo que sí es:

| | |
|---|---:|
| veces que el relanzador encontró workers faltando | **8** |
| tiempo caído estimado | hasta **80 min** |
| duración mediana por agencia | **320 s** (62 propiedades) |
| ritmo teórico con 2 workers | **11,9 agencias/h** |

Y el dato que lo explica:

```
3370 s   219 props   alagna propiedades
3020 s   219 props   alagna propiedades
2001 s   219 props   alagna propiedades
```

**La misma agencia, tres veces, 2,3 horas en total, y sin terminar.** Cada
paro mató al worker mientras la procesaba y, al reiniciar, volvió a
empezarla.

Ahí está el costo real de un paro: no son los diez minutos que tarda el
relanzador, son los **treinta a cincuenta y cinco minutos de trabajo en curso
sobre una agencia grande** que se pierden y hay que rehacer. Con 8 muertes en
un día y agencias de 200 a 450 propiedades, eso solo explica la diferencia
entre 11,9/h teóricas y las 3 a 9 observadas.

Queda anotado, no arreglado: el resume por checkpoint existe
(`Checkpoint(packet_dir / "checkpoint.json")`) y evidentemente no está
recuperando el trabajo de una agencia interrumpida. Mirarlo es trabajo de
runner, y el runner **no** está en la huella —`shared/runner` es
`run_rollout.py`, no `run_agency_certification_queue.py`—, así que se puede
hacer sin esperar al lote. No lo hago ahora porque hoy ya toqué política
operativa tres veces y dos salieron mal; esto merece una medición propia
antes que un cambio.

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
