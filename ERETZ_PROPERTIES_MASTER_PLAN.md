# ERETZ — Plan maestro del sistema de propiedades

Documento vivo. Cubre el dominio completo de propiedades: descubrimiento de
inmobiliarias, adquisición de datos, calidad, experiencia pública, operación
diaria y observabilidad.

Última actualización: 2026-09-02.

---

## 1. Principios que gobiernan las decisiones

Estos no son preferencias de estilo. Cada uno viene de un error real, y su
violación produce datos que después no se pueden distinguir de los buenos.

1. **La ausencia de información nunca se convierte en afirmación.** Un campo
   que la fuente no publica queda `None`, nunca en cero ni inferido. Los
   estados posibles son `EXTRACTED`, `SOURCE_NOT_PROVIDED`,
   `REJECTED_BY_VALIDATION` y `EXTRACTION_FAILED`, y son distintos entre sí.
2. **`NEEDS_FIX` nunca es un cierre.** Los estados terminales válidos son
   `CERTIFIED_COMPLETE`, `CERTIFIED_BEST_AVAILABLE`, `NO_INVENTORY_CONFIRMED`,
   `BLOCKED_EXTERNAL`, `IDENTITY_PENDING` e `INACTIVE`.
3. **Cero inventario se demuestra, no se supone.** La regla
   `LOW_INVENTORY_0_11` obliga a revisión exhaustiva entre 0 y 11 propiedades.
   Un cero sin prueba es un hueco de cobertura disfrazado de hecho comercial.
4. **No declarar terminado algo porque no hubo excepción.** La falta de error
   no es evidencia de corrección.
5. **La identidad no se inventa en el connector.** Se reusa `hash_dedup` del
   pipeline: `SHA256("{inmobiliaria_id}|url|{url_normalizada}")`.
6. **Una propiedad que hoy no aparece no es una baja.** Puede ser un timeout o
   un sitio caído; la baja exige varias corridas coincidentes y comparables.

---

## 2. Estado medido

Todos los números son medidos, con su fuente. No hay estimaciones.

### Cola de certificación

Fuente: `ERETZ_AGENCY_CERTIFICATION_20260827/AGENCY_CERTIFICATION_PROGRESS.json`
(heartbeat 2026-09-01T15:12:33).

| Métrica | Valor |
|---|---|
| Universo de inmobiliarias | 6.597 |
| Cursor global | 179 |
| Certificadas | 187 |
| Pendientes | 6.410 |

Cobertura: **2,8 %** del universo. El grueso del trabajo está por delante.

### Distribución de estados

Fuente: 188 paquetes en `agencies/*/certification.json`, medido 2026-09-02.

| Estado | Paquetes |
|---|---|
| `IDENTITY_PENDING` | 140 |
| `CERTIFIED_COMPLETE` | 30 |
| `BLOCKED_EXTERNAL` | 15 |
| `CERTIFIED_BEST_AVAILABLE` | 2 |
| `NO_INVENTORY_CONFIRMED` | 1 |

`IDENTITY_PENDING` es 140 de 188 paquetes (74 %): **la resolución de identidad
es el cuello de botella dominante**, no la extracción. Sólo 35 paquetes
llegaron a ejecutar una estrategia de connector; el resto se detuvo antes, sin
poder afirmar a qué inmobiliaria real corresponde la fuente.

### Por qué está bloqueada la identidad

Razones registradas en los 140 paquetes `IDENTITY_PENDING` (2026-09-02):

| Razón | Paquetes |
|---|---|
| `canonical agency lacks a resolved ERETZ foreign key` | 134 |
| `live identity was not validated` | 134 |
| `official website unavailable` | 111 |

**111 de 140 no tienen sitio web conocido**: `official_url` es `None`. No hay
nada que certificar. El bloqueo dominante no es la extracción ni el connector,
es el descubrimiento. Las 29 restantes sí tienen web pero no resuelven la
clave foránea.

### Presencia web conocida del universo

