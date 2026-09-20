# ERETZ Propiedades — HANDOFF

**Fecha real de este handoff: 2026-09-20.** El nombre del archivo lleva
`2026-09-18` porque así se pidió y así se buscará; la fecha que vale para juzgar
la antigüedad de cualquier medición de acá adentro es la de arriba.

Este documento no cierra la misión. Es un punto de retomada.

---

## 1. REPO / BRANCH / HEAD

| | |
|---|---|
| Remoto | `https://github.com/NicoWulf2026/eretz-propiedades.git` |
| Branch de handoff | `handoff/codex-unificacion-2026-09-18` |
| HEAD | la punta de esa rama: `git rev-parse handoff/codex-unificacion-2026-09-18`. Un documento no puede contener el hash del commit que lo contiene |
| Worktree donde se produjo | `D:\INMO CAPITAL\eretz-unified` |
| Git status al cerrar | limpio |
| Base de la rama | `b36d8462df`, punta de `codex/eretz-unified-audit` |

`eretz-unified` está en un sistema de archivos que no registra ownership. Todo
comando de git contra él necesita:

```bash
git config --global --add safe.directory 'D:/INMO CAPITAL/eretz-unified'
```

### Relación con main

- **main local** (`e9630f5f70`): el candidato lo contiene entero. 554 commits
  por delante, **0 por detrás**.
- **main remoto** (`15e81991c0`): también contenido. Es un ancestro, no una
  alternativa; está ~534 commits atrás de la evolución local.
- **`main` no fue modificado, ni local ni remoto.**

### Qué contiene esta rama y por qué

`handoff/codex-unificacion-2026-09-18` = candidata unificada de Codex
+ la documentación de `release/eretz-private-preview` + las correcciones
de esta sesión.

Al inventariar los nueve worktrees apareció un hueco: `release/eretz-private-preview`
(`56f220c2b7`) tenía **36 commits que el candidato no contenía**, y ninguno
estaba en el remoto. Antes de mergear se comprobó qué tocaban: el diff de tres
puntos contra el candidato **excluyendo markdown está vacío**. Es decir, todo
cambio de código de esos 36 commits ya estaba en la candidata por otro camino
—incluido `fe5af30e88 fix(promocion)`, que pese al prefijo `fix` corrige un
documento de plan, no código—. Lo que faltaba eran 15 archivos `.md` con
mediciones que costaron horas de reloj. Se mergearon.

Los otros siete worktrees ya estaban contenidos en el candidato; se verificó uno
por uno con `git merge-base --is-ancestor`:

| Worktree | HEAD | ¿Contenido en el candidato? |
|---|---|---|
| `eretz-unified` | `b36d8462df` | es la base |
| `eretz-agency` | `d9238e64be` | sí |
| `eretz-audit` | `8521d47008` | sí |
| `eretz-integration` | `bd3f37c333` | sí |
| `eretz-main` | `e9630f5f70` | sí |
| `eretz-rescue` | `b6c326b0ce` | sí |
| `Inmo-Capital-api-v2-cutovers` | `806d5a5928` | sí |
| `Inmo-Capital-frontend-phase-a` | `ea7708f79f` | sí |
| `Inmo-Capital-main` | `56f220c2b7` | **no** → mergeado acá |

### Cambios sin commitear que había en otros worktrees

`Inmo-Capital-main` y `eretz-audit` mostraban los mismos 5 archivos modificados
(306 inserciones). Se comparó hash por hash: **los cinco son byte por byte
idénticos a los que `eretz-rescue` (`b6c326b0ce`) ya tiene commiteados**, y
`b6c326b0ce` es ancestro del candidato. No se pierde nada. No se tocó ninguno
de esos worktrees.

Los 104 archivos sin versionar de `Inmo-Capital-main` se trataron aparte; ver
§7 y `docs/handoff/herramientas-no-versionadas-2026-09-20/README.md`.

---

## 2. MISIÓN ORIGINAL

Comparar por **comportamiento** —no por antigüedad ni por sofisticación— tres
cosas: la evolución histórica en GitHub, el estado local previo a la
unificación, y una candidata unificada. Conservar la seguridad moderna y las
capacidades históricas que fueran mejores, corregir regresiones por familia,
unificar de forma reversible, y producir un veredicto con un plan hacia beta,
producción y cobertura nacional.

