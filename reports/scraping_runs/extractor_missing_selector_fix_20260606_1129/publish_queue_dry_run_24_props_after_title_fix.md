# Publish queue dry-run — post Fix Issue E (titulos)

- Fecha: 2026-06-06
- Modo: **dry-run** (rollback — sin escritura en Neon)
- Script: `scripts/build_publish_queue.py --dry-run --ids-file ... --limit 30 --min-score 60`
- IDs file: `publish_queue_ids_24_props.csv` (24 staging_ids)
- Origen: batch `internal_batch_20260606_1129`

---

## Novedades vs simulacion anterior

| Item | Simulacion manual (anterior) | Dry-run real (este reporte) |
|---|---|---|
| Script ejecutado | NO (simulacion manual) | **SI** (script real con --ids-file) |
| --ids-file disponible | NO (no existia) | **SI** (agregado en FASE 4) |
| filas leidas | 24 | **24** |
| encoladas | 14 | **14** |
| ya en cola | 0 | **0** |
| skip_geocoding_pending | 10 | **10** |
| accion final | (no ejecutado) | **rollback** |

Resultados identicos a la simulacion anterior. El `--ids-file` funciona correctamente.

---

## Resultado del dry-run (output del script)

```
========================================================================
BUILD PUBLISH QUEUE
mode=dry-run
limit=30
min_score=60
allow_pending_geo=False
ids_file=reports\scraping_runs\extractor_missing_selector_fix_20260606_1129\publish_queue_ids_24_props.csv (24 IDs)
target=internal_db
------------------------------------------------------------------------
filas_leidas=24
encoladas=14
ya_en_cola=0
omitidas_por_motivo:
  skip_geocoding_pending: 10
priorities:
  1: 0
  2: 14
  3: 0
accion_final=rollback
========================================================================
```

---

## Detalle por prop — 24 leidas

### ENCOLADAS — 14 props (priority=2)

#### innoacafayate.com — 10 props

| staging_id | Titulo actual | Tipo | Op | Precio | Ciudad | Prov | Geo | Score | Resultado |
|---|---|---|---|---|---|---|---|---|---|
| 81037 | Depto en Salta sobre avenida Chile. | departamento | venta | 65.000 USD | Cafayate | Salta | skipped | 95 | ENCOLADA p2 |
| 81039 | Propiedad en calle Ex Colon. | terreno | venta | 75.000 USD | Cafayate | Salta | skipped | 95 | ENCOLADA p2 |
| 81040 | Lote Barrio Ribera 1. | terreno | venta | 50.000 USD | Cafayate | Salta | skipped | 95 | ENCOLADA p2 |
| 81043 | Lote en calle Chacabuco.- Cafayate. | terreno | venta | 57.000 USD | Cafayate | Salta | skipped | 95 | ENCOLADA p2 |
| 81051 | Deptos Guemes Sur. | departamento | alquiler | 600.000 ARS | Cafayate | Salta | skipped | 95 | ENCOLADA p2 |
| 81052 | Casa Lamadrid | casa | alquiler | 400.000 ARS | Cafayate | Salta | skipped | 95 | ENCOLADA p2 |
| 81045 | Lotes en calle Los Andes. | terreno | venta | NULL | Cafayate | Salta | skipped | 75 | ENCOLADA p2 |
| 81046 | Hotel Texas.- | hotel | venta | NULL | Cafayate | Salta | skipped | 75 | ENCOLADA p2 |
| 81049 | Local Calchaqui esq. Arnaldo Echart, Cafayate | local | alquiler | NULL | Cafayate | Salta | skipped | 75 | ENCOLADA p2 |
| 81050 | Depto Calchaqui esq. Arnaldo Echart, Cafayate | departamento | alquiler | NULL | Cafayate | Salta | skipped | 75 | ENCOLADA p2 |

#### camposdelapampa.com.ar — 4 props

| staging_id | Titulo ACTUAL (inaceptable) | Titulo NUEVO (pendiente UPDATE) | Geo | Score | Resultado |
|---|---|---|---|---|---|
| 81053 | **Ca266.Html** | Campo en venta en La Pampa | skipped | 75 | ENCOLADA p2 |
| 81054 | **Mo342.Html** | Campo en venta en La Pampa | skipped | 75 | ENCOLADA p2 |
| 81055 | **Mo340.Html** | Campo en venta en La Pampa | skipped | 75 | ENCOLADA p2 |
| 81056 | **Mi319.Html** | Campo en venta en La Pampa | skipped | 75 | ENCOLADA p2 |

**ATENCION:** Los 4 entran como ENCOLABLES pero sus titulos en staging siguen siendo filename-style.
El fix en el codigo (scraper + importer) aplica a **futuros imports**. Los 4 existentes
necesitan un UPDATE controlado (ver seccion abajo). **NO hacer commit de publish_queue hasta corregir titulos.**

---

### SALTADAS — 10 props

