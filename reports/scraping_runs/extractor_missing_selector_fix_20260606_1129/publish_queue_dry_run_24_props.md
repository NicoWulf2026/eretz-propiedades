# Publish queue dry-run — 24 propiedades nuevas en staging

- Fecha: 2026-06-06
- Modo: simulacion manual (equivalente a dry-run del script)
- Origen: propiedades_staging del batch `internal_batch_20260606_1129`
- Script analizado: `scripts/build_publish_queue.py`
- Parametros simulados: `--min-score 60` (default) / sin `--allow-pending-geo`

---

## Por que NO se ejecuto el script directamente

`build_publish_queue.py` **no tiene `--ids-file` ni filtro de source/fecha.**

`STAGING_SELECT_SQL` lee todas las filas con `status='staging'` ordenadas por `validation_score DESC, id ASC`:

| Estadistica de staging total | Valor |
|---|---|
| Filas con status='staging' | **76.447** |
| Filas con score=100 | **44.740** |
| Filas con score>=95 | **44.750** |

Con `--limit 30`, el script leeria los 30 staging_ids de mayor score y menor id historicos — nuestras 24 props nuevas (id > 81036) quedarian en posiciones > 44.737 dentro del score=100, muy por fuera del limite. **El script no tocaria nuestras 24 props.**

Conclusion: se simulo la logica `queue_skip_reason()` y `compute_priority()` directamente sobre los datos reales de las 24 props. El resultado es identico a un dry-run del script con un hipotetico `--ids-file`.

---

## Resultado de la simulacion

| Metrica | Valor |
|---|---|
| Props evaluadas | **24** |
| SERIAN ENCOLADAS (default) | **14** |
| SERIAN SALTADAS (default) | **10** |
| Ya en publish_queue | **0** (nunca estuvieron) |
| Prioridad 1 (alta) | **0** |
| Prioridad 2 (media) | **14** |
| Prioridad 3 (baja) | **0** |

---

## Detalle por prop — con resultado y motivo

### ENCOLADAS — 14 props (priority 2)

#### innoacafayate.com — 10 props (geocoding_status=skipped)

| staging_id | Score | Op | Tipo | Precio | Ciudad | Prov | Geo | Priority |
|---|---|---|---|---|---|---|---|---|
| 81037 | 95 | venta | departamento | 65.000 USD | Cafayate | Salta | skipped | **p2** |
| 81039 | 95 | venta | terreno | 75.000 USD | Cafayate | Salta | skipped | **p2** |
| 81040 | 95 | venta | terreno | 50.000 USD | Cafayate | Salta | skipped | **p2** |
| 81043 | 95 | venta | terreno | 57.000 USD | Cafayate | Salta | skipped | **p2** |
| 81051 | 95 | alquiler | departamento | 600.000 ARS | Cafayate | Salta | skipped | **p2** |
| 81052 | 95 | alquiler | casa | 400.000 ARS | Cafayate | Salta | skipped | **p2** |
| 81045 | 75 | venta | terreno | NULL | Cafayate | Salta | skipped | **p2** |
| 81046 | 75 | venta | hotel | NULL | Cafayate | Salta | skipped | **p2** |
| 81049 | 75 | alquiler | local | NULL | Cafayate | Salta | skipped | **p2** |
| 81050 | 75 | alquiler | departamento | NULL | Cafayate | Salta | skipped | **p2** |

Motivo priority=2: `validation_score >= 70` (score 95 o 75).
Ninguna llega a priority=1 porque requiere `geocoding_status=done` + precio + score>=90.

#### camposdelapampa.com.ar — 4 props (geocoding_status=skipped)

| staging_id | Score | Op | Tipo | Precio | Ciudad | Prov | Geo | Priority |
|---|---|---|---|---|---|---|---|---|
| 81053 | 75 | venta | campo | NULL | NULL | La Pampa | skipped | **p2** |
| 81054 | 75 | venta | campo | NULL | NULL | La Pampa | skipped | **p2** |
| 81055 | 75 | venta | campo | NULL | NULL | La Pampa | skipped | **p2** |
| 81056 | 75 | venta | campo | NULL | NULL | La Pampa | skipped | **p2** |

**Problema critico de calidad:** titulos scrapeados desde CMS short-ID:
- `Ca266.Html` / `Mo342.Html` / `Mo340.Html` / `Mi319.Html`
Estos titulos son completamente inaceptables para publicacion en frontend.

---

### SALTADAS — 10 props

