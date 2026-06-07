# Re-scrape Controlado — FASE 2

- Fecha: 2026-06-06
- Batch: `rescrape_controlled_20260606_fase2`
- Condiciones: workers=1, timeout=220s, static_detail only, NO Playwright, NO DB, NO Supabase
- Objetivo: validar que fixes aplicados en commit 69cac0db funcionan en capturas nuevas

---

## Agencias scrapeadas

| Agencia | inmobiliaria_id | URL listado | Props capturadas | Estado |
|---|---|---|---|---|
| Innoacafayate | 5282 | http://www.innoacafayate.com/propiedades | 17 | OK |
| Campos de la Pampa | 1443 | http://www.camposdelapampa.com.ar/ofertadecampos-camposenventa.html | 4 | OK |
| Watson Propiedades | 6162 | https://www.watsonpropiedades.com/explora-propiedades | 3 | OK |
| **TOTAL** | — | — | **24** | **3/3 OK** |

Errores: 0 · Skipped (fuente inválida): 0

---

## Validación Fix E — Títulos CMS short-ID rural (CamposDelAmapa)

**Antes del fix**: Títulos eran nombres de archivo: `Ca266.Html`, `Mo342.Html`, etc.  
**Después del fix**: Títulos ricos extraídos de `section.famie-benefits-area`:

| URL | Título POST Fix E | Score |
|---|---|---|
| /ca266.html | Departamento Loventué Muy buen acceso 6.000 ha Cria | 60 |
| /mo342.html | Limay Mahuida Oportunidad 15.000 ha Cria | 60 |
| /mo340.html | Departamento Chalileo Oportunidad 30.000 ha Cria | 60 |
| /mi319.html | Departamento Toay Bosque abierto 600 ha Ganaderia y Agricultura | 60 |

✅ **Fix E validado**: 0 títulos filename en nueva captura. Títulos descriptivos y ricos.

Nota: Las 4 props en staging (81053-81056) siguen con el título genérico "Campo en venta en La Pampa" actualizado en el UPDATE controlado. Si se hace re-import, obtendrían los títulos ricos. Decisión pendiente.

---

## Validación Fix B — Operación desde URL path ASP CMS (Innoacafayate)

**Antes del fix**: Operación=None para props con URL `/alquiler/item.asp` o `/venta/item.asp`.  
**Después del fix**: Operación inferida del subfolder de URL.

| Operación | Props | Ejemplo |
|---|---|---|
| `venta` | 11 | `/venta/item.asp?t=Haras-La-Querencia...` |
| `alquiler` | 6 | `/alquiler/item.asp?t=Local-calle-Salta-329...` |

✅ **Fix B validado**: 100% de props con operación correcta.

---

## Validación Fix A — Ubicación desde hostname (Innoacafayate)

**Antes del fix**: ciudad/provincia=None para Innoacafayate (el HTML no los expone).  
**Después del fix**: `_infer_location_from_hostname("innoacafayate.com")` → ciudad=Cafayate, provincia=Salta.

| Ciudad | Provincia | Props |
|---|---|---|
| Cafayate | Salta | 17/17 |

✅ **Fix A validado**: 100% de props de Innoacafayate con ubicación correcta.

---

## Precios por agencia

### Innoacafayate (17 props)

| Precio | Props |
|---|---|
| USD con precio | 5 (Haras 1.45M, Depto 65k, Casa 42k, Lote 75k, Lote 57k) |
| ARS con precio | 3 (Local 450k, Deptos 600k, Casa Lamadrid 400k) |
| Sin precio (precio=None) | 9 |

Ratio con precio: 8/17 = 47% · Genuinos (precio=None en HTML)

### CamposDelAmapa (4 props)

- precio=None en todas — estos campos rurales no publican precio en el HTML (consultar)
- Correcto: no inventar precio

### Watson (3 props) — antes del Fix G

- precio=None en las 3 — root cause investigado en FASE 3

---

## Regresiones detectadas

Ninguna. Los fixes no empeoraron ningún dominio previo.

- Fix E: rechaza correctamente títulos filename sin afectar títulos reales
- Fix B: infiere operación desde URL, no sobreescribe operación explícita
- Fix A: solo activa cuando ciudad/provincia están vacíos, no pisa datos existentes

---

## Comparativa before/after por agencia

| Métrica | Batch anterior (Jun 6 AM) | Re-scrape FASE 2 (Jun 6 PM) |
|---|---|---|
| Props totales | 24 | 24 |
| Títulos filename (inaceptables) | 4 | **0** ✅ |
| Operación=None | 0 (ya corregido) | 0 ✅ |
| Ubicación=None | 3 (watson) | 3 (watson, sin hostname location) |
| Props con precio | 8/24 | 8/24 |
| Estrategia usada | static_html_detail | static_html_detail |

---

*Batch: `rescrape_controlled_20260606_fase2` · workers=1 · NO DB · NO Supabase*
