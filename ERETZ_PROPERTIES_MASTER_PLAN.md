# ERETZ — Plan maestro del sistema de propiedades

Panel de control del dominio de propiedades: descubrimiento de inmobiliarias,
adquisición de datos, calidad, experiencia pública, operación y observabilidad.

Última actualización: 2026-09-02.

---

## 1. Principios

Cada uno viene de un error real. Violarlos produce datos que después no se
pueden distinguir de los buenos.

1. **La ausencia nunca se convierte en afirmación.** Un campo que la fuente no
   publica queda `None`, nunca en cero ni inferido. `EXTRACTED`,
   `SOURCE_NOT_PROVIDED`, `REJECTED_BY_VALIDATION` y `EXTRACTION_FAILED` son
   estados distintos.
2. **`NEEDS_FIX` nunca es un cierre.** Terminales válidos:
   `CERTIFIED_COMPLETE`, `CERTIFIED_BEST_AVAILABLE`, `NO_INVENTORY_CONFIRMED`,
   `BLOCKED_EXTERNAL`, `IDENTITY_PENDING`, `INACTIVE`.
3. **Cero inventario se demuestra.** `LOW_INVENTORY_0_11` obliga a revisión
   exhaustiva entre 0 y 11. Un cero sin prueba es un hueco de cobertura
   disfrazado de hecho comercial.
4. **La falta de excepción no es evidencia de corrección.**
5. **La identidad no se inventa en el connector.** Se reusa el `hash_dedup` del
   pipeline: `SHA256("{inmobiliaria_id}|url|{url_normalizada}")`.
6. **Lo que hoy no aparece no es una baja.** Puede ser un timeout; la baja
   exige varias corridas coincidentes y comparables.
7. **Los tests son una defensa, no una prueba.** Ver §1.1.

### 1.1 Validación contra la fuente real

Cuando un cambio toca **descubrimiento, enumeración, parsing, normalización o
calidad de datos**, los tests sintéticos no alcanzan si existe una fuente real
reproducible que expuso el defecto. Mínimo exigible:

1. regresión automatizada;
2. verificación contra la fuente real que originó el bug;
3. recertificación de esa fuente;
4. comparación de métricas antes/después.

Se aplica al caso que motivó el cambio, no a todas las fuentes.

**Por qué es una regla y no una recomendación.** En un solo día, tres arreglos
pasaron la batería completa y fallaron contra los datos reales:

| Caso | Qué habría pasado |
|---|---|
| Guardia de fichas vacías (D-008) | Descartaba **254 lotes legítimos** que publican sólo título y fotos |
| Heurística de atributos (D-013) | Pasó 5 tests y **no corrigió nada**: las páginas traen tabla *y* prosa |
| "0 homónimas en `main`" | Comparaba el nombre **en orden**; por conjunto de palabras hay **56** |

En los tres, el error era invisible con la batería en verde.

---

## 2. Estado medido

Todos los números tienen fuente y fecha. No hay estimaciones.

### 2.1 Universo e identidad

Fuente: `AGENCY_ID_RESOLUTION_FINAL.jsonl`, 6.597 inmobiliarias.

| Resolución | Inmobiliarias |
|---|---|
| `NOT_FOUND_IN_ERETZ` | 5.428 (82 %) |
| `RESOLVED` | 1.095 |
| `AMBIGUOUS` | 74 |

De las no encontradas, **4.953 viven sólo en `inmobiliarias_staging`**. Sólo
230 son franquicias; **4.723 son inmobiliarias independientes comunes**.

**Elegibles para certificar hoy: 753** (`identity_status == READY`).

Estado de los 190 paquetes existentes:

| Estado | Paquetes |
|---|---|
| `IDENTITY_PENDING` | 140 |
| `CERTIFIED_COMPLETE` | 31 |
| `BLOCKED_EXTERNAL` | 15 |
| `CERTIFIED_BEST_AVAILABLE` | 3 |
| `NO_INVENTORY_CONFIRMED` | 1 |
| **`NEEDS_FIX`** | **0** |

### 2.2 Inventario ya extraído

Fuente: `PREINGESTION_REBUILD.sqlite3`, 189.159 filas. Reconstruido el
2026-09-03 en `ERETZ_PREINGESTION_REBUILD_20260903`; la base anterior era del
27 de agosto, **anterior al fix D-014**, así que sus números ya no valían.

| Estado | 27 ago | 3 sep |
|---|---|---|
| `AGENCY_ID_UNRESOLVED` | 127.595 | 127.595 |
| `CANDIDATE` (publicable) | 45.404 | **58.427** |
| `INVALID_OR_REJECTED` | 15.938 | **2.420** |
| `DUPLICATE_OR_CONFLICT` | 222 | 717 |

**+13.023 propiedades publicables**, un 28,7 % más. Las transiciones cierran
exactas: 13.023 `INVALID` → `CANDIDATE`, 493 `INVALID` →
`DUPLICATE_OR_CONFLICT`, 57 al revés, 2 `CANDIDATE` → `DUPLICATE`.

Las recuperadas son propiedades de verdad, no relleno: sobre una muestra de
4.000, el 100 % tiene URL, el 99,9 % título, el 84 % precio y moneda, el 90 %
descripción, el 82 % imágenes y el 61 % coordenadas. Se descartaban por no
traer `tipo_propiedad`, que en esa muestra es del 0 %.

Lo que les falta queda anotado en `_preingestion.campos_pendientes` —7.139 sin
operación, 3.777 sin ninguna de las dos, 1.929 sin tipo— y se publican igual.
Una señal de calidad para enriquecer después no es un motivo de descarte.

**Dos tercios de todo lo scrapeado sigue sin poder atribuirse** porque su
inmobiliaria no está en `main`. Ver §3.1.

### 2.3 Completitud de las 58.427 candidatas

Cubren 550 inmobiliarias.

| Campo | Cobertura | Filas |
|---|---|---|
| título | 100,0 % | 58.412 |
| moneda | 91,0 % | 53.194 |
| precio | 90,9 % | 53.088 |
| tipo de propiedad | 90,2 % | 52.721 |
| descripción | 89,8 % | 52.466 |
| imágenes | 85,1 % | 49.750 |
| operación | 81,3 % | 47.511 |
| latitud, longitud | 72,7 % | 42.499 |
| baños | 66,2 % | 38.667 |
| dormitorios | 58,8 % | 34.362 |
| ambientes | 58,5 % | 34.168 |
| dirección | 51,1 % | 29.872 |
| superficie cubierta | 47,7 % | 27.856 |
| barrio | 38,6 % | 22.559 |
| superficie total | 26,5 % | 15.484 |
| **ciudad** | **10,2 %** | 5.965 |

