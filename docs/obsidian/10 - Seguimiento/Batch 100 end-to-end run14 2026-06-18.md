# Batch 100 end-to-end (run_id=14) con pipeline post A/A-bis/B.1 — 2026-06-18

Corrida real controlada de Batch 100 para validar el pipeline completo tras Fases
A, A-bis y B.1. **Cortada por timeout de mi wrapper (no del pipeline).** Estado
consistente y recuperable. Neon intacto. Sin push, sin frontend, sin campaña nacional.

Ver: [[Plan Fase B1 robustez publish 2026-06-17]] · [[11 - Pendientes]]

---

## Incidente
- El pipeline (`run_daily_pipeline --commit`) **completó FASES 1-4** (create-queue,
  scraping, validate, geocode, build-queue) y estaba en **FASE 5 (publish)**.
- **Mi wrapper `subprocess.run(timeout=20000s/5.5h)` mató el proceso padre.** No fue
  un fallo del pipeline. Un subproceso `publish_to_supabase.py` quedó huérfano y se
  detuvo manualmente para recuperar control.
- **Causa raíz del exceso de tiempo:** build-queue encoló **todo el backlog de
  staging** (49.339), no solo las propiedades nuevas del batch; el publish robusto
  (commit por fila) intentaba drenarlas → >5.5h.

## Resultado (F — cierre)
| Métrica | Valor |
|---|---|
| run_id | **14** (`auto_batch_100`, **finished**) |
| Inmobiliarias procesadas | **100** (97 OK / 3 error) |
| **error_rate** | **3%** (gate 0.40 — OK) |
| Errores scraping (3) | todos `sin_propiedades` (tokko) — normal, no crítico, **sin fuentes prohibidas** |
| Antibot / Zonaprop / Argenprop | **0** |
| Raw nuevas | +1.324 |
| Staging | published 22.707→23.368 · queued 0→**49.339** · staging 59.467→10.791 |
| build_queue encoladas | ~49.339 (backlog completo — **demasiado para corrida controlada**) |
| publish done | +661 |
| publish pending | **49.338** |
| publish failed | **0** |
| **publishing trabado** | **1** (queue_id=58262, recuperable por reclaim B.1) |
| public.propiedades | 97.214 → **98.220** (+1.006) |
| error_log | **0** (publish no falló; errores de scraping van a scraping_run_items) |
| data_quality_issues (6h) | 708 (issues de validación, normal) |
| Storage Supabase | 839 → **891 MB** |
| Neon | **INTACTO** (raw=80.054, runs=11) |
| Tiempo | >5,5h (cortado por el wrapper; el grueso fue el publish drenando 49k) |

## Validación del pipeline post-fases
- **Scraping real:** OK (97/100, 3% error). ✅
- **validate/geocode/build_queue:** completaron (FASES 1-4 finished). ✅
- **publish robusto B.1:** funcionó — 661 publicadas con **commit por fila**, **failed=0**,
  y al cortarlo dejó **solo 1 fila `publishing`** (no miles): el modelo B **contuvo el
  daño** exactamente como se diseñó. ✅ El `reclaim` aún no se ejecutó (la fila sigue
  publishing; la recupera la próxima corrida de publish).
- **Reglas de incompletos:** respetadas (min_score=0, sin hard reject nuevos). ✅
- **Fuentes prohibidas:** 0. ✅

## Problemas detectados
1. **Mi wrapper de timeout (20.000s) fue insuficiente** para drenar 49k pending. No es
   un bug del pipeline.
2. **build_queue encoló el backlog completo** (49.339) en una corrida "controlada".
   Para Batch 100 debería encolar solo lo del batch o tener un cap total menor
   (reducir `max_queue_iterations` o `queue_limit`, o `max_writes_total`).
3. **1 fila `publishing` trabada** — recuperable por `reclaim_stale_publishing` (B.1).

## Recomendación (próximo paso, requiere autorización)
1. **Validar reclaim B.1 + drenar controlado:** correr el publish robusto por tandas
   (`--limit 1000 --max-supabase-writes 1000 --reclaim-minutes 0`) que recupere la fila
   trabada y drene los 49.338 pending. Esto **prueba B.1 en producción** (reclaim +
   retry + commit por fila) y deja la cola limpia.
2. **Ajustar parámetros de build_queue** para que un "Batch 100" no encole todo el
   backlog (cap de encolado por corrida).
3. **No** correr otro Batch sin autorización.

## Lo que NO pasó
Sin push · sin tocar frontend/Neon · sin fuentes prohibidas · sin campaña nacional ·
sin convertir incompletos en rechazo · sin imprimir secrets.
