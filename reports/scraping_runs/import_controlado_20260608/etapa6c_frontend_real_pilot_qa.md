# ETAPA 6C - QA visual real del piloto publicado

Fecha: 2026-06-09
Branch raiz: `fix/scraping-diagnostics-batch`
HEAD raiz inicial: `992e06dc61 fix(frontend): avoid Supabase timeout when loading map properties`
HEAD frontend inicial: `7477a6b fix(frontend): avoid Supabase timeout when loading map properties`

## Objetivo

Validar visualmente la experiencia local real con el lote piloto de 38 propiedades ya publicadas, sin modificar frontend, `.env`, DB ni Supabase.

## Preflight

- Rama raiz confirmada: `fix/scraping-diagnostics-batch`.
- HEAD raiz confirmado: `992e06dc61`.
- HEAD frontend confirmado: `7477a6b`.
- No habia procesos `node/next/python` activos al inicio.
- No habia cambios staged.
- El repo raiz y el repo frontend siguen con cambios no relacionados previos; no se mezclaron en esta etapa.

## Frontend local

Se levanto:

```powershell
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Resultado:

| check | resultado |
| --- | --- |
| home HTTP | 200 |
| `Datos reales` | si |
| `Datos demo` | no |
| contador home | `225 avisos activos` |
| contador listado | `225 propiedades activas` |
| mapa | carga |
| listado/cards | carga |
| imagenes visibles iniciales | 29 |
| links fuente visibles iniciales | 24 |
| dev server apagado al final | si |

## QA visual basico

| area | resultado |
| --- | --- |
| mapa carga | OK |
| listado carga | OK |
| pines/clusters aparecen | OK |
| cards aparecen | OK |
| imagenes cargan | OK tecnicamente; hallazgo visual en SV Estudio: logo/branding como imagen principal |
| precios/moneda | OK, formato `USD xx.xxx` |
| ubicacion | OK, Mendoza/Tandil visibles |
| links fuente | OK: 8 links visibles muestreados devolvieron HTTP 200 |
| contador | OK: 225 total, 24 visibles, 200 relevantes en mapa |
| titulos basura visibles | no detectados en el bloque piloto visible |
| layout desktop | OK, sin roturas visibles |
| buscador | OK con terminos simples; hallazgo con busqueda multi-palabra |
| filtro ubicacion | OK: abre panel y mantiene datos reales |

## QA especifico piloto

### Mendocasa / Maipu / Mendoza

Verificado en home y busqueda `Maipu`:

- `Venta Terreno calle Maipu - Ciudad Mendoza`
- `Venta Deposito en calle Maipu 235 - Ciudad Mendoza`
- Inmobiliaria visible: `Agostina Garofalo Bienes Raices`
- Precios visibles: `USD 60.000`, `USD 610.000`
- Ubicacion visible: `Mendoza`
- Imagen visible: si, pero la imagen principal se ve como logo/branding de SV Studio, no como foto clara de la propiedad.
- Links fuente visibles y HTTP 200: si

### Pagliaro / Tandil

Verificado en home y busqueda `Garibaldi`:

- `Casas en Venta - Garibaldi y Alem`
- `Casas en Venta - Garibaldi al 700`
- Inmobiliaria visible: `Re/Max Jardin`
- Ubicacion visible: `Tandil, Buenos Aires`
- Precio/moneda visibles: si
- Imagen visible: si
- Links fuente visibles y HTTP 200: si

### SV Estudio / Tandil

Verificado por busqueda `GALERIA LOS PUENTES`:

- `Locales en Venta - GALERIA LOS PUENTES- 9 DE JULIO ENTRE PJE FOURNIER`
- Ubicacion visible: `Tandil`
- Precio visible: `USD 34.000`
- Imagen visible: si
- Link fuente visible: `svestudioinmobiliario.com.ar`
- Inmobiliaria visible: fallback `Inmobiliaria no especificada`

El fallback de inmobiliaria es aceptable para este piloto porque la vista trae `inmobiliaria_nombre = null` para ese grupo. La imagen principal tipo logo si debe revisarse antes de escalar mas publicaciones de SV.

## Buscador y filtros

Resultados:

| prueba | resultado |
| --- | --- |
| buscar `Maipu` | OK, 3 resultados, incluye 2 Mendocasa |
| buscar `Garibaldi` | OK, 2 resultados Pagliaro |
| buscar `GALERIA LOS PUENTES` | OK, resultado SV Estudio |
| abrir filtro `Ubicacion` | OK, muestra provincias/ciudades/barrios |

Hallazgo:

- Las busquedas compuestas `Maipu Mendoza` y `Garibaldi Tandil` devolvieron `Sin resultados`.
- Causa probable: el buscador hace match por frase normalizada completa, no por tokens independientes.
- No se modifico frontend en esta etapa porque la regla pedia no tocar salvo bug minimo justificado. Queda recomendado como ajuste UX separado.

## Capturas generadas

- `reports/scraping_runs/import_controlado_20260608/etapa6c_home_real_pilot.png`
- `reports/scraping_runs/import_controlado_20260608/etapa6c_search_mendocasa_maipu.png`
- `reports/scraping_runs/import_controlado_20260608/etapa6c_search_pagliaro_garibaldi.png`
- `reports/scraping_runs/import_controlado_20260608/etapa6c_search_sv_estudio.png`
- `reports/scraping_runs/import_controlado_20260608/etapa6c_filter_location_open.png`
- `reports/scraping_runs/import_controlado_20260608/etapa6c_debug_supabase_ok.png`

## Resultado general

QA visual real aprobado para el lote piloto. El frontend ya consume datos reales, el mapa/listado cargan, las cards del piloto se ven con imagen/precio/moneda/ubicacion, y los links fuente visibles funcionan.

## Problemas detectados

| problema | severidad | recomendacion |
| --- | --- | --- |
| Busqueda multi-palabra exige frase exacta | media | Cambiar busqueda a match por tokens AND en etapa frontend separada |
| SV Estudio muestra fallback de inmobiliaria | baja | Completar nombre de inmobiliaria en datos/vista si se desea marca correcta |
| SV Estudio usa logo/branding como imagen principal | media | Revisar limpieza/seleccion de imagenes antes de publicar mas SV |

## Recomendacion

Se puede avanzar con cautela a revisar las 3 soft-warning o preparar un siguiente piloto pequeno. Antes de publicar masivamente, conviene resolver el buscador multi-palabra y revisar la seleccion de imagen principal para SV Estudio.

## Guardrails cumplidos

- No git push.
- No Supabase writes.
- No `publish_to_supabase`.
- No publish_queue.
- No import.
- No geocoding.
- No cambios de schema.
- No `.env` modificado.
- No frontend modificado.
- No publicaciones nuevas.
- No cleanup/borrado.
