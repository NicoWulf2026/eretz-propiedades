# Decisiones importantes

Ultima actualizacion: 2026-06-10 (Sprint F)

Esta nota registra decisiones estrategicas, tecnicas y comerciales relevantes de ERETZ Propiedades.

## Decision 1: No hacer un MVP basico

Fecha: mayo 2026

ERETZ Propiedades no se desarrollara como un MVP basico o incompleto. La intencion es construir una plataforma profesional, con datos confiables y estructura escalable.

Impacto:

- Priorizar estabilidad, calidad de datos, experiencia de usuario y escalabilidad.
- Evitar lanzar con datos sucios solo para mostrar volumen.

## Decision 2: Calidad de datos antes que cantidad

Fecha: mayo 2026

La cantidad de propiedades no debe ser mas importante que la calidad de la informacion.

Impacto:

- Revisar ubicacion, precio, moneda, tipo, operacion, imagenes, coordenadas y duplicados.
- Retener propiedades dudosas en staging.
- No publicar datos criticos incompletos sin validacion.

## Decision 3: Obsidian como centro de conocimiento

Fecha: mayo 2026

Obsidian se usa como centro de documentacion, decisiones, contexto y continuidad del proyecto.

Impacto:

- Mantener estado actual, roadmap, prompts, errores, decisiones y registros diarios.
- Obsidian no reemplaza a GitHub, Supabase, Neon ni los reportes operativos.

## Decision 4: Arquitectura dual Supabase + Neon

Fecha: 2026-05-29

Usar Neon como base interna/operativa y Supabase como base publica/canonica.

Flujo:

```text
scraper
-> Neon propiedades_raw
-> staging
-> geocoding
-> publish_queue
-> Supabase propiedades
-> Frontend
```

Motivo:

- Separar trabajo crudo/pesado de la base publica.
- Evitar cargas masivas sin control en Supabase.
- Mantener trazabilidad y staging antes de publicar.

## Decision 5: Corregir scraping por familias de error

Fecha: 2026-05-29

Los errores de scraping se corrigen por familias y causas generales, no inmobiliaria por inmobiliaria salvo que sea inevitable.

Impacto:

- Agrupar errores: SPA/API/XHR, WordPress/AJAX, static detail, cards no reconocidas, timeouts, URL mala, blocked/site_down.
- Implementar fixes generales seguros.
- Dejar cambios riesgosos detras de flag.

## Decision 6: Playwright y estrategias pesadas como flags controlados

Fecha: 2026-05-29

Playwright, visible API, static detail y network interception deben usarse de forma controlada y documentada cuando corresponda.

Impacto:

- Evitar costos innecesarios o scraping lento.
- Probar en muestras antes de generalizar.
- Mantener workers bajos.

## Decision 7: Scraping/autofix cerrado por ahora

Fecha: 2026-06-04

La auditoria global final confirma que no quedan pendientes corregibles con el mecanismo actual.

Datos clave:

- Total inmobiliarias registradas: 7.004.
- Inmobiliarias con web/url: 5.245.
- URLs procesadas localmente: 2.232.
- `v_next_scraping_batch` pendientes no procesadas localmente: 0.
- `latest errors` corregibles no procesados localmente: 0.
- Running/pending colgados: 0.

Impacto:

- No seguir scrapeando por ahora.
- Los errores restantes quedan clasificados como no corregibles automaticamente, fuente mala, sitios caidos/bloqueados, URL mala, fix especifico o requieren autorizacion.

## Decision 8: No publicar masivamente todavia

Fecha: 2026-06-04

No se publicara masivamente a Supabase todavia.

Motivo:

- Hay 76.048 propiedades en staging, pero solo 21.129 son publicables ahora con criterio estricto.
- 46.854 quedan retenidas/no publicables.
- 42.351 requieren geocoding.
- 22.853 tienen falta de ubicacion.
- 8.494 tienen falta de precio.
- 4.406 requieren deduplicacion o agrupacion.

Impacto:

- No correr `publish_to_supabase.py` para publicar masivamente.
- No correr `run_daily_pipeline.py --commit`.
- Preparar una publicacion futura controlada, empezando por 500 propiedades de maxima calidad.

