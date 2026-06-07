# Auditoría Post-Checkpoint — FASE 1

- Fecha: 2026-06-06
- Checkpoint: commit `69cac0db`
- Rama: `fix/scraping-diagnostics-batch`

---

## 1. Fixes aplicados y en producción (commit 69cac0db)

| Fix | Archivo | Tipo | Estado |
|---|---|---|---|
| Fix A — Ubicación desde hostname | `validate_raw_properties.py` | Global | ✅ ACTIVO |
| Fix B — Operación desde URL path ASP CMS | `import_captured_props_to_neon.py` | Por familia | ✅ ACTIVO |
| Fix E — Rechazo títulos short-ID CMS (Ca266.Html) | `scraper_propiedades.py` | Global | ✅ ACTIVO |
| Fix E — Título desde `section.famie-benefits-area` | `scraper_propiedades.py` | Por familia | ✅ ACTIVO |
| Fix E — Safety net en importer | `import_captured_props_to_neon.py` | Global | ✅ ACTIVO |
| Feature — `--ids-file` en `geocode_staging.py` | `geocode_staging.py` | Feature | ✅ ACTIVO |
| Feature — `--ids-file` en `build_publish_queue.py` | `build_publish_queue.py` | Feature | ✅ ACTIVO |

---

## 2. Estado de las 24 propiedades de la tanda (staging_ids 81036-81059)

### Import y validate (COMPLETADOS)

- **24 props importadas** a `propiedades_raw` (raw_ids ~82057-82080)
- **24 props validadas** a `propiedades_staging` (staging_ids 81036-81059)
- Fix A funcionó: `missing_location` bajó de 24 → 3 (solo Watson)
- Fix B funcionó: operaciones correctas en Innoacafayate (venta/alquiler desde URL path)
- Fix E funcionó: 4 camposdelapampa con títulos filename corregidos con UPDATE controlado

### Geocoding (PARCIAL)

| staging_id | Agencia | Geocoding | Situación |
|---|---|---|---|
| 81036, 81038 | Innoacafayate | `pending` | Sin autorización para commit |
| 81041, 81042, 81044 | Innoacafayate | `pending` | Sin autorización para commit |
| 81047, 81048 | Innoacafayate | **`failed`** | Nominatim no cubre calles de Cafayate |
| 81057, 81058, 81059 | Watson | `pending` | Sin ubicación → skippear |

### Publish queue (DRY-RUN HECHO, COMMIT PENDIENTE)

- **14 encolables** como priority=2
- **10 saltadas** por geocoding_status=pending o failed
- NO se hizo commit → pendiente autorización

---

## 3. Errores pendientes conocidos

### Watson sin precio (RESUELTO EN FASE 3)

- **Causa raíz**: JSON-LD `@type=Product` intercepta antes de `_html_extract_detail`
- **Fix G** aplicado: enriquecimiento de precio desde HTML cuando JSON-LD no lo provee
- **Resultado**: 2/3 Watson props ahora tienen precio (88,000 USD y 125,000 USD)
- 1/3 genuinamente sin precio en HTML

### Títulos CamposDelAmapa (MEJORADOS)

- Antes: `Ca266.Html`, `Mo342.Html`, `Mo340.Html`, `Mi319.Html` (inaceptables)
- Staging: UPDATE a "Campo en venta en La Pampa" (genérico pero válido)
- Re-scrape post Fix E: títulos ricos recuperados
  - ca266 → "Departamento Loventué Muy buen acceso 6.000 ha Cria"
  - mo342 → "Limay Mahuida Oportunidad 15.000 ha Cria"
  - mo340 → "Departamento Chalileo Oportunidad 30.000 ha Cria"
  - mi319 → "Departamento Toay Bosque abierto 600 ha Ganaderia y Agricultura"
- Si se hace re-import, los títulos ricos serán los correctos

### Geocoding Cafayate — Nominatim sin cobertura (PENDIENTE)

- Props 81047, 81048 fallaron con Nominatim (status=failed)
- Cafayate es ciudad pequeña (~15k hab), sin cobertura callejera en Nominatim
- Opciones: Google Maps API (requiere autorización + API key)
- Las 2 props son publicables como priority=2 sin geocoding si se resetea a pending
- Pendiente: decisión del usuario sobre Google Maps API

### Publish queue sin commit (PENDIENTE AUTORIZACIÓN)

- 14 encolables listas (priority=2)
- No se hará commit sin autorización explícita
- Las 10 props excluidas requieren geocoding o tienen datos incompletos

---

## 4. Qué funciona (no tocar)

| Componente | Estado |
|---|---|
| Fix A — ubicación hostname | ✅ FUNCIONANDO — 21/24 props ubicadas |
| Fix B — operación URL path | ✅ FUNCIONANDO — alquiler/venta correctos en Inno |
| Fix E — títulos short-ID | ✅ FUNCIONANDO — 0 títulos filename en re-scrape |
| `--ids-file` en geocode/publish | ✅ FUNCIONANDO — aislamiento correcto |
| propiedades_raw / staging (histórico) | ✅ INTACTO — 81035 props anteriores sin tocar |

---

## 5. Qué no tocar

| Ítem | Razón |
|---|---|
| Frontend | Sin autorización explícita |
| publish_queue (commit) | Sin autorización explícita |
| geocoding masivo | Sin autorización + sin API key Google |
| publish_to_supabase.py | Sin autorización explícita |
| .env | Regla absoluta |
| propiedades_staging ids < 81036 | Sin autorización — histórico |
| Zonaprop / Argenprop | Regla absoluta — siempre skip |

---

## 6. Próximo bloque óptimo recomendado

Según evidencia actual, el siguiente bloque de mayor impacto es:

1. **Fix G** (Watson JSON-LD sin precio) — ya implementado en FASE 3
2. **Fix por extractor_missing_selector** — 27+ dominios identificados que podrían capturar props con fix de selectores (FASE 4)
3. **Re-import camposdelapampa** con títulos ricos post Fix E — 4 props con titulos genéricos en staging podrían mejorarse
4. **Geocoding para Cafayate** — decidir sobre Google Maps API para 7 props pending + 2 failed

---

*Generado: 2026-06-06 · FASE 1 post-checkpoint 69cac0db*
