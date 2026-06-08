# url_listado incorrecto — Batch Bajo Riesgo — Ejecutado

**Fecha ejecución:** 2026-06-08  
**Sprint:** sprint_autonomo_20260607  
**Branch:** fix/scraping-diagnostics-batch  
**Estado:** COMMIT EFECTIVO — 4/4 filas actualizadas

---

## Resultado de la transacción

| Paso | Resultado |
|------|-----------|
| STEP 1 Pre-verification | ✅ 4/4 valores previos confirmados |
| STEP 2 UPDATEs | ✅ 4/4 aplicados (guarda id + url_listado viejo) |
| STEP 3 Rollback | No requerido |
| STEP 4 Post-verification | ✅ 4/4 nuevas URLs confirmadas en DB |
| STEP 5 Collateral check | ✅ Sin modificaciones colaterales |

**Nota técnica:** Transacción implementada como _compensating transaction_ sobre la REST API de Supabase (no se dispone de `SUPABASE_DB_URL` para transacción ACID nativa). Las guardas dobles `id=eq.X AND url_listado=eq.VIEJO` en cada PATCH garantizan idempotencia. El campo `updated_at` no fue modificado (no incluido en el payload PATCH — solo `url_listado`).

---

## Cambios aplicados

| id | Nombre | url_listado anterior | url_listado nuevo |
|----|--------|---------------------|-------------------|
| 294 | Martha Bourre | `https://www.marthabourre.com.ar#` | `https://www.marthabourre.com.ar/inmuebles/` |
| 628 | Moreno, Negocios Inmob. | `http://inmobiliaria-moreno.webnode.com/inmuebles/` | `https://inmobiliaria-moreno.webnode.page/inmuebles/` |
| 704 | PAPPACENA \| CARBONE | `https://pcarbone.com#` | `https://pcarbone.com/inmuebles/venta` |
| 3532 | MENDOCASA LAVALLE | `https://inmobiliariamendocasa.com.ar/calculadora-de-alquileres/` | `https://inmobiliariamendocasa.com.ar/listings/` |

---

## Re-test de las nuevas URLs (read-only)

| id | HTTP | Size KB | card_hints | precios | detail_links | score | Veredicto |
|----|------|---------|-----------|---------|--------------|-------|-----------|
| 294 Martha Bourre | 200 | 19.0 | 4 | 0 | 0 | 19 | MODERATE_SIGNALS |
| 628 Moreno | 200 | 57.6 | 5 | 1 | 0 | 25 | STRONG_SIGNALS |
| 704 Pcarbone | 200 | 28.3 | **48** | **20** | 0 | **58** | STRONG_SIGNALS |
| 3532 Mendocasa | 200 | 94.3 | **58** | 0 | 4 | **43** | STRONG_SIGNALS |

**Detalle por sitio:**

**id=294 Martha Bourre** — MODERATE_SIGNALS  
Keywords: propiedad/inmueble/venta/alquiler/dormitorio/precio/ars. Sin precios ni links individuales en HTML estático (posible carga parcial dinámica). La URL es correcta. Sin embargo, `estrategia_scraping='dominio_caido'` hace que el scraper salte este sitio completamente. ⚠️ **No capturará propiedades hasta que se corrija `estrategia_scraping`.**

**id=628 Moreno** — STRONG_SIGNALS  
HTTP 200, 57.6KB, 5 card_hints, precio $350.000, 8 keywords fuertes. URL nueva (webnode.page) responde correctamente. Estrategia `sitemap` debería funcionar si el nuevo dominio tiene sitemap accesible. **Listo para scraping.**

**id=704 Pcarbone** — STRONG_SIGNALS  
HTTP 200, 28.3KB, 48 card_hints, 20 menciones de precio ($290.000 / $1.300.000 / $650.000), 8 keywords. Listado con muchas propiedades activas. **Listo para scraping.**

**id=3532 Mendocasa** — STRONG_SIGNALS  
HTTP 200, 94.3KB, 58 card_hints, 4 links individuales de propiedades, 5 keywords. WP plugin activo, 3 propiedades confirmadas vía REST API. `estrategia_scraping=None` — necesita configuración. **Listo para scraping una vez asignada estrategia.**

---

## Pendientes identificados (requieren autorización separada)

| id | Problema | Acción recomendada |
|----|----------|--------------------|
| 294 | `estrategia_scraping='dominio_caido'` — el scraper saltea este sitio | Cambiar a `'sitemap'` o `'html'` |
| 3532 | `estrategia_scraping=None` — sin estrategia definida | Asignar `'html'` o `'sitemap'` |
| 628 | Campo `web='http://inmobiliaria-moreno.webnode.com'` obsoleto | Actualizar a `'https://inmobiliaria-moreno.webnode.page'` |
| 700 | url_listado pendiente (`http://peconcip.com.ar#`) | En espera — JS-rendered, requiere Playwright |
| 6732 | url_listado pendiente (`https://sauce.com.ar#`) | En espera — card_hints bajos, posible SPA |
| 332 | Uco Domos: empresa de construcción, no inmobiliaria | Considerar `activa=False` |

---

## FRENO

> UPDATEs de url_listado completados. Scripts temporales eliminados.  
> **No se ejecutará nada más sin nueva autorización.**
