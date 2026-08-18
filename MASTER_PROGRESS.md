# ERETZ Propiedades — MASTER_PROGRESS

> Documento de handoff interno de la misión **ROOMIX AGENCY UNIVERSE → ERETZ AGENCY DIRECTORY**.
> Objetivo del documento: que ninguna sesión futura obligue al usuario a repetir el contexto.

**Última actualización:** 2026-08-18
**Fase actual:** `BLOQUEADA EN ENTORNO REMOTO` (ver §4)

---

## 1. Objetivo maestro (estable, NO renegociar)

Obtener **todas** las inmobiliarias que Roomix permita identificar, deduplicarlas contra ERETZ,
incorporar las faltantes a Supabase (solo staging) y encontrar/verificar la **web oficial** de cada una.

Roomix se usa **exclusivamente como directorio indirecto de inmobiliarias**. Las propiedades
publicadas en Roomix **no son el objetivo**: se abre la ficha individual únicamente porque el
anunciante solo aparece ahí, en el bloque *"Publicado por"*.

**No** se importan de Roomix: precios, descripciones, fotos, amenities ni características.

Secuencia comprometida:

1. Crawl exhaustivo de Roomix → padrón de anunciantes
2. Dedupe / canonicalización (aliases)
3. Crosswalk contra ERETZ (`inmobiliarias_main` **y** `inmobiliarias_staging`)
4. Alta en staging únicamente de `HIGH_CONFIDENCE_NEW` de tipo inmobiliaria/oficina
5. Descubrimiento y verificación de web oficial de **todas** las inmobiliarias canónicas
6. **DETENERSE.** El scraping directo de propiedades es una misión posterior
   (*AGENCY SOURCE DISCOVERY + DIRECT WEBSITE SCRAPING*) y **no** se inicia ahora.

Fuera de alcance en esta misión: todo el frente frontend (Roomix Fidelity, CSS, Identity V2,
home, explorer, cards, mapas, Lighthouse, Playwright RC, responsive).

---

## 2. Estado VERIFICADO en este entorno (sesión remota, 2026-08-18)

Todo lo de esta sección fue comprobado directamente. Es la única parte del documento que
constituye evidencia de primera mano.

