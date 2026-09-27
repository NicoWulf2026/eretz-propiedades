# ERETZ — handoff

Para retomar desde una sesión nueva: arrancar Claude Code en `D:\INMO CAPITAL\eretz-unified`.
Reglas: `CLAUDE.md` + `.claude/rules/` (cargan solas). Estado: `docs/agent/CURRENT_STATE.md`.
Historia: Git (`git log --since=2026-09-25`).

## Recién cerrado (25-09)
- Snapshot: frescura desde NEEDS_FIX por campos, títulos/eslóganes del sitio; v4d verificada.
- Portales/directorios como web oficial READY (8 dominios) — `62dbc899c4`, `eeabc94083`.
- `generico`: fotos del visor, `/cdn-cgi/` (`6ee927bb80`); ambientes del título (`0ee0882403`,
  117 fichas); `addressNeighborhood` como barrio (`2961c3ec68`).
- `wasi`: «Habitaciones:» = dormitorios y el parser `scripts/wasi_fingerprint.py` entra en la
  huella (`942e0825e2`). Test general: todo módulo propio que importa un conector está en su huella.
- Geografía compartida: la «ciudad» publicada que es el departamento de la localidad publicada como
  barrio (`fenix` Capital→Posadas, 512 fichas; 7 más, todas correctas) — `2961c3ec68`.
- Gate 14:3x y 16:3x: 217 agencias; 5 pérdidas revisadas y firmadas (alpha ×2 y altos
  CORRECCION; varesse y domus arreglados).
- Tarde: ruteo TFW por la portada (`f44e3f691d`, compartido); rangos de emprendimientos en
  `wordpress` (`232a1b606d`); descripción Wasi como JSON, sin mojibake (`67f6c8ba44`, 208
  fichas); `generico`: contador de visitas (`54db367d5a`), título Xintel (`9db61ad774`),
  similares RealHomes (`1dc3ba7998`), tipo `berrueta` (`7404dfe9b0`), operación como etiqueta
  suelta (`b24c8c42cd`); snapshot: mojibake por tramos (`953f3ed137`).
- Noche (17:xx): «Consultar» de Wasi no es precio (`e6947fc6dd`); delegar inventario = portal
  inmobiliario, no red social (`316068e149`: 15 BLOCKED_EXTERNAL pasan a NEEDS_FIX honesto);
  cochera con dormitorios decidida por el título en coherencia (`4fc408a05b`, 157 fichas) y en la
  snapshot (`17bf526a1b`); `generico`: pares rótulo/valor (`484a5da006`, bardi), acordeón de
  descripción (`70f9be373c`, alianza), ficha con id no es categoría (`71d43466dd`, fogliese),
  taxonomías WP (`904ab50852`), `property-description` de fios (`a282e80af0`); tipos «semipiso» y
  «tríplex» + «5 amb» sin punto (`8b44bc4a61`). Guarda: ningún .py con caracteres de control.
  Gate 17:3x: 222 agencias; 5 pérdidas de cocciolo firmadas (correcciones).
- Diferidas firmadas 16:0x/17:08: `garcia andreu` (rangos de emprendimiento), `domus propiedades` (bloqueo
  puntual), `fj lujan` (TFW mal ruteado), `garbero` (1 ficha + taxonomía como ficha).
- Optimización de Claude Code: `docs/agent/CLAUDE_CODE_OPTIMIZATION.md`.
- Noche (21-22h): TLS con raíces de certifi (`andrade`), paginación Tokko ≠ globo del mapa
  (`global` 20→114), emprendimientos en plural (`alagna`), descartes de validación en el auditor
  (pie legal, moneda del precio de relleno) — `49fa3cadbf`; fichas por `onclick` (`aris`) e
  iframe Amaira de Xintel (`battista`, 480) — `2a6560bd9b`; `og:type=article` solo no veta y
  schema+precio con una foto (`gandino` 0→10, `benitez` 1→8), «+4 amb» es cota, 3 directorios
  (cia.org.ar, empresasdecordoba, propuestasinmobiliarias) — `76f1b30211`; «Propiedad
  inexistente.» = baja (`d uva`) — `036ba1d549`. Gate 22:1x: 258 agencias, 8 firmadas, 0 pendientes.
