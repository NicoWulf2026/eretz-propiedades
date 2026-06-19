# Producto y funcionalidades

Ultima actualizacion: 2026-06-04

Esta nota documenta como debe funcionar ERETZ Propiedades como producto.

## Propuesta de producto

ERETZ Propiedades ayuda a buscar, comparar y entender propiedades mediante datos centralizados, mapa, filtros y trazabilidad a la fuente original.

No es una inmobiliaria ni vende propiedades directamente. La plataforma organiza informacion y deriva al usuario a la publicacion original o a la inmobiliaria.

## Experiencia central

El mapa es protagonista.

La experiencia debe permitir:

- Explorar propiedades por ubicacion.
- Ver resultados sincronizados con el mapa.
- Filtrar por operacion, tipo, precio, ciudad, provincia e inmobiliaria.
- Comparar opciones.
- Entender mejor zonas y precios.
- Abrir el link original.
- Contactar a la inmobiliaria cuando exista informacion confiable.

## Funcionalidades actuales del frontend

Ver tambien [[Frontend estado 2026-06-04]].

- Loading/skeleton.
- Lazy loading de imagenes.
- Filtros client-side.
- Ordenamiento.
- Empty state.
- Mapa con limite de marcadores.
- Timeout Supabase 4500ms.
- Navbar mejorado.
- Layout desktop con mapa a la izquierda y resultados a la derecha.
- Modos de vista: `map-large`, `balanced`, `list-large`, `map-only`, `list-only`.
- Cards premium con precio protagonista, specs, inmobiliaria/desarrolladora, link original y contacto si existe.
- Seleccion mapa-listado.
- Markers seleccionados.
- Fullscreen mapa.

## Pendientes de producto/frontend

- R6 mobile.
- Revision visual general.
- Incorporar logo real.
- Revisar performance con datos reales publicados.
- Revisar consultas Supabase al publicar en produccion.

## Criterios para mostrar propiedades

Una propiedad publicable deberia tener:

- URL original y normalizada.
- Inmobiliaria/desarrolladora identificada.
- Titulo util.
- Tipo y operacion validos.
- Precio y moneda cuando la fuente los publique.
- Ubicacion suficiente para mapa o, si es aproximada, indicarlo.
- Imagen real o tratamiento claro si no existe.
- Link a fuente original.
- Score de calidad aceptable.

## Propiedades retenidas

No todas las propiedades de staging deben mostrarse.

Retener si:

- Falta ubicacion critica.
- Geocoding esta pendiente o fallo sin alternativa confiable.
- Precio/moneda es dudoso.
- Imagenes son placeholders/logos.
- Hay duplicado dudoso.
- Score o issues indican mala calidad.

## Duplicados como funcionalidad

No todos los duplicados son basura.

Si una misma propiedad aparece publicada por varias inmobiliarias, puede convertirse en una funcionalidad:

- Mostrar "tambien publicada por otras inmobiliarias".
- Comparar precio, descripcion o condiciones.
- Mantener trazabilidad de cada fuente.

## Datos que no deben inventarse

- Ciudad/provincia si la fuente no da seniales claras.
- Coordenadas.
- Precio.
- Moneda.
- Imagenes reales.
- Contacto.
- Inmobiliaria.

Si hay duda, guardar null, marcar issue y retener.

## Funcionalidades futuras

- Vista detalle de propiedad.
- Favoritos.
- Alertas.
- Comparador.
- Historial de precios.
- Metricas de mercado.
- IA asesora.
- Panel para inmobiliarias.
- Reportes de mercado.

## Notas relacionadas

- [[01 - Visión y estrategia]]
- [[03 - Desarrollo técnico]]
- [[Frontend estado 2026-06-04]]
- [[Politicas de calidad y publicacion]]
- [[11 - Pendientes]]
