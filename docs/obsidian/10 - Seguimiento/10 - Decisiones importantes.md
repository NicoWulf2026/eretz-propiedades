# Decisiones importantes

Esta nota sirve para registrar las decisiones estratégicas, técnicas y comerciales más importantes de InmoCapital.

Cada vez que se tome una decisión relevante, debe quedar registrada con:

- Fecha.
- Decisión tomada.
- Motivo.
- Impacto.
- Qué no se debe olvidar.

---

## Decisión 1: No hacer un MVP básico

### Fecha
Mayo 2026

### Decisión
InmoCapital no se desarrollará como un MVP básico o incompleto. La intención es construir una plataforma que pueda salir al público con una experiencia profesional, datos confiables y una estructura escalable.

### Motivo
El proyecto tiene una visión más ambiciosa que simplemente probar una idea. Busca convertirse en una herramienta real para usuarios, inmobiliarias e inversores.

### Impacto
Las decisiones técnicas y de producto deben priorizar estabilidad, calidad de datos, diseño profesional, experiencia de usuario y escalabilidad.

---

## Decisión 2: Corregir errores desde el scraper

### Fecha
Mayo 2026

### Decisión
Los errores detectados en los datos deben corregirse desde el código del scraper siempre que sea posible, no manualmente en Supabase.

### Motivo
Si los errores se corrigen manualmente, pueden volver a aparecer en futuros scrapeos. La solución tiene que estar automatizada.

### Impacto
Cada error repetido debe analizarse y transformarse en una mejora del scraper, normalización o validación de datos.

---

## Decisión 3: Priorizar calidad de datos antes que cantidad

### Fecha
Mayo 2026

### Decisión
La cantidad de propiedades cargadas no debe ser más importante que la calidad de la información guardada.

### Motivo
Una plataforma basada en datos necesita información confiable para ser útil. Si hay muchos datos pero están mal normalizados, duplicados o incompletos, la plataforma pierde valor.

### Impacto
Se deben revisar campos como:

- Ciudad.
- Provincia.
- Barrio.
- Precio.
- Moneda.
- Tipo de operación.
- Imágenes.
- Coordenadas.
- Duplicados.

---

## Decisión 4: Obsidian será el centro de control del proyecto

### Fecha
Mayo 2026

### Decisión
Obsidian se usará como centro de conocimiento y documentación de InmoCapital.

### Motivo
El proyecto tiene muchas áreas: desarrollo, scraping, base de datos, producto, marketing, legal, finanzas y estrategia. Si toda la información queda dispersa entre chats, capturas y archivos sueltos, se vuelve difícil continuar.

### Impacto
En Obsidian se debe guardar:

- Estado actual del proyecto.
- Decisiones importantes.
- Prompts útiles.
- Errores y soluciones.
- Documentación de Supabase.
- Documentación del scraping.
- Roadmap.
- Pendientes.
- Ideas estratégicas.
- Información legal y comercial.

---

## Decisión 5: Separar cada herramienta por función

### Fecha
Mayo 2026

### Decisión
Cada herramienta tendrá una función específica dentro del proyecto.

### Distribución

- Obsidian: conocimiento, decisiones y documentación.
- GitHub: código y control de versiones.
- Supabase: base de datos real.
- Google Sheets: números, listas y seguimiento simple.
- ChatGPT / Codex / Claude: ayuda técnica, prompts, desarrollo y resolución de problemas.

### Motivo
Evitar mezclar todo en un mismo lugar y reducir el desorden.

### Impacto
No se debe usar Obsidian como base de datos real ni como reemplazo de GitHub. Obsidian es para documentar y pensar el proyecto.

---

## Decisión 6: Arquitectura dual Supabase + Neon

### Fecha
29/05/2026

### Decisión
Usar **Neon** como base interna/operativa (scraping crudo, staging, geocoding, cola de publicación) y **Supabase** como base pública/canónica que alimenta el frontend. El flujo es:
Scraper → Neon `propiedades_raw` → staging → geocoding → `publish_queue` → Supabase `propiedades` → Frontend.

### Motivo
Separar el trabajo pesado y crudo (que satura) de la base pública liviana. Supabase no debe recibir cargas masivas sin control.

### Impacto
- `USE_INTERNAL_DB=true` activa Neon; `USE_INTERNAL_DB=false` mantiene el modo seguro (solo Supabase) sin romper nada.
- Las escrituras a Supabase pasan por la cola controlada `publish_to_supabase.py`, en lotes chicos.

---

## Decisión 7: Diagnosticar y corregir el scraping por familias de error

### Fecha
29/05/2026

### Decisión
Antes de corregir, **agrupar los errores por familias** y atacar las **causas generales**, no inmobiliarias una por una. Los casos específicos de una sola inmobiliaria se corrigen aparte, solo si vale la pena.

### Motivo
Corregir agencia por agencia no escala. Una sola causa general suele explicar decenas de fallos.

### Impacto
- No correr todas las inmobiliarias de golpe ni hacer scraping masivo.
- Probar siempre en dry-run y lotes chicos.
- Casos antibot / site_down se tratan como no-código o específicos.

---

## Decisión 8: Playwright como opción controlada, no por defecto

### Fecha
29/05/2026

### Decisión
Playwright se habilita con el flag `--allow-playwright` en el orquestador, **no por defecto**. La familia `requires_playwright` es la dominante (~37% de los errores de run53), pero activarlo siempre encarece y enlentece las corridas.

### Motivo
Equilibrar impacto (destrabar sitios JS) con costo (Playwright es pesado y necesita navegadores instalados).

### Impacto
- Si no se pasa el flag, el comportamiento del scraper no cambia.
- El pipeline diario debe seguir siendo conservador.
- Antes de habilitarlo en corridas reales, hacer retest controlado con `--test-url --allow-playwright`.