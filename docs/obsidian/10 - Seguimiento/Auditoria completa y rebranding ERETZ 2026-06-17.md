# Auditoría completa + plan campaña nacional + rebranding ERETZ (2026-06-17)

Auditoría read-only previa a la campaña nacional masiva. **Sin push, sin borrar,
sin tocar frontend, sin secrets, sin campaña aún.** Proyecto: InmoCapital → **ERETZ Propiedades**.

---

## 1. Resumen ejecutivo

El sistema está **operativo y validado a escala 100 inmobiliarias** sobre Supabase
`internal_scraping`, con el pipeline completo (scraping → raw → staging → geocode →
queue → publish) funcionando y reglas de negocio correctas (incompleto no rechaza,
fuentes prohibidas bloqueadas, duplicados por agencia preservados). El cutover a
Supabase está hecho y Neon quedó como backup congelado intacto.

**Pero hay tres brechas que impiden una campaña nacional segura hoy:**
1. **Throughput insuficiente para 24h.** Con 2 workers el scraping rinde ~0.58
   inmobiliarias/min. Revisar 5.500 en 24h exige ~3.8/min (~6.6× más). El objetivo
   de "<24h" solo es viable con **incremental liviano**, que **aún no existe**.
2. **Cuellos de performance no resueltos.** `validate_raw` procesa ~1s/fila (no
   bulk); el orquestador usa timeouts globales; el scraper es un monolito de 19k
   líneas difícil de paralelizar/testear.
3. **Naming y deuda técnica.** 162 referencias a InmoCapital (frontend visible,
   geocoder User-Agent, mocks), scripts sueltos `_*.py`, dir `Viejo/`,
   `.env.example` desactualizado.

**Recomendación:** NO lanzar campaña masiva todavía. Primero implementar la
separación **carga pesada (por cohortes) vs incremental diario**, presupuestos por
inmobiliaria, y desacoplar publish del scraping. La estrategia conceptual del
usuario es **mayormente correcta**; el orden de implementación es lo que ajusto.

---

## 2. Estado actual detectado

| Componente | Estado |
|---|---|
| Base interna | Supabase `internal_scraping` (cutover hecho, `.env` apunta ahí) |
| Neon | Backup congelado, **intacto** (80.054 raw, 11 runs) vía `NEON_DB_URL_BACKUP` |
| `public.propiedades` | ~97.181 (producción/frontend) |
| publish_queue | done=19.707 · **pending≈3.000** (drenaje quedó a medias) |
| staging | published≈19.707 · queued≈3.000 · staging≈59.467 |
| raw | 82.174 validated (0 pendientes tras recovery run 13) |
| Storage Supabase | ~839 MB (internal ~469 MB) — amplio margen (Pro) |
| Inmobiliarias elegibles | ~2.049 (de 7.004 en `inmobiliarias_main`; objetivo 5.500) |
| Último run | run_id=13 (Batch 100, finished) |
| Fixes aplicados | `missing_title` soft, fix orquestador timeout (StepTimeoutError) |

---

## 3. Riesgos principales

1. **Throughput lejos del objetivo de 24h** (ver §8). Sin incremental, una pasada
   nacional deep con 2 workers tarda ~6-7 días.
2. **`validate_raw` O(n) lento** (~1s/fila): a escala nacional (decenas de miles de
   raw) se vuelve un cuello que fuerza recoveries.
3. **publish acoplado al pipeline** sin manejo robusto de transitorios de red
   (Argentina→Supabase): los timeouts de red ya causaron cortes. El drenaje robusto
   solo existe en mis loops ad-hoc, no en el código.
4. **Monolito de 19k líneas** (`scraper_propiedades.py`): alto riesgo al modificar,
   sin tests, difícil paralelizar.
5. **El scraper publica directo a `public.propiedades` en FASE 2** además del
   pipeline interno → doble camino, difícil de controlar con backpressure.
