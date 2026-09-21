# Por qué falta la geografía: siete causas, medidas por separado

**2026-09-20 · `database_writes: 0` · `production_connections: 0`**

Reproducible con:

```bash
python scripts/de_donde_falta_la_geografia.py --snapshot _scratch/unification/snapshot_image_v4/ERETZ_API_SNAPSHOT.sqlite3
```

18 tests en `tests/test_de_donde_falta_la_geografia.py`.

El pedido fue no asumir que «80 % sin ciudad/barrio» es un bug y separar las
causas. Están separadas. **La más grande no es ninguna de las que se
sospechaban**, y la conclusión general se invierte: el catálogo sabe dónde
está la propiedad mucho más seguido de lo que publica.

---

## Antes que nada: son dos poblaciones distintas

Se venían mezclando dos cosas que se llaman igual:

| | qué es | propiedades |
|---|---|---|
| **padrón certificado** | lo que la cola verificó ficha por ficha | **22.097** |
| **snapshot de la API** | lo que el buscador sirve | **57.665** |

No son subconjuntos prolijos uno del otro y sus coberturas difieren. Todo lo
que sigue dice de cuál habla. Nada se promedia entre las dos.

---

## 1. El hallazgo principal: la geografía está demostrada y no se publica

En `GEO_COVERAGE_AUDIT.jsonl`, 58.427 filas con la geometría oficial de GeoRef
—`/ubicacion`, contención en polígono, **no** centroide más cercano—:

| nivel | demostrado por geometría | publicado como dimensión |
|---|---:|---:|
| provincia | 37.016 | 57.469 |
| departamento | 37.016 | **9.574** |
| **municipio** | **36.718** | **0** |

(`provincia` se publica más veces de las que la geometría la demuestra porque
casi toda viene del padrón de la inmobiliaria — ver sección 3. `departamento`
se publica 9.574 veces, pero sólo 596 de ésas coinciden con una fila que
también tenga geometría: las otras 8.978 salieron del camino de la localidad.)

**36.718 propiedades tienen su municipio probado por geometría oficial y el
campo `municipio` está vacío en las 57.665 filas del snapshot.** No es una
muestra: `municipio_canonico` no está lleno en *ninguna* fila del catálogo.

Esto no es un olvido. Es una regla explícita, en `_area_de_busqueda`
(`connectors/base.py`):

> «Baja de nivel hasta encontrar algo demostrado, y NUNCA rellena `localidad`
> al hacerlo: son dos caminos que no se tocan. Uno afirma dónde está la
> propiedad; el otro permite encontrarla.»

La regla es correcta y hay que conservarla **para localidad**. La razón está
medida: el sondeo de 36.552 puntos contra la geometría oficial da
`localidad_determinable_por_coordenada: 0`. GeoRef no expone capa de
localidad en `/ubicacion`, así que resolver localidad por coordenada
obligaría a usar el centroide más cercano, que sí es inventar.

**Pero se está aplicando también a municipio y departamento, donde no
corresponde.** Que un punto caiga *dentro* del polígono oficial del partido de
Avellaneda no es una inferencia: es una medición. La regla se escribió contra
el centroide y terminó tapando la contención.

El costo exacto de eso es el síntoma que apareció en el QA de browser: el
autocompletado devuelve `municipality: null` en 12 de 12 sugerencias. El dato
existe —viaja en `area_nombre`, con `area_nivel = MUNICIPIO`, en 32.428
filas— y no está donde el consumidor lo lee.

### La propuesta, y por qué no la apliqué hoy

Publicar `municipio` y `departamento` con **procedencia propia**
—`GEO_GEOMETRY`, distinta de `GEO_CANONICAL` y de `GEO_SOURCE_TEXT`— para que
nada quede promovido en silencio, y dejar `localidad` exactamente como está.

No está aplicado por una sola razón: toca `connectors/base.py`, que está en la
huella del certificador, y **la cola está corriendo ahora mismo** (791
agencias, dos workers en 413 y 378). Cambiarlo a mitad de corrida invalida el
trabajo en vuelo. Queda como primera acción cuando la cola cierre.

---

## 2. Por qué falta la ciudad — padrón certificado, 22.097 propiedades