**La tabla anterior decía 100 % en operación y tipo, y era sesgo de
supervivencia:** todo lo que no los traía había sido descartado antes de
contar. Los porcentajes de ahora bajan en varios campos porque el denominador
creció un 28,7 %, pero en filas absolutas sube casi todo —las coordenadas pasan
de 34.961 a 42.499—. Son los primeros números honestos de esta tabla.

El dry-run de geografía no cambia: recorre las 189.159 filas sin importar su
estado, así que reclasificar candidatas no mueve sus 29.048 propuestas.
Verificado, no supuesto.

### 2.4 Cobertura: ninguna propiedad se pierde

Principio: **una propiedad válida no deja de mostrarse porque le falte un dato
enriquecible.** Medido sobre los 37 paquetes con corrida:

| Vía de pérdida | Propiedades |
|---|---|
| Detalles fallidos | 0 |
| Descartadas por el guardián de forma | 0 |
| Fichas sin contenido | 0 |
| Sin pedir por presupuesto | 0 |

**4.029 enumeradas → 4.029 guardadas: 100 %.** Los 126 duplicados de listado
son la misma URL repetida, y las 7.037 imágenes descartadas son *chrome* del
sitio, no propiedades.

Se corrigió además el punto donde sí se perdían: faltar operación o tipo las
marcaba `INVALID_OR_REJECTED` y no llegaban a la base. Eran 13.518 (D-014).

### 2.4 Rendimiento real del runner

74 corridas medidas:

| Métrica | Valor |
|---|---|
| Segundos por ficha | **2,0** |
| Segundos por corrida (mediana / p90 / máx) | 143 / 481 / 927 |

El cuello es el **límite de ritmo por host** (1,5 s), no la CPU.

### 2.5 Salud

`eretz-agency`: **1.346 tests pasan**, sin regresiones tras dieciocho defectos
cerrados, la geografía canónica y la compuerta de web oficial. Se partió de
1.233.

---

### 2.6 Web oficial: cuál se puede afirmar

Fuente: `web_identity_resolved.jsonl` (598 dominios descubiertos por el
resolver), pasada por `agency_official_web_gate.py` y
`agency_official_web_verify.py`.

El resolver decidía **una entidad por vez**, y esa era su limitación: un
verificador que mira una sola entidad no puede ver que 65 eligieron el mismo
host. De 598 dominios, **597 quedaron `OFFICIAL_WEB_HIGH_CONFIDENCE`** —o sea
que el estado no discriminaba nada— y `buscainmueble.com` figuraba como web
oficial de **65 inmobiliarias distintas**.

| Etapa | Entidades |
|---|---|
| Dominios descubiertos por el resolver | 598 |
| Descartadas: host reclamado por varias | 121 |
| Descartadas: el nombre no está en el dominio | 82 |
| Afirmables tras la compuerta | 395 |
| **Verificadas argentinas, abriendo el sitio** | **316** |
| Sin evidencia de país | 48 |
| No respondieron / sin texto / ccTLD extranjero / otro país | 31 |

Reglas, en orden:

1. La web oficial es un **origen**, no una página. 298 de 598 apuntaban a la
   ficha de una propiedad.
2. Un host que reclaman **varias entidades no identifica a ninguna**. La regla
   se demuestra con nuestros propios datos y voltea portales, colegios y redes
   de franquicia sin lista mantenida a mano.
3. El nombre tiene que estar en el **dominio**. La evidencia de nombre leída en
   la página no sirve, y se midió: `waze.com` y `signalhire.com` traen
   `nombre_exacto` igual que un sitio propio, porque un directorio que lista a
   una inmobiliaria menciona su nombre exacto.
4. Abrir el sitio y exigir evidencia argentina: dominio `.ar`, la palabra
   Argentina, o teléfono +54. **Un nombre de lugar no es evidencia de país**:
   la primera versión buscó localidades de GeoRef y dejó pasar a la Sandoval de
   **Ibiza**, cuya página dice "esquina" —palabra corriente en cualquier aviso
   y además localidad de Corrientes—. Tampoco alcanza con subir a provincias:
   Córdoba, La Rioja y Santa Fe son también provincias españolas.

**Qué destraba hoy, medido: casi nada.** De las 111 pendientes sin web, la
compuerta aporta una web verificada a **2**, y esas dos siguen frenadas por la
FK de ERETZ. Las otras 78 nunca tuvieron candidatos y encontrarlas exige una
API de búsqueda paga, descartada. El valor es hacia adelante: **308 de las 316
pertenecen a inmobiliarias que todavía no tienen paquete de certificación**. Es
un insumo puesto por anticipado, no un desbloqueo.

---

### 2.7 La misma propiedad publicada dos veces

Fuente: `PROPERTY_DUPLICATE_GROUPS.jsonl`, sobre las 13.322 candidatas con
firma completa (22,8 % del total; el resto no tiene con qué compararse).

El dedup que ya existía es por URL dentro de una misma inmobiliaria
(`hash_dedup`). No ve el caso de producto.

| Caso | Grupos |
|---|---|
| La **misma** inmobiliaria publicándola dos veces | 397 |
| Dos inmobiliarias distintas publicando la misma | 117 |
| Filas involucradas | 1.297 |
| Grupos con precios distintos | 297 |

**El caso más grande es dentro de una misma inmobiliaria.** Las dos URLs
difieren sólo en el id de la ficha —`257229-PH-en-Venta-…` y
`393830-PH-en-Venta-…`— con el mismo título y el mismo precio. `hash_dedup` no
puede verlo porque hashea la URL.

Los 117 entre inmobiliarias se reparten en **133 pares distintos**, y el par
más frecuente cubre 7. O sea que **no** es una inmobiliaria cargada dos veces
con otro nombre —eso sería identidad y se arreglaría en otro lado— sino
multi-listado real, que es como funciona el mercado.

**Agrupa y no elige ganador.** Cuál de las dos se muestra define quién se lleva
el clic: es una decisión comercial, no técnica, y borrar una la destruiría
antes de que nadie la tome. `ganadores_elegidos: 0`.

