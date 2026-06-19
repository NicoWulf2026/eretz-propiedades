# Vision y estrategia

Ultima actualizacion: 2026-06-04

Esta nota documenta la vision general, diferenciacion y direccion estrategica de ERETZ Propiedades.

## Que es ERETZ Propiedades

ERETZ Propiedades es una plataforma proptech orientada a centralizar, ordenar, normalizar y analizar informacion inmobiliaria proveniente de inmobiliarias y desarrolladoras.

No es simplemente otro portal de propiedades.

El diferencial es transformar informacion dispersa en datos comparables, trazables y utiles para tomar mejores decisiones.

## Idea central

No mostramos propiedades solamente. Ayudamos a entender el mercado.

## Rol del mapa

El mapa es el centro de la experiencia. La plataforma debe permitir explorar propiedades por ubicacion, detectar concentraciones, comparar zonas y entender el mercado de forma visual.

## Relacion con inmobiliarias

ERETZ Propiedades no vende propiedades directamente.

La plataforma organiza informacion y deriva al usuario a la publicacion original o a la inmobiliaria/desarrolladora correspondiente.

## Problema que resuelve

La informacion inmobiliaria suele estar:

- Dispersa en muchas paginas.
- Repetida.
- Desordenada.
- Dificil de comparar.
- Con precios en distintas monedas.
- Con ubicaciones poco claras.
- Con datos incompletos o inconsistentes.

ERETZ Propiedades busca ordenar esa informacion y convertirla en una herramienta de analisis.

## Solucion propuesta

- Centralizar publicaciones.
- Normalizar datos.
- Mantener trazabilidad a la fuente original.
- Mostrar propiedades en mapa.
- Permitir filtros utiles.
- Comparar precios y zonas.
- Identificar duplicados o publicaciones repetidas.
- Medir calidad de datos.
- Preparar analitica inmobiliaria futura.

## Principios estrategicos

### Calidad antes que cantidad

No sirve tener muchas propiedades si los datos son sucios, dudosos o imposibles de comparar.

### Pipeline antes que reparacion manual

Los problemas recurrentes deben corregirse en scraping, normalizacion, validacion, geocoding y deduplicacion. No se haran reparaciones manuales propiedad por propiedad.

### Publicacion controlada

No publicar masivamente a Supabase hasta mejorar calidad y revisar visualmente una muestra controlada.

### Transparencia

Cada dato importante debe poder rastrearse a una URL original, inmobiliaria, fecha de captura, estrategia e issues si existieron.

### Producto simple, sistema interno robusto

La experiencia del usuario debe ser clara. La complejidad de scraping, staging y calidad debe quedar debajo del producto.

## Estado estrategico vigente

- Scraping/autofix cerrado por ahora.
- No quedan pendientes corregibles con el mecanismo actual.
- Hay 76.048 propiedades en staging.
- 21.129 son publicables ahora con criterio estricto.
- 46.854 quedan retenidas/no publicables.
- La proxima etapa es mejorar calidad desde el pipeline.
- Frontend R5 esta cerrado; queda R6 mobile y revision visual.

## Alcance geografico

ERETZ Propiedades tiene alcance nacional: Argentina completa desde el inicio.

- Todas las inmobiliarias ya cargadas en la base forman parte del sistema.
- Santa Fe capital es la primera ciudad fuerte de marketing, no el limite del producto.
- La cobertura se amplia gradualmente segun disponibilidad de datos y capacidad de scraping.

## Modelo de negocio pensado

Principalmente B2B:

- Visibilidad para inmobiliarias/desarrolladoras.
- Leads medibles.
- Reportes de mercado.
- Analitica inmobiliaria.
- Herramientas para inmobiliarias.

La monetizacion no debe manipular datos ni dañar la confianza del usuario.

## Objetivo de corto plazo (FASE 1)

Estabilizar el sistema de scraping y persistencia de datos.

- Scraping con cobertura nacional y actualizacion diaria.
- Pipeline completo y confiable: raw -> staging -> geocoding -> publish_queue.
- Todas las propiedades guardadas aunque tengan datos incompletos.
- Estados de propiedades implementados.

El frontend, panel de inmobiliarias y marketing se desarrollan en fases posteriores.

## Objetivo de mediano plazo

Lanzar una version publica con:

- Mapa funcional.
- Datos confiables.
- Propiedades reales y trazables.
- Filtros utiles.
- Contacto o link a fuente original.
- Marca clara.
- Performance aceptable.

## Objetivo de largo plazo

Convertir ERETZ Propiedades en una plataforma de inteligencia inmobiliaria con datos, comparaciones, analisis por zonas, reportes y herramientas para usuarios, inversores e inmobiliarias.

## Notas relacionadas

- [[02 - Producto y funcionalidades]]
- [[03 - Desarrollo técnico]]
- [[04 - Supabase y base de datos]]
- [[05 - Scraping]]
- [[Roadmap actual 2026-06-04]]
- [[10 - Decisiones importantes]]
