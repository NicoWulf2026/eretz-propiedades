# ERETZ Propiedades — MASTER PROGRESS

**Última actualización:** 2026-08-22 — misión de INGESTA DIRECTA en curso.

> Lo de más abajo (campaña Roomix, crosswalk, auditoría de webs) está cerrado y
> se conserva como historia. Lo que sigue es el estado vivo.

---

# ESTADO VIVO — INGESTA DIRECTA DESDE INMOBILIARIAS

## Dónde está todo

| Qué | Dónde |
|---|---|
| Repo | `D:\INMO CAPITAL\eretz-agency` — rama `feat/roomix-agency-coverage` |
| Pipeline ERETZ (se reusa) | `D:\INMO CAPITAL\Inmo-Capital-main` |
| Artefactos de agencias | `D:\INMO CAPITAL\ERETZ_AGENCY_DATA\` |
| Canary Tokko | `D:\INMO CAPITAL\TOKKO_CANARY\` |
| Rollout controlado | `D:\INMO CAPITAL\TOKKO_ROLLOUT_CTRL\` |
| Rollout completo | `D:\INMO CAPITAL\TOKKO_ROLLOUT_FULL\` |

Los datasets no viven en el repo y no deben moverse adentro.

## Universo (regenerar siempre del artefacto, no de este número)

Padrón canónico 6.597 · mapa tecnológico **2.330** fuentes.
TOKKO **920** · UNKNOWN 826 · WORDPRESS **336** · NEXTJS 87 · WASI 39 · LARAVEL 38.

## Arquitectura

`connectors/base.py` define la interfaz común: `discover` · `fetch_listing` ·
`normalize` · `resume` · `registrar` · `identify_deleted_or_inactive`. Todo
connector devuelve `PropiedadNormalizada`.

**Reuso, no copia.** La identidad viene de `scraper/models.py`
(`_compute_hash_dedup`, `_normalize_url_for_hash`) y los vocabularios `ALLOWED_*`.
El hash incluye `inmobiliaria_id`, así que dos agencias no colisionan por
construcción. Lo que no tiene columna va a `datos_extra JSONB`. Cero tablas nuevas.

Cortesía **por host** (1 pedido / 1,5 s) y concurrencia **entre hosts**: son
cosas distintas y no comparten cerrojo.

| Connector | Estado | Variantes |
|---|---|---|
| `tokko` | canary PASS · rollout controlado | `TFW_ESTANDAR`, `TFW_SIN_AJAX` |
| `wordpress` | construido · canary pendiente | `WORDPRESS_REST`, `_SITEMAP`, `_HTML` |

## Ya cerrado — no rehacer

Campaña Roomix · padrón canónico · directorio de webs · control de identidad en
hosts compartidos (223 fuentes removidas por adjudicación equivocada) · mapa
tecnológico de 2.330 · discovery Tokko (TFW_ESTANDAR 88,3 %) · canary Tokko
(paginación 1,000; 322 NUEVA → 322 SIN_CAMBIOS; 0 duplicados; 0 fotos ajenas).

## Bugs resueltos — no reintroducir (todos con test de regresión)

1. `RUTAS_LISTADO` con un byte de retroceso literal: no reconocía ningún listado.
2. Detector ciego a `href` relativos (`href="propiedades.php"`).
3. Identidad sin traducir `canonical_name` → `nombre_original`.
4. `UnicodeEncodeError` en slugs con acentos (19 % de las fichas).
5. `f"{None:>4}"` volteando una corrida entera.
6. Artefactos escritos solo al final: una excepción borraba lo ya procesado.
7. `hash()` de Python como identidad persistente — no es estable entre procesos.
8. Limitador de ritmo con cerrojo global: anulaba el paralelismo.

## La trampa de la paginación Tokko

La página lleva escrito el `$.ajax(...)` con todos los filtros y termina en `&p=`.
Se pagina poniendo el número ahí. Inventar `?page=2` devuelve **HTTP 200 con la
página uno otra vez**: se recogerían 20 de 299 propiedades sin un solo error.

## Bloqueos externos reales

| Bloqueo | Detalle | Impacto |
|---|---|---|
| `PROPERTY_WRITE_CREDENTIAL_PENDING` | **Verificado 2026-08-25.** No existe ninguna credencial para el rol que la escritura necesita. `SUPABASE_POOLER_DATABASE_URL` no esta ni en `.env` ni en el entorno. Lo unico que hay -`SUPABASE_DATABASE_URL` e `INTERNAL_DB_URL`- apunta al host **directo** (solo IPv6) con el usuario **`postgres`**, que es superusuario y esta explicitamente prohibido; ademas su password falla autenticacion. **No hay una sola referencia a `eretz_preview_ro` en ninguno de los dos repos.** No se rota nada, no se adivina host de pooler, no se toca service_role ni NEON ni owner. | Bloquea canary, escritura a `propiedades_raw`, raw->staging, staging->publish y el dedupe historico. **143.337 propiedades quedan listas y verificadas esperando la credencial.** |
| ~~`DB_WRITE_BLOCKED` (redaccion anterior)~~ | Verificado 2026-08-23: `SUPABASE_POOLER_DATABASE_URL` no existe en `.env` ni en el entorno. `SUPABASE_DATABASE_URL` resuelve **solo IPv6**, y desde esta red **la conexión SÍ llega**: el servidor contesta `FATAL: password authentication failed`. O sea el bloqueo es la credencial, no la red — lo anterior decía "IPv6 inalcanzable" y era incorrecto. | Sin canary de escritura ni carga a `propiedades_raw`. Todo lo demás sigue. |
| `SEARCH_API_COST` | Serper y Tavily sin créditos (400 / 432). Exa responde pero cobra **USD 0,0070/consulta**: ~6.032 entidades ≈ **USD 84**. | Búsqueda preparada, no ejecutada: requiere autorización de gasto. Sondeos: USD 0,014. |
| `NETWORK_ACCESS_BLOCKED` | `century21.com.ar` resuelve DNS pero HTTP/HTTPS hacen timeout. | 42 oficinas no auditables desde esta red. |

Ninguno detiene el resto.

## Validado a escala (codigo 1abb03ef37a1)

| | run 1 | run 2 |
|---|---|---|
| Tokko, 100 fuentes | 2.048 NUEVA | **2.048 SIN_CAMBIOS** |
| WordPress, 20 fuentes | 120 NUEVA | **120 SIN_CAMBIOS** |

Ambos reconcilian. 0 duplicados intra-fuente, 0 hash compartido entre agencias,
0 fotos ajenas, 0 errores. El barrido multiple llevo las fuentes con enumeracion
incompleta de 3 a 0 y recupero +1.589 propiedades sobre las mismas 100 fuentes.

### Idempotencia de Tokko — VALIDADA a escala completa (corrida 3)

| | corrida 2 (invalida) | corrida 3 (valida) |
|---|---|---|
| fuentes | 913/913 | 913/913, 798 OK |
| propiedades | 91.715 | 91.659 |
| SIN_CAMBIOS | 0 | **91.503 (99,83%)** |
| NUEVA | 91.715 | 99 |
| MODIFICADA | 0 | 57 |
| potential_inactive | 91.367 | 100 |
| duplicados intra-fuente | 0 | 0 |
| hash compartido entre agencias | 0 | 0 |
| reconcilia | si | si |

Auditado por categoria:

- **99 de 99 NUEVA** no estaban en la corrida 2: altas reales.
- **57 MODIFICADA, ninguna falsa.** Cambios en `extra` (23), fotos (21),
  descripcion (19), precio (10). La unica descripcion que solo estaba
  reordenada pertenecia a una ficha que ademas cambio precio y moneda, asi que
  el reordenamiento no aporto a la huella.
- **100 ausencias**: con el resguardo de comparabilidad, 87 cuentan y 13 no.

### Idempotencia de Tokko — como se arreglo

El baseline se reconstruyo con `scripts/rebuild_checkpoint_baseline.py` desde
`properties_run2.jsonl`, verificando 500/500 hashes por recalculo. Canary de 6
fuentes: **123/123 SIN_CAMBIOS**, 0 MODIFICADA, 0 potential_inactive.

Hicieron falta DOS arreglos, y el segundo solo se vio despues del primero:

1. el checkpoint mezclaba claves de dos formatos (abajo);
2. la huella de contenido no era estable. Tokko arma la lista de servicios sin
   orden fijo -"Cloaca Internet" / "Internet Cloaca"-, y como la descripcion
   entra en la huella, una propiedad sin tocar volvia MODIFICADA. Era el 2,4%:
   ~2.200 cambios falsos por corrida a escala completa. La huella ahora ignora
   el orden de la descripcion y de las fotos.

### La corrida 2 de Tokko NO es la prueba de idempotencia

Termino 913/913 con 91.715 propiedades y reconcilia, pero informa
`NUEVA: 91.715` y `potential_inactive: 91.367`. Ninguno de los dos numeros
significa lo que parece: **arranco 08-23 04:01 y el fix del formato de
checkpoint entro 08-23 07:44**, casi cuatro horas despues. Corrio sin el.

Se ve en el propio artefacto: `TOKKO_ROLLOUT_FULL/checkpoint.json` tiene 807
fuentes, ninguna con `esquema` ni `linea_base`, y sus `vistos` mezclan claves
numericas -de la corrida 1, formato viejo- con hashes de 32 -de la corrida 2-.
Al comparar hash contra id numerico nada coincide: todo figura NUEVA y todo el
inventario anterior figura ausente.

Los datos extraidos si sirven. Lo que no existe todavia es la prueba de
idempotencia de Tokko a escala completa. Para tenerla hay dos caminos:

- correr una 3 y una 4 (la 3 resetea a linea base, la 4 compara): dos corridas
  de ~7 h;
- o migrar el checkpoint una sola vez -tirar las claves numericas y las
  `ausencias` viejas, sellar `esquema: 2`- y que la corrida 3 sea la prueba.

La migracion no esta hecha ni escrita: toca estado vivo y la decision es del
usuario. **No usar el `NUEVA: 91.715` de la corrida 2 como si fuera un
hallazgo.**

## Connectors (4 construidos)

| Connector | Cubre | Validacion | Costo por propiedad |
|---|---|---|---|
| `tokko` | 920 fuentes | idempotencia 2.048→2.048 SIN_CAMBIOS | 1 pedido por ficha |
| `wordpress` | 336 fuentes | idempotencia 120→120 SIN_CAMBIOS | REST + ficha |
| `century21` | 40 oficinas | idempotencia 3.039→3.039 SIN_CAMBIOS | **0 pedidos por ficha** |
| `generico` | sitios propios (826 UNKNOWN) | canary en curso | 1 pedido por ficha |

`century21` es el mas barato con diferencia: el JSON del listado trae todos los
campos, asi que corre a ~100.000 propiedades/hora contra ~9.500 de Tokko.

## Wasi — detectado, medido y con connector

`scripts/wasi_fingerprint.py` (modulo puro, sin red) + `scripts/wasi_discovery.py`.

La deteccion **no puede mirar el hostname**: Wasi es white-label y la
inmobiliaria pone su dominio y su marca. Se combinan senales por peso: una
FUERTE confirma, dos MEDIAS confirman, las DEBILES nunca alcanzan solas.

| Fuerte | Por que |
|---|---|
| `meta name=author` = Wasi.co | lo firma la plataforma |
| `meta name=Designer` = wasi.co | idem |
| `images.wasi.co/(inmuebles\|empresas)/` | CDN de fotos, con su ruta |
| `image.wasi.co/eyJ...` | manipulador de imagenes |
| **`bundle_white_label`** | `/js/v1/<plan>/global.min.js?v<build>` + un hermano con **el mismo build**. No dice "wasi" en ninguna parte: es la que sobrevive a que borren la marca |

Validacion: **39/39** positivos, las cinco senales fuertes en los 39.
**0 falsos positivos** en el control negativo, y ahi no disparo ninguna senal
fuerte ni media -solo debiles-, asi que ningun sitio quedo a una senal del
error.

Las 36 fuentes LARAVEL **no** son Wasi (0/36), aunque el white-label de Wasi
corra sobre Laravel: framework de abajo != forma de publicar.

Via de extraccion, en el orden de costo del proyecto:

1. API/JSON — **no**: `api.wasi.co` pide `id_company` + `wasi_token`, que el
   sitio publico no expone. Por eso la estrategia es `SITEMAP` y no
   `API_DIRECT`, que era lo que decia el detector viejo.
2. endpoint interno — no: el front es Laravel server-side.
3. JSON embebido — JSON-LD por ficha, pero **incompleto**: no trae precio,
   operacion ni superficie, y su `floorSize` es la cantidad de PLANTAS. Leerlo
   como superficie registraria "2 m2" para un duplex de 84.
4. **HTML servido — si**: `/sitemap.xml` enumera las fichas y la ficha trae una
   tabla etiquetada (Area Construida, Dormitorios, Banos, Tipo de negocio...).
   Verificado: sitemap 171 = paginacion exhaustiva 171 en el mismo sitio.
5. navegador — no hace falta.

Rutas: ficha `/<slug>/<id>` (el id es el "Codigo" que la ficha muestra, no hay
que fabricar identificador), listado `/s/<tipo>/<operacion>`, paginacion
`/search?...&page=N`.

Universo medido: **39 fuentes, 3.598 propiedades unicas** (31 COMPLETE, 8
LIKELY_COMPLETE, ninguna incompleta). Barrido de falsos negativos sobre 1.194
sitios no confirmados: **0 Wasi nuevos**, 40 sin respuesta.

### Rollout y idempotencia — CERRADO

| | corrida 1 | corrida 2 |
|---|---|---|
| fuentes | 39/39 (36 OK + 3 falsas incompletas) | **39/39 OK** |
| propiedades | 3.598 NUEVA | 3.596: **3.593 SIN_CAMBIOS**, 2 MODIFICADA, 1 NUEVA |
| duplicados intra-fuente | 0 | 0 |
| hash compartido entre agencias | 0 | 0 |
| fotos ajenas | 0 | 0 |
| errores | 0 | 0 |
| reconcilia | si | si |

3.598 detalles = **3.598 hashes unicos**: la regla de url canonica evito los
duplicados de los dos slugs. Los 3 cambios de la corrida 2 se auditaron uno por
uno y son reales -una ficha sumo `cocheras`, otra perdio `plantas`, y hubo un
alta-. Ninguno es ruido del parser. 2 ausencias, ambas con la fuente
respondiendo OK y enumeracion completa, en observacion.

### Tres trampas de Wasi, ya resueltas

1. **La misma propiedad bajo dos slugs.** `/apartamento-venta-moron/5444177` en
   el sitemap y `/departamento-venta-moron/5444177` en el listado: 184 casos en
   3 fuentes. Como `hash_dedup` lleva la url adentro, entrar por un camino en
   una corrida y por el otro en la siguiente crearia duplicados invisibles al
   indice unico. `og:url` devuelve la url pedida y no sirve; el `url` del
   JSON-LD devuelve siempre la misma. Esa es la identidad.
2. **El total del menu es una cota superior**, no un objetivo: suma una vez por
   operacion. Verificado en jorgeorellano.com -venta 238 + alquiler 23 +
   permuta 2 = 263, lo declarado, mientras la union de ids da 261-.
3. **Dos convenciones de numero en la misma pagina**: pesos a la argentina
   ("$620.000") y dolares a la americana ("US$110,000"). Una sola convencion
   convertia 110.000 dolares en 110.

### Bugs de codigo compartido que aparecieron construyendolo

- `a_numero` borraba el signo: "-34.6690485" volvia 34.6690485. Tokko no lo
  sufrio -convierte coordenadas con float() directo, 76.008 latitudes negativas
  y 3 positivas-, pero cualquier connector nuevo si.
- `a_numero` pegaba los rangos: "55.000-60.000" daba 5.500.060.000.
- El runner daba por ausente lo presente cuando el connector canonicaliza la
  url: 33 bajas falsas en la primera corrida de una fuente.

## Corriendo

- **Tokko corrida 3 — VALIDACION DE IDEMPOTENCIA, en curso.** 913 fuentes sobre
  el baseline reconstruido. A 103/913: 99,97% SIN_CAMBIOS, 0 ausencias.
  Lanzada aislada con `Start-Process` (una consola compartida ya mato una
  corrida antes). Log: `TOKKO_ROLLOUT_FULL/run3_idempotency.log`.
- **Clasificacion del residual, en curso.** 1.225 webs propias sin cubrir,
  `RESIDUAL_CLASSIFIED.jsonl`.
- Wasi: canary de 5 fuentes; despues rollout completo de las 39.
- Tokko corrida 2: TERMINADA 913/913, 91.715 propiedades. Datos utiles; su
  idempotencia NO vale (ver arriba).
- WordPress corrida 3: **TERMINADA** 336/336, 18.567 propiedades. Fue el reset
  de linea base -todo NUEVA pero `potential_inactive: 0`, o sea el fix evito
  ~19.000 bajas falsas-. La prueba de idempotencia de WordPress es la corrida
  4, que todavia no se corrio.
- Rescate Next.js: **TERMINADO** 27/27, 1.614 propiedades (`RESCATE_nextjs`),
  ya incorporado al directorio: 12 fuentes con inventario, ahora SITIO_PROPIO.
- Century 21: 40 oficinas, con soporte bilingue (`C21_CANARY`)
- Generico: canary de 40 fuentes (`GENERICO_CANARY`)

## Las 496 "sin inventario": 190 si publicaban

El sondeo anterior probaba seis rutas fijas, asi que "no publica inventario"
podia significar "no lo encontre". De las 496, solo 5 eran sitios vacios.

`scripts/discover_ficha_shapes.py` no clasifica: agrupa las urls internas por
FORMA -reemplazando numeros y slugs por marcadores- y cuenta cuantas comparten
cada una. Doscientas urls hermanas son inventario, lo reconozca o no el patron
escrito hoy.

| | fuentes | urls |
|---|---:|---:|
| **INVENTARIO_RECUPERABLE** | **190** | **9.128** |
| SIN_FORMA_REPETIDA | 256 | 0 |
| WEB_NO_INMOBILIARIA | 23 | 37.347 |
| FORMA_AMBIGUA | 21 | 768 |
| INACCESIBLE | 6 | 0 |

El bruto era 47.243 urls. **La cifra honesta es 9.128**: `laguiaonline.com.ar`
-un directorio de comercios- aportaba 34.565 el solo, y con `barilocheweb`
sumaban 36.221. Entre las 23 hay tambien un portal de autos, notas
periodisticas y un sitio uruguayo. Eso es un dato para el padron: son webs
asignadas a inmobiliarias que no son webs de inmobiliarias.

### Un cuarto white-label: pixelinmobiliario

96 de las 190 publican en `/ad/<slug>` y **son una sola plataforma**. Se nota
antes de mirar el HTML: 54 de esos sitios declaraban exactamente 18 fichas y 22
exactamente 27. Conteos identicos en dominios independientes no son inventario,
son una plantilla.

Confirmado en el HTML: comparten el MISMO id de Google Analytics
(`UA-178873657-1`), el mismo id de ShareThis y el mismo juego de scripts.
Ninguno de los tres es de la inmobiliaria.

No hizo falta un connector nuevo. Faltaban dos cosas en el generico: `ad` no
estaba en la lista de secciones -es "aviso"- y la paginacion no probaba `?page=N`
en la RAIZ, que es donde pagina esta plataforma. Sin eso solo se veian las 18
fichas de la portada: abinmobiliaria.com.ar tiene 46.

Resultado: 190 fuentes, 95 OK, **3.390 propiedades**, 0 duplicados, reconcilia.

## Fotos: dos problemas distintos, los dos medidos

### 1. Imagenes de la PAGINA, no de la propiedad

El chinche del mapa, el icono del telefono, el boton de Pinterest y el banner de
"Agenda un cafe" salian en todas las fichas del sitio.

| Connector | Referencias | De la pagina | |
|---|---:|---:|---:|
| wordpress | 581.329 | **91.519** | 15,7% |
| generico | 533.008 | 28.724 | 5,4% |
| wasi | 67.635 | 974 | 1,4% |
| tokko | 2.228.095 | 0 | 0,0% |
| century21 | 50.508 | 0 | 0,0% |

Tokko y Century 21 dan cero porque sus connectors ya verifican que la foto sea
de la propiedad por el id en la ruta del CDN.

La senal es estructural: si una url aparece en la mitad o mas del catalogo de
una inmobiliaria, no es de ninguna de sus propiedades. La distribucion no deja
lugar a dudas: **397.375 urls aparecen en UNA sola propiedad** y solo 758 en la
mitad o mas.

Consecuencia incomoda: 600 propiedades de WordPress y 2.746 del generico quedan
sin ninguna foto. No perdieron nada; todas sus "fotos" eran iconos.

### 2. Variantes de tamano de WordPress

WordPress genera una copia por cada tamano que usa el tema: la misma imagen como
`-120x72`, `-224x140`, `-768x1024` y sin sufijo. **El 30% de las "fotos" eran
variantes**: 146.876 entradas de mas en 9.672 propiedades, mas de la mitad del
catalogo. Una propiedad que figuraba con 40 fotos solia tener diez.

Se queda la mas grande de cada imagen. Tokko y el generico no usan variantes -0
casos en 2.228.095 y 504.284 fotos-.

Las dos cosas se aplicaron tambien a los artefactos ya extraidos, sin volver a
bajar nada: `scripts/apply_page_image_filter.py`. El original no se pisa y cada
url descartada queda en `*.imagenes_descartadas.jsonl`.

## Version de huella y artefactos autoritativos

`HUELLA_VERSION = 4` en `connectors/base.py`. La version viaja en el checkpoint
(`huella_version` por fuente) y en cada propiedad (`fingerprint_version`), y
cuando no coincide la corrida informa `BASELINE_INCOMPATIBLE` en vez de una ola
falsa de MODIFICADA.

  1  formula original
  2  se ignora el ORDEN de descripcion y fotos
  3  se ignora `modificado_en_fuente`
  4  se descartan las imagenes de la PAGINA

**Todos los baselines productivos estan sellados en v4.**

### Artefacto autoritativo por plataforma

| Rollout | Archivo | Propiedades |
|---|---|---:|
| Tokko | `TOKKO_ROLLOUT_FULL/properties_run3.jsonl` | 91.659 |
| WordPress | `WP_ROLLOUT_FULL/properties_run6.jsonl` | 18.505 |
| Wasi | `WASI_ROLLOUT_FULL/properties_run2.limpio.jsonl` | 3.596 |
| Century 21 | `C21_CANARY/properties_run2.jsonl` | 5.497 |
| Rescate generico 2 | `RESCATE2_generico/properties_run1.limpio.jsonl` | 26.390 |
| Rescate wordpress 2 | `RESCATE2_wordpress/properties_run1.jsonl` | 3.453 |
| Rescate tokko 2 | `RESCATE2_tokko/properties_run1.jsonl` | 1.683 |
| Rescate nextjs | `RESCATE_nextjs/properties_run1.jsonl` | 1.614 |
| Rescate generico 1 | `RESCATE_generico/properties_run1.jsonl` | 1.442 |
| Canary generico | `GENERICO_CANARY/properties_run2.jsonl` | 230 |
| Rescate tokko 1 | `RESCATE_tokko/properties_run1.jsonl` | 57 |

Los `.limpio.jsonl` son los mismos artefactos con las imagenes de la pagina
sacadas. **El original no se pisa**, y cada url descartada queda en
`*.imagenes_descartadas.jsonl` con en cuantas propiedades aparecia.

## Idempotencia por connector — las tres cerradas

| Connector | Prueba | SIN_CAMBIOS |
|---|---|---|
| tokko | corrida 3 sobre 913 fuentes | **91.503 / 91.659 (99,83%)** |
| wasi | corrida 2 sobre 39 fuentes | **3.593 / 3.596 (99,92%)** |
| wordpress | corrida 5 sobre 336 fuentes | en curso; a 25 fuentes, **99,7%** |

Las tres necesitaron el mismo trabajo previo: reconstruir el baseline desde las
propiedades ya extraidas y arreglar lo que hacia inestable la huella.

### Tres causas distintas de MODIFICADA falsa, encontradas una por una

1. **Orden de la descripcion y de las fotos.** Tokko arma la lista de servicios
   sin orden fijo. 2,4% del canary; ~2.200 falsas por corrida a escala.
2. **La fecha que declara el sitio.** WordPress mueve `modified` cuando
   re-guarda los posts en masa -1.618 fichas, varias con el mismo `04:00:29`-.
   Con ella adentro, la corrida 4 dio 73% SIN_CAMBIOS; sin ella, 99,7%.
3. **Un cambio de formula de huella** deja el baseline anterior incomparable, y
   TODO vuelve MODIFICADA. Paso dos veces. Por eso `rebuild_checkpoint_baseline`
   RECALCULA la huella en vez de copiar la guardada.

## WRITE SET FINAL — 140.160 propiedades, invariantes verificados

Compuerta corrida sobre los artefactos finales de cada rollout (la corrida mas
RECIENTE valida, no la mas grande: Tokko run2 tiene 56 filas mas que run3 pero
incluye propiedades que ya no estan).

| | |
|---|---:|
| propiedades analizadas | 157.516 |
| **DB_WRITE_ELIGIBLE** | **143.337** (91,0%) |
| hash_dedup unicos | 143.337 |
| urls unicas | 143.337 |
| urls con dos inmobiliarias | 0 |
| filas sin eretz_id real | 0 |
| inmobiliarias | 1.230 |
| AGENCY_ID_PENDING | 3.928 (50 agencias) |
| NO_ES_UNA_FICHA | 13 |
| retenidas por conflicto cross-agency | 10.142 |

Por connector: tokko 89.407, generico 24.733, wordpress 20.890, century21
4.935, wasi 3.372.

3.158.909 fotos, 21.090 propiedades sin ninguna. Calidad: 3,61% con alguna
incoherencia (era 4,12% antes de los arreglos de coordenadas e imagenes), 0
hashes repetidos, 0 hashes compartidos entre agencias, 0 urls repetidas.

**APTO PARA ESCRIBIR: si.** Lo unico que falta es la credencial.

### Conflictos cross-agency

4.613 urls disputadas, 10.531 claims. Se liberaron los 389 CLEAR_OWNER; quedan
retenidos 6.406 SAME_AGENCY, 2.187 AMBIGUOUS y 1.160 SHARED_FRANCHISE. Tres
dominios los reclaman dos agencias del padron, y uno solo explica casi todo:
`bustamantepropiedades.com` con **3.137 urls** en conflicto.

### Agencias sin eretz_id (44)

27 NEW_AGENCY_REQUIRED (2.684 propiedades), 16 AMBIGUOUS (924), 1
EXISTING_RESOLVED con evidencia fuerte -De Bernardis Propiedades -> eretz_id
1430, mismo dominio, 169 propiedades-. Ninguna se aplica sola.

## Rescate del residual: 1.225 sin cubrir, 274 con inventario a la vista

`RESIDUAL_CLASSIFIED.jsonl` clasifica las 1.225 webs propias sin cubrir por
MECANISMO de publicacion, no por etiqueta tecnologica. Solo se propone connector
cuando hay fichas A LA VISTA:

| | fuentes |
|---|---:|
| CON_EVIDENCIA_DE_INVENTARIO | 274 |
| PLATAFORMA_SIN_EVIDENCIA | 310 |
| SIN_CONECTOR | 641 |

La distincion no es teorica. Las 81 fuentes con marcadores de Tokko pero **sin**
fichas a la vista rindieron **0 propiedades**: son TOKKO_FRONTEND_PROPIO y ni el
connector de Tokko ni el generico las leen. Las 22 **con** evidencia rindieron
1.683, y las 16 que funcionaron lo hicieron por el respaldo generico.

### Resultado de los rescates

| Rescate | Fuentes | Propiedades | Notas |
|---|---:|---:|---|
| `RESCATE2_wordpress` | 48 (46 OK) | **3.453** | 2 por respaldo generico |
| `RESCATE2_tokko` | 22 (16 OK) | **1.683** | 16 por respaldo generico |
| `RESCATE2_generico` | 204 | en curso | 25.629 fichas visibles |

Todos con 0 hash compartido entre agencias, 0 fotos ajenas, 0 errores y
reconciliando.

## Tres dominios los reclaman dos o tres agencias, y se enumeran igual

En el censo del residual, `comunidadinmobiliaria.com.ar` figura con 3 agencias,
`alquenia.com` con 3 y `bustamantepropiedades.com` con 2. Eso hace que el mismo
sitio se baje varias veces: **4.595 fichas de trabajo duplicado**, y como los
dos workers caen sobre el mismo host se serializan por la cortesia de 1,5 s, lo
que vuelve esas fuentes muy lentas.

Se podria deduplicar el censo por dominio y ahorrar esas horas. **No se hace**:
sacar una agencia del censo le borra el claim, y la regla del proyecto es que
ningun claim se destruye. La adjudicacion es de `resolve_cross_agency.py`, que
decide con la evidencia de cada aviso. Se paga la red para no perder evidencia.

## Tokko no devuelve 404 cuando saca una ficha: sirve la home

Auditada la primera ausencia de la corrida 3 (`8084887`, Clerissi). La fuente
respondio OK, enumero 38/38 con cobertura 1,0, y falta exactamente esa. Pero al
pedir su url la ficha **responde 200 con 74 KB**: es la home institucional de la
inmobiliaria -sin fotos de la propiedad, sin el codigo, titulo generico-.

Consecuencia operativa: **la unica senal fiable de baja es la enumeracion del
listado**. Cualquier logica que confirme "sigue viva" pidiendo la ficha daria
siempre que si, y no se detectaria ninguna baja. Tambien significa que si una
url retirada llegara a enumerarse -por un sitemap viejo, por ejemplo- el parser
produciria una propiedad con el nombre de la inmobiliaria por titulo y sin
precio.

La regla actual ya hace lo correcto: la ausencia se juzga por el listado, hacen
falta 3 corridas consecutivas y nada se desactiva.

## Tests

| Estado | Cantidad | Que son |
|---|---:|---|
| PASS | 688 | incluye 190 de connectors + Wasi |
| PREEXISTING_ENV_FAILURE | 8 | `test_run_manifest.py`: `RuntimeError: Variables de entorno requeridas no configuradas: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY` |
| NO COLECTABLES | 5 archivos | misma causa, falla al importar |

Los 13 son ambientales y ninguno toca codigo de este frente. **No se meten
credenciales de service_role para hacerlos pasar.**

Comando: `pytest tests/ -q --ignore=tests/test_data_quality_regressions.py
--ignore=tests/test_full_7004_coverage.py
--ignore=tests/test_parser_detail_url_candidates.py
--ignore=tests/test_pipeline_a_safety.py --ignore=tests/test_safe_merge.py`

## Pendiente medido: `barrio` de Tokko arrastra texto de amenities

Lo destapo auditar el unico MODIFICADA de la corrida 3: `barrio` paso de
"tranquila" a "tranquila Luminoso Calefaccion F/C Pileta descubierta
Lavanderia". Medido sobre las 91.715 propiedades de la corrida 2:

- 63.130 tienen barrio (68,8%)
- 270 traen palabras de amenities (0,43% de los que tienen; parte son falsos
  positivos como "Balcones del Chateau", que es un barrio de verdad)
- **3.925 tienen mas de 6 palabras (6,22%)**, con el patron "Centro Aire
  Acondicionado individual No Amenities Si Pileta No"

**NO se toca mientras corre la validacion de idempotencia.** Cambiar la
extraccion cambia la huella de contenido, y la corrida 3 empezaria a informar
MODIFICADA por un cambio de parser en vez de un cambio real. Se arregla despues,
con test.

## Estado del write set

```
propiedades analizadas   174.955
DB_WRITE_ELIGIBLE        159.858   (91,4%)
AGENCY_ID_PENDING          4.442   (2,5%)  59 inmobiliarias sin id real
WEB_NO_PROPIA              2.927   (1,7%)  perfiles de portal
CROSS_AGENCY_DUPLICATE     7.283   (4,2%)  misma url, dos inmobiliarias
NO_ES_UNA_FICHA               17
```

Las cuatro invariantes cierran exactas:

```
159.858 filas = 159.858 hashes unicos = 159.858 urls unicas
0 propiedades sin eretz_id real
0 urls reclamadas por dos inmobiliarias
1.493 inmobiliarias
```

De los 7.283 conflictos cross-agency, 6.406 son **una sola inmobiliaria
cargada dos veces en el padron** -Bustamante, con 3.137 propiedades en
disputa-. No se libera ninguno: saber que son la misma empresa no dice cual de
las dos fichas conserva ERETZ, y elegir mal deja 3.137 propiedades colgando de
un id que despues se unifica o se borra. Es un problema del padron y se
resuelve alla; el manifiesto tiene las dos fichas, cual es mas antigua y cual
tiene el dominio verificado.

## Mapa de cobertura (2.259 webs propias)

| Plataforma | Detectadas | Procesadas | Propiedades |
|---|---:|---:|---:|
| TOKKO | 861 | 800 | 91.623 |
| UNKNOWN | 728 | 0 | 0 |
| WORDPRESS | 291 | 186 | 19.002 |
| SIN_CLASIFICAR | 130 | 0 | 0 |
| SITIO_PROPIO | 50 | 48 | 3.243 |
| WASI | 39 | 0 (connector recien construido) | 3.598 enumerables |
| LARAVEL | 36 | 0 | 0 |
| NEXTJS | 32 | 0 | 0 |
| resto | ~92 | 0 | 0 |

**Sin cobertura: 1.225 webs propias** (`RESIDUAL_UNCOVERED.jsonl`), de las
cuales 1.142 respondieron al sondeo y 40 no.

Todo en modo observacion: las ausencias se anotan, nada se desactiva.

## Herramientas

| Script | Para que |
|---|---|
| `scripts/run_rollout.py` | runner paralelo, agnostico de plataforma |
| `scripts/classify_unsupported.py` | censo de fuentes que ningun connector leyo |
| `scripts/write_eligibility.py` | compuerta antes de la base + manifiesto pendientes |
| `scripts/property_write_canary.py` | 13 validaciones antes de escribir |
| `scripts/ingest_to_pipeline.py` | carga a propiedades_raw, dry run por defecto |
| `scripts/quality_audit.py` | cobertura vs coherencia |
| `scripts/mission_report.py` | informe consolidado |
| `scripts/wasi_fingerprint.py` | senales de Wasi por peso; modulo puro, testeable |
| `scripts/wasi_discovery.py` | aplica el fingerprint al universo y mide extraccion |

## Comandos exactos de reanudacion

Todos son **reanudables**: releen el artefacto y saltan lo ya procesado. Nunca
empiezan de cero.

```bash
cd "D:/INMO CAPITAL/eretz-agency"

