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


   **Aclaración del 2026-09-21, porque yo mismo lo mezclé.** Hoy dije cuatro
   veces que «el ítem 8 bloquea este diagnóstico» y en tres de esas estaba
   confundiendo dos brechas distintas:

   - **Ésta, la del ítem 8**: qué propiedades del inventario guardado la
     fuente ya no publica. Vive en `absences_runN.jsonl`, el camino del
     certificador no la guarda, y sigue congelada y sin resolver. Es la que
     bloquea la regla de bajas —`carina gonzalez`, `carlos castano`—.

     **CORRECCIÓN del 2026-09-21, más tarde: esto también estaba mal, y es la
     tercera vez en el día.** El dato existe. Lo que guarda sólo el conteo es
     el **resultado** (campo `ausentes`); el **checkpoint** de cada paquete
     guarda las identidades:

     ```
     checkpoint.json
       fuentes[<agencia>].ausencias  {hash_dedup: corridas_seguidas_ausente}
       fuentes[<agencia>].ids        {hash_dedup: source_listing_id}
     ```

     Medido sobre los 236 checkpoints en disco: **89 agencias tienen
     `ausencias`, con 918 propiedades ausentes registradas, y ninguna sin
     id**. Están en los cuatro conectores —generico 41, tokko 33, wordpress
     11, wasi 4—, así que no es una peculiaridad de una familia. En `cocucci`
     son 14 y la más vieja lleva **20 corridas** ausente.

     La evidencia que la regla de bajas necesitaba se venía acumulando,
     callada, donde nadie la miraba. `scripts/quienes_faltan.py` la lee, y no
     toca la huella porque sólo abre archivos que ya existen.

     Lo que sigue faltando no es la identidad sino la **respuesta**: saber si
     una propiedad ausente se dio de baja o la perdimos exige preguntarle al
     catálogo de la fuente por ese id. En `cocucci` no pude: no hay enlaces de
     paginación en el HTML y ni `?page=N` ni `/N` funcionan, así que sólo
     alcancé 20 de 270.
   - **La otra, que resultó no estar bloqueada**: qué difiere entre la corrida
     1 y la 2. Yo creía que había que tocar `compare_runs`, que está dentro de
     `shared/certifier` y habría invalidado certificaciones. No hacía falta:
     `agency_certifier.py:1011` **ya escribe** `properties_run1.jsonl` y
     `properties_run2.jsonl` en el paquete de cada agencia. El dato estaba en
     disco todo el tiempo; lo único que faltaba era leerlo.

   Lo segundo quedó resuelto con `scripts/que_cambio_entre_corridas.py`, que
   no toca la huella porque sólo lee archivos que ya existen. Con él,
   `castro y compania` y `alagna` —dos paros que llevaban horas sin causa—
   se cerraron en un comando cada uno.
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

13. **Una etiqueta de cierre rota en la fuente se come la página entera.**
    `cecilia sarro` perdió sus 51 fichas por esto, el 2026-09-21, y son
    propiedades reales: la página muestra «VENTA DEPARTAMENTO / CASTELLI 520 /
    1 Hab / 1 Bñ / 55 mts2 / U$S 45000», y el precio está en el HTML crudo,
    literal, `<p class="price"> <span> U$S </span> 45000 </p>`. No es
    JavaScript.

    Lo que pasa es esto, en la fuente:

    ```html
    <script src="…/recaptcha/api.js" async defer></script </head>
    ```

    El cierre está escrito `</script ` **sin su `>`**. El navegador lo tolera;
    `<(script|style)[^>]*>.*?</\1>` no encuentra `</script>` ahí y sigue hasta
    el siguiente, tragándose **228.176 bytes de una vez** —el cuerpo entero—.
    De 237.888 bytes de documento, `_texto()` devuelve **212 caracteres**.
    Después de eso no hay precio, ni schema, ni atributos, y el guardián
    rechaza con razón algo que él mismo dejó vacío.

    **Las tres variantes, probadas contra la página real:**

    | expresión | dónde está | texto | ¿precio? |
    |---|---|---:|---|
    | `</\1>` | `generico` ×2, `wordpress`, +7 | 212 | no |
    | `</\1\s*>` | `tokko:152`, `preingestion_rebuild:50` | 212 | **no** |
    | `</\1\b[^>]*>` | propuesta | 11.567 | **sí** |

    Que la tolerante tampoco alcance es el punto: no basta con copiar la
    variante que ya existe en otro archivo.

    **Y la regla está escrita en doce lugares que ya divergieron**: dos
    aprendieron algo y diez no se enteraron. Es el mismo patrón que ya apareció
    varias veces acá, y arreglar sólo `generico.py` lo dejaría igual de frágil.

    **El tamaño no es «una agencia».** De las 4 con el 100 % descartado, sólo
    ésta tiene el desbocamiento —las otras tres tienen proporciones normales de
    script y texto sano, cada una con otra causa—. Pero el disparador es una
    sola etiqueta malformada en cualquier fuente, y cuando ocurre se pierde la
    agencia **entera, en silencio y sin error**. La exposición es toda fuente
    futura, no una lista de cuatro.