- 23h: paginación que ignora el parámetro ya no tapa la real + `/propiedades/pagina-N/` + filtros
  de catálogo no son fichas (`cuini` 16→37) — `43a0ddd1cd`; operación desde catálogos gemelos
  venta/alquiler (`bottai` 226→317 enumeradas, 314 con operación) — `091b71fa67`.
- 23:5x: WordPress sin REST se normaliza con `generico` (las 6 agencias de ese camino estaban en
  NEEDS_FIX, 394 fichas), «$X / DOLARES» = USD, similares/destacadas de inspiry fuera del
  cuerpo, tipo rotulado antes que el menú — `9947dccc14`. Mirar en el próximo gate: cip,
  christian arce, ente, gonzalez theyler, constant, berardi (cambian muchos campos, a favor).
- Medianoche: título h2-h4 sin og/h1 y «Cocheras: 1» no es tipo (`candoli`) — `b812dfc03b`;
  Terravirtual `/ficha/<md5>` (`blangiforti`, `g calvo`: dejan de guardar tarjetas del listado)
  — `d3f1a7960b`. Gate 23:4x: 266 agencias, 14 firmadas (13 blangiforti + calzetta), 0 pendientes.
- Paro 26-09 00:11 FAMILIA generico (`fandino`: 10 órdenes del listado `venta_mas-nuevas`… como
  fichas) → `c7f463090c` + diferida firmada 00:25 (la familia volvió a la cola).
- Paro 00:28 FAMILIA wordpress (`ingar`, tema ERE: ubicación rotulada con enlace, descripción con
  su propio h2) → `7d94edd1a5` + diferida firmada 00:36.
- Paro 01:43 FAMILIA generico (`ballarre`: la convención `/?page=N` muestreaba destacadas al azar
  de la portada) → paginación DECLARADA por el listado antes que las convenciones `018f2a565e` +
  diferida firmada 02:08. Mirar en el gate: agencias LISTADO_HTML cuyo listado enlaza `?start=`,
  `?page=`, `?pagina=` (ahora se recorren esas páginas en vez de las convenciones).
- 02:4x: «Sup. Lote» = superficie total (`conti`, 74 fichas que guardaban el lote de una vecina) y
  `/buscar/` no es ficha — `2385c5c0d7`. Gate 02:5x: 293 agencias, 86 firmadas, 0 pendientes.
- 03:2x `cuini`: catálogo por operación no es ficha — `a161c7b3f2`.
- Paro 03:56 COMPARTIDO (`ramirez`, nueva): `<base href>` en el catálogo por categorías y
  `/propiedad/<id>-slug.html` es ficha — `b95ce8b7a8` + diferida firmada 04:04. Mirar en el gate:
  RE_FICHA ahora acepta `.html`/`.php` al final (más urls entran como ficha sin guardián).
- Paro 05:1x FAMILIA generico (`zamorano`, plataforma ASP de Miramar como ballarre): todos los
  catálogos con paginación declarada y solo su grilla (sin «Destacadas»/«Últimos Ingresos» al azar)
  — `af75580ceb` + diferida firmada 05:49. Dos corridas idénticas: zamorano 125, ballarre 193.
- Paro 06:2x COMPARTIDO (`berrino`, wordpress REST): miniaturas -WxH al azar del respaldo HTML
  — `ecf733964d` + diferida firmada 06:49. Gate 06:2x: 320 agencias, 0 pendientes.
- Gate 07:5x (594 pérdidas en `alas`): WordPress REST solo leía claves Houzez; RealHomes se traduce
  y el REST sin meta de propiedad (`echesortu`, `fiorio`, `esnal`, `daniel`, `berrino`…: dirección,
  ciudad, baños y superficie en 0 % y CERTIFIED_COMPLETE) se lee del HTML — `5b6a432310`. Gate
  08:1x: 335 agencias, 0 pendientes. `coldwell banker de la vera cruz` (262 COMPLETE con 0 % de
  precio): verificado, el sitio no publica precios en ninguna ficha — no es defecto.
- Paro 08:3x COMPARTIDO (`martinez quiles`: galpón con 2 fotos) → `6d399aa72a` + diferida firmada.
- Paro 09:0x COMPARTIDO (`lizio albarello`: `/resultado/…` como fichas) → se recorren como catálogos; 24 fichas reales + diferida firmada.
- Paro 09:3x FAMILIA wordpress (`landart`): 429 del hosting wnpservers (igual que harfouche) — causa
  externa, diferida firmada sin cambio de código. Mejora posible: que un 429 en el descubrimiento
  deje la corrida como bloqueada y no como «inventario colapsado».
