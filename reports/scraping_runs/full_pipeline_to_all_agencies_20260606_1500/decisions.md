# Pipeline Completo — Decisiones

Fecha: 2026-06-06

---

## Decisiones de alcance

| Decisión | Detalle | Razón |
|---|---|---|
| SOLO FASE 0-3 por ahora | FASE 4+ queda pendiente | Autorización incremental |
| No importar a Neon en esta sesión | Solo capturas locales | Safety |
| No validate staging | Pendiente | Safety |
| No geocoding | Pendiente | Safety |
| No publish_queue commit | Pendiente | Safety |
| No Supabase | Explicitamente prohibido | Safety |
| No git push | Explicitamente prohibido | Safety |

---

## Decisiones técnicas

| ID | Decisión | Razón | Alternativa descartada |
|---|---|---|---|
| D01 | Re-scrape Watson: HTTP simple, sin Playwright | Watson es HTML estático | Playwright (overhead innecesario) |
| D02 | Timeout Watson: 90s | Sitio pequeño, carga rápida | 300s (excesivo para sitio sin JS) |
| D03 | Fix precios: fix por familia si hay patrón | No hardcodear Watson | Fix puntual por dominio |

---

## Decisiones pendientes de usuario

| Decisión | Contexto |
|---|---|
| ¿Publicar las 14 props encolables? | 10 innoacafayate + 4 camposdelapampa calidad aceptable |
| ¿Google Maps API para Cafayate? | Nominatim falló para 2 IDs |
| ¿Geocoding commit para las 8 pending? | Pueblo Nuevo (Mza) + watson sin ubicación |
| ¿Avanzar a FASE 4+ (extractor_missing_selector)? | Pendiente resultados FASE 0-3 |