Fuente: `agency_platform_directory.jsonl`, 2.596 entradas, 99,9 % con dominio.

| Clasificación | Entradas |
|---|---|
| `OFFICIAL_WEB` | 2.085 |
| `EXTERNAL_PORTAL_PROFILE` | 384 |
| `OFFICIAL_OFFICE_PAGE` | 79 |
| `NOT_A_REAL_ESTATE_WEB` | 23 |
| `AMBIGUOUS_WEB_ATTRIBUTION` | 22 |

El directorio cubre 2.596 de las 6.597 del universo: **unas 4.000
inmobiliarias todavía no tienen presencia web clasificada**.

Plataformas detectadas: TOKKO 848, `UNKNOWN` 509, sitio propio 360,
WordPress 357, `SIN_CLASIFICAR` 239, Next.js 75, WASI 39, Laravel 32.
**TOKKO solo concentra un tercio de los sitios conocidos**: es el objetivo de
mayor apalancamiento por unidad de esfuerzo.

### Resolución de identidad en el universo completo

Fuente: `AGENCY_ID_RESOLUTION_FINAL.jsonl`, 6.597 inmobiliarias (2026-09-02).

| Resolución | Inmobiliarias |
|---|---|
| `NOT_FOUND_IN_ERETZ` | 5.428 (82 %) |
| `RESOLVED` | 1.095 |
| `AMBIGUOUS` | 74 |

De las no encontradas, **4.953 son `STAGING_NAMESPACE_NOT_A_MAIN_FK`**:
existen en el namespace de staging y no tienen contraparte en la tabla `main`
de ERETZ.

Verificado localmente contra el backup `2026-05-27_inmobiliarias_main.csv`
(7.004 filas): de esas 4.953, **0 tienen match por nombre normalizado en
`main`**. El método se validó con un grupo de control —las 1.095 resueltas por
nombre exacto dan match 1.095/1.095—, así que el cero es un hecho, no un fallo
de la comparación.

Composición de esas 4.953: sólo 230 son sucursales de franquicia (RE/MAX 159,
Century 21 35, Coldwell 30, Keller Williams 6). Las otras **4.723 son
inmobiliarias independientes comunes**.

**Lectura.** No es un defecto de datos: son ~4.953 inmobiliarias descubiertas
por el scraping de portales que todavía no fueron promovidas al maestro de
ERETZ. Certificarlas antes de promoverlas produce propiedades que no se pueden
asociar a ninguna fila de `main`. Ver §7.

### Integridad de identidad

Auditoría de los 35 paquetes con propiedades persistidas (2026-09-02):
**0 colisiones de identidad**. Ninguna certificación previa informó más
propiedades de las que la base habría guardado.

### Inventario de propiedades ya extraído

Fuente: `PREINGESTION_REBUILD.sqlite3`, 189.159 filas (2026-09-02).

| Estado | Filas |
|---|---|
| `AGENCY_ID_UNRESOLVED` | 127.595 (67,5 %) |
| `CANDIDATE` (publicable) | 45.404 |
| `INVALID_OR_REJECTED` | 15.938 |
| `DUPLICATE_OR_CONFLICT` | 222 |

**127.595 propiedades ya extraídas no se pueden atribuir a ninguna
inmobiliaria de `main`.** Es la misma causa de §7.1, medida en propiedades en
vez de en inmobiliarias: dos tercios de todo lo scrapeado espera una decisión
de promoción.

Entre los rechazos: 13.518 `RAW_ELIGIBLE_NOT_PUBLISH_ELIGIBLE` y 2.401
`EXTERNAL_PORTAL_PROFILE`. Entre los conflictos, **165
`MULTI_AGENCY_NORMALIZED_URL`**: una misma URL normalizada reclamada por más
de una inmobiliaria — la misma clase de problema de identidad que D-001, en el
otro extremo del pipeline.

### Completitud de campos de las 45.404 candidatas

Cubren 520 inmobiliarias distintas.