La firma es deliberadamente conservadora: coordenada a 5 decimales (~1,1 m),
que pierde duplicados cuando dos inmobiliarias geocodifican distinto —perder
uno es mejor que fusionar dos propiedades que no son la misma— y todos los
campos presentes, porque una firma con nulos no es identidad sino ausencia.
Dos unidades idénticas del mismo edificio caen igual en un grupo: otra razón
para no borrar.

#### Qué distingue a los miembros de un grupo

Fuente: `PROPERTY_DUPLICATE_EVIDENCE.jsonl`. La decisión de producto estaba
planteada sobre 514 grupos indistinguibles entre sí, y no son el mismo
problema. La pregunta que la vuelve decidible: **dentro de un grupo, los
miembros se diferencian en algo además del id de la URL?**

| Clase | Grupos | Misma inmob. | Entre inmob. |
|---|---|---|---|
| Puede haber dos unidades distintas | 207 | 111 | 96 |
| Mismo inmueble, precio distinto | 163 | 153 | 10 |
| Sólo texto o ubicación imprecisa | 72 | 65 | 7 |
| Mismo inmueble, datos contradictorios | 40 | 36 | 4 |
| **Idénticos en todo lo visible** | **32** | **32** | **0** |

**La comparación normaliza antes de decidir.** `Tissera Esquina Los Cedros` y
`Tissera esquina Los Cedros` son la misma dirección; comparadas crudas
mandaban el grupo a "dos unidades distintas" cuando lo único que cambiaba era
una mayúscula y un baño. Normalizar movió 72 grupos de esa clase a las de
inconsistencia, que es donde estaban. Es el mismo error de alfabetos distintos
que ya apareció entre la señal de fuente y su extracción, y van cuatro.

**Que difiera la cuenta de baños no prueba que sean dos propiedades.** Dos
fichas con la misma dirección, el mismo precio y la misma superficie cubierta
que discrepan en un baño son un dato mal cargado. Sólo la dirección y la
superficie distinguen de verdad, y ni siquiera ellas alcanzan: la firma ya
exige coordenada idéntica a ~1,1 m, y en un edificio las unidades apiladas
comparten coordenada —`Chacra del Norte 1 Piso 1` es un piso, no un duplicado—.

**Lo único demostrablemente colapsable son 32 grupos**, idénticos en los 17
campos visibles y todos dentro de una misma inmobiliaria: ahí no hay decisión
comercial que tomar, porque el clic va a la misma agencia en cualquier caso.
Los otros 482 siguen sin ganador. Los 163 de precio distinto no son un
duplicado a resolver sino una **contradicción a mostrar**: hoy el portal
enseñaría dos precios para el mismo inmueble sin decir cuál rige.

### 2.8 El quality gate sobre las 58.427

Fuente: `PROPERTY_QUALITY_GATE.jsonl` y su resumen, una fila por propiedad.
`database_writes: 0`.

**58.427 de 58.427 publicables. Cero pérdidas.** La regla se sostiene sobre
datos reales: una propiedad real incompleta sobrevive; lo que falta le quita
alcance, no existencia.

| Alcance | Propiedades | |
|---|---|---|
| FICHA | 58.427 | 100 % |
| LISTADO | 58.427 | 100 % |
| FILTRO_PRECIO | 53.088 | 90,9 % |
| FILTRO_TIPO | 52.721 | 90,2 % |
| FILTRO_OPERACION | 47.511 | 81,3 % |
| MAPA | 42.499 | 72,7 % |
| **FILTRO_CIUDAD** | **5.965** | **10,2 %** |

**La ciudad es el agujero, y con mucha diferencia.** 52.462 propiedades no
entran al filtro por ciudad, que es probablemente el primer filtro que usa
cualquiera que entra a buscar.

**Y el backfill pendiente no lo tapa.** Escribir las 22.158 propuestas aptas
—lo que hoy espera a que vuelva Postgres— llevaría el filtro por ciudad de
5.965 a **10.552**, del 10,2 % al 18,1 %. Sólo 4.587 propiedades ganan ciudad:
la mayoría de las propuestas confirman o corrigen un texto que ya estaba, no
llenan un hueco. Destrabar la base **no** arregla el filtro por ciudad, y darlo
por hecho habría dejado el problema abierto detrás de un blocker que se iba a
levantar solo.

De dónde sale el hueco que quedaría —47.875 propiedades—:

| Señal disponible | Propiedades | |
|---|---|---|
| **Tiene coordenada** | **35.644** | 74,5 % |
| Sólo provincia | 8.586 | 17,9 % |
| Sin coordenada, con barrio o dirección | 3.157 | 6,6 % |
| Sin ninguna señal de ubicación | 488 | 1,0 % |

Tres de cada cuatro tienen coordenada. Hoy la coordenada **sólo desempata**
candidatas que el nombre ya trajo (§3.3), así que no las alcanza. Resolverlas
exige una decisión de producto que el plan ya tomó en el otro sentido: el nivel
canónico es `localidades_censales`, y se descartó `municipios` por ser división
administrativa. Sin polígonos de localidad —GeoRef no los publica—, una
coordenada sola puede ubicar el departamento o el municipio, no la localidad.

**La pregunta es qué significa `ciudad` cuando lo único que hay es un punto en
el mapa.** Sostener `localidades_censales` deja esas 35.644 en `UNKNOWN`;
aceptar el municipio como respuesta de segunda, con la procedencia marcada,
las recupera al costo de mezclar dos niveles. No es una decisión técnica y no
la tomo solo.

**De dónde sale el diagnóstico de un ausente.** Con 30 de 767 agencias
certificadas: 11.206 campos `EXTRACTION_FAILED` —defectos nuestros—, 3.678
`SOURCE_NOT_PROVIDED` y 316.839 `AUSENTE_SIN_DIAGNOSTICO`, que es la verdad
mientras la cola no llegue. Los tres primeros defectos por volumen son
`superficie_total` (1.722), `ambientes` (1.500) y `ciudad` (1.421).

**Haber extraído un campo prueba que la fuente lo publica.** El detector de
señales mira el marcado y falla hacia el "no lo publica": `alpha inmobiliaria`
figuraba con `source_provided: 0` en `descripcion` y a la vez con las 127
descripciones extraídas. Leyendo sólo la señal, esas fichas exoneraban al
parser con un `SOURCE_NOT_PROVIDED` sobre un campo que la fuente evidentemente
publica. Eran 128 de 290 pares agencia/campo, el 44 %, y 1.480 campos sobre las
candidatas —con sólo 30 agencias certificadas—. Sumar la extracción como
evidencia sólo puede mover un campo hacia `EXTRACTION_FAILED`, o sea hacia
buscar defectos propios, que es el lado por el que hay que fallar.

