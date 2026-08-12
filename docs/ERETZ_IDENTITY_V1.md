# ERETZ Identity V1

Sistema visual de ERETZ Propiedades. Documenta lo que está **implementado** en
`frontend/src/app/globals.css`, no una propuesta.

La disciplina espacial (grilla de 3 columnas, densidad, contenedor de 1280,
split 60/40, panel de filtros master-detail, galería en mosaico, alturas de
control de 36/44px, responsive) viene de la fase anterior y **no se toca aquí**.
Identity V1 define únicamente el carácter.

---

## 1. De dónde sale la dirección

De la documentación de marca real del proyecto, no de una preferencia estética:

| Fuente | Qué aporta |
|---|---|
| `docs/obsidian/01 - Estrategia` | Plataforma proptech, no un portal más. **"El mapa es el centro de la experiencia."** Trazabilidad a la fuente. Calidad antes que cantidad. Producto simple, sistema interno robusto. Alcance nacional. |
| `docs/obsidian/06 - Marketing y marca` | Plataforma de inteligencia inmobiliaria accesible. "No mostramos propiedades solamente. Te ayudamos a entender el mercado." Evitar parecer un portal inmobiliario tradicional. |
| `docs/obsidian/02 - Producto` | ERETZ organiza y deriva: no vende ni reemplaza a la inmobiliaria. |

**No existía** ninguna definición previa de paleta, tipografía ni logotipo. El
navy/oro de la fase A y el violeta oscuro de la fase Roomix fueron decisiones de
frontend, nunca doctrina de marca. `public/brand/` sigue vacío y "incorporar
logo real" figura como pendiente en tres notas.

No se introdujo ninguna interpretación cultural, religiosa ni política del
nombre. El sistema se diseñó desde el producto y su categoría.

## 2. Carácter de marca

1. **Cartográfico** — el mapa no es una función, es el centro.
2. **Documental** — cada dato se lee como un registro trazable a su fuente.
3. **Preciso** — números tabulares, alineados, comparables.
4. **Sobrio** — la superficie se retira para que manden la foto y el dato.
5. **Accesible** — público general, lenguaje llano, contraste alto.
6. **Neutral por diseño** — debe contener miles de inmobiliarias sin imponerse.

## 3. Principios visuales

1. El dato antes que la decoración.
2. La superficie nunca compite con la fotografía de la propiedad.
3. **El verde es la marca y lo interactivo. La terracota es la selección del
   usuario. Nunca son sinónimos.**
4. Bordes sólidos y hairline; sombra sólo donde algo flota de verdad.
5. Movimiento que confirma, no que entretiene.
6. ERETZ es marco: en la página de una inmobiliaria ajena, la marca se retira.

## 4. Base clara — por qué

| Razón | Detalle |
|---|---|
| Cartografía | Los tiles OSM son claros. Un shell oscuro convierte al mapa —el centro del producto— en un rectángulo que encandila. |
| Fotografía | Las fotos son el contenido. Sobre papel se leen como objetos; sobre negro brillan y se distorsionan los tonos. |
| Lectura prolongada | Comparar precios y zonas es lectura numérica sostenida. |
| Público general | Uso móvil, en exteriores, por gente que no es usuaria técnica. |
| "Producto simple" | Es principio estratégico explícito. |

Una sola dirección. No hay theme switcher ni modo oscuro.

## 5. Color

Roles reales, no una lista de colores.

### Lienzo y superficies
| Token | Valor | Uso |
|---|---|---|
| `--canvas` | `#edeae3` | Fondo de página: papel cálido. Es la mesa. |
| `--surface-1` | `#ffffff` | Cards, paneles, ficha. Es el documento. |
| `--surface-2` | `#f4f2ec` | Hundido: inputs, celdas, toolbar. |
| `--surface-3` | `#e5e1d8` | Pozo profundo / hover sobre hundido. |
| `--elevated` | `#ffffff` | Modales y dropdowns (con sombra real). |