| Campo | Cobertura |
|---|---|
| título, operación, tipo | 100 % |
| moneda / precio | 92 % |
| descripción | 89 % |
| imágenes | 83 % |
| latitud / longitud | 77 % |
| baños | 66 % |
| ambientes | 62 % |
| dirección / dormitorios | 61 % / 60 % |
| superficie cubierta | 50 % |
| barrio | 49 % |
| superficie total | 21 % |
| **ciudad** | **8,6 %** |

**El hueco más grande es `ciudad`: 3.894 de 45.404.** Para un portal, la
ciudad es la faceta de búsqueda principal: hoy el 91 % del inventario
publicable no se puede filtrar por ciudad aunque haya coordenadas para 35.133.

Cobertura por connector: `wasi` y `century21` 100 %, `generico` 24 %,
**`tokko` 0 de 31.858 y `wordpress` 0 de 3.387**.

**No es un descuido: es una decisión deliberada y documentada.** El padrón de
inmobiliarias tiene un campo `city`, pero guarda zonas —"centro", "recoleta",
"palermo"—, que son barrios. `completar_ubicacion` lo rechaza a propósito y lo
archiva como `zona_padron`, un rastro de auditoría, porque llenar `ciudad` con
barrios disfrazados sería peor que dejarlo vacío: nadie lo notaría después. La
provincia sí se infiere, porque es un vocabulario limpio de 23 valores, y
queda marcada como inferida.

El camino viable es **geocodificación inversa desde las coordenadas** (77 % de
cobertura), no el padrón. Tiene que quedar marcada como derivada, con la misma
disciplina que ya se aplica a la provincia: una ciudad inferida guardada como
si la hubiera publicado la fuente es exactamente la clase de dato que después
no se distingue de uno real. Requiere decidir la fuente geográfica — ver §7.3.

### Inmobiliarias duplicadas en el universo canónico

Los 165 conflictos `MULTI_AGENCY_NORMALIZED_URL` se explican **por completo**:
las 56 URLs en disputa pertenecen a inmobiliarias duplicadas con el nombre
invertido —`inmobiliaria salerno` / `salerno inmobiliaria`—, y **ninguna es un
conflicto entre inmobiliarias realmente distintas**. El guardia del pipeline
funciona; la causa está aguas arriba.

Son **20 grupos (40 inmobiliarias, 0,6 % del universo)**, detectados por
conjunto de palabras idéntico. Lista completa en
`ERETZ_AGENCIAS_DUPLICADAS.json`.

La duplicación llega a producción: `inmobiliaria salerno` es `eretz_id 3535` y
`salerno inmobiliaria` es `6334` — el mismo negocio con dos fichas, partiendo
su inventario. Son 2 grupos con doble id (247 filas). Y hay un caso asimétrico
—`calderon inmobiliaria` tiene id y 0 propiedades; `inmobiliaria calderon`
tiene 117 propiedades y ningún id—, así que unificarlo rescataría **117
propiedades** hoy sin inmobiliaria.

Es un hallazgo menor frente a las 127.595 sin resolver, y unificar cambia la
identidad de propiedades ya guardadas: con 20 grupos, la revisión humana es
más barata que automatizarlo.

**Ojo con el dominio como señal.** Otros 16 grupos comparten dominio y en su
mayoría **no** son duplicados: `re max urbana` / `re max time` son sucursales
distintas, y tres inmobiliarias sin relación comparten un dominio de
plataforma. El dominio no sirve como identidad de inmobiliaria.

### Salud de la batería de tests

`eretz-agency`: **1.250 tests pasan** (2026-09-02), sin regresiones tras los
ocho defectos cerrados. Se partió de 1.233.

---

## 3. Registro de defectos cerrados

### D-001 — `roomix:alcami inmobiliaria` enumeraba 0 propiedades (CERRADO)

**Síntoma.** La fuente se reportaba como `SIN_INVENTARIO` / no soportada y la
certificación se detenía en `NEEDS_FIX`.

