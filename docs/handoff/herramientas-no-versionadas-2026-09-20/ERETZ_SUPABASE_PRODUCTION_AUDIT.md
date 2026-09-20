# ERETZ Propiedades — Auditoría productiva de Supabase

Read-only. Ninguna escritura, ninguna migración, ningún cambio de configuración.
Fecha: 2026-09-09. Proyecto `inmolink` (`pggrvzyixyjkhfknpurg`), us-east-1.

---

## 1. ¿Está sano?

Sí, y hay que dejar de decir que Postgres está caído.

| qué | valor |
|---|---|
| estado del proyecto | `ACTIVE_HEALTHY` |
| motor | PostgreSQL 17.6 |
| conexiones activas | 12 |
| `search_path` | `"$user", public, extensions` |
| esquemas | `archive, audit, auth, extensions, graphql, graphql_public, internal_scraping, public, realtime, storage, supabase_migrations, vault` |

La base responde, tiene sus datos y acepta consultas. Lo que no responde es
**PostgREST**, que es otra cosa.

---

## 2. PGRST002: causa exacta

**Causa: C — ningún esquema expuesto.** No es Postgres, no son permisos, no es
RLS, no es la API key, no es el project ref.

Dos evidencias independientes:

**a) El log de PostgREST**, repetido 2.696 veces en 24 h:

```
Successfully connected to PostgreSQL 17.6 …
Failed to load the schema cache using db-schemas=pg_pgrst_no_exposed_schemas
  and db-extra-search-path=public,extensions.
{"code":"3F000","message":"schema \"pg_pgrst_no_exposed_schemas\" does not exist"}
```

Se conecta bien y falla *después*, al construir el cache. `pg_pgrst_no_exposed_schemas`
es el marcador que pone Supabase cuando la lista de esquemas expuestos está vacía.

**b) La base lo confirma.** El rol `authenticator` —el que usa PostgREST— tiene
sólo `lock_timeout`, `session_preload_libraries` y `statement_timeout`. **No tiene
`pgrst.db_schemas`.**

PostgREST reintenta cada 32 s y vuelve a fallar. Por eso el 503 es permanente
y no intermitente.

---

## 3. Qué está expuesto hoy

**Nada.** Ése es el bug.

Y una consecuencia que conviene entender antes de arreglarlo: **reponer el
esquema expuesto no publica datos**, porque los permisos no están puestos.

| rol | USAGE en `public` | lee `propiedades` | escribe |
|---|---|---|---|
| `anon` | sí | **no** | no |
| `authenticated` | sí | **no** | no |
| `service_role` | sí | sí | sí |
| `eretz_preview_ro` | sí | sí | no |

Lo único que `anon` puede leer en `public` son **tres objetos de PostGIS**:
`geography_columns`, `geometry_columns`, `spatial_ref_sys`.

### Corrección de una advertencia anterior

En el runbook yo había escrito que reponer el esquema expuesto publicaría el
backup de 129.572 filas y que había que cerrarlo primero. **Es falso.**
`backup_propiedades_url_normalizada_20260729_235540` tiene `anon_select = false`:
`anon` no lo puede leer. Lo deduje del advisor de RLS sin comprobar los permisos,
y el advisor habla de RLS, no de grants.

`internal_scraping` tampoco es alcanzable: `anon` **no tiene USAGE** sobre ese
esquema. Sus diez tablas sin RLS están protegidas por permisos.

---

## 4. Qué exponer

Tres diseños posibles, y por qué uno solo se sostiene.

**A. Exponer `public` y nada más.**
Devuelve el endpoint. No abre un solo dato, porque `anon` no tiene SELECT sobre
ninguna tabla de producto (§3): lo único alcanzable son tres objetos de PostGIS,
que son metadatos del sistema espacial. Un cambio, reversible en un minuto, sin
consecuencias sobre los datos.

**B. Exponer `public` + `internal_scraping`.**
Le daría a la API el pipeline interno: `propiedades_raw`, `publish_queue`,
`data_quality_issues`. Hoy `anon` **no tiene USAGE** sobre ese esquema, así que
además de exponerlo habría que conceder permisos. Es trabajo extra para publicar
lo que nadie consume y ampliar la superficie. **No.**

**C. Exponer un esquema nuevo, sólo de lectura, con vistas del catálogo.**
Es el diseño correcto **a futuro**: `eretz_api` con vistas que muestran
exactamente lo que el frontend necesita, y RLS encima. Pero es una migración
—crear esquema, crear vistas, conceder, versionar— y hoy la API está caída. No
se arregla una caída con una migración.

**Recomendación: A**, y C más adelante como diseño de producto.

A tiene además una propiedad que las otras no: **es independiente de todo lo
demás de este plan.** No toca datos, no depende del backup, y se puede autorizar
sola.

Y conviene decir lo que A **no** hace: no publica el catálogo. Qué se le concede
a `anon` —qué vistas, con qué policies— sigue siendo una decisión aparte, y hoy
no está tomada. Mientras tanto existe `eretz_preview_ro`, que lee por conexión
directa sin pasar por PostgREST.

Existe ya un rol `eretz_preview_ro` (login, `default_transaction_read_only=on`,
`statement_timeout=30s`, `search_path=pg_catalog, public`) que lee `propiedades`
y no escribe. Es un camino válido para una preview por conexión directa, sin
PostgREST.

---

## 5. La cifra 129.572: qué es realmente

**No es un backup de propiedades.** Es el registro de reversión de una migración.

`public.backup_propiedades_url_normalizada_20260729_235540` tiene cuatro columnas:

```
property_id, old_url_normalizada, new_url_normalizada, backup_created_at
```

- 129.572 filas, **todas con el mismo timestamp**: `2026-07-29 23:55:43`.
- 129.572 `property_id` distintos.
- 128.728 de esos ids **siguen existiendo** en `propiedades`; 844 ya no.

O sea: el 29 de julio se reescribió `url_normalizada` en 129.572 propiedades y se
guardó el valor viejo para poder volver atrás. Sirve para revertir **una columna**,
nada más. Usarla como "tenemos backup" sería un error grave.

---

## 6. Identidad y clave de UPSERT

`public.propiedades` declara:

| restricción | definición |
|---|---|
| PK | `id` |
| UNIQUE | **`hash_dedup`** |
| UNIQUE parcial | `(inmobiliaria_id, url_normalizada)` donde no es nulo ni vacío |

**`hash_dedup` es la clave de upsert correcta**, y es exactamente la que calcula
nuestro pipeline: `SHA256("{inmobiliaria_id}|url|{url_normalizada}")[:32]`. El
algoritmo legacy (`scraper/models.py::_compute_hash_dedup`) es idéntico al que
usan los connectors.

