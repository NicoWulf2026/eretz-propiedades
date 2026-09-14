# El 5 % de las agencias tiene el 44 % del inventario, y nunca lo leímos

**Medido el 2026-09-14/15 contra la fuente. Nada implementado. `database_writes: 0`.**

---

## 1. El número

```
inmobiliarias en el padrón   6.597     avisos observados   155.111
de red (RE/MAX, C21, CB…)      327     avisos               68.140
                             5,0 %                           43,9 %

avisos por agencia:   de red  208      resto  14
```

**327 agencias concentran el 44 % del inventario del país.** Y de ellas,
**cero fueron certificadas nunca**: sólo dos tienen algún resultado, las dos
`IDENTITY_PENDING`.

Mientras tanto, el plan de discovery apuntaba a las 2.216 `NO_WEB`, que
promedian 5 avisos cada una.

---

## 2. Por qué nunca se leyeron

Las páginas de oficina de las redes **devuelven HTTP 202 con cero bytes** a
cualquier cliente que no ejecute JavaScript:

```
https://www.remax.com.ar/titanium                 202, 0 bytes
https://global.remax.com/es/oficinas/argentina/…  202, 0 bytes
```

Eso hizo que el validador las clasificara primero como "sin web" (por un 403
con user-agent cortés) y después como "dominio parkeado" (por servir poco
texto). Las dos lecturas eran mías y las dos estaban mal: **la página existe,
lo que faltaba era poder leerla.**

---

## 3. Pero el catálogo SÍ se puede leer

La conclusión "hace falta un navegador" era prematura. Lo que está protegido es
la página de **oficina**; el catálogo no.

### a) La enumeración está publicada

```
https://www.remax.com.ar/sitemap.xml
    sitemap0.xml            378 urls   (páginas fijas)
    sitemap1.xml         20.000 urls   listings
    sitemap2.xml         20.000 urls   listings
    sitemap3.xml         20.000 urls   listings
    sitemap4.xml         20.000 urls   listings
    sitemap-agentes0.xml            (agentes)
```

Unas **80.000 fichas enumerables** con XML plano.

### b) Las fichas sirven contenido

```
https://www.remax.com.ar/listings/departamento-2-amb-alquiler-moron-con-cochera
    200, 382 KB de HTML, 8.286 caracteres de texto
    título: "Departamento en alquiler 2 ambientes en Tucumán 1000, Morón,
             Morón, Buenos Aires"
    ambientes, dormitorios y superficie presentes en el cuerpo
```

### c) Y cada ficha dice de qué oficina es

Embebido en el estado de la aplicación:

```json
"office": {
  "id": "32122ede-7f42-4aae-8746-722f336f7ba8",
  "name": "REMAX Net",
  "slug": "net",
  "description": "www.remax-net.com.ar",
  "address": "Avenida Triunvirato 3633 (C1427), Comuna 15, CABA"
}
```

Verificado sobre una muestra aleatoria del sitemap: `REMAX Namai`, `REMAX Net`,
`REMAX Roble` —esta última está en nuestro universo canónico—, cada una con id
estable, slug y, en varios casos, **el dominio propio de la oficina**.

---

## 4. Lo que esto resuelve de una sola vez

| | |
|---|---|
| enumeración | el sitemap, sin navegador |
| extracción | HTML plano en cada ficha |
| **atribución** | el `office.id` de cada ficha, que es lo más caro de conseguir |
| web de la oficina | viene en `office.description` |

La atribución es lo que lo vuelve valioso. Normalmente hay que demostrar que un
catálogo es de una inmobiliaria y no de otra; acá **la fuente lo declara en
cada ficha**, con un identificador estable.

Y resuelve el problema al revés del habitual: en vez de partir de 190 agencias
y buscarle el catálogo a cada una, se recorre un catálogo y se reparte entre las
190.

---

## 4 bis. Medido el 2026-09-15: lo que se sostiene y lo que no

Sondeo sobre 120 fichas tomadas al azar de las 74.529 publicadas.

**Se sostiene:**

| | |
|---|---|
| fichas publicadas en el sitemap | **74.529** |
| atribución cuando la ficha se lee | **prácticamente el 100 %** |
| oficinas distintas vistas en la muestra | 38 |
| de esas, en nuestro padrón | **33 (87 %)** |

