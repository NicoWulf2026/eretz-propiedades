# Pendientes de InmoCapital

Esta nota sirve para ordenar todo lo que falta hacer en el proyecto.

La idea es separar los pendientes por prioridad para no mezclar tareas urgentes con ideas futuras.

---

## Alta prioridad

Estas tareas son las más importantes para avanzar con el desarrollo real del proyecto.

### Scraping

- Revisar el estado actual del scraping.
- Detectar errores repetidos en los scrapers.
- Corregir errores desde el código, no manualmente en Supabase.
- Mejorar el guardado de propiedades nuevas.
- Mejorar el guardado de propiedades actualizadas.
- Revisar inmobiliarias que se detectan pero no guardan propiedades.
- Revisar sitios que requieren Playwright.
- Revisar sitios caídos o inaccesibles.
- Registrar cantidad de propiedades detectadas, guardadas y actualizadas.
- Evitar que los items queden trabados en estado running.
- Mejorar logs del scraper para entender qué pasa en cada inmobiliaria.

### Base de datos / Supabase

- Revisar propiedades sin coordenadas.
- Revisar propiedades sin imágenes.
- Revisar propiedades sin precio.
- Revisar propiedades sin ciudad o provincia.
- Detectar duplicados.
- Revisar normalización de barrios, ciudades y provincias.
- Revisar monedas y precios.
- Revisar campos vacíos importantes.
- Mantener las tablas ordenadas.
- Evitar cambios destructivos en la base.

### Frontend

- Revisar que el mapa cargue correctamente.
- Revisar que las propiedades se vean bien en el listado.
- Revisar cards de propiedades.
- Mejorar filtros principales.
- Mejorar experiencia mobile.
- Mejorar placeholders cuando no hay imágenes.
- Revisar que los datos mostrados coincidan con Supabase.

---

## Media prioridad

Estas tareas son importantes, pero pueden hacerse después de estabilizar scraping y datos.

### Producto

- Definir funcionalidades principales de la primera versión pública.
- Definir qué filtros estarán disponibles.
- Definir cómo será la vista de propiedad.
- Definir cómo se mostrarán las inmobiliarias.
- Definir cómo funcionarán favoritos.
- Definir alertas para usuarios.
- Pensar la experiencia del usuario en mobile.
- Pensar el modo avanzado para usuarios expertos.

### Inteligencia artificial

- Definir cómo funcionará el asesor inmobiliario con IA.
- Definir qué información podrá responder.
- Definir límites del chatbot.
- Pensar preguntas frecuentes del usuario.
- Pensar recomendaciones automáticas.

### Marketing

- Definir mensaje principal de la marca.
- Preparar textos para explicar qué es InmoCapital.
- Preparar propuesta para inmobiliarias.
- Preparar comunicación para usuarios.
- Pensar contenido para redes.
- Definir identidad visual y tono de marca.

---

## Baja prioridad

Estas tareas son importantes a futuro, pero no son urgentes ahora.

### Finanzas

- Definir costos mensuales del proyecto.
- Estimar costos de servidores.
- Estimar costos de scraping.
- Definir posibles planes de monetización.
- Pensar precios para inmobiliarias.
- Pensar ingresos por publicidad.
- Pensar ingresos por leads.
- Pensar ingresos por análisis de datos.

### Legal

- Revisar riesgos del scraping.
- Revisar términos y condiciones.
- Revisar política de privacidad.
- Revisar uso de datos públicos.
- Revisar contacto con inmobiliarias.
- Consultar con abogado antes del lanzamiento público.

### Expansión

- Expandir a más ciudades.
- Expandir a más provincias.
- Agregar más inmobiliarias.
- Agregar propiedades en pozo.
- Agregar análisis por zonas.
- Agregar métricas de inversión.
- Agregar comparación con inflación, IPC u otros índices.

---

## Pendientes de esta semana

- [ ] Actualizar estado actual del scraping.
- [ ] Revisar últimos errores del scraper.
- [ ] Pedir a Codex corrección de errores detectados.
- [ ] Revisar cantidad de propiedades guardadas.
- [ ] Revisar propiedades sin coordenadas.
- [ ] Revisar propiedades sin imágenes.
- [ ] Actualizar nota de errores y soluciones.
- [ ] Actualizar nota de estado actual para ChatGPT o Codex.

---

## Pendientes de hoy

- [ ] Crear estructura inicial de Obsidian.
- [ ] Crear nota panel principal.
- [ ] Crear nota estado actual para ChatGPT o Codex.
- [ ] Crear nota decisiones importantes.
- [ ] Crear nota pendientes.
- [ ] Crear nota errores y soluciones.
      
      ## Pendiente crítico - Supabase inestable  
  
- [ ] Esperar que Supabase vuelva a responder.  
- [ ] Ejecutar health check liviano con `select=id&limit=1`.  
- [ ] No correr scraping, geocoder, repairs ni retries mientras haya ReadTimeout.  
- [ ] Validar FAMILIA 4 solo cuando Supabase responda con `status: 200`.  
- [ ] Mantener Neon preparado pero inactivo.  
- [ ] No activar `USE_INTERNAL_DB=true` todavía.

---

## Próximos pasos (2026-05-29) - Pipeline dual y Playwright

### Inmediatos

- [ ] Commitear si queda pendiente algún cambio de `run_daily_pipeline.py`.
- [ ] Test controlado con `--test-url` y `--allow-playwright` sobre `modernia.com.ar`.
  - Comando: `python scraper/scraper_propiedades.py --test-url "https://www.modernia.com.ar/" --allow-playwright --workers 1`
  - `--test-url` no consume cola y no escribe en Neon ni Supabase.
- [ ] Si funciona, repetir con otro caso de la familia `requires_playwright` (ej. `gama-sa.com`).

### Reglas de seguridad para estos pasos

- [ ] NO correr el pipeline completo todavía.
- [ ] NO correr scraping masivo. NO usar workers altos.
- [ ] NO `run_daily_pipeline.py --commit` durante las pruebas.
- [ ] NO publicar a Supabase durante el retest.
- [ ] NO usar `count(*)` ni `count=exact`.

### Mejoras a diseñar después (por familia de error)

- [ ] `no_property_links` / `no_property_links_confirmed`: re-medir DESPUÉS de habilitar Playwright; lo que siga fallando se trata como mejora general de detección de links.
- [ ] Timeouts (`timeout` / `item_timeout`): ajustar timeouts de sitemap/static/diagnose y/o bajar workers para sitios lentos.
- [ ] `strategy_quality_failed`: revisar umbral de calidad tras extracción.
- [ ] Antibot (`blocked`) y `site_down_confirmed`: tratar como casos **no-código** o **específicos** (no se arreglan con cambios generales del scraper).