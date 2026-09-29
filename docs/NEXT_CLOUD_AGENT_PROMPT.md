# Prompt para Claude Code Cloud (copiar y pegar entero)

```
ERETZ PROPIEDADES — CONTINUACIÓN EN CLAUDE CODE CLOUD (arquitectura híbrida LOCAL + CLOUD)

REPO: https://github.com/NicoWulf2026/eretz-propiedades.git  (PÚBLICO)
RAMA: handoff/codex-unificacion-2026-09-18   (nunca main; nunca force push)
TAG DE REFERENCIA: cloud-checkpoint-2026-09-29 (la rama puede estar más adelante: seguí la rama)

ARQUITECTURA HÍBRIDA (decisión del usuario, no la discutas ni pidas el estado local):
- CODE_CLOUD_READY = YES. OPERATIONAL_CLOUD_READY = NO por decisión.
- LOCAL (PC de Nicolás) conserva ledger de certificación, paquetes, snapshots, workers,
  scheduler y datos privados. Ahí corren la cola y el despliegue de la snapshot local.
- VOS (cloud) trabajás desde GitHub en código, tests, docs, backend, API, frontend web,
  tooling y runbooks. Lo que necesite el estado local lo dejás preparado con instrucciones exactas
  para la sesión LOCAL (sección "PARA LOCAL" en docs/agent/HANDOFF.md) y seguís con otra cosa.
- Nunca subas al repo datos scrapeados, ledgers, snapshots, dumps ni secretos: el repo es público.

ARRANQUE (hacelo en este orden):
1. git clone …; git checkout handoff/codex-unificacion-2026-09-18; git rev-parse HEAD.
2. Leé: docs/CLOUD_CONTINUATION_HANDOFF.md, docs/agent/POLITICAS_PERMANENTES.md (P1–P24,
   vinculantes), CLAUDE.md, .claude/rules/*.md, docs/agent/CURRENT_STATE.md,
   docs/agent/HANDOFF.md, docs/agent/lotes/README.md, docs/CLOUD_BOOTSTRAP.md.
3. Entorno: Python 3.14; python -m pip install --require-hashes -r requirements.lock;
   PYTHON_DOTENV_DISABLED=1 python -m pytest -q  (debe dar todo verde; los tests que necesitan
   datos locales se saltean solos). No repitas auditorías ya documentadas.

TAREAS CLOUD RECOMENDADAS (ninguna necesita el estado local; elegí por valor y seguí):
A. P9 — título derivado en el frontend web: cuando el título falta, «{tipo} en {operación} ·
   {localidad}» solo con campos reales; si no alcanza, «Propiedad sin título». Mobile congelado.
   Archivo de partida: frontend/src/lib/api-v2/property-boundary.ts. Con tests.
B. generico — dirección sin rótulo junto al icono `fa-map-marker` («Laprida 1835, B7602FKK Mar
   del Plata, Provincia de Buenos Aires, Argentina, …», agencia `adriana martelliti`, 42 de 44
   fichas sin provincia): leerla como dirección y pasar la cadena por
   `Geografia.resolver_compuesta`. Fixture HTML + test que muerda. Es huella de la familia
   generico: agrupalo con otros arreglos de generico (P4).
C. Lote 4 (docs/agent/lotes/README.md): conteos en palabras («cuatro dormitorios», «un baño»),
   superficie sin rótulo («50 M² 50 M²», fenix), Strapi propio en subdominio `api.` con catálogo
   > 800 KB (paladino). Cada uno con fixture y test; dejá el parche + README con radio y
   beneficio estimado para que LOCAL lo aplique según P4.
D. P18 — rol escritor de mínimo privilegio: SQL exacto, rollback, test sobre PostgreSQL/WASM
   desechable (scripts/verify_writer_equivalence.mjs / verify_local_postgres.mjs), runbook.
   NO crearlo en producción.
E. P21 — API v2 remota para beta: Dockerfile + config de Fly.io o Railway (FastAPI + SQLite en
   volumen persistente, ≤ USD 10/mes), healthcheck, rollback por snapshot, runbook. Marcar
   EXTERNAL_ACCOUNT_REQUIRED (la cuenta/pago la hace el usuario). No desplegar.
F. P10 — provincia contradictoria: descargar el polígono oficial de provincias del IGN (dato
   público), contención punto-en-polígono con tests; la regla conserva lo publicado como
   evidencia. Radio a medir en LOCAL: dejá el comando.
G. P7 — guardrail local de gasto de búsqueda paga (≤ USD 10/mes, registro por corrida, corte
   duro) en scripts/search_provider.py / run_web_discovery.py, con tests.
H. Browser QA reproducible: una snapshot SINTÉTICA mínima (fixture generada, sin datos reales) +
   API local + frontend + Playwright, para que la QA de navegador no dependa del estado local.

REGLAS (resumen; manda POLITICAS_PERMANENTES.md):
- Autonomía: trabajar → validar → reportar la fase → CONTINUAR. Reportar no es detenerse.
  Decisión técnica reversible: la tomás vos. Caso cubierto por una política: aplicala sin preguntar.
- Bloqueo externo (credencial, cuenta, pago, dominio, abogado, acción productiva): marcalo
  (BLOCKED_EXTERNAL_* / EXTERNAL_*_REQUIRED) y seguí con otra tarea.
- Producción: cero writes a Supabase, migraciones, RLS, restore, deploy público, DNS, retirar
  noindex o merge a main (salvo lo que P19/P24 permiten con sus condiciones). La snapshot LOCAL y
  la cola son de la PC local.
- Huella: cambiar connectors/base.py, geografia.py, agency_certifier.py o run_rollout.py
  reinicia la recertificación en LOCAL: agrupá según P4 y decilo en el commit.
- Scraping desde cloud: solo para verificar un caso puntual, respetando robots.txt, 403/429 y
  cortesía; nunca paralelizar pedidos a Tokko.
- Commits chicos con mensaje claro terminados en la línea Co-Authored-By del entorno; push solo a
  la rama de trabajo; `git pull --rebase` antes de pushear (LOCAL también commitea).
- Tests: específicos primero; suite completa antes de cerrar un cambio compartido.
- Documentá lo hecho en docs/agent/HANDOFF.md y lo que necesite LOCAL en "PARA LOCAL".
- Seguí hasta agotar las tareas cloud seguras; empezá por A o B.
```
