# Sprint F — QA visual y UX frontend

Ultima actualizacion: 2026-06-10

Estado: **CERRADO PARCIAL** ⚡ — QA real completado; UX interactiva pendiente para Sprint G.

---

## Objetivo

Verificar visualmente que el frontend cargue datos reales desde Supabase, que el mapa y las tarjetas funcionen correctamente, y aplicar mejoras de UX para propiedades con datos incompletos o estados especiales.

---

## Resultado principal

El frontend paso de mostrar datos mock (4 propiedades demo) a datos reales de Supabase.

| Indicador | Antes | Despues |
|---|---|---|
| Fuente de datos | "Datos demo" | "Datos reales" ✅ |
| Propiedades visibles | 4 (mock) | 50 (reales) |
| Con ubicacion | 4 (mock) | 50 de 50 |
| AbortErrors en terminal | Si (frecuentes) | Ninguno |
| Latencia fresh load | 19–38s → fallo | 7–13s → exito |
| TypeScript | 0 errores | 0 errores |

---

## Causa raiz original: RLS sin policy SELECT

La tabla `public.propiedades` tenia RLS habilitado sin policy SELECT para el rol `anon`.

El frontend usa `NEXT_PUBLIC_SUPABASE_ANON_KEY` (rol anon). Sin policy, Supabase devolvía 0 filas → fallback a mock.

### Fix RLS (ejecutado manualmente en Supabase SQL Editor)

Archivo: `migrations/supabase_sprint_f_rls_public_read.sql`

```sql
DROP POLICY IF EXISTS "propiedades_public_read" ON public.propiedades;
CREATE POLICY "propiedades_public_read"
  ON public.propiedades FOR SELECT TO anon USING (true);
GRANT SELECT ON public.v_propiedades_frontend_mapa TO anon;
GRANT SELECT ON public.v_propiedades_frontend_mapa TO authenticated;
GRANT SELECT ON public.propiedades TO anon;
GRANT SELECT ON public.propiedades TO authenticated;
```

Resultado: 91.326 propiedades accesibles via anon key.

---

## Causa raiz secundaria: arquitectura 2 fases generaba 3 queries

Incluso despues del fix RLS, el frontend seguia cayendo a mock por `AbortError`.

Flujo anterior (3 queries en serie/paralelo desde unidad de red D:):
1. `GET propiedades?select=id&order=id.desc&limit=150` — ~5s
2. `GET propiedades?select=*&id=in.(chunk1)` — ~10–15s (paralelo)
3. `GET propiedades?select=*&id=in.(chunk2)` — ~10–15s (paralelo)

Latencia total: **19–38s**. `AbortController` con timeout de 25s disparaba → fallback a mock.

Ademas, `v_propiedades_frontend_mapa` tenia errores propios:
- `COALESCE(p.estado, 'activo') = 'activo'` — valor incorrecto (debe ser `'activa'` tras Sprint A)
- JOIN sobre 91k filas a `v_propiedades_location_ready` → timeout 57014 en Supabase

### Fix: query unica directa a `propiedades`

Archivo: `frontend/src/lib/property-supabase-service.ts`

```typescript
// Antes: arquitectura 2 fases / 3 queries
const ids = await fetchRecentActivePropertyIds(limit, signal); // query 1
return fetchFrontendRowsForIds(ids, signal);                   // queries 2 y 3

// Despues: 1 sola query con indice en id
const { data, error } = await client
  .from("propiedades")
  .select(FRONTEND_PROPERTY_COLUMNS)
  .order("id", { ascending: false })
  .limit(limit)
  .abortSignal(signal);
```

Latencia resultante: **7–13s fresh load** — dentro del timeout de 25s.

---

## Archivos modificados en Sprint F

| Archivo | Cambio |
|---|---|
| `frontend/src/types/property.ts` | Agregados `ciudad`/`provincia` directos; campos de view opcionales con `?:` |
| `frontend/src/lib/property-supabase-service.ts` | Query unica directa; timeout 25s; `FRONTEND_PROPERTY_COLUMNS` sin columnas de view |
| `frontend/src/lib/property-mapper.ts` | Fallback `ciudad_final ?? ciudad`; `hasRealImage` con `??`; null coercion para agencia |
| `frontend/src/lib/property-service.ts` | `limit: 50` en llamada a `getPropertiesFromSupabase` |
| `migrations/supabase_sprint_f_rls_public_read.sql` | Migration RLS creada (ejecutada manualmente) |

---

## Checklist QA Sprint F

| Tarea | Estado |
|---|---|
| RLS anon SELECT en propiedades | ✅ ejecutado |
| Frontend muestra "Datos reales" | ✅ confirmado via HTML |
| 50 propiedades reales visibles | ✅ confirmado |
| 50 con ubicacion | ✅ confirmado |
| Mapa carga con pins reales | ✅ screenshot (USD 610k, ARS 280k, USD 200k) |
| Tarjetas muestran datos reales | ✅ screenshot (Pagliaro, Tandil, USD 55k) |
| TypeScript: 0 errores | ✅ `tsc --noEmit` exit 0 |
| ESLint: 0 errores | ✅ |
| Sin AbortErrors despues del fix | ✅ |
| QA interactivo: filtros, scroll, busqueda | ⬜ Chrome MCP desconectado |
| MOLL (IDs 70772–70782) visible | ⬜ no en top-50 por ID; buscar con "Rosario" |
| Revision mobile | ⬜ pendiente Sprint G |
| Opacidad para props no-activas | ⬜ pendiente Sprint G |
| Indicador "No aparece en mapa" | ⬜ pendiente Sprint G |
| Filtro por estado en FilterBar | ⬜ pendiente Sprint G |

---

## Notas tecnicas

### `v_propiedades_frontend_mapa` — NO usar en frontend por ahora

La view tiene dos bugs criticos:
1. Filtra `estado='activo'` (valor anterior a Sprint A) — excluye todas las propiedades actuales (`estado='activa'`)
2. JOIN lento sobre 91k filas — genera timeout 57014 en Supabase

El frontend ahora consulta `public.propiedades` directamente. La view queda para futura correccion en un sprint de DB.

Fix pendiente para la view:
```sql
-- Cambiar:
COALESCE(p.estado, 'activo'::text) = 'activo'::text
-- Por:
COALESCE(p.estado, 'activa'::text) = 'activa'::text
-- Ademas: optimizar o eliminar el JOIN a v_propiedades_location_ready
```

### Latencia en unidad de red D:

El servidor Next.js corre desde D: (unidad de red). Next.js reporta advertencia:
> "Slow filesystem detected. The benchmark took 454ms."

Cada operacion de filesystem Node.js agrega ~5s de latencia. El timeout de 25s cubre el caso actual con la query unica.

---

## Pendientes para Sprint G

- Reconectar Chrome MCP (click en icono de extension).
- Probar filtros interactivos.
- Buscar MOLL en buscador con "Rosario" o "MOLL".
- Revision mobile.
- Opacidad/estilo para propiedades no-activas.
- Indicador "No aparece en mapa" en tarjetas sin coordenadas.
- Filtro por estado en FilterBar.
- Mejorar marcador `venta_y_alquiler` en mapa.
- Fix `v_propiedades_frontend_mapa` en Supabase (sprint futuro separado).

---

## Notas relacionadas

- [[Roadmap 2026-06-09]]
- [[Sprint E - Frontend labels]]
- [[10 - Decisiones importantes]]
- [[2026-06-10 - Registro diario]]
