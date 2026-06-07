# Pipeline Completo — Riesgos

Fecha: 2026-06-06

---

## Riesgos activos

| Riesgo | Severidad | Probabilidad | Mitigación | Estado |
|---|---|---|---|---|
| Publicar props con títulos filename | ALTA | BAJA | Fix E aplicado + UPDATE hecho | RESUELTO |
| Geocoding masivo accidental | ALTA | BAJA | `--ids-file` obligatorio | CONTROLADO |
| Scrapear Zonaprop/Argenprop | CRÍTICA | BAJA | Regla en código + regla de negocio | CONTROLADO |
| publish_queue commit no autorizado | ALTA | BAJA | Dry-run first, freno explícito | CONTROLADO |
| Importar props con datos incorrectos | MEDIA | MEDIA | Dry-run + validaciones previas | CONTROLADO |
| Fix que empeora dominios que funcionan | MEDIA | MEDIA | py_compile + test before/after | ACTIVO |
| Watson sin precio publicado | MEDIA | ALTA | FASE 3 investiga | PENDIENTE |
| Cafayate sin coordenadas publicado | BAJA | ALTA | Aceptado: geo=skipped OK para p2 | ACEPTADO |

---

## Riesgos de código

| Riesgo | Archivo | Descripción |
|---|---|---|
| scraper_propiedades.py muy grande | scraper/ | +6000 líneas — difícil de testear completo |
| Fixes anteriores sin tests unitarios | varios | Dependemos de py_compile + before/after manual |
| geocode_staging.py 478 cambios sin tests | scripts/ | Solo validado por uso exitoso |

---

## Señales de freno automático

- Props con precio incorrecto (inventado) → FRENO
- Fix que produce titles vacíos en dominios que antes funcionaban → FRENO
- Cualquier intento de write a Supabase → FRENO
- publish_queue commit sin dry-run previo → FRENO
- Timeout >70% del batch → FRENO
- Zonaprop/Argenprop en candidatos → SKIP inmediato
