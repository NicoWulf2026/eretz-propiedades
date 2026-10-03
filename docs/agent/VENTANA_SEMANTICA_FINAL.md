# Ventana semantica final (pedido del usuario 03/10) — inventario, radio y plan

Regla: todos los cambios semanticos reales que quedan van en UNA ventana -> tests -> replays/canarios -> huellas finales ->
UNA recertificacion (dirigida) -> candidata final. NULL honesto no es bug.

Hecho clave para el radio: la snapshot toma paquetes por ESTADO (CERTIFIED_*), no por huella vigente
(`property_freshest.mas_frescas`). Invalidar una huella no vacia la candidata: el arreglo solo llega a las agencias que se
recertifican despues. El radio que importa para la beta es el de las agencias cuyo RESULTADO cambia, no el formal.

## Fase 1 — inventario (medido 03/10 10:00-11:00 sobre paquetes, servida v4l-c y candidata v4n)

| # | Bug | Clase | Fichas | Agencias | Donde vive | Entra |
|---|---|---|---|---|---|---|
| 1 | Ubicacion TIV: «Barrio, Capital Federal, Buenos Aires» -> deberia ser CABA (la servida tiene provincia «Buenos Aires», dato falso; v4n la quita) | DATA_CORRUPTION (servida) + REAL_DATA_LOSS | 1.043 | 9 | `generico._ubicacion_tiv` | SI |
| 2 | Ubicacion TIV: «..., Argentina» final no reconocido | REAL_DATA_LOSS | 402 | 17 | idem | SI |
| 3 | Ubicacion TIV: «barrio, localidad, partido» sin provincia (resolver la localidad con el catalogo, sin inventar provincia) | REAL_DATA_LOSS | 427 | 17 | idem | SI |
| 4 | Ubicacion TIV: zona «G.B.A. ...» sin mapa del sitio (G.B.A. es Buenos Aires por definicion) | REAL_DATA_LOSS | 101 | 12 | idem | SI |
| 5 | chacra/finca -> `terreno` borra dormitorios/banos/ambientes (mapeo de 566d5a2 + regla de `coherencia`) | REAL_REGRESSION | 24 evidenciadas en la servida (17 con dormitorios) + hasta ~130 no servidas | ~50 | `connectors/base.py` + `connectors/coherencia.py` (compartido) | SI |
| 6 | Provincia solo inferida del padron + coordenada dentro de CABA -> GEO_CONFLICT oculta provincia y coordenada (d amato) | REAL_REGRESSION | 12 (v4n) | ~6 | snapshot (`api_snapshot`, fuera de la huella) | SI, radio 0 |
| 7 | GEO_CONFLICT con coordenada DENTRO de la provincia declarada: se ocultan coordenadas validas (cip Merlo y otros) | REAL_DATA_LOSS | 102 (paquetes) | 13 | snapshot | SI, radio 0 |
| 8 | Fila de marketplace servida (danisa robledo, mercado-unico.com): `web_kind` mal clasificado | DATA policy | 1 | 1 | directorio de plataformas + snapshot | SI, radio 0 |
| 9 | Interfaz: elegir Provincia y enseguida otra sugerencia con teclado pierde la seleccion (re-render al volver la consulta del mapa) | REAL (UX) | — | — | frontend | SI, radio 0 |
| 10 | Huella: las constantes de modulo de `generico.py` (regex, mapas) no entran en ninguna huella | Riesgo de certificacion falsamente vigente | — | — | `agency_fingerprints` | SI (se paga con 1-4) |
| 11 | wordpress: tipo en campo REST de texto `property-type` (dolgiej) | REAL_DATA_LOSS | 22 | 1 | `connectors/wordpress.py` | SI si se toca wordpress igual (5 lo invalida) |
| 12 | imperia: rotulo compuesto anula dormitorios | REAL_DATA_LOSS | 15 | 1 | generico comun | evaluar |
| — | ramirez/paladino (ficha sin contenido): la plantilla no expone h1/medidas; la regla es correcta | COVERAGE_ONLY | 137 | 9 | plantilla | NO (post-beta) |
| — | Plantillas no soportadas (deka JS, coella, davio, crear Tokko-frontend, cid) | COVERAGE_ONLY | — | 5 | — | NO |
| — | Sitios lentos/limitados (bts presupuesto, emily 429) | COVERAGE_ONLY | — | 2 | — | NO |
| — | «Banco Provincia» senal falsa del auditor (campal) | POST_BETA_IMPROVEMENT | 0 datos | — | certificador | NO |
| — | Identidad: 36 agencias con web en portales/medios (ninguna COMPLETE) | POST_BETA_IMPROVEMENT | — | 36 | identidad | NO |
| — | Firma de defecto demasiado gruesa (dolgiej vs dorsoli) | herramienta | — | — | `defect_triage` | NO (operativo) |
| — | Precio, banos, descripcion que la fuente no publica (concepto, grimaux, fernanda...) | SOURCE_DOES_NOT_PUBLISH | — | — | — | NO es bug |

