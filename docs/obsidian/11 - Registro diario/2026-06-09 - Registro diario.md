# Registro diario — 2026-06-09

## Sprint A — Cierre oficial

Sprint A completado. Objetivo: alinear codigo y schema con las decisiones de FASE 1.

---

### Cambios de codigo aplicados

**scraper/models.py**
- ALLOWED_OPERACIONES ampliado: agrega `consultar`, `venta_y_alquiler`, `alquiler_temporario`.

**scraper/scraper_propiedades.py**
- `normalizar_operacion()`: fallback cambiado de `"venta"` a `"consultar"`.
- Agrega deteccion de senales simultaneas de venta + alquiler → `"venta_y_alquiler"`.

**scripts/validate_raw_properties.py**
- `normalize_operation()`: nunca retorna None. Fallback → `"consultar"`.
- Hard reject por `invalid_operation` eliminado. Reemplazado por soft issue `operacion_normalizada_consultar`.
- Propiedades sin operacion reconocida ahora entran a staging como `consultar`, no se rechazan.

**scripts/build_publish_queue.py**
- `VALID_OPERATIONS` ampliado: agrega `consultar`, `venta_y_alquiler`.

**scripts/publish_to_supabase.py**
- `VALID_OPERATIONS` ampliado igual que build_publish_queue (estaban desincronizados).

**frontend/src/lib/property-supabase-service.ts**
- `.eq("estado", "activo")` cambiado a `.in("estado", ["activo", "activa"])` en dos queries.
- Compatibilidad dual: el frontend funciona tanto antes como despues de la migracion.

**internal_db_schema.sql**
- Comentario documentando los valores reconocidos de `operacion` (sin cambiar constraints SQL — los campos son TEXT libre).

---

### Tests

- `tests/test_sprint_a_operacion.py`: 11/11 OK.
- ESLint sobre el archivo de frontend: 0 warnings, 0 errores.

---

### Migracion Supabase ejecutada

Archivo: `migrations/supabase_sprint_a_operacion_estado.sql`

Resultado:
- `estado` migrado: `activo → activa`, `inactivo → desconocida`.
- Constraint nueva en `estado`: activa / reservada / vendida / alquilada / no_detectada_en_ultimo_scraping / consultar / desconocida.
- Constraint nueva en `operacion`: venta / alquiler / alquiler_temporario / consultar / venta_y_alquiler.

Distribucion post-migracion:
- estado activa: 90.497
- estado desconocida: 829
- operacion venta: 86.519
- operacion alquiler: 4.793
- operacion alquiler_temporario: 14

---

### Archivos nuevos creados

- `tests/test_sprint_a_operacion.py`
- `migrations/supabase_sprint_a_operacion_estado.sql`

---

### Lo que NO se hizo en Sprint A (queda para Sprint B)

- No se toco el scraper para publicar `"activa"` en lugar de `"activo"`.
- No se actualizo `mark_inactivos()` en `scraper_propiedades.py`.
- No se agrego label "Consultar" ni "Venta y alquiler" en el frontend.
- No se corrio scraping masivo.
- No se hizo push.

---

---

## Sprint B — Geocoding + estados nuevos — Cerrado 2026-06-09

Sprint B completado. Objetivos: mejorar contexto de geocoding, agregar ciudades, alinear estado "activa" en scraper y pipeline.

---

### Cambios de codigo aplicados

**scraper/geocoder.py**
- Sauce Viejo agregado a `CITY_BBOXES`: bbox `(-31.62, -31.48, -60.92, -60.70)`.
- Tandil y General Alvear ya estaban presentes desde fix anterior.

**scripts/geocode_staging.py**
- Nuevos argumentos CLI: `--fallback-city` y `--fallback-province`.
- Modulo globals `_BATCH_FALLBACK_CITY` / `_BATCH_FALLBACK_PROVINCE` seteados desde `main()`.
- `infer_location_context_from_raw()` actualizado:
  - Agrega deteccion de "sauce viejo" en URL/contexto.
  - Fallback global como ultimo recurso cuando la prop y la inmobiliaria no tienen ciudad propia.