- 2026-09-27 09:xx: la cola estaba parada desde el 26 12:4x con TRES familias detenidas (generico por
  `ramirez`, wordpress por `piccardo`, tokko por `salerno`) — 762 de 774 excluidas.
  - `salerno` (tokko): CAMBIO_EN_LA_FUENTE. /Propiedades declara hoy 54 (Venta 40, Alquiler 15) y se
    enumeraron 54; el techo 109 es de preingestion vieja. 1 detalle/Bloqueado. Diferida firmada.
  - `piccardo` (grvende.com.ar, REST sin meta → generico): «Propiedades relacionadas» es un `<h6>` sin
    clase propia y sus tarjetas («Ambientes 3 / Baños 1» de OTRA ficha) entraban a la ficha; además
    «<p>Tipo</p> <span>Departamento</span>» no se leía. `cuerpo_principal` corta en ese encabezado y el
    tipo acepta el rótulo «Tipo» solo. En vivo: 19 fichas sin tipo → 0; ambientes/baños ajenos fuera.
  - `ramirez` (generico): 10 fichas reales descartadas por forma — `/propiedad/263-chubut.html`,
    `/propiedad/273-l-molinas-2192-.html` (id adelante, slug corto o terminado en guion) no calzaban
    en RE_FICHA → alternativa `/propiedad/<id>-<slug>.(html|php)`. Y `/tipos/cabanas.html`,
    `/tipos/islas.html` no se reconocían como categoría (entraban como fichas) → rubros por archivo
    entero. Verificado en scratch: forma 12 → 0, 153 → 162 fichas, idempotente. RESIDUAL conocido: 8 fichas casi vacías (título + nota «Lote 27 X 71» + 1-4 fotos, sin
    precio) caen en `ficha_sin_contenido` porque el título incluye «RAMIREZ inmobiliaria» (regla
    `agencia <= titulo`). Relajar ese guardián compartido requiere medir cascarones (alder, arrambide);
    queda en backlog, no se tocó.
- 2026-09-27 10:xx, NEEDS_FIX no idempotentes (backlog 2), revisados sin frenar la cola:
  - `fiorio` (wordpress): una ficha cuyo HTML falló por red caía en silencio al objeto REST pobre
    (sin descripción ni atributos) en vez de volver None para que el runner la difiera → arreglado
    en wordpress.py. Y las 106 fichas llevaban 6 íconos del tema (`bano.avif`, `ambientes.avif`…)
    como fotos: `is_attribute_icon` (nombre = atributo) cuenta como asset SOLO junto con la
    repetición en la mitad del catálogo (`descartar_imagenes_compartidas`); no se usa suelto porque
    una foto real puede llamarse `bano.jpg` y la snapshot filtra con `is_known_page_asset` sin
    repetición.
  - `cocucci`: la fuente cambió expensas ($63.733 → $64.000) entre corridas — CAMBIO_EN_LA_FUENTE.
  - `di maria`: 350 enumeradas en ambas; en cada corrida falló UNA ficha distinta (transitorio).
  - `brikel`: ya CERTIFIED_COMPLETE (26-09 07:08).
  - `blangiforti` (Terravirtual): con el código de hoy el contenido ya era idéntico entre corridas,
    pero el inventario no (164 vs 151). El padrón trae `blangiforti.com.ar` sin www y el sitio enlaza
    `https://www.…/ventas` (174 en una página): `_catalogos_enlazados` no lo aceptaba y se caía a
    `/propiedades`, paginado en orden aleatorio. Ahora acepta la variante www del mismo host; los
    catálogos gemelos venta/alquiler se reconocen en plural (`/ventas` + `/alquileres`: +2 alquileres);
    y la descripción se lee bajo «Información de la Propiedad» (antes caía al eslogan del meta y se
    descartaba por compartida en 164/164). En vivo: 176 fichas, dos enumeraciones idénticas.
    Recertificada en scratch: 176/176, idempotente, descripción 100 %. Quedaba `ambientes` por la
    sección «<strong>Propiedades</strong> que te pueden Interesar» (otras fichas con «3 Amb.») que el
    auditor leía; la ficha publica «Ambientes: 0». `cuerpo_principal` corta ahí (0 cambios de
    extracción en 40 fichas).
