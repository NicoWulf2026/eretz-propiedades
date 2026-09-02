# ERETZ — Geografía canónica

Cómo ERETZ decide en qué ciudad está una propiedad, y por qué prefiere no
decirlo antes que decirlo mal.

Estado: **V1 cerrado en lo que no depende de la base productiva.** Ver §12.

---

## 1. El problema

Dos fichas publican su ubicación en el mismo lugar del aviso:

```
Ubicación: Alberdi
Ubicación: Córdoba Capital
```

La primera es un **barrio** de la ciudad de Córdoba. La segunda es la
**ciudad**. Sin un catálogo, las dos son una cadena de texto, y tratarlas igual
llena la faceta principal de búsqueda del portal con localidades que no
existen.

**Baseline medido:** 12,63 % de las ciudades resueltas estaban a más de 100 km
de donde decían estar, con un p95 de **1.034 km**.

---

## 2. Investigación

Se evaluaron los seis recursos de GeoRef Argentina:

| Recurso | Filas | Veredicto |
|---|---|---|
| provincias | 24 | contexto |
| departamentos | 529 | contexto |
| municipios | 2.082 | **rechazado** |
| **localidades censales** | **4.023** | **adoptado** |
| localidades | 4.028 | contexto |
| asentamientos | 14.466 | **rechazado** |

**Por qué no `asentamientos`.** Son las mismas localidades más 10.425 parajes.
Los nombres repetidos pasan de **270 a 1.545**, y el efecto concreto es que el
**Paraje Alberdi de Chaco** pasaría a ser candidato para una propiedad de
Córdoba que sólo menciona su barrio.

**Por qué no `municipios`.** Son división administrativa. Un municipio puede
contener varias localidades y no coincide con la ciudad que la gente nombra.

**Por qué sí `localidades_censales`.** Es la localidad censal del INDEC: el
lugar poblado con nombre propio, que es lo que un aviso quiere decir cuando
dice una ciudad.

---

## 3. Barrios: otra dimensión

**GeoRef no cataloga barrios.** No existe ninguna localidad llamada `Alberdi`;
hay `Alberdi Viejo`, `Colonia Alberdi`, `Villa Alberdi` y dos `Juan Bautista
Alberdi`. El único `Alberdi` exacto del país es un Paraje en Chaco.

De ahí la regla: **una cadena que no resuelve a una localidad canónica es, muy
probablemente, un barrio.** No se inventa una localidad para representarla.

El catálogo funciona entonces como **árbitro de dimensión**, en los dos
sentidos:

- `ciudad = "Palermo"` → no es localidad → se mueve a `barrio`.
- `barrio = "Mar Del Plata"` → sí es localidad → se promueve a `ciudad`.

El segundo caso no es teórico: Tokko publica la ubicación en un único campo sin
decir de qué nivel es, y **11.440 propiedades** tenían una ciudad real
escondida en `barrio`.

---

## 4. Fuente canónica

**GeoRef Argentina**, del Servicio de Normalización de Datos Geográficos
(datos.gob.ar). Oficial, gratuita, sin credenciales.

Snapshot local en `ERETZ_GEO/`, bajado con `scripts/geo_snapshot.py`. El
`MANIFEST.json` guarda por recurso: url, fecha, total declarado, filas traídas,
vía y **sha256**.

La API topea `max + inicio` en 10.000, así que `asentamientos` sólo sale del
volcado de `infra.datos.gob.ar`; `municipios` es el caso inverso (no está en el
volcado y sí entra por API). El script resuelve ambos automáticamente.

---

## 5. Cómo decide el resolver

Jerarquía de evidencia, de mayor a menor:

1. ciudad estructurada por la fuente;
2. ciudad en texto de la fuente;
3. normalización contra el catálogo canónico;
4. coordenadas como evidencia **complementaria**;
5. si no se puede demostrar: sin ciudad.

Certezas que emite:

| Certeza | Significa |
|---|---|
| `EXACT_CANONICAL` | Una sola localidad con ese nombre |
| `CONTEXT_MATCH` | Varias, y la provincia o el departamento deciden |
| `ALIAS_MATCH` | Forma comercial (`CABA`, `Córdoba Capital`) |
| `COORDINATE_SUPPORTED` | Varias, y la coordenada separa a una sola |
| `AMBIGUOUS` | Varias candidatas y nada que las separe |
| `NOT_FOUND` | Ninguna localidad con ese nombre |
| `CONTRADICTED_BY_COORDINATES` | La coordenada desmiente a la fuente |