- Uso tipico: `python scripts/geocode_staging.py --dry-run --fallback-city "General Alvear" --fallback-province "Mendoza"`.

**scraper/scraper_propiedades.py**
- 10 ocurrencias de `"estado": "activo"` cambiadas a `"activa"`.
- `mark_inactivos()`:
  - Filtro cambiado de `eq.activo` a `in.(activo,activa)` para compatibilidad dual durante transicion.
  - Estado destino cambiado de `"inactivo"` a `"no_detectada_en_ultimo_scraping"`.
  - Docstring y logs actualizados.
- Deteccion de estado no disponible (`_detectar_estado_no_disponible`): resultado cambiado de `"inactivo"` a `"no_detectada_en_ultimo_scraping"`.
- Test log interno actualizado: `"activo"` → `"activa"`, `"inactivo"` → `"no_detectada_en_ultimo_scraping"`.

**scripts/publish_to_supabase.py**
- `staging_to_prop()`: agrega `"estado": staging.get("estado") or "activa"`.
- Props nuevas publicadas ya no tendran estado NULL en Supabase.
- Si staging trae un estado especifico (ej: no_detectada_en_ultimo_scraping), se preserva.

---

### Validacion

- `tests/test_sprint_a_operacion.py`: 11/11 OK (Sprint A intacto).
- `py_compile` limpio: scraper_propiedades, geocoder, geocode_staging, publish_to_supabase.
- Grep de seguridad: cero usos de `"activo"` o `"inactivo"` como valor de estado en los 4 archivos.
- Dry-run geocoding: 19/20 probe, 1 skipped (garbage address), 0 errores.
- Fallback args impresos correctamente en dry-run. No se activo porque las props del lote actual ya tienen ciudad propia — comportamiento correcto.

---

### Lo que NO se hizo en Sprint B

- No se corrio scraping masivo.
- No se publico masivamente a Supabase.
- No se toco `.env`.
- No se hizo push.
- Labels de frontend para "Consultar", "Venta y alquiler", carteles de estado: quedan para Sprint D.
- Geocoding masivo de Angelina (General Alvear) con fallback: disponible, no ejecutado.

---

---

## Sprint C — Batches, baseline y deteccion de desaparecidas — Cerrado 2026-06-09

Sprint C completado. Objetivos: integrar deteccion de propiedades desaparecidas al pipeline, soporte batch, filtro por provincia.

---

### Cambios de codigo aplicados

**scripts/publish_to_supabase.py**
- Agrega columnas `action` y `propiedad_supabase_id` a los SQL de lectura de `publish_queue`.
- Nueva funcion `deactivate_one(db, propiedad_supabase_id)`: hace PATCH a Supabase con `estado='no_detectada_en_ultimo_scraping'`.
- Loop principal: rama `action == 'deactivate'` ejecuta `deactivate_one()` o dry-run.
- Nuevo contador `deactivated_ok` en output.

**scripts/enqueue_deactivations.py** (archivo nuevo creado en Sprint C)
- Compara props activas en Supabase con hashes del ultimo scraping exitoso en Neon.
- Props activas no encontradas en el ultimo scraping → se encolan como `action='deactivate'` en `publish_queue`.
- Modos:
  - `--inmobiliaria-id ID`: procesa una sola inmobiliaria (output verbose).
  - `--all-from-run RUN_ID`: procesa todas las inmobiliarias con scraping exitoso en esa corrida (modo batch para el pipeline).
- `--dry-run` (default) / `--commit`.
- No borra propiedades; solo agrega entradas a la cola.