---

## 3. Decisiones tomadas

### 3.1 Promoción de las 4.953 no promovidas

**Promover = insertar en `inmobiliarias_main` y asignar un `eretz_id` real.**
Es lo que habilita atribuir propiedades. `inmobiliarias_staging` es el buffer;
la promoción es un paso posterior y distinto, y **es escritura productiva**.

**El riesgo no es perder una fila: es crear una duplicada** de una inmobiliaria
que ya existe, partir su inventario y no poder distinguirla después de dos
negocios distintos. Ya ocurre en producción: `inmobiliaria salerno` (3535) y
`salerno inmobiliaria` (6334) son el mismo negocio.

Invariantes exigidas para promoción automática, todas demostradas:

1. el cruce con staging no es ambiguo;
2. no hay homónima en `main`;
3. no es parte de un grupo duplicado del universo canónico;
4. tiene web propia verificada o de alta confianza;
5. esa web no es perfil de portal ajeno ni sitio no inmobiliario;
6. el dominio no lo comparte con otra inmobiliaria.

La sexta importa: hay dominios de plataforma compartidos por inmobiliarias sin
relación, y `re max urbana` / `re max time` son sucursales distintas del mismo
dominio. **Un dominio no identifica a una inmobiliaria.**

Resultado (`scripts/agency_promotion_gate.py`, sin escribir en ninguna base):

| Estado | Antes | Ahora | Propiedades retenidas |
|---|---|---|---|
| `SAFE_TO_PROMOTE` | 939 | **733** | **63.831** |
| `REQUIRES_REVIEW` | 1.197 | 1.197 | — |
| `INSUFFICIENT_EVIDENCE` | 2.462 | 2.631 | — |
| `BLOCKED` | 355 | 392 | 3.966 |

La columna "ahora" es la clasificación con **evidencia web leída** (abajo). Las
733 son las 715 que sostienen su evidencia más 18 que estaban en
`INSUFFICIENT_EVIDENCE` con un único bloqueo —no tener web en el directorio—
cuya web existe y se leyó. Los 37 que pasan a `BLOCKED` son los dominios ajenos
y extranjeros. Las cuentas cierran exactas.

Motivos de bloqueo: 289 web no propia, **56 homónima en `main`**, 25 duplicada.

#### La evidencia web de las 939 nunca se había leído

La invariante 4 exige "web propia con identidad de confianza alta o
verificada". Las 939 la cumplen con `free_web_audit_v1`, **la auditoría que
puntuó URLs sin abrirlas**: 933 de ellas se apoyan en
`OFFICIAL_WEB_HIGH_CONFIDENCE`, que se midió y no discrimina nada —597 de 598
dominios descubiertos lo traen—. Ninguna de las 939 había pasado por el
resolver que sí abre la página.

Se abrieron las 939 (`scripts/promotion_web_recheck.py`, sin escribir en
ninguna base):

| Veredicto | Inmobiliarias |
|---|---|
| Sostiene su evidencia | 715 |
| Plausible, pero el dominio no lo prueba | 79 |
| Sin evidencia de país | 70 |
| No responde | 38 |
| **Dominio ajeno demostrado** | **24** |
| **Dominio de otro país** | **13** |

**24 apuntan a una web que es demostrablemente de otro:** el sitio de los
**Bomberos de San Lorenzo** (Casiana Severio Administración), el canal de
noticias **tn.com.ar** (Fast Propiedades), la web de **turismo municipal de Mar
del Plata** (Abdala Negocios Inmobiliarios), un planificador de viajes
(Coldwell Banker Patagonia), un portal de empleo (CENTURY 21 Mitoff). La página
ni siquiera nombra a la inmobiliaria.

Las 13 no son todas del mismo caso y necesitan ojo humano: `buscojobs.com.uy` o
`fotocasa.es` son dominios equivocados, pero `PropiedadesUY` y `Machado
Inmobiliaria` bajo `.com.uy` parecen inmobiliarias **uruguayas** dentro de un
universo argentino, que es otra pregunta.

**La invariante 4 pasó a exigir evidencia leída**, en los dos sentidos: una web
que se abrió y sostiene la identidad promueve aunque el directorio no la
conociera, y una que se abrió y resultó ajena bloquea, porque mirar es más
fuerte que cualquier estado declarado. Un `OFFICIAL_WEB_HIGH_CONFIDENCE` que
nadie leyó ya no alcanza para insertar una fila en `main`.

**Hallazgo aparte:** esas 56 **no son inmobiliarias nuevas**. Ya existen en
`main` con el orden de palabras invertido —`bechara inmobiliaria` es
`Inmobiliaria Bechara`, id 2654—. Retienen **1.140 propiedades** que se
desbloquean **vinculándolas al id existente, sin crear nada**. Es una acción
distinta y más segura que promover.

Dry-run en `AGENCY_MAIN_LINK_DRYRUN.jsonl`:

| Acción | Inmobiliarias |
|---|---|
| `LINK_TO_EXISTING` (una sola candidata) | 54 |
| `REQUIRES_REVIEW` (varias candidatas) | 2 |

Las 2 en revisión tienen dos candidatas cada una —`inmobiliaria up` apunta a
3019 y 3305, o sea que `main` ya tiene ahí su propia duplicada—. Coincidir el
conjunto de palabras es evidencia fuerte pero no prueba: elegir la primera
sería inventar la identidad.

**Estado: preparado hasta dry-run**, con `writes_a_new_row: false` en todas las
filas. La escritura en `main` queda del otro lado de la barrera de §8.

### 3.2 Rollout de la corrida masiva

Prioridades, en orden: no dañar fuentes › no perder inventario › no duplicar
procesos › recuperabilidad › throughput.

**La concurrencia dentro de un mismo host está descartada por evidencia**: a
2,0 s por ficha el sistema es límite-de-ritmo, no CPU. Subir workers sobre un
host sólo lo golpea más fuerte sin ganar throughput. El único acelerador
legítimo sería paralelizar **entre hosts distintos**, y eso compromete las
prioridades 3 y 4, que están por encima de la 5. **No se habilitó.**

Implementado:

