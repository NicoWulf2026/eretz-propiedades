# Geocoding

Ultima actualizacion: 2026-06-09 (Sprint B cerrado)

---

## Objetivo

Convertir direcciones textuales en coordenadas (latitud, longitud) para mostrar propiedades en mapa.

---

## Estado actual

- Proveedor: Nominatim (OpenStreetMap).
- Script: `scripts/geocode_staging.py`.
- Tabla fuente: `propiedades_staging` (Neon).
- Tabla de cache: `geocoding_results` (Neon).

Statuses de geocoding:
- `pending`: pendiente de geocodificar.
- `done`: geocodificado exitosamente.
- `failed`: intento fallido (direccion incorrecta, fuera de Argentina, etc.).
- `skipped`: direccion insuficiente, no se intenta.

---

## Regla de propiedades sin coordenadas

Una propiedad sin coordenadas:
- Aparece en el listado publico.
- No aparece en el mapa.
- No se descarta ni se retiene en staging por falta de coordenadas.

---

## Ciudades con bbox definida (CITY_BBOXES)

Bboxes en `scraper/geocoder.py` para deteccion de outliers de geocoding.

| Ciudad | Provincia | Bbox (lat_min, lat_max, lon_min, lon_max) | Estado |
|--------|-----------|-------------------------------------------|--------|
| Buenos Aires | Buenos Aires | (-34.71, -34.52, -58.53, -58.33) | ✅ |
| Rosario | Santa Fe | (-33.01, -32.85, -60.75, -60.55) | ✅ |
| Cordoba | Cordoba | (-31.50, -31.30, -64.30, -64.10) | ✅ |
| Mendoza | Mendoza | (-32.95, -32.82, -68.92, -68.78) | ✅ |
| Santa Fe | Santa Fe | (-31.68, -31.58, -60.75, -60.63) | ✅ |
| Tandil | Buenos Aires | (-37.55, -37.10, -59.70, -58.50) | ✅ Sprint B |
| General Alvear | Mendoza | (-35.20, -34.80, -67.95, -67.30) | ✅ Sprint B |
| Sauce Viejo | Santa Fe | (-31.62, -31.48, -60.92, -60.70) | ✅ Sprint B |

---

## Fallback de ciudad por lote (Sprint B)

`geocode_staging.py` acepta `--fallback-city` y `--fallback-province` como argumentos CLI.

El fallback solo se activa cuando:
1. La prop no tiene ciudad/provincia propios.
2. La inmobiliaria (JOIN con `inmobiliarias_staging`) tampoco los tiene.
3. Ningun patron de URL/contexto detecta la ciudad (General Alvear, Las Heras, Tandil, Sauce Viejo, etc.).

Uso tipico para geocodificar props de una inmobiliaria de ciudad especifica:
```
python scripts/geocode_staging.py --dry-run \
  --fallback-city "General Alvear" \
  --fallback-province "Mendoza"
```

Nota: para produccion agregar `--commit` y opcionalmente `--ids-file` para limitar a un lote especifico.

---

## Issues resueltos (Sprint B)

- ✅ Contexto de ciudad: resuelto via `--fallback-city` / `--fallback-province`. No requirio cambio de schema.
- ✅ Tandil y General Alvear: bbox agregadas.
- ✅ Sauce Viejo: bbox agregada. Deteccion automatica por regex en URL/contexto.

---

## Pendientes

- Geocodificar props de Angelina (General Alvear, ~35 props) con fallback: disponible, no ejecutado.
- Retry outliers: props 81820 (Pagliaro) y 81777 (Angelina).
- Extraer direccion desde titulo para props con `direccion_normalizada = "-"` (ej: Sauce Viejo ~28 props).

---

## Notas relacionadas

- [[03 - Modelo de datos propiedades]]
- [[00 - Decisiones oficiales]]
- [[2026-06-09 - Registro diario]]