### La salvedad que hay que respetar

Sobre 60.000 filas de producción, el hash guardado se reproduce con el algoritmo
actual en el **95,7 %**. Las 2.582 que no:

| causa | filas |
|---|---|
| pasaron por la migración de `url_normalizada` (2026-07-29) | 1.475 |
| pasaron por la migración de `inmobiliaria_id` (2026-05-18) | 1.079 |

Las dos migraciones reescribieron un insumo del hash **sin recalcularlo**. Todas
las no coincidentes se crearon entre 2026-05-09 y 2026-07-04, o sea antes.

**Consecuencia para el plan de escritura:** un upsert que busque *sólo* por
`hash_dedup` no encontraría esas filas y **insertaría un duplicado**. Hay que
resolver la identidad por `hash_dedup` **o** por `(inmobiliaria_id,
url_normalizada)`, que tiene índice único parcial y es igual de barato.

---

## 7. Relación entre las 257.073 y nuestras candidatas

No son el mismo universo, y no se reemplazan.

| conjunto | filas | qué es |
|---|---|---|
| `public.propiedades` | 257.073 | todo lo que el pipeline legacy acumuló |
| candidatas locales | 58.427 | lo extraído por los connectors nuevos |
| candidatas escribibles | 57.665 | las anteriores menos 762 retenidas por venir de la web de un tercero |

Las 58.427 pertenecen a **550 inmobiliarias**. De ésas:

- **456 ya tienen filas en producción**: 51.221 en total (50.976 activas, 245 no).
- 94 no tienen ninguna: todo lo suyo es nuevo.

### Cuántas ya existen

Muestra aleatoria de 200 candidatas, resuelta por `(inmobiliaria_id,
url_normalizada)` contra producción:

| | de 198 válidas | proyectado sobre 57.665 |
|---|---|---|
| ya existe | 91 (46 %) | ~26.500 |
| nueva | 107 (54 %) | ~31.100 |

Con n=198 el intervalo al 95 % es de ±7 puntos, así que la lectura correcta es
**"aproximadamente la mitad"**, no una cifra exacta.

**Lo importante: no son 57.665 inserts.** Es del orden de 31.000 INSERT y 26.500
UPDATE, y el plan tiene que estar escrito como upsert, no como carga.

---

## 8. Seguridad

El advisor no reporta **ningún hallazgo crítico ni alto**.

| nivel | qué | evaluación |
|---|---|---|
| INFO | 25 tablas con RLS habilitado y **sin políticas** | Es cierre, no apertura: sin políticas no lee nadie por la API. No es una vulnerabilidad. |
| WARN | `postgis`, `pg_trgm` y `vector` instaladas en `public` | Higiene. Moverlas es invasivo y no aporta a la beta. |

Lo que sí hay que decidir antes de la beta —y es diseño, no defecto— es qué se le
concede a `anon`. Hoy no se le concede nada sobre datos de producto.

---

## 9. Promociones y vínculos, revalidados

**Los 54 vínculos: sanos.** Los 54 `main_id` de destino de
`AGENCY_MAIN_LINK_DRYRUN.jsonl` **existen los 54** hoy en
`public.inmobiliarias_main`. Ninguno desapareció. El dry-run sigue siendo
aplicable.

**Las 733 promociones: hay que rehacer la comprobación de duplicados.**

De las 733 `SAFE_TO_PROMOTE`, 718 traen dominio y los 718 son distintos entre
sí. Pero contra producción, sobre muestra de 60:

| | de 60 | proyectado sobre 718 |
|---|---|---|
| el dominio **ya está** en `inmobiliarias_main.web` | 6 (10 %) | ~72 |
| no está | 54 (90 %) | ~646 |

El estado `SAFE_TO_PROMOTE` incluye la razón `SIN_DUPLICADA`, pero eso se evaluó
contra el padrón del pipeline, **no contra la columna `web` de producción**.
Promover las 733 a ciegas crearía del orden de **70 agencias duplicadas**.

**Corrección necesaria antes de promover:** cruzar cada dominio contra
`inmobiliarias_main.web` y convertir los que ya existan en `LINK_TO_EXISTING`,
que es exactamente lo que ya hace el dry-run de vínculos para otras 54.

---

## 10. Las 22.158 propuestas geográficas: no son aplicables hoy

Éste es el hallazgo más incómodo de la auditoría, y hay que decirlo entero.

### Cómo clasifican en el papel

Sobre las 22.158 `APTA_PARA_ESCRITURA`, comparando la propuesta contra el valor
que el propio dry-run registró como publicado:

| clase | filas | % |
|---|---|---|
| `NOOP` (producción ya dice eso) | 12.917 | 58,3 % |
| `SAFE_UPDATE` (producción vacía) | 5.710 | 25,8 % |
| `CONFLICT` (producción dice otra cosa) | 3.531 | 15,9 % |

Y los 3.531 `CONFLICT` **no son conflictos reales**: ninguno cambia de
provincia, y son cuatro renombres canónicos del mismo lugar.

| n | publicado | propuesto |
|---|---|---|
| 3.397 | `Capital Federal` | `Ciudad Autónoma de Buenos Aires` |
| 80 | `CABA` | `Ciudad Autónoma de Buenos Aires` |
| 32 | `Capital` (Mendoza) | `Mendoza` |
| 21 | `José C Paz` | `José C. Paz` |
| 1 | `CABA` | `Ciudad Autónoma de Buenos Aires` |

O sea: geográficamente, la propuesta es conservadora y no pisa nada.

### Por qué igual no se puede aplicar

**Las filas a las que apunta mayormente no existen en producción.**

Muestra de 120 propuestas, resueltas por `hash_dedup`:

| resultado | filas |
|---|---|
| `NOT_FOUND` | **95** |
| cambió desde el dry-run | 24 |
| igual que el dry-run | 1 |

No es la deriva conocida del hash. Resolviendo por URL, sobre 22 propuestas
sólo **5** aparecen en producción, y el caso que sí se pudo rastrear explica el
resto:

```
dry-run : https://www.paniaguapropiedades.com/p/7651488-...
producción: https://paniaguapropiedades.com/p/7651488-...
```

Producción **perdió el `www.`** en la migración del 2026-07-29, así que ni la URL
ni el hash coinciden. Y hay hosts enteros del dry-run que hoy no tienen ninguna
fila: `redinmobiliaria.ar` da **0**.

