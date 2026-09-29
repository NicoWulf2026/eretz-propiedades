# ERETZ PROPIEDADES — CLOUD CONTINUATION HANDOFF

Checkpoint: **2026-09-29 17:15 (-03)**. Documento canónico para continuar sin la conversación
que lo produjo. Si algo acá contradice a `docs/agent/*`, manda el más nuevo por fecha; este es
el más nuevo a la fecha del checkpoint.

## REPOSITORY
- remote: `https://github.com/NicoWulf2026/eretz-propiedades.git` — **PÚBLICO** (la API de GitHub
  responde sin autenticación). Nunca subir datos scrapeados, ledger, snapshots ni secretos.
- branch de trabajo: `handoff/codex-unificacion-2026-09-18` (nunca `main` sin P24).
- HEAD del checkpoint: ver `git rev-parse HEAD` y el tag `cloud-checkpoint-2026-09-29`
  (el tag apunta al commit que agrega este documento).
- worktree local original: `D:\INMO CAPITAL\eretz-unified` (Windows). `eretz-dev` es una copia
  de trabajo para preparar lotes sin tocar la cola; no es fuente de verdad.

## MISSION
ERETZ Propiedades: buscador de inmuebles de Argentina que lee **solo las webs oficiales** de las
inmobiliarias (nunca portales), certifica cada inventario (dos corridas, idempotencia,
completitud), y sirve un catálogo limpio por una API v2 (FastAPI + SQLite) a un frontend Next.js
en Vercel. Objetivo actual, en dos tracks paralelos que no se bloquean entre sí:
1. **BETA CLOSED → PRODUCTION READY** (criterios exactos en P16).
2. **Cobertura nacional**: certificar las ~1.800 agencias con identidad lista y seguir.

## NON-NEGOTIABLE RULES
Las reglas del repo están en `CLAUDE.md`, `.claude/rules/*.md` y, sobre todo,
**`docs/agent/POLITICAS_PERMANENTES.md` (P1–P24, decididas por el usuario el 29-09)**. Resumen de
lo que no se negocia:
- Cero writes productivos automáticos (Supabase INSERT/UPDATE/DELETE, migraciones, RLS/grants,
  restore, deploy público, DNS) salvo las clases que P19 preautoriza DESPUÉS de backup+restore
  probados (hoy no hay backup: nada preautorizado).
- La snapshot LOCAL se reemplaza solo con `scripts/desplegar_snapshot.py --automatico` y solo si
  pasan todas las compuertas P2.
- Sin force push, sin reescribir historia, sin `reset --hard`, sin `clean` destructivo.
- Nunca imprimir ni commitear secretos. Credencial faltante → `BLOCKED_EXTERNAL_CREDENTIAL`.
- Portales nunca son fuente. Identidad ambigua → no atribuir. Fail-closed: nunca un COMPLETE falso.
- Exterior: se preserva, no se publica (ARGENTINA_ONLY). CABA solo por polígono oficial IGN.
- No se evaden 403/429 ni robots.txt (P11). Tokko: un solo backend con límite compartido — nunca
  paralelizar pedidos a Tokko (la cola ya pone todo Tokko en el worker 0).
- Máximo 3 workers (P5), hoy régimen 2. Mobile congelado.
- Reportar por fase y SEGUIR: reportar no es detenerse.

## CURRENT ARCHITECTURE
- `connectors/` — extractores por familia: `generico` (HTML/sitemap/APIs propias del sitio),
  `tokko`, `wordpress` (REST + generico), `wasi`, `century21`; `base.py` (descargador, robots,
  hash de identidad, geografía, coherencia), `geografia.py` (GeoRef/IGN), `pais.py`/`exterior.py`.
- `scripts/agency_certifier.py` — certifica UNA agencia (dos corridas, señales de fuente,
  field_coverage, estado). `scripts/run_agency_certification_queue.py` — la cola (workers
  particionados: Tokko al 0, el resto por host). `scripts/relanzar_la_cola.py` + tareas de
  Windows `ERETZ_relanzador` / `ERETZ_vigilante_paros` — relanzan y vigilan.