## Fase 2 — radio

- Formal hoy (5 toca `coherencia`/`base`, compartidos): TODAS las agencias con conector (~823: generico 404, tokko 313, wordpress 93, wasi 13).
- Reduccion arquitectonica TIV: `normalize` llama `_ubicacion_tiv` solo si el crudo trae `tiv_zonas` (lo pone UNICAMENTE `fetch_listing` de TIV) y el metodo pasa a `GENERIC_STRATEGY_METHODS["generic/tiv_busqueda"]`. Desde ahi un cambio de ubicacion TIV invalida 22 agencias, no 404.
- Radio optimizado (agencias cuyo resultado cambia): TIV 22 + chacra/finca ~50 + dolgiej 1 (+ imperia 1) = ~74. Snapshot (6, 7, 8) y frontend (9): 0.
- El resto queda formalmente vencido y lo recorre la cola como backlog nacional (no bloquea la beta: la snapshot no exige huella vigente).

## Fase 3 — plan

1. 03/10: implementar 1-4 (+gating), 5, 10, 11 (+12 si es seguro) en `eretz-b`, con tests y replays sobre HTML real guardado.
2. 04/10: canarios (TIV x3, chacra x3, dolgiej), suite completa, huellas finales -> UN fast-forward del nodo operativo -> prioridad de cola con las ~74 agencias (motivo + vencimiento).
3. 04-05/10: UNA recertificacion dirigida (~19 h de worker, ~10-12 h de reloj con 2 workers). En paralelo, sin carga pesada: 6-8 en el builder, 9 en el frontend.
4. 05-06/10: candidata final -> P2 -> Regression Gate -> QA navegador aislada -> performance -> suite -> rollback.
5. 07/10: freeze semantico (llega con margen).

## APLICADA 2026-10-03 11:17 (`5d71f1a`, fast-forward del nodo operativo)

Commits: `8e549bd` (ubicacion TIV + radio propio de tiv_busqueda + constantes de modulo en la huella), `4b300c9` (chacra/finca con dormitorios; wordpress taxonomia como texto), `ba48d16` (snapshot: provincia declarada por poligono, CABA ante provincia inferida; danisa reclasificada portal), `5d71f1a` (certificador: Banco/Resto de la Provincia no son provincia). Suite completa 3957/5.

Validacion previa: replay de 60 fichas TIV reales (35 ganan provincia correcta, 0 otros campos cambian; la regla barrio/localidad/partido se descarto porque sus localidades no estan en el catalogo), REST real de dolgiej (tipo 27/29, antes 7), tests de cada caso. Canarios = primeras 6 agencias de la prioridad (no se corre un tercer proceso de scraping: tope de 2 workers).

Fuera de la ventana (medido, con motivo): imperia (SVG inline junto al rotulo; arreglarlo cambia la lectura de cantidades de todo generico sin poder medir el radio), barrio/localidad/partido TIV (427 fichas: necesita alias en el catalogo), carrera de interfaz (hipotesis: el mapa toma el foco; radio 0, sesion de frontend aparte).

Recertificacion dirigida: `ERETZ_PRIORIDAD_DE_COLA.json` con 58 agencias hasta 06-10 12:00 (7.676 fichas, ~19,8 h de worker, ~10-12 h de reloj). Grandes con 1-8 filas rurales y sin evidencia (beba paez vilaro, crestale, farina, darquier) quedan para la cola normal.