| Comprobación | Resultado |
|---|---|
| Working dir | `/home/user/eretz-propiedades` (contenedor Linux efímero, clon fresco) |
| Rama activa | `claude/roomix-agency-universe-ndvrfu` |
| HEAD | `15e8199` — *fix: handle manifest duplicate hash conflicts after pilot (#8)* |
| Árbol | limpio |
| Rama `feat/roomix-agency-coverage` | **NO EXISTE** — ni local ni en `origin` (`git ls-remote --heads origin`) |
| Commit `10e622d690` | **NO EXISTE** en ningún ref del repositorio |
| `MASTER_PROGRESS.md` previo | **NO EXISTÍA** (este archivo lo crea por primera vez) |
| `ERETZ_AGENCY_DATA/` | **NO EXISTE** (búsqueda en todo el filesystem) |
| `roomix_agency_directory.jsonl` | **NO EXISTE** |
| Código del crawler Roomix | **NO EXISTE** en el repo (0 archivos con `roomix` en el nombre) |
| Proceso del crawler | **NO PRESENTE** (era una tarea programada de **Windows**, en la máquina local del usuario; inalcanzable desde un contenedor Linux en la nube) |
| `SUPABASE_DATABASE_URL` | **NO DEFINIDA**. Solo existe `.env.example` con placeholders; no hay `.env` |
| Suite de tests en el repo | **3 archivos** en `tests/` — no los 538 tests reportados |

**Conclusión:** el trabajo previo de Agency Coverage vive íntegramente en la máquina local
(Windows) del usuario y **nunca fue pusheado**. Coherente con la propia regla de la misión
(«NO push», «datos masivos fuera del repo»), pero implica que este entorno remoto no tiene
acceso a nada de ello.

---

## 3. Estado REPORTADO por el usuario (NO verificado aquí)

> ⚠️ **Regla 13 — no repetir el error histórico.** Estos números provienen del brief del usuario,
> describen el entorno local Windows y **no** pudieron verificarse en esta sesión. No mezclar
> contador vivo con artefacto congelado. No presentarlos como finales ni como verificados.

### Crawler
- Progreso: **18.120 / ~168.563 fichas**
- Ejecución: tarea persistente de Windows, checkpoint automático
- Estado reportado: vivo y avanzando

### RAW vs CANONICAL (métricas distintas — invariante `RAW >= CANONICAL`)
| Métrica | Valor reportado |
|---|---|
| `RAW_PUBLISHER_IDENTITIES` (agent_id distintos) | 4.772 |
| `CANONICAL_PUBLISHER_ENTITIES` (tras consolidar aliases) | 4.728 |
| Aliases fusionados | 44 |

### Clasificación canónica (provisional)
| Tipo | Cantidad |
|---|---|
| INMOBILIARIA | 3.073 |
| AGENTE | 1.064 |
| UNKNOWN | 285 |
| OFICINA_FRANQUICIA | 263 |
| DESARROLLADORA | 40 |
| MARCA_GENERICA | 2 |

**Inmobiliaria real = `INMOBILIARIA` + `OFICINA_FRANQUICIA`.**

### Franquicias (provisional)
RE/MAX ≈191 oficinas · Century 21 decenas · Coldwell Banker ≈29 · Keller Williams varias ·
Toribio Achaval · Interwin · otras por aparecer.

### KPI marginal — nuevas entidades inmobiliarias por 1.000 fichas
| Ventana | KPI |
|---|---|
| 1–2k | 432,5 |
| 2–4k | 259,0 |
| 4–6k | 211,5 |
| 6–8k | 182,5 |
| 8–10k | 133,0 |
| 10–12k | 135,5 |
| 12–14k | 112,5 |
| 14–16k | 101,0 |
| 16k–17,72k | 93,6 |

El KPI se mide **por ventanas**, nunca acumulado. **El KPI NO es criterio de corte**: aunque baje
a 1, no se detiene. El objetivo es *todas* las inmobiliarias, no una muestra ni convergencia.

### Otros
- Tests reportados: **538 verdes**
- Verificador de webs oficiales: ya construido, **17 tests** específicos

---

## 4. BLOQUEO ACTUAL

Esta sesión remota **no puede continuar la misión**. No es un problema de contexto, de tiempo ni
de duración del proceso (ninguno de los cuales sería bloqueo válido). Son tres carencias
materiales e independientes:

1. **No existe el punto de continuación.** La rama `feat/roomix-agency-coverage` y el commit
   `10e622d690` no están en `origin`. Todo el código del crawler, del canonicalizador, del
   matcher y del verificador de webs es inaccesible desde aquí.
2. **No existen los datos de entrada.** `ERETZ_AGENCY_DATA/roomix_agency_directory.jsonl` y los
   checkpoints del crawler están fuera del repo, en la máquina local. Sin el padrón no hay
   dedupe, ni crosswalk, ni canary, ni rollout, ni búsqueda de webs.
3. **No existe la credencial indispensable.** `SUPABASE_DATABASE_URL` no está definida en este
   entorno, por lo que el DB bridge (`SET LOCAL ROLE eretz_agency_coverage_writer`) no puede
   usarse. Sin ella no hay lectura de `inmobiliarias_main` / `inmobiliarias_staging` ni escritura
   en staging.

**Lo que deliberadamente NO se hizo, y por qué:**

- ❌ **No se relanzó el crawler desde cero.** Habría duplicado >18k fichas ya procesadas,
  castigado a Roomix sin necesidad y creado un segundo linaje de artefactos que se confundiría
  con el real — exactamente la clase de error de la regla 13. Además el contenedor es efímero:
  el resultado se perdería.
- ❌ **No se reconstruyó el crawler ni el matcher.** Reimplementarlos aquí produciría lógica
  distinta de la ya probada (538 tests), con riesgo de fusiones falsas destructivas.
- ❌ **No se tocó `main`, ni merge, ni Production, ni Vercel.**

---

## 5. Qué se necesita para reanudar

Cualquiera de estas dos vías desbloquea la misión:

**Vía A — continuar en local (recomendada).** La máquina Windows ya tiene crawler vivo, datos y
credenciales. Es el entorno natural de esta misión. Nada de lo aquí descrito la afecta.

**Vía B — habilitar el entorno remoto.** Requiere las tres cosas:
1. Pushear `feat/roomix-agency-coverage` a `origin` (código, no datos masivos).
2. Poner a disposición el padrón `roomix_agency_directory.jsonl` y los checkpoints del crawler.
3. Definir `SUPABASE_DATABASE_URL` en el entorno remoto (entra como `eretz_preview_ro`, que puede
   `SET LOCAL ROLE eretz_agency_coverage_writer`).

Nótese que la Vía B **no** resuelve el crawler: la tarea persistente de Windows seguiría siendo la
única instancia viva, y no debe duplicarse.

---

## 6. Reglas operativas permanentes de la misión

### Git
- Trabajar solo en la rama designada. **Nunca** `main`, merge, Production, force,
  `git reset --hard`, `git clean`, `git add .`, `git add -A`.
- Siempre `git add <rutas explícitas>`.

### Entidad canónica y fusión
- El padrón se indexa por **entidad canónica**, no por `agent_id`. Los `agent_id` originales
  quedan como provenance. Una inmobiliaria puede tener varios `agent_id` y seguir siendo 1 entidad.
- Fusión **conservadora**: exige nombre normalizado idéntico. **No** fusionar por fuzzy-close.
  Ante duda → mantener separados / `AMBIGUOUS`. Preferible duplicado pendiente de revisión que
  fusión falsa destructiva.
- Preservar la jerarquía **MARCA → OFICINA → AGENTE**. No colapsar RE/MAX, Century 21,
  Coldwell Banker, Keller Williams ni otras redes. Una oficina concreta cuenta; la marca genérica no.
- `AGENTE` y `DESARROLLADORA` se conservan con provenance pero **no** se insertan como inmobiliarias.
- `UNKNOWN` no se descarta: acumula evidencia y se **reprocesa al final del crawl**.

### Roomix — no existe atajo (ya investigado, no repetir)
Sin sitemap de publicadores · sin directorio de inmobiliarias (el visible es de ubicaciones) ·
sin perfil público de inmobiliaria · el anunciante no aparece en resultados. Solo la ficha
individual expone nombre, logo y `agent_id` inferible desde CDN. Roomix hoy **no** expone
teléfono, web ni email. Por eso: una ficha abierta = un anunciante potencial observado.

### Rate limit
Mantener el comportamiento respetuoso. No aumentar concurrencia agresivamente. Si el universo
requiere días, que requiera días. **Persistencia > velocidad.**

### Criterio de finalización del crawl
Solo se cierra con (A) 100% del universo enumerable procesado, o (B) residual técnicamente
inaccesible perfectamente cuantificado. No esconder residual. Luego: **delta final** —
re-enumerar Roomix, comparar contra el snapshot inicial, procesar nuevos IDs, repetir hasta que
no aparezcan nuevos o quede residual documentado.

### Crosswalk ERETZ
Contra `public.inmobiliarias_main` **y** `public.inmobiliarias_staging`. Estados:
`EXACT_MATCH` · `HIGH_CONFIDENCE_EXISTING` · `HIGH_CONFIDENCE_NEW` · `AMBIGUOUS` ·
`INSUFFICIENT_DATA` · `REJECTED_GARBAGE`.
Preservar las mejoras de matching ya implementadas (HTML entities, Unicode, acentos, apóstrofes,
puntuación, calificadores entre paréntesis, SA/SRL/SAS y sufijos societarios, aliases, teléfono,
email, dominio, matrícula, localidad, franquicia, many-to-one, one-to-many, colisiones).
**No declarar NEW si existe vecino significativo no resuelto.**

Colisiones ya auditadas: 31/31 `SAME_ENTITY_HIGH_CONFIDENCE`, pero con evidencia principal
`solo_nombre` → no promover fila staged si ya existe, no borrar, no fusionar destructivamente.
`accion_destructiva_habilitada = false`.

### Supabase / DB bridge
- Proyecto `inmolink`, ref `pggrvzyixyjkhfknpurg`, región `us-east-1`. **Data API OFF — debe seguir OFF.**
- Rol `eretz_agency_coverage_writer`: `LOGIN=false`, `SUPERUSER=false`, `CREATEDB=false`,
  `CREATEROLE=false`, `INHERIT=false`, `REPLICATION=false`, `BYPASSRLS=false`. Es un rol de
  privilegios, no una cuenta de login. El bloqueo de credenciales **ya fue resuelto**: no volver a
  investigar Supabase CLI, service role, postgres password ni Management API token.
- Entrada por `SUPABASE_DATABASE_URL` como `eretz_preview_ro`, que hace `SET ROLE` pero **no** hereda.
- Uso correcto: `BEGIN;` → `SET LOCAL ROLE eretz_agency_coverage_writer;` → operación → `COMMIT;`
  (preferir `SET LOCAL ROLE` por pooler).
- Privilegios: `public` USAGE sí / CREATE no · `inmobiliarias_main` SELECT sí / INSERT no ·
  `inmobiliarias_staging` SELECT+INSERT sí / UPDATE+DELETE no · USAGE solo sobre
  `public.inmobiliarias_staging_id_seq`. **No ampliar permisos.**
- **No usar** `ERETZ_WRITE_DATABASE_URL`. **No tocar** `eretz_app_writer`.

### Inserción
- Re-validar cada `HIGH_CONFIDENCE_NEW` contra main **y** staging justo antes de insertar (la base
  puede cambiar durante un crawl de días). No confiar en el crosswalk viejo.
- **Canary**: 12 candidatas representativas, solo `HIGH_CONFIDENCE_NEW`. Verificar cero duplicados,
  franquicias preservadas, campos, provenance, ninguna escritura en main. Reejecutar → 0 nuevas
  duplicadas (idempotencia).
- **Rollout** tras canary PASS: batches de ~200. Por batch: dedupe main → dedupe staging →
  `SET LOCAL ROLE` → insert → verify → duplicate check → reconciliation → commit solo si PASS.
  Continuar automáticamente, sin aprobación batch por batch.
- **No autoinsertar**: `EXACT_MATCH`, `HIGH_CONFIDENCE_EXISTING`, `AMBIGUOUS`, `INSUFFICIENT`,
  `AGENTE`, `DESARROLLADORA`, `MARCA_GENERICA`, `UNKNOWN`, `GARBAGE`.

### Webs oficiales (después del dedupe, nunca antes)
Se investiga la web de **todas** las inmobiliarias canónicas — las ya existentes en ERETZ, las
nuevas y las oficinas de franquicia. Si Roomix presenta la misma inmobiliaria con 4 `agent_id`,
se investiga la web **una sola vez**.

- Un portal **no** es web oficial: Roomix, Zonaprop, Argenprop, Mercado Libre, Properati,
  directorios, Instagram, Facebook, LinkedIn, Google Maps sirven como evidencia, no como dominio.
- **HTTP 200 no alcanza.** Debe haber evidencia de identidad: nombre, localidad, teléfono,
  matrícula, branding, dirección, perfil de franquicia u otras señales.
- Homónimos: si hay dos dominios igualmente plausibles → `OFFICIAL_WEB_AMBIGUOUS`. No elegir por
  intuición (apellidos comunes, nombres repetidos, distintas provincias).
- Estados: `OFFICIAL_WEB_VERIFIED` · `OFFICIAL_WEB_HIGH_CONFIDENCE` · `OFFICIAL_WEB_AMBIGUOUS` ·
  `OFFICIAL_WEB_NOT_FOUND` · `OFFICIAL_WEB_INACTIVE` · `NO_INDEPENDENT_WEBSITE`.
- Franquicias: **no** asignar `remax.com.ar` a cientos de oficinas. Distinguir `official_domain`
  de `official_office_page`. Una oficina puede tener dominio propio, perfil oficial dentro del
  dominio de la red, o ninguna web independiente. Guardar la mejor fuente oficial específica.
- Auditar también las webs que ERETZ ya tiene (dominio correcto, redirect, dominio muerto,
  pertenece a otra entidad, portal genérico, faltante). **No** hacer UPDATE en main con el bridge
  actual: preparar manifest de correcciones para una fase posterior.
- El proceso debe ser reanudable, checkpointed, incremental, rate-limited e idempotente, y no
  repetir entidades ya resueltas. Su duración no es un bloqueo.

---

## 7. Artefactos

| Artefacto | Ubicación | Estado |
|---|---|---|
| `roomix_agency_directory.jsonl` | `ERETZ_AGENCY_DATA\` (fuera del repo, local) | no accesible desde remoto |
| `agency_web_directory.jsonl` | `ERETZ_AGENCY_DATA\` (fuera del repo, local) | pendiente (fase webs) |
| `MASTER_PROGRESS.md` | repo, raíz | este archivo |

**`roomix_agency_directory.jsonl`** — una fila por entidad canónica. Campos según disponibilidad:
stable ID · raw agent_ids · nombre principal · nombre normalizado · variantes observadas · tipo ·
red · logo · listings_count · hasta N URLs de evidencia · zonas · matrícula · first_seen ·
last_seen · matcher_version · provenance · clasificación ERETZ · candidate ERETZ · confidence ·
reasons · web oficial · web status · evidencia web.

**`agency_web_directory.jsonl`** — una fila por entidad inmobiliaria canónica: canonical ID ·
nombre · tipo · franquicia · ubicación · ERETZ status · ERETZ id · Roomix agent_ids ·
current ERETZ web · discovered domain · official office page · status · confidence · evidence ·
checked_at · verifier_version.

Por listing, el crawler guarda únicamente: URL/provenance, `agent_id`, nombre del anunciante,
método de extracción y timestamp. No hay dataset de propiedades Roomix que desarmar, y no debe
agregarse información comercial de la propiedad. La zona puede inferirse de slugs/URLs cuando sea
razonablemente fiable, descartando tokens que describen el inmueble (departamento, casa,
ambientes, etc.).

---

## 8. Preguntas que la misión debe responder al cerrar

**Roomix:** ¿cuántas inmobiliarias/oficinas únicas hay en todo el universo accesible?
**ERETZ:** ¿cuántas ya estaban? **Gap:** ¿cuántas faltaban?
**Supabase:** ¿cuántas nuevas fueron stageadas?
**Duplicados:** ¿cuántas entidades Roomix se fusionaron como aliases? ¿cuántas coincidieron con
ERETZ? ¿cuántos duplicados nuevos introdujimos? → **respuesta esperada: 0**
**Webs:** ¿cuántas verified / high-confidence / ambiguous / not-found / inactive? ¿cuántas oficinas
solo tienen página oficial dentro de su franquicia?

Frases de cierre (solo al completar la Definition of Done completa):
`ROOMIX AGENCY UNIVERSE EXHAUSTED` · `ERETZ AGENCY DIRECTORY RECONCILED` ·
`NEW AGENCIES STAGED` · `OFFICIAL WEBSITE DISCOVERY COMPLETE` · `DB BRIDGE READY FOR REVOCATION`

---

## 9. Notas de seguridad

- **Production intacta.** Sin deployments, sin variables de Production, sin merge, sin push a `main`.
- **Incidente Vercel histórico:** una ejecución previa creó accidentalmente un proyecto Vercel
  llamado `frontend` al correr `vercel deploy` sin link. No era la Production de ERETZ; los
  deployments fueron eliminados. Antes de cualquier Preview, verificar `.vercel/project.json` y el
  linkage. No volver a crear proyectos accidentalmente.

---

## 10. Próximos pasos

1. Decidir vía de reanudación (§5): local (recomendada) o habilitar el entorno remoto.
2. Verificar que la tarea persistente de Windows del crawler sigue viva y avanzando
   (proceso, último checkpoint, cursor, cantidad procesada, errores, timestamp). Si está viva:
   **no reiniciar**. Si murió: reanudar **exactamente desde el checkpoint**, nunca desde cero.
3. Completar el crawl hasta el criterio de finalización (§6) + delta final.
4. Regenerar completamente `ROOMIX_AGENCY_DIRECTORY` con toda la evidencia, reprocesando aliases,
   types, unknown, brands, offices, agents y developers. Congelar snapshot final.
5. Crosswalk → canary → rollout → reconciliación.
6. Descubrimiento y verificación de webs oficiales de todas las inmobiliarias canónicas.
7. Detenerse. No iniciar el scraping directo de propiedades.
