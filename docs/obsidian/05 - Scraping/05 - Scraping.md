# Scraping

Esta nota documenta todo lo relacionado con el scraping de InmoCapital.

El scraping es una de las partes centrales del proyecto porque permite recopilar propiedades desde sitios de inmobiliarias, procesarlas, normalizarlas y guardarlas en Supabase.

---

## Rol del scraping en InmoCapital

El scraping sirve para:

- Detectar inmobiliarias.
- Entrar a sitios web de inmobiliarias.
- Buscar propiedades publicadas.
- Extraer información importante.
- Normalizar datos.
- Guardar propiedades nuevas.
- Actualizar propiedades existentes.
- Registrar errores.
- Alimentar la base de datos de Supabase.
- Mantener actualizada la información del mercado inmobiliario.

---

## Objetivo principal del scraping

El objetivo no es simplemente traer muchas propiedades.

El objetivo es traer propiedades con datos útiles, ordenados y confiables.

Prioridad:

1. Calidad de datos.
2. Estabilidad del scraper.
3. Corrección automática de errores.
4. Cantidad de propiedades.
5. Velocidad.

---

## Reglas principales

- No corregir errores manualmente en Supabase si pueden corregirse desde el scraper.
- Cada error repetido debe transformarse en una mejora de código.
- No priorizar cantidad de propiedades si los datos se guardan mal.
- Registrar errores importantes en la nota “12 - Errores y soluciones”.
- Registrar decisiones técnicas importantes en “10 - Decisiones importantes”.
- Evitar que una inmobiliaria rota frene toda la corrida.
- Evitar que items queden trabados en estado running.
- Guardar logs claros.
- Separar propiedades nuevas, actualizadas, descartadas y con error.

---

## Ubicación local del proyecto

D:\INMO CAPITAL\Inmo-Capital-main

---

## Tecnología usada

- Python
- Playwright
- Supabase
- Scrapers propios
- Cola de scraping
- Logs por consola
- Tablas de corridas de scraping

---

## Archivo principal del scraper

Archivo principal mencionado:

scraper\scraper_propiedades.py

---

## Comando útil de revisión

python scraper\scraper_propiedades.py --integrity-dry-run --max-items 50

Uso:

Este comando sirve para hacer una revisión de integridad sin reclamar cola, sin scrapear y sin guardar nada.

Sirve para revisar si hay items pendientes y si están en condiciones seguras para procesarse.

---

## Estados posibles de scraping

Estados posibles o esperados:

- pending
- running
- success
- failed
- site_down
- timeout
- blocked
- requires_playwright

---

## Qué debe registrar cada corrida

Cada corrida de scraping debería registrar:

- ID de corrida.
- Tipo de corrida.
- Fecha de inicio.
- Fecha de finalización.
- Estado general.
- Cantidad de inmobiliarias pendientes.
- Cantidad de inmobiliarias procesadas.
- Cantidad de éxitos.
- Cantidad de fallos.
- Duración total.
- Errores generales.

---

## Qué debe registrar cada item de scraping

Cada inmobiliaria o item procesado debería registrar:

- ID del item.
- ID de corrida.
- ID de inmobiliaria.
- Nombre de inmobiliaria.
- Web procesada.
- Estado final.
- URL final.
- Estrategia usada.
- Propiedades detectadas.
- Propiedades nuevas.
- Propiedades actualizadas.
- Propiedades con error.
- Propiedades descartadas.
- Motivo de descarte.
- Error type.
- Error message.
- Duración en segundos.

---

## Métricas importantes

Métricas que hay que revisar después de cada corrida:

- Cantidad de inmobiliarias procesadas.
- Cantidad de inmobiliarias exitosas.
- Cantidad de inmobiliarias fallidas.
- Cantidad de propiedades detectadas.
- Cantidad de propiedades nuevas.
- Cantidad de propiedades actualizadas.
- Cantidad de propiedades con error.
- Cantidad de propiedades sin coordenadas.
- Cantidad de propiedades sin imágenes.
- Cantidad de propiedades sin precio.
- Tiempo promedio por inmobiliaria.
- Errores más frecuentes.

---

## Estrategias de scraping

Estrategias detectadas o posibles:

### Tokko

