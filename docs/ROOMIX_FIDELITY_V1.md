# Roomix Fidelity V1

Base visual de ERETZ Propiedades construida deliberadamente como **base Roomix
fiel**, sobre la que después se construirá la identidad propia.

Cuando la identidad ERETZ V1 y la referencia entraban en conflicto, en esta fase
gana la referencia. El trabajo de identidad no se borró: sigue en el historial de
git y en `ERETZ_IDENTITY_V1.md`.

---

## 1. Auditoría en vivo (2026-08-12)

Medido en `roomix.ai` con sondas de `getComputedStyle` sobre el DOM real, no
desde investigación previa ni desde capturas. Se recorrieron home, resultados
(`/buscar/alquilar`), panel de filtros abierto y ficha de propiedad.

No se copió código, assets, logo, marca, textos ni contenido editorial. Lo
replicado es la lógica visual y espacial, implementada con código propio.

### Global
| | Medido |
|---|---|
| `html` | `oklch(0.12 0 0)` |
| `body` | `linear-gradient(135deg, #171717 0%, #1a1a1c 100%)` |
| Contenedor | 1265 útiles en viewport 1280 |
| Tipografía | pila del sistema (`ui-sans-serif, system-ui`) |

### Color
| Rol | Medido |
|---|---|
| Texto primario | `oklch(0.98 0 0)` ≈ `#fafafa` |
| Secundario | `#e5e7eb` · `#d1d5db` |
| Atenuado | `#9ca3af` |
| Borde de panel | `oklch(0.269 0 0)` |
| Borde de control | `oklch(0.371 0 0)` |
| Borde elevado | `oklch(0.439 0 0)` |
| Divisor de panel | `#9d4edd` al 25% |
| Acento | `#9d4edd` foco · `#7b2cbf` relleno · `#c77dff` claro · `#a855f7` sombra |

### Radios (frecuencia real en la página)
`14px` 496 usos · `16px` 70 · `9999px` 16 · `10px` 6 · `8px` 3 · `24px` overlay.

### Sombras
Casi ausentes. Las que existen: `rgba(0,0,0,.3) 0 2px 4px`,
`rgba(220,220,240,.08) 0 0 1px inset`, y una sombra de acento
`rgba(168,85,247,.2) 0 8px 32px -8px`.

### Tipografía medida
| Rol | Medido |
|---|---|
| Base | 14/400/20 |
| Énfasis | 14/600/20 |
| Título de tarjeta | 18/600/24.75 |
| Precio de tarjeta | 20/600/28 |
| H1 de ficha | 30/700/36 |
| Precio de ficha | 24/700/32 |
| H2 | 36/700/40 |
| Hero | 72/700 |
| Metadatos | 16/400/24 |
| Subtítulo | 14/400/20 `#9ca3af` |

### Shell
`navbar-wrapper` fixed, 114px, z-60, con una banda `#171717` de 64px detrás
(z-0). `search-sticky-header` sticky top-0, z-55, 126px. FAB fixed
`bottom-6 right-6`, 186×48, z-50.

### Resultados
Grilla 3 × 400.3px, gap 32, contenedor 1265.
**Tarjeta 400×360: media 400×275 + 85 de texto, fondo transparente, sin borde y
sin sombra.** Sólo la imagen lleva radio 16. El texto se apoya sobre el lienzo.

### Panel de filtros
Overlay fixed 1280×720, `rgba(0,0,0,.5)`, padding 16, z-20000.
Panel 1006×516, **radio 24**, borde `oklch(0.269 0 0)`.
Aside 291 con borde derecho violeta .25; su cabecera 280×68 con borde inferior
violeta .25; pie con borde superior violeta .25.
Ítems de categoría 229–237 × 55–61, radio 14; el activo suma borde
`oklch(0.371 0 0)`.
Limpiar 117×32 radio 14 · Aplicar 117×32 píldora. Cerrar 36×35 circular.
Contenido 725. Segmento de operación: contenedor 682×35 radio 10, botones
225×31 radio 8. Tarjetas de tipo 221×54 radio 14.

### Ficha
Mosaico **1+4**: principal 613×459 + cuatro de 302×227, gap 8, sobre el
contenedor completo de 1233. Barra de acciones flotante `fixed`, 58×362,
radio 16, z-40. Secciones separadas por hairline `oklch(0.269 0 0)`.

---

## 2. Qué se implementó