- Gate 11:2x: 370 agencias, 15 pendientes → firmadas: `baron` 6 ambientes de emprendimientos
  (CORRECCION: no se afirma una cantidad para unidades heterogéneas), `brunetti` 3 tipos «cochera»
  que eran Cabaña/Edificio (CORRECCION; «cabaña» no está en el vocabulario canónico), `d amato`
  8493262 (CAMBIO_EN_LA_FUENTE: la ficha hoy sirve la plantilla vacía). Y ese cascarón se guardaba
  porque el eslogan del meta contaba como «descripción» → generico lo quita si sin él la ficha es
  cascarón según `ficha_sin_contenido` (título = agencia). d amato puede quedar NEEDS_FIX por esa
  ficha enlazada y vacía: es de la fuente, firmar si para la cola.
  - `constant` (wordpress, 25-09): con el código de hoy 24/24 con operación, tipo y coordenadas.
  - `brunetti` (NEEDS_FIX 11:0x por baños): la señal del auditor leía «Republica del Libano 28» como
    «bano 28» (sin límite de palabra en la segunda forma) — corregido también en dormitorios.

## Corriendo
- Cola con 2 workers + relanzador + vigilante. Mirarla solo si hay paradas.
- **2026-09-27 10:3x: las tareas programadas `ERETZ_relanzador` y del vigilante NO EXISTEN en
  Windows** (`schtasks /query /tn ERETZ_relanzador` → no encontrada; último registro del
  relanzador 26-09 21:04). No se recrearon (configuración persistente; no se sabe si se borraron a
  propósito — decisión del usuario; hay XML de respaldo en el scratchpad de la sesión). Mientras
  tanto la sesión corre `relanzar_la_cola.py --lanzar` cada 10 min. Sin sesión, nadie relanza.

## No rehacer
- **`gaggiotti`**: SPA; el catálogo solo sale de `https://www.gaggiotti.com.ar/api/Property/Search`
  y su robots.txt prohíbe `/api/`; el sitemap no lista fichas. **No se usa la API**: queda como
  bloqueo de la fuente (misma regla que argencasas).
- **Argencasas** (`coviella`, `eduardo fernandez`, `de ruyck`): responde 404 vacío a nuestro UA
  declarado en TODO el sitio y su robots.txt prohíbe `/motor/`. **No se evade** (ni UA de
  navegador ni /motor/). Acción externa: pedir habilitación a argencasas o dejarlas BLOCKED_EXTERNAL.
- Guardia de título repetido en el runner: descartada con medición.
- `armanino`: API de Tokko con clave embebida en su bundle → **no se usan claves ajenas**.
- `estela d onofrio`: el certificador tiene respaldo a `generico`; el diagnóstico liviano no.
- `building`: las 220 «fichas» imagen del 21-09 ya no se enumeran con el código de hoy (81 URLs, 3/3 ok).
- `corporacion`, `cannone`: ya resueltos por el código de hoy; se recertifican solos.
- 5h (mínimo de 40 caracteres en el runner): radio 0 en los paquetes vigentes.

## Próxima prioridad (por impacto medido)
1. **Auditor**: señal de operación más amplia que el extractor (5c) — deuda de diseño, medir
   sobre páginas reales antes. Ruteo TFW, rangos, «Consultar» y portales: RESUELTOS.
2. **NEEDS_FIX no idempotentes** (21): contador de visitas, título Xintel y similares RealHomes
   RESUELTOS; `dorsoli` ya estable con el código de hoy. Quedan por mirar: `blangiforti` (precio e
   imágenes entre corridas), `brikel`/`di maria`/`cocucci` (tokko, inventario o descripción).
3. **Lote `generico` de radio chico** (agrupar): `cometto` (categorías `propiedades_ver2.php`);
   `del parque` (`og:type=article`; solo 1 ficha pasaría: no se afloja la guarda);
   `bunader` (enumera listados); `fios`
   (`.show-more`, foto ajena); precio accesorio `caruso`; tipo de respaldo leído del menú
   (parcela → casa en `fernando villalba`); operación
   solo en la ruta del catálogo: `bottai` RESUELTO; `constant` 24 (wordpress) pendiente.
   Diagnosticados 25-09 noche, sin arreglar: `harfouche` (WP sin CPT en REST, sitemaps con 429: dejar a la cola);