No es una reescritura ni una fusión ciega. **Código histórico ≠ código
correcto**, y también al revés: la sofisticación moderna no garantizó
corrección, y varias regresiones reales estaban del lado nuevo.

El detalle completo de la auditoría está en
`docs/ERETZ_CODEX_TO_CLAUDE_HANDOFF.md` (396 líneas), `docs/ERETZ_UNIFICATION_EVIDENCE.md`
y `docs/ERETZ_UNIFICATION_PLAN.md`. **No repetir esa auditoría.**

---

## 3. QUÉ YA SE HIZO

### 3.1 Auditoría y unificación (Codex, hasta `b36d8462df`)

Inventario de 39 refs, 9 worktrees, ~3040 archivos, 12 heads remotos obtenidos
sin prune. Veredicto: **no está demostrado que GitHub sea globalmente
superior**; sí hubo capacidad histórica de detección de URLs de ficha
perdida o reducida en ciertas familias. Estrategia elegida: candidata sobre la
base local moderna, incorporando F7 (frontend) y API v2 desde sus ramas, y
recuperando capacidades históricas sólo en las fronteras compartidas.

Regresiones demostradas y corregidas, resumidas: URLs de ficha de familias
históricas; SQL del mapa combinado; NULL convertido en cero y bool en count;
campos perdidos por el allowlist del INSERT RPC; lookup REST parcial que podía
pasar por propiedad nueva; imágenes compartidas descartadas sin prueba de que
fueran assets; publicación de snapshots incompletos o concurrentes; archivos
corruptos escondidos detrás de un run válido; lifecycle que dejaba el streak
de ausencia en 1; GeoRef que cortaba páginas cortas y silenciaba errores de
dump; backfill que podía estampar la huella actual sobre un run viejo; y el
reporte que llamaba «certified» a primeros intentos `NEEDS_FIX`.

Hay un detalle de método que conviene no perder: los hashes distintos de los
manifiestos GeoRef **no eran corrupción**. La causa probada fue CRLF —se
calculaba el hash en LF y después `write_text` escribía CRLF en Windows—. No
volver a atribuirlo a corrupción.

### 3.2 Registro de fuentes y control plane (esta sesión, hasta `d9238e64be`)

29 commits sobre identidad de fuente, triage de defectos y observabilidad, todos
en el plano de control (ninguno toca archivos con huella). Los que importan:

**La precedencia de la fuente.** `resolve_identity` resuelve así:
`platform.domain` → `source.official_url` → `resolution.official_domain` →
`verificada.official_url` → `directory.official_url`. **2.327 de 2.330**
agencias tienen entrada en el directorio de plataformas, así que la capa 1 gana
casi siempre. Cinco correcciones de fuente que se habían dado por aplicadas
editando la capa 2 **no hacían nada**; la verificación no lo detectó porque
buscó el directorio con un glob y encontró otro archivo. La lección quedó
escrita en `scripts/corregir_capa_que_manda.py`: **verificar el artefacto no es
verificar el efecto**. Lo que hay que comprobar no es que el archivo quedó
escrito, sino que la certificación siguiente usa la URL nueva.

**Enlazar a un catálogo no es ser uno.** `fios` se recertificó contra la raíz
propuesta y siguió enumerando cero: la raíz declara «0 Propiedades» y
`/propiedades` declara 266. Ahora se visitan las candidatas y se propone la que
declara inventario, eligiendo la que más declara y no la primera del menú
(`yacopino` enlaza `/emprendimientos`, que declara 0, antes que su catálogo de
venta, que declara 85).

**Un rastro es historia, no una lista de estados deseados.** Al revertir una
propuesta mala, el corrector **la volvió a aplicar**, porque leía el rastro de
auditoría como si fuera un estado deseado. Se agregó `retirada: true`, que
cancela lo pendiente sin borrar la fila vieja.

**El resultado medible:** `emir elhelou` pasó de `NEEDS_FIX` con 0 enumeradas
contra un perfil de `agroads.com.ar` a `CERTIFIED_COMPLETE` con 23 propiedades
desde su dominio, precio y moneda al 100 %, dos corridas idempotentes.

