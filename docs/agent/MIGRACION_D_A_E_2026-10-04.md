# Migracion de almacenamiento D: -> E: (2026-10-03/04)

Solo cambio el disco. Estado, evidencia, huellas, certificaciones y Git son los mismos.

## Pausa controlada (03-10 20:16)
- `scripts/eretz_automatizacion.py off`: tareas deshabilitadas + bandera de paro radio APAGADO.
  Ningun proceso se mato: w1 salio 20:18 (ana barbeito), w0 20:45:35 (caian, COMPLETE).
- Checkpoint (fuera del disco copiado, en el scratchpad de C:): 20 archivos de estado con sha256,
  Git (heads, ramas, worktrees) y conteo por directorio: 81 dirs, 310.275 archivos, 41,1 GB.

## Verificacion de la copia (04-10)
- E: contra el checkpoint: 79/81 directorios identicos; 19/20 archivos clave identicos byte a byte
  (resultados, defect queue, diferidas, prioridad, progreso, directorio de plataformas, snapshot
  servida de 558 MB, archivos del Regression Gate). Lo unico ausente en E: eran los 3 archivos de la
  pausa (bandera APAGADO, `ERETZ_AUTOMATION_OFF.json`, el script del checkpoint): copiados.
- Git: heads, ramas y estado limpio de `eretz-unified` y `eretz-b` identicos.

## Cambios de referencias (solo clase A, operativas)
| que | antes | despues |
|---|---|---|
| 14 worktrees (`.git` de cada uno y `.git/worktrees/*/gitdir`) | `D:/INMO CAPITAL/...` | `git worktree repair` desde `E:\INMO CAPITAL\Inmo-Capital-main` |
| raiz de datos (`scripts/rutas_de_datos.py`) | `D:\INMO CAPITAL` fijo | la carpeta que contiene al repo; `RAIZ_ORIGINAL` queda solo para reubicar rutas viejas |
| `preingestion_manifest.describir` | comparaba la ruta reubicada con la del manifiesto (D:) | compara las dos reubicadas (si no, base vigente NO_DECLARADA y el runner no corria) |
| `_relanzador.bat`, `_vigilante.bat`, `ERETZ_AUTOMATION_ON/OFF.cmd` | `cd /d "D:\INMO CAPITAL\eretz-unified"` | `cd /d "%~dp0"`, logs relativos |
| tareas `ERETZ_relanzador`, `ERETZ_vigilante_paros` | Program/Arguments/WorkingDirectory en D: | re-registradas con `eretz_automatizacion.py on` desde E: (reemplazo, sin duplicar) |
| `CLAUDE.md` | repo operativo en D: | E: como raiz operativa permanente |

Commit `e5b5b16` (+ docs). Huellas: las 19 identicas a v6 (ninguna certificacion se invalida por la
migracion). Suite en E:: 3976 passed / 5 skipped / 0 failed (la primera corrida dio 2 fallas: el bug
de `describir`, corregido).

## Sin cambiar (a proposito)
- Clase B: ~30 docs y reportes historicos con rutas D: (evidencia).
- Clase C/D: ~130 scripts de un solo uso con defaults D: (deuda de portabilidad; el nucleo no los usa),
  `scraper/importar_excel.py` (`D:\Inmobiliairas .xlsx`), PATH del usuario (`D:\Antigravity\bin`,
  `D:\Microsoft VS Code\bin`): fuera de ERETZ, decision del usuario.
- D: no se borro: queda como origen viejo hasta que el usuario lo retire.

## Reanudacion (04-10 10:47)
- `eretz_automatizacion.py on` desde E:: tareas creadas, bandera APAGADO borrada, relanzador disparado.
- Workers 4720 (w0) y 4920 (w1) desde `E:\INMO CAPITAL\eretz-unified`, escribiendo progreso y
  cerrojos en E:. Ningun proceso ERETZ usa D: (el progreso de D: quedo en 03-10 20:45).
