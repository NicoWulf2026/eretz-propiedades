# Roomix Agency Coverage V1 — Plan de adquisición

Objetivo: identificar los publicadores inmobiliarios presentes en el Roomix
público, cruzarlos contra ERETZ e incorporar con seguridad los que falten.

Roomix se usa como **señal de descubrimiento de hechos públicos**, no como base
a clonar: nombre del publicador y su relación pública con avisos. No se copian
descripciones, fotos, logos, scores ni métricas propietarias.

---

## 1. Reconocimiento (hecho antes de escribir la campaña)

### robots.txt
Declara `Sitemap: https://roomix.ai/sitemap_index.xml` y define reglas por
user-agent. Para `anthropic-ai` —el agente que corresponde a esta sesión—
declara explícitamente:

```
Allow: /
Allow: /buscar/
Allow: /llms.txt
Disallow: /dashboard/
Disallow: /profile/
Disallow: /api/
```

De ahí se derivan dos límites que la campaña respeta sin excepción:
**no se toca `/api/`** (aunque devolviera datos más cómodos) y no se tocan
`/dashboard/` ni `/profile/`.

### Superficies enumerables medidas

| Sitemap | URLs |
|---|---|
| `properties/sitemap/0..5` | **168.563** |
| `sitemap-buscar` | 3.004 |
| `sitemap-static` (incluye `/directorio` 1.299 y `/roomix-index` 1.409) | 2.742 |
| `sitemap-blog` | 1.904 |
| `sitemap-edificios` | 783 |
| `sitemap-barrios` | 320 |
| `sitemap-landings` | 247 |
| `sitemap-venta` | 28 |

### Dónde vive el publicador
Se descartaron por medición, no por suposición:

- **No existe directorio público de inmobiliarias.** `/inmobiliarias` responde
  200 pero es una landing comercial (`h1: "Más visibilidad para tus
  publicaciones, gratis"`). No hay `/inmobiliaria/*`, `/agencias`,
  `/publicadores` ni sitemap de agencias — todos 404.
- **`/directorio/<prov>/<loc>`** (1.293 páginas) es un directorio **geográfico
  de propiedades**, no de publicadores: sus encabezados son "Propiedades en X",
  "Barrios y zonas dentro de X". No lista agencias.
- **El JSON-LD de la ficha no expone el publicador**: sus claves son
  `@context, @type, datePosted, description, image, mainEntity, name, offers,
  url`. Sin `provider`, `seller`, `broker` ni `agent`.
- **Las tarjetas de resultados no muestran publicador** (dirección y precio).

El publicador viaja **únicamente** en el payload RSC de la ficha, bajo el
encabezado "Publicado por", con esta forma:

```
{"agent":{"_id":"<uuid>","name":"<nombre>","image":"https://cdn.roomix.ai/agents/<uuid>.jpg", ...}}
```

`agent._id` es un UUID estable: sirve como clave de deduplicación exacta y evita
depender del string del nombre.

**Conclusión del reconocimiento: la única vía pública hacia los publicadores es
la ficha de propiedad.** No hay atajo enumerable más barato.

---

## 2. Estrategia primaria

```
sitemap index → 6 shards de propiedades → 168.563 URLs → ficha → agent{_id,name}
```

### El problema de escala, dicho explícitamente
Las fichas pesan ~570 KB. Recorrer las 168.563 son **~96 GB** de transferencia
del sitio ajeno y, a un ritmo cortés de 3 req/s, **~15,6 horas** de tráfico
sostenido. Eso no es proporcionado para un objetivo que es *descubrir entidades*,
y contradice la propia regla de cortesía de esta misión.

### Criterio de completitud elegido: convergencia de publicadores
El brief admite explícitamente como criterios válidos *"segunda pasada no agrega
publishers nuevos"* y *"publisher convergence alcanzada"*. Es el criterio
correcto acá porque la distribución de publicadores sobre avisos es de cola
pesada: unos pocos publican miles de avisos y la mayoría publica pocos, de modo
que la curva de publicadores únicos satura mucho antes que la de propiedades.

La campaña recorre una **muestra aleatoria estratificada por shard** y mide,
después de cada lote:

1. **Tasa marginal** — publicadores nuevos por cada 1.000 fichas.
2. **Chao1** — estimador de riqueza no observada:
   `S_chao1 = S_obs + f1² / (2·f2)`, donde `f1` son los publicadores vistos una
   sola vez y `f2` los vistos exactamente dos. Da una **cota inferior del
   universo total**, no una opinión.
3. **Cobertura de Good–Turing** — `C = 1 − f1/n`: qué proporción de los avisos
   del universo pertenece a publicadores ya observados.

**Se declara enumerado** cuando simultáneamente:
- la tasa marginal cae por debajo de **2 publicadores nuevos por 1.000 fichas**;
- `S_obs / S_chao1 ≥ 0,90`;
- la cobertura Good–Turing `≥ 0,97`;
- se mantiene durante **tres lotes consecutivos**.

