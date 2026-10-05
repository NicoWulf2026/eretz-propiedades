# Migracion definitiva al disco externo y nombre unico: ERETZ Propiedades (2026-10-04)

Continua `MIGRACION_D_A_E_2026-10-04.md` (copia D: -> E: y reanudacion en E: a las 10:47).
Esta fase: demostrar que la copia esta completa, abandonar D: del todo, ordenar la raiz bajo un
nombre unico y validar todo desde E:.

## Fase 0 - Volumenes (evidencia: Get-Disk / Get-Volume / Get-Partition)
| | disco | bus | FS | rol |
|---|---|---|---|---|
| C: | 0, KINGSTON SA400S37 224 GB | SATA | NTFS | sistema (IsSystem/IsBoot); no se toca |
| D: | 1, Generic SD/MMC 116 GB | USB, removible | exFAT | **OLD_VOLUME**, OLD_PROJECT_ROOT `D:\INMO CAPITAL` |
| E: | 2, Seagate ST1000LM 932 GB | USB | NTFS | **NEW_VOLUME** |

## Fases 1-4 - Inventario y comparacion (CAMBIOS POSTERIORES A LA COPIA: NO)
- Git: 54 refs en D:; todas identicas en E: o ancestros de E: (`3321e70` es ancestro de `66a8c02`,
  12 commits). COMMITS_MISSING_FOUND = 0.
- Worktrees: los mismos 14 en los dos discos; los 174 archivos sin commitear de los 4 worktrees
  sucios, identicos por sha256.
- Manifiesto completo (ruta + tamano, sin caches regenerables): D: 153.471 archivos, E: 154.035;
  solo en D: 2 (la bandera APAGADO y un STOP de relanzamiento, consumidos a proposito); D: mas nuevo: 0.
- Barrido recursivo de TODO D: (502.683 archivos) por fecha posterior a la pausa (03-10 20:10):
  lo de ERETZ es la ventana de la pausa (20:12-20:45) y esta en E: identico o como prefijo exacto
  de los ledgers que siguieron creciendo. Lo demas reciente en D: es NUVIA (otro proyecto, no ERETZ).
- Fuera de la raiz, de ERETZ en D:: `inmocapital-main` (copia vieja + imagenes, 15 MB), `acvtmp`,
  `tmp` -> copiados a `_respaldos\disco_D_fuera_de_la_raiz`. `D:\InmoLink\Git` = Git for Windows.

## Dependencias del disco viejo encontradas
| que | estado |
|---|---|
| Git for Windows en `D:\InmoLink\Git`, en el PATH de MAQUINA | copia identica en `%LOCALAPPDATA%\Programs\Git` (C:), verificada; el cambio del PATH de maquina es configuracion del sistema: accion del usuario (ver READY) |
| lanzadores de `eretz-b\.venv` (pytest.exe...) apuntando a `D:\...\.venv\Scripts\python.exe` | venv recreado desde `pyproject.toml` |
| 7 scripts de la clausura activa con defaults `D:\INMO CAPITAL` | `dato(...)` (commit `41402b5`), test guardian |
| PATH de usuario `D:\Antigravity\bin`, `D:\Microsoft VS Code\bin`; PATH de maquina `D:\cursor\...` | editores del usuario, no ERETZ |

## Nombres historicos
"URLink" literal: 0 apariciones. Nombres anteriores del proyecto encontrados: InmoLink e
Inmo Capital / INMO CAPITAL / Inmo-Capital.
- Renombrados: raiz `E:\INMO CAPITAL` -> `E:\ERETZ Propiedades`; repo `Inmo-Capital-main` ->
  `eretz-propiedades`; worktrees `Inmo-Capital-*` -> `eretz-*`; User-Agent del geocoder y del scraper;
  variables propias `INMOCAPITAL_QUEUE_WORKER_*` -> `ERETZ_PROPIEDADES_QUEUE_WORKER_*`.
- Alias de compatibilidad (contratos persistidos, NO se renombran): claves `inmocapital`,
  `_inmocapital` (metadatos de geocodificacion ya guardados) e `inmocapital_source`; funciones SQL
  de Supabase `set_inmolink_password` / `check_inmolink_password` y las migraciones historicas;
  `rutas_de_datos.RAICES_HISTORICAS` (reubica rutas guardadas bajo `D:\INMO CAPITAL` y `E:\INMO CAPITAL`).
- Documentacion historica (handoffs, auditorias, Obsidian): sin cambios, es evidencia.