**Reglas que no se negocian:**

- El nombre solo nunca alcanza: `san pedro` son **trece** localidades censales.
- Las coordenadas sólo **desempatan** candidatas que el nombre ya trajo. Nunca
  inventan una ciudad que la fuente no nombró.
- El desempate no usa radio absoluto. La separación entre homónimas es bimodal
  (p5 = 0,8 km contra mediana de 400 km), así que basta exigir que la más
  cercana lo sea por un margen amplio: dos registros del mismo lugar nunca
  desempatan, y quedan ambiguos.

---

## 6. Alias

Los alias apuntan a una entidad canónica; **nunca crean una nueva**.

- **CABA** no tiene localidad censal: está partida en quince comunas. Resuelve
  a la **provincia**, porque nadie publica "CABA - Comuna 4" como ciudad de un
  aviso y elegir una inventaría una precisión que la fuente no dio.
- **`<Provincia> Capital`** sale del catálogo: la localidad homónima de su
  provincia, o el departamento capital donde el nombre no coincide (Tucumán →
  San Miguel de Tucumán). Resuelve 12 de 24 provincias; **el resto devuelve
  ausencia**, que es seguro. No hay ninguna tabla de correspondencias a mano.

---

## 7. Evidencia contradictoria

Los campos estructurados de una fuente son **evidencia, no verdad**.

Dos casos reales, ambos descubiertos midiendo y no testeando:

**La Plata.** 1.498 avisos traen `provincia = "GBA Sur"` —una zona comercial— y
otros `/api/v1/state/149/`, una ruta de API sin normalizar. La primera versión
lo trataba como contradicción y dejaba **sin ciudad a una ciudad que el
catálogo tiene**. Un valor que no nombra una provincia no puede contradecir a
una.

**Sotheby's / Bariloche.** `argentinasothebysrealty.com` publica
`ciudad = CABA` en avisos cuyas coordenadas caen a 3,7 km de Lago Moreno, Río
Negro: el campo tiene **la oficina de la inmobiliaria**, no la propiedad. Eran
**1.422 casas de Bariloche afirmadas como porteñas**. Ante dos evidencias que
se contradicen no se elige una.

El umbral de contradicción es 100 km, y no es una tuerca: la aglomeración
urbana más grande del país ronda los 40 km de radio.

---

## 8. Procedencia

Cada campo derivado dice de dónde salió:

| Marca | Significa |
|---|---|
| `SOURCE_STRUCTURED` | El connector la sacó de un campo propio de la fuente |
| `SOURCE_TEXT` | Lectura determinística nuestra del contenido |
| `CANONICAL_NORMALIZED` | Normalizada contra el catálogo |
| `COORDINATE_SUPPORTED` | La coordenada participó de la decisión |
| `UNKNOWN` | No se pudo demostrar |

Se guardan además `ciudad_publicada`, `ciudad_match`,
`ciudad_campo_de_origen`, `localidad_id` y `localidad_fuente`.

**Normalizar un nombre no muda una propiedad.** Las 42 correcciones distintas
que produce el sistema son acentos, mayúsculas y formas comerciales
(`Capital Federal` → `Ciudad Autónoma de Buenos Aires`). Ninguna cambia de
lugar un aviso.

---

## 9. Lo que se rechazó, con evidencia

**Geocodificación inversa por proximidad.** Contra 9.840 propiedades de verdad
de campo, el centroide más cercano acierta **sólo el 71,4 %**.

| Condición | Cobertura | Exactitud |
|---|---|---|
| sin condición | 100 % | 71,4 % |
| margen ≥ 2 | 53,2 % | 88,1 % |
| margen ≥ 3 | 33,3 % | 89,1 % |
| margen ≥ 10 | 4,0 % | 81,7 % |
| distancia ≤ 2 km | — | 77,6 % |