El dry-run evaluó **189.159** filas; producción tiene **257.073**. No son el
mismo universo: el artefacto se calculó sobre un estado anterior de la base.

### Qué corresponde

**Las 22.158 propuestas no se escriben.** El trabajo geográfico es válido —la
clasificación de arriba lo muestra— pero está indexado contra una foto vieja.
Hay que **recalcularlo contra `public.propiedades` actual**, resolviendo por
`url_normalizada` con el `www.` ya quitado, antes de que la Fase 6 del plan de
escritura tenga sentido.

Escribirlo tal como está no sería peligroso —casi todo daría `NOT_FOUND` y no
haría nada— pero sería falso decir que se aplicaron 22.158 correcciones cuando
se aplicarían unas pocas miles.

---

## 11. Gate de calidad: no rechaza, gradúa

El gate (`property_quality_gate_v2`, contrato v3) evaluó las 58.427 candidatas y
declaró **58.427 publicables y 0 no publicables**. Eso no es un gate roto: es un
gate que en vez de aceptar o rechazar decide **hasta dónde llega cada ficha**.

| alcance | candidatas | qué significa |
|---|---|---|
| FICHA | 58.427 | 100 % se puede mostrar en su página |
| LISTADO | 58.427 | 100 % se puede listar |
| AREA_BUSQUEDA | 57.935 | 99 % se encuentra por ubicación |
| FILTRO_PRECIO | 53.088 | 91 % |
| FILTRO_TIPO | 52.777 | 90 % |
| FILTRO_OPERACION | 48.014 | 82 % |
| MAPA | 42.518 | 73 % |
| **FILTRO_LOCALIDAD** | **9.619** | **16 %** |

El área de búsqueda cae casi toda en MUNICIPIO (32.428) y PROVINCIA (15.749);
sólo 9.619 llegan a LOCALIDAD y 492 quedan `SIN_AREA`.

**Consecuencia para el plan de escritura:** "publicable" no sirve como filtro,
porque no descarta a nadie. Lo que hay que escribir en la Fase 3 es el
**alcance** de cada fila, y aceptar que el filtro por localidad va a cubrir uno
de cada seis avisos hasta que la geografía mejore.

Y los estados de campo dicen dónde está el trabajo pendiente:

| estado | campos |
|---|---|
| EXTRACTED | 900.320 |
| **AUSENTE_SIN_DIAGNOSTICO** | **225.267** |
| SOURCE_NOT_PROVIDED | 95.872 |
| REJECTED_BY_VALIDATION | 4.172 |
| EXTRACTION_FAILED | 1.336 |

225.267 campos ausentes **sin diagnóstico** contra 97.208 con diagnóstico: de
cada tres campos que faltan, dos no sabemos por qué faltan. Eso no bloquea la
escritura, pero es la deuda más grande del pipeline.

---

## 12. Duplicados: detectados y clasificados, ninguno fusionado

Ya está hecho, y con el criterio correcto: **`ganadores_elegidos: 0`**. Se marca,
no se fusiona.

Sobre las 58.427 candidatas, 29.727 (50,9 %) tienen firma completa —13.322
FUERTE, 16.405 SECUNDARIA—. De ahí salen:

| | grupos |
|---|---|
| dentro de la misma inmobiliaria | 763 |
| entre inmobiliarias distintas | 117 |
| **filas agrupadas** | **2.140** |

Y la evidencia clasifica 514 de esos grupos:

| clase | grupos | qué hacer |
|---|---|---|
| `PUEDEN_SER_UNIDADES_DISTINTAS` | 207 | **nada**: probablemente son dos unidades reales |
| `MISMO_INMUEBLE_PRECIO_DISTINTO` | 163 | marcar; el precio decide, no nosotros |
| `SOLO_TEXTO_O_UBICACION_IMPRECISA` | 72 | evidencia débil, marcar y seguir |
| `MISMO_INMUEBLE_DATOS_INCONSISTENTES` | 40 | marcar y revisar a mano |
| `IDENTICOS_EN_TODO_LO_VISIBLE` | 32 | los únicos candidatos serios a fusión |

Los campos que más difieren dentro de un grupo son `descripcion` (367), `precio`
(304) y `titulo` (301) — o sea que la mayoría de los "duplicados" son el mismo
inmueble contado de dos maneras, no dos filas idénticas.

**Sólo 32 grupos son idénticos en todo lo visible.** Ésa es la cota superior real
de lo fusionable, y aun así la Fase 7 del plan no los fusiona: los marca.

---

## 13. Legacy y extractor nuevo: se complementan, no se reemplazan

Éste es el número que más pesa sobre el plan de escritura.

Tomé 130 candidatas al azar y las resolví contra producción por
`(inmobiliaria_id, url_normalizada)`. **63 ya existen (48 %)** —consistente con
el 46 % de la otra muestra—. Para esas 63 comparé campo por campo quién tiene
valor y quién no:

| campo | sólo producción | sólo nosotros | ambos | ninguno |
|---|---|---|---|---|
| precio | 4 | 14 | 42 | 3 |
| moneda | 7 | 18 | 38 | 0 |
| operacion | 5 | 0 | 58 | 0 |
| tipo_propiedad | 2 | 0 | 61 | 0 |
| ambientes | 6 | 5 | 35 | 17 |
| dormitorios | 3 | **26** | 15 | 19 |
| banos | 1 | **30** | 20 | 12 |
| superficie_total | **22** | 9 | 7 | 25 |
| superficie_cubierta | 0 | **31** | 0 | 32 |
| latitud | 6 | **30** | 19 | 8 |
| longitud | 6 | **30** | 19 | 8 |
| ciudad | **35** | 3 | 3 | 22 |
| barrio | **25** | 0 | 35 | 3 |
| provincia | 0 | **22** | 38 | 3 |
| direccion | **23** | 0 | 38 | 2 |
| **total** | **145** | **218** | | |

### Lo que dice

**Se reparten el trabajo.** Nosotros somos mejores en la estructura del inmueble
—superficie cubierta (31 casos donde sólo nosotros la tenemos), baños (30),
coordenadas (30 y 30), dormitorios (26)—. El legacy es mejor en la ubicación
escrita: ciudad (35), barrio (25), dirección (23), superficie total (22).

Nada de esto es raro: el extractor nuevo lee la ficha y el legacy heredó
geocodificación y normalización de domicilio que nosotros no rehicimos.

### Por qué la regla `COALESCE`-safe no es una precaución, es obligatoria

**145 valores en 63 filas: 2,3 por fila.** Un UPDATE que escriba nuestros
campos tal cual, con los NULL incluidos, **borraría del orden de 60.000 valores
productivos** al aplicarse sobre las ~26.500 filas que ya existen. Casi todos
serían de ubicación: ciudad, barrio y dirección.