6. **Sin checkpoints por inmobiliaria**: si una fuente grande corta a la mitad, se
   reprocesa desde cero.
7. **Timeouts globales** enmascaran problemas reales (criterio del usuario: evitar).
8. **Naming InmoCapital** en User-Agent de geocoding (visible a Nominatim) y
   frontend (visible a usuarios).

---

## 4. Hallazgos por componente

### Scraping (`scraper/scraper_propiedades.py`, 19.125 líneas)
- Monolito: scraping, extracción, dedup, publicación REST, geocoding legacy, RPC interno.
- Clasificación de fuentes madura (familias de error: requires_playwright, site_down,
  sin_propiedades, timeout, skipped_invalid_source).
- **Publica a `public.propiedades` por REST durante el scraping** (FASE 2) y además
  inserta raw en `internal_scraping`.
- Soporta `INTERNAL_DB_SCHEMA` (parametrizado en cutover).
- **Riesgo alto al refactorizar; sin tests de regresión.**

### Orchestrator (`scripts/run_daily_pipeline.py`)
- Orquesta por subprocess: create-queue → scraper → validate → geocode → build-queue → publish.
- Timeouts: `--scraper-timeout` (7200s def), `--step-timeout` (600s def), `--geocode-timeout` (1800s def).
- **Fix aplicado:** `StepTimeoutError` + continúa fases 3-5 si la run quedó `finished`
  (warning `scraper_subprocess_timeout_but_run_finished`).
- **Limitación:** no parte el scraping en sub-lotes; un batch grande no entra en la ventana.

### validate_raw (`scripts/validate_raw_properties.py`)
- raw → staging. **`missing_title` ya es soft** (fallback `{Tipo} en {ciudad}`...).
- Hard rejects que quedan (correctos): missing_hash, missing_inmobiliaria_id,
  missing_url, invalid_price (precio presente malformado), invalid_currency, duplicate.
- **Cuello: ~1s/fila** (no bulk). Candidato #1 a optimización.

### build_queue (`scripts/build_publish_queue.py`)
- **Ya optimizado a bulk** (limit 10.000 en ~8-12s). Sano. Buen modelo a replicar.

### publish (`scripts/publish_to_supabase.py`)
- Lee queue interna, publica a `public.propiedades` por REST con dedup por
  url_normalizada, rate-limit (`--sleep`), caps (`--max-supabase-writes`).
- **Sin manejo robusto de transitorios** (read timeout, ConnectionReset) — frena.
- ~2.4-3s/prop por rate-limit + latencia.

### Geocoding (`scraper/geocoder.py`, `scripts/geocode_staging.py`)
- Nominatim, ~1 req/s. **No bloquea publicación** (`allow_pending_geo=True`). Correcto.
- Backlog actual ~42.000 pending — sano que no bloquee.
- **User-Agent `InmocapitalGeocoder/1.0 (geocoding@inmocapital.local)`** → renombrar a ERETZ.

### Supabase internal_scraping
- 9 tablas + 7 RPC + índices. Sequences sincronizadas. Sano.
- Índice crítico `idx_propiedades_staging_status_score_id` presente.

### Neon backup
- Congelado, intacto. Acceso vía `NEON_DB_URL_BACKUP`. No usado por el pipeline.

### Fuentes prohibidas
- **Bien implementado.** `run_internal_scraping_batch.py:72`
  `SOURCE_PROHIBITED_PORTAL_RE = (zonaprop|argenprop)\.com\.ar` → skip
  `prohibited_external_portal`. Otros portales (mercadolibre, properati…) → `external_portal`.
- ⚠️ **Área gris:** `scraper/scrape_zonaprop_agencias.py` y
  `scraper_zonaprop_inmobiliarias.py` DESCUBREN agencias desde zonaprop (no scrapean
  propiedades). Pregunta abierta (§12).