| Mecanismo | Qué resuelve |
|---|---|
| Cerrojo de instancia única con PID | Dos runners se pisan el cursor y golpean las fuentes al doble de ritmo |
| Latido por inmobiliaria, vence a 1 h | Un proceso muerto no traba la cola para siempre (4× la corrida más larga observada) |
| `--limit N` | Lotes acotados sin cambiar de modo |
| `--ready` | Corre las 753 elegibles, no las 6.597 |
| `RUNNER_ERROR` no terminal | Un fallo aislado no tumba la corrida; la fuente vuelve sola a la cola |
| `AGENCY_DEFECT_QUEUE.jsonl` | Los defectos siguen visibles con `--continue-after-fix` |
| Checkpoint antes y después de cada agencia | Reanudación exacta |
| `agency_rollout_preflight.py` | Seis chequeos antes de abrir; sale distinto de cero si alguno falla |

Flujo: `terminal sano → persistir → siguiente`; `NEEDS_FIX → persistir → detener`.

**Impacto de los cambios, calculado por huella y no por reflejo: 36
certificaciones a rehacer**, no las 6.597 del universo.

### 3.3 Geografía de `ciudad`

Jerarquía de evidencia, de mayor a menor:

1. ciudad estructurada por la fuente → `SOURCE_STRUCTURED`
2. ciudad explícita en dirección o metadata confiable → `SOURCE_TEXT`
3. normalización contra catálogo canónico → `CANONICAL_NORMALIZED`
4. coordenadas, sólo como evidencia complementaria → `GEOCODED`
5. si no se puede demostrar → `UNKNOWN`

Prohibido: `provincia → ciudad`, y `coordenada aproximada → ciudad exacta`.

**Estado: V1 CERRADO** en todo lo que no depende de la base productiva.
Documentación completa en [`ERETZ_CANONICAL_GEOGRAPHY.md`](ERETZ_CANONICAL_GEOGRAPHY.md).

Integrada en el pipeline (`Connector._resolver_geografia`, llamado desde
`completar_ubicacion`): una sola lógica canónica para todos los connectors,
snapshot local, cero consultas remotas por propiedad, 0,509 ms cada una. El
backfill invoca **el mismo código**, no una copia.

**Fuente adoptada: GeoRef Argentina** (Servicio de Normalización de Datos
Geográficos, datos.gob.ar). Oficial, gratuita, sin credenciales. Snapshot local
en `ERETZ_GEO/`, bajado el 2026-09-02 con `scripts/geo_snapshot.py`, con
`MANIFEST.json` que guarda url, fecha, totales, vía y sha256 por recurso.

| Recurso | Filas | Vía |
|---|---|---|
| provincias | 24 | volcado |
| departamentos | 529 | volcado |
| municipios | 2.082 | API (no está en el volcado) |
| **localidades censales** | **4.023** | volcado |
| localidades | 4.028 | volcado |
| asentamientos | 14.466 | volcado |

Para actualizarlo se vuelve a correr el script: reescribe el manifiesto y los
sha256 permiten comparar versiones y ver si cambiaron ids o nombres. La API
topea `max + inicio` en 10.000, por eso `asentamientos` sólo sale del volcado.

**Decisiones tomadas sobre los datos, no supuestas:**

- El nivel canónico de ciudad es **`localidades_censales`**. No
  `asentamientos`, que son las mismas más 10.425 parajes: pasaría de 270
  nombres repetidos a 1.545 y haría matchear el Paraje Alberdi de Chaco con una
  propiedad de Córdoba. No `municipios`, que son división administrativa.
- **CABA no tiene localidad censal**: está partida en quince comunas. Resuelve
  a la provincia, porque nadie publica "CABA - Comuna 4" como ciudad.
- `<Provincia> Capital` sale del catálogo —localidad homónima de su provincia,
  o departamento capital donde el nombre no coincide, como Tucumán— sin
  escribir a mano ninguna correspondencia.
- Las coordenadas **sólo desempatan** candidatas que el nombre ya trajo, y sin
  radio absoluto: la separación entre homónimas es bimodal (p5 = 0,8 km contra
  mediana de 400 km).

**La prueba de que hacía falta un catálogo y no una tabla de excepciones:** en
GeoRef **no existe ninguna localidad llamada `Alberdi`**. Hay `Alberdi Viejo`,
`Colonia Alberdi`, `Villa Alberdi` y dos `Juan Bautista Alberdi`. El único
`Alberdi` exacto del país es un Paraje en Chaco. GeoRef no cataloga barrios.

**Resultado medido** sobre las 31.444 propiedades con ciudad publicada:

| Resolución | % |
|---|---|
| `EXACT_CANONICAL` | 37,2 |
| `NOT_FOUND` (casi todo barrios) | 33,2 |
| `ALIAS_MATCH` | 12,2 |
| `AMBIGUOUS` | 6,3 |
| `CONTEXT_MATCH` | 5,2 |
| `CONTRADICTED_BY_COORDINATES` | 4,5 |
| `COORDINATE_SUPPORTED` | 1,3 |

**56,0 % resueltas y cero falsos positivos** a más de 100 km, contra 12,63 %
antes del control de contradicción. El p95 de distancia entre la propiedad y su
localidad cayó de 1.034 km a 15,2 km. Cuesta 0,509 ms por propiedad, sin una
sola consulta remota.

Validación estratificada (`scripts/geo_validacion.py`, informe en
`ERETZ_GEO/VALIDACION_GEOGRAFICA.json`):

| Estrato | n | Resueltas |
|---|---|---|
| Barrio publicado como ciudad | 1.901 | **0,0 %** |
| Forma comercial o capital | 3.478 | **100,0 %** |
| Con ciudad sin coordenada | 6.432 | 68,1 % |
| Con ciudad y coordenada | 19.633 | 49,7 % |

Los barrios **nunca** se convierten en ciudad, y las formas comerciales
resuelven todas. El estrato con coordenada resuelve menos justamente porque ahí
el control de contradicción actúa.

**Dry-run listo hasta la barrera** (`scripts/geo_dryrun.py`,
`ERETZ_GEO/CIUDAD_DRYRUN.jsonl`, `database_writes: 0`): sobre las 189.159 filas
produce **17.608 propuestas** de ciudad con procedencia — 3.709 corrigen el
texto publicado y 13.899 lo confirman con id oficial. Las 42 correcciones
distintas son todas normalizaciones al nombre oficial (`Capital Federal` →
`Ciudad Autónoma de Buenos Aires`, acentos, mayúsculas); **ninguna cambia de
lugar una propiedad**.

