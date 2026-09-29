# ERETZ — CLOUD BOOTSTRAP (operativo)

Desde un clone limpio. Sin secretos: donde hace falta una variable se da solo el NOMBRE.

## 1. Código
```bash
git clone https://github.com/NicoWulf2026/eretz-propiedades.git eretz
cd eretz
git checkout handoff/codex-unificacion-2026-09-18
git rev-parse HEAD                 # comparar con el HEAD del checkpoint / tag cloud-checkpoint-2026-09-29
git log --oneline -5
```
Leer, en este orden: `docs/CLOUD_CONTINUATION_HANDOFF.md` → `docs/agent/POLITICAS_PERMANENTES.md`
→ `CLAUDE.md` → `docs/agent/CURRENT_STATE.md` → `docs/agent/HANDOFF.md` →
`docs/agent/READY_FOR_PRODUCTION_ACTION.md` → `docs/agent/lotes/README.md` → `docs/agent/ESTADO_DURABLE.md`.

## 2. Entorno Python
Python **3.14** (el lock lo exige; CI usa 3.14).
```bash
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
python -m pip install --require-hashes -r requirements.lock
```

## 3. Tests
```bash
# smoke (segundos): lo tocado en el ultimo bloque
python -m pytest -q -p no:cacheprovider tests/test_snapshot_certificadas_2026_09_29.py \
  tests/test_verificar_retiros.py tests/test_compuertas_de_despliegue.py \
  tests/test_lote_compartido_2026_09_29.py tests/test_lote_compartido_2_2026_09_29.py \
  tests/test_robots_2026_09_29.py tests/test_workers.py
# suite completa (~5 min). Offline: los tests que necesitan datos locales se saltean solos.
PYTHON_DOTENV_DISABLED=1 python -m pytest -q -p no:cacheprovider
```
Al checkpoint: 3.701 passed en la máquina original.

## 4. Datos (NO están en el repo — el repo es público)
**Raíz configurable:** `export ERETZ_DATA_ROOT=/ruta/restaurada` (Windows: `set ERETZ_DATA_ROOT=...`).
Todo el núcleo (API, geografía, cola, certificador, snapshot, despliegue, gate) la usa
(`scripts/rutas_de_datos.py`); las rutas absolutas del manifiesto de datos se reubican solas.
Restaurar y verificar: `docs/agent/ESTADO_DURABLE.md` y `python scripts/cloud/prueba_restore.py`
(desde la raíz del repo, con la variable fijada): debe dar 0 archivos con problema y 0 accesos
a la raíz original.
Todo el estado operativo vive bajo `D:\INMO CAPITAL\` en la máquina original y los scripts tienen
esas rutas por defecto (todas se pueden pasar por argumento). Ver `docs/agent/ESTADO_DURABLE.md`
para qué es cada cosa, su SHA-256 y cómo restaurarla desde `ERETZ_STATE_2026-09-29.tar.gz`
(se extrae con las rutas relativas a `D:\INMO CAPITAL\`). Sin ese archivo se puede trabajar en
código, tests y documentación, pero no en la cola ni en snapshots.

Variables (solo nombres; valores en el gestor de secretos del usuario, nunca en el repo):
`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_DATABASE_URL`,
`INTERNAL_DB_URL`, `ERETZ_API_SNAPSHOT` (ruta del SQLite de la API), frontend:
`ERETZ_API_V2_BASE_URL`, `NEXT_PUBLIC_SITE_URL`, `BLOB_READ_WRITE_TOKEN`, `ERETZ_PREVIEW_*`.
`PYTHON_DOTENV_DISABLED=1` evita que algún script cargue un `.env` por su cuenta.

## 5. API local
```bash
ERETZ_API_SNAPSHOT=/ruta/a/ERETZ_API_SNAPSHOT.sqlite3 python -m uvicorn api.main:app --port 8000
# QA de API sobre una snapshot:
python scripts/benchmark_unified_api.py /ruta/snapshot.sqlite3 --output /tmp/API_BENCHMARK.json
```

## 6. Snapshot: construir, verificar, desplegar (local)
```bash
python scripts/api_snapshot.py --salida _scratch/unification/snapshot_<nombre> \
  --sumar-certificadas --retiros-verificados <RETIROS_VERIFICADOS.jsonl>
python scripts/benchmark_unified_api.py _scratch/unification/snapshot_<nombre>/ERETZ_API_SNAPSHOT.sqlite3 \
  --output _scratch/unification/snapshot_<nombre>/API_BENCHMARK.json
python scripts/desplegar_snapshot.py --candidata _scratch/unification/snapshot_<nombre> \
  --etiqueta-respaldo <etiqueta_de_la_servida> --automatico     # politica P2: aborta si falla una compuerta
```
Retiros (P1): `python scripts/verificar_retiros.py --salida <archivo>` (cortés; Tokko en serie).

## 7. Cola de certificación
```bash
python scripts/eretz_automatizacion.py estado          # interruptor, tareas, workers vivos
python scripts/relanzar_la_cola.py                     # dry-run: que lanzaria y por que
python scripts/relanzar_la_cola.py --lanzar            # lanza los workers que falten (regimen de ERETZ_WORKERS.json)
python scripts/regimen_de_workers.py                   # metricas 2 vs 3 workers (P5)
python scripts/comparar_con_linea_base.py --linea-base _regresion/ANTES_DEL_LOTE_2026-09-24.jsonl \
  --desde 2026-09-24T11:39:00                          # Regression Gate
```
En Windows, `ERETZ_AUTOMATION_ON.cmd` crea las tareas programadas (relanzador cada 10 min,
vigilante cada 5). En Linux/cloud no hay tareas: correr el relanzador con cron o a mano.
PID y cerrojos (`*.lock`) NO son estado durable: en una máquina nueva no existen y está bien.

## 8. Lo que NO se ejecuta
- `api_snapshot.py` sin `--salida` (escribe en la ruta servida).
- Cualquier write a Supabase, `execute_sql`, `apply_migration`, restore, deploy público, DNS.
- `git push --force`, `reset --hard`, `clean -fdx`, merges a `main` que disparen CI/producción.
- Descubrimiento pago (`scripts/search_provider.py`, `run_web_discovery.py`) por encima de USD 10/mes.

## 9. Dónde está cada cosa
- Parches de lotes y su estado: `docs/agent/lotes/`.
- Snapshots candidatas y logs de la sesión: `_scratch/unification/` (ignorado por git; local).
- Registros de despliegue: `D:\INMO CAPITAL\ERETZ_API_CONTRACT\_despliegues\`.
- Logs de la cola: `D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827\cola_w*.log`, `relanzador.log`.
