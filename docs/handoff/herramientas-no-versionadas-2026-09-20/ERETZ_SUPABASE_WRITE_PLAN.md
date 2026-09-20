# ERETZ Propiedades — Plan de escritura productiva

**Estado: `WAITING_USER_AUTHORIZATION`. Nada de este documento está ejecutado.**

Cada fase declara ESTADO ACTUAL → CAMBIO NECESARIO → RESULTADO ESPERADO, y las
que escriben están marcadas. El rollback de cada una está en
`ERETZ_SUPABASE_ROLLBACK_PLAN.md`.

Base fáctica: `ERETZ_SUPABASE_PRODUCTION_AUDIT.md`.

---

## Invariantes (se verifican antes y después de cada fase que escribe)

Si cualquiera falla, la fase se revierte y el plan se detiene.

| # | invariante |
|---|---|
| I1 | `SELECT count(*) FROM public.propiedades` nunca **baja**. Ninguna fase de este plan borra. |
| I2 | `hash_dedup` sigue siendo único y sin nulos. |
| I3 | Ninguna propiedad activa pasa a inactiva por efecto de este plan. La desactivación masiva **no** forma parte del plan. |
| I4 | Ninguna fila cambia de `inmobiliaria_id`. La atribución no se toca. |
| I5 | Ninguna fila gana geografía inventada: sólo se escribe geografía que la fuente publica y el catálogo resuelve sin ambigüedad. |
| I6 | El pipeline de certificación no se toca en ninguna fase: ni workers, ni scheduler, ni fingerprint. |
| I7 | Toda fase que escribe corre dentro de una transacción con conteos antes/después impresos. |

---

## Política de merge — APROBADA 2026-09-09

Regla que manda sobre todas: **un nulo nuestro nunca pisa un valor productivo.**

| familia | campos | qué puede hacer |
|---|---|---|
| **estructurales** | precio, moneda, operacion, tipo_propiedad, ambientes, dormitorios, banos, superficie_total, superficie_cubierta, provincia, direccion | completar **y sobrescribir** |
| **texto y fotos** | titulo, descripcion, imagenes | **sólo completar** |
| **geografía** | ciudad, barrio, latitud, longitud | **sólo completar**, y sólo si la fila pasó la validación geográfica |
| **identidad** | id, inmobiliaria_id, hash_dedup, url_normalizada | **nunca** |

Un valor estructural sólo sobrescribe si es no nulo, pasó validación, pertenece
a la misma propiedad, no está marcado como conflictivo y viene de evidencia
fresca.

**La excepción que agregó la validación de coordenadas** (auditoría §19): en una
fila donde la geografía se contradice a sí misma, `provincia` deja de ser
estructural y no se toca. Son 1.131 filas, y 354 de ellas vienen de dos agencias
donde el extractor leyó un nombre de calle como provincia.

Coordenadas: sólo las **40.491 demostrablemente válidas** quedan habilitadas, y
aun así **completan, no sobrescriben**. Las 2.007 restantes están bloqueadas.

---

## El dry-run con la política aplicada

`DATA_QUALITY/dry_run_politica.jsonl` — una línea por candidata, con clase, fila
productiva, campos iguales, distintos, a completar, a sobrescribir, a conservar,
`no_tocar`, motivo, alcance y clase geográfica.

| clase | filas |
|---|---|
| **NEW** | **28.536** |
| **UPDATE** | **27.112** |
| UNCHANGED | 1.138 |
| **REVIEW_URL_CAMBIO** | **857** |
| RETENIDA_WEB_AJENA | 762 |
| **NOT_PUBLISHABLE** | **22** |

Las 22 `NOT_PUBLISHABLE` aparecieron el 2026-09-10 diagnosticando una parada de
la cola: **no son propiedades**. Son páginas de archivo de WordPress
—`/property-city/barrio-vicente-lopez/`, que dice "1 a 3 fuera de 3
propiedades"—, de agente y de amenity, que entraron porque una estrategia
consume el sitemap índice entero en vez de sólo el sub-sitemap de fichas. Son
10 `/property-feature/`, 6 `/agente/`, 4 `/property-city/` y 2
`/property-type/`, en 4 agencias.

La causa vive en código congelado y espera la ventana semántica. El filtro del
dry-run es para que mientras tanto **no se escriba una categoría como si fuera
una propiedad**.