Muchos sitios inmobiliarios usan Tokko.

Problemas frecuentes:

- Carga dinámica.
- Imágenes dentro de scripts.
- Galerías con lazy loading.
- URLs internas específicas.
- Propiedades paginadas.

Objetivo:

- Extraer propiedades correctamente.
- Detectar imágenes reales.
- Evitar placeholders.
- Guardar datos estructurados.

---

### WordPress

Algunos sitios usan WordPress o plugins inmobiliarios.

Problemas frecuentes:

- Estructuras distintas según el plugin.
- URLs con categorías.
- Datos mezclados en HTML.
- Campos no estandarizados.

Objetivo:

- Detectar listados.
- Extraer detalle de cada propiedad.
- Normalizar campos.

---

### Sitemap

Algunos sitios pueden permitir scraping desde sitemap.

Uso:

- Encontrar URLs de propiedades.
- Evitar recorrer manualmente todo el sitio.
- Detectar páginas nuevas.

Objetivo:

- Usar sitemap cuando esté disponible y sea confiable.

---

### HTML estático

Algunos sitios tienen HTML simple.

Ventaja:

- Más fácil de procesar.
- Menos dependencia de Playwright.
- Más rápido.

Problema:

- Cada sitio puede tener estructura propia.

---

### Custom listing

Sitios con estructura personalizada.

Problemas frecuentes:

- Requieren reglas específicas.
- Pueden no tener etiquetas claras.
- Pueden mezclar propiedades, noticias y páginas institucionales.

Objetivo:

- Detectar patrones.
- Crear extracción flexible.
- No romper el scraper general.

---

## Datos que debe extraer cada propiedad

Campos importantes:

- URL
- ID externo
- Título
- Descripción
- Precio
- Moneda
- Precio en USD
- Expensas
- Tipo de propiedad
- Operación
- Ambientes
- Dormitorios
- Baños
- Toilettes
- Cocheras
- Antigüedad
- Piso
- Superficie total
- Superficie cubierta
- Superficie terreno
- Dirección
- Barrio
- Ciudad
- Provincia
- País
- Latitud
- Longitud
- Imágenes
- Inmobiliaria asociada

---

## Normalización necesaria

El scraper debe intentar normalizar:

- Ciudad.
- Provincia.
- Barrio.
- País.
- Precio.
- Moneda.
- Tipo de operación.
- Tipo de propiedad.
- URL.
- Imágenes.
- Dirección.
- Coordenadas.

---

## Validaciones antes de guardar

Antes de guardar una propiedad, revisar:

- Que tenga URL.
- Que esté asociada a una inmobiliaria.
- Que no sea duplicada.
- Que el precio no sea absurdo.
- Que la moneda sea válida.
- Que la operación sea venta, alquiler u otra categoría reconocida.
- Que ciudad y provincia estén lo más normalizadas posible.
- Que las imágenes no sean logos o placeholders.
- Que las coordenadas, si existen, tengan sentido.
- Que los campos principales no estén completamente vacíos.

---

## Guardado en Supabase

El scraper debe poder diferenciar:

- Propiedades nuevas.
- Propiedades ya existentes.
- Propiedades actualizadas.
- Propiedades descartadas.
- Propiedades con error.

No alcanza con detectar propiedades. Es importante saber cuántas se guardaron realmente.

---

## Problemas frecuentes

### Sitios que no cargan

Puede pasar por:

- Sitio caído.
- Hosting lento.
- Error SSL.
- Bloqueo.
- Redirección rota.
- Error 403.
- Error 404.
- Error 500.

Acción esperada:

- Registrar error.
- Marcar estado correspondiente.
- Continuar con la siguiente inmobiliaria.

---

### Sitios que requieren Playwright

Puede pasar cuando:

- El contenido carga con JavaScript.
- Las propiedades no están en el HTML inicial.
- Las imágenes aparecen después.
- Hay paginación dinámica.

Acción esperada:

- Detectar necesidad de Playwright.
- Procesar con navegador si corresponde.
- No marcar como error si solo requiere otra estrategia.

---

### Propiedades detectadas pero no guardadas

Problema muy importante.

Debe registrarse:

- Cuántas propiedades se detectaron.
- Cuántas se intentaron guardar.
- Cuántas se guardaron.
- Cuántas se actualizaron.
- Cuántas fallaron.
- Por qué fallaron.

---

### Propiedades sin imágenes

Puede pasar por:

- Lazy loading.
- Imágenes en scripts.
- URLs protegidas.
- Logos detectados como imágenes.
- Placeholders.
- Galerías no recorridas.

Acción esperada:

- Mejorar extracción.
- Descartar imágenes falsas.
- Guardar placeholder propio solo si no hay imagen real.

---

### Propiedades sin coordenadas

Puede pasar por:

- Dirección incompleta.
- Falta de ciudad.
- Falta de provincia.
- Geocoding pendiente.
- Dirección genérica.

Acción esperada:

- Guardar propiedad igual si el resto de datos sirve.
- Mandar a cola de geocoding.
- No inventar coordenadas.
- Validar coordenadas antes de guardar.

---

### Duplicados

Puede pasar por:

- Misma URL con parámetros distintos.
- HTTP y HTTPS.
- Barra final.
- Propiedad repetida en distintas secciones.
- Misma propiedad en varias páginas.
- Hash de deduplicación incompleto.

Acción esperada:

- Normalizar URL.
- Usar hash_dedup.
- Usar upsert.
- Actualizar en vez de duplicar.

---

## Logs ideales del scraper

Cada inmobiliaria debería mostrar algo similar a:

Inmobiliaria: Nombre
Web: URL
Estrategia: Tokko / WordPress / Sitemap / HTML / Custom
Estado: success / failed / site_down
Propiedades detectadas: X
Propiedades nuevas: X
Propiedades actualizadas: X
Propiedades descartadas: X
Errores: X
Duración: X segundos

---

## Checklist antes de correr scraping

- [ ] Confirmar que estoy en la carpeta correcta del proyecto.
- [ ] Confirmar que el entorno virtual está activo.
- [ ] Confirmar que Supabase está conectado.
- [ ] Revisar si hay items trabados en running.
- [ ] Revisar qué corrida se va a ejecutar.
- [ ] Confirmar que no se van a borrar datos.
- [ ] Confirmar que el comando no es destructivo.
- [ ] Tener claro qué se quiere probar.

---

## Checklist después de correr scraping

- [ ] Revisar cantidad de inmobiliarias procesadas.
- [ ] Revisar cantidad de éxitos.
- [ ] Revisar cantidad de fallos.
- [ ] Revisar propiedades detectadas.
- [ ] Revisar propiedades nuevas.
- [ ] Revisar propiedades actualizadas.
- [ ] Revisar errores.
- [ ] Revisar si quedaron items en running.
- [ ] Revisar propiedades sin coordenadas.
- [ ] Revisar propiedades sin imágenes.
- [ ] Registrar errores importantes en Obsidian.
- [ ] Pedir corrección desde código si el error se repite.

---

## Prioridades actuales del scraping

### Alta prioridad

- Evitar items trabados en running.
- Mejorar guardado de propiedades.
- Detectar propiedades guardadas vs detectadas.
- Mejorar logs.
- Corregir errores desde código.
- Mejorar imágenes reales.
- Mejorar coordenadas.
- Mejorar normalización de ciudades y provincias.
- Evitar duplicados.

### Media prioridad

- Mejorar estrategias por tipo de sitio.
- Mejorar clasificación de operación.
- Mejorar clasificación de tipo de propiedad.
- Mejorar parsing de precios.
- Mejorar manejo de sitios lentos.

### Baja prioridad

- Optimizar velocidad.
- Ejecutar scraping en servidores.
- Automatizar corridas programadas.
- Crear dashboard de scraping.
- Alertas automáticas de errores.

---

## Relación con otras notas

Notas relacionadas:

- [[04 - Supabase y base de datos]]
- [[12 - Errores y soluciones]]
- [[10 - Decisiones importantes]]
- [[11 - Pendientes]]
- [[13 - Estado actual para ChatGPT o Codex]]

---

## Notas generales

El scraping es el motor de datos de InmoCapital.

Si el scraping funciona mal, la plataforma pierde valor.

Por eso, cada error importante debe corregirse desde el código y quedar documentado.

El objetivo es construir un sistema cada vez más automático, estable y confiable.