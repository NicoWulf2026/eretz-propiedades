# Inventario de capturas — Bloque 2: extractor_missing_selector

- Fecha análisis: 2026-06-07
- Batch original: `block2_extractor_missing_selector_20260607`
- Batch Fix H (luciafrolik + escuza): `block2_title_fix_rerun_20260607_v2`
- Total propiedades: **59**
- Modo: **captura local ONLY — sin escritura a Neon ni Supabase**

---

## 1. Resumen ejecutivo

| Métrica | Valor |
|---|---|
| Total capturadas | **59** |
| Sin problemas de importación | **54** |
| Hard exclude (no son propiedades) | **4** — imágenes .jfif capturadas como propiedades |
| Flag para revisión | **1** — posible página de categoría (tonyzorrilla) |
| Duplicados técnicos (mismo inmob + URL) | **0** |
| Duplicados por hash | **0** |

---

## 2. Por dominio

| Dominio | inmob_id | Props | Importables | Issues |
|---|---|---|---|---|
| tonyzorrilla.com.ar | 5853 | 30 | **29** | 1 posible listing page |
| dilellopropiedades.com | 5916 | 15 | **11** | 4 .jfif image URLs (hard exclude) |
| luciafrolik.com.ar | 5850 | 12 | **12** | 0 — clean ✅ |
| inmobiliariaescuza.com | 5848 | 2 | **2** | 0 — clean ✅ |
| **TOTAL** | | **59** | **54** | |

---

## 3. Análisis por dimensión

### Operación
| Operación | Props |
|---|---|
| venta | 53 |
| alquiler | 6 |

### Tipo de propiedad
| Tipo | Props |
|---|---|
| casa | 44 |
| departamento | 9 |
| terreno | 5 |
| local | 1 |

### Precio
| Estado | Props |
|---|---|
| Con precio | 19 (32%) |
| Sin precio ("consultar") | 40 (68%) |

| Dominio | Con precio / total | Rango |
|---|---|---|
| tonyzorrilla.com.ar | 1/30 | 50,000 USD |
| dilellopropiedades.com | 9/15 | 22,500 – 160,000 USD |
| luciafrolik.com.ar | 8/12 | 115,000 – 480,000 USD |
| inmobiliariaescuza.com | 1/2 | 58,000 USD |

Sin precio = normal en sitios de inmobiliarias que no publican precio online. No es un bug.

### Moneda
- USD: 18 props con precio
- ARS: 1 prop con precio

### Ubicación

| Estado | Props | Dominios |
|---|---|---|
| Con ciudad + provincia | 14 | luciafrolik (12) + escuza (2): Tandil, Buenos Aires |
| Sin ciudad | 45 | tonyzorrilla (30) + dilello (15) |

La ciudad no aparece en el campo estructurado para tonyzorrilla y dilello porque:
- **tonyzorrilla**: Rawson / Playa Unión (Chubut) — ciudad presente en el **título** pero no en campo `ciudad`
- **dilello**: Pergamino (Buenos Aires) — ciudad presente en el **título** (extraído de slug) pero no en campo `ciudad`

Fix A (hostname) no aplica: estos hostnames no revelan ciudad directamente. La ciudad se recuperará en geocoding a partir del título.

### Imágenes

| Dominio | Promedio | Mín | Máx |
|---|---|---|---|
| tonyzorrilla.com.ar | 19.7 | 12 | 60 |
| luciafrolik.com.ar | 7.5 | 2 | 13 |
| inmobiliariaescuza.com | 11.5 | 9 | 14 |
| dilellopropiedades.com | 4.1 | 0 | 12 |

4 props sin imágenes → todas son las 4 .jfif hard-exclude de dilello.

### Score de calidad

| Dominio | Promedio | Mín | Máx |
|---|---|---|---|
| tonyzorrilla.com.ar | 60.2 | 50 | 75 |
| dilellopropiedades.com | 60.3 | 30 | 75 |
| luciafrolik.com.ar | 70.0 | 60 | 75 |
| inmobiliariaescuza.com | 72.5 | 65 | 80 |

Props con score < 60: **6**
- 4 dilello (score=30) → .jfif image URLs — hard exclude
- 1 dilello (score=50) → "Locacion Dilello" — borderline
- 1 tonyzorrilla (score=50) → posible listing page

---

## 4. Issues detectados

### 🔴 HARD EXCLUDE — 4 props (URLs de imagen .jfif)

Cuatro props de `dilellopropiedades.com` tienen como URL una **imagen thumbnail** en lugar de una página de propiedad. El fix de `_looks_like_real_property_url()` detectó correctamente el slug del nombre de archivo como un patrón de propiedad, pero la URL en sí es una imagen `.jfif`.

| idx | URL | Título |
|---|---|---|
| (dilello) | `.../img/properties/departamento-en-venta-en-pergamino-merced-al-300-dilello-01295_thumb.jfif` | Departamento En Venta En Pergamino Merced Al 300 Dilello 01295 Thumb.Jfif |
| (dilello) | `.../img/properties/lotes-en-venta-en-pergamino-club-del-lago-dilello-19256_thumb.jfif` | Lotes En Venta En Pergamino Club Del Lago Dilello 19256 Thumb.Jfif |
| (dilello) | `.../img/properties/casa-en-venta-en-pergamino-san-luis-900-a-reciclar-dilello-02069_thumb.jfif` | Casa En Venta En Pergamino San Luis 900 A Reciclar Dilello 02069 Thumb.Jfif |
| (dilello) | `.../img/properties/casa-en-venta-en-pergamino-diego-de-la-fuente-1130-dilello-02275_thumb.jfif` | Casa En Venta En Pergamino Diego De La Fuente Dilello 02275 Thumb.Jfif |

