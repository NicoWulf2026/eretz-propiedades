# ERETZ Propiedades — reglas universales

Repo operativo: `D:\INMO CAPITAL\eretz-unified`, rama `handoff/codex-unificacion-2026-09-18`.
`D:\INMO CAPITAL\Inmo-Capital-main` es LEGACY / solo referencia: no se usa como cwd ni se modifica.
Estado vigente: `docs/agent/CURRENT_STATE.md`. Cómo seguir: `docs/agent/HANDOFF.md`.
Acciones productivas pendientes: `docs/agent/READY_FOR_PRODUCTION_ACTION.md`. Índice de docs: `docs/INDEX.md`.

## Autonomía
- Trabajo local y reversible: hacerlo sin pedir permiso (código, tests, scraping, certificación,
  QA, docs, commits y push a la rama de trabajo).
- Un informe no es una pausa. Esperar un proceso de fondo no es estar ocioso: tomar otra tarea.
- Terminar el turno solo si no queda trabajo seguro, si solo quedan acciones productivas, o por
  límite real de contexto (antes: commit, push, CURRENT_STATE y HANDOFF con la tarea exacta).

## Barreras (nunca automáticas → anotar en READY_FOR_PRODUCTION_ACTION y seguir con otra cosa)
- INSERT/UPDATE/DELETE, migraciones, RLS/grants, restore o deploy en producción; DNS; merge a `main`.
- Reemplazar la snapshot servida `D:\INMO CAPITAL\ERETZ_API_CONTRACT\ERETZ_API_SNAPSHOT.sqlite3`
  cuenta como deploy: construir y probar en otra ruta.
- Git: sin force push, sin `reset --hard`, sin `clean` destructivo, sin reescribir historia.
- Credencial faltante → `BLOCKED_EXTERNAL_CREDENTIAL` y seguir. Nunca imprimir ni commitear secretos.

## Datos
- Una propiedad real incompleta sobrevive. No inventar datos ni geografía. No mezclar agencias.
- Fail-closed: nunca un COMPLETE falso. Identidad ambigua → no atribuir. Fuente inaccesible → no
  asumir cero inventario.
- Portales (Zonaprop, Argenprop, etc.) nunca son fuente de inventario.
- Máximo 2 workers de certificación. La cola corre sola (relanzador `ERETZ_relanzador`).
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