Otras correcciones del bloque, cada una con su test que muerde: el `%20` de una
URL de WhatsApp leído como contador de propiedades; la regla de geografía que
marcaba 135 de 244 porque se apoyaba en un campo que se rechaza el 0 % de las
veces; la regla de páginas institucionales que daba 26 falsos positivos por
buscar la palabra sin exigir el segmento completo; las horas de cola parada
infladas un 30 % por sumar intervalos solapados (106,3 h de suma contra
**74,2 h de reloj**); el costo de tocar `shared/*` calculado con la mediana
cuando correspondía la suma (9,5 h contra **23,9 h** reales con 2 workers); y
la ETA única reemplazada por un rango, porque el caudal varía 2,5 veces según
la ventana que se mire.

### 3.3 Corregido en este handoff

**Cuatro tests que medían el almanaque.** La suite completa sobre la rama de
handoff dio **4 failed / 2629 passed**. Los cuatro estaban en
`tests/test_fuente_cambiada_invalida.py`, escritos por mí el 2026-09-17 con
fechas fijas del 2026-09-16. No era una regresión de código: `diferida_vigente`
mide el TTL —72 h, 24 h si la firma es crítica— contra `checked_at` usando
`time.time()`. Al 2026-09-20 esas fechas fijas ya habían envejecido más allá
del TTL y las cuatro afirmaciones positivas cayeron.

Es el mismo defecto que este proyecto ya había corregido *en el código* —anclar
el TTL en la firma en vez de en la última mirada— reapareciendo *en los tests*.
Un test que aprueba el martes y reprueba el jueves sin que nadie toque nada no
está midiendo el código.

Arreglado con fechas relativas al reloj, y —lo que importa— se agregó
`test_MUERDE_una_diferida_vencida_no_mantiene_vigente_el_resultado`: mientras
las fechas fijas estuvieron en verde, **nadie estaba comprobando que el TTL
venciera de verdad**. Verificado que muerde: subiendo `TTL_DIFERIDA_HORAS` de
72 a 87.600 el test se pone en rojo.

---

## 4. RESULTADOS DEMOSTRADOS

### Medido en esta sesión, sobre esta rama

| Qué | Resultado |
|---|---|
| Suite backend completa, sobre el árbol de esta rama | **2634 passed**, 0 failed, 125,90 s |
| Suite backend, antes de corregir los tests | 4 failed, **2629 passed**, 186,67 s |
| Censo de certificación (último resultado por agencia) | 429 agencias con resultado |
| — `CERTIFIED_COMPLETE` | 157 |
| — `IDENTITY_PENDING` | 140 |
| — `NEEDS_FIX` | 93 |
| — `BLOCKED_EXTERNAL` | 27 |
| — `CERTIFIED_BEST_AVAILABLE` | 11 |
| — `NO_INVENTORY_CONFIRMED` | 1 |
| Propiedades enumeradas | **27.233** |
| Universo declarado | 6.597 agencias; cola actual de 767 |

### Heredado de Codex — NO re-medido acá, y por qué

Estas cifras son del HEAD funcional `7dd838fa63`. Entre ese commit y esta rama
**no cambió código funcional**: lo único que se agregó fueron documentos y una
corrección de tests. Se citan como heredadas, con su fecha, no como medidas hoy.

- Suite backend en `7dd838fa63`: **2633 PASS**, 0 failures, 0 errors, 0 skipped,
  156,764 s según el XML.
- **17 checks PGlite PASS** sobre la migración SQL real, con CHECK/FK/tipos,
  NULL/zero/security/rollback. **No ejecutados contra Supabase alojado.**
- Frontend: **1235 PASS, 9 SKIP**; typecheck, lint (0 errores, 3 warnings) y
  build PASS; Next 16.3.5, 20 páginas; 9 smokes de integración contra API y
  snapshot local. **No es validación de staging ni de browser.**
- Replay Bottega congelado (5 HTML cacheados, sin red): campos histórico 0/15,
  pre-local 8/15, **candidato 15/15**; URLs 8/9, 6/9, **9/9**. Es una muestra
  chica de extractores, **no** una recuperación global ni las 413 fuentes.
- API: 14 casos × 5 repeticiones PASS. Latencia local combinada ~877–1209 ms
  mediana; mapa ~1100–1227 ms; detail ~10 ms; batch100 ~37–41 ms.
