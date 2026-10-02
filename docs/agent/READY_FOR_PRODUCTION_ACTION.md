# ERETZ — acciones productivas pendientes (READY_FOR_PRODUCTION_ACTION)

Lista única de lo que **no** se ejecuta sin el usuario: escrituras, migraciones,
permisos, deploy, DNS, restore, merge a `main`, o gasto de dinero. Todo lo
demás se hace solo. `database_writes: 0` en todo lo preparado.

Actualizado: 2026-10-01 (LOCAL, cuenta B).

| # | acción | estado | qué la destraba |
|---|---|---|---|
| 1 | Credencial Postgres directa → `pg_dump` con conteos y **restore probado** | `BLOCKED_EXTERNAL_CREDENTIAL` | una credencial válida (la actual falla) |
| 2 | Rol escritor de mínimo privilegio (P18): `eretz_property_loader` LOGIN NOINHERIT + `eretz_direct_property_writer` | **SQL + rollback + test (PGlite 14/14) + runbook LISTOS** (29-09, CLOUD); sin crear | autorización + backup/restore (1); runbook `docs/agent/RUNBOOK_ROL_ESCRITOR.md` |
| 3 | Aplicar migraciones locales (aditivas) | preparadas, sin aplicar | revisión + autorización; exige 1 |
| 4 | Promoción staging → main (agencias) | dry-run del 14-09, a refrescar | autorización; exige 1 |
| 5 | Corregir `url_normalizada` colapsada en producción | medido, sin tocar | autorización de write; exige 1 y 3 |
| 6 | Encender bajas del ciclo de vida | diseñado, **apagado** | decisión de producto |
| 7 | Servir la snapshot v4 en la API local | v4l-c servida desde 29-09 16:52. **Candidata v4m2 lista 01-10 15:xx** (lote 5 + P10 + filas servidas conservadas + retiros verificados aplicados; `_b_scratch/medicion/snap_v4m2`: 66.550 propiedades, +1.526 altas y 4 bajas todas con motivo aprobado, QA 14/14; compuertas P2 evaluadas en lectura: **0 fallas**). La cuenta B intentó el despliegue automático P2 y el control de permisos del agente lo denegó (lo trata como despliegue) | el usuario corre: `python scripts\desplegar_snapshot.py --candidata "D:\INMO CAPITAL\_b_scratch\medicion\snap_v4m2" --etiqueta-respaldo v4l-c_2026-09-29 --automatico` (aborta solo si falla una compuerta, con rollback) o autoriza al agente |
| 8 | Descubrimiento pago de webs (140 `IDENTITY_PENDING`) | no corrido | aprobar gasto (~USD 1,35) |
| 9 | Merge a `main` / deploy | no corresponde todavía | después de 1–4 |
| 10 | API v2 beta remota (P21) | **contenedor + runbook LISTOS** (29-09, CLOUD; docker verificado con snapshot sintética); sin desplegar. Tamaño medido 01-10: servida v4l-c **558 MB** (candidata de hoy 571 MB) → volumen ≥ 2 GB (3× con historial y rollback) | `EXTERNAL_ACCOUNT_REQUIRED` (cuenta/pago de hosting); `deploy/api-beta/RUNBOOK.md` |
| 11 | P18: ¿`eretz_preview_ro` es miembro de `eretz_direct_property_writer`? (solo lectura) | **UNABLE_TO_VERIFY** 01-10: `ERETZ_PREVIEW_RO_URL` no está definida en la PC; la lectura con la credencial legada fue denegada por el control de permisos del agente | el usuario define `ERETZ_PREVIEW_RO_URL` (credencial de solo lectura) o autoriza la consulta READ ONLY con la credencial existente: `python scripts/cloud_bridge/p18_chequeo_lectura.py`. Si da YES: priorizar 2 (requiere 1) |
| 12 | Redeploy del frontend (Preview en Vercel) con next 16.3.8 | parche de seguridad commiteado (`3d9fb63`, GHSA-vcvr-r3jv-pc5j, RCE en next/og; el sitio usa opengraph-image) | `BLOCKED_EXTERNAL_VERCEL_ACCESS` (P22): redeploy del SHA de `integration/eretz` por quien tenga acceso |
| 7b | **AVISO sobre la candidata v4m2 (accion 7)** | Regression Gate de snapshots (`scripts/gate_de_snapshots.py`, 02-10) servida v4l-c contra v4m2: **336 perdidas sin explicar**, 186 en `inmobiliaria pennacchio` (superficie_total 101, barrio 34). Causa: si el ULTIMO cierre de una agencia es NEEDS_FIX no-de-campo (pennacchio: «second run is not idempotent»), el builder no tiene paquete fresco confiable y rearma la fila desde la base de preingestion, MAS VIEJA, perdiendo valores del ultimo certificado que la servida si tiene. Las compuertas P2 no lo ven (miran altas/bajas, no campos). En correccion. | **no desplegar v4m2** hasta la candidata corregida; la servida v4l-c sigue siendo la mejor |
| 13 | Espacio en disco D: (LOCAL) | **RIESGO** medido 01-10 21:00: **4,1 GB libres de 116 GB**. Cada candidata de snapshot ocupa ~0,55 GB y la cola escribe paquetes continuamente. Descartables (mediciones de B, ya volcadas a `lotes/README.md`): `_b_scratch/medicion/snap_base`, `snap_p10`, `snap_p10b`, `snap_v4m` (~2,2 GB). **Conservar `snap_v4m2`** (candidata de la accion 7). El agente no borra archivos por su cuenta | el usuario borra esas 4 carpetas (o mueve `_b_scratch` a otro disco) y revisa `Inmo-Capital-main` (27,8 GB); `eretz-unified` (16,7 GB) es el nodo operativo: NO borrar |

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
**Desplegada la v4g el 28-09 16:58** (autorización del usuario del 28-09). Registro completo:
`D:\INMO CAPITAL\ERETZ_API_CONTRACT\_despliegues\DEPLOY_2026-09-28T16-58-08.json`.
- Antes: servida `api_snapshot_v2` del 08-09, sha256 `e12a8f36…4b1990`, 449.994.752 bytes,
  57.665 propiedades, integrity ok; respaldo `_anteriores/v2_2026-09-08/` verificado por hash
  idéntico; ningún proceso con la servida ni la candidata abiertas (apertura exclusiva).