Sería la peor forma de perder datos: silenciosa, masiva, y con la apariencia de
una actualización exitosa.

**Y al revés, la ganancia es real:** 218 campos nuevos en 63 filas, 3,5 por
fila. Bien hecho, el merge aporta ~92.000 valores que hoy no están.

---

## 14. Calidad de `public.propiedades`

257.073 filas, 3.187 inmobiliarias. Ninguna huérfana, ningún `hash_dedup` nulo,
ningún `created_at` nulo. Hasta ahí, sana.

**La base está congelada desde el 2026-07-31.** Última alta y última
actualización, las dos ese día: el de la migración de `url_normalizada`. Hace
cuarenta días que no entra nada.

### Cobertura de campos

| campo | filas con valor | % |
|---|---|---|
| operacion, tipo_propiedad | 257.073 | 100 % |
| direccion | 206.185 | 80 % |
| imagenes | 178.232 | 69 % |
| precio | 168.385 | 65 % |
| ciudad | 111.157 | **43 %** |
| provincia | 110.963 | **43 %** |
| latitud + longitud | 65.033 | **25 %** |

Y **28.989 filas tienen precio pero no moneda** —un 17 % de las que tienen
precio—: un número sin unidad no se puede mostrar ni filtrar.

### Estado y ciclo de vida

| estado | filas |
|---|---|
| activa | 256.290 (99,7 %) |
| desconocida | 430 |
| no_detectada_en_ultimo_scraping | 353 |

Prácticamente nada se dio de baja nunca. Eso confirma que la desactivación en
masa no tiene precedente en esta base, y refuerza dejarla fuera del plan.

### Datos que no deberían estar

| qué | filas |
|---|---|
| sin descripción útil (< 30 caracteres) | 87.151 (34 %) |
| sin título útil (< 5 caracteres) | 69.723 (27 %) |
| **`ambientes` con valor imposible (≥ 200)** | **7.063** |
| sin `url_normalizada` | 13.082 (249 agencias) |
| **URL que es un enlace de WhatsApp (`wa.me`)** | **941** |
| precio menor a 100 | 651 |
| coordenadas fuera de Argentina | 562 |
| URL que no empieza con `http` | 53 |
| superficie mayor a 100.000 m² | 49 |

Los `ambientes` merecen mirarse de cerca, porque explican de dónde vienen:

| valor | filas | qué es en realidad |
|---|---|---|
| 855 | 4.511 | un identificador de `alder_inmobiliaria` |
| 2025 / 2026 / 2027 | 237 | el **año** de construcción |
| 5913, 7117, 2518… | resto | identificadores de ficha |
| máximo: **1.765.290.777** | | un **timestamp Unix** |

El extractor legacy guardó en `ambientes` el primer número que encontró. Nuestras
reglas de coherencia rechazan exactamente esto, así que en los campos
estructurales el dato nuevo es mejor que el productivo — es la otra cara de §13.

### El problema grande: atribución

Comparando el host de cada URL contra la web declarada de su inmobiliaria:

| caso | filas |
|---|---|
| el host coincide | 222.896 (87 %) |
| subdominio de la misma web | 814 |
| la agencia no tiene web declarada | 3.401 |
| **el host es de otra agencia** | **29.962 (11,7 %)** |

Son **665 inmobiliarias** con propiedades de **680 hosts ajenos**. Y no es teoría:

> 473 propiedades de `marcospropiedades.com` figuran a nombre de **CALELLA
> PROPIEDADES**, cuya web es `calellapropiedades.com.ar`.

Es el mismo modo de falla de `arte propiedades` que ya cerramos en el extractor
—y por el que retiramos 762 candidatas del plan de escritura—, pero ya escrito en
producción, a escala.

Mirado por URL compartida: 29.279 URLs aparecen bajo más de una inmobiliaria,
**60.181 filas involucradas**. De las 727 combinaciones de agencias:

| caso | combinaciones | URLs |
|---|---|---|
| **web distinta → atribución sospechosa** | **710** | **26.917** |
| misma web (sucursal o alta duplicada) | 17 | 2.362 |

Las 17 de misma web son legítimas de otra manera: `Blanco Propiedades` y `Blanco
Propiedades Nordelta`, `VREMONT` y `VREMONT Treus`, `AN Inmuebles` y `Pedro Meda
| AN Inmuebles Gualeguay`. Son sucursales dadas de alta dos veces, y cada una se
lleva el catálogo entero.

**Ninguna de las dos cosas se arregla en este plan** —limpiar atribución es
borrar o reasignar, y eso necesita su propia autorización y su propio
rollback—, pero cambia cómo hay que leer las 257.073: **una de cada nueve filas
está a nombre de quien no corresponde.**

---

## 15. Rendimiento e índices, ahora sí con `EXPLAIN`

Primero una corrección de encuadre: **el API v2 no consulta Postgres.**
`api/v2.py` lee una snapshot SQLite local; el que consulta producción es
`api/main.py`, por PostgREST, y es el que devuelve PGRST002. Así que las
consultas a medir son las que **PostgREST generaría** a partir de `main.py`.

### Lo que ya existe

| índice | usos | tamaño | definición |
|---|---|---|---|
| `propiedades_pkey` | 3.770.608 | 13 MB | `btree (id)` |
| `idx_propiedades_inmobiliaria` | 2.128.817 | 3,6 MB | `btree (inmobiliaria_id)` |
| `propiedades_hash_dedup_key` | 608.920 | 22 MB | `btree (hash_dedup)` |
| `idx_propiedades_latlon` | 8.988 | 4,1 MB | `btree (latitud, longitud) WHERE latitud IS NOT NULL` |
| `idx_propiedades_estado` | 1.222 | 4,2 MB | `btree (estado)` |
| `idx_propiedades_url_normalizada` | 1.051 | 33 MB | parcial |
| `idx_propiedades_tipo_operacion` | 683 | 5,1 MB | `btree (tipo_propiedad, operacion)` |
| `idx_propiedades_ciudad_provincia` | 513 | 4,8 MB | `btree (ciudad, provincia)` |
| `idx_..._unique_inmobiliaria_url_normalizada` | 43 | 40 MB | parcial única |
| `idx_propiedades_precio_usd` | 20 | 14 MB | `btree (precio_usd)` |

**Los contadores de uso no sirven para decidir bajas.** La API lleva días caída,
así que un índice con 20 usos puede estar sin usar o puede ser el índice de la
consulta que hoy no corre. No propongo eliminar ninguno.

