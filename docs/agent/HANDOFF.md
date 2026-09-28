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
- Plataforma **SOM** (`amud`, 27-09): catálogo solo por API externa `apmovil.som.com.ar` con token
  embebido en `js/script.js` → misma regla, no se usa. Diferida firmada.
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
3. **Lote `generico` de radio chico** (agrupar; ver § «28-09 mediodía» para lo hecho y lo diagnosticado): `cometto` (categorías `propiedades_ver2.php`);
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

- 12:1x `cip` (wordpress por sitemap → generico): provincia 0 % en 163 fichas con «<li>Provincia:
  San Luis</li>» (rótulo y valor en el mismo elemento) → `_rotulo_en_linea` como respaldo de
  ciudad/provincia (la geografía compartida valida). En vivo: ciudad y provincia salen.

- 12:4x paro FAMILIA generico `lazzaro` (Inmobiliatica, primera certificación): «dormitorios» salía
  del buscador (<select id="dormitorios"><option>1</option>…) → `sin_filtros_catalogo` quita los
  <select>. RESIDUAL: ciudad 0 % — el JSON-LD pone `addressLocality: "Centro"` (zona) y «Mar del
  Plata» solo figura en título/meta; leerla de ahí es heurística nueva → backlog. Diferida firmada.

- 13:1x paro COMPARTIDO `innoa` (ASP, Cafayate): 22 fichas reales sin precio descartadas por forma
  (`/venta/item.asp?t=…&id=192`) → `RE_FICHA_CON_ID`; y un banner GIF rotativo (`/ac/b/*.gif`) como
  foto la hacía no idempotente → GIF junto a JPG/PNG/WEBP se descarta (medido: solo innoa guardaba
  GIFs). En vivo 35/35 fichas, 0 GIFs. Diferida firmada.

- `di maria` (tokko, cert 12:33): 353 enumeradas en ambas corridas pero 6 fichas intercambiadas
  (ids 7313114–7313268: empates en el orden `?o=2,2&p=`). NO reproducible 14:0x: dos enumeraciones
  seguidas idénticas. El paro FAMILIA quedó diferido por el diagnóstico anterior. Si vuelve: pedir el
  listado con un orden sin empates antes de tocar la paginación.

- 14:58 paro FAMILIA generico `bardi` (Mapaprop): declara 105 y enumerábamos 90 (igual desde
  el 24-09). Las páginas repiten fichas de la anterior (16 por página, ~10 nuevas) y el tope
  ⌈105/16⌉+2 = 9 cortaba antes; llegan en la página 10. Ahora se pagina mientras haya novedades
  (corte: total alcanzado o 2 páginas sin nuevas). En vivo 105/105. Diferida firmada.

- 15:14 paro FAMILIA generico `ivone parodi` (Tokko `/p/<id>` leído por generico): 57 vs 58 con
  fichas distintas, todas de la página 9000 (catálogos gemelos venta/alquiler). Sitio caído al
  investigar (301 a www, www rechaza conexión). Diferida firmada. SOSPECHA a verificar:
  `_catalogos_por_operacion` lee solo la primera página de cada gemelo y Tokko reordena entre
  pedidos → un gemelo Tokko debería paginarse completo o no usarse para agregar fichas.

- 15:46 paro FAMILIA wordpress `jm norte`: publica exactamente 50 (= POR_PAGINA); la página 2 da
  HTTP 400 (`rest_post_invalid_page_number`), que el descargador trae como `ErrorTransitorio("http
  400")` y `_rest` marcaba paginación interrumpida (el `except` que lo trataba como final esperaba
  ErrorPermanente). Ahora un 400 después de la 1a página es el final. Afecta a todo catálogo REST
  múltiplo exacto de 50. En vivo 50, sin interrupción. Diferida firmada.
- 15:3x paro FAMILIA wordpress `jakim`: sin pérdida (techo 32 de una enumeración vieja con 16
  válidas; hoy 20 reales). Diferida firmada.

- 15:53 paro COMPARTIDO `jorge martinez`: el propio listado (/propiedades.php, ?operacion=venta,
  ?operacion=alquiler) y el índice /emprendimientos.php entraban como candidatas por forma → 4
  detalles fallidos. Candidata por forma con la ruta del listado se descarta; el índice de
  emprendimientos va a RE_NO_FICHA. En vivo 28 fichas reales. Diferida firmada.