| huella | antes | despues |
|---|---|---|
| generic/bitrix_landing | `73bd2da9e12d` | `de68d0b211b8` |
| generic/buscadorprop_json | `81de48712df2` | `92341cda40ce` |
| generic/category_html | `00b14ecee7dc` | `533812552dd6` |
| generic/empty_catalog | `850446ef8cc9` | `e7cd069ce24a` |
| generic/html_catalog | `fb8a49f0b814` | `fdfa64d4816a` |
| generic/mapaprop | `caaf5a295102` | `e9f6eef12f0e` |
| generic/no_inventory | `07e0b7d0e4c9` | `ce1b3cdf6f3b` |
| generic/php_ajax_search | `5a1e3569bdac` | `1dbbb6b90e83` |
| generic/php_query_catalog | `dfa8745ff62c` | `2f5672a7130a` |
| generic/portal_offset | `be01c868af8d` | `a0924c05ef8c` |
| generic/sitemap | `2a2881520418` | `cb6ba2de48a5` |
| generic/tiv_busqueda | `6a6eb486722f` | `c18bfaa1fa62` |
| generic/tokko_proxy | `facaa0e132cb` | `3a9e57b02357` |
| generic/wordpress_category | `acfc65763136` | `88afb51e87e1` |
| generic/xintel | `7132ab52147e` | `31fb707c2420` |
| tokko | `9029f5cc624f` | `1b146d5ab242` |
| wordpress | `cdc4fefef209` | `9a45f9fe2636` |
| wasi | `1178964c9e0a` | `c43c85ad620a` |

## Correcciones de canario dentro de la ventana (03-10)

- 11:49 dolgiej: sin `property_meta` el REST nunca se consultaba -> `d6a4cb2` (la taxonomia REST completa tipo/operacion que el HTML no dio). Solo cambio la huella wordpress; un unico resultado afectado.
- 11:59 campal: la senal de provincia veia «banco-provincia» en slugs (la exclusion solo aceptaba espacios) -> `f50e2d8`. Cambia todas las huellas (certificador); invalido solo 2 resultados de la ventana (benitez ullo, cadahia).

### Huellas FINALES (nodo operativo `f50e2d8`)

| estrategia | huella |
|---|---|
| generic/bitrix_landing | `62e0f87712c0` |
| generic/buscadorprop_json | `fd1bb0d0f03b` |
| generic/category_html | `61d75058ee68` |
| generic/empty_catalog | `5a5946538ca5` |
| generic/html_catalog | `52ca8a32d49a` |
| generic/mapaprop | `4888663a78a5` |
| generic/no_inventory | `4e45e13432ee` |
| generic/php_ajax_search | `fea4e9b1e9bf` |
| generic/php_query_catalog | `d2da6495fbb3` |
| generic/portal_offset | `85f690a12305` |
| generic/sitemap | `cea28e2bda33` |
| generic/tiv_busqueda | `d8ab75d2dc86` |
| generic/tokko_proxy | `6ad1f1c266ac` |
| generic/wordpress_category | `8bd0be501c4b` |
| generic/xintel | `06750cb9b4c8` |
| tokko | `9f0d2b04bfda` |
| wordpress | `cfce50223822` |
| wasi | `8bb65891750b` |

- 12:16 atencio (P0, DATO FALSO): el widget lateral KiteProp «Ultimas Propiedades» aportaba dormitorios ajenos (un local con 2 dormitorios); se vio porque rota y rompio la idempotencia. `d1f9fdf`: `cuerpo_principal` corta `div.sidebar-widget.recent-properties` (exige las dos clases). 21 agencias KiteProp (1.819 fichas, 46 filas sospechosas en v4n, fdc 14) agregadas a la prioridad: 78 agencias. Solo cambian las huellas de generico.
- Hueco de huella detectado (RESUELTO antes de beta, ver «Dependencias de huella»): wordpress delega en el extractor de generico (`_normalizar_con_generico`) pero su huella solo hashea `wordpress.py`; un cambio en generico que afecte esas fichas no invalida wordpress.

### Huellas FINALES v3 (nodo operativo `d1f9fdf`)

