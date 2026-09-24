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

---

# Segunda corrida, 2026-09-21: contra la geografía recuperada

## El síntoma que abrió todo esto está cerrado

El test de autocompletado esperaba tres niveles para `ros` y la API devolvía
dos, porque el snapshot no tenía jerarquía. Ahora la tiene:

```
q='ros'   MUNICIPIO  Rosario   7.726
          LOCALIDAD  Rosario   1.668
```

| columna del snapshot | antes | ahora |
|---|---:|---:|
| `municipio` | **0** | **36.281** |
| `departamento` | 9.568 | 45.551 |
| `provincia` | 52.849 | 56.246 |
| `latitud` | 38.827 | 42.225 |
| `SIN_AREA` | 4.350 | **953** |

## Un defecto de búsqueda que apareció al mirar

`collate nocase` de SQLite pliega mayúsculas ASCII y no toca los acentos, así
que **`cordo` devolvía cero áreas** y `córdo` devolvía las tres. Quien escribe
sin acento es casi todo el mundo. Arreglado comparando sin acentos de los dos
lados, con las columnas plegadas guardadas e indexadas.

| | |
|---|---:|
| antes del arreglo, `cordo` | **0 áreas** |
| después | 3 áreas, 4–14 ms |

## Cuatro veces que el error estuvo en mi medición

Vale anotarlas juntas porque son el mismo error con cuatro caras, y las cuatro
veces la conclusión equivocada estaba a un paso:

1. **La sonda de coordenadas.** Busqué `lat\s*[:=]` y el HTML tiene `"lat":`.
   Concluí «la fuente no publica coordenadas» sobre una página que las
   publicaba.
2. **El 0 % de conflictos.** Comparé la provincia publicada contra el padrón
   sin notar que el conflicto **vacía** esa columna: comparaba contra nulos.
   Un cero exacto fue lo único que me hizo desconfiar.
3. **La clave de la respuesta.** Leí `d["sugerencias"]` y la API devuelve
   `d["data"]`. Reporté que el autocompletado no devolvía nada.
4. **El servidor zombi.** Maté uvicorn y lo relancé tres veces; las dos
   últimas no pudieron tomar el puerto 8099 y murieron en silencio. Todo lo
   que medí después fue contra el proceso viejo. Por eso «seguía en 436 ms»
   después de dos arreglos que sí funcionaban: medido contra el servidor
   correcto, **4 a 14 ms**.

El patrón es uno solo: **verifiqué el sistema con una herramienta que no
verifiqué**. La defensa que funcionó las cuatro veces fue la misma —un número
demasiado redondo o demasiado parejo— y no la disciplina.

Lo concreto para la próxima: antes de creerle a una medición sobre un
servidor, preguntar **desde cuándo está corriendo ese proceso**.

```powershell
Get-NetTCPConnection -LocalPort 8099 -State Listen |
  ForEach-Object { (Get-Process -Id $_.OwningProcess).StartTime }
```

## Lo que NO se probó todavía

- La suite Playwright completa contra este snapshot. Queda pendiente y es lo
  siguiente.
- Los dos tests que fallaban en la corrida anterior: el de conteo literal
  sigue siendo un conteo literal, y el de niveles debería cerrarse solo, pero
  **no está comprobado**.

---

# Tercera corrida, 2026-09-24: suite completa contra la snapshot v4 nueva

**`database_writes: 0` · `production_connections: 0`**

- API: sólo el router `/v2`, en `127.0.0.1:8099`, sin `.env` ni Supabase,
  leyendo en solo lectura `_scratch/unification/snapshot_v4_2026-09-24/`
  (57.665 filas, municipio 36.271). La snapshot servida no se tocó.
- Frontend: `next dev` en `:3100` con `ERETZ_API_V2_BASE_URL` en un
  `.env.development.local` temporal (ignorado por git, borrado al terminar).
- Antes de medir se verificó desde cuándo corría cada puerto (16:39 y 16:40):
  la lección de la segunda corrida.

| | primera pasada | tras los arreglos |
|---|---:|---:|
| Playwright e2e | 63 passed, 2 failed, 7 skipped | **65 passed**, 7 skipped |
| Vitest | — | 1.237 passed, 9 skipped |
| tsc / eslint | — | limpios |

Los 7 skipped siguen siendo el asistente de publicación con su bandera apagada.

## Los dos que fallaban

1. **`test_mouse_keyboard_close_requery_and_typed_url` era un defecto real**,
   no del test. El `onBlur` del buscador programaba `setOpen(false)` a 140 ms
   y nunca lo cancelaba: si el foco volvía antes, la lista se abría y se
   cerraba sola. En la e2e, una opción visible que desaparecía antes del
   `mousedown` — 1 de 3 corridas en verde. Arreglado en `c4051b4a21` (el
   cierre pendiente vive en un ref y se cancela al volver el foco); 4 de 4.
2. **El conteo literal** («Comprar (42.536)») ahora se compara contra lo que
   devuelve `/api/properties/filter-metadata`. Era el cambio que la primera
   corrida propuso y dejó sin hacer.

El de niveles de `ros` que fallaba el 20-09 pasa: la jerarquía está en la v4.
