# Runbook — rol escritor de mínimo privilegio (P18)

Estado: **PREPARADO, NO CREADO EN PRODUCCIÓN** (P18: «preparar SQL exacto, permisos
mínimos, rollback, test y runbook; no crearlo en producción»). Aplicarlo es una acción
productiva (roles/grants): la hace el usuario o una sesión con autorización explícita,
y según P19 recién después de backup fresco + restore verificado + rollback probado.

## Qué cambia y por qué

| rol | tipo | privilegios |
|---|---|---|
| `eretz_direct_property_writer` | NOLOGIN (ya existe en producción según `MASTER_PROGRESS.md`) | `SELECT, INSERT` en `internal_scraping.propiedades_raw` + `USAGE` de su secuencia; `EXECUTE` en `insert_property_safe` y `apply_property_safe_merge`. Nada directo sobre `public.propiedades`. |
| `eretz_property_loader` | **nuevo**, LOGIN, NOINHERIT, límite 2 conexiones, sin contraseña en el repo | ninguno propio; puede asumir el escritor con `SET LOCAL ROLE` dentro de una transacción |

Defecto que corrige: el canario (`scripts/property_write_canary.py`) entraba como
`eretz_preview_ro` —la credencial de **solo lectura del Preview**— y asumía el escritor.
Para eso `eretz_preview_ro` tiene que ser miembro del escritor, y entonces cualquiera con
la credencial del Preview puede escribir. La migración revoca esa membresía si existe y
el canario ahora solo entra como `eretz_property_loader` (`eretz_preview_ro` quedó en
su lista de prohibidos).

## Archivos

- `migrations/eretz_property_writer_role.sql` — fail-closed e idempotente: audita
  atributos si los roles ya existen (no los «arregla» en silencio), revoca membresías
  ajenas, fija privilegios exactos y valida lo que puede y lo que NO antes del commit.
- `migrations/eretz_property_writer_role_rollback.sql` — borra el cargador y los EXECUTE;
  el escritor vuelve a lo previo (solo se borra si lo creó la migración, por su COMMENT).
  No restaura la membresía de `eretz_preview_ro`.
- `scripts/verify_writer_role.mjs` — PostgreSQL/WASM desechable, `production_connections: 0`.

## Verificación sin producción (hecho en CLOUD, 29-09)

    cd _scratch/unification/postgres-check && npm install @electric-sql/pglite && cd -
    node scripts/verify_writer_role.mjs        # 14/14

Escenarios: base «como producción hoy» (escritor NOLOGIN con SELECT/INSERT en raw y
`eretz_preview_ro` miembro), aplicada dos veces; base limpia; y fail-closed (escritor con
`UPDATE` en `public.propiedades`, o cargador preexistente con INHERIT → aborta sin
cambios). Cada escritura permitida o prohibida se ejecuta con los privilegios del rol.
Mutaciones comprobadas: sin la revocación, o con el cargador INHERIT, la validación de la
propia migración aborta.

Limitación honesta: PGlite es mono-usuario; «quién puede asumir a quién» se prueba con
`pg_has_role(..., 'MEMBER')` (lo que consulta `SET ROLE`), no entrando con otra sesión.
No es Supabase alojado ni su pooler: el paso 4 de abajo lo prueba en el real.

## Aplicación (cuando se autorice)

Orden: `phase3_internal_scraping_schema.sql` y `property_safe_merge_audit.sql` ya
aplicadas (la migración aborta si faltan los RPC); backup + restore probados (P17/P19).

1. **Dry-run de lectura** con una credencial que pueda leer catálogos: el estado actual de
   los roles y membresías.

       select rolname, rolcanlogin, rolinherit, rolconnlimit from pg_roles
        where rolname in ('eretz_direct_property_writer','eretz_property_loader','eretz_preview_ro');
       select r.rolname as rol, m.rolname as miembro from pg_auth_members am
         join pg_roles r on r.oid = am.roleid join pg_roles m on m.oid = am.member
        where r.rolname = 'eretz_direct_property_writer';

2. **Aplicar** en el SQL Editor (o `psql -f`) con un rol que pueda crear roles:
   `migrations/eretz_property_writer_role.sql`. Si aborta, no cambió nada: leer el motivo.
3. **Contraseña**, fuera del repo y sin pegarla en ningún log:
   `\password eretz_property_loader` en `psql`. Guardar la URL en el gestor de secretos
   como `ERETZ_PROPERTY_LOADER_POOLER_URL` (pooler) o `ERETZ_PROPERTY_LOADER_URL`.
4. **Canario en validación** (hace INSERT y ROLLBACK; puede consumir valores de la
   secuencia, no toca filas):

       python scripts/property_write_canary.py --entrada <jsonl> --limite 3

   Tiene que mostrar `session_user=eretz_property_loader`, `rol asumido:
   eretz_direct_property_writer`, `UPDATE/DELETE rechazado`.
5. Recién con autorización de escritura: `--escribir`.

## Rollback

`migrations/eretz_property_writer_role_rollback.sql`. Antes, cerrar las sesiones del
cargador (`DROP ROLE` falla si tiene conexiones abiertas). Deja el escritor como estaba
(SELECT/INSERT en raw) y sin la membresía del Preview.
