# ETAPA 7G - Auditoria/dry-run de 43 warning fuerte sin publicar

Fecha: 2026-06-09

## Alcance y reglas

Auditoria read-only de las 43 propiedades con warning fuerte excluidas en ETAPA 5B. No se ejecuto `publish_queue --commit`, no se ejecuto `publish_to_supabase`, no se hicieron writes DB/Supabase, no se publico nada y no se tocaron las propiedades ya publicadas.

## Reconstruccion del scope

Fuente principal: `etapa5b_publish_queue_commit_clean_summary.md`, seccion `IDs warning fuerte`. Se cruzo contra `staging_ids_publishqueue_candidates_etapa5a.csv` para recuperar warnings originales.

- IDs reconstruidos: 43.
- Filas encontradas en `propiedades_staging`: 43.
- Overlap con 38 limpias publicadas: [].
- Overlap con 3 soft-warning publicadas: [].
- Estados staging: {'staging': 43}.
- Geocoding: {'done': 43}.
- Filas existentes en `publish_queue` para estas 43: 0.
- Existentes en Supabase por hash/url: 0.
- Duplicados internos por hash/url: 0.
- URLs fuente confirmadas OK: 43/43.

## Resumen por categoria

| Categoria | Total | IDs |
| --- | ---: | --- |
| `candidata_piloto` | 0 | - |
| `corregible_minima` | 0 | - |
| `requiere_rescrape_o_detalle` | 43 | 81700,81705,81706,81712,81719,81720,81721,81724,81727,81728,81733,81734,81735,81736,81737,81739,81740,81742,81743,81745,81746,81747,81749,81752,81753,81754,81755,81757,81758,81759,81760,81761,81762,81763,81765,81767,81769,81773,81774,81775,81776,81778,81780 |
| `descartar_por_calidad` | 0 | - |
| `investigar_manual` | 0 | - |

## Warnings

Warnings originales desde ETAPA 5A/5B:

| Warning original | Total |
| --- | ---: |
| `missing_city_or_province_but_coords_present` | 43 |
| `missing_images` | 43 |
| `weak_title` | 5 |

Warnings actualizados con reglas de ETAPA 7G:

| Warning actualizado | Total |
| --- | ---: |
| `generic_title` | 43 |
| `missing_city_or_province_but_coords_present` | 43 |
| `missing_images_after_filter` | 43 |

## Impacto del nuevo filtro de imagenes

- Imagenes originales en staging: 0 en 43/43.
- Imagenes originales en raw: 0 en 43/43.
- Imagenes reales despues de `normalize_property_images()`: 0 en 43/43.
- Propiedades que quedarian sin imagen usable: 43/43.

Conclusion: el fix de ETAPA 7C funciona para filtrar/reordenar arrays existentes, pero no puede recuperar fotos cuando staging/raw ya vienen con array vacio. Estas 43 necesitan rescrape o extraccion de detalle/fotos antes de cualquier piloto.

## Simulacion de dry-run sin writes

No se ejecuto `build_publish_queue.py --dry-run` porque no hay candidatas limpias y ese script inserta en `publish_queue` dentro de una transaccion aunque luego haga rollback. Para respetar la regla `NO DB writes`, se hizo una simulacion read-only de elegibilidad/calidad.

- Candidatas limpias para piloto: 0.
- Filas que serian tecnicamente elegibles por `build_publish_queue` si se ignoraran imagenes/ciudad: 43.
- Resultado de calidad: 43/43 bloqueadas por falta de imagen usable despues del filtro; 43/43 tambien tienen ciudad/provincia faltante con coords presentes.
- Accion final: no-op/read-only, sin rollback necesario.

## Tabla individual

