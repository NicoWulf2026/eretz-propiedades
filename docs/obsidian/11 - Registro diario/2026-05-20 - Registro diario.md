# 2026-05-20 - Registro diario

## Resumen del día

Hoy se comenzó a ordenar ERETZ Propiedades dentro de Obsidian, creando una estructura centralizada para documentar el proyecto.

El objetivo fue empezar a usar Obsidian como centro de control del proyecto, separando información estratégica, técnica, comercial, legal, financiera y de seguimiento.

---

## Qué se hizo hoy

- Se creó la bóveda de Obsidian para ERETZ Propiedades.
- Se creó el panel principal del proyecto.
- Se creó la nota de estado actual para ChatGPT, Codex o Claude.
- Se creó la nota de decisiones importantes.
- Se creó la nota de pendientes.
- Se creó la nota de errores y soluciones.
- Se creó la nota de Supabase y base de datos.
- Se creó la nota de scraping.
- Se creó la nota de desarrollo técnico.
- Se creó la nota de producto y funcionalidades.
- Se creó la nota de visión y estrategia.
- Se creó la nota de marketing y marca.
- Se creó la nota de finanzas y modelo de negocio.
- Se creó la nota de legal y riesgos.
- Se creó la nota de prompts útiles.
- Se empezó a ordenar la documentación del proyecto en un solo lugar.

---

## Notas creadas

- [[00 - Panel principal InmoCapital]]
- [[01 - Visión y estrategia]]
- [[02 - Producto y funcionalidades]]
- [[03 - Desarrollo técnico]]
- [[04 - Supabase y base de datos]]
- [[05 - Scraping]]
- [[06 - Marketing y marca]]
- [[07 - Finanzas y modelo de negocio]]
- [[08 - Legal y riesgos]]
- [[09 - Prompts útiles]]
- [[10 - Decisiones importantes]]
- [[11 - Pendientes]]
- [[12 - Errores y soluciones]]
- [[13 - Estado actual para ChatGPT o Codex]]

---

## Decisiones tomadas hoy

### Usar Obsidian como centro de control

Se decidió usar Obsidian como espacio central para ordenar el conocimiento del proyecto.

Obsidian no reemplaza a GitHub, Supabase ni Google Sheets.

La función de cada herramienta será:

- Obsidian: conocimiento, decisiones y documentación.
- GitHub: código y control de versiones.
- Supabase: base de datos real.
- Google Sheets: números, listas y seguimiento simple.
- ChatGPT / Codex / Claude: ayuda técnica, estratégica y operativa.

---

## Estado actual del proyecto

ERETZ Propiedades está en desarrollo.

El proyecto ya tiene:

- Frontend con Next.js.
- Estilos con Tailwind.
- Mapa con Leaflet.
- Backend / scraping con Python.
- Scraping con Playwright.
- Base de datos en Supabase.
- Código versionado con GitHub.
- Documentación centralizada en Obsidian.

---

## Pendientes principales

### Alta prioridad

- Ordenar visualmente las notas en carpetas.
- Mantener actualizado el panel principal.
- Actualizar la nota de estado actual cuando haya avances técnicos.
- Usar la nota de prompts útiles para pedir ayuda técnica.
- Registrar errores nuevos en la nota de errores y soluciones.
- Registrar decisiones importantes en la nota de decisiones.

---

## Próximos pasos

- Crear carpetas en Obsidian.
- Mover cada nota a su carpeta correspondiente.
- Revisar que el panel principal tenga enlaces correctos.
- Empezar a usar el registro diario cada vez que se trabaje en ERETZ Propiedades.
- Retomar el desarrollo técnico del proyecto.
- Revisar el estado actual del scraping.
- Revisar últimas corridas y errores.
- Pedir correcciones a Codex o Claude cuando sea necesario.

---

## Errores o problemas del día

No se registraron errores técnicos del proyecto.

Sí hubo aprendizaje inicial sobre el uso de Obsidian:

- Cómo crear notas.
- Cómo renombrarlas.
- Cómo pegar contenido.
- Cómo organizar documentación.
- Cómo usar enlaces internos entre notas.

---

## Observaciones

La estructura inicial de Obsidian ya permite que ERETZ Propiedades tenga un centro de control claro.

A partir de ahora, cada avance importante debería registrarse en alguna de estas notas:

- Si es una decisión: [[10 - Decisiones importantes]]
- Si es un error: [[12 - Errores y soluciones]]
- Si es una tarea: [[11 - Pendientes]]
- Si es contexto general: [[13 - Estado actual para ChatGPT o Codex]]
- Si es avance diario: esta nota de registro diario

---

## Cierre del día

Hoy se avanzó en la organización general del proyecto.

El foco no fue programar, sino ordenar la información para que el desarrollo futuro sea más claro, seguro y fácil de continuar.

```
# 2026-05-27 - Supabase caído - pausa técnica## EstadoSupabase no está respondiendo correctamente.Se ejecutó un health check liviano contra:`propiedades?select=id&limit=1`Resultado:```textReadTimeoutread timeout=15
```

Esto confirma que Supabase no responde ni siquiera a una consulta mínima.

---

## Decisión tomada

No seguir golpeando Supabase mientras esté en este estado.

No ejecutar:

- scraping
- retry-errors
- retry-partial-extractions
- repair-images
- geocoder
- mediciones globales
- count exact
- consultas pesadas
- Table Editor

---

## Estado seguro actual

- GitHub está actualizado.
- Neon ya está preparado con schema interno.
- `USE_INTERNAL_DB=false`.
- `INTERNAL_DB_URL` está cargado pero inactivo.
- Supabase sigue siendo el comportamiento por defecto.
- FAMILIA 4 queda pendiente de validar.
- No hay procesos corriendo.

---

## Causa probable

El problema parece ser infraestructura/carga de Supabase, no código local.

Las fotos no son el problema principal porque se guardan como links externos, no en Supabase Storage.

La saturación probablemente viene de:

- consultas pesadas
- `count=exact`
- lectura masiva de `scraping_run_items.metadata`
- retries
- geocoding
- repairs
- procesos simultáneos
  
```
## Backup realizadoSe exportaron y guardaron las principales tablas de inmobiliarias desde Supabase:- `inmobiliarias_main`- `inmobiliarias_scraping`- `inmobiliarias_staging`Ubicación local:`D:\INMO CAPITAL\Inmo-Capital-main\backups supabase`Estado:- Backup de inmobiliarias realizado correctamente.- Pendiente exportar `propiedades` por lotes.- No ejecutar scraping hasta estabilizar Supabase.- Neon queda preparado pero inactivo.
```

## Etapa 1 Neon completada  
  
Se completó la preparación de Neon como base interna para ERETZ Propiedades.  
  
Tablas existentes en Neon:  
  
- `scraping_runs`  
- `scraping_run_items`  
- `geocoding_results`  
- `inmobiliarias_staging`  
- `propiedades_raw`  
- `propiedades_staging`  
- `publish_queue`  
- `data_quality_issues`  
- `daily_update_summary`  
  
Funciones existentes:  
  
- `claim_next_scraping_item`  
- `start_scraping_item`  
- `retry_scraping_item`  
- `finish_scraping_item_success`  
- `finish_scraping_item_error`  
- `close_scraping_run_if_finished`  
- `cleanup_old_neon_data`  
  
Estado:  
  
- Neon preparado.  
- `USE_INTERNAL_DB` sigue en `false`.  
- No se activó scraping con Neon todavía.  
- Supabase sigue siendo la base pública/liviana.  
- Próxima etapa: adaptar el scraper para escribir también en `propiedades_raw` en Neon.
  
  ## Etapa 2 completada - Modo dual Supabase + Neon

Se validó correctamente el modo dual del scraper.

Resultado de prueba:

- Inmobiliaria procesada: Inmobiliaria Berengeno
- Items procesados: 1
- Estado: success
- Propiedades detectadas: 240
- Propiedades nuevas: 22
- Propiedades actualizadas: 218
- Errores: 0

Supabase:
- Recibió correctamente las propiedades finales.
- El flujo anterior no se rompió.

Neon:
- Recibió copia cruda en `propiedades_raw`.
- Las filas quedaron con status `raw`.
- Se confirmó `hash_dedup`, título, precio, inmobiliaria_id y scraped_at.

Corrección realizada:
- Se corrigió el mapeo `id → scraping_run_item_id` en `claim_next_scraping_item`.

Limpieza:
- El item de prueba fallido quedó marcado como `error / test_aborted`.
- No quedaron items en estado `running`.
- `USE_INTERNAL_DB` volvió a modo seguro.

Estado:
- Etapa 2 validada.
- Próxima etapa: crear validador `propiedades_raw → propiedades_staging`.