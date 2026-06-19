# Prompts utiles

Ultima actualizacion: 2026-06-04

Esta nota guarda prompts reutilizables para las proximas etapas de ERETZ Propiedades. Los prompts incluyen reglas de seguridad para evitar publicacion accidental, cambios destructivos o reparaciones manuales propiedad por propiedad.

## Prompt 1: Auditoria de causas raiz de calidad

```text
Estoy trabajando en ERETZ Propiedades.

Objetivo:
Auditar causas raiz de problemas de calidad en Neon propiedades_raw/propiedades_staging, sin reparar manualmente propiedades una por una.

Problemas a auditar:
- missing_location;
- geocoding_pending;
- missing_price;
- missing_images;
- duplicate;
- geocoding_failed.

Reglas:
- No tocar .env.
- No publicar a Supabase.
- No tocar publish_queue con commit.
- No correr publish_to_supabase.py.
- No correr run_daily_pipeline.py --commit.
- No borrar datos.
- No cambiar esquema.
- No hacer commit.
- No hacer push.
- No inventar datos.
- No pisar datos buenos con datos peores.

Tarea:
1. Tomar muestras representativas de propiedades con problemas.
2. Revisar raw, staging, datos_extra, URL, titulo, descripcion, imagenes y issues.
3. Clasificar causa raiz:
   - el sitio original no trae el dato;
   - el scraper no lo extrajo;
   - el mapper no lo normalizo;
   - el validador lo descarto;
   - el geocoder lo salto correctamente;
   - el dato esta en raw/datos_extra pero no pasa a staging;
   - el dato esta en URL/titulo/descripcion y no se usa;
   - es duplicado que debe agruparse, no eliminarse.
4. Generar reporte con hallazgos, patrones y recomendaciones de pipeline.

No implementar cambios todavia salvo que lo pida explicitamente.
```

## Prompt 2: Mejorar pipeline de scraping y normalizacion

```text
Estoy trabajando en ERETZ Propiedades.

Objetivo:
Convertir problemas detectados en mejoras generales del pipeline de scraping/normalizacion/validacion, no en correcciones manuales propiedad por propiedad.

Implementar mejoras generales para:
- ubicacion desde breadcrumbs, URL, titulo, descripcion, metadatos y JSON-LD;
- precio y moneda desde HTML visible, JSON embebido y APIs;
- imagenes reales desde galleries, og:image, JSON-LD, APIs y sliders;
- descarte de placeholders, logos, iconos, mapas y SVGs;
- normalizacion de ciudad, provincia, barrio y direccion;
- deteccion de direcciones contaminadas;
- geocoding con input mas confiable;
- deduplicacion y agrupacion de publicaciones de la misma propiedad.

Reglas:
- No tocar .env.
- No publicar a Supabase.
- No correr publish_to_supabase.py.
- No correr run_daily_pipeline.py --commit.
- No tocar publish_queue con commit.
- No borrar datos.
- No cambiar esquema sin autorizacion.
- No hacer commit.
- No hacer push.
- No inventar datos.
- No pisar datos buenos con datos peores.
- No hacer fixes hardcodeados para una sola inmobiliaria salvo que quede documentado y justificado.

Validar con muestra controlada before/after y generar reporte local.
```

## Prompt 3: Frontend R6 mobile

```text
Estoy trabajando en el frontend de ERETZ Propiedades.

Objetivo:
Completar R6 mobile manteniendo la experiencia mapa-listado y la marca ERETZ Propiedades.

Contexto:
- Frontend en frontend/.
- Rama: feature/frontend-home-map-ui.
- R5 cerrado con build/lint OK.
- Ya existen loading/skeleton, lazy images, filtros client-side, ordenamiento, empty state, mapa con limite de marcadores, timeout Supabase 4500ms, navbar mejorado, layout desktop, modos de vista, cards premium, link original/contacto y fullscreen mapa.

Tareas:
- Mejorar mobile sin romper desktop.
- Revisar filtros en mobile.
- Revisar mapa/listado en pantallas chicas.
- Revisar cards y textos largos.
- Mantener mapa como protagonista.
- Usar siempre marca ERETZ Propiedades.

Reglas:
- No tocar .env.
- No tocar scraper.
- No tocar Supabase/Neon.
- No publicar datos.
- No hacer commit ni push sin autorizacion.

Validar con build/lint y, si corresponde, captura visual.
```

## Prompt 4: Primera publicacion controlada futura

```text
Estoy trabajando en ERETZ Propiedades.

Objetivo:
Preparar una primera publicacion controlada a Supabase, no masiva.

Antes de publicar:
- Auditar readiness actual.
- Elegir solo propiedades de maxima calidad.
- Excluir propiedades con ubicacion dudosa, precio dudoso, imagen placeholder, duplicado dudoso o datos criticos faltantes.
- Preparar dry-run de publish_queue.
- Revisar muestra visual en frontend.

Reglas:
- No publicar masivamente.
- No correr run_daily_pipeline.py --commit.
- No tocar .env.
- No borrar datos.
- No cambiar esquema.
- No hacer commit/push sin autorizacion.

Plan sugerido:
1. Dry-run para seleccionar 500 propiedades de maxima calidad.
2. Confirmar criterios y riesgos.
3. Solo con autorizacion explicita, hacer commit/publicacion controlada.
4. Revisar frontend y reporte.
5. Decidir si ampliar a 1.000 y luego 5.000.
```

## Prompt 5: Auditoria previa a publicacion

```text
Estoy trabajando en ERETZ Propiedades.

Objetivo:
Auditar propiedades candidatas antes de publicar a Supabase.

Revisar:
- total candidatas;
- unicas por hash_dedup;
- duplicadas por URL;
- posibles duplicadas por titulo/direccion/precio/inmobiliaria;
- con precio;
- sin precio;
- moneda valida;
- tipo y operacion validos;
- ciudad/provincia;
- lat/lon;
- imagen real;
- URL/sourceUrl;
- inmobiliaria/desarrolladora;
- quality_score y distribucion;
- issues/warnings.

Clasificar:
- publicables ahora;
- publicables con warning;
- retenidas por mala calidad;
- duplicadas;
- requieren geocoding;
- requieren completar datos.

Reglas:
- No publicar a Supabase.
- No tocar publish_queue con commit.
- No correr publish_to_supabase.py.
- No borrar datos.
- No cambiar esquema.
- No hacer commit/push.

Generar reporte y recomendacion clara: publicar controlado o seguir limpiando.
```
