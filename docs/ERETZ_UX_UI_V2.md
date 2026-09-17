# ERETZ Propiedades — UX/UI V2

Fecha de corte: 2026-08-27

Rama de referencia: `feat/eretz-frontend-phase-a`

Checkpoint publicado: `a31612c1523de8925dd89417129ebebfabb2951a`

## Propósito y estado

UX/UI V2 es el frontend desktop/web actual de ERETZ Propiedades. El checkpoint está publicado en su rama remota, no está mergeado a `main` y no representa producción pública. El último Preview validado funcionalmente corresponde a `e9d8860249`; Vercel Authentication, `noindex`, `nofollow` y robots bloqueado permanecen activos. La corrección posterior `a31612c152` cambia únicamente el contraste de dos etiquetas de ficha y pasó lint, typecheck, build y 226/226 tests.

El producto debe permitir explorar sin cuenta. ERETZ ordena publicaciones de terceros y nunca vende posiciones dentro del ranking orgánico.

## Arquitectura actual

- Next.js 16 App Router, React 19 y TypeScript.
- Render server-side para inventario, directorios y fichas; estado interactivo en componentes cliente acotados.
- PostgreSQL server-only mediante `postgres`, Transaction Pooler, SSL, `prepare: false`, pool máximo 2 y transacciones explícitas `READ ONLY`.
- Rol de Preview dedicado `eretz_preview_ro`, sin superuser, `BYPASSRLS`, creación ni escritura sobre objetos de aplicación.
- Quality Gate privado cargado desde Vercel Blob, validado y aplicado fail-closed en servidor.
- Leaflet/OpenStreetMap para cartografía; clustering conserva el límite server-side.
- Favoritos, colecciones, comparación, historial y búsquedas en `localStorage`; todavía no existe sincronización de cuenta.
- CSP, headers de seguridad, Vercel Authentication y ejecución `iad1` en Preview.

## Rutas implementadas

| Ruta | Estado | Propósito |
| --- | --- | --- |
| `/` y `/propiedades` | Implementada | Explorer map-first, búsqueda, filtros, resultados y mapa |
| `/propiedad/[id]` | Implementada | Ficha V2 y 404 específico |
| `/mi-eretz` | Implementada local | Guardadas, Colecciones, Comparar, Historial y Búsquedas |
| `/favoritos`, `/colecciones`, `/comparar` | Compatibilidad | Entradas históricas compatibles con Mi ERETZ |
| `/inmobiliarias`, `/inmobiliaria/[slug]` | Implementada | Directorio y perfil público real |
| `/agentes`, `/agente/[slug]` | Implementada | Directorio derivado de publicaciones y perfil real |
| `/inmobiliaria/[slug]/reclamar` | Parcial | Reclamo de perfil como señal; nunca auto-aprueba |
| `/terminos`, `/privacidad`, `/contacto`, `/baja-o-correccion` | Implementada | Información y canales públicos |

## Explorer

El Explorer responde primero dónde buscar, qué resultados hay y cómo alternar la vista. Mantiene tres modos desktop:

- Mapa + propiedades, predeterminado.
- Solo propiedades, con grilla responsive.
- Solo mapa, preservando búsqueda, filtros y conteo.

La selección de vista, filtros, búsqueda y propiedad seleccionada se representan en URL. Hover no cambia URL. La paginación de resultados usa cursor keyset y el rail conserva una densidad de dos columnas cuando su ancho lo permite.

### Búsqueda y filtros

- Búsqueda textual y sugerencias sobre ubicación, dirección, publicador, agente, tipo e ID.
- Interpretación natural determinista; no depende de un proveedor de IA.
- Filtros rápidos y panel ampliado, chips removibles y limpieza total.
- Semántica tri-state: desconocido, falso y cero no son equivalentes.
- Los filtros de precio distinguen precio publicado de `Consultar`.

## Mapa V2

- Clusters accesibles con cantidad completa y activación por teclado.
- Markers compactos de precio para USD, ARS y `Consultar`.
- Selección visible por forma, escala, borde y halo; el dorado no es la única señal.
- Card y marker comparten selección; hover/focus no navega.
- Mover o acercar el mapa muestra `Buscar en esta zona`; no dispara una búsqueda silenciosa.
- Fullscreen, reencuadre, zoom y consentimiento previo a geolocalización.
- El total diferencia propiedades encontradas de propiedades representables en mapa.

