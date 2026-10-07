# ERETZ — auditoría de production readiness (2026-10-07)

Sprint final hacia el 12/10. **PRODUCTION_READY no significa ejecutar producción**: todo lo
productivo sigue en `READY_FOR_PRODUCTION_ACTION.md` y lo decide el usuario.
`database_writes: 0` en todo lo de abajo.

## Veredicto

| criterio (pedido 06-10, §20) | estado | evidencia |
|---|---|---|
| Writer equivalence | **DEMOSTRADA en desechable** | PGlite en memoria, `production_connections: 0`, HEAD `9b43ee6e3c`+: `verify_writer_beta.mjs` 11/11 (insert, update, NULL, cero, legado, idempotencia, matriz por campo, valor fuera de dominio, duplicado por `hash_dedup`, rollback), `verify_writer_equivalence.mjs` 10/10, `verify_writer_role.mjs` 14/14, `verify_local_postgres.mjs` 17/17 |
| Backup probado | **PROCEDIMIENTO PROBADO en local; dump productivo BLOCKED_EXTERNAL_CREDENTIAL** | 07-10: `scripts/ensayo_backup_restore.py` con PostgreSQL 16.15 oficial (pg_dump -Fc de 76.486 propiedades, 30,8 MB, sha256 y lista TOC verificadas); las dos credenciales productivas existentes fallan («password authentication failed»); produccion es PostgreSQL 17 -> hace falta `pg_dump` 17 |
| Restore probado | **PROBADO en local** (sobre un dump local; falta el dump productivo) | restore en base nueva identico al origen (conteo + md5 por tabla, RPC y permisos intactos); recovery tras dano deliberado (10.926 filas borradas, precios alterados, auditoria vaciada) identico al origen |
| Rollback / recovery | **PROBADO (snapshot)**, PROBADO en desechable (migraciones) | ensayo 07-10 sobre copia de la servida: despliegue de sprint_rc2 con QA posterior igual a la de la candidata y rollback verificado por hash (vuelve a `482de3ac…` = v4l-c); `test_desplegar_snapshot.py` 6/6; rollback no destructivo de `property_safe_merge_audit` y del rol escritor en PGlite |
| Secrets seguros | **SÍ (repo)** | barrido 06-10: HEAD solo con marcadores y fixtures de tests; 13 commits de la historia nombran el ref real del proyecto y ninguno con credencial embebida; `.env` no versionado |
| Migrations / runbooks | **PREPARADOS, sin aplicar** | `migrations/property_safe_merge_audit(.sql/_rollback.sql)`, `eretz_property_writer_role(.sql/_rollback.sql)`, `property_active_state_and_quality_flags(+rollback)`; `docs/agent/RUNBOOK_ROL_ESCRITOR.md`; `deploy/api-beta/RUNBOOK.md` |
| Release candidate | **DEFINIDO**: sprint_rc2 | READY #7c, sha256 `6ebecc0e…278ab`, 76.486 props, todos los gates en verde |
| Cutover plan | **DEFINIDO** (abajo) | |
| Post-deploy checks | **DEFINIDOS** (abajo) | automatizados en `desplegar_snapshot.py` y `activar_snapshot.py` |
| Rollback plan | **DEFINIDO** (abajo) | |

**PRODUCTION_READY = NO** solo porque falta el dump REAL de produccion: credencial valida (READY #1) y `pg_dump` 17 (produccion es PostgreSQL 17). El procedimiento entero (dump, checksum, conteos, restore, validacion, recovery) ya esta probado en local con 76.486 filas reales.
Todo lo demás está listo o probado en desechable.

## Cutover plan (orden; cada paso lo autoriza el usuario)

1. **API local (inmediato)**: servir sprint_rc2 — READY #7c, un comando con P2, respaldo,
   `os.replace` atómico, QA posterior y rollback automático.
2. **Base productiva** (exige 1): credencial de lectura → `pg_dump` con conteos y checksum →
   restore en base desechable local → validación de conteos/esquema → recién ahí READY #2
   (rol escritor de mínimo privilegio) y #3 (migraciones aditivas).
3. **API remota P21** (READY #10): cuenta de hosting; `deploy/api-beta/RUNBOOK.md`
   (volumen ≥ 2 GB con historial y rollback); subir sprint_rc2 con `activar_snapshot.py`
   (verifica sha256, integrity, filas, no sintética).
4. **Frontend Preview** (READY #12): redeploy del SHA de `integration/eretz` con
   `ERETZ_API_V2_BASE_URL` apuntando a la API remota.
5. **Escrituras productivas** (#4, #5): solo después de 2, con el escritor por RPC
   (`apply_property_safe_merge`, lista blanca de 17 columnas, auditoría en la misma transacción).

## Post-deploy checks

- API local: lo que hace `desplegar_snapshot.py` después del cambio — sha256 servida = candidata,
  `integrity_check`, conteo, benchmark de 14 casos igual al de la candidata, 0 GEO_CONFLICT en el
  mapa, medianas < 2 s; más `python scripts/qa_api_real.py --snapshot <servida>` (22 casos).
- API remota: `/readyz` 200 con `sintetica: false` y el número de propiedades de la candidata;
  `/api/health` del Preview con `api.ready: true` y el `commit` esperado; QA de navegador sobre
  ese SHA (`scripts/qa_navegador_sintetica.py --snapshot`).
- Base: conteos por tabla contra el dump previo; auditoría `property_merge_audit` por evento.

## Rollback plan

- Snapshot local: automático en `desplegar_snapshot.py` ante cualquier falla posterior (probado
  07-10 sobre copia); manual = copiar `_anteriores/<etiqueta>/ERETZ_API_SNAPSHOT.sqlite3` con
  `os.replace` y verificar el sha256 del registro `DEPLOY_*.json`.
- API remota: `activar_snapshot.py rollback` (vuelve a la anterior verificada); código: release
  anterior de fly; apagado total: `fly scale count 0` (el frontend muestra «no disponible»).
- Base: rollback NO destructivo de las migraciones (revoca EXECUTE, conserva auditoría; probado
  en PGlite) y restore desde el dump del paso 2 (pendiente de credencial).

## Lo que falta y quién lo destraba

| falta | destraba |
|---|---|
| backup + restore probados | usuario: credencial Postgres de lectura (READY #1) y permiso para instalar binarios de PostgreSQL 16 en la PC |
| servir sprint_rc2 | usuario: autorizar READY #7c |
| API remota | usuario: cuenta de hosting (READY #10) |
| Preview | quien tenga acceso a Vercel (READY #12) |
