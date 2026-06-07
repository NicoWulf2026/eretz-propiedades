# Validate raw → staging — Dry-run con Fix J (54 props)

- Fecha: 2026-06-07
- Modo: **DRY-RUN** — rollback, sin escritura a staging
- Script: `scripts/validate_raw_properties.py --ids-file ...`
- IDs: raw 82081–82134 (54 props)
- Fix activo: **Fix J** — location enrichment desde título/URL

---

## 1. Resultado del dry-run

```
filas_leidas              = 54
validadas                 = 54   <- todas pasarían a staging
rechazadas                =  0
duplicadas                =  0
issues_por_tipo:
  location_inferred_from_text: 40
accion_final              = rollback
```

---

## 2. Comparativa antes/después de Fix J

| Métrica | Sin Fix J | Con Fix J |
|---|---|---|
| Validadas | 54 | 54 |
| Rechazadas | 0 | 0 |
| **missing_location** | **40** | **0** OK |
| **location_inferred_from_text** | **0** | **40** OK |
| Duplicadas | 0 | 0 |

---

## 3. Desglose por dominio

### tonyzorrilla.com.ar — 29 props

| Ciudad | Props | Método de inferencia | Motivo |
|---|---|---|---|
| Rawson, Chubut | 19 | Título termina en ", Rawson" | `titulo_termina_en_rawson` |
| Playa Unión, Chubut | 10 | "playa union" en texto título+URL | `titulo_url_contiene_playa_union` |
| **Total inferidos** | **29** | | |

**Nota técnica**: 3 props tenían `direccion_raw = "Rawson NN"` (calle Rawson con número), que contaminaba la detección por alias. El check `,\s*rawson$` en título (antes del loop de aliases) evita este conflicto.

### dilellopropiedades.com — 11 props

| Ciudad | Props | Método de inferencia | Motivo |
|---|---|---|---|
| Pergamino, Buenos Aires | 11 | "pergamino" en texto título+URL | `titulo_url_contiene_pergamino` |
| **Total inferidos** | **11** | | |

**Nota técnica**: id=82129 tenía `"San Luis 900"` en dirección/URL. `_explicit_province_from_text()` detectaba "San Luis" como provincia y bloqueaba el alias de Pergamino. Fix: `specific=True` en la entrada de pergamino en `_LOCATION_ALIASES`.

---

## 4. Implementación Fix J — Resumen técnico

**Archivo modificado**: `scraper/scraper_propiedades.py`

### Cambio 1 — Nuevas entradas en `_LOCATION_ALIASES`

```python
{
    "aliases": ("pergamino",),
    "ciudad": "Pergamino",
    "provincia": "Buenos Aires",
    "specific": True,   # evita bloqueo por "San Luis" como calle
    "motivo": "titulo_url_contiene_pergamino",
},
{
    "aliases": ("playa union", "playa-union"),
    "ciudad": "Playa Unión",
    "provincia": "Chubut",
    "specific": True,
    "motivo": "titulo_url_contiene_playa_union",
},
```

### Cambio 2 — Check inline en `_detect_location_from_text()`

```python
# Fix J: "Rawson" al final del título precedido de coma -> Rawson, Chubut
if titulo and re.search(r",\s*rawson\s*$", str(titulo).strip(), re.I | re.UNICODE):
    return {"ciudad": "Rawson", "provincia": "Chubut", "motivo": "titulo_termina_en_rawson"}
```

**Por qué no en `_LOCATION_ALIASES`**: "rawson" es ambiguo como nombre de calle; el patrón `,\s*rawson$` es más restrictivo y evita falsos positivos.

### Cambio 3 — Nueva dict + función `_infer_city_from_url_slug_last_segment()`

Defensa en profundidad (fallback en `normalize_location_fields()`):
```python
_URL_SLUG_CITY_TOKENS = {
    "playaunion": ("Playa Unión", "Chubut"),       # redundancia con alias
    "pergamino":  ("Pergamino",   "Buenos Aires"),  # redundancia con alias
    # "rawson" excluido: manejado por check de título
}
```

---

## 5. Geocoding_status esperado en staging

| Dominio | Props | Ciudad inferida | geocoding_status |
|---|---|---|---|
| luciafrolik | 12 | Tandil, BA (en raw ya) | pending con ciudad OK |
| escuza | 2 | Tandil, BA (en raw ya) | pending con ciudad OK |
| tonyzorrilla | 19 | Rawson, Chubut (Fix J) | pending con ciudad OK |
| tonyzorrilla | 10 | Playa Unión, Chubut (Fix J) | pending con ciudad OK |
| dilello | 11 | Pergamino, BA (Fix J) | pending con ciudad OK |
| **TOTAL** | **54** | **54/54 con ciudad** | **54 x pending** |

---

## 6. ¿Es seguro hacer validate --commit?

**SÍ. Sin reservas.**

| Check | Estado |
|---|---|
| 54/54 validadas | OK |
| 0 rechazadas | OK |
| 0 duplicadas en staging | OK |
| 0 campos críticos faltantes | OK |
| 0 missing_location (vs 40 sin Fix J) | OK |
| 40 con ciudad inferida + trazabilidad (motivo) | OK |
| staging intacto: max_id 81,059 / 76,487 rows | OK |
| staging esperado: ~76,541 rows (+54) | — |

**Observaciones menores (no bloquean):**
- 3 props dilello con `direccion_raw = "C.M.P. Consultas Online 2477"` (dirección de oficina) — pasan a staging, no causan rechazo
- 2 props luciafrolik con `direccion_raw` con overflow de descripción — ídem

---

## 7. Comando para validate --commit (cuando se autorice)

```bash
USE_INTERNAL_DB=true python scripts/validate_raw_properties.py \
  --ids-file "reports/scraping_runs/block2_extractor_missing_selector_run_20260607/raw_ids_54_props.csv" \
  --commit \
  --report "reports/scraping_runs/block2_extractor_missing_selector_run_20260607/validate_raw_commit_54_props.md"
```

---

## 8. Controles de seguridad

| Control | Estado |
|---|---|
| staging | NO modificado OK |
| geocoding_results | NO tocada OK |
| publish_queue | NO modificada OK |
| Supabase | NO tocada OK |
| .env | NO modificado OK |
| git push | NO ejecutado OK |

---

## FASE 6 — Freno activo

**STATUS: EN ESPERA DE AUTORIZACIÓN PARA validate --commit**

Dry-run exitoso con Fix J: 54/54 pasan, 0 missing_location, 40 ciudades inferidas con trazabilidad.

---

*Dry-run: 2026-06-07 · raw 82081--82134 · Fix J aplicado · accion=rollback · rama fix/scraping-diagnostics-batch*