### Lo que midieron los planes

| consulta | tiempo | por qué |
|---|---|---|
| listado, filtro común (venta + departamento + rosario) | **15 ms** | los primeros 426 ids ya traían 24 resultados |
| listado, filtro raro (alquiler + local + bariloche) | **388 ms** | descartó 2.026 filas para encontrar 2 |
| `count(*)` por operación | **139 ms** | recorrió el índice entero |
| mapa, 1.000 puntos | **123 ms** | |
| detalle por id | trivial | índice primario |

### Los dos hallazgos

**1. `idx_propiedades_tipo_operacion` tiene las columnas al revés.**

```
Index Only Scan using idx_propiedades_tipo_operacion
  Index Cond: (operacion = 'alquiler'::text)
  ... 19.335 filas, 3.101 buffers, 139 ms
```

El índice es `(tipo_propiedad, operacion)` y el filtro más frecuente —el que usa
el contador de la home— es `operacion` **sola**. Al ser la segunda columna,
Postgres no puede saltar: recorre el índice entero.

**Propuesta:** `(operacion, tipo_propiedad)`. Sirve para los dos casos —filtrar
por operación sola, y por operación + tipo—, mientras que el orden actual sólo
sirve bien para tipo solo.

**2. `ciudad ILIKE '%texto%'` no puede usar ningún índice.**

`main.py` filtra ciudad y barrio con `ilike.*x*`, que PostgREST traduce a
`ILIKE '%x%'`. Un btree no sirve con comodín a la izquierda, así que
`idx_propiedades_ciudad_provincia` queda de adorno y la consulta filtra fila por
fila. Ésos son los 388 ms del caso raro.

**Propuesta:** un índice GIN de trigramas. **`pg_trgm` ya está instalada** —es
una de las tres que el advisor marca por estar en `public`—, así que no hace
falta agregar nada:

```sql
CREATE INDEX CONCURRENTLY idx_propiedades_ciudad_trgm
  ON public.propiedades USING gin (ciudad gin_trgm_ops)
  WHERE ciudad IS NOT NULL;
```

Parcial porque sólo el 43 % tiene ciudad. `CONCURRENTLY` para no bloquear.

**No está aplicado y no lo voy a aplicar**: crear un índice productivo está en la
barrera de §26. Y conviene medirlo después de la Fase 1, con la API arriba y
tráfico real, no con mi consulta inventada.

### Un tercer problema que no se arregla con un índice

El listado ordena por `id` y pagina con `LIMIT/OFFSET`. Eso da **15 ms cuando el
filtro es común y 388 ms cuando es raro**: la misma pantalla, veintiséis veces
más lenta según lo que escriba el usuario. Es una decisión de diseño de la
consulta, no de indexado, y hay que resolverla cuando se defina el orden real
del catálogo.

### De paso: de dónde salía el 257.804

El runbook decía 257.804 filas y esta auditoría dice 257.073. Las dos venían de
la base: **257.804 es `n_live_tup`**, la estimación del planificador; 257.073 es
el `count(*)` real. La diferencia son 731 tuplas muertas contadas de más. El
último autovacuum fue el 2026-07-30 y hay 6.104 tuplas muertas — poco, y la
tabla no cambió desde entonces, así que las estadísticas siguen siendo válidas.

---

## 16. El diff exacto: las 57.665, una por una

Ya no es una proyección de muestra. Es el recuento completo.

**Cómo se hizo sin conexión directa.** La contraseña de la base sigue sin
funcionar, así que producción se bajó por MCP en una sola consulta: una tira con
la clave de cada fila —8 hexadecimales de `md5(inmobiliaria_id|url_normalizada)`—
más quince banderas de "este campo tiene valor". 47.204 filas de las 456
inmobiliarias que nos interesan, y el cruce se hizo local.

**47.204 filas dieron 47.204 claves distintas: cero colisiones.** Con 32 bits
se esperaban unas quince; no hubo ninguna.

### El resultado

| clase | filas | % |
|---|---|---|
| **NEW** | **29.413** | 51,0 % |
| **UPDATE_CON_RIESGO** | **28.054** | 48,7 % |
| UPDATE (sin riesgo) | 197 | 0,3 % |
| DUPLICATE | 1 | — |
| *(retenidas por web ajena, fuera del total)* | *762* | |

Las muestras habían dicho 46 % y 48 % de coincidencia; el recuento completo dice
**48,99 %**. La proyección era buena, pero ahora no hace falta proyectar.

### Lo que un UPDATE ingenuo haría

Sobre las **28.252 filas que ya existen**:

| campo | destruiría | aportaría |
|---|---|---|
| ciudad | **16.424** | 1.335 |
| barrio | **13.716** | 52 |
| direccion | **9.585** | 209 |
| superficie_total | **7.468** | 3.716 |
| imagenes | 3.769 | 6.650 |
| latitud | 2.193 | **13.695** |
| ambientes | 2.176 | 4.229 |
| moneda | 1.842 | 8.360 |
| dormitorios | 1.406 | **10.064** |
| banos | 1.363 | **11.003** |
| descripcion | 1.208 | 1.601 |
| precio | 1.127 | 5.459 |
| titulo | 6 | 5.654 |
| provincia | 0 | **10.623** |
| superficie_cubierta | 0 | **13.645** |
| **TOTAL** | **62.283** | **96.295** |

**28.055 de 28.252 filas —el 99,3 %— perderían al menos un dato.** El reparto:

| campos que perdería | filas |
|---|---|
| 1 | 9.680 |
| 2 | 8.206 |
| 3 | 6.067 |
| 4 | 2.714 |
| 5 | 1.234 |
| 6 a 8 | 154 |

La estimación de §13 sobre 63 pares decía "del orden de 60.000". El recuento
completo dice **62.283**. Y la ganancia también se confirma: **96.295 valores
nuevos**, uno y medio por cada uno que se hubiera destruido.

### El artefacto

`DATA_QUALITY/dry_run_escritura.jsonl`, 58.427 líneas, una por candidata, cada
una con su clase, su agencia y **la lista exacta de campos que no hay que
tocar** en esa fila. Ése es el insumo de la Fase 4.

**Lo que este cruce no puede decidir:** si un campo que ambos tienen tiene el
*mismo* valor. Distingue presencia, no contenido. Por eso `UPDATE` y `UNCHANGED`
todavía están juntos, y por eso la Fase 4 sigue necesitando la comparación de
valores contra la base antes de escribir.

---

## 17. El rollback, ensayado

`scripts/ensayo_de_rollback.py`. Base local descartable, `database_writes: 0`
contra Supabase.

