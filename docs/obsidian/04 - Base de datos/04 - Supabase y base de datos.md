# Supabase y base de datos

Esta nota documenta la estructura general de Supabase dentro de InmoCapital.

La base de datos es una de las partes más importantes del proyecto porque guarda la información de inmobiliarias, propiedades, scraping, historial de precios, eventos y calidad de datos.

---

## Rol de Supabase en InmoCapital

Supabase funciona como la base de datos principal del proyecto.

En Supabase se guarda:

- Información de inmobiliarias.
- Información de propiedades.
- Datos extraídos por scraping.
- Historial de precios.
- Estados de corridas de scraping.
- Eventos de propiedades.
- Resultados de geocoding.
- Vistas para calidad de datos.
- Vistas para frontend.

---

## Reglas principales

- No borrar tablas sin revisar.
- No modificar datos de forma destructiva.
- No corregir manualmente errores que deberían corregirse desde el scraper.
- Antes de cambiar una tabla, entender qué la usa.
- Antes de borrar campos, revisar si el frontend o scraper dependen de ellos.
- Usar consultas de revisión antes de aplicar cambios.
- Priorizar calidad de datos antes que cantidad.
- Registrar cambios importantes en Obsidian.

---

## Tablas principales

### propiedades

Tabla principal donde se guardan las propiedades scrapeadas.

Campos importantes:

- id
- inmobiliaria_id
- url
- id_externo
- hash_dedup
- titulo
- descripcion
- precio
- moneda
- precio_usd
- expensas
- expensas_moneda
- tipo_propiedad
- operacion
- ambientes
- dormitorios
- banos
- toilettes
- cocheras
- antiguedad
- piso
- superficie_total
- superficie_cubierta
- superficie_terreno
- direccion
- barrio
- ciudad
- provincia
- pais
- latitud
- longitud
- created_at
- updated_at

---

### inmobiliarias_main

Tabla principal de inmobiliarias.

Puede contener información general y consolidada de cada inmobiliaria.

Campos importantes:

- id
- nombre
- direccion
- telefono
- email
- web
- ciudad
- provincia
- pais
- logo
- created_at
- updated_at

---

### inmobiliarias_scraping

Tabla relacionada con las inmobiliarias a scrapear.

Campos importantes:

- id
- nombre
- direccion
- telefono_principal
- email_principal
- web
- rating
- resenas
- categoria
- ciudad
- fuente
- estado_scraping
- ultimo_scrapeo
- created_at
- barrio
- provincia
- pais
- telefono
- logo
- link_zonaprop
- nombre_normalizado
- updated_at

---

### inmobiliarias_staging

Tabla de carga o revisión previa de inmobiliarias.

Sirve para ordenar datos antes de consolidarlos.

Uso posible:

- Importar inmobiliarias nuevas.
- Revisar duplicados.
- Normalizar nombres.
- Revisar webs.
- Preparar datos antes de pasarlos a tablas principales.

---

### historial_precios

Tabla para guardar cambios de precio de las propiedades.

Uso esperado:

- Registrar precio anterior.
- Registrar precio nuevo.
- Detectar variaciones.
- Analizar aumentos o bajas.
- Comparar evolución histórica.

Campos posibles:

- id
- propiedad_id
- precio_anterior
- precio_nuevo
- moneda
- fecha
- created_at

---

### scraping_runs

Tabla para registrar corridas generales de scraping.

Uso esperado:

- Identificar cada corrida.
- Registrar tipo de corrida.
- Registrar fecha de inicio.
- Registrar fecha de finalización.
- Registrar estado general.
- Registrar cantidad de inmobiliarias procesadas.

Campos posibles:

- id
- run_type
- status
- started_at
- finished_at
- total_items
- success_count
- failed_count
- pending_count
- created_at

---

### scraping_run_items

Tabla para registrar cada inmobiliaria o item dentro de una corrida de scraping.

Uso esperado:

- Saber qué inmobiliaria se procesó.
- Saber si terminó bien o falló.
- Guardar errores.
- Guardar cantidad de propiedades detectadas, nuevas y actualizadas.
- Evitar que queden items trabados en running.

