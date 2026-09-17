# ERETZ Propiedades — Auditoría de seguridad, datos y rendimiento

Fecha de evidencia: 2026-08-27

Proyecto Supabase auditado: `pggrvzyixyjkhfknpurg`

Modalidad: sólo lectura; no se ejecutó DDL, DML, geocoding ni cambio remoto.

## Resumen ejecutivo

El frontend privado está correctamente aislado de Data API, usa PostgreSQL server-only y no envía credenciales al navegador. La exposición crítica pendiente está en ACL de PostGIS: `anon` y `authenticated` recibieron grants directos de escritura sobre tres objetos del schema `public`. No se hallaron privilegios de escritura equivalentes sobre tablas de negocio.

El inventario tiene buena cobertura de operación, tipo, publicador, estado y procedencia, pero cobertura débil de ubicación, precio normalizado, superficies, agentes y fecha de publicación. Los conteos fríos son lentos porque el Quality Gate se aplica después de transferir filas a Node.

## ACL y permisos efectivos

### P0 — grants PostGIS directos

ACL observada en los tres objetos:

```text
{supabase_admin=arwdDxtm/supabase_admin,
 postgres=arwdDxtm/supabase_admin,
 anon=arwdDxtm/supabase_admin,
 authenticated=arwdDxtm/supabase_admin,
 service_role=arwdDxtm/supabase_admin,
 =r/supabase_admin}
```

`arwdDxtm` otorga SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER y MAINTAIN. El grant es directo de `supabase_admin`; no proviene de una membresía de `anon` o `authenticated`. Los únicos miembros de esos roles relevantes son `authenticator` y `postgres`, en el sentido esperado por Supabase.

Objetos afectados:

| Objeto | Tipo | Owner | anon/auth write |
| --- | --- | --- | --- |
| `public.spatial_ref_sys` | tabla PostGIS | `supabase_admin` | Sí |
| `public.geography_columns` | vista PostGIS | `supabase_admin` | Sí |
| `public.geometry_columns` | vista PostGIS | `supabase_admin` | Sí |

`spatial_ref_sys` es el riesgo material: es una tabla real y no tiene RLS. Las vistas pueden no ser actualizables, pero sus grants siguen siendo innecesarios y deben retirarse.

La propuesta mínima y su rollback están en:

- `supabase/proposals/20260827_public_postgis_acl_hardening.sql`
- `supabase/proposals/20260827_public_postgis_acl_hardening.rollback.sql`

No fueron ejecutados.

### P1 — SECURITY DEFINER PostGIS público

Los tres overloads de `public.st_estimatedextent` son `SECURITY DEFINER`, tienen `search_path = pg_catalog, public` y conservan EXECUTE para PUBLIC, `anon` y `authenticated`:

```sql
public.st_estimatedextent(text, text)
public.st_estimatedextent(text, text, text)
public.st_estimatedextent(text, text, text, boolean)
```

El search path ya fue endurecido, pero la función acepta identificadores de relaciones y puede revelar metadatos de extensión. Antes de una Data API pública se debe probar un canary y luego considerar:

```sql
REVOKE EXECUTE ON FUNCTION public.st_estimatedextent(text, text) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.st_estimatedextent(text, text, text) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.st_estimatedextent(text, text, text, boolean) FROM PUBLIC, anon, authenticated;
```

No se preparó como cambio automático porque puede afectar consumidores PostGIS ajenos al frontend.

### P1 — políticas públicas latentes

Hay políticas de lectura para `anon` en propiedades, inmobiliarias, históricos, scores, tipo de cambio y métricas. Los grants de tabla a `anon/authenticated` están actualmente retirados, por lo que no son accesibles. Antes de reactivar Data API deben consolidarse las políticas duplicadas de `propiedades` y verificarse tabla por tabla.

### P2 — SELECT heredado de PUBLIC

