# ERETZ — Modelo geográfico canónico y capa de búsqueda

Estado: **diseño aprobado, sin aplicar**. Nada de esto toca todavía código
fingerprintado. `database_writes: 0` en todos los artefactos citados.

La decisión que ordena el documento: **no inventar geografía**. Un municipio
puede servir para descubrir una propiedad, pero no puede fingir ser una
localidad.

---

## 1. Por qué el modelo plano no alcanzaba

Hoy existe un solo campo `ciudad`, sin procedencia. Las filas guardan
`provincia_origen` y `provincia_confianza`, pero nada equivalente para la
ciudad. Consecuencia medida: `FILTRO_CIUDAD = 5.965` **no era cobertura de
localidad canónica**, era "la fila tiene algún texto en el campo ciudad". Un
barrio escrito ahí contaba igual que una localidad censal.

Con el resolver corriendo y exigiendo corroboración, la localidad realmente
demostrable son **9.619 de 58.427 (16,5 %)** — más que las 5.965, porque el
resolver también recupera localidades escritas en el campo `barrio` cuando algo
las corrobora, y menos de lo que el campo plano sugería.

Un solo campo no puede sostener al mismo tiempo "esto es una localidad censal
demostrada" y "esto es lo que escribió la inmobiliaria".

---

## 2. Dimensiones canónicas

Cinco dimensiones separadas. **Ningún nivel se rellena con otro.**

| Campo | Qué afirma | Fuente |
|---|---|---|
| `geo_provincia_id` / `_nombre` | Provincia | fuente, o geometría |
| `geo_departamento_id` / `_nombre` | Departamento | id de la localidad, o geometría |
| `geo_municipio_id` / `_nombre` | Gobierno local | catálogo, o geometría |
| `geo_localidad_id` / `_nombre` | **Localidad censal** | sólo resolución corroborada |
| `geo_barrio_fuente` / `geo_barrio_canonico` | Barrio | texto de la fuente |

Cada dimensión viaja con cuatro acompañantes, no con uno:

```
geo_<dim>_procedencia   SOURCE_STRUCTURED | SOURCE_TEXT | CANONICAL_NORMALIZED
                        | GEOMETRY | UNKNOWN
geo_<dim>_confianza     ALTA | MEDIA | BAJA
geo_<dim>_evidencia     qué lo sostiene, en una línea legible
geo_<dim>_rechazo       por qué NO se resolvió, cuando quedó en UNKNOWN
```

`geo_<dim>_rechazo` es la mitad que suele faltar. Sin ella, `UNKNOWN` y "nunca
se intentó" se ven iguales, y ya sabemos a dónde lleva confundir una ausencia
con la otra.

**Regla dura.** Si la localidad no se puede demostrar,
`geo_localidad_id = NULL` y `geo_localidad_procedencia = UNKNOWN`, **aunque
haya municipio**. El municipio se guarda en su propio campo, donde no engaña a
nadie.

### Los ids son jerárquicos y eso ahorra inventar

GeoRef numera `06` provincia → `06280` departamento → `06280040` localidad. El
departamento no se deduce ni se adivina: está adentro del id de la localidad.
Por eso `departamento` acompaña a `localidad` sin costo y sin riesgo.

---

## 3. La capa de búsqueda: `area_busqueda`

Separada del dato canónico, derivada, nunca almacenada como localidad.

```
area_busqueda_id
area_busqueda_nombre
area_busqueda_nivel     LOCALIDAD | MUNICIPIO | DEPARTAMENTO | PROVINCIA
area_busqueda_origen    de qué dimensión canónica salió
```

**`area_busqueda_nivel` es obligatorio y es el punto entero del diseño.** Sin
él, un municipio en la caja de búsqueda se lee como una ciudad. Con él, el
frontend puede decir "Municipio de La Calera" y nunca "La Calera" a secas
donde el usuario espera una ciudad.

Regla de derivación, de más preciso a menos:

1. localidad canónica demostrada → nivel `LOCALIDAD`
2. si no, municipio demostrado → nivel `MUNICIPIO`
3. si no, departamento demostrado → nivel `DEPARTAMENTO`
4. si no, provincia → nivel `PROVINCIA`
5. si no → sin área

### Cuánto cambia (medido, no estimado)

