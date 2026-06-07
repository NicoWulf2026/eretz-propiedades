# Bloque 2 — Plan: extractor_missing_selector global

- Fecha plan: 2026-06-07
- Estado: **PENDIENTE AUTORIZACIÓN** — no ejecutar
- Objetivo: scraping controlado de dominios donde el fix de `_looks_like_real_property_url()` ya permite capturar propiedades + validar impacto real
- Estimado de props recuperables: **60–80+**

---

## Contexto

El fix de `extractor_missing_selector` ya está implementado y commiteado en `69cac0db`.

La función `_looks_like_real_property_url()` recibió 3 nuevos patrones de URL:

| Patrón | Regex | Dominios cubiertos |
|---|---|---|
| CMS argentino `{tipo}s-en-{op}-en-{ciudad}-{id}.html` | `(^|/)(?:casa\|depto\|...).-en-(?:venta\|alquiler)-...` | inmobiliariaescuza.com, luciafrolik.com.ar, dilellopropiedades.com |
| WordPress custom slug `{tipo}-(venta\|alquiler)-{dir}-{ciudad}/` | `(^|/)(?:casa\|...).-(?:venta\|alquiler\|alq)[-_][^/?#]{15,}...` | tonyzorrilla.com.ar |
| Armesto CMS `/venta-{tipo}-{loc}-V{id}` | `(^|/)(?:venta\|alquiler)[-_](?:casa\|...).*[-_][A-Z]?\d{3,}...` | armestoinmobiliaria.com.ar |

**Estos patrones son retrocompatibles** — no rompen nada existente.

---

## Lista de dominios candidatos

### Grupo 1 — Fix validado, resultado confirmado (NO necesitan re-test de código, sí necesitan batch de captura)

| inmob_id | Nombre | Dominio | URL listado | Props confirmadas | Evidencia |
|---|---|---|---|---|---|
| 5853 | Tony Zorrilla Inmobiliaria | tonyzorrilla.com.ar | `http://www.tonyzorrilla.com.ar/ventas` | **30** | before_after.md — test 2026-06-05 |
| 5916 | Dilello Propiedades Pergamino | dilellopropiedades.com | `https://www.dilellopropiedades.com/alquileres` | **8** | before_after.md — test 2026-06-05 |

**Estado**: fix correcto, captura exitosa. Bloque 2 = importar estas props que ya sabemos que funcionan.

---

### Grupo 2 — Fix correcto pero test falló por timeout/down (necesitan retry con timeout mayor)

| inmob_id | Nombre | Dominio | URL listado | Props estimadas | Problema previo |
|---|---|---|---|---|---|
| 6391 | Silvia Armesto y Asociados | armestoinmobiliaria.com.ar | `http://www.armestoinmobiliaria.com.ar/venta-de-propiedades?orden=codigo_asc` | ~4 (2 páginas × 2/pág) | Timeout en test — fix correcto según análisis de URL |
| 5850 | Estudio Inmobiliario Lucia Frolik | luciafrolik.com.ar | `http://www.luciafrolik.com.ar/propiedades.php` | 12+ | Timeout en test — mismo CMS que escuza |
| 5848 | Inmobiliaria Ignacio Escuza | inmobiliariaescuza.com | `http://www.inmobiliariaescuza.com/propiedades.php` | 12+ | Site down en 2026-06-05; verificar estado actual |

**Acción**: retry con `--timeout-seconds 350` y `--workers 1`.

---

### Grupo 3 — No fixables con scraping estático (fuera del scope de Bloque 2)

| Dominio | Causa | Acción futura |
|---|---|---|
| maccaroni.com.ar | JS-rendered (Vue/React: `href="${ficha.amigable}"`) | Bloque Playwright pilot |
| benvenutoyzanni.com.ar | Mismo CMS que maccaroni | Bloque Playwright pilot |
| lorussoinmobiliaria.com | Google Sites, sin páginas de detalle individuales | Descartar |
| falcigliapropiedades.com.ar | Redirige a `/admin/login`, sin frontend público | Descartar |
| inmobiliariamartinezquiles.com.ar | `onclick="verFicha(id)"` — sin `<a href>` de detalle | Inspección profunda JS |
| krool.com.ar | `operacion=-1` inválido; posible contenido AJAX | Retry con operacion=1 primero |