Las filas locales se arman con la **máscara real** de cada fila productiva —la
que bajó el diff— y los **valores reales** de las candidatas, así que el ensayo
recorre la misma forma del problema: las mismas 28.251 colisiones y los mismos
campos en juego. Se corren las dos variantes a propósito:

| variante | valores productivos que quedaron nulos |
|---|---|
| `SET campo = nuevo` (ingenuo) | **62.280** |
| `SET campo = COALESCE(nuevo, campo)` | **0** |

Correr el ingenuo no es decoración: si algún día deja de perder datos, el ensayo
dejó de probar lo que dice probar, y el script lo denuncia en vez de pasar.

Después se revierte el `COALESCE`-safe con la imagen previa que anota cada lote
y se compara la tabla entera:

```
[coalesce] la reversion deja la tabla igual que antes: SI
[coalesce] filas que no volvieron a su valor: 0
```

Cinco tests en `tests/test_ensayo_de_rollback.py` fijan las cuatro propiedades
—el ingenuo pierde, el seguro no pierde, el seguro igual aporta lo que falta, y
la reversión es exacta—. Suite completa: **480 tests en verde**.

**Lo que el ensayo no reemplaza:** la prueba sobre datos productivos
restaurados. Eso necesita el dump, y el dump necesita la credencial.

---

## 18. Y ahora el contenido: qué cambia de verdad

§16 comparaba presencias. Faltaba lo otro: cuando los dos lados tienen el campo,
¿es el mismo valor? Se bajó una segunda tira —dos hexadecimales por campo, del
md5 del valor **normalizado**— y se aplicó la misma normalización de este lado.

**Control primero.** Si la normalización no coincidiera, todo daría "distinto" y
el resultado no valdría nada. Sobre 198.545 campos presentes en ambos lados,
coinciden 99.366 (50 %). Y el reparto por campo confirma que la normalización es
correcta: `provincia` coincide el 94 %, `moneda` el 92 %, `precio` el 86 %.

### El resultado

| campo | difieren | lectura |
|---|---|---|
| descripcion | **98,1 %** | reescrita entera |
| imagenes | **95,4 %** | otra cantidad de fotos |
| titulo | **86,1 %** | otro texto |
| latitud | 63,5 % | otra coordenada |
| superficie_total | 56,8 % | |
| ciudad | 47,2 % | |
| dormitorios | 44,6 % | |
| barrio | 44,0 % | |
| banos | 32,9 % | |
| ambientes | 26,6 % | |
| precio | **14,1 %** | |
| direccion | 14,1 % | |
| moneda | 8,3 % | |
| provincia | **5,9 %** | |

### Lo que esto significa para el plan

**Sólo 40 de 28.250 filas no cambian en nada.** Las otras 28.210 tienen al menos
un campo con valor distinto. O sea: **prácticamente no hay `UNCHANGED`**; las
28.252 que ya existen son UPDATE de verdad.

Pero hay una distinción que el plan no tenía y ahora necesita. Que un valor sea
**distinto** no quiere decir que el nuestro sea **mejor**:

- **Sobrescribir es claramente bueno** en lo estructural: `precio` (14 %
  difiere), `moneda`, `provincia`, `direccion` — números y etiquetas que nuestro
  extractor valida con reglas de coherencia y el legacy no. Recordar que el
  legacy guardó timestamps en `ambientes` (§14).
- **Sobrescribir es una decisión, no una mejora**, en `titulo` (86 %),
  `descripcion` (98 %) e `imagenes` (95 %). Ahí no estamos corrigiendo un error:
  estamos reemplazando un texto por otro texto. Si producción tiene una
  descripción de 800 caracteres y nosotros una de 200, "actualizar" empeora.

**El plan de escritura tiene que declarar, campo por campo, cuáles sobrescribe.**
No alcanza con `COALESCE`-safe: eso protege del NULL, no de reemplazar algo
bueno por algo peor.

### El margen de error

Dos hexadecimales son 256 valores, así que uno de cada 256 pares distintos
coincide por azar: de los 99.366 "coinciden", unos **390 en realidad difieren**.
El error va siempre en la dirección segura —decir "no hay que escribir" cuando
sí habría— y nunca en la de pisar un dato. Con todo, es una razón más para que
la Fase 4 verifique contra la base antes de escribir.

---

## 19. La provincia se está leyendo de un nombre de calle

Lo encontró la validación de coordenadas, y no lo estábamos buscando.

De las 42.499 candidatas que traen par de coordenadas, **1.131 declaran una
provincia que contradice su propia coordenada**. Dos agencias explican el 31 %:

| agencia | fichas | provincia que declara | dónde caen las coordenadas |
|---|---|---|---|
| `enz propiedades` | **266 de 266** | `Catamarca` | (-32,877 / -60,696) = **Rosario** |
| `fogliese propiedades` | 88 | `Ciudad Autónoma de Buenos Aires` | (-37,342 / -57,029) = **costa atlántica** |

`enz` es una inmobiliaria de Rosario: sus barrios son Pichincha, Fisherton,
Alberdi, Arroyito, La Florida, Luis Agote. **Catamarca es una calle de Rosario.**
El extractor la leyó como provincia. `fogliese` es el mismo error con
`Buenos Aires`, que también es nombre de calle en medio país.

**El 100 % de una agencia es señal, no ruido.** No es una ficha rara: es la
regla aplicándose mal a todo un sitio.

### Qué se hizo y qué no

**No se tocó el extractor.** Es un componente fingerprintado y el congelamiento
sigue vigente (§22 de la autorización): queda anotado para la ventana semántica
única, junto con `bottega`, SOM y `superficie_total` de Tokko.

**Sí se protegió la escritura.** En cualquier fila donde la geografía se
contradiga a sí misma, el dry-run no toca `provincia`, `ciudad`, `barrio`,
`latitud` ni `longitud`: ni las sobrescribe ni las completa. En las altas nuevas
esos campos entran en NULL. Mejor sin provincia que con la provincia de otro
lado — que es la regla de siempre, "no inventar geografía", aplicada al alta.

### Clasificación completa de las coordenadas

| clase | candidatas |
|---|---|
| **VALIDA** (dentro del país y de su provincia) | **40.492** |
| SIN_COORDENADA | 15.928 |
| CONTRADICE_LA_PROVINCIA | 1.131 |
| SIN_PROVINCIA_QUE_CONTRASTAR | 541 |
| PROVINCIA_DESCONOCIDA | 333 |
| FUERA_DE_ARGENTINA | 2 |