| staging_id | raw_id | inmobiliaria | titulo | precio | moneda | ciudad | provincia | direccion | lat | lon | score | imagenes->reales | URL | categoria | motivo |
| ---: | ---: | --- | --- | ---: | --- | --- | --- | --- | ---: | ---: | ---: | --- | --- | --- | --- |
| 81700 | 82190 | Inmobiliaria Angelina Martinez | Departamento en Alquiler | 280000 | ARS | NULL | NULL | LOS OLMOS 725 | -34.9883296 | -67.6764594 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81705 | 82195 | Inmobiliaria Angelina Martinez | Casa en Alquiler | 350000 | ARS | NULL | NULL | LINIERS 139 | -34.9795432 | -67.6844835 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81706 | 82196 | Inmobiliaria Angelina Martinez | Local en Alquiler | 500000 | ARS | NULL | NULL | ITALIA 62 | -34.9802043 | -67.6885147 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81712 | 82202 | Inmobiliaria Angelina Martinez | Local en Alquiler | 500000 | ARS | NULL | NULL | ITALIA 62 | -34.9802043 | -67.6885147 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81719 | 82209 | Inmobiliaria Angelina Martinez | Departamento en Alquiler | 230000 | ARS | NULL | NULL | GODOY CRUZ 37 | -34.9792437 | -67.6887205 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81720 | 82210 | Inmobiliaria Angelina Martinez | Casa en Alquiler | 300000 | ARS | NULL | NULL | PETERSEN 1116 | -34.9706556 | -67.7024635 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81721 | 82211 | Inmobiliaria Angelina Martinez | Departamento en Alquiler | 130000 | ARS | NULL | NULL | LAPRIDA 160 | -34.9799031 | -67.6867473 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81724 | 82214 | Inmobiliaria Angelina Martinez | Casa en Alquiler | 280000 | ARS | NULL | NULL | DE MAYO 543 | -34.9749701 | -67.6825383 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81727 | 82217 | Inmobiliaria Angelina Martinez | Departamento en Alquiler | 170000 | ARS | NULL | NULL | MITRE 776 | -34.9748041 | -67.699198 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81728 | 82218 | Inmobiliaria Angelina Martinez | Departamento en Alquiler | 127000 | ARS | NULL | NULL | MITRE 776 | -34.9748041 | -67.699198 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81733 | 82223 | Inmobiliaria Angelina Martinez | Departamento en Alquiler | 160000 | ARS | NULL | NULL | GODOY CRUZ 37 | -34.9792437 | -67.6887205 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81734 | 82224 | Inmobiliaria Angelina Martinez | Departamento en Alquiler | 180000 | ARS | NULL | NULL | LUIS PONCE 866 | -34.9712051 | -67.7003591 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81735 | 82225 | Inmobiliaria Angelina Martinez | Departamento en Alquiler | 200000 | ARS | NULL | NULL | AV. LIBERTADOR SUR 119 | -34.979437 | -67.6895598 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81736 | 82226 | Inmobiliaria Angelina Martinez | Departamento en Alquiler | 250000 | ARS | NULL | NULL | AV. LIBERTADOR SUR 119 | -34.979437 | -67.6895598 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81737 | 82227 | Inmobiliaria Angelina Martinez | Departamento en Alquiler | 250000 | ARS | NULL | NULL | AV. LIBERTADOR SUR 119 | -34.979437 | -67.6895598 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81739 | 82229 | Inmobiliaria Angelina Martinez | Departamento en Alquiler | 160000 | ARS | NULL | NULL | GODOY CRUZ 37 | -34.9792437 | -67.6887205 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81740 | 82230 | Inmobiliaria Angelina Martinez | Departamento en Alquiler | 140000 | ARS | NULL | NULL | AGUSTIN ALVAREZ 345 | -34.9741367 | -67.6995483 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81742 | 82232 | Inmobiliaria Angelina Martinez | Departamento en Alquiler | 130000 | ARS | NULL | NULL | Agustin Alvarez 345 | -34.9741367 | -67.6995483 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81743 | 82233 | Inmobiliaria Angelina Martinez | Departamento en Alquiler | 100000 | ARS | NULL | NULL | Agustin Alvarez 345 | -34.9741367 | -67.6995483 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81745 | 82235 | Inmobiliaria Angelina Martinez | Departamento en Alquiler | 140000 | ARS | NULL | NULL | Agustin Alvarez 345 | -34.9741367 | -67.6995483 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81746 | 82236 | Inmobiliaria Angelina Martinez | Casa en Alquiler | 140000 | ARS | NULL | NULL | MANUEL A SAEZ 316 | -34.9976597 | -67.650692 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81747 | 82237 | Inmobiliaria Angelina Martinez | Local en Alquiler | 100000 | ARS | NULL | NULL | BELGRANO 114 | -34.9767965 | -67.6908183 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81749 | 82239 | Inmobiliaria Angelina Martinez | Departamento en Alquiler | 70000 | ARS | NULL | NULL | AV. ALVEAR OESTE 750 | -34.978124 | -67.6989412 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81752 | 82242 | Inmobiliaria Angelina Martinez | Local en Alquiler | 60000 | ARS | NULL | NULL | AV. ALVEAR OESTE 795 | -34.9779297 | -67.6994141 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81753 | 82243 | Inmobiliaria Angelina Martinez | Local en Alquiler | 60000 | ARS | NULL | NULL | AV. ALVEAR OESTE 795 | -34.9779297 | -67.6994141 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81754 | 82244 | Inmobiliaria Angelina Martinez | Local en Alquiler | 60000 | ARS | NULL | NULL | AV. ALVEAR OESTE 795 | -34.9779297 | -67.6994141 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81755 | 82245 | Inmobiliaria Angelina Martinez | Local en Alquiler | 60000 | ARS | NULL | NULL | AV. ALVEAR OESTE 795 | -34.9779297 | -67.6994141 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81757 | 82247 | Inmobiliaria Angelina Martinez | Departamento en Alquiler | 55000 | ARS | NULL | NULL | brevedad. Enviar Mensaje Copyright 2026 | -34.9717092 | -67.6990996 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81758 | 82248 | Inmobiliaria Angelina Martinez | Casa en Alquiler | 60000 | ARS | NULL | NULL | ALVEAR OESTE 15 | -34.9778619 | -67.6897295 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81759 | 82249 | Inmobiliaria Angelina Martinez | Casa en Alquiler | 60000 | ARS | NULL | NULL | ECHEVERRIA 39 | -34.9862574 | -67.6703321 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81760 | 82250 | Inmobiliaria Angelina Martinez | Departamento en Alquiler | 55000 | ARS | NULL | NULL | PEDRO ESCUDE 183 | -34.979716 | -67.6804514 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81761 | 82251 | Inmobiliaria Angelina Martinez | Casa en Alquiler | 45000 | ARS | NULL | NULL | AGUSTIN ALVAREZ 699 | -34.9696147 | -67.6990721 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81762 | 82252 | Inmobiliaria Angelina Martinez | Local en Alquiler | 50000 | ARS | NULL | NULL | USPALLATA 956 | -34.9689951 | -67.7035949 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81763 | 82253 | Inmobiliaria Angelina Martinez | Propiedad en | 70000 | ARS | NULL | NULL | CENTENARIO 95 | -34.9965107 | -67.5118036 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81765 | 82255 | Inmobiliaria Angelina Martinez | Departamento en Alquiler | 51000 | ARS | NULL | NULL | brevedad. Enviar Mensaje Copyright 2026 | -34.9779882 | -67.6893858 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81767 | 82257 | Inmobiliaria Angelina Martinez | Casa en Alquiler | 50000 | ARS | NULL | NULL | MARTIN DE IRIGOYEN 216 | -34.9804883 | -67.6991261 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81769 | 82259 | Inmobiliaria Angelina Martinez | Casa en Alquiler | 40000 | ARS | NULL | NULL | PEDRO PASCUAL SEGURA 49 | -34.9965468 | -67.5097744 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81773 | 82263 | Inmobiliaria Angelina Martinez | Departamento en Alquiler | 37500 | ARS | NULL | NULL | PEDRO ESCUDE 183 | -34.979716 | -67.6804514 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81774 | 82264 | Inmobiliaria Angelina Martinez | Propiedad en | 67500 | ARS | NULL | NULL | JUAN PABLO I 235 | -34.9884479 | -67.6783015 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81775 | 82265 | Inmobiliaria Angelina Martinez | Propiedad en | 35000 | ARS | NULL | NULL | GODOY CRUZ 21 | -35.0013734 | -67.5031178 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81776 | 82266 | Inmobiliaria Angelina Martinez | Propiedad en | 49400 | ARS | NULL | NULL | EMILIO CIVIT 75 | -34.9709246 | -67.6980487 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81778 | 82268 | Inmobiliaria Angelina Martinez | Casa en | 25000 | ARS | NULL | NULL | HILARIO CUADROS 436 | -34.972896 | -67.7066283 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |
| 81780 | 82270 | Inmobiliaria Angelina Martinez | Local en | 110000 | ARS | NULL | NULL | AV. ALVEAR OESTE 750 | -34.9779706 | -67.698846 | 75 | 0->0 | HTTP 200 | `requiere_rescrape_o_detalle` | sin imagen usable en staging/raw; fuente responde y requiere recapturar detalle/fotos |

## Datos detallados por archivo

- `staging_ids_warning_fuerte_43_etapa7g.csv`: 43 IDs auditados.
- `staging_ids_candidata_piloto_etapa7g.csv`: 0 IDs.
- `staging_ids_corregible_minima_etapa7g.csv`: 0 IDs.
- `staging_ids_requiere_rescrape_etapa7g.csv`: 43 IDs.
- `staging_ids_descartar_calidad_etapa7g.csv`: 0 IDs.

## Riesgos

- Publicarlas tal como estan generaria cards sin imagen real y con ciudad/provincia faltante.
- Aunque las URLs fuente responden 200, el staging/raw actual no contiene fotos; el problema parece de extraccion/captura, no de orden de imagenes.
- Los titulos son genericos para la mayoria del bloque de Angelina; conviene enriquecer desde detalle o URL antes de publicar.

## Recomendacion proxima

No publicar ninguna de las 43 todavia. Abrir una etapa enfocada en Angelina Martinez para rescrape de detalle/fotos y enriquecimiento minimo de ciudad/provincia/titulo, con dry-run sobre un subconjunto chico. Recien despues reconstruir candidatas piloto y correr publish_queue dry-run read-only/rollback solo si se autoriza explicitamente.
