# Batches diarios de scraping

Ultima actualizacion: 2026-06-09

---

## Objetivo

Actualizar informacion de propiedades diariamente de forma automatica y controlada.

No se hace un unico scraping gigante. Se usa un sistema de batches o cola de scraping.

---

## Estrategias de division de batches

Posibles criterios para dividir el scraping diario:

- Por provincia.
- Por tipo de web (WordPress, cdh, Webnode, PHP custom, etc.).
- Por inmobiliaria.
- Por prioridad (inmobiliarias activas, con mas propiedades, con scraping exitoso reciente).
- Por ultimo scraping exitoso (las que tienen mas tiempo sin actualizar van primero).
- Por cantidad de errores acumulados (las mas problematicas van al final o a un batch separado).

---

## Logs y trazabilidad

Cada corrida de scraping debe registrar:

- ID del batch.
- Fecha y hora de inicio.
- Fecha y hora de fin.
- Estado: exitoso, parcial, error, timeout.
- Cantidad de propiedades detectadas.
- Cantidad de propiedades nuevas.
- Cantidad de propiedades actualizadas.
- Cantidad de errores.
- Reintentos.

---

## Estado actual (2026-07-01)

Pipeline manual activo: `scripts/run_manifest.py` con manifest CSV.

- **PR-BE-PROD-09d completado** — 50 fuentes, 1.039 propiedades nuevas directamente en `propiedades`.
- **PR-BE-PROD-09e COMPLETADO** — 4 intentos + validación final 29 pendientes (2026-06-28 al 2026-07-01):
  - Delta total 09e + validación: **+19.445 propiedades**
- propiedades actuales: **135.004**.
- Manifest A (892 fuentes) agotado — 0 pendientes.
- 277 fuentes sin FK omitidas (sin match en inmobiliarias_main).
- **Manifest B preparado (no ejecutado)** — 1.391 candidatas nuevas, 894 con FK.

### Pilot 50 — completado (2026-07-01)

Corrida de prueba: 25 fuentes más livianas + 25 más pesadas, workers=2. Objetivo: medir tiempos reales antes de comprometerse con la corrida completa de 894 fuentes.

| Métrica | Valor |
|---|---|
| Fuentes intentadas | 50/50 |
| Propiedades insertadas | **2.262** |
| Crashes de worker | 0 |
| W0 (25 livianas) | 464 props · 1h 14m |
| W1 (25 pesadas) | 1.798 props · 3h 11m |
| Tasa W0 (livianas) | **20,3 f/h** |
| Tasa W1 (pesadas) | **7,9 f/h** |
| Throughput total (reloj) | **15,6 f/h** |
| Errores 409 (hash_dedup) | 1 fuente (inmobiliaria_terra_srl) |
| Errores DB / MemoryError | 0 / 0 |

**Bugs detectados:**
- **409 hash_dedup**: `batch_save_only_new` lanzaba RuntimeError al encontrar un duplicado en DB, tirando toda la fuente. Fix aplicado: fallback fila-a-fila, skipea duplicados, continúa. Tests: **68/68 verdes**.
- **54 URLs con ancla** (`#fragment`) en manifest_b_with_fk.csv: corregidas automáticamente (strip de fragmento, sin alterar la ruta base).
- **Chunking estático desbalanceado**: con fuentes ordenadas light-first, W0 terminó en 1h14m y quedó ocioso 2h mientras W1 seguía. Fix: manifest balanceado (zigzag interleave).

**Decisión post-Pilot:** NO ejecutar Manifest B hasta resolver los 3 bugs. Todos resueltos. Manifest B listo para corrida cuando se autorice.

**Archivos nuevos en `_scratch/preflight_manifest_b/`:**
- `manifest_b_with_fk_balanced.csv` — 894 filas, zigzag (pesadas intercaladas entre workers)
- `manifest_b_normal_sources.csv` — 754 fuentes (ry ≤ 100)
- `manifest_b_heavy_sources.csv` — 140 fuentes (ry > 100)

### Estimaciones Manifest B (basadas en Pilot 50)

Tasas reales: livianas 20,3 f/h · pesadas 7,9 f/h. Distribución: 754 normal + 140 heavy.

| Escenario | Descripción | Clock estimado |
|---|---|---|
| **workers=2, corrida única balanceada** | manifest_b_with_fk_balanced.csv, ambos workers terminan juntos | **~30-34h** |
| **2 tandas** | normal primero (~21h) + heavy aparte (~9h) | **~30h** (2 sesiones) |
| **3 tandas** | thirds iguales balanceados (~12h c/u) | **~36h** (3 sesiones) |
| **Sin balance (naive)** | light-first: W0 termina en 22h, W1 en 57h | **~57h** (W0 ocioso 35h) |

Recomendación: corrida única con `manifest_b_with_fk_balanced.csv` o 2 tandas si se quiere sesiones más cortas con reinicio de RAM entre ellas.

El sistema de batches diarios automáticos sigue sin estar activo. El scheduler y la cola de scraping siguen pendientes de definición.

Ver: [[11 - Pendientes]], [[07 - Deduplicacion]]

---

## Notas relacionadas

- [[00 - Decisiones oficiales]]
- [[05 - Logs y errores]]
