# Estado actual para ChatGPT o Codex

## Contexto general

Estoy trabajando en un proyecto llamado InmoCapital.

InmoCapital es una plataforma proptech que busca centralizar, estandarizar y analizar información inmobiliaria de distintas inmobiliarias. La idea no es crear simplemente otro portal de propiedades, sino una herramienta que ayude a usuarios, inmobiliarias e inversores a entender mejor el mercado inmobiliario mediante datos, mapas, filtros, métricas, comparaciones y asistencia con inteligencia artificial.

## Objetivo principal

Construir una plataforma pública, profesional y escalable, comenzando por Argentina, especialmente la provincia de Santa Fe, y luego expandiendo a otras provincias y países.

El objetivo no es hacer un MVP básico. La intención es crear una plataforma capaz de salir al público con datos confiables, buena experiencia de usuario y una estructura preparada para crecer.

## Ubicación local del proyecto

```text
D:\INMO CAPITAL\Inmo-Capital-main
---

# Estado de avance actualizado

Esta sección sirve para que ChatGPT, Codex o Claude sepan qué se hizo, qué falta y cuál es el próximo paso.

## Última actualización

Fecha: 20/05/2026

## Qué ya está hecho

- Se creó la estructura inicial del proyecto InmoCapital.
- Se configuró Supabase como base de datos principal.
- Se creó el frontend con Next.js.
- Se está usando Tailwind para estilos.
- Se está usando Leaflet para el mapa.
- Se está usando Python y Playwright para scraping.
- Se creó la bóveda de Obsidian para documentar el proyecto.
- Se crearon notas principales en Obsidian para estrategia, producto, desarrollo, Supabase, scraping, marketing, finanzas, legal, prompts, errores, decisiones y pendientes.
- Se creó un índice rápido en Obsidian.
- Se creó un registro diario.
- Se definió que Obsidian será el centro de control del proyecto.
- Se definió que los errores de datos deben corregirse desde el scraper, no manualmente en Supabase.

## Qué está parcialmente hecho

- El scraping está avanzado, pero todavía necesita correcciones.
- La base de datos ya tiene propiedades cargadas, pero hay que revisar calidad de datos.
- El frontend ya existe, pero todavía necesita mejoras de diseño, filtros y experiencia mobile.
- El mapa funciona o está en desarrollo, pero hay que validar bien datos con coordenadas.
- Las notas de Obsidian ya están creadas, pero deben mantenerse actualizadas.

## Qué falta hacer

- Revisar el estado actual del scraping.
- Revisar últimas corridas de scraping.
- Detectar errores repetidos.
- Corregir errores desde código.
- Revisar propiedades sin coordenadas.
- Revisar propiedades sin imágenes.
- Revisar propiedades sin precio.
- Revisar duplicados.
- Mejorar normalización de ciudades, provincias y barrios.
- Mejorar frontend público.
- Mejorar filtros.
- Mejorar experiencia mobile.
- Definir mejor la propuesta comercial para inmobiliarias.
- Revisar riesgos legales antes del lanzamiento público.

## Qué no hay que hacer

- No borrar tablas sin revisar.
- No modificar Supabase de forma destructiva.
- No corregir manualmente en Supabase errores que deberían corregirse desde el scraper.
- No hacer cambios técnicos grandes sin explicar.
- No forzar GitHub.
- No asumir que un error está solucionado sin probarlo.
- No priorizar cantidad de propiedades por encima de calidad de datos.

## Próximo paso recomendado

Revisar el estado actual del scraping y detectar qué errores se están repitiendo.

Después, pedir a Codex o Claude que corrija esos errores desde el código, no desde la base de datos manualmente.

## Pregunta actual o tarea actual

Pendiente de completar antes de abrir un nuevo chat.

Ejemplo:

Necesito revisar los últimos errores del scraper y decidir qué corregir primero.

```
# Registro de trabajo - 2026-05-21## ProyectoInmoCapital## Objetivo del díaMejorar la calidad de datos del scraper, especialmente en:- tipo de propiedad- páginas falsas de listado- propiedades vendidas/reservadas/alquiladas- cierre correcto de items de scraping- precios- imágenes históricasLa prioridad fue corregir problemas desde el código y no manualmente desde Supabase.---## 1. Corrección de `tipo_propiedad = "otro"`### Problema detectadoHabía muchas propiedades guardadas con:```texttipo_propiedad = "otro"
```

aunque el tipo real podía inferirse desde el título o descripción.

Ejemplo:

```
schema_type = "RealEstateListing"titulo = "Departamento 3 ambientes en Palermo"
```

Antes:

```
tipo_propiedad = "otro"
```

Esperado:

```
tipo_propiedad = "departamento"
```

### Causas

- `_parse_jsonld_item()` usaba `schema_type` como fuente principal.
- Tipos genéricos como `RealEstateListing`, `Residence`, `Product`, `Offer`, `Thing` terminaban en `"otro"`.
- `normalizar_tipo()` no normalizaba acentos.
- Palabras como `dúplex`, `galpón`, `depósito` podían fallar.
- Algunas abreviaturas comunes no estaban contempladas correctamente.

### Correcciones aplicadas

Archivo:

```
scraper/scraper_propiedades.py
```

Cambios:

- Se limpió `TIPO_MAP`.
- Se agregó normalización de acentos.
- Se mejoró `normalizar_tipo()`.
- Se agregaron casos como:
    - `dto`
    - `dpto`
    - `ph`
    - `dúplex`
    - `duplex`
    - `galpón`
    - `galpon`
- Se agregó detección de tipos schema.org genéricos.
- Se modificó `_parse_jsonld_item()` para usar:
    1. título
    2. descripción
    3. schema_type específico
    4. `"otro"` solo si no se puede inferir nada
- También se ajustó `_html_extract_detail()` porque algunos WordPress devolvían textos genéricos como `"Venta"` y bloqueaban el fallback al título.

### Resultado

La corrección quedó validada con pruebas controladas.

---

## 2. Corrección de páginas de listado guardadas como propiedades

### Problema detectado

Algunas páginas de listado o resultados se estaban guardando como propiedades reales.

Ejemplo:

```
titulo: Casas Venta Banfield 5 Ambientesdescripcion: Se encontraron 32 resultados para Banfieldurl: /propiedades/casas_venta_banfield_5_ambientes
```

### Causas

- El filtro de URL no detectaba slugs con guiones bajos `_`.
- La descripción no se revisaba para detectar textos de listado.
- Algunas URLs largas se aceptaban automáticamente como propiedad.
- No se detectaban bien patrones como:
    - `casas_venta_banfield`
    - `departamentos_alquiler_2_ambientes`
    - `lotes_venta_santa_fe`

### Correcciones aplicadas

Archivo:

```
scraper/scraper_propiedades.py
```

Cambios:

- Se agregaron plurales a `_PROPERTY_TYPE_SLUG_WORDS`.
- Se agregó `_LISTING_TEXT_RE`.
- Se mejoró `_listing_url_not_property_detail_reason()`.
- Se mejoró `_is_listing_like_property_payload()`.
- Se mejoró `_invalid_listing_property_reason()`.
- Ahora se revisa tanto título como descripción.

### Resultado

La corrección quedó validada con tests.  
Las páginas de listado se descartan y las propiedades reales se mantienen.

---

## 3. Corrección de propiedades vendidas, reservadas o alquiladas

### Problema detectado

Propiedades con títulos como:

```
VENDIDO!!! Chalet 4 ambientesRESERVAD@!! Dto 2 ambientesAlquilado - Departamento céntrico
```

se guardaban como activas.

### Decisión

No se descartan esas propiedades.  
Se guardan como:

```
estado = "inactivo"
```

### Correcciones aplicadas

Archivo:

```
scraper/scraper_propiedades.py
```

Cambios:

- Se agregó `_UNAVAILABLE_STATE_RE`.
- Se agregó `_detectar_estado_no_disponible()`.
- Se integró la detección en `_save_queue_properties()`.

Estados detectados:

- vendido
- vendida
- reservado
- reservada
- reservad@
- alquilado
- alquilada
- suspendido
- suspendida
- pausado
- pausada
- no disponible
- fuera de mercado

### Resultado

La corrección quedó validada.  
No se confundieron operaciones activas como `"en venta"` o `"en alquiler"` con propiedades no disponibles.

---

## 4. Corrección del cierre de `scraping_run_items`

### Problema detectado

Si fallaba la RPC:

```
finish_scraping_item_success
```

con error 404, una extracción exitosa podía terminar marcada como error.

### Causa

El scraper mezclaba dos cosas:

1. extracción y guardado de propiedades
2. cierre del item de scraping

Si el scraping salía bien pero fallaba el cierre por RPC, el item podía quedar marcado incorrectamente.

### Corrección aplicada

Archivo:

```
scraper/scraper_propiedades.py
```

Cambios:

- Se agregó fallback REST directo.
- Si falla `finish_scraping_item_success`, se intenta actualizar `scraping_run_items` por REST.
- El scraping exitoso ya no se convierte en `parse_error` solo porque falló el cierre.

### Resultado

El flujo normal fue probado correctamente.

Ejemplo:

```
Guastavino e Imbert71 propiedades detectadas71 con fotosestado final successexit code 0
```

No se ejecutó SQL en Supabase.  
No se hicieron migraciones.

---

## 5. Corrección y validación de precios

### Problema detectado

Había propiedades sin precio. Se revisó si eran:

- casos legítimos sin precio publicado
- propiedades vendidas/reservadas
- errores de parsing
- precios en formatos no detectados

### Hallazgos

La mayoría de los casos sin precio parecen legítimos, porque el sitio no publica precio.

Ejemplo:

```
Pasaje Drago 4229
```

El sitio no publica precio, por lo que es correcto dejar:

```
precio = null
```

### Bugs corregidos

Archivo:

```
scraper/scraper_propiedades.py
```

Cambios:

1. Se corrigió detección de precios numéricos sin símbolo:

Antes podía fallar:

```
1.200.000
```

Ahora se detecta como:

```
ARS 1200000
```

2. Se corrigió detección de palabras como:

```
dólardólaresdolares
```

3. Se mejoró `_parse_jsonld_item()` para que, si JSON-LD no trae `offers.price`, intente extraer precio desde la descripción JSON-LD.

Caso real corregido:

```
Junin 3537 Cochera 12 Nivel 3
```

Antes:

```
precio = null
```

Después:

```
precio = 13000moneda = USDfuente = json_ld
```

### Formatos validados

```
USD 120.000        -> USD 120000U$S 120.000        -> USD 120000US$ 120000         -> USD 120000u$s 85.000         -> USD 85000$ 450.000          -> ARS 450000ARS 450000         -> ARS 4500001.200.000          -> ARS 1200000Consultar precio   -> nullPrecio a consultar -> nullVendido            -> nullReservado          -> nullAlquilado          -> null
```

### Resultado

Corrección de precios validada.  
No se agregó columna nueva como `precio_consultable`.  
No se hicieron migraciones.

---

## 6. Diagnóstico y mejora de imágenes

### Problema detectado

Algunas propiedades estaban:

- sin imágenes
- con imágenes falsas
- con logos
- con placeholders
- con íconos
- con assets institucionales

### Funciones revisadas

Archivo:

```
scraper/scraper_propiedades.py
```

Funciones revisadas:

- `_normalize_image_url`
- `fake_property_image_reason`
- `clean_property_images`
- `extraer_imagenes`
- `_collect_json_image_values`
- `_parse_tokko_listing_cards`
- `_enrich_tokko_detail_images`
- `_fetch_tokko_detail_images`
- `_extract_detail_page`
- `_sanitize_scraped_props_for_quality`
- `build_protected_update_payload`

### Bugs corregidos

El sanitizer aceptaba imágenes institucionales como fotos reales.

Ejemplos descartados ahora:

```
static.tokkobroker.com/tfw/img/phone...static.tokkobroker.com/static/img/user.pngafip.gob.ar/images/f960/DATAWEB.jpglogos de matrículas como cucicba, cmcpsi, cciníconos socialesimagen-de-relleno-680x510.jpg
```

### Resultado

Se mejoraron los filtros para descartar:

- logos
- placeholders
- íconos
- favicons
- banners
- assets institucionales
- avatares
- SVGs
- imágenes de superficie o interfaz

---

## 7. Implementación de `--repair-images`

### Objetivo

Reparar imágenes históricas de propiedades existentes sin correr el scraper completo.

### Modo agregado

Dry-run:

```
python scraper\scraper_propiedades.py --repair-images --agency-id ID --dry-run --limit 20
```

Ejecución real:

```
python scraper\scraper_propiedades.py --repair-images --agency-id ID --limit 20
```

### Funciones agregadas

Archivo:

```
scraper/scraper_propiedades.py
```

Funciones:

- `_repair_images_skip_url_reason()`
- `_load_properties_for_image_repair()`
- `_extract_clean_images_for_repair()`
- `_patch_property_images_only()`
- `run_repair_images()`

Flags agregados:

```
--repair-images--agency-id
```

### Seguridad del modo

El modo:

- no crea propiedades nuevas
- no borra propiedades
- no toca precio
- no toca moneda
- no toca ciudad
- no toca provincia
- no toca barrio
- no toca dirección
- no toca estado
- no toca hash
- no toca `url_normalizada`
- no toca `inmobiliaria_id`
- no toca título
- no toca descripción
- solo actualiza el campo `imagenes`

Payload usado:

```
{"imagenes": images}
```

---

## 8. Reparación controlada de imágenes históricas

### 8.1 KAIZEN PROPIEDADES

ID:

```
2408
```

Estado inicial:

```
116 propiedades sin imágenes limpias
```

Se ejecutaron lotes controlados con:

```
python scraper\scraper_propiedades.py --repair-images --agency-id 2408 --limit N
```

Resultado final:

```
Total propiedades: 116Con imágenes limpias: 116Sin imágenes limpias: 0URLs con error: 0
```

Estado:

```
COMPLETADO
```

---

### 8.2 Inmobiliaria Eugenio Hoffmann

ID:

```
92
```

Estado inicial:

```
17 propiedades15 sin imágenes limpias2 con imágenes limpias
```

Se ejecutó primero dry-run:

```
python scraper\scraper_propiedades.py --repair-images --agency-id 92 --dry-run --limit 10
```

Luego reparación real:

```
python scraper\scraper_propiedades.py --repair-images --agency-id 92 --limit 10python scraper\scraper_propiedades.py --repair-images --agency-id 92 --limit 5
```

Resultado final:

```
Total propiedades: 17Con imágenes limpias: 17Sin imágenes limpias: 0URLs con error: 0
```

Estado:

```
COMPLETADO
```

---

### 8.3 FES Brokers

ID:

```
304
```

Estado inicial aproximado:

```
Total propiedades: 203Con imágenes limpias: 72Sin imágenes limpias: 131
```

Se ejecutó dry-run:

```
python scraper\scraper_propiedades.py --repair-images --agency-id 304 --dry-run --limit 10
```

Luego reparación real en lotes.

Resultado final:

```
Total propiedades: 203Con imágenes limpias: 203Sin imágenes limpias: 0URLs con error: 0
```

Estado:

```
COMPLETADO
```

---

### 8.4 Navarrete

ID:

```
305
```

Estado inicial aproximado:

```
Total propiedades: 179Con imágenes limpias: 64Sin imágenes limpias: 115
```

Se ejecutó dry-run:

```
python scraper\scraper_propiedades.py --repair-images --agency-id 305 --dry-run --limit 10
```

Resultado del dry-run:

```
Procesadas: 10Encontró imágenes nuevas: 10URLs con error: 0Propiedades actualizadas: 0
```

Luego se ejecutó un lote real:

```
python scraper\scraper_propiedades.py --repair-images --agency-id 305 --limit 10
```

Resultado parcial:

```
Total propiedades: 179Con imágenes limpias aproximadas: 74Sin imágenes limpias aproximadas: 105URLs con error: 0
```

Estado:

```
PENDIENTE CONTINUAR
```

---

## 9. Resultado total aproximado de reparación de imágenes

Propiedades reparadas con imágenes limpias:

```
KAIZEN: 116Eugenio Hoffmann: 17FES Brokers: 131Navarrete: 10
```

Total aproximado:

```
274 propiedades reparadas con imágenes limpias
```

Nota: en mensajes previos se mencionó un total parcial mayor al sumar por lotes, pero el resumen consolidado por inmobiliaria da aproximadamente 274 propiedades efectivamente reparadas.

---

## 10. Validaciones realizadas

Comandos ejecutados durante el proceso:

```
python -m py_compile scraper\scraper_propiedades.pypython scraper\scraper_propiedades.py --help
```

También se usaron:

```
python scraper\scraper_propiedades.py --repair-images --agency-id ID --dry-run --limit Npython scraper\scraper_propiedades.py --repair-images --agency-id ID --limit N
```

No se hicieron:

- migraciones
- cambios manuales en Supabase
- borrado de datos
- cambios en frontend
- commits
- scraping masivo no controlado

---

## 11. Pendientes

### Pendiente 1: continuar reparación de imágenes en Navarrete

Inmobiliaria:

```
Navarreteagency-id: 305
```

Estado pendiente:

```
aprox. 105 propiedades sin imágenes limpias
```

Comando sugerido para continuar:

```
python scraper\scraper_propiedades.py --repair-images --agency-id 305 --limit 20
```

Continuar en lotes controlados mientras:

```
URLs con error: 0Propiedades actualizadas: 20
```

Cuando queden menos de 20 candidatas, ajustar el límite.

---

### Pendiente 2: revisar próximas inmobiliarias candidatas

Candidatas mencionadas:

```
Humboldt / Guastavino - agency-id 1818Ortiz de Urbina - agency-id 11
```

Antes de reparar una inmobiliaria nueva, hacer siempre:

```
python scraper\scraper_propiedades.py --repair-images --agency-id ID --dry-run --limit 10
```

Si sale limpio, hacer reparación real.

---

### Pendiente 3: revisar coordenadas / geocoding

Todavía queda pendiente revisar propiedades sin coordenadas.

Este punto probablemente dependa más del pipeline de geocoding que del scraper principal.

---

### Pendiente 4: revisar bug de URLs de listado

Quedó anotado un caso detectado durante pruebas:

```
Eugenio Hoffmann detectó una URL tipo /property/page/4/ como propiedad candidata
```

Esto debe revisarse luego dentro del blindaje de páginas de listado.

---

## 12. Decisiones importantes tomadas

- No corregir datos manualmente en Supabase cuando el problema viene del scraper.
- Corregir primero el código para evitar que el problema se repita.
- Usar dry-run antes de reparar una inmobiliaria nueva.
- Ejecutar reparaciones reales en lotes chicos.
- No gastar tokens de Codex/Claude en tareas repetitivas que pueden ejecutarse manualmente.
- Usar Codex/Claude solo para diagnóstico, diseño de correcciones y validaciones técnicas.
- Priorizar calidad de datos sobre cantidad de propiedades.

---

## 13. Estado final del día

El scraper quedó más robusto en:

- clasificación de tipo de propiedad
- descarte de páginas falsas de listado
- detección de propiedades no disponibles
- cierre correcto de items de scraping
- parsing de precios
- limpieza de imágenes falsas
- reparación controlada de imágenes históricas

Se completó la reparación de imágenes para:

- KAIZEN PROPIEDADES
- Inmobiliaria Eugenio Hoffmann
- FES Brokers

Queda pendiente continuar con:

- Navarrete
- próximas inmobiliarias candidatas
- coordenadas/geocoding
- revisión final de bugs de listado
---

## 14. Geocoding: diagnóstico, prueba y corrección puntual

### Diagnóstico inicial

Se revisó el estado de coordenadas en InmoCapital.

Estado general:

```text
Propiedades totales: 12.807
Con latitud + longitud: 4.895
Sin coordenadas: 7.912
Coordenadas parciales: 0
Activas sin coordenadas: 7.744
Vista frontend mapa: 4.816
Pendientes en v_geocoding_priority_clean: 7.912
Cola actual v_next_geocoding_batch: 100
  Geocoding:
