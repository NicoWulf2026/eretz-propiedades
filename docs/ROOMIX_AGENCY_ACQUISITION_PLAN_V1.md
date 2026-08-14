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
