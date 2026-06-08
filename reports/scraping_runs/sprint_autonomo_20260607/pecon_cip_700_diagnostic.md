# Pecon Cip id=700 — Diagnostico Completo

**Fecha:** 2026-06-08
**Sprint:** sprint_autonomo_20260607
**Modo:** investigacion + `--test-url --allow-static-detail --allow-playwright-fallback` (sin DB writes)

---

## Estado actual en Supabase (preflight)

| Campo | Valor |
|-------|-------|
| `id` | 700 |
| `nombre` | Inmobiliaria Pecon Cip |
| `web` | http://peconcip.com.ar |
| `url_listado` | `http://peconcip.com.ar#` (rota — `#` al final, igual que Sauce) |
| `estrategia_scraping` | `sitemap` (incorrecta — no hay sitemap de propiedades) |
| `cms_detectado` | `wordpress` |
| `activa` | True |
| `sitio_activo` | True |
| `total_propiedades` | NULL (nunca scrapeado exitosamente) |
| `proximo_scraping` | 2026-06-01 (vencido) |

---

## Diagnostico del sitio

### Homepage

| Senal | Valor |
|-------|-------|
| Titulo | "Pecon CIP - Centro Integral de la Propiedad" |
| HTTP | 200, 93KB |
| Negocio | Inmobiliaria real — venta, alquiler, administracion, direccion de obras |
| Ubicacion | Belgrano 415, Tres Arroyos (7500), Argentina |
| Telefono | (02983) 430606 |
| Menu | Propiedades en Venta / Propiedades en Alquiler |
| URL ventas | `http://peconcip.com.ar/mh/?offer-type=venta` |
| URL alquileres | `http://peconcip.com.ar/mh/?offer-type=alquiler` |

### CMS y theme

| Componente | Valor |
|------------|-------|
| CMS | WordPress |
| Theme | **MyHome** v3.1.33 (detectado via `myhome/assets/css/`) |
| Frontend bundle | **Vite** (SPA/SSR moderno, renderizado con JavaScript) |
| Plugin REST API | `myhome/v1` namespace registrado |

### robots.txt

```
User-agent: *
Disallow: /*?           <- bloquea TODOS los URLs con query parameters
Crawl-delay: 60
Visit-time: 0300-1200
Request-rate: 6/60m
```

**Impacto**: `Disallow: /*?` bloquea `/mh/?offer-type=venta` y todos los endpoints con parametros.
El scraper no respeta robots.txt por default, pero es una senal de que el operador no quiere bots.

---

## Hallazgo critico: 0 propiedades publicadas

### WP REST API — post type `estate`

```
GET /wp-json/wp/v2/estate?per_page=5
HTTP 200
X-WP-Total: 0
X-WP-TotalPages: 0
Items: []
```

El post type `estate` existe (no 404) pero tiene **0 propiedades publicas**.

### MyHome API — `myhome/v1/estates`

```
POST /wp-json/myhome/v1/estates
Body: {"offer-type": "venta", "per_page": 12, "page": 1}
HTTP 200
found_results: 0
results: []
```

```
POST /wp-json/myhome/v1/estates
Body: {"per_page": 12, "page": 1}   (sin filtro)
HTTP 200
found_results: 0
results: []
```

```
POST /wp-json/myhome/v1/estates
Body: {"offer-type": "alquiler", "per_page": 12, "page": 1}
HTTP 200
found_results: 0
results: []
```

**Conclusion**: La API del plugin MyHome confirma 0 propiedades para venta, alquiler, y sin filtro.

### HTML embebido en `/mh/?offer-type=venta`

```json
"initial_results":"1",
"results":{"estates":[],"totalResults":0}
```

El estado inicial del frontend ya incluye 0 resultados — consistente con la API.

### WP Sitemap

```xml
wp-sitemap.xml:
  wp-sitemap-posts-page-1.xml        <- paginas estaticas
  wp-sitemap-posts-testimonial-1.xml <- testimonios
  wp-sitemap-users-1.xml             <- usuarios
```