### Deduplicación / estados / incompleto
- Dedup por `hash_dedup` (raw) y `url_normalizada` (publish). **Duplicados entre
  agencias se preservan** (hash incluye inmobiliaria). Correcto.
- **Incompleto no rechaza** (min_score=0, soft issues). Correcto.
- Operación desconocida → `consultar`. venta+alquiler → `venta_y_alquiler`. Correcto.
- Estados históricos: el pipeline no los borra; `enqueue_deactivations` marca
  desaparecidos (opt-in `--with-deactivations`). Correcto.

### Deuda técnica
- Monolito 19k líneas sin tests.
- Scripts sueltos en raíz: `_audit_sim.py`, `_batch*_status.py`, `_deep_scan_npl.py`,
  `_reset_pq53.py` — mover a `scripts/_scratch/` o borrar.
- Dir `Viejo/` (legacy InmoLink, imágenes, CSVs).
- `.env.example` desactualizado: falta `INTERNAL_DB_SCHEMA`, `NEON_DB_URL_BACKUP`,
  `SUPABASE_DATABASE_URL`.

---

## 5. Auditoría naming InmoCapital → ERETZ Propiedades

162 ocurrencias en 63 archivos. Clasificación:

### A. Cambio seguro (documentación / texto visible no técnico)
- Docs Obsidian (~110 ocurrencias): títulos, marketing, estrategia.
- README / prompts.
- Frontend **texto visible**: `layout.tsx` (title SEO), `HeroSection.tsx`, `Navbar.tsx`
  (logo/alt/span), `PropertyCard.tsx` (texto). *Requiere tu OK por la regla "no tocar
  frontend"; es naming visible, bajo riesgo técnico pero alto impacto de marca.*

### B. No cambiar todavía (compatibilidad)
- `PLATFORM_FALLBACKS = {"InmoCapital","inmocapital","INMOCAPITAL"}` en `PropertyCard.tsx`
  y `property-mapper.ts:294`: es un **set de detección de fallback de agencia**. Si se
  cambia, hay que migrar también los datos que usan ese valor. Cambiar nombre visible
  ≠ cambiar el valor lógico de matching.
- `originCms: "inmocapital"` en mocks (`property-data.ts`): dato de ejemplo; cambiar
  solo si se regeneran los mocks.

### C. Legacy / interno (dejar por ahora)
- **Schema `internal_scraping`, tablas, `public.propiedades`**: NO renombrar
  (rompería todo el pipeline, RLS, frontend).
- Variables de entorno (`INTERNAL_DB_URL`, etc.): NO renombrar.
- Path del repo `D:\INMO CAPITAL\...`: cosmético, no crítico.
- Filtro `'%inmocapital.test%'` en la vista de producción: es exclusión de datos de
  prueba; mantener hasta confirmar que no hay URLs test con ese dominio.

### D. Migración cuidadosa
- **Clases CSS `.inmocapital-leaflet-marker`** (`globals.css` + referencias en TSX):
  renombrar exige cambiar TODAS las referencias a la vez. Hacer en un PR atómico de frontend.
- **User-Agent geocoder** `InmocapitalGeocoder/...inmocapital.local`: cambiar a
  `EretzPropiedadesGeocoder/1.0 (geocoding@eretzpropiedades.<dominio>)`. Bajo riesgo,
  pero Nominatim exige User-Agent identificable y estable; coordinar con un dominio real.

**Recomendación naming:** primero un PR **solo de documentación/Obsidian** (seguro),
luego un PR **frontend de marca** (con tu OK), y dejar identificadores técnicos como legacy.

---

## 6. Evaluación de la estrategia nacional propuesta