| staging_id | Score | Tipo | Geo | Motivo skip | Con --allow-pending-geo |
|---|---|---|---|---|---|
| 81036 | 100 | terreno | pending | skip_geocoding_pending | pasaria (p2) |
| 81038 | 100 | casa | pending | skip_geocoding_pending | pasaria (p2) |
| 81047 | 100 | local | **failed** | skip_geocoding_pending | **NO pasa** |
| 81041 | 80 | terreno | pending | skip_geocoding_pending | pasaria (p3) |
| 81042 | 80 | terreno | pending | skip_geocoding_pending | pasaria (p3) |
| 81044 | 80 | terreno | pending | skip_geocoding_pending | pasaria (p3) |
| 81048 | 80 | casa | **failed** | skip_geocoding_pending | **NO pasa** |
| 81057 | 65 | casa | pending | skip_geocoding_pending | pasaria (p3) |
| 81058 | 65 | casa | pending | skip_geocoding_pending | pasaria (p3) |
| 81059 | 65 | casa | pending | skip_geocoding_pending | pasaria (p3) |

**Nota:** `skip_geocoding_pending` es el nombre del motivo en el codigo, pero aplica a CUALQUIER geocoding_status fuera del set permitido {done, skipped} — incluye `failed`.

Con `--allow-pending-geo`: 8 adicionales pasarian (las 8 con pending). Las 2 failed (81047, 81048) siguen bloqueadas.

---

## Analisis de los checks de publish_queue

| Check | Resultado para nuestras 24 |
|---|---|
| `skip_missing_hash` | NINGUNA — todas tienen hash_dedup |
| `skip_missing_inmobiliaria` | NINGUNA — todas tienen inmobiliaria_id valido |
| `skip_missing_url` | NINGUNA — todas tienen URL |
| `skip_invalid_operation` | NINGUNA — todas tienen venta o alquiler validos |
| `skip_low_score` | NINGUNA — todas tienen score >= 65 > min_score=60 |
| `skip_geocoding_pending` | **10 props** — (5 pending + 3 pending watson + 2 failed) |
| `skip_already_queued` | NINGUNA — ninguna ha estado en publish_queue |
| Duplicados | NINGUNO |

**El unico freno para las 10 saltadas es el geocoding_status.**

---

## Falta de coordenadas — bloquea priority=1

**SI bloquea la prioridad maxima.** Ninguna de las 24 llega a priority=1 porque requiere simultaneamente:
- `validation_score >= 90` — algunas lo cumplen (score=100, 95)
- `geocoding_status == 'done'` — NINGUNA lo cumple (ninguna fue geocodificada con exito)
- `precio > 0` — 10 tienen precio, 14 no

Sin coordenadas, el maximo alcanzable es **priority=2**.

---

## Calidad real de las 14 encolables

Aunque 14 props "pasarian" a publish_queue, la calidad para el frontend es variable:

| Grupo | Props | Coordenadas | Ciudad | Precio | Titulos | Listas para frontend |
|---|---|---|---|---|---|---|
| inno score=95 con precio | 6 | NULL (no lat/lon) | Cafayate/Salta | SI | Normales | PARCIAL — sin mapa |
| inno score=75 sin precio | 4 | NULL | Cafayate/Salta | NO | Normales | DEBIL — sin precio ni mapa |
| camposdelapampa | 4 | NULL | NULL/La Pampa | NO | **Ca266.Html, Mo342.Html...** | NO — titulo inaceptable |

**La camposdelapampa no deberia publicarse**: titulo es el nombre del archivo HTML, no el nombre de la propiedad.

---

## Propuesta: agregar --ids-file a build_publish_queue.py

Cambio minimo necesario en `fetch_staging_rows()`:

```python
# ANTES
def fetch_staging_rows(cur, limit: int) -> List[Dict[str, Any]]:
    cur.execute(STAGING_SELECT_SQL, [limit])
    return [dict(row) for row in cur.fetchall()]

# DESPUES — agregar ids opcional
def fetch_staging_rows(cur, limit: int, ids: Optional[List[int]] = None) -> List[Dict[str, Any]]:
    if ids:
        placeholders = ", ".join(["%s"] * len(ids))
        cur.execute(f"""
            SELECT id, inmobiliaria_id, hash_dedup, url, url_normalizada,
                   operacion, precio, validation_score, geocoding_status, status
            FROM public.propiedades_staging
            WHERE status = 'staging' AND id IN ({placeholders})
            ORDER BY validation_score DESC, id ASC
            LIMIT %s
        """, ids + [limit])
    else:
        cur.execute(STAGING_SELECT_SQL, [limit])
    return [dict(row) for row in cur.fetchall()]
```

Mas agregar `--ids-file` al parser de argumentos (identico al patron de geocode_staging.py).

Este cambio es seguro, no rompe comportamiento existente (ids=None = comportamiento actual).
**Requiere git commit para activarse — pendiente de autorizacion.**

---

## Seguridad

| Verificacion | Estado |
|---|---|
| Script ejecutado con commit | NO — simulacion manual |
| publish_queue modificado | NO |
| propiedades_staging modificado | NO |
| Supabase tocado | NO |
| .env modificado | NO |
| git commit | NO |
| datos historicos procesados | NO |

---

*Simulacion equivalente a dry-run realizada el 2026-06-06 sobre datos reales de Neon.*
