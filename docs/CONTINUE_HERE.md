# CONTINUE HERE (ERETZ Propiedades)

1. Ruta canonica: `E:/ERETZ Propiedades` (D:/INMO CAPITAL es respaldo, no usar). Abrir Claude Code en `E:/ERETZ Propiedades/eretz-unified`.
2. Rama de trabajo: `integration/eretz` (worktree `E:/ERETZ Propiedades/eretz-b`). Nodo operativo: `handoff/codex-unificacion-2026-09-18` (solo ff-only).
3. HEAD: el ultimo commit de `integration/eretz` (`git log -1`); el nodo esta en el mismo SHA.
4. Corriendo: cola de certificacion (2 workers pythonw) + tareas programadas `ERETZ_relanzador` y `ERETZ_vigilante_paros`.
5. A medio hacer: nada sin commitear. Post-beta `b/postbeta-lote8` = `88a22cd` (v7 + iframe Amaira), sin desplegar. Pendiente del usuario: servir `final_v7d` (READY #7b) y Git en el PATH de maquina (READY #14).
6. Proxima accion: re-armar la vigilancia de paros (`_b_scratch/esperar_paro.py`), correr la suite completa, atender cada paro con una fila en `AGENCY_DEFECTS_DIFERIDOS.jsonl`.
7. Leer: `docs/ERETZ_CODEX_TO_CLAUDE_HANDOFF.md`, seccion "HANDOFF URGENTE — 2026-10-06".