Sistema de tokens único en `frontend/src/app/globals.css`, sin parches por
pantalla. Los tokens de Identity V1 que quedaban referenciados por componentes
(`--brand`, `--pick`, `--brand-tint`…) se resolvieron contra el sistema Roomix
en lugar de dejarse como alias muertos: al cambiar la raíz habrían dejado
enlaces y la miniatura seleccionada sin color.

| Superficie | Estado |
|---|---|
| Shell y header | banda oscura, hairline inferior, sin sombra |
| Buscador | campo translúcido, foco con anillo violeta |
| Explorer | grilla 3×394.6 gap 32 en `modo=results_only` |
| Tarjetas | sin superficie, media radio 16 con ratio 400/275 |
| Filtros | panel radio 24, aside 291, divisores violeta |
| Mapa | marcadores píldora violeta con filo blanco, clúster 44px |
| Ficha | mosaico 1+4 a ancho completo, H1 30/700, precio 24/700 |
| Inmobiliarias, agentes, comparador, favoritos | mismo sistema |
| Modales, drawers, vacíos, carga y error | mismo sistema |

### Firmas de Identity V1 retiradas en esta fase
Filo verde superior · verde petróleo · terracota de selección · papel cálido ·
radios documentales 4/6/8/10/14 · marcadores-ficha · pie de tinta · versalita
de moneda en el precio · separadores documentales de metadatos.