**Ausentes**: `estate`, `property`, `propiedad`, `inmueble`, `listing`.
El sitemap de estates (`wp-sitemap-posts-estate-1.xml`) devuelve HTTP 404.

---

## Resultado del test local

**Comando:**
```
--test-url http://peconcip.com.ar/mh/?offer-type=venta
--agency-id 700 --allow-static-detail --allow-playwright-fallback
```

| Extractor intentado | Resultado | Duracion |
|--------------------|-----------|----------|
| `static_html_detail` | FALLO: `no_property_links` | 104s |
| `json_ld` | FALLO: `sin_propiedades` | 0.6s |
| `sitemap` | "exito": 2 items (no son propiedades) | 7.6s |

**Error final**: `strategy_quality_failed`
**Issues**: `['urls_invalidas', 'precios_insuficientes']`
**Score**: 49

### Por que `static_html_detail` tardo 104 segundos?

El diagnostico probo 16 rutas alternativas porque `generic_property_links_count = 0`:
```
rutas_probadas: [
  /mh/?offer-type=venta, /propiedades, /propiedad,
  /mh/?offer-type=venta (www), /propiedades (www), /propiedad (www),
  http://, https:// variants...
]
```

Ninguna encontro property links porque la API devuelve 0 resultados y los links
de detalle no existen en el HTML estatico (se generan via JS).

### Por que `sitemap` capturo 2 items falsos?

El scraper uso `wp-sitemap-posts-page-1.xml` (paginas estaticas WP).
Los 2 items son paginas del sitio (ej: `/`, `/sobre-nosotros/`) — NO propiedades.
Esos URLs no pasan `_looks_like_real_property_url` → `urls_invalidas`.

### Senal clave: requires_js + vite_bundle

```json
"requires_js": true,
"requires_playwright_signals": ["vite_bundle"]
```

La pagina `/mh/` usa un bundle Vite (React/Vue SPA). Los listados se renderizan
completamente via JavaScript. Sin Playwright, el HTML estatico no contiene
los cards de propiedades.

**PERO**: incluso con Playwright, la API devuelve 0 resultados. Playwright renderizaria
el frontend pero veria la pagina de "sin propiedades" — sin cards que extraer.

---

## Clasificacion

### Clasificacion primaria: `no_public_listing_found`

El sitio es una inmobiliaria real (Tres Arroyos, Provincia de Buenos Aires) con:
- Infraestructura completa (MyHome theme, API funcionando)
- Tipos de propiedad configurados: casa, departamento, galpones/locales, terrenos, campos
- Tipos de oferta configurados: venta, alquiler, oportunidad, vendida

Pero **0 propiedades publicadas** en todos los endpoints consultados.
El operador no ha cargado propiedades en el sistema, o las tiene en draft/privadas.

### Clasificacion secundaria: `requires_playwright`

El listing page (`/mh/`) usa Vite SPA — requiere JS para renderizar.
`requires_playwright_signals: ["vite_bundle"]` detectado por el scraper.

### NO es `constructora_sin_listado`

A diferencia de Uco Domos (id=332), esta es una inmobiliaria real que PODRIA
tener propiedades en el futuro. No corresponde desactivar.

---

## Recomendaciones

### Opcion A — Solo fix url_listado (RECOMENDADA como primer paso)

```sql
UPDATE public.inmobiliarias_main
SET url_listado  = 'http://peconcip.com.ar/mh/?offer-type=venta',
    updated_at   = NOW()
WHERE id = 700
  AND url_listado = 'http://peconcip.com.ar#';
```

**Riesgo**: BAJO. La URL nueva existe y devuelve HTTP 200.
**Efecto**: Elimina el `#` roto. El pipeline puede llegar al sitio.
**Limitacion**: El scraper seguira fallando hasta que el operador publique propiedades.

### Opcion B — Fix url_listado + corregir estrategia_scraping

