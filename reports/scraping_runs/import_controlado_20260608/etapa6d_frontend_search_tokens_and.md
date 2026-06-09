# ETAPA 6D - Buscador multi-palabra con tokens AND

Fecha: 2026-06-09
Branch raiz: `fix/scraping-diagnostics-batch`
HEAD raiz inicial: `229448c521 docs(frontend): validate real pilot properties in UI`
HEAD frontend inicial: `7477a6b fix(frontend): avoid Supabase timeout when loading map properties`

## Objetivo

Modificar el buscador frontend para que las busquedas multi-palabra funcionen por tokens AND, sin tocar DB, Supabase ni `.env`.

## Causa raiz

La busqueda libre normalizaba todo el query y luego hacia match por frase completa:

```ts
return haystack.includes(query);
```

Por eso `Maipu` funcionaba, pero `Maipu Mendoza` fallaba si la frase exacta no aparecia contigua en el texto buscable.

## Archivo modificado

- `frontend/src/components/property/PropertyExplorer.tsx`

## Logica anterior

- Normalizaba lowercase/acentos.
- Armaba un `haystack` con titulo, descripcion, direccion, barrio, ciudad, provincia e inmobiliaria.
- Buscaba el query completo como substring.

## Logica nueva

- Normaliza lowercase/acentos.
- Convierte separadores y puntuacion a espacios.
- Divide el query normalizado en tokens.
- Exige que todos los tokens aparezcan en el `haystack`, aunque esten en campos distintos.
- Suma `propertyType` y `operation` al conjunto buscable.

Ejemplo:

```text
query: "Maipu Mendoza"
token "maipu"   -> titulo/direccion
token "mendoza" -> ciudad/provincia
resultado       -> match
```

## Validacion local

Comandos ejecutados:

```powershell
npm run lint
npm run build
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Resultados:

| prueba | resultado |
| --- | --- |
| `npm run lint` | OK |
| `npm run build` | OK |
| home HTTP | 200 |
| `Datos reales` | si |
| `Datos demo` | no |
| `Maipu` | OK, encuentra Mendocasa |
| `Mendoza` | OK, encuentra Mendocasa |
| `Maipu Mendoza` | OK, encuentra 2 Mendocasa |
| `Garibaldi` | OK, encuentra Pagliaro |
| `Tandil` | OK, encuentra Tandil |
| `Garibaldi Tandil` | OK, encuentra 2 Pagliaro |
| `GALERIA LOS PUENTES` | OK, encuentra SV Estudio |
| `zzzinexistente 12345` | OK, muestra sin resultados |
| filtro `Ubicacion` | OK, sigue abriendo y mantiene datos reales |

Captura:

- `reports/scraping_runs/import_controlado_20260608/etapa6d_search_tokens_and.png`

Resultado JSON auxiliar no commiteado:

- `reports/scraping_runs/import_controlado_20260608/etapa6d_search_validation.json`

## Riesgos

- Busquedas con tokens muy genericos, como `venta casa`, pueden devolver muchos resultados porque ambos tokens son comunes.
- El match sigue siendo substring, no ranking semantico; es suficiente para este fix y conserva la busqueda simple.
- No se cambio paginacion, sort, filtros ni carga Supabase.

## Recomendacion

Fix aprobado. Se puede repetir QA visual rapido en una etapa posterior o avanzar con cautela al siguiente piloto. Para una etapa frontend futura, se podria mejorar ranking de resultados por cantidad/campo de tokens coincidentes.

## Guardrails cumplidos

- No git push.
- No Supabase writes.
- No `publish_to_supabase`.
- No publish_queue.
- No import.
- No geocoding.
- No cambios de schema.
- No `.env` modificado.
- No nuevas publicaciones.
- No cleanup/borrado.