`PriceTag` **conserva su semántica** (moneda y monto separables, estado "a
consultar"); lo que cambia es que la moneda deja de ir en versalita atenuada y
el precio se lee como un solo bloque tipográfico, como en la referencia.

---

## 3. Diferencias justificadas por función ERETZ

No penalizan la fidelidad: son capacidades que la referencia no tiene.

| Diferencia | Motivo |
|---|---|
| Tarjeta 395×490 y no 400×360 | ERETZ muestra siete líneas (tipo, título, ubicación, ambientes, publicador, fecha) donde la referencia muestra dos. No se eliminan datos; se comprimió el ritmo vertical. |
| Selector de seis modos de vista | La referencia tiene tres. Los seis son función ERETZ. |
| Cuatro categorías de filtro y no seis | Se mapean los filtros reales de ERETZ; ninguno se eliminó. |
| Panel de filtros con tri-estado y "sin información" | Capacidad propia; cambia la UI, no la semántica. |
| Directorio de inmobiliarias y agentes, claim, reportes | La referencia no tiene equivalente; adoptan el mismo sistema. |
| Comparador y colecciones | Función propia dentro del mismo sistema. |
| Marca ERETZ | Nunca se replica marca ajena. |

---

## 4. Funciones ERETZ preservadas

Verificadas contra el Preview, no asumidas:

- **Búsqueda:** universal, lenguaje natural, autocompletado, multiubicación OR.
- **Filtros:** los 17 casos server-side responden igual, ninguno inerte.
  Tri-estado y `sin información` intactos; NULL nunca se convierte en No.
- **Mapa:** marcadores, clústeres, sincronía lista↔mapa, "buscar en esta zona"
  (aparece al mover y no queda interceptado), restauración por URL.
- **Estado local:** favoritos, visitadas, ocultas, recientes, colecciones,
  comparador.
- **Ficha:** galería, calidad de imágenes, precio, disponibilidad, mapa,
  publicador, aviso original, contacto, similares, disclaimers.
- **Restauración:** filtros + resultados + scroll exacto (416 → 416).
- **106835:** sus tres fotos reales visibles, el logo de Bessa filtrado.
- **Baselines:** `193615 / 62549 / 131066` sin cambios.

---

## 5. QA

| | Resultado |
|---|---|
| tsc / eslint / Vitest / build | 0 · 0 · **184/184** · OK |
| Regresión funcional | **15/15** |
| axe | **0 critical / 0 serious** en 7 páginas × 2 anchos |
| Lighthouse | accesibilidad **100**, best-practices **100**, performance **90** explorer / **84** ficha |
| Responsive | 1440 / 1280 / 1024 / 768 / 390 sin overflow |
| Errores JS | ninguno |

### Defectos corregidos durante la fase
1. La galería de la ficha estaba encajonada en la columna de 1.6fr: su mosaico
   corría a 419px donde la referencia usa la mitad del contenedor completo.
   Ahora ocupa el contenedor y cae en 628px, la misma proporción de 49.7%.
2. El tope de altura de la media aplastaba las fotos a 176px contra los 275 de
   la referencia.
3. `bg-slate-100`, `bg-amber-*` y `bg-emerald-*` sobrevivían en componentes:
   sobre el lienzo oscuro dejaban texto claro sobre superficie clara.
4. El marcador de posición del mapa conservaba una trama azul clara y un
   resplandor radial blanco de la fase clara.
5. `--brand` y `--pick` seguían referenciados en 11 componentes y, al cambiar
   la raíz, resolvían a nada.

### Performance
El explorer pasó de 94 a 86 al adoptar el ratio de tarjeta de la referencia
(hay más píxel de foto por tarjeta). Se recuperó a **90** saltando el render de
las tarjetas fuera de pantalla con `content-visibility`, sin cambiar nada
visualmente y sin reintroducir `backdrop-filter`.

---

## 6. Estado final

**ROOMIX_FIDELITY_V1: CERRADO**

| | |
|---|---|
| Resultado funcional | **PASS** |
| Resultado visual/espacial | **PASS**, según mediciones DOM reales |
| Regresión | **15/15** |
| Vitest | **184/184** |
| TypeScript | **0 errores** |
| ESLint | **0 errores** |
| Build | **OK** |
| axe | **0 critical / 0 serious** |
| Lighthouse | accesibilidad **100**, best-practices **100** |
| Baselines | **193.615** · **62.549** · **131.066** |
| Producción | **intacta** |
| Identidad propia de ERETZ | **pendiente de fase futura** |
| `docs/ERETZ_IDENTITY_V1.md` | **preservado** como fuente para esa futura fase |

Preview de cierre: `dpl_5xhTjMxJU29z9RxN1thtkj6bpBvS`
(`eretz-propiedades-7dv1wyfvh-nicowulf2026s-projects.vercel.app`), target
`preview`, Ready, protegido y con `noindex, nofollow`.

Nota sobre §5: la cifra de performance 90 corresponde a la medición intermedia.
Sobre el Preview de cierre el explorer midió **97** y la ficha **87**.

### Limitación documental

No se generaron pares visuales Roomix ↔ ERETZ porque el entorno utilizado no
permitía componer/capturar el panel del navegador. La comparación final se
realizó mediante mediciones del DOM real y `getComputedStyle`. Esto no
constituye una deuda funcional ni bloquea el cierre de ROOMIX_FIDELITY_V1.

---

## 7. Home y arquitectura de rutas (2026-08-13)

La fase original nunca auditó ni tocó `/`. El producto no tenía landing: `/`
servía el explorador directamente, mientras que el home de la referencia es una
página de 7.410px con dieciséis bloques.

### Auditado en vivo
| y | Bloque | Composición |
|---|---|---|
| 87 | Hero | H1 **72/400/82.8** centrado, `ls -1.8px`, ancho 896 |
| 308 | Tarjeta de búsqueda | **663×131, radio 26**, `rgba(41,41,41,.95)`; textarea 634×58 a **18px/400** sin borde; segmento de operación 151×34 **radio 10** con píldora activa 72×28 **radio 8** en `#c77dff` |
| 720 | Features | H2 36/700/40 centrado + 3 tarjetas con icono 84×84 |
| 1312 | Explorá por ciudad | 9 tarjetas **288×216 radio 16** |
| 1560 | Chips de ciudad | 39 enlaces |
| 1764–4148 | 6 carruseles | tarjetas 288×216, **gap 16**, `overflow-x: auto` |
| 4148 | Bloque B2B | 544 de alto |
| 4692 | Herramientas | H2 centrado + 3 items 16/600 |
| 4990 | Explorá por barrio | 22 tarjetas + 104 chips |
| 5640 | Informativo | 1.023 de alto |
| 6663 | Footer | 4 columnas, H3 14/600 |

Ritmo de sección: **~394px**.

### Implementado
`/` es ahora el landing con esa composición y `/propiedades` sigue siendo el
explorador —ruta que ya existía—. Cualquier deep-link antiguo a `/` con
parámetros de búsqueda **redirige a `/propiedades` conservando todos los
parámetros**; verificado 8/8 en la QA de routing.

Todo dato del home sale de una consulta real: conteos por ciudad y barrio desde
`searchProperties`, carruseles de publicaciones recientes, franja del directorio
real de inmobiliarias y total del inventario vivo. Un bloque sin inventario no
se renderiza; no hay cifras de relleno.

### Diferencia justificada: tarjetas de lugar tipográficas
La referencia usa imagen curada por ciudad. ERETZ no tiene ese dataset y usar la
foto de un aviso cualquiera mostraba **logos de inmobiliaria como portada de la
ciudad**: el clasificador por URL no detecta un logo servido con nombre genérico
desde el CDN de la propia inmobiliaria, y una heurística de repetición tampoco
lo caza dentro de una sola página de resultados. Inventar imágenes estaba
descartado, así que el bloque conserva la geometría (288×216, radio 16) y se
resuelve con el dato que sí es cierto: nombre y conteo.

### Diferencia justificada: altura
El home de ERETZ mide ~5.400px contra los 7.410 de la referencia, porque tiene
menos carruseles de barrio: sólo se generan los que tienen inventario real.

---

## 8. CSS Architecture Closure (2026-08-13)

### Capas que existían
`globals.css` tenía diez bloques encadenados por orden de fuente:

| # | Bloque | Rol |
|---|---|---|
| 0 | Raíz Roomix + base histórica | tokens actuales sobre el sistema navy/oro retokenizado |
| 1 | Cierre de defectos de ficha | parche |
| 2 | Roomix-derived foundations (U2) | métricas |
| 3 | U3 grilla | métricas |
| 4 | U6 densidad de card | métricas |
| 5 | **Roomix Fidelity — capa de superficie** | el sistema visual real |
| 6 | Tarjeta de búsqueda | añadido |
| 7 | Home | añadido |
| 8 | Pase de verificación | correcciones |
| 9 | **U8 panel de filtros** | cargaba **último** |

**34 selectores** se declaraban en más de un bloque con propiedades de riesgo en
conflicto. El caso que se detectó en producción —el panel de filtros volviendo a
radio 16— no era único: era el síntoma visible de ese patrón.

### Qué se consolidó
- **Utilidades ajenas.** 120 clases Tailwind de las escalas `slate`, `amber` y
  `emerald` vivían en 19 componentes, y el CSS global cargaba un bloque cuyo
  único trabajo era ganarles con `!important`. Se migraron a utilidades
  semánticas propias (`.u-text`, `.u-surface`, `.u-warn-text`…) y el bloque
  neutralizador desapareció.
- **`.filter-panel`.** Se declaraba en cuatro lugares de tres épocas: un drawer
  lateral histórico, la capa Roomix y el bloque del panel. Quedan sólo las
  declaraciones del bloque del panel más la transición del drawer, que aquél no
  declara.
- **CSS muerto.** `.nav-contact` no tenía uso en ningún componente.

### `!important`
| | Antes | Después |
|---|---|---|
| Internos | **14** | **0** |
| Leaflet (terceros) | 15 | 15 |
| `prefers-reduced-motion` | 9 | 9 |

Los de Leaflet son justificados: su hoja nativa declara `border-radius`,
tamaños y colores en los controles de zoom, popup y atribución con reglas que de
otro modo ganan. Los de `prefers-reduced-motion` deben ganarle a todo por
definición.

### Excepción de comportamiento corregida
El CTA de WhatsApp llevaba `bg-emerald-700` y el bloque neutralizador lo estaba
forzando en silencio al violeta de marca. Al retirar el bloque habría quedado
verde, así que se le quitó la clase de color: `.primary-button` lo pinta.

### Prueba de que el render no cambió
Huella de estilos computados: **500 registros** (75 selectores × 10 superficies ×
2 anchos), capturada antes y después. **Cero diferencias atribuibles a estilos.**
Las dos únicas deltas son la franja de inmobiliarias del home apareciendo en una
captura y no en la otra, que es timing de la consulta.

### Hallazgo abierto para la fase de identidad
Al capturar Roomix con Playwright directo (UA real) se obtuvo el home en
**HTTP 200 y en tema CLARO**: fondo blanco con degradado violeta y titular
**serif itálico**. Todas las mediciones de esta fase se tomaron a través del
panel del navegador, que corría con `prefers-color-scheme: dark`, de modo que la
base construida corresponde al **tema oscuro de Roomix**, que es un tema real
suyo. La ruta de resultados sigue devolviendo 403 por anti-bot.

Esto no invalida la base aprobada, pero conviene tenerlo presente cuando se
diseñe ERETZ Identity V2: la referencia tiene dos temas y una tipografía de
display serif que esta fase no replicó.
