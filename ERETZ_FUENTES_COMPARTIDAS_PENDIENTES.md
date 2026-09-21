# Las 15 urls compartidas que quedan, con la evidencia recogida

**2026-09-20 · `database_writes: 0` · ninguna aplicada**

De los 25 grupos originales se resolvieron 10, con 29 agencias. **Ninguno de
los 15 que quedan tiene una sola propiedad ni una certificación atribuida**, así
que no hay contaminación en curso: hay una mina desactivable.

Estos 15 **no** se aplicaron, y la razón importa más que la lista.

---

## Por qué no los apliqué: la heurística no alcanza

Escribí un detector de dueño —bajar el sitio, leer el `<title>`, contar
menciones de cada nombre— y lo corrí contra los 15. Acierta en varios y **se
equivoca en otros**, así que no sirve para aplicar:

| url | lo que dice el sitio | lo que eligió la heurística |
|---|---|---|
| `remax-net.com.ar` | título **«re max net»** | eligió `remax star` — **mal** |
| `jmizrahi.com.ar` | título **«j. mizrahi negocios inmobiliarios»** | eligió `mizrahi real estate` — **probablemente mal** |
| `rodriguezjurado.com.ar` | las dos agencias en el título, 12 menciones cada una | eligió una al azar — **indecidible así** |
| `grupoplatino.com.ar` | las dos con 15 menciones | ídem |
| `inmobiliariabertero.com.ar/provincia-…/san-isidro` | «top inmobiliarias en san isidro, opiniones y horarios» | ninguna — **es un directorio**, correcto |

El patrón del error es siempre el mismo: **contar menciones no distingue al
dueño del mencionado**, y cuando los dos nombres comparten la palabra larga
—`remax`, `mizrahi`, `rodriguez`— el conteo empata o se invierte.

Aplicarla habría reasignado identidad con evidencia débil, que es exactamente
la línea que este trabajo vino a proteger.

---

## Lo que sí resolvió la evidencia del sitio

Tres casos quedaron cerrados hoy porque el título era inequívoco y los
registros lo confirmaban:

| url | dueño | evidencia |
|---|---|---|
| `cosapropiedades.com` | `cosa propiedades` (1600) | título «COSA Propiedades», 21 menciones de COSA, **cero** de «CAS.AS» |
| `zaratepropiedades.com` | `zarate gestion inmobiliaria` (6849) | título «Zárate Gestión Immobiliaria», 18 de «Gestión» |
| `palermo.licuo.com.ar/comercializadores_…` | **de ninguna** | página que lista comercializadores de un barrio |

El tercero es el que destapó la quinta aparición de `\b` en este proyecto: el
clasificador no lo veía porque `\b` no casa antes de un guion bajo.

---

## Los 15 pendientes

### `OFICINAS_DE_RED` — 6 grupos, 14 agencias

`remax-urbana` (4 oficinas), `remax-noa`, `remax-net`, `remax-parque`,
`remax-premium`, `grupoplatino`.

Acá el sitio **sí** es de alguna de las oficinas. Lo que hace falta no es una
regla sino saber cuál: la red publica un sitio por oficina y el padrón tiene
dos registros apuntando al mismo. El título ayuda en `remax-net` («re max
net») y `remax-premium`, y empata en `grupoplatino`.

**Riesgo de no hacer nada**: cuando la cola las alcance, las dos oficinas del
par enumerarán el mismo catálogo y las propiedades quedarán atribuidas dos
veces. Es exactamente lo que se evitó en `cosapropiedades.com`.

### `SIN_CLASIFICAR` — 9 grupos, 18 agencias

`crsargentina.com.ar`, `urbanorosario.com.ar/servicios`,
`inmueblesmartinez.com.ar`, `rodriguezjurado.com.ar`,
`inmobiliarialeiva.com.ar`, `century21.com.ar/v/oficina/133-franchi-la-plata`,
`jmizrahi.com.ar`, y dos rutas de `inmobiliariabertero.com.ar`.

Dos de ellos —los de `bertero`— parecen directorios por su título aunque no por
su ruta: **el clasificador mira la ruta y ahí no hay ninguna palabra que lo
delate**. Usar el título como segunda fuente de evidencia es la mejora obvia y
no la hice hoy porque cambia el detector, no los datos, y prefiero medirla
antes.

---

## Lo que recomiendo para cerrarlos

