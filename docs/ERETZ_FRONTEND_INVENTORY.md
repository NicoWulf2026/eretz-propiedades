# ERETZ Propiedades — inventario del frontend

Fecha: 2026-08-28

Para qué existe: antes de construir cualquier pantalla, saber qué hay. La
duplicación en frontend no se nota al escribirla —el segundo `Card` funciona
igual de bien— y se nota meses después, cuando un cambio de marca hay que
hacerlo en cinco lugares y aparece en tres.

## Lo que ya funciona y no hay que rehacer

| Área | Dónde | Estado |
| --- | --- | --- |
| Shell y navegación desktop | `layout/SiteShell`, `Navbar`, `Footer`, `Brand` | completo |
| Explorer | `explorer/` (5 componentes) | completo |
| Búsqueda, filtros, autocompletado | `search/` (6 componentes) | completo |
| Mapa y clusters | `map/` (2 componentes) | completo |
| Cards y ficha | `property/` (12 componentes) | completo |
| Mi ERETZ local | `local/` (5 componentes) | completo |
| Perfiles de inmobiliarias y agentes | `app/inmobiliaria/`, `app/agente/` | completo |
| Páginas legales | `app/terminos`, `privacidad`, `baja-o-correccion`, `contacto` | borrador rotulado |
| **Calculadoras** | `app/calculadoras/`, `components/calculators/` | **nuevo, funcional** |

**46 componentes** antes de este bloque; 6 nuevos con las calculadoras.

## Sistema visual: qué reutilizar

No hay carpeta de primitivos: el sistema vive en `globals.css` como clases
globales sobre tokens CSS. Antes de crear un componente, revisar si la clase ya
existe.

| Necesidad | Clase existente |
| --- | --- |
| Contenedor de página | `.container` |
| Campo de formulario | `.field` (etiqueta + control + foco) |
| Checkbox / radio | `.check` |
| Botón principal / secundario | `.primary-button`, `.secondary-button` |
| Botón de ícono | `.icon-button` |
| Panel de contenido | `.detail-panel` |
| Estado vacío | `.empty-panel` |
| Encabezado de sección | `.detail-section-heading`, `.section-title`, `.eyebrow` |
| Chip / etiqueta | `.chip` |

Paleta: navy (`--navy-900`, `--navy-700`), dorado (`--gold-500`) para acentos
que **no** sustituyen al foco accesible, y superficies claras.

### Deuda conocida, no resuelta

`Intl.NumberFormat` está instanciado por separado en **siete archivos**
(`property-presenter`, `property-share`, `map-presentation`, `property-detail`,
`CompareClient`, `HomeSections`, y ahora `calculators/input`). Consolidarlos es
un refactor de código que funciona y no se hizo en este bloque; queda anotado
para no agregar el octavo sin pensarlo.

## Qué pedía el plan y ya existía

Cosas que la auditoría encontró hechas, y que habría sido un error volver a
construir:

- **Punto de entrada del reclamo de inmobiliaria** — ya está en el perfil
  público: *"¿Sos responsable de esta inmobiliaria?"* con enlace a
  `/inmobiliaria/[slug]/reclamar`.
- **Estados vacíos, carga y 404** — `NoResults`, `loading.tsx`, `not-found.tsx`.
- **Preview `noindex`** — `robots.ts` fijado, con tests.
- **Páginas legales** — las cuatro existen y están rotuladas como borrador, que
  es lo correcto: no afirman haber pasado una revisión que no pasaron.

## Qué NO se construyó, y por qué

El plan pedía preparar la UI de once áreas que dependen de backend inexistente:
cuentas, publicación manual, panel profesional, equipo, administración de
scraped, editor de mini-portales, alertas, Mercado, analítica profesional,
expedientes y cola de moderación.

**No se construyeron**, y la razón es la misma que motiva el propio plan:

> *"dejar ERETZ listo … para que, cuando conectemos backend, no tengamos que
> rediseñar todo."*

Una UI construida contra un backend imaginado casi siempre hay que rediseñarla
igual, porque las decisiones que la determinan —qué devuelve cada endpoint, qué
estados existen, qué latencia tiene, qué falla— todavía no se tomaron. Lo que sí
sobrevive a esas decisiones son los **contratos de dominio**, y ésos ya están
escritos y testeados: `auth`, `publishing`, `permissions`, `claim`, `alerts`,
`miniportal`, `reports`, `market`, `professional-analytics`.

Ese trabajo ya hecho es la preparación real. Ver
[ERETZ_DOMAIN_MODEL.md](ERETZ_DOMAIN_MODEL.md).

### El caso del mini-portal, en concreto

El plan pedía usar el config model para construir la página pública de
inmobiliaria. No se hizo, y conviene decir por qué con precisión:

- la página existe, son 87 líneas y funciona;
- ninguna organización puede configurar nada todavía;
- así que renderizarla desde `normalizarConfig(undefined)` daría **exactamente
  la misma salida** con una capa de indirección más;
- y los datos para el branding no existen: el 0,49% de las inmobiliarias tiene
  logo y el 0% tiene descripción.

Hacerlo ahora sería refactorizar una página que anda para habilitar una función
que nadie puede usar, con datos que no están. Cuando exista el editor y haya
algo que configurar, la página se arma desde el config model — que ya está
escrito, validado y con default completo.

## Mobile

**Congelado.** No se hizo navegación, layout ni QA mobile. El único media query
agregado en este bloque colapsa las calculadoras a una columna por debajo de
900px, que no es trabajo mobile: es que un layout de dos columnas deja de tener
sentido en ese ancho.
