# ERETZ Propiedades — base de Preview aislada

Fecha: 2026-08-27

> ## Estado: `DEFERRED_DB_EXECUTION`
>
> **La Preview DB no se crea.** Decisión tomada el 2026-08-27, después de
> comprobar por API que ninguna de las dos opciones cuesta USD 0 en el plan
> actual: un segundo proyecto son US$10/mes y un branch US$0,01344/hora.
>
> Estrategia vigente: **`PATH_B_NO_ADDITIONAL_INFRA_COST`**. Se sigue
> construyendo producto y queda congelado todo cambio que sería irresponsable
> probar directamente sobre la base real.
>
> Lo que eso significa en concreto:
>
> - no se ejecuta DDL, ni migraciones, ni `CREATE INDEX` sobre la base real;
> - no se aplica el P0 de ACL todavía, aunque esté listo y verificado;
> - no se aplica `eretz_gate` todavía;
> - no se corren benchmarks contra producción.
>
> **Nada de lo preparado se borra.** Todo el trabajo listado en "Qué está
> preparado y espera" queda como `READY_FOR_FUTURE_DB_EXECUTION` y se ejecuta
> sin rediseño el día que exista un entorno donde probarlo.
>
> El resto del documento se conserva porque sigue siendo la investigación
> válida —incluida la línea base medida sobre producción, que es lo que hará
> comparables las mediciones futuras—. Lo que cambió es cuándo se ejecuta.

## El problema que resuelve

Hoy **Vercel Preview ≠ Database Preview**. Existe un solo proyecto Supabase
(`pggrvzyixyjkhfknpurg`) con las 257.073 publicaciones reales, y
`eretz_preview_ro` es un **rol** dentro de esa única base, no otra base. Su
propio rollback lo dice:

```sql
revoke connect on database postgres from eretz_preview_ro;
```

Es decir: cualquiera que leyera "Preview DB" en un runbook y ejecutara una
migración habría estado tocando el dato real, convencido de lo contrario. Por
eso existe la guarda de destino (`frontend/scripts/db-target-guard.mjs`).

Para experimentar con DDL, índices, materialized views y rollbacks hace falta
una base separada de verdad.

## Acceso: MCP con OAuth, no un token pegado a mano

La documentación oficial de Supabase describe un servidor MCP hospedado con
**dynamic client registration**: no hace falta crear un Personal Access Token
manualmente, el cliente abre el flujo OAuth en el navegador.

Configuración, en `.mcp.json` del repositorio:

```json
{
  "mcpServers": {
    "supabase": {
      "type": "http",
      "url": "https://mcp.supabase.com/mcp?read_only=true&features=docs,account,database,debugging,development,branching"
    }
  }
}
```

Dos decisiones sobre esos parámetros:

- **`read_only=true` de entrada.** La primera conexión sirve para mirar
  —organización, proyectos, plan, versión de PostgreSQL— y para eso no hace
  falta poder escribir. Se quita cuando exista la base de Preview y haya algo
  que escribir *en ella*.
- **Sin `project_ref` todavía.** Acotar a un proyecto es lo correcto para
  trabajar, pero impide las operaciones de cuenta, y justamente la primera
  operación pendiente es **crear** un proyecto. Cuando la Preview exista, se
  agrega `project_ref=<ref-de-preview>` y ahí el alcance queda cerrado sobre
  ella.

No hay ningún secreto en ese archivo: la autorización vive en el flujo OAuth,
no en el repositorio.

### Estado: autorizado

El conector oficial de Supabase quedó autorizado desde la app de Claude el
2026-08-27, por OAuth y sin PAT manual. El `.mcp.json` del repositorio sigue
siendo la ruta alternativa para una sesión de terminal; no hizo falta.

Con ese acceso se ejecutó el reconocimiento de sólo lectura que está más abajo.
No se creó, modificó ni borró nada.

## Topología: ninguna opción cuesta cero

**Corrección (2026-08-27, verificada por MCP).** Una versión anterior de este
documento recomendaba "segundo proyecto Free, cuesta cero". Ese consejo se
apoyaba en un supuesto sobre el plan que resultó falso, y se corrige acá.

La organización `hztfazrsktpwgipbmtwb` está en **plan Pro**, no Free. Consultado
el costo por la API, no por deducción:

| | Branching | Segundo proyecto |
| --- | --- | --- |
| Costo consultado | **US$0,01344 por hora** mientras existe | **US$10/mes recurrente** |
| Equivalente mensual | ~US$9,7 si queda encendido; **~US$0,32/día** si se usa y se borra | US$10/mes hasta que se borre |
| Aislamiento | branch dentro del mismo proyecto | proyecto separado: otro `project_ref`, otro host |
| Se pausa por inactividad | no | no (en Pro) |
| Recursos | equivalentes a producción | equivalentes a producción |

