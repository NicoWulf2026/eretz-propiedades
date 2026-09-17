# ERETZ Propiedades — Auditoría de activos, repos y fuente única de verdad

Auditoría de sólo lectura, 2026-09-04. **No se borró, movió, renombró ni
publicó nada.** La cola de certificación siguió corriendo intacta durante todo
el relevamiento (PID 7652).

---

## 1. Executive summary

**No hay proyectos paralelos. Hay uno solo, con siete worktrees.** Lo que a
simple vista parecen siete copias del sistema —`eretz-agency`, `eretz-main`,
`eretz-audit`, `eretz-integration`, `eretz-rescue`,
`Inmo-Capital-frontend-phase-a` y `Inmo-Capital-main`— son **worktrees de un
único repositorio Git**, cada uno con una rama distinta. No son duplicación:
son la forma normal de trabajar varias ramas a la vez sin clonar.

Cuatro hallazgos que sí importan:

1. **La cola activa lee una base de preingestión vieja.** El certificador tiene
   como default la base del **27 de agosto**, anterior al fix D-014, mientras
   la canónica es la del **3 de septiembre** con 13.023 candidatas más.
2. **Todo el proyecto vive en `D:`, que es una unidad EXTRAÍBLE** con 15,4 GB
   libres. `C:` tiene 118,7 GB libres y está prácticamente sin usar.
3. **Hay dos generaciones de scraper conviviendo**, y no es un accidente: hacen
   cosas distintas. Ver §6.
4. **6,58 GB de `_scratch`** dentro del repo, incluida una instalación completa
   de PostgreSQL/pgAdmin, y **1,16 GB de `Viejo`** con una instalación completa
   de VS Code.

---

## 2. Fuente única de verdad actual

| | |
|---|---|
| **Repositorio canónico** | `NicoWulf2026/eretz-propiedades` |
| **Ruta principal** | `D:\INMO CAPITAL\Inmo-Capital-main` |
| **Worktree activo** | `D:\INMO CAPITAL\eretz-agency` (`feat/roomix-agency-coverage`) |
| **Commits** | 194 · 33 ramas · 4 tags |
| **Proyecto Vercel** | `eretz-propiedades` (`prj_pPFVJ8cPst5NMjJ7iWvWTQr9oRLR`) |

---

## 3. Repositorios Git

### Repos reales

| Ruta | Remote | Rama | Estado |
|---|---|---|---|
| `D:\INMO CAPITAL\Inmo-Capital-main` | `NicoWulf2026/eretz-propiedades` | `release/eretz-private-preview` | 92 archivos sin commitear |
| `C:\Users\...\Desktop\inmocapital` | `NicoWulf2026/inmocapital` | `main` (2026-06-25) | limpio |
| `D:\MARFA - Panel Operativo MVP 1` | — | git incompleto | otro proyecto |
| `...\Inmo-Capital-main\Viejo\inmocapital` | — | git incompleto | histórico anidado |

**Los dos repos de GitHub comparten historia.** El commit `bfb1ef9` (HEAD de
`inmocapital`) existe dentro de `eretz-propiedades`: el segundo es la
continuación renombrada del primero, no un proyecto distinto.

### Worktrees — no son copias

| Worktree | Rama | HEAD |
|---|---|---|
| `Inmo-Capital-main` | `release/eretz-private-preview` | `d23051abc6` |
| **`eretz-agency`** | **`feat/roomix-agency-coverage`** | **`7385af6f61`** ← ACTIVO |
| `eretz-audit` | detached | `8521d47008` |
| `eretz-integration` | `integrate/eretz-pre-main` | `bd3f37c333` |
| `eretz-main` | `main` | `e9630f5f70` |
| `eretz-rescue` | `integrate/release-dirty-recovery` | `b6c326b0ce` |
| `Inmo-Capital-frontend-phase-a` | `feat/eretz-frontend-phase-a` | `04e63a2895` |

---

## 4. Cadena ACTIVA — no tocar

```
Task Scheduler "ERETZ_cola_certificacion"  [Running]
  └─ cmd.exe /c "D:\INMO CAPITAL\eretz-agency\_cola_certificacion.bat"
       └─ cd "D:\INMO CAPITAL\eretz-agency"
            └─ python -u scripts\run_agency_certification_queue.py --ready --limit 0
                 ├─ PID 7652
                 ├─ connectors\{base,generico,geografia,tokko,wasi,...}.py
                 ├─ scripts\{run_rollout,agency_certifier,defect_triage}.py
                 └─ salidas → D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827\
                      ├─ AGENCY_CERTIFICATION_RUNNER.lock
                      ├─ AGENCY_CERTIFICATION_PROGRESS.json
                      ├─ AGENCY_DEFECT_QUEUE.jsonl
                      ├─ cola_task.log
                      └─ agencies\<hash>\certification.json
```