- Datos raw 189.159 filas / 1.724 agencias; snapshot API original 58.427,
  candidato derivado 57.665 (762 de fuentes ajenas omitidas).
- Supabase público observado: 257.073 propiedades, 3.187 agencias con
  propiedades, 7.004 en `inmobiliarias_main`. **0 igualdad de PK** entre esos
  IDs y `scraping_id_origen` / `staging_id_origen`.

### Lo que NO está medido y no hay que afirmar

Browser QA, Preview y staging **siguen sin prueba**. Dos intentos de levantar
devserver para QA de browser fueron rechazados; no esquivar el rechazo por otra
ruta. No hay cohorte multifamilia fresca: el último control vivo (Benitez, 12
propiedades, 2 runs idempotentes, 58 requests, 160,6 s) es **STALE** respecto
del schema 5 actual, y no se debe «actualizar» su huella para que pase.

---

## 5. QUÉ QUEDA PENDIENTE

Ordenado por lo que bloquea más.

### P1 — `fios`: el catálogo publica 266 y enumeramos 0

- **Componente:** conector `generico`, enumeración.
- **Problema:** al corregir la fuente de `fios` hacia su catálogo real, la cola
  paró con radio **FAMILIA**: *«el sitio publica catálogo y no lo pudimos
  enumerar: contador publicado: 266 propiedades»*.
- **Estado:** la cola está **detenida** por este paro. 0 workers vivos. El paro
  es correcto y la señal es nueva: antes la fuente apuntaba a una sola ficha y
  el problema era invisible.
- **Siguiente acción:** bajar `https://www.fios.com.ar/propiedades` y ver cómo
  pagina; es un `listado.php` con ~35 rutas enlazadas desde el catálogo.
  Decidir si es variante de paginación no soportada (plano de datos → ventana
  semántica) o ruta mal derivada (plano de control → se puede ahora).
- **Riesgo:** es radio FAMILIA. Si es la paginación, afecta a toda la familia,
  no sólo a `fios`.
- **Test/replay:** `tests/test_fuente_es_una_ficha.py`;
  `scripts/fuente_es_una_ficha.py --agencia fios`.
- **NO** diferirlo sin mirarlo. Una diferida sin diagnóstico es exactamente lo
  que el TTL vino a impedir.

### P2 — El corte por lote no tiene memoria

- **Componente:** `scripts/defect_triage.py :: debe_cortar_por_lote`, plano de
  control, sin huella.
- **Problema, medido:** hubo **13 cortes por lote**. Los tres últimos del worker
  1 pararon en **la misma agencia** (`gomez servicios inmobiliarios`) con **el
  mismo conjunto de cinco defectos** —fernanda aciuolo, fios, forchino, gentina,
  gianini—. La cola se relanza, recorre el mismo tramo, reacumula los mismos
  cinco y vuelve a cortar. Cada corte cuesta un paro completo más un relanzamiento
  a mano.
- **Por qué pasa:** el corte junta defectos para diagnosticarlos de a tanda,
  pero **no registra qué tanda ya provocó un corte**. Un defecto ya presente en
  `AGENCY_DEFECT_QUEUE.jsonl` de una pasada anterior vuelve a contar como si
  fuera nuevo. Es, otra vez, leer un registro histórico como si fuera una lista
  de pendientes.
- **Escala del ruido:** `variante_no_soportada` tiene **405 filas** en la cola de
  defectos que corresponden a **32 agencias distintas** —342 filas de 27
  agencias en `generico/generic/no_inventory`—. Unas 12,7 filas por agencia.
- **Siguiente acción propuesta (no implementada):** que el umbral de cinco
  cuente sólo defectos **nuevos desde el último corte**, conservando el
  registro completo para el radio, el ranking y los reportes. Escribir primero
  el test que muerda: cinco defectos ya vistos **no** deben cortar; cinco
  nuevos, sí.
- **Riesgo si se hace mal:** que no se corte nunca. El corte existe para
  interrumpir una vez, no cero.

### P3 — NEXT-001, el ledger de certificación (heredado de Codex, sin avance)

**No hay patch ni commit de solución.** La pregunta viva: ¿puede una fila
corrupta o un mismo instante hacer que se reutilice un cierre viejo?