| Nivel del área | Hoy | Con municipio geométrico |
|---|---|---|
| LOCALIDAD | 9.619 | 9.619 |
| MUNICIPIO | 0 | **36.130** |
| DEPARTAMENTO | 0 | 289 |
| PROVINCIA | 47.850 | 11.897 |
| sin área | 958 | 492 |

**Búsqueda útil —municipio o mejor— pasa de 9.619 (16,5 %) a 46.038 (78,8 %)**,
sin afirmar una sola localidad que no esté demostrada. `FILTRO_LOCALIDAD` se
queda quieto en 9.619 en las dos columnas, que es exactamente el punto: la
capa de descubrimiento sube y el dato canónico no se mueve.

Bajar de nivel **nunca** rellena `geo_localidad_*`. Son dos caminos que no se
tocan: uno afirma dónde está la propiedad, el otro permite encontrarla.

### Contrato con el frontend

No se toca frontend hasta que el contrato esté fijo. Lo que el contrato exige:

- La ficha muestra la localidad **sólo** si `geo_localidad_procedencia !=
  UNKNOWN`. Si no, muestra el área con su nivel escrito.
- El filtro de búsqueda por área acepta cualquier nivel, y **muestra el nivel**.
- Nunca se compone una cadena tipo "Ciudad, Provincia" a partir del área: si el
  nivel no es `LOCALIDAD`, la palabra "ciudad" no aparece.

---

## 4. Qué se puede afirmar desde una coordenada

El catálogo local trae **sólo centroides**. Con centroides, "qué localidad es
este punto" únicamente se responde por vecino más cercano — que es exactamente
lo que puso `Villa del Parque` en Río Negro. **No se usa.**

GeoRef publica `/ubicacion`, que resuelve un punto contra la **geometría real**
de las capas administrativas. Es la misma fuente ya adoptada y no es una
aproximación nuestra. Devuelve provincia, departamento y municipio — y nunca
localidad, porque el organismo no publica polígonos de localidad.

De ahí la asimetría, que es un hecho de la fuente y no una preferencia:

| Nivel | ¿Determinable por coordenada? |
|---|---|
| provincia | sí, por geometría |
| departamento | sí, por geometría |
| municipio | sí, por geometría |
| **localidad** | **no** |

Medición **completa** sobre los 36.552 puntos con coordenada y sin localidad
demostrable (`GEO_REVERSE_PROBE_SUMMARY.json`):

| | Puntos | |
|---|---|---|
| provincia por geometría | 36.419 | 99,6 % |
| departamento por geometría | 36.419 | 99,6 % |
| municipio por geometría | 36.130 | 98,8 % |
| fuera del país o sin capa | 133 | 0,4 % |
| **localidad** | **0** | por diseño de la fuente |

**La contradicción se cuenta, no se resuelve.** Cuando la provincia geométrica
discrepa de la publicada por la fuente, una de las dos está mal y escribir
cualquiera sería elegir sin evidencia: queda registrada como `CONTRADICE`.

Son **3.852 (10,5 %)**, y conviene decir que la muestra no lo anticipó: en los
primeros 1.000 puntos contradecían 10, porque el barrido de la base sale
agrupado por inmobiliaria y esos 1.000 eran pocas agencias. Es un recordatorio
barato de que una muestra ordenada no es una muestra.

Esas 3.852 no bloquean el área de búsqueda —el municipio geométrico sigue
siendo donde está el punto— pero sí marcan 3.852 propiedades cuya provincia
publicada merece revisión aparte.

---

## 5. Resolver de barrios, como dimensión propia

**Un barrio no se resuelve contra el catálogo de localidades.** GeoRef no
cataloga barrios: en todo el país no existe ninguna localidad llamada
`Alberdi`, y el único `Alberdi` exacto es un Paraje de Chaco. Buscar barrios
ahí produjo `Villa del Parque` → Río Negro y `Barrio Norte` → Río Negro.

El resolver de barrios preserva cinco cosas y no una:

```
barrio_fuente        el texto tal cual lo publicó la inmobiliaria
barrio_canonico      sólo si existe evidencia EXPLÍCITA de equivalencia
barrio_procedencia   SOURCE_TEXT | CANONICAL_NORMALIZED | UNKNOWN
barrio_confianza     ALTA | MEDIA | BAJA
barrio_rechazo       por qué no se canonizó
```