1. Para los seis de red: una decisión por par, mirando qué oficina figura en
   el pie del sitio y qué matrícula publica. Es trabajo de lectura, no de
   regla.
2. Para `bertero`: agregar el título como evidencia en el clasificador, con
   sus tests, y volver a correr.
3. Para el resto: uno por uno, con el criterio que funcionó —el sitio se
   nombra a sí mismo— y anotando la evidencia en el rastro, como se hizo con
   `cosa` y `zarate`.

Ninguno urge: los 15 están en cero propiedades y cero certificaciones. Lo que
urge es hacerlo **antes** de que la cola los alcance, y la cola va por la
letra A.


---

# Lo que el detector no veía: hosts compartidos — 2026-09-21

Las 15 urls compartidas quedaron en 2. Pero el detector agrupa por **url
exacta**, y hay un riesgo que se le escapa entero: varias agencias cuyo
«sitio oficial» es su **perfil en el mismo portal**, cada una con su propia
ruta.

Medido sobre las 318 agencias con `official_url`:

| | |
|---|---:|
| urls compartidas por 2+ agencias | **0** |
| **hosts** compartidos por 2+ agencias | **4** |
| agencias involucradas | **10** |

```
4 agencias en buscainmueble.com
      /inmobiliarias/alonso-propiedades/casas/venta
      /inmobiliarias/analia-verga-propiedades
      /inmobiliarias/calderon-inmobiliaria/inmueble…
      /inmobiliarias/carlos-aslan-propiedades/depar…
2 en inmobusqueda.com      /abalsamopropiedades, /albertodacal
2 en proppies.app          /inmobiliarias/<agencia>-<n>
2 en liderprop.com         /es-ar/propiedades/6257658/alquiler--casa--…
```

**No es el mismo riesgo que una url compartida.** Ahí el peligro era la doble
atribución; acá cada agencia tiene su ruta y nadie se pisa. Lo que pasa es
otra cosa y ya se vio dos veces esta noche: la enumeración recorre el chrome
del portal —le pasó a `gama` y a `bertomeu`— y el inventario propio de la
agencia queda invisible.

El caso de `liderprop` es el peor de los cuatro: la «web oficial» de esa
agencia es **una ficha de propiedad**, no un perfil ni un sitio.

## Y hay una población mayor detrás

De las 318, **34 (10,7 %)** tienen una `official_url` cuyo dominio **no las
nombra en absoluto** —medido con el dictamen de dominio de
`scripts/de_quien_es_el_dominio.py`—. Los hosts que se repiten son portales y
plataformas: `buscainmueble` (4), `inmobusqueda` (2), `liderprop` (2),
`comunidadinmobiliaria`, `redinmosoft`, `inmoclickai`, `ventasprop`… y
`turismomardelplata`, que para una inmobiliaria es difícil de defender.

Que el dominio no la nombre no prueba que esté mal —una agencia puede tener
un dominio de marca distinta— pero es la lista de candidatas correcta para
revisar, y los hosts la confirman.

## El caso que lo destapó

`bertomeu propiedades` tiene como sitio oficial
`https://cia.org.ar/nuevo-directorio/`: el **directorio de socios de la Cámara
Inmobiliaria Argentina**. El guardián paró la cola rechazando dos páginas de
ese sitio —un formulario de inscripción y una **nota periodística** sobre
escrituras— y hacía bien.

Lo notable es el registro: `AGENCY_OFFICIAL_WEB_VERIFIED.jsonl` la marca
`VERIFICADA_ARGENTINA`. La verificación confirmó que la página está **viva y
es argentina**, no que sea de esa agencia. Y el directorio ya lo decía:
`status: OFFICIAL_WEB_AMBIGUOUS`, con la otra candidata siendo un perfil de
ejecutivo en `expansion.com`.

## Qué falta

1. **Extender el detector a hosts**, no sólo a urls exactas. Es donde está el
   riesgo que hoy no se ve.
2. Revisar las 34, empezando por las 10 de host compartido.
3. Corregir la fuente cambia `official_url`, y eso cambia la cola —la
   vigencia compara la fuente—. Va en tanda, no de a una.


---

# El detector ya agrupa por host, y el número es mucho mayor

Extendido `fuentes_compartidas.py` con `colisiones_por_host()`. Sólo reporta
grupos cuyas urls **difieren** —si son iguales ya salían por el camino de
siempre—. Corrido sobre el catálogo completo:

| | |
|---|---:|
| urls compartidas | **2** |
| **hosts** compartidos con urls distintas | **76** |
| agencias involucradas | **650** de 791 |
| de ésas, ya certificadas | **22** |
| **todavía no alcanzadas por la cola** | **628** |

Mi medición a mano de hace un rato dio 4 hosts y 10 agencias. Estaba mirando
sólo las 318 que ya tienen resultado; el catálogo completo es otra cosa.

## Los grandes son portales

```
70  buscainmueble.com     45  inmoclick.com     36  todoprops.com
62  inmoup.com.ar         42  choza.ai          28  proppies.app
46  liderprop.com         39  century21.com.ar  22  inmobusqueda.com
```

14 hosts tienen 10 agencias o más y suman **452**. Y varias de esas urls no
son ni siquiera un perfil: `choza.ai/property/34237` es **una ficha de
propiedad** registrada como el sitio oficial de una inmobiliaria.

## Lo que esto NO es, y por qué importa la diferencia

De las 22 certificadas, **14 lo hicieron contra el portal**. Su resultado:

```
11  BLOCKED_EXTERNAL
 3  NEEDS_FIX
32  fichas enumeradas entre las catorce
```

**El sistema ya se protege.** Certificar contra un portal no produce
inventario ajeno atribuido a la agencia: produce un bloqueo. Eso es lo que
hay que decir con precisión, porque la lectura fácil —«650 agencias van a
contaminar el padrón»— es falsa y llevaría a una urgencia equivocada.

Lo que sí es: **un techo**. 628 agencias todavía sin alcanzar tienen como
fuente registrada una url de portal, y cuando la cola llegue van a certificar
bloqueadas o vacías. No es una mina que explota; es una porción grande del
padrón que **no se puede certificar con la fuente que tiene registrada**.

## Qué haría falta

Para esas 628, el trabajo no es de conectores sino de **registro de fuentes**:
encontrar el sitio propio de cada agencia, o declarar explícitamente que no
tiene. Es el mismo trabajo que se hizo con las 15 urls compartidas, a otra
escala.

Y cambia `official_url`, que es lo que compara la vigencia: va en tanda.

---

# La capa que gana por precedencia no arrastra la duda de la que está abajo — 2026-09-21

**`database_writes: 0` · nada aplicado · la cola sigue a mitad de pasada**

Esto salió del paro de `roomix:casagrande negocios inmobiliarios`, y el paro en
sí era aburrido: 18 fichas descartadas, ninguna sobrevivió, y **cada rechazo
estaba bien**. Las 18 eran `caseritos-al-paso-91800-tala`, `lpm-burgers-sauce`,
`cerveceria-heisenbeer-pando`. No son propiedades. Son comercios de un
directorio **uruguayo**, `smartservices.uy`, que quedó registrado como la
fuente oficial de una inmobiliaria argentina.

Lo que importa no es ese sitio: es **cómo llegó a ser la fuente**.

## El mecanismo

`agency_web_directory.jsonl` ya lo había marcado `OFFICIAL_WEB_AMBIGUOUS`, con
dos candidatas y sin resolver cuál era. Esa duda estaba registrada y era
correcta. Pero `agency_platform_directory.jsonl` guardó la url uruguaya como
`domain`, y **la capa de plataforma gana por precedencia sobre el directorio**.

El resultado es que la duda se pierde en el camino: abajo alguien escribió «no
sé cuál de las dos», arriba quedó una url sola y afirmativa, y la resolución de
identidad leyó la de arriba.

## El tamaño, medido — y una corrección a lo que yo mismo dije

Primero conté TLD extranjeros entre las fuentes certificadas, me dio 1 de 318 y
estuve a punto de firmar «caso aislado». **Estaba midiendo otra cosa**: el
problema no es que la fuente sea extranjera, es que sea de un tercero.

Medido bien, sobre `platform.domain` contra el estado del directorio:

| | agencias |
|---|---|
| con `platform.domain` puesto | 2.567 |
| de esas, el directorio las dejó en `OFFICIAL_WEB_AMBIGUOUS` | 442 |
| de esas 442, el dominio **nombra entera** a la agencia | 369 |
| la nombra **en parte** | 45 |
| **no la nombra en ningún lado** | **28** |

Las 369 + 45 están bien: `abppropiedades.com.ar` para `abp propiedades` es
suya, aunque el directorio nunca haya cerrado la duda. Las 28 son el problema,
y se parten justo por la mitad:

- **14 son páginas de portal que al menos la identifican en la ruta** —`inmoup`,
  `inmoclick`, `todoprops`, `century21`, `guiadebuenosaires`, `laguiaonline`,
  `barilocheweb`, `colegioinmobiliariochaco`—. Traen algo suyo, probablemente
  parcial.
- **14 no la identifican en ningún lado**: dos notas periodísticas
  (`economis.com.ar`, `unoentrerios.com.ar`, `puntoapunto.com.ar`), un padrón de
  matriculados **en su página 33** (`cpicordoba.org.ar/matriculados/page/33/`),
  dos uruguayas (`smartservices.uy`, `century21.com.uy`) y —la peor— **el sitio
  de otra inmobiliaria**.

## Por qué el guardián de forma no alcanza

De las 14 sin identificación, 3 llegaron a la cola: `casagrande`, `arquitectura
inmobiliaria` y `danisa robledo`. **Las 3 salieron `NEEDS_FIX`**, así que hoy no
hay inventario ajeno certificado. Eso está medido, no supuesto.

Pero las 3 se salvaron por la misma razón: la fuente **no era un sitio
inmobiliario**, y sin precio ni schema el guardián de forma las frena.

`Lien Negocios Inmobiliarios` apunta a `inmobiliariabertero.com.ar`, y ahí eso
no pasa. Bertero es una inmobiliaria de verdad: cada ficha trae precio, schema
y fotos. El guardián la dejaría pasar entera y **el inventario de Bertero
quedaría atribuido a Lien**. `Lien` sigue pendiente en la cola.

> El guardián de forma detecta fuentes que **no son inmobiliarias**.
> Es ciego a fuentes que son inmobiliarias pero **de otro**.

Son dos preguntas distintas y hoy sólo se hace una.

## CORRECCIÓN de la misma tarde: medí la puerta equivocada

`cerro inmobiliaria` paró unas horas después y su fuente registrada es
`empresasdecordoba.com/pagina/Cerro-Inmobiliaria-Miguel-A-Caceres/`, otro
directorio. Pero el directorio **no** la había dejado en
`OFFICIAL_WEB_AMBIGUOUS`: la dejó en `SEARCH_SECOND_PASS_REQUIRED` —«no
terminé de buscar»— y se tomó igual su **primera candidata** como
`official_url`.

O sea que yo había condicionado la medición a un solo estado y por eso me dio
442 → 28. **La pregunta correcta no es qué decía el directorio sino qué usó la
certificación.** Medido así, sobre las 429 agencias con resultado:

| | agencias |
|---|---:|
| con resultado de certificación | 429 |
| cuyo `official_url` **no nombra** a la agencia | **34** |

Y lo que el directorio decía de esas 34:

| veredicto del directorio | agencias |
|---|---:|
| `OFFICIAL_WEB_HIGH_CONFIDENCE` | **16** |
| `OFFICIAL_WEB_VERIFIED` | **8** |
| `OFFICIAL_WEB_AMBIGUOUS` | 9 |
| `SEARCH_SECOND_PASS_REQUIRED` | 1 |

**24 de 34 estaban marcadas con confianza alta.** Mi explicación de la mañana
—«la capa que gana por precedencia no arrastra la duda de la de abajo»—
describe 9 de 34. El resto es otra cosa: el directorio estaba seguro y se
equivocó.

### Pero el detector sobre-marca, y sin decirlo el número engaña

Varias de esas 24 son **abreviaturas legítimas** que mi regla de tokens no
reconoce: `acuprop.com` para ACUÑA, `fandiprop.com.ar` para FANDIÑO,
`csgestion.com.ar` para CASTIÑEIRA SALGUERO, `azpropiedades.com` para Agustín
Zlotnik, `bmsrl.com.ar` para Bartolelli Maini.

Lo verifiqué en las **dos únicas que llegaron a `CERTIFIED_COMPLETE`**:
`ventasprop.com` se titula «Abril Negocios Inmobiliarios» y `fandiprop.com.ar`
«Fandiño Propiedades». Las dos son de su agencia.

**Cero certificaciones contaminadas.** Las que sí son fuentes de terceros están
casi todas en `BLOCKED_EXTERNAL`: el sistema las frenó. Dos muestran hasta
dónde llega el problema de registro: `ABATTE DAGA LUXURY ESTATE` apunta a
`inmoclick.ai/257787-**ayres-madero**/…` —la ruta nombra a otra agencia— y
`Abdala Negocios Inmobiliarios` apunta a `turismomardelplata.gob.ar`, un sitio
del gobierno.