**Causa raíz.** `alcamipropiedades.com.ar` corre Bitrix24 Sites: un sitio de
una sola página. El inventario vive en bloques `landing-block-*` de la
portada; no hay ficha por propiedad, ni enlace, ni sitemap. Todos los
detectores buscaban URLs de ficha y volvían vacíos. El cero era un hueco de
cobertura, no un hecho de la fuente.

**Corrección.** Estrategia `BITRIX_LANDING_CARDS` en el connector genérico,
que lee sólo las tarjetas **con precio**: las que no lo tienen son bloques de
servicio de la plantilla ("Tasaciones", "Venta en exclusiva") y contarlas
inflaría el inventario con texto de marketing. Los campos que la tarjeta no
publica quedan ausentes — dormitorios, superficie, ciudad y coordenadas son
`None` — y la operación sólo se afirma cuando el subtítulo la declara.

**Segundo defecto, descubierto por el propio chequeo de idempotencia.** Las
tres tarjetas se enumeraban como `portada/#slug`. Pero `hash_dedup` normaliza
la URL con `urlparse`, que **descarta el fragmento**: las tres propiedades —y
la portada— colapsaban en una sola identidad. Se pisaban entre sí en el
checkpoint y la segunda corrida las reportaba `MODIFICADA` aunque las huellas
de contenido fueran idénticas. La certificación decía "3 propiedades" donde la
base habría guardado 1.

**Corrección.** El discriminador pasó al query, que la normalización sí
conserva, y la identidad ahora sale del `data-fileid` que **Bitrix asigna** a
cada tarjeta: único por construcción e independiente del orden de lectura, con
el slug del título como respaldo. El slug solo era peor identidad, porque dos
lotes pueden llamarse igual y se habrían fusionado en una sola propiedad,
haciendo desaparecer inventario real.

**Estado final.** `CERTIFIED_BEST_AVAILABLE`; 3 propiedades enumeradas, 3
identidades distintas, 0 colisiones, `SIN_CAMBIOS` en las tres, idempotente.
La única razón registrada es `LOW_INVENTORY_0_11`, que es la marca de revisión
esperada para un inventario de 0 a 11, no un defecto.

**Alcance de la clase de error.** Ningún otro connector construye URLs con
fragmento, y los parámetros que la normalización descarta son sólo `utm_*` y
click-ids. El defecto estaba acotado a esta estrategia.

### D-002 — La certificación contaba cadenas, no identidades (CERRADO)

Derivado de D-001. `compare_runs` medía `source_url` distintas, así que una
enumeración podía ser perfectamente estable y aun así estar mal: informaba
propiedades que el pipeline iba a colapsar en una sola fila, y nada lo decía.

El certificador ahora compara identidades además de cadenas y bloquea la
certificación con la razón `listings collapse into another identity after url
normalization`. Reproducido contra el caso histórico de Alcami: nombra la
causa raíz en lugar del síntoma engañoso ("second run is not idempotent").

**Impacto.** Cambiar `agency_certifier.py` invalida la huella de las 35
certificaciones que ejecutaron una estrategia. Es semánticamente correcto: se
ganaron bajo un chequeo que no podía ver esta clase de defecto. Las otras 153
no ejecutaron ninguna estrategia y no se ven afectadas.

---

### D-003 — Una excepción aislada tumbaba la corrida entera (CERRADO)

La llamada a `certify()` no estaba protegida. Sobre una cola de 6.410
inmobiliarias, un fallo inesperado en una sola —un timeout raro, un disco
lleno, un HTML que rompe un parser— mataba el proceso completo.

Ahora el fallo se registra como `RUNNER_ERROR`, que **no** está en `TERMINAL`:
la inmobiliaria vuelve sola a la cola en la próxima corrida. Un crash no es
evidencia sobre la fuente —no prueba que no publique ni que su sitio esté
roto—, así que guardarlo como estado terminal escribiría un problema nuestro
como un hecho sobre ella. El traceback va a `AGENCY_RUNNER_ERRORS.jsonl` y no
contamina el rollup de resultados.