Equivalencia explícita significa: una tabla de equivalencias declarada y
versionada, o una localidad censal cuyo nombre coincida **y** cuya provincia
esté corroborada. Nunca "el nombre existe en el catálogo".

`barrio_fuente` se muestra igual aunque `barrio_canonico` sea `UNKNOWN`: una
persona buscando en Villa del Parque reconoce el nombre, y ocultarlo por no
poder canonizarlo pierde información real sin ganar nada.

---

## 6. Las 6.890 propuestas retenidas

De las 29.048, **22.158 son aptas** y siguen siendo el universo escribible.
Las 6.890 retenidas, por causa:

| Causa | Propuestas |
|---|---|
| Barrio confundido con localidad | 5.730 |
| Nombre de ciudad único, sin nada que lo corrobore | 1.160 |
| Homónimo entre provincias | 0 |
| Contradicción de coordenadas | 0 |

Los dos ceros no son casualidad y conviene decir por qué: los homónimos ya los
descarta el resolver antes, como `AMBIGUOUS` (4.734 resoluciones), y la
contradicción por coordenadas también corta antes (3.402). **Ninguno de los dos
llega nunca a ser una propuesta.** Lo que quedó retenido es exactamente lo que
ningún control anterior podía ver: nombres que resuelven limpio contra el
catálogo y que nada corrobora.

Las 6.890 **no se escriben**. No son irrecuperables: una coordenada o una
provincia publicada alcanza para decidirlas, y el sondeo geométrico le da
provincia a las que tengan coordenada. Se reevalúan cuando el resolver
corregido entre en la ventana.

---

## 7. Radio de invalidación

Los componentes de una huella son:

```
shared/base        connectors/base.py          en TODAS las estrategias
shared/geografia   connectors/geografia.py     en TODAS las estrategias
shared/runner      scripts/run_rollout.py      en TODAS
shared/certifier   scripts/agency_certifier.py en TODAS
generic/common     connectors/generico.py      sólo genéricos
strategy/<x>       connectors/generico.py      sólo esa estrategia
connector/<x>      connectors/<x>.py           sólo ese connector
```

Los tres cambios pendientes caen así:

| Cambio | Componentes que toca | Radio |
|---|---|---|
| Normalización de encoding | `shared/base` + `generic/common` (+ nuevo `shared/texto`) | **transversal** |
| Resolver de barrios | `shared/geografia` + `shared/base` | **transversal** |
| Modelo geográfico | `shared/base` + `shared/geografia` | **transversal** |

**Los tres comparten el mismo radio transversal**, porque `shared/base` y
`shared/geografia` entran en el conjunto de componentes de toda estrategia. Por
la regla de agrupación: **una sola ventana semántica**.

Certificaciones vivas hoy: 201 terminales, de las cuales **41 tienen huella
viva** (22 genérico, 11 tokko, 7 wordpress, 1 wasi). Las otras 153 son
`IDENTITY_PENDING` y equivalentes: veredictos de identidad que no dependen del
código de extracción y a las que no se les exige una huella que nunca tuvieron.

- Agrupado: **41 recertificaciones, una vez.**
- Separado: 41 × 3 = **123**.

No hay reducción artificial posible: `shared/base` está en todos los conjuntos
por diseño, y sacarlo para pagar menos sería exactamente el agujero de
`discover()` otra vez.

### Un agujero que hay que evitar al aplicar

`connectors/texto.py` es un módulo **nuevo y todavía no importado por nadie**,
así que hoy es inerte para las huellas. En el momento de cablearlo hay que
**registrarlo como componente** (`shared/texto`) en `fingerprint_components`.
Si se cablea sin registrarlo, cambiar la normalización de texto dejaría de
invalidar certificaciones — que es la misma clase de agujero que tenía
`discover()` cuando era código semántico fuera de la huella.

---

## 8. Orden de aplicación en la ventana

1. Registrar `shared/texto` como componente.
2. Cablear `connectors/texto.py` en `base.py` y `generico.py`, reemplazando las
   cuatro defensas locales.
3. Modelo geográfico multidimensional en `PropiedadNormalizada` y
   `_resolver_geografia`.
4. Resolver de barrios como dimensión propia.
5. Suite completa.
6. Medir before/after sobre las 58.427.
7. Recalcular huellas y recertificar **sólo el radio real** (41).
8. Preflight 7/7.
9. Reabrir Task Scheduler.
