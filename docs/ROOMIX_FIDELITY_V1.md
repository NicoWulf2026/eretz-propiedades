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