Campos posibles:

- id
- scraping_run_id
- inmobiliaria_id
- inmobiliaria_nombre
- web
- status
- propiedades_detectadas
- propiedades_nuevas
- propiedades_actualizadas
- propiedades_error
- error_type
- error_message
- final_url
- duration_seconds
- created_at
- updated_at

---

### property_events

Tabla para registrar eventos sobre propiedades.

Uso esperado:

- Clicks.
- Aperturas de WhatsApp.
- Aperturas de mail.
- Clicks en publicación original.
- Favoritos.
- Interacciones del usuario.

Sirve para medir leads e interés real.

---

### property_scores

Tabla para guardar puntajes o métricas calculadas de propiedades.

Uso posible:

- Score de oportunidad.
- Score de ubicación.
- Score de precio.
- Score de riesgo.
- Score de calidad del dato.

---

### geocoding_results

Tabla para guardar resultados de geocodificación.

Uso esperado:

- Guardar direcciones procesadas.
- Guardar coordenadas obtenidas.
- Evitar repetir geocoding innecesariamente.
- Registrar errores de geocoding.
- Detectar coordenadas inválidas.

---

## Vistas importantes

### v_propiedades_frontend_mapa

Vista usada por el frontend para mostrar propiedades en el mapa.

Uso:

- Alimentar el mapa.
- Mostrar propiedades activas.
- Filtrar propiedades visibles.
- Evitar exponer campos innecesarios.

---

### v_next_scraping_batch

Vista para determinar próximas inmobiliarias a scrapear.

Uso:

- Armar lotes de scraping.
- Priorizar inmobiliarias pendientes.
- Evitar repetir inmobiliarias recientes.
- Organizar cola de trabajo.

---

### v_geocoding_priority

Vista para priorizar propiedades que necesitan coordenadas.

Uso:

- Detectar propiedades sin latitud y longitud.
- Priorizar geocoding.
- Ordenar por importancia.

---

### v_geocoding_priority_clean

Versión más limpia o filtrada de propiedades para geocoding.

Uso:

- Evitar direcciones inválidas.
- Mejorar calidad del geocoding.
- Reducir errores.

---

### v_data_quality_summary

Vista de resumen de calidad de datos.

Uso:

- Revisar propiedades con problemas.
- Ver cuántas tienen coordenadas.
- Ver cuántas tienen imágenes.
- Ver cuántas tienen precio.
- Detectar campos vacíos importantes.

---

### v_inmocapital_radar

Vista para análisis general del proyecto.

Uso posible:

- Detectar oportunidades.
- Analizar cobertura.
- Revisar calidad de datos.
- Priorizar mejoras.

---

### v_agency_scraping_priority

Vista para priorizar inmobiliarias a scrapear.

Uso:

- Ordenar inmobiliarias según necesidad.
- Revisar pendientes.
- Organizar corridas.

---

### v_agency_scraping_priority_v2

Versión mejorada de priorización de scraping.

---

### v_agency_scraping_priority_v3

Versión más actualizada de priorización de scraping.

---

### v_city_launch_readiness

Vista para revisar qué tan lista está una ciudad para lanzamiento.

Uso posible:

- Medir cantidad de propiedades.
- Medir cantidad de inmobiliarias.
- Medir cobertura de datos.
- Medir calidad de datos por ciudad.

---

### v_location_inconsistencies

Vista para detectar inconsistencias de ubicación.

Uso:

- Ciudades mal cargadas.
- Provincias faltantes.
- Barrios mal ubicados.
- Coordenadas fuera de rango.

---

### v_location_inconsistencies_v2

Versión mejorada de inconsistencias de ubicación.

---

### v_city_normalization_review

Vista para revisar normalización de ciudades.

Uso:

- Detectar ciudades duplicadas.
- Detectar variantes de nombres.
- Revisar errores de escritura.
- Normalizar automáticamente.

---

### v_city_normalized_summary

Vista de resumen de ciudades normalizadas.

Uso:

- Ver ciudades limpias.
- Comparar cantidad de propiedades por ciudad.
- Medir cobertura territorial.

---

## Problemas frecuentes a revisar

### Propiedades sin coordenadas