# Tokko completo (913 fuentes)
python scripts/run_rollout.py --salida "D:/INMO CAPITAL/TOKKO_ROLLOUT_FULL"   --max-fichas 0 --concurrencia 8 --corrida 1

# WordPress completo (336)
python scripts/run_rollout.py --salida "D:/INMO CAPITAL/WP_ROLLOUT_FULL"   --connector wordpress --plataforma WORDPRESS --variantes ""   --max-fichas 0 --concurrencia 4 --corrida 1

# Rescate de las no soportadas, por connector
python scripts/run_rollout.py --salida "D:/INMO CAPITAL/RESCATE_wordpress"   --connector wordpress --censo "D:/INMO CAPITAL/UNSUPPORTED_CENSUS.jsonl"   --respaldo generico --max-fichas 0 --concurrencia 3 --corrida 1

# Segunda corrida (idempotencia): mismo comando con --corrida 2

# Fingerprint de Wasi: las ya marcadas, o todo el universo sin confirmar
python scripts/wasi_discovery.py --plataforma WASI --salida "D:/INMO CAPITAL/WASI_DISCOVERY.jsonl" --concurrencia 2
python scripts/wasi_discovery.py --plataforma TODAS --solo-no-confirmadas --salida "D:/INMO CAPITAL/WASI_SWEEP.jsonl" --concurrencia 2