**No se sostiene, y era mío:**

1. **"El dominio propio de la oficina viene en el payload."** Falso. El campo
   `description` es texto de marketing —*"Todas las propiedades que figuran en
   mi perfil…"*, *"Agentes Excelentes, Resultados Excelentes"*—. De las 38
   oficinas de la muestra, **cero** traen un dominio parseable. Lo afirmé
   generalizando desde `REMAX Net`, que puso su URL en su descripción por
   casualidad.

2. **"62.521 avisos".** Sólo el **34 % de las fichas sirve HTML**; el resto
   devuelve 202 con cero bytes. Y es **determinístico por URL**, no un límite de
   ritmo: la misma ficha devuelve vacío con 2 s y con 6 s de pausa, mientras
   otra sirve 382 KB siempre. Así que lo directamente legible son **~25.000
   fichas**, no 74.529.

**El premio real, entonces:** unas 25.000 propiedades con atribución fiable a
las oficinas. Sigue siendo más que las 18.934 de toda la cola READY actual, y
sigue sin necesitar navegador ni búsqueda paga. Pero es un tercio de lo que
dije, y no resuelve el descubrimiento de webs de las oficinas.

**Un subproducto que sí apareció:** 5 de las 38 oficinas vistas —`REMAX
Diagonal II`, `REMAX Uno`, `REMAX Uno IV` y otras— **no están en nuestro
padrón**. El sitemap también descubre agencias que no sabíamos que existían.

## 5. Qué falta comprobar antes de implementarlo

No está medido todavía, y conviene no prometerlo hasta tenerlo:

1. **Cobertura.** Cuántas de las 190 oficinas de RE/MAX de nuestro padrón
   aparecen efectivamente como `office` en el sitemap. Se mide recorriendo una
   fracción del sitemap y contando oficinas distintas.
2. **Correspondencia de identidad.** El `office.name` de la fuente contra el
   nombre canónico nuestro. `REMAX Roble` ↔ `roomix:remax roble` se ve directo,
   pero hay que confirmarlo sobre el conjunto.
3. **Century 21 y Coldwell Banker.** `century21.com.ar/sitemap.xml` da 404 y el
   de Coldwell corta la conexión. Son 129 agencias y 5.087 avisos: mucho menos
   que RE/MAX, y probablemente necesiten otra vía.
4. **Duplicación.** Una misma propiedad puede aparecer en el sitemap de la red
   y en el sitio propio de la oficina (`remax-net.com.ar`). El `hash_dedup`
   depende de `inmobiliaria_id` y `url_normalizada`, así que **entraría dos
   veces**. Hay que decidir cuál fuente gana antes de escribir.

El punto 4 no es menor: es el mismo mecanismo que ya identificamos cuando se
fusionan dos agencias.

---

## 6. Radio de huella esperado

Es trabajo de ventana semántica, no de ahora.

- Una estrategia nueva —`generic/remax_sitemap` o un conector propio— toca
  `connectors/` y por lo tanto **invalida certificaciones de esa familia**.
- No toca `shared/base`, `shared/geografia` ni `shared/texto` si se escribe como
  estrategia y no como cambio del runner.
- Radio esperado: **la familia nueva solamente**. Ninguna de las 374 agencias
  ya certificadas usa esta estrategia, así que **no debería invalidar nada de lo
  hecho**.

Eso lo vuelve barato de aplicar: se agrega, se certifica el grupo nuevo, y lo
anterior sigue vigente.

---

## 7. Prioridad

Contra las otras dos vías de discovery:

| vía | agencias | avisos | costo |
|---|---:|---:|---|
| **sitemap de RE/MAX** | **190** | **62.521** | una estrategia nueva |
| Brave sobre `NO_WEB` | 2.216 | 11.404 | ~USD 35 + verificación |
| verificar candidatas ya pagas | 1.354 | 34.809 | gratis, ya corriendo |

**Por propiedades recuperadas por unidad de trabajo, el sitemap de RE/MAX es lo
que más rinde de todo lo que hay sobre la mesa**, y es la única de las tres que
no depende de decidir bien una identidad dudosa: la fuente la declara.
