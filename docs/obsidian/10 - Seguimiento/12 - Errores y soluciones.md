
# Errores y soluciones

Esta nota sirve para registrar todos los errores importantes que aparezcan en InmoCapital y cómo se fueron resolviendo.

La idea es que cada error técnico, especialmente del scraping, quede documentado para no repetir el mismo problema muchas veces.

---

## Regla principal

Los errores no deben corregirse manualmente en Supabase si pueden corregirse desde el código.

Si un error aparece durante el scraping, la solución ideal es modificar el scraper, la normalización o la validación para que el problema no vuelva a repetirse.

---

## Objetivo de esta nota

Esta nota debe ayudar a responder rápidamente:

- Qué error apareció.
- En qué parte del proyecto apareció.
- Qué lo pudo causar.
- Qué solución se aplicó.
- Qué archivo o proceso se modificó.
- Qué resultado dio.
- Si el error quedó solucionado o sigue pendiente.

---

## Formato para registrar errores

Cada vez que aparezca un error importante, usar este formato:

```text
## Error X: Nombre corto del error

### Fecha
Día/mes/año

### Área
Scraping / Supabase / Frontend / GitHub / Datos / Otro

### Qué pasó
Descripción simple del error.

### Dónde apareció
Comando, archivo, tabla, pantalla o proceso donde ocurrió.

### Causa probable
Explicación de por qué pudo haber pasado.

### Solución aplicada
Qué se modificó o qué se pidió modificar.

### Resultado
Qué pasó después de aplicar la solución.

### Estado
Pendiente / En revisión / Solucionado
---

# Errores registrados

---

## Error 1: Items de scraping trabados en running

### Fecha

Mayo 2026

### Área

Scraping / Supabase

### Qué pasó

Algunos items de scraping pueden quedar trabados en estado `running` si el proceso falla, se corta, se interrumpe o no cierra correctamente.

### Dónde apareció

Cola de scraping en Supabase, especialmente en tablas relacionadas con corridas e ítems de scraping.

### Causa probable

El scraper inicia un proceso, pero ante errores, timeouts, caídas del sitio o interrupciones, no siempre actualiza correctamente el estado final del item.

### Solución esperada

La solución debería resolverse desde el código del scraper e incluir:

- Manejo de timeouts por inmobiliaria.
- Manejo de errores por item.
- Cierre correcto de cada proceso.
- Cambio automático de estado a `success`, `failed`, `site_down` o el estado correspondiente.
- Evitar que queden procesos abiertos indefinidamente.
- Logs claros que indiquen cuándo empieza y termina cada item.
- Protección para recuperar o liberar items que quedaron trabados.

### Resultado

Pendiente de confirmar.

### Estado

En revisión

---

## Error 2: Inmobiliarias scrapeadas pero sin propiedades guardadas

### Fecha

Mayo 2026

### Área

Scraping / Guardado de datos

### Qué pasó

Hay inmobiliarias donde el scraper detecta información o intenta procesar el sitio, pero las propiedades no se guardan correctamente en Supabase.

### Dónde apareció

Proceso de scraping de inmobiliarias.

### Causa probable

Puede deberse a:

- Diferencias en la estructura del sitio.
- Campos faltantes.
- Errores al extraer precio, ubicación o URL.
- Errores en el guardado.
- Falta de logs claros.
- Problemas con constraints o duplicados.
- Errores de normalización.
- Sitios que cargan propiedades con JavaScript.
- Páginas que requieren Playwright.
- Publicaciones descartadas sin registrar motivo.

### Solución esperada

La solución debería resolverse desde el scraper.

El scraper debería mostrar claramente:

- Propiedades detectadas.
- Propiedades guardadas.
- Propiedades actualizadas.
- Propiedades descartadas.
- Motivo de descarte.
- Errores de extracción.
- Errores de guardado.
- URL final procesada.
- Tiempo de ejecución por inmobiliaria.

### Resultado

Pendiente.

### Estado

En revisión

---

## Error 3: Propiedades sin coordenadas

### Fecha

Mayo 2026

### Área

Datos / Geocoding / Supabase

### Qué pasó

Muchas propiedades pueden guardarse sin latitud y longitud.

### Dónde apareció

Tabla `propiedades` en Supabase.

### Causa probable

Puede deberse a:

- Dirección incompleta.
- Ciudad o provincia mal normalizada.
- Falta de geocoding.
- Errores en la extracción de ubicación.
- Datos de origen incompletos.
- Direcciones genéricas o poco precisas.
- Propiedades publicadas sin dirección exacta.
- Barrios cargados como ciudad.
- Provincias omitidas.
- Coordenadas fuera de rango descartadas.

### Solución esperada

La solución debería incluir:

- Mejor normalización de dirección, barrio, ciudad y provincia.
- Cola de geocoding.
- Priorización de propiedades sin coordenadas.
- Validación de coordenadas fuera de rango.
- Evitar guardar coordenadas incorrectas.
- Usar información parcial cuando no haya dirección completa.
- Registrar motivo por el cual no se pudo geocodificar.
- Revisar vistas de prioridad de geocoding.

### Resultado

Pendiente.

### Estado

En revisión

---

## Error 4: Propiedades sin imágenes reales

### Fecha

Mayo 2026

### Área

Scraping / Imágenes / Frontend

### Qué pasó

Algunas propiedades se guardan sin imágenes reales o con imágenes placeholder.

### Dónde apareció

Scraping de propiedades y visualización en frontend.

### Causa probable

Puede deberse a:

- Sitios que cargan imágenes de forma dinámica.
- Imágenes dentro de scripts.
- Lazy loading.
- URLs protegidas.
- Imágenes placeholder.
- Íconos o logos detectados como si fueran fotos reales.
- Galerías que no se recorren correctamente.
- Sitios con estructura distinta.
- Imágenes servidas desde CDN con parámetros especiales.
- Falta de validación del tipo de imagen.

### Solución esperada

La solución debería resolverse desde el scraper e incluir:

- Detectar imágenes reales.
- Descartar logos, íconos y placeholders.
- Mejorar scraping de galerías.
- Revisar estrategias específicas para sitios Tokko, WordPress y custom.
- Usar Playwright cuando las imágenes carguen con JavaScript.
- Guardar múltiples imágenes cuando estén disponibles.
- Usar placeholders propios solo cuando no haya imagen real.
- Registrar cuántas propiedades fueron guardadas con imagen real.

### Resultado

Pendiente.

### Estado

En revisión

---

## Error 5: Duplicados o conflictos al guardar datos

### Fecha

Mayo 2026

### Área

Supabase / Scraping / Base de datos

### Qué pasó

Pueden aparecer errores de duplicados o conflictos al insertar inmobiliarias o propiedades.

### Dónde apareció

Tablas de Supabase, especialmente inmobiliarias y propiedades.

### Causa probable

Puede deberse a:

- Constraints únicos.
- URLs repetidas.
- Nombres normalizados duplicados.
- Webs repetidas.
- Falta de upsert correcto.
- Hash de deduplicación incompleto.
- Diferencias mínimas en URLs.
- Propiedades repetidas en distintas páginas.
- Inmobiliarias cargadas desde más de una fuente.
- Falta de limpieza previa de datos.

### Solución esperada

La solución debería incluir:

- Uso correcto de `upsert`.
- Definir claves únicas claras.
- Mejorar normalización de nombres.
- Mejorar hash de deduplicación.
- Evitar insertar dos veces la misma inmobiliaria o propiedad.
- Normalizar URLs antes de guardar.
- Separar correctamente propiedades nuevas y actualizadas.
- Registrar conflictos sin cortar toda la corrida.

### Resultado

Pendiente.

### Estado

En revisión

---

## Error 6: Ciudades, provincias o barrios mal normalizados

### Fecha

Mayo 2026

### Área

Datos / Normalización

### Qué pasó

Algunas propiedades pueden quedar con ciudades, provincias o barrios mal escritos, incompletos o inconsistentes.

### Dónde apareció

Tabla `propiedades` y vistas de calidad de datos en Supabase.

### Causa probable

Puede deberse a:

- Datos de origen desordenados.
- Sitios que usan zonas en vez de ciudades.
- Provincias omitidas.
- Barrios cargados como ciudad.
- Diferentes formas de escribir el mismo lugar.
- Falta de reglas de normalización.
- Abreviaturas.
- Errores de tipeo en sitios originales.
- Mezcla de localidad, barrio y zona comercial.

### Solución esperada

La solución debería incluir:

- Reglas automáticas de normalización.
- Diccionario de ciudades y provincias.
- Validaciones antes de guardar.
- Revisión de inconsistencias por vistas en Supabase.
- Corrección desde código, no manualmente.
- Separar barrio, ciudad, provincia y país.
- Detectar zonas ambiguas.
- Registrar valores originales y valores normalizados.

### Resultado

Pendiente.

### Estado

En revisión

---

## Error 7: Propiedades sin precio o con moneda incorrecta

### Fecha

Mayo 2026

### Área

Scraping / Datos / Supabase

### Qué pasó

Algunas propiedades pueden guardarse sin precio, con precio incorrecto o con moneda mal detectada.

### Dónde apareció

Tabla `propiedades`.

### Causa probable

Puede deberse a:

- Precio no publicado.
- Precio escrito como “Consultar”.
- Moneda mezclada en el mismo texto.
- Símbolos mal interpretados.
- Precio en pesos detectado como dólares.
- Precio en dólares detectado como pesos.
- Formatos distintos según el sitio.
- Expensas confundidas con precio principal.
- Precio anterior o tachado tomado como precio actual.

### Solución esperada

La solución debería incluir:

- Parser de precios más robusto.
- Detección clara de moneda.
- Separación entre precio principal y expensas.
- Manejo de casos “Consultar”.
- Validaciones de rangos razonables.
- Registro del texto original del precio.
- Conversión a `precio_usd` cuando corresponda.
- Evitar guardar precios evidentemente absurdos.

### Resultado

Pendiente.

### Estado

En revisión

---

## Error 8: Operación mal detectada

### Fecha

Mayo 2026

### Área

Scraping / Datos

### Qué pasó

Algunas propiedades pueden quedar con operación incorrecta, por ejemplo venta en lugar de alquiler o alquiler en lugar de venta.

### Dónde apareció

Tabla `propiedades`, campo `operacion`.

### Causa probable

Puede deberse a:

- Sitios que mezclan venta y alquiler en la misma página.
- URLs sin categoría clara.
- Títulos ambiguos.
- Filtros internos del sitio.
- Operación indicada en breadcrumbs.
- Operación indicada solo en etiquetas visuales.
- Falta de regla de prioridad para detectar operación.

### Solución esperada

La solución debería incluir:

- Detectar operación desde URL.
- Detectar operación desde título.
- Detectar operación desde breadcrumbs.
- Detectar operación desde etiquetas del sitio.
- Definir regla de prioridad.
- Evitar separar venta y alquiler manualmente si eso rompe el scraping.
- Clasificar automáticamente después de extraer.

### Resultado

Pendiente.

### Estado

En revisión

---

## Error 9: Tipo de propiedad mal detectado

### Fecha

Mayo 2026

### Área

Scraping / Datos

### Qué pasó

Algunas propiedades pueden quedar con tipo incorrecto o incompleto, por ejemplo departamento, casa, terreno, local, cochera, oficina, etc.

### Dónde apareció

Tabla `propiedades`, campo `tipo_propiedad`.

### Causa probable

Puede deberse a:

- Títulos poco claros.
- Categorías distintas según el sitio.
- Sitios que usan nombres comerciales.
- Tipo indicado solo en URL.
- Tipo indicado en breadcrumbs.
- Publicaciones mixtas.
- Falta de diccionario de normalización.

### Solución esperada

La solución debería incluir:

- Diccionario de tipos de propiedad.
- Normalización automática.
- Detección desde título, URL, categoría y breadcrumbs.
- Mantener valor original cuando sea útil.
- Evitar forzar un tipo si no hay suficiente evidencia.
- Registrar casos ambiguos.

### Resultado

Pendiente.

### Estado

En revisión

---

## Error 10: URLs mal normalizadas o repetidas

### Fecha

Mayo 2026

### Área

Scraping / Base de datos

### Qué pasó

Algunas URLs pueden guardarse repetidas o con diferencias mínimas, generando duplicados o errores de actualización.

### Dónde apareció

Tabla `propiedades` y tablas de inmobiliarias.

### Causa probable

Puede deberse a:

- Parámetros UTM.
- Barras finales.
- HTTP vs HTTPS.
- Mayúsculas y minúsculas.
- Redirecciones.
- URLs relativas.
- URLs canónicas no detectadas.
- Diferentes URLs apuntando a la misma propiedad.

### Solución esperada

La solución debería incluir:

- Normalizar URLs antes de guardar.
- Eliminar parámetros innecesarios.
- Resolver URLs relativas.
- Guardar URL final.
- Detectar URL canónica cuando exista.
- Usar URL normalizada en deduplicación.
- Evitar duplicados por variaciones mínimas.

### Resultado

Pendiente.

### Estado

En revisión

---

## Error 11: Sitios caídos, lentos o inaccesibles

### Fecha

Mayo 2026

### Área

Scraping / Infraestructura

### Qué pasó

Algunas páginas de inmobiliarias pueden estar caídas, lentas, bloqueadas o no responder correctamente.

### Dónde apareció

Corridas de scraping.

### Causa probable

Puede deberse a:

- Sitio fuera de línea.
- Hosting lento.
- Bloqueo de bots.
- Errores 403, 404 o 500.
- Certificados SSL vencidos.
- Redirecciones rotas.
- Tiempo de respuesta excesivo.
- Sitios que requieren navegador real.

### Solución esperada

La solución debería incluir:

- Timeouts razonables.
- Reintentos limitados.
- Clasificación de estado `site_down`, `blocked`, `timeout` o similar.
- No trabar toda la corrida por una inmobiliaria.
- Registrar error y continuar con la siguiente.
- Usar Playwright cuando sea necesario.
- Evitar reintentos infinitos.

### Resultado

Pendiente.

### Estado

En revisión

---

## Error 12: Logs insuficientes para entender qué pasó

### Fecha

Mayo 2026

### Área

Scraping / Debugging

### Qué pasó

En algunos casos no queda claro por qué una inmobiliaria falló, cuántas propiedades detectó, cuántas guardó o qué error ocurrió.

### Dónde apareció

Consola, logs del scraper y tablas de scraping.

### Causa probable

Puede deberse a:

- Logs demasiado generales.
- Falta de detalle por inmobiliaria.
- Falta de conteos.
- Errores capturados sin mensaje claro.
- Falta de distinción entre detectadas, guardadas, actualizadas y descartadas.
- Falta de error_type y error_message útiles.

### Solución esperada

La solución debería incluir logs con:

- ID de inmobiliaria.
- Nombre de inmobiliaria.
- URL procesada.
- Estrategia usada.
- Propiedades detectadas.
- Propiedades nuevas.
- Propiedades actualizadas.
- Propiedades descartadas.
- Motivo de descarte.
- Error type.
- Error message.
- Duración del proceso.
- Estado final.

### Resultado

Pendiente.

### Estado

En revisión

---

# Diagnóstico run53 (2026-05-29) - Errores de scraping por familias

Diagnóstico sobre la última corrida completa (**run53**, 2026-05-25). Fuente: logs `*_err.log` (el scraper loguea el detalle a stderr).

## Números globales

```text
Intentos de item: 498
Éxitos:           169 (34%)
Errores:          329 (66%)
```

## Distribución de errores

| error_type | Cantidad | % de errores |
|---|---:|---:|
| requires_playwright | 123 | 37% |
| no_property_links_confirmed | 84 | 26% |
| timeout | 26 | 8% |
| sin_propiedades | 24 | 7% |
| item_timeout | 23 | 7% |
| site_down_confirmed | 15 | 5% |
| strategy_quality_failed | 13 | 4% |
| no_property_links | 12 | 4% |
| blocked (403/429/captcha) | 6 | 2% |
| final_url_domain_mismatch | 2 | <1% |
| save_failed | 1 | <1% |

## Familias de error

- **Familia 1 - requires_playwright (123, ~37%)**: sitios que renderizan el listado con JavaScript. Causa general: Playwright apagado por defecto y el orquestador diario no lo activaba. **Corrección general** (mayor impacto). Prioridad máxima.
- **Familia 2 - no_property_links / confirmed (96, ~29%)**: parte se solapa con Familia 1 (sin JS no aparecen links). Re-medir DESPUÉS de habilitar Playwright. Parcialmente general.
- **Familia 3 - timeouts (timeout + item_timeout = 49, ~15%)**: sitios lentos / sitemaps grandes, agravado por concurrencia alta. General (ajuste de timeouts/workers). Prioridad media.
- **Familia 4 - strategy_quality_failed + sin_propiedades (37, ~11%)**: extrajo pero con baja calidad o sin propiedades publicadas. Mixto. Re-medir después de Familias 1 y 3.
- **Familia 5 - site_down_confirmed (15)**: sitio realmente caído. No-código / específico.
- **Familia 6 - blocked (6)**: antibot/captcha/rate-limit. Mayormente no-código.
- **Familia 7 - final_url_domain_mismatch + save_failed (3)**: marginal. Específico.

## Conclusión

El primer cambio general de **alto impacto** es permitir **Playwright de forma controlada** (`--allow-playwright`), sin activarlo por defecto. La calidad de datos post-extracción (precio, imágenes, ciudad/provincia) está sana: el problema está en descubrimiento, render JS y timeouts, no en normalización.

## Corrección aplicada (parcial)

- Se agregó `--allow-playwright` al orquestador `run_daily_pipeline.py` (commit `7af5248`).
- Pendiente: retest controlado con `--test-url --allow-playwright` antes de habilitarlo en corridas reales. Ver [[11 - Pendientes]].

---

# Historial de soluciones aplicadas

Usar esta sección cuando un error haya sido realmente corregido.

---

## Solución aplicada 1

### Fecha

Pendiente.

### Error relacionado

Pendiente.

### Qué se modificó

Pendiente.

### Archivos modificados

Pendiente.

### Comando ejecutado

Pendiente.

### Resultado

Pendiente.

### Estado final

Pendiente.

---

# Comandos útiles para registrar errores

Usar esta sección para anotar comandos que ayudan a revisar problemas.

```
python scraper\scraper_propiedades.py --integrity-dry-run --max-items 50
```

Uso:  
Sirve para hacer una revisión de integridad sin reclamar cola, sin scrapear y sin guardar nada.

---

# Checklist después de cada corrección

Después de corregir un error, revisar:

- [ ]  Qué archivo se modificó.
- [ ]  Qué problema intentaba resolver.
- [ ]  Si se ejecutó una prueba.
- [ ]  Qué comando se ejecutó.
- [ ]  Qué resultado dio.
- [ ]  Si afectó Supabase.
- [ ]  Si modificó datos.
- [ ]  Si creó datos nuevos.
- [ ]  Si actualizó datos existentes.
- [ ]  Si el error volvió a aparecer.
- [ ]  Si hay que avisar algo en otra nota.

---

# Reglas para no romper el proyecto

- No borrar tablas sin revisar.
- No modificar datos de forma destructiva.
- No corregir manualmente errores que deberían resolverse desde código.
- No hacer cambios grandes sin entender qué se modifica.
- No ejecutar comandos destructivos sin confirmar.
- No forzar Git si no es necesario.
- No asumir que un error se solucionó sin probarlo.
- No mezclar scraping, frontend y base de datos sin registrar qué se tocó.
- No ignorar errores repetidos.
- No priorizar cantidad de datos por encima de calidad.

---

# Notas generales

Cada vez que se solucione un error, actualizar esta nota con:

- Qué se modificó.
- Qué archivo se cambió.
- Qué comando se ejecutó.
- Qué resultado dio.
- Si el error volvió a aparecer o no.
- Qué decisión se tomó.

Esta nota debe mantenerse actualizada después de cada sesión importante de trabajo técnico.

El objetivo no es tener una nota perfecta, sino tener memoria técnica del proyecto para no repetir errores y poder explicarle el contexto a ChatGPT, Codex o Claude cuando sea necesario.