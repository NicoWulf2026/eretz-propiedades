# ERETZ — acciones productivas pendientes (READY_FOR_PRODUCTION_ACTION)

Lista única de lo que **no** se ejecuta sin el usuario: escrituras, migraciones,
permisos, deploy, DNS, restore, merge a `main`, o gasto de dinero. Todo lo
demás se hace solo. `database_writes: 0` en todo lo preparado.

Actualizado: 2026-09-25.

| # | acción | estado | qué la destraba |
|---|---|---|---|
| 1 | Credencial Postgres directa → `pg_dump` con conteos y **restore probado** | `BLOCKED_EXTERNAL_CREDENTIAL` | una credencial válida (la actual falla) |
| 2 | Credencial de mínimo privilegio `eretz_direct_property_writer` | `BLOCKED_EXTERNAL_CREDENTIAL` | crearla en Supabase |
| 3 | Aplicar migraciones locales (aditivas) | preparadas, sin aplicar | revisión + autorización; exige 1 |
| 4 | Promoción staging → main (agencias) | dry-run del 14-09, a refrescar | autorización; exige 1 |
| 5 | Corregir `url_normalizada` colapsada en producción | medido, sin tocar | autorización de write; exige 1 y 3 |
| 6 | Encender bajas del ciclo de vida | diseñado, **apagado** | decisión de producto |
| 7 | Servir la snapshot v4 en la API local | construida y verificada | decisión (el clasificador lo trata como deploy) |
| 8 | Descubrimiento pago de webs (140 `IDENTITY_PENDING`) | no corrido | aprobar gasto (~USD 1,35) |
| 9 | Merge a `main` / deploy | no corresponde todavía | después de 1–4 |

## Detalle

### 1. Backup y restore probados
Sin `pg_dump` verificable y un restore ensayado, ningún write productivo es
reversible de verdad. El acceso actual (MCP de Supabase) es de solo lectura y la
credencial Postgres directa no funciona. Ver `ERETZ_SUPABASE_READINESS.md` §3.

### 2. Escritor con mínimo privilegio
El único camino de escritura aceptado es el RPC `apply_property_safe_merge`
(lista blanca de 17 campos, identidad verificada, auditoría en la misma
transacción). La equivalencia con el REST está cerrada: el REST peligroso no
tiene consumidores y está bloqueado en las tres entradas
(`ERETZ_EQUIVALENCIA_DE_ESCRITORES.md`). Falta la credencial propia del rol.

### 3. Migraciones locales
- `migrations/property_safe_merge_audit.sql` (+ `_rollback.sql`): tabla de
  auditoría y RPC del merge seguro. Aditiva; no modifica filas.
- `migrations/property_active_state_and_quality_flags.sql` (+ `_rollback.sql`):
  contrato de estado activo público y banderas de calidad derivadas para
  `service_role`. No modifica filas.
Verificadas en PostgreSQL/WASM desechable (`scripts/verify_writer_equivalence.mjs`,
10/10; `verify_local_postgres.mjs`, 17). Nunca aplicadas en el alojado.

### 4. Promoción staging → main
`ERETZ_STAGING_PROMOTION_DRYRUN.md` (14-09): 680 agencias promovibles con su
alcance y rollback. Los números son de hace 11 días; **refrescar el dry-run
antes de autorizar**.

### 5. `url_normalizada` en producción
La normalización del volcado productivo colapsa urls que identifican la
propiedad por query: 492 propiedades caen en otra fila (`agostinelli` funde 397
en una clave, `abonapace` 92), y hay un índice sobre esa columna. El pipeline
local ya usa la normalización correcta (`_normalize_url_for_hash`). Corregirlo
es un write. Ver `ERETZ_EQUIVALENCIA_DE_ESCRITORES.md`.

### 6. Bajas
`ERETZ_PROPERTY_LIFECYCLE.md`: modo observación a propósito. Una ausencia no
es una baja (alagna: 210 → 209 fichas en media hora y la «desaparecida»
respondía 200). `mark_as_inactive` existe y no tiene consumidores.

### 7. Snapshot de la API local
Hoy se sirve una `api_snapshot_v2` del 08-09. La v4 más reciente está en
`_scratch/unification/snapshot_v4d_2026-09-25/` (ver §«Snapshot» abajo) con
índices y orden declarados (explorer 307→83 ms, combinada 900→249, mapa sin
filtros ~550→90–165) y con las reglas de calidad del runner aplicadas.
Reemplazar `D:\INMO CAPITAL\ERETZ_API_CONTRACT\ERETZ_API_SNAPSHOT.sqlite3`
(respaldo de la actual en `_anteriores/v2_2026-09-08/`).

### 8. Descubrimiento de webs
140 agencias en `IDENTITY_PENDING` (134 sin clave ERETZ, 111 sin web conocida).
La fase paga de `scripts/run_web_discovery.py` costó USD 2,38 por 250 el 14-09.
Ojo: `scripts/search_provider.py` carga `.env` por su cuenta y podría activar la
fase paga sin que se note.

### 9. Merge / deploy
Rama de trabajo: `handoff/codex-unificacion-2026-09-18`. Nada se mergea a
`main` ni se despliega sin autorización.

## Snapshot
Construida el 25-09 12:11 en `_scratch/unification/snapshot_v4d_2026-09-25/` (HEAD `b8d1f52eef`
para el constructor), `pragma integrity_check` = ok, `database_writes: 0`.

| medida | valor |
|---|---|
| propiedades | 57.665 |
| descripciones del sitio descartadas | 2.558 |
| títulos que son solo la agencia, descartados | 639 |
| cocheras por accesorio corregidas | 178 |
| textos con entidades HTML limpiados | 2.454 |
| filas con frescura desde NEEDS_FIX por campos | 4.678 (0 pérdidas medidas contra la preingestión) |

Auditoría de patrones (v4c, mismas reglas salvo el título solo-nombre): títulos = agencia
1.980 → 326 (los restantes no tienen descripción y el contrato conserva el título), descripción
repetida del sitio 898 → 0.

Latencias (v4c, en proceso, con 2 workers y un diagnóstico corriendo a la vez): explorer 92 ms,
combinada 305 ms, mapa chico 193 ms, mapa combinado 721 ms, detalle 12 ms. Medir de nuevo en
reposo antes de decidir; el 24-09 en reposo la combinada daba 249 ms.