| causa | propiedades | |
|---|---:|---:|
| ciudad presente | 8.216 | 37,2 % |
| **solo inferible por coordenada** | **7.986** | **36,1 %** |
| sin ninguna pista | 3.202 | 14,5 % |
| el validador rechazó | 1.091 | 4,9 % |
| no se intentó | 875 | 4,0 % |
| solo inferible por barrio | 666 | 3,0 % |
| el extractor falló | 38 | 0,2 % |
| solo inferible por dirección | 23 | 0,1 % |

Leído contra las siete categorías pedidas:

- **La fuente no publica**: es el grueso. 14,5 % no tiene absolutamente nada,
  y buena parte del 36,1 % tampoco publica el nombre —tiene el punto—.
- **El extractor no detecta**: **0,2 %**. Era la hipótesis intuitiva y es la
  causa más chica de todas. No hay un extractor roto que explique esto.
- **El validador rechaza**: 4,9 %. Real pero menor, y ya se sabe que en su
  mayoría no pierde dato: los 2.140 «barrios rechazados» eran ciudades que el
  validador promovió.
- **GeoRef contradice**: 164 filas `CONTRADICTED_BY_COORDINATES` en la
  auditoría de cobertura. Marginal.
- **Solo inferible**: 8.675 propiedades (39,3 %) entre coordenada, barrio y
  dirección. **Es la segunda causa y es la única grande que tiene arreglo.**
- **Realmente desconocida**: 3.202.

Por conector, el reparto no es parejo:

| conector | propiedades | con ciudad | solo coordenada | sin ninguna pista |
|---|---:|---:|---:|---:|
| generico | 10.053 | 42 % | 20 % | 22 % |
| tokko | 8.452 | 24 % | **68 %** | 0 % |
| wordpress | 2.639 | 40 % | 5 % | **38 %** |
| wasi | 932 | **96 %** | 4 % | 0 % |

Tokko es casi todo el «solo inferible por coordenada»: publica el punto y no
la ciudad. Wasi publica la ciudad en el 96 % y demuestra que el problema no es
del extractor —el mismo código saca 96 % de una plataforma y 24 % de otra—.

### El caso concreto, para que no quede abstracto

Seis fichas de `dipachipropiedades` (Tokko) sin ciudad y con coordenada:

```
Crucecita  / Sande al 500          lat -34.6642167
Sarandi    / General Arredondo 3200 lat -34.6902908
Pineyro    / Mendoza al 1700       lat -34.6724959
```

Las tres están en el partido de **Avellaneda**. El nombre que publica la
fuente va a `barrio`, y `Sarandí`, `Piñeyro` y `Crucecita` dan **NOT_FOUND**
contra `localidades_censales` —comprobado ejecutando el resolver—, lo cual es
correcto: GeoRef no las cataloga como localidad censal. La ciudad real nunca
aparece por texto. La coordenada sí la ubica, a nivel municipio.

---

## 3. `provincia` al 99 % es una inferencia presentada como extracción

El padrón dice `provincia: PROVIDED_EXTRACTED` en 21.787 de 22.097
propiedades (98,6 %). Suena a que las fuentes publican la provincia. No.

**El 96,4 % de las propiedades declara exactamente la provincia de su propia
inmobiliaria** (20.649 de 21.414), y en **183 de 195 agencias *todas* sus
propiedades repiten ese mismo valor**. En el snapshot es todavía más marcado:
**99,7 %** (52.254 de 52.401).

El conector lo hace a propósito y lo dice con todas las letras
(`completar_ubicacion`, `connectors/base.py`):

```python
prop.extra["provincia_origen"] = "padron_inmobiliaria"
prop.extra["provincia_confianza"] = "inferida"
```

incluyendo la advertencia correcta: *«la provincia de la inmobiliaria no es
necesariamente la del inmueble»*.

**El problema es que esa marca no llega al artefacto.** En las 22.097
propiedades certificadas no hay ni una sola aparición de `provincia_origen`.
El registro dice `PROVIDED_EXTRACTED / FRESH_CERTIFICATION`, que es lo mismo
que dice de un título sacado del `<h1>`. Un consumidor no puede distinguirlos.

Es exactamente la distinción que se pidió para el throughput —esperado contra
demostrado— aplicada a un dato: **el conector es honesto y la certificación
pierde la honestidad por el camino.**

Y no es teórico. El sondeo de geometría encuentra **3.852 contradicciones
entre la provincia publicada y la real**. Separadas:

| familia | filas | qué es |
|---|---:|---|
| Buenos Aires ↔ CABA | 2.067 | propiedad en CABA estampada «Buenos Aires» |
| alias sin canonizar | 427 | `Capital Federal`, `CABA`, `Tierra del Fuego` corto, `Rosario` |
| provincias limítrofes | ~350 | Neuquén/Río Negro, Río Negro/Chubut: conurbaciones reales |
| **distancia imposible** | **~630** | `Catamarca → Santa Fe` (265), `Córdoba → Neuquén` (236), `Córdoba → Río Negro` (79) |

Las últimas ~630 no tienen otra explicación que el estampado: 443 propiedades
caen en el **departamento Rosario** y están publicadas como Catamarca.

### Y 612 propiedades tienen en `provincia` algo que no es una provincia

14 valores distintos, 2,81 % del padrón:

- **567** — etiquetas de zona de portal: `Bs.As. Costa Atlántica` (279),
  `Bs.As. G.B.A. Oeste` (171), `Buenos Aires Interior` (65),
  `Bs.As. G.B.A. Sur` (52). No son provincias, son regiones de un buscador.
- **32** — ciudades de Jujuy en el campo provincia: `San Salvador`,
  `san antonio`, `Palpalá`, `Ciudad Perico`, `perico`, `El Carmen`, `yala`.
  Una agencia poniendo la ciudad donde va la provincia.
- **12** — `Capital Federal` y `CABA`: el lugar correcto, el nombre sin
  canonizar.
- **1** — `Itapúa`, que es un departamento de **Paraguay**.

El resolver se defiende solo de esto (`si la provincia no nombra una
provincia, se ignora`), así que no contamina la resolución de localidad. Pero
queda guardado y sale publicado.

---

## 4. 1.715 barrios que no son barrios

En el snapshot, de 22.559 barrios con valor, **1.715 (7,6 %) son texto
recortado de la descripción**. Se parten en dos familias muy distintas:

**693 son recuperables.** El barrio está bien y se le pegó el campo
siguiente:

```
'Centro Fecha de entrega Diciembre 2027'      33
'Lanús Este Fecha de entrega Abril 2029'      32
'P.Rivadavia Fecha de entrega Junio 2029'     24
'Rada Tilly Fecha de entrega Junio 2026'      22
```

Es una sola familia —avisos de pozo— y se corta en `Fecha de entrega`.

**1.022 son frases sueltas**, sin nada que recuperar:

```
'tranquila Parrilla techada Pileta descubierta Termo de gas Videos'
'en pleno centro de la ciudad y a la versatilidad de sus'
'privilegiada dentro del barrio. * Excelente'
```

Además, los valores más repetidos incluyen **`Rosario` (359)** y
**`Capital` (345)** en el campo `barrio`: ciudades en el casillero del barrio,
el espejo exacto de `Rosario` en el casillero de la provincia.

---

## Lo que esto cambia

La frase «el 80 % no tiene ciudad ni barrio» es cierta y engañosa. Medido:

- **el extractor no está roto**: explica el 0,2 %;
- **la causa más grande con arreglo** es geografía demostrada que no se
  publica —36.718 municipios—, y el arreglo es de una capa, no de 400
  conectores;
- **la provincia, que parecía el campo sano al 99 %, es el más frágil**:
  casi todo inferido, con la marca de inferencia perdida en el artefacto.

Ninguna de las tres se veía sin separar las causas.

## Lo que NO se hizo, y por qué

- **No se rellenó ningún campo.** Publicar municipio y departamento por
  geometría es la propuesta de la sección 1 y toca la huella del certificador
  con la cola corriendo.
- **No se tocó `localidad`.** El sondeo demuestra que por coordenada no se
  puede, y forzarla sería inventar geografía.
- **No se corrigieron los 612 valores de `provincia`.** Requiere decidir qué
  hacer con las 567 etiquetas de portal: no son un error de tipeo, son la
  taxonomía de otra plataforma, y hay que resolver por familia.
- **No se escribió nada en producción.**

## Próximas acciones, en orden

1. Al cerrar la cola: publicar `municipio` y `departamento` con procedencia
   `GEO_GEOMETRY`, dejando `localidad` intacta. 36.718 y 36.420 propiedades.
2. Propagar `provincia_origen` / `provincia_confianza` al artefacto de
   certificación, para que «inferida» no se lea como «extraída».
3. Recortar los 693 barrios de la familia «Fecha de entrega».
4. Resolver por familia las 567 etiquetas de zona en `provincia`.
5. Revisar las ~630 contradicciones de distancia imposible: son propiedades
   estampadas con la provincia de su inmobiliaria.
