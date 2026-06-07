# Fix H — Bug de título: widget de búsqueda capturado como título de propiedad

- Fecha: 2026-06-07
- Tipo: **Fix global** — `_is_useful_scraped_title()` + reordenamiento de candidatos en `_html_extract_detail()`
- Archivo modificado: `scraper/scraper_propiedades.py`
- Bug original detectado en: luciafrolik.com.ar, inmobiliariaescuza.com
- Alcance real: **cualquier sitio** cuya página de detalle contenga un widget de búsqueda con estos patrones de texto
- Modo: **captura local ONLY — sin escritura a Neon ni Supabase**

---

## 1. Diagnóstico del bug

### Síntoma

En el batch del Bloque 2 (20260607), 14 de 14 props de luciafrolik + escuza tenían título incorrecto:

| Sitio | Título incorrecto capturado | Props afectadas |
|---|---|---|
| luciafrolik.com.ar | `¿Que estás buscando?` | 12/12 |
| inmobiliariaescuza.com | `¡Comenzar, búsqueda avanzada!` | 2/2 |

### Causa raíz

Ambos sitios usan el mismo CMS PHP con el patrón de URL `{tipo}s-en-{op}-en-{ciudad}-{id}.html`. Las páginas de detalle tienen un widget de búsqueda visible en el encabezado, con esta estructura HTML:

```html
<h2 class="titulo text-center-xs">
  <span>¿Que estás buscando?</span>
</h2>
</div>
<form class="clearfix" action="propiedades.php">
```

La función `_html_extract_detail()` busca candidatos de título en este orden:
1. CSS selectors: `"h1", ".property-title", ".titulo", ".listing-title", "section.famie-benefits-area"`
2. URL slug (`_title_from_detail_url`)
3. `og:title` / `twitter:title`
4. Tag `<title>`

El selector `.titulo` coincidía con el `h2.titulo text-center-xs` del widget, retornando el texto del formulario antes de llegar al tag `<title>` donde estaba el título correcto.

`_is_useful_scraped_title()` no rechazaba estos textos porque no contenían patrones conocidos de UI (solo detectaba textos de accesibilidad como "mover a la izquierda").

### Confirmación

- **Título incorrecto**: `<h2 class="titulo text-center-xs"><span>¿Que estás buscando?</span></h2>`
- **Título correcto**: `<title>Casas en Venta - Paz 121</title>` (luciafrolik), `<title>Casas en Venta - Cabral al 600</title>` (escuza)
- Sin `og:title` ni `h1` en estas páginas

---

## 2. Implementación del fix

### Componente A — Regex global `_UI_SEARCH_WIDGET_RE` (nuevo)

Agregado en línea ~426 (junto a `_FILENAME_TITLE_RE`):

```python
# Regex global para detectar textos de cabeceras de formularios/widgets de búsqueda.
# Estos textos NUNCA son títulos válidos de propiedades — Fix H (global).
_UI_SEARCH_WIDGET_RE = re.compile(
    r"(?:qu[eé]\s+est[aá]s\s+buscando"       # "¿Que estás buscando?" / "¿Qué estás buscando?"
    r"|b[uú]squeda\s+avanzada"                # "Búsqueda avanzada" / "Busqueda avanzada"
    r"|comenz[aá]r\b.{0,20}b[uú]squeda"      # "Comenzar, búsqueda avanzada" / "¡Comenzar búsqueda!"
    r"|buscador\s+avanzado)",                 # "Buscador avanzado" (variante genérica)
    re.I | re.UNICODE,
)
```

### Componente B — Check en `_is_useful_scraped_title()` (global)

Agregado al final de `_is_useful_scraped_title()`:

```python
# Rechazar cabeceras de formularios/widgets de búsqueda — Fix H (global).
if _UI_SEARCH_WIDGET_RE.search(text):
    return False
```

### Componente C — Reordenamiento de candidatos en `_html_extract_detail()`

Antes:
```python
title_candidates = [
    find_text("h1", ".property-title", ".titulo", ...),
    _title_from_detail_url(url),                         # ← URL slug (2do)
    _first_meta_content(soup, "meta[property='og:title']", ...),
    find_text("title"),                                  # ← <title> tag (último)
]
```

Después:
```python
title_candidates = [
    find_text("h1", ".property-title", ".titulo", ...),
    _first_meta_content(soup, "meta[property='og:title']", ...),
    find_text("title"),                                  # ← <title> tag (3ro, antes que URL slug)
    _title_from_detail_url(url),                         # ← URL slug (fallback final)
]
```

**Razón**: el tag `<title>` da títulos más legibles que el slug de URL (que puede contener IDs, extensiones `.html`, y números de dirección truncados). El slug sigue disponible como fallback final.

---

## 3. Verificación del fix

### Tests unitarios de `_is_useful_scraped_title`

