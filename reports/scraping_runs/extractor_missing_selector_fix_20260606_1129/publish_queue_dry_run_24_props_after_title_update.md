# Publish queue dry-run — post UPDATE títulos (estado final)

- Fecha: 2026-06-06
- Modo: **dry-run** (rollback — sin escritura en Neon)
- Script: `scripts/build_publish_queue.py --dry-run --ids-file ... --limit 30 --min-score 60`
- IDs file: `publish_queue_ids_24_props.csv` (24 staging_ids)
- Origen: batch `internal_batch_20260606_1129`

---

## Contexto: qué cambió respecto al dry-run anterior

| Cambio | Detalle |
|---|---|
| **Fix Issue E — scraper** | `_FILENAME_TITLE_RE` rechaza "Ca266.Html" en `_is_useful_scraped_title()` |
| **Fix Issue E — scraper** | `section.famie-benefits-area` como fuente de título en CMS rural |
| **Fix Issue E — importer** | `_fix_filename_titulo()` safety net para futuros imports |
| **UPDATE staging (FASE 2)** | 4 filas corregidas: Ca266.Html → "Campo en venta en La Pampa" |
| **--ids-file en build_publish_queue.py** | Dry-run ahora es real (script ejecutado, no simulacion) |

---

## Resultado del dry-run