Confirmado por implementación: `agency_certifier.py :: read_jsonl` saltea el
`ValueError` de JSON inválido y acepta cualquier JSON, no sólo objetos; y tanto
`run_agency_certification_queue.py :: latest_results` como
`backfill_strategy_fingerprints.py :: latest_results` toman **el último append
por agencia, sin ordenar ni comparar `checked_at`**. Consecuencia candidata: un
`NEEDS_FIX` reciente pero roto queda salteado y el cierre viejo permanece
elegido. **No demostrado todavía con replay controlado.** Hay 35 grupos
agencia+`checked_at` repetidos en 2.501 filas, sin determinar si son idénticos,
refresh de métricas o evidencia conflictiva.

Paso exacto: replay offline con ledger válido → fila inválida reciente, mismo
instante conflictivo, offsets equivalentes y append fuera de orden. Examinar
los 35 grupos sólo por agregados. No elegir arbitrariamente un COMPLETE entre
dos evidencias distintas. No modificar todos los llamadores tolerantes de
`read_jsonl` sin matriz de consumidores.

### P4 — Fuentes sin catálogo identificado

`barnes` y `demarco` siguen apuntando a una ficha. Se decidió **no proponer
nada** antes que proponer la raíz: ninguna candidata declara inventario, y
convertir un error visible —enumera cero— en uno silencioso es peor. Century
21: 11 oficinas apuntan a una sola propiedad y las páginas de oficina sirven
42 KB sin un solo enlace a ficha en HTML plano. Registrado, no accionado.

### P5 — Ventana semántica, cerrada durante el bulk

Acumulado en `ERETZ_VENTANA_SEMANTICA_ORDEN.md`. El caso mejor entendido es
`ambientes`, que son **dos sub-casos opuestos** y no uno: `bottega` publica
«Ambientes 5» y no lo extraemos —hay que arreglar el extractor—; `bartolelli
maini` no lo publica y la palabra aparece sólo en el menú —28 de 29 «provistos»
no existían y la señal tiene que dejar de disparar—. Anclar a un valor
etiquetado con límite de palabra resuelve los dos. Tocar `shared/*` cuesta
**23,9 h** con 2 workers; está medido, no estimado.

### P6 — Los demás abiertos de Codex

Writer equivalence (el REST sigue en uso; no ampliar el allowlist ni retirar el
REST antes de equivalencia probada); identidad pública (el crosswalk URL
numérica ↔ hash está vacío; **no inventar aliases**); el fingerprint schema 5 no
captura la versión del INPUT GeoRef realmente usado; GeoRef no tiene promoción
multiarchivo atómica contra kill o disk failure; lifecycle sin continuidad de
fuente ni proveniencia; refresh de éxitos por antigüedad sin cambio de código o
fuente; métricas faltantes que todavía pueden caer en cero por default;
`validate_live_agency_identity.py` con `name_exact` marcado VALIDATED aunque
`domain_match` sea false —**detectado por lectura, no corregido**—.

---

## 6. PROBLEMAS ABIERTOS CONOCIDOS — medidos hoy, no asumidos

- **Andrade**: sigue abierto. Emite `variante_no_soportada` con firma
  `ef05c0690dea`, la firma que agrupa cinco causas distintas —una SPA de React,
  jQuery contra la API de SOM, un 200 con cuerpo vacío, una forma de URL
  desconocida y un `/buscador`— y que por eso **ya no dispara la regla de firma
  repetida**. Provocó dos cortes por lote por esa regla antes de la excepción.
- **`fios`**: ver P1. Es el paro activo.
- **`barnes`, `demarco`**: ver P4.
- Los 27 `BLOCKED_EXTERNAL` y los 140 `IDENTITY_PENDING` están frenados **antes**
  del scraping: certificar más rápido no los mueve, y por eso su ETA es
  `SIN_ETA` con motivo y no una fecha.

---

## 7. ARCHIVOS Y CAMBIOS IMPORTANTES

### De la unificación

`scripts/agency_certifier.py`, `agency_fingerprints.py`,
`run_agency_certification_queue.py`, `backfill_strategy_fingerprints.py`,
`property_freshest.py`, `property_observations.py`, `geo_reference.py`,
`geo_snapshot.py`, `geo_snapshot_diff.py`; `scraper/safe_merge.py`,
`clients.py`, `models.py`, `detail_urls.py`; `scripts/publish_to_supabase.py`,
`run_daily_pipeline.py`, `run_manifest.py`;
`migrations/property_safe_merge_audit.sql` y su rollback —**iteración local, no
aplicada**—.

