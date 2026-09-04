# ERETZ Propiedades — Manifiesto de limpieza, 2026-09-04

Fase 3. Sólo se eliminó lo demostrablemente regenerable o software
redistribuible. **Ningún activo histórico, evidencia, base, certificación,
commit ni archivo sin commitear fue borrado.**

---

## Resultado

| | |
|---|---|
| Libre en `D:` antes | 15,4 GB |
| Libre en `D:` después | **44,0 GB** |
| **Liberado** | **28,6 GB** |
| `D:\INMO CAPITAL` ahora | 21,48 GB en 183.568 archivos |

### Por qué el manifiesto por ítem suma menos que lo liberado

El script contabilizó **6,09 GB** sumando el tamaño de cada archivo antes de
borrarlo. El disco reporta 28,6 GB liberados. La diferencia no es un
descuadre: **`node_modules` anida rutas de más de 260 caracteres, y tanto la
enumeración de PowerShell como la de Python las saltean en silencio en
Windows.** Los tamaños de abajo son entonces **cotas inferiores**, y el número
del disco es el único confiable.

Ese mismo sesgo explica que la auditoría de fase 2 estimara "~6,6 GB
borrables": medía con la misma herramienta y con el mismo techo.

---

## Eliminado

Todo lo de esta tabla cumple las seis condiciones exigidas: no lo usa el Task
Scheduler, no es working directory, no contiene `.git`, no contiene datos
únicos, no contiene archivos modificados, y tiene mecanismo de regeneración.

| Ruta | Medido | Tipo | Regeneración |
|---|---|---|---|
| `Inmo-Capital-main\frontend\node_modules` | 538,0 MB | cache | `npm ci` |
| `Inmo-Capital-main\frontend\.next` | 295,6 MB | build | `npm run build` |
| `eretz-agency\frontend\node_modules` | 534,6 MB | cache | `npm ci` |
| `eretz-main\frontend\node_modules` | 534,6 MB | cache | `npm ci` |
| `eretz-main\frontend\.next` | 26,7 MB | build | `npm run build` |
| `eretz-integration\frontend\node_modules` | 534,6 MB | cache | `npm ci` |
| `eretz-integration\frontend\.next` | 26,7 MB | build | `npm run build` |
| `Inmo-Capital-frontend-phase-a\frontend\node_modules` | 534,6 MB | cache | `npm ci` |
| `Inmo-Capital-frontend-phase-a\frontend\.next` | 665,3 MB | build | `npm run build` |
| `Inmo-Capital-main\.venv` | 273,7 MB | entorno | `pip install -r requirements.lock` |
| `_scratch\eretz_definitive_audit\venv_verify` | 393,7 MB | entorno | `pip install` |
| `Viejo\InmoLink\Microsoft VS Code` | 814,2 MB | software | code.visualstudio.com |
| `_scratch\eretz_final_closure\tools\pgsql_complete` | 889,6 MB | software | postgresql.org |
| 442 directorios `__pycache__` | 23,4 MB | cache | se regenera al importar |

**Evidencia de dependencia cero, verificada antes de borrar:**

- La cola usa el Python del sistema (`AppData\Local\Programs\Python\Python314`),
  **no** el `.venv` del repo.
- Ningún script de `eretz-agency\scripts` menciona `node_modules`.
- Ningún proceso `node`/`npm` en ejecución.
- Las dos instalaciones embebidas se inspeccionaron: pgAdmin sólo traía sus
  propios SQL de plantilla, y VS Code no tenía `settings.json` ni workspace.
- `package-lock.json` y `requirements.lock` presentes.

---

## Conservado deliberadamente

