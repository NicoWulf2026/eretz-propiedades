# Reporte de commit real — 24 propiedades a propiedades_raw

- Fecha: 2026-06-06 17:13
- Modo: **commit** (import real a Neon)
- Destino: `public.propiedades_raw`
- Batch origen: `internal_batch_20260606_1129`
- Fixes activos: B + C + D + E + G

---

## Resultado

| Métrica | Valor |
|---|---|
| archivos_leidos | 3 |
| propiedades_detectadas | 24 |
| propiedades_procesadas | 24 |
| **importadas (filas reales en Neon)** | **24** |
| rechazadas | 0 |
| duplicados bloqueados (raw) | 0 |
| duplicados bloqueados (staging) | 0 |
| duplicados dentro del batch | 0 |

---

## Issues registrados por tipo

| Issue | Count | Significado |
|---|---|---|
| `source_test_mode_id_rewritten` | 24 | inmobiliaria_id resuelto desde batch CSV (esperado) |
| `missing_location` | 24 | sin ciudad/provincia — Fix A pendiente |
| `office_address_suspected` | 10 | Fix C: "San Martin Nº 191" nullificada (innoacafayate) |
| `operation_inferred_from_url_path` | 6 | Fix B: operación corregida desde `/alquiler/` en URL |
| `invalid_address` | 4 | Fix D: dominio `camposdelapampa.com.ar` como dirección nullificado |
| `low_quality_score` | 3 | Watson sin precio — Fix F pendiente |
| `tipo_inferred_from_rural_domain` | 3 | Fix E: tipo_propiedad corregido de departamento → campo |

---

## Detalle por inmobiliaria

### innoacafayate.com — 17 props (id: 5282)

| Campo | Valor final en Neon |
|---|---|
| operacion | 11 × venta, 6 × alquiler ← Fix B corrigió |
| tipo_propiedad | asignado por scraper |
| direccion_raw | 7 props con dirección real; 10 × NULL ← Fix C |
| ciudad / provincia | NULL (pendiente Fix A) |
| precio | 9 props con precio; 8 × NULL |

### camposdelapampa.com.ar — 4 props (id: 1443)

| Campo | Valor final en Neon |
|---|---|
| operacion | 4 × venta |
| tipo_propiedad | 4 × campo ← Fix E corrigió 3 (1 ya era campo) |
| direccion_raw | 4 × NULL ← Fix D (dominio como dirección) |
| ciudad / provincia | NULL |
| precio | NULL (sin precio en HTML estático) |

### watsonpropiedades.com — 3 props (id: 6162)

| Campo | Valor final en Neon |
|---|---|
| operacion | 3 × venta |
| tipo_propiedad | asignado por scraper |
| direccion_raw | NULL |
| ciudad / provincia | NULL |
| precio | NULL ← Fix F pendiente |
| score_calidad | 40 (low_quality_score) |

---

## Confirmación de seguridad

| Verificación | Estado |
|---|---|
| Supabase tocado | ✗ NO |
| publish_to_supabase.py ejecutado | ✗ NO |
| publish_queue modificado | ✗ NO |
| geocoding ejecutado | ✗ NO |
| validate_staging con commit | ✗ NO |
| frontend/ modificado | ✗ NO |
| `.env` modificado | ✗ NO (sigue con `USE_INTERNAL_DB=false`) |
| `USE_INTERNAL_DB` seteado | Solo en sesión — no persiste |
| git commit ejecutado | ✗ NO |
| git push ejecutado | ✗ NO |
| datos borrados | ✗ NO |
| schema modificado | ✗ NO |
| procesos Python activos post-commit | ✗ ninguno |

---

## Archivos tocados por el proceso

| Archivo | Motivo |
|---|---|
| `reports/scraping_autofix/import_captured_20260606_24_extractor_fix.md` | Reporte generado por el importer |
| `reports/scraping_autofix/master_progress.md` | Log interno de progreso |

---

## Estado post-commit en Neon

- `propiedades_raw`: +24 filas con `status=raw`
- `propiedades_staging`: sin cambios (validate_staging no ejecutado)
- `geocoding_results`: sin cambios
- `scraping_run_items`: sin cambios

---

## Issues pendientes para próximos ciclos

| Issue | Fix | Prioridad |
|---|---|---|
| `missing_location` (24/24) | Fix A — inferencia desde hostname | Media |
| `watson sin precio` (3 props) | Fix F — inspeccionar HTML watson | Baja |
| `tipo_propiedad` futuras capturas camposdelapampa | Fix E aplicado en scraper | Resuelto para futuras |