- 16:03 paro FAMILIA generico `julia propiedades`: Tokko TFW (tuinmobiliaria) con **0 Resultados**
  en todo el sitio; generico enumeró 2 categorías y el guardián las rechazó. Diferida firmada.
  Mejora: Tokko TFW con total declarado 0 → NO_INVENTORY_CONFIRMED en vez de caer a generico.

- 16:14 paro FAMILIA generico `julian zaparart` (Kiteprop por sitemap): declara 35 y enumeramos 35
  (techo 45 de preingestión vieja: CAMBIO_EN_LA_FUENTE). La no-idempotencia era una URL con token
  cifrado por pedido (`kiteprop.com/maps/view/eyJ…`) dentro de la descripción → `RE_URL_CON_TOKEN`
  la quita (con su `<img>`). Diferida firmada.
- 16:0x paros FAMILIA `julia propiedades` (Tokko 0 resultados) y `dorsoli` (1/5 sin tipo: la fuente
  rotula un edificio de 8 unidades como «Lote, Terrenos»): diferidas firmadas, sin código.

- 16:42 paro FAMILIA generico `lar propiedades` (SIN_INVENTARIO): sus fichas son
  `/ficha?url=<ficha.amaira.com.ar/nue/ficha.php?ficha=RAL102>` (Amaira pasada por parámetro,
  cargada por JS). Se reconocen como fichas, el id es el código Amaira y se lee la ficha del
  proveedor como en el iframe (`battista`). En vivo: 0 → 111 fichas con precio, tipo y fotos.

- 17:30 paro FAMILIA wordpress `daniel` (REST sin meta → generico; tema estate): ficha técnica
  `<span label><icono/><strong>Ambientes</strong></span><span value>5</span>` — el cierre intermedio
  impedía leer ambientes y dirección → los lectores de pares toleran UN cierre span/div. Y la
  dirección «…, Oberá, Misiones» da ciudad/provincia si el último tramo es provincia (lista fija
  `PROVINCIAS_AR`; la geografía compartida valida). En vivo: ambientes 10/10, ciudad 11/12.
  0 cambios en la muestra de blangiforti. Diferida firmada.

- 19:05 paro FAMILIA generico `linkasa` (Kiteprop, *.kitepropcrm.com): el catálogo es
  /site/properties (paginado ?page=N) y no se reconocía («properties» no estaba en los catálogos
  enlazados) → solo 4 destacadas + /site/properties/sale y /rental guardados COMO PROPIEDADES.
  Ahora `properties` es catálogo, sale/rental van a RE_NO_FICHA y «Categoría | PH» da el tipo.
  En vivo: 4 → 18 fichas reales, estables. Diferida firmada. Afecta a toda la plataforma Kiteprop.

- 19:59 paro FAMILIA generico `livia renovell` (GVAmax): catálogo por POST a
  `Php/api.inmuebles.php` del MISMO sitio (filtros vacíos = todo) → `_catalogo_gvamax`, variante
  GVAMAX_API. En vivo: livia 0 → 48, `grupo azor` (backlog) 0 → 35, con tipo/precio/operación.
  Diferida firmada. `liotto` 19:21: identidad (revista barrial), firmada.

- 20:39 paro FAMILIA generico `lo ponte`: «<h2><i class="fas …"></i> Descripción</h2>» — el ícono
  vacío impedía leer la descripción rotulada (el meta supera el tope de 600). En vivo 20/20 con
  descripción (antes 24 %). Diferida firmada. `gianini` (worker 1 desde 18:05): no trabado,
  cientos de fichas por ?p=N con ~3 s por pedido.

- 21:06 paro FAMILIA generico `gianini` (inventario_inestable): FALSO. Ambas corridas enumeraron
  las mismas 1033 fichas y ambas agotaron el presupuesto (5400 s; 822 vs 546 detalles leídos, sitio
  a ~3-6 s/pedido). Diferida firmada. Mejoras: (1) el triaje no debería leer PRESUPUESTO_AGOTADO en
  ambas corridas como inestabilidad; (2) catálogos de ~1000 fichas necesitan presupuesto mayor o
  certificación por muestra — decisión operativa.