PUBLIC conserva SELECT sobre `spatial_ref_sys`, `geography_columns` y `geometry_columns`. Por ello `eretz_preview_ro` y `eretz_app_writer` pueden leer esos objetos aunque no tengan grant directo. El frontend no consulta esos objetos. Retirar este SELECT puede afectar funciones PostGIS y requiere canary separado.

### P2 — schema y extensiones

- `public`: PUBLIC, `anon` y `authenticated` tienen USAGE, no CREATE.
- PostGIS, pg_trgm y vector están instaladas en `public`; conviene mover extensiones futuras a schemas dedicados cuando sea viable.
- Existen numerosos backups en `public`; casi todos tienen RLS deny-all, pero uno no tiene RLS. Ninguno concede SELECT a `anon/authenticated` hoy. Deben salir del schema expuesto por higiene y reducción de superficie.

### Storage

`anon/authenticated` tienen grants estándar sobre tablas de `storage`, pero RLS está activo y no existe ninguna policy: acceso efectivo a filas queda cerrado. No hay buckets/policies públicos configurados desde Supabase Storage para esta aplicación; el Quality Gate usa Vercel Blob privado.

## Cobertura de propiedades

Base total: 257.073 publicaciones.

| Campo/señal | Con dato válido | Cobertura | Nulos/ausentes o no válidos | Observación |
| --- | ---: | ---: | ---: | --- |
| Precio > 0 | 168.385 | 65,50% | 88.688 | Sin ceros/negativos; parte carece de moneda |
| Moneda | 153.081 | 59,55% | 103.992 | USD 101.069; ARS 52.012 |
| `precio_usd` > 0 | 94.594 | 36,80% | 162.479 | No usar como cobertura nacional sin metodología |
| Operación | 257.073 | 100% | 0 | Normalizada |
| Tipo | 257.073 | 100% | 0 | 13 valores observados |
| Dirección | 176.645 | 68,71% | 80.428 | Calidad heterogénea |
| Barrio | 207.954 | 80,89% | 49.119 | Puede ser country/desarrollo/zona |
| Ciudad | 111.009 | 43,18% | 146.064 | Bloqueo para SEO/mercado geográfico |
| Provincia | 110.963 | 43,16% | 146.110 | Bloqueo para agregación confiable |
| Coordenadas válidas AR | 64.471 | 25,08% | 192.602 sin mapa | 562 pares fuera del bounding conservador |
| Superficie total > 0 | 118.329 | 46,03% | 138.744 | 49 valores >100.000 m² requieren revisión |
| Superficie cubierta > 0 | 1.831 | 0,71% | 255.242 | Cobertura insuficiente |
| Ambientes informado | 130.762 | 50,87% | 126.311 | 2.251 ceros; 7.200 fuera de 0–100 |
| Dormitorios informado | 106.767 | 41,53% | 150.306 | 2.779 ceros; 2.790 fuera de 0–100 |
| Baños informado | 117.488 | 45,70% | 139.585 | 3.782 ceros; 5.179 fuera de 0–100 |
| Cocheras informado | 772 | 0,30% | 256.301 | No sirve para facets completos |
| Expensas > 0 | 275 | 0,11% | 256.798 | Máximo imposible: 48.000.050.000.400.000 |
| Apto crédito conocido | 552 | 0,21% | 256.521 | Los 552 son true; no existe false explícito |
| Imágenes | 178.232 | 69,33% | 78.841 | Calidad de URL no equivale a imagen sana |
| Descripción utilizable | 172.278 | 67,02% | 84.795 | Umbral mínimo 20 caracteres |
| Inmobiliaria enlazada | 257.073 | 100% | 0 | No implica ownership formal |
| Agente | 8.721 | 3,39% | 248.352 | Campo libre y contaminado |
| Fecha de publicación | 0 | 0% | 257.073 | Bloquea días en mercado reales |
| Estado | 257.073 | 100% | 0 | 256.290 activas |
| Fuente de extracción | 250.872 | 97,59% | 6.201 | Long tail de fuentes |
| CMS origen | 106.709 | 41,51% | 150.364 | No es provenance completa |

