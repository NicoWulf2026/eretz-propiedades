# ETAPA 7H - Angelina Martinez: diagnostico de fotos/detalle sin publicar

Fecha: 2026-06-09

## Objetivo

Diagnosticar por que las 43 propiedades warning fuerte de Inmobiliaria Angelina Martinez llegan a `propiedades_raw` / `propiedades_staging` sin imagenes, probar una muestra chica y decidir si existe un fix seguro de extractor antes de publicar.

## Reglas operativas cumplidas

- No se ejecuto `publish_to_supabase`.
- No se ejecuto `publish_queue`.
- No hubo import a DB.
- No hubo geocoding.
- No hubo writes DB/Supabase.
- No se toco frontend ni `.env`.
- No se publicaron propiedades.
- No se tocaron las 41 ya publicadas.

## Muestra auditada

Fuente: `staging_ids_warning_fuerte_43_etapa7g.csv`.

| staging_id | raw_id | tipo muestra | titulo staging | direccion | precio | moneda |
| ---: | ---: | --- | --- | --- | ---: | --- |
| 81700 | 82190 | departamento | Departamento en Alquiler | LOS OLMOS 725 | 280000 | ARS |
| 81705 | 82195 | casa | Casa en Alquiler | LINIERS 139 | 350000 | ARS |
| 81706 | 82196 | local | Local en Alquiler | ITALIA 62 | 500000 | ARS |
| 81763 | 82253 | titulo debil | Propiedad en | CENTENARIO 95 | 70000 | ARS |
| 81780 | 82270 | titulo debil | Local en | AV. ALVEAR OESTE 750 | 110000 | ARS |

Archivo auxiliar: `angelina_sample_urls_etapa7h.csv`.

## Diagnostico tecnico

Se probaron las fichas de detalle con `requests` + BeautifulSoup y con `extraer_imagenes()` actual. Para 2 casos representativos tambien se uso Playwright headless, solo lectura, para descartar hidratacion por JavaScript.

Resultado:

| Check | Requests | Playwright |
| --- | ---: | ---: |
| URLs HTTP 200 | 5/5 | 2/2 |
| Imagenes reales detectadas por extractor | 0/5 | 0/2 |
| `img` reales de propiedad en DOM | 0/5 | 0/2 |
| `og:image` / `twitter:image` | 0/5 | no aplica |
| JSON-LD / scripts con fotos | 0/5 | no aplica |
| Links directos a imagenes de propiedad | 0/5 | no aplica |
| Carrusel `#carouselPropiedad` con contenido | 0/5 | 0/2 |

Evidencia principal:

- Las fichas tienen `#carouselPropiedad`, pero el contenedor `.carousel-inner` viene vacio.
- Los unicos `img` server-side son el logo `isologotipo_angelina.png` y, en algunos casos, un mapa estatico de Google.
- Playwright no agrega fotos luego de `networkidle`; solo aparecen logo, mapa y fondos decorativos.
- El listado `propiedades.php` tambien trae solo logo y links a detalle; no trae thumbnails de propiedad.
- `extraer_imagenes()` descarta correctamente logo/mapa y devuelve 0 fotos reales.

## Causa raiz

No se encontro evidencia de fotos de propiedad expuestas en HTML, atributos lazy, `srcset`, `data-*`, JSON-LD, meta tags, scripts, background images utiles ni DOM renderizado por navegador. El problema no es un selector roto del scraper actual: para estas fichas, la fuente publica consultada no entrega fotos reales de propiedad.

Tambien se confirmo que varias fichas tienen titulos genericos porque el propio HTML/title de Angelina es generico, por ejemplo `Departamento en Alquiler`, `Propiedad en` o `Local en`.

## Fix aplicado

No se aplico fix de codigo. Cambiar el extractor para aceptar imagenes decorativas seria peor: publicaria logo, favicon, mapa o fondos como foto principal. El comportamiento actual de `extraer_imagenes()` y `clean_property_images()` es correcto para esta evidencia.

## Resultados antes/despues

| staging_id | imagenes staging/raw antes | requests despues | Playwright despues | decision |
| ---: | ---: | ---: | ---: | --- |
| 81700 | 0 | 0 | 0 | sin foto recuperable |
| 81705 | 0 | 0 | no corrido | sin foto recuperable |
| 81706 | 0 | 0 | no corrido | sin foto recuperable |
| 81763 | 0 | 0 | 0 | sin foto recuperable |
| 81780 | 0 | 0 | no corrido | sin foto recuperable |

Archivo auxiliar liviano: `angelina_sample_results_etapa7h.json`.

## Tests

Ejecutados:

```powershell
python -B -m unittest scripts.test_image_quality
python -B -m py_compile scraper/scraper_propiedades.py scripts/image_quality.py
```

Resultado:

- `scripts.test_image_quality`: OK, 6 tests.
- `py_compile`: OK.

## Riesgos

- Publicar estas 43 como estan generaria propiedades sin imagen real y con titulos/campos blandos debiles.
- Si se fuerza una imagen desde el HTML actual, se corre alto riesgo de publicar branding, mapas o assets decorativos.
- La unica via segura para convertirlas en candidatas es obtener fotos reales desde otra fuente confiable, un endpoint no documentado del CMS, contacto/proveedor, o un recrawl posterior si Angelina corrige las fichas.

## Recomendacion para ETAPA 7I

No publicar las 43. No hacer publish_queue dry-run todavia.

Proxima etapa recomendada:

1. Hacer diagnostico de CMS Ubiquo/Angelina para encontrar si existe endpoint administrativo/publico de fotos por `id`.
2. Si aparece endpoint con fotos reales, implementar extractor especifico y probar sobre 5-10 IDs.
3. Si no aparece endpoint, mantener estas 43 fuera de publicacion o publicarlas solo con una politica explicita de "sin imagen" aprobada por producto.
4. En paralelo, si se decide rescatar datos blandos, enriquecer ciudad/provincia desde URL/coords y titulo desde direccion, pero no mezclar eso con publicacion.
