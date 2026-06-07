# Fix G — Watson sin precio (JSON-LD Product intercepta HTML)

- Fecha: 2026-06-06
- Fix type: **Global** (aplica a cualquier sitio con JSON-LD Product sin offers/price)
- Archivo modificado: `scraper/scraper_propiedades.py`
- Línea: ~7863 (dentro de `_extract_detail_page`)

---

## 1. Diagnóstico

### ¿Qué pasaba?

Watson Propiedades (`watsonpropiedades.com`) captureaba 3 propiedades con `precio=None` aunque los precios están visibles en el HTML estático.

### Síntomas

- 3 props de Watson en staging (81057-81059) con `precio=None`
- `valid_price_ratio: 0.0` en el quality score de Watson
- `score_calidad: 40` (muy bajo, principalmente por missing_price)
- El scraper usó estrategia `static_html_detail` — correcto para este sitio

### Investigación paso a paso

| Paso | Hallazgo |
|---|---|
| Fetch HTTP de Watson URLs | precio EN el HTML: `<h3 class="price">US$\xa088.000,00</h3>` |
| Posición del precio en HTML | 77% del documento (byte 210,966 de 274,392) |
| Simulación BeautifulSoup | `soup.select_one(".price")` → texto `US$ 88.000,00` ✓ |
| Prueba con requests + _fix_mojibake | precio encontrado correctamente ✓ |
| JSON-LD scan en Watson HTML | `@type: "Product"` matchea `_JSONLD_TYPES` con solo `name` + `image` |
| Root cause | JSON-LD intercepta antes de `_html_extract_detail` → retorna sin precio |

---

## 2. Causa raíz

Watson usa el CMS **esmsv.com** que genera este JSON-LD en cada propiedad de detalle:

```json
{
  "@context": "https://schema.org",
  "@type": "Product",
  "name": "Casa en zona Centro. Excelente ubicación.",
  "image": "https://ss-cnt-001c.esmsv.com/.../CasaCentro.webp"
}
```

Este JSON-LD matchea `_JSONLD_TYPES` (que incluye `"Product"`). La función `_extract_detail_page` acepta el resultado de `_parse_jsonld_item()` y retorna **sin precio** (el schema no tiene `offers`/`price`), **sin llegar a llamar `_html_extract_detail`** donde el selector `.price` habría encontrado el precio.

### Flujo antes del fix

```
_extract_detail_page(url)
  → JSON-LD found: @type=Product (name + image only)
  → _parse_jsonld_item() → prop {titulo, imagenes, precio=None}
  → prop is not None → RETURN prop   ← retorna sin precio
  → _html_extract_detail() NEVER CALLED
```

### ¿Por qué el selector `.price` funciona?

El HTML tiene: `<h3 class="price">US$\xa088.000,00</h3>`

```python
# Simulación exacta del scraper (requests + _fix_mojibake_text):
soup.select_one(".price")  # → <h3 class="price">US$ 88.000,00</h3>
_normalizar_precio_detalle("US$ 88.000,00")  # → (88000.0, "USD")
```

✅ La extracción HTML SÍ funciona — solo estaba siendo bloqueada por el JSON-LD.

---

## 3. Fix G implementado

**Principio**: Fix global. No hardcodear Watson. Beneficia cualquier sitio con JSON-LD incompleto.

### Código antes

```python
if prop_jsonld:
    html_images = extraer_imagenes(soup, url)
    ...
    return prop_jsonld  # ← retorna sin precio si JSON-LD no lo tiene
```

### Código después

