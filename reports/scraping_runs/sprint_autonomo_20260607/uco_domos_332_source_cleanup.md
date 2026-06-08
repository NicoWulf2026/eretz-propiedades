# Uco Domos id=332 — Source Cleanup

**Fecha:** 2026-06-08  
**Sprint:** sprint_autonomo_20260607  
**Objetivo:** Confirmar si debe salir del universo scrapeable.

---

## Estado actual en Supabase

| Campo | Valor |
|-------|-------|
| `id` | 332 |
| `nombre` | Uco Domos |
| `web` | https://ucodomos.com |
| `url_listado` | `https://ucodomos.com/ventajas/` |
| `activa` | True |
| `sitio_activo` | True |
| `cms_detectado` | wordpress |
| `estrategia_scraping` | `dominio_caido` (DNS fallo 2026-05-25) |
| `total_propiedades` | NULL (nunca scrapeado exitosamente) |

---

## Evidencia de clasificacion

### Homepage

| Signal | Valor |
|--------|-------|
| Titulo | "Ucodomos – Inspirados en la Naturaleza" |
| Meta description | No expuesta |
| HTTP | 200, 55KB |

### Menu de navegacion

```
Inicio | Ventajas | Tipos de Construccion | Opcionales | Portfolio | Contacto
```

**Ausentes**: "Propiedades", "Inmuebles", "Venta", "Alquiler", "Tasacion", "Buscar".  
El menu describe una empresa de construccion: tipos, opcionales, portfolio.

### Keywords detectados

| Tipo | Keywords encontrados |
|------|---------------------|
| Senales inmobiliaria | `ars` (unico — probable precio de servicio, no de propiedad) |
| Senales constructora | `domo`, `construccion`, `ventajas` |
| Property links | **NINGUNO** |

### url_listado = `/ventajas/`

La pagina `/ventajas/` es una pagina de marketing sobre **beneficios de construir un domo** (por que elegir domos geodesicos, sustentabilidad, etc.). No contiene fichas, precios de propiedades, ni listados.

### Sitemap WP — 7 secciones, ninguna de propiedades

| URL sitemap | Tipo de contenido |
|-------------|------------------|
| `wp-sitemap-posts-page-1.xml` | Paginas estaticas |
| `wp-sitemap-posts-portfolio-1.xml` | **Portfolio** de construcciones |
| `wp-sitemap-posts-monolit_member-1.xml` | Equipo |
| `wp-sitemap-posts-monolit_service-1.xml` | Servicios |
| `wp-sitemap-posts-monolit_timeline-1.xml` | Timeline corporativo |
| `wp-sitemap-taxonomies-portfolio_cat-1.xml` | Categorias de portfolio |
| `wp-sitemap-users-1.xml` | Usuarios |

Ausentes: `property`, `propiedad`, `inmueble`, `listing`. El WP theme es "Monolit" — un tema corporativo/portfolio, no inmobiliario.

### WP REST API

```
404  /wp-json/wp/v2/property
404  /wp-json/wp/v2/propiedad
```

No existen post types de propiedades.

---

## Clasificacion

**`constructora_sin_listado`**

Uco Domos es una empresa constructora de domos geodesicos en el Valle de Uco (Mendoza). Produce domos para glamping / turismo / vivienda. No tiene listado de propiedades en venta ni alquiler, no es intermediaria inmobiliaria. El sitio es 100% institucional/comercial de servicios de construccion.

La inclusion en la base de datos parece haber sido un error de origen — posiblemente captada por el nombre ("Uco" + "propiedades/inmuebles" como contexto de la busqueda inicial) sin verificacion de su actividad real.

---

## Dry-run SQL propuesto

> **NO EJECUTAR** — pendiente autorizacion.

```sql
-- ─────────────────────────────────────────────────────────────────────────
-- Uco Domos id=332: desactivacion por no ser inmobiliaria
-- Evidencia: empresa constructora de domos, sin listado de propiedades,
--            sin post types inmobiliarios, sin precios de propiedades.
-- Guarda estricta: id=332 AND url_listado='https://ucodomos.com/ventajas/'
-- Riesgo: BAJO — total_propiedades=NULL, nunca scrapeado exitosamente,
--         no hay datos historicos a perder.
-- ─────────────────────────────────────────────────────────────────────────
UPDATE public.inmobiliarias_main
SET activa        = FALSE,
    sitio_activo  = FALSE,
    updated_at    = NOW()
WHERE id = 332
  AND url_listado = 'https://ucodomos.com/ventajas/';
```

**Efecto esperado:** `lista_para_batch=False` permanente, no entra en ningun pipeline futuro.  
**Filas afectadas:** 1 (guarda estricta por id + url_listado actual).

---

## Riesgo

| Dimension | Evaluacion |
|-----------|-----------|
| Datos historicos perdidos | Ninguno — `total_propiedades=NULL`, nunca scrapeado |
| Reversible | Si — un UPDATE puede reactivar si fuera necesario |
| Colateral | Cero — id=332 aislado, guarda doble |
| Error de clasificacion | Muy improbable — evidencia multiple y consistente |

---

## Recomendacion

**Desactivar.** Uco Domos no es inmobiliaria. No tiene ni tendra propiedades para scrapear.  
El SQL propuesto es de bajo riesgo y limpia el universo scrapeable de una fuente invalida.

---

---

## Resultado de la ejecucion

**Autorizado y ejecutado el 2026-06-08.**

| Paso | Resultado |
|------|-----------|
| STEP 1 Pre-verify | activa=True, sitio_activo=True, guarda OK |
| STEP 2 PATCH | 1/1 filas actualizadas |
| STEP 3 Post-verify | activa=False, sitio_activo=False, url_listado sin cambio |
| STEP 4 Colateral | Sin otros IDs afectados |

**Estado final:**

| Campo | Antes | Despues |
|-------|-------|---------|
| `activa` | True | **False** |
| `sitio_activo` | True | **False** |
| `url_listado` | https://ucodomos.com/ventajas/ | sin cambio |
| `updated_at` | 2026-05-08 | 2026-06-08T15:08:27Z |

Uco Domos id=332 queda fuera del universo scrapeable. No volvera a entrar en ningun batch del pipeline.