- Inventario: 0 ids sólo en la servida, 0 sólo en la candidata, 0 agencias con conteo distinto.
- Cambio: copia a `.incoming` + fsync + hash + `os.replace` atómico (no se reconstruyó en destino).
- Después: sha256 `57fa64c8…11bcca2` = candidata, integrity ok, 57.665 propiedades, 546
  agencias; QA de API 14/14 igual (estado y total por caso) a la de la candidata; 478
  GEO_CONFLICT y 0 en el mapa. Medianas en frío, con 2 workers: explorer 168 ms, combinada 414,
  mapa chico 302, mapa combinado 1.254, detalle 13, lote de 100 60 (≈2× la QA en caliente de la
  candidata; bajo el umbral de 2 s).
- Rollback manual: copiar `_anteriores/v2_2026-09-08/*` sobre `ERETZ_API_CONTRACT/` (sha
  esperado `e12a8f36…`). Mecanismo reutilizable: `scripts/desplegar_snapshot.py`.

**Candidatas v4l-a y v4l-b — LISTAS, pendientes de autorización (READY_FOR_ACTION)** (29-09).
Reemplazan a la v4k (la incluyen: las 121 del exterior + 2 emprendimientos de Uruguay que la
extracción nueva marcó). Novedad: la snapshot ya no sirve solo la preingestión del 03-09.
- **Suma** lo que los inventarios certificados vigentes (ledger, NEXT-001) saben y el 03-09 no:
  **+9.330 propiedades, +50 agencias** (52 certificadas no tenían ninguna servida). Regla
  conservadora (`scripts/snapshot_certificadas.py`): no se suma si hay CUALQUIER señal de que ya
  está (hash, URL, `source_listing_id`, número de la URL, mismo título+precio+superficie+dorm).
  Duplicados probables que involucran nuevas: 4, revisados a mano (años en la URL, ids
  consecutivos de fichas distintas, y `cavacini` que publica la misma casa con dos ids).
- **Refresca** 5.935 avisos cuya URL cambió (Tokko rehace el slug con el título) sobre la fila ya
  servida, sin cambiar su id.
- **Geografía de la fila servida**: se recalcula sobre la lectura fresca (14.951 filas);
  localidades **9.494 → 18.507** (v4l-a). Una localidad demostrada no se pierde por un vacío (115).
- 0 fuera del país por polígono, 0 precios simbólicos, integrity ok, QA de API 14/14 con el
  mismo estado que la v4k, 0 GEO_CONFLICT en el mapa (628 en total: +107 de `analia requena`,
  cuya ficha publica provincia «CABA» con Santa Clara del Mar; fail-closed como las demás).

| | v4l-a (solo suma) | v4l-b (suma y retira) |
|---|---|---|
| carpeta | `_scratch/unification/snapshot_v4l_a_2026-09-29/` | `_scratch/unification/snapshot_v4l_b_2026-09-29/` |
| propiedades | 66.841 | 64.202 |
| retira | 123 del exterior | 123 del exterior + **2.637 que ya no están en el inventario COMPLETO vigente de su agencia** |
| agencias | 596 | 595 |

