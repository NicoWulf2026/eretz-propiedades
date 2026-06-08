# url_listado incorrecto — Dry-Run Report

**Fecha:** 2026-06-08  
**Sprint:** sprint_autonomo_20260607  
**Branch:** fix/scraping-diagnostics-batch  
**Estado:** DRY-RUN — NO EJECUTADO. Pendiente autorización.

---

## Resumen ejecutivo

| Métrica | Valor |
|---------|-------|
| Targets analizados | 7 |
| `update_safe` | 6 |
| `no_public_listing_found` | 1 |
| `needs_manual_review` | 0 |
| SQL propuesto (UPDATE statements) | 6 |
| SQL ejecutado | 0 |

---

## Clasificación detallada

### ✅ update_safe (6 / 7)

| id | Nombre | url_listado actual | url_listado propuesto | Confianza | Evidencia clave |
|----|--------|-------------------|-----------------------|-----------|-----------------|
| 294 | Martha Bourre | `https://www.marthabourre.com.ar#` | `https://www.marthabourre.com.ar/inmuebles/` | ALTA | HTTP 200, card_hints=4, 7 señales |
| 628 | Moreno, Negocios Inmob. | `http://inmobiliaria-moreno.webnode.com/inmuebles/` | `https://inmobiliaria-moreno.webnode.page/inmuebles/` | ALTA | HTTP 200, 59KB, TLD migration confirmada |
| 700 | Inmobiliaria Pecon Cip | `http://peconcip.com.ar#` | `http://peconcip.com.ar/mh/?offer-type=venta` | MEDIA | Nav links bajo heading "Propiedades" en `/?post_type=property` |
| 704 | PAPPACENA \| CARBONE | `https://pcarbone.com#` | `https://pcarbone.com/inmuebles/venta` | MUY ALTA | HTTP 200, card_hints=23, 8 señales fuertes |
| 3532 | MENDOCASA LAVALLE | `https://inmobiliariamendocasa.com.ar/calculadora-de-alquileres/` | `https://inmobiliariamendocasa.com.ar/listings/` | ALTA | WP REST API retorna 3 listings, URLs de propiedades encontradas |
| 6732 | Sauce Inmobiliaria | `https://sauce.com.ar#` | `https://www.sauce.com.ar/properties/` | MEDIA-ALTA | HTTP 200, 147KB, señales de propiedad/venta/alquiler/ars |

### ❌ no_public_listing_found (1 / 7)

| id | Nombre | url_listado actual | Motivo |
|----|--------|-------------------|----|
| 332 | Uco Domos | `https://ucodomos.com/ventajas/` | Empresa de construcción de domos, NO inmobiliaria. Menú: Ventajas/Construcción/Portfolio/Opcionales. Sitemap: 0 propiedades. Sin precios en contenido. Contacto/WhatsApp únicamente. |

**Acción recomendada para id=332:** No UPDATE de url_listado. Revisar si debe desactivarse: `activa=False, sitio_activo=False`.

---

## DRY-RUN SQL

> **IMPORTANTE: NO EJECUTAR.** Este bloque es de revisión únicamente.  
> Tablas destino: `public.inmobiliarias_main` en Supabase.  
> Solo se modifica `url_listado` y `updated_at` — no se tocan otros campos.