| estrategia | huella |
|---|---|
| generic/bitrix_landing | `4149f6d25512` |
| generic/buscadorprop_json | `02bee503d718` |
| generic/category_html | `663149d847e9` |
| generic/empty_catalog | `17c1a22cf906` |
| generic/html_catalog | `b630810f1c31` |
| generic/mapaprop | `313ebc58e08c` |
| generic/no_inventory | `1489703318a6` |
| generic/php_ajax_search | `11050855db48` |
| generic/php_query_catalog | `45e270429216` |
| generic/portal_offset | `0f13c4febf7c` |
| generic/sitemap | `ed6d2c2a3a35` |
| generic/tiv_busqueda | `9d2230bbf336` |
| generic/tokko_proxy | `75ff16048459` |
| generic/wordpress_category | `152b5e707755` |
| generic/xintel | `a273a9c64007` |
| tokko | `9f0d2b04bfda` |
| wordpress | `cfce50223822` |
| wasi | `8bb65891750b` |

## Dependencias de huella (cierre de la ventana, 03-10 ~13:00)

Pedido: medir y resolver WordPress -> generico antes de declarar la ventana cerrada. La auditoria (AST: alcance real desde `normalize`, imports relativos y a mitad de funcion, y lo que el certificador y el runner ejecutan de otros modulos) encontro CINCO huecos, no uno:

| # | hueco | quien ejecuta | que no estaba en su huella | arreglo |
|---|---|---|---|---|
| 1 | WordPress -> generico | `wordpress.normalize` pasa fichas a `GenericoConnector.normalize` (WORDPRESS_HTML 13, WORDPRESS_SITEMAP 5, y las REST sin meta de 58 WORDPRESS_REST) y lee precio con `cuerpo_principal` | todo `generic/common` | wordpress lleva `generic/common` (mismo payload que generico) |
| 2 | Certificador -> generico | `source_signals` (veredicto `source_provided`) audita WordPress y Century21 con `cuerpo_principal`, `_es_tabla_estructurada`, `_cuenta_de_ficha`, ETIQUETAS... | esas funciones en century21 | componente `certifier/generic_signals` = cierre AST de lo que el certificador usa de generico (no el archivo entero); tokko/wasi no lo llevan (senales propias) |
| 3 | Wasi -> generico | `wasi.discover` usa `fuera_de_servicio` | la funcion y sus 3 constantes | `generic/importado` = solo ese cierre |
| 4 | normalize comun -> estrategia | `normalize` llama sin condicion a `_fichas_en` (6 estrategias), `_normalizar_xintel` (elegida tambien por contenido) y `_normalizar_strapi` -> `_entero/_decimal/_coordenada` (tokko_proxy) | en TIV, categoria, query, MAPAPROP, xintel, WordPress... | pasan a `generic/common`; lo condicionado por clave de crudo queda de su estrategia en `LLAMADAS_CONDICIONADAS` y un test exige el `if` con la clave |
| 5 | transporte de formularios | `_fetch_listing`, `_catalogo_gvamax`, `_catalogo_por_tipo` (comunes) usan `formularios.bajar_formulario` | formularios.py fuera de 14 estrategias | `generic/form_transport` en todo generico |
| + | runner -> defect_triage | `descartes_sospechosos` usa `descarte_parecia_una_propiedad` | nada | `shared/descarte_con_senal` (cierre de esa funcion) |
| + | guarda en vuelo | worker con la definicion vieja de huella en memoria | `agency_fingerprints.py` no lo vigilaba | la guarda lo vigila |

Por que el test no lo vio: `test_huella_importados` miraba solo imports absolutos; `from .generico import` (relativo y dentro de una funcion) pasaba. Corregido, y `tests/test_huella_dependencias_cruzadas.py` (10 tests) fija cada caso.

### Radio

- Medido antes de tocar: certificaciones vigentes con huella v3 = **3** (benitez ullo, cadahia, dolgiej). Todo lo demas ya estaba vencido por la ventana (coherencia/wordpress/generico cambiaron a las 11:17). Arreglarlo ahora cuesta 3 agencias; arreglarlo despues de la pasada habria costado la pasada entera.
- WordPress: 99 agencias (51 COMPLETE, todas ya vencidas por la ventana) -> costo incremental 0 + dolgiej. Wasi: 13, ninguna con la huella v3 (ya vencidas por la ventana) -> costo incremental 0. Century21: ninguna agencia certificada. El snapshot usa estado, no vigencia de huella: nada sale de la candidata por esto.
- Radio minimo correcto: wordpress depende de verdad de todo `normalize` (no hay rama que no pase por el comun); wasi y century21 solo de cierres chicos. No se invalido nada que no ejecute el codigo.
- Futuro: un cambio en `generic/common` ahora tambien reabre WordPress (99). Es el radio correcto: WordPress ejecuta ese codigo.

