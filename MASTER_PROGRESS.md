# ERETZ Propiedades — MASTER PROGRESS

Estado vivo de la misión integral. Se actualiza al cerrar cada frente y antes
de cualquier corte de sesión.

**Última actualización:** 2026-08-17 (puente DB operativo; campaña exhaustiva en curso)

---

## Situación de una línea

El bloqueo de base **se resolvió**: el puente `eretz_agency_coverage_writer`
funciona y quedó verificado 7/7. El frente abierto ahora es la campaña
exhaustiva de Roomix, que necesita ~51 horas de crawl cortés.

## Puente DB — VERIFICADO Y OPERATIVO

Entrada por `SUPABASE_DATABASE_URL` (`eretz_preview_ro`), que es miembro NOINHERIT
de `eretz_agency_coverage_writer`. Los privilegios sólo existen dentro de una
transacción con `SET LOCAL ROLE`.

Dos cosas hubo que resolver para que funcionara:

1. `eretz_preview_ro` no puede leer staging por sí solo, así que **toda** lectura
   de staging va elevada, no sólo las escrituras.
2. El rol de entrada trae `default_transaction_read_only` activo: la transacción
   nacía de sólo lectura y el INSERT fallaba pese a tener el privilegio. Se
   levanta con `SET LOCAL transaction_read_only = off` como primera sentencia de
   la transacción. Nunca a nivel de sesión: con pooler, un cambio persistente lo
   heredaría la siguiente consulta que tome esa conexión física.

Pruebas de privilegio, todas correctas:

| Operación | Esperado | Real |
|---|---|---|
| SELECT main | permitido | permitido |
| SELECT staging | permitido | permitido |
| INSERT staging | permitido | permitido |
| INSERT main | denegado | `permission denied` |
| UPDATE staging | denegado | `permission denied` |
| DELETE staging | denegado | `permission denied` |
| CREATE TABLE | denegado | `permission denied` |

Los negativos se comprueban intentándolos y revirtiendo; ninguno escribió nada.

## Dos contadores que NO son el mismo

Se compararon como si fueran una sola serie y pareció que las entidades habían
bajado de 4.613 a 4.194. Nunca bajaron: 4.613 era el contador vivo del crawler a
16.920 fichas, y 4.194 era `publishers.jsonl`, un archivo congelado el 14/08 con
14.120 fichas que desde entonces no se regeneró. Dos fotos de momentos
distintos.

Quedan separados y no se vuelven a mezclar:

| Métrica | Definición | Valor |
|---|---|---|
| `RAW_PUBLISHER_IDENTITIES` | `agent_id` distintos, tal como los emite Roomix | 4.708 |
| `CANONICAL_PUBLISHER_ENTITIES` | tras unir los `agent_id` que son la misma entidad | 4.666 |
| **Entidades inmobiliarias** | INMOBILIARIA + oficina de franquicia | **3.296** |

El primero es siempre ≥ el segundo. 42 alias fusionados hasta ahora.

## KPI del crawl

**Nuevas entidades inmobiliarias únicas por 1.000 fichas.** Cuenta INMOBILIARIA
y oficina individual de franquicia; no cuenta agente, marca genérica sin
oficina, desarrolladora, unknown ni garbage.

Se mide por ventana, nunca como acumulado, y **no se usa como criterio de
corte**. `scripts/coverage_windows.py`.

## Campaña exhaustiva de Roomix — EN CURSO

**No existe fuente exhaustiva de publicadores.** El `sitemap_index.xml` tiene 13
sitemaps —static, blog, buscar, edificios, landings, venta, barrios y 6 de
propiedades—. Ninguno enumera agencias; los landings son páginas SEO por zona y
tipo. El publicador sólo aparece en el payload RSC de cada ficha, así que
exhaustivo significa recorrer las 168.563.

| | |
|---|---|
| Universo | 168.563 fichas |
| Procesadas | 14.120 |
| Restantes | 154.443 |
| Ritmo medido | 3.033 fichas/hora (2 navegadores) |
| **ETA** | **~51 horas ≈ 2,1 días** |

Lanzada como proceso aislado (la tanda 2 murió por compartir consola).
Reanudable e idempotente vía `state.json`.