14. **`mts2` no cuenta como superficie.** Chico y medido, lo anoto sin
    inflarlo. `alianza real estate` publica un terreno en Pujato con «Precio:
    Consulte», «Área: 382-mts2», «Dormitorios: 2», lista de comodidades y 16
    fotos. Sin precio numérico la regla exige 4 atributos distintos y
    `RE_ATRIBUTOS_TXT` reconoce 3 —baño, cochera, dormitorio—. El cuarto sería
    la superficie, y no se ve: la expresión tiene `m2|m²` pero no `mts2`, que
    es como se escribe en media Argentina, ni `área`, que es la palabra que
    usa esta ficha.

    **Tamaño real: una propiedad.** Hay 118 descartes en todo el corpus con 3+
    fotos y sin precio —los sospechosos de ser fichas reales— y viven en 5
    hosts. 117 pertenecen a causas ya diagnosticadas: `ceciliasarro` 50 (el
    ítem 13), `365litoralargentino` 48 (gama, cuya fuente es un portal),
    `smartservices.uy` 18 (casagrande) y `cia.org.ar` 1 (bertomeu). Bajé 40 de
    esas páginas y probé el umbral: sólo una cambia. Y `superficie_total` /
    `superficie_cubierta` no aparecen entre los campos con `EXTRACTION_FAILED`
    en ninguna agencia, así que el hueco tampoco está costando superficies por
    otro lado.