En Free existe el límite de 2 proyectos activos y ese segundo proyecto sí sería
gratuito, pero **esta organización no está en Free**, así que ese camino no
aplica sin bajar de plan.

Consecuencia directa: la condición del encargo —*"antes de cualquier creación
confirmá que el segundo proyecto realmente cuesta USD 0"*— **no se cumple**, y
por eso no se creó nada. Hace falta una autorización de costo explícita.

**Recomendación, si se autoriza: branching.** Se invierte respecto de la
recomendación anterior, y por una razón concreta: un branch se borra cuando el
trabajo termina y deja de facturar, mientras que un segundo proyecto sigue
costando US$10/mes hasta que alguien se acuerde de borrarlo. Para un uso
acotado —bootstrap, ACL, gate, índices, benchmarks— el branch sale bastante
menos de un dólar. Además corre con recursos equivalentes a producción, así que
los tiempos absolutos **sí son comparables**, cosa que el Free no daba.

La contra honesta del branch: es una rama del proyecto que tiene el dato real,
no un proyecto aparte. El aislamiento es menor. Por eso la guarda de destino
(`db-target-guard.mjs`) sigue siendo obligatoria y no opcional: es lo que
impide que una migración se aplique al `project_ref` equivocado.

## El esquema base no está en el repositorio

Hallazgo al preparar el bootstrap, y cambia el orden de trabajo.

`public.propiedades` —la tabla que lee todo el frontend— **no está definida en
ningún archivo del repositorio**. Las migraciones de `supabase/migrations/` son
incrementales y dan por sentado que ya existe. `MIGRATION_ORDER.md` remite a una
*"sanitized schema baseline captured by the definitive audit"*, y esa baseline
tampoco está versionada.

Consecuencia concreta: **hoy no se puede levantar un entorno desde cero con lo
que hay en Git**, ni siquiera con MCP autorizado y un proyecto Preview creado.

Lo que NO se hizo, a propósito: escribir ese `CREATE TABLE` a partir de las
columnas que el código consulta. Serían tipos, nulabilidad, defaults, claves e
índices adivinados, y una base *parecida* es peor que no tener base — los
benchmarks medirían otra cosa y nadie lo notaría.

Lo que sí se hizo: `frontend/scripts/db-schema-contract.mjs` declara el
**contrato** —qué relaciones y columnas necesita la aplicación— derivado de lo
que el código realmente consulta, con un verificador de sólo lectura. Sirve para
comprobar que una Preview recién creada sirve *antes* de invertir horas en
cargarla, y para detectar deriva entre entornos.

Dos tests lo mantienen honesto: uno falla si el SQL de la aplicación menciona una
columna que el contrato no declara —la deriva silenciosa que dejaría de
protegernos sin que nada falle—, y otro falla si el contrato declara columnas que
nadie usa, porque un contrato inflado rechaza bases que servirían.

### El orden real, entonces

El paso 4 del orden de abajo cambia: antes de aplicar migraciones hay que
**capturar la baseline del esquema desde el proyecto actual**, con acceso de sólo
lectura, y versionarla sanitizada. Recién después el bootstrap es reproducible.

## Línea base medida sobre producción (sólo lectura)

Todo lo de esta sección se obtuvo con `SELECT` y `EXPLAIN`. Ninguna sentencia
modificó nada. Sirve como referencia contra la cual comparar la Preview.

### Entorno

| | |
| --- | --- |
| Proyecto | `pggrvzyixyjkhfknpurg` ("inmolink"), us-east-1 |
| PostgreSQL | 17.6.1.084, ACTIVE_HEALTHY |
| Branches existentes | 0 |
| Extensiones | postgis 3.3.7, pg_trgm 1.6, vector 0.8.0, pg_stat_statements 1.11 |
| Disponibles sin instalar | `hypopg`, `index_advisor` — **no se instalaron**: sería DDL sobre producción |

### Volumen

| | |
| --- | --- |
| `propiedades` | **257.073** filas (coincide con la auditoría) |
| con `estado='activa'` | 256.290 — el **99,7%** |
| con coordenadas | 65.033 — el 25,3% |
| Tamaño | 643 MB tabla + 142 MB índices |

### El camino de conteo

`EXPLAIN (ANALYZE, BUFFERS)` sobre lo que hace el frontend hoy:

```
Seq Scan on propiedades  (actual rows=256290 loops=1)
  Filter: (estado = 'activa'::text)
  Rows Removed by Filter: 783
  Buffers: shared hit=5777 read=41389
Execution Time: 1999.562 ms
```

Tres lecturas, y la tercera es la que cambia el plan de trabajo:

1. **2,0 s son sólo de base.** El resto de los ~20 s documentados está en
   transferir 256.290 filas a Node y filtrarlas ahí.
