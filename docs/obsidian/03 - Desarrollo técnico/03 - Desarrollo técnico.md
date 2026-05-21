# Desarrollo técnico

Esta nota documenta todo lo relacionado con el desarrollo técnico de InmoCapital.

Incluye el frontend, backend, estructura del proyecto, herramientas utilizadas, reglas de trabajo, comandos importantes y criterios para no romper el proyecto.

---

## Rol del desarrollo técnico en InmoCapital

El desarrollo técnico es la base que permite que InmoCapital funcione como plataforma.

Incluye:

- Frontend público.
- Backend.
- Scraping.
- Conexión con Supabase.
- Visualización de propiedades.
- Mapa.
- Filtros.
- Normalización de datos.
- Integración con herramientas externas.
- Control de versiones con GitHub.

---

## Objetivo técnico principal

Construir una plataforma estable, escalable y capaz de salir al público.

El objetivo no es hacer algo improvisado o solamente visual.

El sistema debe poder:

- Mostrar propiedades reales.
- Conectarse correctamente a Supabase.
- Mostrar mapa y listado.
- Filtrar datos.
- Manejar imágenes reales y placeholders.
- Evitar errores graves.
- Escalar a más ciudades, provincias e inmobiliarias.
- Mantener el código ordenado.
- Permitir mejoras futuras.

---

## Ubicación local del proyecto

D:\INMO CAPITAL\Inmo-Capital-main

---

## Stack tecnológico

### Frontend

- Next.js
- Tailwind
- App Router
- Leaflet
- Marker clustering
- Componentes propios

### Backend / scraping

- Python
- Playwright
- Scrapers propios
- Conexión con Supabase
- Procesamiento de datos
- Normalización
- Logs

### Base de datos

- Supabase
- PostgreSQL
- Tablas
- Vistas
- Consultas SQL
- Cola de scraping

### Herramientas de trabajo

- Visual Studio Code
- Git
- GitHub
- ChatGPT
- Codex / Claude Code
- Obsidian
- Google Sheets

---

## Reglas técnicas principales

- No borrar tablas sin revisar.
- No modificar Supabase de forma destructiva.
- No corregir manualmente errores que deben corregirse desde código.
- No hacer cambios grandes sin entender qué se modifica.
- No forzar Git si no es necesario.
- No mezclar muchos cambios en una sola corrección.
- Probar después de cada cambio importante.
- Documentar errores y soluciones.
- Mantener el código ordenado.
- Priorizar estabilidad antes que velocidad.

---

## Estructura general del proyecto

La estructura exacta puede cambiar, pero conceptualmente el proyecto contiene:

- frontend
- scraper
- archivos de configuración
- scripts
- conexión a Supabase
- dependencias de Node
- dependencias de Python
- documentación
- archivos de entorno

---

## Frontend

El frontend está construido con Next.js.

Debe permitir:

- Mostrar la página principal.
- Mostrar mapa.
- Mostrar propiedades.
- Mostrar cards.
- Mostrar filtros.
- Mostrar información clara.
- Tener diseño responsive.
- Funcionar bien en mobile.
- Conectarse a Supabase.
- Usar datos reales.
- Mostrar placeholders cuando no haya imágenes reales.

---

## Mapa

El mapa usa Leaflet.

Funciones esperadas:

- Mostrar propiedades geolocalizadas.
- Mostrar marcadores.
- Agrupar marcadores cuando haya muchos.
- Sincronizar mapa con listado.
- Permitir explorar por zona.
- Evitar mostrar propiedades sin coordenadas inválidas.
- Mantener buena experiencia mobile.

---

## Listado de propiedades

El listado debe mostrar información útil:

- Imagen.
- Título.
- Precio.
- Moneda.
- Ubicación.
- Tipo de propiedad.
- Operación.
- Ambientes.
- Dormitorios.
- Superficie.
- Inmobiliaria.
- Botones de contacto o publicación original.

---

## Cards de propiedades

Las cards deben ser claras y profesionales.

Deben evitar:

- Mostrar datos vacíos de forma fea.
- Mostrar imágenes rotas.
- Mostrar precios mal formateados.
- Mostrar ubicaciones incoherentes.
- Mostrar información excesiva.

Deben priorizar:

- Imagen.
- Precio.
- Ubicación.
- Tipo de propiedad.
- Operación.
- Datos principales.
- Llamado a la acción.

---

## Imágenes

Reglas para imágenes:

- Usar imágenes reales cuando existan.
- No usar logos como fotos de propiedades.
- No usar íconos como fotos reales.
- No usar placeholders externos si se pueden evitar.
- Usar placeholder propio cuando no haya imagen.
- Evitar que una imagen rota rompa la card.
- Registrar si una propiedad tiene imagen real o no.

---

## Filtros

Filtros importantes para el frontend:

- Operación.
- Tipo de propiedad.
- Ciudad.
- Provincia.
- Precio mínimo.
- Precio máximo.
- Moneda.
- Ambientes.
- Dormitorios.
- Superficie.
- Inmobiliaria.
- Propiedades con coordenadas.
- Propiedades con imágenes.

A futuro:

- ROI.
- Precio por metro cuadrado.
- Riesgo de zona.
- Cercanía a servicios.
- Oportunidades.
- Variación histórica.