### Del registro de fuentes (esta sesión)

`scripts/corregir_capa_que_manda.py` (aplica en la capa que gana y **verifica el
efecto**), `fuente_es_una_ficha.py`, `ya_lo_vimos.py`,
`firma_navegacion_javascript.py`, `gates_independientes.py`,
`propiedades_que_no_son_fichas.py`, `tiempo_perdido_por_causa.py`,
`presupuesto_de_riesgo.py`, `operacion_reporte.py`, `banco_de_incidentes.py`,
`canarios_por_familia.py`, `colision_de_ids_estables.py`,
`indice_de_propiedades.py`, `canario_source_switch.py`, `alerta_remota.py`.

### Cuarentena

`docs/handoff/herramientas-no-versionadas-2026-09-20/` — 39 archivos que **no
existían en ningún commit de ningún branch** y vivían sin versionar en
`Inmo-Capital-main`. Leer su `README.md` antes de tocarlos: no fueron
revisados ni ejecutados, y varios escriben en producción.

---

## 8. DECISIONES ARQUITECTÓNICAS

**Fuente de verdad.** La base local moderna, no GitHub. El main remoto es un
ancestro, no una alternativa. Las capacidades históricas se recuperan **por
familia y con evidencia**, no adoptando el árbol viejo.

**Descartado.** Un segundo scraper histórico: el descubrimiento de URLs de
ficha es uno solo, `scraper/detail_urls.py`. Tampoco un segundo autocomplete ni
otra fidelity layer. `run_faceted_scraping.py` queda en cuarentena, no
adoptado: duplica discovery y tiene paginación inventada.

**Integrado.** F7 (frontend) y API v2 desde sus ramas, preservando historia con
dos merges locales. DTO/schema/adapter/domain en la API; el frontend no consume
JSON arbitrario.

**Recuperado del histórico.** La detección de URLs de ficha en las familias
donde se había perdido, con controles positivos y negativos de portales y
editoriales.

**Rechazado del histórico por inseguro.** Cualquier ruta que ampliara
privilegios públicos, que tratara un portal ajeno como fuente de inventario, o
que borrara el REST antes de probar equivalencia de escritores.

**Dos principios que se ganaron caros en esta sesión**, y que conviene aplicar
antes de dar algo por hecho:

1. **Verificar el artefacto no es verificar el efecto.** Cinco correcciones
   quedaron inertes por comprobar que un archivo estaba escrito en vez de
   comprobar que la cola resolvía distinto.
2. **Un rastro de auditoría es historia, no una lista de estados deseados.**
   Salió mal dos veces en dos lugares distintos —el corrector de fuentes y el
   corte por lote—. Si algo lee un registro de eventos para decidir qué hacer
   ahora, es candidato al mismo error.

---

## 9. RESTRICCIONES VIGENTES

- **ERETZ Propiedades** es el nombre actual.
- **Mobile congelado.** No hay trabajo de frontend en curso.
- **Zonaprop y Argenprop no son fuentes de inventario.** El inventario alojado
  contiene 2 URLs de Zonaprop y 24 de Argenprop: son un agregado de control, no
  una autorización. No se ingirieron ni se limpiaron.
- **Máximo 2 workers pesados.**
- **Las propiedades reales incompletas sobreviven** en raw, staging, API y
  presentación. NULL no es cero y un bool no es un count.
- **No hay `COMPLETE` falso.** La certificación separa inventario y determinismo
  de la verdad de los campos y la geografía.
- **No inventar geografía.** Un conflicto geográfico retiene la propiedad y evita
  afirmar coordenadas; no la elimina.
- **No perder identidad, no mezclar agencias.**
- Sin autorización explícita del usuario: no producción, no escrituras en
  Supabase, no migraciones productivas, no deploy, no DNS, no publicación,
  no merge a main, no force push, no borrado de ramas, no rotación de secretos,
  no servicio pago.

---

## 10. ESTADO DE PRODUCCIÓN / SUPABASE

**Preparado y NO ejecutado:**

