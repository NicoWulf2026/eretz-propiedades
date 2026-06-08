# publish_queue commit — Pinamar 21 IDs

**Fecha:** 2026-06-08  
**ids-file:** `publish_queue_ids_pinamar_21_done.csv`  
**Script:** `build_publish_queue.py --commit`

---

## Resultado

| Etapa | Resultado |
|-------|-----------|
| Limpieza direcciones (3 IDs) | COMMIT OK |
| publish_queue encoladas | **21/21** |
| publish_queue skips | 0 |
| accion_final | commit |

---

## FASE 1 — Limpieza direccion_normalizada (3 IDs)

Antes del commit se limpiaron los 3 campos con ruido de marketing:

| staging_id | Antes | Después |
|-----------|-------|---------|
| 81411 | `Martín Pescador 1485 PB 103 - Financiación Flexible` | `Martín Pescador 1485 PB 103` |
| 81412 | `Martín Pescador 1485 1° 111 - Financiación Flexible` | `Martín Pescador 1485 1° 111` |
| 81413 | `Martín Pescador 1485 1° 216 - Financiación Flexible` | `Martín Pescador 1485 1° 216` |

Guard: `geocoding_status='done' AND direccion_normalizada ILIKE '%Financiación Flexible%'`  
Lat/lon: sin cambio (`-37.0963679, -56.8740228` × 3)

---

## FASE 3 — publish_queue commit

**21 IDs encolados, todos priority=1, status=pending.**

| staging_id | Tipo | Precio USD | Precision | Priority |
|-----------|------|-----------|-----------|---------|
| 81392 | departamento | 257,885 | street | 1 |
| 81396 | departamento | 230,000 | street | 1 |
| 81399 | casa | 1,850,000 | street | 1 |
| 81400 | casa | 460,000 | street | 1 |
| 81401 | casa | 480,000 | street | 1 |
| 81402 | casa | 395,000 | street | 1 |
| 81403 | casa | 465,000 | street | 1 |
| 81408 | casa | 560,000 | street | 1 |
| 81410 | departamento | 105,000 | street | 1 |
| 81411 | departamento | 223,000 | street | 1 |
| 81412 | departamento | 230,000 | street | 1 |
| 81413 | departamento | 192,000 | street | 1 |
| 81414 | casa | 490,000 | street | 1 |
| 81418 | casa | 280,000 | street | 1 |
| 81420 | casa | 690,000 | street | 1 |
| 81421 | departamento | 162,782 | street | 1 |
| 81422 | departamento | 255,938 | street | 1 |
| 81423 | departamento | 465,000 | street | 1 |
| 81424 | departamento | 161,137 | street | 1 |
| 81443 | departamento | 200,000 | street | 1 |
| 81445 | departamento | 120,000 | street | 1 |

Validation score: **100 × 21**  
Imagenes: **10 × 21**  
Geocoding: **street × 21**, bbox Pinamar OK × 21

---

## FASE 4 — Verificación post-commit

| Check | Resultado |
|-------|-----------|
| publish_queue antes | count=71, max_id=254 |
| publish_queue después | count=92, max_id=296 |
| Delta | **+21 exacto** ✓ |
| IDs fuera del ids-file encolados | **ninguno** ✓ |
| Todas priority=1 | ✓ |
| Supabase | NO tocada ✓ |
| publish_to_supabase.py | NO ejecutado ✓ |
| frontend | NO tocada ✓ |
| .env | sin cambio (modificado hace ~11 días) ✓ |
| geocoding nuevo | NO ejecutado ✓ |

---

## Próximo paso recomendado

Los 21 IDs están en `publish_queue` con `status=pending, priority=1`.

El siguiente paso es **`publish_to_supabase.py`** — que lee la publish_queue y publica
en Supabase las propiedades en status=pending.

**Requiere autorización explícita** antes de ejecutar.  
Sugerencia: dry-run primero si el script lo soporta, luego commit.

**FRENADO aquí. No se ejecutó publish_to_supabase.py.**