Se agregó además `AGENCY_DEFECT_QUEUE.jsonl`: con `--continue-after-fix` los
defectos dejaban de detener la corrida y también dejaban de ser visibles.

### D-004 — Evidencia congelada en un literal (CERRADO)

Las 4.953 inmobiliarias `STAGING_NAMESPACE_NOT_A_MAIN_FK` llevaban como
evidencia el texto `"0/4920 candidates linked by main.staging_id_origen"`,
**hardcodeado**: una medición hecha una vez y grabada en el código. Si el
enlace se poblara, el texto seguiría diciendo cero. La rama era además
incondicional: toda candidata de staging se cerraba como `NOT_FOUND` sin
comprobar nada.

Ahora se verifica por registro contra el backup de `main` que la función ya
tenía cargado. Si aparece una homónima en `main` sin clave foránea declarada,
el estado pasa a `AMBIGUOUS` en vez de cerrarse: coincidir de nombre no prueba
que sean la misma inmobiliaria, y elegir una sería inventar la identidad.

Sobre los datos actuales el cambio no mueve ninguna clasificación —las 4.953
no tienen homónimas—, pero deja de apoyarse en una afirmación que nadie
comprobaba.

### D-005 — Tokko guardaba prosa de la descripción como barrio (CERRADO)

El extractor de campos de Tokko buscaba la etiqueta **sin exigir dos puntos y
sin distinguir mayúsculas**. Así, una frase corriente de la descripción —"por
su ubicación privilegiada, esta casa ofrece..."— se leía como si fuera el
campo `Ubicación`, y dejaba `barrio='privilegiada'`.

Medido sobre las 67.261 filas de Tokko con barrio: **1.145 (1,7 %) empezaban
en minúscula** y eran fragmentos de prosa —`'tranquila'`, `'y'`,
`'residencial'`, `'| Pileta, Quincho, Parrilla, Terreno de 1074m2 |'`—
guardados como si fueran un barrio real. Un dato inventado que además parecía
correcto.

Un rótulo de ficha viene capitalizado o con dos puntos; en minúscula y sin dos
puntos es una palabra de la descripción. La lectura ahora exige eso y sigue
buscando más abajo si la primera coincidencia era prosa, para que una mención
previa en la descripción no tape al campo verdadero. Los valores legítimos con
mayúscula adentro —"Nueva Cordoba", "Villa Urquiza"— siguen entrando.

El defecto afectaba a todos los campos que usan ese extractor —antigüedad,
condición, orientación, disposición, situación, dirección—, no sólo a la
ubicación.

### D-006 — La operación no se leía de la forma verbal (CERRADO)

13.518 filas quedan fuera de publicación por `RAW_ELIGIBLE_NOT_PUBLISH_ELIGIBLE`,
que exige operación y tipo. La regla es correcta: sin saber si se vende o se
alquila, un aviso no se puede publicar.

De las 11.526 sin operación, el vocabulario tenía los infinitivos —"vender",
"alquilar"— pero no las conjugadas, así que "Se vende terreno en Colastine" o
"INMOBILIARIA LEAL VENDE CASA" quedaban sin el campo que más define un aviso.

La pasada verbal corre sólo cuando nada más dijo algo, con límite de palabra
—"vende" es parte de "vendedor"—, y un aviso que nombra las dos operaciones
sigue devolviendo ausencia: elegir una sería inventar la mitad del anuncio.

**Ganancia real: 117 filas obtienen operación, 53 pasan a publicables.** Es
poco, y conviene decirlo: se verificó que **el 99 % de esas 11.526 no declara
la operación en ningún lado** —ni título ni URL—, así que el hueco grande no
era de extracción. La hipótesis de que los extractores estaban perdiendo una
señal fácil resultó falsa.

### D-007 — Tokko adivinaba el tipo en vez de leer el declarado (CERRADO)

