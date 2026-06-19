# Sprint E — Frontend labels y visualización de datos incompletos

Ultima actualizacion: 2026-06-10

Estado: **CERRADO** ✅ — completado 2026-06-10

---

## Objetivo

Actualizar el frontend para mostrar correctamente los estados, operaciones e indicadores de datos faltantes definidos en sprints anteriores, sin cambiar el diseño general.

Regla de negocio: todas las propiedades deben mostrarse aunque tengan datos incompletos o estados no-activos.

---

## Archivos modificados

| Archivo | Cambio principal |
|---|---|
| `frontend/src/types/property.ts` | `PropertyOperation` y `PropertyStatus` ampliados |
| `frontend/src/lib/property-mapper.ts` | `normalizeOperation()` y `normalizeStatus()` actualizados |
| `frontend/src/lib/property-supabase-service.ts` | Eliminado filtro `.in("estado",...)` |
| `frontend/src/lib/analysis-currency.ts` | `"Consultar"` → `"Consultar precio"` |
| `frontend/src/components/property/PropertyCard.tsx` | Labels + badge de estado |
| `frontend/src/components/filters/FilterBar.tsx` | Chips de operacion nuevos |
| `frontend/src/components/map/PropertyLeafletMap.tsx` | Labels de operacion en mapa |

---

## Cambios detallados

### `types/property.ts`

```typescript
// Antes:
type PropertyOperation = "venta" | "alquiler" | "inversion" | "temporario";
type PropertyStatus = "activa" | "pausada" | "reservada" | "vendida" | "alquilada";

// Despues:
type PropertyOperation = "venta" | "alquiler" | "inversion" | "temporario" | "consultar" | "venta_y_alquiler";
type PropertyStatus = "activa" | "pausada" | "reservada" | "vendida" | "alquilada" | "desconocida" | "no_detectada_en_ultimo_scraping";
```

### `property-mapper.ts`

`normalizeOperation()`:
- `venta_y_alquiler` reconocido antes de separar venta/alquiler.
- `consultar` reconocido explicitamente.
- Fallback de operacion desconocida: `"consultar"` (antes `"venta"`).

`normalizeStatus()`:
- `no_detectada_en_ultimo_scraping` reconocido por `includes("no_detect")`.
- `desconocida` reconocido por `includes("descon")`.

### `property-supabase-service.ts`

Critico: eliminado `.in("estado", ["activo", "activa"])` de las dos queries (fetchRecentActivePropertyIds y fetchFrontendRowsForIds).

Antes: solo se mostraban propiedades con estado activo/activa. Ahora: todas las propiedades se muestran sin filtro de estado.

Motivo: Decision 13 — publicar todo, con indicadores de completitud visibles.

### `analysis-currency.ts`

`getOriginalPublishedPriceLabel`: retorna `"Consultar precio"` cuando `price <= 0` o null.

Usado tanto en tarjetas como en popups del mapa.

### `PropertyCard.tsx`

Nuevo dict `OPERATION_LABEL`:
- `consultar` → "Consultar" (chip color: ink-950/55 blanco)
- `venta_y_alquiler` → "Venta y alquiler" (chip color: violet-700)

Nuevo dict `STATUS_LABEL` + `STATUS_CLS`:
- `reservada` → badge "Reservada" (amber-500)
- `vendida` → badge "Vendida" (red-600)
- `alquilada` → badge "Alquilada" (emerald-700)
- `no_detectada_en_ultimo_scraping` → badge "Sin datos recientes" (ink-950/65)
- `desconocida` → badge "Estado desconocido" (ink-950/40)

Badge posicionado en top-left de la imagen, visible sobre el placeholder y la foto real.

### `FilterBar.tsx`

`OPERATION_OPTIONS` ampliado:
- Agregados `venta_y_alquiler` ("Venta y alquiler") y `consultar` ("Consultar") como chips de filtro.

### `PropertyLeafletMap.tsx`

`operationLabels` ampliado:
- `consultar` → "Consultar"
- `venta_y_alquiler` → "V+A" (abreviado para caber en marcador)

---

## Resultado del sprint

| Tarea | Estado |
|---|---|
| No ocultar propiedades por estado | ✅ filtro eliminado |
| Label "Consultar" para op=consultar | ✅ |
| Label "Venta y alquiler" para op=venta_y_alquiler | ✅ |
| Badge de estado en tarjeta | ✅ 5 estados cubiertos |
| "Consultar precio" para precio null | ✅ |
| Placeholder para props sin imagen | ✅ (ya existia; conservado) |
| Sin coords: listado si, mapa no | ✅ (ya existia; conservado) |
| Filtros: ops nuevas en chips | ✅ |
| Mapa: ops nuevas en labels | ✅ |
| ESLint | ✅ 0 errores |
| TypeScript | ✅ 0 errores |

---

## Pendientes para Sprint F

- `npm run dev` y revision visual real en browser
- Opacidad para tarjetas de props no-activas
- Indicador "No aparece en mapa" en tarjeta sin coordenadas
- Filtro por estado en FilterBar
- Mejorar marcador `venta_y_alquiler` en mapa (icono dual o mejor etiqueta)
- Revision mobile

---

## Notas relacionadas

- [[Roadmap 2026-06-09]]
- [[Sprint D - Prueba controlada pipeline]]
- [[10 - Decisiones importantes]]
- [[2026-06-10 - Registro diario]]