`i alfredo gonzalez theyler`: tipo, precio y relacionadas RESUELTOS; queda el título con
   sufijo del sitio.
   `habita`: sitio institucional sin catálogo (no es defecto).
4. Regression Gate tras cada tanda (comando en `.claude/rules/scraper.md`).
5. Beta del backend (`docs/ERETZ_UNIFICATION_PLAN.md` § «Backend beta confiable»).

## Lote pendiente para agrupar (diagnosticado 27-09 11:4x, sin tocar: cada commit frena la cola)
NEEDS_FIX «no terminó con estado OK» (37): mayoría SIN_INVENTARIO / ERROR_DISCOVERY. Muestra de 9:
- **Identidad equivocada con READY** (tocar `agency_web_discovery.py` = `shared/source_policy`,
  invalida TODAS las certificaciones → hacerlo en un lote propio y planificado):
  `o keefe` → `parquesindustriales.com.ar/detalle-inmobiliaria/7` (directorio);
  `integral s a` → `sibom.slyt.gba.gob.ar/...` (boletín oficial municipal).
  `schulz` → `ar.tellows.net/num/…` (consulta de teléfonos; paró la familia generico 11:43,
  diferida firmada: el guardián de forma rechazó bien un tile de mapa). Regla general
  propuesta: `*.gob.ar`/`*.gov.ar` nunca es la web de una inmobiliaria; y el directorio al listado.
- `marcelo zanni` (wordpress, Divi): CPT `propiedad` vacío; las propiedades son **posts** con
  categorías estándar `venta`(13)/`alquiler`(1) + tipo (casas, departamentos…), sin taxonomía
  `operacion` → `_catalogo_posts_inmobiliarios` exige `operacion`. Extender a categorías
  top-level `venta`/`alquiler` con conteo y posts que las lleven (14 fichas).
- `grupo azor`: plataforma GVAmax (`inmuebles.php?operacion=1|2`, catálogo por `js/api.funciones.js`
  sin HTML de fichas) — investigar el endpoint del propio host antes de tocar.
- `gestionato`, `hcg brokers`: SPA React (HTML de 0,5 KB) — sin JS no hay catálogo; buscar API propia.
- `gustavo santos`, `battini`: 404 en la raíz (fuente caída). `bergo`: respuesta vacía.

## Decisiones de producto abiertas (no técnicas)
- **robots.txt**: el pipeline no lo consulta. Medido 26-09 00:1x: 283 agencias certificadas o en
  NEEDS_FIX, 31.354 URLs de ficha, **0 prohibidas** para nuestro UA. Los dos casos que sí prohíben
  (argencasas `/motor/`, gaggiotti `/api/`) se dejaron sin leer a mano. Falta decidir si se agrega
  una guarda general en el descargador (toca la huella y también los endpoints de listado/API:
  medir antes esos, no solo las fichas).
- Con título vacío (título = agencia descartado en la snapshot) el frontend muestra «Propiedad sin
  título» (`frontend/src/lib/api-v2/property-boundary.ts`). Alternativa: componer «{tipo} en
  {operación} · {localidad}» con campos reales. Decide el producto; mobile sigue congelado.

## Trampas actuales
- Cada commit de huella detiene los workers entre agencias hasta ~10 min: agrupar cambios.
- Un cambio de huella sin commitear lo levantan los workers al relanzarse: commitear enseguida.
- Un archivo que la guarda de workers VIEJOS no vigila (p. ej. uno recién agregado a la huella)
  no los detiene: pedir relanzamiento con bandera `OPERACION` (formato en `relanzar_la_cola.py`).
- Los paquetes NEEDS_FIX con motivos solo de campo alimentan la snapshot.
- Un paro FAMILIA **no** se libera solo por commitear el arreglo en `generico.py`: la
  `strategy_fingerprint` del paro no cambia con ese archivo. Firmar la diferida
  (`firma_del_patron` de `AGENCY_DEFECT_QUEUE.jsonl`, con el commit) y correr `relanzar_la_cola.py`.