**Habilitadas: 40.491. Bloqueadas: 2.007.** Sin polígonos provinciales, la caja
de cada provincia se arma con los centroides de sus localidades censales más un
margen de 1°: es permisiva —deja pasar de más— pero no rechaza una coordenada
que esté bien adentro. El error va en la dirección segura.

`SIN_PROVINCIA_QUE_CONTRASTAR` **no cuenta como válida**: no poder comprobar
algo no es lo mismo que comprobarlo.

---

## 20. El esquema, y las restricciones que el plan no conocía

Extraído de `pg_catalog` —lectura pura— porque un backup sin esquema no se
restaura, y porque las restricciones deciden si un INSERT entra o rebota.

### Lo que las candidatas ya cumplen

| control | resultado |
|---|---|
| `CHECK` de `operacion` (venta, alquiler, alquiler_temporario, consultar, venta_y_alquiler) | **0 violaciones** de 58.427 |
| `CHECK` de `moneda` (ARS, USD, EUR, UYU) | **0 violaciones** |
| `NOT NULL` de `hash_dedup` | 0 faltantes |
| **FK `inmobiliaria_id → inmobiliarias_main(id)`** | **las 550 agencias existen y están activas** |

O sea: **`UNRESOLVED_AGENCY` = 0.** Ninguna alta rebotaría por apuntar a una
inmobiliaria inexistente. Era un riesgo real —el plan lo listaba como clase
posible— y está descartado con la base a la vista.

Los valores que sí aparecen: `venta` 42.536, `alquiler` 4.672,
`alquiler_temporario` 303, sin operación 10.916. Monedas: USD 46.361,
ARS 6.833, sin moneda 5.233.

### Lo que cambia el plan de rollback

`public.propiedades` es destino de **ocho claves foráneas**, y seis con
`ON DELETE CASCADE`:

| tabla que apunta | al borrar la propiedad |
|---|---|
| `geocoding_results` | **CASCADE** |
| `historial_precios` | **CASCADE** |
| `property_analysis` | **CASCADE** |
| `property_events` | **CASCADE** |
| `property_location_corrections` | **CASCADE** |
| `property_scores` | **CASCADE** |
| `property_merge_audit` | SET NULL |

**Borrar una fila insertada por error no borra una fila: borra siete.** Y
`historial_precios` y `property_events` son justamente lo que no se puede
reconstruir. Eso convierte el DELETE de rollback en una operación mucho más
cara de lo que el plan asumía, y confirma la decisión de marcar en vez de
borrar.

### Lo que hay que respetar al promover

`inmobiliarias_main.slug` es **UNIQUE**. Las 655 altas tienen que generar un
slug que no choque con ninguno de los 7.004 existentes, y eso todavía no está
calculado.

---

## 21. Promociones y vínculos, revalidados contra el padrón de hoy

Se bajó el padrón completo —7.003 de 7.004 filas parseadas— y se cruzó local.

### Los 54 vínculos

| clase | vínculos |
|---|---|
| **STILL_SAFE** | **54** |

Los 54 destinos existen, cada uno sigue siendo el único que resuelve ese
nombre, y ninguno se volvió ambiguo. El dry-run de vínculos sigue siendo
aplicable tal cual.

### Las 733 promociones

| clase | agencias | % |
|---|---|---|
| **STILL_SAFE** | **655** | 89,4 % |
| **NOW_EXISTS** | **78** | 10,6 % |
| AMBIGUOUS | 0 | |
| CONFLICT | 0 | |
| REVIEW | 0 | |

Las 78 `NOW_EXISTS` ya tienen su dominio en `inmobiliarias_main.web`: **no son
altas, son vínculos**. Crearlas duplicaría la inmobiliaria.

La muestra de 60 dominios había proyectado ~72; el recuento completo dio 78.
Y el cero en `AMBIGUOUS` y `CONFLICT` no es suerte: el gate ya exigía
`SIN_HOMONIMA` y `SIN_DUPLICADA`, y contra el padrón de hoy esa exigencia
aguanta.

**Corrección al plan:** la Fase 5 pasa de 733 altas + 54 vínculos a **655 altas
+ 132 vínculos**.

---

## 22. La credencial: qué se descartó y qué queda

`CREDENTIAL_INVALID`, y no por lo que parecía. Comparando configuración, sin
tocar el secreto:

| qué se revisó | `SUPABASE_DATABASE_URL` / `INTERNAL_DB_URL` |
|---|---|
| project ref en el host | **correcto** (`pggrvzyixyjkhfknpurg`) |
| forma | directa (`db.<ref>.supabase.co`), que es la que corresponde |
| usuario | `postgres`, correcto para conexión directa |
| puerto | 5432, correcto para directa |
| escaping | la clave es alfanumérica y `_`: **no hay nada que escapar** |
| resolución DNS | resuelve, sólo IPv6 |
| TLS | conecta |

**Y el servidor contesta.** Ése es el dato que cierra el diagnóstico:

```
FATAL:  password authentication failed for user "postgres"
```

Si el host, el puerto, el usuario, el SSL o el escaping estuvieran mal, el
error sería otro —o no habría error, habría timeout—. Que el servidor llegue a
evaluar la contraseña y la rechace deja una sola causa: **la contraseña ya no
es ésa.**

Se probó también el pooler, para descartarlo: `aws-0-us-east-1` responde
`tenant/user postgres.<ref> not found`, o sea que el pooler de este proyecto
vive en otro host. Es irrelevante: con la contraseña correcta la conexión
directa alcanza, y con la incorrecta ningún pooler ayuda.

**No se rotó nada.** Rotar sin necesidad invalidaría lo que use esa clave hoy.

---

## 23. El endpoint `/barrios` va a devolver datos falsos apenas vuelva la API

Esto apareció midiendo rendimiento y no es un problema de rendimiento.

`api/main.py::listar_barrios` le pide a PostgREST:

```
select=barrio & barrio=not.is.null & limit=1000
```

y después dedupe en Python con `sorted(set(...))`.

**`limit=1000` limita FILAS, no barrios distintos.** PostgREST devuelve las
primeras mil filas de la tabla, que pertenecen a un puñado de inmobiliarias
cargadas temprano.

| | |
|---|---|
| barrios distintos en producción | **5.732** |
| barrios que devolvería el endpoint | **25** |

El filtro de barrios del frontend mostraría **25 opciones de 5.732**, y ningún
error: una lista corta y plausible. Es la peor forma de estar mal.

Lo mismo aplica a `ciudad`: 924 distintas en producción, y cualquier endpoint
que use el mismo patrón devolvería una fracción.