### Confianza geográfica

La metadata pública usa `high`, `approximate`, `doubtful` y `none`. En español:

- `high`: Ubicación.
- `approximate`: Ubicación aproximada.
- `doubtful`: Ubicación dudosa.
- `none`: Sin ubicación en mapa.

Una coordenada existente no se presenta automáticamente como exacta. La clasificación deriva señales conservadoras de dirección y reutilización del punto. ERETZ nunca muestra una propiedad sin coordenadas como marker inventado.

## Cards V2

Las cards priorizan precio/condición, operación, tipo, ubicación, atributos reales y publicador. Mantienen acciones de guardar, comparar, compartir, ocultar y reportar. Nunca rellenan imágenes, precios, características o datos profesionales inexistentes. Los estados `Consultar`, sin foto y sin ubicación tienen tratamiento explícito.

## Ficha V2

La ficha incluye, cuando existe dato real:

- regreso contextual al Explorer;
- galería, miniaturas, contador, teclado y Escape;
- precio, expensas y características;
- descripción, ubicación y confidence;
- publicador y contactos directos;
- guardar, comparar y compartir;
- transparencia, fuente original, reporte y corrección;
- historial y publicaciones relacionadas sólo cuando existen.

Las etiquetas de hechos usan contraste AA. `null`, `false` y `0` conservan significados separados.

## Mi ERETZ

Mi ERETZ funciona sin login y agrupa cinco secciones con tabs accesibles, flechas, Home y End. La persistencia es local al dispositivo. No existe todavía una cuenta, sincronización, backup remoto ni migración de conflictos.

## Profesionales

Los directorios usan 7.004 inmobiliarias reales y nombres de agentes derivados de publicaciones. No se inventan logos, fotos, matrículas, sucursales, redes ni relaciones. Los perfiles actuales son informativos; no existe tenancy, membresía, ownership o administración profesional.

## Estados y accesibilidad

- Loading, skeleton, vacío, error recuperable, 404, sin foto, sin precio y sin ubicación.
- Foco visible, landmarks, nombres accesibles, `aria-pressed`, tabs y diálogos.
- QA autenticada: cuatro viewports desktop sin overflow y cero requests browser-side a Supabase.
- Axe remoto: Explorer, Mi ERETZ, inmobiliarias y agentes sin serious/critical. La ficha detectó dos nodos de 4,48:1 y se corrigieron a `--ink-3` en `a31612c152`.

## Performance

El frontend limita pools, usa cache por instancia durante cinco minutos, cursor keyset, clustering server-side, imágenes recortadas en listados y evita prefetch especulativo de fichas. La principal deuda no es de render: conteos y búsqueda todavía escanean grandes porciones de PostgreSQL y filtran el Quality Gate en Node. Ver `docs/ERETZ_SECURITY_AND_DATA_AUDIT_2026-08-27.md`.

## Observabilidad actual

Existe recuperación UI, logs server-side sanitizados y un bus local `eretz:analytics`. No hay todavía un colector persistente de errores, trazas, métricas, alertas ni SLO. Los eventos del navegador se descartan si ningún consumidor está conectado.

## Contratos importantes

- Quality Gate es autoridad de visibilidad y falla cerrado.
- PostgreSQL y Blob son server-only; ningún secreto lleva prefijo `NEXT_PUBLIC_`.
- Data API no forma parte del frontend y debe permanecer apagada.
- La búsqueda pública no requiere login.
- Ningún pago puede modificar el ranking orgánico.
- Una propiedad física, una publicación y un publicador son entidades conceptualmente distintas.
- Las señales de reporte/reclamo no ocultan ni aprueban automáticamente.

## Funciones diferidas

No están implementadas como producto completo: cuentas, sincronización, miniportales, roles profesionales, publicación manual/importada, geocoding masivo, ERETZ Mercado, calculadoras con fuentes externas, recomendaciones persistidas, IA externa, billing, publicidad y mobile V2.