Las 857 `REVIEW_URL_CAMBIO` salieron de las 29.413 que parecían altas: su
`id_externo` ya está en producción con otra URL (auditoría §24). Son la misma
ficha renombrada. **No se insertan ni se actualizan**: se listan.

**Decisiones campo por campo, sobre las 28.252 filas que ya existen:**

| campo | completa | sobrescribe | conserva producción | no toca (nulo nuestro) |
|---|---|---|---|---|
| superficie_cubierta | 13.645 | 0 | 0 | 0 |
| latitud | 13.021 | 0 | 5.503 | 2.435 |
| longitud | 13.053 | 0 | 5.480 | 2.428 |
| banos | 11.003 | 2.654 | 0 | 1.363 |
| provincia | 10.417 | 786 | 440 | 0 |
| dormitorios | 10.064 | 3.167 | 0 | 1.406 |
| moneda | 8.360 | 1.480 | 0 | 1.842 |
| imagenes | 7.469 | 0 | **20.119** | 0 |
| titulo | 5.654 | 0 | **19.459** | 6 |
| precio | 5.459 | 2.977 | 0 | 1.127 |
| ambientes | 4.229 | 3.554 | 0 | 2.176 |
| superficie_total | 3.716 | 1.498 | 0 | 7.468 |
| descripcion | 1.601 | 0 | **23.834** | 1.208 |
| ciudad | 1.331 | 0 | 345 | 16.424 |
| direccion | 209 | 2.308 | 0 | 9.585 |
| barrio | 52 | 0 | 5.612 | 13.716 |
| operacion | 0 | 4.321 | 0 | 3.774 |
| tipo_propiedad | 0 | 3.613 | 0 | 1.744 |
| **TOTAL** | **109.283** | **26.358** | **80.792** | **66.702** |

**Cómo leer esto.** Se aportan **109.283 valores nuevos** a filas que hoy los
tienen vacíos. Se sobrescriben **26.358**, todos estructurales. Se conservan
**80.792** valores productivos que la política protege —23.834 descripciones,
20.119 galerías, 19.459 títulos— y **66.702** no se tocan porque el nuestro es
nulo.

Y las altas: de las 29.413 `NEW`, **1.091 entran con la geografía recortada**
—latitud y longitud en 1.091, provincia en 756, ciudad en 334, barrio en 244—
porque su geografía se contradice.

---

## Fase 0 — Backup verificable  ⟨ESCRIBE: no; BLOQUEADO⟩

**ESTADO ACTUAL.** No hay backup propio. Lo que se llamaba "backup de 129.572
filas" es el registro de reversión de una columna (auditoría §5). Existen los
backups automáticos de Supabase (PITR según plan), que no controlamos ni hemos
verificado restaurando.

**CAMBIO NECESARIO.** Un backup propio, comprobable, de las dos tablas que este
plan toca.

### Estado: `BLOQUEADO_POR_CREDENCIAL` y `RESTORE_TEST_BLOCKED`

La ventana ya está abierta —la cola de certificación está detenida, sin procesos
vivos— así que lo intenté. Falló, y por una razón que conviene saber:

```
FATAL:  password authentication failed for user "postgres"
```

**La contraseña de `SUPABASE_DATABASE_URL` en `.env` no es válida.** Tampoco la
de `INTERNAL_DB_URL`, que apunta al mismo host con el mismo usuario. La clave es
alfanumérica, sin caracteres que necesiten codificarse: no es un problema de
escapes, está rotada o mal copiada.

Vale la pena mirarlo aparte del backup: `INTERNAL_DB_URL` es la que usa el
pipeline interno para escribir en `internal_scraping`.

Y las herramientas tampoco están. Revisado:

| vía | estado |
|---|---|
| `pg_dump` / `pg_restore` / `psql` en el PATH | no |
| binarios bajo `C:\Program Files\PostgreSQL` | sólo dos DLLs sueltas |
| Docker / Podman (para un Postgres descartable) | no instalados, sin daemon |
| `winget` / `choco` | presentes |
| **sesión con permisos de administrador** | **no** |

El instalador de PostgreSQL para Windows necesita administrador, así que
**instalar el cliente requiere tu intervención**. Marcado
`RESTORE_TEST_BLOCKED`.