---

## Evidencia del error original

Todos los dominios del Grupo 1 y 2 fallaban con:
```
error_family: no_property_links
error_subfamily: extractor_missing_selector (o sin_links_detalle_estaticos)
```

El scraper encontraba la página de listado (HTTP 200) pero `_looks_like_real_property_url()` rechazaba todos los links encontrados porque sus patrones de URL no estaban en `detail_patterns`. Con el fix, los mismos links son ahora reconocidos.

---

## Potencial de recuperación

| Dominio | Props (p. 1) | Páginas est. | Props totales est. |
|---|---|---|---|
| tonyzorrilla.com.ar | 30 (confirmado) | 3+ | **90+** |
| dilellopropiedades.com | 8 (confirmado) | 2+ | **15+** |
| luciafrolik.com.ar | 12 | 2+ | **25+** |
| inmobiliariaescuza.com | 12 | 2+ | **25+** |
| armestoinmobiliaria.com.ar | ~2 per_page | 2 páginas | **~4** |
| **Total** | | | **~160+ props** (estimado optimista) |

Estimado conservador: **60–80 props** (asumiendo paginación limitada y prop 2 sin más páginas).

---

## Prioridad

| Dominio | Prioridad | Razón |
|---|---|---|
| tonyzorrilla.com.ar | **ALTA** | 30 props confirmadas, cero riesgo de timeout |
| dilellopropiedades.com | **ALTA** | 8 props confirmadas |
| luciafrolik.com.ar | **MEDIA** | 12 estimadas, mismo CMS que escuza — fix validado indirectamente |
| inmobiliariaescuza.com | **MEDIA** | Mismo fix que dilello — verificar que el sitio volvió online |
| armestoinmobiliaria.com.ar | **BAJA** | ~4 props, lento, timeout previo |

---

## Estrategia de fix — resumen

No hay más código que escribir. El fix ya está en producción.

**Bloque 2 = captura + import, no modificación de scraper.**

Flujo:
1. Crear CSV con los 5 dominios (Grupo 1 + Grupo 2)
2. Correr `run_internal_scraping_batch.py` — NO DB write
3. Revisar los JSON capturados
4. Correr `import_captured_props_to_neon.py` — importar a raw
5. Correr `validate_raw_properties.py` — validar a staging
6. Revisar staging antes de geocoding o publish_queue

---

## Comando de batch controlado

### PASO 1 — Crear input CSV

```csv
idx,inmobiliaria_id,inmobiliaria_nombre,url
1,5853,Tony Zorrilla Inmobiliaria,http://www.tonyzorrilla.com.ar/ventas
2,5916,Dilello Propiedades Pergamino,https://www.dilellopropiedades.com/alquileres
3,6391,Silvia Armesto y Asociados,http://www.armestoinmobiliaria.com.ar/venta-de-propiedades?orden=codigo_asc
4,5850,Estudio Inmobiliario Lucia Frolik,http://www.luciafrolik.com.ar/propiedades.php
5,5848,Inmobiliaria Ignacio Escuza,http://www.inmobiliariaescuza.com/propiedades.php
```

Guardar en: `data/block2_extractor_missing_selector_5_domains.csv`

### PASO 2 — Ejecutar batch (NO DB)

```bash
USE_INTERNAL_DB=true python scripts/run_internal_scraping_batch.py \
  --input data/block2_extractor_missing_selector_5_domains.csv \
  --workers 1 \
  --timeout-seconds 350 \
  --allow-static-detail \
  --out-dir data/scraping_batches/block2_extractor_missing_selector_20260607/
```

