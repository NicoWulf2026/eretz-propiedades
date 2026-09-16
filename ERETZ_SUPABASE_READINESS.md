# Supabase: qué está listo y qué no, medido

**2026-09-16 · sólo lectura · `database_writes: 0`**
Proyecto `inmolink` / `pggrvzyixyjkhfknpurg`.

---

## 1. Auditoría de seguridad (§63)

Clasificada como pide el §63. **Ningún hallazgo CRITICAL ni HIGH.**

### Lo que NO aparece, y es lo importante

No hay `rls_disabled_in_public`, no hay `security_definer_view`, no hay
secretos expuestos. Las nueve políticas que alcanzan a `anon` son **todas
`SELECT`**: no hay escritura anónima en ninguna tabla.

### MEDIUM — una asimetría real en el diseño de RLS

`propiedades` restringe a `estado = 'activa'`. Cuatro tablas satélite no:

| tabla | política | filas | de propiedades NO activas |
|---|---|---:|---:|
| `historial_precios` | `using (true)` | 5.636 | **23** |
| `property_events` | `using (true)` | 5.527 | **23** |
| `property_scores` | `using (true)` | 0 | 0 |
| `property_analysis` | `using (true)` | 0 | 0 |

Con la clave anónima se puede ver el historial de precios y los eventos de 23
propiedades que la tabla principal oculta. Es el filtro de `propiedades`
rodeado por la puerta de al lado.

Las dos vacías no filtran nada **hoy**, pero su política ya está mal escrita
para cuando se llenen. Arreglarlas antes es más barato que después.

**No bloquea la beta.** Son 23 historiales de precios, no credenciales ni datos
personales. Va cuando se toquen las políticas.

### LOW

- `propiedades` tiene **dos políticas idénticas** de `SELECT` para `anon` —
  `Public read active properties` y `propiedades_public_read`, las dos con
  `estado = 'activa'`—. No es un riesgo: es trabajo duplicado en cada consulta.
- 25 tablas con RLS activo y **sin ninguna política**. El efecto es negar todo
  salvo por `service_role`, así que es seguro por omisión. 15 de esas 25 son
  tablas `backup_*`.
- 3 extensiones en `public`: `postgis`, `pg_trgm`, `vector`.

### §57 — `propiedades` ya es pública, y conviene saberlo

El mandato dice: *"No hacer pública `propiedades` sólo para resolver
PGRST002"*. **Ya lo es**, desde antes de este bloque: `anon` la lee con
`estado = 'activa'`. No hay que exponerla; hay que no empeorarla.

`internal_scraping` no tiene ninguna política para `anon`: sigue interno, como
pide el §57.

---

## 2. Rendimiento (§64)

Nada que justifique un índice todavía. El §64 pide EXPLAIN antes de crear, y no
hay una consulta lenta identificada que lo pida.

Lo que el linter reporta, como información:

- **2 claves foráneas sin índice**, las dos en `internal_scraping`
  (`propiedades_raw`, `propiedades_staging`). Esquema interno, no de producto;
- **9 índices nunca usados**. No se tocan: "nunca usado" en una base que
  todavía no sirve tráfico real no prueba que sobren;
- **17 tablas sin clave primaria**, 15 de ellas `backup_*`. Son respaldos
  puntuales, no tablas de trabajo;
- el servidor de Auth está fijado en 10 conexiones absolutas. Si algún día se
  agranda la instancia, eso no acompaña.

---

## 3. Lo que sigue bloqueado, y por qué

| | estado |
|---|---|
| auditoría de seguridad | **hecha** |
| auditoría de rendimiento | **hecha** |
| `pg_dump` verificable | **bloqueado** — credencial Postgres directa inválida |
| restore probado | bloqueado por lo anterior |
| dry-run productivo | preparado en `ERETZ_STAGING_PROMOTION_DRYRUN.md` |
| rollback | descrito, sin ejecutar |
| writes productivos | **esperan autorización** |

El acceso que tengo es el MCP de Supabase, que es de sólo lectura. Un backup
que no se puede restaurar no es un backup, así que **no voy a llamar "listo" al
§58 hasta que exista un `pg_dump` con sus conteos y un restore probado**, y eso
necesita una credencial que hoy no funciona.

---

## 4. Lo medido de la base

```
inmobiliarias_main        7.004
inmobiliarias_staging    12.263
  promovidas alguna vez     138
propiedades             257.073
```

---

## 5. Lo que haría falta de tu lado

1. **Una credencial Postgres válida** para poder hacer `pg_dump`, contar filas
   y probar un restore. Sin eso el §58 no avanza.
2. **La autorización del write** de las 680 agencias promovibles, que sigue en
   `ERETZ_STAGING_PROMOTION_DRYRUN.md` con su alcance y su rollback.

Nada de esto lo hago sin que lo pidas.