---

## Git

| | |
|---|---|
| Repo | `D:\INMO CAPITAL` (multi-worktree) |
| Worktree activo | `D:\INMO CAPITAL\eretz-agency` |
| Branch | `feat/roomix-agency-coverage` |
| Tree | limpio |

### Worktrees

| Ruta | Branch | HEAD | Sucio |
|---|---|---|---|
| `Inmo-Capital-main` | `release/eretz-private-preview` | `8521d47008` | **92 archivos** |
| `eretz-agency` | `feat/roomix-agency-coverage` | ver HEAD actual | no |
| `eretz-integration` | `integrate/eretz-pre-main` | `bd3f37c333` | no |
| `eretz-main` | `main` | `e9630f5f70` | no |
| `eretz-rescue` | `integrate/release-dirty-recovery` | `b6c326b0ce` | no |
| `Inmo-Capital-frontend-phase-a` | `feat/eretz-frontend-phase-a` | `fe85455fb4` | no |
| `eretz-audit` | detached | `8521d47008` | no |

`origin/main` = `15e81991c0`, por delante de `main` local (`e9630f5f70`).
`rescue/release-worktree-integrated` = `4a95a44fab`.

Tags: `roomix-fidelity-v1`, `checkpoint/main-pre-integration`,
`checkpoint/main-pre-rescue`, `checkpoint/release-pre-integration`.

Sin push. Sin merge. `main` intacta.

### Clasificación de ramas (Fase 14)

`main` local está **163 commits por delante** de `origin/main` y 0 por detrás:
todo el rescate y la integración previa ya viven en `main` local, sin publicar.

| Rama | Commits sobre `main` | Exclusivos vs agency | Categoría |
|---|---|---|---|
| `feat/roomix-agency-coverage` | 18 | — | **KEEP** (base de integración) |
| `feat/eretz-frontend-phase-a` | 7 | 7 | **KEEP** (único frontend no contenido) |
| `integrate/eretz-pre-main` | 0 | 0 | **ALREADY_PRESENT** |
| `rescue/release-worktree-integrated` | 4 | 0 | **ALREADY_PRESENT** — el rescate ya está contenido |
| `integrate/release-dirty-recovery` | 3 | — | **NEEDS_REVIEW** |
| `release/eretz-private-preview` | 2 | — | **NEEDS_REVIEW** (worktree sucio, 92 archivos) |

Lectura para la Fase 15: la base correcta de `integration/eretz-rc` es la rama
de agency, que ya contiene el rescate, más los 7 commits de frontend por
cherry-pick. Los fixes del rescate no se pierden: ya están.

---

## Acceso a base — el hecho que gobierna todo

Las variables de Preview están marcadas **Sensitive**, y Vercel no las devuelve
nunca: ni `vercel env pull` ni `vercel env run` las entregan. La base sólo es
alcanzable desde dentro de un deployment.

Medido el 2026-08-17 desde un deployment de Preview:

| Conexión | Rol efectivo | Alcance |
|---|---|---|
| `SUPABASE_DATABASE_URL` | `eretz_preview_ro` | SELECT sobre main (7.003 filas visibles bajo RLS). **staging denegado.** |
| `ERETZ_WRITE_DATABASE_URL` | `eretz_app_writer` | **no autentica**: `password authentication failed` |

Ese fallo de autenticación es la prueba positiva de que la variable ya **no**
usa `postgres`: el usuario que llega a la base es `eretz_app_writer`. Falta que
la contraseña del rol coincida.

### Estado real de las credenciales

- Contraseña nueva: generada, cargada en `ERETZ_WRITE_DATABASE_URL` (Preview).
- Plaintext local: **eliminado** por pedido explícito.
- Entregada como **verificador SCRAM-SHA-256** cifrado con RSA-OAEP.
- `ALTER ROLE` en PostgreSQL: **nunca ejecutado**.

Consecuencia: la contraseña sólo la conoce quien tenga la clave privada. No es
recuperable desde acá.

---

## BLOCKER_DB_ADMIN_PASSWORD_ROTATION