15. **Una foto sin extensión en el nombre no cuenta como foto.**
    `chambouleyron` perdió sus 16 fichas —su catálogo entero— por esto, y el
    triaje lo anunció bien: «16 de 16 fichas descartadas TENÍAN precio o
    schema». Traen precio (7.000.000, 60.000, 2.000.000…), operación en el
    texto, y `fotos: 0`.

    La fuente **sí** publica fotos:

    ```html
    <img src="uploads/foto341-1" />
    ```

    Las bajé: 200, 523.431 / 426.789 / 383.461 bytes, y empiezan con los bytes
    mágicos de JPEG. Son fotos de verdad. Lo que no tienen es extensión en el
    nombre —ni cabecera `Content-Type`—.

    `_imagenes_de` descarta toda url que no matchee
    `RE_EXTENSION = r"\.(?:jpe?g|png|webp|avif)(?:$|[?#])"`. Las tres caen, la
    ficha queda en cero fotos, y el guardián la rechaza por no llegar a
    `FOTOS_MINIMAS`.

    **Y es el mismo patrón que ya ocurrió en esta misma función.** Su docstring
    cuenta que mirar sólo urls absolutas dejaba en cero a los sitios con ruta
    relativa, y que «una fuente perdió 268 fichas reales por eso». Se arregló
    la ruta relativa y se dejó la extensión ausente: el arreglo avanzó un paso
    y se detuvo.

    **Arreglo propuesto:** lo que captura `RE_IMG_ATRIBUTO` ya viene del `src`
    de un `<img>`, así que es una imagen por construcción y exigirle extensión
    es redundante. Aceptarla sin extensión, dejando que `RE_NO_ES_FOTO` siga
    filtrando logos e iconos y que `FOTOS_MINIMAS` haga el resto. Un fallback
    por `Content-Type` no serviría: este servidor no manda ninguno.

    **Actualización de la misma tarde: son dos agencias, no una.**
    `corporacion inmobiliaria` paró por lo mismo y perdió 30 fichas. Sus
    descartes traen precio (800.000, 60.000), operación y títulos que son
    propiedades de verdad —«YOFRE NORTE - LAS MALVINAS 1893 - GALPÓN EN
    ALQUILER»—, y exactamente 2 fotos.

    Pero esas 2 fotos no son fotos: `_imagenes_de` devuelve 5 urls y las cinco
    son adorno —el logo de la plataforma, las dos flechas del carrusel y dos
    sellos de colegiación—. Las de verdad están en el HTML, cinco, en
    `<img src>`:

    ```
    https://gvamax.ar/serverdata/554/Fotos/Fi158411.554
    ```

    Terminan en `.554`, que es el id de la agencia usado como sufijo, así que
    `RE_EXTENSION` las descarta. Bajé la primera: 200, `Content-Type:
    image/jpeg`, bytes mágicos de JPEG.

    **Y ese detalle decide el arreglo:** este servidor *sí* manda
    `Content-Type`, el de `chambouleyron` no manda ninguno. Un fallback por
    `Content-Type` resolvería uno y no el otro. Refuerza que lo correcto es lo
    ya propuesto: lo que viene del `src` de un `<img>` es una imagen por
    construcción.

    De paso, un problema menor que conviene anotar: `RE_NO_ES_FOTO` no filtra
    sellos ni flechas, así que contamos adorno como fotos. Acá jugó a favor
    —sumó 2 en vez de 0— pero está igual de mal: con tres piezas de adorno,
    una ficha sin una sola foto pasaría el mínimo.

    **Tamaño:** 19 descartes con precio y cero fotos en todo el corpus, en 3
    agencias, y sólo `chambouleyron` tiene esa forma exacta. Contando las dos
    variantes, el ítem cuesta **46 propiedades reales en 2 agencias**. Las otras dos son rechazos
    correctos —`bunader` descarta `/propiedades/proyectos`, que es una página
    de sección, y `bertomeu` la ficha de inscripción de la cámara—. Son 16
    propiedades reales, todas de una agencia, que es todo lo que tiene.

16. **`U$D` no es una moneda para nosotros, y sí para media Argentina.**
    Pariente del ítem 14 —las dos son formas de escribir argentinas que las
    expresiones no cubren— pero mucho más caro.

    `cipollone` publica «Lote en Venta Riccheri 489, San Lorenzo · Código: 0 ·
    **U$D 70.000** · SUP. TOTAL 9mx15m» con 9 fotos, y la ficha se descarta por
    no traer precio. Busqué todas las formas de moneda en esa página: hay seis
    importes y los seis dicen `U$D`.

    `RE_PRECIO_CON_MONEDA` acepta `u$s`, `us$`, `usd`, `ars` y `$`, pero no
    `u$d`. El `$` suelto tampoco salva el caso: después del `$` viene una `D`
    y no un dígito. **Y la misma falta está en la expresión que EXTRAE el
    precio** (`generico.py:2025`, `(USD|U\$S|US\$|\$|ARS)`), así que no es sólo que
    el guardián no lo vea: es que no lo leemos.

    **Tamaño: al menos 359 propiedades.** Fui a las agencias con `precio` o
    `moneda` en `EXTRACTION_FAILED` y bajé una ficha de cada una.
    `brunetti propiedades` escribe `U$D` y tiene precio en **70 de 428**: son
    358 sin precio por esto, más la de `cipollone`.

    Conviene decir cuáles **no** son este caso, para no atribuirles algo que
    no es: `blanco propiedades` escribe `U$S` —la regla sí lo acepta— y sus
    1.209 sin precio tienen otra causa; `building` usa `US$` y `$`; `casamia`
    usa `U$S` y `$`.

    Era una **cota inferior**, y la medí después sobre una ficha real de cada
    una de **120 agencias**:

    | | agencias |
    |---|---:|
    | usan otras formas (`U$S`, `US$`, `USD`, `$`) | 70 |
    | sin moneda visible en la ficha mirada | 40 |
    | **escriben `U$D`** | **8** |
    | inaccesibles | 2 |

    Ocho de 120 es el **6,7 %**, y tres de esas ocho escriben `U$D` **y**
    otra forma en la misma página —`belvedere`, `bondar`, `carames`—, así que
    una regla que sólo mire la primera moneda que encuentra puede acertar o
    fallar según el orden.

    **Y corrige algo que yo mismo escribí antes**: dije que `building
    inmobiliaria` «no es este caso» porque la ficha que miré usaba `US$` y
    `$`. Con otra ficha aparece `U$D`. Mirar una página por agencia alcanza
    para encontrar el defecto, no para descartarlo — las 113 de 297 de
    `building` sin precio pueden ser esto después de todo.

    Antes de tocar conviene buscar si hay una tercera copia de la regla: en
    este repo la misma regla suele estar escrita en varios lugares que ya
    divergieron (ver ítems 13 y 15).

