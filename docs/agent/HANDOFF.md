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

## Corriendo
- Cola con 2 workers + relanzador + vigilante. Mirarla solo si hay paradas.

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