| Punto de tu estrategia | Veredicto |
|---|---|
| Separar carga pesada vs incremental diario | ✅ Correcto y esencial |
| No hacer un batch gigante único | ✅ Correcto (ya lo vimos: Batch 100 = 172 min) |
| Colas, cohortes, prioridades | ✅ Correcto |
| Clasificar inmobiliarias por estado | ✅ Correcto (ya existe base: familias de error) |
| Presupuestos por inmobiliaria vs timeouts globales | ✅ **Excelente** — alineado con tu criterio |
| Checkpoints por inmobiliaria | ✅ Correcto — **falta implementar** |
| Separar scraping/validate/geocode/queue/publish | ⚠️ Parcial: ya están separados en scripts, pero el scraper **publica directo** y el orquestador los acopla |
| Continuar fases si scraper terminó pero wrapper cortó | ✅ **Ya implementado** (fix de esta sesión) |
| Publicar incompletas | ✅ Ya es la regla |
| Geocoding asíncrono no bloqueante | ✅ Ya lo es |
| Publish queue con caps | ✅ Existe (`--max-supabase-writes`) |
| Backpressure para proteger producción | ⚠️ **Incompleto** — el scraper publica directo sin backpressure |
| Incremental por hashes/URLs/señales | ✅ Correcto — **no existe aún**, es lo más valioso a construir |
| Deep refresh semanal/mensual | ✅ Correcto |
| Cola separada para problemáticas/antibot | ✅ Correcto — **falta** |
| Prohibición permanente Zonaprop/Argenprop | ✅ Ya implementada |

**Qué está incompleto:** incremental, checkpoints, cola separada de problemáticas,
backpressure real, presupuestos por inmobiliaria.
**Qué es riesgoso:** el scraper publicando directo a producción sin caps unificados.
**Qué haría distinto:** desacoplar publicación del scraping (que el scraper SOLO
escriba a `internal_scraping`, y `public.propiedades` se alimente exclusivamente del
publish_queue con caps + backpressure). Esto da control total.
**Qué agregaría:** métricas por cohorte, una tabla de estado por inmobiliaria
(última revisión, resultado, próximo refresh), y un "presupuesto" (max_props,
max_seconds, max_pages) por inmobiliaria.
**Qué eliminaría:** nada conceptual; sí la deuda (scripts sueltos, monolito a futuro).

---

## 7. Arquitectura operativa recomendada

```
DESCUBRIMIENTO → COLA(cohortes+prioridad) → SCRAPING(presupuesto+checkpoint)
   → internal_scraping.raw → validate(bulk) → staging → geocode(async)
   → build_queue(bulk) → publish_queue(caps+backpressure) → public.propiedades
                                   ↑
                INCREMENTAL diario (señales) ──┘   DEEP refresh (semanal)
```

Principios:
- **El scraper NO publica directo**; solo llena `internal_scraping`. `public.propiedades`
  se alimenta solo del publish_queue (un único grifo controlado).
- **Presupuesto por inmobiliaria** (max_props, max_pages, max_seconds) en vez de
  timeouts globales altos.
- **Checkpoint por inmobiliaria** (URL/página donde quedó).
- **Tabla `estado_inmobiliaria`**: pendiente / scrapeable / prohibida / antibot /
  error_tecnico / vacia / parcial / exitosa / lista_incremental.
- **Cola separada** para problemáticas (antibot, lentas, requires_playwright).
- **Incremental** basado en hash de listado + URLs conocidas + conteo de propiedades.

---

## 8. Throughput para el objetivo de 24h

Evidencia: Batch 100 = 171,7 min para 100 inmobiliarias (2 workers) → **0,58 inmob/min**.

| Universo | Deep @ 2 workers | Requerido para 24h | Brecha |
|---|---|---|---|
| 2.049 elegibles | ~59 h (~2,5 días) | 1,42 inmob/min | ~2,5× (≈5 workers) |
| 5.500 potenciales | ~158 h (~6,6 días) | 3,82 inmob/min | ~6,6× (≈13 workers) |