### Acoplamiento que queda (documentado, no se arregla en la ventana)

`discover`/`fetch_listing` (comunes) prueban los detectores de cada estrategia (`_catalogo_tiv`, `_catalogo_mapaprop`, ... 18 metodos). Cambiar un detector puede hacer que una agencia de OTRA estrategia pase a esta, sin cambiar la huella de la suya. Hoy no afecta a nada vigente (toda certificacion vigente es posterior a v4). Diseno propuesto post-beta: separar cada `_catalogo_X` en `_es_X(html)` (detector, comun) y la enumeracion (de la estrategia); cambiar un detector reabre todo generico, cambiar una enumeracion solo su estrategia.

### Huellas FINALES v4 (dependencias corregidas)

| estrategia | huella |
|---|---|
| century21 | `3f99fac81057` |
| generic/bitrix_landing | `875076ab8271` |
| generic/buscadorprop_json | `8cdede1b3c8f` |
| generic/category_html | `c5c001614089` |
| generic/empty_catalog | `3bd404663ee7` |
| generic/html_catalog | `a8c240272c8f` |
| generic/mapaprop | `042c29f65ce9` |
| generic/no_inventory | `ff5915b00338` |
| generic/php_ajax_search | `2206b9bbbb1a` |
| generic/php_query_catalog | `d131b1fc2103` |
| generic/portal_offset | `ac674429a97c` |
| generic/sitemap | `d3f2f0800bd8` |
| generic/tiv_busqueda | `8a9e2de5674d` |
| generic/tokko_proxy | `1c704856f014` |
| generic/wordpress_category | `99460ce53acf` |
| generic/xintel | `7af32a88b59b` |
| tokko | `ea47cf60748b` |
| wasi | `cfbaa6471ffd` |
| wordpress | `f0b21abaef35` |

Los canarios con resultado bajo v3 (benitez ullo, cadahia, atencio, dolgiej) NO cuentan: se repiten bajo v4.

### Canarios: evidencia de comportamiento (codigo de extraccion identico en v3 y v4)

- atencio (KiteProp, 12:57, COMPLETE): local 0/4 con dormitorios, galpon 0/2, terreno 0/113; casa 123/142, departamento 37/39. Los altos son propios (hoteles con 34 y 58 habitaciones publicadas, complejo de 11 cabanas); la oficina con 3 es «tres locales (oficina o consultorio)» de su propia ficha. P0 corregido.
- dolgiej (WordPress REST): las 2 sin tipo son «Hotel ... 34 habitaciones en suite» (pizarro-5369) y «Edificio comercial ... con local, oficinas, terraza y 8 cocheras» (araoz-631). La taxonomia ERETZ no tiene tipo canonico Hotel/Edificio: NULL honesto, no se fuerza. La senal del certificador en araoz dispara por «local/oficinas/cocheras», que describen lo que el edificio CONTIENE. Estado honesto NEEDS_FIX (1 extraction_failed), clase COBERTURA/TAXONOMIA, deuda post-beta: tipos canonicos hotel/edificio o un tipo «otro» con evidencia.
- campal (13:11, en vuelo con codigo previo al deploy, no cuenta): NEEDS_FIX prov=0.197. 118/147 sin ciudad/provincia = deuda TIV de ubicacion (barrio/localidad/partido sin mapa de zonas). 2 extraction_failed: lp824340 declara «Francisco Alvarez, Provincia de Buenos Aires» solo en la descripcion (deuda TIV, NULL honesto); lp656891 la senal dispara por «Provincia Net» (servicio del Banco Provincia): falso positivo NUEVO de la senal del certificador. No es P0/P1 (no hay dato falso, 1 ficha, agencia NEEDS_FIX igual) y arreglarlo mueve TODAS las huellas: KNOWN_DEBT post-beta (agregar «Provincia Net» a RE_PROVINCIA_QUE_NO_ES_DATO).

## SEMANTIC_WINDOW_CLOSED — 2026-10-03 13:56 (HEAD semantico congelado: `6d04163`)

Canarios finales, todos bajo la MISMA huella v4 (ninguno invalidado por codigo cambiado en vuelo):

