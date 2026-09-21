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