## Decision 9: No reparar propiedades manualmente una por una

Fecha: 2026-06-04

No se haran correcciones manuales propiedad por propiedad.

Las correcciones deben incorporarse al pipeline para que cada nuevo scraping extraiga, normalice, valide, geocodifique y deduplique mejor automaticamente.

Impacto:

- Si falta ubicacion pero esta en URL, breadcrumb, titulo, descripcion o JSON-LD, debe recuperarse automaticamente cuando la senial sea clara.
- Si falta precio, distinguir si el origen no lo publica o si el scraper no lo extrajo.
- Si faltan imagenes, mejorar extraccion desde galleries, JSON-LD, `og:image`, APIs y sliders.
- Si hay datos contaminados, el validador debe marcarlos y evitar geocoding/publicacion dudosa.

## Decision 10: Duplicados como problema de producto, no solo de limpieza

Fecha: 2026-06-04

No todos los duplicados deben eliminarse.

Clasificacion:

- Duplicado exacto: misma URL, mismo hash o misma publicacion repetida.
- Misma propiedad por varias inmobiliarias: conservar trazabilidad y agrupar.
- Posible duplicado dudoso: retener o marcar para revision.

Impacto:

ERETZ Propiedades deberia poder mostrar "tambien publicada por otras inmobiliarias" cuando corresponda.

## Decision 11: Marca escrita siempre como ERETZ Propiedades

Fecha: 2026-06-04

La marca debe escribirse siempre como `ERETZ Propiedades`.

No usar:

- `Inmocapital`.
- `INMOCAPITAL`.
- `ERETZ Propiedades`.

## Decision 12: Alcance nacional desde el inicio

Fecha: 2026-06-09

ERETZ Propiedades tiene alcance nacional: Argentina completa.

No es un proyecto limitado a Santa Fe ni a ninguna region.

- Todas las inmobiliarias ya cargadas en la base forman parte del sistema.
- Santa Fe capital puede ser la primera ciudad fuerte de marketing, pero el producto es nacional.
- La cobertura se amplia gradualmente segun disponibilidad de datos.

## Decision 13: Publicar todas las propiedades aunque tengan datos incompletos

Fecha: 2026-06-09

Todas las propiedades deben guardarse y publicarse aunque tengan datos incompletos.

No se descarta ninguna propiedad por falta de imagenes, precio, descripcion, coordenadas, operacion clara ni calidad de datos.

Reglas:

- Sin precio: mostrar "Consultar precio".
- Sin operacion conocida: mostrar "Consultar".
- Puede ser venta y alquiler a la vez.
- Sin coordenadas: aparece en listado, no en mapa.
- Sin imagenes: aparece con placeholder.

Esto actualiza la decision 2 (calidad antes que cantidad). La nueva prioridad es: guardar todo, publicar todo, con indicadores de completitud visibles.

## Decision 14: Estados de propiedades (lista oficial)

Fecha: 2026-06-09

Estados posibles: `activa`, `reservada`, `vendida`, `alquilada`, `no_detectada_en_ultimo_scraping`, `consultar`, `desconocida`.

Regla: si una propiedad deja de aparecer en la web original, no se borra. Se conserva como historico y se marca `no_detectada_en_ultimo_scraping`.

Ver: [[08 - Estados de propiedades]]

## Decision 15: Propiedades repetidas entre inmobiliarias se conservan separadas

Fecha: 2026-06-09

Si una misma propiedad aparece en varias inmobiliarias, se muestra como publicaciones separadas. No se fusionan automaticamente.

A futuro puede mostrarse "tambien publicada por otras inmobiliarias" como informacion adicional.

Ver: [[07 - Deduplicacion]]

## Decision 16: Orden oficial de desarrollo

Fecha: 2026-06-09

Orden de desarrollo:
1. Scrapers + base de datos (foco actual).
2. Frontend publico.
3. Panel de inmobiliarias.
4. Carga manual de propiedades.
5. Marketing y crecimiento.
6. Monetizacion.

No avanzar fuerte en fases posteriores hasta estabilizar la fase anterior.