| canario | estrategia | resultado v4 | igual a la evidencia v3 |
|---|---|---|---|
| benitez ullo | generic/tiv_busqueda | CERTIFIED_COMPLETE, enum 15, prov 1.0 | si |
| cadahia | generic/tiv_busqueda | CERTIFIED_COMPLETE, enum 28, prov 0.857 | si |
| dolgiej | wordpress | NEEDS_FIX honesto (Hotel/Edificio sin tipo canonico), triaje CONTINUE | si |
| atencio | generic/sitemap (KiteProp) | CERTIFIED_COMPLETE, enum 320, run1 = run2 | si |
| aiba | tokko | CERTIFIED_COMPLETE, enum 44 | si |
| campal | generic/tiv_busqueda | NEEDS_FIX honesto (deuda TIV + falso positivo «Provincia Net»), triaje CONTINUE | si |

KiteProp (P0) verificado por recertificacion v4 (atencio + aguilar bugeau, 3/21 hasta ahora): local, oficina, galpon, cochera (0/3), terreno sin dormitorios heredados; casa 129/148 y departamento 101/107 conservan los propios. Las 3 no residenciales con dormitorios de aguilar bugeau (2 locales, 1 oficina) los PUBLICAN en su propia ficha («Ambientes 3 Dormitorios 2», sin widget lateral en la pagina): dato de la fuente, no herencia. La oficina de atencio idem («tres locales»). Seguimiento: `_b_scratch/kiteprop_dorm_v4.py` sobre las 18 restantes a medida que recertifican; una herencia nueva reabre la ventana como P0.

Criterios: canarios estables bajo una huella (si); P0/P1 conocidos resueltos (si); dependencias de huella correctas (`6d04163`); prioridad recertificando con huella final desde 13:08 (si); suite completa 3969 passed / 5 skipped (si); ningun cambio semantico conocido pendiente (si: «Provincia Net» y Hotel/Edificio son deuda post-beta documentada).

Siguiente: FREEZE HEAD (solo docs/operativo hasta beta) -> la candidata se construye cuando la prioridad (78) termine de recertificar con v4: construirla antes metería paquetes previos a los arreglos (p. ej. KiteProp con dormitorios ajenos) -> DEPLOY GATES -> REGRESSION GATE -> BROWSER QA AISLADO -> PERFORMANCE -> FULL SUITE FINAL -> BETA CANDIDATE.

## VENTANA REABIERTA 14:11 -> P0 corregido 14:23 (`b69d2563`)

La verificacion KiteProp sobre la prioridad (no los canarios) encontro dato falso: `eckert` publica una oficina «Ambientes: 2 Dormitorios: - Baños: 4» y la extraccion guardaba 2 dormitorios. Causa: en `_cuenta`, el rotulo con dos puntos no encuentra numero («-»), y la busqueda en prosa lee «2 Dormitorios» tomando el numero de AMBIENTES. Misma familia que el P0 de las 12:16 (valor de un campo vecino), plantilla KiteProp distinta (las vecinas van en `div.widget.widget_recent_property`, tampoco cortado).

Radio medido antes de arreglar: replay del codigo viejo sobre 116 fichas reales de 41 agencias con la firma dorm==amb: afecta SOLO a la plantilla KiteProp con guiones (fdc 2/3; ninguna otra plantilla). Cota: 78 de 1.802 fichas KiteProp (fdc 32, crm 11, atencio 10, ...), sobre todo monoambientes con «1 dormitorio» y locales/oficinas con dormitorios. Clase DATA_CORRUPTION, P0.

Arreglo: «Rotulo: -» es vacio declarado (NULL), nunca relleno por adyacencia; y se corta `widget_recent_property`. Suite 3973 passed / 5 skipped. Tests: `tests/test_generico_vacio_declarado.py`.

Costo: cambian las huellas de generico/wordpress/century21 (v5); tokko y wasi NO cambian (aiba sigue final). Se repiten bajo v5: benitez ullo, cadahia, dolgiej, atencio, campal, y las ~20 de la prioridad ya hechas con v4.

### Huellas FINALES v5

