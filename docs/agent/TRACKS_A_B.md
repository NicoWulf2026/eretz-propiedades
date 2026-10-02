# Tracks paralelos A/B — mapa de conflictos (preparado 2026-10-01, cuenta B)

Estado: **preparacion, no activado**. Hasta que el usuario asigne tracks, B sigue
siendo CURRENT OWNER de todo y A no trabaja en paralelo sobre los mismos archivos.

## Los dos tracks

| Track | Alcance | Carpetas / archivos que le pertenecen |
|---|---|---|
| **OPERACIONAL** (scraper, certificacion, lotes semanticos, cobertura) | todo lo que cambia una huella o la cola | `connectors/`, `scraper/`, `scripts/run_*`, `scripts/agency_*`, `scripts/defect_*`, `scripts/diferir_por_precedente.py`, `scripts/relanzar_la_cola.py`, `scripts/vigilante_*`, `scripts/regimen_de_workers.py`, `scripts/backlog_de_lote.py`, `scripts/kpi_de_la_cola.py`, `scripts/ya_lo_vimos.py`, `tests/test_generico_*`, `tests/test_rollout_*`, `tests/test_certifier_*`, `tests/fixtures/cloud_bridge/`, `docs/agent/lotes/` |
| **PRODUCT** (API, frontend, writers, QA, production readiness) | lo que sirve el dato ya certificado | `api/`, `frontend/`, `deploy/`, `migrations/`, `supabase/`, `scripts/api_contract.py`, `scripts/prepare_api_v2_snapshot.py`, `scripts/desplegar_snapshot.py`, `scripts/plan_de_escritura.py`, `scripts/verify_writer_*.mjs`, `scripts/qa_navegador_sintetica.py`, `tests/test_api_*`, `frontend/e2e/` |

## Zona COMPARTIDA (riesgo de conflicto) — un solo dueño a la vez

Medido con `git log --since=2026-09-20 --name-only` (toques por archivo):

| Archivo | Toques | Por que es compartido | Regla propuesta |
|---|---|---|---|
| `docs/agent/CURRENT_STATE.md`, `docs/agent/HANDOFF.md`, `docs/ACCOUNT_HANDOFF.md` | 243 en `docs/agent` | ambos tracks reportan estado | una seccion por track (`## OPERACIONAL` / `## PRODUCT`); cada track edita SOLO la suya; ACCOUNT_HANDOFF lo edita solo el CURRENT OWNER |
| `docs/agent/READY_FOR_PRODUCTION_ACTION.md` | — | acciones del usuario de ambos tracks | numeracion por track (`OP-n`, `PR-n`) para no chocar en el numero |
| `scripts/api_snapshot.py`, `scripts/snapshot_certificadas.py` | 24 | puente: lee certificaciones (OP) y produce el snapshot que sirve la API (PR) | dueño PRODUCT; OP solo propone cambios por PR revisado |
| `scripts/agency_fingerprints.py` | 7 | define el radio de recertificacion | dueño OPERACIONAL; PR no lo toca |
| `connectors/geografia.py`, `connectors/poligono_*.py` | 7 | geografia: la usa la extraccion (OP) y el snapshot/P10 (PR) | dueño OPERACIONAL (cambia huella) |
| `tests/conftest.py`, `pyproject.toml`, `requirements*.txt`, `frontend/package*.json` | — | configuracion global | cambios solo en commits aislados y avisados en HANDOFF |

## Datos operativos (fuera del repo) — nunca en paralelo

`ERETZ_AGENCY_CERTIFICATION_20260827/` (ledger, cola de defectos, diferidas,
banderas de paro, `ERETZ_WORKERS.json`) lo escribe UN solo operador: el track
OPERACIONAL. PRODUCT solo lee snapshots ya construidos. Las diferidas se firman
con `radio` = el del paro (si no, no sirven de precedente: corregido el 2026-10-01).

## Ramas

- OPERACIONAL: `integration/eretz` (canonica) + ramas `b/loteN-dev` / `a/loteN-dev` para lotes en preparacion.
- PRODUCT: ramas `a/product-*` o `b/product-*` desde `integration/eretz`, merge por PR.
- Nadie toca `main` directamente. Sin force push.
