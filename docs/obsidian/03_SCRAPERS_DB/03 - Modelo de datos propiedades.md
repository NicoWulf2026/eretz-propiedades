# Modelo de datos — Propiedades

Ultima actualizacion: 2026-06-09

---

## Campos principales

| Campo | Descripcion | Obligatorio | Sin dato |
|-------|-------------|-------------|----------|
| `id` | ID interno | Si | — |
| `url` | URL original de la publicacion | Si | — |
| `inmobiliaria_id` | ID de la inmobiliaria de origen | Si | — |
| `titulo` | Titulo de la publicacion | No | — |
| `tipo_propiedad` | Casa, depto, terreno, local, etc. | No | Desconocido |
| `operacion` | venta, alquiler, venta_y_alquiler | No | Consultar |
| `precio` | Precio numerico | No | Consultar precio |
| `moneda` | ARS, USD | No | Consultar |
| `superficie_total` | m2 totales | No | — |
| `superficie_cubierta` | m2 cubiertos | No | — |
| `ambientes` | Cantidad de ambientes | No | — |
| `dormitorios` | Cantidad de dormitorios | No | — |
| `banos` | Cantidad de banos | No | — |
| `descripcion` | Texto de descripcion | No | — |
| `direccion_normalizada` | Direccion procesada | No | — |
| `ciudad` | Ciudad | No | — |
| `provincia` | Provincia | No | — |
| `pais` | Pais | No | Argentina |
| `latitud` | Latitud geocodificada | No | Sin mapa |
| `longitud` | Longitud geocodificada | No | Sin mapa |
| `imagenes` | Lista de URLs de imagenes | No | Placeholder |
| `estado` | Estado de disponibilidad | No | desconocida |
| `geocoding_status` | pending / done / skipped / failed | No | pending |
| `validation_score` | Puntaje de calidad 0-100 | No | — |

---

## Operaciones validas

- `venta`
- `alquiler`
- `venta_y_alquiler` — una misma publicacion puede ser ambas
- `consultar` — se desconoce la operacion

---

## Contacto de la inmobiliaria

Cada propiedad debe mostrar, cuando exista:

| Campo | Prioridad de contacto |
|-------|----------------------|
| Link original de la publicacion | 1 (mas importante) |
| WhatsApp de la inmobiliaria | 2 |
| Email de la inmobiliaria | 3 |
| Telefono de la inmobiliaria | 4 |
| Web de la inmobiliaria | 5 |

El link original debe llevar siempre a la publicacion de origen, no a la home de la inmobiliaria.

---

## Pipeline de ingestion

```
scraper
  -> propiedades_raw (Neon)
  -> validacion + normalizacion
  -> propiedades_staging (Neon)
  -> geocoding
  -> publish_queue
  -> propiedades (Supabase)
  -> Frontend
```

---

## Notas relacionadas

- [[00 - Decisiones oficiales]]
- [[08 - Estados de propiedades]]
- [[07 - Deduplicacion]]
- [[10 - Geocoding]]