```
========================================================================
BUILD PUBLISH QUEUE
mode=dry-run
limit=30
min_score=60
allow_pending_geo=False
ids_file=... (24 IDs)
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

## Detalle por prop — 24 leídas

### ENCOLABLES — 14 props (priority=2) ← SIN CAMBIO EN CANTIDAD

#### innoacafayate.com — 10 props

| staging_id | Titulo | Tipo | Op | Precio | Ciudad | Prov | Geo | Score | Resultado |
|---|---|---|---|---|---|---|---|---|---|
| 81037 | Depto en Salta sobre avenida Chile. | departamento | venta | 65.000 USD | Cafayate | Salta | skipped | 95 | ENCOLABLE p2 |
| 81039 | Propiedad en calle Ex Colon. | terreno | venta | 75.000 USD | Cafayate | Salta | skipped | 95 | ENCOLABLE p2 |
| 81040 | Lote Barrio Ribera 1. | terreno | venta | 50.000 USD | Cafayate | Salta | skipped | 95 | ENCOLABLE p2 |
| 81043 | Lote en calle Chacabuco.- Cafayate. | terreno | venta | 57.000 USD | Cafayate | Salta | skipped | 95 | ENCOLABLE p2 |
| 81051 | Deptos Guemes Sur. | departamento | alquiler | 600.000 ARS | Cafayate | Salta | skipped | 95 | ENCOLABLE p2 |
| 81052 | Casa Lamadrid | casa | alquiler | 400.000 ARS | Cafayate | Salta | skipped | 95 | ENCOLABLE p2 |
| 81045 | Lotes en calle Los Andes. | terreno | venta | NULL | Cafayate | Salta | skipped | 75 | ENCOLABLE p2 |
| 81046 | Hotel Texas.- | hotel | venta | NULL | Cafayate | Salta | skipped | 75 | ENCOLABLE p2 |
| 81049 | Local Calchaqui esq. Arnaldo Echart, Cafayate | local | alquiler | NULL | Cafayate | Salta | skipped | 75 | ENCOLABLE p2 |
| 81050 | Depto Calchaqui esq. Arnaldo Echart, Cafayate | departamento | alquiler | NULL | Cafayate | Salta | skipped | 75 | ENCOLABLE p2 |

#### camposdelapampa.com.ar — 4 props ✅ TITULOS CORREGIDOS

| staging_id | Titulo ANTES | Titulo AHORA | Geo | Score | Resultado |
|---|---|---|---|---|---|
| 81053 | ~~Ca266.Html~~ | **Campo en venta en La Pampa** | skipped | 75 | ENCOLABLE p2 |
| 81054 | ~~Mo342.Html~~ | **Campo en venta en La Pampa** | skipped | 75 | ENCOLABLE p2 |
| 81055 | ~~Mo340.Html~~ | **Campo en venta en La Pampa** | skipped | 75 | ENCOLABLE p2 |
| 81056 | ~~Mi319.Html~~ | **Campo en venta en La Pampa** | skipped | 75 | ENCOLABLE p2 |

Las 4 props de camposdelapampa ahora tienen titulos válidos para el frontend.
Ya no hay ningun titulo inaceptable entre las 14 encolables.

---

### SALTADAS — 10 props

| staging_id | Titulo | Tipo | Geo | Score | Motivo | Con --allow-pending-geo |
|---|---|---|---|---|---|---|
| 81036 | Haras La Querencia 800 Hectareas | terreno | pending | 100 | skip_geocoding_pending | pasaria (p2) |
| 81038 | Casa Pueblo Nuevo Mza. 21. | casa | pending | 100 | skip_geocoding_pending | pasaria (p2) |
| 81047 | Local calle Salta 329 | local | **failed** | 100 | skip_geocoding_pending | **NO pasa** |
| 81041 | Pueblo Nuevo Mza. 69 dos lotes. | terreno | pending | 80 | skip_geocoding_pending | pasaria (p3) |
| 81042 | Pueblo Nuevo Mza. 46. | terreno | pending | 80 | skip_geocoding_pending | pasaria (p3) |
| 81044 | Pueblo Nuevo Mza. 127. | terreno | pending | 80 | skip_geocoding_pending | pasaria (p3) |
| 81048 | Casa Vertientes 57, Cafayate | casa | **failed** | 80 | skip_geocoding_pending | **NO pasa** |
| 81057 | Casa en zona Centro. Excelente ubicacion. | casa | pending | 65 | skip_geocoding_pending | pasaria (p3) |
| 81058 | Casa de categoria en Quintas de Betbeder... | casa | pending | 65 | skip_geocoding_pending | pasaria (p3) |
| 81059 | Casa en esquina en zona Centro | casa | pending | 65 | skip_geocoding_pending | pasaria (p3) |

**El unico freno para las 10 es geocoding_status.**
Los 2 failed (81047, 81048) son los unicos que no pasarian ni con `--allow-pending-geo`.

---

## Calidad de las 14 encolables — estado actual

| Grupo | Props | Titulo valido | Coordenadas | Ciudad | Precio | Estado |
|---|---|---|---|---|---|---|
| inno score=95 con precio | 6 | SI | NO (geo=skipped) | Cafayate/Salta | SI | ACEPTABLE — sin mapa |
| inno score=75 sin precio | 4 | SI | NO (geo=skipped) | Cafayate/Salta | NO | DEBIL — sin precio ni mapa |
| camposdelapampa | 4 | **SI (corregido)** | NO (geo=skipped) | NULL/La Pampa | NO | MINIMO — sin ciudad/precio/mapa |

Las camposdelapampa siguen sin ciudad, precio ni coordenadas. El titulo ya no es un bloqueante,
pero la ficha en el frontend seria muy escueta:
- Titulo: "Campo en venta en La Pampa" ✅
- Precio: sin dato ⚠️
- Ciudad: sin dato ⚠️
- Mapa: sin coordenadas ⚠️

---

## Problemas restantes para publicacion optima

| Problema | Props afectadas | Solución posible |
|---|---|---|
| geocoding_status=pending | 81036, 81038, 81041, 81042, 81044, 81057-81059 (8 props) | Reintentar con --ids-file cuando se autorice |
| geocoding_status=failed | 81047, 81048 (2 props) | Resetear a pending + reintentar con Google Maps API |
| precio=NULL | 81041-81046, 81048-81050, 81053-81059 (14 props) | No extraible del HTML de estos dominios |
| ciudad=NULL | 81053-81056 (camposdelapampa, 4 props) | Requiere dato manual o scrape mejor |
| Ninguna prop con priority=1 | todas 24 | Requiere geo=done + precio + score>=90 |

---

## ¿Conviene hacer publish_queue commit ahora?

**Recomendacion: NO todavia.**

Razones:
1. Las 14 encolables entrarían con priority=2 — ninguna en priority=1 (sin coords validadas)
2. Las 4 de camposdelapampa tienen titulo correcto pero sin ciudad ni precio — ficha muy escueta
3. Los 8 con geo=pending podrían mejorar a done con geocoding → subir de p2 a p1
4. Las 2 failed (81047, 81048) quedan permanentemente bloqueadas hasta resetear geocoding_status

**Orden recomendado antes del commit:**
1. Decidir si publicar las 10 de innoacafayate (geo=skipped, titulo ok, algunas con precio)
2. Decidir si publicar las 4 de camposdelapampa (sin ciudad/precio, solo provincia)
3. Resolver geocoding para los 8 pending (Nominatim ya falló en 2 de ellos — evaluar Google Maps)
4. Hacer commit solo de las props que tengan calidad suficiente (via --ids-file selectivo)

---

## Verificacion de seguridad post-FASE 4

| Verificacion | Estado |
|---|---|
| publish_queue commit ejecutado | NO — dry-run rollback |
| propiedades_staging modificado (este dry-run) | NO — rollback |
| Supabase tocado | NO |
| publish_to_supabase.py ejecutado | NO |
| frontend tocado | NO |
| geocoding ejecutado | NO |
| .env modificado | NO |
| git commit | NO |
| git push | NO |
| staging_ids fuera del batch procesados | NO — ids-file garantiza aislamiento |

---

## Resumen de cambios aplicados en esta sesion completa

| Que | Resultado |
|---|---|
| Fix Issue E — scraper (3 edits) | Listo — no se puede deshacer sin git |
| Fix Issue E — importer (3 edits) | Listo — aplica a futuros imports |
| --ids-file en build_publish_queue.py | Listo — backward compatible |
| UPDATE titulos staging 4 props | **Persistido en Neon** |
| publish_queue commit | Pendiente autorizacion |
| git commit de codigo | Pendiente autorizacion |

---

*Generado al finalizar FASE 4 del UPDATE controlado de titulos · sesion 2026-06-06*
