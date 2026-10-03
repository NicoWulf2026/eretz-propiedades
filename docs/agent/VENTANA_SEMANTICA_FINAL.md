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
