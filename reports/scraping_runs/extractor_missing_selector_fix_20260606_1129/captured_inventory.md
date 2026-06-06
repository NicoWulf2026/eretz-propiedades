# Inventario de capturas — Fix extractor_missing_selector

- Fecha: 2026-06-06
- Batch fuente: `data/scraping_batches/internal_batch_20260606_1129/captured/`
- Total propiedades capturadas: **24**
- Dominios exitosos: 3 de 11 testeados
- Estado: CAPTURA LOCAL SOLAMENTE — NO importar a Neon sin revisar flags

---

## Resumen por dominio

| Dominio | ID Inmo | Props | Con precio | Sin precio | Tipos | Operaciones | Score prom | Flags |
|---|---|---|---|---|---|---|---|---|
| innoacafayate.com | 5282 | 17 | 9 | 8 | terreno(8) casa(3) dept(3) local(2) hotel(1) | venta(11) alquiler(6) | 68 | operacion_corregida en 6 |
| camposdelapampa.com.ar | 1443 | 4 | 0 | 4 | campo(4) | venta(4) | 60 | titulo/tipo extraídos de URL |
| watsonpropiedades.com | 6162 | 3 | 0 | 3 | casa(3) | venta(3) | 40 | sin precio |
| **TOTAL** | | **24** | **9** | **15** | | | **63** | |

---

## Detalle por dominio

### innoacafayate.com (ID: 5282) — 17 props

**Estrategia**: `static_html_detail` — nueva, habilitada por el fix del patrón ASP CMS (`/venta/item.asp`, `/alquiler/item.asp`)

**Calidad general**: Media-alta. Títulos descriptivos, imágenes presentes en todos, precio en 9 de 17.

**Issues conocidos**:
- **operacion_corregida (6 props)**: Las 6 props de `/alquiler/item.asp` tienen `operacion=venta` en el JSON capturado porque el scraper lee el campo del HTML. El inventario corrige esto inferiendo la operación desde el segmento de URL. Antes de importar a Neon hay que verificar que la columna operacion sea correcta en raw.
- **sin_precio (8 props)**: Precio no extraído, posiblemente en HTML dinámico o formulario de contacto.

**Props de alta calidad (score 75, con precio)**:
- Haras La Querencia 800 Hectareas — terreno — USD 1,450,000
- Depto en Salta sobre avenida Chile — departamento — USD 65,000
- Casa Pueblo Nuevo Mza. 21 — casa — USD 42,000
- Propiedad en calle Ex Colon — terreno — USD 75,000
- Lote Barrio Ribera 1 — terreno — USD 50,000
- Lote en calle Chacabuco Cafayate — terreno — USD 57,000
- Local calle Salta 329 — local — ARS 450,000 (alquiler)
- Deptos Guemes Sur — departamento — ARS 600,000 (alquiler)
- Casa Lamadrid — casa — ARS 400,000 (alquiler)

**Props con issues de precio (score 60)**:
- 8 props sin precio — terreno/hotel/casa/local — ARS sin monto

---

### camposdelapampa.com.ar (ID: 1443) — 4 props

**Estrategia**: `static_html_detail` — nueva, habilitada por el fix del patrón short-ID (`/ca266.html`, `/mo342.html`, etc.)

**Calidad general**: Baja. El patrón de URL corto no provee metadata útil. El scraper captura las páginas de detalle pero no puede extraer título ni tipo desde la URL.

**Issues conocidos**:
- **titulo_extraido_de_url**: El título en el JSON raw es el filename sin extensión (ej: "Ca266.Html"). El inventario lo corrige a "Campo / Propiedad Rural (ref ca266)".
- **tipo_corregido**: El JSON raw muestra `tipo_propiedad=departamento` (fallback del scraper). La inmobiliaria se llama "Campos de la Pampa" y solo comercializa campos, por lo que se corrige a `campo`.
- **sin_precio**: Ninguna de las 4 props tiene precio extraído.

**Score 60 para todas**: Sin precio + metadata incompleta.

**Recomendación antes de importar**: Revisar manualmente los 4 HTMLs de detalle o la web para confirmar título y precio reales. Los archivos están en `data/scraping_batches/internal_batch_20260606_1129/captured/0002_*.json`.

---

### watsonpropiedades.com (ID: 6162) — 3 props

**Estrategia**: `static_html_detail` — nueva, habilitada por el fix del patrón clean-URL (`/casa-en-zona-centro-excelente-ubicacion`)

**Calidad general**: Media-baja. URLs descriptivas (tipo extraído del slug), imágenes presentes, pero sin precio.

**Issues conocidos**:
- **sin_precio (3/3)**: Precio no extraído. Posiblemente está en el HTML como texto libre no estructurado o en una llamada JS posterior.

**Score 40 para todas**: Sin precio, sin coordenadas.

**Nota positiva**: Los slugs son informativos — el tipo de propiedad se infiere del inicio del slug. Ej: `casa-en-zona-centro-excelente-ubicacion` → casa, zona Centro.

---

## Flags para importación a Neon

Antes de ejecutar `import_captured_props_to_neon.py` con estas capturas, verificar:

1. **inmobiliaria_id**: Los archivos JSON capturados muestran `inmobiliaria_id=0` (se usaron IDs temporales en el batch de test). Usar los IDs correctos: 5282 (innoacafayate), 1443 (camposdelapampa), 6162 (watson).
2. **operacion de innoacafayate**: Revisar los 6 registros con `operacion_corregida` — el raw tendrá `venta` pero deben ser `alquiler`.
3. **tipo_propiedad de camposdelapampa**: El raw tendrá `departamento` para los 4 campos — corregir a `campo`.
4. **titulo de camposdelapampa**: Limpiar "Ca266.Html" → título real (requiere revisión manual o scraping de detalle con extracción de título).
5. **Deduplicación**: Verificar que los `hash_dedup` no colisionen con props ya en Neon de estas inmobiliarias.

---

## Estado de importación

- A Neon raw: **NO** (pendiente)
- A staging: **NO** (pendiente)
- A Supabase: **NO** (no autorizado en este sprint)

---

## Archivos relacionados

- Manifest CSV: `reports/scraping_runs/extractor_missing_selector_fix_20260606_1129/captured_manifest.csv`
- JSON raw innoacafayate: `data/scraping_batches/internal_batch_20260606_1129/captured/0001_www_innoacafayate_com_propiedades.json`
- JSON raw camposdelapampa: `data/scraping_batches/internal_batch_20260606_1129/captured/0002_www_camposdelapampa_com_ar_ofertadecampos_camposenventa_html.json`
- JSON raw watson: `data/scraping_batches/internal_batch_20260606_1129/captured/0003_www_watsonpropiedades_com_explora_propiedades.json`
- Batch report: `reports/scraping_autofix/batch_20260606_1129/batch_report.md`