Se distingue el origen de la evidencia: `SOURCE_STRUCTURED` cuando el connector
la saca de un campo propio de la fuente (wasi, century21) y `SOURCE_TEXT`
cuando es una lectura nuestra. No valen lo mismo.

**Dos correcciones que salieron de medir contra los datos reales, no de los
tests** —la regla de §1.1 otra vez:

1. El campo `provincia` trae basura: `"GBA Sur"`, `/api/v1/state/149/`.
   Tratarla como contradicción dejaba sin ciudad a **1.498 avisos de La Plata**.
   Un valor que no nombra una provincia no puede contradecir a una.
2. `argentinasothebysrealty.com` publica `ciudad = CABA` en avisos cuyas
   coordenadas caen a 3,7 km de Lago Moreno, Río Negro: el campo tiene **la
   oficina de la inmobiliaria, no la propiedad**. Eran **1.422 casas de
   Bariloche afirmadas como porteñas**.

### 3.4 Las 29.048 propuestas de ciudad no estaban listas

Fuente: `CIUDAD_DRYRUN_AUDIT.jsonl`. `database_writes: 0`.

El dry-run quedó anotado como "29.048 propuestas listas", esperando únicamente
que volviera Postgres. **La primera fila del artefacto propone `Villa del
Parque` —un barrio de CABA, con `Melincué al 2600`, una calle de CABA— como
localidad de Río Negro.** La segunda propone `Barrio Norte`, también de CABA,
también a Río Negro. Son nombres de barrio que existen como localidad censal en
otra provincia, y lo único que los sostiene es el nombre.

El control de contradicción por coordenadas no puede intervenir: estas filas no
tienen coordenada. Y el plan ya lo había anticipado en otra forma —"GeoRef no
cataloga barrios", y el caso `Alberdi` está documentado como la razón para no
hacer exactamente esto—; lo que faltaba era aplicarlo también cuando el nombre
sale del campo `barrio`.

**El criterio es la corroboración, no el origen.** Una propuesta se sostiene
cuando algo además del nombre la respalda: la provincia que publicó la fuente,
el apoyo de una coordenada, o el desempate por contexto.

| Clase | Propuestas |
|---|---|
| Aptas para escritura | 22.158 |
| Nombre de barrio sin corroborar | 5.730 |
| Nombre de ciudad sin corroborar | 1.160 |

**Qué se descartó por el camino.** Contradecir con la provincia dominante de la
propia inmobiliaria parecía razonable y es falso: marcaba 127 propuestas, y las
que miré son correctas —una agencia de Río Negro vendiendo en Plottier o
Centenario, que son de Neuquén y están al lado—. Habría rechazado respuestas
buenas para atrapar unas pocas malas.

**El costo es asimétrico y por eso se retiene.** Perder la ciudad no pierde la
propiedad: por contrato conserva ficha y listado, y sólo pierde el filtro por
ciudad. Una ciudad falsa no se nota, no se revierte sola, y manda a una persona
a buscar en la provincia equivocada.

Las 5.730 no son irrecuperables: una coordenada, o la provincia publicada,
alcanzan para resolverlas. Quedan en `UNKNOWN` hasta tenerlas.

**La corrección del resolver entra en la próxima ventana sin certificación en
vuelo**, junto al milestone 2: vive en `Connector._resolver_geografia`, o sea
en `connectors/base.py`, y tocarlo invalida la huella de todas las estrategias.

### 3.5 La ventana semántica del 6 de septiembre

Se aplicaron juntos los tres cambios que compartían radio transversal, porque
`shared/base` y `shared/geografia` entran en el conjunto de componentes de toda
estrategia: agrupados cuestan **48 recertificaciones una vez**; separados, tres
veces eso.

**AMI Propiedades.** Publica sus 27 propiedades en un `<select>` "POR CÓDIGO" y
en ningún `<a>`. Leyendo sólo `href`, un sitio entero con catálogo declarado
figuraba como `SIN_INVENTARIO` y el triage lo paró como posible pérdida de
inventario — que es exactamente lo que era. La solución no es por dominio: un
`<select>` cuyas opciones apuntan a tres o más documentos del propio sitio **es**
el índice del catálogo. Lo dice el sitio con su navegación, que es mejor
evidencia que cualquier patrón de URL. Cerró `CERTIFIED_COMPLETE`, 27,
idempotente.

**Normalización de texto.** `normalizar_texto_campos` era una tabla escrita a
mano con cuatro reemplazos: cubría la palabra que alguien recordó el día que la
vio romperse. Ahora delega en `connectors/texto.py`, que repara el mojibake
demostrable y reconoce contra un vocabulario declarado los tokens donde la
fuente ya perdió el byte. Vuelven también `Descripción`, `Antigüedad`,
`Código`, `Año` y el resto, sin escribir una línea por palabra.

**Un tercer agujero de huella.** `connectors/coherencia.py` —que decide qué
atributos se descartan— lo importa `generico.py` desde siempre y no era
componente de ninguna huella: cambiar esa regla habría cambiado lo que se
extrae sin invalidar una sola certificación. Ya van tres, y en las dos
direcciones. Ahora hay dos tests que lo detectan solos, comparando **payloads**
y no nombres: `formularios.py` viaja como `strategy/php_form_transport` y
buscarlo por nombre lo daría por huérfano cuando está correctamente acotado.

**Orden de la cola.** Canarios por familia, después bulk, y la cola larga —las
que nos rechazan o agotan el presupuesto— al final. `alta`, `alma di matteo`,
`altos servicios` y AMI fueron cuatro paradas de la misma clase de problema, y
cada una costó una ventana. El universo no cambia: cambia el orden.

**Dos workers.** La cola es 99,65 % I/O. El reparto es **por host**, no por
posición: la cortesía se le debe al sitio y el limitador vive dentro de cada
proceso, así que dos workers sobre el mismo host pedirían al doble del ritmo
acordado sin que ninguno se entere. Sobre las 767 hay 765 hosts distintos, y el
reparto queda 391/376. `append_jsonl` pasó a ser un `os.write` sobre `O_APPEND`
—una sola llamada al sistema— porque un `write` partido dejaría media línea de
un proceso dentro de la línea del otro, en el archivo que es la fuente de
verdad de las certificaciones. Un STOP transversal escribe una bandera que
corta a los dos.

---

## 4. Defectos