Revisar:

- latitud vacía
- longitud vacía
- dirección incompleta
- ciudad mal cargada
- provincia faltante
- coordenadas fuera de rango

---

### Propiedades sin imágenes

Revisar:

- propiedades sin imagen
- propiedades con placeholder
- logos detectados como imagen
- URLs inválidas
- galerías no extraídas

---

### Propiedades sin precio

Revisar:

- precio vacío
- precio como “Consultar”
- moneda vacía
- moneda incorrecta
- expensas confundidas con precio

---

### Duplicados

Revisar:

- URL repetida
- hash_dedup repetido
- título muy similar
- misma dirección
- misma inmobiliaria
- diferencias mínimas de URL

---

### Ubicación mal normalizada

Revisar:

- barrio cargado como ciudad
- ciudad cargada como provincia
- provincia vacía
- país vacío
- zonas comerciales en vez de localidad real

---

## Consultas útiles

### Ver cantidad total de propiedades

select count(*) as total_propiedades
from propiedades;

---

### Ver propiedades sin coordenadas

select count(*) as sin_coordenadas
from propiedades
where latitud is null
   or longitud is null;

---

### Ver propiedades con coordenadas

select count(*) as con_coordenadas
from propiedades
where latitud is not null
  and longitud is not null;

---

### Ver propiedades sin precio

select count(*) as sin_precio
from propiedades
where precio is null;

---

### Ver propiedades por ciudad

select ciudad, provincia, count(*) as cantidad
from propiedades
group by ciudad, provincia
order by cantidad desc;

---

### Ver propiedades por operación

select operacion, count(*) as cantidad
from propiedades
group by operacion
order by cantidad desc;

---

### Ver propiedades por tipo

select tipo_propiedad, count(*) as cantidad
from propiedades
group by tipo_propiedad
order by cantidad desc;

---

### Ver propiedades recientes

select id, titulo, ciudad, provincia, precio, moneda, created_at
from propiedades
order by created_at desc
limit 50;

---

### Ver últimas corridas de scraping

select *
from scraping_runs
order by created_at desc
limit 20;

---

### Ver últimos items de scraping

select *
from scraping_run_items
order by created_at desc
limit 50;

---

### Ver items trabados en running

select *
from scraping_run_items
where status = 'running'
order by updated_at asc;

---

### Ver errores de scraping más frecuentes

select error_type, count(*) as cantidad
from scraping_run_items
where error_type is not null
group by error_type
order by cantidad desc;

---

## Checklist antes de tocar Supabase

Antes de hacer cambios importantes:

- [ ] Entender qué tabla se va a tocar.
- [ ] Revisar si el frontend usa esa tabla o vista.
- [ ] Revisar si el scraper usa esa tabla.
- [ ] Hacer primero una consulta SELECT.
- [ ] Evitar DELETE, DROP o TRUNCATE sin confirmación.
- [ ] Evitar UPDATE masivo sin WHERE.
- [ ] Guardar la consulta usada.
- [ ] Registrar la decisión en Obsidian.
- [ ] Probar en pequeño antes de aplicar en grande.

---

## Checklist de calidad de datos

Revisar periódicamente:

- [ ] Cantidad total de propiedades.
- [ ] Propiedades con coordenadas.
- [ ] Propiedades sin coordenadas.
- [ ] Propiedades con imágenes reales.
- [ ] Propiedades sin imágenes.
- [ ] Propiedades con precio.
- [ ] Propiedades sin precio.
- [ ] Propiedades por ciudad.
- [ ] Propiedades por provincia.
- [ ] Propiedades duplicadas.
- [ ] Inmobiliarias pendientes de scraping.
- [ ] Inmobiliarias con errores.
- [ ] Últimas corridas de scraping.
- [ ] Items trabados en running.

---

## Notas generales

Supabase debe mantenerse ordenado porque es el centro de los datos reales del proyecto.

La base de datos no debe ser corregida manualmente cada vez que aparece un error. Si el error viene del scraping, la corrección debe hacerse en el scraper.

Esta nota debe actualizarse cada vez que se creen tablas, vistas, campos importantes o consultas útiles.