**Conclusión:** el sistema está **lejos** del objetivo de 24h **con deep scraping**.
El objetivo de "<24h" SOLO es realista para **incremental liviano** (chequear señales
de cambio sin re-scrapear todo). Estimación incremental (~10-15s/inmob, chequeo de
listado): ~4-6 inmob/min/worker → 5.500 en 24h con **2-4 workers**. ✅ alcanzable.

Por eso la separación carga-pesada/incremental no es opcional: es el único camino al
objetivo de 24h. La carga pesada se hace **una vez por cohortes** (días), el
incremental sostiene el <24h.

---

## 9. Plan por fases (camino a la campaña nacional)

**Fase A — Higiene y preparación (sin riesgo productivo)**
- Drenar los ~3.000 pending actuales (cola limpia).
- Actualizar `.env.example`. Mover scripts sueltos `_*.py`. Doc.
- PR naming documentación (ERETZ).

**Fase B — Robustez del pipeline (cambios de código, con tests/dry-run)**
- Optimizar `validate_raw` a bulk (cuello #1).
- Drenaje robusto de transitorios **dentro** de `publish_to_supabase` (no en loops ad-hoc).
- Presupuesto por inmobiliaria + checkpoint en el scraper.

**Fase C — Modelo de cohortes e incremental**
- Tabla `estado_inmobiliaria` + clasificación.
- Cola separada de problemáticas.
- Scraper incremental (señales).

**Fase D — Carga pesada nacional por cohortes**
- Cohortes de 100-200 inmobiliarias, secuenciales, con métricas go/no-go entre cada una.
- Deep refresh programado.

**Fase E — Mantenimiento incremental diario <24h**
- Incremental sobre todas las activas + deep refresh semanal de las que lo requieran.

**Criterios go/no-go entre cohortes:** error_rate ≤ 0,40 · failed=0 no recuperable ·
pending drenándose · storage con margen · sin fuente prohibida colada · público intacto.
**Rollback:** restaurar `.env.bak` o apuntar `INTERNAL_DB_URL` a `NEON_DB_URL_BACKUP`;
publish_queue es idempotente (reset pending).

---

## 10. Cambios recomendados inmediatos (con tu OK)
1. Drenar los 3.000 pending (operativo, seguro).
2. Actualizar `.env.example` + limpiar scripts sueltos (doc/higiene).
3. PR naming **solo documentación** (ERETZ).

## 11. Cambios recomendados después (requieren autorización de código)
1. `validate_raw` bulk.
2. Drenaje robusto en `publish_to_supabase`.
3. Presupuesto + checkpoint por inmobiliaria.
4. Desacoplar publicación directa del scraper.
5. Tabla de estado + incremental.

## 12. Qué NO tocar todavía
- Schema/tablas/`public.propiedades`/RLS/variables de entorno (identificadores técnicos).
- Frontend funcional (solo naming visible con OK explícito).
- Neon (backup).
- El monolito `scraper_propiedades.py` sin tests previos.

---

## 13. Preguntas abiertas
1. **Descubrimiento desde Zonaprop:** ¿`scrape_zonaprop_agencias.py` (descubrir
   *agencias*, no propiedades) está permitido, o lo congelamos también?
2. **Dominio ERETZ:** ¿hay dominio definitivo para User-Agent de geocoding y SEO?
3. **Universo objetivo:** ¿de dónde salen las 5.500 (vs 2.049 elegibles / 7.004 main)?
   ¿Hay fuente de descubrimiento pendiente?
4. **Frontend:** ¿autorizás el PR de naming visible ahora o lo dejamos para después?
5. **Workers:** ¿qué límite de paralelismo tolera tu entorno/IP sin antibot? (define throughput real)
6. **Ventana de carga pesada:** ¿cuántos días tolerás para la primera pasada nacional?

## 14. Próximo paso recomendado
**Fase A (higiene)** — empezar por drenar los 3.000 pending y preparar el PR de
naming-documentación, sin tocar producción ni código crítico. En paralelo, decidir
las preguntas abiertas para planificar Fases B-C.
