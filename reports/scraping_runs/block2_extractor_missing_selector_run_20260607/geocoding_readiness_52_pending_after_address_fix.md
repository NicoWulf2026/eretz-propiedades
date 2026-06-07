# Geocoding Readiness — 52 Pending Props AFTER Fix K (Address Validation Fix)

**Fecha:** 2026-06-07  
**Scope:** staging IDs 81276–81327 (52 propiedades pendientes de geocoding)  
**Fix aplicado:** Fix K — validación y extracción de dirección desde título  
**Modo:** dry-run (0 requests Nominatim, accion=rollback, sin escrituras)

---

## Resumen comparativo

| Métrica              | Antes Fix K | Después Fix K | Δ  |
|----------------------|-------------|---------------|----|
| probe                | 51          | 47            | −4 |
| skipped              | 1           | 5             | +4 |
| requests usados      | 0           | 0             | —  |
| **Direcciones reales corregidas** | 0 | **7** | +7 |
| **Falsos probes eliminados** | 0 | **4** | +4 |

> El descenso de 4 probes refleja eliminación de falsos geocodeos (props sin dirección real).  
> Las 7 correcciones mejoran la calidad efectiva del geocoding real cuando se autorice.

---

## Cambios propiedad por propiedad

### ✅ Direcciones recuperadas desde título (7 props)

| staging_id | Dominio | Dirección mala en DB | Dirección recuperada | accion post-fix |
|------------|---------|----------------------|----------------------|-----------------|
| 81277 | luciafrolik | `compartimentado. Sobre un lote de 15` | `Pavón 1171` | probe ← era **skipped** |
| 81296 | tonyzorrilla | `de febrero de 2025` | `M.M. Güemes C 88` | probe |
| 81298 | tonyzorrilla | `de noviembre de 2024` | `Embarcación Santa Lucía 1236` | probe |
| 81303 | tonyzorrilla | `de julio de 2024` | `Pridiliano Pueyrredón 730` | probe |
| 81307 | tonyzorrilla | `de febrero de 2018` | `Av. Libertad y 1 de Mayo` | **skipped** (intersection, readiness=geocoding_ready_review) |
| 81308 | tonyzorrilla | `de mayo de 2017` | `Cacique Nahuelpán 814` | probe |
| 81309 | tonyzorrilla | `de mayo de 2025` | `Cacique Nahuelpán 1158` | probe |

**Nota 81307:** La dirección recuperada "Av. Libertad y 1 de Mayo" es una intersección (sin altura), 
readiness=geocoding_ready_review → skipped por política del geocoder. Comportamiento correcto: 
no se intenta geocodear intersecciones sin confirmar manualmente.

### ❌ Props sin dirección recuperable → correctamente skipped (4 props)

| staging_id | Dominio | Dirección mala en DB | Motivo no recuperable | accion post-fix |
|------------|---------|----------------------|-----------------------|-----------------|
| 81284 | luciafrolik | `tanto en su estructura y detalles. 677` | Título "Casas en Venta - Fleming" — sin altura | **skipped** (garbage_address) ← era probe |
| 81317 | dilello | `C.M.P. Consultas Online 2477` | Título solo tiene barrio/nombre urbanización | **skipped** (garbage_address) ← era probe |
| 81318 | dilello | `C.M.P. Consultas Online 2477` | Título solo tiene barrio/nombre urbanización | **skipped** (garbage_address) ← era probe |
| 81323 | dilello | `C.M.P. Consultas Online 2477` | Título solo tiene barrio/nombre urbanización | **skipped** (garbage_address) ← era probe |

---

## Estado post-fix de las 52 props

### 47 probe (geocoding_ready_safe)