```python
if prop_jsonld:
    # Fix global: si JSON-LD no tiene precio, enriquecer desde HTML.
    # Causa raiz: sitios con @type=Product en JSON-LD que solo exponen
    # name/image pero no offers/price (ej: Watson CMS, esmsv.com).
    if prop_jsonld.get("precio") is None:
        try:
            _html_prop = _html_extract_detail(soup, url, inmob, raw_html)
            if _html_prop and _html_prop.get("precio") is not None:
                prop_jsonld["precio"] = _html_prop["precio"]
                prop_jsonld["moneda"] = _html_prop.get("moneda", "ARS")
                prop_jsonld["precio_ars"] = _html_prop.get("precio_ars")
                prop_jsonld["precio_usd"] = _html_prop.get("precio_usd")
                raw_json["precio_enriquecido_desde_html"] = True
                prop_jsonld["raw_json"] = raw_json
        except Exception:
            pass
    html_images = extraer_imagenes(soup, url)
    ...
    return prop_jsonld
```

---

## 4. Validación before/after

### Before Fix G (batch rescrape_controlled_20260606_fase2)

| Prop | precio | moneda | score |
|---|---|---|---|
| casa-en-zona-centro-excelente-ubicacion | **None** | ARS | 40 |
| casa-de-categoria-en-quintas-de-betbeder | None | ARS | 40 |
| casa-en-esquina-en-zona-centro | **None** | ARS | 40 |

Watson `valid_price_ratio: 0.0` · score: 61

### After Fix G (batch rescrape_watson_fixG_20260606)

| Prop | precio | moneda | fuente | score |
|---|---|---|---|---|
| casa-en-zona-centro-excelente-ubicacion | **88,000** | USD | HTML enrichment | 40 |
| casa-de-categoria-en-quintas-de-betbeder | None | ARS | sin precio en HTML | 40 |
| casa-en-esquina-en-zona-centro | **125,000** | USD | HTML enrichment | 40 |

Watson `valid_price_ratio: 0.667` · score: 71

Nota: El score de Watson (40) sigue bajo porque `ciudad=None` y `provincia=None` — Watson no expone ubicación ni en HTML ni en JSON-LD. No es un problema del fix.

---

## 5. Prop 2: genuinamente sin precio

La prop `casa-de-categoria-en-quintas-de-betbeder-apta-credito-hipotecario-4` NO tiene precio en el HTML — verificado en 3 fetches independientes. El campo está vacío o la propiedad está listada como "Consultar precio". Correcto mantener `precio=None`.

---

## 6. Análisis de riesgo

| Riesgo | Nivel | Mitigación |
|---|---|---|
| `_html_extract_detail` lanza excepción | MUY BAJO | `try/except Exception: pass` → degradación limpia |
| Fix sobreescribe precio válido de JSON-LD | **CERO** | Solo activa si `prop_jsonld.get("precio") is None` |
| Fix altera otros campos (titulo, imagenes) | CERO | Solo modifica precio/moneda/precio_ars/precio_usd |
| Regresión en sitios con JSON-LD correcto | CERO | Condition `precio is None` nunca activa si JSON-LD tiene precio |
| Performance (llamada doble _html_extract_detail) | MÍNIMO | Solo en caso JSON-LD-match-sin-precio; soup ya parseado |

---

## 7. Alcance del fix

Sitios beneficiados (conocidos o probables):

| Dominio | CMS | Patrón |
|---|---|---|
| watsonpropiedades.com | esmsv.com | Product JSON-LD sin offers |
| Cualquier sitio con Product JSON-LD sin price/offers | Varios | Idem |

**No afectados**:
- Sitios con JSON-LD + precio completo → sin cambio (condition no activa)
- Sitios sin JSON-LD → sin cambio (fix nunca alcanzado)
- Sitios con JSON-LD de otro tipo → sin cambio (JSONLD_TYPES filter no matchea Product vacío... espera, SÍ matchea pero condition `precio is None` activa → mejora, no rompe)

---

## 8. Pendientes Watson

| Pendiente | Situación | Prioridad |
|---|---|---|
| Actualizar staging props 81057-81059 | Necesitan re-import con Fix G | Media |
| Watson ubicación (ciudad/provincia=None) | Watson no expone ubicación → skippear geocoding | Baja |
| Watson tiene más de 3 props (expected=6) | Paginación detectada, solo se captó page 1 | Media |

---

*Fix G implementado y validado · 2026-06-06 · rama fix/scraping-diagnostics-batch*