Ver: [[Roadmap 2026-06-09]]

## Decision 17: Contacto con inmobiliarias — orden de prioridad

Fecha: 2026-06-09

El frontend debe mostrar los datos de contacto en este orden:

1. Link original de la publicacion (mas importante).
2. WhatsApp.
3. Email.
4. Telefono.
5. Web de la inmobiliaria.

## Decision 18: Panel de inmobiliarias — verificacion por link de email

Fecha: 2026-06-09

Las inmobiliarias verifican su perfil via link seguro enviado a su email oficial.

No se usa contrasena fija inicial. El link de activacion es de un solo uso.

Las inmobiliarias verificadas pueden: editar propiedades scrapeadas, corregir datos, agregar imagenes, marcar estado y cargar propiedades nuevas.

Ver: [[00 - Decisiones]] (panel inmobiliarias)

## Decision 19: Particulares pueden cargar propiedades pero requieren revision

Fecha: 2026-06-09

Personas particulares pueden cargar propiedades con campos minimos obligatorios (ver nota del panel).

Las publicaciones de particulares pasan por revision antes de publicarse.

## Decision 20: Marketing — posicionamiento como buscador para usuarios, no B2B

Fecha: 2026-06-09

ERETZ Propiedades se posiciona primero como marca para usuarios que buscan propiedades.

No como herramienta B2B para inmobiliarias en la comunicacion publica inicial.

Mensaje: "ERETZ Propiedades centraliza propiedades disponibles de todo el pais para que buscar sea mas facil."

Canales prioritarios: Instagram, Facebook, TikTok, X, LinkedIn.

No mencionar el scraping de webs como argumento de marketing.

Ver: [[Estrategia general]]

## Decision 21: Actualizacion diaria por batches, no scraping masivo unico

Fecha: 2026-06-09

El objetivo es actualizar propiedades diariamente usando batches o cola de scraping.

Criterios de division: por provincia, tipo de web, inmobiliaria, prioridad, ultimo scraping exitoso, errores acumulados.

Cada corrida debe registrar logs, errores, reintentos y resultado.

Ver: [[06 - Batches diarios]]

## Decision 22: operacion desconocida se guarda como "consultar", no se rechaza

Fecha: 2026-06-09

Una propiedad sin operacion clara (venta/alquiler) no debe ser rechazada del pipeline.

Se normaliza a `consultar` y se publica de todas formas.

Motivo: muchos sitios no publican la operacion explicitamente. Rechazar esas propiedades significa perder datos validos.

Impacto tecnico:
- `validate_raw_properties.py`: hard reject de `invalid_operation` eliminado.
- `normalizar_operacion()` en scraper: fallback cambiado de `"venta"` a `"consultar"`.
- VALID_OPERATIONS en pipeline ampliado: consultar, venta_y_alquiler.

## Decision 23: schema de estados de propiedades en Supabase — 7 valores oficiales

Fecha: 2026-06-09

La columna `estado` en la tabla `propiedades` de Supabase tiene 7 valores validos:
activa / reservada / vendida / alquilada / no_detectada_en_ultimo_scraping / consultar / desconocida.

Los valores anteriores activo/inactivo fueron migrados:
- activo → activa (90.497 filas)
- inactivo → desconocida (829 filas)

Ningun estado elimina una propiedad del listado publico.

Archivo de migracion: `migrations/supabase_sprint_a_operacion_estado.sql`

## Decision 24: operaciones validas ampliadas — consultar y venta_y_alquiler

Fecha: 2026-06-09

Los valores validos de `operacion` en Supabase son:
venta / alquiler / alquiler_temporario / consultar / venta_y_alquiler.

`consultar` cubre el caso de operacion desconocida.
`venta_y_alquiler` cubre propiedades publicadas simultaneamente para ambas operaciones.

Impacto: el frontend no muestra todavia etiquetas especiales para estos valores. Queda para Sprint D.

## Decision 25: fallback de ciudad por argumento CLI en geocode_staging.py

Fecha: 2026-06-09