Ningún umbral la vuelve confiable, y la exactitud **empeora** al exigir más
margen, o sea que el margen ni siquiera es buena señal de confianza. La razón
es estructural: los centroides son puntos y las localidades son áreas de
tamaños muy distintos. Haría falta *point-in-polygon*, y GeoRef no publica
polígonos en estos recursos.

Habría inyectado ~11.600 ciudades falsas en las 40.635 propiedades que tienen
coordenadas y no tienen ciudad. **Un falso positivo geográfico es peor que una
ausencia.**

---

## 10. Arquitectura productiva

La resolución vive en **un solo lugar**: `Connector._resolver_geografia`,
llamado desde `completar_ubicacion` en `connectors/base.py`, que es el gancho
que `run_rollout` ya invocaba para toda propiedad de todo connector.

- Una sola lógica canónica, sin duplicación por connector.
- Snapshot local: **cero consultas remotas por propiedad**.
- **0,509 ms** por propiedad.
- Determinista y testeable sin red.
- Sin snapshot no normaliza, pero no rompe el pipeline ni pierde lo publicado.

`connectors/geografia.py` entra en la huella de certificación: decide qué se
extrae, así que un cambio suyo invalida certificaciones como cualquier otro
cambio de extracción.

**El backfill usa el mismo código.** `scripts/geo_dryrun.py` construye una
`PropiedadNormalizada` e invoca `Connector._resolver_geografia`: no hay una
lógica para lo histórico y otra para lo nuevo, porque eso produce dos verdades
para el mismo dato.

---

## 11. Métricas

Sobre las 31.444 propiedades con ciudad publicada:

| | Antes | Después |
|---|---|---|
| Resueltas | 42,7 % | **56,0 %** |
| p95 de distancia | 1.034 km | **15,2 km** |
| Falsos positivos > 100 km | 12,63 % | **0** |

Por estrato:

| Estrato | n | Resueltas |
|---|---|---|
| Barrio publicado como ciudad | 1.901 | **0,0 %** |
| Forma comercial o capital | 3.478 | **100,0 %** |
| Con ciudad sin coordenada | 6.432 | 68,1 % |
| Con ciudad y coordenada | 19.633 | 49,7 % |

Con el arbitraje de dimensión, el dry-run sobre las 189.159 filas pasa de
17.608 a **29.048 propuestas**.

### Qué sigue sin resolver, y por qué

| Categoría | Propiedades |
|---|---|
| Sin ciudad, con barrio | 67.261 |
| Sin ciudad, sólo coordenada | 40.635 |
| Sin ninguna señal de ubicación | 24.688 |
| Sin ciudad, con dirección | 16.073 |
| Sólo barrio o nombre no catalogado | 10.430 |
| Sin ciudad, sólo provincia | 9.058 |
| Homónimo sin contexto | 1.984 |
| Conflicto con coordenada | 1.422 |

Las 40.635 con coordenada son el mayor grupo recuperable, y hoy no se pueden
resolver sin polígonos (§9). Es el siguiente lugar donde invertir.

---

## 12. Qué falta y por qué

La escritura sobre datos ya guardados **no se ejecutó**: el Postgres de
producción responde `PGRST002 — Could not query the database for the schema
cache`. PostgREST está arriba y la base detrás no responde.

Queda preparado hasta dry-run, con `database_writes: 0`:

- `ERETZ_GEO/CIUDAD_DRYRUN.jsonl` — 29.048 propuestas con procedencia.
- `AGENCY_PROMOTION_GATE.jsonl` — 939 promovibles.
- `AGENCY_MAIN_LINK_DRYRUN.jsonl` — 54 vinculables.

---

## 13. Actualizar el snapshot

```bash
python scripts/geo_snapshot.py --destino "D:/INMO CAPITAL/ERETZ_GEO_nuevo"
python scripts/geo_snapshot_diff.py "D:/INMO CAPITAL/ERETZ_GEO" "D:/INMO CAPITAL/ERETZ_GEO_nuevo"
```

El diff compara por `official_id` y separa altas, bajas, renombres y cambios de
provincia. **Sale distinto de cero si hay bajas o mudanzas de provincia**: eso
deja propiedades apuntando a algo que ya no existe o las mueve de lugar sin que
nadie las haya tocado. Un catálogo externo nunca se reemplaza en silencio.