**La acción manual, si querés desbloquearlo**, en una terminal *como
administrador*:

```
winget install --id PostgreSQL.PostgreSQL.17 -e
```

Alcanza con las *Command Line Tools* del instalador; el servidor no hace falta
para `pg_dump`, aunque sí para probar la restauración. No hay que instalar nada
de terceros: `PostgreSQL.PostgreSQL` es el paquete del proyecto.

### Los dos caminos

**a) Con `pg_dump`** (preferible), una vez instaladas las client tools y con una
cadena de conexión válida:

```bash
pg_dump "$SUPABASE_DB_URL" \
  --format=custom --no-owner --no-privileges --compress=9 \
  --table=public.propiedades \
  --table=public.inmobiliarias_main \
  --file=eretz_prod_$(date +%Y%m%d_%H%M%S).dump
```

Verificación obligatoria —sin esto el backup no cuenta:

```bash
pg_restore --list eretz_prod_*.dump | grep -c 'TABLE DATA'   # debe ser 2
```

y restaurar a una base descartable, contando filas: **257.073** y **7.004**.

**b) Sin `pg_dump`**, ya escrito y listo para correr: `backup_productivo.py`.
Toma las dos tablas con `COPY ... TO STDOUT` dentro de una transacción
`READ ONLY` + `REPEATABLE READ` —o sea las dos del mismo instante—, las guarda
en CSV comprimido con encabezado, y al terminar cuenta las filas del archivo
contra el `count(*)` de la base. Sólo le falta una credencial que funcione.

Un dump que no se restauró no es un backup, es un archivo.

**RESULTADO ESPERADO.** Un `.dump` restaurado al menos una vez, con los dos
conteos coincidiendo.

---

## Fase 1 — Reponer el esquema expuesto  ⟨AUTORIZADA 2026-09-09 — pendiente de acción manual⟩

**ESTADO ACTUAL.** `authenticator` no tiene `pgrst.db_schemas`; PostgREST
levanta `pg_pgrst_no_exposed_schemas` y devuelve PGRST002 a todo. La API está
caída desde hace al menos 24 h.

**CAMBIO NECESARIO.** Poner `public` —y sólo `public`— en la lista de esquemas
expuestos, desde **Dashboard → Settings → API → Exposed schemas**, no por SQL.
El dashboard es la fuente de verdad de ese valor; escribirlo con `ALTER ROLE` lo
deja desincronizado y el siguiente cambio de configuración lo pisa.

**Por qué es seguro.** Ya está demostrado en la auditoría §3: `anon` y
`authenticated` no tienen SELECT sobre `propiedades` ni sobre ninguna tabla de
producto. Exponer `public` devuelve el endpoint; **no publica datos**. Lo único
que `anon` alcanzaría son los tres objetos de PostGIS, que son metadatos del
sistema espacial y no contienen información de nadie.

**RESULTADO ESPERADO.** `GET /rest/v1/` responde 200 con el documento OpenAPI en
vez de 503. En los logs de PostgREST desaparece `pg_pgrst_no_exposed_schemas` y
aparece `Config reloaded` seguido de `Schema cache loaded`.

**Esta fase es independiente de todas las demás.** Arregla la API y no toca un
solo dato.

### Estado: autorizada, no aplicada

**No tengo herramienta para cambiarlo.** El MCP de Supabase expone consultas,
migraciones, ramas y avisos, pero **ningún método para la configuración del
proyecto**. Y hacerlo por `ALTER ROLE authenticator SET pgrst.db_schemas` queda
desincronizado del dashboard y lo pisa el siguiente cambio de configuración, así
que no es un sustituto: es una trampa.

**La acción manual mínima**, en el dashboard del proyecto `pggrvzyixyjkhfknpurg`:

> **Settings → API → Exposed schemas**: dejar `public`. Guardar.

Nada más. No tocar Extra search path, no agregar `graphql_public` si no estaba,
no tocar JWT ni nada de esa pantalla.

### La verificación, ya escrita

`scripts/verificar_fase1.py` corre los siete controles que se pueden hacer por
HTTP con la anon key, y recuerda los tres que se hacen por SQL. Corrido **antes**
del cambio dice:

```
FALLA 1. PostgREST responde              propiedades -> HTTP 503 (sigue caido)
FALLA 2. el schema cache cargo           PGRST002 sigue apareciendo
OK    5. anon NO lee public.propiedades  HTTP 503 sin filas
OK    7. ninguna tabla de producto publicada
VEREDICTO: FASE 1 NO APLICADA O INCOMPLETA
```

Si después del cambio algún control de los grupos 5, 6 o 7 falla —o sea, si algo
que antes no se leía ahora se lee— el veredicto es **ROLLBACK INMEDIATO**:
vaciar Exposed schemas. **No** conceder ni quitar permisos para taparlo.

### La línea de base, tomada antes del cambio

| medida | valor el 2026-09-09 |
|---|---|
| `anon`/`authenticated` con SELECT en `public` | sólo `geography_columns`, `geometry_columns`, `spatial_ref_sys` |
| USAGE en `internal_scraping` | ninguno |
| `pgrst.db_schemas` en `authenticator` | ausente |
| tablas de `public` con RLS | 37 de 39 |
| `public.propiedades` | 257.073 filas |
| `public.inmobiliarias_main` | 7.004 filas |

---

## Fase 2 — Resolver identidad de las candidatas  ⟨ESCRIBE: no⟩

**ESTADO ACTUAL: HECHO.** El recuento completo está en la auditoría §16 y el
artefacto en `DATA_QUALITY/dry_run_escritura.jsonl` (58.427 líneas).

| clase | filas |
|---|---|
| NEW | **29.413** |
| UPDATE_CON_RIESGO | **28.054** |
| UPDATE | 197 |
| DUPLICATE | 1 |
| RETENIDA_WEB_AJENA | 762 |

Ya no es proyección: 47.204 claves productivas bajadas, cero colisiones.

**Las restricciones de la tabla también están verificadas** (auditoría §20):
cero violaciones del `CHECK` de `operacion`, cero del de `moneda`, cero
`hash_dedup` nulos, y **las 550 agencias de las candidatas existen y están
activas en `inmobiliarias_main`**. `UNRESOLVED_AGENCY` = 0: ninguna alta rebota
por la clave foránea.

**La comparación de contenido también está hecha** (auditoría §18): de las
28.250 filas que ya existen, **sólo 40 no cambian en nada**. `UNCHANGED` casi no
existe: las 28.252 son UPDATE de verdad.

**LO QUE FALTA, y es una decisión tuya, no un cálculo:** qué campos se
sobrescriben. Ver Fase 3.

Resolución por **dos llaves, en orden**, por lo que dice la auditoría §6:

1. `hash_dedup`
2. si no hay match, `(inmobiliaria_id, url_normalizada)`

Buscar sólo por `hash_dedup` insertaría duplicados de las ~4,3 % de filas cuyo
hash quedó desactualizado por las dos migraciones.

Clases de salida:

| clase | definición | acción en Fase 4 |
|---|---|---|
| `NEW` | ninguna llave hace match | INSERT |
| `UPDATE` | match, y al menos un campo difiere | UPDATE de los campos que difieren |
| `UNCHANGED` | match, ningún campo difiere | nada |
| `CONFLICT` | las dos llaves hacen match a **filas distintas** | no se escribe; se lista |
| `DUPLICATE` | dos candidatas resuelven a la misma fila productiva | no se escribe; se lista |
| `NOT_PUBLISHABLE` | no pasa el gate de calidad | no se escribe |
| `REVIEW_REQUIRED` | el UPDATE borraría un valor productivo existente | no se escribe; se lista |

**RESULTADO ESPERADO.** `DATA_QUALITY/dry_run_escritura.jsonl`, una línea por
candidata con su clase, su fila productiva si la tiene, y el diff campo por
campo. Más un resumen con los siete totales.

**Regla que gobierna Fase 4, y ahora con número:** un UPDATE **nunca** reemplaza
un valor productivo por `NULL`.

La auditoría §13 lo midió sobre 63 pares reales: producción tiene **145 valores
que nosotros no tenemos** —2,3 por fila, casi todos de ubicación (ciudad 35,
barrio 25, dirección 23)—. Escribir nuestros campos tal cual, con los NULL
incluidos, **borraría del orden de 60.000 valores productivos** sobre las ~26.500
filas que ya existen. Silenciosamente, y con cara de actualización exitosa.