| estrategia | huella |
|---|---|
| century21 | `fdcde95bcba5` |
| generic/bitrix_landing | `c2bced7ffa3b` |
| generic/buscadorprop_json | `70c9ff6d7de7` |
| generic/category_html | `b9a125895771` |
| generic/empty_catalog | `c16dd05629a8` |
| generic/html_catalog | `0fb5151ce8f8` |
| generic/mapaprop | `d28e4f998994` |
| generic/no_inventory | `1eca6fb68052` |
| generic/php_ajax_search | `f52764b1e662` |
| generic/php_query_catalog | `5f816157e1b3` |
| generic/portal_offset | `e733fad043ce` |
| generic/sitemap | `795f88bcc17a` |
| generic/tiv_busqueda | `7f304a7bbacc` |
| generic/tokko_proxy | `74db0059de27` |
| generic/wordpress_category | `4b9d6e902016` |
| generic/xintel | `aae2612f083d` |
| tokko | `ea47cf60748b` |
| wasi | `cfbaa6471ffd` |
| wordpress | `94d5c076421f` |

## SEMANTIC_WINDOW_CLOSED (definitivo) — 2026-10-03 15:12, HEAD semantico `b69d2563`, huellas v5

| canario | resultado v5 | igual a v3/v4 |
|---|---|---|
| benitez ullo | CERTIFIED_COMPLETE (14:36) | si |
| cadahia | CERTIFIED_COMPLETE (14:41) | si |
| dolgiej | NEEDS_FIX honesto, Hotel/Edificio (14:46) | si |
| campal | NEEDS_FIX honesto, deuda TIV (15:06) | si |
| atencio | CERTIFIED_COMPLETE, enum 320 (15:10) | si |
| aiba | CERTIFIED_COMPLETE (tokko: huella v4 = v5, 13:54) | si |

atencio bajo v5: las 10 filas con dormitorios = ambientes son de la fuente («Ambientes: 1 Dormitorios: 1» en dos monoambientes; «Ambientes: 2 Dormitorios: 2» en un depto titulado «1 dormitorio»: contradiccion de la propia fuente, no del parser). El P0 de rotulo vacio se verifica en fdc/eckert/crm a medida que recertifican (`_b_scratch/kiteprop_dorm_v5.py`).

Siguiente: la prioridad (78) recertifica con v5; al terminar -> BUILD FINAL CANDIDATE -> DEPLOY GATES -> REGRESSION GATE -> BROWSER QA AISLADO -> PERFORMANCE -> FULL SUITE FINAL -> BETA CANDIDATE.

## Cierre de 15:12 retirado: paro de eckert 15:30 -> `02995d43` (huellas v6)

Bajo v5, `eckert` (la agencia donde se encontro el P0) paro la cola: 5 monoambientes «Ambientes: 1 Dormitorios: -» quedaron correctamente sin dormitorios, pero la senal del auditor (`SOURCE_SIGNALS["dormitorios"]`, en prosa) seguia leyendo «1 Dormitorios» con el numero de ambientes y los contaba como extraccion fallida. Sin corregirlo, toda agencia KiteProp con rotulos vacios quedaba NEEDS_FIX y fuera del snapshot (fdc: 204 fichas).

Arreglo de radio minimo: el conteo vacio declarado se quita en `normalizar_texto_campos`, que el extractor y `source_signals` ya comparten (su docstring lo pide: la senal y la extraccion no pueden usar alfabetos distintos). Cambiar `agency_certifier.py` habria movido TODAS las huellas; asi tokko y wasi quedan iguales (aiba sigue final). Suite 3974 passed / 5 skipped. Paro diagnosticado en AGENCY_DEFECTS_DIFERIDOS (15:40).

Canarios a repetir bajo v6: benitez ullo, cadahia, dolgiej, atencio, campal. El cierre se declara de nuevo cuando esten.

### Huellas v6

| estrategia | huella |
|---|---|
| century21 | `28fa68848e70` |
| generic/bitrix_landing | `19d9e783cef7` |
| generic/buscadorprop_json | `652d2680ae78` |
| generic/category_html | `e4a8042a4e4b` |
| generic/empty_catalog | `523ee422c3d1` |
| generic/html_catalog | `7f9a1e799b5c` |
| generic/mapaprop | `2f2052e970bc` |
| generic/no_inventory | `4326363596ef` |
| generic/php_ajax_search | `26b8a10abc73` |
| generic/php_query_catalog | `c0ab488346dd` |
| generic/portal_offset | `25fbb6033bdf` |
| generic/sitemap | `e4b3f7ea2a8c` |
| generic/tiv_busqueda | `18436008d412` |
| generic/tokko_proxy | `398e49f296b6` |
| generic/wordpress_category | `55577a5fe420` |
| generic/xintel | `63518297cc41` |
| tokko | `ea47cf60748b` |
| wasi | `cfbaa6471ffd` |
| wordpress | `06596110b8b7` |