# Guardas de coherencia sobre lo ya extraido (escribe *.coherente.jsonl)
python scripts/apply_quality_guards.py --entradas <properties_run*.jsonl ...>

# Compuerta antes de escribir: SIEMPRE con los archivos corregidos
python scripts/write_eligibility.py --entradas   "D:/INMO CAPITAL/TOKKO_ROLLOUT_FULL/properties_run3.coherente.jsonl"   "D:/INMO CAPITAL/WP_ROLLOUT_FULL/properties_run6.coherente.jsonl"   "D:/INMO CAPITAL/WASI_ROLLOUT_FULL/properties_run2.limpio.coherente.jsonl"   "D:/INMO CAPITAL/C21_CANARY/properties_run2.coherente.jsonl"   "D:/INMO CAPITAL/RESCATE2_generico/properties_run1.limpio.coherente.jsonl"   "D:/INMO CAPITAL/RESCATE2_tokko/properties_run1.coherente.jsonl"   "D:/INMO CAPITAL/RESCATE2_wordpress/properties_run1.coherente.jsonl"   "D:/INMO CAPITAL/RESCATE3_shapes/properties_run1.coherente.jsonl"   "D:/INMO CAPITAL/RESCATE_generico/properties_run1.coherente.jsonl"   "D:/INMO CAPITAL/RESCATE_nextjs/properties_run1.coherente.jsonl"   "D:/INMO CAPITAL/FORMAS_ROLLOUT/properties_run1.jsonl"