Flags:
- `--workers 1`: secuencial, sin race conditions
- `--timeout-seconds 350`: cubre los dominios lentos (armestoinmobiliaria tuvo timeout con valores menores)
- `--allow-static-detail`: permite `strategy_static_html_detail` para páginas de detalle estáticas
- Sin `--commit`: NO escribe a DB

**Duración estimada**: 20-40 minutos (5 dominios × ~5 min promedio con timeout largo)

### PASO 3 — Revisar captura (dry-run manual)

```bash
# Ver cuántas props capturó cada dominio
for f in data/scraping_batches/block2_extractor_missing_selector_20260607/captured/*.json; do
    python -c "import json; d=json.load(open('$f', encoding='utf-8')); print(d.get('inmobiliaria_nombre'), d.get('props_count'))"
done
```

### PASO 4 — Import a Neon (requiere autorización separada)

```bash
USE_INTERNAL_DB=true python scripts/import_captured_props_to_neon.py \
  --captured-dir data/scraping_batches/block2_extractor_missing_selector_20260607/captured/ \
  --dry-run
# Revisar dry-run antes de --commit
```

### PASO 5 — Validate (requiere autorización separada)

```bash
USE_INTERNAL_DB=true python scripts/validate_raw_properties.py \
  --ids-file <ids_generados_en_import> \
  --dry-run
```

---

## Riesgos

| Riesgo | Nivel | Mitigación |
|---|---|---|
| inmobiliariaescuza.com sigue down | BAJO | Si HTTP error, el scraper lo skippea automáticamente |
| armestoinmobiliaria timeout incluso con 350s | BAJO | Skippea ese dominio, los otros 4 siguen |
| Falsos positivos en `_looks_like_real_property_url()` | MUY BAJO | Patrones son conservadores; validados con 8 test cases |
| Props duplicadas en Neon (import doble) | CERO | Hash dedup en import_captured_props_to_neon.py previene duplicados |
| Regresiones en otros dominios | CERO | Fix es aditivo — solo agrega patrones, no modifica lógica existente |
| Scraping viola restricciones (Zonaprop/Argenprop) | CERO | Todos los dominios son inmobiliarias propias, ninguna es portal externo |

---

## ETA estimada

| Paso | Tiempo | Dependencia |
|---|---|---|
| Crear CSV + preparar | 2 min | — |
| Batch scraping (5 dominios, workers=1) | 20-40 min | Conexión + velocidad sitios |
| Revisión captura | 5 min | Manual |
| Import dry-run | 2 min | Autorización |
| Import commit | 2 min | Autorización |
| Validate dry-run | 2 min | Autorización |
| Validate commit | 2 min | Autorización |
| **Total mínimo (solo batch + revisión)** | **~30 min** | |
| **Total completo (hasta staging)** | **~50 min** | Requiere 2 autorizaciones adicionales |

---

## Decisiones que requieren autorización antes de ejecutar

1. **Autorización batch scraping** (NO DB): crear CSV + correr `run_internal_scraping_batch.py --no-commit`
2. **Autorización import a Neon**: después de revisar la captura
3. **Autorización validate**: después del import
4. **Publicación**: bloque separado, igual al Bloque 1

---

## Contexto adicional: universo más amplio (Bloque 3+)

El Bloque 2 cubre los 5 dominios con `extractor_missing_selector` confirmados. Hay un universo más amplio:

| Categoría | Dominios | Descripción |
|---|---|---|
| `no_property_links` total | ~80 | Candidatos en CSV (`no_property_links_candidates.csv`) |
| `php_listing` | 36 | PHP con listado pero sin links de detalle reconocidos |
| `clean_path` | 17 | URLs limpias sin patrón reconocido |
| `php_cms_params` | 14 | CMS con parámetros PHP custom |
| `html_static` | 13 | HTML estático sin links de detalle |

Estos 80 dominios son el objetivo de un Bloque 3, con estrategia diferente (análisis por familia CMS, posibles ajustes a `_extract_generic_property_links`, o pilotos de Playwright).

---

*Plan generado: 2026-06-07 · PENDIENTE AUTORIZACIÓN · No ejecutar*