- Huella (`scripts/agency_fingerprints.py::archivos_de_la_huella`): cambiar un archivo compartido
  invalida todas las certificaciones; un conector, su familia. Se agrupan en lotes (P4).
- `scripts/api_snapshot.py` — construye la snapshot SQLite de la API desde la preingestión
  congelada del 03-09 + paquetes certificados vigentes (`snapshot_certificadas.py`) + cobertura
  geo recalculada sobre la fila fresca + retiros verificados (`verificar_retiros.py`).
- `api/` — FastAPI (`api/main.py`, router v2 en `api/v2.py`), lee `ERETZ_API_SNAPSHOT`.
- `frontend/` — Next.js (web). Supabase = base productiva (solo lectura por decisión).

## CURRENT DATA FLOW
web oficial → conector → `agency_certifier` (2 corridas) → paquete en
`ERETZ_AGENCY_CERTIFICATION_20260827/agencies/<id>/` + fila en el ledger
`AGENCY_CERTIFICATION_RESULTS.jsonl` → (`ledger_de_certificacion.vigentes_por_agencia` elige el
cierre vigente) → `api_snapshot.py` (preingestión 03-09 + certificadas vigentes + geo + retiros)
→ candidata en `_scratch/unification/snapshot_*` → compuertas P2 → snapshot servida
`D:\INMO CAPITAL\ERETZ_API_CONTRACT\ERETZ_API_SNAPSHOT.sqlite3` → API v2 → frontend.
Supabase no se escribe (solo lectura) hasta cumplir P17/P19.

## CURRENT QUEUE STATE (17:10)
- workers: **2** (régimen `ERETZ_WORKERS.json`; la prueba de 3 se cortó por bloqueos del backend
  Tokko; ahora todo Tokko va al worker 0 — reprobar 3 es trabajo pendiente).
- scheduler: tareas de Windows `ERETZ_relanzador` (10 min) y `ERETZ_vigilante_paros` (5 min);
  interruptor `ERETZ_AUTOMATION_ON.cmd` / `OFF.cmd`. **No portables**: en otra máquina hay que
  lanzar la cola a mano (ver CLOUD_BOOTSTRAP).
- familias detenidas: se liberan con diferida firmada (`AGENCY_DEFECTS_DIFERIDOS.jsonl`) o cambio
  de huella; al checkpoint, la última pasada del relanzador las había liberado.
- ledger vigente (766 agencias con resultado): CERTIFIED_COMPLETE 338 · CERTIFIED_BEST_AVAILABLE 40
  · NEEDS_FIX 204 · IDENTITY_PENDING 132 · BLOCKED_EXTERNAL 51 · NO_INVENTORY_CONFIRMED 1.
- cola `--ready`: **1.819 agencias** con identidad lista (768 con FK de main + 1.051 por identidad
  canónica verificada, P6). La mayoría de las canónicas todavía no se certificó.
- ritmo medido: ~8 agencias por hora activa con 2 workers → una pasada completa ~230 h.
- huella compartida al checkpoint: `sha256_12 = 8bf7f9274ed4` (digest de los archivos de
  `archivos_de_la_huella()` en el HEAD del checkpoint; lotes 1, 2 y 3 aplicados).

## CURRENT SNAPSHOT STATE
| snapshot | estado | contenido |
|---|---|---|
| **v4l-c** | **SERVIDA** desde 2026-09-29 16:52 (despliegue automático P2, registro `ERETZ_API_CONTRACT/_despliegues/DEPLOY_2026-09-29T16-52-05.json`) | 65.028 propiedades, 603 agencias; +9.929 de inventarios certificados vigentes; −2.366 retiros con muerte verificada (P1), −168 exterior, −46 páginas de categoría, −762 web ajena; localidades 18.428; 0 exterior, 0 precios simbólicos, QA 14/14; sha256 `482de3ac0081…` |
| v4j | anterior servida; respaldo en `ERETZ_API_CONTRACT/_anteriores/v4j_2026-09-28/` | 57.634 |
| v4k | superada, nunca desplegada | v4j − 121 exterior |
| v4l-a / v4l-b | superadas, nunca desplegadas | la b retiraba por ausencia sin verificar: rechazado por P1 |
Política de retiros (P1): REMOVED solo con 404/410, 301/308 fuera de la ficha o soft-404
demostrado (portada o raíz del catálogo sin rastro del aviso); una ficha viva no se retira;
3 ausencias confiables según `ERETZ_PROPERTY_LIFECYCLE.md`. Evidencia en
`_scratch/unification/retiros_2026-09-29/RETIROS_VERIFICADOS.jsonl` (2.370 REMOVED, 189 VIVA,
47 AMBIGUA, 50 NO_VERIFICABLE, 3 ROBOTS_BLOCKED).