El tipo de propiedad salía sólo de adivinarlo en el título. **899 fichas
quedaban sin tipo** —y sin tipo no se puede publicar— teniendo la ficha el dato
declarado como campo propio (`Tipo de Propiedad`), que además ni siquiera
figuraba entre las etiquetas conocidas, así que tampoco servía de frontera y
los valores vecinos podían arrastrarla adentro.

El título sigue mandando y el campo entra sólo donde el título no alcanzó, de
modo que ningún valor ya detectado cambia.

**Queda una decisión de principio pendiente:** lo declarado por la fuente
debería ganarle a lo inferido del título. Es lo correcto, pero invertir la
precedencia cambia valores existentes y no se puede medir el impacto sin el
HTML original guardado.

### D-008 — Una página vacía se guardaba como propiedad (CERRADO)

El defecto más grave encontrado hasta ahora, porque corrompe datos en silencio.

Certificando `roomix:alder inmobiliaria`, dos fichas volvieron **vacías** en la
primera corrida: `titulo = "Alder Inmobiliaria"` —el nombre del sitio—, sin
precio, sin descripción, sin ambientes y sin superficie. El pipeline las guardó
igual y les **adivinó** `tipo_propiedad="departamento"`. En la segunda corrida
las mismas URLs devolvieron los datos reales: casa, 4 dormitorios, USD 125.000.

La ausencia convertida en afirmación. Y lo peor: **si las dos corridas hubieran
fallado igual, se habría certificado `CERTIFIED_COMPLETE`** con dos propiedades
fantasma de tipo inventado. Sólo el chequeo de idempotencia lo delató.

Medido sobre la pre-ingesta: **351 fichas sin ningún campo definitorio**, en
los cuatro connectors. Entre ellas `"Di Marco Propiedades"` guardada como
galpón y `"Lincoln Negocios Inmobiliarios"` como departamento — el título es el
`<title>` del sitio y el tipo sale del slug de la URL.

El guardián de forma ya cubría esto, pero **sólo para URLs descubiertas por
patrón**. Las de Alder venían del sitemap de WASI: mejor procedencia, no mejor
contenido. Que una URL *debería* ser una ficha no prueba que la hayamos leído.
El chequeo ahora corre en el punto común a todos los connectors.

Y un cascarón es un fallo **transitorio**: la segunda corrida leyó esas mismas
URLs enteras. El pipeline ya tenía reintentos diferidos para los timeouts, así
que la ficha vacía entra por esa misma vía —fuera de la ventana inestable— en
vez de darse por perdida al primer intento. Sólo si al reintentarla sigue sin
traer nada cuenta como **detalle fallido**, con su rastro en los descartes:
la URL sí era una ficha y lo que falló fue nuestra lectura, así que la razón
que llega a la certificación es la verdadera.

**El guardia se corrigió sobre datos reales, y la corrección importa.** La
primera versión descartaba toda ficha sin campos publicados. Auditada contra la
pre-ingesta, habría tirado **254 lotes y terrenos legítimos**: así se ofrece un
lote —sólo título y fotos, sin precio, sin ambientes, sin superficie, sin
dirección—. Descartarlos habría perdido inventario real, que es exactamente el
daño que el guardia venía a evitar.

El discriminador verdadero es que **el `<title>` que sobrevive es el del
sitio**. Con las dos condiciones juntas quedan **14 filas en toda la
pre-ingesta**, todas cascarones o páginas de categoría, y cero avisos reales.

No se miran `operacion`, `tipo_propiedad` ni `provincia`: el cascarón de Alder
tenía los tres, sacados del slug de la URL y del padrón, no de la ficha.
Tampoco las imágenes, que ahí eran una sola y genérica.

## 4. Mapa de bloques