| # | Defecto | Estado | Impacto medido |
|---|---|---|---|
| D-001 | Landing de Bitrix24 no reconocida | cerrado | Alcami: 0 → 3 propiedades |
| D-002 | La certificación contaba cadenas, no identidades | cerrado | 0 colisiones previas; guardia preventivo |
| D-003 | Una excepción tumbaba la corrida entera | cerrado | 0 crashes en 24 corridas |
| D-004 | Evidencia congelada en un literal | cerrado | 4.953 clasificadas sobre una afirmación no verificada |
| D-005 | Tokko guardaba prosa como barrio | cerrado | 1.145 fichas |
| D-006 | Operación no leída de la forma verbal | cerrado | 117 filas, 53 publicables |
| D-007 | Tokko adivinaba el tipo | cerrado | 899 fichas sin tipo |
| D-008 | **Página vacía guardada como propiedad** | cerrado | 351 fichas; tipo inventado |
| D-009 | Cero heredado del connector equivocado | cerrado | Requena: 0 → 141 |
| D-010 | Sitemap con fichas de otro host | cerrado | Identidad en host ajeno |
| D-011 | Tipo declarado en la ficha, ignorado | cerrado | 35 de 193 en berrueta |
| D-012 | **Contador del sitio usado como verdad** | cerrado | berrueta: el sitio declara 197 y sirve 193 |
| D-013 | **Atributos tabulados leídos al revés** | cerrado | 1.056 combinaciones imposibles, todas en `generico` |
| D-014 | Propiedad incompleta tratada como inválida | cerrado | **13.518 propiedades no llegaban a la base** |
| D-015 | **Fotos de otras propiedades atribuidas al aviso** | cerrado | 84.378 imágenes ajenas en 6.584 propiedades |
| D-016 | Negarse a afirmar leído como fallo de extracción | cerrado | Bloqueaba inmobiliarias correctas |
| D-017 | Corrida truncada juzgada por idempotencia | cerrado | Razón engañosa; mandaba a buscar un bug inexistente |
| D-018 | Presupuesto plano y duplicado en tres lugares | cerrado | **Dos inmobiliarias no podían certificar nunca** |
| D-019 | Ruido de la fuente confundido con extracción inestable | cerrado | Bloqueo indefinido por un atributo opcional |
| D-020 | Tabla de atributos con encabezados; rótulos compuestos | cerrado | Valores del campo vecino, coincidentes por azar |
| D-021 | Descripción leída por clase CSS y no por rótulo | cerrado | 0 → 11 de 11 en una inmobiliaria |

**`NEEDS_FIX` abiertos: 0.** Verificado por
`scripts/agency_rollout_preflight.py`.

### El patrón que se repitió cinco veces

**Negarse a afirmar no es fallar al extraer.** La certificación distingue
`EXTRACTION_FAILED` —defecto nuestro, bloquea— de `REJECTED_BY_VALIDATION` —la
validación funcionando—. El pipeline decide honestamente no contestar en cinco
lugares distintos: ciudad desmentida por la coordenada, ciudad que era barrio,
barrio promovido a ciudad, rótulo que funde dos atributos, y homónima sin
contexto. Los cinco se leían como si hubiéramos fallado, y bloquearon
inmobiliarias que estaban perfectas.

Los arreglé de a uno hasta que quedó claro que era una sola regla. **Si la
fuente publicó un valor y no lo afirmamos, ese valor se rechazó.**

### El otro patrón: cuatro reglas rotas por la misma vocal

Distinto del anterior y todavía sin arreglar de raíz. Cuatro veces una regla
falló porque comparó texto sin normalizar, y las cuatro veces la arreglé
dentro de la regla:

1. `_es_tabla_estructurada` no veía `Baños` con la ñ rota y leía prosa donde
   había tabla.
2. La señal de fuente y su extracción usaban alfabetos distintos, y un campo
   publicado figuraba como no publicado.
3. `RE/MAX` no matcheaba `remax`, y `Remax Cuore` quedaba fuera de su propia
   verificación de web.
4. `Tissera Esquina Los Cedros` y `Tissera esquina Los Cedros` contaban como
   direcciones distintas, y 72 grupos duplicados salieron clasificados como
   "pueden ser dos unidades" por una mayúscula.

Cada arreglo fue correcto y ninguno fue el arreglo. **La normalización de
texto tiene que ser un paso del pipeline, no una defensa que cada regla se
pone por su cuenta**: mientras sea per-regla, la quinta regla que se escriba va
a nacer rota igual que las cuatro anteriores.

Entra en la misma ventana sin certificación en vuelo que el resolver de
geografía: vive en `connectors/`, así que invalida huellas.

### Los cinco que importan

**D-016 — la diferencia entre no poder y no querer.** La certificación
distingue `EXTRACTION_FAILED` (defecto nuestro, bloquea) de
`REJECTED_BY_VALIDATION` (la validación funcionando). La geografía vacía un
campo en tres situaciones distintas —un barrio en el campo ciudad, una
coordenada que desmiente, una homónima sin contexto— y las tres se leían como
si hubiéramos fallado al extraer.

Bloqueó dos inmobiliarias que estaban perfectas. `aagaard` tenía 301
identidades, 0 colisiones e idempotencia, y quedaba en `NEEDS_FIX` porque 38
promociones correctas de barrio a ciudad se contaban como 38 barrios perdidos.

Los arreglé de a uno, cada vez que uno frenaba la cola, hasta que quedó claro
que era una sola regla: **si la fuente publicó un valor y no lo afirmamos, ese
valor se rechazó.** El tercer caso lo cerré antes de que frenara nada.

**D-015 — la foto de la casa de al lado.** El chequeo de idempotencia marcó que
una de 88 fichas cambiaba de fotos entre dos corridas separadas por segundos.
No era el sitio cambiando: `azpropiedades.com` pone al pie un carrusel de
relacionadas, cada una un enlace a otra ficha con su miniatura adentro.
Extraer imágenes del documento entero le pegaba a cada aviso **las fotos de sus
vecinos**, y como el bloque rota, cada rotación se leía como un cambio.

Verificado contra la página: las cuatro miniaturas de esa ficha estaban las
cuatro dentro de enlaces a **otras** propiedades. Ninguna era suya. Mostrarle a
alguien la foto de otra casa es peor que no mostrarle ninguna.

La regla es estructural, no un filtro por nombre de archivo: una imagen
envuelta en un enlace a otra **página** no es de esta propiedad. Las galerías
con lightbox no se tocan —ahí el href es el archivo— ni la foto enlazada a la
propia ficha.

