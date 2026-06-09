# ETAPA 7B - Auditoría mapeo inmobiliaria e imagen principal

Fecha: 2026-06-09

## Resultado general

Scope auditado: 41 propiedades publicadas del piloto.

- 38 limpias de ETAPA 5D.
- 3 soft-warning de ETAPA 7A.
- Supabase `propiedades`: 41/41 encontradas.
- Vista `v_propiedades_frontend_mapa`: 41/41 encontradas.
- No se publicaron nuevas propiedades.
- No se ejecutó `publish_to_supabase`.
- No se ejecutó `publish_queue`.
- No se hicieron imports, geocoding, schema changes ni cleanup.

Se aplicó un fix mínimo de frontend en `frontend/src/lib/property-mapper.ts` para mejorar la visualización:

- agencia visible por dominio fuente conocido;
- filtrado de logos/branding antes de elegir imágenes para cards.

## Auditoría inmobiliaria

Distribución del scope por dominio fuente:

| Dominio | Propiedades |
|---|---:|
| `pagliaropropiedades.com.ar` | 29 |
| `svestudioinmobiliario.com.ar` | 10 |
| `inmobiliariamendocasa.com.ar` | 2 |

IDs de inmobiliaria publicados:

| Dominio | inmobiliaria_id en staging | inmobiliaria_id en Supabase | Nombre visible antes |
|---|---:|---:|---|
| Pagliaro | 4418 | 4418 | Re/Max Jardin |
| SV Estudio | 6335 | 6335 | NULL |
| Mendocasa | 3532 | 3532 | Agostina Garofalo Bienes Raices |

Evidencia relevante:

- `publish_to_supabase.py` copia `inmobiliaria_id` desde `propiedades_staging` hacia Supabase sin remapearlo.
- La tabla REST `inmobiliarias_main` devuelve los nombres correctos para los IDs del piloto:
  - 4418: Juan I. Pagliaro Propiedades.
  - 6335: SV Inmobiliaria.
  - 3532: INMOBILIARIA & GESTORIA MENDOCASA LAVALLE.
- Sin embargo, `v_propiedades_frontend_mapa` devuelve:
  - 29 Pagliaro como `Re/Max Jardin`.
  - 10 SV como `NULL`.
  - 2 Mendocasa como `Agostina Garofalo Bienes Raices`.

Conclusión:

El problema visible no está en el `inmobiliaria_id` publicado en `propiedades` para estos 41 registros. La evidencia apunta a la definición/resolución de `v_propiedades_frontend_mapa` o a una tabla auxiliar distinta a `inmobiliarias_main`. Desde el acceso REST disponible no se pudo leer la definición SQL de la vista, por lo que no se aplicó ningún fix de datos ni SQL.

## Fix aplicado para agencia visible

Archivo modificado:

- `frontend/src/lib/property-mapper.ts`

Cambio:

- Se agregó un mapa acotado de dominios fuente conocidos:
  - `pagliaropropiedades.com.ar` -> `Juan I. Pagliaro Propiedades`
  - `svestudioinmobiliario.com.ar` -> `SV Inmobiliaria`
  - `inmobiliariamendocasa.com.ar` -> `Mendocasa Lavalle`
- El mapper usa ese nombre por dominio antes que `inmobiliaria_nombre` de la vista.
- Para dominios no conocidos, mantiene el comportamiento anterior.

Validación estática post-fix:

| Agencia visible mapeada | Propiedades |
|---|---:|
| Juan I. Pagliaro Propiedades | 29 |
| SV Inmobiliaria | 10 |
| Mendocasa Lavalle | 2 |

## Auditoría imagen principal

Hallazgos antes del fix:

- 39/41 propiedades tenían como `imagen_principal_real` de la vista un asset con apariencia de logo/branding.
- 29/29 Pagliaro usaban `https://www.pagliaropropiedades.com.ar/imgs/inmobiliaria-pagliaro-tandil.png`.
- 10/10 SV usaban `https://www.svestudioinmobiliario.com.ar/imgs/inmobiliaria-sv-tandil.png`.
- Las 2 Mendocasa no presentaron este problema.
- En muchos casos había fotos reales alternativas en el array `imagenes`.

Causa raíz probable:

- El pipeline publica el array `imagenes` en el orden capturado.
- La vista expone `imagen_principal_real` desde el primer asset que considera válido, pero no filtra logos específicos de estas inmobiliarias.
- El mapper frontend ya filtraba placeholders/tours/iconos genéricos, pero no patrones de branding como `/imgs/inmobiliaria`, `inmobiliaria-`, `mascara-galeria`, `rounded-cds`, `footer` o `logo`.

## Fix aplicado para imagen principal

Archivo modificado:

- `frontend/src/lib/property-mapper.ts`

Cambio:

- Se ampliaron los patrones bloqueados de imagen para evitar assets de branding:
  - `/imgs/inmobiliaria`
  - `inmobiliaria-`
  - `mascara-galeria`
  - `rounded-cds`
  - `footer`
  - `logo`
- `buildImages()` ya arma imágenes desde `imagen_principal_real` + `imagenes`; con los nuevos filtros, salta logos y conserva la primera foto real disponible.

Validación estática post-fix:

| Métrica | Resultado |
|---|---:|
| Principales de vista filtradas como branding | 39 |
| Propiedades con imagen real usable después del mapper | 36 |
| Propiedades sin imagen real usable después del mapper | 5 |

Las 5 sin imagen real usable son de `svestudioinmobiliario.com.ar`: al quitar el logo, no queda una alternativa no-branding en el array. No se inventó imagen ni se hizo corrección de datos.

## Validación técnica

Comandos ejecutados:

```powershell
npm run lint
npm run build
```

Resultados:

- `npm run lint`: OK.
- `npm run build`: OK.
- Build Next.js compiló correctamente.

No se levantó frontend local ni se hicieron capturas en esta etapa.

## Riesgos

- La causa raíz de la agencia visible sigue viva en `v_propiedades_frontend_mapa` o en una tabla auxiliar usada por esa vista. El fix frontend corrige la experiencia para dominios conocidos, pero no reemplaza un arreglo SQL/datos maestros.
- Las 5 SV sin foto real después del filtrado deben revisarse en scraper/pipeline antes de publicar más de ese dominio.
- Si aparecen nuevos dominios con el mismo problema, el mapper no debe crecer indefinidamente con excepciones; conviene arreglar la fuente de datos o la vista.

## Recomendación antes de las 43 warning fuerte

Frenar publicación de las 43 con warning fuerte hasta resolver o decidir explícitamente:

1. Arreglo de vista/datos maestros para que `inmobiliaria_nombre` venga de `inmobiliarias_main` o una fuente canónica correcta.
2. Limpieza de imágenes en pipeline antes de publicar: remover logos/branding o reordenar `imagenes` para dejar primero una foto real.
3. Reauditar un subconjunto chico posterior al fix de datos/vista, no un batch masivo.
