# ETAPA 6B - Diagnostico y fix timeout frontend/Supabase

Fecha: 2026-06-09
Branch: `fix/scraping-diagnostics-batch`
HEAD inicial: `7d59bf4db9 docs(frontend): validate recovered properties visually`

## Objetivo

Resolver o aislar el timeout que hacia que el frontend local cayera a mock data al leer `v_propiedades_frontend_mapa`.

## Preflight

- Branch confirmada: `fix/scraping-diagnostics-batch`.
- HEAD confirmado: `7d59bf4db9` o posterior.
- No habia procesos `node/next/python` activos al inicio.
- No habia cambios staged.
- Working tree seguia sucio con cambios no relacionados ya inventariados.

## Archivos revisados

- `frontend/src/app/page.tsx`
- `frontend/src/app/debug-supabase/page.tsx`
- `frontend/src/lib/property-service.ts`
- `frontend/src/lib/property-supabase-service.ts`
- `frontend/src/lib/supabase-client.ts`
- `frontend/src/types/property.ts`

## Causa raiz

La consulta del frontend ordenaba directamente la vista:

```ts
supabase
  .from("v_propiedades_frontend_mapa")
  .select("*")
  .eq("estado", "activo")
  .order("updated_at", { ascending: false })
  .limit(limit)
```

El problema no era el volumen de columnas ni el `limit`: cualquier `order` sobre `v_propiedades_frontend_mapa` dispara `statement timeout`, incluso con `limit=10` y columnas minimas. Al fallar la consulta, `property-service.ts` caia correctamente al fallback de mock data, por eso la home mostraba `Datos demo` y 4 propiedades.

## Reproduccion read-only

Mediciones REST con la misma config publica del frontend:

| query | status | tiempo | rows |
| --- | ---: | ---: | ---: |
| vista columnas minimas, `limit=20`, sin `order` | 200 | 2361 ms | 20 |
| vista columnas minimas, `limit=20`, `order=updated_at.desc` | 500 | 4505 ms | - |
| vista `select(*)`, `limit=10`, `order=updated_at.desc` | 500 | 4640 ms | - |
| vista columnas necesarias, `limit=300`, `order=updated_at.desc` | 500 | 4572 ms | - |
| vista columnas necesarias, `limit=300`, sin `order` | 200 | 3136 ms | 300 |
| tabla `propiedades`, `order=id.desc`, `limit=300` | 200 | 2771 ms | 300 |
| vista por IDs recientes, sin `order`, 50 candidatos | 200 | 2148 ms | 45 |
| vista por IDs recientes, sin `order`, 100 candidatos | 200 | 1911 ms | 59 |
| vista por IDs recientes, sin `order`, 300 candidatos | 200 | 2013 ms | 127 |

La variante por IDs recientes incluyo las 38 propiedades publicadas.

## Fix aplicado

Se cambio `frontend/src/lib/property-supabase-service.ts` para evitar ordenar la vista:

1. Leer IDs recientes desde `propiedades` con una query liviana:

```ts
supabase
  .from("propiedades")
  .select("id")
  .eq("estado", "activo")
  .order("id", { ascending: false })
  .limit(recentIdCandidateLimit(limit))
```

2. Consultar `v_propiedades_frontend_mapa` por chunks de IDs, sin `order`, usando solo columnas necesarias para el mapper.
3. Reordenar en memoria segun el orden de IDs recientes.
4. Mantener timeout controlado y fallback a mock si Supabase falla.

Tambien se actualizo el texto de `frontend/src/app/debug-supabase/page.tsx` para reflejar que usa la misma carga de datos que la home.

## Validacion local

Comandos:

```powershell
npm run lint
npm run build
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Resultados:

| check | resultado |
| --- | --- |
| `npm run lint` | OK |
| `npm run build` | OK |
| home HTTP | 200 |
| home cae a mock | No |
| home muestra `Datos reales` | Si |
| home muestra propiedades reales | Si |
| home muestra propiedades del piloto | Si |
| `/debug-supabase` timeout | No |
| `/debug-supabase` recibidas | 10 |
| dev server apagado al final | Si |

Evidencia post-fix:

- Home: `225 avisos activos`, `225 propiedades activas`, `Datos reales`.
- DOM contiene propiedades del piloto, entre ellas:
  - `Venta Terreno calle Maipu - Ciudad Mendoza`
  - `Venta Deposito en calle Maipu 235 - Ciudad Mendoza`
  - `Casas en Venta - Garibaldi al 700`
- Captura: `reports/scraping_runs/import_controlado_20260608/etapa6b_home_supabase_real.png`

## Las 38 publicadas

Las 38 ya estaban verificadas en `v_propiedades_frontend_mapa` desde ETAPA 6A. Con el fix, la home vuelve a consumir datos reales y el set inicial incluye propiedades del piloto; el patron por IDs recientes usado por el frontend incluye las 38 publicadas.

## Riesgos

- El orden por `id.desc` se usa como proxy de recencia. Para inserts nuevos es correcto y evita el timeout, pero no reemplaza un indice/optimizacion futura sobre `updated_at`.
- La consulta trae candidatos recientes desde `propiedades` y luego filtra por la vista; puede devolver menos filas que el `limit` solicitado si algunos IDs no aparecen en la vista. En validacion local devolvio 225 propiedades reales.
- Un fix estructural futuro podria ser optimizar la vista o agregar indice/estrategia DB para ordenar por `updated_at`, pero no se aplico porque ETAPA 6B prohibia cambios de schema/migraciones.

## Recomendacion

El fix frontend queda validado para continuar con validacion visual real. Antes de publicar mas propiedades, repetir ETAPA 6A con la home ya en `Datos reales` y revisar mapa/listado sobre el lote piloto. Dejar cualquier optimizacion SQL como propuesta separada, no aplicada en esta etapa.

## Guardrails cumplidos

- No git push.
- No Supabase writes.
- No `publish_to_supabase`.
- No publish_queue.
- No import.
- No geocoding.
- No cambios de schema.
- No migraciones SQL.
- No `.env` ni secretos modificados.
- No borrado de datos.
- No scraper modificado.
