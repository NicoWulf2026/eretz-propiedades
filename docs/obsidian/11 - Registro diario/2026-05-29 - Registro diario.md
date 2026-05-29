# 2026-05-29 - Registro diario

## Resumen del día

Día de mucho avance en la **arquitectura dual Supabase + Neon** y en el **pipeline diario** de InmoCapital.

Se consolidó el flujo completo desde el scraping hasta la publicación en Supabase, se sumó una etapa nueva de geocoding interno, se integró todo en el orquestador diario, se agregó soporte controlado de Playwright y se hizo un diagnóstico de errores de scraping agrupado por familias.

El foco fue: **avanzar de forma conservadora, sin scraping masivo y sin publicar a Supabase sin control.**

---

## Qué se hizo hoy

### Pipeline dual (etapas consolidadas)

- **Etapa 1 - Neon preparado**: base interna lista con schema (`propiedades_raw`, `propiedades_staging`, `publish_queue`, `geocoding_results`, `scraping_runs`, `scraping_run_items`, `daily_update_summary`, etc.).
- **Etapa 2 - Scraper dual Supabase + Neon**: el scraper escribe la copia cruda en `propiedades_raw` en Neon cuando `USE_INTERNAL_DB=true`, sin romper el flujo hacia Supabase.
- **Etapa 3 - propiedades_raw → propiedades_staging**: `validate_raw_properties.py` valida y promueve filas crudas a staging con `validation_score`.
- **Etapa 4 - propiedades_staging → publish_queue**: `build_publish_queue.py` arma la cola de publicación desde staging.
- **Etapa 5 - publish_queue → Supabase**: `publish_to_supabase.py` publica de forma controlada y en lotes chicos.
- **Etapa 6 - run_daily_pipeline.py**: orquestador diario que coordina todas las etapas por subprocess; default dry-run, escritura solo con `--commit`.

### Geocoding interno

- **Etapa 6.5 - geocode_staging.py**: script nuevo que geocodifica filas de `propiedades_staging` con `geocoding_status='pending'`, cachea en `geocoding_results` y actualiza staging con lat/lon y estado `done/failed/skipped`. Reutiliza la lógica pura de `scraper/geocoder.py` (Nominatim, limpieza de direcciones, validación de bounds). Default dry-run; en dry-run no llama a Nominatim ni escribe.
- **Integración en el orquestador**: se sumó como **FASE 3.5 - GEOCODING STAGING**, entre validate (FASE 3) y build_publish_queue (FASE 4). Esto permite que `build_publish_queue` corra **sin** `--allow-pending-geo`, es decir, sin publicar propiedades sin coordenadas.

### Playwright controlado

- Se agregó el flag **`--allow-playwright`** al orquestador `run_daily_pipeline.py`.
  - Por defecto el comportamiento **no cambia**: si no se pasa el flag, el scraper se invoca igual que antes.
  - Con `--allow-playwright`, el orquestador propaga `--allow-playwright` al scraper.
  - Validación liviana: si se pide el flag y Playwright no parece instalado, aborta con mensaje claro (no instala nada).
  - El dry-run plan muestra `playwright=HABILITADO/DESHABILITADO` y el resumen registra `allow_playwright=True/False`.

### Diagnóstico de errores de scraping

- Se analizó la última corrida completa (**run53**, 2026-05-25) agrupando errores por **familias**.
- **Hallazgo principal**: `requires_playwright` es la familia dominante (123 casos ≈ 37% de los errores), causada por tener Playwright apagado por defecto y porque el orquestador diario no lo activaba.
- **Decisión**: no activar Playwright por defecto, sino dejarlo detrás del flag controlado `--allow-playwright`.
- Detalle completo en [[12 - Errores y soluciones]] (sección "Diagnóstico run53").

---

## Validaciones realizadas

- `geocode_staging.py` probado con ~5 propiedades: resultado **5 done**, latitud/longitud cargadas, `geocoding_results` guardado.
- `run_daily_pipeline.py --dry-run` liviano probado: aparece correctamente la **FASE 3.5 - GEOCODING STAGING**.
- `USE_INTERNAL_DB` se seteó solo en la terminal y volvió a quedar sin valor al final (modo seguro).
- `py_compile`, `--help` y `git diff --check` OK en los scripts tocados.

### Commits relevantes del día

- `12df803` Add staging geocoding script
- `db7ce2a` Add staging geocoding phase to daily pipeline
- `7af5248` Add controlled Playwright flag to daily pipeline

---

## Decisiones tomadas hoy

- No correr todas las inmobiliarias de golpe; nada de scraping masivo.
- Diagnosticar primero por familias de error antes de corregir.
- Corregir causas generales, no inmobiliarias una por una.
- Los casos específicos se corrigen aparte, solo si vale la pena.
- Playwright se suma como opción controlada (`--allow-playwright`), no por defecto.
- El pipeline diario debe seguir siendo conservador.
- Supabase no debe recibir cargas masivas sin control.
- Neon se usa como base interna para staging, validación, geocoding y cola de publicación.

(Registradas también en [[10 - Decisiones importantes]].)

---

## Próximos pasos

- Commitear si quedara pendiente algún cambio de `run_daily_pipeline.py`.
- Test controlado con `--test-url` y `--allow-playwright` sobre `modernia.com.ar`.
- Si funciona, repetir con otro caso de la familia `requires_playwright`.
- No correr el pipeline completo todavía. No correr scraping masivo.
- Diseñar después mejoras para `no_property_links`, timeouts y `strategy_quality_failed`.
- Tratar antibot / site_down como casos no-código o específicos.

(Detalle en [[11 - Pendientes]].)

---

## Cierre del día

Quedó armado y documentado el pipeline dual de punta a punta:

Scraper → Neon `propiedades_raw` → `validate_raw_properties.py` → Neon `propiedades_staging` → `geocode_staging.py` → `build_publish_queue.py` → Neon `publish_queue` → `publish_to_supabase.py` → Supabase → Frontend.

El próximo foco es el retest controlado de Playwright antes de habilitarlo en corridas reales.
