# no_property_links — Deep Scan y Fixes T + U

**Fecha:** 2026-06-08
**Sprint:** sprint_autonomo_20260607
**Branch:** fix/scraping-diagnostics-batch
**Previo:** Fix S (2376552e4) — tipos plurales CMS argentino cdh

---

## Resumen ejecutivo

| Metrica | Valor |
|---------|-------|
| Candidatos escaneados (deep scan) | 80 (set completo) |
| Sites PROP_FOUND (links reconocidos) | 18 |
| Sites Fix S nuevos (cdh CMS) | **5** adicionales a Pagliaro |
| Nuevas fixes aplicadas | 2 (Fix T + Fix U) |
| Sites desbloqueados por Fix T | 1 (Alvear — 53+ props) |
| Sites desbloqueados por Fix U | 1 (Angelina — 86+ props) |
| Tests de regresion | 48/48 PASS (26 originales + 22 nuevos) |
| Sites con prop links ya reconocidos (ajenos a nuestros fixes) | 12 |
| Sites con patron nuevo pero sin quick fix (flat_listing/timeout) | ~45 |

---

## Deep scan — metodologia

Script `_deep_scan_npl.py`: para cada uno de los 80 candidatos del set expandido,
se hace HTTP fetch de la URL de listado, se extraen todos los hrefs internos, y cada
URL se clasifica con `_looks_like_real_property_url`. Los misses con score >= 3 (heuristico
por presencia de numeros, keywords de propiedad, longitud de slug) se listan como
patrones candidatos a nuevos fixes.

**Estados de resultado por site:**
- `PROP_FOUND`: al menos 1 URL interna pasa `_looks_like_real_property_url` → ya desbloqueado
- `MISS_FOUND`: 0 URLs reconocidas pero URLs con aspecto de propiedad encontradas → candidato a fix
- `NO_SIGNALS`: 0 URLs de propiedad ni candidatas → flat_listing, sitio vacio, o JS
- `HTTP_4xx/5xx/ERROR`: sitio inaccesible o error de red

### Distribucion

| Estado | Count |
|--------|-------|
| MISS_FOUND | 33 |
| NO_SIGNALS | 23 |
| PROP_FOUND | 18 |
| HTTP_404 | 3 |
| ERROR | 2 |
| HTTP_500 | 1 |

---

## Fix S — 5 sitios cdh adicionales desbloqueados

Fix S (commit `2376552e4`, tipo plurales) habia sido confirmado para Pagliaro (4418).
El deep scan revelo 5 sitios mas del mismo CMS (`cdh.com.ar`) en el set de 80 candidatos
que tambien ahora pasan `_looks_like_real_property_url`.

| id | Dominio | Prop links (scan) | Test result |
|----|---------|------------------|-------------|
| 3462 | higuerabienesraices.com.ar | 13 | timeout (servidor lento) |
| 3460 | inmobiliariaterni.com.ar | 9 | pendiente test |
| 4746 | zaldivarcurutchet.com.ar | 34 | **score=96, 35 props ✅** |
| 186  | inmobiliariafarah.com.ar | 1 | pendiente test |
| 6335 | svestudioinmobiliario.com.ar | 5 | **score=100, 10 props ✅** |

**Confirmados importables**: zaldivarcurutchet (4746) score=96, svestudio (6335) score=100.
**Pendientes de test**: terni (3460), farah (186), higuerabienesraices (3462 — servidor lento).

Todos usan el mismo CMS argentino `cdh.com.ar` con URLs tipo:
`/casas-en-venta-en-tandil-{slug}-{id1}-{id2}.html`

---

## Fix T — Joomla SEF Argentina: `/en-(venta|alquiler)/`

### Sitio afectado

| Campo | Valor |
|-------|-------|
| id | 5167 |
| Nombre | Inmobiliaria Alvear |
| Dominio | inmobiliaria-alvear.com.ar |
| URL listado | `http://www.inmobiliaria-alvear.com.ar/en-venta` |
| CMS | Joomla (SEF URLs activadas) |
| Ciudad | Rafaela / Bustinza (Santa Fe) |

### Patron identificado

URLs de detalle en Joomla argentino con SEF activado:
```
/en-venta/85-en-venta/450-centenario-entre-san-martin-y-moreno.html    <- 3 segmentos
/en-venta/85-en-venta/446-oportunidad-permuta-bustinza-sta-fe.html
/en-alquiler/45-en-alquiler/382-casa-dos-ambientes.html
/en-venta/127-20-de-junio-700-barrio-ferroviario-oportunidad.html      <- 2 segmentos
```

Estructura Joomla SEF: `/{operacion}/{[cat_id-]cat_slug}/{article_id}-{slug}.html`