| # | Bloque | Estado |
|---|---|---|
| 1 | Runner autónomo y durable | hecho (ver D-003 y modo `--ready`) |
| 2 | Universo canónico de inmobiliarias | parcial (6.597 en cola) |
| 3 | **Descubrimiento global de bajo costo** | **pendiente — gatea al #7** |
| 4 | Familias de connectors | parcial (5 connectors, 12 estrategias genéricas) |
| 5 | Huellas por estrategia | hecho (granularidad por familia) |
| 6 | Certificación global | 2,8 % |
| 7 | **Resolución de identidad** | **cuello de botella: 140/188** |
| 8 | Integridad de claves foráneas | pendiente |
| 9 | Contrato de propiedad | pendiente |
| 10 | Normalización | pendiente |
| 11 | Deduplicación | pendiente |
| 12 | Ciclo de vida | pendiente |
| 13 | Quality gate | pendiente |
| 14 | Publicación segura | pendiente |
| 15 | Rendimiento de base | pendiente |
| 16 | API, búsqueda, mapa/lista, detalle, ranking, contacto | pendiente |
| 17 | Observabilidad y seguridad | pendiente |
| 18 | QA, beta, launch gate, operación diaria | pendiente |

El orden de la parte inicial no es negociable, y la evidencia lo confirma:
certificar más inmobiliarias sin resolver identidad multiplica filas que no se
pueden asociar a nadie, y no se puede resolver identidad de una inmobiliaria
cuya web no se conoce. Por eso el orden real de ataque es **#3 → #7 → #1 →
#6**, no el orden nominal de la lista.

---

## 5. Riesgos abiertos

- **El descubrimiento gobierna todo lo demás.** 111 de 140 `IDENTITY_PENDING`
  no tienen web conocida, y ~4.000 inmobiliarias del universo no tienen
  presencia web clasificada. Sin URL no hay certificación posible: agregar
  capacidad de scraping no mueve ese número. El bloque #3 gatea al #7, y el #7
  gatea al resto.
- **Identidad sin resolver (140 de 188).** Cada certificación nueva sin
  identidad resuelta agrega deuda, no cobertura: son filas que después no se
  pueden asociar a ninguna inmobiliaria real.
- **`SIN_INVENTARIO` es un nombre engañoso.** Significa "no reconocimos el
  mecanismo de publicación", no "la inmobiliaria no publica". Alcami mostró
  que la diferencia es inventario real invisible. Conviene renombrarlo.
- **Cobertura 2,8 %.** Cualquier conclusión sobre el catálogo global es
  prematura hasta que la cola avance sustancialmente.

---

## 6. Qué requiere autorización humana explícita

Escritura o modificación en base productiva; borrado de datos; migraciones
productivas; cambios de permisos o RLS; deploy público; `git push`; merge;
cambios de DNS o dominio; indexación pública; alta de servicios pagos; cambio
de secretos o credenciales.

No requieren autorización: analizar, programar localmente, refactorizar,
correr tests, dry-runs, investigar, generar reportes, crear scripts, validar
webs y ejecutar procesos locales seguros.

---

## 7. Decisiones que necesitan al dueño del producto

### 7.1 Qué hacer con las 4.953 inmobiliarias no promovidas

75 % del universo de certificación no existe en la tabla `main` de ERETZ. No
son franquicias ni ruido: 4.723 son inmobiliarias independientes comunes,
descubiertas por el scraping de portales.

Mientras no se promuevan, certificarlas produce propiedades que no se pueden
asociar a ninguna fila de `main`. Las opciones son excluyentes y ninguna es
técnica:

1. **Promoverlas al maestro** y certificar sobre el universo completo. Implica
   escritura en base productiva — barrera de autorización.
2. **Excluirlas de la cola** hasta que se promuevan, y certificar sólo las
   1.095 resueltas más las que resuelvan identidad. Reduce el universo activo
   de 6.597 a ~1.100, y hace que la cobertura real pase de 2,8 % a ~17 %.
3. **Certificarlas igual** aceptando que el resultado queda huérfano hasta la
   promoción.

Sin esta decisión, cualquier avance de la cola gasta esfuerzo de scraping en
datos que hoy no tienen dónde aterrizar.

### 7.2 Alcance de la corrida masiva

La cola completa son 6.410 inmobiliarias pendientes con dos corridas en vivo
cada una: del orden de 250 horas contra sitios de terceros, y la mayor parte
produciría inventario huérfano por §7.1.