- 00:17 paro FAMILIA tokko `lopez baena` (1377 declaradas): igual que gianini — ambas corridas
  enumeraron 1373; run1 leyó 1372 en 51 min, run2 recibió un Bloqueado, cedió ritmo y agotó el
  presupuesto en 878. Diferida firmada. Ya son dos catálogos >1000 que el presupuesto no alcanza.
  28-09: mejora (1) HECHA — el triaje lee «misma enumeración + presupuesto agotado + lo que falta cabe en lo
  no pedido» como `sitio_lento` radio AGENCIA (gianini re-clasifica así). `lopez baena` seguiría parando,
  pero por otra causa real: `paginacion_interrumpida` en ambas corridas (tokko.py, error de red/bloqueo en
  un barrido; 1373/1377). Ese paro conservador se mantiene. (2) sigue siendo decisión operativa.

- 01:38 paro FAMILIA generico `los cerros` (Next.js, Bariloche; 663 imágenes compartidas): el sitio
  responde INTERMITENTEMENTE con 200 y `<h1>Propiedad no encontrada</h1>` (20 KB en vez de 200 KB) y
  se guardaba como propiedad sin datos con og-image + píxel de Facebook como fotos (descartadas →
  253/333 sin fotos, no idempotente). Ahora el h1 «no encontrada» es baja (detalle_permanente) y el
  runner la reintenta. Diferida firmada. Fuente inestable: puede quedar NEEDS_FIX por desaparecidas.

- 02:19 paro COMPARTIDO `arquitectura inmobiliaria` (urbanorosario.com.ar, tienda DonWeb SitioSimple):
  las 26 enumeradas eran CATEGORÍAS de raíz (/ventas-casas, /alquileres-departamentos-2-dormitorios)
  y 17 se guardaban COMO PROPIEDADES con el precio de su primer producto; ninguna ficha real. Ahora
  esas categorías en plural son no-ficha y se recorren como catálogos (junto a /resultado/…). En vivo:
  30 fichas reales, estables. Diferida firmada. OJO gate: esa agencia perdía 17 filas falsas.

- 04:35 paro COMPARTIDO `manuel ponce` (wordpress→generico): TypeError no controlado — el respaldo de
  descripción `property-description` hacía `limpiar(...)[:6000]` y `limpiar` devuelve None con la
  caja vacía. Guardado con `or ""`. El certificador se traga el traceback: para verlo, llamar
  `agency_certifier.run_once(...)` directo (scratch `run_once_ponce.py`). Diferida firmada.

- 05:20 paro FAMILIA generico `diego vacis`: fichas `/comprar_detalle_vacis/<id>/<slug>` no se
  reconocían (run1 SIN_INVENTARIO, run2 1 candidata rechazada) → `RE_FICHA_DETALLE`; `comprar|alquilar`
  cuentan como catálogo. En vivo: 13 fichas estables. Diferida firmada. `constant` ya CERTIFIED_COMPLETE.

- Gate 06:4x (448 agencias): 280 pérdidas, todas explicadas por arreglos de hoy — bottai 108 dormitorios
  eran opciones del <select> del buscador; berrueta/candel raul/franco (Template3) tenían precio, tipo
  «cochera», cantidades y fotos de tarjetas relacionadas; alexis meza una miniatura 150x150 común.
  278 CORRECCION + 2 lectura pendiente. Resultado: 0 pendientes.

- 07:27 paro FAMILIA wordpress `echesortu` (ciudad 0 → 89 % con los arreglos de ayer): señales falsas
  del auditor — `"addressLocality":""` vacío contaba como ciudad provista, y «BAÑO 3ER PISO» como
  «baño 3». La señal exige valor y número completo. Diferida firmada.

## Lote pendiente para agrupar (diagnosticado 27-09 11:4x, sin tocar: cada commit frena la cola)
NEEDS_FIX «no terminó con estado OK» (37): mayoría SIN_INVENTARIO / ERROR_DISCOVERY. Muestra de 9:
- **Identidad equivocada con READY**: HECHO 28-09 10:5x (la cola ya recertificaba todo desde 07:29).
  `es_portal` rechaza `*.gob.ar`/`*.gov.ar`, `tellows.net`, `parquesindustriales.com.ar`,
  `devotomagazine.com.ar` → esas 4 pasan a BLOCKED_EXTERNAL. Medido: no toca ninguna otra agencia.
  Historial:
  `o keefe` → `parquesindustriales.com.ar/detalle-inmobiliaria/7` (directorio);
  `integral s a` → `sibom.slyt.gba.gob.ar/...` (boletín oficial municipal).
  `liotto` → nota de `devotomagazine.com.ar` (revista barrial; paró generico 19:21, firmada).
  `schulz` → `ar.tellows.net/num/…` (consulta de teléfonos; paró la familia generico 11:43,
  diferida firmada: el guardián de forma rechazó bien un tile de mapa). Regla general
  propuesta: `*.gob.ar`/`*.gov.ar` nunca es la web de una inmobiliaria; y el directorio al listado.