2. **Lee de disco, no de caché**: 41.389 buffers leídos contra 5.777
   acertados. Son ~368 MB por conteo.
3. **Un índice sobre `estado` no puede arreglar esto, y ya existe.**
   `idx_propiedades_estado` está creado y tiene 1.219 usos, pero el planner lo
   descarta con razón: cuando el filtro deja pasar el 99,7% de las filas, el
   Seq Scan es la opción correcta. Cualquier propuesta de "indexar `estado`"
   está descartada por medición, no por opinión.

### Los diez índices existentes

`propiedades` ya tiene 10 índices, 142 MB. Los dos menos usados son candidatos
a revisión —`idx_propiedades_precio_usd` (14 MB, 20 usos) y
`idx_propiedades_unique_inmobiliaria_url_normalizada` (40 MB, 42 usos)—, aunque
el segundo probablemente exista por su restricción de unicidad y no por
lecturas, así que **no se toca sin confirmar eso primero**.

### PostGIS está instalado y la tabla no lo usa

`propiedades` **no tiene ninguna columna `geometry` ni `geography`**. Las
coordenadas son numéricos sueltos con un btree parcial sobre
`(latitud, longitud)`.

Importa por dos motivos:

- un btree sobre dos columnas independientes sirve poco para consultas por
  bounding box o radio, que es lo que pide un mapa;
- PostGIS carga el **P0 de ACL** —`anon` y `authenticated` con
  INSERT/UPDATE/DELETE/TRUNCATE sobre `spatial_ref_sys`, `geography_columns` y
  `geometry_columns`, confirmado vigente hoy: 24 de 24 privilegios— sin que la
  tabla principal obtenga nada a cambio.

No se propone desinstalar PostGIS: puede haber otras tablas que sí lo usen. Se
deja anotado para decidirlo con datos en la Preview.

### Lo que dice `pg_stat_statements`

Las consultas más lentas de la base **no son del frontend**: son auditorías del
pipeline de scraping, con medias de 27 a 91 segundos y picos de hasta 432 s.
Ruido para este trabajo, pero vale saber que existen antes de leer cualquier
métrica agregada de la base y atribuirla a la web.

### Advisors de Supabase

Sin hallazgos nuevos. Confirman lo ya documentado: 25 tablas con RLS activo y
sin policy —casi todas backups, y sin policy el efecto es denegar todo— y las 3
extensiones en `public`. Nada de esto sube de prioridad.

## Qué está preparado y espera

Todo lo siguiente está escrito, testeado donde corresponde, y se ejecuta sin
rediseño en cuanto exista el `project_ref` de Preview:

| Artefacto | Qué hace |
| --- | --- |
| `frontend/scripts/db-target-guard.mjs` | impide correr DDL contra el proyecto equivocado |
| `supabase/proposals/20260827_public_postgis_acl_hardening.sql` | P0 de ACL, con preflight y validación en transacción |
| `…_acl_hardening.rollback.sql` | su rollback exacto |
| `…_acl_verify.sql` | verificación de sólo lectura, antes y después |
| `supabase/migrations/20260827120000_quality_gate_eligibility.sql` | schema `eretz_gate` con la invariante como CHECK |
| `supabase/rollbacks/20260827120000_…rollback.sql` | su rollback |
| `frontend/scripts/import-quality-gate.mjs` | importa el manifiesto con swap atómico |

## Orden de ejecución, cuando haya acceso

0. **Autorizar el costo.** Ninguna de las dos opciones es gratuita en el plan
   actual. Sin esta decisión el paso 1 no se ejecuta.
1. Crear el branch (o el proyecto) de Preview y anotar su `project_ref`.
2. Agregar `project_ref` al `.mcp.json` y quitar `read_only`.
3. Declarar el destino: `ERETZ_DB_TARGET_EXPECT=<ref-preview>` y
   `ERETZ_DB_PRODUCTION_REF=pggrvzyixyjkhfknpurg`. La guarda rechaza el
   segundo aunque alguien lo declare como esperado.
4. Bootstrap del esquema desde `supabase/migrations/`.
5. Sembrar el dataset representativo.
6. ACL P0: aplicar, verificar, **ensayar el rollback**, volver a aplicar.
7. Migración `eretz_gate` e importación del manifiesto.
8. Equivalencia OLD vs NEW antes de tocar el camino de lectura.
9. `EXPLAIN ANALYZE`, índices justificados, benchmarks antes/después.
10. Apuntar Vercel Preview a la base de Preview. **Producción no se toca.**

## Lo que no cambia

- la base real no recibe DDL experimental;
- Data API sigue apagada para el frontend;
- PostgreSQL server-only;
- Quality Gate fail-closed;
- ningún secreto versionado.