Las 2.637 de la v4l-b: muestra de 30 en vivo, **25 dan 404 o redirigen sin la ficha** y 5 siguen
visibles. Retirarlas saca ~2.200 enlaces muertos del buscador a cambio de ~450 vivas que el
inventario completo de su agencia ya no lista. Recomendación: **v4l-b**.

Comandos (uno de los dos):
`python scripts\desplegar_snapshot.py --candidata _scratch\unification\snapshot_v4l_b_2026-09-29
--etiqueta-respaldo v4j_2026-09-28 --faltantes-esperados 2760 --nuevos-esperados 9328`
`python scripts\desplegar_snapshot.py --candidata _scratch\unification\snapshot_v4l_a_2026-09-29
--etiqueta-respaldo v4j_2026-09-28 --faltantes-esperados 123 --nuevos-esperados 9330`
(`--nuevos-esperados` es nuevo: el script abortaba ante cualquier id nuevo; ahora exige el
número exacto auditado.)

**Candidata v4k — SUPERADA por la v4l (no desplegar)** (29-09,
`_scratch/unification/snapshot_v4k_2026-09-28/`): la v4j servida menos 121 fichas del exterior que
la v4j todavía publicaba, TODAS verificadas: 116 con coordenada fuera del polígono oficial del país
(IGN `ign:pais`; 115 Uruguay -`enlaze` 88 «Centro (Montevideo)», Punta del Este de `lopez baena`,
`vanzini`, `farina`, `forja`, `vidal`, `o feely`...- y 1 Paraguay) y 5 de Miami sin coordenada
(Brickell, Bal Harbour, Miami-dade). integrity ok, 57.513 propiedades, 152 exterior excluidas, 0
precios simbólicos, QA 14/14 con el mismo estado que la v4j, 0 GEO_CONFLICT en el mapa (510);
medianas explorer 85 ms, combinada 253, mapa combinado 567, detalle 8. Comando:
`python scripts\desplegar_snapshot.py --candidata _scratch\unification\snapshot_v4k_2026-09-28
--etiqueta-respaldo v4j_2026-09-28 --faltantes-esperados 121`
(los 121 auditados arriba; la candidata declara 152 porque la v4j ya excluía 31).

**v4j DESPLEGADA el 28-09 22:58** (autorización del usuario del 28-09). Registro:
`ERETZ_API_CONTRACT/_despliegues/DEPLOY_2026-09-28T22-58-11.json`. Respaldo de la v4g (sha
`57fa64c8…`) en `_anteriores/v4g_2026-09-28/`, verificado por hash; inventario: 31 ids menos
(exactamente los 31 del exterior declarados por la candidata), 0 nuevos. Después: sha = candidata
(`d188fa06…`), integrity ok, 57.634 propiedades, QA 14/14 igual a la de la candidata, 510
GEO_CONFLICT y 0 en el mapa, 0 conflictos con coordenadas servidas, 0 precios simbólicos, 19 de
`cantale` en CABA, 55 de `blanco` sin afirmar «Buenos Aires». Medianas: explorer 88 ms, combinada
257, mapa chico 138, mapa combinado 548, detalle 9. Sin rollback.
**Hallazgo post-deploy**: siguen servidas ~116 fichas con coordenadas en Uruguay (115) y Paraguay
(1) y 6 de Miami sin coordenadas: la caja de coordenadas (-74..-53) cubre Uruguay. Arreglado en el
código (contención en el polígono oficial del país, IGN `ign:pais`); entra en la próxima candidata.
Rollback manual: copiar `_anteriores/v4g_2026-09-28/*` sobre `ERETZ_API_CONTRACT/`.

Candidata v4j (28-09 21:37,
`_scratch/unification/snapshot_v4j_2026-09-28/`): todo lo de la v4i (abajo) + 42 precios simbólicos
descartados (US$1, ventas por USD 460) + lo recertificado hasta las 21:37. integrity ok, 57.634
propiedades, QA 14/14 con el mismo estado que la v4g, 0 GEO_CONFLICT en el mapa (510 en total);
medianas explorer 89 ms, combinada 246, mapa combinado 554, detalle 8. Comando:
`python scripts\desplegar_snapshot.py --candidata _scratch\unification\snapshot_v4j_2026-09-28
--etiqueta-respaldo v4g_2026-09-28 --exclusiones-declaradas exterior_conservadas_no_publicadas`

Candidata anterior v4i (28-09 18:02,
`_scratch/unification/snapshot_v4i_2026-09-28/`): integrity ok, 57.634 propiedades, QA de API
14/14 con el mismo estado que la v4g, 0 GEO_CONFLICT en el mapa (510 en total). Diferencia con la
servida v4g, TODA explicada:
- −31 del exterior (política ARGENTINA_ONLY; hoy se sirven con geografía argentina inventada:
  Miami como «Buenos Aires / Pilar»);
