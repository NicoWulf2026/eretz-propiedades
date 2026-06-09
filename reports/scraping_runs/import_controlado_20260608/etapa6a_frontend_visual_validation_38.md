# ETAPA 6A - Validacion visual read-only de 38 publicadas

Fecha: 2026-06-09
Branch: `fix/scraping-diagnostics-batch`
HEAD inicial: `84ba53baf docs(scraping): document Supabase pilot publish for recovered properties`

## Objetivo

Validar visualmente en frontend/local las 38 propiedades publicadas en ETAPA 5D, sin modificar codigo, `.env`, DB ni Supabase.

Ids auditados:

```text
81645,81646,81647,81648,81649,81650,81651,81652,81653,81654,81781,81782,81814,81815,81816,81817,81818,81819,81821,81823,81824,81825,81826,81827,81828,81829,81830,81831,81832,81833,81834,81835,81836,81837,81838,81839,81840,81841
```

## Preflight

- Branch confirmada: `fix/scraping-diagnostics-batch`.
- HEAD confirmado: `84ba53baf` o posterior.
- No habia procesos `node/next/python` activos al inicio.
- No habia cambios staged.
- Working tree seguia sucio con cambios no relacionados ya inventariados.

## Datos esperados desde DB/Supabase

Lecturas read-only contra Internal DB, `propiedades` y `v_propiedades_frontend_mapa`:

| check | resultado |
| --- | ---: |
| staging IDs del archivo | 38 |
| filas internal DB | 38 |
| propiedades Supabase por `hash_dedup` | 38 |
| filas en `v_propiedades_frontend_mapa` | 38 |
| `publish_queue.status=done` | 38 |
| `propiedades_staging.status=published` | 38 |
| `estado=activo` en vista/propiedades | 38 |
| campos titulo/precio/moneda/coords/url/inmobiliaria presentes | 38 |
| imagenes reales faltantes | 0 |
| imagenes min/max/total | 3 / 10 / 272 |

Distribucion:

| grupo | count |
| --- | ---: |
| Tandil / Buenos Aires | 36 |
| Mendoza / Mendoza | 2 |
| `pagliaropropiedades.com.ar` | 26 |
| `svestudioinmobiliario.com.ar` | 10 |
| `inmobiliariamendocasa.com.ar` | 2 |

Nota: las 10 propiedades de `svestudioinmobiliario.com.ar` aparecen en la vista con `inmobiliaria_nombre = null`; el frontend mappea eso como fallback visual de agencia.

## Validacion externa de URLs e imagenes

Checks read-only HTTP sobre las 38:

| check | resultado |
| --- | ---: |
| coordenadas dentro de zona esperada | 38 / 38 |
| primera imagen accesible HTTP 200 | 38 / 38 |
| URL fuente accesible HTTP 200 | 38 / 38 |

No se detectaron problemas de datos publicados, imagenes, precios, titulos, URLs ni ubicacion en la fuente de datos.

## Validacion frontend local

Se levanto `npm run dev -- --hostname 127.0.0.1 --port 3000` sin editar archivos. La home respondio HTTP 200.

Resultado visual:

- La home renderizo `Datos demo`, no `Datos reales`.
- La home mostro `4 propiedades activas`, no las 38 publicadas.
- El mapa/listado visible correspondio a mock data.
- Los titulos de las 38 publicadas no aparecieron en el DOM de la home.
- La vista `/debug-supabase` respondio con error: `canceling statement due to statement timeout`.

Capturas generadas:

- `reports/scraping_runs/import_controlado_20260608/etapa6a_home_desktop.png`
- `reports/scraping_runs/import_controlado_20260608/etapa6a_debug_supabase_timeout.png`

## Diagnostico

Las 38 propiedades estan publicadas, activas y presentes en `v_propiedades_frontend_mapa`, pero el frontend local no logra consumir la vista dentro del tiempo disponible. Al fallar la consulta, la home cae al fallback de mock data. Por eso la validacion visual real de las 38 en mapa/listado queda bloqueada en frontend/local.

La evidencia apunta a timeout de consulta sobre `v_propiedades_frontend_mapa`, no a problema de publicacion de las 38.

## Problemas visuales detectados

| area | resultado |
| --- | --- |
| carga home | OK HTTP 200 |
| origen de datos home | NOK: mock data |
| cantidad visible | NOK: 4 demo, no 38 publicadas |
| mapa/pines | NOK para el objetivo: muestra demo, no las 38 |
| listado/cards | NOK para el objetivo: muestra demo, no las 38 |
| imagenes 38 | No validables visualmente en UI; URLs externas OK 38/38 |
| precios/titulos 38 | No validables visualmente en UI; datos Supabase OK 38/38 |
| ubicacion 38 | No validable visualmente en UI; coords DB OK 38/38 |

## Recomendacion

Frenar nuevas publicaciones hasta resolver la lectura frontend de `v_propiedades_frontend_mapa` o ajustar la estrategia de carga para que no timeout. Luego repetir ETAPA 6A visual con la home en `Datos reales` y confirmar mapa/listado sobre las 38 publicadas.

No conviene publicar mas propiedades antes de esa validacion visual real.

## Guardrails cumplidos

- No git push.
- No frontend modificado.
- No `.env` modificado.
- No cambios de codigo.
- No Supabase writes.
- No `publish_to_supabase`.
- No import.
- No geocoding.
- No publish_queue.
- No cleanup/borrado.
- Solo lecturas DB/Supabase y validacion local.
