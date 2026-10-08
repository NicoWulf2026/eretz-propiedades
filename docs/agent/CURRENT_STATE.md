# ERETZ — estado actual

Estado VIGENTE, no bitácora. La historia está en Git (`git log`; la bitácora anterior de este
archivo: `git show 6ee927bb80:docs/agent/CURRENT_STATE.md`). `database_writes: 0` en todo.

**Actualizado:** 2026-10-04 22:20 (ver bloque LOCAL 04-10) · **Rama:** `handoff/codex-unificacion-2026-09-18` (push solo acá)
**Fase:** certificación/recertificación continua + calidad de lo servido + preparación productiva.

## SPRINT BETA 12/10 — 2026-10-07 12:xx (estado REAL verificado en la PC)
- **08-10 14:3x — P0 de identidad servido + sprint_rc5 SERVIDA 08-10 15:10 (READY #7d HECHO, autorizado por el usuario: sha 2299bc76, 77.740, 0 filas ajenas, QA 14/14 + 22/22, respaldo rc2 en _anteriores/rc2_2026-10-08)**. La servida rc2 tiene 12 filas de OTRAS inmobiliarias atribuidas a `estudio inmobiliario dos santos` (perfil en patagonprop.com; generico lee el sitemap de la RAIZ del host). Contenido por directorio (dos santos y hogarfe -> EXTERNAL_PORTAL_PROFILE, respaldo en `_respaldos/`). sprint_rc5 (`6f2f52a889`, 77.740) las saca y paso TODO: P2 0, Regression Gate 23/23, QA API 22/22, navegador 71/71, benchmark 14/14, ensayo deploy+rollback por hash, suite 4.073/5/0. El despliegue automatico por P2 lo bloqueo el control de permisos del entorno ('Production Deploy'): no se reintenta; espera autorizacion del usuario (comando en READY #7d). Cola: 2 workers, vigilante armado.
- **ERETZ_BACKEND_BETA_READY = YES** (07-10). **PRODUCTION_READY = NO**: backup/restore bloqueado por credencial
  (READY #1) y sin binarios de PostgreSQL locales. Auditoria: `docs/agent/PRODUCTION_READINESS_2026-10-07.md`.
- **SEMANTIC_FREEZE = ACTIVE** desde 07-10 10:5x (HEAD semantico `bdba3ddbf4`; huellas `_b_scratch/huellas_freeze_2026-10-07.json`).
- **BETA CANDIDATE sprint_rc2** (READY #7c; reemplaza a final_v7d): 76.486 props, sha256 `6ebecc0e…278ab`; P2 0 fallas,
  Regression Gate 317/317 (0 sin explicar), QA API real 22/22, QA navegador 71/71, suite 4.063/0, frontend 1.271/0 + tsc,
  ensayo de despliegue + rollback verificado por hash. Servirla = decision del usuario.
- Cola: 2 workers, relanzador y vigilante desde E:; prioridad reducida a `fabiana bert` (portal). Ledger ~1.190 agencias.
- Flujo: desarrollo en `eretz-b` (`integration/eretz`), nodo `eretz-unified` solo por `merge --ff-only`.

## LOCAL — cuenta B, 2026-10-06 03:30 (estado REAL verificado en la PC)
- **BETA CANDIDATE `snap_final_v7d`** (74.080 props, sha256 `4a2ed923...`, READY #7b; reemplaza a v7c por los dormitorios de
  widget en locales/oficinas/galpones, regla `841a4b6`; suite 4027, QA 71/71, P2 0, gate 0 sin explicar). Antes:
  **BETA CANDIDATE `snap_final_v7c`** (73.790 props, sha256 `998bed36...`, READY #7b, despliegue = decision del usuario):
  P2 0 fallas, Regression Gate 0 sin explicar / 0 bloqueantes, QA aislada 71/71, benchmark sin regresion, suite 4019, rollback 6/6.
  P0 de final_v6 resueltos (operacion por subcadena 487 -> 24, monoambientes 2+ dorm 96 -> 0, tipos en ingles 0, blanco).
  Constructor: `02a3133` (monoambiente), `8e68d88` (sin altas no certificadas). Tests del vigilante aislados (`2d50cdd`).
- **Raiz canonica: `E:\ERETZ Propiedades`** desde el 04-10 (migracion definitiva, `docs/agent/MIGRACION_DEFINITIVA_2026-10-04.md`).
  Nodo operativo `E:\ERETZ Propiedades\eretz-unified` (rama `handoff/codex-unificacion-2026-09-18`), desarrollo
  `E:\ERETZ Propiedades\eretz-b` (`integration/eretz`), HEAD `5cd3e7b` (= nodo). D: esta desconectado fisicamente desde el 06-10 (READY #14 hecho; validacion post-desconexion en HANDOFF punto 5).
- **v7 desplegado en el nodo (04-10 22:1x, `5cd3e7b`)**: P0 hallados despues de los gates de final_v6 -operacion por
  palabra entera (`rent` en `frente`: 516 filas/110 agencias), rotulo con icono vacio (blanco), heredadas sin operacion
  por subcadena en el constructor-. Huellas v7: 18/18 cambiaron (`base.py` compartido). Prioridad: 110 agencias
  afectadas (hasta 08-10). Luego: reconstruir candidata y repetir gates (READY #7b EN ESPERA).
  Medicion intermedia `snap_v7a` (05-10 15:36, 73.073 props): operacion solo por subcadena 487 -> 113 (las 113 son de
  agencias aun sin recertificar), tipos en ingles 16 -> 0, heredadas anuladas 175. Regression Gate: 350 pendientes
  clasificadas (253 correcciones, 96 KNOWN_DEBT, 1 falsa perdida, 0 sin explicar); las 38 perdidas nuevas frente a
  final_v6 dan IGUAL con el codigo v6 sobre el HTML de hoy (replay): son cambios de las fuentes, no de v7
  (`_b_scratch/clasif_v7a.py`, `gate_valores.py`). Deuda nueva: plataforma 'Template4' descarta conteos con la senal
  'cocheras'; orden de listado no determinista (tokko gabilan, generico matias sosa). Cola: prioridad 63/93 (las otras 18
  no tienen certificacion previa); el resto es del w1 por el reparto por host. Arreglos de cola: carrera al borrar la
  bandera (`42e1150`), `recertificar` en el archivo de prioridad (`648c097`; pelay recertificada tras el corte de DNS).
- **Ventana semantica final CERRADA** (huellas v6, HEAD semantico `02995d43`; `docs/agent/VENTANA_SEMANTICA_FINAL.md`).
  Prioridad 78/78 recertificada con v6 (04-10 15:58).
- **BETA CANDIDATE `snap_final_v6`** (`E:\ERETZ Propiedades\_b_scratch\medicion\snap_final_v6`, 72.387 props): P2 0 fallas,
  Regression Gate 0 sin explicar / 0 REAL_BETA_BLOCKER (152: 87 correcciones, 65 KNOWN_DEBT), QA aislada 71/71,
  performance sin regresion, suite 3980 + frontend 1271, rollback 6/6. Despliegue = READY #7b, decision del usuario.
- **Cola**: 2 workers desde E:, tareas `ERETZ_relanzador`/`ERETZ_vigilante_paros` re-registradas desde E:. El
  vigilante ahora ve paros sin bandera (`PARO_SIN_BANDERA`, `90c659f`). Ledger: 1038 agencias — 529 CERTIFIED_COMPLETE, 266 NEEDS_FIX, 116 IDENTITY_PENDING, 67 BLOCKED_EXTERNAL, 58 CERTIFIED_BEST_AVAILABLE, 2 NO_INVENTORY_CONFIRMED.
- **Post-beta** en rama aparte `b/postbeta-lote8` (worktree `eretz-b-dev`, NO integrada): senal de provincia
  (`aac53f6`). Deuda documentada en VENTANA_SEMANTICA_FINAL y BETA_12_10.
- **Bloqueado externo**: restore (READY #1, sin credencial de lectura), validacion del writer hospedado.
- **Disco**: E: es un HDD USB; las mediciones de latencia locales son ~1,7x las de D: (sin efecto en la API beta).

## LOCAL — cuenta B, 2026-10-01 (estado REAL verificado en la PC)
Rama canónica `integration/eretz`; worktree de B `E:\ERETZ Propiedades\eretz-b` (venv propio `.venv` con
`requirements.lock`: el Python global de los workers no se tocó). Worktrees auxiliares de B:
`eretz-b-dev` (rama local `b/lote5-dev`, lote 5 en desarrollo) y `eretz-b-medicion` (detached, medición P10).

- **Cola parada ~11 h al tomar la posta**: 10 paros FAMILIA sin firmar (8 generico, wordpress, wasi,
  tokko) excluían 1.819 de 1.819 agencias desde el 30-09 22:17 (el más viejo, 38 h). Diagnosticados
  y firmados 12 (09:10–10:57): fuente (bajas que el listado sigue enlazando: mooswalder, d amato,
  amaya; slug cambiado: casamia; altas durante la corrida: coldwell; techo fantasma 7.777 del
  directorio: ana de napoli), resuelto por la realidad (andereggen certificó por tokko) y defectos
  reales de plantilla que van al lote 5 (b b, azara, inversiones, agostina saracena, analia dulsan).
  Cola corriendo de nuevo desde 09:12.
- **Nodo operativo integrado**: `eretz-unified` fast-forward a `aae873d` (integration/eretz) a las
  10:3x; huellas por estrategia idénticas (generico html `d17bf285429f`, sitemap `9ec0a67a055d`, tokko
  `019a4005b09b`, wordpress `55a1ea72a700`, wasi `5161d6f75fa5`): sin reinicio de recertificación.
- **Ledger** (última fila por agencia, 10:58): 846 agencias — 403 CERTIFIED_COMPLETE, 46
  BEST_AVAILABLE, 225 NEEDS_FIX, 117 IDENTITY_PENDING, 53 BLOCKED_EXTERNAL, 2 NO_INVENTORY.
- **Workers**: 2 (régimen `ERETZ_WORKERS.json`, prueba de 3 rechazada el 29-09); cola `--ready` 1.819.
- **Snapshot servida**: v4l-c (65.028 propiedades, 603 agencias, 558 MB). Candidata de medición
  construida hoy con el código de integration/eretz: 66.211 propiedades (+1.183 por certificaciones
  nuevas), sin desplegar.
- **Suite LOCAL estricta** (`ERETZ_REQUIRE_LOCAL_DATA=1`, Windows, Python 3.14.4): 3.775 passed,
  4 failed (symlinks de la activación beta: WinError 1314; arreglado, se saltean donde el SO no los
  permite), 1 skipped. 0 salteos por falta de GeoRef/datos.
- **Frontend (Windows)**: typecheck, lint, vitest 1.270 passed / 9 skipped, build OK. `npm audit`
  marcó 1 CRÍTICA nueva (GHSA-vcvr-r3jv-pc5j, RCE en next/og; el sitio usa opengraph-image) →
  next 16.3.8 (`3d9fb63`), audit 0.
- **QA de navegador sintética (Windows)** sobre `b1f182cb`, árbol limpio: 82 → 75 ok, 0 fallos,
  7 salteados (flag del asistente). Antes: 1–2 fallos intermitentes por clic antes de la hidratación
  (arreglado con espera de `networkidle`); el informe ahora registra el SHA.
- **P18 READ-ONLY: UNABLE_TO_VERIFY** — `ERETZ_PREVIEW_RO_URL` no está definida en la PC y la lectura
  con la única credencial disponible (`SUPABASE_DATABASE_URL` del `.env` legado) fue denegada por el
  control de permisos del agente. Acción del usuario: definir la variable RO o autorizar la lectura.
- **IGN**: `connectors/geometria/provincias_ign.json` generado y validado (`1f7cb84`).
- **Lote compartido 5 APLICADO** (`759babb`, 13:59): F1–F9 + Lote 4 v2 + P10 endurecido (detalle y
  mediciones en `lotes/README.md`). Nodo operativo en `759babb` → huellas nuevas (generico html
  `54ba5907da3c`, sitemap `590af5151782`, tokko `9029f5cc624f`, wordpress `c3540dd9e207`, wasi
  `1178964c9e0a`): recertificación completa en curso.
- **LOTE 7b APLICADO 2026-10-02 13:03** (`8c45a67`): ciudad de fichas TIV del GBA (el og:title trae «G.B.A.» con
  puntos). Cambia la huella de todo generico. Snapshot: `c363949` (foto llamada «inmobiliaria-...» ya no se descarta sin
  repeticion: 128 fichas sin foto). Regression Gate v4m3 116 -> 73 clasificados; chacra/finca -> terreno = KNOWN_DEBT beta.
- **LOTE 7 APLICADO 2026-10-02 05:53** (`bb03c09`): TIV Tecnogestion por su buscador (variante `TIV_BUSQUEDA`) +
  zonas TIV. Corrige los 16 falsos CERTIFIED_COMPLETE de abajo al recertificarse. Huellas: generic/html_catalog
  `d3b6f3b11b3b`, generic/sitemap `0143b30a5714`, generic/tiv_busqueda `3e54b1dffdc1`; wordpress `cdc4fefef209` y
  tokko `9029f5cc624f` sin cambio. Canarios: campal 147/147, coseglia 340/340, de leo 88/88, cattaneo 111/111.
- **FALSO CERTIFIED (clase 1) DETECTADO 2026-10-02 03:50: familia TIV Tecnogestion.** 16 agencias TIV estan
  CERTIFIED_COMPLETE con la enumeracion de la portada, que es un subconjunto ROTATIVO: su propio buscador
  (`/buscar/inmuebles/`) declara mucho mas (`bts` 26 de 893, `coseglia` 21 de 340, `miguelez` 24 de 225,
  `centro obligado` 22 de 193...; ~390 enumeradas contra ~2.540 declaradas). Lo publicado de ellas es real,
  pero «COMPLETE» es falso. Arreglo en `b/lote7-dev` (variante `TIV_BUSQUEDA`: total declarado + POST
  `/Buscar/CargaMasInmueblesParam`; campal 147/147). Al aplicarse cambia la huella de todo `generico` y las 16
  se recertifican con el catalogo completo. Lista: `_b_scratch/tiv_declarado.json`.
- **LOTE 6 APLICADO 2026-10-02 01:22** (`0335f2a`, squash de `b/lote6-dev`; nodo operativo `eretz-unified`
  adelantado). Huellas nuevas: generic/html_catalog `4cf19a45cfa5`, generic/sitemap `c7e9a9f2b30a`,
  wordpress `cdc4fefef209`; tokko `9029f5cc624f` y wasi `1178964c9e0a` SIN cambio. Radio 446 agencias
  (solo ~60 ya recertificadas con la huella del lote 5). Medicion, canarios y backlog en `lotes/README.md`.
- **Aceleracion (pedido del usuario 01-10)**: KPI por hora de reloj `scripts/kpi_de_la_cola.py`
  (14:00-23:42: 11,6 resoluciones/h de reloj, 0 h sin resultados, paro->liberacion mediana 2 min);
  backlog por familia y deuda de diagnostico `scripts/backlog_de_lote.py` (133 familias vivas, 51 paros
  sin diagnostico propio); mapa de tracks A/B `docs/agent/TRACKS_A_B.md`.
- **Hallazgo sobre la diferida por precedente**: la firma exacta (`defect_triage.firma`) es GRUESA; dentro
  de una misma firma los diagnosticos humanos nombran causas distintas. La diferida automatica no certifica
  nada, pero su texto copiado no es la causa de la agencia nueva: por eso `backlog_de_lote` cuenta las
  agencias sin diagnostico propio. Corregido ademas: 19 diferidas de B con `radio` AGENCIA en paros FAMILIA
  (no servian de precedente); el firmador de B ahora toma el radio del paro.
- **Prueba de 3 workers (P5) APROBADA** por el relanzador a las 20:02 (`regimen_de_workers.evaluar`,
  `ERETZ_WORKERS.json` + `ERETZ_WORKERS_REGIMEN.jsonl`): 14:00–20:02, 78 agencias, **13,0 por hora
  activa** contra 8,0 de la línea base de 2 workers (28–29/09), bloqueo 0,0 (base 0,075), paros por
  agencia 0,154 (base 0,14; todos de extracción, ninguno de carga). Régimen vigente: 3 workers, todo
  Tokko en el worker 0. Tope duro: 3.
- **Cola**: presupuesto adaptativo por corrida para catálogos lentos (`969070e`); paros del día
  firmados (13 diferidas, todas con diagnóstico contra la fuente); Regression Gate 678 agencias,
  0 pendientes (10 revisadas: 4 CORRECCION, 6 CAMBIO_EN_LA_FUENTE).
- **Snapshot**: la candidata del día (66.211) fue ABORTADA por la compuerta P2 (100 bajas sin motivo:
  filas servidas de agencias que retrocedieron a NEEDS_FIX). Arreglado el constructor (`--servida`,
  `0058f7c`). La candidata v4m (lote 5 + P10 + conservación) se construye en
  `D:\INMO CAPITAL\_b_scratch\medicion\snap_v4m`; **su despliegue requiere autorización del usuario**:
  el control de permisos del agente lo trató como despliegue y lo denegó (READY #7).
- **Evidencia para CLOUD** (fixtures en `tests/fixtures/cloud_bridge/`): martelliti =
  PROPERTY_LOCATION (39 direcciones distintas en 44 fichas; la oficina va en el pie), fenix = OTRA
  (la página solo dice «Superficie»), paladino = Strapi v3 sin clave, Wix (liprandi) = páginas de
  931 KB > tope 800 KB.

## Automatización (ERETZ AUTOMATION)
Encender/apagar TODO: `ERETZ_AUTOMATION_ON.cmd` / `ERETZ_AUTOMATION_OFF.cmd` en la raíz del repo.
Detalle, estado y cómo apagar a mano: `docs/agent/ERETZ_AUTOMATION.md`.
Ver estado: `python scripts\eretz_automatizacion.py estado`.

| pieza | qué hace | dónde |
|---|---|---|
| 2 workers (máx.) | certifican; paran entre agencias ante banderas o cambio de huella | `scripts/run_agency_certification_queue.py` |
| tarea `ERETZ_relanzador` (10 min + al iniciar sesión) | relanza los que falten, acota paros a familias, libera familias | `scripts/relanzar_la_cola.py`, pythonw |
| tarea `ERETZ_vigilante_paros` (5 min + al iniciar sesión) | escribe `ERETZ_QUEUE_WATCH_STATUS.json`, `--sin-alerta` (sin popups) | `scripts/vigilante_de_paros.py`, pythonw |
| interruptor `ERETZ_AUTOMATION_OFF.json` | si existe, ni el relanzador ni el runner arrancan nada | `scripts/interruptor_eretz.py` |

- Paros: `FAMILIA` detiene la familia; `COMPARTIDO` con causa nombrada detiene todo;
  `COMPARTIDO/sin_determinar` detiene su familia. Se libera con diferida firmada posterior o con
  cambio de huella. Libro: `ERETZ_FAMILIAS_DETENIDAS.jsonl`. Radio `APAGADO` = lo puso el OFF.
- Orden: conocidas por `checked_at` ascendente, intercaladas 1:1 con nuevas.

## Resultados (paquetes en `ERETZ_AGENCY_CERTIFICATION_20260827/agencies`, 28-09 21:17)
| estado | agencias |
|---|---|
| CERTIFIED_COMPLETE | 287 |
| CERTIFIED_BEST_AVAILABLE | 37 |
| NEEDS_FIX | 178 |
| BLOCKED_EXTERNAL | 48 |
| IDENTITY_PENDING | 140 |
| NO_INVENTORY_CONFIRMED | 1 |

Recertificación completa en curso desde el 28-09 07:29; los lotes compartidos del día
(`021907caea`, `1b6cf264f7`, `3e1081b107`, `8a8d0b193f`) la reinician por huella.

## Decisiones registradas (28-09)
- **Identidad**: dos agencias con la MISMA web oficial → `IDENTITY_PENDING` con motivo
  `IDENTITY_REVIEW` (hoy solo `martinez negocios inmobiliarios` / `martinez propiedades`,
  inmueblesmartinez.com.ar). No se fusionan ni se atribuye inventario sin evidencia.
- **Exterior — DECIDIDO por el usuario (28-09, durable)**: recolección SÍ, preservación SÍ,
  publicación NO; ERETZ público = `ARGENTINA_ONLY`. La extracción las conserva enteras con
  `extra.publicacion_exterior = PRESERVED_NOT_PUBLISHED`, `politica_publica = ARGENTINA_ONLY`,
  `pais_publicado` (ISO), evidencia y lo publicado (`ciudad/barrio/provincia_publicada`); nunca se
  les afirma geografía argentina. La snapshot pública las excluye (`exterior.publicable` + la misma
  evidencia para filas aún no recertificadas; resumen `exterior_conservadas_no_publicadas`). La
  marca vieja `PRODUCT_DECISION_PENDING` se trata igual. 30 fichas de 12 agencias medidas.
- **CABA + provincia «Buenos Aires» — DECIDIDO (28-09)**: solo desempata la contención
  punto-en-polígono contra la geometría OFICIAL del IGN (`connectors/geometria/caba_ign.geojson`,
  WFS `ign:provincia` in1=02, 1.024 vértices, Ley 27.275, reproducible con
  `scripts/geo_poligono_caba.py`), a ≥100 m del límite. Sin coordenada, afuera o en la frontera:
  sigue el conflicto (fail-closed). Nada de radios, centroides ni cajas. De las 99: 32 se
  recuperan (cantale 30, agostinelli 2); 4 caen fuera (Paraná, La Matanza, Mendoza ×2) y siguen en
  conflicto; 63 de `blanco` sin coordenadas siguen sin ciudad.

## Calidad
- Regression Gate (28-09 09:5x): 461 agencias recertificadas, 0 pendientes (77 firmadas: echesortu 42 fotos WhatsApp-Image → DEFECTO_ARREGLADO en e9e6c7f709, 1 CORRECCION «BAÑO 3ER PISO»; ente 34 dormitorios/baños → DEFECTO_PENDIENTE, ver HANDOFF). Gate anterior 06:4x: 448, 280 firmadas.
- Suite completa (28-09 15:3x, `c951da087e`): 3.460 passed.
- Regression Gate (28-09 15h): 474 agencias, 0 pendientes (34 de berardi firmadas).
- Regression Gate (28-09 21h): 497 agencias, 0 pendientes (77 firmadas: 66 CORRECCION -alagna
  emprendimientos y tarjetas similares-, 10 CAMBIO_EN_LA_FUENTE -christian arce-, 1 DEFECTO_PENDIENTE
  -pozzobon «un baño» en palabras-).
- Suite completa (28-09 21h, `64790ba41e`): 3.541 passed.

## 29-09 tarde — ejecución de las políticas (`docs/agent/POLITICAS_PERMANENTES.md`)
- Lotes compartidos 1 y 2 APLICADOS (`a6746a9338`, `566d5a2644`): P6 certifica por identidad canónica
  verificada sin `main` (275 agencias; la fase 2 verifica ~1.000 webs del directorio más, ~79 %
  afirmables). El `eretz_id` del directorio de plataformas es de STAGING y no se usa.
- Workers (P5): la prueba de 3 subió los bloqueos del backend compartido de Tokko (prey, aparicio):
  régimen devuelto a 2 y todo Tokko al worker 0 (`99a9d41771`). Reprobar 3 con ese reparto.
- Retiros (P1): `scripts/verificar_retiros.py` en curso; la snapshot retira solo REMOVED
  (`--retiros-verificados`). Despliegue automático (P2): `desplegar_snapshot.py --automatico`.
- Regression Gate: 564 agencias, 0 pendientes. Páginas de categoría / archivos de WordPress fuera
  de la extracción y de la snapshot (46 servidas en la v4j).
- Pendiente de fuente puntual: `paladino` (Strapi propio en `api.` subdominio, catálogo entero en una
  respuesta > 800 KB), `lucas liprandi` / `dib kai` (Wix).

## CHECKPOINT CLOUD 2026-09-29 17:15 — estado real
- **Snapshot servida: v4l-c** desde 16:52 (despliegue automático P2; registro
  `ERETZ_API_CONTRACT/_despliegues/DEPLOY_2026-09-29T16-52-05.json`; respaldo de la v4j en
  `_anteriores/v4j_2026-09-28/`): 65.028 propiedades, 603 agencias, localidades 18.428, QA 14/14.
- Lotes compartidos 1, 2 y 3 aplicados (último `c4092f1238`); huella compartida `8bf7f9274ed4`.
- Cola: régimen 2 workers (Tokko al worker 0); 1.819 agencias en la cola `--ready`; ledger 766
  (338 COMPLETE, 40 BEST_AVAILABLE, 204 NEEDS_FIX, 132 IDENTITY_PENDING, 51 BLOCKED_EXTERNAL, 1 NO_INVENTORY).
- Suite 3.701 verdes; Regression Gate 578 agencias, 0 pendientes.
- **Arquitectura híbrida (29-09):** CODE_CLOUD_READY = YES; OPERATIONAL_CLOUD_READY = NO por
  decisión. LOCAL conserva ledger, paquetes, snapshots, workers, scheduler y datos privados; CLOUD
  trabaja desde GitHub en código, tests, docs, backend, API y tooling. Estado portable
  (`ERETZ_DATA_ROOT`), restore probado en otra raíz con 0 accesos a `D:\`.
- Continuidad: `docs/CLOUD_CONTINUATION_HANDOFF.md`, `docs/CLOUD_BOOTSTRAP.md`,
  `docs/NEXT_CLOUD_AGENT_PROMPT.md`, `docs/agent/ESTADO_DURABLE.md`.

`docs/agent/lotes/`: cambios a la huella COMPARTIDA preparados y verificados en `eretz-dev` (3.635 verdes),
sin aplicar porque reinician la recertificación entera: aglomerados GeoRef (+112 localidades), descartes
sin señal (4 agencias, 348 prop.), buscador Houzez / unidades / «Provincia: Argentina» (`o feely`, 600).
`o feely` tiene diferida firmada (29-09 10:05, radio AGENCIA): la familia wordpress queda liberada.

## CLOUD 2026-09-29 noche — rama `claude/sweet-curie-doa2mn` (derivada de `ce57824`)
Nada toca la huella. Integración y verificación en LOCAL: `HANDOFF.md` § PARA LOCAL.
- **P9 hecho**: título derivado «{tipo} en {operación} · {localidad}» en la web (`728ef67`);
  `hasValidTitle` intacto. Mobile sin tocar.
- **Suite reproducible fuera de la PC** (`bfa37a7`): en Linux/3.14.4 desde clone limpio
  3.558 passed, 170 skipped, 0 failed (antes 58 fallos). Marcador `georef` +
  `ERETZ_REQUIRE_LOCAL_DATA=1` para exigir los datos en LOCAL. `httpx2` al lock.
- **Snapshot sintética de QA** (`scripts/snapshot_sintetica.py`, 86 fichas; el commit
  `ab64c32` dice 58, fue un error de conteo): mismo esquema/documento que la real, rotulada;
  QA de API 14/14; `desplegar_snapshot.py` y `/readyz` la rechazan.
- **QA de navegador reproducible** (`scripts/qa_navegador_sintetica.py`): e2e completa sobre
  `f7d4b1c` limpio: 73 → 66 ok, 0 fallos, 7 salteados (asistente de publicación con flag apagado).
- **API beta P21 preparada** (`deploy/api-beta/`): imagen docker verificada, `/healthz`,
  `/readyz`, activación/rollback atómico de snapshot en volumen. `EXTERNAL_ACCOUNT_REQUIRED`.
- **Rol escritor P18 preparado** (`b74184b`): cargador LOGIN NOINHERIT + escritor; revoca la
  membresía de `eretz_preview_ro` (la credencial de solo lectura del Preview podía escribir
  vía canario). PGlite 14/14. Sin crear.
- **P7 activo** (`21ebbe0`): cobro dentro de cada proveedor pago antes de cada pedido; costo por
  consulta declarado (`ERETZ_SEARCH_COSTO_USD_<PROVEEDOR>`) o no se busca; libro
  `ERETZ_SEARCH_SPEND.jsonl`; tope duro USD 10/mes.
- **Lote 4 (conteos en letras)** y **P10 (provincia por polígono)**: PARCHES en `docs/agent/lotes/`,
  sin aplicar (tocan la huella; P4). P10 necesita `provincias_ign.json` generado en LOCAL.
  La parte geométrica de P10 ya está en la rama (`connectors/poligono_provincia.py`, sin uso en la huella).
- **Cola**: no arranca sin GeoRef cargado (`b52a1cb`, caso `criscenti`).
- **Frontend**: undici con parche de seguridad (`1030149`); `npm audit --audit-level=high` = 0 y build ok.
- **CLOUD 30-09** (red del entorno sigue cerrada: agencias, IGN, GeoRef y WebFetch bloqueados):
  contrato real API→frontend (22 respuestas, `fcf4cee`); log JSON por pedido + x-request-id +
  noindex en la API (`e8986ff`); topes de largo en textos (`692be33`); workflow manual de QA de
  navegador (`ed525a6`); `/api/health` del frontend (`5e3a651`). martelliti: la línea junto al
  ícono sería la dirección de la OFICINA → verificar antes de arreglar B (HANDOFF).
- **CLOUD 30-09 (2)** — red todavía cerrada (IGN, GeoRef, agencias, incluso example.com):
  accesibilidad axe-core en 8 páginas de escritorio: 0 violaciones serias/críticas; corregido el
  `<main>` anidado del explorador y el detalle; e2e `test_accesibilidad.py` (`b246765`).
  Línea base de rendimiento, build de producción + snapshot sintética, loopback (sin red real,
  mediana de 3): LCP 130–225 ms, CLS 0, TTFB 7–29 ms, JS comprimido 139–169 KB por página
  (`/`, `/propiedades`, detalle, `/calculadoras`). Es referencia para comparar, no el rendimiento
  en Vercel.
- Pendientes con fixture de LOCAL: martelliti (dirección junto al ícono), fenix, paladino, Wix.
- Red del entorno CLOUD: sin salida a webs de agencias ni a IGN/GeoRef (política del entorno);
  sí PyPI, npm y Docker Hub. Lo que necesita red de fuentes queda para LOCAL.

## Snapshot de la API local
- **Servida: v4j** desde el 28-09 22:58 (exterior excluido, CABA por polígono, departamentos,
  precios simbólicos; deploy autorizado y verificado, respaldo de la v4g en
  `_anteriores/v4g_2026-09-28/`). Antes: v4g desde el 28-09 16:58 (deploy autorizado, controlado, sin rollback; registro en
  `ERETZ_API_CONTRACT/_despliegues/`, respaldo de la v2 en `_anteriores/v2_2026-09-08/`). Detalle:
  `READY_FOR_PRODUCTION_ACTION.md` §7. Todo reemplazo posterior sigue siendo deploy.
- **Candidatas v4l-a / v4l-b listas** (29-09, READY_FOR_ACTION; superan a la v4k): suman lo que
  los inventarios certificados vigentes saben y la preingestión del 03-09 no (+9.330, +50 agencias),
  refrescan 5.935 avisos con URL nueva y recalculan la geografía sobre la fila fresca (localidades
  9.494 → 18.507). La b además retira 2.637 que ya no están en el inventario COMPLETO de su agencia
  (muestra: 25/30 muertas). QA 14/14. Recomendada: v4l-b. Comandos en `READY_FOR_PRODUCTION_ACTION.md` §7.
- (histórico) Candidata v4k: v4j − 121 fichas del exterior; incluida en la v4l.
- (histórico) Candidata v4j (21:37; v4i + 42 precios simbólicos descartados): QA 14/14. La v4i era
  despliegue fue denegado por el control de permisos (deploy): espera autorización explícita.
  Comando en `READY_FOR_PRODUCTION_ACTION.md` §7.
- v4g: `_scratch/unification/snapshot_v4g_2026-09-28/` (integrity ok; +1.047 operación,
  +1.901 superficie total vs v4f; QA 14/14). Anterior: `_scratch/unification/snapshot_v4f_2026-09-26/` (v4e + frescura de la
  tarde; reconstruir cuando la cola recertifique el lote de la noche). Anterior: `_scratch/unification/snapshot_v4e_2026-09-25/` — 57.665 propiedades,
  `integrity_check` ok, reglas de calidad del runner + frescura desde NEEDS_FIX por campos.
  Detalle y latencias en `READY_FOR_PRODUCTION_ACTION.md` §7.

## Producción
Nada escrito. Bloqueos: credencial Postgres directa (`BLOCKED_EXTERNAL_CREDENTIAL`), sin
`pg_dump` con restore probado. Lista única: `docs/agent/READY_FOR_PRODUCTION_ACTION.md`.

## Tareas inmediatas
Ver `docs/agent/HANDOFF.md` § «Próxima prioridad».