- 55 `blanco` «CABA» + provincia «Buenos Aires» sin coordenadas: dejan de afirmar Buenos Aires
  (GEO_CONFLICT, fail-closed);
- 19 `cantale` pasan a CABA confirmada por el polígono del IGN;
- 4 «departamento de la provincia declarada» recuperan su provincia (Junín/San Luis, General Paz).
Comando (el intento automático fue denegado por el control de permisos: es un deploy):
`python scripts\desplegar_snapshot.py --candidata _scratch\unification\snapshot_v4i_2026-09-28
--etiqueta-respaldo v4g_2026-09-28 --exclusiones-declaradas exterior_conservadas_no_publicadas`
(respalda la v4g, reemplaza atómicamente, QA y rollback automático).

Historia previa: se servía una `api_snapshot_v2` del 08-09. La candidata era la **v4g**
(`_scratch/unification/snapshot_v4g_2026-09-28/`, ver §«Snapshot»). La v4 base está en
`_scratch/unification/snapshot_v4e_2026-09-25/` (ver §«Snapshot» abajo) con
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
**v4g** (28-09 15:35, `_scratch/unification/snapshot_v4g_2026-09-28/`, `integrity_check` ok,
`database_writes: 0`; la servida del 08-09 verificada intacta antes y después): mismas 57.665
propiedades. Contra la v4f: operación 49.475 → 50.522, precio 52.372 → 52.867, tipo 52.992 →
53.406, dormitorios 34.519 → 34.914, superficie total 19.161 → 21.062, coordenadas 42.560 →
42.714; frescura parcial 5.429 → 5.721. Toma las recertificaciones hechas hasta las 15:35 del
28-09 (la recertificación de todo el lote del día sigue en curso). QA de API (in-process,
`scripts/benchmark_unified_api.py`, 15:4x): 14/14 con el estado esperado (400 ventana, 422 orden
inválido, 200 vacío); mediana explorer 83 ms, combinada 267, mapa chico 154, mapa combinado 602,
detalle 8, lote de 100 21; 478 GEO_CONFLICT y 0 en el mapa. Salida: `API_BENCHMARK.json` en la
carpeta. Reemplazar la servida sigue siendo un deploy: decide el usuario.

**v4f** (25-09 23:57, `_scratch/unification/snapshot_v4f_2026-09-26/`, integrity ok,
`database_writes: 0`): mismas 57.665 propiedades que la v4e; frescura desde NEEDS_FIX por campos
5.358 → 5.429 y 165 cocheras incoherentes resueltas por la regla de coherencia. Los arreglos de
la noche del 25-09 (bottai, battista, cuini, WordPress→generico, Terravirtual…) entran cuando la
cola recertifique esas agencias: reconstruir entonces (v4g) antes de proponer el reemplazo.
Comando: `python scripts/api_snapshot.py --salida <carpeta en _scratch>` — **sin `--salida`
escribe en la ruta servida** (= deploy).
QA de API en proceso sobre la v4f (`scripts/benchmark_unified_api.py`, 00:0x, con 2 workers
corriendo): 14/14 casos con el estado esperado (400 ventana, 422 orden inválido, 200 vacío);
mediana explorer 201 ms, combinada 260 ms, mapa chico 184 ms, mapa combinado 620 ms, detalle
8 ms, lote de 100 22 ms; 476 GEO_CONFLICT y 0 de ellos en el mapa. Salida:
`_scratch/unification/snapshot_v4f_2026-09-26/API_BENCHMARK.json`. No es TTFB remoto.

Detalle de la v4e:
Construida el 25-09 17:16 en `_scratch/unification/snapshot_v4e_2026-09-25/`,
`pragma integrity_check` = ok, `database_writes: 0`. Reemplaza a la v4d (misma base, más reglas).

| medida | valor |
|---|---|
| propiedades | 57.665 |
| descripciones del sitio descartadas | 2.492 |
| títulos que son solo la agencia, descartados | 639 |
| cocheras por accesorio corregidas | 177 |
| textos con entidades HTML o mojibake limpiados | 2.723 (descripciones con «Ã»: 89 → 4) |
| filas con frescura desde NEEDS_FIX por campos | 5.358 (0 pérdidas medidas contra la preingestión en la v4c) |

Patrones que quedan (auditoría sobre la v4e): título = agencia 215 filas en 16 agencias (sin
descripción: el contrato conserva el título), 104 «cochera» sin forma accesoria en el título, 25
URLs de listado heredadas de la preingestión, 3 geografías con entidades.

Latencias (v4c, en proceso, con 2 workers y un diagnóstico corriendo): explorer 92 ms,
combinada 305 ms, mapa chico 193 ms, mapa combinado 721 ms, detalle 12 ms. Medir de nuevo en
reposo antes de decidir; el 24-09 en reposo la combinada daba 249 ms.