La ganancia también es real y va en la dirección contraria: aportamos 218 campos
que producción no tiene —3,5 por fila: superficie cubierta, baños, coordenadas,
dormitorios—, o sea unos 92.000 valores nuevos. **El merge vale la pena
exactamente si se hace `COALESCE`-safe.**

---

## Fase 3 — Gate de calidad sobre el diff  ⟨ESCRIBE: no⟩

**ESTADO ACTUAL.** El gate ya corrió sobre las 58.427 y declaró **58.427
publicables, 0 rechazadas** (auditoría §11). No es que esté roto: gradúa el
**alcance** en vez de aceptar o rechazar. 100 % llega a FICHA y LISTADO, 73 % al
MAPA, y sólo **16 % al filtro por localidad**.

**CAMBIO NECESARIO.** Dejar de usar `publicable` como filtro —no descarta a
nadie— y escribir el **alcance** de cada fila. Y separar dos cosas que hoy se
mezclan:

- **alcance INSERT:** una candidata `NEW` entra con el alcance que tenga; no se
  descarta por no llegar al filtro de localidad.
- **alcance UPDATE:** se evalúa **campo por campo**. Una ficha con precio bueno
  y superficie mala aporta el precio; no se descarta completa.

### La política de sobrescritura ⟨decisión pendiente⟩

`COALESCE`-safe protege del NULL. **No protege de reemplazar algo bueno por algo
peor**, y §18 muestra que ese riesgo es concreto:

| campo | difiere | sobrescribir |
|---|---|---|
| precio, moneda, provincia, direccion | 6–14 % | **sí**: números y etiquetas que nuestras reglas de coherencia validan y el legacy no |
| ambientes, banos, dormitorios, superficie_total | 27–57 % | **sí**: el legacy llegó a guardar un timestamp en `ambientes` (§14) |
| latitud/longitud | 63 % | **sí, pero midiendo**: hay que ver cuántas de las nuestras caen dentro de la localidad declarada antes de pisar |
| **titulo** | 86 % | **a decidir**: no corregimos un error, cambiamos un texto por otro |
| **descripcion** | 98 % | **a decidir**: si producción tiene 800 caracteres y nosotros 200, "actualizar" empeora |
| **imagenes** | 95 % | **a decidir**: distinta cantidad no es mejor cantidad |

Propuesta por defecto, conservadora: **sobrescribir lo estructural, y en
`titulo`, `descripcion` e `imagenes` escribir sólo cuando producción no tiene
nada.** Es reversible y no pierde nada; ampliarla después es barato, y al revés
no.

**RESULTADO ESPERADO.** Cada línea del dry-run con su alcance, su lista
`no_tocar`, y la lista de campos habilitados a sobrescribir según la política
que autorices.

---

## Fase 4 — Upsert de propiedades  ⟨ESCRIBE: datos⟩ 🔒

**ESTADO ACTUAL.** Producción tiene 257.073 filas del pipeline legacy. Nuestras
candidatas nuevas no están.

**CAMBIO NECESARIO.** Aplicar el dry-run de la Fase 2, **en lotes de 1.000, cada
lote en su transacción**, en este orden:

1. `NEW` → INSERT
2. `UPDATE` → UPDATE de campos habilitados, `COALESCE`-safe (nunca a NULL)
3. el resto → no se toca

Sin `ON CONFLICT DO NOTHING` ciego: cada lote conoce de antemano qué es cada fila.

**El `COALESCE`-safe ya no es una recomendación, está medido y ensayado**
(auditoría §16 y §17): sin él se destruirían **62.283 valores productivos** en
el 99,3 % de las filas que ya existen. El ensayo local sobre las máscaras reales
dio 62.280 perdidos con el UPDATE ingenuo y **0** con el seguro, y su reversión
devolvió la tabla byte a byte.

Cada fila del dry-run trae su lista `no_tocar`: los campos que en esa fila no se
escriben porque producción tiene valor y nosotros no.

**Prerrequisitos innegociables:** Fase 0 verificada (hoy **bloqueada**), Fase 2
completa (hecha) y Fase 3 completa, `DUPLICATE` revisado —hay 1— y la pasada de
comparación de valores hecha.

**RESULTADO ESPERADO.** `count(propiedades)` sube exactamente en la cantidad de
`NEW`. Los invariantes I1–I5 se verifican después de cada lote.

---