- Primer lote aplicado: 19 coordenadas
- Caso malo 11763: corregido y limpiado
- Resultado viejo malo 271: invalidado
- Últimos pendientes: mayormente review/skipped
- No conviene seguir automático hoy
  
  Geocoding:
- Primer lote aplicado: 19 coordenadas
- Caso malo 11763: corregido y limpiado
- Resultado viejo malo 271: invalidado
- Últimos pendientes: mayormente review/skipped
- No conviene seguir automático hoy

---

# Estado técnico actual (2026-05-29)

## Arquitectura actual (pipeline dual)

```text
Scraper
  → Neon propiedades_raw
  → validate_raw_properties.py
  → Neon propiedades_staging
  → geocode_staging.py
  → build_publish_queue.py
  → Neon publish_queue
  → publish_to_supabase.py
  → Supabase propiedades
  → Frontend
```

Neon es la base **interna/operativa** (raw, staging, geocoding, cola de publicación).
Supabase es la base **pública/canónica** que alimenta el frontend (mapa).

## Scripts existentes

- `scripts/validate_raw_properties.py` — propiedades_raw → propiedades_staging.
- `scripts/build_publish_queue.py` — propiedades_staging → publish_queue.
- `scripts/publish_to_supabase.py` — publish_queue → Supabase.
- `scripts/run_daily_pipeline.py` — orquestador diario (coordina todas las fases por subprocess).
- `scripts/geocode_staging.py` — geocoding interno de staging (FASE 3.5).
- `scripts/create_scraping_run_from_next_batch.py` — arma la cola de scraping.
- `scraper/scraper_propiedades.py` — scraper principal (dual Supabase + Neon).