```sql
-- ─────────────────────────────────────────────────────────────────────────────
-- [1] id=294 · Martha Bourre Propiedades Pilar
-- Anterior:  https://www.marthabourre.com.ar#
-- Nuevo:     https://www.marthabourre.com.ar/inmuebles/
-- Motivo:    Fragmento '#' no es URL navigable. /inmuebles/ es el listado real.
-- Evidencia: HTTP 200, card_hints=4, señales: propiedad/inmueble/venta/alquiler/dormitorio/precio/ars
-- Riesgo:    BAJO
-- Nota:      estrategia_scraping='dominio_caido' — revisar por separado (sitio está activo)
-- ─────────────────────────────────────────────────────────────────────────────
UPDATE public.inmobiliarias_main
SET url_listado = 'https://www.marthabourre.com.ar/inmuebles/',
    updated_at  = NOW()
WHERE id = 294
  AND url_listado = 'https://www.marthabourre.com.ar#';

-- ─────────────────────────────────────────────────────────────────────────────
-- [2] id=628 · Moreno, Negocios Inmobiliarios
-- Anterior:  http://inmobiliaria-moreno.webnode.com/inmuebles/
-- Nuevo:     https://inmobiliaria-moreno.webnode.page/inmuebles/
-- Motivo:    Webnode migró TLD de .com → .page. El dominio .com redirige a .page
--            pero el scraper no puede seguir redirecciones inter-TLD.
-- Evidencia: HTTP 200 en nueva URL, 59KB, señales fuertes de listado
-- Riesgo:    BAJO — migración TLD confirmada; contenido verificado
-- Nota:      web='http://inmobiliaria-moreno.webnode.com' también debería actualizarse
--            a 'https://inmobiliaria-moreno.webnode.page' (autorización separada)
-- ─────────────────────────────────────────────────────────────────────────────
UPDATE public.inmobiliarias_main
SET url_listado = 'https://inmobiliaria-moreno.webnode.page/inmuebles/',
    updated_at  = NOW()
WHERE id = 628
  AND url_listado = 'http://inmobiliaria-moreno.webnode.com/inmuebles/';

-- ─────────────────────────────────────────────────────────────────────────────
-- [3] id=700 · Inmobiliaria Pecon Cip
-- Anterior:  http://peconcip.com.ar#
-- Nuevo:     http://peconcip.com.ar/mh/?offer-type=venta
-- Motivo:    Fragmento '#' no navigable. El plugin WP expone listados en /mh/ con
--            filtros ?offer-type=venta y ?offer-type=alquiler (client-side routing).
-- Evidencia: /?post_type=property expone nav links a /mh/?offer-type=venta y
--            /mh/?offer-type=alquiler bajo el heading "Propiedades"
-- Riesgo:    MEDIO — URL identificada vía menú del sitio; listados son JS-rendered.
--            Sin fix de estrategia_scraping, el scraper no extraerá propiedades.
-- Nota extra: estrategia_scraping='sitemap' es INCORRECTO (sitemap tiene 0 props).
--             Este sitio probablemente requiere Playwright o estrategia custom.
--             El UPDATE de url_listado es correcto aunque insuficiente solo.
-- ─────────────────────────────────────────────────────────────────────────────
UPDATE public.inmobiliarias_main
SET url_listado = 'http://peconcip.com.ar/mh/?offer-type=venta',
    updated_at  = NOW()
WHERE id = 700
  AND url_listado = 'http://peconcip.com.ar#';

-- ─────────────────────────────────────────────────────────────────────────────
-- [4] id=704 · PAPPACENA | CARBONE Propiedades
-- Anterior:  https://pcarbone.com#
-- Nuevo:     https://pcarbone.com/inmuebles/venta
-- Motivo:    Fragmento '#' no navigable. /inmuebles/ devuelve HTTP 500; /inmuebles/venta
--            es el listado real con 23 card_hints y 8 señales fuertes.
-- Evidencia: HTTP 200, card_hints=23, señales: propiedad/inmueble/alquiler/venta/dormitorio/precio/ars/m2
-- Riesgo:    BAJO — página listado muy confirmada
-- ─────────────────────────────────────────────────────────────────────────────
UPDATE public.inmobiliarias_main
SET url_listado = 'https://pcarbone.com/inmuebles/venta',
    updated_at  = NOW()
WHERE id = 704
  AND url_listado = 'https://pcarbone.com#';

-- ─────────────────────────────────────────────────────────────────────────────
-- [5] id=3532 · INMOBILIARIA & GESTORIA MENDOCASA LAVALLE
-- Anterior:  https://inmobiliariamendocasa.com.ar/calculadora-de-alquileres/
-- Nuevo:     https://inmobiliariamendocasa.com.ar/listings/
-- Motivo:    url_listado apunta a calculadora de alquileres. /listings/ es el
--            post_type del plugin WP "Essential Real Estate".
-- Evidencia: HTTP 200, WP REST API /wp/v2/listing retorna 3 propiedades activas
--            (X-WP-Total=3), 4 listing URLs encontradas en HTML de /listings/
-- Riesgo:    BAJO — WP REST API confirma plugin y propiedades activas
-- Nota:      Solo 3 propiedades activas en total — rendimiento de scraping bajo
-- ─────────────────────────────────────────────────────────────────────────────
UPDATE public.inmobiliarias_main
SET url_listado = 'https://inmobiliariamendocasa.com.ar/listings/',
    updated_at  = NOW()
WHERE id = 3532
  AND url_listado = 'https://inmobiliariamendocasa.com.ar/calculadora-de-alquileres/';

-- ─────────────────────────────────────────────────────────────────────────────
-- [6] id=6732 · Sauce Inmobiliaria
-- Anterior:  https://sauce.com.ar#
-- Nuevo:     https://www.sauce.com.ar/properties/
-- Motivo:    Fragmento '#' no navigable. /properties/ es el listado real.
--            sauce.com.ar redirige canónicamente a www.sauce.com.ar.
-- Evidencia: HTTP 200, 147KB, card_hints=1, señales: propiedad/venta/alquiler/ars
-- Riesgo:    BAJO-MEDIO — card_hints=1 es bajo para 147KB (posible SPA con carga
--            dinámica de propiedades). Scraping puede requerir Playwright.
-- ─────────────────────────────────────────────────────────────────────────────
UPDATE public.inmobiliarias_main
SET url_listado = 'https://www.sauce.com.ar/properties/',
    updated_at  = NOW()
WHERE id = 6732
  AND url_listado = 'https://sauce.com.ar#';
```