17. **El respaldo a `generico` no se compara con nada.**
    `austral inmobiliaria` certificó `CERTIFIED_COMPLETE` el 2026-09-10 con
    conector `wordpress` y **196 propiedades**. Hoy corrió con `generico` y
    enumeró **17**, contra un baseline de 191.

    La fuente no se achicó: su propia API declara
    `X-WP-Total: 200` en `/wp-json/wp/v2/properties`, y el conector de
    WordPress la descubre bien hoy —`WORDPRESS_REST`, `rest_base=properties`—.
    `choose_connector` recalculado ahora devuelve `wordpress`, así que la
    elección también fue correcta.

    Lo que cambió el resultado es `debe_reintentar_con_generico`: si el
    conector específico no obtuvo **nada**, se reintenta con `generico` y se
    acepta su resultado con la sola condición de que haya obtenido algo
    (`alternate.get("detalles_obtenidos") or estado == "OK"`). El wordpress
    volvió vacío esa vez, entró generico, trajo 17, y se aceptó.

    **El respaldo no es el problema; la falta de comparación sí.** De los 17
    resultados que lo usaron, **14 salieron igual o mejor** —`federico negro`
    1.429, `baron` 227 contra un baseline de 49, `alagna` 218—. La idea que lo
    motivó es buena y su docstring cuenta el caso: `requenapropiedades`, una
    app Laravel a la que se le había asignado WordPress.

    **Pierden dos**, y las dos por lo mismo: ésta (17 contra 191) y
    `forja propiedades` (de `tokko` a `generico`, 7 contra 350). Esa segunda
    cierra un cabo suelto de la mañana: `forja` había aparecido en la rama «la
    fuente no declara ningún total» sin causa conocida. El tercer candidato
    aparente, `carlos castano`, **no** es este caso: su sitio migró a Laravel y
    hoy publica cero, así que ahí generico es lo correcto.

    **Falta una condición**: aceptar el resultado de generico sólo si no es
    drásticamente menor que lo que la agencia ya demostró tener. El baseline
    está calculado en el mismo módulo (`baseline_inventory()`), así que el dato
    está a mano.

    Toca `agency_certifier.py`, que es `shared/certifier` y entra en la huella.

