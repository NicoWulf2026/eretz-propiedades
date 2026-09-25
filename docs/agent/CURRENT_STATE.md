# ERETZ — estado actual

Estado VIGENTE, no bitácora. La historia está en Git (`git log`; la bitácora anterior de este
archivo: `git show 6ee927bb80:docs/agent/CURRENT_STATE.md`). `database_writes: 0` en todo.

**Actualizado:** 2026-09-25 17:05 · **Rama:** `handoff/codex-unificacion-2026-09-18` (push solo acá)
**Fase:** certificación/recertificación continua + calidad de lo servido + preparación productiva.

## Cola de certificación
| pieza | qué hace | dónde |
|---|---|---|
| 2 workers | certifican; paran entre agencias ante banderas o cambio de huella | `scripts/run_agency_certification_queue.py` |
| `ERETZ_relanzador` (cada 10 min) | relanza si es seguro, acota paros a familias, libera familias | `scripts/relanzar_la_cola.py` vía pythonw |
| `ERETZ_vigilante_paros` (cada 5 min) | alerta paros desatendidos y familias detenidas > 12 h | `scripts/vigilante_de_paros.py` |

- 2 workers vivos; paros de la tarde diagnosticados y diferidos. Cada commit de huella los relanza.
- Paros: `FAMILIA` detiene la familia; `COMPARTIDO` con causa nombrada detiene todo;
  `COMPARTIDO/sin_determinar` detiene su familia. Se libera con diferida firmada posterior o con
  cambio de huella. Libro: `ERETZ_FAMILIAS_DETENIDAS.jsonl`.
- Orden: conocidas por `checked_at` ascendente, intercaladas 1:1 con nuevas.

## Resultados (paquetes en `ERETZ_AGENCY_CERTIFICATION_20260827/agencies`, 14:00)
| estado | agencias |
|---|---|
| CERTIFIED_COMPLETE | 157 |
| CERTIFIED_BEST_AVAILABLE | 17 |
| NEEDS_FIX | 117 |
| BLOCKED_EXTERNAL | 44 |
| IDENTITY_PENDING | 140 |
| NO_INVENTORY_CONFIRMED | 1 |

Los cambios del 25-09 (source_policy, base, generico, wasi) invalidaron certificaciones: la
rotación las recertifica sola.

## Calidad
- Regression Gate (16:3x): 217 agencias recertificadas, 0 pendientes tras firmar 5.
- Suite completa (16:5x): 3.302 passed.

## Snapshot de la API local
- Servida: `api_snapshot_v2` del 08-09 (`D:\INMO CAPITAL\ERETZ_API_CONTRACT\`). Reemplazarla = deploy.
- Lista para servir: `_scratch/unification/snapshot_v4d_2026-09-25/` — 57.665 propiedades,
  `integrity_check` ok, reglas de calidad del runner + frescura desde NEEDS_FIX por campos.
  Detalle y latencias en `READY_FOR_PRODUCTION_ACTION.md` §7.

## Producción
Nada escrito. Bloqueos: credencial Postgres directa (`BLOCKED_EXTERNAL_CREDENTIAL`), sin
`pg_dump` con restore probado. Lista única: `docs/agent/READY_FOR_PRODUCTION_ACTION.md`.

## Tareas inmediatas
Ver `docs/agent/HANDOFF.md` § «Próxima prioridad».