- `marcelo zanni`: RESUELTO 28-09 09:3x. Variante `WORDPRESS_POST_CATEGORY`: la operación es una
  categoría estándar de primer nivel (Venta/Alquiler); se enumera por REST filtrando esas categorías y la
  ficha se lee con `generico` (el `content` REST es marcado Divi crudo). 14/14 con operación y tipo;
  blurb Divi `<h4><span>Baños</span></h4><div>3</div>` leído como par (antes «Ambientes 7 Baños 3» = 7 baños).
- `ente` (Gate 28-09 ~09:4x, 23 fichas sin dormitorios/baños): el tema ERE tabula solo lo cargado
  («Garages 2») y `_es_tabla_estructurada` corta la caída a la prosa, donde están «3 dormitorios …».
  Probado: leer la prosa cuando la tabla no tiene la celda del rótulo rompe
  `test_un_titulo_de_varias_unidades_no_dice_los_ambientes` (lee «Edificio en block de 3 ambientes» del
  título). Revertido. 2º intento (prosa del cuerpo sin encabezados): en vivo ente 136/136 iguales a la
  línea base + 2 nuevos, control 0 cambios, PERO rompe `test_la_prosa_no_prueba_un_atributo_que_la_ficha_tabula`:
  decisión documentada — en una ficha tabulada la prosa describe OTRA cosa (monoambiente de alagna: «1 y 2
  dormitorios» del edificio; terreno: la casa a demoler). Revertido. Es un conflicto de producto, no un
  bug: ¿la prosa vale cuando la tabla no tiene la fila? Decidir antes de tocar. Firmado DEFECTO_PENDIENTE.
- `U$` / `U$$` leídos como ARS: RESUELTO 28-09 10:4x sin tocar `base` — `_moneda_del_signo` en generico y
  `_moneda_con_posfijo` en wordpress (que tampoco leía `U$D`). En vivo: zanni, kerlin, cb andes, fdc → USD.
- `grupo azor`: RESUELTO 27-09 20:0x (GVAmax por POST, ver arriba).
- `gestionato`, `hcg brokers`: SPA React (HTML de 0,5 KB) — sin JS no hay catálogo; buscar API propia.
- `gustavo santos`, `battini`: 404 en la raíz (fuente caída). `bergo`: respuesta vacía.
- `loredo` (paró generico 00:50, diferida firmada): /propiedades 404 → se paginaba la PORTADA
  (destacadas al azar) → no idempotente. Catálogo real: /busqueda/todo/venta/ (138) y /alquiler/ (23),
  10 por página + «Cargar más» por POST (Pagina, Orden). La página carga reCAPTCHA Enterprise: verificar
  en /js/busqueda si el POST lo exige (si sí, NO se evade). Mejora general: no paginar la portada por
  convención cuando muestra destacadas al azar.
- `diego martin` (paró generico 22:15, diferida firmada): Next.js cliente + API **Strapi propia sin
  clave** `https://diegogmartin.onrender.com/api/propiedades?populate=*&pagination[page]=N` →
  `{data:[{id, attributes:{Titulo, Direccion, descripcion, Tipo_de_operacion, tipo_de_inmueble,
  valor_dolares, valor_pesos, Ambientes, Dormitorios, Banos, coordenadas(iframe)}}], meta}`.
  Candidata a estrategia «Strapi propio» con mapeo por agencia.
- `david rodriguez` (paró generico 17:50, diferida firmada): declara 161; catálogo solo vía POST
  `searchProperties.php` con `property_type` y `city` obligatorios (navegación `javascript:goTo…`).
  Camino nuevo: recorrer tipo × zona del propio formulario (ver `connectors/formularios.py`).