```
81276  Paz 121 — Tandil (luciafrolik)
81277  Pavón 1171 — Tandil (luciafrolik) [RECUPERADA DESDE TÍTULO]
81278  Piedrabuena 87 — Tandil
81279  Larreal al 900 — Tandil
81280  de mayo al 100 — Tandil [parcial pero válida]
81281  de Andrea al 200 — Tandil [parcial pero válida]
81282  Dr Pere al 1600 — Tandil
81283  Los Aromos 1400 — Tandil
81285  Fontana 400 — Tandil
81286  Linstown 400 — Tandil
81287  Paso de los Andes al 400 — Tandil
81288  Sheffield 667 — Playa Unión
81289  Rivadavia Nº 860 — Rawson
81290  Yrigoyen N° 266 — Rawson
81291  Facundo Quiroga N° 618 — Rawson
81292  Rawson 17 — [RISKY: "Rawson" como calle]
81293  Amancay N° 186 — Rawson
81294  Rawson 14 — [RISKY: "Rawson" como calle]
81295  Los Cipreses 446 B — Rawson
81296  [DB: de feb 2025] → M.M. Güemes C 88 — Rawson [RECUPERADA]
81297  Pasaje Inmigrantes 368 — Rawson
81298  [DB: de nov 2024] → Embarcación Santa Lucía 1236 — Playa Unión [RECUPERADA]
81299  Cacique Chiquichano 1923 — Playa Unión
81300  Valle 125 — Rawson (parcial)
81301  Trinidad 130 — Playa Unión
81302  Rifleros 227 — Playa Unión
81303  [DB: de jul 2024] → Pridiliano Pueyrredón 730 — Playa Unión [RECUPERADA]
81304  Rawson 25 — [RISKY: "Rawson" como calle]
81305  Av. Sarmiento al 600 — Rawson
81306  Rivadavia 360 — Rawson
81308  [DB: de may 2017] → Cacique Nahuelpán 814 — Playa Unión [RECUPERADA]
81309  [DB: de may 2025] → Cacique Nahuelpán 1158 — Playa Unión [RECUPERADA]
81310  Castelli 544 — Rawson
81311  Jujuy 22 — Rawson
81312  Tte. Cnel. Palacios N° 743 — Rawson
81313  Guiraldes 571 — Rawson
81314  Don Victor 1448 — Playa Unión (parcial)
81315  Nahuelpan 585 — Playa Unión
81316  Ushuaia 130 — Rawson
81319  Dr. Alem 147 — Pergamino
81320  DE FEBRERO AL 500 — Pergamino [válida: no es fecha, es calle "3 de Febrero"]
81321  PRUDENCIO GONZALEZ AL 300 — Pergamino
81322  MERCED AL 300 — Pergamino
81324  SAN LUIS 900 — Pergamino
81325  Andrade 1200 — Pergamino
81326  Diego de la fuente 1130 — Pergamino
81327  SARRATEA AL 500 — Pergamino
```

### 5 skipped

| staging_id | Razón | readiness |
|------------|-------|-----------|
| 81284 | overflow descripción, título sin altura ("Fleming") | garbage_address |
| 81307 | Intersección "Av. Libertad y 1 de Mayo" sin altura | geocoding_ready_review |
| 81317 | Contacto dilello, título sin calle | garbage_address |
| 81318 | Contacto dilello, título sin calle | garbage_address |
| 81323 | Contacto dilello, título sin calle | garbage_address |

---

## Mecánica del Fix K (resumen técnico)

### Archivos modificados

| Archivo | Cambio |
|---------|--------|
| `scraper/scraper_propiedades.py` | +8 constantes regex, +5 funciones de detección/extracción, hook en `_html_extract_detail()` |
| `scripts/validate_raw_properties.py` | Import Fix K fns, "consultas online" en GARBAGE_PATTERNS, date+contact en `invalid_address_reason()`, title fallback en validate_row() |
| `scripts/import_captured_props_to_neon.py` | Mismos cambios que validate |
| `scripts/geocode_staging.py` | Import Fix K fns, safety net en `build_geocoder_row()` |

### Flujo de la corrección

```
scraper (prevención futura):
  _html_extract_detail():
    address_raw = <CSS selectors>
    if not address_raw: address_raw = _extract_address_from_text(page_text)
    if address_raw and _is_invalid_scraped_address(address_raw): address_raw = ""
    if not address_raw:
        _addr_from_title = _extract_address_from_titulo(title)
        if _addr_from_title: address_raw = _addr_from_title

geocode_staging (safety net para datos ya staged):
  build_geocoder_row():
    direccion = normalize_address_for_geocoding(staging["direccion_normalizada"])
    if pipeline_is_invalid_scraped_address(direccion):
        _inferred = pipeline_extract_address_from_titulo(staging["titulo"])
        if _inferred: direccion = _inferred
        else: direccion = ""  # → is_garbage_address → skipped
```

### Patrones detectados como inválidos

- **Fecha:** `de febrero de 2025`, `14 de marzo de 2024`, `noviembre 2024` (regex `_DATE_ADDRESS_RE`)
- **Contacto:** `consultas online`, `c.m.p.`, `nuestra oficina` (regex `_CONTACT_ADDRESS_RE`)
- **Overflow descripción:** `compartimentado`, `en su estructura`, `sobre un lote` + len>100 (`_DESCRIPTION_OVERFLOW_RE`)

### Extracción desde título — patrones soportados

```
"{Tipo} en {oper}, {Calle Nro}, {Ciudad}"          → "Calle Nro"
"{Tipo} en {oper}, {Calle Nro} – {Barrio}, {Ciudad}"→ "Calle Nro"
"{Tipo} en {oper} – {Calle Nro}, {Ciudad}"          → "Calle Nro"
"{Categoría} - {Calle Nro}"                          → "Calle Nro"
```

Requiere al menos un dígito. No hardcodea dominios ni ciudades.

---

## Próximos pasos (pendientes de autorización)

1. **`--commit` geocoding** cuando se autorice: las 47 probes están listas.
   - 5 skipped esperan: 81284 (agregar altura a título), 81307 (confirmar intersección manualmente), 81317/81318/81323 (dilello sin calle — no geocodeables).
2. **`build_publish_queue.py`** — NO tocar hasta autorización explícita.
3. **`publish_to_supabase.py`** — NO tocar hasta autorización explícita.