## Fase 5 — Promociones y vínculos  ⟨ESCRIBE: datos⟩ 🔒

**ESTADO ACTUAL: revalidado fila por fila** contra el padrón de hoy
(auditoría §21). Artefactos en `DATA_QUALITY/revalidacion_promociones.jsonl` y
`revalidacion_vinculos.jsonl`.

| | clase | cuántas |
|---|---|---|
| vínculos | STILL_SAFE | **54** |
| promociones | STILL_SAFE | **655** |
| promociones | **NOW_EXISTS** | **78** |
| | AMBIGUOUS / CONFLICT / REVIEW | 0 |

**El plan cambia de forma:** ya no son 733 altas + 54 vínculos, son **655 altas
+ 132 vínculos**. Las 78 `NOW_EXISTS` tienen su dominio en
`inmobiliarias_main.web`: crearlas duplicaría la inmobiliaria.

**LO QUE FALTA.** `inmobiliarias_main.slug` es UNIQUE y las 655 altas todavía no
tienen slug calculado contra los 7.004 existentes. Sin eso, la primera colisión
aborta el lote.

**RESULTADO ESPERADO.** Dos listas sin solapamiento y ningún slug repetido. Los
54 vínculos ya validados pueden ir primero, porque no crean nada.

---

## Fase 6 — Geografía  ⟨ESCRIBE: datos⟩ 🔒

**ESTADO ACTUAL.** 22.158 propuestas, y una mala noticia (auditoría §10):
**están indexadas contra un estado anterior de la base.** Sobre 120, sólo 25
resuelven a una fila existente; producción perdió el `www.` de las URLs en la
migración del 2026-07-29 y el hash dejó de coincidir.

Geográficamente el trabajo es sólido: 58 % NOOP, 26 % SAFE_UPDATE, y los 3.531
"conflictos" son cuatro renombres canónicos —`Capital Federal` →
`Ciudad Autónoma de Buenos Aires` y tres más— sin un solo cambio de provincia.

**CAMBIO NECESARIO.** **Recalcular**, no revalidar: volver a resolver las
propuestas contra `public.propiedades` actual por `url_normalizada`, y recién
entonces clasificar:

| clase | acción |
|---|---|
| `NOOP` | producción ya tiene ese valor → no se escribe |
| `SAFE_UPDATE` | producción está vacía y la propuesta es inequívoca → se escribe |
| `CONFLICT` | producción tiene otro valor → **no se escribe**, se lista |
| `NOT_FOUND` | la fila no existe → se descarta |

`CONFLICT` no se resuelve automáticamente. Ya sabemos por qué: la corroboración
geográfica se probó y se revirtió porque `Villa del Parque`, `Mar del Plata` y
`Rosario` son indistinguibles en el catálogo. Pisar un valor productivo con una
propuesta ambigua es exactamente el error que ese revert evitó.

**RESULTADO ESPERADO.** Los cuatro totales **sobre el universo actual**, y sólo
los `SAFE_UPDATE` habilitados a escribir.

**Bloqueada hasta que el recálculo exista.** Aplicar el artefacto de hoy no sería
peligroso —casi todo daría `NOT_FOUND`— pero sería mentir sobre lo que se aplicó.

---

## Fase 7 — Duplicados  ⟨ESCRIBE: no⟩

**ESTADO ACTUAL.** Ya detectados y clasificados (auditoría §12), con
`ganadores_elegidos: 0`. 880 grupos, 2.140 filas: 763 dentro de la misma agencia
y 117 entre agencias distintas.

De los 514 grupos con evidencia, **207 son probablemente unidades distintas** y
sólo **32 son idénticos en todo lo visible**.

**CAMBIO NECESARIO.** Marcar los grupos como `POTENTIAL_DUPLICATE`. Nada más.

**No fusionar y no borrar**, ni siquiera los 32. Dos avisos idénticos pueden ser
dos unidades reales del mismo edificio publicadas con el mismo texto. La fusión
automática destruye información y no se revierte con un UPDATE.

---

## Fase 8 — Ciclo de vida  ⟨ESCRIBE: no en esta pasada⟩

**ESTADO ACTUAL.** 50.976 filas activas de las 456 agencias que también tienen
candidatas nuestras.

