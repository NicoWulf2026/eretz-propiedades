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
| `PROPERTY_WRITE_CREDENTIAL_PENDING` | Verificado 2026-08-23: `SUPABASE_POOLER_DATABASE_URL` no existe en `.env` ni en el entorno. `SUPABASE_DATABASE_URL` resuelve **solo IPv6**, y desde esta red **la conexión SÍ llega**: el servidor contesta `FATAL: password authentication failed`. O sea el bloqueo es la credencial, no la red — lo anterior decía "IPv6 inalcanzable" y era incorrecto. | Sin canary de escritura ni carga a `propiedades_raw`. Todo lo demás sigue. |
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

### Idempotencia de Tokko — resuelto, corrida 3 en curso

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

# Compuerta antes de escribir
python scripts/write_eligibility.py --entradas <properties_run1.jsonl ...>

# Canary de escritura (valida y hace ROLLBACK; --escribir para confirmar)
python scripts/property_write_canary.py --entrada "D:/INMO CAPITAL/DB_WRITE_ELIGIBLE.jsonl" --limite 50
```

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