---

## Backend / scraping

El backend actual está relacionado principalmente con scraping y procesamiento de datos.

Debe encargarse de:

- Recorrer inmobiliarias.
- Detectar propiedades.
- Extraer datos.
- Normalizar información.
- Validar campos.
- Guardar datos en Supabase.
- Actualizar propiedades existentes.
- Registrar errores.
- Registrar métricas.
- Evitar duplicados.

---

## Supabase

Supabase funciona como la base de datos central.

El frontend debe leer datos desde vistas preparadas para mostrar información limpia.

El scraper debe escribir y actualizar datos de forma controlada.

Regla importante:

La base no debe usarse para corregir manualmente errores que deben resolverse desde el scraper.

---

## GitHub

GitHub se usa para:

- Guardar código.
- Controlar versiones.
- Ver cambios.
- Sincronizar avances.
- Evitar perder trabajo.
- Permitir volver atrás si algo se rompe.

Reglas:

- No hacer cambios sin saber qué se tocó.
- No forzar push sin necesidad.
- No borrar archivos importantes.
- Hacer commits con mensajes claros.
- Revisar estado antes de subir cambios.

---

## Comandos importantes

### Ver ubicación actual

pwd

---

### Ver estado de Git

git status

---

### Ver rama actual

git branch

---

### Ver cambios

git diff

---

### Agregar cambios

git add .

---

### Crear commit

git commit -m "mensaje del cambio"

---

### Subir a GitHub

git push

---

## Comandos del frontend

### Entrar a la carpeta frontend

cd frontend

---

### Instalar dependencias

npm install

---

### Ejecutar en desarrollo

npm run dev

---

### Compilar proyecto

npm run build

---

### Revisar lint

npm run lint

---

## Comandos del scraper

### Ejecutar revisión de integridad

python scraper\scraper_propiedades.py --integrity-dry-run --max-items 50

---

## Revisión antes de pedir ayuda técnica

Antes de pedir ayuda a ChatGPT, Codex o Claude, conviene tener:

- Qué comando ejecuté.
- Qué error apareció.
- Captura o texto del error.
- Qué archivo estaba modificando.
- Qué esperaba que pase.
- Qué pasó realmente.
- Qué no quiero que se modifique.
- Si el cambio puede afectar Supabase.
- Si el cambio puede afectar el frontend.
- Si el cambio puede afectar el scraping.

---

## Cómo pedir ayuda técnica

Usar siempre la nota:

[[13 - Estado actual para ChatGPT o Codex]]

Después agregar:

- Problema puntual.
- Error exacto.
- Comando usado.
- Objetivo.
- Restricciones.
- Qué archivos pueden tocarse.
- Qué archivos no deberían tocarse.

---

## Checklist antes de tocar código

- [ ] Entender qué problema se quiere resolver.
- [ ] Identificar archivo relacionado.
- [ ] Revisar si afecta frontend, scraping o Supabase.
- [ ] Evitar cambios destructivos.
- [ ] Hacer cambios chicos.
- [ ] Probar después.
- [ ] Guardar resultado.
- [ ] Documentar si fue importante.

---

## Checklist después de tocar código

- [ ] Ejecutar prueba correspondiente.
- [ ] Revisar si aparece error.
- [ ] Revisar que el cambio hizo lo esperado.
- [ ] Revisar que no rompió otra parte.
- [ ] Revisar git status.
- [ ] Hacer commit si el cambio está bien.
- [ ] Documentar error y solución si corresponde.

---

## Riesgos técnicos

Riesgos principales:

- Romper conexión con Supabase.
- Romper frontend.
- Romper scraping.
- Guardar datos duplicados.
- Borrar datos sin querer.
- Subir cambios incompletos a GitHub.
- Mezclar muchas correcciones en una sola.
- No registrar decisiones.
- No entender qué cambió.
- Depender demasiado de correcciones manuales.

---

## Prioridades técnicas actuales

### Alta prioridad

- Mantener Supabase estable.
- Mejorar scraping.
- Mejorar calidad de datos.
- Evitar duplicados.
- Corregir errores desde código.
- Mejorar logs.
- Asegurar que el frontend lea datos correctos.
- Mantener GitHub actualizado.

### Media prioridad

- Mejorar diseño frontend.
- Mejorar experiencia mobile.
- Mejorar filtros.
- Mejorar cards.
- Mejorar mapa.
- Mejorar performance.

### Baja prioridad

- Automatizar despliegues.
- Crear panel administrativo.
- Crear dashboard de métricas.
- Automatizar scraping en servidor.
- Agregar alertas automáticas.
- Integrar IA avanzada.

---

## Relación con otras notas

Notas relacionadas:

- [[04 - Supabase y base de datos]]
- [[05 - Scraping]]
- [[12 - Errores y soluciones]]
- [[13 - Estado actual para ChatGPT o Codex]]
- [[11 - Pendientes]]
- [[10 - Decisiones importantes]]

---

## Notas generales

El desarrollo técnico de InmoCapital debe avanzar de forma ordenada.

Cada mejora tiene que acercar el proyecto a una plataforma estable, pública y escalable.

La prioridad no es hacer cambios rápidos, sino hacer cambios que no rompan el proyecto y que puedan mantenerse en el tiempo.