## Flags importantes

- `USE_INTERNAL_DB=true` → activa Neon (modo dual).
- `USE_INTERNAL_DB=false` → mantiene el modo seguro (comportamiento por defecto, solo Supabase).
- `--allow-playwright` → existe en el orquestador, pero **no se usa por defecto**. Si se activa, propaga `--allow-playwright` al scraper. Valida que Playwright esté instalado antes de seguir.
- `--allow-pending-geo` → existe, pero **no conviene usarlo masivamente**: publicaría propiedades sin coordenadas.
- `geocode_staging.py` → ahora permite **evitar** `--allow-pending-geo`, porque geocodifica antes de armar la cola.

## Orden de fases del orquestador

```text
FASE 0/1  crear cola (create_scraping_run_from_next_batch.py)
FASE 2    scraping (scraper_propiedades.py)
FASE 3    validate (validate_raw_properties.py)
FASE 3.5  geocoding staging (geocode_staging.py)   ← nuevo
FASE 4    build publish_queue (build_publish_queue.py)
FASE 5    publish a Supabase (publish_to_supabase.py)
```

Default del orquestador: **dry-run**. Solo escribe con `--commit`.

## Diagnóstico vigente

La familia de error dominante del scraping es `requires_playwright`. La mejora general de mayor impacto es habilitar Playwright de forma controlada (`--allow-playwright`). Detalle en [[12 - Errores y soluciones]] (sección "Diagnóstico run53").