---

## Items fuera de scope (requieren autorización separada)

### id=332 · Uco Domos — recomendación de desactivación
```sql
-- NO incluido en este dry-run — requiere autorización separada
-- Uco Domos es una empresa de construcción de domos geodésicos,
-- no tiene listado público de propiedades en venta/alquiler.
-- Recomendación: desactivar para evitar ciclos de scraping vacíos.
UPDATE public.inmobiliarias_main
SET activa = FALSE, sitio_activo = FALSE, updated_at = NOW()
WHERE id = 332;
```

### id=294, id=700 — estrategia_scraping desactualizada
- **id=294** Martha Bourre: `estrategia_scraping='dominio_caido'` con sitio activo → revisar y actualizar a `sitemap` o `html`
- **id=700** Pecon Cip: `estrategia_scraping='sitemap'` pero sitemap no tiene propiedades → este sitio es JS-rendered; necesita `requires_playwright`

### id=628 — campo `web` desactualizado
- **id=628** Moreno: `web='http://inmobiliaria-moreno.webnode.com'` → debería actualizarse a `'https://inmobiliaria-moreno.webnode.page'`

---

## Recomendación de ejecución

**Ejecutar en este orden (si se aprueba el dry-run):**

1. **Batch bajo riesgo** (ids 294, 628, 704, 3532) — ejecutar juntos, confianza ALTA
2. **Sauce id=6732** — ejecutar por separado, confirmar que el scraper puede extraer propiedades post-fix
3. **Pecon Cip id=700** — ejecutar por separado; planificar fix de `estrategia_scraping` en paralelo o inmediatamente después
4. **Uco Domos id=332** — requiere autorización adicional para desactivación

---

## FRENO — Pendiente autorización

> Este reporte documenta el análisis y el SQL propuesto.  
> **Ningún UPDATE ha sido ejecutado.**  
> Esperando confirmación explícita antes de proceder.