## Estructura canonica (desde el cutover 04-10 20:5x)
| rol | ubicacion |
|---|---|
| CANONICAL_ROOT / RUNTIME_STATE | `E:\ERETZ Propiedades` (ledger, defect queue, paquetes, GeoRef, snapshot servida, directorio, manifiesto: misma estructura relativa; el codigo deriva la raiz del repo) |
| CANONICAL_REPO | `E:\ERETZ Propiedades\eretz-propiedades` (ex `Inmo-Capital-main`; worktree principal en `release/eretz-private-preview`, 115 archivos sin commitear preservados) |
| OPERATIONAL_WORKTREE | `E:\ERETZ Propiedades\eretz-unified` (`handoff/codex-unificacion-2026-09-18`) |
| desarrollo | `eretz-b` (`integration/eretz`), `eretz-b-dev` (`b/postbeta-lote8`) |
| worktrees inactivos | `_worktrees_inactivos\` (10, movidos con `git worktree move`; IDs internos `Inmo-Capital-*` renombrados) |
| BACKUPS | `_respaldos\` (bundle, zip, checkpoint 29-09, `.bak` de la raiz, venvs viejos, lo de D: fuera de la raiz) |
| historico | `_historico\` (logs/err de corridas viejas, imagenes) ; `_herramientas\` (instalador de Git) |
Todo lo que el codigo activo lee quedo en la raiz (se inventariaron las referencias antes de mover).

## Cutover (etapa B)
- Pausa controlada 20:06 (`eretz_automatizacion.py off`), sin matar: los 2 workers terminaron su agencia (20:43).
- Checkpoint antes/despues: 22/22 archivos clave identicos por sha256; HEADs y ramas identicos; los 106
  archivos sueltos movidos de la raiz cuadran exacto.
- `git worktree repair` + `git worktree move`; 0 referencias a la raiz vieja en `.git` de los worktrees y
  en `.git/worktrees/*/gitdir`; `fsck --connectivity-only` limpio.
- venv de `eretz-b` recreado desde `pyproject.toml` (el viejo, con lanzadores a D:, en `_respaldos\entornos`).
  Los pines canonicos NO eran instalables: `httpx2==2.13.1` exige `idna>=3.18` y el pin era `idna==3.15`
  (el entorno probado ya tenia 3.18): pin corregido a 3.18.
- `npm ci` en `eretz-b\frontend` y `eretz-unified\frontend` (479 paquetes c/u).
- Huellas del nodo en la raiz nueva = v6 (18/18): ninguna certificacion se invalida por la migracion.
- Tareas re-registradas desde la raiz nueva (`eretz_automatizacion.py on`, 20:53); workers 19184/3748 con
  command line solo en `E:\ERETZ Propiedades\eretz-unified`. Pausa total: 47 min (casi todo, esperar a los workers).

## Validacion desde la raiz nueva
- Backend: 4001 passed / 5 skipped / 0 failed (igual que antes del cutover).
- Frontend: typecheck 0 errores; lint 0 errores (3 warnings preexistentes); vitest 1271 passed; build OK.
- API real (uvicorn) sobre la snapshot servida: 10/10 (health, ready, listado, ficha, mapa, filtros, stats,
  buscar, sugerencias, filtro combinado). Benchmark oficial sobre `snap_final_v6`: los 14 casos con los
  MISMOS totales que antes del movimiento y medianas comparables (todas < 2000 ms).

## Simulacion sin el disco viejo (Fase 13)
`D:\INMO CAPITAL` renombrado (reversible) y PATH del proceso SIN ninguna entrada de D: (git de la copia en C:):
- git en los 14 worktrees, suite, QA de navegador (`VALID_QA_RUN` 75/82, 0 fallas, 7 salteados), API 10/10,
  relanzador y vigilante disparados a mano (resultado 0, ven los 2 workers), workers vivos y solo en E:.
- **Fallo encontrado y corregido:** 23 tests leian artefactos reales con rutas `D:\INMO CAPITAL` fijas: con D:
  presente leian datos VIEJOS; sin D:, 21 se salteaban y 2 retornaban en verde sin probar nada. Ahora leen
  `dato(...)` (raiz vigente) y pasan contra los datos de E:; el test guardian cubre tambien `tests/`.
  `ERETZ_AGENCY_DATA\run_delta_loop.bat` (lanzador viejo sin tarea) repuntado (original en `_respaldos`).
- 0 escrituras en `D:\INMO CAPITAL` durante la simulacion; nada la recreo.

## Lo que queda fuera de ERETZ / del usuario
- PATH de MAQUINA `D:\InmoLink\Git\cmd` -> READY #14 (configuracion del sistema). Hasta entonces Claude Code
  (su Bash) y un `git` a secas usan Git desde D:; ERETZ (cola, tareas, API, snapshot) no llama a git.
- Esta sesion de Claude Code se abrio con `D:\INMO CAPITAL` como directorio adicional: una sesion nueva se abre
  en `E:\ERETZ Propiedades\eretz-unified`.
- Editores del usuario en D: (VS Code, Antigravity, Cursor) y NUVIA/MARFA/Taller: no son ERETZ.
- Incidente menor: al repuntar las herramientas de `_b_scratch` a la raiz nueva, la copia previa de 12 scripts
  de un solo uso (comparadores D:/E: ya ejecutados) se sobrescribio; sus salidas estan intactas.