**Características**: score=30, 0 imágenes, sin dirección, URL contiene `/img/properties/`

**Impacto**: Las propiedades reales SÍ existen y ESTÁN en el batch (con score=75, imágenes, dirección). Estas 4 son thumbnails duplicados falsos del detector de URLs.

**Acción recomendada**: Fix global en `_looks_like_real_property_url()` para excluir URLs que apunten a archivos de imagen por extensión o por estar bajo `/img/` path. No autorizado en esta sesión — flagear para Bloque 3.

---

### 🟡 FLAG PARA REVISIÓN — 1 prop (posible página de categoría, tonyzorrilla)

| Campo | Valor |
|---|---|
| URL | `http://tonyzorrilla.com.ar/terrenos-a-la-venta-rawson-playa-union/` |
| Título | `Terrenos a la venta \| Rawson & Playa Unión` |
| Score | 50 |
| Imágenes | 12 |
| Dirección | Amancay Nº 265 |

La URL y el título sugieren una página de categoría ("Terrenos a la venta"). Sin embargo, tiene 12 imágenes y una dirección específica ("Amancay Nº 265"), lo que podría indicar que es una propiedad individual con URL atípica.

**Decisión**: importar y dejar que el pipeline de validación decida según score_calidad. Si score < min_score en staging validation, quedará en raw sin pasar a staging.

---

### 🟡 DIRECCIÓN CONTAMINADA — 3 props (dilello)

| Dirección capturada | Título |
|---|---|
| `C.M.P. Consultas Online 2477` | Departamentos En Alquiler En Pergamino Locacion Dilello |
| `C.M.P. Consultas Online 2477` | Terreno En Venta En Pergamino Ayres De Amanecer Dilello |
| `C.M.P. Consultas Online 2477` | Lotes En Venta En Pergamino Club Del Lago Dilello |

"C.M.P. Consultas Online 2477" es información de contacto capturada en el campo `direccion`. Estas props existen realmente (tienen imágenes, score ≥ 50) pero su dirección estructurada es inútil. Geocoding fallará en campo dirección.

**Acción**: importar. El geocoding puede usar ciudad (si se recupera) sin necesitar dirección.

---

### ℹ️ INFORMACIONALES (no bloquean import)

| Flag | Props | Detalle |
|---|---|---|
| missing_ciudad | 45 | tonyzorrilla (30) + dilello (15) — ciudad en título, no en campo |
| missing_precio | 40 | Normal — sitios con "consultar precio" |
| low_score (50) | 2 | Borderline — ver issues anteriores |

---

## 5. Duplicados

| Tipo | Resultado |
|---|---|
| Duplicado técnico exacto (mismo inmob_id + URL) | **0** |
| Duplicado por hash_dedup | **0** |
| Misma dirección inter-agencia | No aplica — regla de negocio permite esto |
| Misma dirección misma agencia (distinto URL) | Sin duplicados detectados |

No hay duplicados técnicos en el batch.

---

## 6. Regla de duplicados aplicada

**Regla vigente**: bloquear solo duplicado técnico exacto (mismo `inmobiliaria_id` + misma `url` o mismo `hash_dedup`).

- NO se eliminan props con misma dirección
- NO se eliminan props de distintas agencias aunque representen la misma propiedad
- NO se eliminan props con mismo título o precio
- Las 4 .jfif son hard-exclude por URL inválida, no por "duplicado"

---

## 7. Resumen de importabilidad

| Categoría | Props | Importable |
|---|---|---|
| Limpias (sin issues técnicos) | 14 luciafrolik + escuza | ✅ SÍ |
| OK con caveats (missing ciudad/precio) | 29 tonyzorrilla + 10 dilello | ✅ SÍ |
| Flag revisión (listing page?) | 1 tonyzorrilla | ⚠️ Probablemente sí |
| Dirección contaminada | 3 dilello | ✅ SÍ (sin dirección útil) |
| Hard exclude (imagen .jfif) | 4 dilello | ❌ NO |
| **TOTAL IMPORTABLES** | **54** | |
| **TOTAL HARD EXCLUDE** | **4** | |

---

## 8. Nota sobre dilello — posible fix adicional

Los 4 `.jfif` son falsos positivos del detector de URLs. Las propiedades reales existen en el batch (con score=75, imágenes, dirección correcta). Esto sugiere que `_looks_like_real_property_url()` capturó correctamente las URLs de imagen porque el path del archivo de imagen usa el mismo formato de slug que las páginas de propiedad.

**Fix sugerido para Bloque 3**: excluir de `_looks_like_real_property_url()` las URLs con extensiones de imagen (`.jpg`, `.jfif`, `.png`, `.webp`, etc.) o las que estén bajo paths `/img/` o `/images/`. Fix global — no por dominio.

---

## 9. Archivos

| Archivo | Descripción |
|---|---|
| `captured_manifest.csv` | Una fila por propiedad con campos clave y flags |
| `captured_inventory.md` | Este reporte |

---

*Inventario: 2026-06-07 · batch block2_extractor_missing_selector + block2_title_fix_rerun_20260607_v2 · rama fix/scraping-diagnostics-batch · commit f0e6c21c*
