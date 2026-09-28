# ERETZ — estado actual

Estado VIGENTE, no bitácora. La historia está en Git (`git log`; la bitácora anterior de este
archivo: `git show 6ee927bb80:docs/agent/CURRENT_STATE.md`). `database_writes: 0` en todo.

**Actualizado:** 2026-09-28 14:4x · **Rama:** `handoff/codex-unificacion-2026-09-18` (push solo acá)
**Fase:** certificación/recertificación continua + calidad de lo servido + preparación productiva.

## Automatización (ERETZ AUTOMATION)
Encender/apagar TODO: `ERETZ_AUTOMATION_ON.cmd` / `ERETZ_AUTOMATION_OFF.cmd` en la raíz del repo.
Detalle, estado y cómo apagar a mano: `docs/agent/ERETZ_AUTOMATION.md`.
Ver estado: `python scripts\eretz_automatizacion.py estado`.

| pieza | qué hace | dónde |
|---|---|---|
| 2 workers (máx.) | certifican; paran entre agencias ante banderas o cambio de huella | `scripts/run_agency_certification_queue.py` |
| tarea `ERETZ_relanzador` (10 min + al iniciar sesión) | relanza los que falten, acota paros a familias, libera familias | `scripts/relanzar_la_cola.py`, pythonw |
| tarea `ERETZ_vigilante_paros` (5 min + al iniciar sesión) | escribe `ERETZ_QUEUE_WATCH_STATUS.json`, `--sin-alerta` (sin popups) | `scripts/vigilante_de_paros.py`, pythonw |
| interruptor `ERETZ_AUTOMATION_OFF.json` | si existe, ni el relanzador ni el runner arrancan nada | `scripts/interruptor_eretz.py` |

- Paros: `FAMILIA` detiene la familia; `COMPARTIDO` con causa nombrada detiene todo;
  `COMPARTIDO/sin_determinar` detiene su familia. Se libera con diferida firmada posterior o con
  cambio de huella. Libro: `ERETZ_FAMILIAS_DETENIDAS.jsonl`. Radio `APAGADO` = lo puso el OFF.
- Orden: conocidas por `checked_at` ascendente, intercaladas 1:1 con nuevas.

## Resultados (paquetes en `ERETZ_AGENCY_CERTIFICATION_20260827/agencies`, 28-09 14:4x)
| estado | agencias |
|---|---|
| CERTIFIED_COMPLETE | 260 |
| CERTIFIED_BEST_AVAILABLE | 35 |
| NEEDS_FIX | 183 |
| BLOCKED_EXTERNAL | 48 |
| IDENTITY_PENDING | 140 |
| NO_INVENTORY_CONFIRMED | 1 |

Recertificación completa en curso desde el 28-09 07:29; los lotes compartidos del día
(`021907caea`, `1b6cf264f7`, `3e1081b107`, `8a8d0b193f`) la reinician por huella.

## Decisiones registradas (28-09)
- **Identidad**: dos agencias con la MISMA web oficial → `IDENTITY_PENDING` con motivo
  `IDENTITY_REVIEW` (hoy solo `martinez negocios inmobiliarios` / `martinez propiedades`,
  inmueblesmartinez.com.ar). No se fusionan ni se atribuye inventario sin evidencia.
- **Exterior**: propiedades publicadas fuera de Argentina se conservan enteras con
  `extra.publicacion_exterior = PRODUCT_DECISION_PENDING`, `pais_publicado`, evidencia y lo
  publicado (`ciudad/barrio/provincia_publicada`); no se les afirma geografía argentina. La
  política de publicación NO cambió (decide producto). 30 fichas de 12 agencias medidas.

## Calidad
- Regression Gate (28-09 09:5x): 461 agencias recertificadas, 0 pendientes (77 firmadas: echesortu 42 fotos WhatsApp-Image → DEFECTO_ARREGLADO en e9e6c7f709, 1 CORRECCION «BAÑO 3ER PISO»; ente 34 dormitorios/baños → DEFECTO_PENDIENTE, ver HANDOFF). Gate anterior 06:4x: 448, 280 firmadas.
- Suite completa (28-09 14:3x, `8a8d0b193f`): 3.445 passed (+ fix de huella de `exterior.py`).

## Snapshot de la API local
- Servida: `api_snapshot_v2` del 08-09 (`D:\INMO CAPITAL\ERETZ_API_CONTRACT\`). Reemplazarla = deploy.
- Candidata más nueva: `_scratch/unification/snapshot_v4f_2026-09-26/` (v4e + frescura de la
  tarde; reconstruir cuando la cola recertifique el lote de la noche). Anterior: `_scratch/unification/snapshot_v4e_2026-09-25/` — 57.665 propiedades,
  `integrity_check` ok, reglas de calidad del runner + frescura desde NEEDS_FIX por campos.
  Detalle y latencias en `READY_FOR_PRODUCTION_ACTION.md` §7.

## Producción
Nada escrito. Bloqueos: credencial Postgres directa (`BLOCKED_EXTERNAL_CREDENTIAL`), sin
`pg_dump` con restore probado. Lista única: `docs/agent/READY_FOR_PRODUCTION_ACTION.md`.

## Tareas inmediatas
Ver `docs/agent/HANDOFF.md` § «Próxima prioridad».
