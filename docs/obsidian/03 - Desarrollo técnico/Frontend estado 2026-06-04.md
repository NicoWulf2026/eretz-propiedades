# Frontend - estado 2026-06-04

## Ubicacion

El frontend vive dentro de:

```text
frontend/
```

Rama frontend:

```text
feature/frontend-home-map-ui
```

## Estado actual

El frontend avanzo fuerte en la experiencia principal de mapa/listado. R5 quedo cerrado con build/lint OK.

El mapa es el centro de la experiencia. El listado acompaña y permite explorar resultados con contexto.

## Avances completados

- Loading/skeleton.
- Lazy loading de imagenes.
- Filtros client-side.
- Ordenamiento.
- Empty state.
- Performance client-side.
- Mapa limita marcadores.
- Timeout frontend Supabase con `AbortController` 4500ms.
- Marca corregida a `ERETZ Propiedades`.
- Navbar mejorado.
- Layout desktop:
  - mapa a la izquierda;
  - resultados a la derecha;
  - mapa como protagonista.
- Modos de vista:
  - `map-large`;
  - `balanced`;
  - `list-large`;
  - `map-only`;
  - `list-only`.
- Filtros sectorizados.
- Cards premium con:
  - precio protagonista;
  - specs;
  - inmobiliaria/desarrolladora;
  - link original;
  - contacto si existe.
- Fix para no mostrar "Publicado por ERETZ Propiedades" si no hay inmobiliaria real.
- Seleccion mapa-listado.
- Markers seleccionados.
- Fullscreen mapa.
- R5 cerrado con build/lint OK.

## Pendientes frontend

- R6 mobile.
- Revision visual general.
- Incorporar logo real en `frontend/public/brand/`.
- Revisar performance cuando haya datos publicados reales.
- Revisar query Supabase cuando se publique en produccion.

## Regla de marca

Usar siempre `ERETZ Propiedades`.

No usar:

- `Inmocapital`.
- `INMOCAPITAL`.
- `ERETZ Propiedades`.

## Relacion con publicacion

No conviene publicar masivamente a Supabase todavia.

Antes de ampliar datos publicos:

1. Mejorar calidad desde pipeline.
2. Repetir readiness audit.
3. Publicar una tanda chica.
4. Revisar visualmente mapa, cards, filtros y performance.
5. Ampliar por etapas.