# Formas verificadas por fuente (158) y residual nunca intentado (463)
python scripts/build_shape_census.py --verificado   "D:/INMO CAPITAL/ROOT_SHAPES_VERIFIED.jsonl" "D:/INMO CAPITAL/SHAPES_2_VERIFIED.jsonl"
python scripts/run_rollout.py --connector generico   --censo "D:/INMO CAPITAL/CENSO_FORMAS.jsonl" --concurrencia 8 --corrida 1   --salida "D:/INMO CAPITAL/FORMAS_ROLLOUT"
python scripts/build_residual_census.py --estados   "NO_INTENTADA,UNSUPPORTED_PLATFORM,UNKNOWN,ENUMERACION_INCOMPLETA,NO_INVENTORY"   --excluir "D:/INMO CAPITAL/CENSO_FORMAS.jsonl"   "D:/INMO CAPITAL/SHAPES_2_CANDIDATAS.jsonl"   --salida "D:/INMO CAPITAL/CENSO_RESIDUAL_GENERICO.jsonl"

# Cadencia de relectura
python scripts/plan_recrawl.py

# Canary de escritura (valida y hace ROLLBACK; --escribir para confirmar)
python scripts/property_write_canary.py --entrada "D:/INMO CAPITAL/DB_WRITE_ELIGIBLE.jsonl" --limite 50
```

## Formas de ficha verificadas por fuente

158 sitios publican sus fichas en formas que el patron global no toma
-`/p-1749_departamento`, `/site/properties/8406/casa-en-venta`- y quedaban
afuera **a proposito**: ese patron gobierna 2.258 fuentes, y aflojarlo para que
entren estos mete listados, paginas institucionales y notas del blog en el
inventario de todas.

El camino largo, en cambio, es por fuente:

1. `discover_ficha_shapes.py` agrupa las urls internas del sitio por FORMA
   (`/p-1749_x` -> `/<slug-con-id>`) y cuenta hermanas.
2. `verify_root_shapes.py` baja tres fichas de esa forma y mira si ahi hay
   propiedades: precio con moneda, operacion o atributos, fotos.
3. `build_shape_census.py` convierte el veredicto en censo.
4. El generico usa esa forma **solo para esa fuente**.

Y dos guardas, porque una forma acotada sigue siendo una forma:

- **En el detalle**: lo que entro por la forma tiene que mostrar una propiedad.
  Medido sobre las 844 paginas bajadas para verificar, acepta el 98,0% de las
  que vienen de una forma confirmada y el 3,4% de las que vienen de una
  descartada. Lo descartado queda con su evidencia en `shape_rejects_run<N>`:
  descartar en silencio hace indistinguible una url que no era ficha de una que
  el guardian tiro por error, y las dos primeras versiones del guardian tiraron
  fichas reales.
- **En el censo**: no entra el host que el padron le atribuye a varias
  inmobiliarias.

Quinta marca blanca encontrada por la forma, no por el nombre: 34 fuentes
publican en `/site/properties/<num>/<slug>`, 11 en el dominio del proveedor y
23 en dominio propio. No necesito un connector nuevo: necesitaba la forma.

## Web propia, perfil de portal, y lo que no es ninguna de las dos

La lista de portales por nombre se equivocaba en las dos direcciones: metia a
kitepropcrm -que da un host por inmobiliaria: es web propia alojada- y dejaba
afuera a inmoup.com.ar, que figura como web oficial de 52 inmobiliarias.

La senal estructural se cuenta: **cuantas inmobiliarias cuelgan del mismo
host**. Tres o mas, no es la web propia de ninguna. Dos, hay que mirar los
nombres: suele ser el mismo negocio cargado dos veces, y cuando no se parecen
queda `AMBIGUOUS_WEB_ATTRIBUTION` -una de las dos es la duena y desde afuera no
se sabe cual-. Y 23 urls llevan a una guia de rubros, un diario de la zona o una
pagina de vehiculos: `NOT_A_REAL_ESTATE_WEB`, comprobado mirando que publican.

| web_kind | agencias |
|---|---:|
| OFFICIAL_WEB | 2.090 |
| EXTERNAL_PORTAL_PROFILE | 384 |
| OFFICIAL_OFFICE_PAGE | 79 |
| NOT_A_REAL_ESTATE_WEB | 23 |
| AMBIGUOUS_WEB_ATTRIBUTION | 20 |

La compuerta de escritura lo mira: lo leido en un portal no se escribe, porque
le atribuiria a una inmobiliaria el inventario de las otras 35. La pagina de la
oficina dentro de su propia red si es suya y si entra.

## El ciclo que cierra la cobertura

El mismo mecanismo, tres vueltas, cada una alimentada por lo que la anterior
no pudo leer:

```
correr el generico  ->  las que devuelven SIN_INVENTARIO
     |                          |
     |                   descubrir FORMAS de sus urls internas
     |                          |
     |                   verificar bajando 3 fichas de cada sitio
     |                          |
     +--------------------  censar y correr con la forma de ESA fuente
