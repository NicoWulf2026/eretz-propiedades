# Sprint Autónomo — Inicio 2026-06-07

**Modo:** Sprint Autónomo Controlado  
**Rama:** `fix/scraping-diagnostics-batch`  
**Último commit:** `9aac0efff` — fix(geocoding): reject coordinates outside city bounds

---

## Estado inicial del pipeline

| Tabla | Valor |
|-------|-------|
| propiedades_raw (total) | 76,599 |
| propiedades_raw (status=raw, no validadas) | **58** ← quick win |
| propiedades_staging (total) | 76,541 |
| staging geocoding_status=done | 18,848 |
| staging geocoding_status=pending | 42,504 |
| staging geocoding_status=skipped | 13,116 |
| staging geocoding_status=failed | 2,002 |
| staging status=queued | 61 |
| publish_queue pending | 61 |

## Bloque 2 — Estado final

| Etapa | Estado |
|-------|--------|
| Import raw 54 props | ✅ |
| Validate staging 54 props | ✅ |
| Fix K — address validation | ✅ `c7aad4d61` |
| Geocoding commit 47 props | ✅ 37 done / 10 failed |
| Fix L — bbox validación | ✅ `9aac0efff` |
| publish_queue commit 31 confiables | ✅ |
| Fix K DB (81298/81308/81309 dir_normalizada) | ⚠ PENDIENTE AUTORIZACIÓN |
| Supabase publish | ⏸ FRENO — espera autorización |

## Familias de error — overnight run (600 failures totales)

| Familia | Count | Dominios únicos | Acción sprint |
|---------|-------|-----------------|--------------|
| requires_playwright | 246 | 246 | Fuera de scope (sin Playwright masivo) |
| **no_property_links_confirmed** | **121** | **121** | → Familia 2 sprint |
| **item_timeout** | **80** | **80** | → Familia 3 sprint (timeout fix) |
| sin_propiedades | 49 | 49 | Baja prioridad (sites vacíos) |
| **strategy_quality_failed** | **37** | **37** | → Familia 4 sprint |
| timeout | 26 | 26 | Parte de item_timeout |
| no_property_links | 15 | 15 | Parte de familia 2 |
| site_down_confirmed | 14 | 14 | Skip (sites caídos) |

## Prioridad del sprint

1. **Validate 58 props Pinamar** (raw→staging, inmo 4019) — quick win
2. **Cerrar Bloque 2** — Fix K DB pendiente
3. **no_property_links_confirmed** — 121 dominios, clasificar y atacar subset fixable
4. **strategy_quality_failed** — 37 dominios, WP/PHP patterns
5. **item_timeout** — 80 dominios, timeout 120s es bajo

## Reglas activas

- NO git push
- NO Supabase sin autorización
- NO .env
- NO frontend
- NO geocoding masivo
- NO Playwright masivo
- NO zonaprop / argenprop

## Próximo paso inmediato

Validate dry-run de 58 props Pinamar → si cumple condiciones → validate commit → geocoding readiness.