- `migrations/property_safe_merge_audit.sql` y su rollback. Iteración local.
  **No aplicada.** Validada con 17 checks en PGlite desechable, no contra el
  proyecto alojado.
- Planes escritos: `ERETZ_SUPABASE_WRITE_PLAN.md`,
  `ERETZ_SUPABASE_ROLLBACK_PLAN.md`, `ERETZ_SUPABASE_PRODUCTION_AUDIT.md`
  —los tres en la cuarentena de §7, nunca versionados antes—, más
  `ERETZ_SUPABASE_READINESS.md` y `ERETZ_PROMOCION_STAGING_A_MAIN.md`,
  que entraron con el merge de `release`.

**Qué se hizo contra Supabase:** sólo metadata y `SELECT` agregados. Proyecto
`pggrvzyixyjkhfknpurg` (inmolink), PG 17.6.1.084. **No** se llamó ningún RPC,
**no** se aplicó SQL ni migración, **no** hubo INSERT ni ROLLBACK, **no** hubo
escritura productiva. No se leyeron `.env` ni credenciales.

**Bloqueado esperando decisión del usuario**, sin avance posible sin ella:
el puerto de heartbeat (necesita migración, rol y escrituras en Supabase);
`pg_dump` y restore (necesita credencial); los grants de `anon`; y el mecanismo
de relanzamiento de la cola.

**No se imprimió ningún secreto en esta sesión.**

---

## 11. NEXT ACTION

Operativo, en este orden:

```bash
git config --global --add safe.directory 'D:/INMO CAPITAL/eretz-unified'
cd "D:/INMO CAPITAL/eretz-unified"
git fetch origin
git checkout handoff/codex-unificacion-2026-09-18
git status                      # debe estar limpio
"C:/Users/Nicolas Wulfsohn/AppData/Local/Programs/Python/Python314/python.exe" \
  -m pytest tests -q -p no:cacheprovider
```

Con la suite en verde, **empezar por P1**, que es lo único que tiene la cola
detenida:

```bash
python scripts/fuente_es_una_ficha.py --agencia "fios consultoria inmobiliaria"
```

Bajar `https://www.fios.com.ar/propiedades`, ver cómo pagina el `listado.php`, y
decidir si el arreglo es de plano de control —ruta mal derivada, se puede
ahora— o de plano de datos —variante de paginación, va a la ventana
semántica—. Recién con eso resuelto, o diferido **con diagnóstico escrito y
firmado**, relanzar la cola con 2 workers.

Después P2, que es barato y devuelve horas de reloj. Después P3 (NEXT-001), que
es el pendiente profundo.

**No repetir** la auditoría GitHub/local, ni las suites completas mientras no
cambie código funcional, ni el benchmark de Bottega, ni la inspección de
CHECK/tipos/PK de Supabase. Está todo en `docs/ERETZ_CODEX_TO_CLAUDE_HANDOFF.md`,
sección «DO NOT REDO».

---

## 12. PLAN FINAL PENDIENTE

La misión original **no está terminada**. Falta, para poder emitir el informe
definitivo «histórico vs local vs unificado» con plan hacia beta, producción y
cobertura nacional:

1. **Cerrar NEXT-001** (P3). Es el único pendiente que toca la confiabilidad
   del ledger, y sin él cualquier afirmación sobre qué está certificado tiene
   una duda estructural encima.
2. **Una cohorte multifamilia fresca** contra el schema 5 actual. Hoy el único
   control vivo es STALE. Sin cohorte no hay comparación histórico/local/unificado
   defendible más allá de los 5 HTML de Bottega.
3. **Equivalencia de escritores** (P6): sin ella no se puede retirar el REST ni
   declarar una única ruta de escritura, y eso bloquea el plan de producción.
4. **Browser QA / staging / Preview**, que hoy no tienen ninguna prueba. No se
   puede declarar beta sin esto.
5. **Cobertura nacional**: 4.267 de las 6.597 agencias **no tienen entrada en el
   registro de fuentes**. No esperan caudal de scraping —esperan descubrimiento
   de fuente, que es otro proceso y hoy no está corriendo—. Por eso su ETA es
   `SIN_ETA` y no una fecha: dividirlas por «agencias certificadas/hora» produce
   un número que además *mejora* cuando mejora un caudal que no las toca.