### Tinta
| Token | Valor | Contraste sobre lienzo |
|---|---|---|
| `--ink` | `#14201d` | ~16.9:1 |
| `--ink-2` | `#46524f` | 6.7:1 |
| `--ink-3` | `#5f6a66` | 4.7:1 |
| `--ink-inverse` | `#ffffff` | — |

La tinta es un grafito verdoso, no un gris azulado: da temperatura propia y
evita el frío de portal genérico.

### Líneas
`--line: #e0ddd5` · `--line-strong: #c8c4b9`. Sólidas y cálidas, **nunca
translúcidas** — es una diferencia deliberada con la referencia anterior, que
usaba cantos de blanco translúcido sobre oscuro.

### Marca — verde petróleo
| Token | Valor | Uso |
|---|---|---|
| `--brand` | `#0d5c55` | Monograma, CTA, foco, link, categoría activa, clúster. 7.8:1 sobre blanco. |
| `--brand-hover` | `#0a4a45` | |
| `--brand-active` | `#073833` | |
| `--brand-tint` | `#e4efed` | Relleno suave de estado activo. |
| `--brand-tint-strong` | `#cbe0dc` | Selección de texto. |

Verde petróleo y no azul: el azul de portal es el cliché de la categoría, y en
cartografía compite con el agua.

### Selección del usuario — terracota
| Token | Valor | Uso |
|---|---|---|
| `--pick` | `#a8421f` | Marcador seleccionado, miniatura activa, card elegida, comparación. 6.1:1 sobre blanco. |
| `--pick-hover` | `#8c3719` | |
| `--pick-tint` | `#fbeee8` | |

El contrapunto cálido es lo que hace legible de un vistazo qué eligió el usuario
y qué es simplemente interactivo.

### Semánticos
`--ok #1c6b47` · `--warn #8a5a06` · `--bad #a32218` · `--info` = `--brand`.
Cada uno con su `-tint`.

### Mapa
`--marker-bg #ffffff` · `--marker-ink`/`--marker-line` = `--ink` ·
`--marker-selected-bg` = `--pick` · `--cluster-bg` = `--brand`.

## 6. Tipografía

**Inter**, autoalojada por `next/font` (sin requests a terceros, sin layout
shift, licencia SIL OFL). Una sola familia en todo el producto.

Se retiró Instrument Serif: una serif de display contradice el posicionamiento
proptech y arrastraba a la estética de inmobiliaria de lujo.

| Rol | Tamaño / peso |
|---|---|
| Wordmark `ERETZ` | 1.02rem / 700 / tracking .13em |
| Wordmark `PROPIEDADES` | .5625rem / 600 / tracking .2em / `--ink-3` |
| H1 | 2.5rem / 700 / -.03em |
| H2 | 1.5rem / 700 |
| Precio en card | 1.28rem / 700 tabular |
| Precio en ficha | 2.1rem / 700 tabular |
| Moneda | .62em / 600 / tracking .1em / `--ink-3` / versalita |
| Cuerpo | .9375rem / 1.55 |
| Etiquetas y badges | .75rem / 600 |
| Eyebrow | .75rem / 700 / tracking .14em / mayúsculas / `--brand` |

Cifras tabulares (`tnum`) en todo lo comparable: precios, superficies, conteos,
marcadores.

## 7. Geometría

**Radios — escala documental**, más cerrada que los 16px de la referencia:
`--radius-xs 4` · `--radius-sm 6` · `--radius-md 8` · `--radius-lg 10` ·
`--radius-xl 14` · `--radius-pill 999`.

Controles a 8, cards y paneles a 10, overlay del panel de filtros a 14, píldora
sólo para chips y badges. El resultado se lee como documento, no como burbujas
de app.

**Sombras — casi planas.** Las cards no tienen sombra: llevan borde. Sólo
flotan los overlays.
`--shadow-xs` a `--shadow-xl`, de `0 1px 0 rgba(20,32,29,.04)` a
`0 24px 64px rgba(20,32,29,.18)`.

**Espaciado:** escala heredada `--space-1..9` (.25rem a 4rem), sin cambios.

## 8. Elementos firma