| Activo | Motivo |
|---|---|
| `.git` (0,65 GB) | Instrucción explícita: `KEEP` por defecto |
| `_scratch\eretz_*` (informes) | evidencia de auditoría |
| `Viejo\inmocapital` | **contiene un `.git`**: por eso `Viejo` no se borró entero |
| `DATA_QUALITY\` (363 MB) | sin seguir por git, contenido único |
| Bases `20260827` | evidencia del delta D-014 |
| Los 7 worktrees | ninguno es copia; ver abajo |

---

## Los `.git` de 0,65 GB, explicados

`git count-objects -vH` sobre el repo canónico:

| Métrica | Valor |
|---|---|
| Objetos sueltos | 18.612 (128 MiB) |
| **De ellos, ya empaquetados** | **14.410** |
| En packs | 546.202 en **154 packs** (528 MiB) |
| Basura | **47 archivos** `.tmp-*.idx` huérfanos (1,98 MiB) |

El bundle pesa 10 MB porque guarda cada objeto alcanzable **una sola vez**.
Los 640 MB extra son **redundancia acumulada y residuos** de operaciones
interrumpidas —categorías **B y E**—, no historia única.

**No se tocó**, conforme a la instrucción. `git gc` recuperaría la mayor parte,
pero es una operación aparte y con su propia autorización.

---

## Objetos colgantes — un hueco del backup que se encontró y cerró

`git fsck` reveló **3 commits colgantes**, todos entradas de stash descartadas
de junio (`git stash list` está vacío, así que son inalcanzables).

**No estaban en el bundle**, porque `--all` sólo alcanza refs vivos. Se
verificó contra el bundle restaurado, no contra el repo de origen: la primera
comprobación se hizo mal y habría dado un falso "backup completo".

Rescatados como patches en `C:\...\20260904\stashes_rescatados\`:

| Commit | Contenido |
|---|---|
| `db8dfb20` | 520 líneas de `docs/obsidian/.../11 - Pendientes.md` |
| `a3bb1f24` | 488 líneas del mismo documento |
| `bbf86f5a` | 520 líneas del mismo documento |

Ese documento existe hoy con 65 KB y siguió evolucionando, así que eran
versiones intermedias y el riesgo era bajo — pero eso se supo **después** de
preservarlas.

---

## Worktrees — clasificación

Ninguno se eliminó. Son ramas del mismo repositorio, no copias.

| Worktree | Rama | Estado | Clasificación |
|---|---|---|---|
| `eretz-agency` | `feat/roomix-agency-coverage` | runner canónico | **ACTIVE** |
| `Inmo-Capital-main` | `release/eretz-private-preview` | 93 sin commitear | **ACTIVE** |
| `eretz-audit` | detached | 5 modificados | `REVIEW_REQUIRED` |
| `eretz-main` | `main` | limpio | `KEEP_TEMPORARILY` |
| `eretz-integration` | `integrate/eretz-pre-main` | limpio | `KEEP_TEMPORARILY` |
| `eretz-rescue` | `integrate/release-dirty-recovery` | limpio | `KEEP_TEMPORARILY` |
| `Inmo-Capital-frontend-phase-a` | `feat/eretz-frontend-phase-a` | limpio | `KEEP_TEMPORARILY` |

Los cuatro `KEEP_TEMPORARILY` están limpios, pero **no se verificó todavía que
sus ramas estén integradas**. Hasta demostrarlo, no se remueven.

---

## Trabajo sin commitear — protegido

93 archivos en `Inmo-Capital-main` y 5 en `eretz-audit`.

| Grupo | Cantidad | Destino |
|---|---|---|
| Modificados con seguimiento | 5 (+306 líneas, 187 de tests) | patch en el backup |
| Sin seguir: código | 73 (9,1 MB) | copiados y verificados |
| Sin seguir: datos | 7 (0,9 MB) | copiados |
| Sin seguir: `DATA_QUALITY\` | 363 MB | copiado |
| Sin seguir: doc/output | 7 | copiados |

**Los 88 sin seguir se verificaron uno por uno contra el backup: cero
faltantes.** Los modificados coinciden por hash. No se hizo ningún commit
artificial.

---

## Lo que sigue pendiente

| Ítem | Estado |
|---|---|
| `.git` — 154 packs y 47 residuos | `REVIEW_REQUIRED` — necesita `git gc` autorizado |
| `_scratch\eretz_*` (~3,5 GB) | `REVIEW_REQUIRED` — comprimible tras revisión |
| Bases `20260827` (2,9 GB) | `KEEP_HISTORICAL` — comprimibles, no borrables |
| `Desktop\inmocapital` | `ARCHIVE` — historia contenida en el canónico |
| Ramas integradas | `REVIEW_REQUIRED` |
| `safe_merge` vs detector de duplicados | `REVIEW_REQUIRED` — documentar antes de deprecar |
