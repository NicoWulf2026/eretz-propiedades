# Politicas de calidad y publicacion

Ultima actualizacion: 2026-06-04

## Regla principal

No se publican propiedades para inflar volumen.

ERETZ Propiedades prioriza menos propiedades confiables antes que muchas propiedades sucias.

## Correccion de datos

No hacer correcciones manuales propiedad por propiedad.

Las mejoras deben entrar al pipeline:

- Scraping.
- Extraccion.
- Normalizacion.
- Validacion.
- Geocoding.
- Deduplicacion.
- Importacion.

## Politica de duplicados

### A. Duplicado exacto

Misma URL, mismo hash o misma publicacion repetida.

Accion esperada:

- No duplicar en publicacion.
- Mantener trazabilidad interna.

### B. Misma propiedad por varias inmobiliarias

Misma direccion/coordenada, precio y caracteristicas, pero distinta inmobiliaria.

Accion esperada:

- No borrar automaticamente.
- Agrupar.
- Mostrar "tambien publicada por otras inmobiliarias" cuando haya evidencia suficiente.

### C. Posible duplicado dudoso

Evidencia incompleta.

Accion esperada:

- Retener o marcar para revision.
- No fusionar automaticamente.

## Politica de precio

### Precio ausente en origen

Si la fuente no publica precio, no inventar.

Posible salida futura:

- Mostrar "Consultar" solo si la fuente realmente no muestra precio.

### Precio no extraido

Si el precio existe en HTML, JSON, API, titulo o descripcion pero no fue extraido, corregir scraper/normalizador.

## Politica de ubicacion

### Ubicacion exacta

Direccion confiable + ciudad/provincia + geocoding valido.

Publicable en mapa.

### Ubicacion aproximada

Ciudad/provincia confiables pero direccion insuficiente.

Puede ser publicable en listado, pero no debe inventar coordenadas exactas.

### Ubicacion no confiable

Direccion contaminada por telefono, email, precio, texto comercial o datos incompletos.

No geocodificar.

### Sin ubicacion

Retener hasta mejorar pipeline o confirmar que el origen no trae el dato.

## Politica de imagenes

### Imagen real

Foto de la propiedad desde galeria, API, JSON-LD, `og:image` o slider.

### Sin imagen real

Puede retenerse o mostrarse con placeholder propio solo si la politica de publicacion lo permite.

### Placeholder prohibido

No usar logos, iconos, mapas, SVGs, assets institucionales ni placeholders externos como fotos reales.

## Politica de publicacion futura

1. Primero publicar propiedades de maxima calidad.
2. Publicar en tandas chicas.
3. Validar visualmente frontend, mapa, filtros y cards.
4. Repetir readiness audit despues de cada etapa.
5. Ampliar solo si no aparecen problemas graves.