18. **La operación se pierde, y son 245 propiedades.** Una propiedad sin
    saber si se vende o se alquila casi no sirve para buscar, así que esto
    pesa más que su lugar en la lista.

    Hay 5 agencias con `operacion` sin extraer y **245 propiedades**. Bajé una
    ficha de cada una y **no es una sola causa** —conviene no juntarlas—:

    **(a) La operación está en la ficha y no la leemos.** `fenix
    inmobiliaria` (323 de 502) la tiene en el `<title>`: «DF621 - Departamento
    **en Venta** en Posadas». `ente inmobiliaria` (49 de 50) la dice en el
    cuerpo, junto al precio: «$990,000 / DOLARES **En Venta**». Hueco de
    extracción liso y llano.

    **(b) La operación sólo está en el catálogo.** `cristina pozzobon` (7 de
    8) y `constant propiedades` (**24 de 24**). En la ficha de pozzobon las
    palabras «Venta» y «Alquiler» aparecen sólo en el menú y en el lema del
    sitio; el cuerpo dice «Terreno», «USD198000» y la dirección. **No extraer
    ahí es lo correcto**: contar el menú pondría «venta» en todas, incluidas
    las de alquiler.

    Pero el dato existe: bajé `/venta/` y `/alquiler/` y la ficha está en la
    primera y no en la segunda. La operación es conocible **por la ruta desde
    la que se llegó**. Lo que falta es que `generic/html_catalog` arrastre esa
    procedencia: el registro guardado tiene `operacion: None` y su `extra` no
    menciona la página de origen. El campo `pagina_listado` existe en
    `generico.py` pero sólo en tres caminos (2255, 2527, 2730) y ninguno es
    éste. **El conector de Tokko ya aprendió esto** —tiene
    `RUTAS_POR_OPERACION` justamente para eso—; el genérico no.

    Las dos de (b) usan códigos con el mismo prefijo —`CLA7919035` y
    `CHO8029324`— así que probablemente son la misma plataforma. Queda sin
    clasificar `christian arce` (9 de 77), que no miré.

19. **El `www`: `compare_runs` compara urls crudas y no identidades.**
    `eckert servicios inmobiliarios` paró diciendo «30 propiedades que la
    primera corrida vio no aparecieron en la segunda». **No falta ninguna.**

    La corrida 1 las vio como `https://www.inmobiliariaeckert.com/site/
    properties/197993/…` y la 2 como `https://inmobiliariaeckert.com/site/
    properties/197993/…`. Los ids coinciden uno a uno.

    | | |
    |---|---:|
    | urls en común entre corridas | **0** |
    | `hash_dedup` en común | **30** |
    | sólo en run1, por hash | 0 |
    | sólo en run2, por hash | **1** |

    Hay una propiedad nueva de verdad y treinta que son las mismas.

    `compare_runs` arma los conjuntos con `source_url` crudo, y de ahí salen
    `same_url_set`, `missing_in_run2` y `new_in_run2`. Pero `hash_dedup` ya
    normaliza la url, **y la propia función lo sabe**: dos líneas más abajo lo
    usa para contar identidades, con un comentario que explica exactamente por
    qué. El mismo criterio aplicado en un lugar y no en el de al lado, dentro
    de la misma función.

    Es el **tercer caso hoy** de esa forma: la regex de `<script>` escrita en
    doce archivos que ya divergieron (ítem 13), el orden de los chequeos del
    triaje, y esto.

    **Tamaño:** recorrí todos los paquetes buscando agencias donde comparar
    por url exagere el faltante respecto de comparar por hash. Hay **una**, y
    con el máximo posible: 30 falsas contra 0 reales. Angosto hoy, pero el
    disparador —un sitio que responde con y sin `www` según el momento— es
    común, y cuando ocurre el falso positivo es del 100 %.

    Toca `agency_certifier.py`, que es `shared/certifier` y entra en la
    huella.