Eso permite afirmar con número —no con impresión— qué fracción del universo se
observó y cuánto queda fuera.

### Enumerador B (reconciliación independiente)
Además de la muestra sobre el sitemap, se recorre `sitemap-buscar` (3.004
páginas de resultados) para extraer URLs de propiedad por otra vía. Sirve para
detectar si el sitemap de propiedades omite regiones enteras: si B produce URLs
que A no contiene, la enumeración A está incompleta y hay que ampliarla.

### Fallbacks (definidos antes de ejecutar, no improvisados)
1. Si un shard responde 5xx: reintento acotado con backoff.
2. Si las fichas empiezan a devolver 403: **se detiene**, no se evade. Se
   reporta cobertura efectiva alcanzada.
3. Si el payload cambia de forma: el parser cae a la extracción por
   `"Publicado por"` + bloque `agent`, y se registra como `parse_fallback`.

---

## 3. Cortesía operativa

- Concurrencia **4**, ritmo objetivo **3 req/s**, jitter.
- Backoff exponencial ante 429/5xx; **ante 403 se aborta**, no se rota nada.
- Timeout 45 s, 2 reintentos sólo para errores transitorios.
- HTTP plano: la ficha es server-rendered, no hace falta navegador.
- User-agent identificable y real, sin rotación.
- Checkpoint cada lote: la campaña se reanuda sin repetir trabajo.

## 4. Clasificación de publicador

`INMOBILIARIA` · `AGENTE` · `RED_FRANQUICIA` · `DESARROLLADORA` ·
`DUENO_DIRECTO` · `OTRO` · `UNKNOWN`

No todo "Publicado por" es inmobiliaria. Se rechazan explícitamente como basura:
`Particular`, `Dueño directo`, `Usuario`, nombres de portal, nombres de CRM,
placeholders, HTML, nulls y textos desmedidos.

## 5. Cruce con ERETZ

Señales por prioridad: dominio · teléfono · email · matrícula+jurisdicción ·
identificadores de fuente (**muy fuertes**); nombre normalizado + ciudad ·
nombre + fuente original (**fuertes**); sólo nombre (**débil**).

Estados: `EXACT_EXISTING` · `HIGH_CONFIDENCE_EXISTING` · `PROBABLE_EXISTING` ·
`NEW_HIGH_CONFIDENCE` · `AMBIGUOUS` · `INSUFFICIENT_DATA`.

**Nunca se auto-fusiona por señal débil.** Los ambiguos quedan preservados como
candidatos, no se incorporan.

## 6. Escritura

Sólo `NEW_HIGH_CONFIDENCE`. Con provenance (`discovered_via`, fecha, evidencia,
confianza, versión de matching). No se modifican entidades existentes. No se
activa Data API. No se amplían grants.

**Restricción conocida al momento de escribir este plan:** ninguna de las dos
credenciales de base almacenadas (`INTERNAL_DB_URL`, `SUPABASE_DATABASE_URL`)
autentica, y la Data API está OFF. La incorporación queda preparada y verificada
pero no ejecutada hasta disponer de credencial válida.

---

## 7. Convergencia observada — corrección del criterio

El umbral definido antes de ejecutar (marginal < 2 publicadores nuevos por
1.000 fichas) **resultó irreal para esta distribución**, y corresponde decirlo
en vez de forzar el dato.

### Lo que muestra la curva (8.120 fichas, ventanas de 1.000)

| Ventana | pub. nuevos/1k | inmob. nuevas/1k | cobertura G-T |
|---|---|---|---|
| 1 | 690 | 363 | 0,468 |
| 2 | 490 | 321 | 0,565 |
| 4 | 351 | 227 | 0,671 |
| 6 | 300 | 196 | 0,724 |
| 8 | 251 | 161 | 0,761 |

La tasa marginal decae como una ley de potencia suave, no exponencialmente.
Roomix agrega desde muchos portales, así que la cola de publicadores con uno o
dos avisos es larguísima. **El conteo absoluto de inmobiliarias no converge sin
recorrer prácticamente todo el universo**, y recorrerlo son ~96 GB del ancho de
banda ajeno.

### Lo que sí converge: la cobertura

La pregunta competitiva no es "cuántas inmobiliarias hay en total" sino "qué
proporción de las que Roomix publica ya tiene ERETZ". Esa proporción **es
estable**:

| Fichas | Inmobiliarias | Ya en ERETZ | Cobertura |
|---|---|---|---|
| 1.000 | 293 | 72 | 24,6% |
| 2.000 | 553 | 138 | 25,0% |
| 4.000 | 933 | 234 | 25,1% |
| 6.000 | 1.261 | 309 | 24,5% |
| 8.120 | 1.555 | 378 | **24,3%** |

**Banda de 0,8 puntos a lo largo de ocho ventanas, con ocho veces más datos.**
El top-10 de gaps se mantiene en 8–10 de 10 entre ventanas consecutivas.

