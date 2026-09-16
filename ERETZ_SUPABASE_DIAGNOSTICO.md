# Supabase: la credencial, PostgREST, y una corrección a lo que yo mismo escribí

**2026-09-16 · sólo lectura · `database_writes: 0` · ningún secreto impreso · nada rotado**

Tres cosas, y son independientes entre sí. Confundirlas lleva a "Supabase está
caído", que es falso: la base está perfectamente viva.

---

## 1. La credencial Postgres (§75)

El §75 pide diagnosticar sin imprimir secretos y sin rotar. Se descartó una
causa por vez, y ninguna de las sospechas obvias resultó ser el problema.

`INTERNAL_DB_URL` y `SUPABASE_DATABASE_URL` apuntan las dos a
`postgresql://postgres@db.pggrvzyixyjkhfknpurg.supabase.co:5432/postgres`
—conexión directa, usuario `postgres`, sin `sslmode` en la cadena—.

| qué se probó | resultado |
|---|---|
| ¿resuelve el host? | **sólo AAAA**. No tiene registro A: es IPv6 puro |
| ¿esta máquina tiene salida IPv6? | **sí** |
| ¿conecta TCP al 5432? | **sí, por IPv6** |
| ¿falta `sslmode=require`? | no cambia nada: mismo error con y sin |
| ¿falta el driver? | no, `psycopg` está |
| ¿project ref equivocado? | no, `pggrvzyixyjkhfknpurg` es el correcto |
| ¿formato de usuario del pooler? | no aplica: en conexión directa `postgres` es correcto |

```
OperationalError: connection to server at "2600:1f18:2e13:...", port 5432 failed:
FATAL:  password authentication failed for use...
```

**Diagnóstico: la contraseña del rol `postgres` en `.env` no es la vigente.** No
es red, no es TLS, no es driver, no es formato.

Vale la pena decir qué se descartó, porque la hipótesis natural era otra. El
host es IPv6 puro y eso suele ser la causa de este fallo —Supabase retiró el
IPv4 directo—, pero acá **hay ruta IPv6 y el puerto contesta**. Si me hubiera
quedado en la forma de la URL habría "arreglado" algo que no estaba roto.

**Qué hace falta de tu lado, y qué NO voy a hacer solo:** la contraseña vigente
se ve o se restablece desde el panel de Supabase, en *Project Settings →
Database*. Restablecerla **es una rotación** y el §22 la prohíbe sin
autorización explícita, así que no la toco. Si preferís rotarla, decímelo y te
digo exactamente qué queda que actualizar.

Mientras tanto el `pg_dump` del §76 sigue bloqueado, y con él el
`BACKUP_GATE` y el `RESTORE_GATE` del §80.

---

## 2. PostgREST devuelve PGRST002, y la base está bien

Las dos claves API —`anon` y `service_role`— devuelven lo mismo:

```
HTTP 503  {"code":"PGRST002","message":"Could not query the database for the schema cache..."}
```

Y sin embargo, por el MCP de sólo lectura, la base contesta al instante:

```
tablas en public             74
tablas en internal_scraping  12
roles de PostgREST presentes  3   (authenticator, anon, service_role)
```

**La base no está caída.** Es PostgREST el que no puede construir su caché de
esquemas, que es lo que ya se había diagnosticado antes en este repositorio
—*"PGRST002 no era una caída, era la lista de esquemas vacía"*—. Es
configuración de la API, no salud de la base, y es **un problema distinto** del
de la contraseña: no comparten causa y arreglar uno no arregla el otro.

---

## 3. Corrección: `propiedades` **no** es legible por `anon`

En `ERETZ_SUPABASE_READINESS.md` escribí:

> *"`propiedades` ya es pública, desde antes de este bloque: `anon` la lee con
> `estado = 'activa'`. No hay que exponerla; hay que no empeorarla."*

**Eso es incorrecto y lo corrijo acá.** Los grants reales:

| rol | tablas de `public` con algún privilegio |
|---|---|
| `anon` | **3**, y las tres son de PostGIS: `geography_columns`, `geometry_columns`, `spatial_ref_sys` |
| `authenticated` | las mismas 3 |
| `service_role` | todas |

```
has_table_privilege('anon','public.propiedades','SELECT')  ->  false
```

Las nueve políticas RLS que alcanzan a `anon` **existen**; lo que no existe es
el `GRANT` sobre la tabla. Una política RLS filtra filas *dentro* de un permiso
que ya se tiene: sin el `GRANT`, la política no llega a evaluarse nunca.

Mi error fue leer las políticas y concluir el acceso. Son dos capas y verifiqué
una sola.

### Qué cambia con esto

**Para seguridad, mejora.** El hallazgo MEDIUM del readiness —que `anon` podía
ver `historial_precios` y `property_events` de 23 propiedades no activas
rodeando el filtro de `propiedades`— **no es explotable hoy**: `anon` tampoco
tiene grant sobre esas tablas. La política sigue mal escrita para el día que se
otorgue el grant, así que el hallazgo se mantiene abierto, pero baja de MEDIUM
a **LOW** y deja de ser una exposición real.

**Para el producto, es un bloqueo.** Un frontend con la clave anónima no puede
leer `propiedades`. Sea porque nunca se otorgó o porque se revocó, el
`API` del §66 no funciona por esa vía tal como está.

**No lo arreglo.** Otorgar un grant a `anon` sobre una tabla de producción es
exactamente lo que el §21 prohíbe sin autorización, y además es una decisión de
diseño: puede ser que la intención sea que el frontend pase por el backend con
`service_role` y que `anon` no toque la base nunca. Esa es tu decisión, no mía.

---

## 4. Estado de los gates del §80

| gate | estado | qué lo bloquea |
|---|---|---|
| `SECURITY_GATE` | sin CRITICAL ni HIGH | el MEDIUM baja a LOW por lo de arriba |
| `BACKUP_GATE` | **bloqueado** | la contraseña de `postgres` |
| `RESTORE_GATE` | **bloqueado** | depende del anterior |
| `ROLLBACK_GATE` | descrito, sin ejecutar | depende del anterior |
| `DRY_RUN_GATE` | preparado | `ERETZ_STAGING_PROMOTION_DRYRUN.md` |

---

## 5. Lo que necesito de tu lado

1. **La contraseña vigente de Postgres**, o tu autorización para rotarla. Sin
   eso no hay `pg_dump`, y sin `pg_dump` probado con su restore no hay
   `BACKUP_GATE`. Es el único bloqueo duro del camino a producción.
2. **Una decisión sobre el acceso de `anon`**: ¿el frontend lee la base
   directamente, o pasa siempre por el backend? La respuesta define si hay que
   otorgar grants o si las nueve políticas RLS sobran.

Ninguna de las dos la resuelvo solo.