## SEMANTIC WINDOW
- Ventana semántica original (15–24-09): cerrada formalmente
  (`ERETZ_SEMANTIC_WINDOW_PLAN.md`). NEXT-001 (ledger vigente por `checked_at`) cerrado
  (`9b31b53f5e`, doc en `docs/ERETZ_CODEX_TO_CLAUDE_HANDOFF.md`).
- Lotes compartidos 29-09 (`docs/agent/lotes/README.md`): **1, 2 y 3 APLICADOS** (`a6746a9338`,
  `566d5a2644`, `c4092f1238`). Cada uno reinició la recertificación por huella; la cola va de la
  más vieja a la más nueva, así que el costo real es rehacer lo recertificado desde el último lote.
- Acumulando para el lote 4: conteos en palabras («cuatro dormitorios»), superficie sin rótulo
  (fenix), Wix (lucas liprandi, dib kai), Strapi en `api.` subdominio (paladino).

## GLOBAL DECISIONS
Texto completo y vinculante: **`docs/agent/POLITICAS_PERMANENTES.md`**. Índice:
P1 retiros con muerte demostrada · P2 auto-deploy de la snapshot LOCAL con compuertas · P3 lote
aplicado · P4 lotes de huella por beneficio/costo · P5 workers adaptativos hasta 3 · P6 certificar
≠ promover ≠ publicar; identidad canónica verificada · P7 búsqueda paga ≤ USD 10/mes · P8
incompletas se publican · P9 título derivado de datos reales · P10 provincia contradictoria
normalizada con polígono, conservando lo publicado · P11 robots.txt · P12 bajas productivas post
backup · P13 no fusionar agencias · P14 beta privada sin abogado, lanzamiento público con
revisión · P15 agencia sí, agente no; fotos por referencia · P16 criterios BETA CLOSED /
PRODUCTION READY · P17 clientes PostgreSQL sí, no rotar contraseñas · P18 rol escritor preparado,
no creado · P19 clases estructurales tras backup · P20 promoción por lotes · P21 API beta ≤ USD
10/mes · P22 Vercel mínimo privilegio · P23 DNS/noindex · P24 merge a main solo si no dispara
producción.

## TEST STATUS
- última suite completa: **3.701 passed, 0 failed** (HEAD `c4092f1238`, Windows, Python 3.14.4).
- Regression Gate (`scripts/comparar_con_linea_base.py --linea-base
  _regresion/ANTES_DEL_LOTE_2026-09-24.jsonl --desde 2026-09-24T11:39:00`): 578 agencias,
  **0 pendientes** (17:0x).
- API QA (`scripts/benchmark_unified_api.py`): 14/14 sobre la v4l-c servida.
- Browser QA: último completo el 20-09 (`ERETZ_QA_BROWSER_2026-09-20.md`); pendiente sobre v4l-c.

## IMPORTANT COMMITS (29-09)
- `9b31b53f5e` NEXT-001: ledger vigente por checked_at.
- `178f3009fd` snapshot suma inventarios certificados vigentes (`snapshot_certificadas.py`).
- `38419477ff` geografía sobre la fila fresca (+3.816 localidades).
- `fb092e7dd9` políticas permanentes P1–P24.
- `a6746a9338` lote compartido 1 · `566d5a2644` lote 2 (P6) · `c4092f1238` lote 3 (robots, contenedoras).
- `cfdecb78d0` régimen adaptativo de workers · `99a9d41771` todo Tokko a un worker.
- `df1500caa3` / `46afc8fb8d` verificación de retiros (P1).
- `3bdb6e0a4f` compuertas del despliegue automático (P2).
- `b0f3fde0b5` Regression Gate: exterior y pie legal explicados por política.
- `60755edff4` P6 fase 2: verificar webs del directorio.
- `6ba533f3fc` / `8bcd5c834f` URLs de categoría y su contabilidad.