Extremos observados confirman contaminación: ambientes hasta 1.765.290.777, dormitorios hasta 12.345.689, baños hasta 1.165.164.932, superficie total hasta 12.200.000 y precio hasta 900.000.950.000. No deben mostrarse, agregarse ni usarse en Mercado sin reglas de validez.

### Cobertura por fuente

Las fuentes estructuradas dominantes son más completas: `tokko_html` aporta 61.243 filas, 98,3% con imagen, 99,8% con ciudad y 55,6% con coordenadas; `json_ld` aporta 14.414, 100% con imagen, 99,8% con ciudad y 83,5% con coordenadas. Varias fuentes específicas tienen 0% de ciudad/coordenadas o 0% de precio. La calidad debe medirse por versión de parser y fuente, no sólo globalmente.

## Confianza geográfica

| Categoría | Cantidad | Porcentaje |
| --- | ---: | ---: |
| Alta | 25.977 | 10,10% |
| Aproximada | 14.668 | 5,71% |
| Dudosa | 23.826 | 9,27% |
| Sin ubicación | 192.602 | 74,92% |

Hay 4.256 grupos de coordenadas compartidas que contienen 40.561 publicaciones; 2.193 grupos mezclan direcciones y 518 mezclan ciudades. La metadata de geocoding sólo cubre una fracción y usa Nominatim con precisión/status heterogéneos. No corresponde usar la palabra “exacta”.

## Inmobiliarias

Base: 7.004.

| Campo | Cantidad | Cobertura |
| --- | ---: | ---: |
| Nombre | 7.004 | 100% |
| Web | 5.210 | 74,39% |
| Teléfono | 6.791 | 96,96% |
| Email | 3.528 | 50,37% |
| Dirección | 6.180 | 88,24% |
| Ciudad | 6.853 | 97,84% |
| Provincia | 6.929 | 98,93% |
| Logo | 34 | 0,49% |
| Descripción | 0 | 0% |
| Slug persistido | 138 | 1,97% |
| Coordenadas válidas | 0 | 0% |
| Con publicaciones activas | 3.187 | 45,50% |
| Verificada | 0 | 0% |

Los perfiles públicos actuales pueden listar inventario y contacto, pero no sostienen todavía miniportales completos, branding, sucursales ni verificación.

## Agentes

No existe tabla de agentes. Los datos se derivan de `propiedades.agente_nombre` y `agente_telefono`.

- 8.721 publicaciones con nombre de agente.
- 511 nombres crudos distintos; 507 claves normalizadas.
- 482 claves (95,07%) aparecen en una sola inmobiliaria; 25 en varias.
- 447 claves (88,17%) tienen algún teléfono.
- No existe email de agente estructurado; 15 nombres contienen un email.
- 128 claves (25,25%) parecen genéricas o ruido de extracción (`Contacto`, `Admin`, `Enviar`, etc.).

Antes de perfiles completos se necesita una entidad estable, provenance, normalización, asociación confirmada y revisión de nombres contaminados.

## Señales de duplicación

Las siguientes cifras son candidatos, no duplicados confirmados:

| Señal compartida | Grupos | Filas afectadas | Cruce de publicador |
| --- | ---: | ---: | ---: |
| `hash_dedup` | 0 | 0 | 0 |
| URL normalizada | 31.771 | 66.179 | Restringida por índice dentro de cada inmobiliaria |
| Dirección + ciudad normalizadas | 21.891 | 89.807 | 13.848 grupos |
| Coordenada redondeada a 6 decimales | 4.256 | 40.561 | 2.222 grupos |
| Primera imagen | 15.944 | 53.946 | 11.601 grupos |

Modelo futuro obligatorio:

```text
PROPIEDAD_FISICA 1 ── N PUBLICACION N ── 1 PUBLICADOR
                              └──── N ── N AGENTE
```

Niveles propuestos:

- `CONFIRMED`: evidencia determinista aprobada o relación declarada por el publicador.
- `HIGH_CONFIDENCE`: dirección/coords/superficie/imágenes compatibles y sin contradicción material.
- `POSSIBLE`: una o dos señales, sin fuerza para fusionar.
- `NO_MATCH`: contradicciones o evidencia insuficiente.

Nunca fusionar automáticamente sólo por coordenada, dirección, precio, teléfono o imagen.

## Rendimiento de búsqueda y conteos

Planes medidos con `EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)`:

| Consulta | Plan | Filas relevantes | Tiempo DB |
| --- | --- | ---: | ---: |
| Conteo actual sin filtros | Seq Scan + transferencia de IDs/coords | 257.073 | 1.360 ms |
| `Palermo` + venta | Seq Scan + hash join + `translate/concat LIKE` | 174.884 inspeccionadas | 2.103 ms |
| Orden inicial, limit 96 | Parallel Seq Scan + top-N sort | 257.073 | 1.347 ms |
| Viewport BA, limit 6.000 | Bitmap index `idx_propiedades_latlon` | 28.955 | 196 ms |

El conteo no ejecuta `COUNT(*)`: trae `id/latitud/longitud` y aplica el Quality Gate en Node. El costo frío observado de hasta ~20 s incluye lectura, transferencia y filtrado JS.

Mejoras propuestas, no ejecutadas:

1. Persistir una tabla/version de elegibilidad del Quality Gate o cargar sus IDs a una relación privada y hacer `COUNT(*) FILTER` en DB.
2. Precalcular facets por versión del gate y filtros de alta cardinalidad.
3. Crear una columna/expresión de búsqueda normalizada con índice GIN trigram o FTS; evitar `translate(lower(concat_ws(...)))` por request.
4. Reescribir recencia como columnas ordenables e indexar `(publicable, estado_prioridad, id DESC)` o equivalente.
5. Agregar índices compuestos sólo después de medir workload: operación/tipo/moneda/precio y ubicación.
6. Mantener keyset; no volver a OFFSET profundo.
7. Cachear conteos con clave de versión del gate y TTL observable.
8. Usar conteo aproximado sólo para vistas exploratorias, nunca cuando el texto promete exactitud.

## Reportes, bajas y correcciones

- `POST /api/reports` valida tamaño, motivo y email; inserta únicamente mediante `eretz_app_writer` cuando está configurado.
- `reportes_publicacion` tiene RLS, policy de INSERT sólo para writer, estado y trazabilidad temporal. Hoy contiene 0 filas.
- El Preview read-only devuelve 503 cuando la persistencia es obligatoria y el writer no existe; no declara éxito falso.
- `/baja-o-correccion` deriva a email y no crea expediente estructurado.
- No hay rate limit, CAPTCHA/BotID, fingerprint de dedupe, cola administrativa, SLA, historial de resolución ni notificación al denunciante.

Para beta pública se requiere rate limiting, dedupe temporal, auditoría de cambios de estado, panel/cola operativa, retención y runbook de abuso. Un reporte nunca debe retirar automáticamente una publicación.

## Observabilidad

Actual:

- errores UI recuperables;
- `console.error` server-side con mensajes sanitizados;
- runtime/build logs de Vercel;
- evento local `eretz:analytics`, sin consumidor persistente;
- sin requests browser-side a Supabase.

Falta para beta:

- request ID y logs JSON estructurados;
- tasa de error y latencia p50/p95/p99 por endpoint;
- disponibilidad y saturación de DB/pooler;
- estado/versión del Quality Gate y fallos de Blob;
- búsquedas sin resultado, errores de imágenes y mapa;
- incidentes auth y rate-limit hits;
- alertas, SLO y runbooks.