**CAMBIO NECESARIO.** **Ninguno.** Que una propiedad no aparezca en nuestra
extracción no prueba que se haya vendido: prueba que hoy no la vimos. Un
connector con un fallo transitorio desactivaría el catálogo de una agencia entera.

La desactivación masiva queda **fuera** de este plan. Cuando corresponda, pedirá
su propio plan, con evidencia de ausencia sostenida en varias corridas.

---

## Fase 9 — Índices y rendimiento  ⟨ESCRIBE: sí; sin propuesta todavía⟩

**ESTADO ACTUAL.** Medido con `EXPLAIN (ANALYZE, BUFFERS)` (auditoría §15). Dos
problemas reales:

- `idx_propiedades_tipo_operacion` es `(tipo_propiedad, operacion)`, pero el
  filtro más frecuente es `operacion` sola. Al ser la segunda columna, el
  `count(*)` recorre el índice entero: **139 ms**.
- `ciudad ILIKE '%x%'` —lo que PostgREST genera desde `main.py`— no puede usar
  ningún btree. El caso raro tarda **388 ms** contra 15 ms del común.

**CAMBIO NECESARIO.** Dos índices, ninguno aplicado:

```sql
CREATE INDEX CONCURRENTLY idx_propiedades_operacion_tipo
  ON public.propiedades (operacion, tipo_propiedad);

CREATE INDEX CONCURRENTLY idx_propiedades_ciudad_trgm
  ON public.propiedades USING gin (ciudad gin_trgm_ops)
  WHERE ciudad IS NOT NULL;
```

`pg_trgm` ya está instalada. `CONCURRENTLY` para no bloquear la tabla.

**Orden correcto: después de la Fase 1, no antes.** Con la API arriba se mide
con tráfico real en vez de con consultas inventadas, y se compara el `EXPLAIN`
de antes contra el de después. Un índice que no mejora un plan medido es peso
muerto que además se paga en cada INSERT de la Fase 4.

**No propongo eliminar ninguno de los diez índices actuales**: sus contadores de
uso vienen de días con la API caída y no significan nada todavía.

---

## Fuera de plan — la limpieza de producción

La auditoría §14 encontró cosas que hay que arreglar y que **este plan no
arregla**, porque arreglarlas es borrar o reasignar y eso necesita su propia
autorización, su propio backup y su propio rollback.

Se listan acá para que no se pierdan, no para ejecutarlas:

| qué | filas | por qué no va acá |
|---|---|---|
| propiedades a nombre de una agencia que no es la dueña del host | **29.962** | reasignar o borrar; el criterio hay que acordarlo |
| URLs que son enlaces de WhatsApp (`wa.me`) | 941 | son basura, pero borrar es borrar |
| `ambientes` con timestamps e identificadores | 7.063 | poner en NULL es destruir un dato, aunque sea malo |
| sucursales dadas de alta dos veces (misma web, dos `inmobiliaria_id`) | 17 pares, 2.362 URLs | fusionar agencias es irreversible |
| filas sin `url_normalizada` | 13.082 | quedan fuera del índice único parcial |
| coordenadas fuera de Argentina | 562 | |
| superficies mayores a 100.000 m² | 49 | |

**Ninguna de estas es un obstáculo para las Fases 1 a 10.** El upsert por
`(inmobiliaria_id, url_normalizada)` convive con todas: no las empeora y no
depende de ellas.

Lo único que cambia es cómo hay que leer la base: **una de cada nueve filas de
producción está atribuida a quien no corresponde**, y eso ya estaba ahí antes de
que escribiéramos nada.

---

## Fase 10 — Verificación final  ⟨ESCRIBE: no⟩

Los siete invariantes, los conteos de las dos tablas, y una comparación del
dry-run contra lo efectivamente escrito. Si algo no cierra, se ejecuta el
rollback de la fase correspondiente.

---

## Cómo probar la Fase 1 sin tocar producción

La forma limpia es una **branch de Supabase**: copia la base, se le pone el
esquema expuesto, se comprueba que PostgREST arranca, y se descarta.

**Las branches son de pago.** No la creo sin autorización explícita.

Alternativa sin costo, ya disponible: `eretz_preview_ro` permite validar por
conexión directa que los datos están y se leen, lo que separa "PostgREST no
arranca" de "los datos no están". Eso ya está comprobado y es lo que sostiene el
diagnóstico de la auditoría §2.
