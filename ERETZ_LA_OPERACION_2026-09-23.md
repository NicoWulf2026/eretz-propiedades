# La operación: 2.032 vacías, 64 equivocadas y 220 propiedades que no existen

**2026-09-23 · `database_writes: 0`**

Fui a resolver el ítem 18 del lote congelado —«la operación se pierde, y son
245 propiedades»— y el número era otro. Midiendo sobre los paquetes de
certificación completos:

| | |
|---|---:|
| propiedades del conector genérico | 10.985 |
| sin `operacion`, en 51 agencias | **2.032** |
| con `operacion` **equivocada** | **64** |
| «propiedades» que son archivos `.jpg` | **220** |

Las 245 del ítem eran sólo el cubo `source_not_provided`. Las otras 1.787
estaban clasificadas como «la fuente no lo publica» sin que nadie hubiera ido
a mirar la fuente.

Una propiedad sin saber si se vende o se alquila casi no sirve para buscar.
Una con la operación **al revés** es peor: el que quiere comprar no la ve, y
el que quiere alquilar la ve y no puede alquilarla.

## 1. El menú deja ambigua toda la ficha (2.032 vacías)

`_operacion_en_la_ficha` mira los primeros 600 caracteres y exige que aparezca
**una sola** de las dos operaciones. Es una regla correcta —contar el menú
pondría «venta» en todas, incluidas las de alquiler— pero el menú está
justamente ahí:

```
Inicio Propiedades Venta Alquiler Tasación Sobre nosotros Contacto
Detalle | Casa en Catamarca ... 1 Dorm 1 Baño 120 m² USD 30.000 En venta
```

`atencio propiedades` dice «En venta» pegado al precio y otra vez más abajo
—«Venta: USD 30.000»— y quedaba sin operación en **256 de 328**. `conti`
—«En venta U$S 440.000»— en **263 de 290**. `eckert` en 27 de 31.

**La señal que distingue el aviso del resto de la página es el precio.** No
cualquier precio: el que ya extrajimos para esta propiedad. Las «Últimas
propiedades» del pie traen sus propios precios y su propia operación, y son
las del vecino; anclar en el número ya extraído las deja afuera sin tener que
adivinar dónde termina la ficha.

Si las apariciones de ese precio no coinciden todas en la misma operación, no
se devuelve nada. `bottai` publica un buscador con «Venta | Alquiler» y ahí la
página no está diciendo cuál es.

**Medido sobre 72 fichas reales de 50 agencias** (una descarga por ficha,
contra la fuente): **22 pasan de vacío a tener operación**, ninguna correcta
se pierde.

## 2. «Alquilado» no quiere decir alquiler (64 equivocadas)

La regla del estado consumado estaba **primera** y ganaba siempre:

```python
if re.search(r"\balquilad[oa]\b", texto, re.I):
    return "alquiler"
```

Su intención está escrita en su propio comentario: «conserva la semántica de
la operación **aunque el aviso ya no publique precio**». Esa condición nunca
se programó. Con precio adelante, la palabra significa otra cosa:

| agencia | lo que dice la ficha | precio | guardado |
|---|---|---:|---|
| `alma di matteo` | «IDEAL INVERSIONISTAS, **SE VENDE ALQUILADO**» | USD 139.000 | alquiler |
| `buhler` | «**En venta** USD 33.000 … Alquilado hasta 30-09-2026» | USD 33.000 | alquiler |
| `bottai` | «…primer piso por escalera. **Alquilado**. Precio: U$S55.000» | USD 55.000 | alquiler |

Son ventas con inquilino adentro. 64 propiedades tenían el estado consumado
en su texto y **las 64** estaban guardadas como alquiler; 48 son de `bottai`,
con precios de U$S 55.000 a U$S 250.000.

Dos cambios, y el segundo es el que importa:

1. El estado consumado pasa a ser la **última** pregunta, no la primera.
2. Sólo se consulta **cuando no hay precio**, que es la condición que la regla
   decía tener. Con precio, el aviso está vivo: la operación tiene que salir
   de lo que el aviso dice, y si no lo dice, se queda vacía.

`bottai` pierde 48 valores llenos. Estaban mal. Un campo vacío se completa
después; uno equivocado se publica.

## 3. Una imagen no es una ficha (220 propiedades inventadas)

`building inmobiliaria` publica **77** propiedades y nosotros guardamos
**297**. Las 220 de diferencia son sus fotos:

```
https://inmobiliariabuilding.com.ar/storage/properties/209/original_6aa2a3a24d3b3.jpg
    titulo: null   operacion: null   precio: 320.0
    source_listing_id: "original_6aa2a3a24d3b3.jpg"
```

Para `RE_FICHA_ANIDADA` esa ruta es indistinguible de una ficha: sección
`properties`, id `209`, un último segmento cualquiera. El **74 % del
inventario** de esa agencia era inventado, con precios sacados de la nada.

La regla que lo evita **ya existía**: `scraper/detail_urls.py` descarta esas
extensiones desde siempre. `_es_ficha_url` tenía su propio criterio y nunca se
enteró. Por eso ahora importa la lista de allá en vez de escribir una segunda:
es la quinta vez en este trabajo que la misma regla escrita dos veces termina
diciendo cosas distintas.

Es un solo caso en todo el corpus —se midió sobre las 23.936 propiedades
guardadas— pero es el peor tipo: inventario inventado, no inventario perdido.

## Lo que no se tocó

`bottai`, `pozzobon` y `constant` siguen sin operación, y está bien: sus
fichas **no la dicen**. El dato existe pero sólo en la ruta del catálogo desde
la que se llegó (`/venta/` contra `/alquiler/`), y eso es el ítem 18(b): que
`generic/html_catalog` arrastre esa procedencia, como el conector de Tokko ya
hace con `RUTAS_POR_OPERACION`. Queda pendiente y es la mitad grande que falta.

## Costo y momento

Los tres cambios tocan `connectors/generico.py`, que es el componente
`generic/common` de la huella: invalidan las certificaciones de la familia
`generico` —366 de las 791 agencias de la cola—.

Es el momento más barato posible para hacerlo: esa familia **ya está
detenida** desde las 12:29 de hoy por el paro de `alagna propiedades`, y no
va a correr hasta que su diagnóstico esté firmado. Los otros 311 agencias
siguen certificando mientras tanto, que es justamente lo que el acotamiento
por familia vino a permitir.
