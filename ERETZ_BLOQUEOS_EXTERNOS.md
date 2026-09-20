# Bloqueos que no se resuelven desde acá

**2026-09-20 · comprobados, no supuestos · `database_writes: 0`**

Ninguno detiene el resto del trabajo. Se registran acá para que el día que
haga falta desbloquearlos, no haya que volver a averiguar qué pasa.

---

## `BLOCKED_CREDENTIAL` — la credencial guardada no autentica

`Inmo-Capital-main/.env` tiene `SUPABASE_DATABASE_URL` y `INTERNAL_DB_URL`.
Existen, tienen forma válida, y **el servidor las rechaza**:

```
connection to server at "2600:1f18:...", port 5432 failed:
FATAL:  password authentication failed for user "postgre…"
```

La conexión se intentó en modo `default_transaction_read_only=on` y el valor
nunca se imprimió ni se escribió en ningún log.

No la roto ni la reemplazo: está explícitamente fuera de lo autorizado, y una
credencial rotada por un agente es un problema peor que una vencida.

**Qué habilita destrabarlo**: `pg_dump` read-only, conteos y checksums contra
producción, y la comparación posterior con el restore.

---

## `BLOCKED_TOOLING` — no hay binarios de PostgreSQL ni servidor local

Comprobado:

| | |
|---|---|
| `pg_dump`, `psql`, `pg_restore`, `initdb` en PATH | no |
| `C:\Program Files\PostgreSQL\16\bin` | existe y **sólo tiene dos DLL**, ningún `.exe` |
| Cluster en `…\16\data` | inicializado (`PG_VERSION` = 16) |
| Puerto 5432 en localhost | cerrado |
| `docker` | no disponible |
| `psycopg` en Python | **sí** |

O sea: la instalación quedó a medias —el cluster está creado y los ejecutables
no—. Sin `pg_dump` no hay backup, y sin servidor local ni `initdb` no hay
dónde restaurar.

`psycopg` alcanza para leer y contar, que es lo que se usó para comprobar la
credencial, pero **no** para producir un dump ni para probar un restore. Un
export con `SELECT` no es un backup: no trae esquema, ni índices, ni
restricciones, ni permisos, y no se puede restaurar con nada de lo que hay.

**Qué habilita destrabarlo**: reinstalar las herramientas de línea de comandos
de PostgreSQL 16, o tener Docker disponible para levantar un servidor
desechable.

---

## Lo que sí se puede hacer sin esto, y se está haciendo

- **Writer equivalence** completa contra entornos locales y PGlite, que es
  donde se validaron los 17 checks de la migración.
- Todo el trabajo de cola, certificación, identidad y ventana semántica.
- Browser QA local sobre el snapshot SQLite, sin tocar PostgreSQL.

El backup no bloquea nada de eso. Bloquea **production readiness**, y ahí sí
es uno de los últimos pasos.