El bulk actual —la única población con un proceso corriendo y midiéndose—
recibe un **rango** y no una fecha, porque el caudal varía 2,5 veces según la
ventana: 2,83 nuevas/h en 6 h contra 1,06 en 48 h. El ancho de ese rango es,
literalmente, lo que vale atender la cola cuando para.

---

## VERIFICACIÓN DEL CHECKPOINT

Comprobado antes de dar el handoff por cerrado:

- **Suite**: `pytest tests -q` sobre el árbol exacto de esta rama →
  **2634 passed, 0 failed**, 125,90 s. El número subió de 2633 a 2634 porque se
  agregó un test; los 4 que fallaban eran del almanaque y están corregidos.
- **El repo versionado reproduce la candidata**: `git status` limpio; el árbol
  contiene `b36d8462df` entero y la suite corre sin nada de fuera del repo.
- **No se depende de otro worktree — probado, no argumentado**: se creó un
  bundle de respaldo, se clonó en un directorio temporal fuera de los nueve
  worktrees, y la suite corrió ahí: **2634 passed en 126,64 s**. Un clon limpio
  que pasa entero es la prueba de que ningún import ni ningún path apunta
  afuera del repo. Los scripts que sí necesitan las rutas de la cola las llevan
  escritas y declaradas, no descubiertas con un glob —precisamente el error que
  dejó cinco correcciones inertes—.
- **Bundle de respaldo**: `D:\INMO CAPITAL\ERETZ_HANDOFF_2026-09-20.bundle`,
  5.067.740 bytes, con `handoff/codex-unificacion-2026-09-18` y `main`.
  `git bundle verify` → «records a complete history». El clon reprodujo
  `b857ce6129`, 941 archivos, 860 commits. Sin secretos ni artefactos externos:
  contiene sólo lo versionado.
- **Sin secretos**: escaneo de los archivos versionados y de los 39 de
  cuarentena buscando JWT `eyJ`, tokens `sbp_`, cadenas de conexión con
  contraseña y asignaciones literales a `api_key`/`service_role`/`password`/
  `token`. Lo único que aparece son referencias a `os.environ` y dos plantillas
  `.env.example` / `frontend/.env.local.example` con placeholders.
- **El archivo versionado más grande** es `scraper/scraper_propiedades.py`, con
  0,81 MB. No hay bases, ni dumps, ni checkpoints de workers.
- **`main` no fue modificado**, ni el local ni el remoto.
- **Cero escrituras productivas.** `database_writes: 0` en toda la sesión.

### Artefactos locales necesarios que NO están en GitHub

| Qué | Dónde | Tamaño | Cómo se regenera | Por qué no se versiona |
|---|---|---|---|---|
| Resultados de certificación | `D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827` | 665 MB, 3.021 archivos | Se reconstruye corriendo la cola; el JSONL es el registro y el SQLite su índice | Salida de corrida, crece por append, incluye payloads |
| Datos de agencias | `D:\INMO CAPITAL\ERETZ_AGENCY_DATA` | 140 MB, 101 archivos | Descubrimiento + reconciliación | Datos derivados |
| Reconciliación v2 | `D:\INMO CAPITAL\ERETZ_SUPABASE_RECONCILIATION_V2_20260827` | 2,5 GB, 26 archivos | Export desde Supabase | Volcado productivo |
| Directorio de plataformas | `D:\INMO CAPITAL\agency_platform_directory.jsonl` | 2.596 líneas | Descubrimiento; **es la capa que gana en `resolve_identity`** | Derivado, y se corrige en caliente |
| `_scratch` de la unificación | `D:\INMO CAPITAL\eretz-unified\_scratch` | 3,7 GB, 4.530 archivos | Replays, XML, snapshots, wheels | Gigante; ignorado a propósito. **No borrar** |
| `DATA_QUALITY` | `D:\INMO CAPITAL\Inmo-Capital-main\DATA_QUALITY` | 436 MB, 35 CSV | Consulta de calidad contra la base | Exportación de datos productivos |
| Scratch de sesiones | `Inmo-Capital-main\_*.py`, `_*.json`, `_batch*` | ~63 archivos | No se regenera; son salidas de un momento | Ruido, no herramientas |

Ninguno de estos hace falta para reproducir la candidata: el árbol versionado
es autosuficiente para la suite. Hacen falta para **operar** la cola.