El script `geocode_staging.py` acepta `--fallback-city` y `--fallback-province` para proveer contexto de ciudad a props sin ciudad propia.

El fallback es el ultimo recurso: solo se aplica si la prop, la inmobiliaria, y los patrones de URL no proveen ciudad.

Motivo: el JOIN a `inmobiliarias_staging` no sirve para inmobiliarias establecidas (viven en Supabase, no en Neon). El fallback CLI evita un JOIN cross-DB o un cambio de schema.

Uso tipico: geocodificar todas las props de una inmobiliaria de ciudad especifica en un batch dedicado.

## Decision 27: deteccion de desaparecidas usa dos mecanismos complementarios

Fecha: 2026-06-09

La deteccion de propiedades que dejaron de aparecer en el sitio usa dos mecanismos:

1. `mark_inactivos()` en el scraper: actua en linea, agencia por agencia, durante el scraping. Inmediato.
2. `enqueue_deactivations.py`: auditoria post-run. Compara hashes del ultimo scraping exitoso en Neon vs props activas en Supabase. Encola `action='deactivate'` en `publish_queue` para lo que `mark_inactivos` no proceso.

Ambos mecanismos usan el mismo estado destino: `no_detectada_en_ultimo_scraping`.

El mecanismo 2 se activa en el pipeline con `run_daily_pipeline.py --with-deactivations` (FASE 2.5).

## Decision 30: el frontend no filtra propiedades por estado

Fecha: 2026-06-10

El frontend muestra todas las propiedades independientemente de su estado.

El filtro `.in("estado", ["activo","activa"])` fue eliminado de `property-supabase-service.ts` en Sprint E.

Impacto: propiedades con estado `vendida`, `reservada`, `alquilada`, `no_detectada_en_ultimo_scraping` o `desconocida` aparecen en el listado con un badge de estado visible en la tarjeta. El usuario puede verlas pero entiende su situacion actual.

Motivo: Decision 13 — guardar y publicar todo con indicadores de completitud visibles.

Si en el futuro se decide filtrar estados del listado por defecto, la logica correcta es agregar un filtro opcional en FilterBar (no volver a hardcodear el filtro en la query).

## Decision 28: pipeline controlado usa USE_INTERNAL_DB=true inline, sin modificar .env

Fecha: 2026-06-10

Durante Sprint D se establecio el patron correcto para correr el pipeline con Neon:

- `.env` mantiene `USE_INTERNAL_DB=false` (modo produccion / Supabase).
- Para correr el pipeline interno (propiedades_raw, propiedades_staging, publish_queue en Neon) se usa `$env:USE_INTERNAL_DB='true'` inline por sesion.
- No se modifica `.env` salvo autorizacion explicita.

Impacto: todos los scripts del pipeline (create_scraping_run, scraper, enqueue_deactivations, build_publish_queue, publish_to_supabase) respetan esta variable por sesion sin efectos secundarios.

## Decision 29: enqueue_deactivations no se ejecuta si la extraccion fue parcial

Fecha: 2026-06-10

Si `metadata.partial_extraction=True`, `completion_ratio < min_ratio` o `detectadas/expected < min_ratio`, el script omite la agencia y registra `skipped_partial=1`.

El umbral default es `--min-completion-ratio=0.5`. Por debajo del 50% de extraccion esperada, no se encolan deactivations.

Motivo: una extraccion parcial no puede distinguir propiedades genuinamente desaparecidas de propiedades simplemente no scrapeadas en esa corrida.

## Decision 31: el frontend usa query directa a propiedades, no la view v_propiedades_frontend_mapa

Fecha: 2026-06-10

El frontend consulta `public.propiedades` directamente con `ORDER BY id DESC LIMIT 50`.

No usa `v_propiedades_frontend_mapa` para la carga principal.

Motivo:
- La view tiene filtro `estado='activo'` incorrecto (debe ser `'activa'` tras Sprint A) — excluye todas las propiedades actuales.
- La view genera timeout 57014 (statement timeout) en Supabase por JOIN lento sobre 91k filas.
- La query directa usa el indice de `id` y carga datos en 7–13s vs 19–38s de la arquitectura anterior.