| staging_id | Titulo | Tipo | Geo | Motivo | Con --allow-pending-geo |
|---|---|---|---|---|---|
| 81036 | Haras La Querencia 800 Hectareas | terreno | pending | skip_geocoding_pending | pasaria (p2) |
| 81038 | Casa Pueblo Nuevo Mza. 21. | casa | pending | skip_geocoding_pending | pasaria (p2) |
| 81047 | Local calle Salta 329 | local | **failed** | skip_geocoding_pending | **NO pasa** |
| 81041 | Pueblo Nuevo Mza. 69 dos lotes. | terreno | pending | skip_geocoding_pending | pasaria (p3) |
| 81042 | Pueblo Nuevo Mza. 46. | terreno | pending | skip_geocoding_pending | pasaria (p3) |
| 81044 | Pueblo Nuevo Mza. 127. | terreno | pending | skip_geocoding_pending | pasaria (p3) |
| 81048 | Casa Vertientes 57, Cafayate | casa | **failed** | skip_geocoding_pending | **NO pasa** |
| 81057 | Casa en zona Centro. Excelente ubicacion. | casa | pending | skip_geocoding_pending | pasaria (p3) |
| 81058 | Casa de categoria en Quintas de Betbeder. | casa | pending | skip_geocoding_pending | pasaria (p3) |
| 81059 | Casa en esquina en zona Centro | casa | pending | skip_geocoding_pending | pasaria (p3) |

Nota: `skip_geocoding_pending` aplica a cualquier geocoding_status fuera del set {done, skipped},
incluyendo `failed`. Las 2 failed (81047, 81048) NO pasan ni con `--allow-pending-geo`.

---

## Estado del Fix Issue E post-FASE 5

### Lo que esta resuelto

| Componente | Estado |
|---|---|
| `_FILENAME_TITLE_RE` en scraper | **APLICADO** — `_is_useful_scraped_title()` rechaza Ca266.Html |
| `section.famie-benefits-area` en title_candidates | **APLICADO** — extrae texto real del CMS rural |
| `_FILENAME_TITLE_RE` en importer | **APLICADO** — safety net para futuros imports |
| `_fix_filename_titulo()` en importer | **APLICADO** — sintetiza desde tipo+op+provincia |
| py_compile scraper | **OK** |
| py_compile importer | **OK** |
| Tests 22/22 | **PASS** |
| `--ids-file` en build_publish_queue.py | **APLICADO + py_compile OK** |
| Dry-run real con --ids-file | **EJECUTADO — rollback correcto** |

### Lo que falta (requiere autorizacion separada)

| Tarea | Descripcion | Riesgo |
|---|---|---|
| **UPDATE titulos staging** | Corregir Ca266.Html→Campo en venta en La Pampa para los 4 staging_ids existentes | BAJO — UPDATE controlado, 4 filas exactas |
| **publish_queue commit** | Publicar las 14 encolables (despues de corregir titulos) | MEDIO — revisar titulos antes |
| **git commit** | Persistir los cambios de codigo en git | NINGUNO |

---

## SQL de UPDATE para los 4 titulos (requiere autorizacion)

```sql
UPDATE public.propiedades_staging
SET titulo = 'Campo en venta en La Pampa'
WHERE id IN (81053, 81054, 81055, 81056)
  AND titulo ~ '^[a-zA-Z]{2,4}[0-9]{3,6}\.html?$';
-- Guarda: el regex evita sobreescribir si el titulo ya fue corregido manualmente
-- Afectaria: 4 filas exactas (verificado en dry-run)
-- Resultado esperado: UPDATE 4
```

Los titulos del frontend quedan:
- 81053 (ca266): "Campo en venta en La Pampa"
- 81054 (mo342): "Campo en venta en La Pampa"
- 81055 (mo340): "Campo en venta en La Pampa"
- 81056 (mi319): "Campo en venta en La Pampa"

Alternativa si se quieren titulos mas especificos (requiere re-scrape con el nuevo scraper):
- 81053: "Departamento Loventue Muy buen acceso 6.000 ha Cria"
- 81054: "Limay Mahuida Oportunidad 15.000 ha Cria"
- 81055: "Departamento Chalileo Oportunidad 30.000 ha Cria"
- 81056: "Departamento Toay Bosque abierto 600 ha Ganaderia y Agricultura"

---

## Cambios de codigo aplicados en esta sesion

| Archivo | Cambio | Tipo |
|---|---|---|
| `scraper/scraper_propiedades.py` | `_FILENAME_TITLE_RE` regex constant | Fix global |
| `scraper/scraper_propiedades.py` | Rechazo en `_is_useful_scraped_title()` | Fix global |
| `scraper/scraper_propiedades.py` | `section.famie-benefits-area` en title_candidates | Fix por familia |
| `scripts/import_captured_props_to_neon.py` | `_FILENAME_TITLE_RE` + `_TIPO_LABEL_MAP` | Fix global |
| `scripts/import_captured_props_to_neon.py` | `_fix_filename_titulo()` funcion | Fix global |
| `scripts/import_captured_props_to_neon.py` | Llamada en `build_raw_candidate()` post-provincia | Fix global |
| `scripts/build_publish_queue.py` | `fetch_staging_rows()` con ids opcional | Feature |
| `scripts/build_publish_queue.py` | `--ids-file` argument parser | Feature |
| `scripts/build_publish_queue.py` | Carga CSV + log en print block | Feature |
| `scripts/build_publish_queue.py` | `ids=target_ids` en llamada | Feature |

---

## Seguridad

| Verificacion | Estado |
|---|---|
| publish_queue con commit | NO — dry-run rollback |
| propiedades_staging modificado | NO — dry-run rollback |
| propiedades_raw modificado | NO |
| Supabase tocado | NO |
| frontend tocado | NO |
| .env modificado | NO |
| git commit | NO |
| git push | NO |
| datos historicos procesados | NO — ids-file aísla exactamente los 24 IDs |
| staging_ids fuera del batch evaluados | **0** — garantizado por ids-file |

---

*Generado al finalizar FASE 5 del Fix Issue E · sesion 2026-06-06*