- `irujo` (paró generico 14:09, diferida firmada): catálogo hidratado por un proxy PROPIO de Tokko en
  el mismo host (`api_destacadas.php?page=&limit=&offset=` → `{meta, objects}`), como alta.com.ar.
  Su respuesta expone la clave de la API de Tokko en `meta.next`: **no usarla** (regla armanino);
  solo el proxy del sitio. Falta el endpoint del listado completo (no solo destacadas).
- `estudio uno` (paró tokko 10:04 del 28-09, diferida firmada, radio AGENCIA): 304 declaradas, 296/295
  enumeradas (Tokko reordena entre pedidos); 1 de borde. Mismo 296/304 que el 25-09 (BEST_AVAILABLE).
- `maure inmobiliaria` (paró generico 09:02 del 28-09, diferida firmada con radio AGENCIA): 6 de 21
  `/emprendimientos/` sin cuerpo legible; las otras 15, de la misma plantilla, se leyeron. El sitio
  respondía 503 (mantenimiento) durante todo el diagnóstico → no reproducible. Revisar esas 6 cuando vuelva.

## 28-09 mediodía (lote `generico` + auditor, `021907caea`; desarrollado en el worktree `D:\INMO CAPITAL\eretz-dev`)
Se desarrolla en un worktree aparte (rama local `dev/lote-2026-09-28`) para que editar archivos de la
huella no frene a los workers; el lote se aplica y se commitea de una vez en la rama de trabajo.
- `farias`: «U$D40.000» no era precio para la señal del auditor → la franja «Alquilado» exigía
  «alquiler» a una venta. La señal acepta `U$`, `U$$`, `U$S`, `U$D` (como el extractor).
- `matias sosa` (plantilla Coding & Company): cierra todo con espacio (`</h1 >`) → título del
  `<title>`, descripción del meta y fotos de «Otras propiedades» al azar (36/42 no idempotentes).
  `con_cierres_normales` + corte en `<hN>Otras propiedades</hN>`. «semicubiertos» ya no es cubierta.
- `guillermo rodriguez`: galería solo como `background-image` en `style` (240 fichas descartadas
  por forma) y título «Inmobiliaria | Guillermo Rodriguez» no reconocido como el del sitio → 9
  categorías `propiedades.php?tipo=N` guardadas COMO propiedades. Y cada ficha llega con dos URLs
  (`?id=N` y `?id=N&tipo=…&operacion=…`): `fetch_listing` descarta la larga solo si la corta también
  se enumeró (radio: 0 URLs guardadas en los paquetes tienen esos parámetros).
- Radio medido: A/B de `normalize` + señales sobre una ficha por agencia (189, HTML cacheado): solo
  cambian esas dos agencias; señal de precio/moneda nueva en 7 agencias, todas con el precio ya
  extraído (abril va por la API Xintel). `</tag >` en 3 de 234 sitios (feijo y agostinelli sin cambio).
- NO entró: subir `Descargador.limite_bytes` (800 KB). Wix pesa 0,9–1,9 MB → `lucas liprandi` (71
  fichas) y `dib kai` fallan con `OutboundResponseError`. Con 4 MB bajan, pero `generico` lee Wix mal
  («SUP. TERRENO 60 HABITACIONES 2» → 60 dormitorios, 60 baños): hacerlo junto con un lector Wix.
- Paro 11:23 FAMILIA tokko `mechi cogorno`: la ficha 8699134 del listado sirve la plantilla vacía
  (de la fuente). Diferida firmada 11:46 radio AGENCIA.
- Sin defecto nuestro: `maspero` (la fuente pasó de 67 a 68 entre corridas); `martinez negocios
  inmobiliarios` y `martinez propiedades` → mismo dominio `inmueblesmartinez.com.ar` con HTTP 500
  (Mod_Security). **Dos agencias con el mismo dominio: revisar identidad** (no se tocó).
- Próximos (diagnosticados, sin arreglar): `cometto` — fichas `inmueble_ver.php?recordID=N`, las
  categorías `propiedades_ver2.php?inmueble=N & tipoope=M` (con espacios) no se recorren como
  catálogo; `farina` (wordpress, 979) — `property_city` con dos términos (`centro`, `rosario`) se
  pega «Centro Rosario» (119 sin ciudad): elegir el término que resuelve como localidad; 133 tipos
  «taxonomía no mapeada»; 12 sin operación son emprendimientos (estado, no operación: no inventar).

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
