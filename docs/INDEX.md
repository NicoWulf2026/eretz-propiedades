# Índice de documentación — ERETZ

Mapa para saber qué leer y qué NO leer por defecto. Nada de esto se carga solo en Claude Code;
se consulta a pedido. Vault de Obsidian: esta carpeta `docs/` (la raíz del repo queda afuera;
sus documentos se listan acá con su ruta).

## CURRENT — estado y operación vigentes
- `docs/agent/CURRENT_STATE.md` — estado actual (no bitácora).
- `docs/agent/HANDOFF.md` — cómo seguir, qué no rehacer, próxima prioridad.
- `docs/agent/READY_FOR_PRODUCTION_ACTION.md` — lista única de acciones productivas pendientes.
- `docs/agent/CLAUDE_CODE_OPTIMIZATION.md` — configuración de Claude Code para este repo y su rollback.
- `ERETZ_RUNBOOK_OPERACION.md` — operar la cola, el relanzador y los paros.
- `ERETZ_DECISION_LEDGER.md` — decisiones vigentes.
- `ERETZ_BLOQUEOS_EXTERNOS.md` — bloqueos que dependen de terceros.

## REFERENCE — contratos y reglas de datos
- `ERETZ_PROPERTY_CONTRACT.md`, `ERETZ_CONTRATO_DE_DATOS.md`, `ERETZ_PROPERTY_LIFECYCLE.md`.
- `ERETZ_QUALITY_GATE.md`, `ERETZ_EQUIVALENCIA_DE_ESCRITORES.md`, `PROPERTY_WRITE_ACCESS_MANIFEST.md`.
- `ERETZ_SUPABASE_READINESS.md`, `ERETZ_PROMOCION_STAGING_A_MAIN.md`, `ERETZ_STAGING_PROMOTION_DRYRUN.md`.
- `docs/API_V2_CONVERGENCE.md`, `docs/API_V2_CUTOVER_CONTRACT.md`, `docs/ERETZ_IDENTITY_V1.md`.
- `docs/TESTING.md`, `docs/SECURITY.md`, `docs/LOCAL_SETUP.md`, `docs/RELEASE_PROCESS.md`.

## ARCHITECTURE
- `docs/ARCHITECTURE.md`, `docs/DATA_MODEL.md`, `docs/ERETZ_DOMAIN_MODEL.md`,
  `docs/SCRAPING_PIPELINE.md`, `docs/ERETZ_PUBLICATION_ARCHITECTURE.md`.
- Geografía: `ERETZ_GEO_MODELO_CANONICO.md` (modelo) y `ERETZ_CANONICAL_GEOGRAPHY.md` (fuentes y
  reglas); se solapan en parte — leer el primero.
- Planes: `docs/ERETZ_UNIFICATION_PLAN.md`, `ERETZ_SEMANTIC_WINDOW_PLAN.md`,
  `ERETZ_VENTANA_SEMANTICA_ORDEN.md`, `ERETZ_PLAN_DE_CAPACIDAD.md`.

## HISTORICAL — evidencia fechada (leer solo si se investiga ese episodio)
- Diagnósticos: `ERETZ_LA_COLA_NO_AVANZA_2026-09-21.md` (50 KB), `ERETZ_UN_PARO_DE_FAMILIA_NO_ES_LA_COLA_2026-09-23.md`,
  `ERETZ_LA_OPERACION_2026-09-23.md`, `ERETZ_GEOGRAFIA_CAUSAS_2026-09-20.md`, `ERETZ_HALLAZGO_REDES.md`,
  `ERETZ_RETRABAJO.md`, `ERETZ_BRAVE_250.md`, `ERETZ_REMAX_CANARIO.md`, `ERETZ_PLAYWRIGHT_OFFICE_CANARY.md`.
- Handoffs y bitácoras viejas: `ERETZ_HANDOFF_2026-09-18.md`, `ERETZ_BITACORA_2026-09-20.md`,
  `docs/ERETZ_CODEX_TO_CLAUDE_HANDOFF.md`, `docs/ERETZ_UNIFICATION_EVIDENCE.md`, `docs/handoff/`.
- Auditorías: `ERETZ_ASSET_AND_REPO_AUDIT.md`, `ERETZ_GITHUB_HISTORICAL_AUDIT.md`,
  `docs/ERETZ_SECURITY_AND_DATA_AUDIT_2026-08-27.md`, `ERETZ_QA_BROWSER_2026-09-20.md`.
- Obsidian: `docs/obsidian/10 - Seguimiento/`, `docs/obsidian/11 - Registro diario/`.

## LEGACY — no leer completos por defecto
- `MASTER_PROGRESS.md` (66 KB) y `ERETZ_PROPERTIES_MASTER_PLAN.md` (65 KB): buscar con grep.
- `ERETZ_CODEX_RECOVERY_MASTER_REPORT.md`, `ERETZ_CLEANUP_MANIFEST_20260904.md`,
  `ERETZ_FUENTES_COMPARTIDAS_PENDIENTES.md`.
- `docs/ROOMIX_*`, `docs/ERETZ_FUNCTIONAL_V3_STATUS.md`, `docs/ERETZ_POST_V2_ROADMAP.md`.
- El repo `D:\INMO CAPITAL\Inmo-Capital-main` entero (copias viejas de varios de estos documentos).

## QUARANTINED
- `docs/handoff/herramientas-no-versionadas-2026-09-20/`: copias de auditorías de Supabase y GitHub
  que en `Inmo-Capital-main` siguen sin versionar. Se conservan como evidencia; no son fuente vigente.

## Obsidian
Las carpetas `03_SCRAPERS_DB`, `05_PANEL_INMOBILIARIAS` y `06_MARKETING` NO duplican a
`03 - …`, `05 - …`, `06 - …`: tienen notas distintas y el panel principal las enlaza por ruta.
Se dejan como están. La memoria automática de Claude (`~/.claude/projects/…/memory`) no forma
parte del vault.