Cuatro recursos repetibles, todos derivados del sistema.

1. **El filo de marca.** 3px de `--brand` fijos en el borde superior de la
   página. Es lo único permanentemente coloreado del shell: la marca está sin
   ocupar superficie.
2. **El precio como dato.** Moneda en versalita atenuada delante, monto en
   cifras tabulares con tracking cerrado. Idéntico en tarjeta, ficha,
   comparador y marcador (`components/property/PriceTag.tsx`).
3. **Marcadores-ficha.** En el mapa, un precio se lee como etiqueta de
   documento: fondo papel, tinta oscura, filo definido de 1.5px, radio 6.
   No son globos ni pines. Seleccionado: relleno terracota.
4. **La selección entra por el filo izquierdo.** `inset 3px 0 0 var(--pick)`
   con la misma gramática en card, sugerencia, categoría de filtro y fila de
   comparación.

Además: filete de marca de 2.5rem bajo los títulos de sección, y el pie como
única superficie de tinta llena del producto.

## 9. Iconografía

Familia única de trazo, alineada a la caja de control de 36/44px. Los controles
de acción de card miden 36px. No se copió ningún icono propietario de la
referencia.

## 10. Movimiento

`--motion-fast 120ms` (hover, press, estados), `--motion-normal 180ms` (paneles
y drawers), `--motion-slow 260ms`. Curva `--ease-out cubic-bezier(.22,.61,.36,1)`.

Se anima color, borde y sombra. El único desplazamiento es 1px de hundido al
presionar un botón. `prefers-reduced-motion: reduce` neutraliza transiciones,
animaciones, scroll suave y el escalado del marcador seleccionado.

## 11. Accesibilidad

- axe: **0 critical / 0 serious** en explorer, filtros, ficha, inmobiliarias,
  comparar, favoritos y mapa, a 1440 y a 390.
- Todo par texto/fondo del sistema verificado ≥4.5:1; `--ink-3` es el piso.
- Foco visible: `outline: 2px solid var(--brand)` con offset 2px, más
  `--focus-ring` en campos.
- El panel de filtros devuelve el foco a `.filter-toggle` al cerrarse con
  Escape.
- Ningún estado se comunica sólo por color: la selección suma filo, el activo
  suma peso tipográfico, el visitado suma etiqueta "Vista".

## 12. Logotipo

**No existe un logotipo oficial.** Identity V1 resuelve la marca con un
monograma `E` en `--brand` (radio 6) más un wordmark tipográfico en Inter. Es
una adaptación cromática y tipográfica del asset que ya estaba en el código, no
un símbolo nuevo. Queda pendiente el logo real en `public/brand/`, como ya
registra la documentación de producto.

## 13. Do / Don't

| Hacer | No hacer |
|---|---|
| Usar `--brand` para lo interactivo y de marca | Usar `--brand` para marcar lo que el usuario eligió |
| Usar `--pick` para la selección del usuario | Usar `--pick` como segundo color decorativo |
| Cards con borde y sin sombra | Cards con sombra y sin borde |
| Superficies que se retiran detrás de la foto | Bloques de color detrás del contenido |
| Cifras tabulares en todo lo comparable | Números proporcionales en precios |
| Radios de 6 a 10 | Volver a la escala de 14–16 |
| Escala de tinta ERETZ | Reintroducir la escala slate de Tailwind |
| Marcadores como etiqueta de dato | Volver a pines o globos de color |
| Un solo tono en toda la interfaz | Mezclar navy, oro o violeta históricos |
| Sombra sólo en overlays | Reintroducir Liquid Glass, blur o cantos ópticos |

## 14. Deuda técnica registrada

- **Logotipo real** pendiente (`public/brand/`).
- Quedan ~90 utilidades Tailwind de la escala `slate` en 12 componentes. Están
  remapeadas a la escala de tinta ERETZ en CSS, así que **renderizan
  correctamente**, pero la clase sigue diciendo `slate`. Migrarlas a clases
  semánticas es trabajo de limpieza, no de identidad.
