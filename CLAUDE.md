# ERETZ Propiedades — reglas universales

Repo operativo: `E:\ERETZ Propiedades\eretz-unified`, rama `handoff/codex-unificacion-2026-09-18`.
**Raiz canonica: `E:\ERETZ Propiedades` desde el 2026-10-04 (migracion definitiva, `docs/agent/MIGRACION_DEFINITIVA_2026-10-04.md`).**
D: (`D:\INMO CAPITAL`) y el nombre `E:\INMO CAPITAL` son historicos: no ejecutar, leer ni escribir ahi. Las rutas `D:\...` en documentos viejos son historicas; el codigo
resuelve la raiz desde la ubicacion del repo (`scripts/rutas_de_datos.py`).
Repo canonico: `E:\ERETZ Propiedades\eretz-propiedades` (ex `Inmo-Capital-main`; worktree principal en `release/eretz-private-preview`,
no se usa como cwd). Desarrollo: `E:\ERETZ Propiedades\eretz-b`. Worktrees viejos: `E:\ERETZ Propiedades\_worktrees_inactivos`.
Estado vigente: `docs/agent/CURRENT_STATE.md`. Cómo seguir: `docs/agent/HANDOFF.md`.
Acciones productivas pendientes: `docs/agent/READY_FOR_PRODUCTION_ACTION.md`. Índice de docs: `docs/INDEX.md`.
**Políticas permanentes del usuario (29-09, P1–P24): `docs/agent/POLITICAS_PERMANENTES.md`.** Un caso
cubierto por una política se resuelve con ella, sin preguntar.

## Autonomía
- Trabajo local y reversible: hacerlo sin pedir permiso (código, tests, scraping, certificación,
  QA, docs, commits y push a la rama de trabajo).
- Un informe no es una pausa. Esperar un proceso de fondo no es estar ocioso: tomar otra tarea.
- Terminar el turno solo si no queda trabajo seguro, si solo quedan acciones productivas, o por
  límite real de contexto (antes: commit, push, CURRENT_STATE y HANDOFF con la tarea exacta).

## Barreras (nunca automáticas → anotar en READY_FOR_PRODUCTION_ACTION y seguir con otra cosa)
- INSERT/UPDATE/DELETE, migraciones, RLS/grants, restore o deploy en producción; DNS. Excepciones
  acotadas en POLITICAS_PERMANENTES: P19 (clases estructurales tras backup+restore probados) y P24
  (merge a `main` solo si no dispara nada productivo).
- La snapshot servida `E:\ERETZ Propiedades\ERETZ_API_CONTRACT\ERETZ_API_SNAPSHOT.sqlite3` se reemplaza
  solo con `scripts/desplegar_snapshot.py` y solo si pasan TODOS los chequeos de P2; si no, no.
- Git: sin force push, sin `reset --hard`, sin `clean` destructivo, sin reescribir historia.
- Credencial faltante → `BLOCKED_EXTERNAL_CREDENTIAL` y seguir. Nunca imprimir ni commitear secretos.

## Datos
- Una propiedad real incompleta sobrevive. No inventar datos ni geografía. No mezclar agencias.
- Fail-closed: nunca un COMPLETE falso. Identidad ambigua → no atribuir. Fuente inaccesible → no
  asumir cero inventario.
- Portales (Zonaprop, Argenprop, etc.) nunca son fuente de inventario.
- Máximo 3 workers de certificación, adaptativo (P5). La cola corre sola (relanzador `ERETZ_relanzador`).
- robots.txt se respeta (P11). Retiros solo con muerte demostrada o 3 ausencias (P1).
- Mobile congelado.

## Cómo trabajar
- Ciclo: detectar → medir → causa → radio → test que muerda → corregir → validar contra el caso
  real → regresión → commit → push.
- Tests específicos primero; la suite completa antes de cerrar un cambio compartido.
- Buscar antes de leer: símbolo o patrón, después el rango relevante, expandir solo si hace falta.
  No leer completos por defecto `MASTER_PROGRESS.md` ni bitácoras o evidencias grandes.
- La historia vive en Git (`git log -S`, `git show`, `git blame`), no en memoria ni en CURRENT_STATE.
- Commits: problema, evidencia, arreglo, tests y radio cuando corresponda.
- Subagente solo para investigaciones amplias que contaminarían el contexto principal.
- Cambio fuerte de tarea → `/clear`; misma tarea con contexto lleno → `/compact` después de
  dejar tarea, bloqueos, decisiones y próximos pasos en CURRENT_STATE/HANDOFF.

## Trampas del entorno (Windows + Git Bash)
- Hay archivos con finales de línea mixtos: editar en binario o con Edit, nunca `Path.write_text()`
  ni `sed -i`. Revisar `git diff --numstat` antes de commitear.
- El heredoc de Bash se come las barras invertidas: código con regex va por archivo (Write).
- Procesos largos (workers, suites, builds) van aislados o en segundo plano, nunca en la consola
  compartida con Claude.
