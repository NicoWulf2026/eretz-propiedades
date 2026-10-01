# ERETZ — protocolo de relevo entre cuentas (A ↔ B)

**Regla principal: UNA SOLA CUENTA TRABAJA SOBRE `integration/eretz` A LA VEZ.**
No usar A y B simultáneamente sobre la misma rama. El estado de quién tiene la posta está en
`docs/ACCOUNT_HANDOFF.md` (`CURRENT OWNER`).

GitHub es la memoria compartida de código y estado de desarrollo. La PC local sigue siendo el
nodo operativo (ledger, paquetes, snapshots, GeoRef, preingestión, workers, scheduler, datos
privados bajo `ERETZ_DATA_ROOT`).

## Antes de soltar la posta (cuenta saliente)
1. Terminar una unidad atómica segura (nada a medias en un archivo de la huella).
2. Correr los tests relevantes (y la suite completa si se tocó algo compartido).
3. `git status` (sin sorpresas).
4. Commit.
5. `git push origin integration/eretz` (sin force).
6. Verificar: `git rev-parse HEAD` == `git ls-remote origin refs/heads/integration/eretz`.
7. Actualizar `docs/ACCOUNT_HANDOFF.md` (CURRENT HEAD, LAST UPDATE, estado operativo LAST_KNOWN).
8. Dejar NEXT ACTION concreta.
9. Árbol limpio (commit + push del handoff).
10. Cambiar CURRENT OWNER a la otra cuenta.

## Al tomar la posta (cuenta entrante)
1. `git fetch origin`
2. `git checkout integration/eretz`
3. `git pull --ff-only` (si no es fast-forward: parar y entender por qué; nunca forzar).
4. Verificar HEAD local == remoto.
5. Leer `docs/ACCOUNT_HANDOFF.md`.
6. Leer `docs/agent/CURRENT_STATE.md` (y `docs/agent/HANDOFF.md` § PARA LOCAL si aplica).
7. Continuar la NEXT ACTION.

## Worktrees locales (recomendación, no obligatorio)
- Cuenta A: `D:\INMO CAPITAL\eretz-a`
- Cuenta B: `D:\INMO CAPITAL\eretz-b`

Crearlos desde el repo existente, por ejemplo:

    git -C "D:\INMO CAPITAL\eretz-unified" fetch origin
    git -C "D:\INMO CAPITAL\eretz-unified" worktree add "D:\INMO CAPITAL\eretz-b" integration/eretz

Git no deja tener la MISMA rama en dos worktrees a la vez: eso refuerza la regla principal. La
cuenta que no tiene la posta deja su worktree en otra rama (o desmontado) hasta tomarla.

Ambos pueden compartir `ERETZ_DATA_ROOT` (`D:\INMO CAPITAL`), pero:
- nunca trabajar simultáneamente sobre la misma rama;
- la cola y los workers son UNO solo en la PC (los lanza el relanzador): ninguna cuenta lanza
  workers propios desde su worktree;
- un cambio a un archivo de la huella hecho en un worktree no afecta a los workers hasta que el
  worktree OPERATIVO (`eretz-unified`) lo integra: decidir eso es parte de la NEXT ACTION.