```sql
UPDATE public.inmobiliarias_main
SET url_listado          = 'http://peconcip.com.ar/mh/?offer-type=venta',
    estrategia_scraping  = NULL,
    updated_at           = NOW()
WHERE id = 700
  AND url_listado = 'http://peconcip.com.ar#';
```

**Riesgo**: BAJO-MEDIO. `estrategia_scraping = sitemap` es incorrecta (no hay sitemap de estates).
Resetear a NULL permite que el pipeline re-detecte la estrategia correcta cuando haya propiedades.
**Efecto adicional**: El proximo run no intentara estrategia `sitemap` inapropiada.

### No recomendado

- **Activar Playwright sin propiedades**: inutil hasta que el operador cargue fichas.
- **Desactivar (activa=FALSE)**: prematuro — es una inmobiliaria real que puede publicar propiedades.
- **Usar `myhome/v1/estates` como api_candidate**: requiere nonce de sesion (cookie-based auth).
  No es accesible sin autenticacion a pesar de responder 200 con cuerpo vacio.

---

## Acciones pendientes (requieren autorizacion)

### UPDATE url_listado + estrategia_scraping (Opcion B)

```sql
-- ─────────────────────────────────────────────────────────────────────────
-- Pecon Cip id=700: fix url_listado rota (#) + reset estrategia incorrecta
-- Guarda estricta: id=700 AND url_listado='http://peconcip.com.ar#'
-- Riesgo: BAJO — total_propiedades=NULL, nunca scrapeado exitosamente
-- ─────────────────────────────────────────────────────────────────────────
UPDATE public.inmobiliarias_main
SET url_listado         = 'http://peconcip.com.ar/mh/?offer-type=venta',
    estrategia_scraping = NULL,
    updated_at          = NOW()
WHERE id = 700
  AND url_listado = 'http://peconcip.com.ar#';
```

**Efecto esperado**: 1 fila actualizada.

---

## Resumen ejecutivo

| Dimension | Estado |
|-----------|--------|
| Sitio activo | SI — HTTP 200, 93KB, servicio de Tres Arroyos |
| Es inmobiliaria real | SI — venta, alquiler, administracion |
| url_listado valida | NO — `#` al final (rota) |
| Propiedades publicadas | **0** (confirmado por REST API + MyHome API + HTML embebido) |
| Requiere JS/Playwright | SI — Vite bundle detectado |
| WP Sitemap de propiedades | NO — ausente |
| estrategia_scraping actual | `sitemap` (incorrecta) |
| Bloqueante para pipeline | SI — url_listado rota; estrategia incorrecta |
| Importable ahora | NO — 0 propiedades |
| Reactivar cuando | Cuando el operador publique propiedades (monitorear) |

---

## Resultado de la ejecucion

**Autorizado y ejecutado el 2026-06-08 (Opcion B).**

| Paso | Resultado |
|------|-----------|
| STEP 1 Pre-verify | url_listado='http://peconcip.com.ar#', estrategia='sitemap', activa=True, guarda OK |
| STEP 2 PATCH | 1/1 filas actualizadas |
| STEP 3 Post-verify | Todos los assertions pasados |
| STEP 4 Colateral | 0 otros IDs afectados (solo id=700 en la tabla) |

**Estado final:**

| Campo | Antes | Despues |
|-------|-------|---------|
| `url_listado` | `http://peconcip.com.ar#` | `http://peconcip.com.ar/mh/?offer-type=venta` |
| `estrategia_scraping` | `sitemap` | **NULL** |
| `activa` | True | True (sin cambio) |
| `sitio_activo` | True | True (sin cambio) |
| `updated_at` | 2026-05-08 | 2026-06-08 |

Pecon Cip id=700 tiene ahora url_listado correcto y estrategia reseteada.
El pipeline puede alcanzar el sitio; fallara (0 propiedades) hasta que el operador publique fichas.

---

## FRENO

No se importo, valido, ni publico nada adicional.
UPDATE ejecutado y verificado.
No se corrio scraping adicional.