```

| vuelta | fuentes miradas | con forma | verificadas | habilitadas |
|---|---:|---:|---:|---:|
| 1 (residual clasificado) | 496 | 190 | 95 | 58 |
| 2 (nunca sondeadas) | 460 | 283 | 198 | 100 |
| 3 (residual del generico) | 441 | 48 | 44 | 6 |

El rendimiento cae vuelta a vuelta -58, 100, 6- y eso es informacion, no
fracaso: la tercera vuelta mira lo que ya sobrevivio a dos filtros. Cuando el
descubrimiento devuelve 355 de 441 sin una forma repetida, lo que dice es que
esos sitios no publican un catalogo enlazado, no que falte un connector.

Y el residual del generico -453 fuentes con web propia que nunca habia
intentado nadie- devolvio 12 con inventario y 613 propiedades. Correrlo costo
25 minutos y convirtio 453 "no sabemos" en 441 "no publica catalogo" y 12
inmobiliarias mas.

## Lo que el rastro de descartes encontro

Guardar cada url descartada con su evidencia -precio, schema, operacion en el
texto, cantidad de fotos- costo veinte lineas y encontro tres defectos que
ninguna prueba unitaria hubiera encontrado, porque los tres se veian como
"esa fuente publica poco":

1. **Fotos detras de un proxy.** Un sitio sirve sus 12 fotos por
   `/api/img?u=<foto>`. Quitar la query -correcto para descartar variantes de
   tamano- las dejaba en una sola: `/api/img`.
2. **Fotos con ruta relativa.** El extractor solo miraba urls absolutas. Una
   fuente perdio 268 fichas reales porque el guardian las veia sin una foto.
3. **El guardian pedia mas que su propia calibracion.** La forma se verifico
   con "precio Y (operacion O atributos)" y el guardian exigia la operacion
   siempre: 21 fichas de 31 en una sola fuente, con precio, titulo y 190
   fotos.

Una url descartada en silencio es indistinguible de una que nunca existio.

Lo que queda descartado -403 en 158 fuentes- esta anotado con su evidencia:
242 son fichas sin precio ni schema.org y 161 tienen menos de tres fotos. Se
midio la alternativa de aceptar por galeria grande en vez de precio: sube los
falsos positivos del 3,4% al 11,5% para ganar 0,2% de fichas buenas. No se
cambio.

## Aritmetica de inmuebles

`connectors/coherencia.py`. No es validacion de formato: un dormitorio ES un
ambiente, lo cubierto es parte de lo total, un lote no tiene banos, cero metros
no es una superficie y Nueva York no queda en Argentina. Cuando los numeros
dicen otra cosa, alguno vino de las "propiedades relacionadas" al pie de la
misma ficha.

Cuando dos valores se contradicen **se van los dos**: no hay forma de saber
cual salio de la ficha y cual del vecino, y un dato ausente se ve mientras que
uno incorrecto se publica.

| corpus | antes | despues |
|---|---:|---:|
| WordPress (18.505) | 10,08% | 0,03% |
| generico (29.780) | 7,01% | 0,00% |
| Tokko (91.659) | 0,48% | 0,00% |

`apply_quality_guards.py` lo aplica a lo ya extraido sin volver a bajar nada
-los defectos son de lectura, no de la fuente- y escribe al lado, con sufijo
`.coherente.jsonl`. **Antes de la proxima corrida sobre esas fuentes hay que
reconstruir el baseline desde el archivo corregido**, o la corrida siguiente lee
nuestra correccion como un cambio de la inmobiliaria.

El mismo modulo lo usa el connector generico, asi que las dos rutas no pueden
divergir.

## Cada cuanto volver a cada fuente

`plan_recrawl.py`. Entre la corrida 2 y la 3 de Tokko, 91.503 de 91.659
propiedades estaban iguales: recorrer todo todos los dias gasta el 99,8% del
trabajo en confirmar que nada cambio. La cadencia sale de lo que cada fuente
hizo en su ultima corrida, entre 1 y 14 dias: **37.336 fichas/dia en vez de
154.225, un 76% menos**, sin perder de vista a ninguna.

La fuente que estuvo caida vuelve manana. La que no supimos leer no se arregla
volviendo 365 veces al ano -lo que falta es un connector-, y esas 334 estaban
pidiendo lectura diaria.

El plan no corre nada: dice a quien volver y cuando.

## Regla aprendida

**No editar connectors ni runners con una corrida en vuelo.** Paso dos veces:
la segunda corrida lee codigo distinto, todo sale MODIFICADA y la idempotencia
parece rota. Cada corrida graba ahora `version_codigo` en su reporte.

## Reglas

Solo `feat/roomix-agency-coverage`. Sin push, sin merge, sin main, sin Production.
`git add` por rutas explícitas. Sin frontend, sin mobile. Roomix **no** es fuente
de propiedades. Data API OFF.

---
---

# HISTORIA — CAMPAÑA ROOMIX (cerrada)


Estado vivo de la misión integral. Se actualiza al cerrar cada frente y antes
de cualquier corte de sesión.

**Última actualización:** 2026-08-21 (campaña cerrada; rollout hecho; auditoría de webs completa)

---

## Situación de una línea — CAMPAÑA CERRADA

Crawl, delta, crosswalk, rollout y auditoría gratuita de webs: **todo terminado**.
Nada corriendo. El único frente abierto necesita una API key de búsqueda.

### Resultado final

| | |
|---|---|
| Universo Roomix procesado | 168.563 + 24.256 del delta |
| `observations.jsonl` | 202.111 filas |
| RAW / CANONICAL | 9.773 / 9.622 (151 alias) |
| **Inmobiliarias + oficinas** | **6.597** |
| Ya en `main` / staging | 1.122 / 4.920 |
| **Nuevas incorporadas a staging** | **465** |
| Ambiguas preservadas | 80 |
| **Duplicados introducidos** | **0** |

### Webs (auditoría gratuita, cero consultas pagas)

| | |
|---|---|
| VERIFIED | 417 |
| HIGH_CONFIDENCE | 148 |
| **Fuentes READY para scrapear** | **535** |
| AMBIGUOUS / INACTIVE / portal | 277 / 75 / 18 |
| Sin URL cargada | 5.662 |
| **Cola para Search API** | **6.032** |

### Bloqueo único

`BRAVE_SEARCH_API_KEY` ausente. Sin ella, 6.032 entidades quedan en
`SEARCH_API_PENDING` — nunca en `NOT_FOUND`. Consultas estimadas: 6.032 a 12.064
según escenario.

### Frente libre pendiente (no requiere key)

Lote 2: las inmobiliarias históricas marcadas como no scrapeables. El
diagnóstico de URL histórica ya está construido y probado
(`identity_scoring.diagnosticar_url_historica`), y puede recuperar fuentes dadas
por perdidas por un parser viejo y no por falta de web.

## Situación anterior

El bloqueo de base **se resolvió**: el puente `eretz_agency_coverage_writer`
funciona y quedó verificado 7/7. El frente abierto ahora es la campaña
exhaustiva de Roomix, que necesita ~51 horas de crawl cortés.

## Puente DB — VERIFICADO Y OPERATIVO

Entrada por `SUPABASE_DATABASE_URL` (`eretz_preview_ro`), que es miembro NOINHERIT
de `eretz_agency_coverage_writer`. Los privilegios sólo existen dentro de una
transacción con `SET LOCAL ROLE`.

Dos cosas hubo que resolver para que funcionara:

1. `eretz_preview_ro` no puede leer staging por sí solo, así que **toda** lectura
   de staging va elevada, no sólo las escrituras.
2. El rol de entrada trae `default_transaction_read_only` activo: la transacción
   nacía de sólo lectura y el INSERT fallaba pese a tener el privilegio. Se
   levanta con `SET LOCAL transaction_read_only = off` como primera sentencia de
   la transacción. Nunca a nivel de sesión: con pooler, un cambio persistente lo
   heredaría la siguiente consulta que tome esa conexión física.

Pruebas de privilegio, todas correctas:

| Operación | Esperado | Real |
|---|---|---|
| SELECT main | permitido | permitido |
| SELECT staging | permitido | permitido |
| INSERT staging | permitido | permitido |
| INSERT main | denegado | `permission denied` |
| UPDATE staging | denegado | `permission denied` |
| DELETE staging | denegado | `permission denied` |
| CREATE TABLE | denegado | `permission denied` |

Los negativos se comprueban intentándolos y revirtiendo; ninguno escribió nada.

## Cadena desatendida en marcha

| Tarea de Windows | Qué hace | Estado |
|---|---|---|
| `EretzRoomixCrawl` | crawl inicial | **terminado** (168.563/168.563, 20/08 06:28) |
| `EretzDeltaChain` | espera al delta en curso y lanza `delta_loop.py` | **corriendo** |

`run_delta_chain.bat` no mata nada: espera a que no queden procesos python y
recién entonces arranca el bucle. `delta_loop.py` reconstruye su estado desde
`observations.jsonl`, así que no reprocesa nada de lo ya hecho.

Bitácora por delta: `delta_audit.jsonl`, una fila por pasada con las quince
categorías, sin ocultar ninguna.

### Cierre del delta (aprobado, determinista)

Dos deltas consecutivos completos con, a la vez:
`NEW_INMOBILIARIA = 0`, `NEW_OFICINA_FRANQUICIA = 0` y
`NEW_UNKNOWN_POTENCIALMENTE_INMOBILIARIA = 0`.

Un delta puede traer miles de avisos, cientos de `agent_id`, agentes y
desarrolladoras nuevas, y contar como cero igual.

### Recuperación de fichas sin publicador — cerrada

274 reintentadas, **4 recuperadas**, 270 sin anunciante. Son avisos de dueño
directo: residual legítimo y cuantificado, no un agujero.

## El delta no puede cerrar por avisos — cierra por publicadores

Medido el 20/08 tras agotar el snapshot inicial:

| | |
|---|---|
| Snapshot inicial | 168.563 |
| Universo actual | 166.919 |
| URLs nuevas | 27.003 |
| URLs desaparecidas | ~28.700 |
| Hash reutilizado | **0** |

Roomix rota **~16% de sus avisos cada tres días**. Los hashes nuevos son
genuinamente nuevos, no re-slugueados: se verificó comparando el sufijo de hash
de cada URL contra las ya observadas y no hubo ni una coincidencia.

Consecuencia: **el criterio "repetir hasta que una pasada no traiga URLs nuevas"
es inalcanzable**. Cada pasada tarda ~9 h y en ese lapso aparecen ~11.000 avisos
más. Es un blanco móvil; el bucle no converge nunca.

**Decisión tomada de forma autónoma**, coherente con el objetivo declarado de la
misión —que son las inmobiliarias, no los avisos—: el delta cierra cuando una
pasada **no aporta publicadores nuevos**, no cuando no aporta URLs nuevas. Sigue
siendo cierre por enumeración y no por convergencia estadística; lo que cambia
es sobre qué universo se enumera, y es el universo que importa.

## Fase de webs oficiales — motor construido, sin ejecutar

`scripts/agency_web_discovery.py`. La lógica de decisión está completa y
probada; falta enchufarle la capa de búsqueda y correrla sobre el padrón, cosa
que sólo tiene sentido cuando el padrón esté cerrado.

Reglas que fija el verificador, todas nacidas de un modo de fallar concreto:

- **Un portal nunca es web oficial.** Zonaprop, Argenprop, Instagram y compañía
  son evidencia para llegar al dominio, no lo reemplazan.
- **El dominio de la red no es el de la oficina.** `remax.com.ar` vale para las
  191 oficinas y por eso no identifica a ninguna. Si la oficina tiene perfil
  dentro del dominio de la red, va a `official_office_page`, que es un campo
  distinto de `official_domain`.
- **Un HTTP 200 no demuestra propiedad.** Hace falta que el sitio hable de la
  misma entidad: nombre completo, localidad, teléfono o matrícula.
- **Dos dominios igualmente sostenidos → AMBIGUOUS.** Es el caso de las
  homónimas en provincias distintas; elegir uno sería inventar.

Estados: VERIFIED · HIGH_CONFIDENCE · AMBIGUOUS · NOT_FOUND · INACTIVE ·
NO_INDEPENDENT_WEBSITE. 17 tests.

## Dos contadores que NO son el mismo

Se compararon como si fueran una sola serie y pareció que las entidades habían
bajado de 4.613 a 4.194. Nunca bajaron: 4.613 era el contador vivo del crawler a
16.920 fichas, y 4.194 era `publishers.jsonl`, un archivo congelado el 14/08 con
14.120 fichas que desde entonces no se regeneró. Dos fotos de momentos
distintos.

Quedan separados y no se vuelven a mezclar:

| Métrica | Definición | Valor |
|---|---|---|
| `RAW_PUBLISHER_IDENTITIES` | `agent_id` distintos, tal como los emite Roomix | 4.708 |
| `CANONICAL_PUBLISHER_ENTITIES` | tras unir los `agent_id` que son la misma entidad | 4.666 |
| **Entidades inmobiliarias** | INMOBILIARIA + oficina de franquicia | **3.296** |

El primero es siempre ≥ el segundo. 42 alias fusionados hasta ahora.

## KPI del crawl

**Nuevas entidades inmobiliarias únicas por 1.000 fichas.** Cuenta INMOBILIARIA
y oficina individual de franquicia; no cuenta agente, marca genérica sin
oficina, desarrolladora, unknown ni garbage.

Se mide por ventana, nunca como acumulado, y **no se usa como criterio de
corte**. `scripts/coverage_windows.py`.

## Campaña exhaustiva de Roomix — EN CURSO

**No existe fuente exhaustiva de publicadores.** El `sitemap_index.xml` tiene 13
sitemaps —static, blog, buscar, edificios, landings, venta, barrios y 6 de
propiedades—. Ninguno enumera agencias; los landings son páginas SEO por zona y
tipo. El publicador sólo aparece en el payload RSC de cada ficha, así que
exhaustivo significa recorrer las 168.563.

| | |
|---|---|
| Universo | 168.563 fichas |
| Procesadas | 14.120 |
| Restantes | 154.443 |
| Ritmo medido | 3.033 fichas/hora (2 navegadores) |
| **ETA** | **~51 horas ≈ 2,1 días** |

Lanzada como proceso aislado (la tanda 2 murió por compartir consola).
Reanudable e idempotente vía `state.json`.

---

## Git

| | |
|---|---|
| Repo | `D:\INMO CAPITAL` (multi-worktree) |
| Worktree activo | `D:\INMO CAPITAL\eretz-agency` |
| Branch | `feat/roomix-agency-coverage` |
| Tree | limpio |

### Worktrees

| Ruta | Branch | HEAD | Sucio |
|---|---|---|---|
| `Inmo-Capital-main` | `release/eretz-private-preview` | `8521d47008` | **92 archivos** |
| `eretz-agency` | `feat/roomix-agency-coverage` | ver HEAD actual | no |
| `eretz-integration` | `integrate/eretz-pre-main` | `bd3f37c333` | no |
| `eretz-main` | `main` | `e9630f5f70` | no |
| `eretz-rescue` | `integrate/release-dirty-recovery` | `b6c326b0ce` | no |
| `Inmo-Capital-frontend-phase-a` | `feat/eretz-frontend-phase-a` | `fe85455fb4` | no |
| `eretz-audit` | detached | `8521d47008` | no |

`origin/main` = `15e81991c0`, por delante de `main` local (`e9630f5f70`).
`rescue/release-worktree-integrated` = `4a95a44fab`.

Tags: `roomix-fidelity-v1`, `checkpoint/main-pre-integration`,
`checkpoint/main-pre-rescue`, `checkpoint/release-pre-integration`.

Sin push. Sin merge. `main` intacta.

### Clasificación de ramas (Fase 14)

`main` local está **163 commits por delante** de `origin/main` y 0 por detrás:
todo el rescate y la integración previa ya viven en `main` local, sin publicar.

| Rama | Commits sobre `main` | Exclusivos vs agency | Categoría |
|---|---|---|---|
| `feat/roomix-agency-coverage` | 18 | — | **KEEP** (base de integración) |
| `feat/eretz-frontend-phase-a` | 7 | 7 | **KEEP** (único frontend no contenido) |
| `integrate/eretz-pre-main` | 0 | 0 | **ALREADY_PRESENT** |
| `rescue/release-worktree-integrated` | 4 | 0 | **ALREADY_PRESENT** — el rescate ya está contenido |
| `integrate/release-dirty-recovery` | 3 | — | **NEEDS_REVIEW** |
| `release/eretz-private-preview` | 2 | — | **NEEDS_REVIEW** (worktree sucio, 92 archivos) |

Lectura para la Fase 15: la base correcta de `integration/eretz-rc` es la rama
de agency, que ya contiene el rescate, más los 7 commits de frontend por
cherry-pick. Los fixes del rescate no se pierden: ya están.

---

## Acceso a base — el hecho que gobierna todo

Las variables de Preview están marcadas **Sensitive**, y Vercel no las devuelve
nunca: ni `vercel env pull` ni `vercel env run` las entregan. La base sólo es
alcanzable desde dentro de un deployment.

Medido el 2026-08-17 desde un deployment de Preview:

| Conexión | Rol efectivo | Alcance |
|---|---|---|
| `SUPABASE_DATABASE_URL` | `eretz_preview_ro` | SELECT sobre main (7.003 filas visibles bajo RLS). **staging denegado.** |
| `ERETZ_WRITE_DATABASE_URL` | `eretz_app_writer` | **no autentica**: `password authentication failed` |

Ese fallo de autenticación es la prueba positiva de que la variable ya **no**
usa `postgres`: el usuario que llega a la base es `eretz_app_writer`. Falta que
la contraseña del rol coincida.

### Estado real de las credenciales

- Contraseña nueva: generada, cargada en `ERETZ_WRITE_DATABASE_URL` (Preview).
- Plaintext local: **eliminado** por pedido explícito.
- Entregada como **verificador SCRAM-SHA-256** cifrado con RSA-OAEP.
- `ALTER ROLE` en PostgreSQL: **nunca ejecutado**.

Consecuencia: la contraseña sólo la conoce quien tenga la clave privada. No es
recuperable desde acá.

---

## BLOCKER_DB_ADMIN_PASSWORD_ROTATION

**Único bloqueo humano de la misión.** Gatea las fases 3 (ejecución), 4, 6, 7, 8
y la mitad de la 9.

Para desbloquear, aplicar por el canal administrativo de Supabase el verificador
SCRAM ya entregado:

```sql
ALTER ROLE eretz_app_writer PASSWORD '<verificador SCRAM-SHA-256 entregado>';
```

Después de eso, un deployment de Preview nuevo debería autenticar como
`eretz_app_writer` y todo lo construido queda ejecutable.

Bloqueo secundario: `eretz_preview_ro` no puede leer `inmobiliarias_staging`, lo
que impide la auditoría de staging aunque se resuelva lo anterior. Requiere
SELECT sobre staging para algún rol alcanzable.

---

## Estado de datos conocido

| | |
|---|---|
| `inmobiliarias_main` | 7.004 filas (7.003 visibles bajo RLS) |
| `inmobiliarias_staging` | 11.798 filas |
| — de las cuales `roomix_agency_coverage` | 260 |
| — `zonaprop_inmobiliarias` | 9.040 |
| — `excel_colegio_cpi_cordoba` | 2.498 |
| main con `nombre_normalizado` NULL | 1.983 de 7.003 visibles |

Rollout de Agency Coverage: **cerrado**, no repetir. 1.635 candidatas → 260
insertadas, 1.290 ya en staging, 74 ya en main, 0 duplicados, 0 errores.

---

## Fases

| # | Frente | Estado |
|---|---|---|
| 0 | Inventario | **hecho** |
| 1 | `ERETZ_WRITE_DATABASE_URL` | **parcial** — ya no es `postgres`; falta el `ALTER ROLE` |
| 2 | 31 colisiones | **hecho** — clasificadas, manifest fuera del repo |
| 3 | Backfill `nombre_normalizado` | **código hecho y probado**; ejecución bloqueada |
| 4 | Auditoría de staging | **desbloqueada** — staging legible vía puente |
| 5 | Motor de dedupe | **hecho** — 20 tests |
| 6 | Pipeline staging→main | pendiente (depende de 4) |
| 7 | Franquicias | pendiente |
| 8 | Agentes y desarrolladoras | pendiente |
| 9 | Métricas de cobertura | **parcial** — terminología documentada; recálculo bloqueado |
| 10 | Crawl exhaustivo Roomix | **en curso** — 14.120/168.563 |
| 11 | Cierre estructural CSS | pendiente |
| 12 | Identity V2 | pendiente |
| 13 | Auditoría repo ↔ Supabase | pendiente |
| 14 | Ordenar branches | **hecho** — clasificadas arriba |
| 15 | Rama de integración | pendiente |
| 16 | Release Candidate | pendiente |
| 17 | Preview RC | pendiente |
| 18 | Production readiness | pendiente |
| 19 | Documentación | en curso |

---

## Artefactos fuera del repo

`D:\INMO CAPITAL\ERETZ_AGENCY_DATA\`

- `collision_manifest_staging_main.jsonl` — 31 pares crudos
- `collision_manifest_classified.jsonl` — 31 clasificados con evidencia
- `staging_rows.jsonl` — 1.635 candidatas del rollout
- `crosswalk.jsonl`, `publishers.jsonl`, `observations.jsonl`, `state.json`

---

## Deployments

Todos los Preview temporales creados durante la misión fueron eliminados y
responden 404. Production **intacta y sin variables de entorno** (0 en
Production, 0 en Development, 8 en Preview).

Incidente registrado: un `vercel deploy` sin link creó un proyecto `frontend`
accidental cuyo primer deploy fue a Production y **falló en build**. Ambos
deployments fueron eliminados; el proyecto vacío quedó porque el borrado de
proyectos está denegado por el clasificador de permisos.

---

## Próxima acción exacta

La cadena corre sola. Cuando `delta_loop` alcance los dos ceros consecutivos,
seguir sin pausa con:

1. `python scripts/build_agency_directory.py` — canónico definitivo
2. crosswalk: `python scripts/agency_rollout.py --base <preview> --dry-run`
3. canary + rollout: el mismo comando sin `--dry-run`
4. `python scripts/run_web_discovery.py` — webs oficiales
5. suite completa + informe final

El puente necesita un Preview desplegado: `vercel link` al proyecto
`eretz-propiedades` y `vercel deploy` desde `frontend/`. Los deployments
temporales se eliminan al terminar.