**D-012 — el denominador no era verdad.** Lo describí como "falla por 0,0003",
lo que sugiere un borde de precisión. No lo es: 193/197 = 0,97969 y en enteros
hacen falta 194. Enumerando el catálogo a mano por su scroll infinito, el sitio
sirve **194 fichas y la 194 es `/propiedad/0`, que devuelve el catálogo
entero**. O sea 193 reales, exactamente las que trajo el connector: **el
contador del sitio está inflado en 4**.

No se tocó el umbral. Faltaba una distinción: el bucle cortaba igual ante un
error de descarga que al llegar al final. Agotar la paginación por debajo del
total declarado es una limitación documentada
(`DECLARED_TOTAL_ABOVE_ENUMERATION` → `CERTIFIED_BEST_AVAILABLE`); que la
interrumpan sigue siendo `NEEDS_FIX`, porque cortar por un error no prueba nada
sobre el inventario restante. La pérdida grave la sigue atajando
`collapse_ratio`, que compara contra lo que **esta inmobiliaria tenía**.

**D-008 — la ausencia convertida en afirmación.** Dos fichas volvieron vacías y
el pipeline las guardó con el nombre del sitio por título y un tipo
**adivinado**. Si ambas corridas hubieran fallado igual, se habría certificado
`CERTIFIED_COMPLETE` con propiedades fantasma. Sólo el chequeo de idempotencia
lo delató. El guardia exige ahora dos condiciones —sin datos publicados **y**
título igual al del sitio—, porque sólo la primera habría tirado 254 lotes
reales.

**D-013 — el valor del campo vecino.** `Ambientes 3 Dormitorios 2` sin dos
puntos se leía buscando el número *antes* del rótulo: `dormitorios` tomaba el 3
de ambientes y `ambientes` el 2 de `196 m2`. No un campo vacío — un valor
equivocado que parece correcto. La ambigüedad no estaba en la regla: estaba en
haber aplanado el HTML. Se lee de la estructura
(`<span>Ambientes</span><span>3</span>`).

---

## 5. Arquitectura

```
Descubrimiento → Directorio de plataformas → Resolución de identidad
                                                      │
                          ┌───────────────────────────┤
                          ▼                           ▼
                 identity READY (753)         staging sin promover (4.953)
                          │                           │
                          ▼                    gate de promoción
                  Cola de certificación         (733 / 1.197 / 2.631 / 392)
                          │                           │
              connector + estrategia            [BARRERA: escritura en main]
                          │
                 dos corridas en vivo
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
   CERTIFIED_*      NO_INVENTORY_*     NEEDS_FIX → detener, diagnosticar
        │
        ▼
   Pre-ingesta (189.159) → quality gate → CANDIDATE (45.404)
                                                │
                                        [BARRERA: publicación]
```

---

## 6. Blockers

| Blocker | Qué frena | Necesita |
|---|---|---|
| Promoción a `main` | 63.831 propiedades atribuibles (733 inmobiliarias) | Autorización de escritura productiva |
| Vinculación de las 56 homónimas | 1.140 propiedades | Autorización de escritura productiva |
| **Postgres de producción caído** | Promoción, vinculación y escritura de ciudad | `PGRST002`: PostgREST responde, la base detrás no |
| Escribir `ciudad` sobre lo ya extraído | **22.158** propuestas aptas; 6.890 retenidas (§3.4) | Que vuelva la base |
| Polígonos de localidad | 40.635 propiedades con coordenada y sin ciudad | GeoRef no los publica en estos recursos |
| 2.462 sin web conocida | Su promoción y certificación | 316 webs oficiales ya verificadas (§2.6); las 78 sin candidatos necesitan API de búsqueda paga |

---

## 7. Próximos milestones

1. **Cerrar la cola `--ready`** (753, ~91 h de ejecución medida). En curso.
2. **Geografía.** El cableado ya está: vive en `Connector._resolver_geografia`
   para los connectors, y el quality gate ahora consulta las propuestas aptas y
   reporta el alcance proyectado aparte del real. Lo que queda son dos cosas
   distintas:
   - **Corregir el resolver** para que un nombre que sale del campo `barrio` no
     resuelva a una localidad de otra provincia sin corroboración (§3.4). Vive
     en `connectors/base.py`, así que necesita un punto sin certificación en
     vuelo: tocarlo cambia la huella de todas las estrategias.
   - **Decidir qué significa `ciudad` cuando sólo hay una coordenada** (§2.8).
     Son 35.644 propiedades, tres de cada cuatro de las que quedarían sin
     ciudad. No es técnica: el plan ya descartó `municipios` como nivel
     canónico, y recuperarlas obliga a revisar esa decisión o a dejarlas en
     `UNKNOWN`.
3. ~~Cablear las webs verificadas y la base canónica.~~ **Hecho.**
   `AGENCY_OFFICIAL_WEB_VERIFIED.jsonl` entra por `load_catalog` y
   `resolve_identity` lo prefiere al directorio; el default de la base sale del
   manifiesto, no de una ruta escrita a mano. Se probó que ambas bases dan la
   misma línea base —189.159 filas, 1.724 ids, cero conteos distintos—, así que
   corregirlo no invalidó ninguna certificación.
4. **Vinculación e ingesta** una vez levantada la barrera.
5. **Decidir qué se hace con los grupos duplicados** (§2.7). La evidencia ya
   está: 32 grupos son idénticos en todo lo visible y todos de una misma
   inmobiliaria —ahí no hay decisión comercial—, y 163 muestran dos precios
   para el mismo inmueble. Los 482 restantes siguen sin ganador.
6. Contrato de propiedad, ciclo de vida, quality gate, publicación. El gate ya
   corrió sobre las 58.427: **58.427 publicables, cero pérdidas** (§2.8).

La geografía es una **dependencia** del contrato de propiedad y del filtro de
búsqueda, no una misión aparte: entra en el DAG entre la normalización y el
quality gate.

---

## 8. Barrera de autorización

Requieren autorización humana explícita: escritura o modificación en base
productiva; borrado; migraciones; permisos o RLS; deploy público; `git push`;
merge; DNS; indexación pública; servicios pagos; secretos.

No la requieren: analizar, programar localmente, refactorizar, correr tests,
dry-runs, investigar, generar reportes, crear scripts, validar webs y ejecutar
procesos locales seguros.