### Criterio final adoptado
Se declara **convergente la medición de cobertura** —no el censo— cuando la
proporción se mantiene dentro de ±1 punto durante cinco ventanas consecutivas
de 1.000 fichas y el top-10 de gaps conserva ≥8 elementos entre ventanas.
Ambas condiciones se cumplen desde la ventana 4.

Queda explícitamente separado:
- **cobertura observada: 24,3%** (medida, convergida);
- **censo total de inmobiliarias de Roomix: no determinado** (cola larga; exigiría
  enumeración completa).

### Corrección con la campaña completa (14.120 fichas)

Al duplicar los datos, la cobertura **no se mantuvo dentro de ±1 punto**:

| Fichas | Inmobiliarias | Ya en ERETZ | Cobertura |
|---|---|---|---|
| 4.000 | 933 | 234 | 25,1% |
| 8.000 | 1.541 | 376 | 24,4% |
| 10.000 | 1.746 | 425 | 24,3% |
| 12.000 | 1.961 | 467 | 23,8% |
| 14.120 | 2.142 | 498 | **23,2%** |

Hay una **deriva descendente de 1,9 puntos**, no una meseta. La lectura correcta
es que ERETZ cubre bien las inmobiliarias grandes —que aparecen temprano en
cualquier muestra— y la cola larga está desproporcionadamente descubierta. Por lo
tanto:

- **cobertura observada a 14.120 fichas: 23,2%**;
- **la cobertura real sobre el universo completo es probablemente algo MENOR**,
  porque cada tramo adicional aporta más cola no cubierta;
- el criterio de "±1 punto en cinco ventanas" que se adoptó a 8.120 fichas **no
  se sostuvo** y queda anulado.

Lo que sí es sólido: el orden de magnitud (≈¼ de cobertura), la concentración del
gap en oficinas de franquicia, y el ranking de gaps principales, que se mantuvo
estable en todos los cortes.

Chao1 sobre 14.120 fichas estima **7.552 publicadores** como cota inferior del
universo, contra 4.194 observados: queda al menos un 44% del padrón sin ver.

---

## Corrección conceptual: "nuevo para ERETZ" no es "ausente de main"

El rollout de incorporación dejó al descubierto un error de encuadre del cruce.
El crosswalk se construyó comparando los publicadores de Roomix **contra
`inmobiliarias_main` solamente**, y todo lo que no aparecía ahí se etiquetó
`NEW_HIGH_CONFIDENCE`. Pero el padrón de ERETZ no vive sólo en main: en el
momento del rollout `inmobiliarias_staging` tenía 11.538 filas de otros imports
—9.040 de Zonaprop y 2.498 del colegio de Córdoba— que el cruce nunca miró.

El resultado se vio al escribir: de 1.635 candidatas presentadas como nuevas,
**1.290 (79%) ya estaban en staging** y sólo 260 eran realmente nuevas. El
dedupe server-side las frenó a todas, así que no se duplicó nada; pero la
métrica de cobertura que produjo la campaña estaba inflada por construcción.

### Los tres estados hay que distinguirlos

Un cruce competitivo tiene que clasificar cada publicador externo en uno de
tres, y no en dos:

- **A — presente en MAIN.** Está en el producto vivo. Cuenta como cobertura
  real frente al usuario.
- **B — presente en STAGING.** Ya lo conocemos y está en la cola de
  incorporación, sin promover. No es un descubrimiento; volver a "descubrirlo"
  no agrega nada.
- **C — realmente nuevo.** No está en ninguna de las dos. Sólo esto es
  hallazgo.

Etiquetar B como C es lo que pasó acá, y sobrestima tanto el gap del competidor
como el aporte de la campaña.

### Dos coberturas, no una

Por eso conviene reportar dos números separados y nunca sumarlos ni
confundirlos:

- **`LIVE_COVERAGE`** — contra `inmobiliarias_main`. Es lo que un usuario ve
  hoy. Es la métrica honesta para comparar contra un competidor.
- **`KNOWN_PIPELINE_COVERAGE`** — contra `main ∪ staging`. Es lo que la
  organización ya conoce, promovido o no. Es la métrica que sirve para decidir
  si vale la pena una campaña de adquisición nueva.

La cobertura observada del 23,2% que documenta este plan es `LIVE_COVERAGE`, y
como tal sigue siendo válida. Lo que no es válido es leer las 1.635 candidatas
como incorporaciones potenciales: contra `main ∪ staging` eran 260.

### Un segundo hueco: la clave de dedupe

El dedupe contra main compara `nombre_normalizado`. De las 7.004 filas de main,
**1.984 lo tienen en NULL**, así que quedan invisibles para esa comparación por
más que su `nombre` diga exactamente lo mismo. Eso dejó 31 filas staged que
casi con certeza ya existen en main (ver
`collision_manifest_staging_main.jsonl`, fuera del repo).

Antes del próximo cruce conviene poblar `nombre_normalizado` en main, o
comparar contra `coalesce(nombre_normalizado, normalizar(nombre))` en vez de
sólo contra la columna.