### Canarios bajo v6 (en curso) y hallazgo de dolgiej

- benitez ullo 15:56 y cadahia 16:02: CERTIFIED_COMPLETE, identicos a v3/v4/v5.
- dolgiej 16:09: NEEDS_FIX por «run inventories differ». La corrida 1 eligio WORDPRESS_HTML (la sonda REST `/wp-json/wp/v2/types` fallo de forma transitoria y `discover` cae en silencio a sitemap/HTML) y enumero 10 en una sola pagina declarando la enumeracion completa; la corrida 2 uso REST: 29, con cobertura identica a v5 (tipo 0.931, dormitorios 0.3448). El comportamiento del codigo es estable; la inestabilidad es de la fuente.
- Riesgo medido (FALSE_COMPLETE_RISK teorico): 6 de 101 agencias WordPress tuvieron alguna corrida degradada de REST a otra variante; las 6 terminaron NEEDS_FIX (doble corrida + revision de inventario bajo), ninguna certifico inventario parcial. Para certificar parcial harian falta las dos corridas degradadas igual: 0 casos. KNOWN_DEBT post-beta, con diseno: un fallo TRANSITORIO de la sonda REST tiene que abortar el descubrimiento (reintentable), no degradar la estrategia. No se hace ahora: mueve la huella de wordpress por un riesgo con 0 ocurrencias.
- campal 16:26 NEEDS_FIX (deuda TIV, igual a v4/v5) y atencio 16:33 CERTIFIED_COMPLETE (enum 320, igual a v3-v5). aiba final por huella tokko sin cambio. 6/6 canarios bajo v6. El cierre se declara cuando `eckert` y `fdc` (donde vive el P0) pasen bajo v6: los dos cierres anteriores se retiraron por declarar antes de verlas.

## SEMANTIC_WINDOW_CLOSED — 2026-10-03 17:25, HEAD semantico `02995d43`, huellas v6

Esta vez con la verificacion del P0 en SUS agencias, no solo en los canarios:

- `eckert` 16:49 CERTIFIED_COMPLETE: 4 monoambientes y la oficina 217237 sin dormitorios (ambientes conservados); oficina y cochera sin dormitorios; 0 filas dorm==amb. Dormitorios 0.761 (v4) -> 0.652: lo que bajo era falso.
- `fdc` 17:17 CERTIFIED_COMPLETE (204): local 0/11, cochera 0/4, galpon 0/2, oficina 0/2, terreno 0/38 con dormitorios; 7 monoambientes sin dormitorios. Los 3 con 1 dormitorio lo publican: dos «Dormitorios: 1» en su tabla; `paraguay-1800` tiene la tabla vacia pero la descripcion dice «departamento a estrenar de 1 dormitorio» (contradiccion de la propia fuente; se toma lo afirmado).
- Canarios v6: benitez ullo, cadahia, atencio COMPLETE; campal NEEDS_FIX (deuda TIV); dolgiej estable en codigo (corrida REST = v5), NEEDS_FIX por sonda REST transitoria de la fuente (deuda medida, 0 casos de cierre parcial en la historia); aiba COMPLETE (tokko sin cambio).
- crm y lurati bajo v6 iguales a v5 (NEEDS_FIX de cobertura: tipo solo en texto libre; operacion de un fondo de comercio).

Deuda post-beta registrada en la ventana: «Provincia Net» en la senal de provincia; tipos Hotel/Edificio; detectores de estrategia separados de la enumeracion; sonda REST transitoria de WordPress que degrada la variante; tipo solo en texto libre (KiteProp).

Siguiente: terminar la prioridad (78) con v6 -> BUILD FINAL CANDIDATE -> DEPLOY GATES -> REGRESSION GATE -> BROWSER QA AISLADO -> PERFORMANCE -> FULL SUITE FINAL -> BETA CANDIDATE.