Columnas perdidas respecto a la view:
- `ciudad_final` / `provincia_final` (geocodificadas) → se usa `ciudad` / `provincia` directos.
- `inmobiliaria_nombre`, `inmobiliaria_web`, `inmobiliaria_telefono`, `inmobiliaria_email` → quedan null.
- `imagen_principal_real` / `tiene_imagen_real` → `hasRealImage` usa `images.length > 0` como fallback.

Impacto visual: las propiedades aparecen con ciudad/provincia tal como estan en la tabla, sin normalizacion geocodificada. Aceptable para el estado actual del proyecto.

La view puede corregirse en un sprint futuro de DB y reintroducirse si se optimiza el JOIN.

## Decision 33: índice compuesto en propiedades_staging autorizado para desbloquear build_queue

Fecha: 2026-06-12

Durante el recovery de Batch 50, `build_publish_queue.py` con `--limit 10000` tardaba >60s en la query `WHERE status='staging' ORDER BY validation_score DESC LIMIT 10000` sobre 78k filas staging. La causa fue falta de índice compuesto.

Acción autorizada:
```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_propiedades_staging_status_score_id
ON public.propiedades_staging (status, validation_score DESC, id ASC);
```

Resultado: query pasó de >60s (timeout) a <1s con el índice.

No genera riesgo: CREATE INDEX CONCURRENTLY no lockea la tabla. Sin impacto en datos ni en lógica de negocio.

## Decision 34: limpieza de data_quality_issues test data autorizada

Fecha: 2026-06-12

Durante el diagnóstico de storage (Neon al 81%), se detectaron 76,320 filas con `issue_type = 'source_test_mode_id_rewritten'` en la tabla `data_quality_issues`. Estas filas fueron generadas durante corridas de prueba en modo test y no representan datos de negocio.

Acción autorizada:
```sql
DELETE FROM public.data_quality_issues WHERE issue_type = 'source_test_mode_id_rewritten';
VACUUM public.data_quality_issues;
```

Resultado: 76,320 filas eliminadas. Tabla pasó de 148,332 a 72,012 filas. El espacio se reclamará progresivamente por autovacuum.

Solo este `issue_type` fue borrado. Todos los demás tipos (missing_location, low_quality_score, missing_images, etc.) se mantienen intactos.

## Decision 32: geocoding_status='failed' no bloquea publicacion

Fecha: 2026-06-11

Cuando allow_pending_geo=True (valor por defecto desde Sprint G0), los estados de geocoding permitidos para publicar son: done / skipped / pending / failed.

Una propiedad con geocoding_status='failed' se publica normalmente, pero sin pin en el mapa.

Motivo: el geocoding puede fallar por razones transitorias o por direccion no geocodificable (Nominatim). Bloquear propiedades tecnicamente validas por este motivo viola la regla de negocio (Decision 13: publicar todo).

Impacto tecnico:
- `build_publish_queue.py`: `allowed_geo.update({"pending", "failed"})` cuando allow_pending_geo=True.
- `publish_to_supabase.py`: misma logica en `validation_skip_reason()`.
- Batch 5: 36 propiedades con geocoding_status='failed' publicadas sin pin.

Complementa: [[Decision 13]] (publicar todo aunque falten datos), [[Decision 25]] (fallback ciudad por CLI).

## Decision 26: estado de propiedades desaparecidas es no_detectada_en_ultimo_scraping, no inactivo

Fecha: 2026-06-09

Cuando una propiedad deja de aparecer en el listado de la inmobiliaria, el sistema la marca como `no_detectada_en_ultimo_scraping`.

No se usa `inactivo` (valor eliminado de Supabase) ni `desconocida` (reservado para datos sin informacion suficiente).

Impacto tecnico Sprint B:
- `mark_inactivos()` en el scraper: filtro dual `in.(activo,activa)`, estado destino `no_detectada_en_ultimo_scraping`.
- `_detectar_estado_no_disponible()` en scraper: resultado `no_detectada_en_ultimo_scraping`.
- `publish_to_supabase.py`: `staging_to_prop()` incluye estado, default `"activa"` para publicaciones nuevas.