**scripts/run_daily_pipeline.py**
- Nuevo argumento `--with-deactivations`.
- FASE 2.5 — ENCOLAR DESACTIVACIONES: si activo, corre `enqueue_deactivations.py --all-from-run {run_id} --commit` post-scraping.
- Si `run_id` no esta disponible y `--with-deactivations` esta activo, la fase se omite con log.
- Plan dry-run muestra FASE 2.5 con el comando real o mensaje de "deshabilitado".

**scripts/create_scraping_run_from_next_batch.py**
- Nuevo argumento `--provincia TEXT`.
- Filtra candidatos de `v_next_scraping_batch` por provincia en ambas pasadas (lista_para_batch=true y nuevas).
- Sin `--provincia`: comportamiento identico al anterior (sin filtro).
- Output imprime `provincia_filter=todas` o la provincia especificada.

---

### Arquitectura resultante: deteccion de desaparecidas

Flujo completo post-Sprint C:

```
Scraping exitoso
  → mark_inactivos() [en linea, durante scraping]
     PATCH Supabase: estado=no_detectada_en_ultimo_scraping para props de la agencia no vistas
  → FASE 2.5 enqueue_deactivations.py --all-from-run RUN_ID [opcional, post-scraping]
     Compara hashes en Neon vs activas en Supabase
     Encola action='deactivate' en publish_queue para props que se escaparon
  → FASE 5 publish_to_supabase.py
     Procesa deactivate: PATCH estado=no_detectada_en_ultimo_scraping en Supabase
```

Dos mecanismos complementarios:
- `mark_inactivos()`: inmediato, en linea, agencia por agencia.
- `enqueue_deactivations.py`: auditoria post-run, agarra lo que mark_inactivos no alcanzo.

---

### Validacion

- `py_compile` limpio: enqueue_deactivations, run_daily_pipeline, create_scraping_run_from_next_batch.
- `--help` de enqueue_deactivations: muestra grupo mutuamente exclusivo `--inmobiliaria-id` / `--all-from-run`.
- `--help` de create_scraping_run: muestra `--provincia`.
- dry-run de run_daily_pipeline sin `--with-deactivations`: muestra "FASE 2.5 - DESACTIVACIONES: deshabilitado".
- dry-run con `--with-deactivations`: muestra comando `enqueue_deactivations.py --all-from-run {RUN_ID} --commit`.

---

### Lo que NO se hizo en Sprint C

- No se corrio scraping masivo.
- No se publico masivamente a Supabase.
- No se toco `.env`.
- No se hizo push.
- Scheduler/cron: no implementado; deployment-specific (Windows Task Scheduler o cron Linux).
- Test real con agencia: requiere corrida de scraping real; restringido por REGLAS ROJAS.

---

---

## Sprint D — Plan preparado 2026-06-09

Sprint D definido. Objetivo: prueba controlada del pipeline completo con 1 agencia real.

### Definicion

- Reemplaza al anterior "Sprint D — Frontend y presentacion" (movido a Sprint E).
- No es scraping masivo ni publicacion masiva.
- Cada paso con `--commit` requiere autorizacion explicita.

### Pendientes no bloqueantes heredados de Sprint C

- **Scheduler/cron**: template de corrida diaria (Windows Task Scheduler o cron Linux). Deployment-specific. No urgente hasta tener Sprint D validado.
- **Test real con agencia**: es exactamente el objetivo de Sprint D.
- **Geocodificar Angelina (General Alvear)**: disponible con `geocode_staging.py --fallback-city "General Alvear" --fallback-province "Mendoza"`. No urgente.
- **Retry outliers geocoding**: props 81820 (Pagliaro) y 81777 (Angelina). No urgente.

### Referencia

Ver: [[Sprint D - Prueba controlada pipeline]]

---

## Notas relacionadas

- [[Roadmap 2026-06-09]]
- [[Sprint D - Prueba controlada pipeline]]
- [[00 - Decisiones oficiales]]
- [[08 - Estados de propiedades]]
- [[10 - Geocoding]]