**Único bloqueo humano de la misión.** Gatea las fases 3 (ejecución), 4, 6, 7, 8
y la mitad de la 9.

Para desbloquear, aplicar por el canal administrativo de Supabase el verificador
SCRAM ya entregado:

```sql
ALTER ROLE eretz_app_writer PASSWORD '<verificador SCRAM-SHA-256 entregado>';
```

Después de eso, un deployment de Preview nuevo debería autenticar como
`eretz_app_writer` y todo lo construido queda ejecutable.

Bloqueo secundario: `eretz_preview_ro` no puede leer `inmobiliarias_staging`, lo
que impide la auditoría de staging aunque se resuelva lo anterior. Requiere
SELECT sobre staging para algún rol alcanzable.

---

## Estado de datos conocido

| | |
|---|---|
| `inmobiliarias_main` | 7.004 filas (7.003 visibles bajo RLS) |
| `inmobiliarias_staging` | 11.798 filas |
| — de las cuales `roomix_agency_coverage` | 260 |
| — `zonaprop_inmobiliarias` | 9.040 |
| — `excel_colegio_cpi_cordoba` | 2.498 |
| main con `nombre_normalizado` NULL | 1.983 de 7.003 visibles |

Rollout de Agency Coverage: **cerrado**, no repetir. 1.635 candidatas → 260
insertadas, 1.290 ya en staging, 74 ya en main, 0 duplicados, 0 errores.

---

## Fases

| # | Frente | Estado |
|---|---|---|
| 0 | Inventario | **hecho** |
| 1 | `ERETZ_WRITE_DATABASE_URL` | **parcial** — ya no es `postgres`; falta el `ALTER ROLE` |
| 2 | 31 colisiones | **hecho** — clasificadas, manifest fuera del repo |
| 3 | Backfill `nombre_normalizado` | **código hecho y probado**; ejecución bloqueada |
| 4 | Auditoría de staging | **desbloqueada** — staging legible vía puente |
| 5 | Motor de dedupe | **hecho** — 20 tests |
| 6 | Pipeline staging→main | pendiente (depende de 4) |
| 7 | Franquicias | pendiente |
| 8 | Agentes y desarrolladoras | pendiente |
| 9 | Métricas de cobertura | **parcial** — terminología documentada; recálculo bloqueado |
| 10 | Crawl exhaustivo Roomix | **en curso** — 14.120/168.563 |
| 11 | Cierre estructural CSS | pendiente |
| 12 | Identity V2 | pendiente |
| 13 | Auditoría repo ↔ Supabase | pendiente |
| 14 | Ordenar branches | **hecho** — clasificadas arriba |
| 15 | Rama de integración | pendiente |
| 16 | Release Candidate | pendiente |
| 17 | Preview RC | pendiente |
| 18 | Production readiness | pendiente |
| 19 | Documentación | en curso |

---

## Artefactos fuera del repo

`D:\INMO CAPITAL\ERETZ_AGENCY_DATA\`

- `collision_manifest_staging_main.jsonl` — 31 pares crudos
- `collision_manifest_classified.jsonl` — 31 clasificados con evidencia
- `staging_rows.jsonl` — 1.635 candidatas del rollout
- `crosswalk.jsonl`, `publishers.jsonl`, `observations.jsonl`, `state.json`

---

## Deployments

Todos los Preview temporales creados durante la misión fueron eliminados y
responden 404. Production **intacta y sin variables de entorno** (0 en
Production, 0 en Development, 8 en Preview).

Incidente registrado: un `vercel deploy` sin link creó un proyecto `frontend`
accidental cuyo primer deploy fue a Production y **falló en build**. Ambos
deployments fueron eliminados; el proyecto vacío quedó porque el borrado de
proyectos está denegado por el clasificador de permisos.

---

## Próxima acción exacta

1. Aplicar el verificador SCRAM (ver bloqueo arriba).
2. Conceder SELECT sobre `inmobiliarias_staging` a un rol alcanzable.
3. Correr `scripts/backfill_main_normalizado.py` en dry-run contra datos reales,
   revisar conflictos, y recién después `--commit`.
4. Con staging legible: Fase 4 (auditoría) → Fase 6 (pipeline).
