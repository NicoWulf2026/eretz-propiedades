# Prompt para la próxima sesión (copiar y pegar)

```
ERETZ PROPIEDADES — CONTINUACIÓN DESDE EL CHECKPOINT CLOUD DEL 2026-09-29

Repo: https://github.com/NicoWulf2026/eretz-propiedades.git (PÚBLICO: nunca subir datos, ledger,
snapshots ni secretos).
Rama: handoff/codex-unificacion-2026-09-18. Tag del checkpoint: cloud-checkpoint-2026-09-29.

1. Cloná, hacé checkout de la rama y verificá con `git rev-parse HEAD` que estás en el tag
   cloud-checkpoint-2026-09-29 o en un commit posterior de la misma rama.
2. Leé, en este orden y ANTES de tocar nada:
   docs/CLOUD_CONTINUATION_HANDOFF.md, docs/agent/POLITICAS_PERMANENTES.md, CLAUDE.md,
   docs/agent/CURRENT_STATE.md, docs/agent/HANDOFF.md, docs/agent/READY_FOR_PRODUCTION_ACTION.md,
   docs/agent/lotes/README.md, docs/agent/ESTADO_DURABLE.md, docs/CLOUD_BOOTSTRAP.md.
3. No repitas auditorías ya hechas: están documentadas. Empezá por NEXT ACTION del handoff.
4. Las políticas P1–P24 son decisiones del usuario, permanentes: un caso cubierto se resuelve con
   ellas sin preguntar. Decisiones técnicas reversibles: las tomás vos.
5. Autonomía: trabajar → validar → reportar la fase → CONTINUAR. Reportar no es detenerse.
   Solo preguntá ante una decisión nueva, irreversible o de alto impacto que ninguna política
   cubra y que no tenga salida conservadora; y aun así seguí con otra tarea segura.
6. Bloqueo externo (credencial, cuenta, pago, dominio, abogado, acción productiva): marcalo
   (BLOCKED_EXTERNAL_* / EXTERNAL_*_REQUIRED) y seguí con otra cosa.
7. Seguridad productiva: cero writes a Supabase, migraciones, RLS, restore, deploy público, DNS o
   merge a main que dispare producción, salvo lo que P2/P19/P24 permiten con sus condiciones.
8. Cola: hasta 3 workers adaptativos (P5), régimen actual 2; todo Tokko en un solo worker; no
   paralelizar pedidos a Tokko; respetar robots.txt y 403/429.
9. Cobertura nacional y beta son tracks separados: ninguno bloquea al otro.
10. Estado operativo: descargar ERETZ_STATE_2026-09-29.tar.gz del almacenamiento privado del usuario,
    verificar SHA-256, extraer en una carpeta, `export ERETZ_DATA_ROOT=<carpeta>` y correr
    `python scripts/cloud/prueba_restore.py` (0 problemas, 0 accesos a D:\). Si no está disponible, trabajá en lo
    que no lo necesita (código, tests, runbooks, frontend) y documentalo; no reconstruyas la cola
    desde cero.
11. Commits con mensaje claro y la línea Co-Authored-By indicada por el entorno; push solo a la
    rama de trabajo; sin force push.
Trabajá hasta agotar las tareas seguras, empezando por NEXT ACTION.
```