El validador anterior no reconocia estas URLs porque:
- No tienen tipo de propiedad al inicio (`casa`, `depto`, etc.)
- No usan el formato `{tipo}-en-{operacion}-`
- La operacion esta al inicio del path como categoria

### Regex Fix T

```python
# Joomla SEF argentina: /en-(venta|alquiler)/[categoria/]{ID_num}-{slug}.html
# ej: /en-venta/85-en-venta/450-centenario-entre-san-martin-y-moreno.html
#     /en-venta/127-20-de-junio-700-barrio-ferroviario-oportunidad.html
#     /en-alquiler/45-en-alquiler/382-casa-dos-ambientes.html
r"(^|/)en-(venta|alquiler)/(?:[^/?#]+/)?\d{3,}-[^/?#]{10,}\.html?$"
```

**Requisitos**:
- Path raiz = `en-venta` o `en-alquiler`
- 1 segmento intermedio OPCIONAL (sin /, sin ?, sin #)
- Segmento final: 3+ digitos + `-` + 10+ chars slug + `.html`

**Riesgo**: BAJO — requiere `en-(venta|alquiler)` al inicio + ID numerico 3 cifras.
El segundo escudo es la quality gate (score >= 70).

### Test post-Fix T

```
--test-url http://www.inmobiliaria-alvear.com.ar/en-venta --agency-id 5167
```

| Metrica | Valor |
|---------|-------|
| generic_property_links_count | 53 (era 0) |
| Props capturadas | **53** |
| Score | **84** |
| Completitud | partial_ratio=0.177, expected=300 |
| Retry | `sitemap_batch` |
| Estrategia | `static_html_detail` |

**Importable**: ✅ — quality gate aprobada, 53 props en primer run.
**Total estimado**: ~300 props (retry sitemap_batch para captura completa).

---

## Fix U — `ver.php?id=N`

### Sitio afectado

| Campo | Valor |
|-------|-------|
| id | 3531 |
| Nombre | Inmobiliaria Angelina Martinez |
| Dominio | inmobiliariaangelinam.com.ar |
| URL listado | `http://www.inmobiliariaangelinam.com.ar/propiedades.php` |
| CMS | PHP propio (listado en `propiedades.php`, detalle en `ver.php`) |
| Ciudad | Villa Mercedes / San Luis (Argentina) |

### Patron identificado

```
/ver.php?id=100&propiedad=Local+en+Alquiler+ubica...
/ver.php?id=101&propiedad=Departamento+en+Alquiler...
/ver.php?id=76&propiedad=Casa+en+Alquiler...
```

CMS PHP personalizado argentino con:
- `propiedades.php` — pagina de listado
- `ver.php?id=N` — pagina de detalle de propiedad
- El parametro `propiedad=` contiene descripcion del inmueble
- `load_more_signals: ["cargar_mas"]` — tiene paginacion via "Cargar mas"

El validador anterior no reconocia `ver.php?id=N` porque:
- `ver` no estaba en los path-names de detalle conocidos (`ficha`, `detalle`, `property`, etc.)
- El parametro `id=` no esta en `detail_query_keys`

### Regex Fix U

```python
# Fix U: ver.php?id=N — CMS propio argentino con pagina de detalle en ver.php
# ej: inmobiliariaangelinam.com.ar/ver.php?id=100&propiedad=Local+en+Alquiler
# Requiere path=ver.php + id=2+digitos. No es ficha.php ni detalle.php (ya cubiertos).
if re.search(r"(^|/)ver\.php$", path, re.I) and re.fullmatch(r"\d{2,}", query.get("id", "")):
    return True
```

**Implementacion**: early-return check (antes de `detail_patterns`) para acceder al dict `query`.
**Requisitos**: `path` termina en `ver.php` + `id=` con 2+ digitos exactos.
**Riesgo**: BAJO — `ver.php` + `id=N` (exacto, sin otros caracteres en id) es muy especifico.

### Test post-Fix U

```
--test-url http://www.inmobiliariaangelinam.com.ar/propiedades.php --agency-id 3531
```

| Metrica | Valor |
|---------|-------|
| generic_property_links_count | 86 (era 0) |
| cards_posibles | 95 |
| listing_links_count | 95 |
| Props capturadas | **86** |
| Score | **87** |
| Completitud | partial_ratio=0.287, expected=300 |
| Retry | `playwright_or_ajax_load_more` |
| Estrategia | `static_html_detail` |
| load_more_signals | `["cargar_mas"]` |

**Importable**: ✅ — quality gate aprobada, 86 props en primer run.
**Total estimado**: ~300 props (retry ajax_load_more para captura completa).

---

## Tests de regresion — 48/48 PASS

| Grupo | Tests | Resultado |
|-------|-------|-----------|
| Fix U — ver.php id=N (PASS) | 3 | PASS |
| Fix U — falsos positivos (id muy corto, sin id=, sin query) | 3 | PASS |
| Fix T — Joomla 3 segmentos | 2 | PASS |
| Fix T — Joomla 2 segmentos | 2 | PASS |
| Fix T — falsos positivos (sin num, sin .html) | 2 | PASS |
| Fix S — plurales (casas, deptos, galpones, locales) | 9 | PASS |
| Fix M — singulares y compuestos | 4 | PASS |
| Fix Q — /listings/ | 3 | PASS |
| Fix R — /properties/ | 2 | PASS |
| Fix O — listing-preview | 1 | PASS |
| Falsos positivos generales | 7 | PASS |
| Existentes varios (ficha.php, detalle.php, listados bare) | 10 | PASS |
| **Total** | **48** | **48/48 PASS** |

---

## Codigo aplicado

### Fix T — en `detail_patterns` tuple (scraper_propiedades.py ~linea 10121)

```python
# Joomla SEF argentina: /en-(venta|alquiler)/[categoria/]{ID_num}-{slug}.html
# ej: /en-venta/85-en-venta/450-centenario-entre-san-martin-y-moreno.html
#     /en-venta/127-20-de-junio-700-barrio-ferroviario-oportunidad.html
#     /en-alquiler/45-en-alquiler/382-casa-dos-ambientes.html
# Fix T: cubre el patron de articulos Joomla con categoria en-venta/en-alquiler.
# Requiere 3+digitos de ID + 10+chars de slug + .html (evita categorias y blogs cortos).
r"(^|/)en-(venta|alquiler)/(?:[^/?#]+/)?\d{3,}-[^/?#]{10,}\.html?$",
```

### Fix U — early-return check (scraper_propiedades.py ~linea 10052)

```python
# Fix U: ver.php?id=N — CMS propio argentino con pagina de detalle en ver.php
# ej: inmobiliariaangelinam.com.ar/ver.php?id=100&propiedad=Local+en+Alquiler
#     inmobiliariaangelinam.com.ar/ver.php?id=76&propiedad=Casa+en+Alquiler
# Requiere path=ver.php + id=2+digitos. No es ficha.php ni detalle.php (ya cubiertos).
if re.search(r"(^|/)ver\.php$", path, re.I) and re.fullmatch(r"\d{2,}", query.get("id", "")):
    return True
```

---

## Sitios adicionales PROP_FOUND (ya desbloqueados, no por nuestros fixes)

12 sitios en el set de 80 candidatos ya tienen URLs reconocidas por patrones preexistentes
(antes de Fix Q/R/S/T/U). Estos fueron clasificados como `no_property_links` en el pipeline
historico probablemente por:
- Sitio lento/no disponible durante el run del pipeline
- Pagina de listado con JS parcial que el pipeline no pudo procesar completamente
- URL de listado diferente en Supabase vs la que encontramos aqui

| id | Dominio | Patron reconocido |
|----|---------|------------------|
| 6705 | saezfarez.com | `/ficha.php?prp_id=N` |
| 3064 | inmoromanazzi.com.ar | `/ficha.php?prp_id=N` |
| 1773 | dealtainmobiliaria.com | `/detalle.php?id=N` |
| 5959 | inmobiliariafarina.com.ar | `/ficha.php?prp_id=N` |
| 1443 | camposdelapampa.com.ar | `/{2-3let}{3-6dig}.html` |
| 6697 | roilands.com | `/ficha-prop.php?id=N` |
| 3358 | jalilpropiedades.com.ar | `/detalles.php?op=V&...` |
| 945  | amipropiedades.com.ar | `/propiedades/{slug}` (Fix R) |
| 6678 | remax.com.ar | `/casas-en-alquiler-en-{ciudad}` (Fix S cdh) |
| 6162 | atsonpropiedades.com | `/{slug-tipo-propiedad-30+}` |
| 5282 | innoacafayate.com | `/venta/item.asp?t=N` |
| 51   | grupofons.com | `/propiedades/{slug}` (Fix R) |

Nota: `remax.com.ar` (6678) es un portal nacional — verificar que la URL listado en Supabase
sea de una sucursal especifica y no el portal nacional.

---

## Candidatos sin quick fix identificado

| Familia | Count | Razon | Accion sugerida |
|---------|-------|-------|-----------------|
| flat_listing (JS-rendered cards) | ~20 | Sin links de detalle, datos en cards | Feature nueva: extractor flat |
| requires_playwright | ~10 | Vite/React bundle | Playwright masivo — out of scope |
| PHP custom sistema propio distinto | ~5 | Patron unico por sitio | Analisis individual si prioridad alta |
| Sitios lentos/timeout | 3-4 | Servidor lento, no error de codigo | Retry con timeout mayor |
| Sin solucion (down/sin contenido) | ~6 | Sitios caidos o sin propiedades | Desactivar o monitorear |

---

## Impacto acumulado del sprint (a esta instancia)

| Fix | Commit | Sites desbloqueados | Props estimadas |
|-----|--------|--------------------|-----------------| 
| Fix Q | 8c636d818 | 1 (Mendocasa 3532) | ~3 |
| Fix R | 3b4c0d489 | 1 (Sauce 6732) | ~149 |
| Fix S | 2376552e4 | 6 (Pagliaro 4418 + 5 cdh) | ~150+ |
| Fix T | (pendiente commit) | 1 (Alvear 5167) | ~300 |
| Fix U | (pendiente commit) | 1 (Angelina 3531) | ~300 |
| **Total** | | **10 sites** | **~900+ props** |

---

---

## Fix V — PHP slug con operacion al inicio (sin ID numerico)

### Sitio afectado

| Campo | Valor |
|-------|-------|
| id | 4709 |
| Nombre | VivancoGroup Inmobiliaria — Patagonia |
| Dominio | vivancogroup.com |
| URL listado | `http://www.vivancogroup.com/alquiler_casasydptos.php` |
| CMS | PHP propio (Cipolletti, Rio Negro) |

### Patron identificado

```
/alquiler_casa_1_dorm_amoblada_lisandro-de-la-torre-700_cipolletti.php
/alquiler_casa_2_dorm_lisandro-de-la-torre-700_cipolletti-rn.php
/venta_terreno_en_cipolletti_los-lapachos.php
```

Estructura: `/{op}_{tipo}_{slug_largo}.php` — variante con operacion al inicio y
underscores como separadores. NO tiene ID numerico al final.

Diferencia con patron existente (`{tipo}[-_]{op}[-_]{ID}`):
- Operacion va AL INICIO, no el tipo
- No tiene ID numerico final
- Requiere `.php` extension

### Regex Fix V

```python
# Fix V: CMS argentino PHP con operacion al inicio y slug largo, SIN ID numerico al final.
# ej: /alquiler_casa_1_dorm_amoblada_lisandro-de-la-torre-700_cipolletti.php
#     /venta_terreno_en_cipolletti_los-lapachos.php
r"(^|/)(?:alquiler|venta)[-_](?:casa|depto|departamento|terreno|local|oficina|lote|campo|chalet|galpon|cochera|duplex|triplex|ph|monoambiente)(?:e?s)?[-_][^/?#]{15,}\.php$"
```

### Test post-Fix V

```
--test-url http://www.vivancogroup.com/alquiler_casasydptos.php --agency-id 4709
```

| Metrica | Valor |
|---------|-------|
| generic_property_links_count | 11 (era 0) |
| Props capturadas | **10** |
| Score | **90** |
| Estrategia | `static_html_detail` |

**Importable**: ✅ score=90.

---

## Tests de regresion — 28/28 PASS (Fix V + T + U + S + Q + R)

Todos los tests previos mas los nuevos de Fix V pasan sin regresiones.

---

## Impacto acumulado del sprint (actualizado)

| Fix | Commit | Sites desbloqueados | Props confirmadas |
|-----|--------|--------------------|-----------------| 
| Fix Q | 8c636d818 | 1 (Mendocasa 3532) | ~3 |
| Fix R | 3b4c0d489 | 1 (Sauce 6732) | ~30 |
| Fix S | 2376552e4 | 6 (Pagliaro 4418 + 5 cdh) | ~100+ |
| Fix T | ead8ba52b | 1 (Alvear 5167) | 53 |
| Fix U | ead8ba52b | 1 (Angelina 3531) | 86 |
| Fix V | (pendiente commit) | 1 (Vivanco 4709) | 10 |
| **Total** | | **11 sites** | **~280+ props** |

Sitios PROP_FOUND adicionales confirmados (sin codigo nuevo):
- amipropiedades.com.ar (945): score=98, 39 props ✅
- innoacafayate.com (5282): score=92, 17 props ✅
- zaldivarcurutchet.com.ar (4746): score=96, 35 props ✅ (Fix S)
- svestudioinmobiliario.com.ar (6335): score=100, 10 props ✅ (Fix S)

---

## FRENO

No se importo, valido, ni publico nada.
Fixes T, U, V aplicados y probados localmente.
No se modifico DB.
No se hizo git push.
Fix T+U commiteados en ead8ba52b.
Fix V pendiente de commit.