La primera mejora sin proveedor debe ser un logger estructurado server-only con allowlist, redacción, duración, ruta y outcome. No se implementó en esta ejecución porque modifica todas las rutas críticas y merece un bloque probado propio.

## Revisión de la propuesta P0 (2026-08-27, ejecución posterior)

La propuesta y su rollback fueron revisados línea por línea. **No se ejecutaron**:
son un cambio remoto de base y requieren autorización explícita.

El SQL está bien construido: transacción, preflight que aborta si falta un objeto
o un rol, revoca **sólo** privilegios de escritura dejando `SELECT` intacto, y
valida dentro de la misma transacción, de modo que si algún privilegio efectivo
sobrevive, revierte en vez de dejar el trabajo a medias.

Cuatro observaciones, ninguna bloqueante:

1. **`MAINTAIN` existe desde PostgreSQL 17.** La evidencia de la ACL lo confirma
   —la `m` de `arwdDxtm` es exactamente ese privilegio— así que el cluster es 17+.
   Pero conviene saber que, en un cluster anterior, el `REVOKE` fallaría al
   **parsear**, antes de que el preflight llegue a correr. El fallo es seguro
   (no se aplica nada), pero el mensaje no diría lo que pasa.

2. **La validación usa `has_table_privilege`, que mide privilegio efectivo**, no
   la ACL literal: incluye lo que llega por `PUBLIC` o por pertenencia a otro
   rol. Es la comprobación correcta —es más estricta que el `REVOKE`— pero
   implica que si `PUBLIC` ganara escritura en el futuro, el script revocaría
   bien y aun así revertiría. Quien opere debe leer ese error como "hay otra
   fuente de privilegio", no como "el revoke falló".

3. **El rollback restaura los privilegios, no el otorgante.** Los grants
   originales figuran como `arwdDxtm/supabase_admin`. Si el rollback corre como
   `postgres`, la ACL queda equivalente en privilegios pero no idéntica en
   texto. No cambia el efecto; sí cambia lo que se ve al comparar.

4. **El rollback reabre la exposición P0**, que es su trabajo. Conviene que
   quien lo ejecute lo sepa antes y no después.

### Verificación de sólo lectura

Se agregó `supabase/proposals/20260827_public_postgis_acl_verify.sql`. No cambia
nada y corre con `eretz_preview_ro`. Responde tres preguntas sin depender de la
memoria de nadie: si la exposición sigue ahí, si se cerró, y si volvió. Incluye
la versión del servidor (por el punto 1), el origen del privilegio —grant directo
frente a herencia, que son dos problemas distintos y se arreglan distinto— y el
inventario de `SECURITY DEFINER` públicos, que queda medido aunque esta propuesta
no lo toque.

## Observabilidad y antiabuso implementados

Dos de los pendientes que este documento marcaba dejaron de estarlo. Los dos son
código de aplicación: **no se tocó la base ni se contrató ningún proveedor**.

**Logs estructurados con request ID.** Una línea JSON por request a stdout —lo que
Vercel ya recolecta— en las 7 rutas de API. El caso que cierra es concreto:
`/api/properties/counts` hacía `catch { return 503 }`, así que desde afuera un
timeout de la base, una credencial vencida y un bug de parseo se veían igual. Y
cuando alguien reportaba "me tira error al buscar" no había forma de encontrar
esa request entre las demás; ahora el id viaja en la respuesta y se puede citar.

Dos reglas sobre qué se escribe: ningún valor de entrada —los filtros son texto
que tipeó una persona— sino los nombres de los parámetros; y todo pasa por un
redactor, sin confiar en quien llama, porque un error de `postgres` trae la
cadena de conexión completa con usuario y contraseña dentro del mensaje.

**Freno de abuso en reportes y reclamos.** Tasa por endpoint y deduplicación por
contenido. Con un límite que conviene no perder de vista: el estado vive en
memoria del proceso, y en Vercel cada instancia tiene la suya. Es un badén, no un
control distribuido: frena el bucle trivial y no frena a quien rote origen. Para
beta pública hace falta un almacén compartido, y por eso el estado está detrás de
una interfaz en vez de desparramado por las rutas.

