# ERETZ — estado actual

Estado VIGENTE, no bitácora. La historia está en Git (`git log`; la bitácora anterior de este
archivo: `git show 6ee927bb80:docs/agent/CURRENT_STATE.md`). `database_writes: 0` en todo.

**Actualizado:** 2026-09-28 21:1x · **Rama:** `handoff/codex-unificacion-2026-09-18` (push solo acá)
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

## Resultados (paquetes en `ERETZ_AGENCY_CERTIFICATION_20260827/agencies`, 28-09 21:17)
| estado | agencias |
|---|---|
| CERTIFIED_COMPLETE | 287 |
| CERTIFIED_BEST_AVAILABLE | 37 |
| NEEDS_FIX | 178 |
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
- Regression Gate (28-09 21h): 497 agencias, 0 pendientes (77 firmadas: 66 CORRECCION -alagna
  emprendimientos y tarjetas similares-, 10 CAMBIO_EN_LA_FUENTE -christian arce-, 1 DEFECTO_PENDIENTE
  -pozzobon «un baño» en palabras-).
- Suite completa (28-09 21h, `64790ba41e`): 3.541 passed.

## Lote compartido pendiente (huella)
`docs/agent/lotes/`: cambios a la huella COMPARTIDA preparados y verificados en `eretz-dev` (3.635 verdes),
sin aplicar porque reinician la recertificación entera: aglomerados GeoRef (+112 localidades), descartes
sin señal (4 agencias, 348 prop.), buscador Houzez / unidades / «Provincia: Argentina» (`o feely`, 600).
`o feely` tiene diferida firmada (29-09 10:05, radio AGENCIA): la familia wordpress queda liberada.

## Snapshot de la API local
- **Servida: v4j** desde el 28-09 22:58 (exterior excluido, CABA por polígono, departamentos,
  precios simbólicos; deploy autorizado y verificado, respaldo de la v4g en
  `_anteriores/v4g_2026-09-28/`). Antes: v4g desde el 28-09 16:58 (deploy autorizado, controlado, sin rollback; registro en
  `ERETZ_API_CONTRACT/_despliegues/`, respaldo de la v2 en `_anteriores/v2_2026-09-08/`). Detalle:
  `READY_FOR_PRODUCTION_ACTION.md` §7. Todo reemplazo posterior sigue siendo deploy.
- **Candidatas v4l-a / v4l-b listas** (29-09, READY_FOR_ACTION; superan a la v4k): suman lo que
  los inventarios certificados vigentes saben y la preingestión del 03-09 no (+9.330, +50 agencias),
  refrescan 5.935 avisos con URL nueva y recalculan la geografía sobre la fila fresca (localidades
  9.494 → 18.507). La b además retira 2.637 que ya no están en el inventario COMPLETO de su agencia
  (muestra: 25/30 muertas). QA 14/14. Recomendada: v4l-b. Comandos en `READY_FOR_PRODUCTION_ACTION.md` §7.
- (histórico) Candidata v4k: v4j − 121 fichas del exterior; incluida en la v4l.
- (histórico) Candidata v4j (21:37; v4i + 42 precios simbólicos descartados): QA 14/14. La v4i era
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
