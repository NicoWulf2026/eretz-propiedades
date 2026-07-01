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
- **PR-BE-PROD-09e parcialmente completado** — 4 intentos acumulados (2026-06-28 al 2026-07-01):
  - Intento 1: 99/615 fuentes, +3.082 props (cortado por desconexión sesión)
  - rerun_01: 123/615 fuentes, +841 props (ídem)
  - rerun_02: 586/615 fuentes (95%), +12.610 props (cortado por MemoryError en Playwright)
  - rerun_03: 250/615 fuentes (41%), +2.752 props (cortado por apagado accidental del equipo)
  - **Delta total 09e: +19.285 propiedades**
- propiedades actuales: **134.844**.
- 29 fuentes pendientes de 09e (nunca procesadas) — ver `_scratch/run_manifest_09e_audit/manifest_pendientes_09e.csv`.
- 276 fuentes sin FK omitidas (sin match en inmobiliarias_main).
- Decisión: no lanzar rerun_04 ahora. Pasar a auditoría backend y frontend.
- Próxima corrida: mismo manifest `manifest_success_only.csv`, dedup protege las 134.844 URLs existentes.

El sistema de batches diarios automáticos sigue sin estar activo. El scheduler y la cola de scraping siguen pendientes de definición.

Ver: [[11 - Pendientes]], [[07 - Deduplicacion]]

---

## Notas relacionadas

- [[00 - Decisiones oficiales]]
- [[05 - Logs y errores]]