20. **Entidades HTML sin decodificar: 2.560 propiedades, y el costo es
    geográfico.** El más grande de los encontrados hoy.

    `bondar` paró por 3 fichas distintas entre corridas. En una, la corrida 1
    trajo barrio `B&deg; GRAN BOEDO` y ciudad `None`; la 2 trajo `B° GRAN
    BOEDO` y ciudad `Luján de Cuyo`. El rastro geo lo explica solo:

    | corrida | rechazo / evidencia |
    |---|---|
    | 1 | «`Luj&aacute;n de Cuyo` no se pudo demostrar: **NOT_FOUND**» |
    | 2 | «`Luján de Cuyo` **resolvió** contra georef:localidades_censales» |

    La misma localidad. La única diferencia es la entidad HTML.

    **El vaivén es de la fuente**: llamé a la API de Xintel hoy con las tres
    variantes —con la clave como valor de `utf8decode`, que es lo que hace el
    conector; con `1`; y sin el parámetro— y devuelven exactamente lo mismo,
    sin una sola entidad. El parámetro que enviamos está inerte, y el propio
    JS del sitio ni lo manda.

    **Lo nuestro es no defendernos.** El camino xintel arma los campos con
    `limpiar(...)`, que sólo colapsa espacios —probado:
    `limpiar('Luj&aacute;n de Cuyo')` devuelve la cadena igual—. `unescape` se
    usa en **ocho** lugares del camino HTML y en **ninguno** del camino JSON.
    Otra vez la misma regla aplicada en un lado y no en el de al lado.

    **Tamaño, sobre los 23.903 registros de todos los paquetes:**

    | | propiedades |
    |---|---:|
    | con entidades sin decodificar | **2.560 (10,7 %)** en 50 agencias |
    | `descripcion` | 1.744 |
    | `titulo` | 734 |
    | **`barrio`** | **396** |
    | `direccion` | 21 |
    | `ciudad` | **0** |

    Ese cero es la parte engañosa: cuando la ciudad llega con entidad no
    resuelve contra GeoRef y **se descarta**, así que no queda guardada.

    **El costo geográfico, medido por `extra.ciudad_publicada`**, que es donde
    sí queda el rastro —lo pude contar cuando `elgart propiedades` paró por lo
    mismo media hora después—:

    | | propiedades |
    |---|---:|
    | declaran una ciudad publicada | 16.504 |
    | la traen con una entidad HTML | **349** |
    | **y perdieron la ciudad** | **349 — el 100 %** |

    Cuando la entidad está, la resolución **siempre** falla. Son 14 agencias
    (`carames` 158, `aconcagua` 70, `federico negro` 53, `elgart` 17, `bondar`
    12…) y 343 por el conector genérico contra 6 por tokko, así que no es una
    peculiaridad del camino JSON de Xintel: `elgart` va por
    `generic/sitemap`.

    Y las ciudades que se pierden son reales y conocidas: **Lanús 159, Maipú
    77, Muñiz 27, San Miguel de Tucumán 17, José C Paz 16, Garupá 12,
    Guaymallén 6**. Todas resolverían decodificadas.

    **Esto cierra una pregunta abierta con un número.** Sobre por qué faltan
    ciudad y barrio, ésta es una de las causas y ya no es hipótesis: 349
    propiedades donde la fuente publica la ciudad, la publica bien, y la
    perdemos al normalizar. No es «la fuente no lo publica» ni «el dato es
    desconocido»: es «la normalización lo pierde», con nombre y apellido.

21. **Una ficha real que su tema declara `og:type="article"`.** Chico y
    verificado, con su contracara medida.

    `cordoba propiedades` perdió sus 2 fichas —de **31 y 53 fotos**—. El texto
    visible de una dice «Departamento en Venta San Luis 1038 | Bº Observatorio
    | **U$D 45.000**»: es una propiedad, con precio y operación.

    La página declara `property="og:type" content="article"`, que es el valor
    por defecto de muchos temas de WordPress para cualquier entrada.
    `RE_EDITORIAL` matchea eso y el guardián la trata como nota de blog.

    **Y el ítem 16 está apilado encima**: aunque no estuviera la marca
    editorial, el precio tampoco se leería, porque dice `U$D 45.000`.

    **El filtro editorial acierta casi siempre, y conviene decirlo**: de los
    320 descartes de todos los paquetes, 30 están marcados editorial y **28
    están bien** —18 son las páginas del directorio uruguayo de `casagrande`,
    10 son páginas de archivo de categoría de `austral`, y sus títulos lo
    dicen: «Casa de río **archivos**», «Cochera **archivos**»—. Los 2
    equivocados son éstos.

    Así que no conviene aflojar el filtro. Conviene que una página con precio,
    operación y 31 fotos pese más que una etiqueta de metadatos.

    ### DESCARTADO el 2026-09-23, y la medición lo dio vuelta

    Fui a escribir exactamente esa escapatoria —«si tiene precio con moneda y
    fotos suficientes, la etiqueta `article` no manda»— y antes miré qué
    tenían los 30 descartes editoriales:

    | | tiene precio | 3+ fotos |
    |---|---|---|
    | `austral`, 10 páginas de archivo (**mal** rechazadas… no: bien) | **sí** | sí |
    | `casagrande`, 18 del directorio uruguayo (bien) | no | sí |
    | `cordoba propiedades`, 2 fichas reales (mal) | **no** | sí |

    La escapatoria habría admitido las **10 páginas de archivo de categoría**
    de `austral` —que tienen precio porque listan propiedades— y habría
    seguido rechazando las 2 de `cordoba`, que en esa corrida tenían
    `precio: None` justamente por el `U$D`.

    O sea: el arreglo que iba a escribir invertía el resultado. Admitía las
    equivocadas y no recuperaba las correctas.

    **Queda sin arreglar, a propósito.** Cuesta 2 propiedades. La alternativa
    era una heurística para distinguir una ficha de un listado —contar precios
    en la página, mirar si hay un solo `<h1>`— y eso es adivinar: si se
    calibra mal, entran diez páginas de archivo con todo su contenido mezclado.
    Dos propiedades no pagan ese riesgo.

    Lo que sí cambió: con `U$D` arreglado, la próxima corrida de `cordoba` va
    a extraer el precio. Sigue sin entrar por la etiqueta `article`, pero el
    defecto queda reducido a uno solo en vez de dos apilados.

    De paso **refuerza el ítem 17**: que `austral` enumere páginas de archivo
    de categoría en vez de fichas es consecuencia de haber caído al conector
    genérico cuando el de WordPress volvió vacío.

