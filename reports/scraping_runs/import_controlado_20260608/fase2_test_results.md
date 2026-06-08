# ETAPA 2 — FASE 2: Tests formales id=628 y id=704

**Fecha:** 2026-06-08  
**Branch:** fix/scraping-diagnostics-batch  

---

## id=628 — Inmobiliaria Moreno (Webnode)

**URL testeada:** `https://inmobiliaria-moreno.webnode.page/inmuebles/`  
**Resultado:** `strategy_quality_failed` — EXCLUIDO

### Detalle

| Extractor | Estado | Props | Score | Issues |
|-----------|--------|-------|-------|--------|
| static_html_detail | no_property_links | — | — | sin_links_detalle_estaticos |
| json_ld | sin_propiedades | — | — | json-ld sin datos |
| sitemap | success (parcial) | 1 | 67 | urls_invalidas |

**Diagnóstico:** El sitio usa Vue.js (`requires_playwright_signals: ["vue_app"]`). El HTML
estático no contiene links de propiedades — el contenido se genera en el cliente.
La URL de listado retorna solo 1 card hint estático (enlace a la página general) sin
links individuales de fichas.

**Causa raíz:** SPA (Single Page Application) con Vue.js. El scraper estático no puede
navegar a las fichas individuales sin Playwright.

**Decisión:** EXCLUIDO de este batch. Requiere autorización de Playwright masivo para 
importar. Se mantiene en la DB como `activa=True` con URL corregida, pero la estrategia
de scraping no puede resolverse con extractores estáticos.

**Próxima acción recomendada:** Incluir en bloque `requires_playwright` (pendiente autorización).

---

## id=704 — Pcarbone / Pappacena Propiedades

**URL testeada:** `https://pcarbone.com/inmuebles/venta`  
**Primer resultado (antes de Fix W):** `strategy_quality_failed` — score=84, `urls_invalidas`  
**Causa:** Las URLs de fichas individuales usan un patrón no reconocido por el scraper.

### Patrón de URLs de pcarbone.com

```
https://pcarbone.com/2930-local-comercial-en-venta-olazabal-esq-camacua-ocampo
https://pcarbone.com/2931-chalet-en-venta-cardoso-2900
https://pcarbone.com/2947-minimalista-en-venta-del-remedio-1100
https://pcarbone.com/2953-departamento-en-venta-camacua-500
https://pcarbone.com/2955-lote-para-desarrollo-en-venta-olazabal-esquina-p-rojas
```

Patrón: `/{ID_4+digitos}-{tipo}-en-(venta|alquiler)-{descripcion}` — path raíz sin extensión.

### Fix W aplicado

```python
# Fix W: CMS argentino con ID numerico de 4+ digitos al inicio del path raiz +
# slug con operacion embebida: /{ID}-{tipo}-en-(venta|alquiler)-{desc}
r"^\d{4,}-[^/?#]*-en-(venta|alquiler)[^/?#]*$",
```

- Insertado en `detail_patterns` (scraper_propiedades.py ~línea 10141)
- 17/17 tests de regresión PASS (incluyendo pcarbone + prior fixes Q-V)
- Retest formal con `--test-url` corriendo en background (task: byeixitas)

### Diagnóstico del primer test (pre-Fix W)

```
static_html_detail: score=84, 11 props extraídas, 20 páginas detectadas, 24 cards/página
json_ld: sin_propiedades
Resultado: strategy_quality_failed (urls_invalidas como blocking issue)
```

**Señales positivas:** 20 páginas de resultados × ~12 props/página ≈ 240 props totales disponibles.
Precios y tipos de propiedad detectados en el HTML. Score base de 84 (supera el umbral de 70).

**Decisión:** PENDIENTE resultado del retest post-Fix W. Si pasa:
- 11 props capturadas en esta etapa es partial_ratio (falta paginación)
- Se puede incluir en próximo batch (este batch ya está lleno con los 10 candidatos confirmados)
- Estimado: 50 props máx en primer run (cap por dominio), con ~240 disponibles

---

## Resumen FASE 2

| id | Sitio | URL | Score | Resultado | Acción |
|----|-------|-----|-------|-----------|--------|
| 628 | Moreno Webnode | `.webnode.page/inmuebles/` | 67 | FALLO — Vue.js/Playwright | Excluido este batch |
| 704 | Pcarbone | `pcarbone.com/inmuebles/venta` | 84→? | FIX W aplicado, retest pendiente | Próximo batch si aprueba |

**FASE 3 Candidatos:** Los 10 sitios confirmados del sprint anterior (ids: 6335, 4418, 945, 4746, 5282, 4709, 3531, 3532, 5167, 6732).
