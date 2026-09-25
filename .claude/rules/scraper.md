---
paths:
  - "connectors/**"
  - "scraper/**"
  - "scripts/**"
  - "tests/**"
---
# Scraper, conectores y certificación

## Clasificar el arreglo antes de escribirlo
- Global → familia → dominio, en ese orden de preferencia. Un dominio puntual es evidencia de un
  patrón, no un caso para parchear aparte.
- Antes de editar: ¿qué falla?, ¿con qué evidencia?, ¿cuántas agencias/fichas toca (radio medido
  sobre los paquetes)?, ¿qué más lee ese código?, ¿qué test lo muerde?, ¿cómo se valida en vivo?
- Timeouts: no subirlos para esconder una falla; medir primero dónde se va el tiempo.

## Verificar contra la fuente, no contra el código
- Una medición o un diagnóstico se confirma bajando la página real, no releyendo el extractor.
- Diagnóstico liviano con el código de hoy: `_procesar_con` con 2 o 3 fichas por agencia (no es
  un worker). El certificador tiene respaldo a `generico` que ese diagnóstico no usa.

## Huella y recertificación
- `scripts/agency_fingerprints.py::archivos_de_la_huella()` lista los archivos que invalidan
  certificaciones. `shared/*` (base, runner, certifier, source_policy, …) invalida todas; un
  conector invalida su familia. Agrupar cambios compartidos en un solo lote.
- Los workers paran entre agencias si cambia un archivo de la huella en disco y el relanzador los
  levanta en ≤10 min: no dejar cambios de huella sin commitear.
- Fuera de la huella: `run_agency_certification_queue.py`, `defect_triage.py`, `regression_gate.py`,
  `comparar_con_linea_base.py`, `api_snapshot.py`, `property_freshest.py`, `api/v2.py`.

## Paradas de la cola
- Stop de familia/COMPARTIDO: diagnosticar la agencia, y si el defecto es de radio acotado firmar
  el diferimiento en `AGENCY_DEFECTS_DIFERIDOS.jsonl` (backup antes; `firma_del_patron` del
  `AGENCY_DEFECT_QUEUE.jsonl`; `cuando` = hora real). Nunca una heurística que esconda errores:
  degradar de forma segura y dejar la agencia en NEEDS_FIX.
- Regression Gate: `python scripts/comparar_con_linea_base.py --linea-base
  _regresion/ANTES_DEL_LOTE_2026-09-24.jsonl --desde 2026-09-24T11:39:00`; cada pérdida se baja de la
  fuente y se firma en `_regresion/REVISADAS.jsonl` con evidencia y hora real.

## Listas que no pueden divergir
- Portales: `agency_web_discovery.PORTALES_POR_NOMBRE` (nombre registrable exacto) y
  `verificador_identidad_v2.PORTALES` (subcadena: solo nombres inequívocos). Un test las compara.