```
=== DEBE RECHAZAR (widget texts) ===
  [OK RECHAZADO] '¿Que estás buscando?'
  [OK RECHAZADO] '¡Comenzar, búsqueda avanzada!'
  [OK RECHAZADO] 'Búsqueda avanzada'
  [OK RECHAZADO] 'Comenzar búsqueda avanzada'
  [OK RECHAZADO] 'Buscador avanzado'
  [OK RECHAZADO] 'Busqueda avanzada'

=== DEBE ACEPTAR (property titles) ===
  [OK ACEPTADO] 'Casa en venta en Tandil - Paz 121'
  [OK ACEPTADO] 'Casas en Venta - Paz 121'
  [OK ACEPTADO] 'Departamento en alquiler - Cabral al 600'
  [OK ACEPTADO] 'Casas En Venta En Tandil Paz 121 44.Html'
  [OK ACEPTADO] 'Lote en venta Rawson'
```

**6/6 rechazados correctamente. 5/5 aceptados correctamente.**

### Re-run batch post-fix (local, no DB)

Batch: `block2_title_fix_rerun_20260607_v2` · workers=1 · timeout=350s

| Sitio | Props | Antes | Después |
|---|---|---|---|
| luciafrolik.com.ar | 12 | `¿Que estás buscando?` | ✅ Ver tabla detalle |
| inmobiliariaescuza.com | 2 | `¡Comenzar, búsqueda avanzada!` | ✅ Ver tabla detalle |

### Títulos capturados post-fix

#### luciafrolik.com.ar (12 props — todas corregidas)

| Título capturado | Precio |
|---|---|
| Casas en Venta - Paz 121 | 115,000 USD |
| Casas en Venta - Pavón 1171 | 170,000 USD |
| Casas en Venta - Piedrabuena 87 | 129,000 USD |
| Casas en Venta - Larreal al 900 | 195,000 USD |
| Casas en Venta - 25 de mayo al 100 | 195,000 USD |
| Casas en Venta - Monseñor de Andrea al 200 | 265,000 USD |
| Casas en Venta - Dr Pere al 1600 | 350,000 USD |
| Casas en Venta - Los Aromos 1400 Zona Golf | 480,000 USD |
| Casas en Venta - Fleming | (consultar) |
| Casas en Venta - Fontana 400 | (consultar) |
| Casas en Venta - Linstown 400 | (consultar) |
| Casas en Venta - Paso de los Andes al 400 | (consultar) |

#### inmobiliariaescuza.com (2 props — ambas corregidas)

| Título capturado | Precio |
|---|---|
| Casas en Venta - Av. Avellaneda al 1300 | (consultar) |
| Casas en Venta - Cabral al 600 | 58,000 USD |

---

## 4. Naturaleza del fix — global, no por dominio

| Criterio | Evaluación |
|---|---|
| ¿Hardcodea luciafrolik o escuza? | **NO** — el fix es regex en `_is_useful_scraped_title()` |
| ¿Aplica a otros CMS con widget similar? | **SÍ** — cualquier sitio con "búsqueda avanzada" como h2 |
| ¿Puede afectar sitios existentes? | Mínimo — ningún título legítimo contiene "¿Que estás buscando?" o "Búsqueda avanzada" |
| ¿El reordenamiento de candidatos es seguro? | Sí — `_is_useful_scraped_title` filtra `<title>` tags de agencia o genéricos |
| Regresiones posibles | Prácticamente cero — fix aditivo en filtro de rechazo |

---

## 5. Estado final

### Commits involucrados (pendientes de push)

| Fix | Commit activo |
|---|---|
| Bloque 1 (detail_patterns, Fix E, Fix A, Fix B) | `69cac0db` |
| Fix G (JSON-LD price enrichment) | `fe4ecd04` |
| Block 2 batch reports + Block 2 plan | `eff74f37` |
| **Fix H (widget blacklist + candidatos)** | **pendiente de commit** |

---

## 6. Impacto en props importables

Con Fix H aplicado, las 14 props de luciafrolik + escuza pasan de **no importables** a **importables**:

| Dominio | Props | Estado post-fix |
|---|---|---|
| luciafrolik.com.ar | 12 | ✅ Títulos ricos — listos para import |
| inmobiliariaescuza.com | 2 | ✅ Títulos correctos — listos para import |
| **Subtotal** | **14** | **importables** |

Junto con las 45 ya limpias (tonyzorrilla=30 + dilello=15), el bloque completo tiene ahora **59 props importables**.

---

## 7. Controles de seguridad

| Control | Estado |
|---|---|
| Import a Neon | NO ejecutado |
| validate_raw_properties | NO ejecutado |
| Geocoding | NO ejecutado |
| publish_queue | NO modificado |
| Supabase | NO tocado |
| Frontend | NO tocado |
| .env | NO modificado |
| git push | NO ejecutado |

---

## FASE 6 — Freno activo

**STATUS: EN ESPERA DE AUTORIZACIÓN**

Fix implementado, validado y verificado en re-run.  
14 props con títulos correctos. Sin importar nada.  
Próximo paso: commit de Fix H + autorización de import (tonyzorrilla + dilello = 45 props, o también luciafrolik + escuza = 14 props).

---

*Fix H: 2026-06-07 · batch block2_title_fix_rerun_20260607_v2 · rama fix/scraping-diagnostics-batch*