Un duplicado responde `received`, no "duplicado": decirle eso a alguien que
reporta un problema real suena a que no se le dio curso. Y la guarda corre
**después** de validar, porque si un 422 gastara cuota bastaría con mandar basura
para dejar sin servicio a quien reporta de verdad desde la misma red.

## Credenciales de base: qué existe y qué no (2026-08-27)

El bloque de hardening y performance quedó **detenido antes de ejecutar nada**.
El motivo no es una decisión de criterio sino una comprobación:

**No existe una base de datos de Preview separada.** `eretz_preview_ro` es un
**rol** dentro de la única base del proyecto `pggrvzyixyjkhfknpurg` —el rollback
del rol dice `revoke connect on database postgres from eretz_preview_ro`— y ese
proyecto es el que contiene las 257.073 publicaciones y las 7.004 inmobiliarias
reales. "Preview" en esta arquitectura es un **entorno de despliegue de Vercel**
que se conecta de sólo lectura a esa misma base, no una copia.

Evidencia recogida:

| Comprobación | Resultado |
| --- | --- |
| Project refs distintos en el repo | uno solo: `pggrvzyixyjkhfknpurg` |
| `supabase/config.toml` | `project_id = "eretz-propiedades"`, `major_version = 17` |
| `frontend/.env.local` | sin ninguna URL de base (sólo `VERCEL_OIDC_TOKEN`) |
| Variables de DB en el entorno | ninguna |
| `vercel env ls preview` | `SUPABASE_DATABASE_URL` y `ERETZ_WRITE_DATABASE_URL` existen, marcadas **Sensitive** |
| `vercel env pull` de esas dos | 11 caracteres, sin `@`: Vercel no descifra las Sensitive |
| Único DSN en disco | usuario `postgres` (superusuario), contraseña ya probada vencida |

De ahí que no haya camino: la credencial de Preview **no se puede recuperar por
diseño**, y la única que existe es la del superusuario sobre la base real, que
además no debe usarse para saltear la restricción de privilegio mínimo.

`major_version = 17` confirma, de paso, el punto 1 de la revisión anterior:
`MAINTAIN` es válido en este cluster.

### Qué haría falta para desbloquearlo

Una de estas dos, y son decisiones distintas:

1. **Una credencial con privilegio suficiente** para el DDL —crear objetos en un
   schema privado, y `REVOKE` sobre los objetos PostGIS— disponible como
   variable de entorno local. Aplicaría sobre la base real, con su rollback.
2. **Una base de Preview de verdad**: un proyecto Supabase aparte con una copia
   del esquema, donde probar sin tocar el dato real. Es más trabajo y es lo que
   la palabra "Preview" promete.

La segunda es la que corresponde si se quiere ensayar rollbacks e índices sin
riesgo. La primera alcanza para el P0 de ACL, que es acotado y reversible.

## Beta readiness

### Beta privada — YES WITH CONDITIONS

- usar Preview protegido;
- aplicar/revisar el P0 de ACL antes de cualquier Data API;
- aceptar que reportes/reclamos pueden estar deshabilitados sin writer;
- monitoreo manual de runtime y Quality Gate;
- QA remota del commit exacto cuando Vercel permita nuevo Preview.

### Beta pública — NO

Bloqueantes: ACL P0, política de indexación, observabilidad/alertas, persistencia antiabuso de reportes, runbook de incidentes, términos/privacidad revisados, performance de conteos y criterio explícito de publicación/retirada.

### Producción pública — NO

Además de lo anterior: SLA operacional, backups/restore probados, geocoding/provenance, calidad mínima por campo/fuente, ownership y administración, métricas de disponibilidad, seguridad continua y release/rollback probado.
