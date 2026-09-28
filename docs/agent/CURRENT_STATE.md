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
- **Exterior — DECIDIDO por el usuario (28-09, durable)**: recolección SÍ, preservación SÍ,
  publicación NO; ERETZ público = `ARGENTINA_ONLY`. La extracción las conserva enteras con
  `extra.publicacion_exterior = PRESERVED_NOT_PUBLISHED`, `politica_publica = ARGENTINA_ONLY`,
  `pais_publicado` (ISO), evidencia y lo publicado (`ciudad/barrio/provincia_publicada`); nunca se
  les afirma geografía argentina. La snapshot pública las excluye (`exterior.publicable` + la misma
  evidencia para filas aún no recertificadas; resumen `exterior_conservadas_no_publicadas`). La
  marca vieja `PRODUCT_DECISION_PENDING` se trata igual. 30 fichas de 12 agencias medidas.
- **CABA + provincia «Buenos Aires» — DECIDIDO (28-09)**: solo desempata la contención
  punto-en-polígono contra la geometría OFICIAL del IGN (`connectors/geometria/caba_ign.geojson`,
  WFS `ign:provincia` in1=02, 1.024 vértices, Ley 27.275, reproducible con
  `scripts/geo_poligono_caba.py`), a ≥100 m del límite. Sin coordenada, afuera o en la frontera:
  sigue el conflicto (fail-closed). Nada de radios, centroides ni cajas. De las 99: 32 se
  recuperan (cantale 30, agostinelli 2); 4 caen fuera (Paraná, La Matanza, Mendoza ×2) y siguen en
  conflicto; 63 de `blanco` sin coordenadas siguen sin ciudad.

## Calidad
- Regression Gate (28-09 09:5x): 461 agencias recertificadas, 0 pendientes (77 firmadas: echesortu 42 fotos WhatsApp-Image → DEFECTO_ARREGLADO en e9e6c7f709, 1 CORRECCION «BAÑO 3ER PISO»; ente 34 dormitorios/baños → DEFECTO_PENDIENTE, ver HANDOFF). Gate anterior 06:4x: 448, 280 firmadas.
- Suite completa (28-09 15:3x, `c951da087e`): 3.460 passed.
- Regression Gate (28-09 15h): 474 agencias, 0 pendientes (34 de berardi firmadas).

## Snapshot de la API local
- **Servida: v4g** desde el 28-09 16:58 (deploy autorizado, controlado, sin rollback; registro en
  `ERETZ_API_CONTRACT/_despliegues/`, respaldo de la v2 en `_anteriores/v2_2026-09-08/`). Detalle:
  `READY_FOR_PRODUCTION_ACTION.md` §7. Todo reemplazo posterior sigue siendo deploy.
- **Candidata v4i lista** (exterior excluido, CABA por polígono, departamentos): QA 14/14. Su
  despliegue fue denegado por el control de permisos (deploy): espera autorización explícita.
  Comando en `READY_FOR_PRODUCTION_ACTION.md` §7.
- v4g: `_scratch/unification/snapshot_v4g_2026-09-28/` (integrity ok; +1.047 operación,
  +1.901 superficie total vs v4f; QA 14/14). Anterior: `_scratch/unification/snapshot_v4f_2026-09-26/` (v4e + frescura de la
  tarde; reconstruir cuando la cola recertifique el lote de la noche). Anterior: `_scratch/unification/snapshot_v4e_2026-09-25/` — 57.665 propiedades,
  `integrity_check` ok, reglas de calidad del runner + frescura desde NEEDS_FIX por campos.
  Detalle y latencias en `READY_FOR_PRODUCTION_ACTION.md` §7.

## Producción
Nada escrito. Bloqueos: credencial Postgres directa (`BLOCKED_EXTERNAL_CREDENTIAL`), sin
`pg_dump` con restore probado. Lista única: `docs/agent/READY_FOR_PRODUCTION_ACTION.md`.

## Tareas inmediatas
Ver `docs/agent/HANDOFF.md` § «Próxima prioridad».