Por eso la cola tiene ahora un modo `--ready`, que corre **sólo las 753
inmobiliarias cuya identidad ya resuelve** (`identity_status == READY`) en vez
de las 6.597. De esas 753 sólo 43 están certificadas, así que hay ~710 de
trabajo productivo disponible **sin depender de ninguna decisión de producto**:
sus resultados sí tienen dónde aterrizar.

Queda por acordar la ventana y el ritmo de esa corrida, y si se usa
`--continue-after-fix` para no detenerse en cada defecto —ahora que los
defectos quedan registrados en `AGENCY_DEFECT_QUEUE.jsonl` y no se pierden de
vista.

**Costo real medido**, no estimado. Piloto de 8 sobre inmobiliarias `READY`,
ejecutado 2026-09-02: **6 `CERTIFIED_COMPLETE` seguidas** y una `NEEDS_FIX`
que detuvo la corrida por diseño (`roomix:alder inmobiliaria`, causa en
D-008). Siete inmobiliarias en 77 minutos: **11 minutos de promedio**, con
dispersión real —de 4 a 25 minutos según el tamaño del catálogo—.

A ese ritmo las 753 son del orden de **140 horas** de ejecución continua. La
cifra importa para la decisión: no es una tarde. Y con la cola deteniéndose en
cada defecto, tampoco es desatendida sin `--continue-after-fix`.

El piloto también validó lo construido: el campo nuevo de colisiones de
identidad quedó en cero en las seis certificaciones, y `alpha inmobiliaria`
cerró con 125 propiedades, baseline 125 y 125 identidades distintas.

`alder` quedó después en **`CERTIFIED_COMPLETE`**: 148 propiedades, 148
identidades, 0 colisiones, `SIN_CAMBIOS` en las 148, idempotente. Esa corrida
tuvo **0 cascarones**, lo que confirma que eran transitorios —el piloto estaba
golpeando el sitio— pero también significa que **no ejerció el guardia en
vivo**: D-008 está validado por tests y por la auditoría de la pre-ingesta, no
por esa corrida.

**La dispersión de tiempos es mucho mayor de lo que sugiere el promedio.** La
misma inmobiliaria tardó 13 minutos en el piloto y casi **3 horas** al
recertificarla, con el sitio más lento. Cualquier planificación de la corrida
masiva tiene que contar con eso.

**Dato para planificar:** las 7 del piloto eran inmobiliarias **ya
certificadas** cuya huella había quedado obsoleta. Con todas las huellas
invalidadas, las próximas ~35 corridas vuelven a ganar certificaciones
existentes antes de sumar cobertura nueva.

### 7.3 Fuente geográfica para derivar ciudad

El 91 % del inventario publicable no tiene ciudad, y el padrón no sirve para
llenarla (guarda barrios). Con coordenadas para el 77 %, la geocodificación
inversa lo resuelve.

**No hace falta un servicio pago.** El repo ya tiene `scraper/geocoder.py`
usando **Nominatim (OpenStreetMap)**, gratuito y sin API key, para
geocodificación *directa* (dirección → coordenadas), con validación de que las
coordenadas caigan dentro de los límites de la ciudad esperada. Lo que falta
es el sentido inverso (coordenadas → ciudad), del mismo proveedor.

Lo que sí hay que decidir:

1. **Nominatim inverso**: sin costo, pero su política pide ~1 req/s, así que
   35.133 propiedades son del orden de 12 horas y es un servicio público
   ajeno; el uso masivo conviene acordarlo.
2. **Dataset local de localidades**: resuelve el volumen sin depender de la
   red ni de terceros, y es la opción sana para reprocesar. Implica descargar
   un archivo de datos abiertos — autorización de descarga.

Sin ciudad no hay filtro por ciudad, y sin filtro por ciudad el portal no
tiene su búsqueda principal.

Nota: `geocoder.py` lee y escribe Supabase con service role. Cualquier corrida
suya cae bajo la barrera de §6 y no se ejecutó.