Entradas que además lee: `ERETZ_AGENCY_DATA\`,
`agency_platform_directory.jsonl`, `ERETZ_SUPABASE_RECONCILIATION_V2_20260827\`.

**Todo lo listado arriba es `ACTIVE_DO_NOT_TOUCH`.**

---

## 5. Bases de datos

| Ruta | MB | Fecha | Estado |
|---|---|---|---|
| `ERETZ_PREINGESTION_REBUILD_20260903\PREINGESTION_REBUILD.sqlite3` | 1.096 | 03-09 | **CANÓNICA** — 58.427 candidatas |
| `ERETZ_SUPABASE_RECONCILIATION_V2_20260827\PREINGESTION_REBUILD.sqlite3` | 1.090 | 27-08 | **la lee la cola activa** — 45.404 candidatas |
| `ERETZ_SUPABASE_RECONCILIATION_20260827\SUPABASE_RECONCILIATION.sqlite3` | 342 | 27-08 | histórico |
| `ERETZ_SUPABASE_RECONCILIATION_V2_20260827\SUPABASE_RECONCILIATION.sqlite3` | 229 | 27-08 | histórico |

### El componente que lee una versión vieja

`scripts/agency_certifier.py` tiene como valor por defecto de
`--preingestion-db` la base del 27 de agosto. La usa para `baseline_inventory`
—el conteo de filas previas por inmobiliaria—, así que **subestima el
inventario histórico de las agencias afectadas por D-014**. No corrompe nada y
no cambia el veredicto de idempotencia, pero es un dato viejo alimentando una
decisión actual.

**Corrección propuesta (no ejecutada):** apuntar el default a la base del 3 de
septiembre, en la próxima ventana sin certificación en vuelo. Toca
`agency_certifier.py`, que entra en la huella, así que invalida.

---

## 6. Scraper canónico y las dos generaciones

**¿El scraper de hoy es evolución directa del histórico? → PARCIAL.**

| | Generación 1 | Generación 2 |
|---|---|---|
| Ubicación | `scraper/` | `connectors/` + `scripts/` |
| Nace | 2026-05-09 (primer commit del repo) | 2026-08-22 |
| Último cambio | 2026-08-12 | hoy |
| Qué hace | portales (Zonaprop), descubrimiento por Google, Playwright, pipeline a Supabase | ingesta directa del sitio propio de cada inmobiliaria |
| Quién la usa | 35 archivos, casi todos en `scripts/` de la rama principal | la cola de certificación |

**Mismo repositorio, misma historia, pero distinta estrategia de adquisición.**
La generación 2 no reemplaza a la 1: la 1 descubre inmobiliarias y raspa
portales; la 2 entra al sitio de cada inmobiliaria ya identificada. Son etapas
distintas del mismo embudo.

**El scraper canónico para certificación es la generación 2**, en el worktree
`eretz-agency`.

---

## 7. Frontend canónico

Ocho `next.config` encontrados. Siete son el **mismo frontend** en distintos
worktrees; el octavo es el histórico del Escritorio.

**Canónico:** `frontend/` del repo `eretz-propiedades`, vinculado al proyecto
Vercel `eretz-propiedades`. La versión más avanzada vive en la rama
`feat/eretz-frontend-phase-a`.

`C:\Users\...\Desktop\inmocapital\frontend` (27-06) es el antecedente
histórico: mismo linaje, tres meses atrás.

---

## 8. API canónica

`api/main.py`, FastAPI, 6 rutas: `/propiedades`, `/propiedades/mapa`,
`/propiedades/{id}`, `/barrios`, `/stats`, `/`.

Aparece diez veces, pero **ocho son el mismo archivo en distintos worktrees**.
Las dos versiones realmente distintas son las del Escritorio y la de
`Viejo/InmoLink`, ambas históricas.

---

## 9. Vercel

**Un solo proyecto real.** Los cuatro `.vercel/project.json` encontrados
apuntan al mismo `projectId` y al mismo team:

| Campo | Valor |
|---|---|
| Project | `eretz-propiedades` |
| projectId | `prj_pPFVJ8cPst5NMjJ7iWvWTQr9oRLR` |
| orgId | `team_ic2G65xEo6yEgCk` |

**Limitación declarada:** el conector de Vercel requiere autorización OAuth que
esta sesión no puede completar, así que **no pude enumerar deployments,
previews, dominios ni variables de entorno desde la API**. Todo lo de esta
sección sale de los archivos locales. Para separar proyectos de deployments
hace falta autorizar el conector o correr `vercel projects ls` y
`vercel deployments ls` en una terminal interactiva.

---

## 10. Supabase

No hay URLs de Supabase incrustadas en el código: todo pasa por variables de
entorno. Archivos de configuración presentes:

- `Inmo-Capital-main\.env` y `.env.example`
- `Inmo-Capital-main\.env.bak.precutover_20260616_161121`
- `frontend\.env.local` y `.env.local.example`
- equivalentes en `Inmo-Capital-frontend-phase-a`

No se imprimen valores. **No detecté configuraciones apuntando a proyectos
Supabase distintos**, pero el `.env.bak.precutover` sugiere que hubo un cambio
de base en junio y conviene revisarlo manualmente.

Producción hoy: la que responde `PGRST002` desde ayer.

---

## 11. Espacio y duplicados

### Ocupación

| Directorio | GB |
|---|---|
| `Inmo-Capital-main` | 10,68 |
| ├─ `_scratch` | **6,58** |
| ├─ `Viejo` | **1,16** |
| ├─ `frontend` | 0,78 |
| ├─ `.git` | 0,65 |
| └─ `.venv` | 0,25 |
| `ERETZ_SUPABASE_RECONCILIATION_V2_20260827` | 2,40 |
| `ERETZ_PREINGESTION_REBUILD_20260903` | 2,04 |
| `TOKKO_ROLLOUT_FULL` | 2,01 |
| `Inmo-Capital-frontend-phase-a` | 1,30 |
| worktrees `eretz-*` | ~0,5 c/u |

### Clasificación

| Categoría | Qué | GB aprox |
|---|---|---|
| **CACHE REGENERABLE** | 13 dirs `node_modules` / `.next` / `.venv` | **4,08** |
| **DUPLICADO INÚTIL** | `Viejo\InmoLink\Microsoft VS Code` (instalación completa) | ~1,0 |
| **DUPLICADO INÚTIL** | `_scratch\...\pgsql_complete` (PostgreSQL+pgAdmin) | ~1,5 |
| **SNAPSHOT REPRODUCIBLE** | `ERETZ_SUPABASE_RECONCILIATION_V2` (base vieja) | 2,40 |
| **EVIDENCIA DE AUDITORÍA** | `_scratch\eretz_*` (informes de cierre) | ~3,5 |
| **ACTIVO** | cadena del §4 + base del 03-09 | — |

---

## 12. Trabajo rehecho

| Funcionalidad | Veredicto |
|---|---|
| Scraping de portales | **YA EXISTÍA** (`scraper/`), sigue en uso para descubrimiento |
| Ingesta directa por inmobiliaria | **NO EXISTÍA** — es la generación 2 |
| Geocodificación | **SE REESCRIBIÓ CON JUSTIFICACIÓN**: `scraper/geocoder.py` (1.697 líneas, con red) → `connectors/geografia.py` (419 líneas, catálogo local, 0 llamadas remotas, 0 falsos positivos) |
| Dedupe de propiedades | **SE DUPLICÓ PARCIALMENTE**: `scraper/safe_merge.py` (646 líneas) y `scripts/property_duplicate_groups.py` resuelven cosas distintas pero se solapan; revisar |
| Identidad de inmobiliaria | **SE REESCRIBIÓ CON JUSTIFICACIÓN**: el cruce por una sola columna fallaba |
| Frontend / API / mapa / filtros | **YA EXISTÍA**, se continúa el mismo |
| Scheduler | **NO EXISTÍA** como tal |
| Normalización | **YA EXISTÍA** y se extendió |

**No estamos reconstruyendo el sistema.** El único solapamiento real a revisar
es dedupe.

---

## 13. Clasificación final

| Activo | Categoría |
|---|---|
| Cadena del §4 completa | `ACTIVE_DO_NOT_TOUCH` |
| Repo `eretz-propiedades` + 7 worktrees | `KEEP_CANONICAL` |
| Base preingestión 03-09 | `KEEP_CANONICAL` |
| Base preingestión 27-08 | `KEEP_HISTORICAL` (evidencia del delta D-014) |
| `ERETZ_GEO`, `ERETZ_AGENCY_DATA`, `*_ROLLOUT_FULL` | `KEEP_HISTORICAL` |
| `Desktop\inmocapital` | `ARCHIVE` — historia ya contenida en el canónico |
| `Viejo\InmoLink\Microsoft VS Code` | `SAFE_TO_DELETE` |
| `_scratch\...\pgsql_complete` | `SAFE_TO_DELETE` |
| `node_modules` / `.next` / `.venv` | `SAFE_TO_DELETE` (regenerable) |
| `_scratch\eretz_*` informes | `REVIEW_REQUIRED` — evidencia, quizá comprimible |
| Ramas viejas (33) | `REVIEW_REQUIRED` |
| `D:\MARFA`, `D:\BASURA 1` | fuera de alcance |

**Evidencia exigida para `SAFE_TO_DELETE`:** ninguno de esos elementos es
importado por código vigente, ninguno aparece en la cadena del Task Scheduler,
ninguno contiene commits únicos, y `node_modules`/`.venv` se regeneran con
`npm install` / `pip install -r requirements.lock`.

---

## 14. Riesgos

1. **Todo el proyecto en una unidad extraíble con 15,4 GB libres.** Es el
   riesgo más alto del inventario: una desconexión mata la cola y deja el
   cerrojo huérfano, y no hay copia en `C:`.
2. **El certificador lee la base del 27 de agosto.**
3. **92 archivos sin commitear** en el worktree principal.
4. **33 ramas** sin política de retención.
5. **No pude auditar Vercel de verdad** por falta de autorización del conector.

---

## 15. Arquitectura propuesta

Un solo repositorio, como hoy. **La evidencia no justifica separar** scraper,
API y frontend: comparten contrato de datos, se versionan juntos y el
despliegue de Vercel usa sólo `frontend/`.

```
eretz-propiedades  (repo único)
├── connectors/     ingesta directa            gen 2
├── scraper/        portales y descubrimiento  gen 1
├── scripts/        certificación, gates, dry-runs
├── api/            FastAPI
├── frontend/       Next.js → Vercel
└── tests/          1.411
```

Datos **fuera** del repo, como ya están, en un único árbol versionado por fecha.

---

## 16. Plan de limpieza — NO EJECUTADO

| Fase | Acción | Libera | Riesgo |
|---|---|---|---|
| 1 | Commitear o descartar los 92 archivos sueltos | — | bajo |
| 2 | **Copiar el proyecto a `C:`** antes de tocar nada | — | — |
| 3 | Borrar `node_modules` / `.next` / `.venv` | **4,08 GB** | nulo, regenerable |
| 4 | Borrar `Viejo\...\VS Code` y `_scratch\...\pgsql` | ~2,5 GB | bajo |
| 5 | Comprimir `_scratch\eretz_*` a `.zip` | ~2,5 GB | revisar antes |
| 6 | Archivar `Desktop\inmocapital` | — | bajo |
| 7 | Apuntar el certificador a la base del 03-09 | — | invalida huellas |
| 8 | Podar ramas ya integradas | — | revisar antes |

**Espacio recuperable sin riesgo: ~6,6 GB.** Con la compresión de evidencia,
hasta ~9 GB — que sobre 15,4 GB libres en `D:` no es menor.

---

## 17. Respuestas directas

1. **¿Uno o varios proyectos?** Uno. Siete worktrees de un repo, no siete copias.
2. **¿Scraper canónico?** `connectors/` + `scripts/` en `eretz-agency`.
3. **¿Es el histórico?** **Parcial.** Mismo repo y misma historia, pero
   `connectors/` es una arquitectura nueva del 22 de agosto que convive con
   `scraper/`, que sigue viva para descubrimiento.
4. **¿Frontend canónico?** `frontend/` del repo canónico; lo más avanzado en
   `feat/eretz-frontend-phase-a`.
5. **¿Cuántos repos Git?** 2 en GitHub (`eretz-propiedades`, `inmocapital`,
   con historia compartida) + 2 locales incompletos.
6. **¿Proyectos Vercel reales?** 1 — `eretz-propiedades`.
7. **¿Deployments/previews?** No verificable sin autorizar el conector.
8. **¿Base vigente?** `ERETZ_PREINGESTION_REBUILD_20260903`, aunque la cola
   lea la del 27-08 para el baseline.
9. **¿Qué duplicamos?** Nada estructural. Solapamiento real sólo en dedupe.
10. **¿Qué rehacemos sin necesidad?** Nada demostrado.
11. **¿Qué se puede borrar?** Caches regenerables, VS Code y pgAdmin
    incrustados: ~6,6 GB.
12. **¿Qué fusionar?** `safe_merge` con el detector de duplicados; y decidir
    qué ramas integrar.
13. **¿Qué no tocar?** Toda la cadena del §4.
14. **¿Cuánto espacio?** ~6,6 GB sin riesgo, ~9 GB comprimiendo evidencia.
15. **¿Arquitectura definitiva?** Repo único con datos afuera. Separar no está
    justificado por la evidencia.
