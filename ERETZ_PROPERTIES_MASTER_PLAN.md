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

Fuente: `PREINGESTION_REBUILD.sqlite3`, 189.159 filas.

| Estado | Filas |
|---|---|
| `AGENCY_ID_UNRESOLVED` | 127.595 (67,5 %) |
| `CANDIDATE` (publicable) | 45.404 |
| `INVALID_OR_REJECTED` | 15.938 |
| `DUPLICATE_OR_CONFLICT` | 222 |

**Dos tercios de todo lo scrapeado no se puede atribuir** porque su
inmobiliaria no está en `main`. Ver §3.1.

### 2.3 Completitud de las 45.404 candidatas

Cubren 520 inmobiliarias.

| Cobertura | Campos |
|---|---|
| 100 % | título, operación, tipo |
| 92 % | moneda, precio |
| 89 % | descripción |
| 83 % | imágenes |
| 77 % | latitud, longitud |
| 60-66 % | baños, ambientes, dirección, dormitorios |
| 49-50 % | superficie cubierta, barrio |
| 21 % | superficie total |
| **8,6 %** | **ciudad** |

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

`eretz-agency`: **1.316 tests pasan**, sin regresiones tras quince defectos
cerrados y la geografía canónica. Se partió de 1.233.

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

| Estado | Inmobiliarias | Propiedades retenidas |
|---|---|---|
| `SAFE_TO_PROMOTE` | **939** | **79.001** |
| `REQUIRES_REVIEW` | 1.197 | — |
| `INSUFFICIENT_EVIDENCE` | 2.462 | — |
| `BLOCKED` | 355 | — |

Motivos de bloqueo: 289 web no propia, **56 homónima en `main`**, 25 duplicada.

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
                  Cola de certificación         (939 / 1.197 / 2.462 / 355)
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
| Promoción a `main` | 79.001 propiedades atribuibles | Autorización de escritura productiva |
| Vinculación de las 56 homónimas | 1.140 propiedades | Autorización de escritura productiva |
| **Postgres de producción caído** | Promoción, vinculación y escritura de ciudad | `PGRST002`: PostgREST responde, la base detrás no |
| Escribir `ciudad` sobre lo ya extraído | 29.048 propuestas listas | Que vuelva la base |
| Polígonos de localidad | 40.635 propiedades con coordenada y sin ciudad | GeoRef no los publica en estos recursos |
| 2.462 sin web conocida | Su promoción y certificación | Descubrimiento (bloque #3) |

---

## 7. Próximos milestones

1. **Cerrar la cola `--ready`** (753, ~91 h de ejecución medida). En curso.
2. **Cablear la geografía** a los connectors y al quality gate, en un punto sin
   certificación en vuelo: tocar `connectors/base.py` cambia la huella de todas
   las estrategias y invalidaría la evidencia de la corrida activa.
3. **Descubrimiento** para las 2.462 sin web.
4. **Vinculación e ingesta** una vez levantada la barrera.
5. Contrato de propiedad, dedup, ciclo de vida, quality gate, publicación.

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