22. lo que aparezca de los paros que la cola encuentre de acá en adelante.

---

## El salteo de los `CONTINUE`, medido en produccion

El arreglo de `el_triaje_ya_decidio_no_parar` se desplegó pasadas las 15:00.
Contando reintentos de un `NEEDS_FIX` con la misma huella y la misma url que
el resultado inmediato anterior:

| tramo | corridas | agencias | reintentos inútiles |
|---|---:|---:|---:|
| 05:00–15:00, antes | 115 | 82 | **35 (30 %)** |
| 15:00–en adelante, con el salteo | 41 | **41** | **1 (2 %)** |

41 corridas para 41 agencias distintas: en ese tramo la cola dejó de rehacer.
Es una medición más limpia que la del transporte, porque acá el mecanismo es
determinista —una agencia se saltea o no— y no depende de la red.

El único reintento que queda es correcto: una agencia cuyo resultado anterior
sí pedía rehacerse.

## Lo que se está acumulando, medido

169 defectos abiertos (el último por agencia y componente), repartidos así:

| radio | |
|---|---:|
| FAMILIA | 93 |
| AGENCIA | 34 |
| ESTRATEGIA | 32 |
| COMPARTIDO | 10 |

| componente | |
|---|---:|
| `extraccion_transversal_de_atributos` | **35** |
| `variante_no_soportada` | 32 |
| `posible_perdida_de_inventario` | 17 |
| `extraccion_de_baja_magnitud` | 15 |
| `fuente_inaccesible` | 11 |
| `sin_determinar` | 10 |
| `guardian_de_forma_compartido` | 10 |

El bloque más grande es el primero y no es una sola causa: sus 35 agencias se
reparten en 8 estrategias (`generic/sitemap` 13, `generic/html_catalog` 10,
`wordpress` 6, `tokko` 2 y cinco más con una cada una) y 7 plataformas. El
ítem 11 —el icono de RealHomes— es una de ellas.

Lo que sí se puede decir con un número: sobre las 275 agencias con cobertura
de campos medida, **`ambientes` falla en 12 agencias y 1.900 propiedades**,
que es el campo más caro de todos. Le siguen `precio` (1.803), `moneda`
(1.214) y `ciudad` (776). No afirmo que sea una sola causa —no lo medí— pero
es por donde habría que empezar cuando la tanda se descongele.

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

### CORRECCIÓN, medida más tarde: el costo dominante no eran las muertes

Miré las conexiones del worker 0 en vivo mientras estaba «trabado» en `alagna`
y encontré otra cosa. No estaba colgado: estaba pidiendo, y una sola conexión
quedó **50 segundos en `SynSent`** contra una IPv6 de Cloudflare.