## OPEN WORK
**P0**
1. Preservar el estado operativo fuera del repo en almacenamiento PRIVADO (ver EXTERNAL
   BLOCKERS: el archivo ya está empaquetado y verificado localmente).
2. Mantener la cola sana (paros → diagnóstico → diferida firmada o arreglo; nunca esperar).
3. Reprobar 3 workers con el reparto Tokko→worker 0 (P5) y dejar el régimen más eficiente.
**P1**
4. Seguir el Regression Gate a 0 tras cada tanda; reconstruir y auto-desplegar la snapshot (P2)
   cuando las certificaciones nuevas lo justifiquen.
5. Browser QA local sobre v4l-c (frontend `next dev` + API local).
6. API beta remota (P21): preparar contenedor/runbook (Fly.io o Railway), marcar
   `EXTERNAL_ACCOUNT_REQUIRED`.
7. P18 rol escritor: SQL + rollback + test + runbook, sin crear.
8. P9 título derivado en el frontend web.
**P2**
9. Lote 4 (ver SEMANTIC WINDOW). P10 provincia contradictoria con polígono provincial (requiere
   polígonos IGN de provincias). P7 descubrimiento pago con guardrail de USD 10/mes (111 agencias
   sin web).
**LONG TAIL**
10. NEEDS_FIX restantes (muchos son cierres viejos que la pasada resuelve sola: mirar
    `checked_at` contra `git log` antes de re-diagnosticar); 47 retiros AMBIGUA; cobertura nacional.

## EXTERNAL BLOCKERS
Portabilidad del estado: resuelta en código (`ERETZ_DATA_ROOT`, `8c062b59de`, `0ddbd12af4`) y
probada (restore en otra raíz, 0 accesos a `D:\`). Falta SOLO el upload humano del paquete a
almacenamiento privado (ver `docs/agent/ESTADO_DURABLE.md`).
BLOCKED EXTERNAL:
- **Almacenamiento privado para el estado operativo** (el repo es público): el usuario tiene que
  elegir dónde subir `ERETZ_STATE_2026-09-29.tar.gz` (ver `docs/agent/ESTADO_DURABLE.md`).
- Credencial PostgreSQL válida (P17) → backup/restore. Tooling: autorizado instalar clientes
  PostgreSQL oficiales (aún no instalados).
- Cuenta/pago de hosting para la API beta (P21).
- Acceso Vercel de mínimo privilegio (P22) → QA de Preview sobre el SHA exacto.
- Revisión legal (P14) para lanzamiento público. Dominio final (P23).
WORK THAT CAN CONTINUE: todo OPEN WORK salvo lo que dependa de esos puntos.

## PRODUCTION SAFETY
NO automático: writes a Supabase, migraciones, RLS/grants, restore, deploy público (Vercel prod,
API remota), DNS, retirar `noindex`, merge a `main` que dispare CI/producción, rotar contraseñas,
gastar más de USD 10/mes en búsqueda. Autorizado automático: snapshot LOCAL con compuertas P2,
certificación, código/tests/docs/commits/push a la rama de trabajo.

## CLOUD BOOTSTRAP
Ver **`docs/CLOUD_BOOTSTRAP.md`** (comandos exactos desde clone limpio).

## NEXT ACTION
1. `git rev-parse HEAD` == HEAD del tag `cloud-checkpoint-2026-09-29` (o posterior en la rama).
2. Si el estado operativo privado está disponible: restaurarlo (ESTADO_DURABLE.md) y verificar
   los SHA-256 del `MANIFEST.json`. Si no: trabajar en OPEN WORK que no lo necesita (P18 runbook,
   P21 contenedor, P9 frontend, lote 4 con tests) y dejar la cola para la máquina que lo tiene.
3. En la máquina con estado: `python scripts/eretz_automatizacion.py estado`; si hay paros,
   diagnosticar; después reprobar 3 workers (P5).