**El arreglo no es un índice.** PostgREST no hace `DISTINCT`; hay que pedirlo
por una vista o una función. Las dos opciones tocan la base, así que van con la
decisión de diseño de §4, no antes.

**Mientras tanto conviene saberlo**: cuando la Fase 1 devuelva la API, este
endpoint va a responder 200 con una lista incompleta. Verde en el monitoreo,
roto en la pantalla.

---

## 24. 851 altas que no eran altas

Una ficha que cambia de slug —el sitio la renombra— deja de resolver por URL y
aparece como nueva. Insertarla duplica la propiedad. Por eso las 29.413 `NEW`
se volvieron a cruzar por una segunda llave: `(inmobiliaria_id, id_externo)`.

Primero, qué tan confiable es esa llave en producción:

| | |
|---|---|
| filas con `id_externo` | 108.305 de 257.073 (42 %) |
| pares `(agencia, id_externo)` distintos | 72.235 |
| pares de las 456 agencias que nos importan | 22.471, de los cuales **60 se repiten** |

**No es una llave única**, así que sirve para *descartar* un alta, nunca para
decidir sola qué fila actualizar.

Y el resultado sobre las 29.413:

| | candidatas | % |
|---|---|---|
| **NEW confirmada** | **28.556** | 97,1 % |
| **ya existe con otra URL** | **851** | 2,9 % |
| id_externo ambiguo | 6 | |

**851 altas habrían creado 851 duplicados.** Son la misma ficha con otro slug.

Quedan clasificadas `REVIEW_URL_CAMBIO` y **no se insertan**. Tampoco se
actualizan automáticamente: la resolución campo por campo se calculó contra
"no hay fila productiva", así que para esas 857 no sabemos qué escribir. Se
listan para que alguien las mire, que es lo único honesto que se puede hacer
con ellas hoy.

---

## 25. El catálogo está a un `GRANT` de ser público

Esto apareció en el advisor de **rendimiento**, no en el de seguridad, y es lo
más importante que encontró esta pasada.

`public.propiedades` tiene **tres políticas RLS**, y dos de ellas son
permisivas para `anon`:

| tabla | política | roles | condición |
|---|---|---|---|
| `propiedades` | `Public read active properties` | `anon` | `estado = 'activa'` |
| `propiedades` | `propiedades_public_read` | `anon`, `authenticated` | `estado = 'activa'` |
| `propiedades` | `eretz_preview_ro_read_active` | `eretz_preview_ro` | `true` |
| `inmobiliarias_main` | `public_read_main` | `anon`, `authenticated` | `activa = true` |

`estado = 'activa'` son **256.290 de 257.073 filas: el 99,7 %**.

### Por qué hoy no pasa nada

Verificado con la prueba que manda, no con el catálogo declarativo:

```
has_table_privilege('anon','public.propiedades','SELECT')          -> false
has_table_privilege('authenticated','public.propiedades','SELECT') -> false
```

**Falta el `GRANT`, y sin `GRANT` la política no se llega a evaluar.** Las
políticas están, escritas y permisivas, pero inertes.

Vale la pena decir cómo se comprobó, porque el primer método fallaba:
`information_schema.role_table_grants` sólo lista los permisos otorgados
*directamente* a un rol. Un `GRANT ... TO PUBLIC` aparecería con `grantee =
PUBLIC` y esa consulta lo pasaría por alto. `has_table_privilege` no: resuelve
herencia y `PUBLIC`. Las dos coinciden en que no hay permiso, pero sólo la
segunda lo prueba.

### Lo que esto significa

**Un solo `GRANT SELECT ON propiedades TO anon` publica 256.290 propiedades**,
sin migración, sin deploy y sin que nada más cambie. Y es exactamente lo que
haría alguien que quiera "abrir el catálogo": las políticas ya lo están
esperando.

Eso no es un defecto —el diseño de RLS para un catálogo público es
razonable— pero **cambia dónde está el interruptor**. La conversación de §4
sobre qué exponer no es sobre PostgREST: es sobre ese `GRANT`.

### Y confirma que la Fase 1 es segura

Exponer `public` no toca permisos. Después del cambio, `anon` va a seguir
recibiendo un error de permisos en `/rest/v1/propiedades`, no una lista.
`scripts/verificar_fase1.py` lo comprueba pidiéndolo de verdad con la anon key,
que es la única forma de estar seguro.

**Si después del cambio devolviera filas, el veredicto es rollback inmediato**,
y ahora sabemos qué habría que mirar: si apareció un `GRANT`.

---

## 26. Resto de los avisos de rendimiento

Ninguno urgente, y uno que conviene entender.

| nivel | qué | cuántos | lectura |
|---|---|---|---|
| WARN | dos políticas permisivas de `anon` en `propiedades` | 1 | es §25: redundantes entre sí, hacen el mismo trabajo dos veces |
| INFO | tablas sin clave primaria | 17 | **las 17 son tablas de backup**, no del producto |
| INFO | índices nunca usados | 9 | los contadores vienen de días con la API caída: no significan nada todavía |
| INFO | claves foráneas sin índice | 2 | las dos en `internal_scraping`, que no sirve consultas de producto |
| INFO | conexiones de Auth en número absoluto (10) | 1 | sólo importa si se agranda la instancia |

Las 17 tablas sin PK son las mismas que el advisor de seguridad marca por RLS
sin políticas. Son restos de migraciones —`backup_propiedades_run32_…`,
`backup_propiedades_duplicadas_url_…`— y limpiarlas es borrar, así que van al
plan de limpieza aparte, no acá.

---

## 27. Lo que esta auditoría todavía no cubre

Honestidad sobre el alcance:

- **No hay backup productivo tomado, y no es por falta de ventana.** La cola de
  certificación está detenida, así que lo intenté: la contraseña de
  `SUPABASE_DATABASE_URL` en `.env` **no autentica** (`password authentication
  failed for user "postgres"`), y la de `INTERNAL_DB_URL` es la misma. Además no
  hay `pg_dump` instalado. El script alternativo está escrito y verificado en
  `scripts/backup_productivo.py`; sólo le falta una credencial válida. Ver
  `ERETZ_SUPABASE_WRITE_PLAN.md`, Fase 0.
- **Falta la política de sobrescritura campo por campo.** §18 muestra qué
  difiere; decidir qué se pisa y qué no es una decisión de producto.
- **El rollback está ensayado sobre datos sintéticos con máscaras reales**, no
  sobre producción restaurada.
- **Las 22.158 propuestas geográficas necesitan recálculo** contra el estado
  actual, no revalidación. Ver §10.