Medido sobre `alagnapropiedades.com.ar` —la misma página, los mismos
**106.183 bytes**—:

| | |
|---|---:|
| como está hoy | 5.444 ms |
| forzando IPv4 | **1.462 ms** |
| como está hoy, otra vez | **23.224 ms** |

La IPv6 de esta máquina no está muerta —a Google conecta en 20 ms— pero hacia
Cloudflare se cuelga: `cloudflare.com` dio 1.018 ms y después timeout de más de
12 s, contra 28 ms por IPv4.

Sondeé 400 hosts del padrón:

| | hosts | |
|---|---:|---|
| sin AAAA | 317 | 79,2 % — no les afecta |
| rápido | 51 | 12,8 % |
| lento | 14 | 3,5 % — 1 a 3 s de handshake |
| **colgado** | **18** | **4,5 % — timeout** |

**`alagnapropiedades.com.ar` está entre los colgados.** Y ahí se cae mi propia
explicación de arriba: 219 propiedades por unos 20 s de handshake perdido son
**4.380 s**, o sea prácticamente los 3.370 s enteros de la primera corrida. No
es que las muertes de worker no costaran nada —costaron—, es que **no eran lo
dominante**, y yo había cerrado el análisis sin mirar el transporte.

#### Primera medición en producción, con su límite dicho

Relancé **sólo el worker 0** con el arreglo y dejé el worker 1 sin él, como
control en la misma cola. La primera agencia que tocó fue justamente `alagna`.
Las corridas de hoy sobre esa agencia, en orden:

| hora | duración |
|---|---:|
| 05:34 | 934 s |
| 06:34 | 1.158 s |
| 07:54 | 2.001 s |
| 09:04 | 3.020 s |
| 10:14 | 3.370 s |
| **12:38, con el arreglo** | **863 s** |

Las cinco previas venían **creciendo monótonamente** toda la mañana y la
primera con el arreglo cayó por debajo de todas. Eso es consistente con que el
handshake fuera el costo dominante y con que la IPv6 se estuviera degradando
durante el día.

**No es prueba todavía**: es una sola corrida, y esta agencia tiene histórico
de 884 s y 934 s sin el arreglo, así que 863 s no está fuera del rango que
alcanzó alguna vez. Lo que sí es raro de explicar por azar es la forma —cinco
crecientes y un corte— y eso se confirma o se cae con las próximas agencias
contra el control.

#### Cierre de la medición, al final del día

El A/B con control se terminó temprano —un paro COMPARTIDO mató al worker 1 y
lo relancé con el arreglo, así que dejó de ser control—. Lo que queda es
comparar tramos del día, con su matiz:

| tramo | resultados/h | paros/h |
|---|---:|---:|
| 00–06, antes de la degradación | **15,4** | 1,0 |
| 07–12, degradado (IPv6 empeorando) | **8,7** | 2,2 |
| 13–17, con IPv4 primero | **12,8** | 3,2 |

El ritmo se recuperó de 8,7 a 12,8/h, un 47 % más, **y con el triple de paros
por hora** que el tramo rápido de la madrugada. Cada paro mata a los dos
workers hasta que se firma y se relanza, así que la comparación juega en
contra del tramo de la tarde y aun así gana.

No volvió a 15,4, y no tengo cómo separar cuánto de eso es el arreglo y
cuánto la carga de paros. Lo que sí se sostiene: la caída de la mañana se
revirtió, y la forma —cinco horas cayendo, corte, recuperación— coincide con
lo medido en el handshake.

Arreglado en `scripts/ipv4_primero.py`, conectado en el runner de la cola.
Reordena las direcciones para poner IPv4 adelante y **no descarta las IPv6**:
de los 83 hosts con AAAA, 51 conectan rápido por IPv6 y hay redes donde es el
único camino. Va en el runner y no en el `Descargador` porque
`connectors/base.py` entra en la huella y esto no cambia **nada** de lo que se
extrae: los 106.183 bytes son idénticos por las dos familias. Verificado que
ninguna de las dos huellas se mueve.

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
