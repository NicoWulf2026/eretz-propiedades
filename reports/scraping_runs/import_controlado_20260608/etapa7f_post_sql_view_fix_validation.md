# ETAPA 7F - Validacion post-fix SQL de v_propiedades_frontend_mapa

Fecha: 2026-06-09

## Objetivo

Cerrar la validacion posterior al fix SQL aplicado manualmente en Supabase sobre `public.v_propiedades_frontend_mapa`, verificando que el frontend local consume datos reales con nombres canonicos de inmobiliaria y sin timeout.

## SQL aplicado manualmente

El cambio aplicado fuera de Codex fue el fix preparado en ETAPA 7E:

```sql
LEFT JOIN inmobiliarias_scraping i ON i.id = p.inmobiliaria_id
```

reemplazado por:

```sql
LEFT JOIN inmobiliarias_main i ON i.id = p.inmobiliaria_id
```

No se modificaron columnas, orden de columnas, filtros ni logica de `imagen_principal_real` / `tiene_imagen_real`.

## Validacion DB read-only

Validaciones ejecutadas solo por lectura via API Supabase/PostgREST.

| Check | Resultado |
| --- | --- |
| Total filas en vista | 41.271 |
| Columnas de la vista | 51 |
| Orden de columnas esperado | OK |
| `imagen_principal_real` presente | OK |
| `tiene_imagen_real` presente | OK |
| Piloto visible | 41/41 |
| Duplicados por `id` | 0 |

Nota: una primera lectura paginada sin `order=id.asc` produjo falsos positivos de duplicados por inestabilidad de paginacion. Se repitio la validacion con orden explicito sobre las 41.271 filas y checks exactos por ID: resultado final, 0 duplicados.

### Nombres del piloto

| Dominio | `inmobiliaria_nombre` en vista | Total |
| --- | --- | ---: |
| mendocasa | INMOBILIARIA & GESTORIA MENDOCASA LAVALLE | 2 |
| pagliaro | Juan I. Pagliaro Propiedades | 29 |
| sv | SV Inmobiliaria | 10 |

Resultado: el problema raiz de nombres visibles incorrectos/null quedo corregido en la vista.

## Validacion frontend local

Frontend levantado localmente en modo read-only y luego apagado.

| Check | Resultado |
| --- | --- |
| Home `/` | HTTP 200 |
| Fuente de datos | Datos reales |
| Mock/demo data | No aparece |
| Timeout Supabase | No aparece |
| `/debug-supabase` | HTTP 200, sin timeout |
| Cards/listado renderizados | OK |
| Nombre Pagliaro visible | OK |
| Nombre SV visible | OK |
| Nombre Mendocasa visible | OK |

Validaciones de busqueda multi-palabra contra datos reales del piloto:

| Busqueda | Resultado |
| --- | --- |
| `Garibaldi Tandil` | 2 matches Pagliaro, incluyendo `Casas en Venta - Garibaldi al 700` |
| `GALERIA LOS PUENTES` | 1 match SV, `Locales en Venta - GALERIA LOS PUENTES...` |
| `Maipu Mendoza` | 2 matches Mendocasa |

Filtro basico de operacion: las 41 propiedades del piloto matchean `venta` en la vista.

No se generaron capturas nuevas: la validacion se realizo por HTTP local renderizado y datos reales de Supabase. Playwright no estaba instalado en este workspace, por lo que no se agrego ninguna dependencia ni se ejecuto automatizacion visual con navegador.

## Lint y build

Ejecutado en `frontend/`:

```bash
npm run lint
npm run build
```

Resultado: ambos OK. Next.js compilo correctamente las rutas `/`, `/_not-found` y `/debug-supabase`.

## Riesgos restantes

- La logica SQL de `imagen_principal_real` sigue siendo la misma que antes del fix; ETAPA 7B/7C ya mitigaron visualmente y en pipeline futuro el problema de logos/branding como primera imagen.
- La validacion interactiva con navegador no se ejecuto por falta de Playwright instalado; no se instalo nada para respetar el alcance read-only/cierre.
- Antes de revisar las 43 con warning fuerte conviene hacer un nuevo dry-run de calidad con la vista ya corregida y el pipeline de imagenes de ETAPA 7C.

## Recomendacion

Dar por cerrado el fix raiz de `inmobiliaria_nombre` en `v_propiedades_frontend_mapa`. Proximo paso recomendado: ETAPA 7G de auditoria/dry-run de las 43 warning fuerte, sin publicar, usando la vista canonica ya corregida y el ordenamiento/filtro de imagenes del pipeline.