### Lo que sirve para la próxima

Cuando el dominio no nombra a la agencia, **el `<title>` del sitio ayuda**, porque ahí el dueño se declara. Es distinto de contar menciones
en el cuerpo, que ya probé y falla por la razón que explica
`de_quien_es_el_dominio.py`: contar no distingue al dueño del mencionado. Leer
el título sí, y resolvió los dos casos certificados sin ambigüedad.

**Pero solo no alcanza, y lo supe usándolo.** Lo corrí sobre las 34 y `Cerro
Inmobiliaria` volvió como «suya», porque `empresasdecordoba.com` titula cada
una de sus páginas con el nombre del negocio: «Cerro Inmobiliaria Miguel A
Caceres — Empresas de Córdoba». Es un directorio y la página igual se titula
con la agencia. Igual `inmobusqueda.com/abalsamopropiedades` y
`lujanprop.com.ar/inmobiliaria/arte`.

Lo que los delata es que el título nombra **también al dominio**. Con las dos
preguntas juntas, sobre las 34:

| | agencias |
|---|---:|
| el título la nombra y **no** nombra al dominio → suya | 10 |
| el título la nombra y **sí** nombra al dominio → ficha en portal | 3 |
| el título **no** la nombra → ajena | 12 |
| sin título o sin respuesta → a revisar | 9 |

Queda un límite conocido y escrito en el test: `inmobusqueda.com` titula
«ABALSAMO PROPIEDADES» a secas, sin nombrarse, así que sus dos fichas siguen
contando como «suya». **Esto reduce el ruido, no lo elimina**, y un veredicto
sigue necesitando a alguien que lo mire. Implementado en
`de_quien_es_el_dominio.py` —`titulo_de`, `el_titulo_la_nombra`,
`el_titulo_es_del_portal`—, que está fuera de la huella.

## Un desvío que investigué y que resultó ser otra cosa

Mientras medía esto encontré 8 agencias con conector `wordpress` y cero
enumeradas, etiquetadas `publication_mechanism: SIN_INVENTARIO`, y bajé sus
sitios porque «cero inventario» es justo lo que no hay que asumir. Tres de las
ocho **sí publican**: `aguirre inmobiliaria` sirve `property` por
`wp-json/wp/v2/properties` —corrí el `discover` real y hoy devuelve
`WORDPRESS_REST, soportada=true`—, `franchi` tiene 13 fichas en `/propiedad/` y
`cintia fonzo` publica como productos de WooCommerce en
`/categoria-producto/venta`.

Estuve a punto de escribir que eso era «certificar cero en silencio». **No lo
es, y la diferencia importa.** Ninguna de las ocho está certificada: siete
están en `NEEDS_FIX` y dos en `BLOCKED_EXTERNAL`, y la razón registrada es
`one or both runs did not finish with connector state OK`. O sea que el sistema
no concluyó «esta agencia no publica»: concluyó que la corrida no terminó, y
paró. El guardián hizo lo suyo.

Lo que queda mal es la **etiqueta**. `SIN_INVENTARIO` se escribe igual cuando
la fuente no publica que cuando la corrida no llegó a mirar, y son dos cosas
distintas leídas por un humano que abre el archivo. `base.py:475` tiene
`hubo_contacto()` escrito exactamente contra esta confusión —su docstring
nombra a `aguirreinmobiliaria.com.ar`, «publica 38 propiedades»— pero separa
los estados terminales, no esta etiqueta.

Es un defecto de nombre, no de decisión, y toca `connectors/*.py`, que sí entra
en la huella. **Va a la tanda congelada, no se toca con la cola a mitad de
pasada.**

## Qué haría falta

`scripts/de_quien_es_el_dominio.py` ya responde la segunda —es el dictamen que
produjo esta tabla— pero corre a mano y después del hecho. Donde tiene que
correr es **antes de certificar**, como condición de la fuente, no como
auditoría posterior.

Y la regla de precedencia necesita que **la duda viaje hacia arriba**: si el
directorio dejó una agencia en `OFFICIAL_WEB_AMBIGUOUS`, la capa de plataforma
no debería poder resolverla en silencio. Hoy puede, y por eso pasó.

Nada de esto es de extracción, así que no toca huella y no invalida
certificaciones. Es registro de fuentes.
