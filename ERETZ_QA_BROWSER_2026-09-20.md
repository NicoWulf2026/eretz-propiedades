# Browser QA contra la API local — lo que pasa y lo que no

**2026-09-20 · `database_writes: 0` · `production_connections: 0`**

Codex dejó browser QA y staging **sin ninguna prueba**, y los dos intentos de
levantar un devserver en su sesión fueron rechazados. Acá está corrido, contra
una API local servida desde el snapshot, sin tocar Supabase ni producción.

## Cómo se armó

1. `api/v2` servida con uvicorn en `127.0.0.1:8099`, leyendo
   `_scratch/unification/snapshot_image_v4/ERETZ_API_SNAPSHOT.sqlite3` en modo
   `?mode=ro`. 57.665 propiedades.
2. Next.js en `localhost:3100` con `ERETZ_API_V2_BASE_URL` apuntando a esa API.
3. La suite Playwright que ya existía en `frontend/e2e`, sin modificarla.

Nada de esto toca la base: la API abre el SQLite en solo lectura y el frontend
no tiene credencial configurada.

## Resultados

| | |
|---|---|
| **Playwright e2e** | **63 passed**, 2 failed, 7 skipped · 8 min |
| **Vitest** | **1235 passed**, 9 skipped, 92 archivos |
| **typecheck** | pasa |
| **Benchmark de API** | 14 casos, todos con su status esperado |

Los 7 skipped son del asistente de publicación, con su bandera apagada.

### Latencia, re-medida sobre el mismo snapshot

| caso | mediana | máx |
|---|---:|---:|
| `price_asc` | 19 ms | 159 ms |
| `window_end` | 42 ms | 106 ms |
| `explorer` | 285 ms | **4.745 ms** |
| `map_small` | 590 ms | **4.624 ms** |
| `combined` | 813 ms | 2.772 ms |
| `map_large_combined` | 1.193 ms | 1.404 ms |
| `detail` | 7,5 ms | 8 ms |
| `batch_100` | 23 ms | 64 ms |

Consistente con lo que Codex había medido (~877–1209 ms combinada, ~1100–1227
el mapa, ~10 ms detalle, ~37–41 batch100), con `batch_100` algo mejor. Los
máximos de casi 5 s en `explorer` y `map_small` son los outliers que Codex ya
había anotado como variabilidad del host.

Los rechazos también funcionan: `window_rejected` devuelve 400 e `invalid_sort`
devuelve 422, en 5–6 ms.

---

## Los dos que fallan, y por qué no son defectos del frontend

### `test_filter_metadata_enriches_existing_controls_without_changing_values`

```
esperaba  'Comprar (42.536)'
obtuvo    'Comprar (42.691)'
```

El test fija un **conteo literal** de propiedades. El snapshot cambió y el
número con él. Es la tercera variante que aparece hoy del mismo problema: un
test que mide una constante en vez de una conducta —antes fueron fechas fijas
en `test_fuente_cambiada_invalida` y totales de suite escritos de memoria—.

Lo que el test quiere probar es que **el control muestra el valor que la API
reporta**, y eso se puede afirmar sin clavar el número: comparar el texto del
`<option>` contra la respuesta de `/api/properties/filter-metadata`. No lo
cambié todavía porque toca una suite que no escribí y prefiero proponerlo
antes que reescribirlo de apuro.

### `test_accented_api_v2_autocomplete_keeps_real_levels[1366-ros-Rosario]`

El test espera tres niveles —Municipio, Provincia y Localidad— para `ros`. La
API devuelve **Municipio y Localidad**, y ninguna Provincia.

No es el frontend: **el snapshot no tiene jerarquía geográfica**. Medido sobre
las 12 sugerencias de `ros`:

| campo | nulos |
|---|---|
| `province` | 12 de 12 |
| `department` | 12 de 12 |
| `municipality` | 12 de 12 |
| `locality` | 12 de 12 |
| `entityId` | 12 de 12 |
| `canonical` | 5 de 12 |

El contrato soporta los niveles y el dato no los llena.

---

## Lo que esto conecta

La jerarquía vacía no es un problema del buscador: es el mismo hueco que
apareció midiendo `barrio`. En las 72 agencias con `barrio` rechazado, la
cobertura de `ciudad` tiene **mediana 0,205** — el 80 % de las propiedades no
tiene ni barrio ni ciudad.

Dos caminos distintos llegando al mismo lugar: **la geografía del catálogo es
delgada**, y eso limita el buscador por área tanto como la certificación.

Es la próxima investigación, y hay que separar sus causas antes de tocar nada:
la fuente no publica, el extractor no detecta, la normalización pierde, el
validador rechaza, o GeoRef no encuentra la localidad. Ya hay una respuesta
parcial —los 2.140 «barrios rechazados» eran ciudades promovidas, no datos
perdidos—, y eso deja el resto más acotado.

## Lo que NO se probó

- Staging real ni Preview: no hay entorno configurado y no lo invento.
- La API alojada: esto corre contra un snapshot local, no contra Supabase.
- Carga concurrente: las latencias son de un proceso local, no TTFB remoto.
